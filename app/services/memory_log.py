"""
Memory measurement for the report pipeline: process RSS and DataFrame sizes, logged so a
change can be judged against a number instead of a guess.

Pure Python, no Flask -- see app/services/CLAUDE.md. Logging goes to the 'memory' logger
at INFO; nothing is emitted unless MEMORY_LOG=1 is set, so production stays quiet until
you turn it on (Railway: add MEMORY_LOG=1 to the service variables).
"""
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pandas as pd

logger = logging.getLogger('memory')

_PAGE_SIZE = os.sysconf('SC_PAGE_SIZE') if hasattr(os, 'sysconf') else 4096


def enabled() -> bool:
    return os.environ.get('MEMORY_LOG') == '1'


def rss_mb() -> float | None:
    """Resident memory of this process in MB, or None where it can't be read (e.g. Windows dev)."""
    try:
        with open('/proc/self/statm') as f:
            return int(f.read().split()[1]) * _PAGE_SIZE / 1024 / 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / 1024  # peak not current, but better than nothing (Linux reports KB)
    except (ImportError, OSError):
        return None


def frame_mb(frame: pd.DataFrame) -> float:
    """Deep size of a DataFrame in MB (counts the Python objects behind string columns)."""
    return float(frame.memory_usage(deep=True).sum()) / 1024 / 1024


def _fmt(value: float | None) -> str:
    return 'n/a' if value is None else f'{value:.0f}MB'


@contextmanager
def track(label: str, frame: pd.DataFrame | None = None) -> Iterator[None]:
    """Log RSS and elapsed time around a block. No-op unless MEMORY_LOG=1."""
    if not enabled():
        yield
        return
    before = rss_mb()
    start = time.perf_counter()
    try:
        yield
    finally:
        after = rss_mb()
        size = f' frame={frame_mb(frame):.0f}MB rows={len(frame)} cols={len(frame.columns)}' if frame is not None else ''
        logger.info('%s rss %s -> %s (%.2fs)%s', label, _fmt(before), _fmt(after),
                    time.perf_counter() - start, size)


def log_frame(label: str, frame: pd.DataFrame) -> None:
    """Log one frame's size alongside current RSS. No-op unless MEMORY_LOG=1."""
    if enabled():
        logger.info('%s rss %s frame=%.0fMB rows=%d cols=%d', label, _fmt(rss_mb()),
                    frame_mb(frame), len(frame), len(frame.columns))
