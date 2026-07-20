import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


class WizardSafeApplyPipelineTests(unittest.TestCase):
    def _wizard_plan(self, *, include_dataset_readback: bool = True) -> dict:
        from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan

        config = {
            "route": "wizard_native",
            "visualization_id": "column",
            "widget_id": "sales_column",
            "location": {"workbookId": "workbook_1", "name": "sales_column"},
            "dataset": "dataset_1",
            "field_bindings": {"x": "category_guid", "y": "value_guid"},
            "options": {"labels": [{"guid": "value_guid"}]},
        }
        if include_dataset_readback:
            config["dataset_readbacks"] = [
                {
                    "datasetId": "dataset_1",
                    "result_schema": [
                        {"guid": "category_guid", "type": "string", "title": "Category"},
                        {"guid": "value_guid", "type": "float", "title": "Value"},
                    ],
                    "unrelated": {"discard": True},
                }
            ]
        plan = build_wizard_payload_plan(config)
        plan["generation_status"] = "ready"
        return plan

    def _write_wizard_plan(self, root: Path, *, include_dataset_readback: bool = True) -> dict:
        plan = self._wizard_plan(include_dataset_readback=include_dataset_readback)
        (root / "artifacts").mkdir(parents=True, exist_ok=True)
        (root / "artifacts" / "sales_column.wizard_payload_plan.json").write_text(
            json.dumps(plan),
            encoding="utf-8",
        )
        return plan

    def _build_safe_create_plan(self, root: Path) -> dict:
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_payload_plan,
            dl_create_safe_apply_plan,
        )

        self._write_wizard_plan(root)
        payload_plan = dl_build_payload_plan(
            str(root),
            workbook_id="workbook_1",
            delivery_intent_text="implement the chart",
        )
        self.assertTrue(payload_plan["payloads"], payload_plan)
        return dl_create_safe_apply_plan(
            str(root),
            entries_payload={"entries": []},
            delivery_intent_text="implement the chart",
            target_workbook_id="workbook_1",
        )

    def test_standard_wizard_create_carries_validated_evidence_and_reuse_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._build_safe_create_plan(Path(tmp))

        self.assertTrue(plan["ok"], plan.get("blocked_reasons"))
        self.assertEqual(plan["status"], "safe_apply_plan_ready")
        action = plan["actions"][0]
        self.assertEqual(action["action"], "create_wizard_chart")
        self.assertEqual(action["object_type"], "wizard_chart")
        self.assertTrue(action["enforce_wizard_role_types"])
        self.assertEqual(
            action["dataset_readbacks"][0]["result_schema"],
            [
                {"guid": "category_guid", "data_type": "string"},
                {"guid": "value_guid", "data_type": "float"},
            ],
        )
        self.assertEqual(action["object_reuse_decision"]["decision"], "create")
        self.assertTrue(action["object_reuse_decision"]["create_allowed"])
        self.assertTrue(action["object_reuse_decision"]["baseline_proof_artifact"])

    def test_standard_wizard_create_fails_closed_without_dataset_readback(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_payload_plan,
            dl_create_safe_apply_plan,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_wizard_plan(root, include_dataset_readback=False)
            payload_plan = dl_build_payload_plan(str(root), workbook_id="workbook_1")
            safe_plan = dl_create_safe_apply_plan(
                str(root),
                entries_payload={"entries": []},
            )

        self.assertFalse(payload_plan["payloads"])
        self.assertEqual(
            payload_plan["blocking_issues"][0]["status"],
            "blocked_missing_dataset_readback_evidence",
        )
        self.assertFalse(safe_plan["ok"])
        self.assertEqual(safe_plan["status"], "payload_plan_blocked")

    def test_standard_create_rejects_missing_or_incomplete_entries_evidence(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_payload_plan,
            dl_create_safe_apply_plan,
        )

        for entries_payload in ({}, {"entries": [], "nextPageToken": "next"}):
            with self.subTest(entries_payload=entries_payload), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_wizard_plan(root)
                dl_build_payload_plan(str(root), workbook_id="workbook_1")
                safe_plan = dl_create_safe_apply_plan(
                    str(root),
                    entries_payload=entries_payload,
                )

            self.assertFalse(safe_plan["ok"])
            self.assertEqual(safe_plan["status"], "blocked_entries_reconciliation")
            self.assertEqual(
                safe_plan["error"]["category"],
                "invalid_entries_reconciliation_evidence",
            )

    def test_standard_wizard_update_preserves_compact_type_evidence(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

        payload = {
            "entryId": "chart_1",
            "revId": "rev_1",
            "mode": "save",
            "template": "datalens",
            "data": {
                "visualization": {
                    "id": "column",
                    "placeholders": [
                        {"id": "x", "items": [{"guid": "category_guid"}]},
                        {"id": "y", "items": [{"guid": "value_guid"}]},
                    ],
                },
                "datasetsIds": ["dataset_1"],
                "datasetsPartialFields": [
                    {"guid": "category_guid"},
                    {"guid": "value_guid"},
                ],
                "labels": [{"guid": "value_guid"}],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            plan = dl_create_safe_apply_plan(
                tmp,
                existing_update_actions=[
                    {
                        "object_type": "wizard_chart",
                        "object_id": "chart_1",
                        "base_revision": "rev_1",
                        "payload": payload,
                        "changed_sections": ["data.visualization"],
                        "dataset_readbacks": [
                            {
                                "datasetId": "dataset_1",
                                "result_schema": [
                                    {"guid": "category_guid", "type": "string", "title": "Category"},
                                    {"guid": "value_guid", "type": "float", "title": "Value"},
                                    {"guid": "unused_guid", "type": "integer"},
                                ],
                            }
                        ],
                        "enforce_wizard_role_types": True,
                    }
                ],
                delivery_intent_text="update the chart",
                target_chart_id="chart_1",
            )

        self.assertTrue(plan["ok"], plan.get("blocked_reasons"))
        action = plan["actions"][0]
        self.assertTrue(action["enforce_wizard_role_types"])
        self.assertEqual(
            action["dataset_readbacks"][0]["result_schema"],
            [
                {"guid": "category_guid", "data_type": "string"},
                {"guid": "value_guid", "data_type": "float"},
            ],
        )

    def test_create_execution_reads_exact_created_object_and_verifies_content(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class ExactCreateClient:
            def __init__(self):
                self.calls = []
                self.created_payload = {}

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                if method == "getWorkbookEntries":
                    return {"entries": []}
                if method == "createWizardChart":
                    self.created_payload = deepcopy(payload)
                    return {"entryId": "chart_created", "revId": "rev_created"}
                if method == "getWizardChart":
                    if payload.get("chartId") != "chart_created":
                        raise AssertionError("readback must address the identity returned by create")
                    return {
                        "entry": {
                            "entryId": "chart_created",
                            "revId": "rev_created",
                            "name": self.created_payload["name"],
                            "template": self.created_payload["template"],
                            "data": deepcopy(self.created_payload["data"]),
                            "createdAt": "2026-07-20T00:00:00Z",
                            "updatedAt": "2026-07-20T00:00:01Z",
                            "createdBy": "service",
                            "updatedBy": "service",
                        }
                    }
                raise AssertionError(method)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._build_safe_create_plan(root)
            client = ExactCreateClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertTrue(result["executed"], result)
        self.assertEqual(
            [method for method, _payload in client.calls],
            ["getWorkbookEntries", "createWizardChart", "getWizardChart"],
        )
        self.assertEqual(client.calls[-1][1]["chartId"], "chart_created")
        verification = result["actions"][0]["readback_verification"]
        self.assertTrue(verification["verified"])
        self.assertTrue(verification["content_equivalent"])
        self.assertEqual(verification["actual_object_id"], "chart_created")

    def test_create_execution_fails_when_write_response_has_no_identity(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class MissingIdentityClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                if method == "getWorkbookEntries":
                    return {"entries": []}
                if method == "createWizardChart":
                    return {"status": "saved"}
                raise AssertionError("readback must not run without a created object identity")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._build_safe_create_plan(root)
            client = MissingIdentityClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertFalse(result["executed"])
        self.assertEqual(result["actions"][0]["error"]["category"], "missing_created_identity")
        self.assertEqual(
            [method for method, _payload in client.calls],
            ["getWorkbookEntries", "createWizardChart"],
        )

    def test_create_execution_reconciles_against_fresh_entries_before_write(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class ExistingObjectClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                if method == "getWorkbookEntries":
                    return {
                        "entries": [
                            {
                                "entryId": "chart_existing",
                                "scope": "widget",
                                "type": "d3_wizard_node",
                                "key": "2248817075424333788/Sales Column",
                                "displayKey": "2248817075424333788/Sales Column",
                            }
                        ]
                    }
                raise AssertionError("create must not run when a matching object now exists")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._build_safe_create_plan(root)
            client = ExistingObjectClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertFalse(result["executed"])
        self.assertEqual(result["actions"][0]["error"]["category"], "create_target_now_exists")
        self.assertFalse(result["actions"][0]["write_attempted"])
        self.assertEqual(
            [method for method, _payload in client.calls],
            ["getWorkbookEntries"],
        )

    def test_create_execution_rejects_empty_fresh_entries_envelope(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class EmptyFreshClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                if method == "getWorkbookEntries":
                    return {}
                raise AssertionError("create must not run without an authoritative entries envelope")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._build_safe_create_plan(root)
            client = EmptyFreshClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertFalse(result["executed"])
        self.assertEqual(
            result["actions"][0]["error"]["category"],
            "fresh_create_pagination_incomplete_page",
        )
        self.assertFalse(result["actions"][0]["write_attempted"])

    def test_create_execution_paginates_inventory_and_keeps_exact_readback_proof(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import (
            execute_safe_apply,
            load_safe_apply_stage_value,
        )

        class PaginatedCreateClient:
            def __init__(self):
                self.calls = []
                self.created_payload = {}

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                if method == "getWorkbookEntries":
                    page = int(payload.get("page") or 1)
                    if page == 1:
                        return {
                            "entries": [
                                {
                                    "entryId": "dataset_z",
                                    "scope": "dataset",
                                    "displayKey": "Z Dataset",
                                }
                            ],
                            "nextPageToken": "cursor_2",
                        }
                    if page == 2:
                        return {
                            "entries": [
                                {
                                    "entryId": "dataset_a",
                                    "scope": "dataset",
                                    "displayKey": "A Dataset",
                                }
                            ]
                        }
                    raise AssertionError(f"unexpected page {page}")
                if method == "createWizardChart":
                    self.created_payload = deepcopy(payload)
                    return {"entryId": "chart_created", "revId": "rev_created"}
                if method == "getWizardChart":
                    return {
                        "entry": {
                            "entryId": "chart_created",
                            "revId": "rev_created",
                            "name": self.created_payload["name"],
                            "template": self.created_payload["template"],
                            "data": deepcopy(self.created_payload["data"]),
                        }
                    }
                raise AssertionError(method)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = self._build_safe_create_plan(root)
            client = PaginatedCreateClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )
            pre_write = load_safe_apply_stage_value(
                result["actions"][0],
                "pre_write",
                project_root=root,
            )

        self.assertTrue(result["executed"], result)
        self.assertEqual(
            [method for method, _payload in client.calls],
            [
                "getWorkbookEntries",
                "getWorkbookEntries",
                "createWizardChart",
                "getWizardChart",
            ],
        )
        self.assertEqual(client.calls[1][1]["page"], 2)
        self.assertNotIn("pageToken", client.calls[1][1])
        pagination = result["actions"][0]["fresh_read_pagination"]
        self.assertTrue(pagination["complete"])
        self.assertEqual(pagination["page_count"], 2)
        self.assertEqual(pagination["entry_count"], 2)
        self.assertEqual(
            pagination["target_lock_hash"],
            plan["actions"][0]["target_lock_hash"],
        )
        self.assertEqual(
            [entry["entryId"] for entry in pre_write["value"]["entries"]],
            ["dataset_a", "dataset_z"],
        )
        self.assertTrue(
            result["actions"][0]["readback_verification"]["verified"]
        )
        self.assertEqual(
            result["actions"][0]["readback_verification"]["actual_object_id"],
            "chart_created",
        )

    def test_create_inventory_pagination_blocks_cursor_cycle(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class CursorCycleClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                if method != "getWorkbookEntries":
                    raise AssertionError("write must not run after a cursor cycle")
                return {"entries": [], "nextPageToken": "repeated_cursor"}

        with tempfile.TemporaryDirectory() as tmp:
            plan = self._build_safe_create_plan(Path(tmp))
            client = CursorCycleClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertFalse(result["executed"])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            result["actions"][0]["error"]["category"],
            "fresh_create_pagination_cursor_cycle",
        )
        self.assertFalse(result["actions"][0]["fresh_read_pagination"]["complete"])

    def test_create_inventory_pagination_blocks_page_and_entry_caps(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class PageCapClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                page = int(payload.get("page") or 1)
                return {
                    "entries": [
                        {
                            "entryId": f"dataset_{page}",
                            "scope": "dataset",
                            "displayKey": f"Dataset {page}",
                        }
                    ],
                    "nextPageToken": f"cursor_{page + 1}",
                }

        class EntryCapClient:
            def rpc(self, method, payload):
                return {
                    "entries": [
                        {"entryId": "dataset_1", "scope": "dataset"},
                        {"entryId": "dataset_2", "scope": "dataset"},
                    ]
                }

        cases = [
            (
                "page",
                PageCapClient(),
                "SAFE_APPLY_CREATE_INVENTORY_MAX_PAGES",
                2,
                "fresh_create_pagination_page_cap_exceeded",
            ),
            (
                "entry",
                EntryCapClient(),
                "SAFE_APPLY_CREATE_INVENTORY_MAX_ENTRIES",
                1,
                "fresh_create_pagination_entry_cap_exceeded",
            ),
        ]
        for label, client, constant, limit, category in cases:
            with self.subTest(cap=label), tempfile.TemporaryDirectory() as tmp, patch(
                f"datalens_dev_mcp.pipeline.safe_apply.{constant}",
                limit,
            ):
                plan = self._build_safe_create_plan(Path(tmp))
                result = execute_safe_apply(
                    plan,
                    config=DataLensConfig(write_enabled=True),
                    client=client,
                )

            self.assertFalse(result["executed"])
            self.assertEqual(result["actions"][0]["error"]["category"], category)

    def test_create_inventory_pagination_blocks_conflicting_duplicate(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class ConflictingDuplicateClient:
            def rpc(self, method, payload):
                page = int(payload.get("page") or 1)
                return {
                    "entries": [
                        {
                            "entryId": "same_entry",
                            "scope": "dataset",
                            "displayKey": "First" if page == 1 else "Changed",
                        }
                    ],
                    **({"nextPageToken": "cursor_2"} if page == 1 else {}),
                }

        with tempfile.TemporaryDirectory() as tmp:
            plan = self._build_safe_create_plan(Path(tmp))
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=ConflictingDuplicateClient(),
            )

        self.assertFalse(result["executed"])
        self.assertEqual(
            result["actions"][0]["error"]["category"],
            "fresh_create_pagination_duplicate_conflict",
        )

    def test_create_inventory_second_page_existing_object_blocks_create(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class SecondPageReuseClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, deepcopy(payload)))
                if method != "getWorkbookEntries":
                    raise AssertionError("create must not run when page two has the target")
                page = int(payload.get("page") or 1)
                if page == 1:
                    return {"entries": [], "nextPageToken": "cursor_2"}
                return {
                    "entries": [
                        {
                            "entryId": "chart_existing",
                            "scope": "widget",
                            "type": "d3_wizard_node",
                            "displayKey": "2248817075424333788/Sales Column",
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as tmp:
            plan = self._build_safe_create_plan(Path(tmp))
            client = SecondPageReuseClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertFalse(result["executed"])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            result["actions"][0]["error"]["category"],
            "create_target_now_exists",
        )
        self.assertEqual(
            result["actions"][0]["error"]["existing_object_id"],
            "chart_existing",
        )

    def test_create_execution_rejects_wrong_object_content_or_revision(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class InvalidReadbackClient:
            def __init__(self, failure_mode):
                self.failure_mode = failure_mode
                self.created_payload = {}

            def rpc(self, method, payload):
                if method == "getWorkbookEntries":
                    return {"entries": []}
                if method == "createWizardChart":
                    self.created_payload = deepcopy(payload)
                    return {"entryId": "chart_created", "revId": "rev_created"}
                if method == "getWizardChart":
                    object_id = "chart_other" if self.failure_mode == "identity" else "chart_created"
                    revision = "rev_other" if self.failure_mode == "revision" else "rev_created"
                    data = deepcopy(self.created_payload["data"])
                    if self.failure_mode == "content":
                        data["visualization"]["id"] = "line"
                    return {
                        "entry": {
                            "entryId": object_id,
                            "revId": revision,
                            "name": self.created_payload["name"],
                            "template": self.created_payload["template"],
                            "data": data,
                        }
                    }
                raise AssertionError(method)

        expected_categories = {
            "identity": "created_object_missing_from_readback",
            "content": "readback_content_mismatch",
            "revision": "readback_write_revision_mismatch",
        }
        for failure_mode, expected_category in expected_categories.items():
            with self.subTest(failure_mode=failure_mode), tempfile.TemporaryDirectory() as tmp:
                plan = self._build_safe_create_plan(Path(tmp))
                result = execute_safe_apply(
                    plan,
                    config=DataLensConfig(write_enabled=True),
                    client=InvalidReadbackClient(failure_mode),
                )

            self.assertFalse(result["executed"])
            self.assertEqual(result["actions"][0]["error"]["category"], expected_category)

    def test_semantic_comparison_ignores_only_top_level_volatile_metadata(self):
        from datalens_dev_mcp.pipeline.safe_apply import _write_payload_matches_readback

        expected = {
            "entry": {
                "entryId": "chart_1",
                "updatedAt": "old",
                "updatedBy": "old_actor",
                "data": {"title": "Chart", "updatedAt": "business_value"},
            }
        }
        volatile_only = {
            "entry": {
                "entryId": "chart_1",
                "updatedAt": "new",
                "updatedBy": "new_actor",
                "data": {"title": "Chart", "updatedAt": "business_value"},
            }
        }
        nested_business_change = deepcopy(volatile_only)
        nested_business_change["entry"]["data"]["updatedAt"] = "changed_business_value"

        self.assertTrue(
            _write_payload_matches_readback(
                method="updateEditorChart",
                write_payload=expected,
                readback=volatile_only,
            )
        )
        self.assertFalse(
            _write_payload_matches_readback(
                method="updateEditorChart",
                write_payload=expected,
                readback=nested_business_change,
            )
        )


if __name__ == "__main__":
    unittest.main()
