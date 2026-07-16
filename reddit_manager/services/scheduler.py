"""Irregular next-run scheduling."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from reddit_manager.config import WORKER_CONFIG


def sample_next_interval_hours() -> float:
    low = float(WORKER_CONFIG["SCHEDULER_MIN_HOURS"])
    high = float(WORKER_CONFIG["SCHEDULER_MAX_HOURS"])
    mean = (low + high) / 2.0
    value = random.lognormvariate(math.log(max(mean, 1.0)), 0.55)
    return max(low, min(high, value))


def compute_next_eligible_at(from_time: datetime | None = None) -> str:
    base = from_time or datetime.now(timezone.utc)
    delta = timedelta(hours=sample_next_interval_hours())
    return (base + delta).replace(microsecond=0).isoformat().replace("+00:00", "Z")
