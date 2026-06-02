from datetime import time

import pandas as pd
import pytest
from pandas_market_calendars.market_calendar import MarketCalendar

from chronosx_quant.scheduler import SchedulerManager, StaticMinuteScheduler
from chronosx_quant.time import ChronoTime


def test_init():
    StaticMinuteScheduler("SSE")
    StaticMinuteScheduler("CME Globex Crypto")
    StaticMinuteScheduler("CN_FUTURES_0230")
    StaticMinuteScheduler("CN_FUTURES_0100")
    StaticMinuteScheduler("CN_FUTURES_2300")


class ThreeBreakCalendar(MarketCalendar):
    name = "THREE_BREAK"
    tz = "Asia/Shanghai"
    regular_market_times = {
        "market_open": ((None, time(9, 0)),),
        "break_start_1": ((None, time(10, 0)),),
        "break_end_1": ((None, time(10, 15)),),
        "break_start_2": ((None, time(11, 30)),),
        "break_end_2": ((None, time(13, 0)),),
        "break_start_3": ((None, time(14, 30)),),
        "break_end_3": ((None, time(14, 45)),),
        "market_close": ((None, time(16, 0)),),
    }
    open_close_map = {
        "market_open": True,
        "break_start_1": False,
        "break_end_1": True,
        "break_start_2": False,
        "break_end_2": True,
        "break_start_3": False,
        "break_end_3": True,
        "market_close": False,
    }

    @property
    def regular_holidays(self):
        return None

    @property
    def adhoc_holidays(self):
        return []


def test_multi_break_calendar_support(monkeypatch):
    calendar = ThreeBreakCalendar()

    def ts(value):
        return pd.Timestamp(value, tz=calendar.tz)

    def fake_get_calendar(name):
        assert name == "THREE_BREAK"
        return calendar

    monkeypatch.setattr("chronosx_quant.scheduler.mcal.get_calendar", fake_get_calendar)

    scheduler = StaticMinuteScheduler("THREE_BREAK")

    assert len(scheduler.intervals) == 4 * len(scheduler.schedule)
    assert scheduler.is_trading(ts("2026-03-10 09:30:00"))
    assert not scheduler.is_trading(ts("2026-03-10 10:05:00"))
    assert scheduler.is_trading(ts("2026-03-10 10:20:00"))
    assert not scheduler.is_trading(ts("2026-03-10 12:00:00"))
    assert scheduler.is_trading(ts("2026-03-10 15:00:00"))


@pytest.mark.parametrize(
    ("calendar_name", "alias", "last_trading_minute", "first_non_trading_minute"),
    [
        (
            "CN_FUTURES_0230",
            "SC.INE AG.SHF",
            "2026-03-11 02:29:00",
            "2026-03-11 02:30:00",
        ),
        (
            "CN_FUTURES_0100",
            "BC.INE CU.SHF",
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
    scheduler = StaticMinuteScheduler(calendar_name)
    alias_scheduler = StaticMinuteScheduler(alias)

    assert type(alias_scheduler.calendar) is type(scheduler.calendar)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    # A China futures trading day starts from the previous evening session.
    assert not scheduler.is_trading(ts("2026-03-09 20:59:00"))
    assert scheduler.is_trading(ts("2026-03-09 21:00:00"))
    assert not scheduler.is_trading(ts(first_non_trading_minute))
    assert scheduler.is_trading(ts(last_trading_minute))

    # Shared daytime breaks should stay non-trading across all three calendars.
    assert scheduler.is_trading(ts("2026-03-10 09:30:00"))
    assert not scheduler.is_trading(ts("2026-03-10 10:20:00"))
    assert scheduler.is_trading(ts("2026-03-10 10:30:00"))
    assert not scheduler.is_trading(ts("2026-03-10 12:00:00"))
    assert scheduler.is_trading(ts("2026-03-10 13:30:00"))
    assert scheduler.is_trading(ts("2026-03-10 14:59:00"))
    assert not scheduler.is_trading(ts("2026-03-10 15:00:00"))


@pytest.mark.parametrize(
    "calendar_name",
    ["CN_FUTURES_0230", "CN_FUTURES_0100", "CN_FUTURES_2300"],
)
def test_builtin_china_futures_calendar_has_no_night_session_after_holidays(
    calendar_name,
):
    scheduler = StaticMinuteScheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    # 2026-09-25 is an SSE holiday, so the first trading day after that holiday
    # block should start at 09:00 with no prior-night reopen.
    assert scheduler.is_trading(ts("2026-09-24 14:59:00"))
    assert not scheduler.is_trading(ts("2026-09-24 15:00:00"))
    assert not scheduler.is_trading(ts("2026-09-27 20:59:00"))
    assert not scheduler.is_trading(ts("2026-09-27 21:00:00"))
    assert scheduler.next_trading_time(
        ts("2026-09-27 21:00:00"), step="1min", inclusive=True
    ) == ts("2026-09-28 09:00:00")
    assert scheduler.to_session_start(ts("2026-09-28 09:30:00")) == ts(
        "2026-09-28 09:00:00"
    )


@pytest.mark.parametrize(
    ("holiday_name", "nightless_date", "reopen_date"),
    [
        ("new_year", "2025-12-31", "2026-01-05"),
        ("spring_festival", "2026-02-13", "2026-02-24"),
        ("qingming", "2026-04-03", "2026-04-07"),
        ("labor_day", "2026-04-30", "2026-05-06"),
        ("dragon_boat", "2026-06-18", "2026-06-22"),
        ("mid_autumn", "2026-09-24", "2026-09-28"),
        ("national_day", "2026-09-30", "2026-10-08"),
    ],
)
@pytest.mark.parametrize(
    "calendar_name",
    ["CN_FUTURES_0230", "CN_FUTURES_0100", "CN_FUTURES_2300"],
)
def test_builtin_china_futures_calendars_follow_2026_holiday_night_session_notices(
    calendar_name, holiday_name, nightless_date, reopen_date
):
    scheduler = StaticMinuteScheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.is_trading(ts(f"{nightless_date} 14:59:00"))
    assert not scheduler.is_trading(ts(f"{nightless_date} 15:00:00"))
    assert not scheduler.is_trading(ts(f"{nightless_date} 20:59:00"))
    assert not scheduler.is_trading(ts(f"{nightless_date} 21:00:00"))

    assert scheduler.next_trading_time(
        ts(f"{nightless_date} 21:00:00"), step="1min", inclusive=True
    ) == ts(f"{reopen_date} 09:00:00"), holiday_name
    assert scheduler.to_session_start(ts(f"{reopen_date} 09:30:00")) == ts(
        f"{reopen_date} 09:00:00"
    ), holiday_name

@pytest.mark.parametrize(
    "calendar_name",
    ["CN_FUTURES_0230", "CN_FUTURES_0100", "CN_FUTURES_2300"],
)
def test_builtin_china_futures_calendar_has_no_night_session_on_2024_12_31(
    calendar_name,
):
    scheduler = StaticMinuteScheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.is_trading(ts("2024-12-31 14:59:00"))
    assert not scheduler.is_trading(ts("2024-12-31 15:00:00"))
    assert not scheduler.is_trading(ts("2025-01-01 20:59:00"))
    assert not scheduler.is_trading(ts("2025-01-01 21:00:00"))
    assert scheduler.next_trading_time(
        ts("2025-01-01 21:00:00"), step="1min", inclusive=True
    ) == ts("2025-01-02 09:00:00")


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
    scheduler = StaticMinuteScheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.shift(ts(before_break), 1, step="1min") == ts(after_break)
    assert scheduler.shift(ts(after_break), -1, step="1min") == ts(before_break)
    assert scheduler.shift(ts(night_last), 1, step="1min") == ts(next_session_first)

    with SchedulerManager.use_scheduler(scheduler):
        assert (
            ChronoTime(before_break).shift(1).isoformat() == ts(after_break).isoformat()
        )
        assert (
            ChronoTime(night_last).shift(1).isoformat()
            == ts(next_session_first).isoformat()
        )


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
    scheduler = StaticMinuteScheduler(calendar_name)

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
    scheduler = StaticMinuteScheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    day_times = scheduler.trading_times(ts(day_start), ts(day_end), step="1min")
    assert len(day_times) == day_expected_len
    assert day_times.iloc[0] == ts("2026-03-10 10:14:00")
    assert day_times.iloc[-1] == ts("2026-03-10 10:30:00")

    night_times = scheduler.trading_times(ts(night_start), ts(night_end), step="1min")
    assert len(night_times) == night_expected_len
    assert night_times.iloc[0] == ts(night_start)
    assert night_times.iloc[-1] == scheduler.shift(ts(night_start), night_expected_len - 1, step="1min")

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
    scheduler = StaticMinuteScheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert (
        scheduler.previous_trading_time(ts(break_time), step="1min", inclusive=True)
        == ts(prev_expected)
    )
    assert (
        scheduler.next_trading_time(ts(break_time), step="1min", inclusive=True)
        == ts(next_expected)
    )

    assert (
        scheduler.previous_trading_time(ts(trading_time), step="1min", inclusive=False)
        == ts(exclusive_prev_expected)
    )
    assert (
        scheduler.next_trading_time(ts(trading_time), step="1min", inclusive=False)
        == ts(exclusive_next_expected)
    )

    assert (
        scheduler.previous_trading_time(
            ts(after_close_time), step="1min", inclusive=True
        )
        == ts(after_close_prev_expected)
    )
    assert (
        scheduler.next_trading_time(ts(after_close_time), step="1min", inclusive=True)
        == ts(after_close_next_expected)
    )

    with SchedulerManager.use_scheduler(scheduler):
        assert (
            ChronoTime(break_time).previous_trading_time().isoformat()
            == ts(prev_expected).isoformat()
        )
        assert (
            ChronoTime(break_time).next_trading_time().isoformat()
            == ts(next_expected).isoformat()
        )
        assert (
            ChronoTime(trading_time)
            .previous_trading_time(inclusive=False)
            .isoformat()
            == ts(exclusive_prev_expected).isoformat()
        )
        assert (
            ChronoTime(trading_time).next_trading_time(inclusive=False).isoformat()
            == ts(exclusive_next_expected).isoformat()
        )


@pytest.mark.parametrize(
    "calendar_name",
    ["CN_FUTURES_0230", "CN_FUTURES_0100", "CN_FUTURES_2300"],
)
def test_shift_raises_when_result_is_out_of_range(calendar_name):
    scheduler = StaticMinuteScheduler(calendar_name)
    first_trading_minute = scheduler.trading_minutes[0]
    last_trading_minute = scheduler.trading_minutes[-1]

    with pytest.raises(IndexError):
        scheduler.shift(first_trading_minute, -1, step="1min")

    with pytest.raises(IndexError):
        scheduler.shift(last_trading_minute, 1, step="1min")
