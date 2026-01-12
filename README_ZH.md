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

`exec_command` 使用 list 形式执行命令。默认 `sync=True` 会通过 ECI 的 WebSocket 流读取输出。`timeout` 单位为秒，用于限制读取时长（默认 600 秒，最大 600）。如果你只需要 WebSocket/HTTP URL，请设置 `sync=False`。

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

## 长命令执行（WebSocket）

ECI 的 API 有 2048 字节的命令长度限制。对于更长的命令，使用 `bash_ws` 通过 WebSocket stdin 发送命令（无长度限制）。

```python
# 执行超长命令（如内嵌 Python 脚本）
long_script = """python3 << 'EOF'
import json
# ... 数百行代码 ...
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

`write_file_ws` 通过 WebSocket 写入大文件：

```python
result = client.write_file_ws(
    sandbox_id=sandbox_id,
    file_path="/tmp/large_script.py",
    content="# 很长的文件内容...\n" * 1000,
    timeout=30,
)
```

## Tmux 会话管理

对于非阻塞命令执行和输出捕获，使用 tmux 方法。长命令会自动通过 WebSocket 文件传输处理。

```python
# 在 tmux 中启动命令（非阻塞）
start_result = client.tmux_start(
    sandbox_id=sandbox_id,
    command="python train.py --epochs 100",
    exec_dir="/workspace",
)
print(f"会话 ID: {start_result.session_id}")

# 轮询状态和部分输出
poll_result = client.tmux_poll(
    sandbox_id=sandbox_id,
    session_id=start_result.session_id,
)
print(f"状态: {poll_result.status}")  # RUNNING, COMPLETED, NOT_FOUND
print(f"输出: {poll_result.output}")

# 等待命令完成（指数退避轮询）
wait_result = client.tmux_wait(
    sandbox_id=sandbox_id,
    session_id=start_result.session_id,
    timeout=300,  # 最大等待时间
)
print(f"退出码: {wait_result.exit_code}")
print(f"输出: {wait_result.output}")

# 手动终止会话
client.tmux_kill(sandbox_id=sandbox_id, session_id=start_result.session_id)

# 列出所有 tmux 会话
list_result = client.tmux_list(sandbox_id=sandbox_id)
print(list_result.data)  # [{"session_id": "...", "created": "...", "attached": False}]
```

## API 参考

### 客户端方法

| 方法 | 说明 |
|------|------|
| `create(image, name, cpu, memory, ...)` | 创建新的沙箱容器 |
| `get(sandbox_id)` | 通过 ID 获取沙箱实例 |
| `get_sandbox(sandbox_id)` | 获取沙箱信息 |
| `list(limit, status, tags, ...)` | 列出沙箱 |
| `delete(sandbox_id, force)` | 删除沙箱 |
| `restart(sandbox_id)` | 重启沙箱 |
| `exec_command(sandbox_id, command, ...)` | 执行命令（列表形式） |
| `bash(sandbox_id, command, exec_dir, ...)` | 执行 bash 命令 |
| `bash_ws(sandbox_id, command, exec_dir, ...)` | 通过 WebSocket 执行 bash（无长度限制） |
| `write_file_ws(sandbox_id, file_path, content, ...)` | 通过 WebSocket 写文件（无长度限制） |
| `tmux_start(sandbox_id, command, ...)` | 在 tmux 会话中启动命令 |
| `tmux_poll(sandbox_id, session_id, ...)` | 轮询 tmux 会话状态 |
| `tmux_wait(sandbox_id, session_id, timeout, ...)` | 等待 tmux 会话完成 |
| `tmux_kill(sandbox_id, session_id)` | 终止 tmux 会话 |
| `tmux_list(sandbox_id)` | 列出所有 tmux 会话 |
