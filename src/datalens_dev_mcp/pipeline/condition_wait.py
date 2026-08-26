from __future__ import annotations

import time
from typing import Any, Callable

from datalens_dev_mcp.pipeline.result_dedup import semantic_result_hash
from datalens_dev_mcp.validators.redaction import sanitize_value


def wait_for_condition(
    poll: Callable[[], Any],
    satisfied: Callable[[Any], bool],
    *,
    timeout_sec: float = 30.0,
    initial_delay_sec: float = 0.25,
    max_delay_sec: float = 4.0,
    retry_after: Callable[[Any], float | None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Poll for a state condition and return only material state changes."""

    started = clock()
    delay = max(0.0, initial_delay_sec)
    changes: list[Any] = []
    last_hash = ""
    polls = 0
    while True:
        value = sanitize_value(poll())
        polls += 1
        digest = semantic_result_hash(value)
        if digest != last_hash:
            changes.append(value)
            last_hash = digest
        if satisfied(value):
            return {
                "status": "satisfied",
                "poll_count": polls,
                "state_changes": changes,
                "suppressed_unchanged_polls": polls - len(changes),
                "final": value,
            }
        elapsed = clock() - started
        if elapsed >= timeout_sec:
            return {
                "status": "timeout",
                "poll_count": polls,
                "state_changes": changes,
                "suppressed_unchanged_polls": polls - len(changes),
                "final": value,
            }
        requested = retry_after(value) if retry_after else None
        pause = max(delay, float(requested or 0.0))
        pause = min(pause, max(0.0, timeout_sec - elapsed))
        sleeper(pause)
        delay = min(max_delay_sec, max(initial_delay_sec, delay * 2 or initial_delay_sec))
