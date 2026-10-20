from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, cast

import pandas as pd

from .scheduler import SchedulerManager


class ChronoTime(pd.Timestamp):
    """Scheduler-aware timestamp with trading-calendar helpers."""

    # Store mocked ``now()`` values in thread-local state.
    _local = threading.local()

    @classmethod
    def _get_stack(cls):
        """Return the current thread's stack of mocked timestamps."""
        if not hasattr(cls._local, "stack"):
            cls._local.stack = []
        return cls._local.stack

    @classmethod
    def now(cls, tz: Any = None) -> ChronoTime:
        """
        Return the current scheduler-aware time or the active mocked value.

        Parameters
        ----------
        tz : Any, optional
            Must be ``None``. Passing any non-None value raises
            a :exc:`ValueError` because the time zone is strictly managed by the
            active :class:`~chronosx_quant.scheduler.SchedulerManager`. This parameter
            is retained solely for signature compatibility with :meth:`pandas.Timestamp.now`.

        Returns
        -------
        ChronoTime
        """
        if tz is not None:
            raise ValueError(
                "ChronoTime.now() does not accept 'tz'; time zone is strictly managed by SchedulerManager."
            )
        return cls()

    def __new__(cls, ts: Any = None) -> ChronoTime:
        """
        Create a timestamp normalized to the active scheduler timezone.

        Timezone Handling Rules:
        -------------------------
        1. **Current Time**: If ``ts is None``, returns the current scheduler-aware time.
           Always use ``ChronoTime.now()`` or ``ChronoTime()`` to retrieve current time;
           it internally resolves the global UTC time into the scheduler timezone accurately.
        2. **Naive Inputs**: Any timezone-naive input (string, datetime, Timestamp) is
           strictly interpreted as **market wall-clock time** in the scheduler timezone
           (i.e. localized directly to ``scheduler.tz``).
        3. **Host Time Warnings**: Do NOT wrap host-system naive timestamps like
           ``ChronoTime(datetime.now())`` or ``ChronoTime(pd.Timestamp.now())``, as they
           represent host OS time (e.g., UTC in Docker containers) rather than market time
           and will cause silent timezone offsets.
        4. **Aware Inputs**: Timezone-aware inputs are converted into ``scheduler.tz``.
        """
        if ts is None:
            stack = cls._get_stack()
            if stack:
                return stack[-1]
        elif isinstance(ts, ChronoTime):
            return ts

        default_tz = SchedulerManager.get_scheduler().tz
        temp_ts = pd.Timestamp.now(tz=default_tz) if ts is None else pd.Timestamp(ts)
        if isinstance(temp_ts, type(pd.NaT)):
            raise ValueError(f"Invalid timestamp: {ts!r}")
        if temp_ts.tz is None:
            temp_ts = temp_ts.tz_localize(default_tz)
        elif temp_ts.tz != default_tz:
            # Convert into the scheduler timezone before calendar comparisons.
            temp_ts = temp_ts.tz_convert(default_tz)
        assert isinstance(temp_ts, pd.Timestamp)
        instance = cast(pd.Timestamp, super().__new__(cls, temp_ts))
        instance.__class__ = cls
        return cast(ChronoTime, instance)

    def shift(
        self,
        delta: int,
        step: str = "1min",
    ) -> ChronoTime:
        """Move forward or backward by trading minutes along the active timeline."""
        if step != "1min":
            raise ValueError(
                f"ChronoTime.shift only supports step='1min', got {step!r}. "
                "To shift by trading days, use time.trading_day.shift(delta) or ChronoDay."
            )
        return ChronoTime(
            SchedulerManager.get_scheduler().shift(time=self, delta=delta, step=step)
        )

    def trading_times(
        self, end: datetime | ChronoTime | pd.Timestamp | str, step: str = "1min"
    ) -> pd.Series:
        """Return the trading timestamps in the half-open interval ``[self, end)``."""
        return SchedulerManager.get_scheduler().trading_times(
            start=self, end=ChronoTime(end), step=step
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

    @property
    def trading_day(self) -> ChronoDay:
        """Return the trading day containing this timestamp as a ``ChronoDay``."""
        return ChronoDay(self)

    def get_trading_date(self) -> ChronoDay:
        """Return the trading day containing this timestamp as a ``ChronoDay``."""
        return self.trading_day


class ChronoDay(pd.Timestamp):
    """Scheduler-aware trading day representation (normalized to midnight in scheduler timezone)."""

    def __new__(cls, day: Any = None) -> ChronoDay:
        scheduler = SchedulerManager.get_scheduler()
        default_tz = scheduler.tz
        if day is None:
            now_ts = ChronoTime.now()
            temp_ts = scheduler.get_trading_date(now_ts)
        elif isinstance(day, ChronoTime):
            temp_ts = scheduler.get_trading_date(day)
        elif isinstance(day, ChronoDay):
            return day
        else:
            temp_ts = pd.Timestamp(day)

        if isinstance(temp_ts, type(pd.NaT)):
            raise ValueError(f"Invalid trading day: {day!r}")
        if temp_ts.tz is None:
            temp_ts = temp_ts.tz_localize(default_tz)
        elif temp_ts.tz != default_tz:
            temp_ts = temp_ts.tz_convert(default_tz)

        assert isinstance(temp_ts, pd.Timestamp)
        instance = cast(pd.Timestamp, super().__new__(cls, temp_ts))
        instance.__class__ = cls
        return cast(ChronoDay, instance)

    def shift(self, delta: int) -> ChronoDay:
        """Move forward or backward by trading days on the active calendar."""
        scheduler = SchedulerManager.get_scheduler()
        shifted_date = scheduler.shift_trading_day(day=self, delta=delta)
        return ChronoDay(shifted_date)

    def previous_trading_day(self, inclusive: bool = True) -> ChronoDay | None:
        """
        Return the nearest trading day at or before ``self``.

        If ``inclusive`` is ``True`` and ``self`` is already a trading day,
        return ``self``. If ``inclusive`` is ``False``, return the previous
        trading day strictly before ``self``. Return ``None`` if there is no
        earlier trading day in the loaded schedule.
        """
        scheduler = SchedulerManager.get_scheduler()
        res = scheduler.previous_trading_day(self, inclusive=inclusive)
        return ChronoDay(res) if res is not None else None

    def next_trading_day(self, inclusive: bool = True) -> ChronoDay | None:
        """
        Return the nearest trading day at or after ``self``.

        If ``inclusive`` is ``True`` and ``self`` is already a trading day,
        return ``self``. If ``inclusive`` is ``False``, return the next
        trading day strictly after ``self``. Return ``None`` if there is no
        later trading day in the loaded schedule.
        """
        scheduler = SchedulerManager.get_scheduler()
        res = scheduler.next_trading_day(self, inclusive=inclusive)
        return ChronoDay(res) if res is not None else None

    def previous(self, inclusive: bool = True) -> ChronoDay | None:
        """Alias for ``previous_trading_day``."""
        return self.previous_trading_day(inclusive=inclusive)

    def next(self, inclusive: bool = True) -> ChronoDay | None:
        """Alias for ``next_trading_day``."""
        return self.next_trading_day(inclusive=inclusive)

    def _get_session_idx(self) -> int:
        scheduler = SchedulerManager.get_scheduler()
        dates = scheduler.schedule.index
        self_local = self.tz_convert(scheduler.tz) if self.tzinfo is not None else self
        target = pd.Timestamp(self_local.strftime("%Y-%m-%d"))
        if target not in dates:
            raise ValueError(
                f"Date {self_local.strftime('%Y-%m-%d')} is not a valid trading day for {scheduler.calendar.name}"
            )
        idx = dates.get_loc(target)
        if not isinstance(idx, int):
            raise ValueError(f"Ambiguous trading date location for {target}")
        return idx

    @property
    def session_start(self) -> ChronoTime:
        """Return the market open timestamp for this trading day."""
        scheduler = SchedulerManager.get_scheduler()
        idx = self._get_session_idx()
        return ChronoTime(scheduler.schedule["market_open"].iloc[idx])

    def to_session_start(self) -> ChronoTime:
        """Return the market open timestamp for this trading day."""
        return self.session_start

    @property
    def session_end(self) -> ChronoTime:
        """Return the market close timestamp for this trading day."""
        scheduler = SchedulerManager.get_scheduler()
        idx = self._get_session_idx()
        return ChronoTime(scheduler.schedule["market_close"].iloc[idx])

    def to_session_end(self) -> ChronoTime:
        """Return the market close timestamp for this trading day."""
        return self.session_end

    def is_trading(self) -> bool:
        """Return True if this date is a trading day in the active calendar."""
        scheduler = SchedulerManager.get_scheduler()
        self_local = self.tz_convert(scheduler.tz) if self.tzinfo is not None else self
        target = pd.Timestamp(self_local.strftime("%Y-%m-%d"))
        return target in scheduler.schedule.index

    def delta(self, other: Any) -> int:
        """Return the signed trading-day distance between this day and ``other``."""
        other_day = ChronoDay(other) if not isinstance(other, ChronoDay) else other
        return SchedulerManager.get_scheduler().trading_day_delta(self, other_day)

    def trading_times(self, step: str = "1min") -> pd.Series:
        """Return all tradable minute timestamps within this trading day's session."""
        return SchedulerManager.get_scheduler().trading_times(
            start=self.session_start, end=self.session_end, step=step
        )
