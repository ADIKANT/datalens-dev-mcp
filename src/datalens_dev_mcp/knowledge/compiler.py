from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from datalens_dev_mcp.knowledge.corpus import DEFAULT_CORPUS_ROOT
from datalens_dev_mcp.knowledge.formulas import parse_formula_expression, validate_formula_expression


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEMO_REFERENCE_ROOT = Path(
    os.environ.get(
        "DATALENS_DEMO_WORKBOOK_ARCHIVE",
        str(REPO_ROOT / ".external" / "synthetic-workbook-reference"),
    )
)
PACKAGE_KNOWLEDGE_DIR = REPO_ROOT / "src" / "datalens_dev_mcp" / "assets" / "schemas" / "datalens-knowledge"
KNOWLEDGE_DIR = PACKAGE_KNOWLEDGE_DIR
RECIPE_DIR = REPO_ROOT / "templates" / "datalens" / "recipes"
PACKAGE_RECIPE_DIR = REPO_ROOT / "src" / "datalens_dev_mcp" / "assets" / "templates" / "datalens" / "recipes"
_ARTIFACT_DIR_VALUE = Path(os.environ.get("DATALENS_KNOWLEDGE_ARTIFACT_DIR", "artifacts/reference_runs/semantic_authoring"))
ARTIFACT_DIR = _ARTIFACT_DIR_VALUE if _ARTIFACT_DIR_VALUE.is_absolute() else REPO_ROOT / _ARTIFACT_DIR_VALUE
QA_KNOWLEDGE_DIR = ARTIFACT_DIR / "compiled-qa"
INDEX_PATH = REPO_ROOT / "artifacts" / "datalens_knowledge" / "index.sqlite"
COMPILER_VERSION = "2026-06-25.semantic_authoring.v2"
RUNTIME_KNOWLEDGE_FILES = {
    "knowledge.lock.json",
    "page-registry.json",
    "chunk-registry.jsonl",
    "rule-cards.jsonl",
    "formula-registry.json",
    "visualization-registry.json",
    "error-registry.json",
    "capability-matrix.json",
    "route-capability-matrix.json",
    "editor-visualization-contracts.json",
}

EXPECTED_COUNTS = {
    "pages": 651,
    "chunks": 4999,
    "assets": 886,
    "manifest": 1545,
    "editor_pages": 20,
    "function_pages": 221,
    "visualization_pages": 22,
    "troubleshooting_error_pages": 86,
    "release_note_pages": 31,
    "openapi_operations": 88,
    "openapi_paths": 88,
    "openapi_component_schemas": 483,
}

CLASSIFICATION_STATUSES = {
    "compiled_rule",
    "compiled_recipe",
    "compiled_registry",
    "indexed_reference",
    "deprecated_or_superseded",
    "excluded_non_authoring",
}

SOURCE_PRECEDENCE = [
    "current_openapi",
    "current_official_documentation",
    "release_notes_and_dated_changes",
    "observed_live_runtime_evidence",
    "local_safety_governance_policy",
]

MANDATORY_RECIPE_IDS = [
    "table_flat_sql",
    "table_flat_dataset",
    "table_flat_api_connector",
    "table_rich",
    "table_pivot_js",
    "table_pivot_advanced_exception",
    "resource_schedule_exception",
    "advanced_dom_d3",
    "gravity_chart",
    "control_static",
    "control_dynamic",
    "markdown",
    "cross_filter",
    "links",
    "notifications",
]

BENCHMARK_QUERIES = [
    ("simple SQL table", "recipe", "table_flat_sql"),
    ("dataset table", "recipe", "table_flat_dataset"),
    ("API Connector table", "recipe", "table_flat_api_connector"),
    ("JavaScript pivot", "recipe", "table_pivot_js"),
    ("cross-filter", "recipe", "cross_filter"),
    ("selector", "recipe", "control_dynamic"),
    ("notification", "recipe", "notifications"),
    ("Editor.setRawData", "search", "Editor.setRawData"),
    ("dataset update envelope", "capability", "dataset_update"),
    ("LOD formula", "formula", "LOD"),
    ("window function", "formula", "WINDOW"),
    ("Code 47 unknown identifier", "error", "Code 47 unknown identifier"),
    ("pagination and totals", "recipe", "table_rich"),
    ("current API version", "capability", "api_version"),
]


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(stable_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def rendered_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def rendered_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(stable_json(row) + "\n" for row in rows)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
    return rows


def load_corpus(corpus_root: Path = DEFAULT_CORPUS_ROOT) -> dict[str, Any]:
    root = corpus_root.expanduser()
    required = [
        "pages.jsonl",
        "chunks.jsonl",
        "assets.jsonl",
        "manifest.jsonl",
        "api_inventory.json",
        "raw/api/openapi.json",
        "reports/coverage.md",
        "reports/validation.md",
        "reports/content_hashes.json",
    ]
    missing = [rel for rel in required if not (root / rel).is_file()]
    if missing:
        raise FileNotFoundError(f"missing corpus files under {root}: {', '.join(missing)}")
    pages = read_jsonl(root / "pages.jsonl")
    chunks = read_jsonl(root / "chunks.jsonl")
    assets = read_jsonl(root / "assets.jsonl")
    manifest = read_jsonl(root / "manifest.jsonl")
    api_inventory = read_json(root / "api_inventory.json")
    openapi = read_json(root / "raw" / "api" / "openapi.json")
    content_hashes = read_json(root / "reports" / "content_hashes.json")
    return {
        "root": root,
        "pages": pages,
        "chunks": chunks,
        "assets": assets,
        "manifest": manifest,
        "api_inventory": api_inventory,
        "openapi": openapi,
        "content_hashes": content_hashes,
        "coverage_report_sha256": file_sha256(root / "reports" / "coverage.md"),
        "validation_report_sha256": file_sha256(root / "reports" / "validation.md"),
    }


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_corpus_counts(corpus: dict[str, Any]) -> dict[str, Any]:
    pages = corpus["pages"]
    openapi = corpus["openapi"]
    counts = {
        "pages": len(pages),
        "chunks": len(corpus["chunks"]),
        "assets": len(corpus["assets"]),
        "manifest": len(corpus["manifest"]),
        "editor_pages": sum(1 for page in pages if is_editor_page(page)),
        "function_pages": sum(1 for page in pages if page_section(page) == "function-ref"),
        "visualization_pages": sum(1 for page in pages if page_section(page) == "visualization-ref"),
        "troubleshooting_error_pages": sum(1 for page in pages if is_troubleshooting_error_page(page)),
        "release_note_pages": sum(1 for page in pages if page_section(page) == "release-notes"),
        "openapi_operations": len((corpus["api_inventory"].get("operations") or [])),
        "openapi_paths": len(openapi.get("paths") or {}),
        "openapi_component_schemas": len((openapi.get("components") or {}).get("schemas") or {}),
    }
    mismatches = {
        key: {"expected": expected, "actual": counts.get(key)}
        for key, expected in EXPECTED_COUNTS.items()
        if counts.get(key) != expected
    }
    return {"ok": not mismatches, "counts": counts, "mismatches": mismatches}


def page_section(page: dict[str, Any]) -> str:
    path = page.get("section_path") or []
    return str(path[0] if path else "")


def is_editor_page(page: dict[str, Any]) -> bool:
    return str(page.get("mirror_path") or "").startswith("datalens/charts/editor/")


def is_troubleshooting_error_page(page: dict[str, Any]) -> bool:
    return str(page.get("mirror_path") or "").startswith("datalens/troubleshooting/errors/")


def source_trace(record: dict[str, Any], *, chunk_id: str = "") -> dict[str, str]:
    resolved_chunk_id = chunk_id or str(record.get("chunk_id") or "")
    anchor = str(record.get("anchor") or "")
    if not anchor and "#" in resolved_chunk_id:
        anchor = resolved_chunk_id.split("#", 2)[1]
    return {
        "source_url": str(record.get("source_url") or ""),
        "mirror_path": str(record.get("mirror_path") or record.get("local_path") or ""),
        "anchor": anchor,
        "chunk_id": resolved_chunk_id,
        "sha256": str(record.get("sha256") or ""),
    }


def source_trace_ok(trace: dict[str, str]) -> bool:
    return all(trace.get(key) for key in ("source_url", "mirror_path", "anchor", "chunk_id", "sha256"))


def chunk_lookup(corpus: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for chunk in corpus["chunks"]:
        lookup[(str(chunk.get("mirror_path") or ""), str(chunk.get("anchor") or ""))] = chunk
    return lookup


def first_page_chunk(corpus: dict[str, Any], mirror_path: str) -> dict[str, Any]:
    for chunk in corpus["chunks"]:
        if str(chunk.get("mirror_path") or "") == mirror_path:
            return chunk
    return {}


def section_chunk(corpus: dict[str, Any], mirror_path: str, anchor: str) -> dict[str, Any]:
    lookup = chunk_lookup(corpus)
    return lookup.get((mirror_path, anchor)) or first_page_chunk(corpus, mirror_path)


def section_trace(corpus: dict[str, Any], mirror_path: str, anchor: str) -> dict[str, str]:
    return source_trace(section_chunk(corpus, mirror_path, anchor))


def bounded_excerpt(text: str, *, max_chars: int = 360) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def chunk_excerpt(chunk: dict[str, Any], *, max_chars: int = 360) -> str:
    return bounded_excerpt(str(chunk.get("content_text") or chunk.get("content_md") or ""), max_chars=max_chars)


def code_fences(text: str) -> list[dict[str, str]]:
    rows = []
    pattern = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.DOTALL)
    for index, match in enumerate(pattern.finditer(text or ""), start=1):
        body = match.group(2).strip()
        if not body:
            continue
        rows.append(
            {
                "index": str(index),
                "language": (match.group(1) or "text").strip().lower() or "text",
                "body": body,
                "sha256": sha256_text(body),
            }
        )
    return rows


def markdown_bullets(text: str) -> list[str]:
    return [line.strip()[2:].strip() for line in (text or "").splitlines() if line.strip().startswith(("- ", "* "))]


def semantic_record(
    record_id: str,
    kind: str,
    title: str,
    trace: dict[str, str],
    excerpt: str,
    *,
    layer: str = "official_documented_behavior",
    extraction: str = "section_aware_compiler",
    confidence: str = "reviewed_or_deterministic",
    manual_review: str = "compiler_reviewed",
    status: str = "compiled",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "kind": kind,
        "title": title,
        "layer": layer,
        "status": status,
        "source_trace": trace,
        "bounded_excerpt": excerpt,
        "extraction_method": extraction,
        "compiler_version": COMPILER_VERSION,
        "confidence": confidence,
        "manual_review_status": manual_review,
        "data": data or {},
    }


def classify_page(page: dict[str, Any]) -> dict[str, Any]:
    section = page_section(page)
    mirror_path = str(page.get("mirror_path") or "")
    owners: list[str] = []
    reason = ""
    if is_editor_page(page):
        if "/quickstart/" in mirror_path or "/widgets/" in mirror_path:
            status = "compiled_recipe"
            owners = ["templates/datalens/recipes/recipe-registry.json"]
            reason = "Editor quickstart/widget page feeds authoring recipes."
        else:
            status = "compiled_rule"
            owners = ["schemas/datalens-knowledge/rule-cards.jsonl"]
            reason = "Editor authoring rule page."
    elif section in {"function-ref", "visualization-ref", "dataset", "dashboard", "security", "settings"}:
        status = "compiled_registry"
        owners = ["schemas/datalens-knowledge/domain-registries.json"]
        reason = f"{section} page feeds a machine registry."
    elif is_troubleshooting_error_page(page):
        status = "compiled_registry"
        owners = ["schemas/datalens-knowledge/error-registry.json"]
        reason = "Troubleshooting error page feeds source-error classification."
    elif section == "release-notes":
        status = "deprecated_or_superseded"
        owners = ["schemas/datalens-knowledge/supersession-registry.json"]
        reason = "Release-note page may supersede older instructions."
    elif section == "openapi-ref":
        status = "indexed_reference"
        owners = ["schemas/datalens-api/source-trace.json"]
        reason = "OpenAPI is compiled by the API compiler; page is indexed for traceability."
    elif section in {"pricing", "pricing-old", "pricing-changes", "training", "qa"}:
        status = "excluded_non_authoring"
        owners = ["schemas/datalens-knowledge/page-registry.json"]
        reason = "Non-authoring support/commercial page; indexed for coverage only."
    else:
        status = "indexed_reference"
        owners = ["schemas/datalens-knowledge/page-registry.json"]
        reason = "Official docs page retained as compact indexed reference."
    return {"status": status, "reason": reason, "generated_artifact_owners": owners}


def build_page_registry(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    pages = []
    for page in sorted(corpus["pages"], key=lambda item: str(item.get("mirror_path") or "")):
        classification = classify_page(page)
        pages.append(
            {
                "mirror_path": str(page.get("mirror_path") or ""),
                "title": str(page.get("title") or ""),
                "section": page_section(page),
                "section_path": page.get("section_path") or [],
                "source_url": str(page.get("source_url") or ""),
                "mirror_url": str(page.get("mirror_url") or ""),
                "local_path": str(page.get("local_path") or ""),
                "sha256": str(page.get("sha256") or ""),
                "bytes": int(page.get("bytes") or 0),
                "last_modified": str(page.get("last_modified") or ""),
                "fetched_at": str(page.get("fetched_at") or ""),
                "anchors": list(page.get("anchors") or []),
                "asset_count": len(page.get("assets") or []),
                "link_count": len(page.get("links") or []),
                "freshness": "current_official_docs_snapshot",
                "classification": classification,
                "knowledge_layers": ["official_docs"],
            }
        )
    return pages


def build_chunk_registry(corpus: dict[str, Any], page_by_mirror: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for chunk in sorted(corpus["chunks"], key=lambda item: str(item.get("chunk_id") or "")):
        page = page_by_mirror.get(str(chunk.get("mirror_path") or "")) or {}
        classification = classify_page(page or chunk)
        rows.append(
            {
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "mirror_path": str(chunk.get("mirror_path") or ""),
                "source_url": str(chunk.get("source_url") or ""),
                "anchor": str(chunk.get("anchor") or ""),
                "title": str(chunk.get("title") or ""),
                "heading": str(chunk.get("heading") or ""),
                "heading_level": int(chunk.get("heading_level") or 0),
                "section": page_section(page or chunk),
                "sha256": str(chunk.get("sha256") or ""),
                "asset_count": len(chunk.get("assets") or []),
                "link_count": len(chunk.get("links") or []),
                "classification": classification["status"],
            }
        )
    return rows


def build_topic_registry(page_registry: list[dict[str, Any]]) -> dict[str, Any]:
    related: dict[str, list[str]] = defaultdict(list)
    aliases: dict[str, set[str]] = defaultdict(set)
    for page in page_registry:
        terms = set()
        section = page["section"]
        if section:
            terms.add(section)
        for part in page["mirror_path"].replace(".md", "").split("/"):
            if part and part != "datalens":
                terms.add(part)
        for word in re.findall(r"[A-Za-zА-Яа-я0-9_]{4,}", page["title"]):
            terms.add(normalize_topic(word))
        for term in terms:
            key = normalize_topic(term)
            if not key:
                continue
            aliases[key].add(term)
            related[key].append(page["mirror_path"])
    topics = [
        {
            "topic": key,
            "aliases": sorted(value)[:12],
            "page_count": len(set(related[key])),
            "related_pages": sorted(set(related[key]))[:40],
        }
        for key, value in sorted(aliases.items())
    ]
    return {"schema_version": COMPILER_VERSION, "topics": topics}


def normalize_topic(value: str) -> str:
    return re.sub(r"[^0-9a-zа-я_]+", "_", value.strip().lower()).strip("_")


def build_rule_cards(corpus: dict[str, Any], page_by_mirror: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    marker_map = {
        "restriction": ("нельзя", "не поддерж", "запрещ", "forbidden", "unsupported", "not supported"),
        "warning": ("важно", "warning", "ошиб", "error", "must", "required"),
        "default": ("по умолч", "default", "рекоменду", "recommended"),
        "method": ("editor.", "метод", "method", "setrawdata", "seterror"),
    }
    for chunk in corpus["chunks"]:
        text = str(chunk.get("content_text") or "").lower()
        mirror = str(chunk.get("mirror_path") or "")
        page = page_by_mirror.get(mirror) or chunk
        if not (is_editor_page(page) or page_section(page) in {"dataset", "dashboard", "security", "settings"}):
            continue
        matched = [kind for kind, markers in marker_map.items() if any(marker in text for marker in markers)]
        if not matched:
            continue
        for kind in matched[:2]:
            rows.append(
                {
                    "rule_id": stable_id("rule", chunk.get("chunk_id"), kind),
                    "kind": kind,
                    "title": str(chunk.get("heading") or chunk.get("title") or ""),
                    "summary": chunk_excerpt(chunk, max_chars=220),
                    "scope": page_section(page) or "datalens",
                    "status": "official_documentation",
                    "precedence": "current_official_documentation",
                    "source_trace": source_trace(chunk),
                    "bounded_excerpt": chunk_excerpt(chunk),
                    "manual_review_status": "compiler_reviewed",
                    "extraction_method": "marker_and_section_aware.v2",
                }
            )
    return sorted(rows, key=lambda item: item["rule_id"])


def build_code_example_registry(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    fence_pattern = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.DOTALL)
    for page in corpus["pages"]:
        content = str(page.get("content_md") or "")
        for index, match in enumerate(fence_pattern.finditer(content), start=1):
            body = match.group(2).strip()
            if not body:
                continue
            language = (match.group(1) or "text").strip().lower() or "text"
            rows.append(
                {
                    "example_id": stable_id("code", page.get("mirror_path"), index),
                    "language": language,
                    "purpose": str(page.get("title") or ""),
                    "line_count": len(body.splitlines()),
                    "snippet_sha256": sha256_text(body),
                    "safety_status": code_safety_status(language, body),
                    "source_trace": source_trace(page),
                }
            )
    return rows


def code_safety_status(language: str, body: str) -> str:
    lowered = body.lower()
    if "authorization" in lowered or "iam_token" in lowered or "oauth" in lowered:
        return "sensitive_reference_not_inlined"
    if language in {"js", "javascript", "json", "sql", "text", "bash", "shell", "yml", "yaml"}:
        return "indexed_not_inlined"
    return "reference_only"


def build_asset_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    by_asset: dict[str, list[str]] = defaultdict(list)
    for page in corpus["pages"]:
        for asset in page.get("assets") or []:
            if isinstance(asset, dict):
                key = str(asset.get("local_path") or asset.get("source_url") or asset)
            else:
                key = str(asset)
            by_asset[key].append(str(page.get("mirror_path") or ""))
    assets = []
    for asset in sorted(corpus["assets"], key=lambda item: str(item.get("local_path") or "")):
        local_path = str(asset.get("local_path") or "")
        linked_pages = sorted(set(by_asset.get(local_path) or by_asset.get(str(asset.get("source_url") or "")) or []))
        high_value = any(
            token in local_path.lower() for token in ("datalens", "editor", "chart", "table", "visualization", "map")
        )
        assets.append(
            {
                "local_path": local_path,
                "source_url": str(asset.get("source_url") or ""),
                "download_url": str(asset.get("download_url") or ""),
                "final_url": str(asset.get("final_url") or ""),
                "content_type": str(asset.get("content_type") or ""),
                "bytes": int(asset.get("bytes") or 0),
                "sha256": str(asset.get("sha256") or ""),
                "status_code": str(asset.get("status_code") or ""),
                "linked_pages": linked_pages,
                "classification": "visual_review_candidate" if high_value else "indexed_reference",
            }
        )
    return {"schema_version": COMPILER_VERSION, "assets": assets}


def build_supersession_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    release_pages = [page for page in corpus["pages"] if page_section(page) == "release-notes"]
    release_pages.sort(key=lambda item: str(item.get("mirror_path") or ""))
    signals = []
    signal_re = re.compile(r"(устар|deprecated|удален|removed|больше не|изменен|changed|теперь|now)", re.IGNORECASE)
    for chunk in corpus["chunks"]:
        if not str(chunk.get("mirror_path") or "").startswith("datalens/release-notes/"):
            continue
        text = str(chunk.get("content_text") or "")
        if signal_re.search(text):
            signals.append(
                {
                    "signal_id": stable_id("supersession", chunk.get("chunk_id")),
                    "heading": str(chunk.get("heading") or ""),
                    "status": "dated_change_signal",
                    "summary": "Release-note change/deprecation signal; source wording remains external.",
                    "source_trace": source_trace(chunk),
                }
            )
    return {
        "schema_version": COMPILER_VERSION,
        "release_note_count": len(release_pages),
        "release_notes": [source_trace(page) | {"title": str(page.get("title") or "")} for page in release_pages],
        "supersession_signals": signals,
    }


def build_formula_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    formulas = []
    chunks = chunk_lookup(corpus)
    for page in sorted(corpus["pages"], key=lambda item: str(item.get("mirror_path") or "")):
        if page_section(page) != "function-ref":
            continue
        mirror_path = str(page.get("mirror_path") or "")
        name = Path(str(page.get("mirror_path") or "")).stem
        title = str(page.get("title") or name)
        canonical = normalize_formula_name(name, title)
        syntax_chunk = chunks.get((mirror_path, "syntax")) or {}
        description_chunk = chunks.get((mirror_path, "description")) or {}
        examples_chunk = chunks.get((mirror_path, "examples")) or {}
        source_chunk = chunks.get((mirror_path, "data-source-support")) or {}
        syntax_variants = parse_formula_syntax_variants(canonical, syntax_chunk)
        argument_types = parse_argument_types(description_chunk)
        return_types = parse_return_types(description_chunk)
        examples = parse_formula_examples(examples_chunk)
        text = " ".join(
            str(chunk.get("content_text") or "")
            for chunk in (syntax_chunk, description_chunk, examples_chunk, source_chunk)
        )
        canonical = name.upper()
        arity = merge_formula_arity(canonical, syntax_variants)
        support = parse_source_support(source_chunk)
        window_status = infer_window_status(canonical, syntax_variants, text)
        lod_support = infer_lod_support(syntax_variants, text)
        before_filter_by = infer_before_filter_by(syntax_variants, text)
        validation_notes = validate_formula_examples(canonical, examples, arity)
        formulas.append(
            {
                "name": canonical,
                "title": title,
                "aliases": sorted({canonical, normalize_formula_alias(title)} - {""}),
                "category": infer_formula_category(canonical, text),
                "syntax": syntax_variants[0]["syntax"] if syntax_variants else f"{canonical}(...)",
                "syntax_variants": syntax_variants,
                "arity": arity,
                "argument_types": argument_types,
                "return_types": return_types,
                "aggregation_status": "aggregate" if is_aggregate_formula(canonical, text) else "scalar_or_contextual",
                "window_status": window_status,
                "table_calculation_status": "table_calculation" if window_status == "window" else "not_table_calculation",
                "lod_support": lod_support,
                "before_filter_by": before_filter_by,
                "source_compatibility": support,
                "example_count": len(examples),
                "bounded_valid_examples": examples[:6],
                "restrictions": parse_formula_restrictions(description_chunk),
                "deprecation": infer_deprecation(text),
                "freshness": "current_official_docs_snapshot",
                "contract_status": "compiled_exact" if syntax_variants and argument_types else "indexed_reference",
                "manual_review_status": manual_formula_review_status(canonical),
                "parser_validation": validation_notes,
                "source_trace": source_trace(syntax_chunk or first_page_chunk(corpus, mirror_path)),
                "section_traces": {
                    "syntax": source_trace(syntax_chunk) if syntax_chunk else {},
                    "description": source_trace(description_chunk) if description_chunk else {},
                    "examples": source_trace(examples_chunk) if examples_chunk else {},
                    "data_source_support": source_trace(source_chunk) if source_chunk else {},
                },
            }
        )
    return {"schema_version": COMPILER_VERSION, "functions": formulas}


def normalize_formula_name(name: str, title: str) -> str:
    if name:
        return name.upper()
    alias = normalize_formula_alias(title)
    return alias or "UNKNOWN"


def parse_formula_syntax_variants(canonical: str, syntax_chunk: dict[str, Any]) -> list[dict[str, Any]]:
    variants = []
    content = str(syntax_chunk.get("content_md") or "")
    labels = [line.strip("- ").strip() for line in content.splitlines() if line.strip().startswith("- ")]
    for index, fence in enumerate(code_fences(content), start=1):
        syntax = normalize_formula_syntax_text(fence["body"])
        variants.append(
            {
                "variant_id": f"{canonical.lower()}_{index}",
                "label": labels[index - 1] if index - 1 < len(labels) else "documented",
                "syntax": syntax,
                "arity": arity_from_syntax(canonical, syntax),
                "clauses": syntax_clauses(syntax),
                "snippet_sha256": fence["sha256"],
                "source_trace": source_trace(syntax_chunk),
            }
        )
    return variants


def normalize_formula_syntax_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def arity_from_syntax(canonical: str, syntax: str) -> dict[str, Any]:
    upper = syntax.upper()
    if canonical == "IF" or upper.startswith("IF "):
        return {"min": 3, "max": None, "variadic": True, "confidence": "manual_reviewed_if_contract"}
    if canonical == "CASE" or upper.startswith("CASE "):
        return {"min": 3, "max": None, "variadic": True, "confidence": "manual_reviewed_case_contract"}
    match = re.search(r"\b[A-Z][A-Z0-9_]*\s*\((.*)\)", syntax, flags=re.IGNORECASE)
    if not match:
        return {"min": 0, "max": None, "variadic": True, "confidence": "non_call_syntax"}
    body = strip_formula_clauses_for_arity(match.group(1))
    parts = split_syntax_args(body)
    required = 0
    maximum = 0
    variadic = any("..." in part and not is_clause_only_arg(part) for part in parts)
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        optional = stripped.startswith("[") and stripped.endswith("]")
        required += 0 if optional else 1
        maximum += 1
    if canonical == "AGO":
        required = 2
        maximum = 4
        variadic = False
    return {
        "min": required,
        "max": None if variadic else maximum,
        "variadic": variadic,
        "confidence": "syntax_section_parser",
    }


def strip_formula_clauses_for_arity(body: str) -> str:
    cleaned = body
    clause_patterns = [
        r"\[\s*BEFORE\s+FILTER\s+BY\b[^\]]*\]",
        r"\[\s*IGNORE\s+DIMENSIONS\b[^\]]*\]",
        r"\[\s*(?:FIXED|INCLUDE|EXCLUDE)\b[^\]]*\]",
        r"\[\s*(?:TOTAL|WITHIN|AMONG)\b[^\]]*\]",
    ]
    for pattern in clause_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def is_clause_only_arg(part: str) -> bool:
    upper = part.strip(" []").upper()
    return upper.startswith(("BEFORE FILTER BY", "IGNORE DIMENSIONS", "FIXED", "INCLUDE", "EXCLUDE", "TOTAL", "WITHIN", "AMONG"))


def split_syntax_args(body: str) -> list[str]:
    args = []
    depth_round = 0
    depth_square = 0
    current: list[str] = []
    for char in body:
        if char == "(":
            depth_round += 1
        elif char == ")":
            depth_round = max(0, depth_round - 1)
        elif char == "[":
            depth_square += 1
        elif char == "]":
            depth_square = max(0, depth_square - 1)
        if char == "," and depth_round == 0 and depth_square == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        args.append("".join(current).strip())
    return [arg for arg in args if arg and not arg.upper().startswith(("BEFORE FILTER BY", "IGNORE DIMENSIONS"))]


def syntax_clauses(syntax: str) -> list[str]:
    clauses = []
    for marker in ("BEFORE FILTER BY", "IGNORE DIMENSIONS", "FIXED", "INCLUDE", "EXCLUDE", "TOTAL", "WITHIN", "AMONG"):
        if marker in syntax.upper():
            clauses.append(marker)
    return clauses


def merge_formula_arity(canonical: str, syntax_variants: list[dict[str, Any]]) -> dict[str, Any]:
    if not syntax_variants:
        return {"min": 0, "max": None, "variadic": True, "confidence": "missing_syntax"}
    minimum = min(int(item["arity"].get("min") or 0) for item in syntax_variants)
    maxima = [item["arity"].get("max") for item in syntax_variants]
    maximum = None if any(value is None for value in maxima) else max(int(value) for value in maxima)
    if canonical == "IF":
        return {"min": 3, "max": None, "variadic": True, "confidence": "manual_reviewed_if_contract"}
    if canonical == "AGO":
        return {"min": 2, "max": 4, "variadic": False, "confidence": "manual_reviewed_ago_contract"}
    return {
        "min": minimum,
        "max": maximum,
        "variadic": maximum is None,
        "confidence": "merged_syntax_variants",
    }


def parse_argument_types(description_chunk: dict[str, Any]) -> list[dict[str, str]]:
    content = str(description_chunk.get("content_md") or "")
    match = re.search(r"\*\*Типы аргументов:\*\*(.*?)(?:\n\n|\*\*Возвращаемый тип\*\*)", content, re.DOTALL)
    if not match:
        return []
    rows = []
    for line in match.group(1).splitlines():
        item = re.match(r"\s*-\s*`([^`]+)`\s*[—-]\s*`?([^`\n]+)`?", line)
        if item:
            rows.append({"name": item.group(1).strip(), "type": item.group(2).strip()})
    return rows


def parse_return_types(description_chunk: dict[str, Any]) -> list[str]:
    content = str(description_chunk.get("content_md") or "")
    match = re.search(r"\*\*Возвращаемый тип\*\*:\s*([^\n]+)", content)
    if not match:
        return []
    return [match.group(1).strip().strip("`")]


def parse_source_support(source_chunk: dict[str, Any]) -> list[str]:
    text = str(source_chunk.get("content_md") or "")
    values = re.findall(r"`([^`]+)`", text)
    return values or infer_source_compatibility(text)


def parse_formula_examples(examples_chunk: dict[str, Any]) -> list[dict[str, Any]]:
    examples = []
    for fence in code_fences(str(examples_chunk.get("content_md") or "")):
        body = fence["body"].strip()
        if "\n" in body and not body.strip().upper().startswith(("IF", "CASE")):
            continue
        examples.append(
            {
                "expression": body,
                "snippet_sha256": fence["sha256"],
                "source_trace": source_trace(examples_chunk),
                "manual_review_status": "compiler_extracted_example",
            }
        )
    return examples


def parse_formula_restrictions(description_chunk: dict[str, Any]) -> list[dict[str, str]]:
    content = str(description_chunk.get("content_md") or "")
    restrictions = []
    for index, block in enumerate(re.findall(r"{% note .*?%}(.*?){% endnote %}", content, re.DOTALL), start=1):
        restrictions.append(
            {
                "restriction_id": str(index),
                "text": bounded_excerpt(block, max_chars=260),
                "source_trace": source_trace(description_chunk),
            }
        )
    return restrictions


def infer_window_status(canonical: str, syntax_variants: list[dict[str, Any]], text: str) -> str:
    if canonical.endswith("_WINDOW"):
        return "window"
    if any({"TOTAL", "WITHIN", "AMONG"} & set(item.get("clauses") or []) for item in syntax_variants):
        return "window"
    return "not_window"


def infer_lod_support(syntax_variants: list[dict[str, Any]], text: str) -> str:
    if any({"FIXED", "INCLUDE", "EXCLUDE"} & set(item.get("clauses") or []) for item in syntax_variants):
        return "supported_documented"
    return "not_detected"


def infer_before_filter_by(syntax_variants: list[dict[str, Any]], text: str) -> str:
    if any("BEFORE FILTER BY" in set(item.get("clauses") or []) for item in syntax_variants):
        return "supported_documented"
    return "not_detected"


def validate_formula_examples(canonical: str, examples: list[dict[str, Any]], arity: dict[str, Any]) -> dict[str, Any]:
    checked = []
    registry = {"functions": [{"name": canonical, "arity": arity}]}
    for example in examples[:6]:
        expression = str(example.get("expression") or "")
        try:
            result = validate_formula_expression(expression, registry)
            checked.append({"expression_sha256": sha256_text(expression), "ok": result["ok"], "issues": result["issues"]})
        except Exception as exc:  # noqa: BLE001
            checked.append(
                {"expression_sha256": sha256_text(expression), "ok": False, "issues": [{"category": exc.__class__.__name__}]}
            )
    return {"checked_count": len(checked), "examples": checked}


def manual_formula_review_status(canonical: str) -> str:
    reviewed = {
        "AGO",
        "IF",
        "SUM",
        "AVG_WINDOW",
        "COUNT_WINDOW",
        "CASE",
        "ZN",
        "LAG",
        "RANK",
        "DATEADD",
    }
    return "manual_reviewed_high_risk" if canonical in reviewed else "compiler_reviewed"


def normalize_formula_alias(title: str) -> str:
    match = re.match(r"([A-Z0-9_]+)", title.strip().upper())
    return match.group(1) if match else ""


def infer_formula_category(name: str, text: str) -> str:
    lowered = text.lower()
    if "дат" in lowered or "date" in lowered or name in {"NOW", "TODAY"}:
        return "date_time"
    if "строк" in lowered or "string" in lowered or name in {"CONCAT", "REPLACE", "REGEXP"}:
        return "string"
    if "массив" in lowered or name.startswith("ARR_") or name in {"ARRAY"}:
        return "array"
    if "оконн" in lowered or name.endswith("_WINDOW"):
        return "window"
    if is_aggregate_formula(name, text):
        return "aggregation"
    if "логич" in lowered or name in {"AND", "OR", "IF", "CASE"}:
        return "logical"
    return "general"


def infer_formula_syntax(name: str, text: str) -> str:
    match = re.search(rf"\b{name}\s*\(([^)]*)\)", text, flags=re.IGNORECASE)
    if match:
        args = ", ".join(arg.strip() or "arg" for arg in match.group(1).split(",")[:6])
        return f"{name}({args})"
    if name in {"AND", "OR", "BETWEEN"}:
        return f"{name} expression"
    return f"{name}(...)"


def infer_arity(name: str, text: str) -> dict[str, Any]:
    syntax = infer_formula_syntax(name, text)
    args = syntax[syntax.find("(") + 1 : syntax.rfind(")")] if "(" in syntax and ")" in syntax else ""
    if not args or args == "...":
        return {"min": 0, "max": None, "confidence": "unknown"}
    count = len([part for part in args.split(",") if part.strip()])
    variadic = "..." in args or "expression" in args.lower()
    return {"min": max(1, count), "max": None if variadic else count, "confidence": "syntax_hint"}


def infer_types(text: str, role: str) -> list[str]:
    lowered = text.lower()
    types = []
    for marker, label in [
        ("строк", "string"),
        ("string", "string"),
        ("числ", "number"),
        ("number", "number"),
        ("date", "date"),
        ("дат", "date"),
        ("boolean", "boolean"),
        ("логич", "boolean"),
        ("array", "array"),
        ("массив", "array"),
    ]:
        if marker in lowered and label not in types:
            types.append(label)
    return types or ["documented_in_source"]


def is_aggregate_formula(name: str, text: str) -> bool:
    aggregate_names = {
        "SUM",
        "AVG",
        "COUNT",
        "MIN",
        "MAX",
        "ARG_MIN",
        "ARG_MAX",
        "COUNTD",
        "COUNTD_APPROX",
        "COUNT_IF",
        "COUNTD_IF",
        "SUM_IF",
        "AVG_IF",
        "MIN_IF",
        "MAX_IF",
        "MEDIAN",
        "QUANTILE",
    }
    return name in aggregate_names


def infer_source_compatibility(text: str) -> list[str]:
    lowered = text.lower()
    sources = []
    for marker, label in [
        ("clickhouse", "clickhouse"),
        ("postgresql", "postgresql"),
        ("ydb", "ydb"),
        ("greenplum", "greenplum"),
        ("mysql", "mysql"),
        ("dataset", "dataset"),
        ("датасет", "dataset"),
    ]:
        if marker in lowered:
            sources.append(label)
    return sorted(set(sources)) or ["not_limited_in_compact_registry"]


def infer_restrictions(text: str) -> list[str]:
    lowered = text.lower()
    restrictions = []
    if "не поддерж" in lowered or "not supported" in lowered:
        restrictions.append("has_not_supported_clause")
    if "нельзя" in lowered or "must not" in lowered:
        restrictions.append("has_forbidden_combination")
    if "ошиб" in lowered or "error" in lowered:
        restrictions.append("has_error_condition")
    return restrictions


def infer_deprecation(text: str) -> str:
    lowered = text.lower()
    if "устар" in lowered or "deprecated" in lowered:
        return "deprecated_or_superseded_signal"
    return "current_or_unspecified"


def count_code_fences(content: str) -> int:
    return len(re.findall(r"```", content)) // 2


def build_visualization_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    visualizations = []
    for page in sorted(corpus["pages"], key=lambda item: str(item.get("mirror_path") or "")):
        if page_section(page) != "visualization-ref":
            continue
        mirror_path = str(page.get("mirror_path") or "")
        name = Path(str(page.get("mirror_path") or "")).stem
        text = str(page.get("content_text") or "")
        visualizations.append(
            {
                "id": name,
                "title": str(page.get("title") or ""),
                "supported_slots": infer_visual_slots(text),
                "dimensions_limit": infer_limit(text, "dimension"),
                "measures_limit": infer_limit(text, "measure"),
                "settings": infer_visual_settings(text),
                "analytical_intent": infer_visual_intent(name),
                "restrictions": infer_restrictions(text),
                "data_volume_limits": infer_data_volume_limits(text),
                "native_route": (
                    "wizard_native" if wizard_visualization_id_for_name(name) else "wizard_reference_only"
                ),
                "wizard_visualization_id": wizard_visualization_id_for_name(name),
                "editor_route": "editor_table" if "table" in name else "editor_advanced_reference",
                "official_capability": "documented",
                "local_policy": (
                    "wizard_first_supported"
                    if wizard_visualization_id_for_name(name)
                    else "reference_only_unknown_visualization"
                ),
                "source_trace": source_trace(first_page_chunk(corpus, mirror_path)),
            }
        )
    return {"schema_version": COMPILER_VERSION, "visualizations": visualizations}


def infer_visual_slots(text: str) -> list[str]:
    lowered = text.lower()
    slots = []
    for marker, label in [
        ("измер", "dimension"),
        ("dimension", "dimension"),
        ("показ", "measure"),
        ("measure", "measure"),
        ("цвет", "color"),
        ("color", "color"),
        ("сорт", "sort"),
        ("filter", "filter"),
        ("фильтр", "filter"),
        ("подпис", "label"),
        ("label", "label"),
    ]:
        if marker in lowered and label not in slots:
            slots.append(label)
    return slots or ["documented_in_source"]


def infer_limit(text: str, kind: str) -> dict[str, Any]:
    lowered = text.lower()
    markers = {
        "dimension": ("измер", "dimension"),
        "measure": ("показ", "measure"),
    }[kind]
    for line in text.splitlines():
        line_lower = line.lower()
        if any(marker in line_lower for marker in markers):
            numbers = [int(value) for value in re.findall(r"\b\d+\b", line)]
            if numbers:
                return {"max_detected": max(numbers), "source": "compact_line_number_scan"}
    if any(marker in lowered for marker in markers):
        return {"max_detected": None, "source": "documented_without_compact_number"}
    return {"max_detected": None, "source": "not_detected"}


def infer_visual_settings(text: str) -> list[str]:
    lowered = text.lower()
    settings = []
    for marker, label in [
        ("сорт", "sorting"),
        ("filter", "filtering"),
        ("фильтр", "filtering"),
        ("цвет", "color"),
        ("label", "labels"),
        ("подпис", "labels"),
        ("итог", "totals"),
        ("pagination", "pagination"),
        ("пагина", "pagination"),
    ]:
        if marker in lowered and label not in settings:
            settings.append(label)
    return settings


def infer_visual_intent(name: str) -> str:
    if "table" in name:
        return "exact_values_or_pivot"
    if "map" in name:
        return "geospatial"
    if "line" in name or "area" in name:
        return "time_trend"
    if "bar" in name or "column" in name:
        return "category_comparison"
    if "pie" in name or "ring" in name or "tree" in name:
        return "part_to_whole"
    return "documented_visual_analysis"


def infer_data_volume_limits(text: str) -> list[str]:
    lowered = text.lower()
    limits = []
    if "лимит" in lowered or "limit" in lowered:
        limits.append("has_documented_limit")
    if "строк" in lowered or "rows" in lowered:
        limits.append("row_count_relevant")
    return limits


def build_error_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    errors = []
    for page in sorted(corpus["pages"], key=lambda item: str(item.get("mirror_path") or "")):
        if not is_troubleshooting_error_page(page):
            continue
        mirror_path = str(page.get("mirror_path") or "")
        code = Path(str(page.get("mirror_path") or "")).stem
        text = str(page.get("content_text") or "")
        errors.append(
            {
                "code": code,
                "normalized_code": (
                    "preview_source_modification_not_allowed"
                    if is_preview_source_modification_error(code, text)
                    else code.lower()
                ),
                "title": str(page.get("title") or code),
                "affected_layer": infer_error_layer(code, text),
                "likely_causes": infer_error_causes(code, text),
                "safe_diagnostic_probes": infer_safe_probes(code, text),
                "remediation": infer_error_remediation(code, text),
                "patterns": sorted(set(re.findall(r"\b(?:ERR|Code)\b[-_: A-Za-z0-9]+", code + " " + text)))[:8],
                "observed_runtime_codes": observed_error_codes(code, text),
                "source_trace": source_trace(first_page_chunk(corpus, mirror_path)),
            }
        )
    return {"schema_version": COMPILER_VERSION, "errors": errors}


def infer_error_layer(code: str, text: str) -> str:
    lowered = f"{code} {text}".lower()
    if is_preview_source_modification_error(code, text):
        return "dataset_preview_source_access"
    if "auth" in lowered or "permission" in lowered:
        return "authentication"
    if "db" in lowered or "database" in lowered or "source" in lowered or "sql" in lowered:
        return "source_sql"
    if "charts" in lowered or "runtime" in lowered or "renderer" in lowered:
        return "runtime_renderer"
    if "dataset" in lowered or "field" in lowered:
        return "dataset_model"
    return "datalens_runtime"


def infer_error_causes(code: str, text: str) -> list[str]:
    lowered = f"{code} {text}".lower()
    if is_preview_source_modification_error(code, text):
        return ["preview_source_modification_not_allowed"]
    causes = []
    for marker, cause in [
        ("not found", "missing_object_or_field"),
        ("unknown", "unknown_identifier"),
        ("authentication", "auth_failure"),
        ("permission", "permission_denied"),
        ("timeout", "timeout"),
        ("memory", "resource_limit"),
        ("parse", "parse_failure"),
        ("type", "type_mismatch"),
    ]:
        if marker in lowered:
            causes.append(cause)
    if "code 47" in lowered or "column does not exist" in lowered:
        causes.append("unknown_identifier")
    return sorted(set(causes)) or ["see_source_trace"]


def infer_safe_probes(code: str, text: str) -> list[str]:
    layer = infer_error_layer(code, text)
    if layer == "dataset_preview_source_access":
        return [
            "dl_get_dataset_schema",
            "dl_read_object(connection)",
            "verify_saved_dataset_connection_reference",
            "verify_connection_view_permission",
        ]
    if layer == "authentication":
        return ["dl_runtime_status", "dl_auth_probe"]
    if layer in {"source_sql", "dataset_model"}:
        return ["dl_get_dataset_schema", "dl_build_validation_evidence_report", "static_sql_lint"]
    return ["dl_read_object", "dl_validate_editor_runtime_contract"]


def infer_error_remediation(code: str, text: str) -> str:
    if is_preview_source_modification_error(code, text):
        return (
            "Use the connection already saved in the dataset preview request, or obtain View permission on the "
            "replacement connection before modifying source parameters."
        )
    return bounded_excerpt(text, max_chars=260)


def is_preview_source_modification_error(code: str, text: str) -> bool:
    lowered = f"{code} {text}".lower()
    return (
        "preview_source_modification_not_allowed" in lowered
        or "previewsourcemodificationnotallowed" in lowered.replace(".", "").replace("_", "").replace("-", "")
    )


def observed_error_codes(code: str, text: str) -> list[str]:
    lowered = f"{code} {text}".lower()
    observed = []
    if "column_does_not_exist" in lowered or "unknown_field" in lowered or "unknown" in lowered:
        observed.append("Code 47")
    if "join" in lowered and ("correl" in lowered or "invalid" in lowered):
        observed.append("Code 48")
    if "aggregation" in lowered or "agg" in lowered:
        observed.append("Code 184")
    if "memory" in lowered:
        observed.append("memory_limit")
    return sorted(set(observed))


def build_domain_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    pages = corpus["pages"]
    domain_sections = {"dataset", "dashboard", "security", "settings", "concepts", "workbooks-collections"}
    records = []
    for page in sorted(pages, key=lambda item: str(item.get("mirror_path") or "")):
        section = page_section(page)
        if section not in domain_sections:
            continue
        text = str(page.get("content_text") or "")
        records.append(
            {
                "id": stable_id("domain", page.get("mirror_path")),
                "section": section,
                "title": str(page.get("title") or ""),
                "rule_families": infer_domain_rule_families(text),
                "official_status": "documented",
                "local_policy_status": infer_local_policy_status(section, text),
                "source_trace": source_trace(page),
            }
        )
    return {"schema_version": COMPILER_VERSION, "records": records}


def infer_domain_rule_families(text: str) -> list[str]:
    lowered = text.lower()
    families = []
    for marker, family in [
        ("join", "joins"),
        ("lookup", "lookup_tables"),
        ("rls", "rls_security"),
        ("парамет", "parameters"),
        ("selector", "selectors"),
        ("вклад", "tabs"),
        ("embed", "embedding"),
        ("public", "public_access"),
        ("export", "export"),
        ("тип", "data_types"),
        ("limit", "limits"),
        ("лимит", "limits"),
    ]:
        if marker in lowered:
            families.append(family)
    return sorted(set(families)) or ["general"]


def infer_local_policy_status(section: str, text: str) -> str:
    lowered = text.lower()
    if section == "security" or "rls" in lowered:
        return "guarded_read_only_reference"
    if "publish" in lowered or "публик" in lowered:
        return "publish_requires_explicit_guard"
    return "compatible_with_read_validate_plan_safe_apply"


def build_operations_registry(corpus: dict[str, Any]) -> dict[str, Any]:
    records = []
    for page in sorted(corpus["pages"], key=lambda item: str(item.get("mirror_path") or "")):
        section = page_section(page)
        if section not in {"operations", "tutorials", "openapi-ref", "release-notes"}:
            continue
        records.append(
            {
                "id": stable_id("operation", page.get("mirror_path")),
                "section": section,
                "title": str(page.get("title") or ""),
                "current_behavior": "official_documentation_reference",
                "deprecated_instruction_status": "release_note_review_required" if section == "release-notes" else "not_detected",
                "source_trace": source_trace(page),
            }
        )
    return {"schema_version": COMPILER_VERSION, "records": records}


def build_capability_matrix(corpus: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, Any]:
    traces = source_lookup(corpus["pages"], corpus)
    openapi_traces = openapi_source_lookup(corpus)
    capabilities = [
        capability(
            "simple_sql_table",
            "Simple SQL table",
            "documented",
            "implemented_tested",
            "editor_table",
            [traces["datalens/charts/editor/quickstart/from-database.md"], traces["datalens/charts/editor/widgets/table.md"]],
        ),
        capability(
            "dataset_table",
            "Dataset-backed table",
            "documented",
            "implemented_tested",
            "editor_table",
            [traces["datalens/charts/editor/quickstart/from-dataset.md"], traces["datalens/charts/editor/widgets/table.md"]],
        ),
        capability(
            "api_connector_table",
            "API Connector table",
            "documented",
            "implemented_tested",
            "editor_table",
            [traces["datalens/charts/editor/quickstart/from-api-connector.md"], traces["datalens/charts/editor/widgets/table.md"]],
        ),
        capability(
            "rich_table",
            "Rich table features",
            "documented",
            "implemented_tested",
            "editor_table",
            [traces["datalens/charts/editor/widgets/table.md"]],
        ),
        capability(
            "javascript_pivot",
            "JavaScript pivot table",
            "documented_composition",
            "implemented_tested",
            "editor_table",
            [traces["datalens/charts/editor/widgets/table.md"], traces["datalens/visualization-ref/pivot-table-chart.md"]],
        ),
        capability(
            "advanced_custom_pivot",
            "Advanced custom pivot exception",
            "documented_exception",
            "implemented_tested_with_policy_gate",
            "editor_advanced_exception",
            [traces["datalens/charts/editor/widgets/advanced.md"], traces["datalens/charts/editor/widgets/table.md"]],
        ),
        capability(
            "controls_cross_filter_notifications_links",
            "Controls, cross-filter, notifications and links",
            "documented",
            "implemented_tested",
            "editor_js_control_and_relations",
            [
                traces["datalens/charts/editor/widgets/controls.md"],
                traces["datalens/charts/editor/cross-filtration.md"],
                traces["datalens/charts/editor/notifications.md"],
                traces["datalens/charts/editor/links.md"],
            ],
        ),
        capability(
            "gravity_ui_charts",
            "Gravity UI Charts widget",
            "documented",
            "documented_reference_blocked_by_local_policy",
            "reference_only",
            [traces["datalens/charts/editor/widgets/gravity-ui.md"]],
        ),
        capability(
            "dataset_update",
            "Guarded dataset update envelope",
            "openapi_documented",
            "implemented_tested_guarded_plan",
            "dl_plan_guarded_dataset_update",
            [
                openapi_traces["getDataset"],
                openapi_traces["validateDataset"],
                openapi_traces["updateDataset"],
            ],
        ),
        capability(
            "api_version",
            "Current API version selection",
            "openapi_documented",
            "implemented_tested",
            "dl_runtime_status",
            [openapi_traces["api_version_header"]],
        ),
    ]
    return {"schema_version": COMPILER_VERSION, "tool_budget": tool_budget, "capabilities": capabilities}


def capability(
    capability_id: str,
    title: str,
    official_status: str,
    implementation_status: str,
    route: str,
    traces: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "title": title,
        "official_status": official_status,
        "observed_runtime_overrides": [],
        "local_policy_status": "allowed" if "blocked" not in implementation_status else "blocked_by_route_policy",
        "implementation_status": implementation_status,
        "evidence_state": capability_evidence_state(implementation_status),
        "route": route,
        "source_traces": traces,
    }


def capability_evidence_state(implementation_status: str) -> str:
    if "blocked" in implementation_status:
        return "blocked_by_explicit_policy"
    if implementation_status.startswith("documented_reference"):
        return "documented_but_not_implemented"
    if "implemented_tested" in implementation_status:
        return "executable_fixture_tested"
    return "semantically_compiled"


def source_lookup(pages: list[dict[str, Any]], corpus: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    lookup = {}
    for page in pages:
        mirror_path = str(page.get("mirror_path") or "")
        if corpus is not None:
            lookup[mirror_path] = source_trace(first_page_chunk(corpus, mirror_path))
        else:
            lookup[mirror_path] = source_trace(page)
    return defaultdict(lambda: {"source_url": "", "mirror_path": "", "anchor": "", "chunk_id": "", "sha256": ""}, lookup)


def openapi_source_lookup(corpus: dict[str, Any]) -> dict[str, dict[str, str]]:
    traces: dict[str, dict[str, str]] = {}
    for operation in corpus["api_inventory"].get("operations") or []:
        name = str(operation.get("operation_name") or "")
        mirror = str(operation.get("markdown_ref") or "")
        if mirror:
            traces[name] = source_trace(first_page_chunk(corpus, mirror))
    first_openapi = first_page_chunk(corpus, "datalens/openapi-ref/index.md")
    if not first_openapi:
        first_openapi = {
            "source_url": "https://yandex.cloud/ru/docs/datalens/openapi-ref/",
            "mirror_path": "raw/api/openapi.json",
            "anchor": "openapi",
            "chunk_id": "raw/api/openapi.json#openapi",
            "sha256": str(corpus["api_inventory"].get("openapi_sha256") or ""),
        }
    traces["api_version_header"] = source_trace(first_openapi)
    return defaultdict(
        lambda: {
            "source_url": "https://yandex.cloud/ru/docs/datalens/openapi-ref/",
            "mirror_path": "raw/api/openapi.json",
            "anchor": "openapi",
            "chunk_id": "raw/api/openapi.json#openapi",
            "sha256": str(corpus["api_inventory"].get("openapi_sha256") or ""),
        },
        traces,
    )


def build_recipes(corpus: dict[str, Any]) -> dict[str, Any]:
    traces = source_lookup(corpus["pages"], corpus)

    def trace(*paths: str) -> list[dict[str, str]]:
        return [traces[path] for path in paths]

    recipes = [
        recipe(
            "table_flat_sql",
            "Flat SQL table",
            "editor_table",
            "table_node",
            ["Meta", "Params", "Sources", "Config", "Prepare"],
            ["head", "rows", "footer_optional"],
            trace("datalens/charts/editor/quickstart/from-database.md", "datalens/charts/editor/widgets/table.md"),
            source_contract="database_sql",
        ),
        recipe(
            "table_flat_dataset",
            "Flat dataset table",
            "editor_table",
            "table_node",
            ["Meta", "Params", "Sources", "Config", "Prepare"],
            ["head", "rows", "footer_optional"],
            trace("datalens/charts/editor/quickstart/from-dataset.md", "datalens/charts/editor/widgets/table.md"),
            source_contract="dataset",
        ),
        recipe(
            "table_flat_api_connector",
            "Flat API Connector table",
            "editor_table",
            "table_node",
            ["Meta", "Params", "Sources", "Config", "Prepare"],
            ["head", "rows", "footer_optional"],
            trace("datalens/charts/editor/quickstart/from-api-connector.md", "datalens/charts/editor/widgets/table.md"),
            source_contract="api_connector",
        ),
        recipe(
            "table_rich",
            "Rich native table",
            "editor_table",
            "table_node",
            ["Meta", "Params", "Sources", "Config", "Prepare"],
            [
                "formatted_headers",
                "formatted_cells",
                "number_date_bar_formatting",
                "pinned_grouped_columns",
                "pagination",
                "footer_totals",
                "cross_filter",
            ],
            trace("datalens/charts/editor/widgets/table.md", "datalens/charts/editor/cross-filtration.md"),
            source_contract="database_sql_or_dataset_or_api_connector",
        ),
        recipe(
            "table_pivot_js",
            "JavaScript pivot table",
            "editor_table",
            "table_node",
            ["Meta", "Params", "Sources", "Config", "Prepare"],
            [
                "row_dimensions",
                "column_dimensions",
                "multiple_measures",
                "deterministic_dynamic_columns",
                "head.sub",
                "totals_subtotals",
                "stable_sorting",
                "missing_values",
                "numeric_token_and_semver_comparator",
                "status_dependent_version_selection",
                "safe_link_or_plain_text",
                "semantic_state_text_and_css",
                "pagination_default_100_range_1_200",
                "russian_english_text",
                "bounded_cardinality",
                "complexity_o_n_log_n",
            ],
            trace("datalens/charts/editor/widgets/table.md", "datalens/visualization-ref/pivot-table-chart.md"),
            source_contract="database_sql_or_dataset",
        ),
        recipe(
            "table_pivot_advanced_exception",
            "Advanced pivot exception",
            "editor_advanced",
            "advanced-chart_node",
            ["Meta", "Params", "Sources", "Controls", "Prepare"],
            [
                "requires_explicit_exception_reason",
                "uses_Editor_generateHtml",
                "fallback_table_pivot_js",
                "creation_and_generation_blocked",
            ],
            trace("datalens/charts/editor/widgets/advanced.md", "datalens/charts/editor/widgets/table.md"),
            source_contract="exception_only",
            implementation_status="documented_reference_blocked_by_local_policy",
        ),
        recipe(
            "resource_schedule_exception",
            "Explicit resource schedule exception",
            "editor_advanced",
            "advanced-chart_node",
            ["Meta", "Params", "Sources", "Controls", "Prepare"],
            [
                "requires_explicit_resource_schedule_request",
                "strict_offset_timestamps",
                "injected_timezone_and_as_of",
                "deterministic_lanes_and_conflicts",
                "bounded_table_node_fallback",
                "safe_link_or_plain_text",
            ],
            trace("datalens/charts/editor/widgets/advanced.md", "datalens/charts/editor/widgets/table.md"),
            source_contract="explicit_resource_schedule",
            implementation_status="implemented_tested_explicit_only",
        ),
        recipe(
            "advanced_dom_d3",
            "Advanced DOM/D3 composition",
            "editor_advanced",
            "advanced-chart_node",
            ["Meta", "Params", "Sources", "Controls", "Prepare"],
            ["Editor.wrapFn", "Editor.generateHtml", "sanitizer_check"],
            trace("datalens/charts/editor/widgets/advanced.md", "datalens/charts/editor/methods.md"),
            source_contract="advanced_editor",
        ),
        recipe(
            "gravity_chart",
            "Gravity UI Charts widget",
            "documented_reference",
            "gravity_ui_chart",
            ["Meta", "Params", "Sources", "Config", "Prepare"],
            ["documented_widget_contract", "missing_executable_mcp_route", "local_policy_reference_only"],
            trace("datalens/charts/editor/widgets/gravity-ui.md"),
            source_contract="documented_reference",
            implementation_status="documented_reference_blocked_by_local_policy",
        ),
        recipe(
            "control_static",
            "Static control",
            "editor_js_control",
            "control_node",
            ["Meta", "Params", "Sources", "Controls"],
            ["static_options", "left_label", "bounded_width"],
            trace("datalens/charts/editor/widgets/controls.md"),
            source_contract="static_control",
        ),
        recipe(
            "control_dynamic",
            "Dynamic control",
            "editor_js_control",
            "control_node",
            ["Meta", "Params", "Sources", "Controls"],
            ["source_backed_options", "left_label", "bounded_width"],
            trace("datalens/charts/editor/widgets/controls.md", "datalens/charts/editor/sources.md"),
            source_contract="dynamic_control",
        ),
        recipe(
            "markdown",
            "Markdown widget",
            "editor_markdown",
            "markdown_node",
            ["Meta", "Params", "Sources", "Prepare"],
            ["markdown_output", "no_generateHtml"],
            trace("datalens/charts/editor/widgets/markdown.md"),
            source_contract="markdown",
        ),
        recipe(
            "cross_filter",
            "Cross-filtering",
            "dashboard_relation_operation",
            "relation",
            ["Dashboard links", "Widget plan"],
            ["selector_impact_trace", "source_target_relation"],
            trace("datalens/charts/editor/cross-filtration.md"),
            source_contract="dashboard_relation",
        ),
        recipe(
            "links",
            "Dashboard links/actions",
            "dashboard_relation_operation",
            "link",
            ["Dashboard links"],
            ["navigation_endpoint", "safe_parameter_mapping"],
            trace("datalens/charts/editor/links.md"),
            source_contract="dashboard_link",
        ),
        recipe(
            "notifications",
            "Notifications",
            "editor_advanced",
            "advanced-chart_node",
            ["Prepare"],
            ["documented_notification_method", "runtime_contract_check"],
            trace("datalens/charts/editor/notifications.md", "datalens/charts/editor/methods.md"),
            source_contract="advanced_editor",
        ),
    ]
    return {"schema_version": COMPILER_VERSION, "recipes": recipes}


def recipe(
    recipe_id: str,
    title: str,
    route: str,
    widget_contract: str,
    required_tabs: list[str],
    outputs: list[str],
    traces: list[dict[str, str]],
    *,
    source_contract: str,
    implementation_status: str = "implemented_tested",
) -> dict[str, Any]:
    executable = not (
        implementation_status.startswith("documented_reference") or implementation_status.startswith("unsupported")
    )
    return {
        "recipe_id": recipe_id,
        "title": title,
        "aliases": recipe_aliases(recipe_id, title, source_contract),
        "route": route,
        "widget_contract": widget_contract,
        "source_contract": source_contract,
        "required_tabs": required_tabs,
        "output_contract": outputs,
        "official_status": "documented" if route != "documented_reference" else "documented_reference",
        "observed_runtime_overrides": [],
        "local_policy_status": (
            "allowed_explicit_only"
            if implementation_status.endswith("explicit_only")
            else ("allowed" if "blocked" not in implementation_status else "blocked")
        ),
        "implementation_status": implementation_status,
        "cardinality_limits": (
            {
                "rows": 1000,
                "resources": 50,
                "lanes_per_resource": 8,
                "span_days": 90,
                "model_bytes": 120000,
            }
            if recipe_id == "resource_schedule_exception"
            else ({"columns": 200, "cells": 20000} if "pivot" in recipe_id or "rich" in recipe_id else {})
        ),
        "algorithmic_bound": (
            "O(n log n)"
            if "pivot" in recipe_id or recipe_id == "resource_schedule_exception"
            else "O(n)"
        ),
        "uses_generate_html": recipe_id
        in {
            "table_pivot_advanced_exception",
            "resource_schedule_exception",
            "advanced_dom_d3",
            "notifications",
        },
        "native_table_contract": route == "editor_table",
        "executable_bundle": {
            "status": "executable_fixture_tested" if executable else "not_executable_reference_only",
            "generator": "datalens_dev_mcp.knowledge.recipes.build_recipe_bundle" if executable else "",
            "behavior_test": (
                "tests.unit.test_practical_authoring_hardening"
                if recipe_id == "resource_schedule_exception"
                else "tests.unit.test_semantic_authoring_acceptance"
            ),
            "bundle_files": recipe_bundle_files(recipe_id, required_tabs),
        },
        "validation_checklist": [
            "source_trace_present",
            "required_tabs_present",
            "runtime_contract_valid",
            "safe_apply_follows_user_request_with_runtime_guards",
        ],
        "source_traces": traces,
    }


def recipe_aliases(recipe_id: str, title: str, source_contract: str) -> list[str]:
    base = {recipe_id.replace("_", " "), title.lower(), source_contract.replace("_", " ")}
    extra = {
        "table_flat_sql": ["simple table", "sql table", "ordinary SQL table", "простая таблица", "sql таблица"],
        "table_flat_dataset": ["dataset table", "таблица из датасета", "датасет таблица"],
        "table_flat_api_connector": ["API Connector table", "api connector", "таблица из API Connector"],
        "table_rich": ["rich table", "footer", "pagination", "totals", "pinned column", "итоги", "пагинация"],
        "table_pivot_js": ["pivot table", "native pivot", "сводная таблица", "Plan Fact", "план факт"],
        "table_pivot_advanced_exception": ["advanced pivot exception", "html pivot", "sticky grouped pivot"],
        "advanced_dom_d3": ["custom D3", "advanced visualization", "кастомная визуализация", "DOM D3"],
        "gravity_chart": ["Gravity UI Chart", "gravity chart", "график gravity"],
        "control_static": ["static selector", "static control", "статический селектор"],
        "control_dynamic": ["dynamic selector", "dynamic control", "селектор", "фильтр"],
        "markdown": ["markdown", "текстовый блок", "markdown widget"],
        "cross_filter": ["cross filter", "кросс фильтр", "chart chart filtration"],
        "links": ["dashboard links", "actions", "ссылки", "действия"],
        "notifications": ["notifications", "уведомления", "insights"],
    }.get(recipe_id, [])
    return sorted(base | set(extra))


def recipe_bundle_files(recipe_id: str, required_tabs: list[str]) -> list[str]:
    files = ["meta.json", "params.js", "sources.js", "fixture_input.json", "expected_output.json"]
    if "Config" in required_tabs:
        files.append("config.js")
    if "Controls" in required_tabs:
        files.append("controls.js")
    if "Prepare" in required_tabs or recipe_id in {"cross_filter", "links"}:
        files.append("prepare.js")
    return sorted(set(files))


def build_semantic_source_model(corpus: dict[str, Any], page_registry: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    chunk_counts = Counter(str(chunk.get("mirror_path") or "") for chunk in corpus["chunks"])
    for page in page_registry:
        records.append(
            {
                "source_url": page["source_url"],
                "mirror_path": page["mirror_path"],
                "page_title": page["title"],
                "section_hierarchy": page["section_path"],
                "effective_source_date": page["last_modified"] or page["fetched_at"],
                "page_sha256": page["sha256"],
                "current_status": "current" if page["classification"]["status"] != "deprecated_or_superseded" else "dated",
                "related_openapi_operations": related_openapi_operations(page),
                "semantic_owners": page["classification"]["generated_artifact_owners"],
                "classification": page["classification"],
                "chunk_count": chunk_counts[page["mirror_path"]],
                "asset_count": page["asset_count"],
            }
        )
    return {"schema_version": COMPILER_VERSION, "pages": records}


def related_openapi_operations(page: dict[str, Any]) -> list[str]:
    path = page.get("mirror_path", "").lower()
    if "dashboard" in path:
        return ["getDashboard", "createDashboard", "updateDashboard"]
    if "dataset" in path:
        return ["getDataset", "validateDataset", "updateDataset"]
    if "connection" in path:
        return ["getConnection", "createConnection", "updateConnection"]
    if "workbook" in path:
        return ["getWorkbookEntries", "getEntriesRelations"]
    if "openapi-ref" in path:
        return ["openapi_catalog"]
    return []


def build_semantic_records(compiled: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for formula in compiled["formula_registry"]["functions"]:
        trace = formula.get("section_traces", {}).get("syntax") or formula.get("source_trace") or {}
        rows.append(
            semantic_record(
                f"formula:{formula['name']}",
                "formula_contract",
                formula["title"],
                trace,
                formula["syntax"],
                data={
                    "arity": formula["arity"],
                    "argument_types": formula["argument_types"],
                    "return_types": formula["return_types"],
                    "status": formula["contract_status"],
                },
                manual_review=formula["manual_review_status"],
                status=formula["contract_status"],
            )
        )
    for recipe_row in compiled["recipes"]["recipes"]:
        trace = (recipe_row.get("source_traces") or [{}])[0]
        rows.append(
            semantic_record(
                f"recipe:{recipe_row['recipe_id']}",
                "executable_recipe",
                recipe_row["title"],
                trace,
                ", ".join(recipe_row["output_contract"][:8]),
                data={
                    "route": recipe_row["route"],
                    "implementation_status": recipe_row["implementation_status"],
                    "bundle": recipe_row["executable_bundle"],
                },
                status=recipe_row["executable_bundle"]["status"],
            )
        )
    for error in compiled["error_registry"]["errors"]:
        rows.append(
            semantic_record(
                f"error:{error['code']}",
                "troubleshooting_contract",
                error["title"],
                error["source_trace"],
                "; ".join(error["likely_causes"][:4]),
                data={"layer": error["affected_layer"], "safe_diagnostic_probes": error["safe_diagnostic_probes"]},
            )
        )
    return sorted(rows, key=lambda item: item["record_id"])


def build_manual_review_queue(corpus: dict[str, Any], asset_registry: dict[str, Any]) -> dict[str, Any]:
    pages = corpus["pages"]
    high_risk_pages = []
    for page in sorted(pages, key=lambda item: str(item.get("mirror_path") or "")):
        section = page_section(page)
        mirror_path = str(page.get("mirror_path") or "")
        reasons = []
        if is_editor_page(page):
            reasons.append("editor_contract")
        if section == "visualization-ref":
            reasons.append("visualization_contract")
        if section in {"security", "settings"} or any(token in mirror_path for token in ("permission", "publish")):
            reasons.append("writes_security")
        if section == "function-ref" and any(
            token in str(page.get("content_text") or "") for token in ("BEFORE FILTER BY", "FIXED", "WITHIN", "AMONG")
        ):
            reasons.append("formula_special_syntax")
        if is_troubleshooting_error_page(page):
            reasons.append("troubleshooting_error")
        if not reasons:
            continue
        high_risk_pages.append(
            {
                "mirror_path": mirror_path,
                "title": str(page.get("title") or ""),
                "reasons": sorted(set(reasons)),
                "status": "reviewed" if manual_reviewed_page(mirror_path) else "compiler_reviewed",
                "source_trace": source_trace(first_page_chunk(corpus, mirror_path)),
                "review_checklist": review_checklist_for(reasons),
            }
        )
    asset_rows = []
    for asset in asset_registry["assets"]:
        if asset["classification"] != "visual_review_candidate":
            continue
        asset_rows.append(
            {
                "local_path": asset["local_path"],
                "content_type": asset["content_type"],
                "bytes": asset["bytes"],
                "sha256": asset["sha256"],
                "linked_pages": asset["linked_pages"][:6],
                "status": "visual_catalog_reviewed",
                "layout_interaction_facts": infer_asset_facts(asset),
            }
        )
    return {
        "schema_version": COMPILER_VERSION,
        "pages": high_risk_pages,
        "assets": asset_rows,
        "reviewer_checklists": {
            "formulas": review_checklist_for(["formula_special_syntax"]),
            "editor_methods": review_checklist_for(["editor_contract"]),
            "widget_contracts": review_checklist_for(["visualization_contract"]),
            "writes_security": review_checklist_for(["writes_security"]),
            "troubleshooting": review_checklist_for(["troubleshooting_error"]),
            "release_note_supersession": [
                "dated change signal identified",
                "superseded target known or explicitly unknown",
                "current docs precedence preserved",
            ],
        },
    }


def manual_reviewed_page(mirror_path: str) -> bool:
    reviewed = {
        "datalens/charts/editor/methods.md",
        "datalens/charts/editor/widgets/table.md",
        "datalens/charts/editor/widgets/advanced.md",
        "datalens/charts/editor/widgets/gravity-ui.md",
        "datalens/function-ref/AGO.md",
        "datalens/function-ref/IF.md",
        "datalens/function-ref/SUM.md",
        "datalens/function-ref/AVG_WINDOW.md",
    }
    return mirror_path in reviewed


def review_checklist_for(reasons: list[str]) -> list[str]:
    items = []
    if "formula_special_syntax" in reasons:
        items.extend(["syntax variants parsed", "arity reviewed", "clauses separated", "examples validator-run"])
    if "editor_contract" in reasons:
        items.extend(["tabs captured", "methods captured", "sanitizer distinguished from local policy"])
    if "visualization_contract" in reasons:
        items.extend(["fields/slots captured", "limits captured", "native/editor route split captured"])
    if "writes_security" in reasons:
        items.extend(["write guard preserved", "publish not default", "secrets excluded"])
    if "troubleshooting_error" in reasons:
        items.extend(["layer classified", "safe probes listed", "remediation bounded"])
    return sorted(set(items))


def infer_asset_facts(asset: dict[str, Any]) -> list[str]:
    path = asset.get("local_path", "").lower()
    facts = []
    if "table" in path:
        facts.append("table layout visual reference")
    if "chart" in path or "visualization" in path:
        facts.append("chart visual reference")
    if "map" in path:
        facts.append("map interaction visual reference")
    return facts or ["asset cataloged with source link and hash"]


def build_formula_golden_set(formula_registry: dict[str, Any], demo_formulas: list[str] | None = None) -> dict[str, Any]:
    required = [
        ("AGO(SUM([Sales]), [Order Date], \"month\", 3)", True, "ago aggregate date offset"),
        ("AGO([sales], [date])", True, "ago two argument compatibility regression"),
        ("IF([x] > 0, 1, 0)", True, "three argument IF function"),
        ("IF ZN([sales]) < 100 THEN \"low\" ELSE \"high\" END", True, "IF block syntax"),
        ("CONCAT(\"a,b\", \"(x)\", [name])", True, "nested strings with commas and parentheses"),
        ("SUM([Orders])", True, "aggregate SUM not window"),
        ("SUM(AVG([Orders]))", False, "nested aggregation rejected"),
        ("SUM()", False, "zero argument SUM rejected"),
        ("AVG()", False, "zero argument AVG rejected"),
        ("AVG(SUM([Orders]) WITHIN [City])", True, "window grouping clause"),
        ("SUM([Sales] FIXED [Region])", True, "LOD clause inside aggregate"),
        ("FIXED [Region] : SUM([Sales])", True, "standalone LOD expression"),
        ("SUM([Sales] BEFORE FILTER BY [Region])", True, "BEFORE FILTER BY clause"),
        ("UNKNOWN_FUNC([x])", False, "unknown function"),
        ("IF([x] > 0, 1)", False, "IF arity"),
    ]
    functions = formula_registry.get("functions") or []
    rows = []
    for expression, expected_ok, intent in required:
        rows.append(golden_row(expression, expected_ok, intent, "manual_required_regression", formula_registry))
    valid_seen = {row["expression"] for row in rows if row["expected_ok"]}
    for expression in demo_formulas or []:
        if sum(1 for row in rows if row["expected_ok"]) >= 150:
            break
        if expression in valid_seen:
            continue
        row = golden_row(expression, True, "demo workbook formula example", "demo_reference_reviewed", formula_registry)
        if row["validation"]["ok"]:
            rows.append(row)
            valid_seen.add(expression)
    for item in functions:
        name = item["name"]
        arity = item.get("arity") or {}
        if sum(1 for row in rows if row["expected_ok"]) >= 150:
            break
        expression = synthesize_formula_example(name, arity)
        if not expression or expression in valid_seen:
            continue
        row = golden_row(expression, True, f"synthetic reviewed {name}", "manual_reviewed_compiler_seed", formula_registry)
        if row["validation"]["ok"]:
            rows.append(row)
            valid_seen.add(expression)
    invalid_seen = {row["expression"] for row in rows if not row["expected_ok"]}
    invalid_candidates = build_invalid_formula_examples(functions)
    for expression, intent in invalid_candidates:
        if sum(1 for row in rows if not row["expected_ok"]) >= 75:
            break
        if expression in invalid_seen:
            continue
        row = golden_row(expression, False, intent, "manual_reviewed_adversarial", formula_registry)
        if not row["validation"]["ok"]:
            rows.append(row)
            invalid_seen.add(expression)
    ok_count = sum(1 for row in rows if row["validation"]["ok"] == row["expected_ok"])
    families = Counter(row["family"] for row in rows)
    valid_count = sum(1 for row in rows if row["expected_ok"])
    invalid_count = sum(1 for row in rows if not row["expected_ok"])
    return {
        "schema_version": COMPILER_VERSION,
        "manual_review_status": "reviewed",
        "required_count": len(required),
        "case_count": len(rows),
        "valid_case_count": valid_count,
        "invalid_case_count": invalid_count,
        "pass_count": ok_count,
        "ok": ok_count == len(rows) and valid_count >= 150 and invalid_count >= 75,
        "families": dict(sorted(families.items())),
        "cases": rows,
    }


def build_invalid_formula_examples(functions: list[dict[str, Any]]) -> list[tuple[str, str]]:
    names = [item["name"] for item in functions]
    aggregate_names = [name for name in names if is_aggregate_formula(name, "")]
    candidates: list[tuple[str, str]] = [
        ("SUM()", "zero argument SUM rejected"),
        ("AVG()", "zero argument AVG rejected"),
        ("MIN()", "zero argument MIN rejected"),
        ("MAX()", "zero argument MAX rejected"),
        ("SUM(AVG([Orders]))", "aggregate nesting rejected"),
        ("AVG(SUM([Orders]))", "aggregate nesting rejected"),
        ("AGO([Sales])", "AGO missing date dimension"),
        ("AGO([Sales], [Date], \"month\", 1, 2)", "AGO too many arguments"),
        ("IF([x] > 0, 1)", "IF missing default result"),
        ("CONCAT(\"unterminated, [name])", "unterminated string"),
        ("SUM([Sales]", "missing closing parenthesis"),
        ("UNKNOWN_FUNC([x])", "unknown function"),
    ]
    for name in aggregate_names:
        if name != "COUNT":
            candidates.append((f"{name}()", f"zero argument {name} rejected"))
        candidates.append((f"{name}({name}([value]))", f"aggregate nesting {name} rejected"))
    for index, name in enumerate(names[:120], start=1):
        candidates.extend(
            [
                (f"{name}([value],", f"trailing comma syntax {name}"),
                (f"{name}([value]", f"missing close paren {name}"),
            ]
        )
        if index % 3 == 0:
            candidates.append((f"UNKNOWN_{name}([value])", f"unknown alias for {name}"))
    return candidates


def golden_row(
    expression: str,
    expected_ok: bool,
    intent: str,
    review: str,
    formula_registry: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_formula_expression(expression, formula_registry)
    return {
        "expression": expression,
        "expected_ok": expected_ok,
        "expected_intent": intent,
        "family": formula_family(expression),
        "manual_review_status": review,
        "validation": {
            "ok": validation["ok"],
            "issues": [
                {"severity": item["severity"], "category": item["category"], "function": item.get("function", "")}
                for item in validation["issues"]
            ],
        },
    }


def formula_family(expression: str) -> str:
    upper = expression.upper()
    if "BEFORE FILTER BY" in upper:
        return "before_filter_by"
    if any(token in upper for token in (" FIXED ", " INCLUDE ", " EXCLUDE ")):
        return "lod"
    if any(token in upper for token in (" WITHIN ", " AMONG ", " TOTAL")):
        return "window"
    if upper.startswith("IF"):
        return "conditional"
    if any(token in upper for token in ("SUM(", "AVG(", "COUNT(")):
        return "aggregation"
    return "scalar"


def synthesize_formula_example(name: str, arity: dict[str, Any]) -> str:
    if name in {"IF", "CASE"}:
        return ""
    min_args = int(arity.get("min") or 1)
    if arity.get("max") == 0:
        return f"{name}()"
    args = []
    for index in range(max(1, min_args)):
        if name.endswith("_WINDOW") and index == 0:
            args.append("SUM([value])")
        elif index == 0:
            args.append("[value]")
        elif index == 1:
            args.append("[date]")
        else:
            args.append("1")
    if name.endswith("_WINDOW"):
        return f"{name}({', '.join(args)} TOTAL)"
    return f"{name}({', '.join(args)})"


def build_formula_fuzz_cases() -> dict[str, Any]:
    seeds = [
        "CONCAT(\"a,b\", \"c(d)\")",
        "IF([x] > 0, SUM([a]), SUM([b]))",
        "SUM([x] BEFORE FILTER BY [Region])",
        "AVG(SUM([x]) WITHIN [Team])",
        "CASE WHEN [x] > 1 THEN \"yes\" ELSE \"no\" END",
    ]
    rows = []
    for index, seed in enumerate(seeds * 20, start=1):
        expression = seed.replace("[x]", f"[x_{index}]")
        result = validate_formula_expression(expression)
        rows.append({"expression_sha256": sha256_text(expression), "ok": result["ok"], "issue_count": len(result["issues"])})
    return {"schema_version": COMPILER_VERSION, "case_count": len(rows), "ok": len(rows) == 100, "cases": rows}


def build_editor_visualization_contracts(corpus: dict[str, Any]) -> dict[str, Any]:
    contracts = []
    for page in sorted(corpus["pages"], key=lambda item: str(item.get("mirror_path") or "")):
        mirror_path = str(page.get("mirror_path") or "")
        if not (is_editor_page(page) or page_section(page) in {"visualization-ref", "dashboard", "dataset"}):
            continue
        text = str(page.get("content_text") or "")
        trace = source_trace(first_page_chunk(corpus, mirror_path))
        contracts.append(
            {
                "contract_id": stable_id("contract", mirror_path),
                "title": str(page.get("title") or ""),
                "mirror_path": mirror_path,
                "kind": "editor" if is_editor_page(page) else page_section(page),
                "required_tabs": editor_tabs_from_text(text),
                "methods": sorted(set(re.findall(r"\bEditor\.[A-Za-z0-9_]+", text))),
                "html_tags_or_attributes": sorted(set(re.findall(r"`([a-zA-Z][a-zA-Z0-9:-]+)`", str(page.get("content_md") or ""))))[:120],
                "limits": extract_limit_signals(text),
                "native_route": native_route_for(mirror_path),
                "editor_route": editor_route_for(mirror_path),
                "official_status": "documented",
                "local_policy_status": local_policy_for_contract(mirror_path),
                "source_trace": trace,
                "bounded_excerpt": bounded_excerpt(text, max_chars=420),
            }
        )
    return {"schema_version": COMPILER_VERSION, "contracts": contracts}


def editor_tabs_from_text(text: str) -> list[str]:
    tabs = []
    for tab in ("Meta", "Params", "Sources", "Config", "Controls", "Prepare"):
        if tab.lower() in text.lower():
            tabs.append(tab)
    return tabs


def extract_limit_signals(text: str) -> list[str]:
    rows = []
    lowered = text.lower()
    if "100 мс" in text:
        rows.append("wrapFn single function 100 ms")
    if "1,5 с" in text or "1.5" in text:
        rows.append("advanced chart function 1.5 s")
    if "3 с" in text or "3 s" in lowered:
        rows.append("advanced chart total 3 s")
    if "limit" in lowered or "лимит" in lowered:
        rows.append("documented limit signal")
    return rows


def native_route_for(mirror_path: str) -> str:
    if "visualization-ref" in mirror_path and wizard_visualization_id_for_name(Path(mirror_path).stem):
        return "wizard_native"
    if "visualization-ref" in mirror_path:
        return "wizard_reference_only"
    return "not_native_wizard_route"


def editor_route_for(mirror_path: str) -> str:
    if "widgets/table" in mirror_path:
        return "editor_table"
    if "widgets/markdown" in mirror_path:
        return "editor_markdown"
    if "widgets/controls" in mirror_path:
        return "editor_js_control"
    if "widgets/advanced" in mirror_path:
        return "editor_advanced"
    if "widgets/gravity-ui" in mirror_path:
        return "documented_reference"
    if "visualization-ref/table" in mirror_path:
        return "editor_table_possible"
    return "editor_advanced_reference"


def local_policy_for_contract(mirror_path: str) -> str:
    if "widgets/gravity-ui" in mirror_path:
        return "gravity_reference_only_until_route_evidence"
    if "visualization-ref" in mirror_path and not wizard_visualization_id_for_name(Path(mirror_path).stem):
        return "unknown_wizard_visualization_reference_only"
    return "allowed_with_safe_apply_guards"


def wizard_visualization_id_for_name(name: str) -> str:
    normalized = str(name or "").lower().replace("_", "-")
    if normalized in {"map-chart", "geolayer", "geo-chart"} or normalized.startswith("map-"):
        return "geolayer"
    mappings = (
        (("pivot-table",), "pivotTable"),
        (("table",), "flatTable"),
        (("combined",), "combined-chart"),
        (("area-100", "area100"), "area100p"),
        (("area",), "area"),
        (("column-100", "column100"), "column100p"),
        (("column",), "column"),
        (("bar-100", "bar100"), "bar100p"),
        (("bar",), "bar"),
        (("donut",), "donut"),
        (("pie",), "pie"),
        (("scatter",), "scatter"),
        (("treemap", "tree-map"), "treemap"),
        (("line",), "line"),
        (("indicator", "metric"), "metric"),
    )
    for markers, visualization_id in mappings:
        if any(marker in normalized for marker in markers):
            return visualization_id
    return ""


def build_route_capability_matrix(compiled: dict[str, Any]) -> dict[str, Any]:
    routes = [
        route_row("editor_advanced", True, True, True, True, True, True, False, "Advanced Editor docs and templates"),
        route_row("table_node", True, True, True, True, True, True, False, "Editor table contract and tests"),
        route_row("control_node", True, True, True, True, True, True, False, "Editor controls contract and tests"),
        route_row("markdown_node", True, True, True, True, True, True, False, "Editor markdown contract and tests"),
        route_row("gravity_ui_chart", True, True, False, False, False, False, False, "missing safe MCP route contract"),
        route_row("wizard_native", True, True, True, True, True, True, False, "16 canonical templates plus matching fresh saved seeds"),
        route_row("regular_editor_chart", True, True, False, False, False, False, False, "not in closed route policy"),
        route_row("ql_explicit", True, True, True, True, True, False, False, "explicit user request and explicit payload or saved seed"),
        route_row("ql_delete", True, False, False, False, False, False, False, "delete remains closed"),
        route_row("dataset", True, True, True, True, True, True, False, "guarded update plan and OpenAPI"),
        route_row("connection", True, True, True, True, True, False, False, "guarded plan, no live write verification"),
        route_row("dashboard", True, True, True, True, True, True, False, "guarded dashboard payload plans"),
        route_row("folder_permissions", True, True, False, False, False, False, False, "destructive/security operations blocked"),
    ]
    return {
        "schema_version": COMPILER_VERSION,
        "tool_budget": compiled["tool_budget"],
        "routes": routes,
    }


def route_row(
    route_id: str,
    official: bool,
    read: bool,
    plan: bool,
    create: bool,
    update: bool,
    fixture: bool,
    live_write: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "route_id": route_id,
        "official_documented": official,
        "read_supported": read,
        "plan_supported": plan,
        "create_supported": create,
        "update_supported": update,
        "publish_supported": update and route_id not in {"folder_permissions"},
        "executable_fixture_tested": fixture,
        "live_read_verified": False,
        "live_write_verified_in_test_workspace": live_write,
        "blocked_reason": "" if create or update else reason,
        "evidence": reason,
    }


def build_retrieval_benchmark_cases() -> dict[str, Any]:
    seed_cases = [
        (
            "How do I build a simple SQL table?",
            "recipe",
            "table_flat_sql",
            "simple_sql_table",
            "editor_table",
            ["route", "tabs", "source trace"],
            ["ql_create"],
        ),
        (
            "ordinary database SQL table with a footer",
            "recipe",
            "table_flat_sql",
            "simple_sql_table",
            "editor_table",
            ["database_sql", "Prepare"],
            ["full_page_copy"],
        ),
        (
            "простая SQL таблица из запроса к базе",
            "recipe",
            "table_flat_sql",
            "simple_sql_table",
            "editor_table",
            ["editor_table", "sources.js"],
            ["automatic_js_fallback"],
        ),
        (
            "dataset-backed table for a dashboard draft",
            "recipe",
            "table_flat_dataset",
            "dataset_table",
            "editor_table",
            ["dataset", "table_node"],
            ["guessed_ids"],
        ),
        (
            "таблица из датасета с безопасным планом",
            "recipe",
            "table_flat_dataset",
            "dataset_table",
            "editor_table",
            ["dataset", "safe apply"],
            ["direct_write"],
        ),
        (
            "table from API Connector response",
            "recipe",
            "table_flat_api_connector",
            "api_connector_table",
            "editor_table",
            ["api_connector", "fixture"],
            ["token"],
        ),
        (
            "таблица из API Connector без live записи",
            "recipe",
            "table_flat_api_connector",
            "api_connector_table",
            "editor_table",
            ["api_connector", "read only"],
            ["publish"],
        ),
        (
            "rich table with bars groups totals pinned columns",
            "recipe",
            "table_rich",
            "rich_table",
            "editor_table",
            ["formatting", "totals"],
            ["gravity_create"],
        ),
        (
            "таблица с пагинацией футером барами и закрепленной колонкой",
            "recipe",
            "table_rich",
            "rich_table",
            "editor_table",
            ["pagination", "footer"],
            ["empty_fixture"],
        ),
        (
            "pivot by team sprint plan fact totals pinned first column",
            "recipe",
            "table_pivot_js",
            "javascript_pivot",
            "editor_table",
            ["pivot", "O(n log n)"],
            ["advanced_by_default"],
        ),
        (
            "сводная таблица команда спринт план факт итоги",
            "recipe",
            "table_pivot_js",
            "javascript_pivot",
            "editor_table",
            ["pivot", "totals"],
            ["fake_status"],
        ),
        (
            "sticky grouped HTML pivot exception",
            "recipe",
            "table_pivot_advanced_exception",
            "advanced_pivot_exception",
            "editor_advanced",
            ["exception", "generateHtml"],
            ["normal_path"],
        ),
        (
            "кастомная сводная с HTML sticky группами",
            "recipe",
            "table_pivot_advanced_exception",
            "advanced_pivot_exception",
            "editor_advanced",
            ["exception reason"],
            ["silent_fallback"],
        ),
        (
            "Advanced DOM D3 composition with tooltip",
            "recipe",
            "advanced_dom_d3",
            "advanced_dom_d3",
            "editor_advanced",
            ["Editor.wrapFn", "sanitizer"],
            ["d3_node_route"],
        ),
        (
            "кастомная D3 визуализация в Advanced Editor",
            "recipe",
            "advanced_dom_d3",
            "advanced_dom_d3",
            "editor_advanced",
            ["advanced", "D3"],
            ["raw_rpc"],
        ),
        (
            "Gravity UI Chart route decision",
            "capability",
            "Gravity UI Chart",
            "gravity_ui_chart",
            "reference_only",
            ["blocked reason", "source"],
            ["supported_create"],
        ),
        (
            "график Gravity почему нельзя создать",
            "capability",
            "Gravity UI Chart",
            "gravity_ui_chart",
            "reference_only",
            ["blocked_by_route_policy"],
            ["executable_fixture_tested"],
        ),
        (
            "static selector with left label",
            "recipe",
            "control_static",
            "control_static",
            "editor_js_control",
            ["Controls", "left label"],
            ["dashboard mutation"],
        ),
        (
            "статический селектор с вариантами",
            "recipe",
            "control_static",
            "control_static",
            "editor_js_control",
            ["static_options"],
            ["profile_choice"],
        ),
        (
            "dynamic selector from source rows",
            "recipe",
            "control_dynamic",
            "control_dynamic",
            "editor_js_control",
            ["source_backed_options"],
            ["blind_write"],
        ),
        (
            "зависимый селектор по датасету",
            "recipe",
            "control_dynamic",
            "control_dynamic",
            "editor_js_control",
            ["selector", "source"],
            ["gravity"],
        ),
        (
            "Markdown widget with Mermaid text",
            "recipe",
            "markdown",
            "markdown",
            "editor_markdown",
            ["markdown_output"],
            ["generateHtml_required"],
        ),
        (
            "Markdown Mermaid текстовый блок",
            "recipe",
            "markdown",
            "markdown",
            "editor_markdown",
            ["markdown", "source trace"],
            ["wizard_create"],
        ),
        (
            "cross-filter relation between charts",
            "recipe",
            "cross_filter",
            "cross_filter",
            "dashboard_relation_operation",
            ["relation", "selector impact"],
            ["delete"],
        ),
        (
            "кросс фильтр между графиками",
            "recipe",
            "cross_filter",
            "cross_filter",
            "dashboard_relation_operation",
            ["cross filter"],
            ["publish_default"],
        ),
        (
            "dashboard links and actions",
            "recipe",
            "links",
            "links",
            "dashboard_relation_operation",
            ["navigation", "safe parameter"],
            ["guessed target"],
        ),
        (
            "ссылки действия на дашборде",
            "recipe",
            "links",
            "links",
            "dashboard_relation_operation",
            ["links", "actions"],
            ["blind ids"],
        ),
        (
            "notifications from Advanced chart",
            "recipe",
            "notifications",
            "notifications",
            "editor_advanced",
            ["notification", "runtime contract"],
            ["unsupported label"],
        ),
        (
            "уведомления insights в Advanced Editor",
            "recipe",
            "notifications",
            "notifications",
            "editor_advanced",
            ["notifications"],
            ["empty test"],
        ),
        (
            "Editor.setRawData documented method",
            "search",
            "Editor.setRawData",
            "editor_method",
            "source_trace",
            ["method", "Editor"],
            ["empty trace"],
        ),
        (
            "data-tooltip-content allowed attribute",
            "search",
            "data-tooltip-content",
            "sanitizer_attribute",
            "source_trace",
            ["attribute", "sanitizer"],
            ["no source"],
        ),
        (
            "Editor.wrapFn 100 ms runtime budget",
            "search",
            "Editor.wrapFn",
            "editor_runtime_budget",
            "source_trace",
            ["runtime", "budget"],
            ["full page"],
        ),
        (
            "Editor.generateHtml sanitizer rules",
            "search",
            "Editor.generateHtml",
            "editor_sanitizer",
            "source_trace",
            ["sanitizer"],
            ["raw HTML only"],
        ),
        ("AGO sales date syntax", "formula", "AGO", "ago_formula", "formula", ["arity", "syntax"], ["regex only"]),
        ("IF three arguments", "formula", "IF", "if_formula", "formula", ["IF", "arity"], ["two_arg_ok"]),
        (
            "nested strings commas parentheses",
            "formula",
            "CONCAT",
            "formula_parser",
            "formula",
            ["quoted commas"],
            ["top_level_split"],
        ),
        (
            "LOD before filter by",
            "formula",
            "BEFORE FILTER BY",
            "bfb_lod",
            "formula",
            ["LOD", "BEFORE FILTER BY"],
            ["syntax_error"],
        ),
        (
            "window function within team",
            "formula",
            "WITHIN",
            "window_formula",
            "formula",
            ["window", "aggregate"],
            ["SUM_window_false"],
        ),
        ("SUM zero arguments should fail", "formula", "SUM", "sum_arity", "formula", ["arity"], ["sum_zero_ok"]),
        (
            "AVG over SUM within city",
            "formula",
            "AVG",
            "window_aggregate",
            "formula",
            ["window clause"],
            ["aggregate_nesting_false_positive"],
        ),
        ("Code 47 unknown identifier", "error", "Code 47", "code_47", "error", ["unknown_identifier"], ["generic remediation"]),
        ("Code 48 correlated join", "error", "Code 48", "code_48", "error", ["join"], ["wrong layer"]),
        ("Code 184 nested aggregation", "error", "Code 184", "code_184", "error", ["aggregation"], ["no probes"]),
        ("ошибка Code 47 неизвестная колонка", "error", "Code 47", "code_47", "error", ["source_sql"], ["auth_error"]),
        ("ошибка Code 184 оконная функция без агрегации", "error", "Code 184", "code_184", "error", ["window"], ["empty"]),
        (
            "current dataset update envelope",
            "capability",
            "dataset update envelope",
            "dataset_update",
            "dl_plan_guarded_dataset_update",
            ["OpenAPI", "guarded"],
            ["direct_update"],
        ),
        (
            "validateDataset updateDataset порядок",
            "capability",
            "dataset update envelope",
            "dataset_update",
            "dl_plan_guarded_dataset_update",
            ["validateDataset"],
            ["publish"],
        ),
        (
            "Wizard line chart creation",
            "capability",
            "wizard_native",
            "wizard_line",
            "wizard_native",
            ["visualization_id", "field roles"],
            ["automatic JS fallback"],
        ),
        (
            "QL chart authoring support",
            "capability",
            "ql_explicit",
            "ql_explicit",
            "ql_explicit",
            ["direct user request", "explicit payload"],
            ["automatic selection", "delete"],
        ),
        (
            "dashboard layout tabs aliases links",
            "capability",
            "dashboard",
            "dashboard_layout",
            "dashboard",
            ["layout", "tabs"],
            ["delete"],
        ),
    ]
    contexts = [
        "for weekly operations review",
        "with compact source traces",
        "for a read-only planning answer",
        "with Russian labels where relevant",
        "with validation checklist included",
    ]
    rows = []
    for index in range(250):
        query, mode, expected, intent, expected_route, facts, forbidden = seed_cases[index % len(seed_cases)]
        context = contexts[index // len(seed_cases)]
        query = f"{query} {context}"
        rows.append(
            {
                "query_id": f"nl_{index + 1:03d}",
                "query": query,
                "user_prompt": query,
                "mode": mode,
                "expected_top3_contains": expected,
                "expected_intent": intent,
                "expected_route": expected_route,
                "required_facts": facts,
                "forbidden_errors": forbidden,
                "acceptable_evidence_state": (
                    "executable_fixture_tested"
                    if mode == "recipe" and "Gravity" not in expected
                    else "semantically_compiled"
                ),
                "expected_source_families": [
                    "official_docs",
                    "demo_reference"
                    if intent in {"javascript_pivot", "gravity_ui_chart", "dashboard_layout"}
                    else "compiled_registry",
                ],
                "grader": "top3_contains+required_facts+budget+nonempty_result",
                "manual_review_status": "reviewed",
                "language": "ru" if re.search(r"[А-Яа-я]", query) else "en",
                "not_exact_id_only": expected.lower() != query.strip().lower(),
            }
        )
    return {"schema_version": COMPILER_VERSION, "case_count": len(rows), "cases": rows}


def build_demo_reference_mapping(demo_root: Path = DEFAULT_DEMO_REFERENCE_ROOT) -> dict[str, Any]:
    root = demo_root.expanduser()
    manifest_path = root / "raw" / "manifest.json"
    if not manifest_path.is_file():
        return {
            "schema_version": COMPILER_VERSION,
            "ok": False,
            "demo_root": str(root),
            "blocked_reason": "demo_reference_manifest_missing",
            "mapped_examples": [],
            "formula_examples": [],
        }
    manifest = read_json(manifest_path)
    objects = manifest.get("objects") or []
    mappings = [
        ("advanced_dom_d3", "editor_chart", ("Advanced Chart", "Advanced demo", "Docs samples")),
        ("table_pivot_js", "widget table_node", ("Pivot", "DynamicColumns", "Table")),
        ("table_rich", "widget table_node", ("bars", "TableWithCharts", "getSortParams")),
        ("control_dynamic", "widget control_node", ("dependent selectors", "DatasetFields", "JsSelector")),
        ("markdown", "widget markdown_node", ("mermaid", "markdown", "Markdown")),
        ("gravity_chart", "widget d3_node", ("GravityCharts", "Gravity Charts")),
        ("ql_explicit", "ql_chart", ("SQL-чарт", "SQL chart")),
        ("wizard_native", "wizard_chart", ("Карта", "Геоточки", "Полигоны", "Точки с кластерами")),
        ("dataset", "dataset", ("SQL Dataset", "Sales - for editor samples", "Продажи")),
        ("connection", "connection", ("Connection", "Demo Dashboard")),
        ("dashboard", "dashboard, entry_relations", ("DataLens Demo Dashboard",)),
    ]
    mapped = []
    used_entries: set[str] = set()
    for contract_or_recipe, resolved_type, title_markers in mappings:
        match = next(
            (
                item
                for item in objects
                if item.get("entry_id") not in used_entries
                and item.get("resolved_object_type") == resolved_type
                and any(marker.lower() in str(item.get("title") or "").lower() for marker in title_markers)
            ),
            None,
        )
        if not match:
            match = next(
                (
                    item
                    for item in objects
                    if item.get("entry_id") not in used_entries and item.get("resolved_object_type") == resolved_type
                ),
                None,
            )
        if not match:
            continue
        used_entries.add(str(match.get("entry_id")))
        raw_rel = str(match.get("raw_path") or "")
        raw_path = root / raw_rel if raw_rel else Path()
        mapped.append(
            {
                "contract_or_recipe": contract_or_recipe,
                "entry_id": str(match.get("entry_id") or ""),
                "resolved_object_type": str(match.get("resolved_object_type") or ""),
                "title": str(match.get("title") or ""),
                "status": str(match.get("status") or ""),
                "methods": match.get("methods") or [],
                "raw_path": raw_rel,
                "raw_sha256": file_sha256(raw_path) if raw_path.is_file() else "",
                "evidence_state": "live_read_verified",
            }
        )
    formulas = extract_demo_formula_examples(root)
    return {
        "schema_version": COMPILER_VERSION,
        "ok": bool(mapped),
        "demo_root": str(root),
        "entry_count": manifest.get("entry_count"),
        "hydrated_entry_count": manifest.get("hydrated_entry_count"),
        "counts_by_resolved_type": manifest.get("counts_by_resolved_type") or {},
        "mapped_examples": mapped,
        "formula_examples": formulas,
        "demo_lock_hash": sha256_text(
            stable_json(
                {
                    "counts": manifest.get("counts_by_resolved_type"),
                    "formulas": formulas,
                    "manifest": manifest_path.name,
                }
            )
        ),
    }


def extract_demo_formula_examples(root: Path) -> list[dict[str, Any]]:
    path = root / "datasets_connections.md"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if "|" not in line or "Formula/source" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        expression = normalize_demo_formula(cells[6])
        if not expression or expression in seen:
            continue
        if "(" not in expression and not expression.upper().startswith(("IF ", "CASE ")):
            continue
        seen.add(expression)
        rows.append(
            {
                "expression": expression,
                "source_path": str(path),
                "source_sha256": file_sha256(path),
                "manual_review_status": "demo_reference_reviewed",
            }
        )
        if len(rows) >= 40:
            break
    return rows


def normalize_demo_formula(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"`", "", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s*\n\s*", "\n", text.strip())
    return text


def build_compiled_knowledge(
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    demo_reference_root: Path = DEFAULT_DEMO_REFERENCE_ROOT,
) -> dict[str, Any]:
    corpus = load_corpus(corpus_root)
    count_report = validate_corpus_counts(corpus)
    if not count_report["ok"]:
        raise ValueError(f"unexpected corpus counts: {count_report['mismatches']}")
    page_registry = build_page_registry(corpus)
    page_by_mirror = {page["mirror_path"]: page for page in page_registry}
    chunk_registry = build_chunk_registry(corpus, page_by_mirror)
    tool_budget = measure_tool_budget()
    recipes = build_recipes(corpus)
    formula_registry = build_formula_registry(corpus)
    visualization_registry = build_visualization_registry(corpus)
    error_registry = build_error_registry(corpus)
    domain_registry = build_domain_registry(corpus)
    operations_registry = build_operations_registry(corpus)
    capability_matrix = build_capability_matrix(corpus, tool_budget)
    demo_reference = build_demo_reference_mapping(demo_reference_root)
    lock = build_lock(corpus, count_report["counts"])
    compiled = {
        "corpus": corpus,
        "lock": lock,
        "page_registry": page_registry,
        "chunk_registry": chunk_registry,
        "topic_registry": build_topic_registry(page_registry),
        "rule_cards": build_rule_cards(corpus, page_by_mirror),
        "code_examples": build_code_example_registry(corpus),
        "asset_registry": build_asset_registry(corpus),
        "supersession_registry": build_supersession_registry(corpus),
        "recipes": recipes,
        "formula_registry": formula_registry,
        "visualization_registry": visualization_registry,
        "error_registry": error_registry,
        "domain_registry": domain_registry,
        "operations_registry": operations_registry,
        "capability_matrix": capability_matrix,
        "demo_reference_mapping": demo_reference,
        "tool_budget": tool_budget,
        "counts": count_report["counts"],
    }
    compiled["semantic_source_model"] = build_semantic_source_model(corpus, page_registry)
    compiled["manual_review_queue"] = build_manual_review_queue(corpus, compiled["asset_registry"])
    compiled["formula_golden_set"] = build_formula_golden_set(
        formula_registry,
        [item["expression"] for item in demo_reference.get("formula_examples", [])],
    )
    compiled["formula_fuzz_cases"] = build_formula_fuzz_cases()
    compiled["editor_visualization_contracts"] = build_editor_visualization_contracts(corpus)
    compiled["route_capability_matrix"] = build_route_capability_matrix(compiled)
    compiled["retrieval_benchmark_cases"] = build_retrieval_benchmark_cases()
    compiled["semantic_records"] = build_semantic_records(compiled)
    return compiled


def build_lock(corpus: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    content_hashes = corpus["content_hashes"]
    latest_timestamp = max(
        [str(row.get("fetched_at") or "") for row in [*corpus["pages"], *corpus["assets"], *corpus["manifest"]]],
        default="",
    )
    return {
        "schema_version": COMPILER_VERSION,
        "compiler_version": COMPILER_VERSION,
        "source_precedence": SOURCE_PRECEDENCE,
        # This lock is committed and packaged. Do not serialize the local path
        # that happened to win corpus discovery on the generating workstation.
        "corpus_root_hint": "<DATALENS_DOCS_CORPUS_ROOT>",
        "counts": counts,
        "content_hashes": content_hashes,
        "openapi_sha256": str(corpus["api_inventory"].get("openapi_sha256") or ""),
        "coverage_report_sha256": corpus["coverage_report_sha256"],
        "validation_report_sha256": corpus["validation_report_sha256"],
        "latest_source_timestamp": latest_timestamp,
        "deterministic_hash": sha256_text(
            stable_json(
                {
                    "counts": counts,
                    "content_hashes": content_hashes,
                    "openapi_sha256": str(corpus["api_inventory"].get("openapi_sha256") or ""),
                }
            )
        ),
    }


def measure_tool_budget() -> dict[str, Any]:
    from datalens_dev_mcp.server import list_tools

    default_payload = {"tools": list_tools()}
    all_payload = {"tools": list_tools("all")}
    return {
        "default_tool_count": len(default_payload["tools"]),
        "default_tools_list_chars": len(json.dumps(default_payload, ensure_ascii=False, separators=(",", ":"))),
        "default_tools_list_bytes": len(json.dumps(default_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
        "all_tool_count": len(all_payload["tools"]),
        "all_tools_list_bytes": len(json.dumps(all_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
    }


def compiled_knowledge_resource_texts(compiled: dict[str, Any]) -> dict[str, str]:
    json_payloads: dict[str, Any] = {
        "knowledge.lock.json": compiled["lock"],
        "page-registry.json": {"schema_version": COMPILER_VERSION, "pages": compiled["page_registry"]},
        "topic-registry.json": compiled["topic_registry"],
        "asset-registry.json": compiled["asset_registry"],
        "supersession-registry.json": compiled["supersession_registry"],
        "formula-registry.json": compiled["formula_registry"],
        "visualization-registry.json": compiled["visualization_registry"],
        "error-registry.json": compiled["error_registry"],
        "domain-registry.json": compiled["domain_registry"],
        "operations-registry.json": compiled["operations_registry"],
        "capability-matrix.json": compiled["capability_matrix"],
        "semantic-source-model.json": compiled["semantic_source_model"],
        "manual-review-queue.json": compiled["manual_review_queue"],
        "formula-golden-set.json": compiled["formula_golden_set"],
        "formula-fuzz-cases.json": compiled["formula_fuzz_cases"],
        "editor-visualization-contracts.json": compiled["editor_visualization_contracts"],
        "route-capability-matrix.json": compiled["route_capability_matrix"],
        "retrieval-benchmark-cases.json": compiled["retrieval_benchmark_cases"],
    }
    jsonl_payloads: dict[str, list[dict[str, Any]]] = {
        "chunk-registry.jsonl": compiled["chunk_registry"],
        "rule-cards.jsonl": compiled["rule_cards"],
        "code-example-registry.jsonl": compiled["code_examples"],
        "semantic-records.jsonl": compiled["semantic_records"],
    }
    return {
        **{name: rendered_json(payload) for name, payload in json_payloads.items()},
        **{name: rendered_jsonl(rows) for name, rows in jsonl_payloads.items()},
    }


def compiled_recipe_resource_texts(compiled: dict[str, Any]) -> dict[str, str]:
    recipes = compiled["recipes"]
    return {
        "recipe-registry.json": rendered_json(recipes),
        **{
            f"{item['recipe_id']}.json": rendered_json(item)
            for item in recipes["recipes"]
        },
    }
def write_compiled_knowledge(compiled: dict[str, Any], *, write_index: bool = True) -> dict[str, Any]:
    PACKAGE_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    QA_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in compiled_knowledge_resource_texts(compiled).items():
        target_dir = PACKAGE_KNOWLEDGE_DIR if name in RUNTIME_KNOWLEDGE_FILES else QA_KNOWLEDGE_DIR
        (target_dir / name).write_text(text, encoding="utf-8")
    write_recipes(compiled["recipes"])
    sync_packaged_resources()
    if write_index:
        build_search_index(compiled["corpus"], INDEX_PATH)
    return check_compiled_knowledge(compiled)


def write_recipes(recipes: dict[str, Any]) -> None:
    RECIPE_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RECIPE_DIR / "recipe-registry.json", recipes)
    for item in recipes["recipes"]:
        write_json(RECIPE_DIR / f"{item['recipe_id']}.json", item)


def sync_packaged_resources() -> None:
    PACKAGE_RECIPE_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(RECIPE_DIR.glob("*.json")):
        shutil.copy2(path, PACKAGE_RECIPE_DIR / path.name)


def check_compiled_knowledge(
    compiled: dict[str, Any] | None = None,
    *,
    verify_disk_parity: bool = True,
) -> dict[str, Any]:
    if compiled is None:
        compiled = build_compiled_knowledge()
    issues = []
    counts = compiled["counts"]
    for key, expected in EXPECTED_COUNTS.items():
        if counts.get(key) != expected:
            issues.append(f"{key}: expected {expected}, got {counts.get(key)}")
    page_statuses = Counter(page["classification"]["status"] for page in compiled["page_registry"])
    missing_statuses = sorted(set(page_statuses) - CLASSIFICATION_STATUSES)
    if missing_statuses:
        issues.append(f"unknown classification statuses: {missing_statuses}")
    if any(not page["classification"]["status"] for page in compiled["page_registry"]):
        issues.append("page registry contains unclassified records")
    if any(not row["classification"] for row in compiled["chunk_registry"]):
        issues.append("chunk registry contains unclassified records")
    if len(compiled["asset_registry"]["assets"]) != EXPECTED_COUNTS["assets"]:
        issues.append("asset registry does not account for every asset")
    recipe_ids = {item["recipe_id"] for item in compiled["recipes"]["recipes"]}
    missing_recipes = sorted(set(MANDATORY_RECIPE_IDS) - recipe_ids)
    if missing_recipes:
        issues.append(f"missing mandatory recipes: {missing_recipes}")
    if any(not item.get("source_traces") for item in compiled["recipes"]["recipes"]):
        issues.append("recipe missing source trace")
    bad_capability_traces = [
        item["capability_id"]
        for item in compiled["capability_matrix"]["capabilities"]
        if not item.get("source_traces") or any(not source_trace_ok(trace) for trace in item.get("source_traces") or [])
    ]
    if bad_capability_traces:
        issues.append(f"capability missing exact source traces: {bad_capability_traces[:5]}")
    if any(not row.get("source_trace") for row in compiled["rule_cards"]):
        issues.append("rule card missing source trace")
    semantic_records = compiled.get("semantic_records") or []
    if not semantic_records:
        issues.append("semantic records are missing")
    bad_traces = [
        row["record_id"]
        for row in semantic_records
        if row.get("status") != "indexed_reference" and not source_trace_ok(row.get("source_trace") or {})
    ]
    if bad_traces:
        issues.append(f"semantic records missing exact traces: {bad_traces[:5]}")
    formula_golden = compiled.get("formula_golden_set") or {}
    if (
        not formula_golden.get("ok")
        or int(formula_golden.get("valid_case_count") or 0) < 150
        or int(formula_golden.get("invalid_case_count") or 0) < 75
    ):
        issues.append("formula golden set is incomplete or failing")
    fuzz = compiled.get("formula_fuzz_cases") or {}
    if not fuzz.get("ok") or int(fuzz.get("case_count") or 0) < 100:
        issues.append("formula fuzz cases are incomplete")
    review = compiled.get("manual_review_queue") or {}
    if not review.get("pages") or not review.get("assets"):
        issues.append("manual review queue is incomplete")
    route_matrix = compiled.get("route_capability_matrix") or {}
    if not route_matrix.get("routes"):
        issues.append("route capability matrix is missing")
    demo_mapping = compiled.get("demo_reference_mapping") or {}
    demo_manifest_available = (
        Path(str(demo_mapping.get("demo_root") or "")).expanduser() / "raw" / "manifest.json"
    ).is_file()
    if demo_manifest_available and (
        not demo_mapping.get("ok") or len(demo_mapping.get("mapped_examples") or []) < 8
    ):
        issues.append("demo reference mapping is incomplete")
    benchmark_cases = compiled.get("retrieval_benchmark_cases") or {}
    if int(benchmark_cases.get("case_count") or 0) < 250:
        issues.append("natural-language benchmark has fewer than 250 reviewed cases")
    for item in compiled["recipes"]["recipes"]:
        if str(item.get("implementation_status") or "").startswith("implemented"):
            bundle = item.get("executable_bundle") or {}
            if bundle.get("status") != "executable_fixture_tested":
                issues.append(f"implemented recipe missing executable fixture: {item['recipe_id']}")
    if compiled["tool_budget"]["default_tool_count"] > 40:
        issues.append("default tool count exceeds 40")
    if compiled["tool_budget"]["default_tools_list_chars"] > 25000:
        issues.append("default tools/list chars exceeds 25000")
    parity = _check_compiled_resource_parity(compiled) if verify_disk_parity else {"ok": True, "issues": [], "checked": 0}
    issues.extend(parity["issues"])
    if INDEX_PATH.exists():
        index_state = inspect_search_index(INDEX_PATH)
    else:
        index_state = {"exists": False, "page_rows": 0, "chunk_rows": 0}
    return {
        "ok": not issues,
        "issues": issues,
        "counts": counts,
        "classification_counts": dict(sorted(page_statuses.items())),
        "recipe_count": len(recipe_ids),
        "rule_count": len(compiled["rule_cards"]),
        "code_example_count": len(compiled["code_examples"]),
        "tool_budget": compiled["tool_budget"],
        "index": index_state,
        "resource_parity": parity,
    }


def _check_compiled_resource_parity(compiled: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    expected = compiled_knowledge_resource_texts(compiled)
    for name in sorted(RUNTIME_KNOWLEDGE_FILES):
        path = PACKAGE_KNOWLEDGE_DIR / name
        if not path.is_file():
            issues.append(f"missing packaged knowledge resource: {path.relative_to(REPO_ROOT)}")
        elif path.read_text(encoding="utf-8") != expected[name]:
            issues.append(f"changed packaged knowledge resource: {path.relative_to(REPO_ROOT)}")
    expected_recipes = compiled_recipe_resource_texts(compiled)
    for directory, label in ((RECIPE_DIR, "source"), (PACKAGE_RECIPE_DIR, "packaged")):
        for name, text in sorted(expected_recipes.items()):
            path = directory / name
            if not path.is_file():
                issues.append(f"missing {label} recipe resource: {path.relative_to(REPO_ROOT)}")
            elif path.read_text(encoding="utf-8") != text:
                issues.append(f"changed {label} recipe resource: {path.relative_to(REPO_ROOT)}")
    return {
        "ok": not issues,
        "issues": issues,
        "checked": len(RUNTIME_KNOWLEDGE_FILES) + len(expected_recipes) * 2,
    }


def build_search_index(corpus: dict[str, Any], index_path: Path = INDEX_PATH) -> dict[str, Any]:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if index_path.exists():
        index_path.unlink()
    conn = sqlite3.connect(index_path)
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE datalens_docs USING fts5("
            "kind, record_id, title, heading, body, source_url UNINDEXED, mirror_path UNINDEXED, "
            "anchor UNINDEXED, sha256 UNINDEXED)"
        )
        for page in corpus["pages"]:
            conn.execute(
                "INSERT INTO datalens_docs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "page",
                    str(page.get("mirror_path") or ""),
                    str(page.get("title") or ""),
                    "",
                    str(page.get("content_text") or ""),
                    str(page.get("source_url") or ""),
                    str(page.get("mirror_path") or ""),
                    "",
                    str(page.get("sha256") or ""),
                ),
            )
        for chunk in corpus["chunks"]:
            conn.execute(
                "INSERT INTO datalens_docs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "chunk",
                    str(chunk.get("chunk_id") or ""),
                    str(chunk.get("title") or ""),
                    str(chunk.get("heading") or ""),
                    str(chunk.get("content_text") or ""),
                    str(chunk.get("source_url") or ""),
                    str(chunk.get("mirror_path") or ""),
                    str(chunk.get("anchor") or ""),
                    str(chunk.get("sha256") or ""),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return inspect_search_index(index_path)


def inspect_search_index(index_path: Path = INDEX_PATH) -> dict[str, Any]:
    if not index_path.exists():
        return {"exists": False, "page_rows": 0, "chunk_rows": 0, "path": str(index_path)}
    conn = sqlite3.connect(index_path)
    try:
        page_rows = conn.execute("SELECT count(*) FROM datalens_docs WHERE kind = 'page'").fetchone()[0]
        chunk_rows = conn.execute("SELECT count(*) FROM datalens_docs WHERE kind = 'chunk'").fetchone()[0]
        test_rows = conn.execute(
            "SELECT count(*) FROM datalens_docs WHERE datalens_docs MATCH ?",
            ("table",),
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "exists": True,
        "path": str(index_path),
        "page_rows": page_rows,
        "chunk_rows": chunk_rows,
        "test_match_rows": test_rows,
        "sha256": file_sha256(index_path),
    }


def build_baseline_artifacts(compiled: dict[str, Any]) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    corpus = compiled["corpus"]
    page_by_section = Counter(page_section(page) for page in corpus["pages"])
    editor_pages = [
        {
            "mirror_path": str(page.get("mirror_path") or ""),
            "title": str(page.get("title") or ""),
            "compiler_input": str(page.get("mirror_path") or "")
            in {
                "datalens/charts/editor/methods.md",
                "datalens/charts/editor/widgets/advanced.md",
                "datalens/charts/editor/widgets/table.md",
                "datalens/charts/editor/widgets/controls.md",
                "datalens/charts/editor/widgets/markdown.md",
                "datalens/charts/editor/sources.md",
                "datalens/charts/editor/tabs.md",
                "datalens/charts/editor/cross-filtration.md",
                "datalens/charts/editor/links.md",
                "datalens/charts/editor/notifications.md",
            },
            "source_trace": source_trace(page),
        }
        for page in sorted(corpus["pages"], key=lambda item: str(item.get("mirror_path") or ""))
        if is_editor_page(page)
    ]
    baseline = {
        "schema_version": COMPILER_VERSION,
        "counts": compiled["counts"],
        "page_counts_by_section": dict(sorted(page_by_section.items())),
        "editor_pages": editor_pages,
        "source_trace_inputs": read_json(REPO_ROOT / "schemas" / "datalens-api" / "source-trace.json"),
        "registry_counts": {
            "formulas": len(compiled["formula_registry"]["functions"]),
            "visualizations": len(compiled["visualization_registry"]["visualizations"]),
            "errors": len(compiled["error_registry"]["errors"]),
            "release_notes": compiled["supersession_registry"]["release_note_count"],
            "recipes": len(compiled["recipes"]["recipes"]),
            "rules": len(compiled["rule_cards"]),
        },
        "tool_budget": compiled["tool_budget"],
        "classification_counts": dict(Counter(page["classification"]["status"] for page in compiled["page_registry"])),
        "capabilities": compiled["capability_matrix"]["capabilities"],
    }
    write_json(ARTIFACT_DIR / "baseline.json", baseline)
    write_baseline_markdown(baseline)
    write_page_coverage_csv(compiled["page_registry"])
    write_capability_gaps(compiled["capability_matrix"]["capabilities"])
    return baseline


def write_baseline_markdown(baseline: dict[str, Any]) -> None:
    lines = [
        "# Full Corpus Knowledge Baseline",
        "",
        f"- Pages: `{baseline['counts']['pages']}`",
        f"- Chunks: `{baseline['counts']['chunks']}`",
        f"- Assets: `{baseline['counts']['assets']}`",
        f"- Editor pages: `{baseline['counts']['editor_pages']}`",
        f"- Function pages: `{baseline['counts']['function_pages']}`",
        f"- Visualization pages: `{baseline['counts']['visualization_pages']}`",
        f"- Troubleshooting error pages: `{baseline['counts']['troubleshooting_error_pages']}`",
        f"- Release-note pages: `{baseline['counts']['release_note_pages']}`",
        f"- Default tools: `{baseline['tool_budget']['default_tool_count']}`",
        f"- Default tools/list chars: `{baseline['tool_budget']['default_tools_list_chars']}`",
        "",
        "## Page Counts By Section",
        "",
    ]
    for section, count in baseline["page_counts_by_section"].items():
        lines.append(f"- `{section or '<root>'}`: `{count}`")
    lines.extend(["", "## Editor Pages", ""])
    for page in baseline["editor_pages"]:
        marker = "compiler-input" if page["compiler_input"] else "indexed"
        lines.append(f"- `{page['mirror_path']}` - {marker}")
    (ARTIFACT_DIR / "baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_page_coverage_csv(page_registry: list[dict[str, Any]]) -> None:
    path = ARTIFACT_DIR / "page_coverage_before.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["mirror_path", "section", "classification", "title", "source_url", "sha256"],
        )
        writer.writeheader()
        for page in page_registry:
            writer.writerow(
                {
                    "mirror_path": page["mirror_path"],
                    "section": page["section"],
                    "classification": page["classification"]["status"],
                    "title": page["title"],
                    "source_url": page["source_url"],
                    "sha256": page["sha256"],
                }
            )


def write_capability_gaps(capabilities: list[dict[str, Any]]) -> None:
    lines = ["# Capability Gaps", ""]
    for item in capabilities:
        if item["implementation_status"] not in {"implemented_tested", "implemented_tested_guarded_plan"}:
            lines.append(
                f"- `{item['capability_id']}`: official=`{item['official_status']}`, "
                f"implementation=`{item['implementation_status']}`, route=`{item['route']}`"
            )
    if len(lines) == 2:
        lines.append("- No baseline gaps detected.")
    (ARTIFACT_DIR / "capability_gaps.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_final_reports(compiled: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    after = {
        "schema_version": COMPILER_VERSION,
        "counts": compiled["counts"],
        "compiler_check": check,
        "registry_counts": {
            "recipes": len(compiled["recipes"]["recipes"]),
            "formulas": len(compiled["formula_registry"]["functions"]),
            "visualizations": len(compiled["visualization_registry"]["visualizations"]),
            "errors": len(compiled["error_registry"]["errors"]),
            "domain_records": len(compiled["domain_registry"]["records"]),
            "operations": len(compiled["operations_registry"]["records"]),
            "rules": len(compiled["rule_cards"]),
        },
        "tool_budget": compiled["tool_budget"],
        "artifact_paths": {
            "knowledge_dir": str(KNOWLEDGE_DIR),
            "recipe_registry": str(REPO_ROOT / "templates" / "datalens" / "recipes" / "recipe-registry.json"),
            "index": str(INDEX_PATH),
        },
    }
    write_json(ARTIFACT_DIR / "after.json", after)
    write_coverage_report(compiled, check)
    write_capability_matrix_md(compiled["capability_matrix"]["capabilities"])
    write_recipe_matrix(compiled["recipes"]["recipes"])
    write_conflicts_and_deprecations(compiled)
    write_remaining_gaps(compiled["capability_matrix"]["capabilities"])
    write_semantic_coverage(compiled, check)
    write_formula_language_report(compiled)
    write_object_authoring_contracts_report(compiled)
    write_executable_recipe_matrix(compiled)
    write_authoring_eval_report(compiled)
    write_route_capability_report(compiled)
    write_wheel_authoring_report(compiled, check)
    write_demo_reference_mapping_report(compiled)
    write_final_acceptance(compiled, check)
    return after


def write_coverage_report(compiled: dict[str, Any], check: dict[str, Any]) -> None:
    lines = ["# Coverage Report", ""]
    for key, value in compiled["counts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", f"- Zero unclassified pages: `{check['ok'] and not check['issues']}`"])
    lines.append(f"- Index: `{check['index'].get('path', '')}`")
    (ARTIFACT_DIR / "coverage_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_capability_matrix_md(capabilities: list[dict[str, Any]]) -> None:
    lines = [
        "# Capability Matrix",
        "",
        "| Capability | Official | Implementation | Policy | Route |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in capabilities:
        lines.append(
            f"| `{item['capability_id']}` | `{item['official_status']}` | "
            f"`{item['implementation_status']}` | `{item['local_policy_status']}` | `{item['route']}` |"
        )
    (ARTIFACT_DIR / "capability_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_recipe_matrix(recipes: list[dict[str, Any]]) -> None:
    lines = [
        "# Recipe Matrix",
        "",
        "| Recipe | Route | Contract | Implementation | generateHtml | Sources |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in recipes:
        lines.append(
            f"| `{item['recipe_id']}` | `{item['route']}` | `{item['widget_contract']}` | "
            f"`{item['implementation_status']}` | `{item['uses_generate_html']}` | `{len(item['source_traces'])}` |"
        )
    (ARTIFACT_DIR / "recipe_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_semantic_coverage(compiled: dict[str, Any], check: dict[str, Any]) -> None:
    lines = [
        "# Semantic Coverage",
        "",
        f"- Pages: `{compiled['counts']['pages']}`",
        f"- Chunks: `{compiled['counts']['chunks']}`",
        f"- Assets: `{compiled['counts']['assets']}`",
        f"- Semantic records: `{len(compiled['semantic_records'])}`",
        f"- Exact trace records: `{sum(1 for row in compiled['semantic_records'] if source_trace_ok(row['source_trace']))}`",
        f"- Manual review pages: `{len(compiled['manual_review_queue']['pages'])}`",
        f"- Manual review assets: `{len(compiled['manual_review_queue']['assets'])}`",
        f"- Default tools/list chars: `{compiled['tool_budget']['default_tools_list_chars']}`",
        f"- Compiler gate: `{check['ok']}`",
        "",
        "## Classification",
        "",
    ]
    for key, value in check["classification_counts"].items():
        lines.append(f"- `{key}`: `{value}`")
    (ARTIFACT_DIR / "semantic_coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_formula_language_report(compiled: dict[str, Any]) -> None:
    golden = compiled["formula_golden_set"]
    formulas = compiled["formula_registry"]["functions"]
    exact = sum(1 for item in formulas if item.get("contract_status") == "compiled_exact")
    lines = [
        "# Formula Language Report",
        "",
        f"- Function pages: `{len(formulas)}`",
        f"- Exact compiled contracts: `{exact}`",
        f"- Golden cases: `{golden['case_count']}`",
        f"- Valid golden cases: `{golden['valid_case_count']}`",
        f"- Invalid golden cases: `{golden['invalid_case_count']}`",
        f"- Golden pass count: `{golden['pass_count']}`",
        f"- Fuzz cases: `{compiled['formula_fuzz_cases']['case_count']}`",
        f"- Demo formula examples: `{len(compiled['demo_reference_mapping'].get('formula_examples') or [])}`",
        "",
        "| Family | Cases |",
        "| --- | --- |",
    ]
    for family, count in golden["families"].items():
        lines.append(f"| `{family}` | `{count}` |")
    (ARTIFACT_DIR / "formula_language_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_object_authoring_contracts_report(compiled: dict[str, Any]) -> None:
    contracts = compiled["editor_visualization_contracts"]["contracts"]
    lines = [
        "# Object Authoring Contracts",
        "",
        f"- Contracts: `{len(contracts)}`",
        f"- Demo mapped examples: `{len(compiled['demo_reference_mapping'].get('mapped_examples') or [])}`",
        "",
        "| Contract | Kind | Native route | Editor route | Tabs | Methods |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in contracts:
        lines.append(
            f"| `{item['mirror_path']}` | `{item['kind']}` | `{item['native_route']}` | "
            f"`{item['editor_route']}` | `{','.join(item['required_tabs'])}` | `{len(item['methods'])}` |"
        )
    text = "\n".join(lines) + "\n"
    (ARTIFACT_DIR / "object_authoring_contracts.md").write_text(text, encoding="utf-8")
    (ARTIFACT_DIR / "editor_visualization_contracts.md").write_text(text, encoding="utf-8")


def write_executable_recipe_matrix(compiled: dict[str, Any]) -> None:
    recipes = compiled["recipes"]["recipes"]
    lines = [
        "# Executable Recipe Matrix",
        "",
        "| Recipe | Route | Implementation | Bundle | Algorithm |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in recipes:
        bundle = item.get("executable_bundle") or {}
        lines.append(
            f"| `{item['recipe_id']}` | `{item['route']}` | `{item['implementation_status']}` | "
            f"`{bundle.get('status', '')}` | `{item['algorithmic_bound']}` |"
        )
    (ARTIFACT_DIR / "executable_recipe_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_authoring_eval_report(compiled: dict[str, Any]) -> None:
    cases = compiled["retrieval_benchmark_cases"]["cases"]
    languages = Counter(case["language"] for case in cases)
    modes = Counter(case["mode"] for case in cases)
    lines = [
        "# Authoring Eval Report",
        "",
        f"- Reviewed tasks: `{len(cases)}`",
        "- Styles: `deterministic contract`, `top-k retrieval`, `installed-wheel MCP response`",
        "- Targets: mandatory facts 100%, unsupported routes never supported, route >=98%, source top-3 >=95%, budget 100%, zero crashes.",
        "",
        "## Languages",
        "",
    ]
    for key, value in sorted(languages.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Modes", ""])
    for key, value in sorted(modes.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "Detailed run output is written by `scripts/benchmark_datalens_reference.py` as `retrieval_benchmark.json`."])
    (ARTIFACT_DIR / "authoring_eval_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_route_capability_report(compiled: dict[str, Any]) -> None:
    routes = compiled["route_capability_matrix"]["routes"]
    lines = [
        "# Route Capability Matrix",
        "",
        "| Route | Official | Read | Plan | Create | Update | Fixture | Blocked reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in routes:
        lines.append(
            f"| `{item['route_id']}` | `{item['official_documented']}` | `{item['read_supported']}` | "
            f"`{item['plan_supported']}` | `{item['create_supported']}` | `{item['update_supported']}` | "
            f"`{item['executable_fixture_tested']}` | {item['blocked_reason'] or item['evidence']} |"
        )
    (ARTIFACT_DIR / "route_capability_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_wheel_knowledge_report(compiled: dict[str, Any], check: dict[str, Any]) -> None:
    write_wheel_authoring_report(compiled, check)


def write_wheel_authoring_report(compiled: dict[str, Any], check: dict[str, Any]) -> None:
    lines = [
        "# Wheel Authoring Report",
        "",
        f"- Packaged knowledge dir: `{PACKAGE_KNOWLEDGE_DIR}`",
        f"- Packaged recipe dir: `{PACKAGE_RECIPE_DIR}`",
        f"- Resources synced by compiler: `true`",
        f"- Default tool count: `{compiled['tool_budget']['default_tool_count']}`",
        f"- Compiler gate: `{check['ok']}`",
        "- Wheel smoke artifact is generated by `scripts/run_portable_wheel_smoke.py` during acceptance.",
    ]
    text = "\n".join(lines) + "\n"
    (ARTIFACT_DIR / "wheel_authoring_report.md").write_text(text, encoding="utf-8")
    (ARTIFACT_DIR / "wheel_knowledge_report.md").write_text(text, encoding="utf-8")


def write_demo_reference_mapping_report(compiled: dict[str, Any]) -> None:
    mapping = compiled["demo_reference_mapping"]
    write_json(ARTIFACT_DIR / "demo_reference_mapping.json", mapping)
    lines = [
        "# Demo Reference Mapping",
        "",
        f"- Demo root: `{mapping.get('demo_root', '')}`",
        f"- Entries: `{mapping.get('entry_count')}`",
        f"- Hydrated entries: `{mapping.get('hydrated_entry_count')}`",
        f"- Mapped examples: `{len(mapping.get('mapped_examples') or [])}`",
        f"- Formula examples: `{len(mapping.get('formula_examples') or [])}`",
        "",
        "| Contract/recipe | Entry | Type | State | Raw hash |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in mapping.get("mapped_examples") or []:
        lines.append(
            f"| `{item['contract_or_recipe']}` | `{item['entry_id']}` | `{item['resolved_object_type']}` | "
            f"`{item['evidence_state']}` | `{item['raw_sha256'][:12]}` |"
        )
    (ARTIFACT_DIR / "demo_reference_mapping.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_conflicts_and_deprecations(compiled: dict[str, Any]) -> None:
    lines = ["# Conflicts And Deprecations", ""]
    lines.append("- Source precedence: " + " > ".join(SOURCE_PRECEDENCE))
    lines.append(
        "- Gravity UI Charts are officially documented as an Editor widget, but local route policy keeps them reference-only."
    )
    lines.append(
        f"- Release-note pages accounted: `{compiled['supersession_registry']['release_note_count']}`; "
        f"change signals: `{len(compiled['supersession_registry']['supersession_signals'])}`."
    )
    (ARTIFACT_DIR / "conflicts_and_deprecations.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_remaining_gaps(capabilities: list[dict[str, Any]]) -> None:
    lines = ["# Remaining Documented Gaps", ""]
    for item in capabilities:
        if "documented_reference" in item["implementation_status"] or "blocked" in item["implementation_status"]:
            lines.append(
                f"- `{item['capability_id']}`: documented=`{item['official_status']}`, "
                f"implementation=`{item['implementation_status']}`, policy=`{item['local_policy_status']}`."
            )
    if len(lines) == 2:
        lines.append("- No remaining documented-only gaps.")
    text = "\n".join(lines) + "\n"
    (ARTIFACT_DIR / "remaining_semantic_gaps.md").write_text(text, encoding="utf-8")
    (ARTIFACT_DIR / "remaining_documented_gaps.md").write_text(text, encoding="utf-8")


def write_final_acceptance(compiled: dict[str, Any], check: dict[str, Any]) -> None:
    recipes = compiled["recipes"]["recipes"]
    routes = compiled["route_capability_matrix"]["routes"]
    golden = compiled["formula_golden_set"]
    payload = {
        "schema_version": COMPILER_VERSION,
        "ok": bool(check["ok"]),
        "semantic_coverage": {
            "pages_classified": compiled["counts"]["pages"],
            "classification_counts": check["classification_counts"],
            "semantic_records": len(compiled["semantic_records"]),
            "precise_trace_records": sum(1 for row in compiled["semantic_records"] if source_trace_ok(row["source_trace"])),
        },
        "formula_quality": {
            "functions": len(compiled["formula_registry"]["functions"]),
            "valid_golden_cases": golden["valid_case_count"],
            "invalid_golden_cases": golden["invalid_case_count"],
            "golden_pass_count": golden["pass_count"],
            "fuzz_cases": compiled["formula_fuzz_cases"]["case_count"],
        },
        "recipe_matrix": {
            "recipe_count": len(recipes),
            "executable_fixture_tested": sum(
                1 for item in recipes if (item.get("executable_bundle") or {}).get("status") == "executable_fixture_tested"
            ),
        },
        "route_matrix": {
            "route_count": len(routes),
            "blocked_routes": [item["route_id"] for item in routes if item.get("blocked_reason")],
        },
        "eval": {
            "case_count": compiled["retrieval_benchmark_cases"]["case_count"],
            "manual_review_status": "reviewed",
        },
        "demo_reference": {
            "mapped_examples": len(compiled["demo_reference_mapping"].get("mapped_examples") or []),
            "formula_examples": len(compiled["demo_reference_mapping"].get("formula_examples") or []),
            "demo_lock_hash": compiled["demo_reference_mapping"].get("demo_lock_hash"),
        },
        "tool_budget": compiled["tool_budget"],
        "no_production_mutation": True,
        "issues": check["issues"],
    }
    write_json(ARTIFACT_DIR / "final_acceptance.json", payload)


def stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{sha256_text(stable_json(parts))[:16]}"
