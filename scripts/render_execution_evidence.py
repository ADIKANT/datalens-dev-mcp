#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.pipeline.artifacts import loads_strict_json, write_json, write_text  # noqa: E402
from datalens_dev_mcp.pipeline.execution_evidence import (  # noqa: E402
    build_execution_evidence_model,
    render_execution_evidence_views,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render consistent execution evidence views from one typed model.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = loads_strict_json(args.input.read_text(encoding="utf-8"), source=str(args.input))
    model = build_execution_evidence_model(
        goal=dict(source.get("goal") or {}),
        build=dict(source.get("build") or {}),
        records=list(source.get("records") or []),
        obligations=dict(source.get("obligations") or {}),
    )
    views = render_execution_evidence_views(model)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "execution-evidence-model.json", model)
    for name, payload in views.items():
        write_json(args.output_dir / f"execution-{name.replace('_', '-')}.json", payload)
    write_text(args.output_dir / "execution-final-report.md", _markdown(views))
    print(model["evidence_model_hash"])
    return 0


def _markdown(views: dict[str, dict]) -> str:
    final = views["final_report"]
    calls = views["call_counts"]
    coverage = views["coverage_matrix"]
    lines = [
        "# Execution evidence report",
        "",
        f"Evidence model: `{final['evidence_model_hash']}`",
        f"Completion proven: `{str(final['completion_proven']).lower()}`",
        "",
        "## Current obligations",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(final["obligations"].items()))
    lines.extend(["", "## Current evidence", ""])
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(final["current_statuses"].items()))
    lines.extend(
        [
            "",
            "## Observed provider calls",
            "",
            f"- Reads: `{calls['provider_reads']}`",
            f"- Writes: `{calls['provider_writes']}`",
            f"- Planned methods counted as observed: `{str(calls['planned_methods_counted']).lower()}`",
            "",
            "## Mode-specific coverage",
            "",
        ]
    )
    lines.extend(
        f"- `{row['cell']}` — `{row['mode']}` — `{row['state']}`"
        for row in coverage["cells"]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
