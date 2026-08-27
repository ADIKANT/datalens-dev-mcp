#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run executable public-only autonomous MCP acceptance.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "autonomy" / "public-e2e-receipt.json",
    )
    args = parser.parse_args()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DATALENS_MCP_TOOL_SURFACE"] = "autonomous-v2"
    commands = [
        [sys.executable, "scripts/validate_behavior_trace_corpus.py"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/regression/policy_matrix",
            "tests/regression/test_public_behavior_traces.py",
            "tests/integration/test_public_autonomy_e2e.py",
            "tests/integration/test_public_autonomy_failures.py",
            "tests/integration/test_public_autonomy_call_budgets.py",
        ],
    ]
    ok = True
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, env=env, check=False)  # noqa: S603
        if completed.returncode:
            ok = False
            break
    report = json.loads(
        (ROOT / "tests" / "regression" / "behavior_traces" / "corpus-report.json").read_text(encoding="utf-8")
    )
    receipt = {
        "schema_id": "datalens_public_e2e_receipt",
        "status": "passed" if ok else "failed",
        "tool_surface": "autonomous-v2",
        "case_count": int(report["case_count"]),
        "family_count": int(report["family_count"]),
        "public_call_count": int(report["case_count"]),
        "write_count": 0,
        "proof_levels": ["source_static", "contract_runtime", "save_readback", "publish_readback"],
        "corpus_sha256": str(report["corpus_sha256"]),
    }
    schema = json.loads((ROOT / "schemas" / "public-e2e-receipt.schema.json").read_text(encoding="utf-8"))
    schema_issues = list(Draft202012Validator(schema).iter_errors(receipt))
    if schema_issues:
        ok = False
        receipt["status"] = "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": ok,
                "receipt": str(args.output),
                "receipt_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
