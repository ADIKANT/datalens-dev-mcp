from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from datalens_dev_mcp.editor.semantic_slots import discover_semantic_slots


@dataclass(frozen=True)
class AnchorMatch:
    kind: str
    value: Any
    path: tuple[Any, ...] = ()
    start: int = 0
    end: int = 0


class PatchAnchorError(ValueError):
    pass


def resolve_anchor(document: Any, anchor: dict[str, Any], *, tab: str = "") -> AnchorMatch:
    matches = resolve_anchor_matches(document, anchor, tab=tab)
    if len(matches) != 1:
        raise PatchAnchorError(f"patch anchor must resolve exactly once; resolved {len(matches)} times")
    return matches[0]


def resolve_anchor_matches(document: Any, anchor: dict[str, Any], *, tab: str = "") -> list[AnchorMatch]:
    kind = str(anchor.get("kind") or "")
    if kind == "semantic_slot":
        if not isinstance(document, str):
            return []
        slot_id = str(anchor.get("slot_id") or "")
        rows = [
            item
            for item in discover_semantic_slots({tab or "content": document})
            if str(item.get("id") or "") == slot_id
        ]
        return [
            AnchorMatch(
                kind=kind,
                value=document[int(item["start"]) : int(item["end"])],
                start=int(item["start"]),
                end=int(item["end"]),
            )
            for item in rows
        ]
    if kind == "json_pointer":
        path = _decode_pointer(str(anchor.get("pointer") or ""))
        found, value = _get_path(document, path)
        return [AnchorMatch(kind=kind, value=value, path=path)] if found else []
    if kind == "semantic_widget":
        identity = str(anchor.get("object_id") or anchor.get("widget_id") or "")
        candidates = _find_identity_paths(document, identity)
        suffix = _decode_pointer(str(anchor.get("pointer") or ""))
        matches: list[AnchorMatch] = []
        for base_path in candidates:
            path = (*base_path, *suffix)
            found, value = _get_path(document, path)
            if found:
                matches.append(AnchorMatch(kind=kind, value=value, path=path))
        return matches
    raise PatchAnchorError(f"unsupported patch anchor kind: {kind}")


def replace_anchor(document: Any, match: AnchorMatch, value: Any) -> Any:
    if match.kind == "semantic_slot":
        if not isinstance(document, str):
            raise PatchAnchorError("semantic slot replacement requires text")
        return document[: match.start] + str(value) + document[match.end :]
    root = _deepcopy_json(document)
    if not match.path:
        return _deepcopy_json(value)
    parent = root
    for token in match.path[:-1]:
        parent = parent[token]
    parent[match.path[-1]] = _deepcopy_json(value)
    return root


def anchor_hash(value: Any) -> str:
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decode_pointer(pointer: str) -> tuple[Any, ...]:
    if pointer in {"", "/"}:
        return ()
    if not pointer.startswith("/"):
        raise PatchAnchorError("JSON Pointer must start with /")
    tokens: list[Any] = []
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        tokens.append(int(token) if token.isdigit() else token)
    return tuple(tokens)


def _get_path(document: Any, path: tuple[Any, ...]) -> tuple[bool, Any]:
    value = document
    try:
        for token in path:
            value = value[token]
    except (KeyError, IndexError, TypeError):
        return False, None
    return True, value


def _find_identity_paths(document: Any, identity: str, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    if isinstance(document, dict):
        values = {str(document.get(key) or "") for key in ("id", "objectId", "widgetId", "chartId")}
        if identity and identity in values:
            rows.append(path)
        for key, value in document.items():
            rows.extend(_find_identity_paths(value, identity, (*path, key)))
    elif isinstance(document, list):
        for index, value in enumerate(document):
            rows.extend(_find_identity_paths(value, identity, (*path, index)))
    return rows


def _deepcopy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))
