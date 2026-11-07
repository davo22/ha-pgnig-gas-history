"""Pure helpers for spreading a billing period evenly over hours (no HA imports)."""
from __future__ import annotations

from datetime import datetime, timedelta

HOUR = timedelta(hours=1)


def hourly_points(
    start: datetime, end: datetime, total: float, base_sum: float
) -> list[tuple[datetime, float, float]]:
    """Split `total` evenly over every hour in [start, end).

    Returns (hour start, change, cumulative sum) tuples. `start` and `end` must
    be aware datetimes on hour boundaries; the caller passes local midnights
    converted to UTC, so DST days simply have 23 or 25 hours. The last hour
    absorbs the rounding remainder so the period adds up to `total` exactly.
    """
    hours = int((end - start) / HOUR)
    if hours <= 0:
        return []
    per_hour = total / hours
    points: list[tuple[datetime, float, float]] = []
    running = base_sum
    for i in range(hours):
        change = per_hour if i < hours - 1 else total - per_hour * (hours - 1)
        running += change
        points.append((start + i * HOUR, change, round(running, 4)))
    # Pin the final sum to the exact target, free of float drift.
    last_start, last_change, _ = points[-1]
    points[-1] = (last_start, last_change, round(base_sum + total, 4))
    return points
