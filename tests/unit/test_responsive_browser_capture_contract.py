from __future__ import annotations

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


def _png_bytes(*, width: int = 2, height: int = 2) -> bytes:
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


def _write_v2_capture(
    root: Path,
    *,
    change_scope: str = "layout",
    widths: tuple[int, ...] = (1200, 1440),
    device_pixel_ratio: float = 1.0,
    screenshot_size: tuple[int, int] | None = None,
    horizontal_overflow_px: float = 0,
    clipped_object_ids: list[str] | None = None,
    missing_object_ids: list[str] | None = None,
) -> Path:
    object_ids = ["chart_alpha", "chart_beta"]
    viewport_checks: list[dict[str, object]] = []
    for index, width in enumerate(widths):
        screenshot = root / f"viewport-{width}-{index}.png"
        image_width, image_height = screenshot_size or (
            round(width * device_pixel_ratio),
            round(900 * device_pixel_ratio),
        )
        screenshot.write_bytes(_png_bytes(width=image_width, height=image_height))
        viewport_checks.append(
            {
                "label": f"desktop-{width}",
                "width": width,
                "height": 900,
                "device_pixel_ratio": device_pixel_ratio,
                "document_width": width,
                "horizontal_overflow_px": horizontal_overflow_px,
                "scope_object_ids": object_ids,
                "visible_object_ids": object_ids,
                "clipped_object_ids": clipped_object_ids or [],
                "missing_object_ids": missing_object_ids or [],
                "screenshot_artifact": {
                    "path": str(screenshot),
                    "sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                },
            }
        )
    capture = {
        "schema_version": "datalens.browser_capture.v2",
        "status": "passed",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target_url": "https://datalens.example/dashboard",
        "tab_id": "overview",
        "branch": "published",
        "object_revisions": {
            "chart_alpha": "rev_alpha",
            "chart_beta": "rev_beta",
        },
        "changed_object_ids": object_ids,
        "checked_selectors": [],
        "selector_interaction": {
            "status": "not_applicable",
            "scope_object_ids": object_ids,
            "reason": {
                "code": "no_selectors_in_scope",
                "detail": "The synthetic changed scope has no selector controls.",
            },
        },
        "scroll_check": {
            "status": "not_applicable",
            "scope_object_ids": object_ids,
            "document_height": 900,
            "viewport_height": 900,
            "reason": {
                "code": "content_fits_viewport",
                "detail": "The synthetic target fits in the measured viewport.",
            },
        },
        "visible_widget_titles": ["Synthetic trend", "Synthetic summary"],
        "body_text_excerpt": "Synthetic trend Synthetic summary",
        "console_messages": [],
        "dom_error_texts": [],
        "marker_counts": {},
        "console_error_count": 0,
        "change_scope": change_scope,
        "viewport_checks": viewport_checks,
    }
    path = root / "browser.capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    return path


class ResponsiveBrowserCaptureContractTests(unittest.TestCase):
    def test_layout_capture_requires_and_accepts_compact_and_wide_viewports(self):
        from datalens_dev_mcp.pipeline.runtime_gate import build_browser_runtime_smoke

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_v2_capture(Path(tmp))
            smoke = build_browser_runtime_smoke(
                status="passed",
                browser_capture_artifact=str(capture),
                required_changed_chart_ids=["chart_alpha", "chart_beta"],
            )

        self.assertEqual(smoke["status"], "passed", smoke["evidence_validation_issues"])
        self.assertEqual(smoke["browser_capture_schema_version"], "datalens.browser_capture.v2")
        self.assertEqual(smoke["change_scope"], "layout")
        self.assertEqual([item["width"] for item in smoke["viewport_checks"]], [1200, 1440])
        self.assertEqual(len(smoke["screenshot_artifacts"]), 2)
        self.assertTrue(set(smoke["screenshot_artifacts"]).issubset(set(smoke["proof_artifacts"])))
        self.assertEqual(
            len(smoke["browser_capture_validation"]["viewport_image_details"]),
            2,
        )
        first_image = smoke["browser_capture_validation"]["viewport_image_details"][0]
        self.assertEqual(first_image["viewport_width"], 1200)
        self.assertEqual(first_image["device_pixel_ratio"], 1.0)
        self.assertEqual(first_image["width"], 1200)
        self.assertEqual(first_image["height"], 900)

    def test_content_capture_accepts_one_viewport(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_v2_capture(
                Path(tmp),
                change_scope="content",
                widths=(1280,),
            )
            validation = validate_browser_capture_artifact(str(capture))

        self.assertTrue(validation["ok"], validation["issues"])
        self.assertEqual(len(validation["image_artifacts"]), 1)

    def test_fractional_device_pixel_ratio_scales_expected_screenshot_size(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_v2_capture(
                Path(tmp),
                change_scope="content",
                widths=(400,),
                device_pixel_ratio=1.5,
            )
            validation = validate_browser_capture_artifact(str(capture))

        self.assertTrue(validation["ok"], validation["issues"])
        details = validation["viewport_image_details"][0]
        self.assertEqual(details["expected_image_width"], 600)
        self.assertEqual(details["expected_image_height"], 1350)
        self.assertEqual(details["width"], 600)
        self.assertEqual(details["height"], 1350)

    def test_layout_capture_rejects_single_or_duplicate_widths(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        for widths in ((1200,), (1200, 1200)):
            with self.subTest(widths=widths), tempfile.TemporaryDirectory() as tmp:
                capture = _write_v2_capture(Path(tmp), widths=widths)
                validation = validate_browser_capture_artifact(str(capture))

            self.assertFalse(validation["ok"])
            self.assertTrue(
                any(issue["rule"] == "browser_capture_viewport_coverage" for issue in validation["issues"])
            )

    def test_viewport_overflow_clipping_and_missing_ids_are_blocking(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_v2_capture(
                Path(tmp),
                horizontal_overflow_px=3,
                clipped_object_ids=["chart_alpha"],
                missing_object_ids=["chart_beta"],
            )
            validation = validate_browser_capture_artifact(str(capture))

        rules = {issue["rule"] for issue in validation["issues"]}
        self.assertFalse(validation["ok"])
        self.assertIn("browser_capture_horizontal_overflow", rules)
        self.assertIn("browser_capture_viewport_clipping", rules)
        self.assertIn("browser_capture_viewport_missing", rules)

    def test_every_viewport_screenshot_is_hash_bound_and_verified(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_v2_capture(Path(tmp))
            document = json.loads(capture.read_text(encoding="utf-8"))
            document["viewport_checks"][1]["screenshot_artifact"]["sha256"] = "0" * 64
            capture.write_text(json.dumps(document), encoding="utf-8")
            validation = validate_browser_capture_artifact(str(capture))

        self.assertFalse(validation["ok"])
        self.assertTrue(any(issue["rule"] == "artifact_sha256_mismatch" for issue in validation["issues"]))

    def test_viewport_screenshot_dimensions_must_match_css_viewport_and_dpr(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_v2_capture(Path(tmp), screenshot_size=(2, 2))
            validation = validate_browser_capture_artifact(str(capture))

        self.assertFalse(validation["ok"])
        self.assertTrue(
            any(
                issue["rule"] == "browser_capture_viewport_screenshot_dimensions"
                for issue in validation["issues"]
            )
        )

    def test_viewport_device_pixel_ratio_is_required_and_positive(self):
        from datalens_dev_mcp.pipeline.runtime_gate import validate_browser_capture_artifact

        with tempfile.TemporaryDirectory() as tmp:
            capture = _write_v2_capture(Path(tmp))
            document = json.loads(capture.read_text(encoding="utf-8"))
            document["viewport_checks"][0].pop("device_pixel_ratio")
            document["viewport_checks"][1]["device_pixel_ratio"] = 0
            capture.write_text(json.dumps(document), encoding="utf-8")
            validation = validate_browser_capture_artifact(str(capture))

        self.assertFalse(validation["ok"])
        self.assertEqual(
            sum(
                issue["rule"] == "browser_capture_device_pixel_ratio"
                for issue in validation["issues"]
            ),
            2,
        )

    def test_schema_accepts_v1_and_v2_and_packaged_mirrors_match(self):
        schema_path = REPO_ROOT / "schemas" / "browser_capture.schema.json"
        packaged_path = (
            REPO_ROOT
            / "src"
            / "datalens_dev_mcp"
            / "assets"
            / "schemas"
            / "browser_capture.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        packaged = json.loads(packaged_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema, packaged)

        validator = Draft202012Validator(schema)
        with tempfile.TemporaryDirectory() as tmp:
            v2_path = _write_v2_capture(Path(tmp))
            v2 = json.loads(v2_path.read_text(encoding="utf-8"))
            v1 = {
                **v2,
                "schema_version": "datalens.browser_capture.v1",
                "image_artifact": v2["viewport_checks"][0]["screenshot_artifact"],
            }
            v1.pop("change_scope")
            v1.pop("viewport_checks")

        self.assertEqual(list(validator.iter_errors(v1)), [])
        self.assertEqual(list(validator.iter_errors(v2)), [])


if __name__ == "__main__":
    unittest.main()
