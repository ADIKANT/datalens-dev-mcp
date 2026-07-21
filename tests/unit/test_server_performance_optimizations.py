import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp.api.scheduler import REQUEST_SCHEDULER, scheduler_status
from datalens_dev_mcp.config import DataLensConfig, use_api_defaults
from datalens_dev_mcp.mcp.heavy_response import project_heavy_tool_response
from datalens_dev_mcp.mcp.response_projection import sanitize_response, stable_json_text
from datalens_dev_mcp.mcp.tools.pipeline import (
    _PROJECT_VALIDATION_CACHE,
    _delivery_stage_snapshot,
    dl_validate_project,
)
from datalens_dev_mcp.mcp.tools.runtime import (
    EDITOR_ARTIFACT_MAX_BYTES,
    _EDITOR_VALIDATION_CACHE,
    dl_validate_editor_runtime_contract,
)
from datalens_dev_mcp.pipeline.artifacts import write_json, write_text
from datalens_dev_mcp.runtime_resources import (
    RESOURCE_OVERRIDE_ENV,
    declared_resource_manifest,
    _package_manifest,
    _package_resource_json,
    _package_resource_text,
    resource_json,
    resource_manifest,
    resource_text,
)
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract


class ServerPerformanceOptimizationTests(unittest.TestCase):
    def setUp(self):
        _PROJECT_VALIDATION_CACHE.clear()
        _EDITOR_VALIDATION_CACHE.clear()

    def test_repeated_project_validation_is_stable_cached_and_invalidated_by_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requirements = root / "requirements"
            requirements.mkdir()
            fixture = requirements / "fixture.sql"
            fixture.write_text("SELECT 1\n", encoding="utf-8")

            first = dl_validate_project(tmp)
            second = dl_validate_project(tmp)
            fixture.write_text("SELECT 2\n", encoding="utf-8")
            third = dl_validate_project(tmp)

        self.assertEqual(first["status"], "fail")
        self.assertEqual(second["status"], "fail")
        self.assertEqual(first["issues"], second["issues"])
        self.assertTrue(any("zero_dashboard_payload_preflight_coverage" in issue for issue in second["issues"]))
        self.assertFalse(first["validation_cache"]["hit"])
        self.assertTrue(second["validation_cache"]["hit"])
        self.assertFalse(third["validation_cache"]["hit"])

    def test_generated_validation_reports_do_not_become_coverage_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = dl_validate_project(tmp)
            _PROJECT_VALIDATION_CACHE.clear()
            second = dl_validate_project(tmp)

        self.assertEqual(first["status"], "fail")
        self.assertEqual(second["status"], "fail")
        self.assertEqual(first["static_sql_lint"]["checked_paths"], [])
        self.assertEqual(second["static_sql_lint"]["checked_paths"], [])
        self.assertEqual(first["dashboard_payload_preflight"]["checked_paths"], [])
        self.assertEqual(second["dashboard_payload_preflight"]["checked_paths"], [])

    def test_stable_artifact_writes_preserve_file_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "artifact.json"
            text_path = Path(tmp) / "artifact.txt"
            write_json(json_path, {"value": 1})
            write_text(text_path, "stable")
            old_ns = 1_000_000_000
            os.utime(json_path, ns=(old_ns, old_ns))
            os.utime(text_path, ns=(old_ns, old_ns))

            write_json(json_path, {"value": 1})
            write_text(text_path, "stable")

            self.assertEqual(json_path.stat().st_mtime_ns, old_ns)
            self.assertEqual(text_path.stat().st_mtime_ns, old_ns)

    def test_packaged_resource_manifest_is_cached_and_defensively_copied(self):
        _package_manifest.cache_clear()

        first = resource_manifest()
        first[0]["path"] = "mutated-by-caller"
        second = resource_manifest()
        cache_info = _package_manifest.cache_info()

        self.assertNotEqual(second[0]["path"], "mutated-by-caller")
        self.assertEqual(cache_info.misses, 1)
        self.assertGreaterEqual(cache_info.hits, 1)

    def test_packaged_text_and_json_are_cached_but_override_is_always_fresh(self):
        _package_resource_text.cache_clear()
        _package_resource_json.cache_clear()
        first_text = resource_text("config/datalens_api_methods.json")
        second_text = resource_text("config/datalens_api_methods.json")
        first_json = resource_json("config/datalens_api_methods.json")
        first_json["methods"] = []
        second_json = resource_json("config/datalens_api_methods.json")

        self.assertEqual(first_text, second_text)
        self.assertGreaterEqual(_package_resource_text.cache_info().hits, 1)
        self.assertGreaterEqual(_package_resource_json.cache_info().hits, 1)
        self.assertTrue(second_json["methods"])

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fixture.txt"
            target.write_text("first", encoding="utf-8")
            with patch.dict(os.environ, {RESOURCE_OVERRIDE_ENV: tmp}):
                self.assertEqual(resource_text("fixture.txt"), "first")
                target.write_text("second", encoding="utf-8")
                self.assertEqual(resource_text("fixture.txt"), "second")
                manifest_path = Path(tmp) / "resource_manifest.json"
                manifest_path.write_text('{"schema_version":"first","resources":[]}', encoding="utf-8")
                self.assertEqual(declared_resource_manifest()["schema_version"], "first")
                manifest_path.write_text('{"schema_version":"second","resources":[]}', encoding="utf-8")
                self.assertEqual(declared_resource_manifest()["schema_version"], "second")

    def test_runtime_cache_metrics_are_aggregate_only(self):
        REQUEST_SCHEDULER.reset_for_tests()
        _package_resource_text.cache_clear()
        resource_text("config/datalens_api_methods.json")
        resource_text("config/datalens_api_methods.json")
        status = scheduler_status()

        self.assertGreaterEqual(status["cache_hits"]["packaged_resource_text"], 1)
        serialized = stable_json_text(status)
        self.assertNotIn("workbook_id", serialized)
        self.assertNotIn("payload", serialized)
        self.assertNotIn("Authorization", serialized)

    def test_delivery_stage_snapshot_drops_duplicate_heavy_evidence(self):
        snapshot = _delivery_stage_snapshot(
            {
                "ok": True,
                "status": "completed",
                "executed": True,
                "completed_action_count": 2,
                "saved_readback_paths": ["saved.json"],
                "actions": [{"payload": "x" * 20_000}],
                "stdout": "y" * 20_000,
                "publish_results": [{"result": "z" * 20_000}],
            }
        )

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["completed_action_count"], 2)
        self.assertEqual(snapshot["saved_readback_paths"], ["saved.json"])
        self.assertNotIn("actions", snapshot)
        self.assertNotIn("stdout", snapshot)
        self.assertNotIn("publish_results", snapshot)

    def test_response_sanitization_reads_environment_secrets_once_per_object(self):
        secret = "fixture-secret-value"
        payload = {"rows": [{"value": f"prefix {secret} suffix"} for _ in range(100)]}

        with patch(
            "datalens_dev_mcp.serialization.secret_values_from_mapping",
            return_value=[secret],
        ) as env_secrets:
            sanitized = sanitize_response(payload)

        self.assertEqual(env_secrets.call_count, 1)
        self.assertTrue(all(row["value"] == "prefix <redacted> suffix" for row in sanitized["rows"]))

    def test_editor_validation_cache_and_artifact_path_mode_preserve_quality(self):
        payload = {"prepare": "module.exports = {render: () => ''};"}
        first = dl_validate_editor_runtime_contract(sections=payload)
        second = dl_validate_editor_runtime_contract(sections=payload)

        self.assertFalse(first["validation_cache"]["hit"])
        self.assertTrue(second["validation_cache"]["hit"])
        self.assertEqual(first["ok"], second["ok"])
        self.assertEqual(first["findings"], second["findings"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "editor.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            result = dl_validate_editor_runtime_contract(
                project_root=tmp,
                artifact_paths=["editor.json"],
            )

            self.assertEqual(result["mode"], "artifact_paths")
            self.assertEqual(result["summary"]["artifacts"], 1)
            self.assertTrue(Path(result["artifact"]["path"]).is_file())
            self.assertTrue(result["items"][0]["validation_cache"]["hit"])

    def test_editor_validation_cache_is_shared_with_safe_apply_preflight(self):
        payload = {"prepare": "module.exports = {render: () => ''};"}
        planned = validate_editor_runtime_contract(payload, source="existing_update[0]")
        safe_apply = validate_editor_runtime_contract(payload, source="safe_apply.action[0]")

        self.assertFalse(planned["validation_cache"]["hit"])
        self.assertTrue(safe_apply["validation_cache"]["hit"])
        self.assertEqual(
            [{key: value for key, value in finding.items() if key != "source"} for finding in planned["findings"]],
            [{key: value for key, value in finding.items() if key != "source"} for finding in safe_apply["findings"]],
        )
        self.assertTrue(
            all(finding["source"] == "safe_apply.action[0]" for finding in safe_apply["findings"])
        )

    def test_editor_validation_cache_invalidates_when_override_rules_change(self):
        contract_text = resource_text("validators/editor_runtime_contract.json")
        allowlist_text = resource_text("schemas/datalens-api/editor-runtime-allowlist.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract_path = root / "validators" / "editor_runtime_contract.json"
            allowlist_path = root / "schemas" / "datalens-api" / "editor-runtime-allowlist.json"
            contract_path.parent.mkdir(parents=True)
            allowlist_path.parent.mkdir(parents=True)
            contract_path.write_text(contract_text, encoding="utf-8")
            allowlist_path.write_text(allowlist_text, encoding="utf-8")
            with patch.dict(os.environ, {RESOURCE_OVERRIDE_ENV: tmp}):
                first = validate_editor_runtime_contract({"prepare": "module.exports = {};"})
                second = validate_editor_runtime_contract({"prepare": "module.exports = {};"})
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                contract["rule_version"] = str(contract["rule_version"]) + ".changed"
                contract_path.write_text(json.dumps(contract), encoding="utf-8")
                changed = validate_editor_runtime_contract({"prepare": "module.exports = {};"})

        self.assertFalse(first["validation_cache"]["hit"])
        self.assertTrue(second["validation_cache"]["hit"])
        self.assertFalse(changed["validation_cache"]["hit"])
        self.assertNotEqual(first["validation_cache"]["rule_token"], changed["validation_cache"]["rule_token"])

    def test_editor_artifact_paths_reject_escape_format_and_size_before_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "project"
            root.mkdir()
            outside = base / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            unsupported = root / "editor.txt"
            unsupported.write_text("{}", encoding="utf-8")
            oversized = root / "large.json"
            oversized.write_text('{"value":"' + ("x" * EDITOR_ARTIFACT_MAX_BYTES) + '"}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "escapes project_root"):
                dl_validate_editor_runtime_contract(
                    project_root=str(root),
                    artifact_paths=[str(outside)],
                )
            with self.assertRaisesRegex(ValueError, "must be a JSON file"):
                dl_validate_editor_runtime_contract(
                    project_root=str(root),
                    artifact_paths=["editor.txt"],
                )
            with self.assertRaisesRegex(ValueError, "exceeds"):
                dl_validate_editor_runtime_contract(
                    project_root=str(root),
                    artifact_paths=["large.json"],
                )

    def test_heavy_tool_defaults_to_bounded_summary_and_stable_canonical_artifact(self):
        payload = {
            "ok": True,
            "status": "completed",
            "actions": [{"method": "updateDashboard", "payload": "x" * 50_000} for _ in range(4)],
            "stdout": "y" * 50_000,
            "request_intent": {"request_source": "current_user_request", "text": "z" * 50_000},
        }
        with tempfile.TemporaryDirectory() as tmp:
            first = project_heavy_tool_response(
                "dl_create_safe_apply_plan",
                payload,
                response_mode="summary",
                inline_char_budget=15_000,
                project_root=tmp,
            )
            artifact_path = Path(first["canonical_artifact"]["path"])
            artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            old_ns = 1_000_000_000
            os.utime(artifact_path, ns=(old_ns, old_ns))
            second = project_heavy_tool_response(
                "dl_create_safe_apply_plan",
                payload,
                response_mode="summary",
                inline_char_budget=15_000,
                project_root=tmp,
            )

            self.assertLessEqual(len(stable_json_text(first)), 15_000)
            self.assertEqual(artifact_payload, sanitize_response(payload))
            self.assertEqual(first["canonical_artifact"]["sha256"], second["canonical_artifact"]["sha256"])
            self.assertEqual(artifact_path.stat().st_mtime_ns, old_ns)

    def test_api_default_precedence_is_env_then_local_then_builtin(self):
        with patch.dict(os.environ, {}, clear=True):
            builtin = DataLensConfig.from_env()
            with use_api_defaults(
                {
                    "request_interval_sec": 1.25,
                    "max_read_concurrency": 2,
                    "read_transient_retries": 1,
                }
            ):
                local = DataLensConfig.from_env()
                with patch.dict(
                    os.environ,
                    {
                        "DATALENS_REQUEST_INTERVAL_SEC": "1.5",
                        "DATALENS_MAX_READ_CONCURRENCY": "3",
                        "DATALENS_READ_TRANSIENT_RETRIES": "0",
                    },
                ):
                    explicit = DataLensConfig.from_env()

        self.assertEqual(builtin.request_interval_sec, 1.05)
        self.assertEqual(local.request_interval_sec, 1.25)
        self.assertEqual(local.max_read_concurrency, 2)
        self.assertEqual(local.read_transient_retries, 1)
        self.assertEqual(explicit.request_interval_sec, 1.5)
        self.assertEqual(explicit.max_read_concurrency, 3)
        self.assertEqual(explicit.read_transient_retries, 0)

        with self.assertRaisesRegex(ValueError, "max_read_concurrency"):
            DataLensConfig(max_read_concurrency=0)
        with self.assertRaisesRegex(ValueError, "max_read_concurrency"):
            DataLensConfig(max_read_concurrency=4)
        with self.assertRaisesRegex(ValueError, "read_transient_retries"):
            DataLensConfig(read_transient_retries=-1)
        with self.assertRaisesRegex(ValueError, "read_transient_retries"):
            DataLensConfig(read_transient_retries=3)


if __name__ == "__main__":
    unittest.main()
