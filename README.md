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
