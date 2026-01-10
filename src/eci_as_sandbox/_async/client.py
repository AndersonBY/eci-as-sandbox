from __future__ import annotations

import json
import os
import random
import shlex
import string
from typing import Any, Dict, Optional

from alibabacloud_eci20180808 import models as eci_models
from alibabacloud_eci20180808.client import Client as EciClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from .._common.config import Config, _load_config
from .._common.exceptions import AuthenticationError
from .._common.logger import (
    _log_api_call,
    _log_api_response,
    _log_operation_error,
    get_logger,
)
from .._common.models import (
    CommandResult,
    DeleteResult,
    GetSandboxResult,
    OperationResult,
    SandboxInfo,
    SandboxListResult,
    AsyncSandboxResult,
    extract_request_id,
)
from .sandbox import AsyncSandbox


_logger = get_logger("eci-as-sandbox.async")


class AsyncEciSandbox:
    def __init__(
        self,
        access_key_id: str = "",
        access_key_secret: str = "",
        cfg: Optional[Config] = None,
        env_file: Optional[str] = None,
        security_token: str = "",
        region_id: str = "",
    ):
        config_data = _load_config(cfg, env_file)

        if not access_key_id:
            access_key_id = (
                os.getenv("ECI_SANDBOX_ACCESS_KEY_ID")
                or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
                or ""
            )
        if not access_key_secret:
            access_key_secret = (
                os.getenv("ECI_SANDBOX_ACCESS_KEY_SECRET")
                or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
                or ""
            )

        if not access_key_id or not access_key_secret:
            raise AuthenticationError(
                "Access key is required. Provide it or set ALIBABA_CLOUD_ACCESS_KEY_ID "
                "and ALIBABA_CLOUD_ACCESS_KEY_SECRET."
            )

        if not region_id:
            region_id = config_data.get("region_id") or ""
        if not region_id:
            raise AuthenticationError(
                "Region ID is required. Provide it or set ALIBABA_CLOUD_REGION_ID."
            )

        self.region_id = region_id
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.security_token = security_token

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            security_token=security_token,
            endpoint=config_data["endpoint"],
            region_id=region_id,
            read_timeout=config_data["timeout_ms"],
            connect_timeout=config_data["timeout_ms"],
        )

        self.client = EciClient(config)
        self._sandboxes: Dict[str, AsyncSandbox] = {}

    def _generate_name(self, prefix: str = "sandbox") -> str:
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        name = f"{prefix}-{suffix}".lower()
        return name[:128].strip("-")

    def _normalize_name(self, name: str) -> str:
        sanitized = []
        for ch in name.lower():
            if ch.isalnum() or ch == "-":
                sanitized.append(ch)
            else:
                sanitized.append("-")
        normalized = "".join(sanitized).strip("-")
        if len(normalized) < 2:
            normalized = self._generate_name()
        return normalized[:128].strip("-")

    def _build_tags(self, tags: Dict[str, str]):
        tag_list = []
        for key, value in tags.items():
            tag_list.append(
                eci_models.CreateContainerGroupRequestTag(key=key, value=value)
            )
        return tag_list

    def _build_list_tags(self, tags: Dict[str, str]):
        tag_list = []
        for key, value in tags.items():
            tag_list.append(
                eci_models.DescribeContainerGroupsRequestTag(key=key, value=value)
            )
        return tag_list

    async def create(
        self,
        image: str,
        name: Optional[str] = None,
        container_name: str = "sandbox",
        cpu: float = 1.0,
        memory: float = 2.0,
        command: Optional[list[str]] = None,
        args: Optional[list[str]] = None,
        env: Optional[Dict[str, str]] = None,
        ports: Optional[list[dict[str, Any]]] = None,
        v_switch_id: Optional[str] = None,
        security_group_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        instance_type: Optional[str] = None,
        restart_policy: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        auto_create_eip: bool = False,
        eip_bandwidth: Optional[int] = None,
        eip_instance_id: Optional[str] = None,
    ) -> AsyncSandboxResult:
        if not image:
            return AsyncSandboxResult(success=False, error_message="image is required")

        group_name = self._normalize_name(name or self._generate_name())
        env = env or {}
        ports = ports or []
        tags = tags or {}

        env_vars = [
            eci_models.CreateContainerGroupRequestContainerEnvironmentVar(
                key=k, value=v
            )
            for k, v in env.items()
        ]
        port_configs = []
        for port in ports:
            if not isinstance(port, dict):
                continue
            raw_port = port.get("port")
            if isinstance(raw_port, str) and raw_port.isdigit():
                raw_port = int(raw_port)
            if not isinstance(raw_port, int):
                continue
            protocol = port.get("protocol", "TCP")
            port_configs.append(
                eci_models.CreateContainerGroupRequestContainerPort(
                    port=raw_port,
                    protocol=str(protocol),
                )
            )

        container = eci_models.CreateContainerGroupRequestContainer(
            name=container_name,
            image=image,
            cpu=cpu,
            memory=memory,
            command=command or [],
            arg=args or [],
            environment_var=env_vars,
            port=port_configs,
        )

        request = eci_models.CreateContainerGroupRequest(
            region_id=self.region_id,
            container_group_name=group_name,
            container=[container],
            cpu=cpu,
            memory=memory,
        )

        if instance_type:
            request.instance_type = instance_type
        if v_switch_id:
            request.v_switch_id = v_switch_id
        if security_group_id:
            request.security_group_id = security_group_id
        if zone_id:
            request.zone_id = zone_id
        if restart_policy:
            request.restart_policy = restart_policy
        if tags:
            request.tag = self._build_tags(tags)
        if auto_create_eip:
            request.auto_create_eip = auto_create_eip
        if eip_bandwidth is not None:
            request.eip_bandwidth = eip_bandwidth
        if eip_instance_id:
            request.eip_instance_id = eip_instance_id

        _log_api_call("CreateContainerGroup", f"Name={group_name}, Image={image}")

        try:
            response = await self.client.create_container_group_async(request)
            request_id = extract_request_id(response)
            body = response.to_map().get("body", {})
            sandbox_id = body.get("ContainerGroupId", "")

            if not sandbox_id:
                _log_api_response("CreateContainerGroup", request_id, False)
                return AsyncSandboxResult(
                    request_id=request_id,
                    success=False,
                    error_message="ContainerGroupId not found in response",
                )

            sandbox = AsyncSandbox(self, sandbox_id, container_name=container_name)
            self._sandboxes[sandbox_id] = sandbox

            _log_api_response(
                "CreateContainerGroup",
                request_id,
                True,
                {"sandbox_id": sandbox_id},
            )
            return AsyncSandboxResult(
                request_id=request_id,
                success=True,
                sandbox=sandbox,
            )
        except Exception as exc:
            _log_operation_error("CreateContainerGroup", str(exc), exc_info=True)
            return AsyncSandboxResult(
                request_id="",
                success=False,
                error_message=f"Failed to create sandbox: {exc}",
            )

    async def get_sandbox_info(self, sandbox_id: str) -> OperationResult:
        if not sandbox_id:
            return OperationResult(
                success=False, error_message="sandbox_id is required"
            )

        request = eci_models.DescribeContainerGroupsRequest(
            region_id=self.region_id,
            container_group_ids=json.dumps([sandbox_id]),
        )

        _log_api_call("DescribeContainerGroups", f"ContainerGroupId={sandbox_id}")

        try:
            response = await self.client.describe_container_groups_async(request)
            request_id = extract_request_id(response)
            body = response.to_map().get("body", {})
            groups = body.get("ContainerGroups", []) or []

            if not groups:
                return OperationResult(
                    request_id=request_id,
                    success=False,
                    error_message=f"Sandbox {sandbox_id} not found",
                )

            info = SandboxInfo.from_group(groups[0])
            _log_api_response(
                "DescribeContainerGroups",
                request_id,
                True,
                {"sandbox_id": info.sandbox_id, "status": info.status},
            )
            return OperationResult(
                request_id=request_id,
                success=True,
                data=info,
            )
        except Exception as exc:
            _log_operation_error("DescribeContainerGroups", str(exc), exc_info=True)
            return OperationResult(
                request_id="",
                success=False,
                error_message=f"Failed to describe sandbox {sandbox_id}: {exc}",
            )

    async def get_sandbox(self, sandbox_id: str) -> GetSandboxResult:
        info_result = await self.get_sandbox_info(sandbox_id)
        if not info_result.success:
            return GetSandboxResult(
                request_id=info_result.request_id,
                success=False,
                error_message=info_result.error_message,
            )
        return GetSandboxResult(
            request_id=info_result.request_id,
            success=True,
            data=info_result.data,
        )

    async def get(self, sandbox_id: str) -> AsyncSandboxResult:
        info_result = await self.get_sandbox_info(sandbox_id)
        if not info_result.success:
            return AsyncSandboxResult(
                request_id=info_result.request_id,
                success=False,
                error_message=info_result.error_message,
            )

        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None:
            sandbox = AsyncSandbox(self, sandbox_id)
            self._sandboxes[sandbox_id] = sandbox

        return AsyncSandboxResult(
            request_id=info_result.request_id,
            success=True,
            sandbox=sandbox,
        )

    async def list(
        self,
        limit: int = 20,
        next_token: str = "",
        status: Optional[str] = None,
        name: Optional[str] = None,
        security_group_id: Optional[str] = None,
        v_switch_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> SandboxListResult:
        limit = min(max(limit, 1), 20)
        tags = tags or {}
        request = eci_models.DescribeContainerGroupsRequest(
            region_id=self.region_id,
            limit=limit,
        )

        if next_token:
            request.next_token = next_token
        if status:
            request.status = status
        if name:
            request.container_group_name = name
        if security_group_id:
            request.security_group_id = security_group_id
        if v_switch_id:
            request.v_switch_id = v_switch_id
        if tags:
            request.tag = self._build_list_tags(tags)

        _log_api_call(
            "DescribeContainerGroups", f"Limit={limit}, Status={status or ''}"
        )

        try:
            response = await self.client.describe_container_groups_async(request)
            request_id = extract_request_id(response)
            body = response.to_map().get("body", {})
            groups = body.get("ContainerGroups", []) or []
            sandbox_ids: list[str] = []
            for group in groups:
                if not isinstance(group, dict):
                    continue
                sandbox_id = group.get("ContainerGroupId")
                if isinstance(sandbox_id, str) and sandbox_id:
                    sandbox_ids.append(sandbox_id)
            next_token = body.get("NextToken", "")
            total_count = int(body.get("TotalCount", len(sandbox_ids)))

            _log_api_response(
                "DescribeContainerGroups",
                request_id,
                True,
                {"returned": len(sandbox_ids), "total": total_count},
            )
            return SandboxListResult(
                request_id=request_id,
                success=True,
                sandbox_ids=sandbox_ids,
                next_token=next_token,
                max_results=limit,
                total_count=total_count,
            )
        except Exception as exc:
            _log_operation_error("DescribeContainerGroups", str(exc), exc_info=True)
            return SandboxListResult(
                request_id="",
                success=False,
                sandbox_ids=[],
                error_message=f"Failed to list sandboxes: {exc}",
            )

    async def delete(self, sandbox_id: str, force: bool = False) -> DeleteResult:
        if not sandbox_id:
            return DeleteResult(success=False, error_message="sandbox_id is required")

        request = eci_models.DeleteContainerGroupRequest(
            region_id=self.region_id,
            container_group_id=sandbox_id,
            force=force,
        )

        _log_api_call("DeleteContainerGroup", f"ContainerGroupId={sandbox_id}")

        try:
            response = await self.client.delete_container_group_async(request)
            request_id = extract_request_id(response)
            _log_api_response(
                "DeleteContainerGroup",
                request_id,
                True,
                {"sandbox_id": sandbox_id},
            )
            self._sandboxes.pop(sandbox_id, None)
            return DeleteResult(request_id=request_id, success=True)
        except Exception as exc:
            _log_operation_error("DeleteContainerGroup", str(exc), exc_info=True)
            return DeleteResult(
                request_id="",
                success=False,
                error_message=f"Failed to delete sandbox {sandbox_id}: {exc}",
            )

    async def restart(self, sandbox_id: str) -> OperationResult:
        if not sandbox_id:
            return OperationResult(
                success=False, error_message="sandbox_id is required"
            )

        request = eci_models.RestartContainerGroupRequest(
            region_id=self.region_id,
            container_group_id=sandbox_id,
        )

        _log_api_call("RestartContainerGroup", f"ContainerGroupId={sandbox_id}")

        try:
            response = await self.client.restart_container_group_async(request)
            request_id = extract_request_id(response)
            _log_api_response(
                "RestartContainerGroup",
                request_id,
                True,
                {"sandbox_id": sandbox_id},
            )
            return OperationResult(request_id=request_id, success=True)
        except Exception as exc:
            _log_operation_error("RestartContainerGroup", str(exc), exc_info=True)
            return OperationResult(
                request_id="",
                success=False,
                error_message=f"Failed to restart sandbox {sandbox_id}: {exc}",
            )

    async def exec_command(
        self,
        sandbox_id: str,
        command: list[str],
        container_name: Optional[str] = None,
        sync: bool = True,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        if not sandbox_id:
            return CommandResult(success=False, error_message="sandbox_id is required")
        if not command:
            return CommandResult(success=False, error_message="command is required")

        if not container_name:
            container_name = await self._resolve_container_name(sandbox_id)
        if not container_name:
            return CommandResult(
                success=False,
                error_message="container_name is required",
            )

        log_path = None
        if sync and timeout is not None:
            log_path = (
                f"/tmp/eci_sandbox_exec_{int(random.random() * 1_000_000_000)}.log"
            )
            command = self._wrap_command_for_log(command, log_path)

        command_json = json.dumps(command, ensure_ascii=False)

        _log_api_call(
            "ExecContainerCommand",
            f"ContainerGroupId={sandbox_id}, Container={container_name}",
        )

        try:
            response = await self._exec_container_command(
                sandbox_id=sandbox_id,
                container_name=container_name,
                command_json=command_json,
                sync=sync,
                timeout=timeout,
            )
            request_id = extract_request_id(response)
            body = response.to_map().get("body", {})
            output = body.get("SyncResponse", "") if sync else ""
            if log_path:
                output = (
                    await self._read_log_output(sandbox_id, container_name, log_path)
                    or output
                )
            http_url = body.get("HttpUrl", "")
            websocket_url = body.get("WebSocketUri", "")
            _log_api_response(
                "ExecContainerCommand",
                request_id,
                True,
                {"sandbox_id": sandbox_id, "container": container_name},
            )
            return CommandResult(
                request_id=request_id,
                success=True,
                output=output,
                http_url=http_url,
                websocket_url=websocket_url,
            )
        except Exception as exc:
            output = ""
            if log_path:
                output = await self._read_log_output(
                    sandbox_id, container_name, log_path
                )
            _log_operation_error("ExecContainerCommand", str(exc), exc_info=True)
            return CommandResult(
                request_id="",
                success=False,
                output=output,
                error_message=f"Failed to exec command: {exc}",
            )

    async def bash(
        self,
        sandbox_id: str,
        command: str,
        exec_dir: Optional[str] = None,
        container_name: Optional[str] = None,
        sync: bool = True,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        if not command:
            return CommandResult(success=False, error_message="command is required")
        if exec_dir:
            command = f"cd {shlex.quote(exec_dir)} && {command}"
        return await self.exec_command(
            sandbox_id=sandbox_id,
            command=["bash", "-lc", command],
            container_name=container_name,
            sync=sync,
            timeout=timeout,
        )

    async def _resolve_container_name(self, sandbox_id: str) -> str:
        info_result = await self.get_sandbox_info(sandbox_id)
        if not info_result.success or not info_result.data:
            return ""
        containers = info_result.data.containers or []
        if not containers:
            return ""
        first = containers[0]
        if isinstance(first, dict):
            return first.get("Name", "") or first.get("name", "")
        return ""

    async def _exec_container_command(
        self,
        sandbox_id: str,
        container_name: str,
        command_json: str,
        sync: bool,
        timeout: Optional[float],
    ):
        request = eci_models.ExecContainerCommandRequest(
            region_id=self.region_id,
            container_group_id=sandbox_id,
            container_name=container_name,
            command=command_json,
            sync=sync,
            tty=False,
            stdin=False,
        )
        if timeout is None:
            return await self.client.exec_container_command_async(request)
        timeout_ms = int(timeout * 1000)
        runtime = util_models.RuntimeOptions(
            read_timeout=timeout_ms,
            connect_timeout=timeout_ms,
        )
        return await self.client.exec_container_command_with_options_async(
            request, runtime
        )

    def _wrap_command_for_log(self, command: list[str], log_path: str) -> list[str]:
        if len(command) >= 2 and command[0] in {"/bin/sh", "sh"} and command[1] == "-c":
            inner = command[2] if len(command) > 2 else ""
            shell_cmd = inner
        else:
            shell_cmd = " ".join(shlex.quote(part) for part in command)
        wrapped = f"{shell_cmd} > {log_path} 2>&1"
        return ["/bin/sh", "-c", wrapped]

    async def _read_log_output(
        self,
        sandbox_id: str,
        container_name: str,
        log_path: str,
    ) -> str:
        command = [
            "/bin/sh",
            "-c",
            f"tail -n 200 {log_path} 2>/dev/null || cat {log_path} 2>/dev/null",
        ]
        command_json = json.dumps(command, ensure_ascii=False)
        try:
            response = await self._exec_container_command(
                sandbox_id=sandbox_id,
                container_name=container_name,
                command_json=command_json,
                sync=True,
                timeout=None,
            )
            body = response.to_map().get("body", {})
            return body.get("SyncResponse", "") or ""
        except Exception:
            return ""
