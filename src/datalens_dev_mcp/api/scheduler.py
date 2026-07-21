from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Condition, RLock
from typing import Any


OFFICIAL_USER_REQUESTS_PER_MINUTE = 60
OFFICIAL_INSTANCE_REQUESTS_PER_MINUTE = 200
RATE_LIMIT_RECOVERY_SUCCESSES = 3


@dataclass
class _MethodMetrics:
    requests: int = 0
    queue_wait_ms: float = 0.0
    network_ms: float = 0.0
    response_bytes: int = 0
    failures: int = 0
    rate_limit_429: int = 0
    transient_retries: int = 0


@dataclass
class _SchedulerState:
    last_started_at: float = float("-inf")
    cooldown_until: float = 0.0
    active_reads: int = 0
    active_write: bool = False
    active_exclusive_read: bool = False
    pending_writes: int = 0
    rate_limited: bool = False
    recovery_successes: int = 0
    configured_interval_sec: float = 0.0
    configured_max_read_concurrency: int = 1
    methods: dict[str, _MethodMetrics] = field(default_factory=lambda: defaultdict(_MethodMetrics))


class DataLensRequestScheduler:
    """Process-scoped request-start limiter with bounded read overlap.

    Every client for the same API base URL and organization shares one state.
    The scheduler spaces request starts globally, permits bounded concurrent
    reads, and drains reads before a write is allowed to start.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._condition = Condition(RLock())
        self._states: dict[str, _SchedulerState] = {}
        self._cache_hits: dict[str, int] = defaultdict(int)

    def execute(
        self,
        *,
        key: str,
        method: str,
        readonly: bool,
        exclusive: bool = False,
        interval_sec: float,
        max_read_concurrency: int,
        operation: Callable[[], bytes],
    ) -> bytes:
        queue_started = self._clock()
        state = self._acquire(
            key=key,
            readonly=readonly,
            exclusive=exclusive,
            interval_sec=max(0.0, float(interval_sec)),
            max_read_concurrency=max(1, int(max_read_concurrency)),
        )
        request_started = self._clock()
        try:
            result = operation()
        except Exception:
            self._release(
                key=key,
                method=method,
                readonly=readonly,
                exclusive=exclusive,
                queue_wait_ms=max(0.0, (request_started - queue_started) * 1000),
                network_ms=max(0.0, (self._clock() - request_started) * 1000),
                response_bytes=0,
                success=False,
            )
            raise
        self._release(
            key=key,
            method=method,
            readonly=readonly,
            exclusive=exclusive,
            queue_wait_ms=max(0.0, (request_started - queue_started) * 1000),
            network_ms=max(0.0, (self._clock() - request_started) * 1000),
            response_bytes=len(result),
            success=True,
        )
        return result

    def note_rate_limit(self, *, key: str, method: str, retry_after_sec: float) -> None:
        with self._condition:
            state = self._state(key)
            state.cooldown_until = max(state.cooldown_until, self._clock() + max(0.0, retry_after_sec))
            state.rate_limited = True
            state.recovery_successes = 0
            state.methods[method].rate_limit_429 += 1
            self._condition.notify_all()

    def note_transient_retry(self, *, key: str, method: str) -> None:
        with self._condition:
            self._state(key).methods[method].transient_retries += 1

    def note_cache_hit(self, category: str) -> None:
        normalized = str(category or "unknown").strip() or "unknown"
        with self._condition:
            self._cache_hits[normalized] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            methods: dict[str, _MethodMetrics] = defaultdict(_MethodMetrics)
            active_reads = 0
            active_writes = 0
            active_exclusive_operations = 0
            rate_limited_states = 0
            cooldown_remaining = 0.0
            configured_intervals: list[float] = []
            configured_concurrency: list[int] = []
            now = self._clock()
            for state in self._states.values():
                active_reads += state.active_reads
                active_writes += int(state.active_write and not state.active_exclusive_read)
                active_exclusive_operations += int(state.active_write)
                rate_limited_states += int(state.rate_limited)
                cooldown_remaining = max(cooldown_remaining, max(0.0, state.cooldown_until - now))
                configured_intervals.append(state.configured_interval_sec)
                configured_concurrency.append(state.configured_max_read_concurrency)
                for method, source in state.methods.items():
                    target = methods[method]
                    target.requests += source.requests
                    target.queue_wait_ms += source.queue_wait_ms
                    target.network_ms += source.network_ms
                    target.response_bytes += source.response_bytes
                    target.failures += source.failures
                    target.rate_limit_429 += source.rate_limit_429
                    target.transient_retries += source.transient_retries
            total = _MethodMetrics()
            for source in methods.values():
                total.requests += source.requests
                total.queue_wait_ms += source.queue_wait_ms
                total.network_ms += source.network_ms
                total.response_bytes += source.response_bytes
                total.failures += source.failures
                total.rate_limit_429 += source.rate_limit_429
                total.transient_retries += source.transient_retries
            interval = max(configured_intervals, default=0.0)
            return {
                "scope": "process_per_api_base_url",
                "official_limits": {
                    "per_user_requests_per_minute": OFFICIAL_USER_REQUESTS_PER_MINUTE,
                    "per_instance_requests_per_minute": OFFICIAL_INSTANCE_REQUESTS_PER_MINUTE,
                },
                "request_interval_sec": interval,
                "effective_request_starts_per_minute": round(60.0 / interval, 2) if interval > 0 else None,
                "max_read_concurrency": max(configured_concurrency, default=1),
                "active_reads": active_reads,
                "active_writes": active_writes,
                "active_exclusive_operations": active_exclusive_operations,
                "rate_limited_states": rate_limited_states,
                "cooldown_remaining_sec": round(cooldown_remaining, 3),
                "totals": _metrics_dict(total),
                "by_method": {method: _metrics_dict(value) for method, value in sorted(methods.items())},
                "cache_hits": dict(sorted(self._cache_hits.items())),
            }

    def reset_for_tests(self) -> None:
        with self._condition:
            self._states.clear()
            self._cache_hits.clear()
            self._condition.notify_all()

    def _acquire(
        self,
        *,
        key: str,
        readonly: bool,
        exclusive: bool,
        interval_sec: float,
        max_read_concurrency: int,
    ) -> _SchedulerState:
        with self._condition:
            state = self._state(key)
            state.configured_interval_sec = interval_sec
            state.configured_max_read_concurrency = max_read_concurrency
            exclusive_access = exclusive or not readonly
            if exclusive_access:
                state.pending_writes += 1
            try:
                while True:
                    now = self._clock()
                    effective_read_limit = 1 if state.rate_limited else max_read_concurrency
                    slot_available = (
                        not state.active_write
                        and (
                            (
                                not exclusive_access
                                and state.pending_writes == 0
                                and state.active_reads < effective_read_limit
                            )
                            or (exclusive_access and state.active_reads == 0)
                        )
                    )
                    earliest_start = max(state.cooldown_until, state.last_started_at + interval_sec)
                    delay = max(0.0, earliest_start - now)
                    if slot_available and delay <= 0:
                        state.last_started_at = now
                        if exclusive_access:
                            state.active_write = True
                            state.active_exclusive_read = readonly
                        else:
                            state.active_reads += 1
                        return state
                    if slot_available and delay > 0 and self._sleeper is not None:
                        self._condition.release()
                        try:
                            self._sleeper(delay)
                        finally:
                            self._condition.acquire()
                        continue
                    self._condition.wait(timeout=delay if slot_available and delay > 0 else None)
            finally:
                if exclusive_access:
                    state.pending_writes -= 1

    def _release(
        self,
        *,
        key: str,
        method: str,
        readonly: bool,
        exclusive: bool,
        queue_wait_ms: float,
        network_ms: float,
        response_bytes: int,
        success: bool,
    ) -> None:
        with self._condition:
            state = self._state(key)
            if exclusive or not readonly:
                state.active_write = False
                state.active_exclusive_read = False
            else:
                state.active_reads = max(0, state.active_reads - 1)
            metrics = state.methods[method]
            metrics.requests += 1
            metrics.queue_wait_ms += queue_wait_ms
            metrics.network_ms += network_ms
            metrics.response_bytes += max(0, int(response_bytes))
            metrics.failures += int(not success)
            if success and state.rate_limited and self._clock() >= state.cooldown_until:
                state.recovery_successes += 1
                if state.recovery_successes >= RATE_LIMIT_RECOVERY_SUCCESSES:
                    state.rate_limited = False
                    state.recovery_successes = 0
            self._condition.notify_all()

    def _state(self, key: str) -> _SchedulerState:
        normalized = str(key or "default")
        state = self._states.get(normalized)
        if state is None:
            state = _SchedulerState()
            self._states[normalized] = state
        return state


class TokenRefreshCoordinator:
    """Single-flight refresh coordinator with success and failure cooldowns."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._condition = Condition(RLock())
        self._states: dict[str, dict[str, Any]] = {}

    def refresh(
        self,
        key: str,
        refresher: Callable[[], str],
        *,
        negative_cooldown_sec: float = 3.0,
        success_reuse_sec: float = 1.0,
    ) -> str:
        normalized = str(key or "default")
        with self._condition:
            state = self._states.setdefault(
                normalized,
                {
                    "in_flight": False,
                    "generation": 0,
                    "result": "",
                    "error": None,
                    "negative_until": 0.0,
                    "success_until": 0.0,
                },
            )
            now = self._clock()
            if state["result"] and now < state["success_until"]:
                return str(state["result"])
            if state["error"] is not None and now < state["negative_until"]:
                raise state["error"]
            if state["in_flight"]:
                generation = int(state["generation"])
                while state["in_flight"] and int(state["generation"]) == generation:
                    self._condition.wait()
                if state["error"] is not None:
                    raise state["error"]
                return str(state["result"])
            state["in_flight"] = True
        try:
            result = refresher()
            if not result:
                raise RuntimeError("token refresher returned an empty token")
        except Exception as exc:
            with self._condition:
                state["error"] = exc
                state["result"] = ""
                state["negative_until"] = self._clock() + max(0.0, negative_cooldown_sec)
                state["success_until"] = 0.0
                state["in_flight"] = False
                state["generation"] = int(state["generation"]) + 1
                self._condition.notify_all()
            raise
        with self._condition:
            state["error"] = None
            state["result"] = result
            state["negative_until"] = 0.0
            state["success_until"] = self._clock() + max(0.0, success_reuse_sec)
            state["in_flight"] = False
            state["generation"] = int(state["generation"]) + 1
            self._condition.notify_all()
        return result

    def reset_for_tests(self) -> None:
        with self._condition:
            self._states.clear()
            self._condition.notify_all()


def _metrics_dict(value: _MethodMetrics) -> dict[str, Any]:
    return {
        "requests": value.requests,
        "queue_wait_ms": round(value.queue_wait_ms, 3),
        "network_ms": round(value.network_ms, 3),
        "response_bytes": value.response_bytes,
        "failures": value.failures,
        "rate_limit_429": value.rate_limit_429,
        "transient_retries": value.transient_retries,
    }


REQUEST_SCHEDULER = DataLensRequestScheduler()
TOKEN_REFRESH_COORDINATOR = TokenRefreshCoordinator()


def scheduler_status() -> dict[str, Any]:
    return REQUEST_SCHEDULER.snapshot()


def record_cache_hit(category: str) -> None:
    REQUEST_SCHEDULER.note_cache_hit(category)
