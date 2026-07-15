import hashlib
import json
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


class RuntimeGateCompletionStatusTests(unittest.TestCase):
    def test_api_readback_without_runtime_proof_is_runtime_not_verified(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence, final_status_from_runtime_gate

        gate = build_runtime_gate_evidence(status="not_run", target_url="https://datalens.example/dash")

        self.assertEqual(final_status_from_runtime_gate(gate), "runtime_not_verified")

    def test_runtime_marker_blocks_success(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence, final_status_from_runtime_gate

        gate = build_runtime_gate_evidence(
            status="passed",
            target_url="https://datalens.example/dash",
            proof_artifacts=["/tmp/runtime.png"],
            console_messages=["ILLEGAL_AGGREGATION: aggregate function is found inside another function"],
        )

        self.assertEqual(gate["status"], "failed")
        self.assertGreater(gate["marker_counts"]["ILLEGAL_AGGREGATION"], 0)
        self.assertEqual(final_status_from_runtime_gate(gate), "blocked")

    def test_too_many_series_runtime_markers_block_success(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence, final_status_from_runtime_gate

        for marker in ("Too many series on the chart", "ERR.CK.TOOMANYLINES"):
            with self.subTest(marker=marker):
                gate = build_runtime_gate_evidence(
                    status="passed",
                    body_text_excerpt=f"Dashboard runtime error: {marker}",
                )

                self.assertEqual(gate["status"], "failed")
                self.assertGreater(gate["marker_counts"][marker], 0)
                self.assertIn(marker, gate["blocking_markers_found"])
                self.assertEqual(final_status_from_runtime_gate(gate), "blocked")

    def test_passed_runtime_gate_allows_done(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_runtime_gate_evidence, final_status_from_runtime_gate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proof = root / "runtime.png"
            proof.write_bytes(_valid_png_bytes())
            capture = root / "runtime.capture.json"
            capture.write_text(
                json.dumps(
                    {
                        "schema_version": "datalens.browser_capture.v1",
                        "status": "passed",
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "target_url": "https://datalens.example/dash",
                        "tab_id": "overview",
                        "branch": "published",
                        "object_revisions": {"chart_1": "rev_chart_1"},
                        "changed_object_ids": ["chart_1"],
                        "checked_selectors": [],
                        "selector_interaction": {
                            "status": "not_applicable",
                            "scope_object_ids": ["chart_1"],
                            "reason": {
                                "code": "no_selectors_in_scope",
                                "detail": "The changed runtime scope contains no selector controls.",
                            },
                        },
                        "scroll_check": {
                            "status": "not_applicable",
                            "scope_object_ids": ["chart_1"],
                            "document_height": 800,
                            "viewport_height": 800,
                            "reason": {
                                "code": "content_fits_viewport",
                                "detail": "The complete target tab fits in the measured viewport.",
                            },
                        },
                        "visible_widget_titles": [],
                        "console_messages": [],
                        "dom_error_texts": [],
                        "console_error_count": 0,
                        "image_artifact": {
                            "path": str(proof),
                            "sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
                        },
                    }
                ),
                encoding="utf-8",
            )
            gate = build_runtime_gate_evidence(
                status="passed",
                browser_capture_artifact=str(capture),
            )

        self.assertEqual(gate["status"], "passed")
        self.assertEqual(len(gate["proof_artifact_metadata"][0]["sha256"]), 64)
        self.assertEqual(final_status_from_runtime_gate(gate), "done")


if __name__ == "__main__":
    unittest.main()
