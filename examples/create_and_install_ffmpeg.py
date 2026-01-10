import os
import time
from pathlib import Path

from eci_as_sandbox import EciSandbox


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    client = EciSandbox(env_file=str(env_path) if env_path.exists() else None)

    image = require_env("ECI_SANDBOX_IMAGE_ID")
    v_switch_id = require_env("ECI_SANDBOX_VSWITCH_ID")
    security_group_id = require_env("ECI_SANDBOX_SECURITY_GROUP_ID")
    auto_create_eip = parse_bool(os.getenv("ECI_SANDBOX_AUTO_CREATE_EIP", "false"))
    eip_bandwidth = os.getenv("ECI_SANDBOX_EIP_BANDWIDTH", "").strip()
    eip_instance_id = os.getenv("ECI_SANDBOX_EIP_INSTANCE_ID", "").strip() or None

    result = client.create(
        image=image,
        name="ubuntu-ffmpeg",
        container_name="sandbox",
        cpu=1.0,
        memory=2.0,
        command=["/bin/sh", "-c"],
        args=["sleep infinity"],
        v_switch_id=v_switch_id,
        security_group_id=security_group_id,
        restart_policy="Never",
        auto_create_eip=auto_create_eip,
        eip_bandwidth=int(eip_bandwidth) if eip_bandwidth else None,
        eip_instance_id=eip_instance_id,
    )
    if not result.success:
        raise RuntimeError(f"Create failed: {result.error_message}")

    if result.sandbox is None:
        raise RuntimeError("Create failed: sandbox is missing in result")

    sandbox = result.sandbox
    print(f"Sandbox created: {sandbox.sandbox_id}")

    for _ in range(60):
        info = sandbox.info()
        if info.success and info.data and info.data.status == "Running":
            break
        time.sleep(5)
    else:
        raise RuntimeError("Sandbox did not reach Running status in time")

    install = sandbox.exec_command(
        [
            "/bin/sh",
            "-c",
            'nohup sh -c "apt-get update && '
            "DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg && "
            'ffmpeg -version | head -n 1 > /tmp/ffmpeg_version" '
            ">/tmp/ffmpeg_install.log 2>&1 &",
        ]
    )
    if not install.success:
        raise RuntimeError(f"Install failed: {install.error_message}")

    for _ in range(120):
        check = sandbox.exec_command(
            [
                "/bin/sh",
                "-c",
                "if [ -f /tmp/ffmpeg_version ]; then cat /tmp/ffmpeg_version; fi",
            ]
        )
        if check.success and check.output.strip():
            print(check.output.strip())
            break
        time.sleep(5)
    else:
        log = sandbox.exec_command(["/bin/sh", "-c", "tail -n 50 /tmp/ffmpeg_install.log || true"])
        raise RuntimeError(f"Install timed out. Log:\n{log.output}")


if __name__ == "__main__":
    main()
