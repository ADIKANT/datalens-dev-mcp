import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.api.methods import get_method_schema, openapi_lock_summary
from datalens_dev_mcp.api.request_compiler import compile_method_request
from datalens_dev_mcp.knowledge.reference import build_reference_response
from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan, load_wizard_template_registry
from datalens_dev_mcp.runtime_resources import declared_resource_manifest, resource_manifest
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_RESOURCE_FILES = [
    REPO_ROOT / "src/datalens_dev_mcp/api/methods.py",
    REPO_ROOT / "src/datalens_dev_mcp/api/request_compiler.py",
    REPO_ROOT / "src/datalens_dev_mcp/validators/advanced_editor_validator.py",
    REPO_ROOT / "src/datalens_dev_mcp/pipeline/wizard_templates.py",
    REPO_ROOT / "src/datalens_dev_mcp/pipeline/chart_param_matrix.py",
    REPO_ROOT / "src/datalens_dev_mcp/pipeline/requirements_workspace.py",
    REPO_ROOT / "src/datalens_dev_mcp/editor/standard_templates.py",
    REPO_ROOT / "src/datalens_dev_mcp/knowledge/reference.py",
    REPO_ROOT / "src/datalens_dev_mcp/knowledge/recipes.py",
    REPO_ROOT / "src/datalens_dev_mcp/knowledge/formulas.py",
]


class PortableRuntimeResourceTests(unittest.TestCase):
    def test_runtime_resource_manifest_is_deterministic_and_complete(self):
        declared = declared_resource_manifest()
        current = resource_manifest()
        paths = {item["path"] for item in current}

        self.assertEqual(declared["resources"], current)
        self.assertEqual(declared["resource_count"], len(current))
        self.assertNotIn("config/datalens_mcp.local.json", paths)
        self.assertNotIn("schemas/datalens-api/selected-openapi-schema-refs.json", paths)
        for required in {
            "config/datalens_api_methods.json",
            "schemas/datalens-api/openapi.lock.json",
            "schemas/datalens-api/closed-schema-bundle.json",
            "schemas/datalens-api/operation-schema-index.json",
            "validators/editor_runtime_contract.json",
            "templates/datalens/wizard/wizard_template_registry.json",
            "templates/datalens/recipes/recipe-registry.json",
            "schemas/datalens-knowledge/page-registry.json",
            "schemas/datalens-knowledge/chunk-registry.jsonl",
            "schemas/datalens-knowledge/rule-cards.jsonl",
            "schemas/datalens-knowledge/formula-registry.json",
            "schemas/datalens-knowledge/visualization-registry.json",
            "schemas/datalens-knowledge/error-registry.json",
            "schemas/datalens-knowledge/capability-matrix.json",
            "schemas/datalens-knowledge/route-capability-matrix.json",
            "schemas/datalens-knowledge/editor-visualization-contracts.json",
        }:
            self.assertIn(required, paths)

    def test_packaged_resource_lookups_cover_runtime_contracts(self):
        schema = get_method_schema("getDashboard")
        compiled = compile_method_request(
            "updateDashboard",
            {"entry": {"entryId": "dash_1", "data": {"tabs": []}}},
            object_type="dashboard",
            operation="update",
            object_id="dash_1",
        )
        runtime = validate_editor_runtime_contract(
            {"javascript": "module.exports = {render: Editor.wrapFn({args: [], fn: function() { return Editor.generateHtml(''); }} )};"},
            source="portable-runtime-test",
            allow_unknown_warnings=True,
        )
        wizard = load_wizard_template_registry()
        wizard_plan = build_wizard_payload_plan()
        reference = build_reference_response(mode="recipe", name="markdown", max_chars=4000)

        self.assertEqual(schema["mode"], "readonly")
        self.assertEqual(openapi_lock_summary()["required_api_header_version"], "2")
        self.assertIn("schema_ref", compiled)
        self.assertIn("rule_version", runtime)
        self.assertIn("templates", wizard)
        self.assertTrue(wizard_plan["ok"])
        self.assertTrue(reference["ok"])
        self.assertGreaterEqual(reference["result_count"], 1)

    def test_runtime_resource_files_do_not_use_repo_relative_config_schema_template_roots(self):
        forbidden = ("Path(__file__).resolve().parents[3]", "Path(__file__).resolve().parents[2]")
        for path in RUNTIME_RESOURCE_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertFalse(any(pattern in text for pattern in forbidden), path)

    def test_source_runtime_smoke_passes_from_arbitrary_cwd(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "smoke_portable_runtime.py")],
            cwd=tempfile.gettempdir(),
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(payload["ok"], payload)


if __name__ == "__main__":
    unittest.main()
