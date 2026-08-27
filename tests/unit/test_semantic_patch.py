from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.editor.protected_regions import build_protected_regions
from datalens_dev_mcp.pipeline.noop_guard import attempt_signature, record_noop_attempt
from datalens_dev_mcp.pipeline.patch_preflight import (
    preflight_semantic_patch_batch,
    verify_semantic_patch_readback,
)
from datalens_dev_mcp.pipeline.patch_recovery import recover_semantic_patch_plan
from datalens_dev_mcp.pipeline.semantic_patch import (
    build_semantic_patch_plan,
    canonical_hash,
    semantic_patch_plan_hash,
)


def editor_payload() -> dict:
    return {
        "entryId": "synthetic_chart",
        "unknownTop": {"preserve": True},
        "tabs": {
            "sources.js": (
                "module.exports={rows:{sql_query:`"
                "/* datalens-slot:source_sql:sql:start */SELECT old_value FROM synthetic_table"
                "/* datalens-slot:source_sql:end */`}};"
            ),
            "prepare.js": (
                "/* datalens-protected:runtime:start */"
                "function safeRatio(a,b){return b?a/b:null;}"
                "/* datalens-protected:runtime:end */\n"
                "const label='/* datalens-slot:series_label:text:start */Old label"
                "/* datalens-slot:series_label:end */';\nmodule.exports={label};"
            ),
        },
    }


def build_plan(*, sections: list[dict] | None = None, payload: dict | None = None) -> dict:
    saved = payload or editor_payload()
    return build_semantic_patch_plan(
        task_id="task_synthetic",
        targets=[
            {
                "object_id": "synthetic_chart",
                "object_type": "editor_chart",
                "saved_revision": 17,
                "payload": saved,
                "protected_regions": build_protected_regions(saved["tabs"]),
                "sections": sections
                or [
                    {
                        "tab": "sources.js",
                        "anchor": {"kind": "semantic_slot", "slot_id": "source_sql"},
                        "operation": "replace",
                        "value": "SELECT new_value FROM synthetic_table",
                    }
                ],
            }
        ],
    )


def fresh(payload: dict, revision: int = 17) -> dict:
    return {"object_type": "editor_chart", "saved_revision": revision, "payload": payload}


class SemanticPatchTests(unittest.TestCase):
    def test_valid_source_sql_patch_preserves_unknown_fields(self) -> None:
        base = editor_payload()
        plan = build_plan(payload=base)
        result = preflight_semantic_patch_batch(plan, fresh_targets={"synthetic_chart": fresh(base)})
        self.assertTrue(result["ok"])
        patched = result["materialized_payloads"]["synthetic_chart"]
        self.assertIn("SELECT new_value", patched["tabs"]["sources.js"])
        self.assertEqual(patched["unknownTop"], {"preserve": True})
        self.assertEqual(patched["tabs"]["prepare.js"], base["tabs"]["prepare.js"])

    def test_valid_labels_only_patch(self) -> None:
        base = editor_payload()
        plan = build_plan(
            payload=base,
            sections=[
                {
                    "tab": "prepare.js",
                    "anchor": {"kind": "semantic_slot", "slot_id": "series_label"},
                    "operation": "replace",
                    "value": "Readable label",
                }
            ],
        )
        result = preflight_semantic_patch_batch(plan, fresh_targets={"synthetic_chart": fresh(base)})
        self.assertTrue(result["ok"])
        self.assertIn("Readable label", result["materialized_payloads"]["synthetic_chart"]["tabs"]["prepare.js"])

    def test_stale_tab_hash_is_rejected(self) -> None:
        base = editor_payload()
        plan = build_plan(payload=base)
        stale = copy.deepcopy(base)
        stale["tabs"]["sources.js"] += "\n// unrelated but stale"
        result = preflight_semantic_patch_batch(plan, fresh_targets={"synthetic_chart": fresh(stale, 18)})
        self.assertFalse(result["ok"])
        self.assertTrue(result["targets"][0]["recovery_required"])

    def test_duplicate_anchor_is_rejected(self) -> None:
        duplicate = editor_payload()
        duplicate["tabs"]["sources.js"] += duplicate["tabs"]["sources.js"]
        plan = build_plan()
        target = plan["targets"][0]
        target["saved_hash"] = canonical_hash(duplicate)
        target["sections"][0]["tab_hash"] = canonical_hash(duplicate["tabs"]["sources.js"])
        plan["plan_hash"] = semantic_patch_plan_hash(plan)
        result = preflight_semantic_patch_batch(plan, fresh_targets={"synthetic_chart": fresh(duplicate)})
        self.assertFalse(result["ok"])
        self.assertIn("exactly once", " ".join(result["issues"]))

    def test_protected_region_change_is_rejected(self) -> None:
        base = editor_payload()
        base["tabs"]["prepare.js"] = base["tabs"]["prepare.js"].replace(
            "function safeRatio(a,b){return b?a/b:null;}",
            "function safeRatio(a,b){return /* datalens-slot:protected_value:text:start */b?a/b:null"
            "/* datalens-slot:protected_value:end */;}",
        )
        plan = build_plan(
            payload=base,
            sections=[
                {
                    "tab": "prepare.js",
                    "anchor": {"kind": "semantic_slot", "slot_id": "protected_value"},
                    "operation": "replace",
                    "value": "0",
                }
            ],
        )
        result = preflight_semantic_patch_batch(plan, fresh_targets={"synthetic_chart": fresh(base)})
        self.assertFalse(result["ok"])
        self.assertIn("protected region", " ".join(result["issues"]))

    def test_unrelated_change_can_be_recovered_to_new_immutable_plan(self) -> None:
        base = editor_payload()
        plan = build_plan(payload=base)
        fresh_payload = copy.deepcopy(base)
        fresh_payload["unknownTop"]["newField"] = "preserved"
        recovery = recover_semantic_patch_plan(
            plan,
            base_targets={"synthetic_chart": fresh(base)},
            fresh_targets={"synthetic_chart": fresh(fresh_payload, 18)},
        )
        self.assertTrue(recovery["ok"])
        self.assertNotEqual(recovery["old_plan_hash"], recovery["new_plan_hash"])
        self.assertEqual(plan["plan_hash"], recovery["old_plan_hash"])
        preflight = preflight_semantic_patch_batch(
            recovery["plan"],
            fresh_targets={"synthetic_chart": fresh(fresh_payload, 18)},
        )
        self.assertTrue(preflight["ok"])
        self.assertEqual(
            preflight["materialized_payloads"]["synthetic_chart"]["unknownTop"]["newField"],
            "preserved",
        )

    def test_targeted_change_blocks_recovery(self) -> None:
        base = editor_payload()
        plan = build_plan(payload=base)
        changed = copy.deepcopy(base)
        changed["tabs"]["sources.js"] = changed["tabs"]["sources.js"].replace("old_value", "other_value")
        recovery = recover_semantic_patch_plan(
            plan,
            base_targets={"synthetic_chart": fresh(base)},
            fresh_targets={"synthetic_chart": fresh(changed, 18)},
        )
        self.assertFalse(recovery["ok"])
        self.assertEqual(recovery["conflicts"][0]["reason"], "targeted_anchor_changed")

    def test_dashboard_semantic_widget_anchor_uses_identity(self) -> None:
        dashboard = {"widgets": [{"id": "widget_a", "title": "Old"}, {"id": "widget_b", "title": "Keep"}]}
        plan = build_semantic_patch_plan(
            task_id="task_dashboard",
            targets=[
                {
                    "object_id": "dashboard_synthetic",
                    "object_type": "dashboard",
                    "saved_revision": 3,
                    "payload": dashboard,
                    "sections": [
                        {
                            "tab": "",
                            "anchor": {"kind": "semantic_widget", "object_id": "widget_a", "pointer": "/title"},
                            "operation": "replace",
                            "value": "Readable",
                        }
                    ],
                }
            ],
        )
        result = preflight_semantic_patch_batch(
            plan,
            fresh_targets={"dashboard_synthetic": {"object_type": "dashboard", "saved_revision": 3, "payload": dashboard}},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["materialized_payloads"]["dashboard_synthetic"]["widgets"][0]["title"], "Readable")

    def test_dashboard_raw_array_position_anchor_is_rejected(self) -> None:
        dashboard = {"widgets": [{"id": "widget_a", "title": "Old"}]}
        plan = build_semantic_patch_plan(
            task_id="task_dashboard",
            targets=[
                {
                    "object_id": "dashboard_synthetic",
                    "object_type": "dashboard",
                    "saved_revision": 3,
                    "payload": dashboard,
                    "sections": [
                        {
                            "tab": "",
                            "anchor": {"kind": "json_pointer", "pointer": "/widgets/0/title"},
                            "operation": "replace",
                            "value": "Unsafe",
                        }
                    ],
                }
            ],
        )
        result = preflight_semantic_patch_batch(
            plan,
            fresh_targets={"dashboard_synthetic": {"object_type": "dashboard", "saved_revision": 3, "payload": dashboard}},
        )
        self.assertFalse(result["ok"])
        self.assertIn("raw array positions", " ".join(result["issues"]))

    def test_dashboard_tab_id_guards_global_identity_pointer(self) -> None:
        dashboard = {
            "entryId": "dashboard_synthetic",
            "data": {"tabs": [{"id": "W7", "title": "Main"}], "supportDescription": "Old"},
            "unknownTop": {"preserve": True},
        }
        plan = build_semantic_patch_plan(
            task_id="task_dashboard",
            targets=[
                {
                    "object_id": "dashboard_synthetic",
                    "object_type": "dashboard",
                    "saved_revision": 3,
                    "payload": dashboard,
                    "sections": [
                        {
                            "tab": "W7",
                            "anchor": {"kind": "json_pointer", "pointer": "/data/supportDescription"},
                            "operation": "replace",
                            "value": "Controlled marker",
                        }
                    ],
                }
            ],
        )
        result = preflight_semantic_patch_batch(
            plan,
            fresh_targets={
                "dashboard_synthetic": {
                    "object_type": "dashboard",
                    "saved_revision": 3,
                    "payload": dashboard,
                }
            },
        )
        self.assertTrue(result["ok"])
        patched = result["materialized_payloads"]["dashboard_synthetic"]
        self.assertEqual(patched["data"]["supportDescription"], "Controlled marker")
        self.assertEqual(patched["unknownTop"], {"preserve": True})

    def test_noop_loop_guard_stops_identical_attempt(self) -> None:
        signature = attempt_signature(
            target_revision=17,
            plan_hash="a" * 64,
            failure_class="readback_mismatch",
            resulting_hash="b" * 64,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "attempts.json"
            self.assertTrue(record_noop_attempt(path, signature)["ok"])
            repeated = record_noop_attempt(path, signature)
            self.assertFalse(repeated["ok"])
            self.assertEqual(repeated["status"], "NO_PROGRESS")
            self.assertFalse(repeated["repeat_write_allowed"])

    def test_replay_exact_plan_is_idempotent_and_readback_hash_matches(self) -> None:
        base = editor_payload()
        plan = build_plan(payload=base)
        first = preflight_semantic_patch_batch(plan, fresh_targets={"synthetic_chart": fresh(base)})
        patched = first["materialized_payloads"]["synthetic_chart"]
        replay = preflight_semantic_patch_batch(plan, fresh_targets={"synthetic_chart": fresh(patched, 18)})
        self.assertTrue(replay["ok"])
        self.assertEqual(replay["targets"][0]["status"], "already_applied")
        proof = verify_semantic_patch_readback(plan, readback_targets={"synthetic_chart": fresh(patched, 18)})
        self.assertTrue(proof["ok"])


if __name__ == "__main__":
    unittest.main()
