from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest


class StandardDashboardAttestedFlowTests(unittest.TestCase):
    def test_validated_dashboard_publishes_only_the_qa_checked_saved_revision(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.api.request_compiler import project_method_request
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_generate_editor_bundle,
            dl_validate_project,
        )
        from datalens_dev_mcp.pipeline.browser_qa import (
            BROWSER_QA_ASSERTIONS,
            BROWSER_QA_RESULT_SCHEMA_ID,
            build_browser_qa_plan,
            build_qa_attestation,
            delivery_status_from_qa_attestation,
        )
        from datalens_dev_mcp.pipeline.safe_apply import (
            create_publish_safe_apply_plan,
            execute_safe_apply,
            validate_safe_apply_plan_exhaustive,
        )

        class DashboardClient:
            def __init__(self, entry: dict):
                self.entry = json.loads(json.dumps(entry))
                self.calls: list[tuple[str, dict]] = []

            def rpc(self, method: str, payload: dict) -> dict:
                self.calls.append((method, json.loads(json.dumps(payload))))
                if method == "getDashboard":
                    return {"entry": json.loads(json.dumps(self.entry))}
                if method == "updateDashboard":
                    self.entry = json.loads(json.dumps(payload["entry"]))
                    self.entry["savedId"] = "saved_snapshot"
                    return {"entry": json.loads(json.dumps(self.entry))}
                raise AssertionError(f"unexpected method {method}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / "artifacts"
            artifacts.mkdir(parents=True)
            (artifacts / "dashboard_brief.json").write_text(
                json.dumps(
                    {
                        "dashboard_name": "Synthetic attested dashboard",
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
                                "route": "editor_advanced",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            generated = dl_generate_editor_bundle(
                project_root=tmp,
                widget_id="trend_widget",
                route="editor_advanced",
                dataset_alias="synthetic_source",
                columns=["bucket", "value"],
            )
            self.assertEqual(generated["generation_status"], "ready")
            datasets = root / "datasets"
            datasets.mkdir()
            (datasets / "synthetic.sql").write_text(
                "SELECT bucket, value FROM mart.synthetic_daily\n",
                encoding="utf-8",
            )
            validation = dl_validate_project(tmp)
            self.assertEqual(validation["status"], "pass", validation["issues"])
            final_attestation = validation["final_payload_attestation"]
            composition = json.loads(
                (artifacts / "dashboard_composition.json").read_text(encoding="utf-8")
            )
            dashboard_payload = json.loads(
                (
                    artifacts
                    / "dashboard_payloads"
                    / "generated.dashboard.payload.json"
                ).read_text(encoding="utf-8")
            )
            create_projection = project_method_request(
                "createDashboard",
                dashboard_payload,
                object_type="dashboard",
                operation="create",
                workbook_id="workbook_target",
            )
            self.assertTrue(create_projection["ok"], create_projection["issues"])
            saved_entry = {
                "entryId": "dashboard_target",
                "revId": "rev_saved",
                "savedId": "saved_snapshot",
                "key": "synthetic-attested-dashboard",
                "meta": {"title": "Synthetic attested dashboard"},
                "data": dashboard_payload["entry"]["data"],
            }
            saved_path = artifacts / "readback" / "dashboard.saved.latest.json"
            saved_path.parent.mkdir(parents=True, exist_ok=True)
            saved_path.write_text(
                json.dumps({"branch": "saved", "dashboard": {"entry": saved_entry}}),
                encoding="utf-8",
            )

            proof_path = artifacts / "browser_qa" / "synthetic-proof.json"
            proof_path.parent.mkdir(parents=True, exist_ok=True)
            proof_path.write_text("{}\n", encoding="utf-8")
            browser_plan = build_browser_qa_plan(
                dashboard_id="dashboard_target",
                tab_ids=["main"],
                expected_object_ids=["trend_widget"],
                saved_revision="rev_saved",
                published_revision="rev_saved",
                dashboard_composition=composition,
                final_payload_attestation_sha256=final_attestation["attestation_sha256"],
                payload_set_sha256=final_attestation["payload_set_sha256"],
            )
            assertions = {item["id"]: True for item in BROWSER_QA_ASSERTIONS}
            viewport_results = [
                {
                    "schema_id": BROWSER_QA_RESULT_SCHEMA_ID,
                    "viewport": {"width": width, "height": 900},
                    "tab_id": "main",
                    "scroll_position": position,
                    "passed": True,
                    "assertions": assertions,
                    "observations": {},
                }
                for width in (item["width"] for item in browser_plan["viewports"])
                for position in ("top", "bottom")
            ]
            qa = build_qa_attestation(
                plan=browser_plan,
                viewport_results=viewport_results,
                dashboard_id="dashboard_target",
                saved_revision="rev_saved",
                published_revision="rev_saved",
                artifact_paths=[str(proof_path)],
            )
            self.assertTrue(qa["ok"], qa["issues"])
            (artifacts / "qa_attestation.json").write_text(
                json.dumps(qa),
                encoding="utf-8",
            )

            safe_plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="dashboard",
                object_type="dashboard",
                object_id="dashboard_target",
                saved_readback_path=str(saved_path),
                approved=True,
            )
            preflight = validate_safe_apply_plan_exhaustive(safe_plan)
            self.assertTrue(preflight["ok"], preflight["issues"])
            client = DashboardClient(saved_entry)
            result = execute_safe_apply(
                safe_plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

            expected_qa = {
                "dashboard_id": "dashboard_target",
                "saved_revision": "rev_saved",
                "published_revision": "rev_saved",
                "final_payload_attestation_sha256": final_attestation["attestation_sha256"],
                "payload_set_sha256": final_attestation["payload_set_sha256"],
                "dashboard_composition_sha256": composition["sha256"],
            }
            self.assertTrue(result["executed"], result)
            self.assertEqual(
                [method for method, _payload in client.calls],
                ["getDashboard", "updateDashboard", "getDashboard"],
            )
            self.assertTrue(
                result["actions"][0]["readback_verification"][
                    "publish_source_revision_matched"
                ]
            )
            self.assertEqual(
                delivery_status_from_qa_attestation(qa, **expected_qa),
                "done",
            )


if __name__ == "__main__":
    unittest.main()
