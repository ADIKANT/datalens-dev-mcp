import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "safe-apply-plan.schema.json"


def load_schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def full_saved_dashboard_readback() -> dict:
    return {
        "branch": "saved",
        "dashboard": {
            "entry": {
                "entryId": "dash_1",
                "revId": "rev_saved",
                "savedId": "saved_1",
                "data": {"counter": 1, "salt": "s", "schemeVersion": 8, "tabs": [], "settings": {}},
                "meta": {},
            }
        },
    }


class SafeApplyPlanSchemaTests(unittest.TestCase):
    def test_update_plan_schema_requires_fresh_read_readback_payload_owner_revision_and_lock(self):
        validator = load_schema_validator()
        valid = self._valid_update_plan()

        self.assertFalse(list(validator.iter_errors(valid)))

        required_paths = [
            ("actions", 0, "fresh_read_contract"),
            ("actions", 0, "readback_contract"),
            ("actions", 0, "payload_contract"),
            ("actions", 0, "source_owner"),
            ("actions", 0, "revision_guard"),
            ("target_lock",),
        ]
        for path in required_paths:
            with self.subTest(path=path):
                candidate = copy.deepcopy(valid)
                parent = candidate
                for key in path[:-1]:
                    parent = parent[key]
                parent.pop(path[-1])
                errors = list(validator.iter_errors(candidate))
                self.assertTrue(errors, path)

    def test_publish_schema_accepts_saved_branch_and_rejects_published_or_unknown_branch(self):
        validator = load_schema_validator()
        valid = self._valid_publish_plan()

        self.assertFalse(list(validator.iter_errors(valid)))

        for bad_branch in ("published", "unknown"):
            candidate = copy.deepcopy(valid)
            action = candidate["actions"][0]
            action["source_branch"] = bad_branch
            action["fresh_read_contract"]["branch"] = bad_branch
            action["branch_semantics"]["source_branch"] = bad_branch
            errors = list(validator.iter_errors(candidate))
            self.assertTrue(errors, bad_branch)

    def test_schema_valid_but_api_payload_invalid_is_rejected_by_python_preflight(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        validator = load_schema_validator()
        lock = create_target_lock(
            "fix chart_1",
            target_source="manual",
            target_workbook_id="workbook_1",
            target_chart_id="chart_1",
        )
        plan = create_safe_apply_plan(
            project_root="/tmp/schema-valid-preflight-invalid",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "mode": "save",
                    "target_lock_hash": lock.lock_hash,
                    "expected_rev_id": "rev_1",
                    "payload": {"mode": "save", "bad": "missing entry"},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_1", "branch": "saved"},
                    "generator": "unit_test",
                    "source_path": "tests/unit/test_safe_apply_plan_schema.py",
                }
            ],
        )
        plan["target_lock"] = lock.to_dict()

        self.assertFalse(list(validator.iter_errors(plan)))
        preflight = validate_safe_apply_plan(plan)
        self.assertFalse(preflight.ok)
        self.assertIn("missing required field `entry`", "\n".join(preflight.issues))

    def _valid_update_plan(self) -> dict:
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        lock = create_target_lock(
            "fix chart_1",
            target_source="manual",
            target_workbook_id="workbook_1",
            target_chart_id="chart_1",
        )
        plan = create_safe_apply_plan(
            project_root="/tmp/schema-valid-update",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "mode": "save",
                    "target_lock_hash": lock.lock_hash,
                    "payload": {"mode": "save", "entry": {"entryId": "chart_1", "revId": "rev_1"}},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_1", "branch": "saved"},
                    "generator": "unit_test",
                    "source_path": "tests/unit/test_safe_apply_plan_schema.py",
                }
            ],
        )
        plan["target_lock"] = lock.to_dict()
        return plan

    def _valid_publish_plan(self) -> dict:
        from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved_path = root / "artifacts" / "readback" / "dashboard.saved.latest.json"
            saved_path.parent.mkdir(parents=True)
            saved_path.write_text(json.dumps(full_saved_dashboard_readback()), encoding="utf-8")
            plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="dashboard",
                object_type="dashboard",
                object_id="dash_1",
                saved_readback_path=str(saved_path),
                approved=True,
            )
            lock = create_target_lock(
                "publish dash_1",
                target_source="manual",
                target_workbook_id="workbook_1",
                target_dashboard_id="dash_1",
            )
            plan["target_lock"] = lock.to_dict()
            for action in plan["actions"]:
                action["target_lock_hash"] = lock.lock_hash
            return plan


if __name__ == "__main__":
    unittest.main()
