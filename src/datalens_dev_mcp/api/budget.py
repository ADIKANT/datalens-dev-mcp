"""Request-local provider limits and cancellation, shared by API and SDK transports."""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event, RLock
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, InputContractError


class RequestBudget:
    def __init__(self, seconds: float = 120, max_calls: int = 200, *, cancelled: Event | None = None,
                 response_reserve_sec: float = 0) -> None:
        if (type(seconds) not in {int, float} or not 0 < seconds <= 180
                or type(max_calls) is not int or not 1 <= max_calls <= 1000):
            raise InputContractError("budget_sec must be in (0, 180]; max_provider_calls in [1, 1000]")
        self.started = time.monotonic()
        self.deadline = self.started + seconds - response_reserve_sec
        self.response_reserve_sec = response_reserve_sec
        self._lock = RLock()
        self._expired = False
        self.read_progress: dict[str, Any] = {}
        self.seconds = seconds
        self.max_calls = max_calls
        self.calls = 0
        self.reads = 0
        self.effects = 0
        self.phase = "admission"
        self.cancelled = cancelled or Event()
        self.sdk_targets: dict[tuple[str, str], Any] = {}

    def check(self) -> float:
        remaining = self.deadline - time.monotonic()
        code = "operation_cancelled" if self.cancelled.is_set() else "operation_budget_exhausted"
        if self.cancelled.is_set() or self._expired or remaining <= 0:
            raise DataLensApiError("Operation budget or cancellation barrier reached; no further dispatch is admitted", remote_code=code,
                                   dispatch_state="not_dispatched", stage=self.phase)
        return remaining

    def dispatch(self, *, readonly: bool) -> float:
        # Expiry and admission are atomic: a timeout response cannot race a
        # new admission and incorrectly report that no effect was admitted.
        with self._lock:
            remaining = self.check()
            if self.calls >= self.max_calls:
                raise DataLensApiError("Operation provider-call limit reached", remote_code="operation_budget_exhausted",
                                       dispatch_state="not_dispatched", stage=self.phase)
            self.calls += 1
            self.reads += int(readonly)
            self.effects += int(not readonly)
            return remaining

    def expire(self) -> dict[str, Any]:
        with self._lock:
            self._expired = True
            return self.progress()

    def progress(self) -> dict[str, Any]:
        with self._lock:
            return {"phase": self.phase, "elapsed_sec": round(time.monotonic() - self.started, 3),
                    "budget_sec": self.seconds, "response_reserve_sec": self.response_reserve_sec,
                    "max_provider_calls": self.max_calls,
                    "provider_calls": self.calls, "provider_reads": self.reads, "provider_effects": self.effects,
                    "cancel_requested": self.cancelled.is_set(), **self.read_progress}


current_budget: ContextVar[RequestBudget | None] = ContextVar("datalens_request_budget", default=None)
request_cancellation: ContextVar[Event | None] = ContextVar("datalens_request_cancellation", default=None)


@contextmanager
def operation_budget(seconds: float = 120, max_calls: int = 200, *, response_reserve_sec: float = 0):
    existing = current_budget.get()
    if existing is not None:
        yield existing
        return
    budget = RequestBudget(seconds, max_calls, cancelled=request_cancellation.get(),
                           response_reserve_sec=response_reserve_sec)
    token = current_budget.set(budget)
    try:
        yield budget
    finally:
        current_budget.reset(token)


def check_dispatch(*, readonly: bool) -> float | None:
    cancellation = request_cancellation.get()
    if cancellation is not None and cancellation.is_set():
        raise DataLensApiError("Request cancelled before provider dispatch", remote_code="operation_cancelled",
                               dispatch_state="not_dispatched")
    budget = current_budget.get()
    return budget.dispatch(readonly=readonly) if budget is not None else None
