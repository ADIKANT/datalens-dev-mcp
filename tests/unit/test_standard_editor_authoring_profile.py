import json
import hashlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp.editor.authoring_profiles import (
    _packaged_template_set_identity,
    _project_template_set_identity,
    apply_authoring_profile_bundle,
    authoring_profile_route_decision,
    authoring_profile_template_set_identity,
    load_project_authoring_profile_bundle,
    resolve_authoring_profile,
)
from datalens_dev_mcp.mcp.tools.pipeline import dl_generate_editor_bundle
from datalens_dev_mcp.mcp.tools.runtime import dl_validate_editor_runtime_contract
from datalens_dev_mcp.pipeline.project_live_workflows import run_project_live_dry_run
from datalens_dev_mcp.runtime_resources import RESOURCE_OVERRIDE_ENV, resource_json


PROFILE_ID = "standard_editor_v1"
TEMPLATE_SET_SHA256 = "f1b2848350bc9dc0119149a50fdeb41bbd79faf0adee376f9ca5ab4f79bb4ed9"


class StandardEditorAuthoringProfileTests(unittest.TestCase):
    def test_project_local_profile_rejects_descriptor_path_escape_before_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "project"
            root.mkdir()
            outside = base / "outside-profile.json"
            outside.write_text("{}", encoding="utf-8")
            (root / ".datalens-mcp.json").write_text(
                json.dumps(
                    {
                        "authoring_profile": {
                            "id": "escaped_profile",
                            "descriptor_path": "../outside-profile.json",
                            "descriptor_sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                        }
                    }
                ),
                encoding="utf-8",
            )

            profile = resolve_authoring_profile(
                project_root=root,
                requested_profile="escaped_profile",
            )

        self.assertFalse(profile["ok"])
        self.assertEqual(
            profile["error"]["category"],
            "authoring_profile_descriptor_unavailable",
        )
        self.assertIn("escapes project_root", profile["error"]["message"])

    def test_hash_bound_project_local_profile_loads_exact_registered_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template_dir = root / "profiles" / "fleet" / "line"
            template_dir.mkdir(parents=True)
            tabs = {
                "meta.json": '{"links": {}}\n',
                "params.js": "module.exports = {};\n",
                "sources.js": "module.exports = {};\n",
                "controls.js": "module.exports = {};\n",
                "prepare.js": "module.exports = {prepare: __TITLE_JSON__};\n",
            }
            for name, text in tabs.items():
                (template_dir / name).write_text(text, encoding="utf-8")
            registry_path = root / "profiles" / "fleet" / "families.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "families": {
                            "line_chart": {
                                "route": "editor_advanced",
                                "template_dir": "profiles/fleet/line",
                                "required_files": list(tabs),
                                "variant": "fleet_line",
                                "source_binding": "template_complete",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            identity = _project_template_set_identity(
                root=root,
                family_registry="profiles/fleet/families.json",
                shared_assets=[],
            )
            descriptor_path = root / "profiles" / "fleet" / "profile.json"
            descriptor_path.write_text(
                json.dumps(
                    {
                        "schema_version": "2026-07-23.project_authoring_profile.v1",
                        "id": "project_fleet_v1",
                        "route_policy": "project_registered_editor_family",
                        "template_policy": "exact_registered_asset",
                        "fallback_policy": "block",
                        "allowed_routes": ["editor_advanced"],
                        "family_registry": "profiles/fleet/families.json",
                        "template_set_sha256": identity["sha256"],
                        "style_contract": {
                            "semantic_roles": ["success", "failure", "neutral", "comparison", "track"],
                            "track": "lighter_than_comparison",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            descriptor_sha256 = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
            (root / ".datalens-mcp.json").write_text(
                json.dumps(
                    {
                        "authoring_profile": {
                            "id": "project_fleet_v1",
                            "descriptor_path": "profiles/fleet/profile.json",
                            "descriptor_sha256": descriptor_sha256,
                        }
                    }
                ),
                encoding="utf-8",
            )

            profile = resolve_authoring_profile(
                project_root=root,
                requested_profile="project_fleet_v1",
            )
            route = authoring_profile_route_decision(profile=profile, family="line_chart")
            bundle = load_project_authoring_profile_bundle(
                profile=profile,
                route_decision=route,
                widget_id="fleet_growth",
                title="Fleet growth",
            )
            bound = apply_authoring_profile_bundle(
                bundle=bundle,
                profile=profile,
                route_decision=route,
            )

        self.assertTrue(profile["ok"], profile)
        self.assertEqual(profile["source_kind"], "project_local")
        self.assertEqual(profile["descriptor_sha256"], descriptor_sha256)
        self.assertTrue(route["ok"], route)
        self.assertEqual(bundle["tabs"]["prepare.js"], 'module.exports = {prepare: "Fleet growth"};\n')
        self.assertEqual(
            bound["template_provenance"]["profile_descriptor_sha256"],
            descriptor_sha256,
        )

    def test_profile_alias_selects_every_registered_family_and_blocks_route_drift(self):
        profile = resolve_authoring_profile(requested_profile="standard_js")
        registry = resource_json("templates/datalens/standard_chart_templates.json")

        self.assertTrue(profile["active"])
        self.assertEqual(profile["id"], PROFILE_ID)
        self.assertEqual(profile["registered_family_count"], 38)
        self.assertEqual(profile["template_asset_count"], 74)
        self.assertEqual(profile["template_set_sha256"], TEMPLATE_SET_SHA256)
        for family, spec in registry["families"].items():
            with self.subTest(family=family):
                selected = authoring_profile_route_decision(profile=profile, family=family)
                self.assertTrue(selected["ok"])
                self.assertEqual(selected["route"], spec["route"])
                self.assertEqual(selected["source_template"], spec["template_dir"])

        conflict = authoring_profile_route_decision(
            profile=profile,
            family="line_chart",
            explicit_route="wizard_native",
        )
        unsupported = authoring_profile_route_decision(profile=profile, family="unregistered_map")
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["error"]["category"], "authoring_profile_route_conflict")
        self.assertFalse(unsupported["ok"])
        self.assertEqual(unsupported["error"]["category"], "profile_family_requires_review")

    def test_project_profile_reuses_registered_template_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "artifacts").mkdir()
            (root / ".datalens-mcp.json").write_text(
                json.dumps({"authoring_profile": {"id": PROFILE_ID}}),
                encoding="utf-8",
            )
            brief = {
                "dashboard_name": "Synthetic time series",
                "dashboard_type": "operational",
                "audience": ["operator"],
                "requirements": [{"text": "Show a trend"}],
                "data_contract": {"fields": []},
                "chart_decisions": [
                    {
                        "decision_id": "trend",
                        "title": "Synthetic chart title",
                        "family": "line_chart",
                        "route": "wizard_native",
                        "renderer_visual_spec": {},
                        "chart_decision_record": {
                            "selected_family": "line_chart",
                            "selected_route": "wizard_native",
                            "renderer_visual_spec": {},
                        },
                    }
                ],
            }
            (root / "artifacts" / "dashboard_brief.json").write_text(json.dumps(brief), encoding="utf-8")

            first = dl_generate_editor_bundle(
                project_root=str(root),
                widget_id="trend",
                dataset_alias="dataset",
                columns=["bucket", "value"],
            )
            second = dl_generate_editor_bundle(
                project_root=str(root),
                widget_id="trend",
                dataset_alias="dataset",
                columns=["bucket", "value"],
            )

        self.assertEqual(first["route"], "editor_advanced")
        self.assertEqual(first["display_title"], "Synthetic chart title")
        self.assertEqual(first["source_template"], "templates/datalens/advanced_editor/time_series")
        self.assertTrue(first["authoring_profile"]["exact_template_reused"])
        self.assertEqual(first["authoring_profile"]["registered_family_count"], 38)
        provenance = first["template_provenance"]
        self.assertEqual(provenance["policy"], "exact_registered_asset")
        self.assertFalse(provenance["approximate_fallback_used"])
        self.assertEqual(provenance["profile_template_set_sha256"], TEMPLATE_SET_SHA256)
        self.assertNotIn("canonical_runtime_asset", provenance)
        self.assertEqual(
            provenance["template_asset_sha256"],
            second["template_provenance"]["template_asset_sha256"],
        )
        self.assertEqual(
            provenance["compiled_tabs_sha256"],
            second["template_provenance"]["compiled_tabs_sha256"],
        )

    def test_template_set_identity_is_cached_for_packaged_assets(self):
        with patch.dict(os.environ, {RESOURCE_OVERRIDE_ENV: ""}, clear=False):
            _packaged_template_set_identity.cache_clear()
            first = authoring_profile_template_set_identity(
                "templates/datalens/standard_chart_templates.json"
            )
            second = authoring_profile_template_set_identity(
                "templates/datalens/standard_chart_templates.json"
            )
            cache = _packaged_template_set_identity.cache_info()

        self.assertEqual(first, second)
        self.assertEqual(first["sha256"], TEMPLATE_SET_SHA256)
        self.assertEqual(cache.misses, 1)
        self.assertEqual(cache.hits, 1)

    def test_changed_template_set_fails_closed(self):
        with patch(
            "datalens_dev_mcp.editor.authoring_profiles.authoring_profile_template_set_identity",
            return_value={"sha256": "0" * 64, "asset_count": 74, "family_count": 38},
        ):
            profile = resolve_authoring_profile(requested_profile=PROFILE_ID)

        self.assertFalse(profile["ok"])
        self.assertEqual(profile["status"], "blocked_authoring_profile")
        self.assertEqual(
            profile["error"]["category"],
            "authoring_profile_template_set_hash_mismatch",
        )

    def test_validator_accepts_javascript_paths_directories_comparisons_and_tooltips(self):
        javascript = (
            "const value = index < numericValues.length ? numericValues[index] : total > 0 ? 1 : 0;\n"
            "const chart = {tooltip: {enabled: true}};\n"
            "module.exports = {value, chart};\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            widget = root / "widgets" / "trend"
            widget.mkdir(parents=True)
            (widget / "prepare.js").write_text(javascript, encoding="utf-8")
            (widget / "meta.json").write_text('{"links": {}}', encoding="utf-8")

            direct = dl_validate_editor_runtime_contract(
                project_root=str(root),
                artifact_paths=["widgets/trend/prepare.js"],
            )
            directory = dl_validate_editor_runtime_contract(
                project_root=str(root),
                artifact_paths=["widgets/trend"],
            )

        direct_rules = {item["rule"] for item in direct.get("findings_preview") or []}
        directory_rules = {item["rule"] for item in directory.get("findings_preview") or []}
        self.assertTrue(direct["ok"])
        self.assertTrue(directory["ok"])
        self.assertNotIn("unsupported_html_tag", direct_rules | directory_rules)
        self.assertNotIn("inline_hint_ui", direct_rules | directory_rules)

    def test_long_project_command_returns_execution_id_and_polls_without_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            (root / "scripts" / "dry.py").write_text(
                "from pathlib import Path\n"
                "import json, time\n"
                "with Path('reports/starts.txt').open('a') as handle: handle.write('start\\n')\n"
                "time.sleep(0.15)\n"
                "json.dump({'branch_status': 'dry_run', 'changed_object_counts': {'charts': 0}}, "
                "open('reports/dry.json', 'w'))\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
                "project_name": "async_test",
                "workbook_id": "workbook_1",
                "dashboard_ids": ["dashboard_1"],
                "workflows": [
                    {
                        "name": "dry",
                        "may_execute_command": True,
                        "dry_run": {
                            "command": [sys.executable, "scripts/dry.py"],
                            "summary_path": "reports/dry.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")

            started = time.monotonic()
            first = run_project_live_dry_run(
                root,
                workflow_name="dry",
                execute_now=True,
                timeout_sec=120,
                wait_for_completion_sec=0,
            )
            launch_duration = time.monotonic() - started
            attached = run_project_live_dry_run(
                root,
                workflow_name="dry",
                execute_now=True,
                timeout_sec=120,
                wait_for_completion_sec=0,
            )
            from datalens_dev_mcp.pipeline.project_live_workflows import _PROJECT_LIVE_JOBS

            detached_job = _PROJECT_LIVE_JOBS.pop(first["execution_id"], None)
            resumed = run_project_live_dry_run(
                root,
                execution_id=first["execution_id"],
                wait_for_completion_sec=0,
            )
            final = first
            for _ in range(80):
                if final["status"] != "running":
                    break
                time.sleep(0.025)
                final = run_project_live_dry_run(root, execution_id=first["execution_id"])
            replay = run_project_live_dry_run(root, execution_id=first["execution_id"])
            if detached_job:
                detached_job["process"].wait(timeout=1)
            starts = (root / "reports" / "starts.txt").read_text(encoding="utf-8").splitlines()

        self.assertLess(launch_duration, 1.0)
        self.assertEqual(first["status"], "running")
        self.assertEqual(attached["execution_id"], first["execution_id"])
        self.assertTrue(attached["execution"]["attached_to_existing"])
        self.assertEqual(resumed["status"], "running")
        self.assertTrue(resumed["execution"]["resumed_from_state"])
        self.assertGreaterEqual(first["poll_after_sec"], 5)
        self.assertEqual(final["status"], "completed")
        self.assertTrue(final["ok"])
        self.assertEqual(replay["status"], "completed")
        self.assertTrue(replay["execution"]["resumed_from_state"])
        self.assertEqual(starts, ["start"])


if __name__ == "__main__":
    unittest.main()
