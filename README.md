English | [简体中文](README_ZH.md)

# eci-as-sandbox

ECI-backed sandbox manager built on `alibabacloud-eci20180808` with a lightweight API for managing container-group sandboxes.

## Install

```bash
pdm add eci-as-sandbox
```

## Environment

The client auto-loads a `.env` file (searching upward from the working directory). You can also pass `env_file=...` or explicit credentials.

Required Alibaba Cloud credentials:

```bash
set ALIBABA_CLOUD_ACCESS_KEY_ID=...
set ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
set ALIBABA_CLOUD_REGION_ID=cn-shanghai
```

Optional overrides:

```bash
set ECI_SANDBOX_ACCESS_KEY_ID=...
set ECI_SANDBOX_ACCESS_KEY_SECRET=...
set ECI_SANDBOX_REGION_ID=cn-shanghai
set ECI_SANDBOX_ENDPOINT=eci.cn-shanghai.aliyuncs.com
set ECI_SANDBOX_TIMEOUT_MS=60000
```

If you use a private image, configure registry credentials in ECI.

## Quick start (sync)

```python
from eci_as_sandbox import EciSandbox

client = EciSandbox()
result = client.create(
    image="registry.cn-hangzhou.aliyuncs.com/eci_open/nginx:latest",
    name="sandbox-demo",
    cpu=1.0,
    memory=2.0,
    v_switch_id="vsw-xxx",
    security_group_id="sg-xxx",
    ports=[{"port": 8080, "protocol": "TCP"}],
)

if result.success and result.sandbox:
    sandbox = result.sandbox
    info = sandbox.info()
    print(info.data.status)
    sandbox.delete()
```

## Async quick start

```python
import asyncio
from eci_as_sandbox import AsyncEciSandbox


async def main() -> None:
    client = AsyncEciSandbox()
    result = await client.create(
        image="registry.cn-hangzhou.aliyuncs.com/eci_open/nginx:latest",
        name="sandbox-demo",
        cpu=1.0,
        memory=2.0,
        v_switch_id="vsw-xxx",
        security_group_id="sg-xxx",
    )
    if result.success and result.sandbox:
        info = await result.sandbox.info()
        print(info.data.status)


asyncio.run(main())
```

## Command helpers

`exec_command` runs a list-form command. With `sync=True` (default) it uses the ECI WebSocket stream to collect output. `timeout` is in seconds and caps the stream duration (default 600 seconds, max 600). Use `sync=False` if you want the WebSocket/HTTP URLs without waiting.

```python
result = sandbox.exec_command(
    ["/bin/sh", "-c", "for i in 1 2 3; do echo tick-$i; sleep 2; done"],
    timeout=3,
)
print(result.output)
```

`bash` runs a shell command via `bash -lc` and supports `exec_dir`.

```python
result = sandbox.bash(
    command="pwd; ls -la",
    exec_dir="/tmp",
    timeout=5,
)
print(result.output)
```

## Listing

```python
result = client.list(limit=10, status="Running")
print(result.sandbox_ids)
```

## Long command execution (WebSocket)

ECI's API has a 2048-byte command limit. For longer commands, use `bash_ws` which sends commands through WebSocket stdin (no length limit).

```python
# Execute a very long command (e.g., inline Python script)
long_script = """python3 << 'EOF'
import json
# ... hundreds of lines of code ...
print(json.dumps({"status": "done"}))
EOF
"""

result = client.bash_ws(
    sandbox_id=sandbox_id,
    command=long_script,
    exec_dir="/workspace",
    timeout=60,
)
print(result.output)
```

`write_file_ws` writes large content to a file via WebSocket:

```python
result = client.write_file_ws(
    sandbox_id=sandbox_id,
    file_path="/tmp/large_script.py",
    content="# Very long file content...\n" * 1000,
    timeout=30,
)
```

## Tmux session management

For non-blocking command execution with output capture, use tmux methods. Long commands are automatically handled via WebSocket file transfer.

```python
# Start a command in tmux (non-blocking)
start_result = client.tmux_start(
    sandbox_id=sandbox_id,
    command="python train.py --epochs 100",
    exec_dir="/workspace",
)
print(f"Session: {start_result.session_id}")

# Poll for status and partial output
poll_result = client.tmux_poll(
    sandbox_id=sandbox_id,
    session_id=start_result.session_id,
)
print(f"Status: {poll_result.status}")  # RUNNING, COMPLETED, NOT_FOUND
print(f"Output: {poll_result.output}")

# Wait for completion with exponential backoff
wait_result = client.tmux_wait(
    sandbox_id=sandbox_id,
    session_id=start_result.session_id,
    timeout=300,  # max wait time
)
print(f"Exit code: {wait_result.exit_code}")
print(f"Output: {wait_result.output}")

# Kill a session manually
client.tmux_kill(sandbox_id=sandbox_id, session_id=start_result.session_id)

# List all tmux sessions
list_result = client.tmux_list(sandbox_id=sandbox_id)
print(list_result.data)  # [{"session_id": "...", "created": "...", "attached": False}]
```

## API Reference

### Client Methods

| Method | Description |
|--------|-------------|
| `create(image, name, cpu, memory, ...)` | Create a new sandbox container |
| `get(sandbox_id)` | Get sandbox instance by ID |
| `get_sandbox(sandbox_id)` | Get sandbox info |
| `list(limit, status, tags, ...)` | List sandboxes |
| `delete(sandbox_id, force)` | Delete a sandbox |
| `restart(sandbox_id)` | Restart a sandbox |
| `exec_command(sandbox_id, command, ...)` | Execute command (list form) |
| `bash(sandbox_id, command, exec_dir, ...)` | Execute bash command |
| `bash_ws(sandbox_id, command, exec_dir, ...)` | Execute bash via WebSocket (unlimited length) |
| `write_file_ws(sandbox_id, file_path, content, ...)` | Write file via WebSocket (unlimited length) |
| `tmux_start(sandbox_id, command, ...)` | Start command in tmux session |
| `tmux_poll(sandbox_id, session_id, ...)` | Poll tmux session status |
| `tmux_wait(sandbox_id, session_id, timeout, ...)` | Wait for tmux session completion |
| `tmux_kill(sandbox_id, session_id)` | Kill tmux session |
| `tmux_list(sandbox_id)` | List all tmux sessions |
