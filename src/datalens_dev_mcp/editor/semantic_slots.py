from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any


SLOT_START_RE = re.compile(r"/\*\s*datalens-slot:(?P<id>[a-z0-9_-]+):(?P<kind>[a-z0-9_-]+):start\s*\*/", re.I)
SLOT_END_TEMPLATE = r"/\*\s*datalens-slot:{slot_id}:end\s*\*/"
SQL_RE = re.compile(r"sql_query\s*:\s*`(?P<body>[\s\S]*?)`", re.I)
PAGINATION_RE = re.compile(r"(?P<prefix>\b(?:limit|pageSize|page_size)\s*[:=]\s*)(?P<body>\d+)")
SOURCE_ALIAS_RE = re.compile(r"^\s{0,4}([A-Za-z_$][A-Za-z0-9_$]*)\s*:\s*\{", re.M)


@dataclass(frozen=True)
class SemanticSlot:
    id: str
    tab: str
    kind: str
    start: int
    end: int
    sha256: str
    discovery: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_semantic_slots(tabs: dict[str, str]) -> list[dict[str, Any]]:
    slots: list[SemanticSlot] = []
    for tab, text in tabs.items():
        slots.extend(_explicit_slots(tab, text))
    occupied = {(item.tab, item.start, item.end) for item in slots}
    for index, match in enumerate(SQL_RE.finditer(tabs.get("sources.js", "")), start=1):
        slot = _slot(
            slot_id="source_sql" if index == 1 else f"source_sql_{index}",
            tab="sources.js",
            kind="sql",
            start=match.start("body"),
            end=match.end("body"),
            text=tabs["sources.js"],
            discovery="sql_query_template",
        )
        if (slot.tab, slot.start, slot.end) not in occupied and not _overlaps(slot, slots):
            slots.append(slot)
    prepare = tabs.get("prepare.js", "")
    for index, match in enumerate(PAGINATION_RE.finditer(prepare), start=1):
        slot = _slot(
            slot_id="pagination" if index == 1 else f"pagination_{index}",
            tab="prepare.js",
            kind="integer",
            start=match.start("body"),
            end=match.end("body"),
            text=prepare,
            discovery="pagination_literal",
        )
        if not _overlaps(slot, slots):
            slots.append(slot)
    return [item.to_dict() for item in sorted(slots, key=lambda item: (item.tab, item.start, item.id))]


def source_aliases(sources_js: str) -> list[str]:
    return list(dict.fromkeys(match.group(1) for match in SOURCE_ALIAS_RE.finditer(sources_js)))


def apply_semantic_slot_updates(
    tabs: dict[str, str],
    slots: list[dict[str, Any]],
    updates: dict[str, Any],
) -> dict[str, str]:
    result = dict(tabs)
    by_tab: dict[str, list[tuple[dict[str, Any], str]]] = {}
    known = {str(item.get("id") or "") for item in slots}
    unknown = sorted(set(updates) - known)
    if unknown:
        raise ValueError(f"unknown semantic slots: {', '.join(unknown)}")
    for slot in slots:
        slot_id = str(slot.get("id") or "")
        if slot_id not in updates:
            continue
        tab = str(slot.get("tab") or "")
        text = result.get(tab)
        if text is None:
            raise ValueError(f"semantic slot {slot_id} references missing tab {tab}")
        start, end = int(slot.get("start") or 0), int(slot.get("end") or 0)
        if start < 0 or end < start or end > len(text):
            raise ValueError(f"semantic slot {slot_id} has an invalid range")
        current = text[start:end]
        if _sha256(current) != str(slot.get("sha256") or ""):
            raise ValueError(f"semantic slot {slot_id} is stale")
        replacement = str(updates[slot_id])
        if str(slot.get("kind") or "") == "integer" and not replacement.isdigit():
            raise ValueError(f"semantic slot {slot_id} requires an integer")
        by_tab.setdefault(tab, []).append((slot, replacement))
    for tab, rows in by_tab.items():
        text = result[tab]
        for slot, replacement in sorted(rows, key=lambda item: int(item[0]["start"]), reverse=True):
            start, end = int(slot["start"]), int(slot["end"])
            text = text[:start] + replacement + text[end:]
        result[tab] = text
    return result


def bounded_slot_projection(
    tabs: dict[str, str],
    slots: list[dict[str, Any]],
    *,
    resource_uri: str,
    max_fragments: int = 3,
    max_chars: int = 6_000,
) -> dict[str, Any]:
    fragments: list[dict[str, Any]] = []
    remaining = max(0, int(max_chars))
    for slot in slots[: max(0, int(max_fragments))]:
        text = tabs.get(str(slot.get("tab") or ""), "")
        start, end = int(slot.get("start") or 0), int(slot.get("end") or 0)
        excerpt_start = max(0, start - 120)
        excerpt_end = min(len(text), end + 120, excerpt_start + remaining)
        excerpt = text[excerpt_start:excerpt_end]
        remaining -= len(excerpt)
        fragments.append(
            {
                "slot_id": slot.get("id"),
                "tab": slot.get("tab"),
                "kind": slot.get("kind"),
                "sha256": slot.get("sha256"),
                "excerpt": excerpt,
            }
        )
        if remaining <= 0:
            break
    return {
        "slot_count": len(slots),
        "fragments": fragments,
        "fragment_count": len(fragments),
        "resource_uri": resource_uri,
        "full_content_inline": False,
    }


def _explicit_slots(tab: str, text: str) -> list[SemanticSlot]:
    rows: list[SemanticSlot] = []
    for match in SLOT_START_RE.finditer(text):
        slot_id = match.group("id")
        end_match = re.search(SLOT_END_TEMPLATE.format(slot_id=re.escape(slot_id)), text[match.end() :], re.I)
        if not end_match:
            continue
        start = match.end()
        end = match.end() + end_match.start()
        rows.append(_slot(slot_id, tab, match.group("kind"), start, end, text, "explicit_marker"))
    return rows


def _slot(slot_id: str, tab: str, kind: str, start: int, end: int, text: str, discovery: str) -> SemanticSlot:
    return SemanticSlot(slot_id, tab, kind, start, end, _sha256(text[start:end]), discovery)


def _overlaps(candidate: SemanticSlot, slots: list[SemanticSlot]) -> bool:
    return any(
        candidate.tab == item.tab and candidate.start < item.end and item.start < candidate.end
        for item in slots
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
