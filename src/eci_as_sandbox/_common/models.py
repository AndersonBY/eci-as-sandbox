from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .._async.sandbox import AsyncSandbox
    from .._sync.sandbox import Sandbox


class ApiResponse:
    def __init__(self, request_id: str = ""):
        self.request_id = request_id

    def get_request_id(self) -> str:
        return self.request_id


class OperationResult(ApiResponse):
    def __init__(
        self,
        request_id: str = "",
        success: bool = False,
        data: Any = None,
        error_message: str = "",
        code: str = "",
        message: str = "",
        http_status_code: int = 0,
    ):
        super().__init__(request_id)
        self.success = success
        self.data = data
        self.error_message = error_message
        self.code = code
        self.message = message
        self.http_status_code = http_status_code


class SandboxResult(ApiResponse):
    def __init__(
        self,
        request_id: str = "",
        success: bool = False,
        error_message: str = "",
        sandbox: Optional["Sandbox"] = None,
    ):
        super().__init__(request_id)
        self.success = success
        self.error_message = error_message
        self.sandbox = sandbox


class AsyncSandboxResult(ApiResponse):
    def __init__(
        self,
        request_id: str = "",
        success: bool = False,
        error_message: str = "",
        sandbox: Optional["AsyncSandbox"] = None,
    ):
        super().__init__(request_id)
        self.success = success
        self.error_message = error_message
        self.sandbox = sandbox


class SandboxListResult(ApiResponse):
    def __init__(
        self,
        request_id: str = "",
        success: bool = False,
        error_message: str = "",
        sandbox_ids: Optional[List[str]] = None,
        next_token: str = "",
        max_results: int = 0,
        total_count: int = 0,
    ):
        super().__init__(request_id)
        self.success = success
        self.error_message = error_message
        self.sandbox_ids = sandbox_ids or []
        self.next_token = next_token
        self.max_results = max_results
        self.total_count = total_count


class DeleteResult(ApiResponse):
    def __init__(
        self,
        request_id: str = "",
        success: bool = False,
        error_message: str = "",
        code: str = "",
        message: str = "",
        http_status_code: int = 0,
    ):
        super().__init__(request_id)
        self.success = success
        self.error_message = error_message
        self.code = code
        self.message = message
        self.http_status_code = http_status_code


class GetSandboxResult(ApiResponse):
    def __init__(
        self,
        request_id: str = "",
        success: bool = False,
        error_message: str = "",
        data: Optional["SandboxInfo"] = None,
    ):
        super().__init__(request_id)
        self.success = success
        self.error_message = error_message
        self.data = data


class CommandResult(ApiResponse):
    def __init__(
        self,
        request_id: str = "",
        success: bool = False,
        output: str = "",
        error_message: str = "",
        http_url: str = "",
        websocket_url: str = "",
    ):
        super().__init__(request_id)
        self.success = success
        self.output = output
        self.error_message = error_message
        self.http_url = http_url
        self.websocket_url = websocket_url


class SandboxInfo:
    def __init__(
        self,
        sandbox_id: str = "",
        name: str = "",
        status: str = "",
        cpu: Optional[float] = None,
        memory: Optional[float] = None,
        region_id: str = "",
        zone_id: str = "",
        intranet_ip: str = "",
        internet_ip: str = "",
        creation_time: str = "",
        containers: Optional[List[Dict[str, Any]]] = None,
        raw: Optional[Dict[str, Any]] = None,
    ):
        self.sandbox_id = sandbox_id
        self.name = name
        self.status = status
        self.cpu = cpu
        self.memory = memory
        self.region_id = region_id
        self.zone_id = zone_id
        self.intranet_ip = intranet_ip
        self.internet_ip = internet_ip
        self.creation_time = creation_time
        self.containers = containers or []
        self.raw = raw or {}

    @classmethod
    def from_group(cls, group: Dict[str, Any]) -> "SandboxInfo":
        return cls(
            sandbox_id=group.get("ContainerGroupId", ""),
            name=group.get("ContainerGroupName", ""),
            status=group.get("Status", ""),
            cpu=group.get("Cpu"),
            memory=group.get("Memory"),
            region_id=group.get("RegionId", ""),
            zone_id=group.get("ZoneId", ""),
            intranet_ip=group.get("IntranetIp", ""),
            internet_ip=group.get("InternetIp", ""),
            creation_time=group.get("CreationTime", ""),
            containers=group.get("Containers", []) or [],
            raw=group,
        )


def extract_request_id(response: Any) -> str:
    if response is None:
        return ""

    try:
        response_dict = response.to_map()
        if isinstance(response_dict, dict) and "body" in response_dict:
            body = response_dict.get("body", {})
            if isinstance(body, dict) and "RequestId" in body:
                return body["RequestId"]
    except Exception:
        return ""

    return ""


Response = ApiResponse
