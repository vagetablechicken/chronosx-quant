from __future__ import annotations

from functools import lru_cache

from chronosx_quant.scheduler import StaticMinuteScheduler


@lru_cache(maxsize=None)
def get_scheduler(calendar_name: str) -> StaticMinuteScheduler:
    """Return an LRU-cached scheduler using the default start and end dates.

    The cache key only includes ``calendar_name``. Tests that need a specific
    schedule start or end must not use this helper; construct a
    ``StaticMinuteScheduler`` directly instead.
    """
    return StaticMinuteScheduler(calendar_name)
