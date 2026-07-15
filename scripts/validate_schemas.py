#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datalens_dev_mcp.validators.artifact_validator import validate_schema_file


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("schemas")
    issues: list[str] = []
    for path in sorted(root.glob("*.schema.json")):
        result = validate_schema_file(path)
        issues.extend(result.issues)
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
