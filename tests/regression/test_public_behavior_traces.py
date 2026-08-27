from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest

from datalens_dev_mcp.server import JsonRpcServer
from tests.fixtures.public_autonomy_api.fake_api import PublicAutonomyApi
from tests.integration.public_autonomy_jsonrpc_support import public_exchange, public_server


CORPUS_ROOT = Path(__file__).with_name("behavior_traces")
CASES = [
    json.loads(path.read_text(encoding="utf-8"))
    for path in sorted((CORPUS_ROOT / "cases").glob("*.json"))
]


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_sanitized_behavior_trace_through_public_jsonrpc(case: dict) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        api = PublicAutonomyApi(**case["mock_provider_state"])
        with public_server(root, api) as server:
            observed = _run_case(server, root=root, api=api, case=case)

    assert observed["terminal_state"] == case["expected_terminal_state"]
    assert observed["public_call_count"] <= case["call_budget"]
    assert observed["question_count"] == case["expected_questions"]
    assert observed["contract_mode"] == case["expected_contract"]["operation"]
    assert observed["contract_publish"] is case["expected_contract"]["publish"]
    assert observed["browser_policy"] == case["expected_contract"]["browser_policy"]
    assert observed["browser_calls"] == case["expected_browser_calls"]
    if case["expected_discovery"]["status"] == "bound":
        assert case["expected_discovery"]["root_id"] in observed["graph_ids"]
        assert case["expected_discovery"]["dataset_id"] in observed["graph_ids"]
    else:
        assert observed["graph_ids"] == []
    if observed["plan_route"]:
        assert observed["plan_route"] == case["expected_plan"]["technology"]
        assert observed["semantic_target_count"] == case["expected_plan"]["target_count"]
    assert observed["contract_route"] != "ql_explicit"
    assert observed["plan_route"] != "ql_explicit"
    for transition in case["expected_transitions"]:
        assert transition in observed["performed"]
    methods = [method for method, _ in api.calls]
    for expected in case["expected_provider_calls"]:
        assert expected in methods, (case["case_id"], expected, methods)
    assert not (set(case["forbidden_provider_calls"]) & set(methods))
    if observed["terminal_state"] == "COMPLETED":
        assert observed["verify_ok"] is True
        assert observed["highest_proof_level"] == case["expected_proof"]["highest"]


def _run_case(server: JsonRpcServer, *, root: Path, api: PublicAutonomyApi, case: dict) -> dict:
    driver = str(case["context"].get("driver") or "direct")
    semantic_changes = list(case["context"].get("semantic_changes") or [])
    call_count = 0

    def exchange(current: JsonRpcServer, name: str, arguments: dict) -> dict:
        nonlocal call_count
        call_count += 1
        return public_exchange(current, call_count, name, arguments)

    initial_boundary = "plan_ready" if driver != "direct" else "completed"
    started = exchange(
        server,
        "dl_task_start",
        {
            "request": case["request"],
            "project_root": str(root),
            "context": {"semantic_changes": semantic_changes},
            "run_until": initial_boundary,
        },
    )
    if not started["ok"]:
        return _error_observation(started, call_count)
    result = started["payload"]
    task_id = str(result.get("task_id") or "")
    if driver != "direct" and result.get("state") != "BLOCKED":
        task_root = root / ".datalens-mcp" / "tasks" / task_id
        if driver == "restart_after_save":
            saved = exchange(
                server,
                "dl_execute",
                {
                    "task_id": task_id,
                    "plan_hash": result["plan_hash"],
                    "project_root": str(root),
                    "stop_after": "saved",
                },
            )
            if not saved["ok"]:
                return _error_observation(saved, call_count)
            restarted = JsonRpcServer(project_root=str(root))
            resumed = exchange(
                restarted,
                "dl_task_resume",
                {"task_id": task_id, "project_root": str(root), "run_until": "completed"},
            )
            result = resumed["payload"] if resumed["ok"] else {"state": "BLOCKED"}
        elif driver == "corrupt_tail_then_resume":
            with (task_root / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write('{"incomplete":')
            resumed = exchange(
                server,
                "dl_task_resume",
                {"task_id": task_id, "project_root": str(root), "run_until": "completed"},
            )
            result = resumed["payload"] if resumed["ok"] else {"state": "BLOCKED"}
        elif driver in {
            "tamper_plan_then_execute",
            "tamper_style_binding_then_execute",
            "source_drift_then_resume",
            "mutate_chart_then_execute",
        }:
            if driver == "tamper_plan_then_execute":
                _replace_json_value(task_root / "plans" / "plan.json", "plan_hash", "0" * 64)
            elif driver == "tamper_style_binding_then_execute":
                _replace_json_value(task_root / "style-binding.json", "binding_hash", "0" * 64)
            elif driver == "source_drift_then_resume":
                _replace_json_value(task_root / "build-identity.json", "identity_hash", "0" * 64)
            else:
                api.saved_chart["revId"] = "chart-runtime-r9"
                api.saved_chart["data"]["prepare"] = "module.exports={title:'changed outside plan'};"
            continued = exchange(
                server,
                "dl_execute" if "execute" in driver else "dl_task_resume",
                {
                    "task_id": task_id,
                    "project_root": str(root),
                    **(
                        {"plan_hash": result["plan_hash"], "stop_after": "completed"}
                        if "execute" in driver
                        else {"run_until": "completed"}
                    ),
                },
            )
            result = continued["payload"] if continued["ok"] else {"state": "BLOCKED"}
        elif driver == "repeat_status":
            completed = exchange(
                server,
                "dl_execute",
                {
                    "task_id": task_id,
                    "plan_hash": result["plan_hash"],
                    "project_root": str(root),
                    "stop_after": "completed",
                },
            )
            result = completed["payload"] if completed["ok"] else {"state": "BLOCKED"}
            first = exchange(server, "dl_task_status", {"task_id": task_id, "project_root": str(root)})
            second = exchange(server, "dl_task_status", {"task_id": task_id, "project_root": str(root)})
            assert first == second
    question = result.get("question") or (result.get("blocked_by") or {}).get("question")
    task_root = root / ".datalens-mcp" / "tasks" / task_id
    contract = _read_json(task_root / "contract.json")
    graph = _read_json(task_root / "target-graph.json")
    plan = _read_json(task_root / "plans" / "plan.json")
    semantic_plan = _read_json(task_root / "plans" / "semantic-patch-plan.json")
    qa = _read_json(task_root / "evidence" / "qa-receipt.json")
    transitions = [
        str(event.get("transition") or "")
        for event in _read_jsonl(task_root / "events.jsonl")
        if event.get("status") == "success"
    ]
    verify_ok = False
    highest = ""
    if result.get("state") == "COMPLETED":
        verified = exchange(
            server,
            "dl_verify",
            {"task_id": task_id, "project_root": str(root)},
        )
        if verified["ok"]:
            verify_ok = bool(verified["payload"].get("ok"))
            highest = str(verified["payload"].get("highest_proof_level") or "")
    return {
        "terminal_state": str(result.get("state") or "BLOCKED"),
        "public_call_count": call_count,
        "question_count": int(bool(question)),
        "browser_calls": int(qa.get("browser_adapter_calls") or 0),
        "verify_ok": verify_ok,
        "highest_proof_level": highest,
        "contract_mode": str(contract.get("mode") or ""),
        "contract_publish": bool((contract.get("delivery") or {}).get("publish")),
        "browser_policy": str((contract.get("browser_policy") or {}).get("mode") or ""),
        "contract_route": str(contract.get("route") or ""),
        "graph_ids": sorted(
            str(item.get("object_id") or "")
            for item in graph.get("nodes") or []
            if isinstance(item, dict) and item.get("object_id")
        ),
        "plan_route": str(plan.get("route") or ""),
        "semantic_target_count": len(semantic_plan.get("targets") or []),
        "performed": transitions,
    }


def _error_observation(result: dict, call_count: int) -> dict:
    return {
        "terminal_state": "BLOCKED",
        "public_call_count": call_count,
        "question_count": 0,
        "browser_calls": 0,
        "verify_ok": False,
        "highest_proof_level": "",
    }


def _replace_json_value(path: Path, key: str, value: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[key] = value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows
