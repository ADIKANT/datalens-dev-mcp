"""Request-local provider limits and cancellation, shared by API and SDK transports."""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, InputContractError


class RequestBudget:
    def __init__(self, seconds: float = 120, max_calls: int = 200, *, cancelled: Event | None = None) -> None:
        if (type(seconds) not in {int, float} or not 0 < seconds <= 180
                or type(max_calls) is not int or not 1 <= max_calls <= 1000):
            raise InputContractError("budget_sec must be in (0, 180]; max_provider_calls in [1, 1000]")
        self.started = time.monotonic()
        self.deadline = self.started + seconds
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
        if self.cancelled.is_set() or remaining <= 0:
            raise DataLensApiError("Operation stopped before the next provider dispatch", remote_code=code,
                                   dispatch_state="not_dispatched", stage=self.phase)
        return remaining

    def dispatch(self, *, readonly: bool) -> float:
        remaining = self.check()
        if self.calls >= self.max_calls:
            raise DataLensApiError("Operation provider-call limit reached", remote_code="operation_budget_exhausted",
                                   dispatch_state="not_dispatched", stage=self.phase)
        self.calls += 1
        self.reads += int(readonly)
        self.effects += int(not readonly)
        return remaining

    def progress(self) -> dict[str, Any]:
        return {"phase": self.phase, "elapsed_sec": round(time.monotonic() - self.started, 3),
                "budget_sec": self.seconds, "max_provider_calls": self.max_calls,
                "provider_calls": self.calls, "provider_reads": self.reads, "provider_effects": self.effects,
                "cancel_requested": self.cancelled.is_set()}


current_budget: ContextVar[RequestBudget | None] = ContextVar("datalens_request_budget", default=None)
request_cancellation: ContextVar[Event | None] = ContextVar("datalens_request_cancellation", default=None)


@contextmanager
def operation_budget(seconds: float = 120, max_calls: int = 200):
    existing = current_budget.get()
    if existing is not None:
        yield existing
        return
    budget = RequestBudget(seconds, max_calls, cancelled=request_cancellation.get())
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
