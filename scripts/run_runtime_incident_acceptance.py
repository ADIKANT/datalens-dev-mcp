#!/usr/bin/env python3
from __future__ import annotations

import json

from acceptance_shards import compact_report, py, run_acceptance


def main() -> int:
    shards = [
        {
            "name": "provider-normalization",
            "command": py(
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_runtime_provider_normalization.py",
                "tests/unit/test_api_scheduler_and_batch.py",
                "tests/unit/test_runtime_safe_apply_incident_contracts.py",
            ),
        },
        {
            "name": "dataset-data-context",
            "command": py(
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_dataset_data_contract.py",
                "tests/unit/test_dataset_data_failures.py",
                "tests/unit/test_dataset_preview.py",
                "tests/unit/test_dataset_probe_planner.py",
                "tests/unit/test_dataset_context_profile.py",
                "tests/unit/test_target_discovery.py",
                "tests/integration/test_public_dataset_context_workflow.py",
                "tests/integration/test_public_typed_data_proof.py",
            ),
        },
        {
            "name": "public-create-manifest",
            "command": py(
                "-m",
                "pytest",
                "-q",
                "tests/unit/test_public_create_manifest.py",
                "tests/integration/test_public_create_workflow.py",
            ),
        },
    ]
    report = run_acceptance("runtime-incidents", shards, surface="autonomous-v2")
    print(json.dumps(compact_report(report), indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
