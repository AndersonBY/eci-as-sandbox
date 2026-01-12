"""
Tmux session management demo.

This example demonstrates how to run commands in tmux sessions
for non-blocking execution with output capture.

Usage:
    export TEST_ECI_SANDBOX_ID=eci-xxx
    python tmux_demo.py
"""

import os
import time
from pathlib import Path

from eci_as_sandbox import EciSandbox


def main(sandbox_id: str) -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    client = EciSandbox(env_file=str(env_path) if env_path.exists() else None)

    print(f"Using sandbox: {sandbox_id}")
    print()

    # Example 1: Start a command in tmux and wait for completion
    print("=" * 50)
    print("Example 1: tmux_start + tmux_wait")
    print("=" * 50)

    start_result = client.tmux_start(
        sandbox_id=sandbox_id,
        command="for i in 1 2 3; do echo count-$i; sleep 1; done; echo done",
        exec_dir="/tmp",
    )

    if not start_result.success:
        print(f"Failed to start: {start_result.error_message}")
        return

    print(f"Session started: {start_result.session_id}")

    # Wait for completion
    wait_result = client.tmux_wait(
        sandbox_id=sandbox_id,
        session_id=start_result.session_id,
        timeout=30,
    )

    print(f"Status: {wait_result.status}")
    print(f"Exit code: {wait_result.exit_code}")
    print(f"Output:\n{wait_result.output}")
    print()

    # Example 2: Poll for status manually
    print("=" * 50)
    print("Example 2: tmux_start + manual polling")
    print("=" * 50)

    start_result = client.tmux_start(
        sandbox_id=sandbox_id,
        command="sleep 3; echo 'Task completed!'",
    )

    if not start_result.success:
        print(f"Failed to start: {start_result.error_message}")
        return

    print(f"Session started: {start_result.session_id}")

    # Poll manually
    for i in range(10):
        poll_result = client.tmux_poll(
            sandbox_id=sandbox_id,
            session_id=start_result.session_id,
        )
        print(f"Poll {i + 1}: status={poll_result.status}, exit_code={poll_result.exit_code}")

        if poll_result.status.value == "completed":
            print(f"Output:\n{poll_result.output}")
            break

        time.sleep(1)

    # Cleanup
    client.tmux_kill(sandbox_id=sandbox_id, session_id=start_result.session_id)
    print()

    # Example 3: List all tmux sessions
    print("=" * 50)
    print("Example 3: tmux_list")
    print("=" * 50)

    list_result = client.tmux_list(sandbox_id=sandbox_id)
    if list_result.success:
        print(f"Active sessions: {list_result.data}")
    else:
        print(f"Failed to list: {list_result.error_message}")


if __name__ == "__main__":
    if "TEST_ECI_SANDBOX_ID" not in os.environ:
        raise RuntimeError("Please set the TEST_ECI_SANDBOX_ID environment variable.")
    main(os.environ["TEST_ECI_SANDBOX_ID"])
