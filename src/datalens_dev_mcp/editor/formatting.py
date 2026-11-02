"""Readable Editor source at authoring and mutation boundaries."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import jsbeautifier
import tree_sitter_javascript
from tree_sitter import Language, Parser

from datalens_dev_mcp.api.errors import InputContractError
from datalens_dev_mcp.editor.validation import TAB_FIELDS

EDITOR_TYPES = frozenset({"editor_chart", "advanced_chart", "advanced-chart_node", "table_node",
                          "d3_node", "markdown_node", "control_node"})
_JS_FIELDS = frozenset(TAB_FIELDS.values()) - {"meta"}
_LANGUAGE = Language(tree_sitter_javascript.language())


def _syntax(source: str) -> list[tuple[str, int, bytes | None]]:
    root = Parser(_LANGUAGE).parse(source.encode("utf-8")).root_node
    if root.has_error:
        raise InputContractError("Cannot safely format Editor JavaScript: syntax is invalid or unsupported")
    result = []
    pending = [root]
    while pending:
        node = pending.pop()
        if node.type == "comment":
            continue
        children = [child for child in node.children if child.type != "comment"]
        result.append((node.type, len(children), None if children else node.text))
        pending.extend(reversed(children))
    return result


def format_editor_source(source: str) -> str:
    options = jsbeautifier.default_options()
    options.indent_size = 2
    options.wrap_line_length = 100
    options.brace_style = "collapse"
    options.max_preserve_newlines = 2
    options.end_with_newline = source.endswith("\n")
    # Never unpack/evaluate code or rewrite string escapes (SQL, HTML, regex).
    options.eval_code = False
    options.unescape_strings = False
    formatted = source
    # Wrapped expressions can settle their indentation on a second pass.
    for _ in range(4):
        candidate = jsbeautifier.beautify(formatted, options)
        if candidate == formatted:
            break
        formatted = candidate
    else:
        raise InputContractError("Editor JavaScript formatting did not stabilize; no source was saved")
    if formatted != source and _syntax(source) != _syntax(formatted):
        raise InputContractError(
            "Editor formatting would change JavaScript syntax; make statement boundaries explicit before saving"
        )
    return formatted


def format_editor_payload(payload: dict[str, Any], object_type: str) -> dict[str, Any]:
    """Copy and format only source explicitly supplied in known Editor carriers."""
    result = deepcopy(payload)
    if object_type not in EDITOR_TYPES:
        return result
    tabs = result.get("tabs")
    if isinstance(tabs, dict):
        for filename, source in tabs.items():
            if TAB_FIELDS.get(filename) in _JS_FIELDS and isinstance(source, str):
                tabs[filename] = format_editor_source(source)
    entry = result.get("entry", result)
    data = entry.get("data") if isinstance(entry, dict) else None
    if isinstance(data, dict):
        for field, source in data.items():
            if field in _JS_FIELDS and isinstance(source, str):
                data[field] = format_editor_source(source)
    if isinstance(result.get("snapshot"), dict):
        result["snapshot"] = format_editor_payload(result["snapshot"], object_type)
    return result
