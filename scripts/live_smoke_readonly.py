#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

LIVE_FLAG = "DATALENS_MCP_RUN_LIVE_TESTS"


def _env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _response_summary(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        summary: dict[str, Any] = {"keys": sorted(response)[:30]}
        for key in ("items", "entries", "workbooks", "result"):
            value = response.get(key)
            if isinstance(value, list):
                summary[f"{key}_count"] = len(value)
            elif isinstance(value, dict):
                summary[f"{key}_keys"] = sorted(value)[:30]
        return summary
    if isinstance(response, list):
        return {"items_count": len(response)}
    return {"type": type(response).__name__}


def _step(name: str, *, ok: bool, status: str, **data: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "status": status, **data}


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    if os.getenv(LIVE_FLAG) != "1":
        _print(
            {
                "ok": True,
                "skipped": True,
                "reason": f"set {LIVE_FLAG}=1 with disposable DataLens credentials",
                "write_attempted": False,
                "publish_attempted": False,
            }
        )
        return 0

    credential_presence = {
        "org_id_present": _env_present("DATALENS_ORG_ID"),
        "iam_token_present": _env_present("DATALENS_IAM_TOKEN"),
    }
    payload: dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "credential_presence": credential_presence,
        "write_attempted": False,
        "publish_attempted": False,
        "steps": [],
    }
    if not all(credential_presence.values()):
        payload["status"] = "BLOCKED_LIVE_CREDENTIALS"
        _print(payload)
        return 0

    from datalens_dev_mcp.mcp.tools.discovery import dl_get_workbook_entries, dl_list_workbooks
    from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_probe_auth, dl_read_object
    from datalens_dev_mcp.mcp.tools.pipeline import dl_build_dashboard_blueprint_plan, dl_ingest_requirements

    auth = dl_probe_auth()
    payload["steps"].append(
        _step(
            "auth_probe",
            ok=bool(auth.get("ok")),
            status=auth.get("status", "failed"),
            method=auth.get("method"),
            response_keys=auth.get("response_keys", []),
        )
    )
    if not auth.get("ok"):
        payload["ok"] = False
        payload["status"] = "AUTH_PROBE_FAILED"
        _print(payload)
        return 1

    try:
        workbooks = dl_list_workbooks(page=1, page_size=5)
        payload["steps"].append(
            _step("list_workbooks", ok=True, status="read_only_ok", response_summary=_response_summary(workbooks))
        )
    except Exception as exc:  # noqa: BLE001
        payload["ok"] = False
        payload["steps"].append(_step("list_workbooks", ok=False, status=type(exc).__name__, message=str(exc)[:300]))
        _print(payload)
        return 1

    workbook_id = os.getenv("DATALENS_MCP_LIVE_WORKBOOK_ID", "").strip()
    if workbook_id:
        try:
            entries = dl_get_workbook_entries(workbook_id)
            payload["steps"].append(
                _step(
                    "read_workbook_entries",
                    ok=True,
                    status="read_only_ok",
                    workbook_id_supplied=True,
                    response_summary=_response_summary(entries),
                )
            )
        except Exception as exc:  # noqa: BLE001
            payload["ok"] = False
            payload["steps"].append(
                _step("read_workbook_entries", ok=False, status=type(exc).__name__, message=str(exc)[:300])
            )
            _print(payload)
            return 1
    else:
        payload["steps"].append(_step("read_workbook_entries", ok=True, status="skipped_no_workbook_id"))

    object_type = os.getenv("DATALENS_MCP_LIVE_OBJECT_TYPE", "").strip()
    object_id = os.getenv("DATALENS_MCP_LIVE_OBJECT_ID", "").strip()
    branch = os.getenv("DATALENS_MCP_LIVE_OBJECT_BRANCH", "saved").strip() or "saved"
    if object_type and object_id:
        read = dl_read_object(object_type, object_id, branch=branch)
        payload["steps"].append(
            _step(
                "read_object",
                ok=bool(read.get("ok")),
                status="read_only_ok" if read.get("ok") else read.get("error", {}).get("category", "read_failed"),
                object_type=read.get("object_type", object_type),
                method=read.get("method"),
                branch=branch,
                response_summary=_response_summary(read.get("response", {})),
            )
        )
        if not read.get("ok"):
            payload["ok"] = False
            payload["status"] = "OBJECT_READ_FAILED"
            _print(payload)
            return 1
    else:
        payload["steps"].append(_step("read_object", ok=True, status="skipped_no_object_id"))

    with tempfile.TemporaryDirectory(prefix="datalens-mcp-live-smoke-") as tmp:
        requirements = (
            "Disposable local live smoke dashboard plan. Audience: internal tester. "
            "Goal: verify MCP planning and safe defaults. Data: synthetic status rows. "
            "Metrics: smoke count and latest status. Visuals: KPI and table."
        )
        dl_ingest_requirements(tmp, requirements_text=requirements, source_name="live_smoke_readonly")
        plan = dl_build_dashboard_blueprint_plan(tmp)
        payload["steps"].append(
            _step(
                "dashboard_plan_without_writes",
                ok=True,
                status="offline_plan_ok",
                blueprint_type=plan.get("selected_blueprint", {}).get("type"),
                execution_blocked=plan.get("execution_blocked"),
            )
        )

    if os.getenv("DATALENS_MCP_LIVE_ALLOW_SAVE") == "1" or os.getenv("DATALENS_MCP_LIVE_ALLOW_PUBLISH") == "1":
        payload["steps"].append(
            _step(
                "write_flags",
                ok=True,
                status="ignored_by_readonly_smoke",
                message="This script never executes save or publish. Use an approved safe-apply plan manually.",
            )
        )

    payload["status"] = "READONLY_SMOKE_OK"
    _print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
