from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from typing import Any

import httpx

from datalens_dev_mcp.api.budget import check_dispatch, current_budget
from datalens_dev_mcp.api.errors import DataLensApiError

HTML_MAX_BYTES = 5 * 1024 * 1024


def read_html_preview(url: str) -> str:
    """Consume only a just-issued SDK URL; use a separate credential-free client."""
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise DataLensApiError("HTML preview returned an unsupported storage URL", stage="html_content_read")
    remaining = check_dispatch(readonly=True)
    try:
        with (
            httpx.Client(trust_env=False, follow_redirects=False, timeout=min(remaining or 30, 30)) as client,
            client.stream("GET", url, headers={"Accept": "text/html"}) as response,
        ):
            if response.status_code != 200:
                raise DataLensApiError("HTML preview storage is unavailable; request a fresh preview URL",
                                       http_status=response.status_code, stage="html_content_read")
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("text/html"):
                raise DataLensApiError("HTML preview storage returned a non-HTML content type", stage="html_content_read")
            if "charset=" in content_type and content_type.split("charset=", 1)[1].strip(' \";') not in {"utf-8", "utf8"}:
                raise DataLensApiError("HTML preview storage charset is not UTF-8", stage="html_content_read")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                if current_budget.get() is not None:
                    current_budget.get().check()
                size += len(chunk)
                if size > HTML_MAX_BYTES:
                    raise DataLensApiError("HTML preview exceeds the content byte limit", stage="html_content_read")
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8-sig")
    except (httpx.HTTPError, UnicodeError, ValueError) as exc:
        # HTTP exceptions include signed URLs; never persist or return their text.
        raise DataLensApiError("HTML preview could not be read as bounded UTF-8 content", stage="html_content_read") from exc


def html_semantic_content(content: str, *, ignore_injected_csp: bool = False,
                          ignore_provider_policy: bool = False) -> list[Any]:
    # Exact provider policy v3 observed in a controlled preview. Markers alone
    # cannot authorize ignoring arbitrary CSS/JavaScript or authored content.
    if ignore_provider_policy and content.startswith("<!DOCTYPE html>\n<!--datalens-html-policy:start-->\n"):
        marker = "<!--datalens-html-policy:end-->\n"
        end = content.find(marker)
        if end != -1:
            end += len(marker)
            digest = hashlib.sha256(content[:end].encode("utf-8")).hexdigest()
            if digest == "1b3f0c8274747fbc373da514130f4dc700f6bda7ff7e0e0e8da09536ab09a664":
                content = content[end:]

    class Document(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_starttag(self, tag, attrs):
            if (ignore_injected_csp and tag == "meta"
                    and dict(attrs).get("http-equiv", "").lower() == "content-security-policy"):
                return
            self.parts.append(["start", tag, sorted(attrs)])

        def handle_endtag(self, tag):
            self.parts.append(["end", tag])

        def handle_data(self, data):
            self.parts.append(["text", data])

        def handle_decl(self, decl):
            self.parts.append(["decl", decl.lower()])

        def handle_comment(self, data):
            self.parts.append(["comment", data])

    parser = Document()
    parser.feed(content)
    parser.close()
    return parser.parts


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
        "html_page": {"backend": "official_sdk_and_public_api", "content": "exact_revision_preview", "content_authoring": "save_with_content_readback",
                      "publish": "existing_saved_revision_only", "browser_fallback": False},
    }
