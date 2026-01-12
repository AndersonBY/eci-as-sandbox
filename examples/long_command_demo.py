"""
Long command execution demo via WebSocket.

This example demonstrates how to execute very long commands
that would exceed ECI's 2048-byte API limit.

Usage:
    export TEST_ECI_SANDBOX_ID=eci-xxx
    python long_command_demo.py
"""

import os
from pathlib import Path

from eci_as_sandbox import EciSandbox


def main(sandbox_id: str) -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    client = EciSandbox(env_file=str(env_path) if env_path.exists() else None)

    print(f"Using sandbox: {sandbox_id}")
    print()

    # Example 1: Execute a long inline Python script via bash_ws
    print("=" * 50)
    print("Example 1: bash_ws - Long Python script")
    print("=" * 50)

    long_python_script = """python3 << 'EOF'
import json
import time

print("Starting data processing...")

# Simulate complex data processing
data_config_1 = {"name": "config1", "value": 100, "enabled": True}
data_config_2 = {"name": "config2", "value": 200, "enabled": False}
data_config_3 = {"name": "config3", "value": 300, "enabled": True}
data_config_4 = {"name": "config4", "value": 400, "enabled": False}
data_config_5 = {"name": "config5", "value": 500, "enabled": True}

all_configs = [data_config_1, data_config_2, data_config_3, data_config_4, data_config_5]

# Process configurations
enabled_count = sum(1 for c in all_configs if c["enabled"])
total_value = sum(c["value"] for c in all_configs)

result = {
    "total_configs": len(all_configs),
    "enabled_count": enabled_count,
    "total_value": total_value,
    "timestamp": time.time()
}

print(f"Processing complete!")
print(f"Result: {json.dumps(result, indent=2)}")
EOF
"""

    print(f"Script length: {len(long_python_script)} characters")

    result = client.bash_ws(
        sandbox_id=sandbox_id,
        command=long_python_script,
        exec_dir="/tmp",
        timeout=30,
    )

    print(f"Success: {result.success}")
    if result.output:
        print(f"Output:\n{result.output}")
    print()

    # Example 2: Write a large file via write_file_ws
    print("=" * 50)
    print("Example 2: write_file_ws - Large file")
    print("=" * 50)

    large_content = "# This is line {i}\n".format(i=1)
    large_content = "\n".join([f"# This is line {i}" for i in range(1, 201)])
    large_content += "\nprint('Hello from large script!')\n"

    print(f"Content length: {len(large_content)} characters")

    write_result = client.write_file_ws(
        sandbox_id=sandbox_id,
        file_path="/tmp/large_script.py",
        content=large_content,
        timeout=30,
    )

    print(f"Write success: {write_result.success}")

    # Verify the file was written correctly
    verify_result = client.bash(
        sandbox_id=sandbox_id,
        command="wc -l /tmp/large_script.py && python3 /tmp/large_script.py",
        timeout=10,
    )
    print(f"Verification:\n{verify_result.output}")
    print()

    # Example 3: Long command via tmux (auto file-based execution)
    print("=" * 50)
    print("Example 3: tmux_start with long command")
    print("=" * 50)

    # This long command will automatically use WebSocket file transfer
    long_command = long_python_script  # Reuse the long script

    start_result = client.tmux_start(
        sandbox_id=sandbox_id,
        command=long_command,
        exec_dir="/tmp",
    )

    if start_result.success:
        print(f"Session: {start_result.session_id}")

        wait_result = client.tmux_wait(
            sandbox_id=sandbox_id,
            session_id=start_result.session_id,
            timeout=30,
        )

        print(f"Status: {wait_result.status}")
        print(f"Exit code: {wait_result.exit_code}")
        if wait_result.output:
            print(f"Output:\n{wait_result.output}")
    else:
        print(f"Failed: {start_result.error_message}")


if __name__ == "__main__":
    if "TEST_ECI_SANDBOX_ID" not in os.environ:
        raise RuntimeError("Please set the TEST_ECI_SANDBOX_ID environment variable.")
    main(os.environ["TEST_ECI_SANDBOX_ID"])
