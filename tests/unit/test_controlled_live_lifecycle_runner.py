import importlib.util
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from datalens_dev_mcp.config import DataLensConfig


ROOT = Path(__file__).resolve().parents[2]
TEST_WORKBOOK_ID = "syntheticwb01"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_controlled_live_lifecycle",
        ROOT / "scripts" / "run_controlled_live_lifecycle.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ControlledLiveLifecycleRunnerTests(unittest.TestCase):
    def test_runner_requires_explicit_live_write_approval(self):
        runner = load_runner()
        class NetworkBlockedClient:
            def rpc(self, method, payload):
                raise AssertionError("approval guard must block before network access")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(runner.ControlledLiveBlocked) as raised:
                runner.run_controlled_lifecycle(
                    out=Path(tmp) / "controlled_lifecycle_raw.json",
                    approved_live_writes=False,
                    approval_note="",
                    test_workbook_id=TEST_WORKBOOK_ID,
                    client=NetworkBlockedClient(),
                    config=DataLensConfig(write_enabled=False, expert_rpc_enabled=True),
                    env={},
                )

        self.assertIn("explicit --approved-live-writes", str(raised.exception))

    def test_cli_workbook_and_approval_do_not_require_manual_env_flags(self):
        runner = load_runner()

        class NetworkReached(RuntimeError):
            pass

        class NetworkProbeClient:
            def rpc(self, method, payload):
                raise NetworkReached(method)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(NetworkReached) as raised:
                runner.run_controlled_lifecycle(
                    out=Path(tmp) / "controlled_lifecycle_raw.json",
                    approved_live_writes=True,
                    approval_note="approved controlled test writes",
                    test_workbook_id=TEST_WORKBOOK_ID,
                    confirm_disposable_workbook=True,
                    client=NetworkProbeClient(),
                    config=DataLensConfig(write_enabled=False, expert_rpc_enabled=True),
                    env={},
                )

        self.assertEqual(str(raised.exception), "getWorkbookEntries")

    def test_disposable_workbook_confirmation_is_required_before_network(self):
        runner = load_runner()

        class NetworkBlockedClient:
            def rpc(self, method, payload):
                raise AssertionError("workbook guard must block before network access")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(runner.ControlledLiveBlocked) as raised:
                runner.run_controlled_lifecycle(
                    out=Path(tmp) / "controlled_lifecycle_raw.json",
                    approved_live_writes=True,
                    approval_note="approved controlled test writes",
                    test_workbook_id=TEST_WORKBOOK_ID,
                    client=NetworkBlockedClient(),
                    config=DataLensConfig(),
                    env={},
                )
        self.assertIn("confirm-disposable-workbook", str(raised.exception))

    def test_transient_env_does_not_leak_to_process_env_after_helper(self):
        runner = load_runner()

        class NetworkReached(RuntimeError):
            pass

        class NetworkProbeClient:
            def rpc(self, method, payload):
                raise NetworkReached(method)

        flag_names = set(runner.CONTROLLED_TRANSIENT_FLAGS) | {"DATALENS_MCP_TEST_WORKBOOK_ID"}
        with mock.patch.dict(os.environ, {}, clear=True):
            before = {name: os.environ.get(name) for name in flag_names}
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(NetworkReached):
                    runner.run_controlled_lifecycle(
                        out=Path(tmp) / "controlled_lifecycle_raw.json",
                        approved_live_writes=True,
                        approval_note="approved controlled test writes",
                        test_workbook_id=TEST_WORKBOOK_ID,
                        confirm_disposable_workbook=True,
                        client=NetworkProbeClient(),
                        config=DataLensConfig(),
                        env={},
                    )
            after = {name: os.environ.get(name) for name in flag_names}

        self.assertEqual(before, after)

    def test_runtime_preflight_records_transient_scope_and_no_token_mint(self):
        runner = load_runner()
        cfg = runner.build_transient_controlled_config(
            DataLensConfig(write_enabled=False, expert_rpc_enabled=True, token_refresh_enabled=True)
        )
        env = runner.build_transient_controlled_env({}, TEST_WORKBOOK_ID)

        preflight = runner.runtime_preflight_summary(
            cfg=cfg,
            env=env,
            workbook_id=TEST_WORKBOOK_ID,
            auth_probe_ok=True,
        )

        self.assertFalse(preflight["manual_env_exports_required"])
        self.assertTrue(preflight["transient_guarded_env"])
        self.assertFalse(preflight["transient_env_persisted"])
        self.assertFalse(preflight["canonical_env_file_mutated"])
        self.assertFalse(preflight["token_refresh_on_401_enabled"])
        self.assertFalse(preflight["unconditional_token_mint_at_startup"])

    def test_optional_connection_skip_does_not_make_global_result_false(self):
        runner = load_runner()
        routes = [self._verified_route(route, publishable=route != "dataset") for route in runner.CONTROLLED_LIVE_REQUIRED_ROUTES]
        routes.append(
            {
                "route": "connection",
                "state": "documented_but_not_live_write_verified",
                "status": "skipped",
                "reason": "connection readback omits canonical create type/secret material required for safe clone",
            }
        )

        summary = runner.summarize_route_evidence(routes)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["documented_non_blocking_routes"], ["connection"])
        self.assertEqual(summary["missing_required_routes"], [])

    def test_release_decision_requires_evidence_complete_verified_routes(self):
        runner = load_runner()
        routes = [self._verified_route(route, publishable=route != "dataset") for route in runner.CONTROLLED_LIVE_REQUIRED_ROUTES]
        routes[0]["artifacts"].pop("saved_read")

        summary = runner.summarize_route_evidence(routes)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["malformed_verified_routes"][0]["route"], routes[0]["route"])
        self.assertIn("artifacts.saved_read", summary["malformed_verified_routes"][0]["missing"])

    def test_release_decision_is_derived_from_required_evidence_states(self):
        runner = load_runner()
        routes = [self._verified_route(route, publishable=route != "dataset") for route in runner.CONTROLLED_LIVE_REQUIRED_ROUTES]
        routes = [route for route in routes if route["route"] != "dashboard"]

        summary = runner.summarize_route_evidence(routes)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["missing_required_routes"], ["dashboard"])

    def test_stale_revision_negative_uses_safe_apply_without_write_rpc(self):
        runner = load_runner()

        class FakeClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "updateEditorChart":
                    raise AssertionError("stale negative must not attempt write")
                return {
                    "entry": {
                        "entryId": payload["chartId"],
                        "revId": "actual_live_revision",
                        "name": "fixture",
                    }
                }

        client = FakeClient()
        route = {
            "route": "editor_chart",
            "read_method": "getEditorChart",
            "update_method": "updateEditorChart",
            "id_key": "chartId",
        }

        with tempfile.TemporaryDirectory() as tmp:
            result = runner.run_stale_negative(
                client=client,
                root=Path(tmp),
                run_id="unit",
                route=route,
                payload={"mode": "save", "entry": {"entryId": "chart_1", "revId": "rev_live"}},
                object_id="chart_1",
                config=DataLensConfig(write_enabled=True),
            )

        self.assertEqual(result["status"], "blocked_expected")
        self.assertFalse(result["write_attempted"])
        self.assertEqual([call[0] for call in client.calls], ["getEditorChart"])

    def _verified_route(self, route: str, *, publishable: bool) -> dict:
        artifacts = {
            "create": {"path": f"{route}/create.json"},
            "saved_read": {"path": f"{route}/saved.json"},
            "noop_update": {"path": f"{route}/noop.json"},
            "post_noop_read": {"path": f"{route}/post_noop.json"},
            "meaningful_update": {"path": f"{route}/meaningful.json"},
            "updated_read": {"path": f"{route}/updated.json"},
            "publish": [{"path": f"{route}/publish.json"}] if publishable else [],
        }
        return {
            "route": route,
            "state": "controlled_live_write_verified",
            "status": "completed",
            "publishable": publishable,
            "object_id": f"{route}_id",
            "artifacts": artifacts,
        }


if __name__ == "__main__":
    unittest.main()
