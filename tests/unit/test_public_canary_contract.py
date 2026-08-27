from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.public_stdio_client import PublicStdioClient
from scripts.run_public_autonomy_canary import PUBLIC_TOOLS, _semantic_context

ROOT = Path(__file__).resolve().parents[2]


def test_canary_runner_has_no_internal_server_imports_or_legacy_surface() -> None:
    source = (ROOT / "scripts" / "run_public_autonomy_canary.py").read_text(encoding="utf-8")
    forbidden = (
        "datalens_dev_mcp.api",
        "datalens_dev_mcp.pipeline",
        "datalens_dev_mcp.editor",
        "WorkflowEngine",
        "ProjectJournal",
        "legacy-v1",
    )
    assert not any(item in source for item in forbidden)
    assert "PublicStdioClient" in source
    assert '"dl_task_start"' in source
    assert '"dl_execute"' in source
    assert '"dl_task_resume"' in source
    assert '"dl_verify"' in source


def test_canary_surface_and_semantic_change_are_exact() -> None:
    assert len(PUBLIC_TOOLS) == 8
    context = _semantic_context("controlled_dashboard", "tab_main", "bounded marker")
    change = context["semantic_changes"][0]
    assert change == {
        "target_id": "controlled_dashboard",
        "tab": "tab_main",
        "anchor": {"kind": "json_pointer", "pointer": "/data/supportDescription"},
        "value": "bounded marker",
    }


def test_success_receipt_contract_requires_installed_public_proof() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "public-autonomy-canary-receipt.schema.json").read_text(encoding="utf-8")
    )
    digest = "a" * 64
    receipt = {
        "schema_id": "datalens_public_autonomy_canary",
        "status": "completed",
        "surface": "autonomous-v2",
        "public_tools_only": True,
        "public_tool_count": 8,
        "installed_package": True,
        "package_version": "0.5.0",
        "build_identity_hash": digest,
        "exact_head": "b" * 40,
        "source_tree_sha256": digest,
        "source_unchanged": True,
        "task_id": "task",
        "contract_hash": digest,
        "target_binding_hash": digest,
        "style_binding_hash": digest,
        "plan_hash": digest,
        "save_write_count": 1,
        "publish_write_count": 1,
        "process_restart_after_save": True,
        "saved_readback_verified": True,
        "published_readback_verified": True,
        "typed_data_verified": True,
        "dataset_data_semantics": "unknown_experimental",
        "raw_rows_inline": False,
        "browser_policy": "forbidden",
        "browser_call_count": 0,
        "stale_revision_write_count": 0,
        "completion_verified": True,
        "cleanup": {"executed": False, "policy": "dedicated target retained"},
        "artifact_hashes": {f"artifact_{index}": digest for index in range(5)},
        "live_verified": True,
        "ok": True,
    }
    assert list(Draft202012Validator(schema).iter_errors(receipt)) == []


def test_public_stdio_client_initializes_and_decodes_tool_payload() -> None:
    child = r'''
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18"}
    elif method == "tools/list":
        result = {"tool_surface": "autonomous-v2", "tools": [{"name": name} for name in __PUBLIC_TOOLS__]}
    else:
        payload = {"ok": True, "state": "PLAN_VALIDATED"}
        result = {"isError": False, "content": [{"type": "text", "text": json.dumps(payload)}]}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
'''.replace("__PUBLIC_TOOLS__", repr(sorted(PUBLIC_TOOLS)))
    with (
        tempfile.TemporaryDirectory() as tmp,
        PublicStdioClient([sys.executable, "-u", "-c", child], cwd=tmp, timeout=5) as client,
    ):
        initialized = client.initialize()
        listed = client.list_tools()
        called = client.call_tool("dl_task_start", {})
    assert initialized["protocolVersion"] == "2025-06-18"
    assert {item["name"] for item in listed["tools"]} == PUBLIC_TOOLS
    assert called == {"ok": True, "state": "PLAN_VALIDATED"}
