#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERIC_RUNNERS = (
    ROOT / "scripts" / "acceptance_shards.py",
    ROOT / "scripts" / "run_autonomy_acceptance.py",
    ROOT / "scripts" / "run_affected_acceptance.py",
    ROOT / "scripts" / "run_full_acceptance.py",
)


def main() -> int:
    issues: list[str] = []
    generic = GENERIC_RUNNERS[0].read_text(encoding="utf-8")
    if '"DATALENS_MCP_TOOL_SURFACE": "legacy-v1"' in generic:
        issues.append("generic acceptance runner forces legacy-v1")
    for path in GENERIC_RUNNERS:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            issues.append(f"{path.name}: {exc.msg}")
    for path in GENERIC_RUNNERS[1:]:
        text = path.read_text(encoding="utf-8")
        if 'surface="autonomous-v2"' not in text:
            issues.append(f"{path.name}: autonomous surface is not explicit")
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("acceptance surface isolation: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
