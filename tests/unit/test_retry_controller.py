from __future__ import annotations

from io import BytesIO
import json
import unittest
from urllib.error import HTTPError

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.api.scheduler import DataLensRequestScheduler
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.pipeline.retry_controller import retry_decision


def http_error(status: int) -> HTTPError:
    return HTTPError("https://api.datalens.tech/rpc/test", status, "failure", {}, BytesIO(b'{}'))


class SequenceTransport:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def post_json(self, url, body, headers):
        self.calls.append((url, dict(headers)))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return json.dumps(value).encode()


class RetryControllerTests(unittest.TestCase):
    def config(self) -> DataLensConfig:
        return DataLensConfig(iam_token="old", org_id="org", request_interval_sec=0)

    def test_401_probe_success_forbids_refresh(self):
        transport = SequenceTransport([http_error(401), {"workbooks": []}])
        refreshes = []
        client = DataLensApiClient(
            self.config(), transport=transport, token_refresher=lambda: refreshes.append(1) or "new"
        )
        with self.assertRaises(DataLensApiError) as raised:
            client.rpc_readonly("getDashboard", {"dashboardId": "synthetic"})
        self.assertEqual(refreshes, [])
        self.assertIn("probe_status=success", str(raised.exception))
        self.assertEqual(len(transport.calls), 2)

    def test_401_probe_401_refreshes_once_and_retries_safe_read(self):
        transport = SequenceTransport([http_error(401), http_error(401), {"ok": True}])
        refreshes = []
        client = DataLensApiClient(
            self.config(), transport=transport, token_refresher=lambda: refreshes.append(1) or "new"
        )
        self.assertEqual(client.rpc_readonly("getDashboard", {"dashboardId": "synthetic"}), {"ok": True})
        self.assertEqual(refreshes, [1])
        self.assertEqual(len(transport.calls), 3)

    def test_403_never_refreshes_and_ambiguous_write_reconciles(self):
        self.assertFalse(retry_decision("AUTH_403_PERMISSION_DENIED", readonly=True).refresh_token)
        decision = retry_decision("AMBIGUOUS_WRITE", readonly=False)
        self.assertTrue(decision.reconcile)
        self.assertFalse(decision.retry)

    def test_rate_limit_cooldown_is_shared(self):
        now = [10.0]
        scheduler = DataLensRequestScheduler(clock=lambda: now[0], sleeper=lambda delay: now.__setitem__(0, now[0] + delay))
        scheduler.note_rate_limit(key="api", method="getDashboard", retry_after_sec=7)
        self.assertEqual(scheduler.cooldown_remaining("api"), 7)
        self.assertEqual(scheduler.snapshot()["cooldown_remaining_sec"], 7)
