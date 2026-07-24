from __future__ import annotations

import hashlib
import json
import os
import re
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
from threading import RLock
from typing import Any

from datalens_dev_mcp.api.scheduler import record_cache_hit
from datalens_dev_mcp.runtime_resources import (
    RESOURCE_OVERRIDE_ENV,
    RuntimeResourceError,
    resource_json,
    resource_text,
)
from datalens_dev_mcp.validators.route_validator import ValidationResult
from datalens_dev_mcp.validators.uri_safety import assess_uri


ALLOWED_EDITOR_METHODS = {
    "generateHtml",
    "getActionParams",
    "getCurrentPage",
    "getId",
    "getLang",
    "getLoadedData",
    "getParam",
    "getParams",
    "getSortParams",
    "getWidgetConfig",
    "resolveInterval",
    "resolveOperation",
    "resolveRelative",
    "setChartsInsights",
    "setRawData",
    "updateActionParams",
    "updateParams",
    "wrapFn",
}

METHOD_RE = re.compile(r"\bEditor\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
RUNTIME_METHOD_RE = re.compile(r"\b(Editor|ChartEditor)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
D3_ATTR_RE = re.compile(r"\.attr\s*\(\s*([\"'])(?P<name>[^\"']+)\1", re.S)
# Real opening tags do not contain whitespace between ``<`` and the tag name.
# Allowing it made ordinary JavaScript comparisons such as ``index < value``
# look like one enormous unsupported HTML tag until a later ``>`` operator.
HTML_TAG_RE = re.compile(r"<(?P<tag>[A-Za-z][A-Za-z0-9:-]*)\b(?P<attrs>[^<>]*)>", re.S)
HTML_ATTR_RE = re.compile(r"(?P<name>[A-Za-z_:][A-Za-z0-9_:.-]*)\s*=", re.S)
HTML_URI_ATTR_RE = re.compile(
    r"(?P<name>href|src|xlink:href)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.I | re.S,
)
D3_URI_ATTR_RE = re.compile(
    r"\.attr\s*\(\s*(['\"])(?P<name>href|src|xlink:href)\1\s*,\s*(['\"])(?P<value>.*?)\3\s*\)",
    re.I | re.S,
)
D3_DYNAMIC_URI_ATTR_RE = re.compile(
    r"\.attr\s*\(\s*(['\"])(?P<name>href|src|xlink:href)\1\s*,\s*(?P<value>[^\n;]+?)\s*\)",
    re.I,
)
DYNAMIC_INTERPOLATION_RE = re.compile(r"\$\{(?P<expression>[^{}]+)\}")
URI_SANITIZER_NAMES = {"safeUri", "safeUrl", "safeHref", "sanitizeUri"}
URI_ESCAPE_WRAPPER_NAMES = {"esc", "escapeHtml"}
RENDER_WRAP_RE = re.compile(r"render\s*:\s*Editor\.wrapFn\s*\(\s*\{", re.S)
CONTRACT_RESOURCE = "validators/editor_runtime_contract.json"
ALLOWLIST_RESOURCE = "schemas/datalens-api/editor-runtime-allowlist.json"
EDITOR_VALIDATION_CACHE_VERSION = "2026-07-23.editor_validation_cache.v2"
EDITOR_VALIDATION_CACHE_MAX_ENTRIES = 128
_EDITOR_VALIDATION_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_EDITOR_VALIDATION_CACHE_LOCK = RLock()


def validate_advanced_editor_js(text: str, *, source: str = "<memory>") -> ValidationResult:
    issues: list[str] = []
    for match in METHOD_RE.finditer(text):
        method = match.group(1)
        if method not in ALLOWED_EDITOR_METHODS:
            issues.append(f"{source}: unavailable Editor method {method}")

    has_render_export = "render" in text and "module.exports" in text
    if has_render_export and not RENDER_WRAP_RE.search(text):
        issues.append(f"{source}: render must be exported as Editor.wrapFn({{args, fn}})")

    if re.search(r"render\s*:\s*Editor\.generateHtml|const\s+render\s*=\s*Editor\.generateHtml", text):
        issues.append(f"{source}: render must not be Editor.generateHtml directly")

    if "Editor.wrapFn(" in text and "Editor.wrapFn({" not in text:
        issues.append(f"{source}: use object-form Editor.wrapFn({{args, fn}})")

    if RENDER_WRAP_RE.search(text):
        if not re.search(r"args\s*:", text):
            issues.append(f"{source}: wrapped render must declare args")
        if not re.search(r"fn\s*:\s*function\s*\(", text):
            issues.append(f"{source}: wrapped render fn must use function(options, data) form")
        if "return Editor.generateHtml" not in text:
            issues.append(f"{source}: wrapped render must return Editor.generateHtml(...)")

    if 'data-id="hint"' in text:
        issues.append(f"{source}: top-level dashboard hints must be native dashboard metadata, not chart-body UI")
    if re.search(r"\bdata\.title\b", text):
        issues.append(f"{source}: top-level dashboard titles must be native dashboard metadata, not chart-body UI")

    return ValidationResult(ok=not issues, issues=issues)


def validate_editor_runtime_contract(
    value: dict[str, Any],
    *,
    source: str = "<memory>",
    allow_unknown_warnings: bool = False,
) -> dict[str, Any]:
    canonical = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    payload_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rule_token = _editor_validation_rule_token()
    cache_key = f"{payload_sha256}:{rule_token}"
    with _EDITOR_VALIDATION_CACHE_LOCK:
        cached = _EDITOR_VALIDATION_CACHE.get(cache_key)
        if cached is not None:
            base = deepcopy(cached)
            _EDITOR_VALIDATION_CACHE.move_to_end(cache_key)
            cache_hit = True
        else:
            base = {}
            cache_hit = False
    if not base:
        computed = _validate_editor_runtime_contract_uncached(value)
        with _EDITOR_VALIDATION_CACHE_LOCK:
            cached = _EDITOR_VALIDATION_CACHE.get(cache_key)
            if cached is not None:
                base = deepcopy(cached)
                cache_hit = True
            else:
                base = computed
                _EDITOR_VALIDATION_CACHE[cache_key] = deepcopy(base)
                while len(_EDITOR_VALIDATION_CACHE) > EDITOR_VALIDATION_CACHE_MAX_ENTRIES:
                    _EDITOR_VALIDATION_CACHE.popitem(last=False)
            _EDITOR_VALIDATION_CACHE.move_to_end(cache_key)
    if cache_hit:
        record_cache_hit("editor_validation")
    base["source"] = source
    for finding in base.get("findings") or []:
        if isinstance(finding, dict):
            finding["source"] = source
    warnings = sum(1 for finding in base.get("findings") or [] if finding.get("severity") == "warning")
    errors = sum(1 for finding in base.get("findings") or [] if finding.get("severity") == "error")
    blocking_warning_rules = set(base.get("blocking_warning_rules") or [])
    for finding in base.get("findings") or []:
        if isinstance(finding, dict):
            finding["blocking"] = bool(
                finding.get("severity") == "error"
                or (
                    finding.get("severity") == "warning"
                    and finding.get("rule") in blocking_warning_rules
                )
            )
    blocking = sum(
        1
        for finding in base.get("findings") or []
        if isinstance(finding, dict) and finding.get("blocking") is True
    )
    base["allow_unknown_warnings"] = bool(allow_unknown_warnings)
    base["ok"] = blocking == 0
    base["summary"] = {
        "findings": len(base.get("findings") or []),
        "errors": errors,
        "warnings": warnings,
        "blocking_findings": blocking,
    }
    base["payload_sha256"] = payload_sha256
    base["validation_cache"] = {
        "hit": cache_hit,
        "strategy": "canonical_payload_and_rule_resources",
        "rule_token": rule_token,
    }
    return base


def _validate_editor_runtime_contract_uncached(value: dict[str, Any]) -> dict[str, Any]:
    contract = _load_runtime_contract()
    allowlist = _load_editor_allowlist()
    uri_policy = _uri_policy(value)
    findings: list[dict[str, Any]] = []
    for path, text in _iter_strings(value):
        findings.extend(
            _runtime_findings_for_text(
                text,
                path=path,
                source="<payload>",
                contract=contract,
                allowlist=allowlist,
                uri_policy=uri_policy,
            )
        )
        findings.extend(
            _date_range_rerender_findings(
                text,
                path=path,
                source="<payload>",
                contract=contract,
            )
        )
    for path, html_object in _iter_html_objects(value):
        findings.extend(
            _runtime_findings_for_html_object(
                html_object,
                path=path,
                source="<payload>",
                contract=contract,
            )
        )
    findings.extend(_selector_value_findings(value, source="<payload>", contract=contract))
    findings.extend(_editor_payload_shape_findings(value, source="<payload>", contract=contract))
    findings.extend(_advanced_editor_semantic_findings(value, source="<payload>", contract=contract))
    findings = _dedupe_findings(findings)
    blocking_warning_rules = {
        str(item)
        for item in contract.get("blocking_warning_rules") or []
        if str(item).strip()
    }
    blocking = [
        finding
        for finding in findings
        if finding["severity"] == "error"
        or (
            finding["severity"] == "warning"
            and finding["rule"] in blocking_warning_rules
        )
    ]
    warnings = [finding for finding in findings if finding["severity"] == "warning"]
    return {
        "ok": not blocking,
        "schema_version": "2026-06-25.editor_runtime_contract.result.v2",
        "rule_version": contract["rule_version"],
        "source": "<payload>",
        "allow_unknown_warnings": False,
        "blocking_warning_rules": sorted(blocking_warning_rules),
        "official_sanitizer": {
            "allowlist_artifact": contract["official_sanitizer"]["allowlist_artifact"],
            "allowed_tag_count": len(allowlist["html_tags"]),
            "allowed_attribute_count": len(allowlist["html_attributes"]),
            "supported_method_count": len(allowlist["methods"]),
        },
        "performance_budgets_ms": contract["official_sanitizer"]["documented_execution_budgets_ms"],
        "uri_policy": uri_policy,
        "summary": {
            "findings": len(findings),
            "errors": sum(1 for finding in findings if finding["severity"] == "error"),
            "warnings": len(warnings),
            "blocking_findings": len(blocking),
        },
        "findings": findings,
    }


def _editor_validation_rule_token() -> str:
    if os.getenv(RESOURCE_OVERRIDE_ENV, "").strip():
        return _build_editor_validation_rule_token()
    return _packaged_editor_validation_rule_token()


@lru_cache(maxsize=1)
def _packaged_editor_validation_rule_token() -> str:
    return _build_editor_validation_rule_token()


def _build_editor_validation_rule_token() -> str:
    digest = hashlib.sha256()
    digest.update(EDITOR_VALIDATION_CACHE_VERSION.encode("utf-8"))
    for relative in (CONTRACT_RESOURCE, ALLOWLIST_RESOURCE):
        try:
            digest.update(resource_text(relative).encode("utf-8"))
        except RuntimeResourceError:
            digest.update(f"<missing:{relative}>".encode("utf-8"))
    return digest.hexdigest()


def _load_runtime_contract() -> dict[str, Any]:
    return resource_json(CONTRACT_RESOURCE)


def _load_editor_allowlist() -> dict[str, Any]:
    try:
        return resource_json(ALLOWLIST_RESOURCE)
    except Exception:
        # Keep the built-in method list as a deterministic fallback for older wheels.
        # The packaged allowlist is required by the portable runtime acceptance gate.
        pass
    return {
        "methods": sorted(ALLOWED_EDITOR_METHODS),
        "html_tags": [],
        "html_attributes": [],
    }


def _runtime_findings_for_text(
    text: str,
    *,
    path: str,
    source: str,
    contract: dict[str, Any],
    allowlist: dict[str, Any],
    uri_policy: dict[str, bool],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    observed = contract.get("observed_runtime_overrides") or {}
    blocked_attributes = observed.get("blocked_attributes") or {}
    for name, pattern in blocked_attributes.items():
        findings.extend(_regex_findings(text, pattern, path=path, source=source, rule=name, contract=contract))
    blocked_tags = observed.get("blocked_tags") or {}
    for name, pattern in blocked_tags.items():
        findings.extend(_regex_findings(text, pattern, path=path, source=source, rule=name, contract=contract))
    blocked_patterns = observed.get("blocked_patterns") or {}
    for name, pattern in blocked_patterns.items():
        findings.extend(_regex_findings(text, pattern, path=path, source=source, rule=name, contract=contract))
    governance = contract.get("project_governance") or {}
    warning_patterns = governance.get("warning_patterns") or {}
    for name, pattern in warning_patterns.items():
        findings.extend(
            _regex_findings(
                text,
                pattern,
                path=path,
                source=source,
                rule=name,
                contract=contract,
                severity="warning",
                layer="project_governance",
            )
        )
    findings.extend(_method_findings(text, path=path, source=source, contract=contract, allowlist=allowlist))
    findings.extend(_html_tag_findings(text, path=path, source=source, contract=contract, allowlist=allowlist))
    findings.extend(_d3_attr_findings(text, path=path, source=source, contract=contract))
    findings.extend(_html_attr_findings(text, path=path, source=source, contract=contract))
    findings.extend(
        _uri_findings(
            text,
            path=path,
            source=source,
            contract=contract,
            allow_http=uri_policy["allow_http"],
            allow_relative=uri_policy["allow_relative"],
        )
    )
    findings.extend(_performance_findings(text, path=path, source=source, contract=contract))
    findings.extend(_visual_governance_findings(text, path=path, source=source, contract=contract))
    return findings


def _uri_policy(value: dict[str, Any]) -> dict[str, bool]:
    policy = value.get("uri_policy") if isinstance(value, dict) else {}
    policy = policy if isinstance(policy, dict) else {}
    return {
        "allow_http": policy.get("allow_http") is True,
        "allow_relative": policy.get("allow_relative") is not False,
        "plain_text_fallback": True,
    }


def _uri_findings(
    text: str,
    *,
    path: str,
    source: str,
    contract: dict[str, Any],
    allow_http: bool,
    allow_relative: bool,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pattern in (HTML_URI_ATTR_RE, D3_URI_ATTR_RE):
        for match in pattern.finditer(text):
            raw_value = match.group("value")
            if "${" in raw_value:
                expressions = [item.group("expression") for item in DYNAMIC_INTERPOLATION_RE.finditer(raw_value)]
                if not expressions or any(not _uri_expression_is_sanitized(expression) for expression in expressions):
                    findings.append(
                        _finding(
                            path=path,
                            line=_line_for_offset(text, match.start()),
                            source=source,
                            rule="dynamic_uri_without_sanitizer",
                            contract=contract,
                            layer="uri_safety",
                        )
                    )
                continue
            decision = assess_uri(raw_value, allow_http=allow_http, allow_relative=allow_relative)
            if not decision.allowed:
                findings.append(
                    _finding(
                        path=path,
                        line=_line_for_offset(text, match.start()),
                        source=source,
                        rule="unsafe_uri_scheme",
                        contract=contract,
                        layer="uri_safety",
                    )
                )
    for match in D3_DYNAMIC_URI_ATTR_RE.finditer(text):
        raw_value = match.group("value").strip()
        if raw_value[:1] in {"'", '"'}:
            continue
        candidate = raw_value
        if any(candidate.startswith(f"{name}(") for name in URI_SANITIZER_NAMES):
            candidate += ")" * max(0, candidate.count("(") - candidate.count(")"))
        if not _uri_expression_is_sanitized(candidate):
            findings.append(
                _finding(
                    path=path,
                    line=_line_for_offset(text, match.start()),
                    source=source,
                    rule="dynamic_uri_without_sanitizer",
                    contract=contract,
                    layer="uri_safety",
                )
            )
    return findings


def _uri_expression_is_sanitized(expression: str) -> bool:
    value = expression.strip()
    if "=>" in value:
        value = value.split("=>", 1)[1].strip()
    function_return = re.fullmatch(r"function\s*\([^)]*\)\s*\{\s*return\s+(.+?);?\s*\}", value, re.S)
    if function_return:
        value = function_return.group(1).strip()
    value = _strip_balanced_parentheses(value)
    call = _single_js_call(value)
    if call is None:
        return False
    name, arguments = call
    if name in URI_SANITIZER_NAMES:
        return True
    if name in URI_ESCAPE_WRAPPER_NAMES:
        return _uri_expression_is_sanitized(arguments)
    return False


def _strip_balanced_parentheses(value: str) -> str:
    current = value.strip()
    while current.startswith("(") and _matching_parenthesis(current, 0) == len(current) - 1:
        current = current[1:-1].strip()
    return current


def _single_js_call(value: str) -> tuple[str, str] | None:
    match = re.match(r"^([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", value)
    if not match:
        return None
    opening = value.find("(", match.start())
    closing = _matching_parenthesis(value, opening)
    if closing < 0 or value[closing + 1 :].strip():
        return None
    return match.group(1), value[opening + 1 : closing]


def _matching_parenthesis(value: str, opening: int) -> int:
    depth = 0
    quote = ""
    escaped = False
    for index in range(opening, len(value)):
        character = value[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if character in {"'", '"', "`"}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _runtime_findings_for_html_object(
    html_object: dict[str, Any],
    *,
    path: str,
    source: str,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    tag = str(html_object.get("tag") or "")
    if tag.lower() == "script":
        findings.append(_finding(path=path, line=1, source=source, rule="inline_script_tag", contract=contract))
    attrs = html_object.get("attrs") or html_object.get("attributes") or html_object.get("props") or {}
    if isinstance(attrs, dict):
        for attr_name in attrs:
            finding = _attribute_finding_for_name(str(attr_name), path=path, line=1, source=source, contract=contract)
            if finding:
                findings.append(finding)
    return findings


def _method_findings(
    text: str,
    *,
    path: str,
    source: str,
    contract: dict[str, Any],
    allowlist: dict[str, Any],
) -> list[dict[str, Any]]:
    supported = {str(method) for method in allowlist.get("methods") or ALLOWED_EDITOR_METHODS}
    findings: list[dict[str, Any]] = []
    for match in RUNTIME_METHOD_RE.finditer(text):
        method = match.group(2)
        if method not in supported:
            findings.append(
                _finding(
                    path=path,
                    line=_line_for_offset(text, match.start()),
                    source=source,
                    rule="unknown_runtime_call",
                    contract=contract,
                    layer="official_sanitizer",
                )
            )
    return findings


def _d3_attr_findings(text: str, *, path: str, source: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for match in D3_ATTR_RE.finditer(text):
        attr_name = match.group("name")
        finding = _attribute_finding_for_name(
            attr_name,
            path=path,
            line=_line_for_offset(text, match.start()),
            source=source,
            contract=contract,
        )
        if finding:
            findings.append(finding)
    return findings


def _html_attr_findings(text: str, *, path: str, source: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for tag_match in HTML_TAG_RE.finditer(text):
        tag = tag_match.group("tag")
        if tag.lower() == "script":
            continue
        attrs = tag_match.group("attrs") or ""
        for attr_match in HTML_ATTR_RE.finditer(attrs):
            finding = _attribute_finding_for_name(
                attr_match.group("name"),
                path=path,
                line=_line_for_offset(text, tag_match.start() + attr_match.start()),
                source=source,
                contract=contract,
            )
            if finding:
                findings.append(finding)
    return findings


def _html_tag_findings(
    text: str,
    *,
    path: str,
    source: str,
    contract: dict[str, Any],
    allowlist: dict[str, Any],
) -> list[dict[str, Any]]:
    allowed = {str(tag).lower() for tag in allowlist.get("html_tags") or []}
    findings: list[dict[str, Any]] = []
    for match in HTML_TAG_RE.finditer(text):
        tag = match.group("tag")
        normalized = tag.lower()
        if normalized == "script":
            continue
        if normalized not in allowed:
            findings.append(
                _finding(
                    path=path,
                    line=_line_for_offset(text, match.start()),
                    source=source,
                    rule="unsupported_html_tag",
                    contract=contract,
                    layer="official_sanitizer",
                )
            )
    return findings


def _attribute_finding_for_name(
    attr_name: str,
    *,
    path: str,
    line: int,
    source: str,
    contract: dict[str, Any],
) -> dict[str, Any] | None:
    normalized = attr_name.strip().lower()
    if normalized.startswith("on"):
        return _finding(path=path, line=line, source=source, rule="inline_event_handler", contract=contract)
    if normalized == "srcdoc":
        return _finding(path=path, line=line, source=source, rule="srcdoc_attribute", contract=contract)
    if normalized == "markerwidth":
        return _finding(path=path, line=line, source=source, rule="svg_marker_width", contract=contract)
    if normalized == "markerheight":
        return _finding(path=path, line=line, source=source, rule="svg_marker_height", contract=contract)
    if normalized == "marker-end":
        return _finding(path=path, line=line, source=source, rule="svg_marker_end", contract=contract)
    if normalized == "rel":
        return _finding(path=path, line=line, source=source, rule="unsupported_rel", contract=contract)
    return None


def _performance_findings(text: str, *, path: str, source: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = contract.get("performance_diagnostics") or {}
    findings: list[dict[str, Any]] = []
    arg_limit = int(diagnostics.get("wrap_fn_arg_bytes_warning") or 6000)
    for match in re.finditer(r"Editor\.wrapFn\s*\(\s*\{(?P<body>.{0,20000}?)fn\s*:", text, flags=re.S):
        body = match.group("body")
        args_match = re.search(r"args\s*:\s*(?P<args>\[[^\]]*\])", body, flags=re.S)
        if args_match and len(args_match.group("args").encode("utf-8")) > arg_limit:
            findings.append(
                _finding(
                    path=path,
                    line=_line_for_offset(text, match.start()),
                    source=source,
                    rule="wrapfn_argument_bytes",
                    contract=contract,
                    severity="warning",
                    layer="performance_diagnostics",
                )
            )
    heavy_limit = int(diagnostics.get("heavy_iteration_warning") or 100000)
    heavy_loop_re = re.compile(r"\b(for|while)\s*\([^)]*(?:<|<=)\s*(?P<count>\d{6,}|1e\d+)", re.I | re.S)
    for match in heavy_loop_re.finditer(text):
        raw_count = match.group("count").lower()
        if _numeric_bound(raw_count) >= heavy_limit:
            findings.append(
                _finding(
                    path=path,
                    line=_line_for_offset(text, match.start()),
                    source=source,
                    rule="heavy_loop_budget_risk",
                    contract=contract,
                    severity="warning",
                    layer="performance_diagnostics",
                )
            )
    for pattern in diagnostics.get("data_multiplication_patterns") or []:
        findings.extend(
            _regex_findings(
                text,
                pattern,
                path=path,
                source=source,
                rule="data_multiplication_budget_risk",
                contract=contract,
                severity="warning",
                layer="performance_diagnostics",
            )
        )
    return findings


def _visual_governance_findings(text: str, *, path: str, source: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    patterns = {
        "decorative_css_shadow": r"(box-shadow|text-shadow|filter\s*:\s*drop-shadow)",
        "decorative_css_gradient": r"(linear-gradient|radial-gradient)",
        "decorative_css_3d": r"(\b3d\b|perspective\s*:|transform-style\s*:\s*preserve-3d)",
        "html_table_bar": r"<div[^>]+style=[^>]+(?:width|height)\s*:[^>]+%[^>]*>\s*</div>",
        "html_table_inside_advanced_editor": r"<\s*(?:table|thead|tbody|tr|td|th)\b|role\s*=\s*['\"]table['\"]",
        "div_grid_table_inside_advanced_editor": r"(?:div-grid\s+table|html_table|table-grid|table_grid)",
        "inline_chart_body_heading": r"<\s*h[12]\b",
    }
    for rule, pattern in patterns.items():
        findings.extend(
            _regex_findings(
                text,
                pattern,
                path=path,
                source=source,
                rule=rule,
                contract=contract,
                layer="renderer_visual_spec",
            )
        )
    return findings


def _advanced_editor_semantic_findings(value: Any, *, source: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if _is_static_reference_artifact(value):
        return []
    findings: list[dict[str, Any]] = []
    for path, text in _iter_strings(value):
        if not _is_chart_body_path(path):
            continue
        roles = _dashboard_roles_in_text(text)
        material_roles = roles - {"title_hint"}
        if len(material_roles) >= 2:
            findings.append(
                _finding(
                    path=path,
                    line=1,
                    source=source,
                    rule="composite_dashboard_in_advanced_editor",
                    contract=contract,
                    layer="renderer_visual_spec",
                )
            )
        if "selector" in roles:
            findings.append(
                _finding(
                    path=path,
                    line=1,
                    source=source,
                    rule="selector_inside_advanced_editor_body",
                    contract=contract,
                    layer="renderer_visual_spec",
                )
            )
        if "kpi_grid" in roles:
            findings.append(
                _finding(
                    path=path,
                    line=1,
                    source=source,
                    rule="kpi_card_grid_inside_advanced_editor",
                    contract=contract,
                    layer="renderer_visual_spec",
                )
            )
    return findings


def _dashboard_roles_in_text(text: str) -> set[str]:
    lowered = text.lower()
    roles: set[str] = set()
    if re.search(
        r"<\s*select\b|selector-row|data-selector|class\s*=\s*['\"][^'\"]*(?:selector|filter-control|control-panel)"
        r"|impacttabsids|dropdown|control_node|type\s*:\s*['\"]select['\"]",
        lowered,
    ):
        roles.add("selector")
    if (
        re.search(r"\b(kpi|indicator|metric)\b", lowered)
        and re.search(r"(kpi-card|metric-card|card-grid|cards-grid)", lowered)
    ):
        roles.add("kpi_grid")
    if re.search(r"<\s*(?:table|thead|tbody|tr|td|th)\b|role\s*=\s*['\"]table['\"]|div-grid\s+table|html_table", lowered):
        roles.add("table")
    if re.search(r"\b(chart-container|plot-area|chart-grid|line-chart|bar-chart|axis)\b", lowered):
        roles.add("chart")
    if re.search(r"<\s*h[12]\b|data-id\s*=\s*['\"]hint['\"]|\btitle\b|\bhint\b", lowered):
        roles.add("title_hint")
    return roles


def _is_chart_body_path(path: str) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in ("prepare", "render", "html", "body"))


def _is_static_reference_artifact(value: Any) -> bool:
    if isinstance(value, dict):
        for key in (
            "static_reference_artifact",
            "reference_only",
            "static_mock",
            "mock_reference",
            "allow_composite_advanced_editor_reference",
        ):
            if value.get(key) is True:
                return True
        intent = str(value.get("artifact_intent") or value.get("intent") or "").strip().lower()
        if intent in {"static_mock", "static_reference", "reference_only", "reference_artifact"}:
            return True
        return any(_is_static_reference_artifact(item) for item in value.values())
    if isinstance(value, list):
        return any(_is_static_reference_artifact(item) for item in value)
    return False


def _editor_payload_shape_findings(value: Any, *, source: str, contract: dict[str, Any], path: str = "$") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "metaon" in value:
            findings.append(
                _finding(
                    path=f"{path}.metaon",
                    line=1,
                    source=source,
                    rule="editor_metaon_tab",
                    contract=contract,
                    layer="compiled_payload",
                )
            )
        data = value.get("data")
        if isinstance(data, dict):
            findings.extend(_editor_data_findings(data, source=source, contract=contract, path=f"{path}.data"))
        for key, item in value.items():
            findings.extend(_editor_payload_shape_findings(item, source=source, contract=contract, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_editor_payload_shape_findings(item, source=source, contract=contract, path=f"{path}[{index}]"))
    return findings


def _editor_data_findings(data: dict[str, Any], *, source: str, contract: dict[str, Any], path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if "metaon" in data:
        findings.append(
            _finding(
                path=f"{path}.metaon",
                line=1,
                source=source,
                rule="editor_metaon_tab",
                contract=contract,
                layer="compiled_payload",
            )
        )
    meta = data.get("meta")
    parsed_meta: Any = None
    if isinstance(meta, str) and meta.strip().startswith("{"):
        try:
            parsed_meta = json.loads(meta)
        except json.JSONDecodeError:
            parsed_meta = None
    elif isinstance(meta, dict):
        parsed_meta = meta
    if isinstance(parsed_meta, dict) and "title" in parsed_meta:
        findings.append(
            _finding(
                path=f"{path}.meta.title",
                line=1,
                source=source,
                rule="unsupported_editor_meta_title",
                contract=contract,
                layer="compiled_payload",
            )
        )
    return findings


def _selector_value_findings(value: Any, *, source: str, contract: dict[str, Any], path: str = "$") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "value" in value and not isinstance(value["value"], str):
            findings.append(
                _finding(
                    path=f"{path}.value",
                    line=1,
                    source=source,
                    rule="selector_option_value_not_string",
                    contract=contract,
                    layer="renderer_visual_spec",
                )
            )
        for key, item in value.items():
            findings.extend(_selector_value_findings(item, source=source, contract=contract, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(_selector_value_findings(item, source=source, contract=contract, path=f"{path}[{index}]"))
    return findings


def _regex_findings(
    text: str,
    pattern: str,
    *,
    path: str,
    source: str,
    rule: str,
    contract: dict[str, Any],
    severity: str = "error",
    layer: str = "observed_runtime_overrides",
) -> list[dict[str, Any]]:
    findings = []
    for match in re.finditer(pattern, text, flags=re.I | re.S):
        findings.append(
            _finding(
                path=path,
                line=_line_for_offset(text, match.start()),
                source=source,
                rule=rule,
                contract=contract,
                severity=severity,
                layer=layer,
            )
        )
    return findings


def _finding(
    *,
    path: str,
    line: int,
    source: str,
    rule: str,
    contract: dict[str, Any],
    severity: str = "error",
    layer: str = "observed_runtime_overrides",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "layer": layer,
        "rule": rule,
        "rule_version": contract["rule_version"],
        "path": path,
        "line": line,
        "source": source,
        "message": str((contract.get("messages") or {}).get(rule) or f"{rule} is not supported by the runtime"),
    }


def _date_range_rerender_findings(
    text: str,
    *,
    path: str,
    source: str,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    from datalens_dev_mcp.pipeline.selector_maintenance import date_range_rerender_findings

    warnings = date_range_rerender_findings(text)
    if not warnings:
        return []
    line = _line_for_offset(text, text.find("updateControlsOnChange"))
    return [
        {
            "severity": "warning",
            "layer": "selector_runtime_safety",
            "rule": str(item["rule"]),
            "rule_version": contract["rule_version"],
            "path": path,
            "line": line,
            "source": source,
            "message": str(item["message"]),
        }
        for item in warnings
    ]


def _iter_strings(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for finding in findings:
        key = (
            finding.get("severity"),
            finding.get("layer"),
            finding.get("rule"),
            finding.get("path"),
            finding.get("line"),
        )
        deduped.setdefault(key, finding)
    return list(deduped.values())


def _iter_html_objects(value: Any, path: str = "$"):
    if isinstance(value, dict):
        if isinstance(value.get("tag"), str) and isinstance(
            value.get("attrs") or value.get("attributes") or value.get("props") or {}, dict
        ):
            yield path, value
        for key, item in value.items():
            yield from _iter_html_objects(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_html_objects(item, f"{path}[{index}]")


def _numeric_bound(raw: str) -> int:
    if "e" in raw:
        base, exponent = raw.split("e", 1)
        try:
            return int(float(base) * (10 ** int(exponent)))
        except ValueError:
            return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
