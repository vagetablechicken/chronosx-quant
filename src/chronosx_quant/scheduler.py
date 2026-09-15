from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import tzinfo
from functools import wraps
from typing import Any, Protocol, runtime_checkable

import pandas as pd
import pandas_market_calendars as mcal

# Import custom calendars for registration side effects. Their classes are
# registered into pandas_market_calendars via metaclass hooks when imported, so
# `mcal.get_calendar(...)` can resolve names like `CN_FUTURES_0230`.
from . import calendars as _custom_calendars  # noqa: F401

"""
Scheduler abstractions for trading-calendar queries.

The scheduler implementation is customizable, but the default runtime scheduler is
`StaticMinuteScheduler` because it precomputes a fixed timeline and is optimized
for performance.
"""

DEFAULT_CALENDAR_NAME = "SSE"
DEFAULT_SCHEDULE_START = "2022-01-01"


@dataclass(frozen=True)
class SchedulerInfo:
    """Size and memory statistics for a precomputed scheduler."""

    session_intervals_count: int
    session_intervals_memory_bytes: int
    intervals_count: int
    intervals_memory_bytes: int
    trading_minutes_count: int
    trading_minutes_memory_bytes: int
    total_memory_bytes: int


def get_default_calendar_name() -> str:
    return os.getenv("CALENDAR_NAME", DEFAULT_CALENDAR_NAME)


def get_schedule_start() -> pd.Timestamp:
    res = pd.Timestamp(os.getenv("SCHEDULE_START", DEFAULT_SCHEDULE_START))
    assert isinstance(res, pd.Timestamp)
    return res


def get_schedule_end() -> pd.Timestamp:
    configured_end = os.getenv("SCHEDULE_END")
    if configured_end:
        res = pd.Timestamp(configured_end)
    else:
        res = pd.Timestamp.now() + pd.DateOffset(years=3)
    assert isinstance(res, pd.Timestamp)
    return res


def require_1min_step(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        step = kwargs.get("step")
        if step is not None and step != "1min":
            raise ValueError(
                f"Performance Lock: '{func.__name__}' only supports step='1min'."
            )

        return func(*args, **kwargs)

    return wrapper


class SchedulerManager:
    _storage = threading.local()

    @staticmethod
    def create_scheduler(
        calendar_name: str | None = None,
        *,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
    ) -> Scheduler:
        """Create a new StaticMinuteScheduler with customized calendar name and schedule window."""
        return StaticMinuteScheduler(
            calendar_name or get_default_calendar_name(),
            start=start,
            end=end,
        )

    @staticmethod
    def get_scheduler() -> Scheduler:
        if not hasattr(SchedulerManager._storage, "schedule"):
            # SSE: China Exchange (Shanghai, Shenzhen, CFE) are all in the same timezone, so we can use the same calendar for them.
            # CME Globex Crypto
            # other calendars haven't been checked
            SchedulerManager._storage.schedule = SchedulerManager.create_scheduler()
        return SchedulerManager._storage.schedule

    @staticmethod
    def set_scheduler(schedule: Scheduler) -> None:
        SchedulerManager._storage.schedule = schedule

    @staticmethod
    @contextmanager
    def use_scheduler(temp_schedule: Scheduler):
        """
        Temporarily switch the active scheduler and restore it after the `with` block.

        Usage:
        with SchedulerManager.use_scheduler(MockSchedule()):
            # run test logic
        """
        # 1. Save the previous scheduler state.
        has_old = hasattr(SchedulerManager._storage, "schedule")
        old_schedule: Scheduler | None = getattr(
            SchedulerManager._storage, "schedule", None
        )

        # 2. Install the temporary scheduler.
        SchedulerManager.set_scheduler(temp_schedule)

        try:
            yield temp_schedule
        finally:
            # 3. Restore the previous scheduler state.
            if has_old and old_schedule is not None:
                SchedulerManager.set_scheduler(old_schedule)
            else:
                # If there was no scheduler before, remove the temporary value so
                # the thread-local storage stays clean.
                if hasattr(SchedulerManager._storage, "schedule"):
                    del SchedulerManager._storage.schedule


@contextmanager
def use_calendar(
    calendar_name: str,
    *,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
):
    """Temporarily use a calendar without manually creating a scheduler.

    The previous scheduler is restored when the context exits. ``start`` and
    ``end`` define the precomputed schedule window.
    """
    scheduler = StaticMinuteScheduler(calendar_name, start=start, end=end)
    with SchedulerManager.use_scheduler(scheduler):
        yield scheduler


@runtime_checkable
class Scheduler(Protocol):
    calendar: Any
    schedule: pd.DataFrame

    def shift(
        self,
        time: pd.Timestamp,
        delta: int,
        *,
        step: str = "1min",
    ) -> pd.Timestamp: ...
    def shift_trading_day(self, day: Any, delta: int) -> pd.Timestamp: ...
    def trading_times(
        self, start: pd.Timestamp, end: pd.Timestamp, *, step: str = "1min"
    ) -> pd.Series: ...
    def trading_day_delta(self, start: pd.Timestamp, end: pd.Timestamp) -> int: ...
    def previous_trading_time(
        self, time: pd.Timestamp, *, step: str = "1min", inclusive: bool = True
    ) -> pd.Timestamp | None: ...
    def next_trading_time(
        self, time: pd.Timestamp, *, step: str = "1min", inclusive: bool = True
    ) -> pd.Timestamp | None: ...

    def previous_trading_day(
        self, day: pd.Timestamp, *, inclusive: bool = True
    ) -> pd.Timestamp | None: ...
    def next_trading_day(
        self, day: pd.Timestamp, *, inclusive: bool = True
    ) -> pd.Timestamp | None: ...

    def is_trading(self, time: pd.Timestamp) -> bool: ...
    def is_trading_day(self, time: pd.Timestamp) -> bool:
        """Check if the time is a trading day, no matter if it's a trading time."""
        ...

    def get_trading_date(self, time: pd.Timestamp) -> pd.Timestamp: ...
    def to_session_start(self, time: pd.Timestamp) -> pd.Timestamp: ...
    def to_session_end(self, time: pd.Timestamp) -> pd.Timestamp: ...

    @property
    def tz(self) -> tzinfo: ...

    @property
    def info(self) -> SchedulerInfo: ...


SchedulerTemplate = Scheduler


class StaticMinuteScheduler(Scheduler):
    """
    Load a fixed schedule window and let it crash if time is not in the schedule.

    For performance, only support 1 minute step, prepare all timeline when init, no more updates
    """

    def __init__(
        self,
        calendar_name: str,
        *,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
    ):
        self.calendar = mcal.get_calendar(calendar_name)

        def schedule_bound(
            value: str | pd.Timestamp | None, default: pd.Timestamp
        ) -> pd.Timestamp:
            bound = default if value is None else pd.Timestamp(value)
            assert isinstance(bound, pd.Timestamp)
            if bound.tzinfo is not None:
                converted = bound.tz_convert(self.calendar.tz).tz_localize(None)
                assert isinstance(converted, pd.Timestamp)
                bound = converted
            return bound

        schedule_start = schedule_bound(start, get_schedule_start())
        schedule_end = schedule_bound(end, get_schedule_end())
        if schedule_start > schedule_end:
            raise ValueError(
                f"Schedule start must not be after end: "
                f"start={schedule_start}, end={schedule_end}"
            )
        self.schedule = self.calendar.schedule(
            schedule_start,
            schedule_end,
            tz=self.calendar.tz,
        )
        self.session_intervals = pd.IntervalIndex.from_arrays(
            self.schedule["market_open"],
            self.schedule["market_close"],
            closed="left",
        )
        # IntervalIndex.get_loc uses pandas' generic interval lookup machinery.
        # Sessions are already sorted and non-overlapping, so keep zero-copy
        # nanosecond views for a much cheaper binary search on this hot path.
        self._session_opens: pd.DatetimeIndex = pd.DatetimeIndex(
            self.schedule["market_open"]
        )
        self._session_closes: pd.DatetimeIndex = pd.DatetimeIndex(
            self.schedule["market_close"]
        )
        self._session_opens_ns = (
            self._session_opens.tz_convert("UTC")
            .tz_localize(None)
            .astype("datetime64[ns]")
            .astype("int64")
            .to_numpy()
        )
        self._session_closes_ns = (
            self._session_closes.tz_convert("UTC")
            .tz_localize(None)
            .astype("datetime64[ns]")
            .astype("int64")
            .to_numpy()
        )

        self.intervals = self._build_trading_intervals()
        # Trading intervals are sorted and non-overlapping. Keep zero-copy
        # nanosecond views so is_trading() can use a direct binary search
        # instead of pandas' generic IntervalIndex lookup machinery.
        self._interval_starts_ns = (
            pd.DatetimeIndex(self.intervals.left)
            .tz_convert("UTC")
            .tz_localize(None)
            .astype("datetime64[ns]")
            .astype("int64")
            .to_numpy()
        )
        self._interval_ends_ns = (
            pd.DatetimeIndex(self.intervals.right)
            .tz_convert("UTC")
            .tz_localize(None)
            .astype("datetime64[ns]")
            .astype("int64")
            .to_numpy()
        )
        self.trading_minutes = self._build_trading_minutes()

    @property
    def tz(self):
        return self.calendar.tz

    @property
    def info(self) -> SchedulerInfo:
        """Compute size and memory statistics once, on first access."""
        if not hasattr(self, "_cached_info"):
            session_intervals_memory_bytes = int(
                self.session_intervals.memory_usage(deep=True)
            )
            intervals_memory_bytes = self.intervals.memory_usage(deep=True)
            trading_minutes_memory_bytes = self.trading_minutes.memory_usage(deep=True)
            self._cached_info = SchedulerInfo(
                session_intervals_count=len(self.session_intervals),
                session_intervals_memory_bytes=session_intervals_memory_bytes,
                intervals_count=len(self.intervals),
                intervals_memory_bytes=intervals_memory_bytes,
                trading_minutes_count=len(self.trading_minutes),
                trading_minutes_memory_bytes=trading_minutes_memory_bytes,
                total_memory_bytes=(
                    intervals_memory_bytes
                    + trading_minutes_memory_bytes
                    + (
                        0
                        if self.session_intervals is self.intervals
                        else session_intervals_memory_bytes
                    )
                ),
            )
        return self._cached_info

    def __repr__(self):
        return f"StaticMinuteScheduler({self.calendar.name}, end={self.schedule.index[-1]})"

    def _build_trading_intervals(self) -> pd.IntervalIndex:
        """
        Build intraday trading intervals from any regular open/close event columns.

        The schedule columns are already ordered by market time, so we can walk each
        row, pair every opening event with the next closing event, and support any
        number of fixed breaks without hard-coding specific column names.
        """
        event_columns = [
            column
            for column in self.schedule.columns
            if column in self.calendar.open_close_map
        ]
        if event_columns == ["market_open", "market_close"]:
            return self.session_intervals

        interval_starts = []
        interval_ends = []

        for _, trading_day in self.schedule[event_columns].iterrows():
            start_time = None

            for column, event_time in trading_day.items():
                if pd.isna(event_time):
                    continue

                if self.calendar.open_close_map[column]:
                    start_time = event_time
                    continue

                if start_time is None:
                    raise ValueError(
                        f"Schedule for {self.calendar.name} closes at {column} "
                        "before any opening event."
                    )

                interval_starts.append(start_time)
                interval_ends.append(event_time)
                start_time = None

            if start_time is not None:
                raise ValueError(
                    f"Schedule for {self.calendar.name} has an unmatched opening event."
                )

        return pd.IntervalIndex.from_arrays(
            pd.DatetimeIndex(interval_starts),
            pd.DatetimeIndex(interval_ends),
            closed="left",
        )

    def _build_trading_minutes(self) -> pd.DatetimeIndex:
        """
        Expand our precomputed trading intervals into one flat minute timeline.

        Upstream `mcal.date_range(schedule, frequency="1min")` works for simpler
        calendars, but it does not understand the extra open/close events we add
        for Chronosx multi-break calendars. Instead of asking the upstream helper
        to infer valid trading minutes from `schedule`, we already know the exact
        valid intervals in `self.intervals`, so we expand each interval ourselves.

        Concretely, for every interval like [09:00, 10:15), we create:
        09:00, 09:01, ..., 10:14
        and then append all interval minute ranges in chronological order.

        The final flat minute index is the source of truth for:
        - `shift`
        - `trading_times`
        - `previous_trading_time`
        - `next_trading_time`

        Because break minutes are never materialized here, those APIs naturally
        skip over breaks and night-session gaps.
        """
        minute_ranges = []
        one_minute = pd.Timedelta("1min")

        for interval in self.intervals:
            # Intervals are left-closed/right-open, so [09:00, 10:15) should
            # include 10:14 but exclude 10:15.
            interval_end = interval.right - one_minute
            if interval_end < interval.left:
                continue
            minute_ranges.append(
                pd.date_range(interval.left, interval_end, freq="1min")
            )

        if not minute_ranges:
            return pd.DatetimeIndex([], tz=self.calendar.tz)

        # Append every per-interval minute range into one monotonically
        # increasing DatetimeIndex for fast binary search and index lookup.
        trading_minutes = minute_ranges[0]
        for minute_range in minute_ranges[1:]:
            # `DatetimeIndex.append(...)` concatenates index values here, more
            # like `list.extend(...)` than `list.append(...)`.
            trading_minutes = trading_minutes.append(minute_range)

        return trading_minutes

    @require_1min_step
    def shift(
        self,
        time: pd.Timestamp,
        delta: int,
        *,
        step: str = "1min",
    ) -> pd.Timestamp:
        """Shift time forward or backward by trading minutes along the active timeline.

        Parameters
        ----------
        time : pd.Timestamp
            Reference timestamp. Must be a valid trading minute.
        delta : int
            Number of minutes to shift. Positive shifts into the future, negative into the past.
        step : {"1min"}, default "1min"
            Unit of progression. Only "1min" is supported.
        """
        time = self._to_market_time(time)
        second = time.second
        microsecond = time.microsecond
        time_clean = time.replace(second=0, microsecond=0)
        try:
            loc = self.trading_minutes.get_loc(time_clean)
        except KeyError:
            raise ValueError(
                f"Time {time} is not a valid trading minute for {self.calendar.name}"
            ) from None

        if not isinstance(loc, int):
            raise ValueError(f"Ambiguous time location for {time_clean}")

        time_idx = loc
        shifted_idx = time_idx + delta
        if shifted_idx < 0 or shifted_idx >= len(self.trading_minutes):
            raise IndexError(
                f"Shift result out of range for {self.calendar.name}: "
                f"time={time}, delta={delta}, step={step}"
            )
        shifted = self.trading_minutes[shifted_idx]
        assert isinstance(shifted, pd.Timestamp)
        return shifted.replace(second=second, microsecond=microsecond)

    def _to_market_time(self, time: pd.Timestamp) -> pd.Timestamp:
        """
        Convert timestamp to calendar's market timezone (`self.tz`).

        Rules:
        - Naive inputs are interpreted as market wall-clock time (`tz_localize(self.tz)`).
        - Aware inputs are converted to market timezone (`tz_convert(self.tz)`).
        """
        if not isinstance(time, pd.Timestamp):
            time = pd.Timestamp(time)
        if time.tzinfo is None:
            return time.tz_localize(self.tz)
        if time.tz != self.tz:
            return time.tz_convert(self.tz)
        return time

    def _to_trading_date(self, day: pd.Timestamp) -> pd.Timestamp:
        """Convert timestamp to scheduler timezone, strip timezone, and normalize to 00:00."""
        if not isinstance(day, pd.Timestamp):
            day = pd.Timestamp(day)
        if day.tzinfo is not None:
            day = day.tz_convert(self.tz).tz_localize(None)
        return day.normalize()

    def shift_trading_day(self, day: pd.Timestamp, delta: int) -> pd.Timestamp:
        """Shift a trading day forward or backward by trading days on the calendar.

        Parameters
        ----------
        day : pd.Timestamp
            Reference day at 00:00 (e.g. ``ChronoDay``).
        delta : int
            Number of trading days to shift. Positive into the future, negative into the past.
        """
        day_local = day.tz_convert(self.tz) if day.tzinfo is not None else day
        if (
            day_local.hour,
            day_local.minute,
            day_local.second,
            day_local.microsecond,
        ) != (0, 0, 0, 0):
            raise ValueError(f"Day {day} must be a timestamp at 00:00")

        dates = self.schedule.index
        target = self._to_trading_date(day)

        if target in dates:
            loc = dates.get_loc(target)
            if not isinstance(loc, int):
                raise ValueError(f"Ambiguous trading date location for {target}")
            base_idx = loc
            target_idx = base_idx + delta
        else:
            # `day` is on a non-trading calendar date (weekend or holiday)
            if delta < 0:
                preceding_idx = int(dates.searchsorted(target, side="right")) - 1
                if preceding_idx < 0:
                    raise IndexError(
                        f"Shift result out of range for {self.calendar.name}: "
                        f"day={day}, delta={delta}"
                    )
                target_idx = preceding_idx + (delta + 1)
            elif delta > 0:
                succeeding_idx = int(dates.searchsorted(target, side="left"))
                if succeeding_idx >= len(dates):
                    raise IndexError(
                        f"Shift result out of range for {self.calendar.name}: "
                        f"day={day}, delta={delta}"
                    )
                target_idx = succeeding_idx + (delta - 1)
            else:  # delta == 0
                raise ValueError(
                    f"Date {day} is not a valid trading day for {self.calendar.name}"
                )

        if target_idx < 0 or target_idx >= len(dates):
            raise IndexError(
                f"Shift result out of range for {self.calendar.name}: "
                f"day={day}, delta={delta}"
            )

        return dates[target_idx]

    def previous_trading_day(
        self, day: pd.Timestamp, *, inclusive: bool = True
    ) -> pd.Timestamp | None:
        """Return the nearest trading day at or before ``day``."""
        dates = self.schedule.index
        target = self._to_trading_date(day)
        idx = int(dates.searchsorted(target, side="right" if inclusive else "left") - 1)
        if idx < 0:
            return None
        res = dates[idx]
        assert isinstance(res, pd.Timestamp)
        return res

    def next_trading_day(
        self, day: pd.Timestamp, *, inclusive: bool = True
    ) -> pd.Timestamp | None:
        """Return the nearest trading day at or after ``day``."""
        dates = self.schedule.index
        target = self._to_trading_date(day)
        idx = int(dates.searchsorted(target, side="left" if inclusive else "right"))
        if idx >= len(dates):
            return None
        res = dates[idx]
        assert isinstance(res, pd.Timestamp)
        return res

    @require_1min_step
    def trading_times(
        self, start: pd.Timestamp, end: pd.Timestamp, *, step: str = "1min"
    ) -> pd.Series:
        # [start, end)
        start = self._to_market_time(start)
        end = self._to_market_time(end)
        left_idx = self.trading_minutes.searchsorted(start, side="left")
        right_idx = self.trading_minutes.searchsorted(end, side="left")
        return self.trading_minutes[left_idx:right_idx].to_series()

    def trading_day_delta(self, start: pd.Timestamp, end: pd.Timestamp) -> int:
        """
        Return the signed trading-day distance between `start` and `end`.

        This is a coarse day-level statistic, not an exact measure of trading-time
        duration. It only looks at calendar dates in the scheduler timezone, so
        intraday time does not matter and it does not care whether the timestamp
        covers a full trading session.

        Counting uses trading-day dates in a left-closed, right-closed interval:
        [start_day, end_day]. In practice both endpoints are included if those
        dates are trading days; if an endpoint falls on a non-trading date, that
        date contributes 0. Order is preserved: forward ranges are positive and
        backward ranges are negative.

        Examples:
        - same trading day -> 1
        - Tuesday to Thursday across three trading dates -> 3
        - Monday back to previous Friday -> -2
        - same non-trading day -> 0
        """
        start_day = self._to_trading_date(start)
        end_day = self._to_trading_date(end)
        if start_day <= end_day:
            left_idx = self.schedule.index.searchsorted(start_day, side="left")
            right_idx = self.schedule.index.searchsorted(end_day, side="right")
            return int(right_idx - left_idx)

        left_idx = self.schedule.index.searchsorted(end_day, side="left")
        right_idx = self.schedule.index.searchsorted(start_day, side="right")
        return -int(right_idx - left_idx)

    @require_1min_step
    def previous_trading_time(
        self, time: pd.Timestamp, *, step: str = "1min", inclusive: bool = True
    ) -> pd.Timestamp | None:
        # inclusive, search right means > time, -1 must be <= time
        # exclusive, search left means >= time, -1 must be < time
        # NOTE: binary search is quick, but time may out of range
        time = self._to_market_time(time)
        idx = int(
            self.trading_minutes.searchsorted(
                time, side="right" if inclusive else "left"
            )
            - 1
        )
        if idx < 0:
            return None
        res = self.trading_minutes[idx]
        assert isinstance(res, pd.Timestamp)
        return res

    @require_1min_step
    def next_trading_time(
        self, time: pd.Timestamp, *, step: str = "1min", inclusive: bool = True
    ) -> pd.Timestamp | None:
        # inclusive, search left means >= time
        # exclusive, search right means > time
        time = self._to_market_time(time)
        idx = int(
            self.trading_minutes.searchsorted(
                time, side="left" if inclusive else "right"
            )
        )
        if idx >= len(self.trading_minutes):
            return None
        res = self.trading_minutes[idx]
        assert isinstance(res, pd.Timestamp)
        return res

    def is_trading(self, time: pd.Timestamp) -> bool:
        """Check if the time is a trading time."""
        time = self._to_market_time(time)
        time_ns = time.value
        # Find the last interval whose left edge is <= time. Intervals are
        # left-closed/right-open, so the right edge itself is not tradable.
        idx = int(self._interval_starts_ns.searchsorted(time_ns, side="right")) - 1
        return bool(idx >= 0 and time_ns < self._interval_ends_ns[idx])

    # TODO: it should be is_active_trading_date, rename it
    def is_trading_day(self, time: pd.Timestamp) -> bool:
        """Check if the date is in trading, no matter if it's a trading time."""
        time = self._to_market_time(time)

        # trading day may start from previous day, use interval to check
        day_start = time.normalize()
        day_end = day_start + pd.Timedelta(days=1) - pd.Timedelta("1ns")

        # O(log N) fast overlap check using precomputed nanosecond views
        # 1. Find the first trading session that ends AFTER the day starts
        idx = int(self._session_closes_ns.searchsorted(day_start.value, side="right"))

        if idx == len(self._session_closes_ns):
            return False

        # 2. Check if this session starts BEFORE the day ends
        return bool(self._session_opens_ns[idx] <= day_end.value)

    def _get_session_loc(self, time: pd.Timestamp) -> int:
        """Return the position of the session containing one timestamp."""
        time = self._to_market_time(time)
        time_ns = time.value
        # `side="right"` finds the first open > time; -1 gives the last open <= time.
        idx = int(self._session_opens_ns.searchsorted(time_ns, side="right")) - 1
        if idx < 0 or time_ns >= self._session_closes_ns[idx]:
            raise ValueError(f"Time {time} is not in trading interval")
        return idx

    def to_session_end(self, time: pd.Timestamp) -> pd.Timestamp:
        """use calendar cuz we may meet early close time before holidays"""
        idx = self._get_session_loc(time)
        return self._session_closes[idx]

    def to_session_start(self, time: pd.Timestamp) -> pd.Timestamp:
        idx = self._get_session_loc(time)
        return self._session_opens[idx]

    def get_trading_date(self, time: pd.Timestamp) -> pd.Timestamp:
        """Return the trading date of the session containing ``time``."""
        idx = self._get_session_loc(time)
        return self.schedule.index[idx]
