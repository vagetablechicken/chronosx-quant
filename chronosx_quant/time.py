from __future__ import annotations
from datetime import datetime
import threading
from typing import Union
import pandas as pd

from chronosx_quant.scheduler import SchedulerManager


class ChronoTime(pd.Timestamp):
    # mock now() thread-safely
    _local = threading.local()

    @staticmethod
    def _get_stack():
        if not hasattr(ChronoTime._local, "stack"):
            ChronoTime._local.stack = []
        return ChronoTime._local.stack

    @staticmethod
    def now():
        stack = ChronoTime._get_stack()
        if stack:
            # if in mock, return mock time
            return stack[-1]
        tz = SchedulerManager.get_scheduler().tz
        return ChronoTime(pd.Timestamp.now(tz))

    def __new__(cls, ts: Union[datetime, str, "ChronoTime", int, float]):
        temp_ts = pd.Timestamp(ts)
        default_tz = SchedulerManager.get_scheduler().tz
        if temp_ts.tz is None:
            temp_ts = temp_ts.tz_localize(default_tz)
        elif temp_ts.tz != default_tz:
            # convert to named tz, to avoid compare static tz time with named tz time of scheduler
            temp_ts = temp_ts.tz_convert(default_tz)
        instance = super().__new__(cls, temp_ts)
        instance.__class__ = cls
        return instance

    def shift(self, delta: int, step: str = "1min") -> ChronoTime:
        return ChronoTime(
            SchedulerManager.get_scheduler().shift(time=self, delta=delta, step=step)
        )

    def trading_times(
        self, end: Union[datetime, "ChronoTime", pd.Timestamp, str], step: str = "1min"
    ) -> pd.Series:
        """
        [self, end)
        """
        return SchedulerManager.get_scheduler().trading_times(
            start=self, end=ChronoTime(end), step=step
        )

    def trading_day_delta(
        self, end: Union[datetime, "ChronoTime", pd.Timestamp, str]
    ) -> int:
        """
        Return the signed trading-day distance between `self` and `end`.

        Forward ranges return a positive count and backward ranges return a
        negative count.
        """
        return SchedulerManager.get_scheduler().trading_day_delta(
            start=self, end=ChronoTime(end)
        )

    def previous_trading_time(self, step: str = "1min", inclusive=True) -> ChronoTime:
        return ChronoTime(
            SchedulerManager.get_scheduler().previous_trading_time(
                time=self, step=step, inclusive=inclusive
            )
        )

    def next_trading_time(self, step: str = "1min", inclusive=True) -> ChronoTime:
        return ChronoTime(
            SchedulerManager.get_scheduler().next_trading_time(
                time=self, step=step, inclusive=inclusive
            )
        )

    def is_trading(self) -> bool:
        return SchedulerManager.get_scheduler().is_trading(self)

    def is_trading_day(self) -> bool:
        return SchedulerManager.get_scheduler().is_trading_day(self)

    def to_session_start(self) -> ChronoTime:
        return ChronoTime(SchedulerManager.get_scheduler().to_session_start(self))

    def to_session_end(self) -> ChronoTime:
        return ChronoTime(SchedulerManager.get_scheduler().to_session_end(self))
