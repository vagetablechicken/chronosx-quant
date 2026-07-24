from contextlib import contextmanager
from dataclasses import dataclass
from datetime import tzinfo
from functools import wraps
import os
import threading

import pandas_market_calendars as mcal
import pandas as pd

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

    intervals_count: int
    intervals_memory_bytes: int
    trading_minutes_count: int
    trading_minutes_memory_bytes: int

    @property
    def total_memory_bytes(self) -> int:
        return self.intervals_memory_bytes + self.trading_minutes_memory_bytes


def get_default_calendar_name() -> str:
    return os.getenv("CALENDAR_NAME", DEFAULT_CALENDAR_NAME)


def get_schedule_start() -> pd.Timestamp:
    return pd.Timestamp(os.getenv("SCHEDULE_START", DEFAULT_SCHEDULE_START))


def get_schedule_end() -> pd.Timestamp:
    configured_end = os.getenv("SCHEDULE_END")
    if configured_end:
        return pd.Timestamp(configured_end)
    return pd.Timestamp.now() + pd.DateOffset(years=3)


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
    def get_scheduler():
        if not hasattr(SchedulerManager._storage, "schedule"):
            # SSE: China Exchange (Shanghai, Shenzhen, CFE) are all in the same timezone, so we can use the same calendar for them.
            # CME Globex Crypto
            # other calendars haven't been checked
            SchedulerManager._storage.schedule = StaticMinuteScheduler(
                get_default_calendar_name()
            )
        return SchedulerManager._storage.schedule

    @staticmethod
    def set_scheduler(schedule):
        SchedulerManager._storage.schedule = schedule

    @staticmethod
    @contextmanager
    def use_scheduler(temp_schedule):
        """
        Temporarily switch the active scheduler and restore it after the `with` block.

        Usage:
        with SchedulerManager.use_schedule(MockSchedule()):
            # run test logic
        """
        # 1. Save the previous scheduler state.
        has_old = hasattr(SchedulerManager._storage, "schedule")
        old_schedule = getattr(SchedulerManager._storage, "schedule", None)

        # 2. Install the temporary scheduler.
        SchedulerManager.set_scheduler(temp_schedule)

        try:
            yield
        finally:
            # 3. Restore the previous scheduler state.
            if has_old:
                SchedulerManager.set_scheduler(old_schedule)
            else:
                # If there was no scheduler before, remove the temporary value so
                # the thread-local storage stays clean.
                if hasattr(SchedulerManager._storage, "schedule"):
                    del SchedulerManager._storage.schedule


class SchedulerTemplate:
    def shift(self, time: pd.Timestamp, delta: int, step: str) -> pd.Timestamp: ...
    def trading_times(
        self, start: pd.Timestamp, end: pd.Timestamp, step: str
    ) -> pd.Series: ...
    def trading_day_delta(self, start: pd.Timestamp, end: pd.Timestamp) -> int: ...
    def previous_trading_time(
        self, time: pd.Timestamp, step: str, inclusive=True
    ) -> pd.Timestamp | None: ...
    def next_trading_time(
        self, time: pd.Timestamp, step: str, inclusive=True
    ) -> pd.Timestamp | None: ...

    def is_trading(self, time: pd.Timestamp) -> bool: ...
    def is_trading_day(self, time: pd.Timestamp) -> bool:
        """Check if the time is a trading day, no matter if it's a trading time."""
        ...

    def to_session_start(self, time: pd.Timestamp) -> pd.Timestamp: ...
    def to_session_end(self, time: pd.Timestamp) -> pd.Timestamp: ...

    @property
    def tz(self) -> tzinfo: ...

    @property
    def info(self) -> SchedulerInfo: ...


class StaticMinuteScheduler(SchedulerTemplate):
    """
    Load a fixed schedule window and let it crash if time is not in the schedule.

    For performance, only support 1 minute step, prepare all timeline when init, no more updates
    """

    def __init__(self, calendar_name: str):
        self.calendar = mcal.get_calendar(calendar_name)
        self.schedule = self.calendar.schedule(
            get_schedule_start(),
            get_schedule_end(),
            tz=self.calendar.tz,
        )
        self.session_intervals = pd.IntervalIndex.from_arrays(
            self.schedule["market_open"],
            self.schedule["market_close"],
            closed="left",
        )
        self.intervals = self._build_trading_intervals()
        self.trading_minutes = self._build_trading_minutes()
        self._info = SchedulerInfo(
            intervals_count=len(self.intervals),
            intervals_memory_bytes=int(self.intervals.memory_usage(deep=True)),
            trading_minutes_count=len(self.trading_minutes),
            trading_minutes_memory_bytes=int(
                self.trading_minutes.memory_usage(deep=True)
            ),
        )

    @property
    def tz(self):
        return self.calendar.tz

    @property
    def info(self) -> SchedulerInfo:
        """Return cached size and memory statistics for precomputed indexes."""
        return self._info

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
    def shift(self, time: pd.Timestamp, delta: int, *, step: str) -> pd.Timestamp:
        """
        Shift the time by delta in trading time, i.e. jump to the next trading time if the result is not a trading time.

        Time should be a valid trading time, second and microsecond will be preserved.
        """
        # save second and microsecond
        second = time.second
        microsecond = time.microsecond
        time = time.replace(second=0, microsecond=0)
        # raise an error if time is not a trading time
        time_idx = self.trading_minutes.get_loc(time)
        # raise an error if out of range
        shifted_idx = time_idx + delta
        if shifted_idx < 0 or shifted_idx >= len(self.trading_minutes):
            raise IndexError(
                f"Shift result out of range for {self.calendar.name}: "
                f"time={time}, delta={delta}"
            )
        shifted = self.trading_minutes[shifted_idx]
        # restore second and microsecond
        return shifted.replace(second=second, microsecond=microsecond)

    @require_1min_step
    def trading_times(
        self, start: pd.Timestamp, end: pd.Timestamp, *, step: str
    ) -> pd.Series:
        # [start, end)
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
        start_day = start.normalize().tz_localize(None)
        end_day = end.normalize().tz_localize(None)
        if start_day <= end_day:
            left_idx = self.schedule.index.searchsorted(start_day, side="left")
            right_idx = self.schedule.index.searchsorted(end_day, side="right")
            return right_idx - left_idx

        left_idx = self.schedule.index.searchsorted(end_day, side="left")
        right_idx = self.schedule.index.searchsorted(start_day, side="right")
        return -(right_idx - left_idx)

    @require_1min_step
    def previous_trading_time(
        self, time: pd.Timestamp, *, step: str, inclusive: bool
    ) -> pd.Timestamp | None:
        # inclusive, search right means > time, -1 must be <= time
        # exclusive, search left means >= time, -1 must be < time
        # TODO: binary search is quick, but time may out of range
        idx = (
            self.trading_minutes.searchsorted(
                time, side="right" if inclusive else "left"
            )
            - 1
        )
        return self.trading_minutes[idx] if idx >= 0 else None

    @require_1min_step
    def next_trading_time(
        self, time: pd.Timestamp, *, step: str, inclusive: bool
    ) -> pd.Timestamp | None:
        # inclusive, search left means >= time
        # exclusive, search right means > time
        idx = self.trading_minutes.searchsorted(
            time, side="left" if inclusive else "right"
        )
        return self.trading_minutes[idx] if idx < len(self.trading_minutes) else None

    def is_trading(self, time: pd.Timestamp) -> bool:
        """Check if the time is a trading time."""
        # be careful to exclude break times
        try:
            self.intervals.get_loc(time)
        except KeyError:
            return False
        return True

    def is_trading_day(self, time: pd.Timestamp) -> bool:
        """Check if the date is in trading, no matter if it's a trading time."""
        # trading day may start from previous day, use interval to check
        day_start = time.normalize()
        day_end = day_start + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

        # O(log N) fast overlap check instead of O(N) `self.session_intervals.overlaps().any()`
        # 1. Find the first trading session that ends AFTER the day starts
        close_times = self.schedule["market_close"]
        idx = close_times.searchsorted(day_start, side="right")

        if idx == len(close_times):
            return False

        # 2. Check if this session starts BEFORE the day ends
        return self.schedule["market_open"].iloc[idx] <= day_end

    def _get_session_loc(self, time: pd.Timestamp) -> int:
        """Return the position of the session containing one timestamp."""
        try:
            return self.session_intervals.get_loc(time)
        except KeyError:
            raise ValueError(f"Time {time} is not in trading interval") from None

    def to_session_end(self, time: pd.Timestamp) -> pd.Timestamp:
        """use calendar cuz we may meet early close time before holidays"""
        idx = self._get_session_loc(time)
        return self.schedule["market_close"].iloc[idx]

    def to_session_start(self, time: pd.Timestamp) -> pd.Timestamp:
        idx = self._get_session_loc(time)
        return self.schedule["market_open"].iloc[idx]

    def get_trading_date(self, time: pd.Timestamp) -> pd.Timestamp:
        """Return the trading date of the session containing ``time``."""
        idx = self._get_session_loc(time)
        return self.schedule.index[idx]
