from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.html_pages import (
    HTML_PAGE_CONTRACT_VERSION,
    render_standalone_html_page,
    validate_standalone_html_page,
)
from datalens_dev_mcp.knowledge.recipes import build_recipe_bundle, select_authoring_recipe
from datalens_dev_mcp.mcp.tools.pipeline import dl_generate_editor_bundle, dl_validate_project
from datalens_dev_mcp.mcp.tools.runtime import dl_validate_editor_runtime_contract


class HtmlPageAuthoringTests(unittest.TestCase):
    def test_generator_is_deterministic_self_contained_and_script_safe(self):
        spec = {
            "title": "Synthetic report",
            "summary": "Portable fixture.",
            "data": {"text": "</script><img src=x>", "value": 42},
        }
        first = render_standalone_html_page(spec)
        second = render_standalone_html_page(spec)

        self.assertTrue(first["ok"], first["validation"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["schema_version"], HTML_PAGE_CONTRACT_VERSION)
        self.assertNotIn("</script><img src=x>", first["html"])
        self.assertIn("URLSearchParams", first["html"])
        self.assertIn("'EXPORT'", first["html"])
        self.assertIn("'OPEN_URL'", first["html"])
        self.assertNotIn("Content-Security-Policy", first["html"])

    def test_validator_blocks_sandbox_escape_and_network_apis(self):
        valid = render_standalone_html_page({"title": "Synthetic"})["html"]
        hostile = valid.replace(
            "</body>",
            "<iframe src=\"https://example.invalid\"></iframe>"
            "<script>localStorage.setItem('x','1');fetch('/private')</script></body>",
        )
        result = validate_standalone_html_page(hostile)
        rules = {finding["rule"] for finding in result["findings"]}

        self.assertFalse(result["ok"])
        self.assertLessEqual({"sandbox_tag", "persistent_storage", "network_fetch"}, rules)

    def test_validator_enforces_csp_for_css_srcset_media_and_script_schemes(self):
        valid = render_standalone_html_page({"title": "Synthetic"})["html"]
        hostile = valid.replace(
            "</head>",
            "<meta http-equiv=\"refresh\" content=\"0;url=https://example.invalid\">"
            "<link rel=\"stylesheet\" href=\"data:text/css,body{}\">"
            "<style>.x{background:url(./missing.png)}"
            "@import 'https://example.invalid/theme.css';</style></head>",
        ).replace(
            "</body>",
            "<img srcset=\"https://example.invalid/image.png 1x\">"
            "<video src=\"https://example.invalid/video.mp4\"></video>"
            "<script src=\"data:text/javascript,alert(1)\"></script>"
            "<a href=\"https://example.invalid\" download>download</a>"
            "<button onclick=\"fetch('/private')\">run</button></body>",
        )
        result = validate_standalone_html_page(hostile)
        rules = {finding["rule"] for finding in result["findings"]}

        self.assertFalse(result["ok"])
        self.assertLessEqual(
            {
                "blocked_download",
                "css_resource_origin",
                "meta_refresh",
                "network_fetch",
                "resource_origin",
            },
            rules,
        )

    def test_validator_accepts_only_documented_external_resource_hosts(self):
        valid = render_standalone_html_page({"title": "Synthetic"})["html"]
        allowed = valid.replace(
            "</head>",
            "<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=Inter\">"
            "<style>@font-face{src:url(https://fonts.gstatic.com/font.woff2)}"
            ".x{background:url(https://yastatic.net/image.png)}</style></head>",
        ).replace(
            "</body>",
            "<script src=\"//cdn.jsdelivr.net/npm/example.js\"></script>"
            "<img src=\"data:image/png;base64,AA==\">"
            "<video src=\"blob:https://example.invalid/id\"></video></body>",
        )

        result = validate_standalone_html_page(allowed)

        self.assertTrue(result["ok"], result)

    def test_existing_tools_generate_and_validate_html_without_new_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            generated = dl_generate_editor_bundle(
                tmp,
                widget_id="synthetic_report",
                html_page={"title": "Synthetic report", "summary": "Ready", "data": [1, 2, 3]},
            )
            artifact = Path(tmp) / generated["artifact"]["path"]
            validated = dl_validate_editor_runtime_contract(
                project_root=tmp,
                artifact_paths=[generated["artifact"]["path"]],
            )
            project = dl_validate_project(tmp)

            self.assertTrue(generated["ok"], generated)
            self.assertTrue(artifact.is_file())
            self.assertNotIn("html", generated)
            self.assertEqual(generated["publication"]["status"], "local_artifact_only")
            self.assertIsNone(generated["publication"]["public_create_or_upload_method"])
            self.assertTrue(validated["ok"], validated)
            self.assertEqual(validated["items"][0]["kind"], "standalone_html_page")
            self.assertEqual(project["status"], "pass", project)

    def test_html_generation_rejects_chart_inputs_and_unsafe_page_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                dl_generate_editor_bundle(
                    tmp,
                    route="editor_advanced",
                    html_page={"title": "Synthetic"},
                )
            with self.assertRaisesRegex(ValueError, "safe"):
                dl_generate_editor_bundle(
                    tmp,
                    widget_id="../outside",
                    html_page={"title": "Synthetic"},
                )
            with self.assertRaisesRegex(ValueError, "JSON serializable"):
                dl_generate_editor_bundle(
                    tmp,
                    widget_id="invalid_data",
                    html_page={"title": "Synthetic", "data": float("nan")},
                )

    def test_public_skill_recipe_is_bounded_and_upload_stays_fail_closed(self):
        selected = select_authoring_recipe("generate html page")
        bundle = build_recipe_bundle("standalone_html_page")

        self.assertEqual(selected["recipe_id"], "standalone_html_page")
        self.assertTrue(bundle["ok"], bundle)
        self.assertLess(len(bundle["files"]["index.html"].encode("utf-8")), 5 * 1024 * 1024)
        self.assertEqual(
            bundle["constraints"]["publication_status"],
            "blocked_without_documented_public_api",
        )


if __name__ == "__main__":
    unittest.main()
