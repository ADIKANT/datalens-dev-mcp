import json
import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from datalens_dev_mcp.api.client import DataLensApiClient, _retry_after_seconds
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.api.scheduler import DataLensRequestScheduler, TokenRefreshCoordinator
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.tools.discovery import dl_get_workbook_entries


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.value

    def sleep(self, seconds):
        with self.lock:
            self.value += max(0.0, seconds)


class SequenceTransport:
    def __init__(self, responses, clock=None):
        self.responses = list(responses)
        self.clock = clock
        self.starts = []
        self.requests = []

    def post_json(self, url, body, headers):
        if self.clock is not None:
            self.starts.append(self.clock())
        self.requests.append((url, json.loads(body.decode("utf-8")), dict(headers)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response).encode("utf-8")


def http_error(status, payload, headers=None):
    return HTTPError(
        url="https://api.datalens.tech/rpc/getWorkbooksList",
        code=status,
        msg="error",
        hdrs=headers or {},
        fp=BytesIO(json.dumps(payload).encode("utf-8")),
    )


class BatchWorkbookClient:
    def __init__(self):
        self.config = SimpleNamespace(max_read_concurrency=3)
        self.calls = []
        self.lock = threading.Lock()

    def rpc_readonly(self, method, payload):
        with self.lock:
            self.calls.append((method, dict(payload)))
        workbook_id = payload["workbookId"]
        if workbook_id == "missing":
            raise DataLensApiError("getWorkbookEntries failed with HTTP 404: workbook not found")
        return {
            "workbookId": workbook_id,
            "entries": [{"entryId": f"entry_{workbook_id}", "scope": "dashboard"}],
        }


class ApiSchedulerAndBatchTests(unittest.TestCase):
    def test_request_start_spacing_is_shared_across_new_clients(self):
        clock = FakeClock()
        scheduler = DataLensRequestScheduler(clock=clock, sleeper=clock.sleep)
        transport = SequenceTransport([{"workbooks": []}, {"workbooks": []}], clock=clock)
        config = DataLensConfig(
            iam_token="token",
            org_id="org",
            request_interval_sec=1.05,
            max_read_concurrency=3,
        )
        with patch("datalens_dev_mcp.api.client.REQUEST_SCHEDULER", scheduler):
            DataLensApiClient(config, transport=transport).rpc_readonly(
                "getWorkbooksList", {"page": 1, "pageSize": 1}
            )
            DataLensApiClient(config, transport=transport).rpc_readonly(
                "getWorkbooksList", {"page": 1, "pageSize": 1}
            )

        self.assertEqual(transport.starts, [0.0, 1.05])
        status = scheduler.snapshot()
        self.assertEqual(status["totals"]["requests"], 2)
        self.assertEqual(status["effective_request_starts_per_minute"], 57.14)

    def test_three_reads_overlap_and_write_is_exclusive(self):
        scheduler = DataLensRequestScheduler()
        read_barrier = threading.Barrier(4)
        read_release = threading.Event()
        writer_started = threading.Event()
        writer_release = threading.Event()
        late_read_started = threading.Event()

        def read_operation():
            read_barrier.wait()
            read_release.wait()
            return b"{}"

        def writer_operation():
            writer_started.set()
            writer_release.wait()
            return b"{}"

        def late_read_operation():
            late_read_started.set()
            return b"{}"

        readers = [
            threading.Thread(
                target=lambda: scheduler.execute(
                    key="shared",
                    method="getDashboard",
                    readonly=True,
                    interval_sec=0,
                    max_read_concurrency=3,
                    operation=read_operation,
                )
            )
            for _ in range(3)
        ]
        for thread in readers:
            thread.start()
        read_barrier.wait()
        writer = threading.Thread(
            target=lambda: scheduler.execute(
                key="shared",
                method="updateDashboard",
                readonly=False,
                interval_sec=0,
                max_read_concurrency=3,
                operation=writer_operation,
            )
        )
        writer.start()
        self.assertFalse(writer_started.wait(0.05))
        late_reader = threading.Thread(
            target=lambda: scheduler.execute(
                key="shared",
                method="getDataset",
                readonly=True,
                interval_sec=0,
                max_read_concurrency=3,
                operation=late_read_operation,
            )
        )
        late_reader.start()
        read_release.set()
        for thread in readers:
            thread.join(1)
        self.assertTrue(writer_started.wait(1))
        self.assertFalse(late_read_started.wait(0.05))
        writer_release.set()
        writer.join(1)
        late_reader.join(1)
        self.assertTrue(late_read_started.is_set())

    def test_fresh_read_can_take_the_same_exclusive_slot_as_a_write(self):
        scheduler = DataLensRequestScheduler()
        exclusive_started = threading.Event()
        exclusive_release = threading.Event()
        regular_started = threading.Event()

        def exclusive_operation():
            exclusive_started.set()
            exclusive_release.wait()
            return b"{}"

        exclusive = threading.Thread(
            target=lambda: scheduler.execute(
                key="shared",
                method="getDashboard",
                readonly=True,
                exclusive=True,
                interval_sec=0,
                max_read_concurrency=3,
                operation=exclusive_operation,
            )
        )
        regular = threading.Thread(
            target=lambda: scheduler.execute(
                key="shared",
                method="getDataset",
                readonly=True,
                interval_sec=0,
                max_read_concurrency=3,
                operation=lambda: regular_started.set() or b"{}",
            )
        )
        exclusive.start()
        self.assertTrue(exclusive_started.wait(1))
        regular.start()
        self.assertFalse(regular_started.wait(0.05))
        self.assertEqual(scheduler.snapshot()["active_writes"], 0)
        self.assertEqual(scheduler.snapshot()["active_exclusive_operations"], 1)
        exclusive_release.set()
        exclusive.join(1)
        regular.join(1)
        self.assertTrue(regular_started.is_set())

    def test_429_retry_after_uses_global_cooldown_and_http_date_parser(self):
        clock = FakeClock()
        scheduler = DataLensRequestScheduler(clock=clock, sleeper=clock.sleep)
        transport = SequenceTransport(
            [
                http_error(429, {"message": "rate limited"}, {"Retry-After": "2"}),
                {"workbooks": []},
            ],
            clock=clock,
        )
        config = DataLensConfig(
            iam_token="token",
            org_id="org",
            request_interval_sec=0,
            rate_limit_retries=1,
        )
        with patch("datalens_dev_mcp.api.client.REQUEST_SCHEDULER", scheduler):
            result = DataLensApiClient(config, transport=transport).rpc_readonly(
                "getWorkbooksList", {"page": 1, "pageSize": 1}
            )

        self.assertEqual(result, {"workbooks": []})
        self.assertEqual(transport.starts, [0.0, 2.0])
        self.assertEqual(scheduler.snapshot()["totals"]["rate_limit_429"], 1)
        self.assertEqual(
            _retry_after_seconds(
                "Thu, 01 Jan 1970 00:00:05 GMT",
                fallback=1,
                wall_time=2,
            ),
            3,
        )

    def test_429_cooldown_blocks_a_new_client_for_the_same_api(self):
        clock = FakeClock()
        scheduler = DataLensRequestScheduler(clock=clock, sleeper=clock.sleep)
        first_transport = SequenceTransport(
            [http_error(429, {"message": "rate limited"}, {"Retry-After": "2"})],
            clock=clock,
        )
        second_transport = SequenceTransport([{"workbooks": []}], clock=clock)
        config = DataLensConfig(
            iam_token="token",
            org_id="org",
            request_interval_sec=0,
            rate_limit_retries=0,
        )
        with patch("datalens_dev_mcp.api.client.REQUEST_SCHEDULER", scheduler):
            with self.assertRaises(DataLensApiError):
                DataLensApiClient(config, transport=first_transport).rpc_readonly(
                    "getWorkbooksList", {"page": 1, "pageSize": 1}
                )
            result = DataLensApiClient(config, transport=second_transport).rpc_readonly(
                "getWorkbooksList", {"page": 1, "pageSize": 1}
            )

        self.assertEqual(result, {"workbooks": []})
        self.assertEqual(first_transport.starts, [0.0])
        self.assertEqual(second_transport.starts, [2.0])

    def test_transient_retry_is_read_only_and_404_is_terminal(self):
        from http.client import RemoteDisconnected

        read_transport = SequenceTransport([RemoteDisconnected("closed"), {"workbooks": []}])
        config = DataLensConfig(
            iam_token="token",
            org_id="org",
            request_interval_sec=0,
            read_transient_retries=2,
        )
        with patch("datalens_dev_mcp.api.client._transient_retry_pause", return_value=None):
            result = DataLensApiClient(config, transport=read_transport).rpc_readonly(
                "getWorkbooksList", {"page": 1, "pageSize": 1}
            )
        self.assertEqual(result, {"workbooks": []})
        self.assertEqual(len(read_transport.requests), 2)

        service_transport = SequenceTransport(
            [http_error(503, {"message": "temporarily unavailable"}), {"workbooks": []}]
        )
        with patch("datalens_dev_mcp.api.client._transient_retry_pause", return_value=None):
            result = DataLensApiClient(config, transport=service_transport).rpc_readonly(
                "getWorkbooksList", {"page": 1, "pageSize": 1}
            )
        self.assertEqual(result, {"workbooks": []})
        self.assertEqual(len(service_transport.requests), 2)

        write_transport = SequenceTransport([RemoteDisconnected("closed"), {"ok": True}])
        with patch("datalens_dev_mcp.api.client._transient_retry_pause", return_value=None):
            with self.assertRaises(DataLensApiError):
                DataLensApiClient(config, transport=write_transport).rpc(
                    "updateDashboard", {"entry": {"entryId": "dashboard_1"}}
                )
        self.assertEqual(len(write_transport.requests), 1)

        missing_transport = SequenceTransport([http_error(404, {"message": "missing"}), {"workbooks": []}])
        with self.assertRaises(DataLensApiError):
            DataLensApiClient(config, transport=missing_transport).rpc_readonly(
                "getWorkbooksList", {"page": 1, "pageSize": 1}
            )
        self.assertEqual(len(missing_transport.requests), 1)

    def test_token_refresh_is_single_flight(self):
        coordinator = TokenRefreshCoordinator()
        refresh_started = threading.Event()
        release_refresh = threading.Event()
        calls = []
        results = []

        def refresher():
            calls.append("refresh")
            refresh_started.set()
            release_refresh.wait()
            return "fresh-token"

        first = threading.Thread(target=lambda: results.append(coordinator.refresh("key", refresher)))
        second = threading.Thread(target=lambda: results.append(coordinator.refresh("key", refresher)))
        first.start()
        self.assertTrue(refresh_started.wait(1))
        second.start()
        release_refresh.set()
        first.join(1)
        second.join(1)

        self.assertEqual(calls, ["refresh"])
        self.assertEqual(results, ["fresh-token", "fresh-token"])

    def test_token_refresh_timeout_uses_short_negative_cooldown(self):
        clock = FakeClock()
        coordinator = TokenRefreshCoordinator(clock=clock)
        calls = []

        def refresher():
            calls.append("refresh")
            raise TimeoutError("timed out")

        with self.assertRaises(TimeoutError):
            coordinator.refresh("key", refresher, negative_cooldown_sec=3)
        with self.assertRaises(TimeoutError):
            coordinator.refresh("key", refresher, negative_cooldown_sec=3)
        self.assertEqual(calls, ["refresh"])
        clock.sleep(3.1)
        with self.assertRaises(TimeoutError):
            coordinator.refresh("key", refresher, negative_cooldown_sec=3)
        self.assertEqual(calls, ["refresh", "refresh"])

    def test_batch_workbook_read_preserves_order_and_partial_errors(self):
        client = BatchWorkbookClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = dl_get_workbook_entries(
                workbook_ids=["first", "missing", "third"],
                scope="all",
                project_root=tmp,
                client=client,
            )

            self.assertEqual([item["workbook_id"] for item in result["items"]], ["first", "missing", "third"])
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["succeeded"], 2)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["items"][1]["error"]["http_status"], 404)
            self.assertFalse(result["items"][1]["error"]["retryable"])
            self.assertTrue(Path(result["items"][0]["artifact"]["path"]).is_file())
            self.assertTrue(Path(result["items"][2]["artifact"]["path"]).is_file())
            self.assertNotEqual(
                result["items"][0]["artifact"]["path"],
                result["items"][2]["artifact"]["path"],
            )
        self.assertTrue(all("scope" not in payload for _, payload in client.calls))

    def test_batch_scope_validation_happens_before_http(self):
        client = BatchWorkbookClient()
        with self.assertRaises(ValueError):
            dl_get_workbook_entries(
                workbook_ids=["first", "second"],
                scope=["all", "dashboard"],
                client=client,
            )
        with self.assertRaises(ValueError):
            dl_get_workbook_entries(
                workbook_ids=["first"],
                response_mode="invalid",
                client=client,
            )
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
