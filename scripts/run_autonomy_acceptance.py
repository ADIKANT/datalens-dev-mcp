#!/usr/bin/env python3
from __future__ import annotations

import json

from acceptance_shards import compact_report, py, run_acceptance


def main() -> int:
    shards = [
        {
            "name": "task-contract-and-resume",
            "command": py(
                "-m", "pytest", "-q", "tests/unit/test_task_compiler.py",
                "tests/unit/test_acceptance_surface_policy.py",
                "tests/unit/test_project_journal.py", "tests/unit/test_workflow_engine.py",
                "tests/integration/test_workflow_resume.py", "tests/integration/test_task_tools_stdio.py",
            ),
        },
        {
            "name": "semantic-patches",
            "command": py("-m", "pytest", "-q", "tests/unit/test_semantic_patch.py", "tests/integration/test_semantic_patch_safe_apply.py"),
        },
        {
            "name": "typed-data-assertions",
            "command": py("-m", "pytest", "-q", "tests/unit/test_data_assertions.py"),
        },
        {
            "name": "intent-aware-qa",
            "command": py(
                "-m", "pytest", "-q", "tests/unit/test_evidence_matrix.py",
                "tests/integration/test_editor_contract_harness.py", "tests/integration/test_browser_policy_safe_apply.py",
            ),
        },
        {
            "name": "failure-retry-context",
            "command": py(
                "-m", "pytest", "-q", "tests/unit/test_failure_classifier.py",
                "tests/unit/test_retry_controller.py", "tests/unit/test_result_dedup.py",
                "tests/integration/test_compact_task_context.py",
            ),
        },
        {
            "name": "public-behavior-regression",
            "commands": [
                py("scripts/validate_behavior_trace_corpus.py"),
                py("scripts/run_public_autonomy_acceptance.py"),
            ],
        },
        {
            "name": "stdio-task-flow",
            "commands": [
                py("scripts/smoke_mcp_stdio.py"),
                py(
                    "-m", "pytest", "-q",
                    "tests/integration_offline/test_mcp_stdio.py",
                    "tests/integration_offline/test_mcp_stdio_autonomous.py",
                    "tests/integration_offline/test_mcp_stdio_legacy.py",
                ),
            ],
        },
        {
            "name": "runtime-incidents",
            "command": py("scripts/run_runtime_incident_acceptance.py"),
            "timeout_sec": 300,
        },
    ]
    report = run_acceptance("autonomy", shards, surface="autonomous-v2")
    print(json.dumps(compact_report(report), indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
