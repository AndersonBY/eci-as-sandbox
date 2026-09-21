"""Exercise the SDK against real local tmux, replacing only the cloud transport."""
import asyncio
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from eci_as_sandbox import CommandResult, TmuxCommandStatus
from eci_as_sandbox._async.client import AsyncEciSandbox
from eci_as_sandbox._sync.client import EciSandbox


@unittest.skipUnless(shutil.which("tmux"), "requires a local tmux executable")
class TmuxStartProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vv-tmux-test-")
        self.addCleanup(self.temp.cleanup)
        self.env = dict(os.environ, TMUX_TMPDIR=self.temp.name)
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)
        self.scripts = []
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        subprocess.run(["tmux", "kill-server"], env=self.env, capture_output=True, timeout=5, check=False)
        for path in self.scripts:
            path.unlink(missing_ok=True)

    def local_bash(self, *, command, **kwargs):
        # Deterministically expose the former scheduling race between the two
        # separate tmux clients. The corrected command has no such second call.
        command = command.replace("; tmux set-option", "; sleep 0.15; tmux set-option")
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=self.temp.name,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return CommandResult(request_id="local-transport", success=result.returncode == 0,
                             output=result.stdout, error_message=result.stderr if result.returncode else "")

    def write_script(self, *, file_path, content, **kwargs):
        path = Path(file_path)
        self.assertEqual(path.parent, Path("/tmp"))
        self.assertTrue(path.name.startswith("tmux_cmd_vv_test_"))
        path.write_text(content, encoding="utf-8")
        self.scripts.append(path)
        return CommandResult(request_id="local-write", success=True, output="")

    async def exercise(self, asynchronous, *, long_command, exit_code):
        if asynchronous:
            client = object.__new__(AsyncEciSandbox)

            async def bash(**kwargs):
                return self.local_bash(**kwargs)

            async def write(**kwargs):
                return self.write_script(**kwargs)

            client.bash, client.write_file_ws = bash, write
        else:
            client = object.__new__(EciSandbox)
            client.bash, client.write_file_ws = self.local_bash, self.write_script

        async def invoke(method, **kwargs):
            result = getattr(client, method)(sandbox_id="local", container_name="local", **kwargs)
            return await result if asynchronous else result

        session = "vv_test_" + uuid.uuid4().hex[:12]
        command = "printf 'once\\n' >> executions.txt; printf 'verified output\\n'; exit " + str(exit_code)
        if long_command:
            command = "# " + "long command " * 200 + "\n" + command
        started = await invoke("tmux_start", command=command, session_id=session, exec_dir=self.temp.name)
        self.assertTrue(started.success, started.error_message)
        deadline = time.monotonic() + 5
        while True:
            result = await invoke("tmux_poll", session_id=session)
            if result.status != TmuxCommandStatus.RUNNING or time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.02)
        self.assertEqual(result.status, TmuxCommandStatus.COMPLETED, result)
        self.assertEqual(result.exit_code, exit_code)
        self.assertIn("verified output", result.output)
        self.assertEqual((Path(self.temp.name) / "executions.txt").read_text(), "once\n")
        self.assertEqual(bool(self.scripts), long_command)

        duplicate = await invoke("tmux_start", command="printf duplicate >> executions.txt", session_id=session)
        self.assertFalse(duplicate.success)
        self.assertEqual((Path(self.temp.name) / "executions.txt").read_text(), "once\n")

    def test_sync_short_command(self):
        asyncio.run(self.exercise(False, long_command=False, exit_code=0))

    def test_sync_long_nonzero_command(self):
        asyncio.run(self.exercise(False, long_command=True, exit_code=7))

    def test_async_short_command(self):
        asyncio.run(self.exercise(True, long_command=False, exit_code=0))

    def test_async_long_nonzero_command(self):
        asyncio.run(self.exercise(True, long_command=True, exit_code=7))


if __name__ == "__main__":
    unittest.main()
