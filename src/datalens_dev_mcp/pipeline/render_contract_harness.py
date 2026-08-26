from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import write_json


RENDER_VIEWPORTS = (
    {"id": "compact", "width": 320, "height": 220},
    {"id": "dashboard", "width": 640, "height": 340},
    {"id": "wide", "width": 960, "height": 460},
)
RENDER_DATA_STATES = (
    "full",
    "partial-null",
    "empty-expected",
    "empty-unexpected",
    "single-row",
    "long-labels",
    "high-cardinality",
    "pagination-boundary",
)
RENDER_THEMES = ("light", "dark", "contrast")


def build_render_contract_fixture(
    *,
    fixture_id: str,
    prepare_source: str,
    expectations: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_id": "render_contract_fixture",
        "fixture_id": fixture_id,
        "prepare_source": prepare_source,
        "viewports": [dict(item) for item in RENDER_VIEWPORTS],
        "data_states": list(RENDER_DATA_STATES),
        "themes": list(RENDER_THEMES),
        "params": params or {},
        "expectations": expectations,
    }


def run_render_contract_fixture(
    fixture: dict[str, Any],
    *,
    project_root: str | Path = ".",
    artifact_name: str = "editor-contract-fixture",
    node_binary: str = "node",
) -> dict[str, Any]:
    source = str(fixture.get("prepare_source") or "") if isinstance(fixture, dict) else ""
    if not source or len(source.encode("utf-8")) > 200_000:
        return {
            "schema_id": "render_contract_result",
            "ok": False,
            "status": "blocked",
            "proof_level": "source_static",
            "issues": ["prepare_source must contain between 1 and 200000 UTF-8 bytes"],
            "browser_rendered": False,
        }
    script = Path(__file__).resolve().parents[3] / "scripts" / "run_editor_contract_fixture.mjs"
    completed = subprocess.run(
        [node_binary, str(script), "--stdin"],
        input=json.dumps(fixture, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "schema_id": "render_contract_result",
            "ok": False,
            "status": "runtime_failed",
            "proof_level": "contract_runtime",
            "issues": [completed.stderr.strip() or "contract harness process failed"],
            "browser_rendered": False,
        }
    result["proof_level"] = "contract_runtime"
    result["browser_rendered"] = False
    safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in artifact_name)
    path = Path(project_root) / "artifacts" / "render_contract" / f"{safe_name or 'fixture'}.json"
    write_json(path, result)
    result["artifact_path"] = str(path)
    return result
