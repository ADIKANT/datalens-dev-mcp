from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.server import (
    AUTONOMOUS_TOOL_NAMES,
    LEGACY_TOOL_NAMES,
    TOOLS,
    JsonRpcServer,
    list_tools,
)
from datalens_dev_mcp.mcp.heavy_response import project_task_tool_response
from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.artifacts import write_json
from datalens_dev_mcp.pipeline.project_journal import JournalIdentityError, ProjectJournal
from datalens_dev_mcp.pipeline.build_identity import BuildIdentityResolver
from datalens_dev_mcp.pipeline.execution_authorization import resolve_execution_authorization
from datalens_dev_mcp.pipeline.target_binding import resolve_contract_target_binding
from datalens_dev_mcp.pipeline.target_binding import create_live_target_binding
from datalens_dev_mcp.pipeline.target_graph import build_target_graph
from datalens_dev_mcp.pipeline.task_contract import (
    DeliveryContract,
    ScopeContract,
    TargetContract,
    WorkspaceContract,
    create_task_contract,
)


class AutonomousToolSurfaceTests(unittest.TestCase):
    def test_single_run_owned_object_becomes_the_implicit_follow_up_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = ProjectJournal(tmp, "task-created-one")
            write_json(
                journal.delivery_root / "created-object-ownership.json",
                {
                    "objects": [
                        {
                            "object_id": "chart_created_1",
                            "object_type": "wizard_chart",
                            "workbook_id": "workbook_1",
                        }
                    ]
                },
            )

            inferred = tasks._run_owned_follow_up_target(
                journal,
                {"workbook_id": "workbook_1", "object_ids": [], "object_types": []},
                context={},
            )

            self.assertEqual(inferred["object_ids"], ["chart_created_1"])
            self.assertEqual(inferred["object_types"], ["wizard_chart"])

    def _amendable_journal(self, root: str, *, saved: bool = False) -> tuple[ProjectJournal, dict, str]:
        contract = create_task_contract(
            raw_request="Update dashboard:dash_1 and publish it",
            mode="update",
            route="wizard_native",
            workspace=WorkspaceContract(project_root=root),
            target=TargetContract(
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                object_ids=("dash_1",),
                object_types=("dashboard",),
                technology="wizard_native",
            ),
            scope=ScopeContract(allowed_objects=("dash_1",)),
            delivery=DeliveryContract(save=True, publish=True),
        ).to_dict()
        journal = ProjectJournal(root, contract["task_id"])
        build = BuildIdentityResolver().resolve()
        binding = resolve_contract_target_binding(contract)
        state, _, _ = journal.initialize_task(
            contract,
            build_identity=build,
            target_binding=binding,
            compile_receipt={"status": "compiled"},
            execution_grant=resolve_execution_authorization(contract),
        )
        next_state = "SAVED_READBACK" if saved else "VALIDATED"
        next_transition = "SAVED_READBACK -> PUBLISHED" if saved else "VALIDATED -> SAVED"
        with journal.locked(owner="amendment-test-fixture"):
            state, _ = journal.replay()
            journal.append_transition(
                state,
                transition="SYNTHETIC_FIXTURE_PROGRESS",
                input_value={},
                receipt_uri="",
                status="success",
                idempotency_key="fixture-saved" if saved else "fixture-validated",
                next_state=next_state,
                next_transition=next_transition,
            )
        plan_hash = "old-plan-hash"
        write_json(journal.root / "plans" / "plan.json", {"plan_hash": plan_hash})
        if saved:
            write_json(journal.saved_readback_receipt_path, {"status": "success", "revision": "saved-r1"})
        return journal, contract, plan_hash

    def test_default_surface_is_compact_and_has_no_low_level_duplicates(self) -> None:
        tools = list_tools("autonomous-v2")
        names = {tool["name"] for tool in tools}
        compact_bytes = len(json.dumps({"tools": tools}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        self.assertEqual(names, AUTONOMOUS_TOOL_NAMES)
        self.assertLessEqual(len(tools), 9)
        self.assertLessEqual(compact_bytes, 9_000)
        self.assertFalse(names & LEGACY_TOOL_NAMES)
        by_name = {tool["name"]: tool for tool in tools}
        self.assertTrue(by_name["dl_task_status"]["annotations"]["readOnlyHint"])
        self.assertFalse(by_name["dl_task_resume"]["annotations"]["readOnlyHint"])
        self.assertTrue(by_name["dl_execute"]["annotations"]["destructiveHint"])

    def test_legacy_surface_preserves_exact_39_tools_and_expert_is_operator_owned(self) -> None:
        self.assertEqual(len(LEGACY_TOOL_NAMES), 39)
        self.assertEqual({tool["name"] for tool in list_tools("legacy-v1")}, LEGACY_TOOL_NAMES)
        self.assertEqual({tool["name"] for tool in list_tools("expert")}, set(TOOLS))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"DATALENS_MCP_TOOL_SURFACE": "legacy-v1"}, clear=False):
                legacy = JsonRpcServer(project_root=tmp)
                listed = legacy.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
                self.assertEqual(listed["result"]["tool_count"], 39)
            with patch.dict(os.environ, {"DATALENS_MCP_TOOL_SURFACE": "expert"}, clear=False):
                expert = JsonRpcServer(project_root=tmp)
                self.assertEqual(expert.tool_surface, "expert")
            with patch.dict(os.environ, {}, clear=True):
                default = JsonRpcServer(project_root=tmp)
                rejected = default.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "dl_execute_safe_apply", "arguments": {}},
                    }
                )
                self.assertIn("error", rejected)
                self.assertIn("not exposed", rejected["error"]["message"])

    def test_initialization_and_argument_contracts_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            server = JsonRpcServer(project_root=tmp)
            initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertLessEqual(len(initialized["result"]["instructions"].encode("utf-8")), 1_500)
            listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            self.assertEqual(listed["result"]["tool_surface"], "autonomous-v2")
            self.assertEqual(listed["result"]["tool_count"], 8)
            invalid = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "dl_task_status", "arguments": {"task_id": "missing", "extra": True}},
                }
            )
            payload = json.loads(invalid["result"]["content"][0]["text"])
            self.assertTrue(invalid["result"]["isError"])
            self.assertEqual(payload["error"]["category"], "invalid_tool_arguments")
            self.assertEqual(payload["error"]["unknown"], ["extra"])

    def test_oversized_task_response_falls_back_to_resource_binding(self) -> None:
        projected = project_task_tool_response(
            "dl_task_resume",
            {
                "task_id": "task-1",
                "state": "PLAN_VALIDATED",
                "resource_uri": "datalens://tasks/task-1",
                "observed_facts": ["x" * 7_000],
            },
        )
        self.assertTrue(projected["inline_truncated"])
        self.assertEqual(projected["resource_uri"], "datalens://tasks/task-1")
        self.assertNotIn("observed_facts", projected)

    def test_completed_start_cannot_bypass_required_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def execute(**kwargs):
                result = {"ok": True, "status": "completed", "executed": True, "results": []}
                write_json(Path(tmp) / "artifacts" / "safe_apply_result.json", result)
                return result

            safe_plan = {"ok": True, "status": "planned", "actions": [{"method": "updateDashboard"}]}
            with (
                patch.object(tasks.pipeline, "dl_validate_project", return_value={"ok": True, "status": "pass"}),
                patch.object(tasks.pipeline, "dl_create_safe_apply_plan", return_value=safe_plan),
                patch.object(tasks.pipeline, "dl_execute_safe_apply", side_effect=execute),
            ):
                result = tasks.dl_task_start(
                    "Update the current dashboard and publish it",
                    project_root=tmp,
                    run_until="completed",
                )

            self.assertEqual(result["state"], "BLOCKED")
            self.assertEqual(result["blocked_by"]["code"], "BLOCKED_DISCOVERY")

    def test_provider_discovery_failure_is_actionable_and_retryable_after_recovery(self) -> None:
        from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
        from tests.unit.test_target_discovery import DiscoveryClient

        scenarios = (
            (
                "credential_recovery",
                DataLensApiError(
                    "sanitized token refresh failure",
                    failure_family="AUTH_401_TOKEN_INVALID_OR_EXPIRED",
                ),
                "credential_recovery_required",
            ),
            (
                "transport",
                DataLensApiError(
                    "sanitized provider timeout",
                    request_phase="read",
                    response_received=False,
                    transport_category="transport_timeout",
                ),
                "transport_timeout",
            ),
        )
        for label, failure, expected_category in scenarios:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                failure.provider_method = "getDashboard"
                with patch(
                    "datalens_dev_mcp.mcp.tools.tasks.TargetDiscoveryService.discover",
                    side_effect=failure,
                ):
                    result = tasks.dl_task_start(
                        "Review https://datalens.example/dash_demo",
                        project_root=tmp,
                    )

                journal = ProjectJournal(tmp, result["task_id"])
                receipt_path = next((journal.root / "receipts").glob(
                    "target-discovery-blocked-*.json"
                ))
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertEqual(receipt["provider_calls"][0]["method"], "getDashboard")
                self.assertEqual(receipt["provider_calls"][0]["effect"], "read")
                self.assertEqual(receipt["provider_calls"][0]["failure_category"], expected_category)
                self.assertIs(result["blocked_by"]["retryable"], True)
                if label == "credential_recovery":
                    service = TargetDiscoveryService(DiscoveryClient())
                    with patch.object(tasks, "TargetDiscoveryService", return_value=service):
                        resumed = tasks.dl_task_resume(
                            result["task_id"],
                            project_root=tmp,
                            expected_state="BLOCKED",
                            run_until="plan_ready",
                        )
                    self.assertIn("TASK_DISCOVERY_RETRY_SUCCEEDED", resumed["performed"])
                    self.assertIsNone(resumed.get("blocked_by"))

    def test_public_start_resolves_unambiguous_project_manifest_target(self) -> None:
        from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
        from tests.unit.test_target_discovery import DiscoveryClient

        target_shapes = (
            ("top_level", {"workbook_id": "book_demo", "dashboard_ids": ["dash_demo"]}),
            (
                "nested_target",
                {"target": {"workbook_id": "book_demo", "dashboard_ids": ["dash_demo"]}},
            ),
        )
        for label, target_shape in target_shapes:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                manifest = {
                    "project_name": "synthetic_project",
                    "workflows": [{"name": "delivery", "may_execute_command": False}],
                    **target_shape,
                }
                Path(tmp, ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
                client = DiscoveryClient()
                service = TargetDiscoveryService(client)
                with patch.object(tasks, "TargetDiscoveryService", return_value=service):
                    started = tasks.dl_task_start(
                        "Update the project dashboard while preserving its layout",
                        project_root=tmp,
                        run_until="plan_ready",
                    )

                contract = ProjectJournal(tmp, started["task_id"]).load_contract()
                self.assertEqual(contract["target"]["workbook_id"], "book_demo")
                self.assertEqual(contract["target"]["dashboard_id"], "dash_demo")
                self.assertEqual(
                    client.calls[0],
                    ("getDashboard", {"dashboardId": "dash_demo", "branch": "saved"}),
                )
                self.assertNotEqual(started.get("blocked_by", {}).get("code"), "BLOCKED_DISCOVERY")

    def test_explicit_working_project_path_outranks_context_project_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "reference project"
            target = root / "target project"
            for path in (reference, target):
                path.mkdir()
                (path / ".datalens-mcp.json").write_text("{}", encoding="utf-8")
            request = (
                f"'{reference}' - это дашборд для контекста. "
                f"Работать мы будем в проекте - '{target}'."
            )

            self.assertEqual(tasks._request_project_root(request, tmp), str(target.resolve()))

    def test_public_resume_recovers_interrupted_or_incomplete_discovery(self) -> None:
        from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
        from tests.unit.test_target_discovery import DiscoveryClient

        class SimulatedInterruption(BaseException):
            pass

        for label, persist_baseline_blocker in (
            ("interrupted_resolved", False),
            ("persisted_baseline_blocker", True),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                with (
                    patch.object(
                        tasks.TargetDiscoveryService,
                        "discover",
                        side_effect=SimulatedInterruption,
                    ),
                    self.assertRaises(SimulatedInterruption),
                ):
                    tasks.dl_task_start(
                        "Update the current dashboard while preserving its layout",
                        project_root=tmp,
                        context={"workbook_id": "book_demo", "dashboard_id": "dash_demo"},
                        run_until="plan_ready",
                    )

                task_id = next(
                    path.name
                    for path in (Path(tmp) / ".datalens-mcp" / "tasks").iterdir()
                    if path.is_dir() and not path.name.startswith(".")
                )
                journal = ProjectJournal(tmp, task_id)
                contract = journal.load_contract()
                if persist_baseline_blocker:
                    tasks._advance(journal, contract, boundary="plan_ready")
                    state, _ = journal.replay()
                    self.assertEqual(state.current_state, "BLOCKED")

                service = TargetDiscoveryService(DiscoveryClient())
                with patch.object(tasks, "TargetDiscoveryService", return_value=service):
                    resumed = tasks.dl_task_resume(
                        task_id,
                        project_root=tmp,
                        run_until="plan_ready",
                    )

                self.assertIn("TASK_DISCOVERY_RETRY_SUCCEEDED", resumed["performed"])
                self.assertNotEqual(resumed.get("risk"), "live target discovery is unavailable")

    def test_destructive_resume_requires_persisted_execution_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            safe_plan = {"ok": True, "status": "planned", "actions": [{"method": "deleteDashboard"}]}
            contract = create_task_contract(
                raw_request="Synthetic destructive workflow guard",
                mode="update",
                route="wizard_native",
                workspace=WorkspaceContract(project_root=tmp),
                delivery=DeliveryContract(save=True, publish=False, destructive=True),
            ).to_dict()
            journal = ProjectJournal(tmp, contract["task_id"])
            journal.initialize(contract)
            with self.assertRaisesRegex(JournalIdentityError, "execution authorization is missing"):
                tasks._advance(journal, contract, boundary="plan_ready")

    def test_compiler_question_is_persisted_as_terminal_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            started = tasks.dl_task_start("delete chart:synthetic_chart_18", project_root=tmp)
            resumed = tasks.dl_task_resume(started["task_id"], project_root=tmp)

            self.assertEqual(started["state"], "BLOCKED")
            self.assertEqual(started["next_action"], "")
            self.assertEqual(resumed["state"], "BLOCKED")
            self.assertEqual(resumed["task_revision"], started["task_revision"])

    def test_public_resume_accepts_idempotent_versioned_user_amendment_and_rejects_old_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal, contract, old_plan_hash = self._amendable_journal(tmp)
            status = tasks.dl_task_status(journal.task_id, project_root=tmp)
            turn = {
                "source_event_id": "user-event-42",
                "request": "Use JavaScript Editor and replace created orders with paid orders.",
                "relationship_to_previous": "correct_wrong_result",
                "context": {
                    "browser_policy": "forbidden",
                    "semantic_changes": [{
                        "target_id": "dash_1",
                        "anchor": {"kind": "json_pointer", "pointer": "/metric"},
                        "value": "paid_orders",
                    }],
                },
            }
            first = tasks.dl_task_resume(
                journal.task_id,
                project_root=tmp,
                expected_state=status["state"],
                expected_hash=status["state_etag"],
                expected_contract_revision=1,
                user_turn=turn,
                run_until="plan_ready",
            )
            self.assertEqual(first["task_id"], contract["task_id"])
            self.assertEqual(first["contract_revision"], 2)
            self.assertEqual(first["route"], "editor_advanced")
            self.assertEqual(first["amendment"]["status"], "accepted")
            amended = journal.load_contract()
            semantic_acceptance = [
                item for item in amended["acceptance"] if item.get("kind") == "semantic_change"
            ]
            self.assertEqual(len(semantic_acceptance), 1)
            self.assertEqual(json.loads(semantic_acceptance[0]["statement"])["value"], "paid_orders")
            self.assertEqual(semantic_acceptance[0]["source"], "current_user_correction")
            self.assertEqual(amended["browser_policy"]["mode"], "forbidden")
            self.assertEqual(amended["browser_policy"]["applicability"], "not_applicable")
            self.assertTrue(amended["browser_policy"]["read_only"])
            self.assertFalse(amended["browser_policy"]["mutation_allowed"])
            self.assertFalse(amended["browser_policy"]["calls_before_earliest_stage_allowed"])
            self.assertIn("data_diagnostics", first["amendment"]["semantic_delta"])
            self.assertIn("data_profile", first["amendment"]["invalidated_artifacts"])
            expanded_target = tasks._amendment_current_live_target(
                amended["target"],
                [{"target_id": "chart_2", "value": "paid_orders"}],
            )
            self.assertEqual(expanded_target["object_ids"], ["dash_1", "chart_2"])
            self.assertTrue(
                {"public_plan", "plan"} & set(first["amendment"]["invalidated_artifacts"])
            )
            duplicate = tasks.dl_task_resume(
                journal.task_id,
                project_root=tmp,
                expected_contract_revision=1,
                user_turn=turn,
                run_until="blocked",
            )
            self.assertEqual(duplicate["contract_revision"], 2)
            self.assertEqual(duplicate["amendment"]["status"], "duplicate")
            with self.assertRaisesRegex(ValueError, "resumable delivery state"):
                tasks.dl_execute(journal.task_id, old_plan_hash, project_root=tmp)
            chain = json.loads(journal.contract_revisions_path.read_text(encoding="utf-8"))
            self.assertEqual([item["revision"] for item in chain["revisions"]], [1, 2])

    def test_public_amendment_preserves_typed_verification_continuity(self) -> None:
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        with tempfile.TemporaryDirectory() as tmp:
            contract = compile_task_contract(
                "Я уже опубликовал dashboard: synthetic_dashboard_followup — проверь.",
                project_root=tmp,
            )["contract"]
            journal = ProjectJournal(tmp, contract["task_id"])
            journal.initialize_task(
                contract,
                build_identity=BuildIdentityResolver().resolve(),
                target_binding=resolve_contract_target_binding(contract),
                compile_receipt={"status": "compiled"},
                execution_grant=resolve_execution_authorization(contract),
            )
            status = tasks.dl_task_status(journal.task_id, project_root=tmp)

            amendment = tasks._amend_task(
                journal,
                user_turn={
                    "source_event_id": "verification-continue-1",
                    "request": "Продолжай проверку.",
                    "relationship_to_previous": "continue",
                },
                expected_contract_revision=1,
                expected_state=status["state"],
                expected_hash=status["state_etag"],
            )
            amended = journal.load_contract()

            self.assertEqual(amendment["status"], "accepted")
            self.assertEqual(amended["operation_kind"], "verify_existing_effect")
            self.assertEqual(amended["effect"], contract["effect"])
            self.assertEqual(amended["verification"], contract["verification"])
            self.assertEqual(amended["delivery"], contract["delivery"])
            self.assertEqual(amended["mode"], "review")

    def test_post_save_amendment_preserves_saved_receipt_and_invalidates_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal, _, _ = self._amendable_journal(tmp, saved=True)
            status = tasks.dl_task_status(journal.task_id, project_root=tmp)
            graph = build_target_graph(
                root_ids=["dash_1"],
                nodes=[{
                    "object_id": "dash_1",
                    "object_type": "dashboard",
                    "technology": "wizard_native",
                    "saved_revision": "saved-r2",
                    "payload_hash": "a" * 64,
                }],
                edges=[],
                provider_calls=[{"method": "getDashboard", "status": "success"}],
            )
            target_binding = create_live_target_binding(
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                object_ids=["dash_1"],
                object_types=["dashboard"],
                saved_revision="saved-r2",
                published_revision="published-r1",
                payload_hash="a" * 64,
                layout_hash="b" * 64,
                tabs_hash="c" * 64,
                technology="wizard_native",
                target_graph_hash=graph["graph_hash"],
            )
            discovered = {
                "status": "success",
                "observed_at": "2026-08-29T00:00:00Z",
                "provider_calls": [{"method": "getDashboard", "status": "success"}],
                "technology": "wizard_native",
                "tab_count": 1,
                "dataset_count": 0,
                "field_count": 0,
                "target_binding": target_binding,
                "target_graph": graph,
                "baselines": {"dashboard-dash_1-saved": {"entry": {"entryId": "dash_1", "revId": "saved-r2"}}},
            }
            with patch.object(tasks.TargetDiscoveryService, "discover", return_value=discovered) as fresh_discovery:
                result = tasks.dl_task_resume(
                    journal.task_id,
                    project_root=tmp,
                    expected_state=status["state"],
                    expected_hash=status["state_etag"],
                    expected_contract_revision=1,
                    user_turn={
                        "source_event_id": "post-save-1",
                        "request": "Keep the same dashboard, but remove the header only.",
                        "relationship_to_previous": "restrict_scope",
                        "context": {"scope": {"allowed_semantic_slots": ["header"]}},
                    },
                    run_until="plan_ready",
                )
            self.assertIn("publish_plan", result["amendment"]["invalidated_artifacts"])
            self.assertIn("target_binding", result["amendment"]["invalidated_artifacts"])
            self.assertIn("saved_readback_receipt", result["amendment"]["preserved_artifacts"])
            self.assertTrue(journal.saved_readback_receipt_path.is_file())
            self.assertEqual(
                json.loads(journal.target_binding_path.read_text(encoding="utf-8"))["saved_revision"],
                "saved-r2",
            )
            fresh_discovery.assert_called_once()

    def test_confirmation_is_inherited_only_for_unchanged_material_scope(self) -> None:
        base = {
            "operation_kind": "mutate",
            "route": "editor_advanced",
            "target": {"object_ids": ["chart_1"]},
            "scope": {"allowed_semantic_slots": ["legend"]},
            "delivery": {"save": True, "publish": True, "destructive": False},
        }
        unchanged = json.loads(json.dumps(base))
        changed_scope = json.loads(json.dumps(base))
        changed_scope["scope"]["allowed_semantic_slots"].append("layout")

        self.assertTrue(tasks._can_inherit_confirmation(base, unchanged, "SAVED_READBACK"))
        self.assertFalse(tasks._can_inherit_confirmation(base, unchanged, "VALIDATED"))
        self.assertFalse(tasks._can_inherit_confirmation(base, changed_scope, "SAVED_READBACK"))


if __name__ == "__main__":
    unittest.main()
