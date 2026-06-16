import pandas as pd
import pytest

from chronosx_quant.scheduler import SchedulerManager
from chronosx_quant.time import ChronoTime
from tests.helpers import get_scheduler


@pytest.mark.parametrize(
    ("calendar_name", "alias", "last_trading_minute", "first_non_trading_minute"),
    [
        (
            "CN_FUTURES_0230",
            "AG.SHF",
            "2026-03-11 02:29:00",
            "2026-03-11 02:30:00",
        ),
        (
            "CN_FUTURES_0100",
            "CU.SHF",
            "2026-03-11 00:59:00",
            "2026-03-11 01:00:00",
        ),
        (
            "CN_FUTURES_2300",
            "DCE",
            "2026-03-10 22:59:00",
            "2026-03-10 23:00:00",
        ),
    ],
)
def test_builtin_china_futures_calendar_aliases_and_close_boundaries(
    calendar_name, alias, last_trading_minute, first_non_trading_minute
):
    scheduler = get_scheduler(calendar_name)
    alias_scheduler = get_scheduler(alias)

    assert type(alias_scheduler.calendar) is type(scheduler.calendar)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert not scheduler.is_trading(ts("2026-03-09 20:59:00"))
    assert scheduler.is_trading(ts("2026-03-09 21:00:00"))
    assert not scheduler.is_trading(ts(first_non_trading_minute))
    assert scheduler.is_trading(ts(last_trading_minute))
    assert scheduler.is_trading(ts("2026-03-10 09:30:00"))
    assert not scheduler.is_trading(ts("2026-03-10 10:20:00"))
    assert scheduler.is_trading(ts("2026-03-10 10:30:00"))
    assert not scheduler.is_trading(ts("2026-03-10 12:00:00"))
    assert scheduler.is_trading(ts("2026-03-10 13:30:00"))
    assert scheduler.is_trading(ts("2026-03-10 14:59:00"))
    assert not scheduler.is_trading(ts("2026-03-10 15:00:00"))


@pytest.mark.parametrize(
    (
        "calendar_name",
        "before_break",
        "after_break",
        "night_last",
        "next_session_first",
    ),
    [
        (
            "CN_FUTURES_0230",
            "2026-03-10 10:14:00",
            "2026-03-10 10:30:00",
            "2026-03-11 02:29:00",
            "2026-03-11 09:00:00",
        ),
        (
            "CN_FUTURES_0100",
            "2026-03-10 10:14:00",
            "2026-03-10 10:30:00",
            "2026-03-11 00:59:00",
            "2026-03-11 09:00:00",
        ),
        (
            "CN_FUTURES_2300",
            "2026-03-10 10:14:00",
            "2026-03-10 10:30:00",
            "2026-03-10 22:59:00",
            "2026-03-11 09:00:00",
        ),
    ],
)
def test_builtin_china_futures_calendar_shift(
    calendar_name, before_break, after_break, night_last, next_session_first
):
    scheduler = get_scheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.shift(ts(before_break), 1, step="1min") == ts(after_break)
    assert scheduler.shift(ts(after_break), -1, step="1min") == ts(before_break)
    assert scheduler.shift(ts(night_last), 1, step="1min") == ts(next_session_first)

    with SchedulerManager.use_scheduler(scheduler):
        assert ChronoTime(before_break).shift(1).isoformat() == ts(after_break).isoformat()
        assert ChronoTime(night_last).shift(1).isoformat() == ts(next_session_first).isoformat()


@pytest.mark.parametrize(
    (
        "calendar_name",
        "trading_time",
        "expected_session_start",
        "expected_session_end",
    ),
    [
        (
            "CN_FUTURES_0230",
            "2026-03-10 10:00:00",
            "2026-03-09 21:00:00",
            "2026-03-10 15:00:00",
        ),
        (
            "CN_FUTURES_0100",
            "2026-03-10 10:00:00",
            "2026-03-09 21:00:00",
            "2026-03-10 15:00:00",
        ),
        (
            "CN_FUTURES_2300",
            "2026-03-10 10:00:00",
            "2026-03-09 21:00:00",
            "2026-03-10 15:00:00",
        ),
    ],
)
def test_builtin_china_futures_calendar_session_boundaries(
    calendar_name, trading_time, expected_session_start, expected_session_end
):
    scheduler = get_scheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.to_session_start(ts(trading_time)) == ts(expected_session_start)
    assert scheduler.to_session_end(ts(trading_time)) == ts(expected_session_end)


@pytest.mark.parametrize(
    (
        "calendar_name",
        "day_start",
        "day_end",
        "day_expected_len",
        "night_start",
        "night_end",
        "night_expected_len",
    ),
    [
        (
            "CN_FUTURES_0230",
            "2026-03-10 10:14:00",
            "2026-03-10 10:31:00",
            2,
            "2026-03-10 22:58:00",
            "2026-03-11 02:31:00",
            212,
        ),
        (
            "CN_FUTURES_0100",
            "2026-03-10 10:14:00",
            "2026-03-10 10:31:00",
            2,
            "2026-03-10 22:58:00",
            "2026-03-11 01:01:00",
            122,
        ),
        (
            "CN_FUTURES_2300",
            "2026-03-10 10:14:00",
            "2026-03-10 10:31:00",
            2,
            "2026-03-10 22:58:00",
            "2026-03-10 23:01:00",
            2,
        ),
    ],
)
def test_builtin_china_futures_calendar_trading_times(
    calendar_name,
    day_start,
    day_end,
    day_expected_len,
    night_start,
    night_end,
    night_expected_len,
):
    scheduler = get_scheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    day_times = scheduler.trading_times(ts(day_start), ts(day_end), step="1min")
    assert len(day_times) == day_expected_len
    assert day_times.iloc[0] == ts("2026-03-10 10:14:00")
    assert day_times.iloc[-1] == ts("2026-03-10 10:30:00")

    night_times = scheduler.trading_times(ts(night_start), ts(night_end), step="1min")
    assert len(night_times) == night_expected_len
    assert night_times.iloc[0] == ts(night_start)
    assert night_times.iloc[-1] == scheduler.shift(
        ts(night_start), night_expected_len - 1, step="1min"
    )

    with SchedulerManager.use_scheduler(scheduler):
        chrono_day_times = ChronoTime(day_start).trading_times(day_end)
        assert len(chrono_day_times) == day_expected_len
        assert chrono_day_times.iloc[0].isoformat() == ts("2026-03-10 10:14:00").isoformat()
        assert chrono_day_times.iloc[-1].isoformat() == ts("2026-03-10 10:30:00").isoformat()


@pytest.mark.parametrize(
    (
        "calendar_name",
        "break_time",
        "prev_expected",
        "next_expected",
        "trading_time",
        "exclusive_prev_expected",
        "exclusive_next_expected",
        "after_close_time",
        "after_close_prev_expected",
        "after_close_next_expected",
    ),
    [
        (
            "CN_FUTURES_0230",
            "2026-03-10 10:20:00",
            "2026-03-10 10:14:00",
            "2026-03-10 10:30:00",
            "2026-03-10 21:00:00",
            "2026-03-10 14:59:00",
            "2026-03-10 21:01:00",
            "2026-03-11 02:30:00",
            "2026-03-11 02:29:00",
            "2026-03-11 09:00:00",
        ),
        (
            "CN_FUTURES_0100",
            "2026-03-10 10:20:00",
            "2026-03-10 10:14:00",
            "2026-03-10 10:30:00",
            "2026-03-10 21:00:00",
            "2026-03-10 14:59:00",
            "2026-03-10 21:01:00",
            "2026-03-11 01:00:00",
            "2026-03-11 00:59:00",
            "2026-03-11 09:00:00",
        ),
        (
            "CN_FUTURES_2300",
            "2026-03-10 10:20:00",
            "2026-03-10 10:14:00",
            "2026-03-10 10:30:00",
            "2026-03-10 21:00:00",
            "2026-03-10 14:59:00",
            "2026-03-10 21:01:00",
            "2026-03-10 23:00:00",
            "2026-03-10 22:59:00",
            "2026-03-11 09:00:00",
        ),
    ],
)
def test_builtin_china_futures_calendar_previous_and_next_trading_time(
    calendar_name,
    break_time,
    prev_expected,
    next_expected,
    trading_time,
    exclusive_prev_expected,
    exclusive_next_expected,
    after_close_time,
    after_close_prev_expected,
    after_close_next_expected,
):
    scheduler = get_scheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.previous_trading_time(
        ts(break_time), step="1min", inclusive=True
    ) == ts(prev_expected)
    assert scheduler.next_trading_time(
        ts(break_time), step="1min", inclusive=True
    ) == ts(next_expected)
    assert scheduler.previous_trading_time(
        ts(trading_time), step="1min", inclusive=False
    ) == ts(exclusive_prev_expected)
    assert scheduler.next_trading_time(
        ts(trading_time), step="1min", inclusive=False
    ) == ts(exclusive_next_expected)
    assert scheduler.previous_trading_time(
        ts(after_close_time), step="1min", inclusive=True
    ) == ts(after_close_prev_expected)
    assert scheduler.next_trading_time(
        ts(after_close_time), step="1min", inclusive=True
    ) == ts(after_close_next_expected)

    with SchedulerManager.use_scheduler(scheduler):
        assert ChronoTime(break_time).previous_trading_time().isoformat() == ts(prev_expected).isoformat()
        assert ChronoTime(break_time).next_trading_time().isoformat() == ts(next_expected).isoformat()
        assert (
            ChronoTime(trading_time).previous_trading_time(inclusive=False).isoformat()
            == ts(exclusive_prev_expected).isoformat()
        )
        assert (
            ChronoTime(trading_time).next_trading_time(inclusive=False).isoformat()
            == ts(exclusive_next_expected).isoformat()
        )


@pytest.mark.parametrize(
    (
        "calendar_name",
        "friday_open",
        "saturday_break_start",
        "saturday_last_trading_minute",
        "sunday_open",
        "monday_daytime",
    ),
    [
        (
            "CN_FUTURES_0230",
            "2026-03-06 21:00:00",
            "2026-03-07 02:30:00",
            "2026-03-07 02:29:00",
            "2026-03-08 21:00:00",
            "2026-03-09 10:00:00",
        ),
        (
            "CN_FUTURES_0100",
            "2026-03-06 21:00:00",
            "2026-03-07 01:00:00",
            "2026-03-07 00:59:00",
            "2026-03-08 21:00:00",
            "2026-03-09 10:00:00",
        ),
        (
            "CN_FUTURES_2300",
            "2026-03-06 21:00:00",
            "2026-03-06 23:00:00",
            "2026-03-06 22:59:00",
            "2026-03-08 21:00:00",
            "2026-03-09 10:00:00",
        ),
    ],
)
def test_builtin_china_futures_calendar_monday_session_comes_from_friday_night(
    calendar_name,
    friday_open,
    saturday_break_start,
    saturday_last_trading_minute,
    sunday_open,
    monday_daytime,
):
    scheduler = get_scheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.is_trading(ts(friday_open))
    assert scheduler.to_session_end(ts(friday_open)) == ts("2026-03-09 15:00:00")
    assert scheduler.to_session_start(ts(monday_daytime)) == ts(friday_open)
    assert scheduler.previous_trading_time(
        ts("2026-03-09 09:00:00"), step="1min", inclusive=False
    ) == ts(saturday_last_trading_minute)
    assert not scheduler.is_trading(ts(saturday_break_start))
    assert not scheduler.is_trading(ts(sunday_open))
