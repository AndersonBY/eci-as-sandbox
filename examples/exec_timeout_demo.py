import os
import time
from pathlib import Path

from eci_as_sandbox import EciSandbox


def main(sandbox_id: str) -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    client = EciSandbox(env_file=str(env_path) if env_path.exists() else None)

    print(f"Using sandbox: {sandbox_id}")

    result = client.exec_command(
        sandbox_id,
        ["/bin/sh", "-c", "for i in 1 2 3 4 5; do echo tick-$i; sleep 2; done"],
        timeout=3,
    )

    print("Success:", result.success)
    print("Error:", result.error_message)
    print("Output:")
    print(result.output.strip())

    time.sleep(4)
    follow_up = client.exec_command(
        sandbox_id,
        ["/bin/sh", "-c", "tail -n 20 /tmp/eci_sandbox_exec_*.log 2>/dev/null || true"],
    )
    print("Follow-up output:")
    print(follow_up.output.strip())


if __name__ == "__main__":
    if "TEST_ECI_SANDBOX_ID" not in os.environ:
        raise RuntimeError("Please set the TEST_ECI_SANDBOX_ID environment variable.")
    main(os.environ["TEST_ECI_SANDBOX_ID"])
