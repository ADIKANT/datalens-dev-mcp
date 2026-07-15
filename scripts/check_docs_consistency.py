#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_DOCS = (
    "README.md",
    "README_en.md",
    "docs/README.md",
    "docs/README_en.md",
    "docs/tools.md",
    "docs/tools_en.md",
    "docs/usage-flow.md",
    "docs/usage-flow_en.md",
    "docs/sources.md",
    "docs/sources_en.md",
    "docs/getting-started.md",
    "docs/one-prompt-workflow.md",
    "docs/project_workflow.md",
    "docs/architecture.md",
    "docs/getting_started_local.md",
    "docs/mcp/codex_connection.md",
    "docs/codex_setup.md",
    "docs/codex_setup_en.md",
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

LANGUAGE_PAIRS = (
    ("README.md", "README_en.md"),
    ("docs/README.md", "docs/README_en.md"),
    ("docs/tools.md", "docs/tools_en.md"),
    ("docs/usage-flow.md", "docs/usage-flow_en.md"),
    ("docs/sources.md", "docs/sources_en.md"),
    ("docs/codex_setup.md", "docs/codex_setup_en.md"),
)

REQUIRED_SOURCE_URLS = (
    "https://yandex.cloud/ru/docs/datalens/",
    "https://yandex.cloud/ru/docs/datalens/concepts/chart/",
    "https://yandex.cloud/ru/docs/datalens/operations/api-start",
    "https://yandex.cloud/ru/docs/datalens/openapi-ref/",
    "https://yandex.cloud/ru/docs/datalens/charts/editor/tabs",
    "https://yandex.cloud/ru/docs/datalens/charts/editor/methods",
    "https://github.com/yandex-cloud/docs/blob/master/LICENSE",
    "https://api.datalens.tech/json/",
    "https://yandex.cloud/llms.txt",
)

ALLOWED_SOURCE_DOMAINS = frozenset(
    {
        "api.datalens.tech",
        "github.com",
        "yandex.cloud",
    }
)

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
URL_RE = re.compile(r"https?://[^\s<>\"'`)}\]]+", re.IGNORECASE)


@dataclass(frozen=True)
class DocsConsistencyReport:
    ok: bool
    issues: tuple[str, ...]
    checked_files: tuple[str, ...]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _link_target(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    if " " in value:
        value = value.split(" ", 1)[0]
    return value


def _check_local_links(rel: str, text: str) -> list[str]:
    issues: list[str] = []
    source = ROOT / rel
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = _link_target(match.group(1))
        if not target or target.startswith(("#", "http://", "https://", "mailto:", "data:")):
            continue
        parsed = urlsplit(target)
        path_part = unquote(parsed.path)
        if not path_part:
            continue
        if path_part.startswith("/"):
            issues.append(f"{rel}: absolute local Markdown link is not portable: {target}")
            continue
        resolved = (source.parent / path_part).resolve(strict=False)
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            issues.append(f"{rel}: Markdown link escapes repository: {target}")
            continue
        if not resolved.exists():
            issues.append(f"{rel}: broken local Markdown link: {target}")
    return issues


def _check_language_pairs() -> list[str]:
    issues: list[str] = []
    for russian_rel, english_rel in LANGUAGE_PAIRS:
        russian = _text(russian_rel)
        english = _text(english_rel)
        russian_target = Path(english_rel).name
        english_target = Path(russian_rel).name
        if f"]({russian_target})" not in russian:
            issues.append(f"{russian_rel}: missing English language switch to {russian_target}")
        if f"]({english_target})" not in english:
            issues.append(f"{english_rel}: missing Russian language switch to {english_target}")
    return issues


def _check_source_guides() -> list[str]:
    issues: list[str] = []
    provenance = json.loads(
        (ROOT / "src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json").read_text(
            encoding="utf-8"
        )
    )
    api_trace = json.loads((ROOT / "schemas/datalens-api/source-trace.json").read_text(encoding="utf-8"))
    expected_values = (
        str(provenance["snapshot"]["generated_at"]),
        str(provenance["snapshot"]["pages_content_sha256"]),
        str(api_trace["openapi_sha256"]),
    )

    for rel in ("docs/sources.md", "docs/sources_en.md"):
        text = _text(rel)
        for url in REQUIRED_SOURCE_URLS:
            if url not in text:
                issues.append(f"{rel}: missing required official source URL: {url}")
        for value in expected_values:
            if value not in text:
                issues.append(f"{rel}: packaged provenance value is stale or missing: {value}")
        for url in URL_RE.findall(text):
            host = (urlsplit(url).hostname or "").casefold()
            if host not in ALLOWED_SOURCE_DOMAINS:
                issues.append(f"{rel}: non-official source domain in source map: {host or url}")
        if "discovery" not in text.casefold():
            issues.append(f"{rel}: llms.txt must be labeled as discovery only")
        if "compiler input" not in text.casefold():
            issues.append(f"{rel}: OpenAPI must be labeled as compiler input")
    return issues


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
        issues.extend(_check_local_links(rel, text))

    if (ROOT / "README_ru.md").exists():
        issues.append("README_ru.md: Russian default must live in README.md; legacy mirror should be removed")

    readme = _text("README.md")
    if "## Установка" not in readme or "## Что умеет сервер" not in readme:
        issues.append("README.md: Russian must be the default public language")
    if "dl_runtime_status" not in readme:
        issues.append("README.md: missing first read-only runtime check")
    if "dl_runtime_status" not in _text("README_en.md"):
        issues.append("README_en.md: missing first read-only runtime check")

    codex_docs = "\n".join((_text("docs/codex_setup.md"), _text("docs/codex_setup_en.md")))
    for required in ("[mcp_servers.", "codex mcp add", "codex mcp list", "/mcp"):
        if required not in codex_docs:
            issues.append(f"Codex setup guides: missing current Codex MCP marker: {required}")
    if '"mcpServers"' in codex_docs:
        issues.append("Codex setup guides: legacy JSON Codex configuration present")

    issues.extend(_check_language_pairs())
    issues.extend(_check_source_guides())

    return DocsConsistencyReport(
        ok=not issues,
        issues=tuple(sorted(set(issues))),
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
