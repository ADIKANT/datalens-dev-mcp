from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]


def _valid_png_bytes(*, width: int = 2, height: int = 2) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def _write_capture(
    root: Path,
    *,
    image_bytes: bytes | None = None,
    checked_selectors: list[dict[str, object]] | None = None,
    selector_interaction: dict[str, object] | None = None,
    scroll_check: dict[str, object] | None = None,
) -> Path:
    image = root / "browser.png"
    image.write_bytes(image_bytes if image_bytes is not None else _valid_png_bytes())
    object_ids = ["chart_1"]
    capture = {
        "schema_version": "datalens.browser_capture.v1",
        "status": "passed",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target_url": "https://datalens.example/dash",
        "tab_id": "overview",
        "branch": "published",
        "object_revisions": {"chart_1": "rev_chart_1"},
        "changed_object_ids": object_ids,
        "checked_selectors": checked_selectors or [],
        "selector_interaction": selector_interaction
        or {
            "status": "not_applicable",
            "scope_object_ids": object_ids,
            "reason": {
                "code": "no_selectors_in_scope",
                "detail": "The changed runtime scope contains no selector controls.",
            },
        },
        "scroll_check": scroll_check
        or {
            "status": "not_applicable",
            "scope_object_ids": object_ids,
            "document_height": 800,
            "viewport_height": 800,
            "reason": {
                "code": "content_fits_viewport",
                "detail": "The complete target tab fits in the measured viewport.",
            },
        },
        "visible_widget_titles": ["Fleet utilization"],
        "body_text_excerpt": "Fleet utilization",
        "console_messages": [],
        "dom_error_texts": [],
        "marker_counts": {},
        "console_error_count": 0,
        "image_artifact": {
            "path": str(image),
            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        },
    }
    path = root / "browser.capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    return path


def _completed_execution_manifest() -> dict[str, object]:
    approval = {
        "approved": True,
        "approval_source": "codex_tool",
        "approval_note": "Approved safe apply",
    }
    action = {
        "index": 0,
        "action": "update_editor_chart",
        "method": "updateEditorChart",
        "object_id": "chart_1",
        "transaction_group_id": "delivery",
        "change_scope": "content",
        "mode": "save",
        "expected_revision": "rev_1",
        "payload_sha256": "a" * 64,
        "desired_overlay_sha256": "d" * 64,
        "readback_branch": "saved",
        "target_lock_hash": "lock_1",
        "approval_provenance": approval,
    }
    return {
        "schema_version": "datalens.safe_apply_execution_evidence.v1",
        "generated_at": "2026-07-10T10:00:00Z",
        "project_root": "/tmp/project",
        "run_id": "safe_apply_aaaaaaaaaaaa",
        "run_binding": {
            "project_root": "/tmp/project",
            "approved": True,
            "approval_provenance": approval,
            "target_lock_hash": "lock_1",
            "action_count": 1,
            "actions": [action],
        },
        "status": "completed",
        "actions": [
            {
                **action,
                "status": "executed",
                "executed": True,
                "write_result": {"path": "/tmp/write.json", "sha256": "b" * 64},
                "readback": {
                    "path": "/tmp/readback.json",
                    "sha256": "c" * 64,
                    "branch": "saved",
                    "object_id": "chart_1",
                    "revision_id": "rev_2",
                },
            }
        ],
    }


class RuntimeProofSchemaHardeningTests(unittest.TestCase):
    def test_truncated_png_header_is_not_readable_browser_proof(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_capture(Path(tmp), image_bytes=b"\x89PNG\r\n\x1a\ntruncated")
            validation = validate_browser_capture_artifact(str(capture))

        self.assertFalse(validation["ok"])
        self.assertEqual(validation["image_details"], {})
        self.assertTrue(any(issue["rule"] == "browser_capture_image_invalid" for issue in validation["issues"]))

    def test_valid_png_and_structured_not_applicable_evidence_pass(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_capture(Path(tmp))
            gate = build_runtime_gate_evidence(
                status="passed",
                browser_capture_artifact=str(capture),
                required_changed_object_ids=["chart_1"],
                required_target_url="https://datalens.example/dash",
                required_tab_id="overview",
                expected_titles=["Fleet utilization"],
            )

        self.assertEqual(gate["status"], "passed", gate["evidence_validation_issues"])
        self.assertEqual(gate["selector_interaction"]["status"], "not_applicable")
        self.assertEqual(gate["scroll_check"]["status"], "not_applicable")
        self.assertEqual(gate["browser_capture_validation"]["image_details"]["format"], "png")
        self.assertEqual(gate["browser_capture_validation"]["image_details"]["width"], 2)

    def test_selector_pass_requires_a_scoped_successful_interaction(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        selector_contract = {"status": "passed", "scope_object_ids": ["chart_1"]}
        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_capture(Path(tmp), selector_interaction=selector_contract)
            validation = validate_browser_capture_artifact(str(capture))

        self.assertFalse(validation["ok"])
        self.assertTrue(
            any(issue["rule"] == "browser_capture_selector_interaction" for issue in validation["issues"])
        )

    def test_scoped_selector_and_long_page_bottom_evidence_pass(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        checked_selectors = [
            {
                "selector_id": "period_selector",
                "interaction": "selected previous month and observed refresh",
                "status": "passed",
                "affected_object_ids": ["chart_1"],
                "selected_value": "previous_month",
            }
        ]
        selector_contract = {"status": "passed", "scope_object_ids": ["chart_1"]}
        completed_scroll = {
            "status": "passed",
            "scope_object_ids": ["chart_1"],
            "document_height": 1600,
            "viewport_height": 800,
            "start_scroll_y": 0,
            "end_scroll_y": 800,
            "bottom_reached": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_capture(
                Path(tmp),
                checked_selectors=checked_selectors,
                selector_interaction=selector_contract,
                scroll_check=completed_scroll,
            )
            validation = validate_browser_capture_artifact(str(capture))

        self.assertTrue(validation["ok"], validation["issues"])

    def test_long_page_scroll_must_measurably_reach_bottom(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        incomplete_scroll = {
            "status": "passed",
            "scope_object_ids": ["chart_1"],
            "document_height": 1600,
            "viewport_height": 800,
            "start_scroll_y": 0,
            "end_scroll_y": 600,
            "bottom_reached": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_capture(Path(tmp), scroll_check=incomplete_scroll)
            validation = validate_browser_capture_artifact(str(capture))

        self.assertFalse(validation["ok"])
        self.assertTrue(any(issue["rule"] == "browser_capture_scroll_bottom" for issue in validation["issues"]))

    def test_success_schemas_reject_missing_or_unexecuted_evidence(self):
        live_schema = json.loads((REPO_ROOT / "schemas" / "live_maintenance_run.schema.json").read_text())
        execution_schema = json.loads(
            (REPO_ROOT / "schemas" / "safe_apply_execution_evidence.schema.json").read_text()
        )
        invalid_live = {
            "schema_version": "datalens.delta_v7.live_maintenance_run.v1",
            "run_id": "run_1",
            "target": {"workbook_id": "workbook_1"},
            "status": "done",
            "phases": [],
            "runtime_gate": {"non_rendering_exemption": "Non-rendering target"},
            "completion_evidence": {
                "completion_ready": True,
                "missing_evidence": ["saved_readback_evidence"],
                "blocked_reasons": [],
            },
        }
        valid_execution = _completed_execution_manifest()
        invalid_execution = deepcopy(valid_execution)
        invalid_execution["actions"][0]["executed"] = False

        self.assertTrue(list(Draft202012Validator(live_schema).iter_errors(invalid_live)))
        self.assertEqual(list(Draft202012Validator(execution_schema).iter_errors(valid_execution)), [])
        self.assertTrue(list(Draft202012Validator(execution_schema).iter_errors(invalid_execution)))

    def test_hardened_schema_mirrors_are_valid_and_synchronized(self):
        schema_names = (
            "browser_capture.schema.json",
            "browser_runtime_smoke.schema.json",
            "live_maintenance_run.schema.json",
            "runtime_gate_evidence.schema.json",
            "safe_apply_execution_evidence.schema.json",
        )
        packaged_root = REPO_ROOT / "src" / "datalens_dev_mcp" / "assets" / "schemas"
        for name in schema_names:
            with self.subTest(name=name):
                schema = json.loads((REPO_ROOT / "schemas" / name).read_text())
                packaged = json.loads((packaged_root / name).read_text())
                Draft202012Validator.check_schema(schema)
                self.assertEqual(schema, packaged)


if __name__ == "__main__":
    unittest.main()
