from __future__ import annotations

import hashlib
import html
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit


HTML_PAGE_CONTRACT_VERSION = "2026-07-23.standalone_html_page.v1"
HTML_PAGE_SOFT_MAX_BYTES = 5 * 1024 * 1024
HTML_PAGE_HARD_MAX_BYTES = 10 * 1024 * 1024
HTML_SKILL_COMMIT = "8fbb3aabac6b09d4c44f053fa63affea1dc386f7"
HTML_SKILL_SHA256 = "5a6585649bdc052fe1db5acc9704a5737ec2de99916034d16bd6f210da787c3f"
HTML_SKILL_URL = (
    "https://github.com/datalens-tech/datalens-skills/blob/"
    f"{HTML_SKILL_COMMIT}/skills/datalens-html-pages/SKILL.md"
)
EDITOR_HTML_IMPLEMENTATION_COMMIT = "f581b7c31d6e9189ebeb1e1632b5fe7570534fb8"
EDITOR_HTML_IMPLEMENTATION_SHA256 = "31522ca9c9f732befddcbe708da232c8beb6aa46e0f611021e209a08c9caf85c"
EDITOR_HTML_IMPLEMENTATION_URL = (
    "https://github.com/datalens-tech/datalens-ui/blob/"
    f"{EDITOR_HTML_IMPLEMENTATION_COMMIT}/src/ui/libs/DatalensChartkit/modules/html-generator/index.ts"
)

_SPEC_KEYS = {"body_html", "data", "lang", "script_js", "style_css", "summary", "title"}
_BLOCKED_TAGS = {"base", "embed", "form", "iframe", "object"}
_SCRIPT_HOSTS = {
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "cdn.tailwindcss.com",
    "yastatic.net",
}
_STYLE_HOSTS = _SCRIPT_HOSTS | {"fonts.googleapis.com"}
_FONT_HOSTS = {
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "fonts.gstatic.com",
}
_IMAGE_HOSTS = {"yastatic.net"}
_LINK_HOSTS = _STYLE_HOSTS | _FONT_HOSTS
_CSS_RESOURCE_HOSTS = _LINK_HOSTS | _IMAGE_HOSTS
_CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)
_CSS_IMPORT = re.compile(r"@import\s+(?:url\(\s*)?['\"]?([^'\"\)\s;]+)", re.I)
_BLOCKED_SCRIPT_APIS = {
    "browser_dialog": re.compile(r"\b(?:alert|confirm|prompt)\s*\("),
    "cache_api": re.compile(r"\bcaches\s*\."),
    "camera": re.compile(r"\bgetUserMedia\b"),
    "cookie": re.compile(r"\bdocument\s*\.\s*cookie\b"),
    "event_stream": re.compile(r"\bEventSource\s*\("),
    "fullscreen": re.compile(r"\brequestFullscreen\b"),
    "geolocation": re.compile(r"\bnavigator\s*\.\s*geolocation\b"),
    "indexed_db": re.compile(r"\bindexedDB\b"),
    "network_fetch": re.compile(r"\bfetch\s*\("),
    "network_xhr": re.compile(r"\bXMLHttpRequest\b"),
    "parent_navigation": re.compile(r"\b(?:parent|top)\s*\.\s*location\b"),
    "persistent_storage": re.compile(r"\b(?:localStorage|sessionStorage)\b"),
    "popup": re.compile(r"\bwindow\s*\.\s*open\s*\("),
    "send_beacon": re.compile(r"\bsendBeacon\s*\("),
    "service_worker": re.compile(r"\bserviceWorker\b"),
    "websocket": re.compile(r"\bWebSocket\s*\("),
    "worker": re.compile(r"\b(?:SharedWorker|Worker)\s*\("),
}


def html_page_source_contract() -> dict[str, Any]:
    return {
        "contract_version": HTML_PAGE_CONTRACT_VERSION,
        "standalone_html": {
            "source_url": HTML_SKILL_URL,
            "source_commit": HTML_SKILL_COMMIT,
            "source_sha256": HTML_SKILL_SHA256,
            "scope": "sandboxed standalone HTML document",
        },
        "editor_generate_html": {
            "source_url": EDITOR_HTML_IMPLEMENTATION_URL,
            "source_commit": EDITOR_HTML_IMPLEMENTATION_COMMIT,
            "source_sha256": EDITOR_HTML_IMPLEMENTATION_SHA256,
            "scope": "allowlisted markup inside an Editor chart",
        },
        "publication": {
            "status": "local_artifact_only",
            "public_create_or_upload_method": None,
            "reason": "No standalone HTML create/upload RPC is documented in the current Public API.",
        },
    }


def render_standalone_html_page(spec: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_spec(spec)
    title = html.escape(normalized["title"], quote=True)
    lang = html.escape(normalized["lang"], quote=True)
    body = normalized["body_html"] or (
        f"<main class=\"dl-page\"><h1>{title}</h1>"
        f"<p>{html.escape(normalized['summary'], quote=True)}</p></main>"
    )
    data_json = _json_for_script(normalized["data"])
    document = (
        "<!doctype html>\n"
        f"<html lang=\"{lang}\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{title}</title><style>{_base_css()}{normalized['style_css']}</style></head>"
        f"<body>{body}<script id=\"dl-page-data\" type=\"application/json\">{data_json}</script>"
        f"<script>{_bridge_script()}{normalized['script_js']}</script></body></html>\n"
    )
    validation = validate_standalone_html_page(document, strict=True)
    encoded = document.encode("utf-8")
    return {
        "ok": validation["ok"],
        "schema_version": HTML_PAGE_CONTRACT_VERSION,
        "html": document,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "validation": validation,
        "source_contract": html_page_source_contract(),
    }


def validate_standalone_html_page(
    value: str | bytes,
    *,
    source: str = "<memory>",
    strict: bool = True,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if isinstance(value, bytes):
        encoded = value
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            text = value.decode("utf-8", errors="replace")
            _finding(findings, "utf8", "error", "HTML document must be valid UTF-8.", source)
        byte_count = len(value)
    else:
        text = str(value)
        encoded = text.encode("utf-8")
        byte_count = len(encoded)

    if byte_count > HTML_PAGE_HARD_MAX_BYTES:
        _finding(
            findings,
            "hard_size_limit",
            "error",
            f"HTML document exceeds {HTML_PAGE_HARD_MAX_BYTES} bytes.",
            source,
        )
    elif byte_count > HTML_PAGE_SOFT_MAX_BYTES:
        _finding(
            findings,
            "soft_size_limit",
            "warning",
            f"HTML document exceeds the {HTML_PAGE_SOFT_MAX_BYTES}-byte authoring target.",
            source,
        )
    if re.search(r"```(?:html)?", text, flags=re.I):
        _finding(findings, "markdown_fence", "error", "Return a raw HTML document without Markdown fences.", source)
    if not re.match(r"\s*<!doctype\s+html\b", text, flags=re.I):
        _finding(findings, "doctype", "error", "A complete document must start with <!doctype html>.", source)
    if not re.search(r"<meta\s+[^>]*charset\s*=\s*['\"]?utf-8\b", text[:1024], flags=re.I):
        _finding(findings, "charset", "error", "UTF-8 charset must appear in the first 1024 bytes.", source)
    replacement_count = text.count("\ufffd")
    if replacement_count and replacement_count / max(len(text), 1) > 0.0005:
        _finding(
            findings,
            "mojibake",
            "warning",
            "High U+FFFD density suggests an encoding mismatch.",
            source,
        )

    parser = _PageParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # HTMLParser is permissive; fail closed on parser faults.
        _finding(findings, "parse", "error", f"HTML parsing failed: {exc.__class__.__name__}.", source)
    for required_tag in ("html", "head", "body"):
        count = parser.tag_counts.get(required_tag, 0)
        if count != 1:
            _finding(
                findings,
                "document_shape",
                "error",
                f"A complete document must contain exactly one <{required_tag}> element.",
                source,
            )
    for tag in sorted(parser.tags & _BLOCKED_TAGS):
        _finding(findings, "sandbox_tag", "error", f"<{tag}> is unavailable in the standalone sandbox.", source)
    if parser.has_csp_meta:
        _finding(findings, "platform_csp", "error", "Do not inject CSP; DataLens supplies it.", source)
    if parser.has_meta_refresh:
        _finding(findings, "meta_refresh", "error", "Meta refresh navigation is unavailable.", source)
    if parser.has_srcdoc:
        _finding(findings, "nested_document", "error", "srcdoc is unavailable in the standalone sandbox.", source)
    if parser.has_download:
        _finding(
            findings,
            "blocked_download",
            "error",
            "Browser downloads are unavailable; use the EXPORT parent protocol.",
            source,
        )
    if parser.has_javascript_uri:
        _finding(findings, "javascript_uri", "error", "javascript: resource URLs are unavailable.", source)

    for tag, attribute, uri in parser.resource_uris:
        if not _resource_uri_allowed(tag, attribute, uri):
            _finding(
                findings,
                "resource_origin",
                "error",
                f"{tag}[{attribute}] uses an origin unavailable under the DataLens CSP.",
                source,
            )
    for uri in parser.css_resource_uris:
        if not _css_resource_uri_allowed(uri):
            _finding(
                findings,
                "css_resource_origin",
                "error",
                "CSS references a resource unavailable under the DataLens CSP.",
                source,
            )
    scripts = "\n".join([*parser.script_text, *parser.executable_attribute_text])
    for rule, pattern in _BLOCKED_SCRIPT_APIS.items():
        if pattern.search(scripts):
            _finding(findings, rule, "error", f"Blocked sandbox API detected: {rule}.", source)
    if "URLSearchParams" not in scripts or ".get('theme')" not in scripts or ".get('lang')" not in scripts:
        _finding(
            findings,
            "theme_language",
            "warning",
            "Read theme and lang from location.search for platform integration.",
            source,
        )
    if re.search(r"<a\b[^>]*\bhref\s*=", text, flags=re.I) and "'OPEN_URL'" not in scripts:
        _finding(
            findings,
            "external_link_protocol",
            "warning",
            "External links should use the OPEN_URL parent postMessage protocol.",
            source,
        )
    if "'EXPORT'" not in scripts:
        _finding(
            findings,
            "export_protocol",
            "note",
            "Use the EXPORT parent postMessage protocol when the page exposes downloads.",
            source,
        )

    errors = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    return {
        "ok": errors == 0 and (not strict or warnings == 0),
        "schema_version": HTML_PAGE_CONTRACT_VERSION,
        "kind": "standalone_html_page",
        "source": source,
        "strict": strict,
        "bytes": byte_count,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "summary": {
            "findings": len(findings),
            "errors": errors,
            "warnings": warnings,
            "notes": sum(item["severity"] == "note" for item in findings),
            "blocking_findings": errors + (warnings if strict else 0),
        },
        "findings": findings,
        "source_contract": html_page_source_contract(),
    }


def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("html_page must be an object")
    unknown = sorted(set(spec) - _SPEC_KEYS)
    if unknown:
        raise ValueError(f"html_page contains unsupported fields: {', '.join(unknown)}")
    title = str(spec.get("title") or "DataLens HTML page").strip()
    lang = str(spec.get("lang") or "ru").strip().lower()
    if not title or len(title) > 200:
        raise ValueError("html_page.title must contain 1..200 characters")
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", lang):
        raise ValueError("html_page.lang must be a short BCP 47 language tag")
    body = str(spec.get("body_html") or "")
    style = str(spec.get("style_css") or "")
    script = str(spec.get("script_js") or "")
    if re.search(r"<\s*/?\s*(?:base|body|head|html|meta|script|style)\b", body, flags=re.I):
        raise ValueError("html_page.body_html must contain body markup only")
    if "</style" in style.lower() or "</script" in script.lower():
        raise ValueError("html_page style/script must not close its container element")
    try:
        json.dumps(spec.get("data"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("html_page.data must be JSON serializable") from exc
    return {
        "title": title,
        "lang": lang,
        "summary": str(spec.get("summary") or ""),
        "body_html": body,
        "style_css": style,
        "script_js": script,
        "data": spec.get("data"),
    }


def _json_for_script(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _base_css() -> str:
    return (
        ":root{color-scheme:light dark;--bg:#fff;--fg:#1f2430;--muted:#626b7a;}"
        "html[data-theme^=dark]{--bg:#15171c;--fg:#f2f3f5;--muted:#a7adb8;}"
        "*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--fg);}"
        "body{font:14px/1.45 Arial,sans-serif}.dl-page{width:min(100%,1200px);margin:auto;padding:24px;}"
        ".dl-page h1{font-size:clamp(22px,4vw,36px);margin:0 0 12px}.dl-page p{color:var(--muted);}"
        "@media(max-width:640px){.dl-page{padding:16px}}"
    )


def _bridge_script() -> str:
    return (
        "(()=>{const q=new URLSearchParams(location.search),"
        "theme=q.get('theme')||'light',lang=q.get('lang')||document.documentElement.lang||'ru';"
        "document.documentElement.dataset.theme=theme;document.documentElement.lang=lang;"
        "const post=(code,data)=>parent.postMessage({code,data},'*');"
        "const node=document.getElementById('dl-page-data');"
        "window.datalensPage={data:JSON.parse(node.textContent||'null'),theme,lang,"
        "exportFile:(name,mime,data)=>post('EXPORT',{name,mime,data}),"
        "openUrl:(url)=>post('OPEN_URL',{url})};"
        "document.addEventListener('click',event=>{const link=event.target.closest&&event.target.closest('a[href]');"
        "if(!link)return;const url=link.getAttribute('href')||'';"
        "if(/^https?:\\/\\//i.test(url)){event.preventDefault();window.datalensPage.openUrl(url);}});})();"
    )


def _finding(findings: list[dict[str, Any]], rule: str, severity: str, message: str, source: str) -> None:
    findings.append({"rule": rule, "severity": severity, "message": message, "source": source})


def _resource_uri_allowed(tag: str, attribute: str, value: str) -> bool:
    del attribute
    uri = value.strip()
    if not uri:
        return False
    lowered = uri.lower()
    if lowered.startswith("data:"):
        return tag in {"img", "media"}
    if lowered.startswith("blob:"):
        return tag in {"img", "media"}
    if uri.startswith("//"):
        parsed = urlsplit(f"https:{uri}")
    else:
        parsed = urlsplit(uri)
    if not parsed.scheme and not parsed.netloc:
        return False
    if parsed.scheme.lower() != "https":
        return False
    host = (parsed.hostname or "").lower()
    if tag == "script":
        return host in _SCRIPT_HOSTS
    if tag == "link":
        return host in _LINK_HOSTS
    if tag == "img":
        return host in _IMAGE_HOSTS
    if tag == "media":
        return False
    return False


def _css_resource_uri_allowed(value: str) -> bool:
    uri = value.strip()
    if not uri or uri.startswith("#") or uri.lower().startswith(("data:", "blob:")):
        return True
    if uri.startswith("//"):
        parsed = urlsplit(f"https:{uri}")
    else:
        parsed = urlsplit(uri)
    if not parsed.scheme and not parsed.netloc:
        return False
    return parsed.scheme.lower() == "https" and (parsed.hostname or "").lower() in _CSS_RESOURCE_HOSTS


def _css_resource_uris(css: str) -> list[str]:
    values = [
        *[match.group(1) for match in _CSS_URL.finditer(css)],
        *[match.group(1) for match in _CSS_IMPORT.finditer(css)],
    ]
    return list(dict.fromkeys(values))


def _srcset_uris(value: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(r"(data:[^\s]+|[^,\s]+)(?:\s+[^,]+)?(?:,|$)", value, flags=re.I)
    ]


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: set[str] = set()
        self.tag_counts: dict[str, int] = {}
        self.resource_uris: list[tuple[str, str, str]] = []
        self.css_resource_uris: list[str] = []
        self.script_text: list[str] = []
        self.executable_attribute_text: list[str] = []
        self._script_types: list[str] = []
        self._in_style = 0
        self.has_csp_meta = False
        self.has_meta_refresh = False
        self.has_srcdoc = False
        self.has_download = False
        self.has_javascript_uri = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        normalized_attrs = {str(key).lower(): str(value or "") for key, value in attrs}
        self.tags.add(normalized_tag)
        self.tag_counts[normalized_tag] = self.tag_counts.get(normalized_tag, 0) + 1
        if normalized_tag == "script":
            self._script_types.append(normalized_attrs.get("type", "").lower())
        if normalized_tag == "style":
            self._in_style += 1
        if normalized_tag == "meta" and normalized_attrs.get("http-equiv", "").lower() == "content-security-policy":
            self.has_csp_meta = True
        if normalized_tag == "meta" and normalized_attrs.get("http-equiv", "").lower() == "refresh":
            self.has_meta_refresh = True
        if "srcdoc" in normalized_attrs:
            self.has_srcdoc = True
        if normalized_tag == "a" and "download" in normalized_attrs:
            self.has_download = True
        for attribute, value in normalized_attrs.items():
            if attribute.startswith("on") and value:
                self.executable_attribute_text.append(value)
            if attribute in {"href", "src", "xlink:href"} and value.strip().lower().startswith("javascript:"):
                self.has_javascript_uri = True
                self.executable_attribute_text.append(value.partition(":")[2])
        resource_attributes = {
            "script": (("src", "script"),),
            "link": (("href", "link"),),
            "img": (("src", "img"),),
            "image": (("href", "img"), ("xlink:href", "img")),
            "audio": (("src", "media"),),
            "video": (("src", "media"), ("poster", "img")),
            "source": (("src", "media"),),
        }
        for attribute, resource_kind in resource_attributes.get(normalized_tag, ()):
            if normalized_attrs.get(attribute):
                self.resource_uris.append((resource_kind, attribute, normalized_attrs[attribute]))
        if normalized_tag in {"img", "source"} and normalized_attrs.get("srcset"):
            self.resource_uris.extend(
                ("img", "srcset", uri)
                for uri in _srcset_uris(normalized_attrs["srcset"])
            )
        if normalized_attrs.get("style"):
            self.css_resource_uris.extend(_css_resource_uris(normalized_attrs["style"]))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "script" and self._script_types:
            self._script_types.pop()
        if normalized_tag == "style" and self._in_style:
            self._in_style -= 1

    def handle_data(self, data: str) -> None:
        if self._script_types and self._script_types[-1] not in {"application/json", "application/ld+json"}:
            self.script_text.append(data)
        if self._in_style:
            self.css_resource_uris.extend(_css_resource_uris(data))
