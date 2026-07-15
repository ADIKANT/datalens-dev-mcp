from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalens_dev_mcp.validators.datalens_names import find_unsafe_internal_names

TUPLE_INDEX_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*_item)\s*\[\s*(\d+)\s*\]")
ARRAY_ZIP_RE = re.compile(r"\barrayZip\s*\(", re.IGNORECASE)
IFNULL_MIXED_RE = re.compile(
    r"\bifNull\s*\(\s*(?!toString\s*\()([A-Za-z_][A-Za-z0-9_.]*(?:_id|state|status))\s*,\s*''",
    re.IGNORECASE,
)
JOIN_ID_COMPARE_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_.]*_id)\s*=\s*([A-Za-z_][A-Za-z0-9_.]*_id)\b",
    re.IGNORECASE,
)
AVAILABILITY_DEFAULT_RE = re.compile(
    r"\b(?:ifNull|coalesce)\s*\([^)]*(?:available|availability)[^)]*,\s*0\s*\)",
    re.IGNORECASE,
)
RAW_PAYLOAD_COLUMNS = ("raw_payload_json", "detail_json")
CORRELATED_SUBQUERY_RE = re.compile(
    r"\b(?:exists|in)\s*\(\s*select\b[\s\S]{0,900}?\bwhere\b[\s\S]{0,500}?"
    r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\s*="
    r"\s*[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*",
    re.IGNORECASE,
)
AGGREGATE_ALIAS_RE = re.compile(
    r"\b(?P<function>sum|count|avg|min|max|uniqExact|uniqExactIf|countIf)\s*\("
    r"\s*(?P<expression>[^()]{1,240}?)\s*\)\s+AS\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
OR_JOIN_RE = re.compile(r"\bjoin\b[\s\S]{0,320}?\bon\b[\s\S]{0,320}?\bor\b", re.IGNORECASE)
PAIRWISE_JOIN_RE = re.compile(r"\b(?:cross\s+join|join\b[\s\S]{0,180}?\bon\s+1\s*=\s*1)", re.IGNORECASE)
SELECT_STAR_RE = re.compile(r"\bselect\s+\*", re.IGNORECASE)
ROLLUP_FINAL_JOIN_RE = re.compile(
    r"\bwith\b[\s\S]{0,2000}?\brollup\s+as\s*\([\s\S]{0,2000}?\)\s*select\b[\s\S]{0,900}?\bfrom\s+rollup\b[\s\S]{0,500}?\bjoin\b",
    re.IGNORECASE,
)
REFERENCE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*\b")
ALIAS_RE = re.compile(
    r"\b(?:from|join)\s+(?!select\b)(?:[A-Za-z_][A-Za-z0-9_\".]*)"
    r"(?:\s+(?:as\s+)?([A-Za-z_][A-Za-z0-9_]*))?",
    re.IGNORECASE,
)
CTE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", re.IGNORECASE)
SQL_QUERY_LITERAL_RE = re.compile(
    r"\bsql_query\s*:\s*`([\s\S]*?)`|\"sql_query\"\s*:\s*\"((?:\\.|[^\"])*)\"",
    re.IGNORECASE,
)
SQL_KEYWORDS = {
    "and",
    "array",
    "as",
    "by",
    "case",
    "default",
    "from",
    "group",
    "if",
    "join",
    "left",
    "on",
    "or",
    "order",
    "right",
    "select",
    "then",
    "toString",
    "where",
    "when",
    "with",
}


@dataclass(frozen=True)
class EditorSqlLintIssue:
    severity: str
    rule: str
    path: str
    message: str
    suggested_fix: str = ""
    excerpt: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "path": self.path,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "excerpt": self.excerpt[:240],
        }


@dataclass(frozen=True)
class EditorSqlLintResult:
    ok: bool
    issues: list[EditorSqlLintIssue]
    checked_paths: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [issue.to_dict() for issue in self.issues],
            "checked_paths": self.checked_paths,
        }


def lint_editor_sql_text(
    text: str,
    *,
    path: str = "<inline>",
    required_early_filters: list[str] | None = None,
    environment: str = "",
    field_types: dict[str, str] | None = None,
) -> EditorSqlLintResult:
    issues: list[EditorSqlLintIssue] = []
    issues.extend(_correlated_subquery_issues(text, path))
    issues.extend(_unknown_alias_issues(text, path))
    issues.extend(_tuple_index_issues(text, path))
    issues.extend(_array_zip_issues(text, path))
    issues.extend(_unsafe_quote_escape_issues(text, path))
    issues.extend(_ifnull_issues(text, path))
    issues.extend(_join_type_issues(text, path, field_types=field_types or {}))
    issues.extend(_aggregate_inside_scalar_issues(text, path))
    issues.extend(_lead_in_frame_issues(text, path, field_types=field_types or {}))
    issues.extend(_or_join_issues(text, path))
    issues.extend(_pairwise_join_issues(text, path))
    issues.extend(_late_filter_issues(text, path, required_early_filters or []))
    issues.extend(_select_star_prod_issues(text, path, environment=environment))
    issues.extend(_rollup_final_join_issues(text, path))
    issues.extend(_raw_payload_visibility_issues(text, path))
    issues.extend(_availability_default_issues(text, path))
    issues.extend(_unsafe_internal_name_issues(text, path))
    return EditorSqlLintResult(ok=not any(issue.severity == "error" for issue in issues), issues=issues, checked_paths=[path])


def lint_editor_sql_file(path: str | Path) -> EditorSqlLintResult:
    source = Path(path)
    text = source.read_text(encoding="utf-8", errors="replace")
    return lint_editor_sql_text(text, path=str(source))


def lint_project_editor_sql(project_root: str | Path = ".") -> EditorSqlLintResult:
    root = Path(project_root)
    checked: list[str] = []
    issues: list[EditorSqlLintIssue] = []
    candidates: list[Path] = []
    for pattern in (
        "dashboard/*/sources.js",
        "dashboard/*/bundle.json",
        "artifacts/**/*.sources.js",
        "artifacts/**/*sources*.js",
        "artifacts/**/*sql*.js",
        "artifacts/**/*sql*.json",
        "dataset/**/*.sql",
        "datasets/**/*.sql",
        "requirements/**/*.sql",
        "datalens_mapping/**/*dataset*.sql",
        "datalens_mapping/**/*source*.sql",
    ):
        candidates.extend(sorted(root.glob(pattern)))
    unique_candidates = []
    seen = set()
    for candidate in candidates:
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)
    for candidate in unique_candidates:
        checked.append(str(candidate))
        text = _candidate_text(candidate)
        result = lint_editor_sql_text(text, path=str(candidate))
        issues.extend(result.issues)
    if not checked:
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="zero_sql_lint_coverage",
                path=str(root),
                message="SQL lint checked zero paths; an empty fixture cannot produce a pass.",
                suggested_fix=(
                    "Generate or provide at least one Editor source, bundle, SQL artifact, "
                    "or dataset SQL file before validation."
                ),
                excerpt="",
            )
        )
    return EditorSqlLintResult(
        ok=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        checked_paths=checked,
    )


def _candidate_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".json":
        sql_literals = _sql_query_literals(text)
        return "\n".join(sql_literals) if sql_literals else text
    try:
        import json

        payload = json.loads(text)
    except Exception:  # noqa: BLE001
        return text
    joined = _joined_strings(payload)
    sql_literals = _sql_query_literals(joined)
    return "\n".join(sql_literals) if sql_literals else joined


def _tuple_index_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    issues = []
    for match in TUPLE_INDEX_RE.finditer(text):
        variable, index = match.groups()
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="tuple_indexing",
                path=path,
                message=f"{variable}[{index}] is tuple-like indexing; ClickHouse arrayElement expects an Array.",
                suggested_fix=f"Use tupleElement({variable}, {index}) or parse one tuple/fragment per row.",
                excerpt=_excerpt(text, match.start(), match.end()),
            )
        )
    return issues


def _correlated_subquery_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    issues = []
    for match in CORRELATED_SUBQUERY_RE.finditer(text):
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="correlated_subquery_unsupported",
                path=path,
                message="Correlated subquery/unsupported join shape can fail in ClickHouse with Code 48.",
                suggested_fix="Precompute the inner relation as a CTE and join on explicit keys after early filtering.",
                excerpt=_excerpt(text, match.start(), match.end()),
            )
        )
    return issues


def _unknown_alias_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    sql_literals = _sql_query_literals(text)
    if not sql_literals and path.endswith((".js", ".json")) and "module.exports" in text:
        return []
    scan_text = "\n".join(sql_literals) or text
    if not re.search(r"\bselect\b", scan_text, re.IGNORECASE) or not re.search(
        r"\b(?:from|join)\b",
        scan_text,
        re.IGNORECASE,
    ):
        return []
    aliases = {alias for alias in (match.group(1) for match in ALIAS_RE.finditer(scan_text)) if alias}
    table_references = {
        match.group(1).strip('"').split(".")[-1]
        for match in re.finditer(
            r"\b(?:from|join)\s+(?!select\b)([A-Za-z_][A-Za-z0-9_\".]*)",
            scan_text,
            flags=re.IGNORECASE,
        )
    }
    ctes = {match.group(1) for match in CTE_RE.finditer(scan_text)}
    allowed = {
        *(name.lower() for name in aliases),
        *(name.lower() for name in table_references),
        *(name.lower() for name in ctes),
        *(keyword.lower() for keyword in SQL_KEYWORDS),
    }
    issues: list[EditorSqlLintIssue] = []
    for match in REFERENCE_RE.finditer(scan_text):
        prefix = match.group(1)
        lowered = prefix.lower()
        if lowered in allowed:
            continue
        if _looks_like_schema_or_catalog_reference(scan_text, match.start(), prefix):
            continue
        if "_" in prefix and prefix.islower():
            continue
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="unknown_alias_reference",
                path=path,
                message=f"Reference {prefix}.<field> has no visible FROM/JOIN/CTE alias in this SQL text.",
                suggested_fix="Declare the alias explicitly or move the calculation into the CTE that owns the field.",
                excerpt=_excerpt(scan_text, match.start(), match.end()),
            )
        )
    return issues


def _array_zip_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    issues = []
    for match in ARRAY_ZIP_RE.finditer(text):
        window = text[match.start() : match.start() + 900]
        if len(re.findall(r"\bextractAll\s*\(", window, flags=re.IGNORECASE)) >= 2:
            issues.append(
                EditorSqlLintIssue(
                    severity="error",
                    rule="arrayzip_independent_regex_lists",
                    path=path,
                    message="arrayZip over multiple extractAll regex arrays can join arrays with different lengths.",
                    suggested_fix="Extract one object or fragment per row, then derive fields from the same fragment.",
                    excerpt=_excerpt(text, match.start(), match.start() + min(len(window), 240)),
                )
            )
    return issues


def _unsafe_quote_escape_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    if "\\\\'" not in text and "\\'" not in text:
        return []
    position = text.find("\\\\'")
    if position < 0:
        position = text.find("\\'")
    return [
        EditorSqlLintIssue(
            severity="error",
            rule="unsafe_single_quote_regex_escape",
            path=path,
            message="SQL regex string contains backslash-single-quote escaping that is fragile in DataLens/ClickHouse strings.",
            suggested_fix=r"Use \x27 in the regex string instead of \' style escaping.",
            excerpt=_excerpt(text, position, position + 8),
        )
    ]


def _ifnull_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    issues = []
    for match in IFNULL_MIXED_RE.finditer(text):
        field = match.group(1)
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="no_common_type_prone_ifnull",
                path=path,
                message=f"ifNull({field}, '') can mix numeric/nullable fields with String defaults.",
                suggested_fix=f"Use ifNull(toString({field}), '') before display or joins.",
                excerpt=_excerpt(text, match.start(), match.end()),
            )
        )
    return issues


def _join_type_issues(text: str, path: str, *, field_types: dict[str, str]) -> list[EditorSqlLintIssue]:
    issues = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if " join " not in f" {lowered} " and " on " not in f" {lowered} ":
            continue
        if "tostring" in lowered or "cast(" in lowered:
            continue
        for match in JOIN_ID_COMPARE_RE.finditer(line):
            left, right = match.groups()
            left_type = _declared_field_type(left, field_types)
            right_type = _declared_field_type(right, field_types)
            if left_type and right_type and _normalized_sql_type(left_type) == _normalized_sql_type(right_type):
                continue
            issues.append(
                EditorSqlLintIssue(
                    severity="error",
                    rule="no_common_type_prone_join",
                    path=f"{path}:{line_number}",
                    message=f"Join compares {left} to {right} without an explicit String cast.",
                    suggested_fix=f"Use toString({left}) = toString({right}) when source types can differ.",
                    excerpt=line.strip(),
                )
            )
    return issues


def _aggregate_inside_scalar_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    """Detect the proven Code 184 alias shapes without rejecting legal SQL.

    ClickHouse accepts scalar formatting around an aggregate, for example
    ``round(sum(revenue), 2)``. The regression fixtures cover an
    aggregate alias shadowing its source column or a later aggregation over an
    already-aggregated alias. Those narrower shapes are deterministic and do
    not turn ordinary aggregate formatting into a false blocker.
    """

    issues: list[EditorSqlLintIssue] = []
    for match in AGGREGATE_ALIAS_RE.finditer(text):
        alias = match.group("alias")
        expression = match.group("expression").strip()
        simple_expression = expression.split(".")[-1].strip(' `"')
        if simple_expression.lower() == alias.lower():
            issues.append(
                EditorSqlLintIssue(
                    severity="error",
                    rule="aggregate_alias_shadows_input",
                    path=path,
                    message=f"Aggregate alias {alias!r} shadows its input field and can be re-expanded by ClickHouse.",
                    suggested_fix=f"Use a distinct alias such as {alias}_agg or materialize the rollup in a named CTE.",
                    excerpt=_excerpt(text, match.start(), match.end()),
                )
            )
        # Alias reuse can be illegal inside the same SELECT list. Aggregating a
        # materialized alias in an outer CTE/query is a valid change of grain,
        # so never scan past this SELECT block's FROM clause.
        tail = re.split(r"\bfrom\b", text[match.end() :], maxsplit=1, flags=re.IGNORECASE)[0]
        reaggregation = re.search(
            rf"\b(?:sum|count|avg|min|max|uniqExact|uniqExactIf|countIf)\s*\(\s*"
            rf"(?:[A-Za-z_][A-Za-z0-9_]*\.)?{re.escape(alias)}\s*\)",
            tail,
            flags=re.IGNORECASE,
        )
        if reaggregation:
            start = match.end() + reaggregation.start()
            end = match.end() + reaggregation.end()
            issues.append(
                EditorSqlLintIssue(
                    severity="error",
                    rule="aggregate_alias_reaggregated",
                    path=path,
                    message=f"Aggregate alias {alias!r} is aggregated again in a later query stage.",
                    suggested_fix="Keep row-level and aggregate aliases distinct, or aggregate once in the final rollup CTE.",
                    excerpt=_excerpt(text, start, end),
                )
            )
    return issues


def _lead_in_frame_issues(
    text: str,
    path: str,
    *,
    field_types: dict[str, str],
) -> list[EditorSqlLintIssue]:
    issues: list[EditorSqlLintIssue] = []
    for start, end, arguments_text in _function_calls(text, "leadInFrame"):
        arguments = _split_top_level_arguments(arguments_text)
        if not arguments:
            continue
        value_expression = arguments[0].strip()
        normalized_expression = re.sub(r"\s+", "", value_expression).lower()
        declared_type = _declared_field_type(value_expression, field_types)
        nullable_value = bool(
            normalized_expression.startswith("tonullable(")
            or (normalized_expression.startswith("cast(") and "nullable(" in normalized_expression)
            or "nullable(" in str(declared_type or "").lower()
        )
        explicit_null_default = bool(
            len(arguments) >= 3 and arguments[2].strip().lower() in {"null", "nullable(null)"}
        )
        if nullable_value and explicit_null_default:
            continue
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="lead_in_frame_requires_nullable_and_null_default",
                path=path,
                message=(
                    "leadInFrame DateTime boundary safety requires both a nullable value and an explicit NULL "
                    "third default; otherwise the partition tail can materialize the epoch"
                ),
                suggested_fix=(
                    "Use leadInFrame(toNullable(value), offset, NULL) and assert the partition's last row is NULL."
                ),
                excerpt=_excerpt(text, start, end),
            )
        )
    return issues


def _function_calls(text: str, function_name: str) -> list[tuple[int, int, str]]:
    calls: list[tuple[int, int, str]] = []
    pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(", re.IGNORECASE)
    for match in pattern.finditer(text):
        open_index = text.find("(", match.start(), match.end())
        depth = 0
        quote = ""
        escaped = False
        for index in range(open_index, len(text)):
            char = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in {"'", '"', "`"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    calls.append((match.start(), index + 1, text[open_index + 1 : index]))
                    break
    return calls


def _split_top_level_arguments(value: str) -> list[str]:
    arguments: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            arguments.append(value[start:index])
            start = index + 1
    arguments.append(value[start:])
    return arguments


def _or_join_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    return [
        EditorSqlLintIssue(
            severity="error",
            rule="or_join_memory_explosion",
            path=path,
            message="JOIN condition contains OR, which can explode memory or produce unsupported join plans.",
            suggested_fix="Split directions into separate bounded CTEs and UNION ALL or normalize keys before joining.",
            excerpt=_excerpt(text, match.start(), match.end()),
        )
        for match in OR_JOIN_RE.finditer(text)
    ]


def _pairwise_join_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    return [
        EditorSqlLintIssue(
            severity="error",
            rule="pairwise_join_memory_explosion",
            path=path,
            message="Pairwise/CROSS join shape is not safe for generated dashboard SQL.",
            suggested_fix="Filter both sides first and join on explicit bounded keys.",
            excerpt=_excerpt(text, match.start(), match.end()),
        )
        for match in PAIRWISE_JOIN_RE.finditer(text)
    ]


def _late_filter_issues(text: str, path: str, required_filters: list[str]) -> list[EditorSqlLintIssue]:
    if not required_filters:
        return []
    lowered = text.lower()
    first_where = lowered.find(" where ")
    issues: list[EditorSqlLintIssue] = []
    for required_filter in required_filters:
        filter_token = required_filter.strip().lower()
        if not filter_token:
            continue
        first_filter = lowered.find(filter_token)
        if first_filter < 0:
            issues.append(
                EditorSqlLintIssue(
                    severity="error",
                    rule="missing_early_filter",
                    path=path,
                    message=f"Required early filter {required_filter!r} is absent.",
                    suggested_fix="Filter the driving task/request scope before wide history joins or rollups.",
                )
            )
        elif first_where >= 0 and first_filter > first_where + 1200:
            issues.append(
                EditorSqlLintIssue(
                    severity="error",
                    rule="late_filter_after_wide_scan",
                    path=path,
                    message=f"Required filter {required_filter!r} appears too late in the SQL text.",
                    suggested_fix="Move task/request filters into the first CTE that touches wide history tables.",
                    excerpt=_excerpt(text, first_filter, first_filter + len(required_filter)),
                )
            )
    return issues


def _select_star_prod_issues(text: str, path: str, *, environment: str) -> list[EditorSqlLintIssue]:
    explicit_prod_source = bool(
        re.search(r"\b(?:from|join)\s+(?:[A-Za-z_][A-Za-z0-9_]*\.)?(?:prod|production|prd)\.", text, re.IGNORECASE)
    )
    if environment.strip().lower() not in {"prod", "production", "prd"} and not explicit_prod_source:
        return []
    return [
        EditorSqlLintIssue(
            severity="error",
            rule="select_star_prod_probe",
            path=path,
            message="SELECT * is rejected for production SQL/evidence probes.",
            suggested_fix="Enumerate explicit columns and add a bounded LIMIT or scoped WHERE.",
            excerpt=_excerpt(text, match.start(), match.end()),
        )
        for match in SELECT_STAR_RE.finditer(text)
    ]


def _rollup_final_join_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    return [
        EditorSqlLintIssue(
            severity="error",
            rule="rollup_final_join_shape",
            path=path,
            message="Final SELECT from rollup reintroduces a JOIN shape after aggregation.",
            suggested_fix="Join dimensions before the rollup or materialize the joined scope in an earlier bounded CTE.",
            excerpt=_excerpt(text, match.start(), match.end()),
        )
        for match in ROLLUP_FINAL_JOIN_RE.finditer(text)
    ]


def _raw_payload_visibility_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    issues: list[EditorSqlLintIssue] = []
    lowered = text.lower()
    for field in RAW_PAYLOAD_COLUMNS:
        start = 0
        while True:
            index = lowered.find(field, start)
            if index < 0:
                break
            window = lowered[max(0, index - 140) : index + 220]
            explicitly_hidden = (
                "visible: false" in window
                or '"visible": false' in window
                or "hidden: true" in window
                or '"hidden": true' in window
            )
            if not explicitly_hidden:
                issues.append(
                    EditorSqlLintIssue(
                        severity="error",
                        rule="raw_payload_default_visible",
                        path=path,
                        message=f"Raw payload column {field} must not be default-visible in detail/source tables.",
                        suggested_fix=f"Mark {field} hidden/debug-only or remove it from default visible columns.",
                        excerpt=_excerpt(text, index, index + len(field)),
                    )
                )
            start = index + len(field)
    return issues


def _availability_default_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    issues: list[EditorSqlLintIssue] = []
    for match in AVAILABILITY_DEFAULT_RE.finditer(text):
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="availability_default_regression",
                path=path,
                message="Availability/default logic falls back to 0 for an availability field.",
                suggested_fix="Use project availability rules; DEV/test sources that are runtime-available must not default to 0.",
                excerpt=_excerpt(text, match.start(), match.end()),
            )
        )
    return issues


def _unsafe_internal_name_issues(text: str, path: str) -> list[EditorSqlLintIssue]:
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return []
    try:
        import json

        payload = json.loads(stripped)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(payload, dict):
        return []
    issues = []
    for unsafe in find_unsafe_internal_names(payload):
        issues.append(
            EditorSqlLintIssue(
                severity="error",
                rule="unsafe_internal_name",
                path=f"{path}:{unsafe['path']}",
                message=unsafe["reason"],
                suggested_fix=unsafe["suggested"],
                excerpt=unsafe["value"],
            )
        )
    return issues


def _joined_strings(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            parts.append(_joined_strings(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(_joined_strings(item))
    elif isinstance(value, str):
        parts.append(value)
    return "\n".join(parts)


def _sql_query_literals(text: str) -> list[str]:
    literals: list[str] = []
    for match in SQL_QUERY_LITERAL_RE.finditer(text):
        literal = match.group(1) or match.group(2) or ""
        if literal.strip():
            literals.append(literal)
    return literals


def _looks_like_schema_or_catalog_reference(text: str, position: int, prefix: str) -> bool:
    left = text[max(0, position - 24) : position].lower()
    right = text[position : position + 120]
    if any(keyword in left for keyword in (" from ", " join ", " update ", " into ")):
        return True
    if re.match(rf"{re.escape(prefix)}\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", right):
        return True
    return False


def _declared_field_type(field: str, field_types: dict[str, str]) -> str:
    normalized = {str(key).lower(): str(value) for key, value in field_types.items() if str(value)}
    lowered = field.lower()
    return normalized.get(lowered) or normalized.get(lowered.split(".")[-1], "")


def _normalized_sql_type(value: str) -> str:
    lowered = re.sub(r"\s+", "", str(value).lower())
    while lowered.startswith("nullable(") and lowered.endswith(")"):
        lowered = lowered[9:-1]
    aliases = {
        "varchar": "string",
        "char": "string",
        "text": "string",
        "int": "int64",
        "integer": "int64",
        "bigint": "int64",
    }
    return aliases.get(lowered, lowered)


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 80)
    right = min(len(text), end + 120)
    return " ".join(text[left:right].split())
