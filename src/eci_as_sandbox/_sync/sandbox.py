from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .._common.models import (
    CommandResult,
    DeleteResult,
    OperationResult,
    TmuxKillResult,
    TmuxPollResult,
    TmuxStartResult,
    TMUX_HISTORY_LIMIT,
    TMUX_OUTPUT_TAIL_LINES,
    TMUX_POLL_BACKOFF_FACTOR,
    TMUX_POLL_INITIAL_DELAY,
    TMUX_POLL_MAX_DELAY,
)

if TYPE_CHECKING:
    from .client import EciSandbox


class Sandbox:
    def __init__(
        self,
        manager: "EciSandbox",
        sandbox_id: str,
        container_name: Optional[str] = None,
    ):
        self._manager = manager
        self.sandbox_id = sandbox_id
        self.container_name = container_name or ""

    def info(self) -> OperationResult:
        return self._manager.get_sandbox_info(self.sandbox_id)

    def delete(self, force: bool = False) -> DeleteResult:
        return self._manager.delete(self.sandbox_id, force=force)

    def restart(self) -> OperationResult:
        return self._manager.restart(self.sandbox_id)

    def exec_command(
        self,
        command: list[str],
        container_name: Optional[str] = None,
        sync: bool = True,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        return self._manager.exec_command(
            sandbox_id=self.sandbox_id,
            command=command,
            container_name=container_name or self.container_name,
            sync=sync,
            timeout=timeout,
        )

    def bash(
        self,
        command: str,
        exec_dir: Optional[str] = None,
        container_name: Optional[str] = None,
        sync: bool = True,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        return self._manager.bash(
            sandbox_id=self.sandbox_id,
            command=command,
            exec_dir=exec_dir,
            container_name=container_name or self.container_name,
            sync=sync,
            timeout=timeout,
        )

    # ==================== Tmux Methods ====================

    def tmux_start(
        self,
        command: str,
        exec_dir: Optional[str] = None,
        session_id: Optional[str] = None,
        history_limit: int = TMUX_HISTORY_LIMIT,
    ) -> TmuxStartResult:
        """Start a command in a tmux session (non-blocking)."""
        return self._manager.tmux_start(
            sandbox_id=self.sandbox_id,
            command=command,
            exec_dir=exec_dir,
            container_name=self.container_name,
            session_id=session_id,
            history_limit=history_limit,
        )

    def tmux_poll(
        self,
        session_id: str,
        tail_lines: int = TMUX_OUTPUT_TAIL_LINES,
    ) -> TmuxPollResult:
        """Poll for command completion and retrieve output."""
        return self._manager.tmux_poll(
            sandbox_id=self.sandbox_id,
            session_id=session_id,
            container_name=self.container_name,
            tail_lines=tail_lines,
        )

    def tmux_wait(
        self,
        session_id: str,
        timeout: Optional[float] = None,
        poll_interval: float = TMUX_POLL_INITIAL_DELAY,
        max_poll_interval: float = TMUX_POLL_MAX_DELAY,
        backoff_factor: float = TMUX_POLL_BACKOFF_FACTOR,
        tail_lines: int = TMUX_OUTPUT_TAIL_LINES,
        cleanup: bool = True,
    ) -> TmuxPollResult:
        """Wait for command completion with exponential backoff polling."""
        return self._manager.tmux_wait(
            sandbox_id=self.sandbox_id,
            session_id=session_id,
            container_name=self.container_name,
            timeout=timeout,
            poll_interval=poll_interval,
            max_poll_interval=max_poll_interval,
            backoff_factor=backoff_factor,
            tail_lines=tail_lines,
            cleanup=cleanup,
        )

    def tmux_kill(self, session_id: str) -> TmuxKillResult:
        """Kill a tmux session and clean up resources."""
        return self._manager.tmux_kill(
            sandbox_id=self.sandbox_id,
            session_id=session_id,
            container_name=self.container_name,
        )

    def tmux_list(self) -> OperationResult:
        """List all tmux sessions in the sandbox."""
        return self._manager.tmux_list(
            sandbox_id=self.sandbox_id,
            container_name=self.container_name,
        )
