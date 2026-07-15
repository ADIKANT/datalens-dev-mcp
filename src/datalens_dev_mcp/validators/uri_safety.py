from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit


CONTROL_CHARACTER_RE = re.compile(r"[\x00-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"\s")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class UriSafetyDecision:
    allowed: bool
    normalized: str
    reason: str
    render_as: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_uri(
    value: Any,
    *,
    allow_http: bool = False,
    allow_relative: bool = True,
) -> UriSafetyDecision:
    """Classify an untrusted URI for generated DataLens links.

    HTTPS and ordinary relative references are allowed by default. HTTP needs an
    explicit policy opt-in. Unsafe or malformed values use the plain-text
    fallback contract instead of being emitted as clickable links.
    """

    raw = "" if value is None else str(value)
    normalized = html.unescape(raw).strip()
    if not normalized:
        return _plain_text("empty_uri")
    if CONTROL_CHARACTER_RE.search(normalized):
        return _plain_text("control_character")
    if "\\" in normalized:
        return _plain_text("backslash_not_allowed")
    if normalized.startswith("//"):
        return _plain_text("scheme_relative_uri_not_allowed")
    if "://" in normalized and not SCHEME_RE.match(normalized):
        return _plain_text("malformed_scheme_like_uri")

    if WHITESPACE_RE.search(normalized):
        return _plain_text("whitespace_not_allowed")
    try:
        parsed = urlsplit(normalized)
        # Accessing hostname/port performs extra validation that urlsplit alone
        # defers (for example unmatched IPv6 brackets and out-of-range ports).
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return _plain_text("malformed_uri")
    scheme = parsed.scheme.lower()
    if scheme == "https":
        if not parsed.netloc or not hostname:
            return _plain_text("https_host_required")
        if parsed.username is not None or parsed.password is not None:
            return _plain_text("userinfo_not_allowed")
        return UriSafetyDecision(True, normalized, "https_allowed", "link")
    if scheme == "http":
        if not parsed.netloc or not hostname:
            return _plain_text("http_host_required")
        if parsed.username is not None or parsed.password is not None:
            return _plain_text("userinfo_not_allowed")
        if not allow_http:
            return _plain_text("http_requires_explicit_opt_in")
        return UriSafetyDecision(True, normalized, "http_explicitly_allowed", "link")
    if scheme or SCHEME_RE.match(normalized):
        return _plain_text(f"scheme_not_allowed:{scheme or 'unknown'}")
    if not allow_relative:
        return _plain_text("relative_uri_not_allowed")
    return UriSafetyDecision(True, normalized, "relative_uri_allowed", "link")


def sanitize_uri(
    value: Any,
    *,
    allow_http: bool = False,
    allow_relative: bool = True,
) -> str:
    decision = assess_uri(value, allow_http=allow_http, allow_relative=allow_relative)
    return decision.normalized if decision.allowed else ""


def link_or_plain_text(
    label: Any,
    uri: Any,
    *,
    allow_http: bool = False,
    allow_relative: bool = True,
) -> dict[str, Any]:
    decision = assess_uri(uri, allow_http=allow_http, allow_relative=allow_relative)
    return {
        "text": "" if label is None else str(label),
        "href": decision.normalized if decision.allowed else "",
        "render_as": decision.render_as,
        "reason": decision.reason,
    }


def _plain_text(reason: str) -> UriSafetyDecision:
    return UriSafetyDecision(False, "", reason, "plain_text")
