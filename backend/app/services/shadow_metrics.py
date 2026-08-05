"""V67 Phase 7 — in-process Shadow metrics (read-only; no runtime actions)."""
from __future__ import annotations
from collections import defaultdict
from threading import Lock

_lock = Lock()
_counters: dict[str, int] = defaultdict(int)


def incr(name: str, n: int = 1) -> None:
    with _lock:
        _counters[name] += n


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)


def reset_for_tests() -> None:
    with _lock:
        _counters.clear()
