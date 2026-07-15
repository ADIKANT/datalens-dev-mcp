#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS_ROOTS = [ROOT / "templates", ROOT / "examples"]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text


def main() -> int:
    node = shutil.which("node")
    issues: list[str] = []
    checked = 0
    wrapfn_files = 0
    for root in JS_ROOTS:
        for path in sorted(root.rglob("*.js")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "Editor.wrapFn" in text:
                wrapfn_files += 1
                if "args" not in text:
                    issues.append(f"{path}: Editor.wrapFn must pass compact args")
            if node:
                result = subprocess.run([node, "--check", str(path)], check=False, capture_output=True, text=True)
                if result.returncode != 0:
                    issues.append(f"{path}: {result.stderr.strip() or result.stdout.strip()}")
            elif text.count("{") != text.count("}"):
                issues.append(f"{path}: fallback brace check failed")
            sql_lint = lint_editor_sql_text(text, path=str(path))
            for issue in sql_lint.issues:
                if issue.severity == "error":
                    issues.append(f"{path}: {issue.rule}: {issue.message}")
            checked += 1
    payload = {"ok": not issues, "checked_js_files": checked, "wrapfn_files": wrapfn_files, "issues": issues}
    print(json.dumps(payload, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
