from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "task_contracts" / "cases.json"


class TaskCompilerTests(unittest.TestCase):
    def test_fixture_matrix_has_at_least_forty_cases(self):
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(payload["case_count"], 40)
        self.assertEqual(payload["case_count"], len(payload["cases"]))

    def test_fixture_matrix(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        for case in payload["cases"]:
            with self.subTest(case=case["name"]):
                result = compile_task_contract(case["request"], **case.get("kwargs", {}))
                self.assertTrue(result["ok"], result)
                self._assert_expected(result, case["expect"])

    def test_contract_is_byte_stable_and_hash_bound(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract
        from datalens_dev_mcp.pipeline.task_contract import task_contract_hash

        kwargs = {
            "current_live": {
                "technology": "editor_advanced",
                "layout": {"widgets": ["synthetic_widget"]},
                "tabs": ["sources.js"],
                "saved_revision": "synthetic_saved_rev",
            }
        }
        first = compile_task_contract("update chart:synthetic_chart_stable", **kwargs)
        second = compile_task_contract("update chart:synthetic_chart_stable", **kwargs)

        self.assertEqual(first["contract"], second["contract"])
        self.assertEqual(first["task_contract_hash"], task_contract_hash(first["contract"]))

    def test_compiled_contract_validates_against_public_schema(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        schema = json.loads((ROOT / "schemas" / "task-contract.schema.json").read_text(encoding="utf-8"))
        browser_schema = json.loads((ROOT / "schemas" / "browser-policy.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(browser_schema["$id"], Resource.from_contents(browser_schema))
        result = compile_task_contract("review dashboard:synthetic_dash_schema")

        Draft202012Validator(schema, registry=registry).validate(result["contract"])

    def test_correction_changes_contract_hash_and_becomes_hard_acceptance(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        base = compile_task_contract("review dashboard:synthetic_dash_hash")
        corrected = compile_task_contract(
            "review dashboard:synthetic_dash_hash",
            corrections=["do not change layout"],
        )

        self.assertNotEqual(base["task_contract_hash"], corrected["task_contract_hash"])
        self.assertIn("layout_change", corrected["contract"]["scope"]["forbidden_changes"])
        self.assertTrue(
            any(
                item["statement"] == "do not change layout" and item["hard"]
                for item in corrected["contract"]["acceptance"]
            )
        )

    def test_task_contract_dataclasses_are_frozen(self):
        from datalens_dev_mcp.pipeline.task_contract import WorkspaceContract

        workspace = WorkspaceContract(project_root="synthetic/project")
        with self.assertRaises(FrozenInstanceError):
            workspace.project_root = "changed"  # type: ignore[misc]

    def test_every_write_route_declares_and_validates_task_contract_hash(self):
        from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT, validate_write_route_context

        digest = "a" * 64
        for route, spec in ROUTE_CONTRACT.routes.items():
            with self.subTest(route=route):
                self.assertIn("task_contract_hash", spec.write_context_fields)
                self.assertEqual(validate_write_route_context(route, digest), ())
                self.assertTrue(validate_write_route_context(route, "bad"))

    def test_delivery_and_approval_adapters_preserve_task_contract_hash(self):
        from datalens_dev_mcp.pipeline.approval_intent import SafeGates, resolve_approval_intent
        from datalens_dev_mcp.pipeline.delivery_intent import DeliveryContext, resolve_delivery_intent
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        digest = "b" * 64
        request = "update chart:synthetic_chart_adapter"
        delivery = resolve_delivery_intent(
            request,
            DeliveryContext(
                target_known=True,
                writes_enabled=True,
                save_enabled=True,
                publish_enabled=True,
                task_contract_hash=digest,
            ),
        )
        approval = resolve_approval_intent(
            request,
            target_lock=create_target_lock(request, target_workbook_id="synthetic_workbook_adapter"),
            safe_gates=SafeGates(),
            task_contract_hash=digest,
        )

        self.assertEqual(delivery.task_contract_hash, digest)
        self.assertEqual(approval.task_contract_hash, digest)

    def test_context_reference_rejects_mutated_contract(self):
        from datalens_dev_mcp.pipeline.context_contracts import validate_task_contract_reference
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        compiled = compile_task_contract("review dashboard:synthetic_dash_context")
        contract = compiled["contract"]
        self.assertEqual(validate_task_contract_reference(contract), compiled["task_contract_hash"])
        mutated = json.loads(json.dumps(contract))
        mutated["mode"] = "update"
        with self.assertRaisesRegex(ValueError, "contract_hash"):
            validate_task_contract_reference(mutated)

    @staticmethod
    def _assert_expected(result: dict, expected: dict) -> None:
        contract = result["contract"]
        if "mode" in expected:
            assert contract["mode"] == expected["mode"]
        if "route" in expected:
            assert contract["route"] == expected["route"]
        if "save" in expected:
            assert contract["delivery"]["save"] is expected["save"]
        if "publish" in expected:
            assert contract["delivery"]["publish"] is expected["publish"]
        if "destructive" in expected:
            assert contract["delivery"]["destructive"] is expected["destructive"]
        if "browser" in expected:
            assert contract["browser_policy"]["mode"] == expected["browser"]
        if "browser_source" in expected:
            assert contract["browser_policy"]["source"] == expected["browser_source"]
        if "status" in expected:
            assert result["status"] == expected["status"]
        if "question" in expected:
            actual = result["question"]["category"] if result["question"] else None
            assert actual == expected["question"]
        if "target" in expected:
            assert expected["target"] in contract["target"]["object_ids"]
        if "target_absent" in expected:
            assert expected["target_absent"] not in contract["target"]["object_ids"]
        if "ignored_historical" in expected:
            assert expected["ignored_historical"] in result["source_trace"]["ignored_historical_target_fields"]
        if "discovery" in expected:
            assert expected["discovery"] in result["discovery_required"]
        if "forbidden_change" in expected:
            assert expected["forbidden_change"] in contract["scope"]["forbidden_changes"]
        if "acceptance" in expected:
            assert any(item["statement"] == expected["acceptance"] for item in contract["acceptance"])
        if "reference_exact" in expected:
            assert contract["reference"]["required_exact_style"] is expected["reference_exact"]
        if "reference_kind" in expected:
            assert contract["reference"]["kind"] == expected["reference_kind"]
        if "saved_revision" in expected:
            assert contract["target"]["saved_revision"] == expected["saved_revision"]


if __name__ == "__main__":
    unittest.main()
