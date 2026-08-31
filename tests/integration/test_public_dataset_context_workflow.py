from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import datalens_dev_mcp.pipeline.task_planning_stage_services as planning_services
from datalens_dev_mcp.mcp.task_resources import read_task_resource, task_resource_uri
from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService
from datalens_dev_mcp.pipeline.task_dataset_context_service import TaskDatasetContextService
from tests.unit.test_target_discovery import DiscoveryClient


class PlanningClient(DiscoveryClient):
    def rpc_readonly(self, method: str, payload: dict) -> dict:
        if method == "getDatasetData":
            self.calls.append((method, payload))
            return {
                "schema": [
                    {"guid": "guid_date", "name": "event_date", "type": "date"},
                    {"guid": "guid_value", "name": "value", "type": "float"},
                ],
                "rows": [["2026-08-27", 42.0]],
            }
        response = super().rpc_readonly(method, payload)
        if method == "getEditorChart":
            response["result"]["chart"]["data"]["prepare"] = (
                "const title='/* datalens-slot:series_label:text:start */Old"
                "/* datalens-slot:series_label:end */'; module.exports={title};"
            )
        return response


def test_dashboard_to_dataset_context_to_public_plan_uses_internal_service() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = PlanningClient()
        discovery = TargetDiscoveryService(client)

        def context_factory(journal, contract):
            return TaskDatasetContextService(journal, contract, client=client)

        with (
            patch.object(tasks, "TargetDiscoveryService", return_value=discovery),
            patch.object(planning_services, "TaskDatasetContextService", side_effect=context_factory),
        ):
            result = tasks.dl_task_start(
                "Update dashboard https://datalens.example/dash_demo and save it",
                project_root=tmp,
                context={
                    "semantic_changes": [
                        {"target_id": "chart_demo", "slot_id": "series_label", "value": "Revenue"}
                    ]
                },
                run_until="plan_ready",
            )
        journal = tasks.ProjectJournal(tmp, result["task_id"])
        profile_resource = read_task_resource(
            task_resource_uri(result["task_id"], "data/context-profile.json"),
            project_root=tmp,
        )
        profile = json.loads(profile_resource["text"])
        plan = tasks.read_json(journal.root / "plans" / "plan.json", {})
        inspection = tasks.dl_inspect(project_root=tmp, task_id=result["task_id"])
        raw_dir_present = Path(journal.root / "data" / "raw").is_dir()
    assert result["state"] == "PLAN_VALIDATED"
    assert result["plan_hash"] == plan["plan_hash"]
    assert plan["dataset_context_profile_hash"] == profile["profile_hash"]
    assert plan["safe_apply_action_count"] == 1
    assert profile["dataset_data_semantics"] == "unknown_experimental"
    assert profile["raw_rows_inline"] is False
    assert inspection["data_context"]["dataset_context_profile_hash"] == profile["profile_hash"]
    assert inspection["data_context"]["raw_rows_inline"] is False
    assert [method for method, _ in client.calls].count("getDatasetData") == 0
    assert all(not method.startswith(("create", "update", "delete")) for method, _ in client.calls)
    assert not raw_dir_present
