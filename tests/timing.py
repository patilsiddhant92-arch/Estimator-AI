"""Linear-time checks that hold on a loaded machine: they compare growth, never a wall-clock limit.

`grows_linearly(work, n)` times `work(n)` and `work(4 * n)` (best of several runs each, the garbage collector off,
one warm-up) and passes when the larger run took less than `limit` times the smaller one. Linear work grows about
4 times, quadratic about 16 times, so the default limit of 8 tells them apart; load slows both runs alike and the
best of several runs drops the slow outliers. `perf_counter` is used, not `process_time`, which ticks at about
15.6 ms on Windows. `n` should make the smaller run take some milliseconds: the base is raised until it does."""
from __future__ import annotations

import gc
import time
from collections.abc import Callable

MIN_BASE = 0.1           # seconds: a smaller run than this is timed again with a larger n


def _best(work: Callable[[int], object], n: int, runs: int) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        work(n)
        best = min(best, time.perf_counter() - start)
    return best


def growth(work: Callable[[int], object], n: int, runs: int = 5) -> float:
    """How many times longer `work(4 * n)` takes than `work(n)` (best of `runs` each)."""
    enabled = gc.isenabled()
    gc.disable()
    try:
        work(n)                                       # warm-up: caches, compiled patterns
        base = _best(work, n, runs)
        while base < MIN_BASE and n < 10_000_000:
            n *= 2
            work(n)
            base = _best(work, n, runs)
        return _best(work, 4 * n, runs) / max(base, 1e-9)
    finally:
        if enabled:
            gc.enable()


def grows_linearly(work: Callable[[int], object], n: int, limit: float = 8.0, attempts: int = 3) -> bool:
    """True when `work` grows less than `limit` times from n to 4n; a slow measurement is taken again (up to
    `attempts` times), so a burst of load on one run does not fail it, while quadratic work fails every time."""
    return any(growth(work, n) < limit for _ in range(attempts))


def grows_faster(work: Callable[[int], object], n: int, limit: float = 8.0, attempts: int = 3) -> bool:
    """True when `work` grows `limit` times or more from n to 4n in at least one of `attempts` measurements: the
    check for work that must NOT be linear. Load can only hide the growth (a burst during the small run makes
    the big one look less than `limit` times slower), never invent it, so one clear measurement is the proof and
    a single low one does not fail the test. Fewer runs per measurement (3, not 5): quadratic work is slow at
    the 4n size, and the repeats across attempts make up for it."""
    return any(growth(work, n, runs=3) >= limit for _ in range(attempts))
