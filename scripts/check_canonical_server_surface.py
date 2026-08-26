#!/usr/bin/env python3
"""Fail closed when internal implementation versions reappear.

Git history and reviewed pull requests carry the implementation history. The
runtime exposes one canonical contract. External protocol and DataLens payload
versions remain allowed only where their upstream contracts require them.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}

VERSIONED_PATH_RE = re.compile(r"(?:^|[_-])v\d+(?:$|[._-])", re.IGNORECASE)
VERSIONED_SYMBOL_RE = re.compile(
    r"(?m)^\s*(?:(?:async\s+)?def\s+[A-Za-z_]\w*_v\d+\s*\(|"
    r"class\s+[A-Za-z_]\w*V\d+\b|[A-Z][A-Z0-9_]*_V\d+\s*=)"
)
VERSIONED_SCHEMA_ID_RE = re.compile(
    r'(?i)(?:"schema_id"\s*:\s*|SCHEMA_ID\s*=\s*)'
    r'"[^"]*(?:[._-]v\d+)[^"]*"'
)
FORBIDDEN_TEXT_PATTERNS = {
    "schema_version": re.compile(r"\bschema_version\b|\bSCHEMA_VERSION\b"),
    "versioned_route_policy": re.compile(r"\broute_selection_policy_v\d+\b", re.IGNORECASE),
    "versioned_dashboard_profile": re.compile(r"\bstandard_dashboard_v\d+\b", re.IGNORECASE),
    "versioned_delta_contract": re.compile(r"\bdelta[_-]?v\d+\b", re.IGNORECASE),
    "selectable_api_version_env": re.compile(r"\bDATALENS_API_VERSION\b"),
}

EXTERNAL_CONTRACT_PREFIXES = (
    "schemas/datalens-api/",
    "src/datalens_dev_mcp/assets/schemas/datalens-api/",
    "tests/fixtures/api_contracts/",
)
EXTERNAL_VERSION_FIELD_PATHS = {
    "src/datalens_dev_mcp/server.py",  # MCP initialize serverInfo.version
    "scripts/smoke_mcp_stdio.py",  # MCP initialize clientInfo.version
    "tests/integration_offline/test_mcp_stdio.py",  # MCP client fixture
    "tests/unit/test_current_api_corpus_hardening.py",  # official DataLens payload
    "tests/unit/test_incident_log_hardening.py",  # official DataLens readback field
    "tests/unit/test_practical_authoring_hardening.py",  # synthetic business data
    "templates/datalens/wizard/canonical_templates.json",  # official Wizard payload
    "src/datalens_dev_mcp/assets/templates/datalens/wizard/canonical_templates.json",
}
POLICY_LITERAL_PATHS = {"scripts/check_canonical_server_surface.py"}
VERSIONED_PATH_ALLOWLIST = {
    "docs/migration-v1-to-v2.md",  # bounded compatibility migration guide
}


def publication_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    paths: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8"))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"unsafe publication path: {relative}")
        if (ROOT / relative).is_file():
            paths.append(relative)
    return sorted(set(paths), key=lambda item: item.as_posix())


def _is_external_contract(relative: str) -> bool:
    return relative.startswith(EXTERNAL_CONTRACT_PREFIXES)


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def check_surface() -> dict[str, object]:
    issues: list[dict[str, str]] = []
    paths = publication_paths()
    for relative_path in paths:
        relative = relative_path.as_posix()
        if relative not in VERSIONED_PATH_ALLOWLIST and not _is_external_contract(relative) and any(
            VERSIONED_PATH_RE.search(part) for part in relative_path.parts
        ):
            issues.append({"rule": "versioned_internal_path", "path": relative})

        if relative_path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = _text(ROOT / relative_path)
        if content is None:
            continue

        if relative not in POLICY_LITERAL_PATHS:
            for rule, pattern in FORBIDDEN_TEXT_PATTERNS.items():
                if pattern.search(content):
                    issues.append({"rule": rule, "path": relative})
            if VERSIONED_SYMBOL_RE.search(content):
                issues.append({"rule": "versioned_python_symbol", "path": relative})
            if not _is_external_contract(relative) and VERSIONED_SCHEMA_ID_RE.search(content):
                issues.append({"rule": "versioned_internal_schema_id", "path": relative})

        internal_runtime_path = relative.startswith(("src/", "config/", "schemas/"))
        if (
            internal_runtime_path
            and not _is_external_contract(relative)
            and relative not in EXTERNAL_VERSION_FIELD_PATHS
            and re.search(r'"version"\s*:', content)
        ):
            issues.append({"rule": "internal_version_field", "path": relative})

    issues.extend(_contract_shape_issues())
    return {
        "ok": not issues,
        "checked_path_count": len(paths),
        "issues": issues,
        "external_version_allowlist": sorted(EXTERNAL_VERSION_FIELD_PATHS),
    }


def _contract_shape_issues() -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    required = (
        "config/route_selection_policy.json",
        "src/datalens_dev_mcp/assets/config/route_selection_policy.json",
        "templates/datalens/authoring_profiles/standard_dashboard/advanced_editor_runtime.js",
        "src/datalens_dev_mcp/assets/templates/datalens/authoring_profiles/standard_dashboard/advanced_editor_runtime.js",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            issues.append({"rule": "missing_canonical_artifact", "path": relative})

    profile_path = ROOT / "config" / "editor_authoring_profiles.json"
    try:
        profile_registry = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(
            {
                "rule": "invalid_authoring_profile_registry",
                "path": "config/editor_authoring_profiles.json",
                "detail": exc.__class__.__name__,
            }
        )
    else:
        profiles = profile_registry.get("profiles")
        if not isinstance(profiles, dict) or set(profiles) != {"standard_dashboard"}:
            issues.append(
                {
                    "rule": "multiple_authoring_profile_contracts",
                    "path": "config/editor_authoring_profiles.json",
                }
            )

    route_path = ROOT / "config" / "route_selection_policy.json"
    try:
        route_policy = json.loads(route_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(
            {
                "rule": "invalid_route_policy",
                "path": "config/route_selection_policy.json",
                "detail": exc.__class__.__name__,
            }
        )
    else:
        if route_policy.get("schema_id") != "route_selection_policy":
            issues.append(
                {
                    "rule": "noncanonical_route_policy_id",
                    "path": "config/route_selection_policy.json",
                }
            )
    return issues


def main() -> int:
    report = check_surface()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
