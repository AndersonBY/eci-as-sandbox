"""Submission evidence must survive both API and WebSocket transports."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from eci_as_sandbox._async.client import AsyncEciSandbox
from eci_as_sandbox._common.models import CommandResult
from eci_as_sandbox._sync.client import EciSandbox


class ProviderError(RuntimeError):
    def __init__(self, code):
        super().__init__("provider rejected request")
        self.code = code


class ExecEvidenceTests(unittest.TestCase):
    async def exercise(self, asynchronous, websocket, *, error=None, after_accept=False, uri=True):
        cls = AsyncEciSandbox if asynchronous else EciSandbox
        client = object.__new__(cls)
        client.region_id = "test-region"
        factory = AsyncMock if asynchronous else Mock
        response = SimpleNamespace(to_map=lambda: {"body": {"RequestId": "request-1", **({"WebSocketUri": "wss://transport.invalid"} if uri else {})}})
        submit = factory(return_value=response)
        observe = factory(return_value="confirmed output")
        if error is not None:
            (observe if after_accept else submit).side_effect = error
        client.client = SimpleNamespace(
            exec_container_command_with_options=submit,
            exec_container_command_with_options_async=submit,
        )
        client._exec_container_command = submit
        client._read_ws_output = observe
        client._send_command_via_ws = observe
        module = "eci_as_sandbox._async.client" if asynchronous else "eci_as_sandbox._sync.client"
        with (
            patch(module + ".time.monotonic", side_effect=[10.0, 12.0, 14.0, 15.0]),
            patch(module + "._log_operation_error"),
            patch(module + "._log_api_call"),
            patch(module + "._log_api_response"),
        ):
            result = (
                client._exec_via_ws("sandbox", "echo hello", "container", 20)
                if websocket else client.exec_command("sandbox", ["echo", "hello"], container_name="container", timeout=20)
            )
            if asynchronous:
                result = await result
        return result, submit, observe

    def cases(self, **kwargs):
        for asynchronous in (False, True):
            for websocket in (False, True):
                with self.subTest(asynchronous=asynchronous, websocket=websocket):
                    yield websocket, asyncio.run(self.exercise(asynchronous, websocket, **kwargs))

    def test_explicit_status_rejection_is_not_a_dispatch(self):
        for _, (result, submit, observe) in self.cases(error=ProviderError("IncorrectStatus")):
            self.assertFalse(result.success)
            self.assertEqual(result.code, "IncorrectStatus")
            self.assertIs(result.command_dispatched, False)
            submit.assert_called_once()
            observe.assert_not_called()

    def test_invalid_request_keeps_permanent_code(self):
        for _, (result, _, _) in self.cases(error=ProviderError("InvalidParameter.ValueExceeded")):
            self.assertEqual(result.code, "InvalidParameter.ValueExceeded")
            self.assertIs(result.command_dispatched, False)

    def test_request_timeout_does_not_prove_non_execution(self):
        for _, (result, submit, observe) in self.cases(error=TimeoutError("reply lost")):
            self.assertIsNone(result.command_dispatched)
            submit.assert_called_once()
            observe.assert_not_called()

    def test_reply_loss_after_acceptance_retains_identity(self):
        for _, (result, submit, observe) in self.cases(error=TimeoutError("observation lost"), after_accept=True):
            self.assertFalse(result.success)
            self.assertIs(result.command_dispatched, True)
            self.assertEqual(result.request_id, "request-1")
            submit.assert_called_once()
            observe.assert_called_once()

    def test_missing_output_uri_is_not_a_new_submission_authority(self):
        for websocket, (result, submit, observe) in self.cases(uri=False):
            self.assertFalse(result.success)
            # Interactive bash has not received user stdin; ordinary exec has
            # already submitted the command along with the API request.
            self.assertIs(result.command_dispatched, not websocket)
            submit.assert_called_once()
            observe.assert_not_called()

    def test_observation_uses_remaining_deadline(self):
        for _, (result, submit, observe) in self.cases():
            self.assertTrue(result.success)
            self.assertIs(result.command_dispatched, True)
            self.assertEqual(result.output, "confirmed output")
            self.assertLess(observe.call_args.args[-1], 20)
            submit.assert_called_once()

    def test_long_command_script_survives_unknown_start_reply(self):
        async def run(asynchronous, dispatched):
            cls = AsyncEciSandbox if asynchronous else EciSandbox
            client = object.__new__(cls)
            factory = AsyncMock if asynchronous else Mock
            client.write_file_ws = factory(return_value=CommandResult(success=True))
            client.bash = factory(return_value=CommandResult(success=False, command_dispatched=dispatched))
            value = client._tmux_start_via_file("sandbox", "user command", "original-session", "container")
            if asynchronous:
                value = await value
            self.assertFalse(value.success)
            self.assertIs(value.command_dispatched, dispatched)
            self.assertEqual(client.bash.call_count, 2 if dispatched is False else 1)

        for asynchronous in (False, True):
            for dispatched in (False, True, None):
                with self.subTest(asynchronous=asynchronous, dispatched=dispatched):
                    asyncio.run(run(asynchronous, dispatched))


if __name__ == "__main__":
    unittest.main()
