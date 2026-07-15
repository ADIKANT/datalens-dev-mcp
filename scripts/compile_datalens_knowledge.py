#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.knowledge.compiler import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_DEMO_REFERENCE_ROOT,
    build_baseline_artifacts,
    build_compiled_knowledge,
    build_search_index,
    check_compiled_knowledge,
    write_compiled_knowledge,
    write_final_reports,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile compact DataLens full-corpus knowledge registries.")
    parser.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    parser.add_argument("--demo-root", default=str(DEFAULT_DEMO_REFERENCE_ROOT))
    parser.add_argument("--check", action="store_true", help="Validate current corpus and generated compact registries.")
    parser.add_argument("--write", action="store_true", help="Write compact registries and recipes.")
    parser.add_argument("--baseline", action="store_true", help="Write step-1 baseline artifacts.")
    parser.add_argument("--reports", action="store_true", help="Write final acceptance reports.")
    parser.add_argument("--no-index", action="store_true", help="Skip rebuilding the ignored SQLite index.")
    args = parser.parse_args()

    if args.check and (args.write or args.baseline or args.reports):
        parser.error("--check is read-only and cannot be combined with --write, --baseline, or --reports")

    compiled = build_compiled_knowledge(Path(args.corpus_root), Path(args.demo_root))
    if args.write:
        check = write_compiled_knowledge(compiled, write_index=not args.no_index)
    else:
        if not args.check and not args.no_index:
            build_search_index(compiled["corpus"])
        check = check_compiled_knowledge(compiled, verify_disk_parity=args.check)
    if args.baseline:
        build_baseline_artifacts(compiled)
    if args.reports:
        write_final_reports(compiled, check)
    print(json.dumps(check, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if check["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
