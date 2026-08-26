from __future__ import annotations

import unittest

from datalens_dev_mcp.pipeline.safe_apply import (
    preflight_safe_apply_semantic_patches,
    preflight_semantic_patch_runtime,
)
from datalens_dev_mcp.pipeline.semantic_patch import build_semantic_patch_plan


def payload(object_id: str, value: str) -> dict:
    return {
        "entryId": object_id,
        "tabs": {
            "sources.js": (
                "module.exports={rows:{sql_query:`"
                f"/* datalens-slot:source_sql:sql:start */{value}"
                "/* datalens-slot:source_sql:end */`}};"
            )
        },
    }


def patch_plan(object_id: str, base: dict, revision: int) -> dict:
    return build_semantic_patch_plan(
        task_id="task_batch",
        targets=[
            {
                "object_id": object_id,
                "object_type": "editor_chart",
                "saved_revision": revision,
                "payload": base,
                "sections": [
                    {
                        "tab": "sources.js",
                        "anchor": {"kind": "semantic_slot", "slot_id": "source_sql"},
                        "operation": "replace",
                        "value": "SELECT current_value FROM synthetic_table",
                    }
                ],
            }
        ],
    )


class SemanticPatchSafeApplyIntegrationTests(unittest.TestCase):
    def test_multi_object_preflight_failure_means_zero_writes(self) -> None:
        first = payload("chart_a", "SELECT old_a FROM synthetic_table")
        second = payload("chart_b", "SELECT old_b FROM synthetic_table")
        first_plan = patch_plan("chart_a", first, 1)
        second_plan = patch_plan("chart_b", second, 2)
        first_after = first_plan["targets"][0]["expected_after_hash"]
        second_after = second_plan["targets"][0]["expected_after_hash"]
        safe_plan = {
            "actions": [
                {
                    "payload": _materialized(first_plan, first),
                    "semantic_patch_plan": first_plan,
                    "semantic_expected_payloads": {"chart_a": _materialized(first_plan, first)},
                },
                {
                    "payload": _materialized(second_plan, second),
                    "semantic_patch_plan": second_plan,
                    "semantic_expected_payloads": {"chart_b": _materialized(second_plan, second)},
                },
            ]
        }
        stale_second = payload("chart_b", "SELECT conflicting_value FROM synthetic_table")
        result = preflight_safe_apply_semantic_patches(
            safe_plan,
            fresh_targets={
                "chart_a": {"object_type": "editor_chart", "saved_revision": 1, "payload": first},
                "chart_b": {"object_type": "editor_chart", "saved_revision": 3, "payload": stale_second},
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["write_count"], 0)
        self.assertEqual(first_plan["targets"][0]["expected_after_hash"], first_after)
        self.assertEqual(second_plan["targets"][0]["expected_after_hash"], second_after)

    def test_runtime_reads_every_target_and_dispatches_zero_writes_on_failure(self) -> None:
        first = payload("chart_a", "SELECT old_a FROM synthetic_table")
        second = payload("chart_b", "SELECT old_b FROM synthetic_table")
        first_plan = patch_plan("chart_a", first, 1)
        second_plan = patch_plan("chart_b", second, 2)
        safe_plan = {
            "actions": [
                {
                    "payload": _materialized(first_plan, first),
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_a"},
                    "semantic_patch_plan": first_plan,
                },
                {
                    "payload": _materialized(second_plan, second),
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_b"},
                    "semantic_patch_plan": second_plan,
                },
            ]
        }
        client = _ReadOnlyBatchClient(
            {
                "chart_a": {**first, "revId": 1},
                "chart_b": {**payload("chart_b", "SELECT conflict FROM synthetic_table"), "revId": 3},
            }
        )
        result = preflight_semantic_patch_runtime(safe_plan, client=client)
        self.assertFalse(result["ok"])
        self.assertEqual(client.write_calls, [])
        self.assertEqual(client.read_calls, ["chart_a", "chart_b"])

    def test_exact_replay_is_classified_as_safe_apply_noop(self) -> None:
        base = payload("chart_a", "SELECT old_a FROM synthetic_table")
        plan = patch_plan("chart_a", base, 1)
        after = _materialized(plan, base)
        safe_plan = {
            "actions": [
                {
                    "payload": after,
                    "semantic_patch_plan": plan,
                    "semantic_expected_payloads": {"chart_a": after},
                }
            ]
        }
        result = preflight_safe_apply_semantic_patches(
            safe_plan,
            fresh_targets={"chart_a": {"object_type": "editor_chart", "saved_revision": 2, "payload": after}},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["noop_action_indices"], [0])
        self.assertEqual(result["write_count"], 0)


def _materialized(plan: dict, base: dict) -> dict:
    from datalens_dev_mcp.pipeline.patch_preflight import preflight_semantic_patch_batch

    object_id = plan["targets"][0]["object_id"]
    revision = plan["targets"][0]["saved_revision"]
    result = preflight_semantic_patch_batch(
        plan,
        fresh_targets={object_id: {"object_type": "editor_chart", "saved_revision": revision, "payload": base}},
    )
    return result["materialized_payloads"][object_id]


class _ReadOnlyBatchClient:
    def __init__(self, values: dict[str, dict]) -> None:
        self.values = values
        self.read_calls: list[str] = []
        self.write_calls: list[str] = []

    def rpc_exclusive_read(self, method: str, request: dict) -> dict:
        object_id = str(request.get("chartId") or "")
        self.read_calls.append(object_id)
        return self.values[object_id]

    def rpc(self, method: str, request: dict) -> dict:
        self.write_calls.append(method)
        raise AssertionError("preflight must not dispatch writes")


if __name__ == "__main__":
    unittest.main()
