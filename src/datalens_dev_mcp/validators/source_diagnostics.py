from __future__ import annotations

from typing import Any

from datalens_dev_mcp.knowledge.reference import lookup_error_reference


def classify_datalens_source_error(error_payload: dict[str, Any]) -> dict[str, Any]:
    stage = str(error_payload.get("stage") or "").strip().lower()
    query = error_payload.get("query")
    text = " ".join(str(error_payload.get(key) or "") for key in ("message", "error", "description", "detail")).lower()
    query_text = str(query or "").lower()
    unsupported_tables = [str(item).lower() for item in error_payload.get("statically_unsupported_tables") or []]
    if _is_preview_source_modification_not_allowed(text):
        category = "dataset_preview_source_access"
    elif "auth" in text or "401" in text or "permission" in text:
        category = "authentication"
    elif stage == "request" and query is None:
        category = "connection_request_refusal"
    elif "502" in text or "504" in text or "bad gateway" in text or "timeout" in text:
        category = "source_timeout_or_high_fanout_candidate"
    elif unsupported_tables and any(table and table in query_text for table in unsupported_tables):
        category = "stale_availability_param"
    elif "code: 60" in text or "unknown_table" in text or "unknown table" in text:
        category = "missing_table_or_bad_availability_guard"
    elif "unknown_identifier" in text or "unknown identifier" in text or "column does not exist" in text:
        category = "schema_mismatch"
    elif "renderer" in text or "render" in text:
        category = "runtime_renderer"
    elif "sanitizer" in text or "sanitize" in text or "unsupported tag" in text:
        category = "sanitizer"
    elif any(
        token in text
        for token in (
            "sql",
            "syntax",
            "compilation",
            "execute",
            "execution",
            "code 47",
            "unknown identifier",
            "unknown_identifier",
            "code 60",
            "unknown table",
            "unknown_table",
            "column does not exist",
            "column_do_es_not_exist",
            "column_does_not_exist",
        )
    ):
        category = "sql_compilation_execution"
    else:
        category = "unknown_source_error"
    preview_source_access = category == "dataset_preview_source_access"
    return {
        "ok": True,
        "schema_version": "2026-06-23.datalens_source_diagnostic.v1",
        "category": category,
        "stage": stage or "unknown",
        "query_available": query not in (None, ""),
        "is_sql_error": category
        in {
            "sql_compilation_execution",
            "missing_table_or_bad_availability_guard",
            "schema_mismatch",
            "stale_availability_param",
        },
        "safe_summary": _safe_summary(category),
        "cause_code": "preview_source_modification_not_allowed" if preview_source_access else "",
        "safe_diagnostic_probes": (
            [
                "dl_get_dataset_schema",
                "dl_read_object(connection)",
                "verify_saved_dataset_connection_reference",
                "verify_connection_view_permission",
            ]
            if preview_source_access
            else []
        ),
        "remediation": (
            "Use the connection already saved in the dataset preview request, or obtain View permission on the "
            "replacement connection before changing source parameters."
            if preview_source_access
            else ""
        ),
        "corpus_references": lookup_error_reference(text or category, limit=3),
    }


def _safe_summary(category: str) -> str:
    return {
        "connection_request_refusal": "Request-stage refusal before query text was available.",
        "authentication": "Authentication or permission failure.",
        "dataset_preview_source_access": (
            "Dataset preview attempted to change a source without View access; use the saved connection or obtain "
            "View permission on the replacement connection."
        ),
        "sql_compilation_execution": "SQL compilation or execution failure.",
        "missing_table_or_bad_availability_guard": "Physical table is missing or an unavailable branch was emitted.",
        "schema_mismatch": "Query references a missing identifier or changed schema.",
        "stale_availability_param": "Runtime availability state attempted to query a statically unsupported source.",
        "source_timeout_or_high_fanout_candidate": "Source timeout/gateway failure; collect bounded fanout evidence.",
        "runtime_renderer": "Runtime renderer failure.",
        "sanitizer": "Renderer sanitizer failure.",
    }.get(category, "Source failure category is unknown.")


def _is_preview_source_modification_not_allowed(text: str) -> bool:
    compact = text.replace(".", "").replace("_", "").replace("-", "")
    return "previewsourcemodificationnotallowed" in compact
