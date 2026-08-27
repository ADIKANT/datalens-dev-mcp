#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from acceptance_shards import ROOT, compact_report, py, run_acceptance

EDITOR_MARKERS = ("editor", "chart", "wizard", "dashboard", "browser", "visual", "style", "renderer", "layout")
PIPELINE_MARKERS = (
    "pipeline", "workflow", "task", "journal", "safe_apply", "semantic", "data_", "proof", "evidence",
    "failure", "retry", "result_dedup", "live_maintenance", "patch", "delivery",
)


def unit_shards() -> tuple[list[str], list[str], list[str]]:
    paths = sorted((ROOT / "tests" / "unit").glob("test_*.py"))
    editor: list[str] = []
    pipeline: list[str] = []
    core: list[str] = []
    for path in paths:
        name = path.name.lower()
        relative = path.relative_to(ROOT).as_posix()
        if any(marker in name for marker in EDITOR_MARKERS):
            editor.append(relative)
        elif any(marker in name for marker in PIPELINE_MARKERS):
            pipeline.append(relative)
        else:
            core.append(relative)
    return core, editor, pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the complete sharded offline acceptance suite.")
    parser.add_argument("--sharded", action="store_true")
    parser.parse_args()
    core, editor, pipeline = unit_shards()
    shards = [
        {"name": "unit-core", "command": py("-m", "pytest", "-q", *core), "timeout_sec": 900},
        {"name": "unit-editor", "command": py("-m", "pytest", "-q", *editor), "timeout_sec": 900},
        {"name": "unit-pipeline", "command": py("-m", "pytest", "-q", *pipeline), "timeout_sec": 900},
        {
            "name": "integration-api-mocked",
            "command": py("-m", "pytest", "-q", "tests/integration_offline"),
            "timeout_sec": 600,
        },
        {
            "name": "integration-workflow",
            "command": py("-m", "pytest", "-q", "tests/integration"),
            "timeout_sec": 600,
        },
        {
            "name": "regression-public-behaviors",
            "commands": [
                py("scripts/run_public_autonomy_acceptance.py"),
                py("scripts/run_runtime_incident_acceptance.py"),
            ],
            "timeout_sec": 600,
        },
        {
            "name": "release-surface",
            "commands": [
                py("scripts/check_canonical_server_surface.py"), py("scripts/validate_schemas.py"),
                py("scripts/build_runtime_resource_manifest.py", "--check"), py("scripts/check_docs_consistency.py"),
                py("scripts/validate_api_contract_coverage.py"), py("scripts/check_public_release.py"),
                py("scripts/scan_sensitive_artifacts.py"), py("scripts/check_repo_size_budget.py", "--strict"),
                py("scripts/run_server_efficiency_suite.py", "--strict"),
            ],
            "timeout_sec": 300,
        },
    ]
    report = run_acceptance("full-sharded", shards, surface="autonomous-v2")
    print(json.dumps(compact_report(report), indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
