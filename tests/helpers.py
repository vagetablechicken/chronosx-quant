from __future__ import annotations

from functools import lru_cache

from chronosx_quant.scheduler import StaticMinuteScheduler


@lru_cache(maxsize=None)
def get_scheduler(calendar_name: str) -> StaticMinuteScheduler:
    return StaticMinuteScheduler(calendar_name)
