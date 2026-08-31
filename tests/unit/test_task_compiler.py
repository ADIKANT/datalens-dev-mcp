from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "task_contracts" / "cases.json"


class TaskCompilerTests(unittest.TestCase):
    def test_request_reference_url_is_separate_from_target_url(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        result = compile_task_contract(
            "Update target dashboard: https://datalens.ru/?dashboardId=synthetic_target_123\n"
            "Use reference style: https://datalens.ru/?dashboardId=synthetic_reference_456"
        )

        self.assertEqual(result["contract"]["target"]["dashboard_id"], "synthetic_target_123")
        self.assertEqual(
            result["contract"]["reference"]["locator"],
            "https://datalens.ru/?dashboardId=synthetic_reference_456",
        )
        self.assertEqual(result["contract"]["reference"]["kind"], "live_object")

    def test_compiled_source_trace_carries_target_url_to_typed_discovery(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        result = compile_task_contract("Update https://datalens.example/dash_demo and save it")

        self.assertEqual(result["status"], "needs_discovery")
        self.assertEqual(result["source_trace"]["target_url"], "https://datalens.example/dash_demo")

    def test_generic_followup_content_noun_preserves_existing_route(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        result = compile_task_contract(
            "update chart:synthetic_chart_route",
            current_live={"chart_id": "synthetic_chart_route", "technology": "editor_advanced"},
            corrections=["Уточни только строки таблицы и подпись"],
        )

        self.assertEqual(result["contract"]["route"], "editor_advanced")

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

    def test_update_with_save_and_publish_compiles_as_existing_object_update(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        result = compile_task_contract(
            "Update the existing controlled dashboard description, save and publish it without browser.",
            current_live={
                "workbook_id": "synthetic_workbook",
                "dashboard_id": "synthetic_dashboard",
                "object_ids": ["synthetic_dashboard"],
                "object_types": ["dashboard"],
                "technology": "dashboard",
                "saved_revision": "synthetic_saved_revision",
                "layout": {"tabs": ["synthetic_tab"]},
                "tabs": ["synthetic_tab"],
            },
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["contract"]["mode"], "update")
        self.assertTrue(result["contract"]["delivery"]["save"])
        self.assertTrue(result["contract"]["delivery"]["publish"])
        self.assertEqual(result["contract"]["browser_policy"]["mode"], "forbidden")

    def test_verify_existing_effect_is_read_only_and_has_nonempty_acceptance(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        cases = (
            (
                "Я уже опубликовал dashboard: synthetic_dashboard_verify — проверь.",
                "published",
                {"current_object", "saved_or_published_revision", "relations"},
            ),
            (
                "Посмотри, применились ли правки в dashboard: synthetic_dashboard_verify.",
                "changed",
                {"current_object", "saved_or_published_revision", "relations", "runtime_assertions_if_applicable"},
            ),
            (
                "Проверь, что данные появились в chart: synthetic_chart_verify.",
                "data_appeared",
                {"current_object", "saved_or_published_revision", "relations", "data_assertions"},
            ),
        )
        for prompt, effect, required_reads in cases:
            with self.subTest(prompt=prompt):
                result = compile_task_contract(prompt)
                contract = result["contract"]
                self.assertEqual(contract["mode"], "review")
                self.assertEqual(contract["operation_kind"], "verify_existing_effect")
                self.assertEqual(contract["effect"]["kind"], effect)
                self.assertEqual(contract["delivery"], {"save": False, "publish": False, "destructive": False})
                self.assertTrue(contract["acceptance"])
                self.assertEqual(set(contract["verification"]["required_live_reads"]), required_reads)
                self.assertFalse(contract["verification"]["remediation_enabled"])
                self.assertEqual(set(result["discovery_required"]), required_reads)

    def test_plain_review_and_direct_publish_remain_adjacent_non_verification_cases(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        review = compile_task_contract("Проверь текущий dashboard: synthetic_dashboard_review")
        publish = compile_task_contract("Опубликуй dashboard: synthetic_dashboard_publish")

        self.assertEqual(review["contract"]["operation_kind"], "inspect")
        self.assertEqual(publish["contract"]["operation_kind"], "mutate")
        self.assertTrue(publish["contract"]["delivery"]["publish"])

    def test_russian_redo_request_preserves_mutation_and_negation_semantics(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        cases = (
            (
                "все отлично, теперь дашборд нравится, но остается проблемы, что kpi блоки ты сделал "
                "одним общим чартом, а я просил так не делать. каждая kpi карточка должна быть отдельным "
                "объектом. поэтому переделай, расположение оставь таким же, оставь через header выделение, "
                "что это executive kpi и так далее",
                "mutate",
                "update",
                {"save": True, "publish": True, "destructive": False},
            ),
            (
                "Не переделывай KPI-блоки, только проверь текущую структуру.",
                "inspect",
                "review",
                {"save": False, "publish": False, "destructive": False},
            ),
        )
        for request, operation_kind, mode, delivery in cases:
            with self.subTest(request=request):
                contract = compile_task_contract(
                    request,
                    current_live={
                        "workbook_id": "synthetic_workbook",
                        "dashboard_id": "synthetic_dashboard",
                        "technology": "dashboard",
                    },
                )["contract"]

                self.assertEqual(contract["operation_kind"], operation_kind)
                self.assertEqual(contract["mode"], mode)
                self.assertEqual(contract["delivery"], delivery)

    def test_generic_followup_preserves_typed_mutation_mode_and_delivery(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        base = compile_task_contract(
            "Update dashboard:synthetic_dashboard_followup and publish it",
            current_live={
                "dashboard_id": "synthetic_dashboard_followup",
                "technology": "wizard_native",
            },
        )["contract"]
        amended = compile_task_contract(
            "Continue the current typed task contract.",
            current_live=base["target"],
            current_task_journal=base,
            corrections=["Продолжай."],
        )["contract"]

        self.assertEqual(amended["operation_kind"], "mutate")
        self.assertEqual(amended["mode"], "update")
        self.assertEqual(amended["delivery"], base["delivery"])

        save_only = compile_task_contract(
            "Update dashboard:synthetic_dashboard_followup, save only and do not publish.",
            current_live={
                "dashboard_id": "synthetic_dashboard_followup",
                "technology": "wizard_native",
            },
        )["contract"]
        save_only_amended = compile_task_contract(
            "Continue the current typed task contract.",
            current_live=save_only["target"],
            current_task_journal=save_only,
            corrections=["Продолжай."],
        )["contract"]
        self.assertEqual(save_only_amended["delivery"], save_only["delivery"])

    def test_runtime_error_browser_request_keeps_api_diagnostics_before_final_visual_qa(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        cases = (
            (
                "открой браузер внутренний, там ошибка: Code: 184. DB::Exception: "
                "Aggregate function min(payment_at) is found in WHERE (ILLEGAL_AGGREGATION)",
                "illegal_aggregation",
            ),
            (
                "verify in the browser after fixing Data fetching error "
                '{"code":"ERR.DS_API.DB.SOURCE_CONNECT_ERROR"}',
                "data fetching error",
            ),
        )
        for correction, expected_reason in cases:
            with self.subTest(correction=correction):
                base = compile_task_contract(
                    "Update dashboard:synthetic_dashboard_diagnostics and publish it",
                    current_live={
                        "dashboard_id": "synthetic_dashboard_diagnostics",
                        "technology": "wizard_native",
                    },
                )["contract"]
                contract = compile_task_contract(
                    "Continue the current typed task contract.",
                    current_live=base["target"],
                    current_task_journal=base,
                    corrections=[correction],
                )["contract"]

                self.assertEqual(contract["browser_policy"]["mode"], "required")
                self.assertEqual(contract["browser_policy"]["purpose"], "final_visual_acceptance")
                self.assertEqual(
                    contract["browser_policy"]["earliest_stage"],
                    "published_readback_and_api_diagnostics_complete",
                )
                self.assertFalse(contract["browser_policy"]["calls_before_earliest_stage_allowed"])
                self.assertTrue(contract["browser_policy"]["read_only"])
                self.assertFalse(contract["browser_policy"]["mutation_allowed"])
                self.assertTrue(contract["data_diagnostics"]["required"])
                self.assertTrue(contract["data_diagnostics"]["validate_dataset"])
                self.assertTrue(contract["data_diagnostics"]["diagnostic_probe"])
                self.assertIn("runtime_data_error", contract["data_diagnostics"]["reason_classes"])
                self.assertIn(expected_reason, json.dumps(contract["acceptance"]).lower())

    def test_followup_preserves_exact_reference_without_spurious_discovery(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        for correction in ("стоп, не надо в браузер лезть", "Use the API and MCP first"):
            with self.subTest(correction=correction):
                base = compile_task_contract(
                    "Update chart:synthetic_chart_reference exactly like the supplied example",
                    current_live={
                        "chart_id": "synthetic_chart_reference",
                        "technology": "editor_advanced",
                    },
                    reference={
                        "kind": "portfolio_object",
                        "locator": "portfolio/synthetic-reference",
                        "required_exact_style": True,
                    },
                )["contract"]
                contract = compile_task_contract(
                    "Continue the current typed task contract.",
                    current_live=base["target"],
                    current_task_journal=base,
                    corrections=[correction],
                    reference=base["reference"],
                )["contract"]

                self.assertEqual(contract["reference"], base["reference"])

    def test_explicit_followup_can_transition_typed_operation_without_inheriting_delivery(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        base = compile_task_contract(
            "Update dashboard:synthetic_dashboard_followup and publish it",
            current_live={
                "dashboard_id": "synthetic_dashboard_followup",
                "technology": "wizard_native",
            },
        )["contract"]
        review = compile_task_contract(
            "Continue the current typed task contract.",
            current_live=base["target"],
            current_task_journal=base,
            corrections=["Теперь только проверь текущий dashboard."],
        )["contract"]

        self.assertEqual(review["operation_kind"], "inspect")
        self.assertEqual(review["mode"], "review")
        self.assertEqual(
            review["delivery"],
            {"save": False, "publish": False, "destructive": False},
        )

    def test_generic_followup_preserves_typed_verification_effect(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        base = compile_task_contract(
            "Я уже опубликовал dashboard: synthetic_dashboard_followup — проверь."
        )["contract"]
        amended = compile_task_contract(
            "Continue the current typed task contract.",
            current_live=base["target"],
            current_task_journal=base,
            corrections=["Продолжай проверку."],
        )["contract"]

        self.assertEqual(amended["operation_kind"], "verify_existing_effect")
        self.assertEqual(amended["mode"], "review")
        self.assertEqual(amended["effect"]["kind"], "published")
        self.assertEqual(
            amended["delivery"],
            {"save": False, "publish": False, "destructive": False},
        )

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

    def test_negated_ql_does_not_become_direct_ql_request(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        for request in (
            "Update dashboard synthetic_dashboard with no QL fallback",
            "Update dashboard synthetic_dashboard without QL",
            "Обнови дашборд synthetic_dashboard без QL",
        ):
            compiled = compile_task_contract(request)
            self.assertNotEqual(compiled["contract"]["route"], "ql_explicit", request)

    def test_real_journey_owner_transitions_preserve_target_route_and_delivery(self):
        from datalens_dev_mcp.pipeline.task_compiler import compile_task_contract

        vehicle = compile_task_contract(
            "работать будем над таблицей https://datalens.ru/editor/mqc6snad6u2o6; "
            "добавь selector nexus ci diff flg"
        )["contract"]
        self.assertEqual(vehicle["mode"], "update")
        self.assertEqual(vehicle["route"], "editor_advanced")
        self.assertEqual(vehicle["target"]["object_ids"], ["mqc6snad6u2o6"])

        base = compile_task_contract(
            "Update chart:synthetic_editor_chart and publish it",
            current_live={"chart_id": "synthetic_editor_chart", "technology": "editor_advanced"},
        )["contract"]
        correction = compile_task_contract(
            "Continue the current typed task contract.",
            current_live=base["target"],
            current_task_journal=base,
            corrections=[
                "оставь линии, но убери легенду; в tooltip покажи статус, число и долю; "
                "расположение не меняй"
            ],
        )["contract"]
        self.assertEqual(correction["operation_kind"], "mutate")
        self.assertEqual(correction["route"], "editor_advanced")
        self.assertEqual(correction["delivery"], base["delivery"])

        adopted = compile_task_contract(
            "Continue the current typed task contract.",
            current_live=base["target"],
            current_task_journal=base,
            corrections=[
                "перечитай еще раз дашборд, запомни расположение, "
                "я корректно переделал размещение в layout"
            ],
        )["contract"]
        self.assertEqual(adopted["operation_kind"], "verify_existing_effect")
        self.assertEqual(adopted["delivery"], {"save": False, "publish": False, "destructive": False})

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
