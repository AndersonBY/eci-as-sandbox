"""Deletion must build a request the installed ECI SDK accepts."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from alibabacloud_eci20180808 import models as eci_models

from eci_as_sandbox._async.client import AsyncEciSandbox
from eci_as_sandbox._sync.client import EciSandbox


class DeleteTests(unittest.TestCase):
    async def exercise(self, asynchronous, *, force, error=None):
        cls = AsyncEciSandbox if asynchronous else EciSandbox
        client = object.__new__(cls)
        client.region_id = "test-region"
        client._sandboxes = {"sandbox": object()}
        response = SimpleNamespace(to_map=lambda: {"body": {"RequestId": "request-1"}})
        call = (AsyncMock if asynchronous else Mock)(return_value=response, side_effect=error)
        client.client = SimpleNamespace(delete_container_group=call, delete_container_group_async=call)
        module = "eci_as_sandbox._async.client" if asynchronous else "eci_as_sandbox._sync.client"
        with (
            patch(module + "._log_operation_error"),
            patch(module + "._log_api_call"),
            patch(module + "._log_api_response"),
        ):
            result = client.delete("sandbox", force=force)
            if asynchronous:
                result = await result
        return client, result, call

    def test_delete_sends_supported_request_with_and_without_force(self):
        for asynchronous in (False, True):
            for force in (False, True):
                with self.subTest(asynchronous=asynchronous, force=force):
                    client, result, call = asyncio.run(self.exercise(asynchronous, force=force))
                    self.assertTrue(result.success, result.error_message)
                    self.assertEqual(result.request_id, "request-1")
                    self.assertNotIn("sandbox", client._sandboxes)
                    (request,), _ = call.call_args
                    self.assertIsInstance(request, eci_models.DeleteContainerGroupRequest)
                    self.assertEqual(request.region_id, "test-region")
                    self.assertEqual(request.container_group_id, "sandbox")

    def test_request_construction_errors_are_reported_not_raised(self):
        module = "eci_as_sandbox._{}.client.eci_models.DeleteContainerGroupRequest"
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                with patch(module.format("async" if asynchronous else "sync"), side_effect=TypeError("bad kwarg")):
                    client, result, call = asyncio.run(self.exercise(asynchronous, force=True))
                self.assertFalse(result.success)
                self.assertIn("bad kwarg", result.error_message)
                self.assertIn("sandbox", client._sandboxes)
                call.assert_not_called()

    def test_provider_error_is_reported(self):
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                client, result, _ = asyncio.run(self.exercise(asynchronous, force=False, error=RuntimeError("denied")))
                self.assertFalse(result.success)
                self.assertIn("denied", result.error_message)
                self.assertIn("sandbox", client._sandboxes)


if __name__ == "__main__":
    unittest.main()
