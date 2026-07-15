import json
import hashlib
import struct
import tempfile
import unittest
import zlib
from datetime import datetime, timezone
from pathlib import Path


def _valid_png_bytes() -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def _write_browser_capture(
    root: Path,
    *,
    target_url: str,
    tab_id: str,
    object_ids: list[str],
    titles: list[str] | None = None,
    console_messages: list[str] | None = None,
    dom_error_texts: list[str] | None = None,
    marker_counts: dict[str, int] | None = None,
    console_error_count: int = 0,
    branch: str = "published",
    object_revisions: dict[str, str] | None = None,
    capture_name: str = "browser",
) -> Path:
    image = root / f"{capture_name}.png"
    image.write_bytes(_valid_png_bytes())
    capture = root / f"{capture_name}.capture.json"
    capture.write_text(
        json.dumps(
            {
                "schema_version": "datalens.browser_capture.v1",
                "status": "passed",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "target_url": target_url,
                "tab_id": tab_id,
                "branch": branch,
                "object_revisions": object_revisions or {item: f"rev_{item}" for item in object_ids},
                "changed_object_ids": object_ids,
                "checked_selectors": [],
                "selector_interaction": {
                    "status": "not_applicable",
                    "scope_object_ids": object_ids,
                    "reason": {
                        "code": "no_selectors_in_scope",
                        "detail": "The changed runtime scope contains no selector controls.",
                    },
                },
                "scroll_check": {
                    "status": "not_applicable",
                    "scope_object_ids": object_ids,
                    "document_height": 800,
                    "viewport_height": 800,
                    "reason": {
                        "code": "content_fits_viewport",
                        "detail": "The complete target tab fits in the measured viewport.",
                    },
                },
                "visible_widget_titles": titles or [],
                "body_text_excerpt": " ".join(titles or []),
                "console_messages": console_messages or [],
                "dom_error_texts": dom_error_texts or [],
                "marker_counts": marker_counts or {},
                "console_error_count": console_error_count,
                "image_artifact": {
                    "path": str(image),
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )
    return capture


def _artifact(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _write_execution_manifest(root: Path, plan: dict, *, write_path: Path, readback_path: Path) -> dict:
    from datalens_dev_mcp.pipeline.safe_apply import safe_apply_run_binding, safe_apply_run_id

    binding = safe_apply_run_binding(plan)
    action = dict(binding["actions"][0])
    readback = json.loads(readback_path.read_text(encoding="utf-8"))
    object_id = action["object_id"]
    revision = readback.get("revId") or readback.get("entry", {}).get("revId")
    manifest = {
        "schema_version": "datalens.safe_apply_execution_evidence.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "run_id": safe_apply_run_id(plan),
        "run_binding": binding,
        "status": "completed",
        "actions": [
            {
                **action,
                "status": "executed",
                "executed": True,
                "write_result": _artifact(write_path),
                "readback": {
                    **_artifact(readback_path),
                    "branch": action["readback_branch"],
                    "object_id": object_id,
                    "revision_id": revision,
                },
            }
        ],
    }
    path = root / f"{manifest['run_id']}.execution.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return {"execution_artifact": _artifact(path)}


class DeltaV8RuntimeFirstContractsTests(unittest.TestCase):
    def test_unrelated_text_file_cannot_forge_browser_pass(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            unrelated = Path(tmp) / "unrelated.txt"
            unrelated.write_text("all good", encoding="utf-8")
            gate = build_runtime_gate_evidence(
                status="passed",
                target_url="https://datalens.example/dash",
                tab_id="overview",
                changed_object_ids=["chart_1"],
                proof_artifacts=[str(unrelated)],
            )

        self.assertNotEqual(gate["status"], "passed")
        self.assertFalse(gate["browser_capture_validation"]["ok"])

    def test_browser_capture_recomputes_markers_and_rejects_negative_counts(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_browser_capture(
                Path(tmp),
                target_url="https://datalens.example/dash",
                tab_id="overview",
                object_ids=["chart_1"],
                console_messages=["DB::Exception: UNKNOWN_TABLE telemetry"],
                marker_counts={"UNKNOWN_TABLE": -100},
            )
            gate = build_runtime_gate_evidence(status="passed", browser_capture_artifact=str(capture))

        self.assertEqual(gate["status"], "failed")
        self.assertGreater(gate["marker_counts"]["UNKNOWN_TABLE"], 0)
        self.assertTrue(any("nonnegative" in issue for issue in gate["evidence_validation_issues"]))

    def test_browser_capture_console_error_count_blocks_pass(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_browser_capture(
                Path(tmp),
                target_url="https://datalens.example/dash",
                tab_id="overview",
                object_ids=["chart_1"],
                console_messages=["Uncaught TypeError: cannot read properties of undefined"],
                console_error_count=1,
            )
            gate = build_runtime_gate_evidence(status="passed", browser_capture_artifact=str(capture))

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["console_error_count"], 1)

    def test_stale_browser_capture_is_rejected(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_browser_capture(
                Path(tmp),
                target_url="https://datalens.example/dash",
                tab_id="overview",
                object_ids=["chart_1"],
            )
            document = json.loads(capture.read_text(encoding="utf-8"))
            document["captured_at"] = "2000-01-01T00:00:00Z"
            capture.write_text(json.dumps(document), encoding="utf-8")
            gate = build_runtime_gate_evidence(status="passed", browser_capture_artifact=str(capture))

        self.assertEqual(gate["status"], "failed")
        self.assertTrue(
            any(item["rule"] == "browser_capture_freshness" for item in gate["artifact_validation_issues"])
        )

    def test_derived_title_and_dashboard_id_are_mandatory_runtime_bindings(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = _write_browser_capture(
                root,
                target_url="https://datalens.example/dash_1",
                tab_id="overview",
                object_ids=["chart_1"],
                titles=[],
            )
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_tab_id="overview",
                target_object_ids=["chart_1"],
                changed_objects=[{"object_id": "chart_1", "title": "Fleet utilization"}],
                approved=True,
                publish=False,
                baseline_dashboard={"entryId": "dash_1", "data": {"tabs": []}},
                runtime_gate_evidence={"status": "passed", "browser_capture_artifact": str(capture)},
                target_url="https://datalens.example/dash_1",
            )
            run = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))

        self.assertEqual(run["runtime_gate"]["missing_changed_object_ids"], ["dash_1"])
        self.assertEqual(run["runtime_gate"]["missing_expected_titles"], ["Fleet utilization"])
        self.assertEqual(run["runtime_gate"]["status"], "failed")

    def test_save_only_maintenance_rejects_publish_mode_action(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            action = {
                "action": "publish_object",
                "method": "updateEditorChart",
                "object_id": "chart_1",
                "publish": True,
                "payload": {"mode": "publish", "entry": {"entryId": "chart_1", "revId": "rev_1"}},
                "fresh_read_method": "getEditorChart",
                "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                "readback_method": "getEditorChart",
                "readback_payload": {"chartId": "chart_1", "branch": "published"},
            }
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                target_object_ids=["chart_1"],
                approved=True,
                publish=False,
                safe_apply_actions=[action],
            )

        self.assertTrue(
            any("publish_action_requires_top_level_publish_true" in item for item in result["blocked_reasons"])
        )

    def test_execution_manifest_replay_with_changed_payload_is_rejected(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def action(revision: str, title: str) -> dict:
                return {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "object_id": "chart_1",
                    "payload": {
                        "mode": "save",
                        "entry": {"entryId": "chart_1", "revId": revision, "data": {"title": title}},
                    },
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_1", "branch": "saved"},
                }

            readback = root / "saved.json"
            readback.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "live_readback": True,
                        "entry": {"entryId": "chart_1", "revId": "rev_after"},
                    }
                ),
                encoding="utf-8",
            )
            write_result = root / "write.json"
            write_result.write_text(json.dumps({"entry": {"entryId": "chart_1", "revId": "rev_after"}}))
            old_plan = create_safe_apply_plan(
                project_root=str(root), actions=[action("rev_old", "Old payload")], approved=True
            )
            replayed = _write_execution_manifest(root, old_plan, write_path=write_result, readback_path=readback)
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                target_object_ids=["chart_1"],
                approved=True,
                publish=False,
                safe_apply_actions=[action("rev_new", "New payload")],
                safe_apply_execution_evidence=replayed,
                saved_readback_evidence={"artifact_path": str(readback)},
            )

        self.assertEqual(result["completion_evidence_status"], "blocked")
        self.assertTrue(any("approved safe-apply plan" in item for item in result["blocked_reasons"]))

    def test_safe_apply_run_id_binds_payload_mode_and_revision(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, safe_apply_run_id

        def plan(mode: str, revision: str, title: str) -> dict:
            return create_safe_apply_plan(
                project_root="/tmp/project",
                approved=True,
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "object_id": "chart_1",
                        "payload": {
                            "mode": mode,
                            "entry": {"entryId": "chart_1", "revId": revision, "data": {"title": title}},
                        },
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {
                            "chartId": "chart_1",
                            "branch": "published" if mode == "publish" else "saved",
                        },
                        "publish": mode == "publish",
                        "source_branch": "saved" if mode == "publish" else "",
                    }
                ],
            )

        ids = {
            safe_apply_run_id(plan("save", "rev_1", "A")),
            safe_apply_run_id(plan("save", "rev_2", "A")),
            safe_apply_run_id(plan("save", "rev_1", "B")),
            safe_apply_run_id(plan("publish", "rev_1", "A")),
        }
        self.assertEqual(len(ids), 4)

    def test_wrapper_claims_and_unrelated_text_cannot_forge_completion(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unrelated = root / "unrelated.txt"
            unrelated.write_text("executed=true branch=saved live_readback=true chart_1", encoding="utf-8")
            action = {
                "action": "update_editor_chart",
                "method": "updateEditorChart",
                "object_id": "chart_1",
                "payload": {"mode": "save", "entry": {"entryId": "chart_1", "revId": "rev_1"}},
                "fresh_read_method": "getEditorChart",
                "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                "readback_method": "getEditorChart",
                "readback_payload": {"chartId": "chart_1", "branch": "saved"},
            }
            forged = {
                "executed": True,
                "status": "completed",
                "run_id": "safe_apply_forged",
                "artifact_path": str(unrelated),
                "branch": "saved",
                "live_readback": True,
                "object_ids": ["chart_1"],
            }
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                target_object_ids=["chart_1"],
                approved=True,
                publish=False,
                safe_apply_actions=[action],
                safe_apply_execution_evidence=forged,
                saved_readback_evidence=forged,
            )

        self.assertEqual(result["completion_evidence_status"], "blocked")
        self.assertTrue(any("must be JSON" in item for item in result["blocked_reasons"]))

    def test_nonexistent_runtime_artifact_reproduction_cannot_finish_done(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="wb",
                dashboard_id="dash",
                approved=True,
                publish=True,
                runtime_gate_evidence={
                    "schema_version": "datalens.delta_v7.runtime_gate_evidence.v1",
                    "status": "passed",
                    "proof_artifacts": ["/definitely/missing/browser.png"],
                },
            )
            run = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))

        self.assertNotEqual(result["status"], "done")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(run["runtime_gate"]["status"], "failed")
        self.assertTrue(
            any(item["rule"] == "artifact_missing" for item in run["runtime_gate"]["artifact_validation_issues"])
        )
        self.assertFalse(run["completion_evidence"]["completion_ready"])

    def test_runtime_gate_binds_titles_ids_target_and_preserves_console_messages(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_browser_capture(
                Path(tmp),
                target_url="https://datalens.example/wrong",
                tab_id="wrong-tab",
                object_ids=["chart_wrong"],
                titles=["Different title"],
                console_messages=["console info retained"],
            )
            gate = build_runtime_gate_evidence(
                status="passed",
                required_target_url="https://datalens.example/dash",
                required_tab_id="overview",
                required_changed_object_ids=["chart_1"],
                expected_titles=["Fleet utilization"],
                browser_capture_artifact=str(capture),
            )

        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["console_messages"], ["console info retained"])
        self.assertEqual(gate["missing_changed_object_ids"], ["chart_1"])
        self.assertEqual(gate["missing_expected_titles"], ["Fleet utilization"])
        self.assertTrue(gate["proof_artifact_metadata"][0]["sha256"])

    def test_runtime_gate_rejects_supplied_artifact_hash_mismatch(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_browser_capture(
                Path(tmp),
                target_url="https://datalens.example/dash",
                tab_id="overview",
                object_ids=["chart_1"],
            )
            gate = build_runtime_gate_evidence(
                status="passed",
                browser_capture_artifact=str(capture),
                browser_capture_artifact_metadata={"path": str(capture), "sha256": "0" * 64},
            )

        self.assertEqual(gate["status"], "failed")
        self.assertTrue(any(item["rule"] == "artifact_sha256_mismatch" for item in gate["artifact_validation_issues"]))

    def test_valid_browser_proof_without_execution_stays_plan_only(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_browser_capture(
                Path(tmp),
                target_url="https://datalens.example/dash_1",
                tab_id="overview",
                object_ids=["dash_1", "chart_1"],
            )
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_tab_id="overview",
                target_object_ids=["chart_1"],
                approved=True,
                publish=False,
                runtime_gate_evidence={
                    "status": "passed",
                    "browser_capture_artifact": str(capture),
                },
                target_url="https://datalens.example/dash_1",
            )

        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["runtime_first_status"], "runtime_not_verified")
        self.assertEqual(result["completion_evidence_status"], "not_supplied")

    def test_done_requires_executed_save_publish_and_both_readbacks(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update
        from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan, create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def write_json(name, value):
                path = root / name
                path.write_text(json.dumps(value), encoding="utf-8")
                return path

            saved = write_json(
                "saved.json",
                {
                    "branch": "saved",
                    "live_readback": True,
                    "entry": {
                        "entryId": "chart_1",
                        "revId": "rev_saved",
                        "savedId": "saved_1",
                        "data": {"title": "Fleet utilization"},
                    },
                },
            )
            save_write = write_json("save.write.json", {"entry": {"entryId": "chart_1", "revId": "rev_saved"}})
            publish_write = write_json(
                "publish.write.json", {"entry": {"entryId": "chart_1", "revId": "rev_published"}}
            )
            publish_readback = write_json(
                "publish.readback.json", {"entry": {"entryId": "chart_1", "revId": "rev_published"}}
            )
            published = write_json(
                "published.json",
                {
                    "branch": "published",
                    "live_readback": True,
                    "object_ids": ["chart_1"],
                    "revId": "rev_published",
                },
            )
            safe_action = {
                "action": "update_editor_chart",
                "method": "updateEditorChart",
                "object_id": "chart_1",
                "payload": {"mode": "save", "entry": {"entryId": "chart_1", "revId": "rev_1"}},
                "fresh_read_method": "getEditorChart",
                "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                "readback_method": "getEditorChart",
                "readback_payload": {"chartId": "chart_1", "branch": "saved"},
            }
            save_plan = create_safe_apply_plan(project_root=str(root), actions=[safe_action], approved=True)
            execution_evidence = _write_execution_manifest(
                root, save_plan, write_path=save_write, readback_path=saved
            )
            publish_plan = create_publish_safe_apply_plan(
                project_root=str(root),
                target="chart",
                object_type="editor_chart",
                object_id="chart_1",
                saved_readback_path=str(saved),
                approved=True,
            )
            self.assertTrue(publish_plan["ok"])
            publish_evidence = _write_execution_manifest(
                root, publish_plan, write_path=publish_write, readback_path=publish_readback
            )
            saved_capture = _write_browser_capture(
                root,
                target_url="https://datalens.example/chart_1",
                tab_id="overview",
                object_ids=["chart_1"],
                titles=["Fleet utilization"],
                branch="saved",
                object_revisions={"chart_1": "rev_saved"},
                capture_name="saved_browser",
            )
            published_capture = _write_browser_capture(
                root,
                target_url="https://datalens.example/chart_1",
                tab_id="overview",
                object_ids=["chart_1"],
                titles=["Fleet utilization"],
                branch="published",
                object_revisions={"chart_1": "rev_published"},
                capture_name="published_browser",
            )
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                target_tab_id="overview",
                target_object_ids=["chart_1"],
                approved=True,
                publish=True,
                safe_apply_actions=[safe_action],
                safe_apply_execution_evidence=execution_evidence,
                saved_readback_evidence={"artifact_path": str(saved)},
                publish_from_saved_evidence=publish_evidence,
                published_readback_evidence={"artifact_path": str(published)},
                saved_runtime_gate_evidence={
                    "status": "passed",
                    "browser_capture_artifact": str(saved_capture),
                },
                published_runtime_gate_evidence={
                    "status": "passed",
                    "browser_capture_artifact": str(published_capture),
                },
                target_url="https://datalens.example/chart_1",
            )
            run = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["runtime_first_status"], "runtime_passed")
        self.assertTrue(run["completion_evidence"]["completion_ready"])
        self.assertEqual(len(run["handoff"]["proof"]["api_readback_paths"]), 2)

    def test_standard_wrapper_exposes_baseline_and_completion_evidence_inputs(self):
        from datalens_dev_mcp.server import list_tools

        tool = next(item for item in list_tools() if item["name"] == "dl_run_live_maintenance_update")
        properties = tool["inputSchema"]["properties"]

        for name in (
            "baseline_dashboard",
            "proposed_dashboard",
            "safe_apply_execution_evidence",
            "saved_readback_evidence",
            "publish_from_saved_evidence",
            "published_readback_evidence",
            "saved_runtime_gate_evidence",
            "published_runtime_gate_evidence",
        ):
            with self.subTest(name=name):
                self.assertIn(name, properties)
                self.assertEqual(properties[name]["type"], "object")

    def test_success_schemas_reject_unbound_passed_and_done_states(self):
        from jsonschema import Draft202012Validator

        root = Path(__file__).resolve().parents[2]
        runtime_schema = json.loads((root / "schemas" / "runtime_gate_evidence.schema.json").read_text())
        smoke_schema = json.loads((root / "schemas" / "browser_runtime_smoke.schema.json").read_text())
        live_schema = json.loads((root / "schemas" / "live_maintenance_run.schema.json").read_text())

        runtime_errors = list(
            Draft202012Validator(runtime_schema).iter_errors(
                {
                    "schema_version": "datalens.delta_v7.runtime_gate_evidence.v1",
                    "status": "passed",
                    "target_url": "",
                    "marker_counts": {},
                }
            )
        )
        smoke_errors = list(
            Draft202012Validator(smoke_schema).iter_errors(
                {"status": "passed", "target_url": "", "checked_markers": [], "blocking_markers_found": []}
            )
        )
        live_errors = list(
            Draft202012Validator(live_schema).iter_errors(
                {
                    "schema_version": "datalens.delta_v7.live_maintenance_run.v1",
                    "run_id": "run",
                    "target": {"workbook_id": "wb"},
                    "status": "done",
                    "phases": [],
                    "runtime_gate": {"status": "not_run"},
                    "completion_evidence": {
                        "completion_ready": False,
                        "missing_evidence": [],
                        "blocked_reasons": [],
                    },
                }
            )
        )

        self.assertTrue(runtime_errors)
        self.assertTrue(smoke_errors)
        self.assertTrue(live_errors)

    def test_validate_dataset_ok_but_browser_field_not_found_blocks_done(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_tab_id="overview",
                target_object_ids=["chart_1"],
                target_url="https://datalens.example/dash_1",
                approved=True,
                publish=False,
                runtime_gate_evidence={
                    "status": "passed",
                    "console_messages": ["validateDataset ok", "ERR.DS_API.FIELD.NOT_FOUND team_nm_6ae8"],
                    "proof_artifacts": ["/tmp/browser-smoke.png"],
                },
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["runtime_first_status"], "runtime_failed")
        self.assertIn("runtime_gate_failed", result["blocked_reasons"])

    def test_validate_dataset_is_schema_hint_not_acceptance_gate(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_guarded_dataset_update

        plan = dl_plan_guarded_dataset_update(
            dataset_id="dataset_1",
            current_dataset={"datasetId": "dataset_1", "revId": "rev_1", "fields": [{"guid": "field_1"}]},
            proposed_dataset={"datasetId": "dataset_1", "revId": "rev_1", "fields": [{"guid": "field_1"}]},
            workbook_id="workbook_1",
            validate_only=True,
        )

        self.assertEqual(plan["validation_gate_classification"]["validateDataset"], "schema_hint")
        self.assertEqual(plan["validation_gate_classification"]["browser_runtime_smoke"], "acceptance_gate")
        validate_steps = [step for step in plan["action_sequence"] if step["method"] == "validateDataset"]
        self.assertEqual(validate_steps[0]["gate_role"], "schema_hint")
        self.assertFalse(validate_steps[0]["acceptance_gate"])

    def test_stale_revision_retry_policy_blocks_runtime_fix_fallback(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan

        plan = create_safe_apply_plan(
            project_root="/tmp/delta-v8",
            approved=True,
            actions=[
                {
                    "action": "update_dataset",
                    "method": "updateDataset",
                    "object_id": "dataset_1",
                    "expected_rev_id": "rev_1",
                    "payload": {"datasetId": "dataset_1", "revId": "rev_1", "fields": []},
                    "fresh_read_method": "getDataset",
                    "fresh_read_payload": {"datasetId": "dataset_1"},
                    "readback_method": "getDataset",
                    "readback_payload": {"datasetId": "dataset_1"},
                    "readback_mode": "minimal",
                    "requires_fresh_read": True,
                    "readback_required": True,
                }
            ],
        )

        policy = plan["actions"][0]["stale_revision_retry_policy"]
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["max_retry_count"], 1)
        self.assertFalse(policy["create_new_on_revision_mismatch"])
        self.assertEqual(policy["unresolved_status"], "revision_conflict_unresolved")

    def test_runtime_fix_or_generated_name_blocks_without_lifecycle(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive

        plan = create_safe_apply_plan(
            project_root="/tmp/delta-v8",
            approved=True,
            actions=[
                {
                    "action": "create_generated_repair_dataset",
                    "method": "createDataset",
                    "payload": {"dataset": {"name": "Generated Runtime Fix Repair"}},
                    "requires_fresh_read": True,
                    "fresh_read_method": "getWorkbookEntries",
                    "fresh_read_payload": {"workbookId": "workbook_1"},
                    "readback_method": "getWorkbookEntries",
                    "readback_payload": {"workbookId": "workbook_1"},
                }
            ],
        )
        result = validate_safe_apply_plan_exhaustive(plan)

        self.assertFalse(result["ok"])
        self.assertIn("temporary/runtime-fix object names require an explicit cleanup lifecycle", "\n".join(result["issues"]))

    def test_existing_pivot_table_list_features_preserved(self):
        from datalens_dev_mcp.pipeline.baseline_preservation import build_baseline_diff_contract

        contract = build_baseline_diff_contract(
            dashboard_id="dash_1",
            baseline_dashboard={
                "tabs": [
                    {
                        "id": "requests",
                        "items": [
                            {
                                "chartId": "request_list",
                                "type": "pivot table request list",
                                "links": ["ticket"],
                                "actions": ["open"],
                                "sort": ["priority"],
                                "formatting": {"priority": "red"},
                            }
                        ],
                    }
                ]
            },
            proposed_dashboard={
                "tabs": [
                    {
                        "id": "requests",
                        "items": [
                            {
                                "chartId": "request_list",
                                "type": "flatTable",
                            }
                        ],
                    }
                ]
            },
        )

        self.assertIn("table_or_pivot_actionability_regressed", contract["blocked_reasons"])
        loss = contract["unexpected_layout_diff"][0]
        self.assertEqual(loss["diff_type"], "lost_table_or_pivot_features")
        self.assertIn("links", loss["missing_features"])
        self.assertIn("actions", loss["missing_features"])
        self.assertIn("sort", loss["missing_features"])

    def test_sql_runtime_reality_detects_logged_risks(self):
        from datalens_dev_mcp.pipeline.sql_runtime_reality import build_sql_runtime_reality_check

        report = build_sql_runtime_reality_check(
            sql="""
            WITH rcp_scope AS (SELECT id FROM src)
            SELECT any(relation_nm) AS relation_nm
            FROM issues b JOIN rcp_scope AS rcp ON rcp.id = b.id
            WHERE relation_nm = 'blocked'
            """,
            dialect="clickhouse",
            target_execution_engine="datalens_clickhouse",
            validated_by=["validateDataset", "metadata_fetch_trino"],
        )

        self.assertTrue(report["runtime_probe_required"])
        self.assertIn("aggregate_alias_in_where", report["risk_patterns"])
        self.assertIn("cte_on_join_side_with_external_or_free_variables", report["risk_patterns"])
        self.assertIn("source_alias_leakage", report["risk_patterns"])
        self.assertIn("validateDataset is a schema/compile hint, not runtime acceptance", report["known_limitations"])

    def test_source_availability_consumer_conflict_blocks_publish(self):
        from datalens_dev_mcp.pipeline.source_availability import build_source_availability_runtime_matrix

        matrix = build_source_availability_runtime_matrix(
            {
                "schema_version": "datalens.delta_v7.source_availability_consumer_matrix.v1",
                "sources": [
                    {
                        "source_key": "source_inventory",
                        "environment": "stage",
                        "physical_table_present": True,
                        "static_supported": True,
                        "row_count": 10,
                        "expected_status": "OK",
                        "consumer_statuses": {"data_health": "OK", "source_tables": "NO_TABLE"},
                    }
                ],
            }
        )

        self.assertFalse(matrix["ok"])
        self.assertEqual(matrix["status"], "blocked")
        self.assertEqual(matrix["conflicts"][0]["rule"], "consumer_status_conflict")

    def test_labels_required_for_changed_line_bar_column_wizard_payload(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_visual_dataset_contract

        result = validate_wizard_visual_dataset_contract(
            {
                "chart_type": "bar",
                "datasetsPartialFields": [{"guid": "measure_1"}],
                "measures": ["measure_1"],
            }
        )

        rules = {finding.rule for finding in result.findings}
        self.assertFalse(result.ok)
        self.assertIn("wizard_labels_required_by_default", rules)

    def test_wizard_line_can_use_readable_axes_and_value_tooltips_instead_of_labels(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_visual_dataset_contract

        result = validate_wizard_visual_dataset_contract(
            {
                "chart_type": "line",
                "datasetsPartialFields": [{"guid": "measure_1"}],
                "measures": ["measure_1"],
                "labels": [],
                "axes": {"show": True, "date_axis_ascending": True},
                "tooltips": [{"fieldGuid": "measure_1"}],
            }
        )

        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])

    def test_wizard_bar_still_requires_labels_when_axes_and_tooltips_exist(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_visual_dataset_contract

        result = validate_wizard_visual_dataset_contract(
            {
                "chart_type": "bar",
                "datasetsPartialFields": [{"guid": "measure_1"}],
                "measures": ["measure_1"],
                "labels": [],
                "axes": {"show": True},
                "tooltips": [{"fieldGuid": "measure_1"}],
            }
        )

        self.assertFalse(result.ok)
        self.assertIn("wizard_labels_required_by_default", {finding.rule for finding in result.findings})

    def test_browser_unavailable_is_runtime_not_verified(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_object_ids=["chart_1"],
                approved=True,
                publish=False,
                runtime_gate_evidence={"status": "browser_auth_required", "blocked_reason": "auth"},
            )

        self.assertEqual(result["status"], "runtime_not_verified")
        self.assertEqual(result["runtime_first_status"], "runtime_not_verified")

    def test_browser_error_details_are_extracted_when_more_details_present(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_browser_runtime_smoke

        smoke = build_browser_runtime_smoke(
            status="failed",
            target_url="https://datalens.example/dash",
            body_text_excerpt=(
                "Data fetching error. More. Database response: DB::Exception: UNKNOWN_TABLE. "
                "Sent query: SELECT * FROM missing_table"
            ),
        )

        self.assertEqual(smoke["status"], "failed")
        self.assertTrue(smoke["detail_extraction_attempted"])
        self.assertEqual(smoke["detail_extraction_status"], "found")
        self.assertIn("UNKNOWN_TABLE", smoke["blocking_markers_found"])

    def test_wizard_formula_resolves_cyrillic_and_spaced_field_names(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "datasetsPartialFields": [{"guid": "status_guid", "name": "Статус", "type": "string"}],
                "filters": [{"formula": "IF([Статус] = 'OK', [Field Name], NULL)"}],
            },
            [
                {
                    "datasetId": "dataset_1",
                    "fields": [
                        {"guid": "status_guid", "name": "Статус", "type": "string"},
                        {"guid": "field_name_guid", "name": "Field Name", "type": "string"},
                    ],
                    "connection": {"id": "connection_not_a_field"},
                }
            ],
        )

        self.assertTrue(report["ok"], report["findings"])

    def test_generic_nested_ids_do_not_count_as_dataset_fields(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {"filters": [{"field": "connection_not_a_field"}]},
            [{"datasetId": "dataset_1", "fields": [], "connection": {"id": "connection_not_a_field"}}],
        )

        self.assertIn(
            "wizard_field_ref_unresolved_against_dataset_readback",
            {item["rule"] for item in report["findings"]},
        )

    def test_flat_table_description_requires_visible_hint_settings(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_visual_dataset_contract

        result = validate_wizard_visual_dataset_contract(
            {
                "visualization": {
                    "id": "flatTable",
                    "placeholders": [
                        {"items": [{"guid": "quality", "description": "Explain quality statuses"}]}
                    ],
                },
                "datasetsPartialFields": [{"guid": "quality"}],
            }
        )

        self.assertIn("wizard_flat_table_hint_not_enabled", {item.rule for item in result.findings})


if __name__ == "__main__":
    unittest.main()
