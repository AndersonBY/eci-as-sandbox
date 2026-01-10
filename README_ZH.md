简体中文 | [English](README.md)

# eci-as-sandbox

基于阿里云 ECI 的沙箱管理库，封装了 `alibabacloud-eci20180808`，提供轻量的容器组沙箱管理 API。

## 安装

```bash
pdm add eci-as-sandbox
```

## 环境配置

客户端会自动加载 `.env` 文件（从当前目录向上查找）。也可以通过 `env_file=...` 或直接传入凭证参数。

必须的阿里云凭证：

```bash
set ALIBABA_CLOUD_ACCESS_KEY_ID=...
set ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
set ALIBABA_CLOUD_REGION_ID=cn-shanghai
```

可选覆盖项：

```bash
set ECI_SANDBOX_ACCESS_KEY_ID=...
set ECI_SANDBOX_ACCESS_KEY_SECRET=...
set ECI_SANDBOX_REGION_ID=cn-shanghai
set ECI_SANDBOX_ENDPOINT=eci.cn-shanghai.aliyuncs.com
set ECI_SANDBOX_TIMEOUT_MS=60000
```

使用私有镜像时，请先在 ECI 里配置镜像仓库认证。

## 快速开始（同步）

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

## 异步快速开始

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

## 命令助手

`exec_command` 使用 list 形式执行命令。`timeout` 单位为秒，用于控制 API 的读取超时。当 `sync=True` 且设置了 `timeout` 时，会将输出写入 `/tmp`，即便超时也会返回已捕获的输出（最多回传 200 行）。

```python
result = sandbox.exec_command(
    ["/bin/sh", "-c", "for i in 1 2 3; do echo tick-$i; sleep 2; done"],
    timeout=3,
)
print(result.output)
```

`bash` 通过 `bash -lc` 执行命令，并支持 `exec_dir` 指定运行目录。

```python
result = sandbox.bash(
    command="pwd; ls -la",
    exec_dir="/tmp",
    timeout=5,
)
print(result.output)
```

## 列表查询

```python
result = client.list(limit=10, status="Running")
print(result.sandbox_ids)
```
