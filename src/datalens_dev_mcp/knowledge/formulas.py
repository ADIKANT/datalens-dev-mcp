from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_json


AGGREGATE_NAMES = {
    "SUM",
    "AVG",
    "COUNT",
    "COUNTD",
    "COUNTD_APPROX",
    "MIN",
    "MAX",
    "MEDIAN",
    "QUANTILE",
    "ARG_MIN",
    "ARG_MAX",
    "ANY",
}
STRICT_NONEMPTY_AGGREGATES = AGGREGATE_NAMES - {"COUNT"}
CLAUSE_KEYWORDS = {
    "TOTAL",
    "WITHIN",
    "AMONG",
    "BEFORE",
    "FILTER",
    "BY",
    "FIXED",
    "INCLUDE",
    "EXCLUDE",
    "IGNORE",
    "DIMENSIONS",
}
KEYWORDS = {
    "AND",
    "OR",
    "NOT",
    "IF",
    "THEN",
    "ELSEIF",
    "ELSE",
    "END",
    "CASE",
    "WHEN",
    "NULL",
    "TRUE",
    "FALSE",
    *CLAUSE_KEYWORDS,
}
INFIX_PRECEDENCE = {
    "OR": 1,
    "AND": 2,
    "=": 3,
    "==": 3,
    "!=": 3,
    "<>": 3,
    "<": 3,
    "<=": 3,
    ">": 3,
    ">=": 3,
    "+": 4,
    "-": 4,
    "*": 5,
    "/": 5,
    "%": 5,
    "^": 6,
}
FALLBACK_SIGNATURES: dict[str, dict[str, Any]] = {
    "AGO": {"min": 2, "max": 4, "variadic": False},
    "IF": {"min": 3, "max": None, "variadic": True},
    "CASE": {"min": 3, "max": None, "variadic": True},
    "SUM": {"min": 1, "max": 1, "variadic": False},
    "AVG": {"min": 1, "max": 1, "variadic": False},
    "COUNT": {"min": 0, "max": 1, "variadic": False},
}


class FormulaSyntaxError(ValueError):
    def __init__(self, message: str, position: int = 0) -> None:
        super().__init__(message)
        self.position = position


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


def load_formula_registry(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        if not path.is_file():
            return {"schema_version": "missing", "functions": []}
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        return resource_json("schemas/datalens-knowledge/formula-registry.json")
    except RuntimeResourceError:
        return {"schema_version": "missing", "functions": []}


def tokenize_formula(expression: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    while index < len(expression):
        char = expression[index]
        if char.isspace():
            index += 1
            continue
        if char == "[":
            end = expression.find("]", index + 1)
            if end < 0:
                raise FormulaSyntaxError("unterminated field reference", index)
            value = expression[index + 1 : end].strip()
            if not value:
                raise FormulaSyntaxError("empty field reference", index)
            tokens.append(Token("field", value, index))
            index = end + 1
            continue
        if char in {"'", '"'}:
            quote = char
            start = index
            index += 1
            value_chars: list[str] = []
            while index < len(expression):
                current = expression[index]
                if current == "\\" and index + 1 < len(expression):
                    value_chars.append(expression[index + 1])
                    index += 2
                    continue
                if current == quote:
                    if index + 1 < len(expression) and expression[index + 1] == quote:
                        value_chars.append(quote)
                        index += 2
                        continue
                    tokens.append(Token("string", "".join(value_chars), start))
                    index += 1
                    break
                value_chars.append(current)
                index += 1
            else:
                raise FormulaSyntaxError("unterminated string literal", start)
            continue
        if char.isdigit() or (char == "." and index + 1 < len(expression) and expression[index + 1].isdigit()):
            start = index
            index += 1
            while index < len(expression) and (expression[index].isdigit() or expression[index] == "."):
                index += 1
            tokens.append(Token("number", expression[start:index], start))
            continue
        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < len(expression) and (
                expression[index].isalnum() or expression[index] in {"_", "."}
            ):
                index += 1
            value = expression[start:index]
            upper = value.upper()
            tokens.append(Token("keyword" if upper in KEYWORDS else "identifier", upper, start))
            continue
        two = expression[index : index + 2]
        if two in {"<=", ">=", "!=", "<>", "=="}:
            tokens.append(Token("operator", two, index))
            index += 2
            continue
        if char in "(),:+-*/%^=<>":
            kind = "punct" if char in "(),:" else "operator"
            tokens.append(Token(kind, char, index))
            index += 1
            continue
        raise FormulaSyntaxError(f"unexpected character {char!r}", index)
    tokens.append(Token("eof", "", len(expression)))
    return tokens


def parse_formula_expression(expression: str) -> dict[str, Any]:
    parser = _FormulaParser(tokenize_formula(expression))
    return parser.parse()


def validate_formula_expression(expression: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    active = registry or load_formula_registry()
    by_name = {str(item.get("name") or "").upper(): item for item in active.get("functions") or []}
    issues: list[dict[str, Any]] = []
    try:
        ast = parse_formula_expression(expression or "")
    except FormulaSyntaxError as exc:
        return {
            "ok": False,
            "parser": "recursive_descent",
            "ast": None,
            "function_calls": [],
            "field_refs": [],
            "issues": [
                {
                    "severity": "error",
                    "category": "syntax_error",
                    "message": str(exc),
                    "position": exc.position,
                }
            ],
        }
    calls = collect_function_calls(ast)
    field_refs = sorted(set(collect_field_refs(ast)))
    for call in calls:
        name = call["name"].upper()
        record = by_name.get(name)
        if not record and name not in FALLBACK_SIGNATURES:
            issues.append({"severity": "error", "category": "unknown_function", "function": name})
            continue
        signature = _signature_for(record, name)
        actual = len(call.get("args") or [])
        if isinstance(signature.get("min"), int) and actual < int(signature["min"]):
            issues.append(
                {
                    "severity": "error",
                    "category": "arity",
                    "function": name,
                    "expected_min": signature["min"],
                    "expected_max": signature.get("max"),
                    "actual": actual,
                }
            )
        max_args = signature.get("max")
        if isinstance(max_args, int) and actual > max_args:
            issues.append(
                {
                    "severity": "error",
                    "category": "arity",
                    "function": name,
                    "expected_min": signature.get("min"),
                    "expected_max": max_args,
                    "actual": actual,
                }
            )
        unsupported_clauses = _unsupported_clauses(call, record)
        for clause in unsupported_clauses:
            issues.append(
                {
                    "severity": "error",
                    "category": "window_lod_restriction",
                    "function": name,
                    "clause": clause,
                }
            )
    issues.extend(_semantic_issues(ast, by_name))
    return {
        "ok": not any(issue["severity"] == "error" for issue in issues),
        "parser": "recursive_descent",
        "ast": ast,
        "function_calls": [call["name"] for call in calls],
        "field_refs": field_refs,
        "issues": issues,
    }


def collect_function_calls(node: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(node, dict):
        return []
    rows: list[dict[str, Any]] = []
    if node.get("type") == "call":
        rows.append(node)
    for key in ("args", "children", "cases"):
        value = node.get(key)
        if isinstance(value, list):
            for child in value:
                rows.extend(collect_function_calls(child))
    for key in ("left", "right", "operand", "else", "condition", "result", "base"):
        value = node.get(key)
        if isinstance(value, dict):
            rows.extend(collect_function_calls(value))
    for clause in node.get("clauses") or []:
        for child in clause.get("expressions") or []:
            rows.extend(collect_function_calls(child))
    return rows


def collect_field_refs(node: dict[str, Any] | None) -> list[str]:
    if not isinstance(node, dict):
        return []
    rows: list[str] = []
    if node.get("type") == "field":
        rows.append(str(node.get("name") or ""))
    for key in ("args", "children", "cases"):
        value = node.get(key)
        if isinstance(value, list):
            for child in value:
                rows.extend(collect_field_refs(child))
    for key in ("left", "right", "operand", "else", "condition", "result", "base"):
        value = node.get(key)
        if isinstance(value, dict):
            rows.extend(collect_field_refs(value))
    for clause in node.get("clauses") or []:
        for child in clause.get("expressions") or []:
            rows.extend(collect_field_refs(child))
    return rows


class _FormulaParser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def parse(self) -> dict[str, Any]:
        expression = self.expression()
        if not self.at("eof"):
            token = self.current
            raise FormulaSyntaxError(f"unexpected token {token.value or token.kind}", token.position)
        return expression

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def at(self, kind: str, value: str | None = None) -> bool:
        token = self.current
        return token.kind == kind and (value is None or token.value.upper() == value.upper())

    def match(self, value: str) -> bool:
        if self.current.value.upper() == value.upper():
            self.index += 1
            return True
        return False

    def consume(self, value: str) -> Token:
        if not self.match(value):
            token = self.current
            raise FormulaSyntaxError(f"expected {value!r}", token.position)
        return self.tokens[self.index - 1]

    def expression(self, min_precedence: int = 1, stop_values: set[str] | None = None) -> dict[str, Any]:
        stop = stop_values or set()
        left = self.unary(stop)
        while True:
            token = self.current
            value = token.value.upper()
            if token.kind == "eof" or value in stop or value in {")", ",", "THEN", "ELSE", "ELSEIF", "END", ":"}:
                break
            precedence = INFIX_PRECEDENCE.get(value)
            if precedence is None or precedence < min_precedence:
                break
            self.index += 1
            right = self.expression(precedence + 1, stop)
            left = {"type": "binary", "operator": value, "left": left, "right": right}
        return left

    def unary(self, stop_values: set[str]) -> dict[str, Any]:
        token = self.current
        if token.value.upper() in {"NOT", "+", "-"}:
            self.index += 1
            return {"type": "unary", "operator": token.value.upper(), "operand": self.unary(stop_values)}
        return self.primary(stop_values)

    def primary(self, stop_values: set[str]) -> dict[str, Any]:
        token = self.current
        value = token.value.upper()
        if value in stop_values:
            raise FormulaSyntaxError(f"expected expression before {token.value!r}", token.position)
        if token.kind == "field":
            self.index += 1
            return {"type": "field", "name": token.value}
        if token.kind == "string":
            self.index += 1
            return {"type": "literal", "literal_type": "string", "value": token.value}
        if token.kind == "number":
            self.index += 1
            return {"type": "literal", "literal_type": "number", "value": token.value}
        if value in {"NULL", "TRUE", "FALSE"}:
            self.index += 1
            return {"type": "literal", "literal_type": value.lower(), "value": value}
        if value in {"FIXED", "INCLUDE", "EXCLUDE"}:
            return self.lod_expression()
        if value == "IF" and self._peek_value() != "(":
            return self.if_block()
        if value == "CASE":
            return self.case_block()
        if token.kind in {"identifier", "keyword"}:
            self.index += 1
            if self.match("("):
                return self.call(value)
            return {"type": "identifier", "name": value}
        if self.match("("):
            inner = self.expression(stop_values=stop_values | {")"})
            self.consume(")")
            return inner
        raise FormulaSyntaxError(f"unexpected token {token.value or token.kind}", token.position)

    def call(self, name: str) -> dict[str, Any]:
        args: list[dict[str, Any]] = []
        clauses: list[dict[str, Any]] = []
        while not self.at("eof") and not self.match(")"):
            if self.current.value.upper() in CLAUSE_KEYWORDS:
                clauses.append(self.clause())
            else:
                args.append(self.expression(stop_values={",", ")", *CLAUSE_KEYWORDS}))
            if self.current.value.upper() in CLAUSE_KEYWORDS:
                clauses.append(self.clause())
            if self.match(","):
                continue
            if self.at("eof"):
                break
        return {"type": "call", "name": name, "args": args, "clauses": clauses}

    def clause(self) -> dict[str, Any]:
        start = self.current
        head = start.value.upper()
        words = [head]
        self.index += 1
        if head == "BEFORE":
            if self.match("FILTER"):
                words.append("FILTER")
            if self.match("BY"):
                words.append("BY")
        elif head == "IGNORE" and self.match("DIMENSIONS"):
            words.append("DIMENSIONS")
        expressions: list[dict[str, Any]] = []
        while not self.at("eof") and self.current.value not in {")", ",", ":"}:
            if self.current.value.upper() in CLAUSE_KEYWORDS and expressions:
                break
            expressions.append(self.expression(stop_values={",", ")", *CLAUSE_KEYWORDS}))
        return {"type": "clause", "name": " ".join(words), "expressions": expressions}

    def lod_expression(self) -> dict[str, Any]:
        clause = self.clause()
        expression = None
        if self.match(":"):
            expression = self.expression()
        return {"type": "lod", "clause": clause, "expression": expression}

    def if_block(self) -> dict[str, Any]:
        self.consume("IF")
        condition = self.expression(stop_values={"THEN"})
        self.consume("THEN")
        result = self.expression(stop_values={"ELSEIF", "ELSE", "END"})
        cases = [{"condition": condition, "result": result}]
        while self.match("ELSEIF"):
            condition = self.expression(stop_values={"THEN"})
            self.consume("THEN")
            result = self.expression(stop_values={"ELSEIF", "ELSE", "END"})
            cases.append({"condition": condition, "result": result})
        default = None
        if self.match("ELSE"):
            default = self.expression(stop_values={"END"})
        self.consume("END")
        return {"type": "if_block", "cases": cases, "else": default}

    def case_block(self) -> dict[str, Any]:
        self.consume("CASE")
        base = None
        if self.current.value.upper() != "WHEN":
            base = self.expression(stop_values={"WHEN"})
        cases = []
        while self.match("WHEN"):
            condition = self.expression(stop_values={"THEN"})
            self.consume("THEN")
            result = self.expression(stop_values={"WHEN", "ELSE", "END"})
            cases.append({"condition": condition, "result": result})
        default = None
        if self.match("ELSE"):
            default = self.expression(stop_values={"END"})
        self.consume("END")
        return {"type": "case_block", "base": base, "cases": cases, "else": default}

    def _peek_value(self) -> str:
        if self.index + 1 >= len(self.tokens):
            return ""
        return self.tokens[self.index + 1].value.upper()


def _signature_for(record: dict[str, Any] | None, name: str) -> dict[str, Any]:
    fallback = FALLBACK_SIGNATURES.get(name.upper())
    arity = dict((record or {}).get("arity") or {})
    if fallback:
        arity.update({key: value for key, value in fallback.items() if arity.get(key) in {None, "unknown"}})
        if "min" not in arity:
            arity["min"] = fallback["min"]
        if "max" not in arity:
            arity["max"] = fallback["max"]
    if name.upper() in STRICT_NONEMPTY_AGGREGATES and int(arity.get("min") or 0) < 1:
        arity["min"] = 1
        if arity.get("confidence"):
            arity["confidence"] = f"{arity['confidence']}+nonempty_aggregate_guard"
        else:
            arity["confidence"] = "nonempty_aggregate_guard"
    return arity


def _unsupported_clauses(call: dict[str, Any], record: dict[str, Any] | None) -> list[str]:
    if not record:
        return []
    unsupported = []
    supports_bfb = str(record.get("before_filter_by") or "").startswith("supported")
    supports_lod = str(record.get("lod_support") or "").startswith("supported")
    for clause in call.get("clauses") or []:
        name = clause.get("name") or ""
        if name == "BEFORE FILTER BY" and not supports_bfb:
            unsupported.append(name)
        if name in {"FIXED", "INCLUDE", "EXCLUDE"} and not supports_lod:
            unsupported.append(name)
    return unsupported


def _semantic_issues(ast: dict[str, Any], by_name: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> str:
        kind = node.get("type")
        if kind == "field":
            return "scalar"
        if kind == "literal":
            return "literal"
        if kind == "lod":
            if isinstance(node.get("expression"), dict):
                walk(node["expression"])
            return "lod"
        if kind == "unary":
            return walk(node["operand"])
        if kind == "binary":
            left = walk(node["left"])
            right = walk(node["right"])
            if {left, right} & {"aggregate", "window"} and {left, right} & {"scalar"}:
                issues.append({"severity": "error", "category": "aggregate_scalar_mix"})
            return "aggregate" if "aggregate" in {left, right} else "scalar"
        if kind == "call":
            name = str(node.get("name") or "").upper()
            record = by_name.get(name) or {}
            child_kinds = [walk(arg) for arg in node.get("args") or []]
            aggregate_like = _is_aggregate_record(name, record)
            window_like = _is_window_record(name, record) or any(
                clause.get("name") in {"TOTAL", "WITHIN", "AMONG"} for clause in node.get("clauses") or []
            )
            if window_like:
                if child_kinds and "aggregate" not in child_kinds:
                    issues.append({"severity": "warning", "category": "window_without_aggregate_argument", "function": name})
                return "window"
            if aggregate_like and "aggregate" in child_kinds:
                issues.append({"severity": "error", "category": "aggregate_nesting", "function": name})
            if aggregate_like:
                return "aggregate"
            return "scalar"
        if kind in {"if_block", "case_block"}:
            for case in node.get("cases") or []:
                walk(case["condition"])
                walk(case["result"])
            if isinstance(node.get("else"), dict):
                walk(node["else"])
            return "scalar"
        return "scalar"

    walk(ast)
    return issues


def _is_aggregate_record(name: str, record: dict[str, Any]) -> bool:
    status = str(record.get("aggregation_status") or "")
    if status == "aggregate":
        return True
    return name.upper() in AGGREGATE_NAMES


def _is_window_record(name: str, record: dict[str, Any]) -> bool:
    status = str(record.get("window_status") or "")
    return status == "window" or name.upper().endswith("_WINDOW")
