from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .._common.models import CommandResult, DeleteResult, OperationResult

if TYPE_CHECKING:
    from .client import AsyncEciSandbox


class AsyncSandbox:
    def __init__(
        self,
        manager: "AsyncEciSandbox",
        sandbox_id: str,
        container_name: Optional[str] = None,
    ):
        self._manager = manager
        self.sandbox_id = sandbox_id
        self.container_name = container_name or ""

    async def info(self) -> OperationResult:
        return await self._manager.get_sandbox_info(self.sandbox_id)

    async def delete(self, force: bool = False) -> DeleteResult:
        return await self._manager.delete(self.sandbox_id, force=force)

    async def restart(self) -> OperationResult:
        return await self._manager.restart(self.sandbox_id)

    async def exec_command(
        self,
        command: list[str],
        container_name: Optional[str] = None,
        sync: bool = True,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        return await self._manager.exec_command(
            sandbox_id=self.sandbox_id,
            command=command,
            container_name=container_name or self.container_name,
            sync=sync,
            timeout=timeout,
        )

    async def bash(
        self,
        command: str,
        exec_dir: Optional[str] = None,
        container_name: Optional[str] = None,
        sync: bool = True,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        return await self._manager.bash(
            sandbox_id=self.sandbox_id,
            command=command,
            exec_dir=exec_dir,
            container_name=container_name or self.container_name,
            sync=sync,
            timeout=timeout,
        )
