#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from datalens_dev_mcp.server import STANDARD_TOOL_NAMES, list_tools  # noqa: E402
from datalens_dev_mcp.knowledge.reference import build_reference_response  # noqa: E402


ACTIVE_DOCS = (
    "README.md",
    "README_en.md",
    "AGENTS.md",
    "SECURITY.md",
    "docs/README.md",
    "docs/README_en.md",
    "docs/access.md",
    "docs/access_en.md",
    "docs/tools.md",
    "docs/tools_en.md",
    "docs/usage-flow.md",
    "docs/usage-flow_en.md",
    "docs/sources.md",
    "docs/sources_en.md",
    "docs/mcp/codex_connection.md",
    "docs/codex_setup.md",
    "docs/codex_setup_en.md",
    "docs/configuration.md",
    "docs/configuration_en.md",
    "docs/local-only-safety-model.md",
    "docs/local-only-safety-model_en.md",
    "docs/route-policy.md",
    "docs/route-policy_en.md",
    "docs/safe-apply.md",
    "docs/safe-apply_en.md",
    "docs/mcp/tools.md",
    "docs/mcp/response_contracts.md",
    "docs/source_provenance.md",
    "docs/materials_policy.md",
    "THIRD_PARTY_NOTICES.md",
)

LEGACY_ONBOARDING_DOCS = (
    "docs/datalens-auth.md",
    "docs/datalens/api_start_auth.md",
    "docs/mcp-configuration.md",
    "docs/getting-started.md",
    "docs/getting_started_local.md",
)

FORBIDDEN_MARKERS = (
    "/Users/",
    "materials/raw/",
    "docs/knowledge_base/",
    "docs/reports/",
)

FORBIDDEN_PUBLIC_TERMS = (
    re.compile(r"\btest[- ]only\b", re.IGNORECASE),
    re.compile(r"\bhidden[/ -](?:internal|tool|call|profile)", re.IGNORECASE),
    re.compile(r"\bcompatibility[/ -](?:test|tool|profile)", re.IGNORECASE),
    re.compile(r"\braw\s+rpc\b", re.IGNORECASE),
    re.compile(r"DATALENS_MCP_TEST_ONLY_REGISTRY"),
    re.compile(r"DATALENS_MCP_ALLOW_HIDDEN_TOOL_CALLS"),
    re.compile(r"\bapproved_plan_path\b"),
    re.compile(r"\bapproval_source\b"),
    re.compile(r"\bapproved\s*=\s*(?:true|false|1|0)\b", re.IGNORECASE),
    re.compile(r"\bapproved(?:\b|_)", re.IGNORECASE),
    re.compile(r"\bapproval(?:\b|_)", re.IGNORECASE),
    re.compile(r"safe_apply_plan_only_until_approved", re.IGNORECASE),
    re.compile(r"\b(?:separate\s+explicit\s+publish|guarded\s+(?:live-)?write)\s+approval\b", re.IGNORECASE),
)

PUBLIC_TEXT_SUFFIXES = frozenset({".md", ".json", ".toml", ".yaml", ".yml"})

LANGUAGE_PAIRS = (
    ("README.md", "README_en.md"),
    ("docs/README.md", "docs/README_en.md"),
    ("docs/access.md", "docs/access_en.md"),
    ("docs/tools.md", "docs/tools_en.md"),
    ("docs/usage-flow.md", "docs/usage-flow_en.md"),
    ("docs/sources.md", "docs/sources_en.md"),
    ("docs/codex_setup.md", "docs/codex_setup_en.md"),
    ("docs/configuration.md", "docs/configuration_en.md"),
    ("docs/local-only-safety-model.md", "docs/local-only-safety-model_en.md"),
    ("docs/route-policy.md", "docs/route-policy_en.md"),
    ("docs/safe-apply.md", "docs/safe-apply_en.md"),
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

REQUIRED_ACCESS_URLS = (
    "https://yandex.cloud/ru/docs/cli/quickstart",
    "https://yandex.cloud/ru/docs/organization/operations/organization-get-id",
    "https://yandex.cloud/ru/docs/iam/operations/iam-token/create-for-local",
    "https://yandex.cloud/ru/docs/datalens/security/roles",
    "https://yandex.cloud/ru/docs/datalens/operations/api-start",
)

ALLOWED_SOURCE_DOMAINS = frozenset({"api.datalens.tech", "github.com", "yandex.cloud"})

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
URL_RE = re.compile(r"https?://[^\s<>\"'`)}\]]+", re.IGNORECASE)
TOOL_NAME_RE = re.compile(r"\bdl_[a-z0-9_]+\b")


@dataclass(frozen=True)
class DocsConsistencyReport:
    ok: bool
    issues: tuple[str, ...]
    checked_files: tuple[str, ...]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _public_text_files() -> tuple[Path, ...]:
    paths: set[Path] = {
        ROOT / "README.md",
        ROOT / "README_en.md",
        ROOT / "AGENTS.md",
        ROOT / "SECURITY.md",
        ROOT / "THIRD_PARTY_NOTICES.md",
    }
    for directory in (ROOT / "docs", ROOT / "examples", ROOT / "templates"):
        if not directory.is_dir():
            continue
        paths.update(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.casefold() in PUBLIC_TEXT_SUFFIXES
        )
    return tuple(sorted(paths))


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
        if russian.count("\n## ") != english.count("\n## "):
            issues.append(f"{russian_rel} / {english_rel}: section structure is not bilingual")
    return issues


def _check_machine_provenance() -> tuple[list[str], tuple[str, ...]]:
    issues: list[str] = []
    provenance_path = ROOT / "src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json"
    trace_path = ROOT / "schemas/datalens-api/source-trace.json"
    packaged_trace_path = ROOT / "src/datalens_dev_mcp/assets/schemas/datalens-api/source-trace.json"
    lock_path = ROOT / "schemas/datalens-api/openapi.lock.json"
    packaged_lock_path = ROOT / "src/datalens_dev_mcp/assets/schemas/datalens-api/openapi.lock.json"
    checked = tuple(
        str(path.relative_to(ROOT))
        for path in (provenance_path, trace_path, packaged_trace_path, lock_path, packaged_lock_path)
    )
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        packaged_trace = json.loads(packaged_trace_path.read_text(encoding="utf-8"))
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        packaged_lock = json.loads(packaged_lock_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return [f"machine provenance could not be read: {exc}"], checked

    if trace != packaged_trace:
        issues.append("source-trace.json: source and packaged copies differ")
    if lock != packaged_lock:
        issues.append("openapi.lock.json: source and packaged copies differ")
    openapi_hashes = {
        str(trace.get("openapi_sha256") or ""),
        str(lock.get("openapi_sha256") or ""),
        str(lock.get("inventory_openapi_sha256") or ""),
    }
    if len(openapi_hashes) != 1 or "" in openapi_hashes:
        issues.append("machine provenance: OpenAPI hashes do not match")
    page_hash = str((provenance.get("snapshot") or {}).get("pages_content_sha256") or "")
    lock_page_hash = str((lock.get("content_hashes") or {}).get("pages_content_hash") or "")
    if not page_hash or page_hash != lock_page_hash:
        issues.append("machine provenance: documentation content hashes do not match")
    if provenance.get("license") != "CC-BY-4.0" or trace.get("license") != "CC-BY-4.0":
        issues.append("machine provenance: expected CC-BY-4.0 attribution is missing")
    knowledge_root = provenance_path.parent
    for filename in provenance.get("covered_files") or []:
        if not (knowledge_root / str(filename)).is_file():
            issues.append(f"machine provenance: missing covered knowledge file: {filename}")
    for rel in trace.get("generated_artifacts") or []:
        if not (ROOT / str(rel)).is_file():
            issues.append(f"machine provenance: missing generated API artifact: {rel}")
    return issues, checked


def _check_source_guides(provenance_values: tuple[str, ...]) -> list[str]:
    issues: list[str] = []
    required_phrases = {
        "docs/sources.md": (
            "использован для поиска страниц документации",
            "документация yandex cloud распространяется по cc by 4.0",
            "вход для компилятора схем",
        ),
        "docs/sources_en.md": (
            "used to discover documentation pages",
            "yandex cloud documentation is distributed under cc by 4.0",
            "compiler input",
        ),
    }
    for rel, phrases in required_phrases.items():
        text = _text(rel)
        visible_text = MARKDOWN_LINK_RE.sub(lambda match: match.group(0).split("](", 1)[0].lstrip("!)["), text)
        lowered = visible_text.casefold()
        for url in REQUIRED_SOURCE_URLS:
            if url not in text:
                issues.append(f"{rel}: missing required official source URL: {url}")
        for phrase in phrases:
            if phrase not in lowered:
                issues.append(f"{rel}: missing public source explanation: {phrase}")
        for value in provenance_values:
            if value and value in text:
                issues.append(f"{rel}: machine snapshot value must not be duplicated in user documentation")
        for url in URL_RE.findall(text):
            host = (urlsplit(url).hostname or "").casefold()
            if host not in ALLOWED_SOURCE_DOMAINS:
                issues.append(f"{rel}: non-official source domain in source map: {host or url}")
    return issues


def _check_access_guides() -> list[str]:
    issues: list[str] = []
    required_env = (
        "DATALENS_MCP_ENABLE_WRITES=1",
        "DATALENS_MCP_LIVE_ALLOW_SAVE=1",
        "DATALENS_MCP_LIVE_ALLOW_PUBLISH=1",
        "DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1",
        "DATALENS_MCP_ENABLE_EXPERT_RPC=0",
    )
    for rel in ("docs/access.md", "docs/access_en.md"):
        text = _text(rel)
        for url in REQUIRED_ACCESS_URLS:
            if url not in text:
                issues.append(f"{rel}: missing official access URL: {url}")
        for setting in required_env:
            if setting not in text:
                issues.append(f"{rel}: missing working access setting: {setting}")
        for category in (
            "missing_credentials",
            "expired_token",
            "organization_access_denied",
            "yc_reauthentication_required",
            "transport_failure",
            "api_failure",
        ):
            if category not in text:
                issues.append(f"{rel}: missing auth-probe category: {category}")
    return issues


def _check_public_tool_schemas() -> list[str]:
    issues: list[str] = []
    tools = list_tools()
    names = {str(tool.get("name") or "") for tool in tools}
    if names != STANDARD_TOOL_NAMES or len(tools) != 39:
        issues.append("tools/list: public tool surface is not the exact 39 STANDARD_TOOL_NAMES")
    forbidden_fields = {"approved", "approval_source", "approved_plan_path", "approve_guid_changes"}
    for tool in tools:
        properties = set(((tool.get("inputSchema") or {}).get("properties") or {}))
        leaked = sorted(properties & forbidden_fields)
        if leaked:
            issues.append(f"{tool.get('name')}: public schema exposes deprecated fields: {', '.join(leaked)}")
    rendered = json.dumps(tools, ensure_ascii=False).casefold()
    if "approval" in rendered or "approved" in rendered:
        issues.append("tools/list: public schema still exposes obsolete approval terminology")
    return issues


def _check_public_runtime_guidance() -> list[str]:
    issues: list[str] = []
    modes = (
        "delivery_intent",
        "source_route",
        "performance_budget",
        "api_contract",
        "tool_selection",
        "authoring_guidance",
    )
    forbidden = (
        re.compile(r"\bapprov(?:al|e|ed|ing)\b", re.IGNORECASE),
        re.compile(r"\btest[- ]only\b", re.IGNORECASE),
        re.compile(r"hidden compatibility", re.IGNORECASE),
        re.compile(r"raw\s+rpc", re.IGNORECASE),
    )
    for mode in modes:
        response = build_reference_response(mode=mode, query="safe apply publish", max_chars=12000, project_root=str(ROOT))
        rendered = json.dumps(response, ensure_ascii=False)
        for pattern in forbidden:
            if pattern.search(rendered):
                issues.append(f"dl_reference({mode}): public runtime guidance contains obsolete wording: {pattern.pattern}")
    return issues


def _check_public_content(provenance_values: tuple[str, ...]) -> tuple[list[str], tuple[str, ...]]:
    issues: list[str] = []
    checked: list[str] = []
    for path in _public_text_files():
        rel = str(path.relative_to(ROOT))
        checked.append(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_MARKERS:
            if marker.casefold() in text.casefold():
                issues.append(f"{rel}: forbidden private or legacy marker: {marker}")
        for pattern in FORBIDDEN_PUBLIC_TERMS:
            if pattern.search(text):
                issues.append(f"{rel}: internal implementation terminology is public: {pattern.pattern}")
        unknown_tools = sorted(set(TOOL_NAME_RE.findall(text)) - STANDARD_TOOL_NAMES)
        if unknown_tools:
            issues.append(f"{rel}: names non-public MCP tools: {', '.join(unknown_tools)}")
        for value in provenance_values:
            if value and value in text:
                issues.append(f"{rel}: machine snapshot value must not be duplicated in user documentation")
        if path.suffix.casefold() == ".md":
            issues.extend(_check_local_links(rel, text))
    return issues, tuple(checked)


def run_checks() -> DocsConsistencyReport:
    issues: list[str] = []
    for rel in ACTIVE_DOCS:
        if not (ROOT / rel).is_file():
            issues.append(f"{rel}: missing active documentation")
    for rel in LEGACY_ONBOARDING_DOCS:
        if (ROOT / rel).exists():
            issues.append(f"{rel}: obsolete onboarding duplicate must be removed")
    if (ROOT / "README_ru.md").exists():
        issues.append("README_ru.md: Russian default must live in README.md; legacy mirror should be removed")

    machine_issues, machine_checked = _check_machine_provenance()
    issues.extend(machine_issues)
    provenance = json.loads(
        (ROOT / "src/datalens_dev_mcp/assets/schemas/datalens-knowledge/PROVENANCE.json").read_text(
            encoding="utf-8"
        )
    )
    trace = json.loads((ROOT / "schemas/datalens-api/source-trace.json").read_text(encoding="utf-8"))
    provenance_values = (
        str((provenance.get("snapshot") or {}).get("generated_at") or ""),
        str((provenance.get("snapshot") or {}).get("pages_content_sha256") or ""),
        str(trace.get("openapi_sha256") or ""),
    )

    public_issues, public_checked = _check_public_content(provenance_values)
    issues.extend(public_issues)

    readme = _text("README.md")
    if "## Быстрый старт" not in readme or not any(
        heading in readme for heading in ("## Возможности", "## Что умеет сервер")
    ):
        issues.append("README.md: Russian must be the default public language")
    required_nav = (
        "Быстрый старт",
        "Доступ к DataLens",
        "Подключение",
        "Инструменты",
        "Сценарии",
        "Источники",
        "Безопасность",
        "English",
    )
    if any(item not in readme for item in required_nav):
        issues.append("README.md: incomplete Russian default navigation")
    for rel in ("README.md", "README_en.md"):
        if "dl_runtime_status" not in _text(rel):
            issues.append(f"{rel}: missing first runtime check")

    codex_docs = "\n".join((_text("docs/codex_setup.md"), _text("docs/codex_setup_en.md")))
    for required in (
        "[mcp_servers.",
        "codex mcp add",
        "codex mcp list",
        "/mcp",
        'default_tools_approval_mode = "approve"',
    ):
        if required not in codex_docs:
            issues.append(f"Codex setup guides: missing current Codex MCP marker: {required}")
    if '"mcpServers"' in codex_docs:
        issues.append("Codex setup guides: legacy JSON Codex configuration present")

    issues.extend(_check_language_pairs())
    issues.extend(_check_source_guides(provenance_values))
    issues.extend(_check_access_guides())
    issues.extend(_check_public_tool_schemas())
    issues.extend(_check_public_runtime_guidance())

    checked = tuple(sorted(set(public_checked + machine_checked)))
    return DocsConsistencyReport(ok=not issues, issues=tuple(sorted(set(issues))), checked_files=checked)


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
