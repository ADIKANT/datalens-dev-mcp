#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from acceptance_shards import compact_report, py, run_acceptance


def main() -> int:
    parser = argparse.ArgumentParser(description="Run affected-source acceptance for the autonomous DataLens server.")
    parser.add_argument("--all", action="store_true", help="Run the complete affected contract set.")
    parser.parse_args()
    shards = [
        {
            "name": "static-and-schema",
            "commands": [
                py("scripts/lint_local.py"),
                py("scripts/validate_schemas.py"),
                py("scripts/build_runtime_resource_manifest.py", "--check"),
            ],
            "timeout_sec": 180,
        },
        {
            "name": "autonomy-contracts",
            "command": py(
                "-m", "pytest", "-q",
                "tests/unit/test_task_compiler.py", "tests/unit/test_workflow_engine.py",
                "tests/unit/test_semantic_patch.py", "tests/unit/test_data_assertions.py",
                "tests/unit/test_evidence_matrix.py", "tests/unit/test_failure_classifier.py",
                "tests/unit/test_retry_controller.py", "tests/unit/test_result_dedup.py",
                "tests/regression",
            ),
            "timeout_sec": 300,
        },
        {
            "name": "public-surface",
            "commands": [
                py("scripts/check_autonomous_tool_surface.py"),
                py("scripts/check_public_release.py"),
                py("scripts/scan_sensitive_artifacts.py"),
            ],
            "timeout_sec": 180,
        },
    ]
    report = run_acceptance("affected", shards, surface="autonomous-v2")
    print(json.dumps(compact_report(report), indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
