from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar


T = TypeVar("T")
R = TypeVar("R")


def configured_read_workers(client: Any, *, default: int = 3) -> int:
    config = getattr(client, "config", None)
    return max(1, int(getattr(config, "max_read_concurrency", default) or default))


def bounded_read_map(
    items: Sequence[T],
    reader: Callable[[T], R],
    *,
    max_workers: int,
) -> list[R]:
    """Run independent reads concurrently while retaining input order."""

    rows = list(items)
    if len(rows) <= 1 or max_workers <= 1:
        return [reader(item) for item in rows]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(rows)), thread_name_prefix="datalens-read") as pool:
        return list(pool.map(reader, rows))
