from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from datalens_dev_mcp.serialization import stable_sha256
from datalens_dev_mcp.validators.redaction import sanitize_value


RESULT_CLASSIFICATIONS = frozenset(
    {"material", "superseded", "unchanged_poll", "no_op", "empty_expected", "empty_useless", "error"}
)
ACTIVE_CONTEXT_RESULTS = frozenset({"material", "empty_expected", "error"})


def semantic_result_hash(value: Any) -> str:
    return stable_sha256(_without_volatile(value))


def classify_result(
    value: Any,
    *,
    previous: Any = None,
    poll: bool = False,
    expected_empty: bool = False,
    superseded: bool = False,
    error: bool = False,
) -> str:
    if error:
        return "error"
    if superseded:
        return "superseded"
    if _is_empty(value):
        return "empty_expected" if expected_empty else "empty_useless"
    if previous is not None and semantic_result_hash(value) == semantic_result_hash(previous):
        return "unchanged_poll" if poll else "no_op"
    return "material"


@dataclass
class ResultLedger:
    records: list[dict[str, Any]] = field(default_factory=list)
    _latest_by_key: dict[str, Any] = field(default_factory=dict)

    def add(
        self,
        key: str,
        value: Any,
        *,
        poll: bool = False,
        expected_empty: bool = False,
        superseded: bool = False,
        error: bool = False,
    ) -> dict[str, Any]:
        previous = self._latest_by_key.get(key)
        classification = classify_result(
            value,
            previous=previous,
            poll=poll,
            expected_empty=expected_empty,
            superseded=superseded,
            error=error,
        )
        record = {
            "key": key,
            "classification": classification,
            "sha256": semantic_result_hash(value),
            "active_context": classification in ACTIVE_CONTEXT_RESULTS,
            "value": sanitize_value(value),
        }
        self.records.append(record)
        self._latest_by_key[key] = value
        return record

    def active_context(self) -> list[dict[str, Any]]:
        return [record for record in self.records if record["active_context"]]


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _without_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_volatile(item)
            for key, item in sorted(value.items())
            if key not in {"timestamp", "updated_at", "polled_at", "elapsed_ms", "request_id", "trace_id"}
        }
    if isinstance(value, (list, tuple)):
        return [_without_volatile(item) for item in value]
    return sanitize_value(value)
