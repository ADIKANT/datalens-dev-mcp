from __future__ import annotations

import json
import subprocess
from pathlib import Path

from datalens_dev_mcp.server import list_tools

EXPECTED_CASES = {
    *(f"A{i:02d}" for i in range(1, 6)),
    *(f"B{i:02d}" for i in range(1, 9)),
    *(f"C{i:02d}" for i in range(1, 11)),
    *(f"D{i:02d}" for i in range(1, 9)),
    *(f"E{i:02d}" for i in range(1, 9)),
    *(f"F{i:02d}" for i in range(1, 10)),
    *(f"G{i:02d}" for i in range(1, 11)),
    *(f"H{i:02d}" for i in range(1, 5)),
}
IMPLEMENTED_BOUNDARY_CASES = {"C10", "H02", "H04"}


def root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_all_62_authoritative_cases_have_direct_owner_and_boundary() -> None:
    coverage = json.loads(
        (root() / "src/datalens_dev_mcp/schemas/capability-coverage.json").read_text(encoding="utf-8")
    )
    assert len(EXPECTED_CASES) == 62
    assert set(coverage) == EXPECTED_CASES
    public_tools = {tool["name"] for tool in list_tools()}
    for case_id, record in coverage.items():
        assert record["owner"] in public_tools | {"codex_host", "skill", "unsupported_public_api"}, case_id
        assert record["boundary"], case_id
        assert record["implementation_status"] in {
            "implemented",
            "implemented_with_boundary",
            "host_owned",
            "documented_boundary",
        }, case_id
        if record["owner"] == "codex_host":
            assert record["implementation_status"] == "host_owned", case_id
        elif record["owner"] == "unsupported_public_api":
            assert record["implementation_status"] == "documented_boundary", case_id
        elif case_id in IMPLEMENTED_BOUNDARY_CASES:
            assert record["implementation_status"] == "implemented_with_boundary", case_id
        else:
            assert record["implementation_status"] == "implemented", case_id


def test_tracked_runtime_contains_no_legacy_orchestrator_owners() -> None:
    tracked = subprocess.check_output(["git", "ls-files"], cwd=root(), text=True).splitlines()
    forbidden_paths = (
        "src/datalens_dev_mcp/pipeline/",
        "src/datalens_dev_mcp/mcp/task",
        "memory-bank/",
        "schemas/task-",
        "tests/unit/test_task_",
    )
    offenders = [path for path in tracked if path.startswith(forbidden_paths)]
    assert offenders == []


def test_ci_and_release_only_reference_tracked_scripts() -> None:
    base = root()
    for workflow in (base / ".github/workflows/ci.yml", base / ".github/workflows/release.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if "scripts/" not in line:
                continue
            fragment = line.split("scripts/", 1)[1].split()[0]
            path = base / "scripts" / fragment
            assert path.is_file(), f"{workflow.name} references missing {path.relative_to(base)}"
