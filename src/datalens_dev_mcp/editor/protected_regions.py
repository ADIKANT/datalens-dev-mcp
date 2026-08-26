from __future__ import annotations

import hashlib
import re
from typing import Any


PROTECTED_START_RE = re.compile(r"/\*\s*datalens-protected:(?P<id>[a-z0-9_-]+):start\s*\*/", re.I)
PROTECTED_END_TEMPLATE = r"/\*\s*datalens-protected:{region_id}:end\s*\*/"
FUNCTION_RE = re.compile(r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)\s*\{")
KNOWN_SHARED_HELPERS = frozenset(
    {
        "finiteOrNull",
        "safeRatio",
        "sumFinite",
        "averageFinite",
        "parseDateOnly",
        "toDateKey",
        "shiftDate",
        "startOfQuarter",
        "shiftMonth",
        "shiftYear",
        "createRender",
        "createChart",
    }
)


def build_protected_regions(tabs: dict[str, str]) -> list[dict[str, Any]]:
    explicit: list[dict[str, Any]] = []
    for tab, text in tabs.items():
        for match in PROTECTED_START_RE.finditer(text):
            region_id = match.group("id")
            end_match = re.search(
                PROTECTED_END_TEMPLATE.format(region_id=re.escape(region_id)),
                text[match.end() :],
                re.I,
            )
            if not end_match:
                continue
            start, end = match.end(), match.end() + end_match.start()
            explicit.append(_region(region_id, tab, "explicit_block", start, end, text, signature=region_id))
    if explicit:
        return explicit
    inferred: list[dict[str, Any]] = []
    prepare = tabs.get("prepare.js", "")
    for name, start, end in extract_named_functions(prepare):
        if name not in KNOWN_SHARED_HELPERS and len(inferred) >= 24:
            continue
        inferred.append(_region(f"function_{name}", "prepare.js", "function", start, end, prepare, signature=name))
    return inferred[:128]


def extract_named_functions(text: str) -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for match in FUNCTION_RE.finditer(text):
        brace = text.find("{", match.start())
        end = _balanced_block_end(text, brace)
        if end > brace:
            rows.append((match.group(1), match.start(), end))
    return rows


def function_signatures(text: str) -> list[str]:
    return [name for name, _, _ in extract_named_functions(text)]


def validate_protected_regions(
    before_tabs: dict[str, str],
    after_tabs: dict[str, str],
    regions: list[dict[str, Any]],
    *,
    template_migration: bool = False,
) -> dict[str, Any]:
    changes: list[dict[str, str]] = []
    for region in regions:
        tab = str(region.get("tab") or "")
        region_id = str(region.get("id") or "")
        signature = str(region.get("signature") or "")
        current = _locate_region(after_tabs.get(tab, ""), region)
        if current is None:
            changes.append({"region_id": region_id, "tab": tab, "reason": "protected_region_missing"})
            continue
        if _normalized_sha256(current) != str(region.get("hash") or ""):
            changes.append({"region_id": region_id, "tab": tab, "reason": "protected_region_hash_changed"})
    blocked = bool(changes) and not template_migration
    return {
        "ok": not blocked,
        "status": "migration_required" if blocked else "migration_authorized" if changes else "unchanged",
        "changed_regions": changes,
        "template_migration": bool(template_migration),
        "expanded_acceptance_required": bool(changes),
    }


def _locate_region(text: str, region: dict[str, Any]) -> str | None:
    kind = str(region.get("kind") or "")
    signature = str(region.get("signature") or "")
    if kind == "function":
        for name, start, end in extract_named_functions(text):
            if name == signature:
                return text[start:end]
        return None
    marker = re.search(rf"/\*\s*datalens-protected:{re.escape(signature)}:start\s*\*/", text, re.I)
    if not marker:
        return None
    end = re.search(PROTECTED_END_TEMPLATE.format(region_id=re.escape(signature)), text[marker.end() :], re.I)
    return text[marker.end() : marker.end() + end.start()] if end else None


def _region(
    region_id: str,
    tab: str,
    kind: str,
    start: int,
    end: int,
    text: str,
    *,
    signature: str,
) -> dict[str, Any]:
    return {
        "id": region_id,
        "tab": tab,
        "kind": kind,
        "start": start,
        "end": end,
        "hash": _normalized_sha256(text[start:end]),
        "policy": "immutable",
        "signature": signature,
    }


def _balanced_block_end(text: str, brace_start: int) -> int:
    if brace_start < 0:
        return -1
    depth = 0
    quote = ""
    escaped = False
    index = brace_start
    while index < len(text):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return -1


def _normalized_sha256(text: str) -> str:
    normalized = re.sub(r"\s+", " ", re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", text)).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
