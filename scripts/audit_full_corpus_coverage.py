#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.knowledge.compiler import DEFAULT_CORPUS_ROOT, build_baseline_artifacts, build_compiled_knowledge


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit DataLens full-corpus coverage without changing runtime behavior.")
    parser.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    args = parser.parse_args()

    compiled = build_compiled_knowledge(Path(args.corpus_root))
    baseline = build_baseline_artifacts(compiled)
    print(json.dumps({"ok": True, "counts": baseline["counts"], "tool_budget": baseline["tool_budget"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
