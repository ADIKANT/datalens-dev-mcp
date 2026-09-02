from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import datalens_dev_mcp.api.client as api_client_module
import datalens_dev_mcp.pipeline.target_discovery as target_discovery_module
from datalens_dev_mcp.server import JsonRpcServer
from tests.fixtures.public_autonomy_api.fake_api import PublicAutonomyApi


def public_call(server: JsonRpcServer, request_id: int, name: str, arguments: dict) -> dict:
    response = public_exchange(server, request_id, name, arguments)
    assert response["ok"] is True, response
    return response["payload"]


def public_exchange(server: JsonRpcServer, request_id: int, name: str, arguments: dict) -> dict:
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None and "error" not in response, response
    result = response["result"]
    return {
        "ok": result["isError"] is False,
        "payload": json.loads(result["content"][0]["text"]),
    }


def public_confirmation_arguments(
    result: dict,
    *,
    run_until: str = "completed",
) -> dict:
    action = result.get("confirmation_action") or (result.get("execution_brief") or {}).get("confirmation_action")
    assert action and action["tool"] == "dl_task_resume", result
    arguments = dict(action["fixed_arguments"])
    arguments["run_until"] = run_until
    arguments[action["user_confirmation_field"]] = "I explicitly confirm the exact unchanged current plan."
    return arguments


def public_task_root(task_id: str) -> Path:
    storage_root = str(os.environ.get("DATALENS_MCP_TASKS_DIR") or "").strip()
    assert storage_root
    return Path(storage_root) / task_id


@contextmanager
def public_server(root: Path, api: PublicAutonomyApi) -> Iterator[JsonRpcServer]:
    with tempfile.TemporaryDirectory(prefix="datalens-test-state-", dir=root.parent) as state_tmp:
        storage_root = Path(state_tmp) / "tasks"
        with (
            patch.dict(os.environ, {"DATALENS_MCP_TASKS_DIR": str(storage_root)}, clear=False),
            patch.object(target_discovery_module, "DataLensApiClient", return_value=api),
            patch.object(api_client_module, "DataLensApiClient", return_value=api),
        ):
            yield JsonRpcServer(project_root=str(root))


def semantic_context(*, acceptance: list[dict] | None = None) -> dict:
    return {
        "acceptance": list(acceptance or []),
        "semantic_changes": [
            {
                "target_id": "chart_demo",
                "slot_id": "series_label",
                "dataset_id": "dataset_demo",
                "field_guid": "guid_value",
                "change_kind": "filter_change",
                "value": {"operator": "GT", "value": 0},
            }
        ],
    }
