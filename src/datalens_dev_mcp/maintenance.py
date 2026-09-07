from __future__ import annotations

from typing import Any

HTML_MAX_BYTES = 5 * 1024 * 1024


def validate_html_content(content: Any) -> dict[str, Any]:
    if not isinstance(content, str):
        return {
            "ok": False,
            "issues": [{"code": "html_must_be_string", "message": "HTML Page content must be one string"}],
        }
    size = len(content.encode("utf-8"))
    if size > HTML_MAX_BYTES:
        return {
            "ok": False,
            "issues": [{"code": "html_too_large", "message": f"HTML content exceeds {HTML_MAX_BYTES} bytes"}],
            "bytes": size,
        }
    return {"ok": True, "issues": [], "bytes": size, "content_contract": "single_html_string"}


def admin_capabilities() -> dict[str, Any]:
    return {
        "ok": True,
        "license_inventory": True,
        "license_assignment": True,
        "license_revoke": False,
        "workbook_lifecycle": "official_sdk",
        "html_page": {"backend": "public_api_adapter", "content": "single_string", "browser_fallback": False},
    }
