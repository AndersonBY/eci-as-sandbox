from __future__ import annotations

import base64
import gzip
import json
import os
import random
import shlex
import string
import time
import uuid
from typing import Any, Dict, Optional

from alibabacloud_eci20180808 import models as eci_models
from alibabacloud_eci20180808.client import Client as EciClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from .._common.config import Config, _get_endpoint_for_region, _load_config
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
    SandboxResult,
    TmuxCommandStatus,
    TmuxKillResult,
    TmuxPollResult,
    TmuxStartResult,
    TMUX_DEFAULT_TIMEOUT,
    TMUX_HISTORY_LIMIT,
    TMUX_MARKER_EXIT_CODE,
    TMUX_OUTPUT_TAIL_LINES,
    TMUX_POLL_BACKOFF_FACTOR,
    TMUX_POLL_INITIAL_DELAY,
    TMUX_POLL_MAX_DELAY,
    TMUX_SESSION_PREFIX,
    extract_request_id,
)
from .._common.ws import decode_ws_message
from .sandbox import Sandbox


_logger = get_logger("eci-as-sandbox")
_DEFAULT_SYNC_TIMEOUT = 600.0


class EciSandbox:
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

        # Auto-adjust endpoint based on region_id if it differs from config
        endpoint = config_data["endpoint"]
        expected_endpoint = _get_endpoint_for_region(region_id)
        if endpoint != expected_endpoint:
            endpoint = expected_endpoint

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            security_token=security_token,
            endpoint=endpoint,
            region_id=region_id,
            read_timeout=config_data["timeout_ms"],
            connect_timeout=config_data["timeout_ms"],
        )

        self.client = EciClient(config)
        self._sandboxes: Dict[str, Sandbox] = {}

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

    def create(
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
    ) -> SandboxResult:
        if not image:
            return SandboxResult(success=False, error_message="image is required")

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

        # 注意：ECI API 中如果传递空列表 [] 给 command，会覆盖容器的 ENTRYPOINT
        # 只有当 command/args 有实际内容时才传递，否则让容器使用镜像默认的 ENTRYPOINT/CMD
        container_kwargs: Dict[str, Any] = {
            "name": container_name,
            "image": image,
            "cpu": cpu,
            "memory": memory,
            "environment_var": env_vars,
            "port": port_configs,
        }
        if command:
            container_kwargs["command"] = command
        if args:
            container_kwargs["arg"] = args

        container = eci_models.CreateContainerGroupRequestContainer(**container_kwargs)

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
            response = self.client.create_container_group(request)
            request_id = extract_request_id(response)
            body = response.to_map().get("body", {})
            sandbox_id = body.get("ContainerGroupId", "")

            if not sandbox_id:
                _log_api_response("CreateContainerGroup", request_id, False)
                return SandboxResult(
                    request_id=request_id,
                    success=False,
                    error_message="ContainerGroupId not found in response",
                )

            sandbox = Sandbox(self, sandbox_id, container_name=container_name)
            self._sandboxes[sandbox_id] = sandbox

            _log_api_response(
                "CreateContainerGroup",
                request_id,
                True,
                {"sandbox_id": sandbox_id},
            )
            return SandboxResult(
                request_id=request_id,
                success=True,
                sandbox=sandbox,
            )
        except Exception as exc:
            _log_operation_error("CreateContainerGroup", str(exc), exc_info=True)
            return SandboxResult(
                request_id="",
                success=False,
                error_message=f"Failed to create sandbox: {exc}",
            )

    def get_sandbox_info(self, sandbox_id: str) -> OperationResult:
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
            response = self.client.describe_container_groups(request)
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

    def get_sandbox(self, sandbox_id: str) -> GetSandboxResult:
        info_result = self.get_sandbox_info(sandbox_id)
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

    def get(self, sandbox_id: str) -> SandboxResult:
        info_result = self.get_sandbox_info(sandbox_id)
        if not info_result.success:
            return SandboxResult(
                request_id=info_result.request_id,
                success=False,
                error_message=info_result.error_message,
            )

        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None:
            sandbox = Sandbox(self, sandbox_id)
            self._sandboxes[sandbox_id] = sandbox

        return SandboxResult(
            request_id=info_result.request_id,
            success=True,
            sandbox=sandbox,
        )

    def list(
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
            response = self.client.describe_container_groups(request)
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

    def delete(self, sandbox_id: str, force: bool = False) -> DeleteResult:
        if not sandbox_id:
            return DeleteResult(success=False, error_message="sandbox_id is required")

        request = eci_models.DeleteContainerGroupRequest(
            region_id=self.region_id,
            container_group_id=sandbox_id,
            force=force,
        )

        _log_api_call("DeleteContainerGroup", f"ContainerGroupId={sandbox_id}")

        try:
            response = self.client.delete_container_group(request)
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

    def restart(self, sandbox_id: str) -> OperationResult:
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
            response = self.client.restart_container_group(request)
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

    def exec_command(
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
            container_name = self._resolve_container_name(sandbox_id)
        if not container_name:
            return CommandResult(
                success=False,
                error_message="container_name is required",
            )

        _log_api_call(
            "ExecContainerCommand",
            f"ContainerGroupId={sandbox_id}, Container={container_name}",
        )

        try:
            command_json = json.dumps(command, ensure_ascii=False)
            if sync:
                response = self._exec_container_command(
                    sandbox_id=sandbox_id,
                    container_name=container_name,
                    command_json=command_json,
                    sync=False,
                    timeout=None,
                )
                request_id = extract_request_id(response)
                body = response.to_map().get("body", {})
                http_url = body.get("HttpUrl", "")
                websocket_url = body.get("WebSocketUri", "")
                output = ""
                if not websocket_url:
                    return CommandResult(
                        request_id=request_id,
                        success=False,
                        error_message="WebSocketUri not returned for sync exec.",
                        http_url=http_url,
                        websocket_url=websocket_url,
                    )
                output = self._read_ws_output(
                    websocket_url, self._normalize_sync_timeout(timeout)
                )
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

            response = self._exec_container_command(
                sandbox_id=sandbox_id,
                container_name=container_name,
                command_json=command_json,
                sync=sync,
                timeout=timeout,
            )
            request_id = extract_request_id(response)
            body = response.to_map().get("body", {})
            output = body.get("SyncResponse", "") if sync else ""
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
            _log_operation_error("ExecContainerCommand", str(exc), exc_info=True)
            return CommandResult(
                request_id="",
                success=False,
                output="",
                error_message=f"Failed to exec command: {exc}",
            )

    def bash(
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
        # Encode command as base64 to preserve heredoc, special characters, etc.
        # The command is decoded and piped to bash in the container.
        # For long commands, use gzip compression to stay within ECI's 2048 byte limit.
        encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
        wrapper = f"echo {encoded} | base64 -d | bash"
        if len(wrapper) > 1900:
            # Use gzip compression for long commands
            compressed = gzip.compress(command.encode("utf-8"))
            encoded = base64.b64encode(compressed).decode("ascii")
            wrapper = f"echo {encoded} | base64 -d | gunzip | bash"
        return self.exec_command(
            sandbox_id=sandbox_id,
            command=["bash", "-lc", wrapper],
            container_name=container_name,
            sync=sync,
            timeout=timeout,
        )

    def _resolve_container_name(self, sandbox_id: str) -> str:
        info_result = self.get_sandbox_info(sandbox_id)
        if not info_result.success or not info_result.data:
            return ""
        containers = info_result.data.containers or []
        if not containers:
            return ""
        first = containers[0]
        if isinstance(first, dict):
            return first.get("Name", "") or first.get("name", "")
        return ""

    def _exec_container_command(
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
            return self.client.exec_container_command(request)
        timeout_ms = int(timeout * 1000)
        runtime = util_models.RuntimeOptions(
            read_timeout=timeout_ms,
            connect_timeout=timeout_ms,
        )
        return self.client.exec_container_command_with_options(request, runtime)

    def _normalize_sync_timeout(self, timeout: Optional[float]) -> float:
        if timeout is None:
            return _DEFAULT_SYNC_TIMEOUT
        if timeout <= 0:
            return _DEFAULT_SYNC_TIMEOUT
        return min(timeout, _DEFAULT_SYNC_TIMEOUT)

    def _read_ws_output(self, websocket_url: str, timeout: float) -> str:
        try:
            import websocket
        except Exception as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "websocket-client is required for sync exec output streaming."
            ) from exc

        output_chunks: list[str] = []
        end_time = time.monotonic() + timeout
        ws = websocket.create_connection(websocket_url, timeout=1)
        try:
            while time.monotonic() < end_time:
                remaining = end_time - time.monotonic()
                ws.settimeout(min(1.0, remaining))
                try:
                    message = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                except websocket.WebSocketConnectionClosedException:
                    break
                if message is None:
                    break
                output_chunks.append(decode_ws_message(message))
        finally:
            try:
                ws.close()
            except Exception:
                pass
        return "".join(output_chunks)

    def _wrap_command_for_log(self, command: list[str], log_path: str) -> list[str]:
        if len(command) >= 2 and command[0] in {"/bin/sh", "sh"} and command[1] == "-c":
            inner = command[2] if len(command) > 2 else ""
            shell_cmd = inner
        else:
            shell_cmd = " ".join(shlex.quote(part) for part in command)
        wrapped = f"{shell_cmd} > {log_path} 2>&1"
        return ["/bin/sh", "-c", wrapped]

    def _read_log_output(
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
            response = self._exec_container_command(
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

    # ==================== Tmux Methods ====================

    def tmux_start(
        self,
        sandbox_id: str,
        command: str,
        exec_dir: Optional[str] = None,
        container_name: Optional[str] = None,
        session_id: Optional[str] = None,
        history_limit: int = TMUX_HISTORY_LIMIT,
    ) -> TmuxStartResult:
        """
        Start a command in a tmux session (non-blocking).

        Args:
            sandbox_id: The sandbox container ID
            command: Shell command to execute
            exec_dir: Working directory for command execution
            container_name: Container name (auto-resolved if not provided)
            session_id: Custom session ID (auto-generated if not provided)
            history_limit: tmux scrollback buffer size

        Returns:
            TmuxStartResult with session_id on success
        """
        if not sandbox_id:
            return TmuxStartResult(success=False, error_message="sandbox_id is required")
        if not command:
            return TmuxStartResult(success=False, error_message="command is required")

        if not container_name:
            container_name = self._resolve_container_name(sandbox_id)
        if not container_name:
            return TmuxStartResult(success=False, error_message="container_name is required")

        # Generate unique session ID if not provided
        if not session_id:
            session_id = f"{TMUX_SESSION_PREFIX}{uuid.uuid4().hex[:12]}"

        # Build marker for completion detection
        marker = f"{TMUX_MARKER_EXIT_CODE}{session_id}__"

        # Build the command with exec_dir and completion marker
        inner_cmd = command
        if exec_dir:
            inner_cmd = f"cd {shlex.quote(exec_dir)} && {command}"

        # Wrap command to capture exit code and output completion marker
        # Use subshell () to capture exit code even if command uses 'exit'
        wrapped_cmd = f'''({inner_cmd})
__exit_code__=$?
echo ""
echo "{marker}$__exit_code__"'''

        # Create tmux session with the command
        # Use base64 encoding to avoid shell quoting issues with complex commands
        # Set remain-on-exit so the pane stays open after command completes (for output capture)
        encoded_cmd = base64.b64encode(wrapped_cmd.encode("utf-8")).decode("ascii")
        tmux_cmd = (
            f'tmux new-session -d -s {shlex.quote(session_id)} "echo {encoded_cmd} | base64 -d | bash -l"; '
            f'tmux set-option -t {shlex.quote(session_id)} remain-on-exit on 2>/dev/null || true'
        )

        # Execute via existing bash() method
        result = self.bash(
            sandbox_id=sandbox_id,
            command=tmux_cmd,
            container_name=container_name,
            sync=True,
            timeout=30,
        )

        if not result.success:
            return TmuxStartResult(
                request_id=result.request_id,
                success=False,
                error_message=f"Failed to start tmux session: {result.error_message or result.output}",
            )

        # Verify session was created
        verify_cmd = f"tmux has-session -t {shlex.quote(session_id)} 2>/dev/null && echo 'EXISTS' || echo 'NOT_FOUND'"
        verify_result = self.bash(
            sandbox_id=sandbox_id,
            command=verify_cmd,
            container_name=container_name,
            sync=True,
            timeout=10,
        )

        if "EXISTS" not in (verify_result.output or ""):
            return TmuxStartResult(
                request_id=result.request_id,
                success=False,
                error_message="Session created but verification failed",
            )

        return TmuxStartResult(
            request_id=result.request_id,
            success=True,
            session_id=session_id,
        )

    def tmux_poll(
        self,
        sandbox_id: str,
        session_id: str,
        container_name: Optional[str] = None,
        tail_lines: int = TMUX_OUTPUT_TAIL_LINES,
    ) -> TmuxPollResult:
        """
        Poll for command completion and retrieve output.

        Args:
            sandbox_id: The sandbox container ID
            session_id: The tmux session ID from tmux_start()
            container_name: Container name (auto-resolved if not provided)
            tail_lines: Number of lines to retrieve from output

        Returns:
            TmuxPollResult with status, exit_code (if completed), and output
        """
        if not sandbox_id:
            return TmuxPollResult(success=False, error_message="sandbox_id is required")
        if not session_id:
            return TmuxPollResult(success=False, error_message="session_id is required")

        if not container_name:
            container_name = self._resolve_container_name(sandbox_id)
        if not container_name:
            return TmuxPollResult(success=False, error_message="container_name is required")

        # Check if session exists
        check_cmd = f"tmux has-session -t {shlex.quote(session_id)} 2>/dev/null && echo 'EXISTS' || echo 'NOT_FOUND'"
        check_result = self.bash(
            sandbox_id=sandbox_id,
            command=check_cmd,
            container_name=container_name,
            sync=True,
            timeout=10,
        )

        if "NOT_FOUND" in (check_result.output or ""):
            return TmuxPollResult(
                request_id=check_result.request_id,
                success=True,
                status=TmuxCommandStatus.NOT_FOUND,
                error_message="Session does not exist (may have been cleaned up)",
            )

        # Capture output from tmux pane
        # capture-pane -p prints to stdout, -S - starts from beginning of history
        capture_cmd = f"tmux capture-pane -t {shlex.quote(session_id)} -p -S - 2>/dev/null | tail -n {tail_lines}"
        capture_result = self.bash(
            sandbox_id=sandbox_id,
            command=capture_cmd,
            container_name=container_name,
            sync=True,
            timeout=30,
        )

        if not capture_result.success:
            return TmuxPollResult(
                request_id=capture_result.request_id,
                success=False,
                status=TmuxCommandStatus.ERROR,
                error_message=f"Failed to capture output: {capture_result.error_message}",
            )

        output = capture_result.output or ""
        marker = f"{TMUX_MARKER_EXIT_CODE}{session_id}__"

        # Check for completion marker in output
        if marker in output:
            # Extract exit code from marker line
            lines = output.split("\n")
            exit_code: Optional[int] = None
            clean_output_lines: list[str] = []

            for line in lines:
                if marker in line:
                    # Extract exit code after marker
                    try:
                        exit_code_str = line.split(marker)[-1].strip()
                        exit_code = int(exit_code_str)
                    except (ValueError, IndexError):
                        exit_code = -1  # Unknown exit code
                elif line.startswith("Pane is dead"):
                    # Filter out tmux "Pane is dead" message (from remain-on-exit)
                    pass
                else:
                    clean_output_lines.append(line)

            # Remove trailing empty lines
            while clean_output_lines and not clean_output_lines[-1].strip():
                clean_output_lines.pop()

            clean_output = "\n".join(clean_output_lines)

            return TmuxPollResult(
                request_id=capture_result.request_id,
                success=True,
                status=TmuxCommandStatus.COMPLETED,
                exit_code=exit_code,
                output=clean_output,
                output_truncated=len(lines) >= tail_lines,
            )

        # Command still running - return partial output
        return TmuxPollResult(
            request_id=capture_result.request_id,
            success=True,
            status=TmuxCommandStatus.RUNNING,
            output=output,
            output_truncated=len(output.split("\n")) >= tail_lines,
        )

    def tmux_wait(
        self,
        sandbox_id: str,
        session_id: str,
        container_name: Optional[str] = None,
        timeout: Optional[float] = None,
        poll_interval: float = TMUX_POLL_INITIAL_DELAY,
        max_poll_interval: float = TMUX_POLL_MAX_DELAY,
        backoff_factor: float = TMUX_POLL_BACKOFF_FACTOR,
        tail_lines: int = TMUX_OUTPUT_TAIL_LINES,
        cleanup: bool = True,
    ) -> TmuxPollResult:
        """
        Wait for command completion with exponential backoff polling.

        Args:
            sandbox_id: The sandbox container ID
            session_id: The tmux session ID
            container_name: Container name
            timeout: Maximum time to wait (None = use default)
            poll_interval: Initial polling interval
            max_poll_interval: Maximum polling interval
            backoff_factor: Multiplier for exponential backoff
            tail_lines: Lines to retrieve from output
            cleanup: Whether to kill the session after completion

        Returns:
            TmuxPollResult with final status and output
        """
        if timeout is None:
            timeout = TMUX_DEFAULT_TIMEOUT

        start_time = time.monotonic()
        current_interval = poll_interval

        while True:
            # Check timeout
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                # Timeout - get final output and optionally cleanup
                poll_result = self.tmux_poll(sandbox_id, session_id, container_name, tail_lines)
                if cleanup:
                    self.tmux_kill(sandbox_id, session_id, container_name)
                return TmuxPollResult(
                    request_id=poll_result.request_id,
                    success=False,
                    status=TmuxCommandStatus.RUNNING,
                    output=poll_result.output,
                    output_truncated=poll_result.output_truncated,
                    error_message=f"Timeout after {elapsed:.1f}s",
                )

            # Poll for status
            poll_result = self.tmux_poll(sandbox_id, session_id, container_name, tail_lines)

            if not poll_result.success:
                return poll_result

            if poll_result.status == TmuxCommandStatus.COMPLETED:
                if cleanup:
                    self.tmux_kill(sandbox_id, session_id, container_name)
                return poll_result

            if poll_result.status == TmuxCommandStatus.NOT_FOUND:
                return poll_result

            # Still running - wait with backoff
            time.sleep(current_interval)
            current_interval = min(current_interval * backoff_factor, max_poll_interval)

    def tmux_kill(
        self,
        sandbox_id: str,
        session_id: str,
        container_name: Optional[str] = None,
    ) -> TmuxKillResult:
        """
        Kill a tmux session and clean up resources.

        Args:
            sandbox_id: The sandbox container ID
            session_id: The tmux session ID to kill
            container_name: Container name

        Returns:
            TmuxKillResult indicating success/failure
        """
        if not sandbox_id:
            return TmuxKillResult(success=False, error_message="sandbox_id is required")
        if not session_id:
            return TmuxKillResult(success=False, error_message="session_id is required")

        if not container_name:
            container_name = self._resolve_container_name(sandbox_id)

        kill_cmd = f"tmux kill-session -t {shlex.quote(session_id)} 2>/dev/null || true"
        result = self.bash(
            sandbox_id=sandbox_id,
            command=kill_cmd,
            container_name=container_name,
            sync=True,
            timeout=10,
        )

        return TmuxKillResult(
            request_id=result.request_id,
            success=True,  # Always succeed (idempotent)
        )

    def tmux_list(
        self,
        sandbox_id: str,
        container_name: Optional[str] = None,
    ) -> OperationResult:
        """
        List all tmux sessions in the sandbox.

        Args:
            sandbox_id: The sandbox container ID
            container_name: Container name

        Returns:
            OperationResult with data containing list of session info dicts
        """
        if not sandbox_id:
            return OperationResult(success=False, error_message="sandbox_id is required")

        if not container_name:
            container_name = self._resolve_container_name(sandbox_id)

        list_cmd = "tmux list-sessions -F '#{session_name}:#{session_created}:#{session_attached}' 2>/dev/null || echo ''"
        result = self.bash(
            sandbox_id=sandbox_id,
            command=list_cmd,
            container_name=container_name,
            sync=True,
            timeout=10,
        )

        if not result.success:
            return OperationResult(
                request_id=result.request_id,
                success=False,
                error_message=result.error_message,
            )

        sessions: list[dict[str, Any]] = []
        for line in (result.output or "").strip().split("\n"):
            if ":" in line:
                parts = line.split(":")
                if len(parts) >= 3:
                    sessions.append({
                        "session_id": parts[0],
                        "created": parts[1],
                        "attached": parts[2] == "1",
                    })

        return OperationResult(
            request_id=result.request_id,
            success=True,
            data=sessions,
        )
