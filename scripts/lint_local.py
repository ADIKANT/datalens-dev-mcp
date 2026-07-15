#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


STYLE_EXCLUDED_PREFIXES = (
    Path("src") / "datalens_dev_mcp" / "pipeline" / "governance_bundle.py",
)
COMPILE_EXCLUDED_PREFIXES: tuple[Path, ...] = ()


def style_excluded(path: Path) -> bool:
    return any(path == prefix or prefix in path.parents for prefix in STYLE_EXCLUDED_PREFIXES)


def compile_excluded(path: Path) -> bool:
    return any(path == prefix or prefix in path.parents for prefix in COMPILE_EXCLUDED_PREFIXES)


def main() -> int:
    roots = [Path("src"), Path("tests"), Path("scripts")]
    issues: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if not compile_excluded(path):
                try:
                    compile(path.read_text(encoding="utf-8"), str(path), "exec")
                except SyntaxError as exc:
                    issues.append(f"{path}: {exc.msg}")
            if style_excluded(path):
                continue
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if len(line) > 140:
                    issues.append(f"{path}:{line_no}: line too long")
                if line.rstrip() != line:
                    issues.append(f"{path}:{line_no}: trailing whitespace")
    if issues:
        print("\n".join(issues))
        return 1
    print("lint_local: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
