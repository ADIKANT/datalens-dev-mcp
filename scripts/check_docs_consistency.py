#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_DOCS = (
    "README.md",
    "README_ru.md",
    "docs/architecture.md",
    "docs/getting_started_local.md",
    "docs/mcp/codex_connection.md",
    "docs/codex_setup.md",
    "docs/configuration.md",
    "docs/local-only-safety-model.md",
    "docs/route-policy.md",
    "docs/safe-apply.md",
    "docs/mcp/tools.md",
    "docs/mcp/response_contracts.md",
    "docs/source_provenance.md",
    "docs/materials_policy.md",
    "THIRD_PARTY_NOTICES.md",
)

FORBIDDEN_MARKERS = (
    "/Users/",
    "materials/raw/",
    "docs/knowledge_base/",
    "docs/reports/",
)


@dataclass(frozen=True)
class DocsConsistencyReport:
    ok: bool
    issues: tuple[str, ...]
    checked_files: tuple[str, ...]


def run_checks() -> DocsConsistencyReport:
    issues: list[str] = []
    checked: list[str] = []
    for rel in ACTIVE_DOCS:
        path = ROOT / rel
        if not path.is_file():
            issues.append(f"{rel}: missing active documentation")
            continue
        checked.append(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_MARKERS:
            if marker.casefold() in text.casefold():
                issues.append(f"{rel}: forbidden private or legacy marker: {marker}")

    codex_docs = (ROOT / "docs/mcp/codex_connection.md").read_text(encoding="utf-8")
    if "[mcp_servers." not in codex_docs:
        issues.append("docs/mcp/codex_connection.md: missing current Codex TOML example")
    if '"mcpServers"' in codex_docs:
        issues.append("docs/mcp/codex_connection.md: legacy JSON Codex configuration present")

    for rel in ("README.md", "README_ru.md"):
        if "dl_runtime_status" not in (ROOT / rel).read_text(encoding="utf-8"):
            issues.append(f"{rel}: missing first read-only runtime check")

    return DocsConsistencyReport(
        ok=not issues,
        issues=tuple(issues),
        checked_files=tuple(checked),
    )


def main() -> int:
    report = run_checks()
    if report.ok:
        print(f"docs_consistency: ok checked_files={len(report.checked_files)}")
        return 0
    print("docs_consistency: failed")
    for issue in report.issues:
        print(issue)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
