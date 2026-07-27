from __future__ import annotations
from datetime import datetime
import threading
from typing import Union
import pandas as pd

from .scheduler import SchedulerManager


class ChronoTime(pd.Timestamp):
    """Scheduler-aware timestamp with trading-calendar helpers."""

    # Store mocked ``now()`` values in thread-local state.
    _local = threading.local()

    @staticmethod
    def _get_stack():
        """Return the current thread's stack of mocked timestamps."""
        if not hasattr(ChronoTime._local, "stack"):
            ChronoTime._local.stack = []
        return ChronoTime._local.stack

    @staticmethod
    def now():
        """Return the current scheduler-aware time or the active mocked value."""
        stack = ChronoTime._get_stack()
        if stack:
            # Use the top-most mocked value when time travel is active.
            return stack[-1]
        tz = SchedulerManager.get_scheduler().tz
        return ChronoTime(pd.Timestamp.now(tz))

    def __new__(cls, ts: Union[datetime, str, "ChronoTime", int, float]):
        """Create a timestamp normalized to the active scheduler timezone."""
        temp_ts = pd.Timestamp(ts)
        default_tz = SchedulerManager.get_scheduler().tz
        if temp_ts.tz is None:
            temp_ts = temp_ts.tz_localize(default_tz)
        elif temp_ts.tz != default_tz:
            # Convert into the scheduler timezone before calendar comparisons.
            temp_ts = temp_ts.tz_convert(default_tz)
        instance = super().__new__(cls, temp_ts)
        instance.__class__ = cls
        return instance

    def shift(self, delta: int, step: str = "1min") -> ChronoTime:
        """Move forward or backward by trading-time steps."""
        return ChronoTime(
            SchedulerManager.get_scheduler().shift(time=self, delta=delta, step=step)
        )

    def trading_times(
        self, end: Union[datetime, "ChronoTime", pd.Timestamp, str], step: str = "1min"
    ) -> pd.Series:
        """Return the trading timestamps in the half-open interval ``[self, end)``."""
        return SchedulerManager.get_scheduler().trading_times(
            start=self, end=ChronoTime(end), step=step
        )

    def trading_day_delta(
        self, end: Union[datetime, "ChronoTime", pd.Timestamp, str]
    ) -> int:
        """
        Return the signed trading-day distance between `self` and `end`.

        This is only an approximate trading-day count. It works at the date level,
        not the full-session level, so it ignores intraday coverage and does not
        try to measure exact tradable duration.

        Counting is based on trading-day dates in a left-closed, right-closed
        interval: [self_day, end_day]. If both timestamps are on the same trading
        day, the delta is 1. If an endpoint falls on a non-trading date, that date
        contributes 0. Forward ranges return a positive count and backward ranges
        return a negative count.

        In other words, this method counts trading dates, not tradable minutes
        or full-session coverage. A same-day trading interval returns 1, a
        same-day non-trading interval returns 0, and weekends or holidays
        inside the date span are skipped unless one of those dates is itself a
        trading day.

        Examples:
        - `ChronoTime("2026-03-10T09:30:00").trading_day_delta("2026-03-10T14:59:00") == 1`
          because both timestamps fall on the same trading date, so the closed
          date range contains exactly one trading day
        - `ChronoTime("2026-03-10T11:29:00").trading_day_delta("2026-03-12T13:00:00") == 3`
          because the date range covers `2026-03-10`, `2026-03-11`, and
          `2026-03-12`, and all three are trading dates
        - `ChronoTime("2026-03-16T09:30:00").trading_day_delta("2026-03-13T14:59:00") == -2`
          because the covered trading dates are `2026-03-13` and
          `2026-03-16`; the weekend dates in between do not count, and the
          reverse direction makes the result negative
        - `ChronoTime("2026-03-15T09:30:00").trading_day_delta("2026-03-15T14:59:00") == 0`
          because both timestamps fall on the same non-trading date, so the
          date range contains zero trading days
        """
        return SchedulerManager.get_scheduler().trading_day_delta(
            start=self, end=ChronoTime(end)
        )

    def previous_trading_time(
        self, step: str = "1min", inclusive=True
    ) -> ChronoTime | None:
        """
        Return the nearest trading timestamp at or before ``self``.

        If ``inclusive`` is ``True`` and ``self`` is already a trading
        timestamp, return ``self``. If ``inclusive`` is ``False``, return the
        previous trading timestamp strictly before ``self``. Return ``None`` if
        there is no earlier trading timestamp in the loaded schedule.
        """
        previous_time = SchedulerManager.get_scheduler().previous_trading_time(
            time=self, step=step, inclusive=inclusive
        )
        return ChronoTime(previous_time) if previous_time is not None else None

    def next_trading_time(
        self, step: str = "1min", inclusive=True
    ) -> ChronoTime | None:
        """
        Return the nearest trading timestamp at or after ``self``.

        If ``inclusive`` is ``True`` and ``self`` is already a trading
        timestamp, return ``self``. If ``inclusive`` is ``False``, return the
        next trading timestamp strictly after ``self``. Return ``None`` if
        there is no later trading timestamp in the loaded schedule.
        """
        next_time = SchedulerManager.get_scheduler().next_trading_time(
            time=self, step=step, inclusive=inclusive
        )
        return ChronoTime(next_time) if next_time is not None else None

    def is_trading(self) -> bool:
        """Return whether this timestamp falls inside trading time."""
        return SchedulerManager.get_scheduler().is_trading(self)

    def is_trading_day(self) -> bool:
        """
        Return whether this timestamp's date overlaps a trading session.

        This check uses the complete session interval. Timestamps during
        intraday breaks are accepted and treated as part of the session.
        """
        return SchedulerManager.get_scheduler().is_trading_day(self)

    def to_session_start(self) -> ChronoTime:
        """
        Return the session open for the session containing ``self``.

        ``self`` only needs to fall within the session range from session open
        to session close. Break times inside the same session are accepted. If
        ``self`` is outside any session, this method raises an exception.
        """
        return ChronoTime(SchedulerManager.get_scheduler().to_session_start(self))

    def to_session_end(self) -> ChronoTime:
        """
        Return the session close for the session containing ``self``.

        ``self`` only needs to fall within the session range from session open
        to session close. Break times inside the same session are accepted. If
        ``self`` is outside any session, this method raises an exception.
        """
        return ChronoTime(SchedulerManager.get_scheduler().to_session_end(self))

    def get_trading_date(self) -> ChronoTime:
        """
        Return the trading date as a ``ChronoTime`` at midnight.

        Returning ``ChronoTime`` makes it convenient to keep using
        scheduler-aware timestamp methods. Call ``.date()`` on the result when
        a date object is needed.

        For overnight sessions, the returned trading date can differ from this
        timestamp's calendar date. If this timestamp is outside any session,
        this method raises an exception.
        """
        return ChronoTime(SchedulerManager.get_scheduler().get_trading_date(self))
