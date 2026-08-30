from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from datalens_dev_mcp.editor.reference_runtime import (
    STANDARD_DASHBOARD_RUNTIME_SHA256,
    validate_standard_dashboard_renderer,
)
from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract
from datalens_dev_mcp.editor.title_contract import normalize_title_contract
from datalens_dev_mcp.mcp.tools.pipeline import dl_generate_editor_bundle
from datalens_dev_mcp.pipeline.browser_qa import (
    BROWSER_QA_ASSERTIONS,
    BROWSER_QA_RESULT_SCHEMA_ID,
    build_browser_qa_plan,
    build_qa_attestation,
    delivery_status_from_qa_attestation,
    validate_qa_attestation_binding,
)
from datalens_dev_mcp.pipeline.dashboard_composition import (
    DashboardCompositionError,
    build_dashboard_composition,
    validate_dashboard_composition,
)
from datalens_dev_mcp.pipeline.final_payload_attestation import (
    build_final_payload_attestation,
    validate_payload_against_attestation,
    write_final_payload_attestation,
)
from datalens_dev_mcp.pipeline.safe_apply import (
    _qa_attestation_issues,
    create_safe_apply_plan,
    validate_safe_apply_plan_exhaustive,
)
from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload
from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "standard_dashboard"


class StandardDashboardContractTests(unittest.TestCase):
    def test_role_owned_title_modes_are_mutually_exclusive(self):
        embedded = normalize_title_contract(
            route="editor_advanced",
            family="line_chart",
            display_title="Synthetic trend",
            hint="Synthetic hint",
        )
        kpi = normalize_title_contract(
            route="editor_advanced",
            family="kpi_value_delta",
            display_title="Synthetic KPI",
        )
        native = normalize_title_contract(
            route="wizard_native",
            family="line_chart",
            display_title="Native trend",
        )
        self.assertEqual(embedded["mode"], "embedded_title")
        self.assertTrue(embedded["native_metadata"]["hideTitle"])
        self.assertEqual(kpi["mode"], "content_label")
        self.assertEqual(native["mode"], "native_title")
        self.assertFalse(native["native_metadata"]["hideTitle"])

    def test_dashboard_payload_rejects_title_mode_visibility_mismatch(self):
        payload = {
            "data": {
                "tabs": [
                    {
                        "id": "main",
                        "items": [
                            {
                                "id": "trend_item",
                                "type": "widget",
                                "data": {
                                    "chartId": "trend_chart",
                                    "title": "Synthetic trend",
                                    "titleMode": "embedded_title",
                                    "hideTitle": False,
                                },
                            }
                        ],
                        "layout": [{"i": "trend_item", "x": 0, "y": 0, "w": 36, "h": 14}],
                    }
                ]
            }
        }
        result = validate_dashboard_payload(payload)
        self.assertFalse(result.ok)
        self.assertIn("title_mode_native_visibility_mismatch", {item.rule for item in result.issues})

    def test_positive_dashboard_shape_fixtures_compile(self):
        fixture_names = [
            "six_tab_dashboard.json",
            "two_tab_internal_dashboard.json",
            "one_tab_external_dashboard.json",
            "mixed_routes_dashboard.json",
        ]
        for fixture_name in fixture_names:
            with self.subTest(fixture=fixture_name):
                requested = json.loads((FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8"))
                widget_ids = [
                    item if isinstance(item, str) else item["widget_id"]
                    for tab in requested["tabs"]
                    for row in tab["rows"]
                    for item in row["items"]
                ]
                components = [_component(widget_id) for widget_id in widget_ids]
                composition = build_dashboard_composition(components, requested=requested)
                self.assertFalse(validate_dashboard_composition(composition, components=components))
                self.assertEqual(len(composition["tabs"]), len(requested["tabs"]))

    def test_selector_group_exact_rows_and_clear_semantics(self):
        contract = normalize_selector_contract(
            family="selector_group",
            title="",
            selector_contract={
                "controls": [
                    {
                        "family": "date_range_selector",
                        "label": "Period",
                        "param": "period",
                        "option_source": "none",
                        "default_values": [],
                        "reset_behavior": "empty",
                        "row": 1,
                    },
                    {
                        "family": "multi_select_dropdown",
                        "label": "Segment",
                        "param": "segment",
                        "option_source": "static",
                        "options": ["A", "B"],
                        "default_values": [],
                        "reset_behavior": "empty",
                        "row": 1,
                    },
                    {
                        "family": "single_select_dropdown",
                        "label": "Status",
                        "param": "status",
                        "option_source": "static",
                        "options": ["Open", "Closed"],
                        "default_values": [],
                        "reset_behavior": "empty",
                        "row": 2,
                    },
                ]
            },
        )
        self.assertTrue(contract["ok"], contract["issues"])
        self.assertEqual(contract["dashboard_grid_height_units"], 3)
        self.assertEqual([row["width_total_percent"] for row in contract["rows"]], [94, 94])
        multiselect = next(item for item in contract["controls"] if item["multiple"])
        self.assertTrue(multiselect["emptyMeansAll"])
        self.assertFalse(multiselect["restoreDefaultAfterClear"])

    def test_selector_label_above_and_clear_repopulation_fail_closed(self):
        contract = normalize_selector_contract(
            family="selector_group",
            title="",
            selector_contract={
                "controls": [
                    {
                        "family": "multi_select_dropdown",
                        "label": "Segment",
                        "labelPlacement": "top",
                        "param": "segment",
                        "option_source": "static",
                        "options": ["A", "B"],
                        "default_values": ["A"],
                        "reset_behavior": "empty",
                    }
                ]
            },
        )
        issue_codes = {item["code"] for item in contract["issues"]}
        self.assertFalse(contract["ok"])
        self.assertIn("selector_group_unknown_selector_contract_fields", issue_codes)
        self.assertIn("selector_group_empty_reset_with_defaults", issue_codes)

        component = {
            **_component("selector_main"),
            "family": "selector_group",
            "route": "editor_js_control",
            "title_mode": "tab_only",
            "display_title": "",
            "selector_contract": {
                **contract,
                "ok": True,
                "issues": [],
                "controls": [
                    {
                        **contract["controls"][0],
                        "labelPlacement": "top",
                        "restoreDefaultAfterClear": True,
                    }
                ],
            },
        }
        with self.assertRaises(DashboardCompositionError) as caught:
            build_dashboard_composition([component])
        self.assertIn("selector labels must be left-aligned", str(caught.exception))
        self.assertIn("Clear must not repopulate", str(caught.exception))

    def test_negative_layout_fixtures_fail_closed(self):
        components = [_component("kpi_a"), _component("kpi_b"), _component("kpi_c")]
        valid = build_dashboard_composition(components)
        cases: list[tuple[str, dict]] = []

        height = deepcopy(valid)
        height["tabs"][0]["rows"][0]["items"][1]["h"] = 7
        cases.append(("height", height))

        gap = deepcopy(valid)
        gap["tabs"][0]["rows"][0]["gap_after"] = 1
        cases.append(("gap", gap))

        technical = deepcopy(valid)
        technical["tabs"][0]["rows"][0]["items"][0]["display_title"] = "widget_001"
        cases.append(("technical_title", technical))

        for name, composition in cases:
            with self.subTest(case=name):
                issues = validate_dashboard_composition(composition, components=components)
                self.assertTrue(issues)

        four = [_component(f"kpi_{suffix}") for suffix in ("a", "b", "c", "d")]
        four_requested = {
            "tabs": [
                {
                    "id": "main",
                    "title": "Main",
                    "rows": [{"id": "dense", "role": "kpi", "items": [item["widget_id"] for item in four]}],
                }
            ],
        }
        with self.assertRaises(DashboardCompositionError):
            build_dashboard_composition(four, requested=four_requested)

    def test_table_readability_failures_are_blocking(self):
        component = _component("detail_table")
        requested = {
            "tabs": [
                {
                    "id": "main",
                    "title": "Main",
                    "rows": [
                        {
                            "id": "detail",
                            "role": "table",
                            "items": [
                                {
                                    "widget_id": "detail_table",
                                    "table_contract": {
                                        "sticky_column_kind": "constant",
                                        "header_groups": [{"title": ""}],
                                        "columns": [{"label_clipped": True, "display_label": ""}],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        with self.assertRaises(DashboardCompositionError) as caught:
            build_dashboard_composition([component], requested=requested)
        self.assertIn("constant column", str(caught.exception))
        self.assertIn("empty grouped header", str(caught.exception))
        self.assertIn("clipped label", str(caught.exception))

    def test_exact_runtime_is_hash_locked_and_materialized_tabs_are_attested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_brief(root)
            bundle = dl_generate_editor_bundle(
                project_root=tmp,
                widget_id="trend_widget",
                route="editor_advanced",
                dataset_alias="synthetic_source",
                columns=["bucket", "value"],
            )
            self.assertEqual(
                bundle["template_provenance"]["canonical_runtime_sha256"],
                STANDARD_DASHBOARD_RUNTIME_SHA256,
            )
            self.assertTrue(validate_standard_dashboard_renderer(bundle)["ok"])
            visual_quality = validate_visual_quality_contract(bundle["renderer_visual_spec"])
            self.assertTrue(
                visual_quality.ok,
                [finding.to_dict() for finding in visual_quality.findings],
            )
            attestation = write_final_payload_attestation(root)
            self.assertTrue(attestation["ok"], attestation["issues"])

            prepare_path = root / "dashboard" / "trend_widget" / "prepare.js"
            prepare_path.write_text(prepare_path.read_text(encoding="utf-8") + "\n// drift\n", encoding="utf-8")
            drift = build_final_payload_attestation(root)
            self.assertFalse(drift["ok"])
            self.assertTrue(any("materialized tab prepare.js differs" in issue for issue in drift["issues"]))

    def test_wizard_route_and_composition_drift_are_attested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_brief(root, route="wizard_native")
            plan = dl_generate_editor_bundle(
                project_root=tmp,
                widget_id="trend_widget",
                route="wizard_native",
                dataset_alias="synthetic_source",
                columns=["bucket", "value"],
            )
            self.assertEqual(plan["route"], "wizard_native")
            self.assertTrue(write_final_payload_attestation(root)["ok"])

            plan_path = root / "artifacts" / "trend_widget.wizard_payload_plan.json"
            persisted = json.loads(plan_path.read_text(encoding="utf-8"))
            persisted["route"] = "editor_advanced"
            plan_path.write_text(json.dumps(persisted), encoding="utf-8")
            route_drift = build_final_payload_attestation(root)
            self.assertFalse(route_drift["ok"])
            self.assertTrue(any("Wizard-first route was replaced" in issue for issue in route_drift["issues"]))

            persisted["route"] = "wizard_native"
            plan_path.write_text(json.dumps(persisted), encoding="utf-8")
            composition_path = root / "artifacts" / "dashboard_composition.json"
            composition = json.loads(composition_path.read_text(encoding="utf-8"))
            composition["tabs"][0]["rows"][0]["gap_after"] = 1
            composition_path.write_text(json.dumps(composition), encoding="utf-8")
            layout_drift = build_final_payload_attestation(root)
            self.assertFalse(layout_drift["ok"])
            self.assertTrue(any("dashboard_composition" in issue for issue in layout_drift["issues"]))

    def test_route_and_payload_drift_are_absent_from_attestation(self):
        attestation = {
            "ok": True,
            "components": [
                {
                    "widget_id": "trend_widget",
                    "binding_neutral_payload_sha256": "0" * 64,
                }
            ],
            "dashboard_payload": {"binding_neutral_sha256": "1" * 64},
        }
        issues = validate_payload_against_attestation(
            {"entry": {"data": {"prepare": "rewritten"}}},
            attestation,
            widget_id="trend_widget",
        )
        self.assertTrue(issues)

    def test_dashboard_mount_chart_binding_is_attested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_brief(root)
            generated = dl_generate_editor_bundle(
                project_root=tmp,
                widget_id="trend_widget",
                route="editor_advanced",
                dataset_alias="synthetic_source",
                columns=["bucket", "value"],
            )
            self.assertEqual(generated["generation_status"], "ready")
            attestation = write_final_payload_attestation(root)
            self.assertTrue(attestation["ok"], attestation["issues"])
            payload = json.loads(
                (
                    root
                    / "artifacts"
                    / "dashboard_payloads"
                    / "generated.dashboard.payload.json"
                ).read_text(encoding="utf-8")
            )
            widget = payload["entry"]["data"]["tabs"][0]["items"][0]
            self.assertEqual(widget["type"], "widget")
            self.assertIn("tabs", widget["data"])
            self.assertEqual(widget["data"]["tabs"][0]["chartId"], "trend_widget")

            drift = deepcopy(payload)
            drift["entry"]["data"]["tabs"][0]["items"][0]["data"]["tabs"][0]["chartId"] = "other_chart"
            issues = validate_payload_against_attestation(
                drift,
                attestation,
                is_dashboard=True,
            )
            self.assertTrue(any("mount to chart bindings" in issue for issue in issues))

            title_drift = deepcopy(payload)
            title_drift["entry"]["meta"]["title"] = "Wrong dashboard title"
            self.assertTrue(
                validate_payload_against_attestation(
                    title_drift,
                    attestation,
                    is_dashboard=True,
                )
            )

    def test_safe_apply_normalizes_legacy_alias_and_requires_current_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                user_request_text="create dashboard",
                actions=[
                    {
                        "action": "create_editor_chart",
                        "action_type": "create",
                        "authoring_profile_id": "standard_dashboard",
                        "method": "createEditorChart",
                        "payload": {
                            "entry": {
                                "workbookId": "wb",
                                "name": "js - chart synthetic",
                                "type": "d3",
                                "data": {},
                            },
                            "mode": "save",
                        },
                        "fresh_read_method": "getWorkbookEntries",
                        "fresh_read_payload": {"workbookId": "wb"},
                        "readback_method": "getEditorChart",
                    }
                ],
            )
            result = validate_safe_apply_plan_exhaustive(plan)
        self.assertFalse(any("standard_dashboard is forbidden" in issue for issue in result["issues"]))
        self.assertTrue(
            any("final_payload_attestation binding is required" in issue for issue in result["issues"]),
            result["issues"],
        )

    def test_browser_qa_is_revision_and_payload_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            proof_path = Path(tmp) / "browser-proof.json"
            proof_path.write_text("{}\n", encoding="utf-8")
            composition = {"sha256": "c" * 64, "tabs": []}
            plan = build_browser_qa_plan(
                dashboard_id="dashboard_1",
                tab_ids=["main"],
                expected_object_ids=["trend_widget"],
                saved_revision="saved_7",
                published_revision="saved_7",
                dashboard_composition=composition,
                final_payload_attestation_sha256="a" * 64,
                payload_set_sha256="b" * 64,
            )
            results = []
            assertions = {item["id"]: True for item in BROWSER_QA_ASSERTIONS}
            for width in (1200,):
                for position in ("top", "bottom"):
                    results.append(
                        {
                            "schema_id": BROWSER_QA_RESULT_SCHEMA_ID,
                            "viewport": {"width": width, "height": 900},
                            "tab_id": "main",
                            "scroll_position": position,
                            "passed": True,
                            "assertions": assertions,
                            "observations": {},
                        }
                    )
            attestation = build_qa_attestation(
                plan=plan,
                viewport_results=results,
                dashboard_id="dashboard_1",
                saved_revision="saved_7",
                published_revision="saved_7",
                artifact_paths=[str(proof_path)],
            )
            self.assertTrue(attestation["ok"], attestation["issues"])
            self.assertEqual(attestation["viewport_widths"], [1200])
            self.assertEqual(attestation["final_payload_attestation_sha256"], "a" * 64)
            expected = {
                "dashboard_id": "dashboard_1",
                "saved_revision": "saved_7",
                "published_revision": "saved_7",
                "final_payload_attestation_sha256": "a" * 64,
                "payload_set_sha256": "b" * 64,
                "dashboard_composition_sha256": "c" * 64,
            }
            self.assertFalse(validate_qa_attestation_binding(attestation, **expected))
            self.assertEqual(
                delivery_status_from_qa_attestation(attestation, **expected),
                "done",
            )
            final_attestation = {
                "attestation_sha256": "a" * 64,
                "payload_set_sha256": "b" * 64,
                "dashboard_composition": {"sha256": "c" * 64},
            }
            action = {
                "object_id": "dashboard_1",
                "revision_guard": {"expected_saved_rev_id": "saved_7"},
                "qa_attestation": attestation,
            }
            self.assertFalse(
                _qa_attestation_issues(
                    action=action,
                    payload={"dashboardId": "dashboard_1"},
                    index=0,
                    attestation=final_attestation,
                    project_root=Path(tmp),
                )
            )
            tampered = deepcopy(attestation)
            tampered["published_revision"] = "other_revision"
            self.assertEqual(
                delivery_status_from_qa_attestation(tampered, **expected),
                "blocked",
            )


def _component(widget_id: str) -> dict:
    if widget_id.startswith("kpi_"):
        family = "kpi_value_sparkline"
        route = "editor_advanced"
        title_mode = "content_label"
    elif widget_id.startswith("wizard_kpi"):
        family = "kpi_value_only"
        route = "wizard_native"
        title_mode = "native_title"
    elif "table" in widget_id:
        family = "table_node"
        route = "wizard_native"
        title_mode = "native_title"
    elif widget_id == "method_note":
        family = "md_methodology_block"
        route = "editor_markdown"
        title_mode = "tab_only"
    elif widget_id.startswith("wizard_"):
        family = "line_chart"
        route = "wizard_native"
        title_mode = "native_title"
    else:
        family = "horizontal_bar" if "segment" in widget_id else "line_chart"
        route = "editor_advanced"
        title_mode = "embedded_title"
    return {
        "widget_id": widget_id,
        "ok": True,
        "route": route,
        "family": family,
        "display_title": widget_id.replace("_", " ").title(),
        "title_mode": title_mode,
        "title_contract_sha256": "a" * 64,
    }


def _write_brief(root: Path, *, route: str = "editor_advanced") -> None:
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "dashboard_brief.json").write_text(
        json.dumps(
            {
                "dashboard_name": "Synthetic Dashboard",
                "dashboard_type": "overview",
                "audience": ["analyst"],
                "requirements": [{"text": "Show a synthetic trend."}],
                "data_contract": {
                    "contract_id": "DATA-001",
                    "dataset_alias": "synthetic_source",
                    "fields": [{"name": "bucket"}, {"name": "value"}],
                },
                "chart_decisions": [
                    {
                        "widget_id": "trend_widget",
                        "title": "Synthetic trend",
                        "family": "line_chart",
                        "route": route,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
