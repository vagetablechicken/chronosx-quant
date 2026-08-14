from datetime import time

import pandas as pd
import pytest
from pandas_market_calendars.market_calendar import MarketCalendar

from chronosx_quant.scheduler import SchedulerManager, StaticMinuteScheduler
from chronosx_quant.time import ChronoTime
from tests.helpers import get_scheduler


def test_init():
    get_scheduler("SSE")
    get_scheduler("CME Globex Crypto")
    get_scheduler("CN_FUTURES_0230")
    get_scheduler("CN_FUTURES_0100")
    get_scheduler("CN_FUTURES_2300")


def test_init_accepts_explicit_schedule_window():
    scheduler = StaticMinuteScheduler(
        "SSE",
        start="2026-03-01",
        end="2026-03-31",
    )

    assert scheduler.schedule.index[0] == pd.Timestamp("2026-03-02")
    assert scheduler.schedule.index[-1] == pd.Timestamp("2026-03-31")


def test_init_rejects_reversed_schedule_window():
    with pytest.raises(ValueError, match="Schedule start must not be after end"):
        StaticMinuteScheduler(
            "SSE",
            start="2026-04-01",
            end="2026-03-01",
        )


def test_info_is_cached():
    scheduler = get_scheduler("SSE")

    assert scheduler.info is scheduler.info


def test_session_lookup_uses_left_closed_boundaries():
    scheduler = get_scheduler("SSE")
    session_open = scheduler.schedule["market_open"].iloc[0]
    session_close = scheduler.schedule["market_close"].iloc[0]

    assert scheduler.to_session_start(session_open) == session_open
    assert (
        scheduler.to_session_end(session_close - pd.Timedelta("1ns")) == session_close
    )
    assert (
        scheduler.get_trading_date(session_open.tz_convert("UTC"))
        == (scheduler.schedule.index[0])
    )

    with pytest.raises(ValueError, match="is not in trading interval"):
        scheduler.to_session_end(session_open - pd.Timedelta("1ns"))

    with pytest.raises(ValueError, match="is not in trading interval"):
        scheduler.to_session_end(session_close)


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
    "calendar_name",
    ["CN_FUTURES_0230", "CN_FUTURES_0100", "CN_FUTURES_2300"],
)
def test_shift_raises_when_result_is_out_of_range(calendar_name):
    scheduler = get_scheduler(calendar_name)
    first_trading_minute = scheduler.trading_minutes[0]
    last_trading_minute = scheduler.trading_minutes[-1]

    with pytest.raises(IndexError):
        scheduler.shift(first_trading_minute, -1, step="1min")

    with pytest.raises(IndexError):
        scheduler.shift(last_trading_minute, 1, step="1min")


@pytest.mark.parametrize(
    "calendar_name",
    ["CN_FUTURES_0230", "CN_FUTURES_0100", "CN_FUTURES_2300"],
)
def test_simple_friday_evening(calendar_name):
    scheduler = get_scheduler(calendar_name)
    with SchedulerManager.use_scheduler(scheduler):
        friday_night = ChronoTime("2023-05-26 21:00:00+08:00")
        scheduler.shift(friday_night, 100, step="1min")
        assert scheduler.to_session_end(friday_night) == ChronoTime(
            "2023-05-29 15:00:00"
        )
        assert friday_night.get_trading_date() == ChronoTime("2023-05-29")
