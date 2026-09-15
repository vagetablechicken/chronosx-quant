from datetime import date

import pandas as pd
import pytest

from chronosx_quant import ChronoDay, ChronoTime, use_calendar
from tests.helpers import ts


def test_chrono_day_init_and_conversion():
    with use_calendar("SSE"):
        d1 = ChronoDay("2026-03-10")
        assert isinstance(d1, ChronoDay)
        assert d1.date() == date(2026, 3, 10)
        assert d1.strftime("%Y-%m-%d") == "2026-03-10"

        # From ChronoTime
        t = ChronoTime("2026-03-10 10:15:30")
        d2 = ChronoDay(t)
        assert d2 == d1

        # From ChronoTime.trading_day property
        assert t.trading_day == d1
        assert t.get_trading_date() == d1

        # From date
        d3 = ChronoDay(date(2026, 3, 10))
        assert d3 == d1

        # From ChronoDay idempotence
        assert ChronoDay(d1) == d1


def test_chrono_day_shift_forward_and_backward():
    with use_calendar("SSE"):
        day = ChronoDay("2026-03-10")
        next_day = day.shift(1)
        assert isinstance(next_day, ChronoDay)
        assert next_day == ChronoDay("2026-03-11")

        prev_day = next_day.shift(-1)
        assert prev_day == day


def test_chrono_day_shift_skips_weekends():
    with use_calendar("SSE"):
        friday = ChronoDay("2026-03-13")
        monday = friday.shift(1)
        assert monday == ChronoDay("2026-03-16")
        assert monday.shift(-1) == friday

        tues = ChronoDay("2026-03-10")
        three_days_ago = tues.shift(-3)
        assert three_days_ago == ChronoDay("2026-03-05")


def test_chrono_day_shift_from_non_trading_day():
    with use_calendar("SSE"):
        # Sunday 2026-03-15 looking back 1 trading day -> Friday 2026-03-13
        sunday = ChronoDay("2026-03-15")
        assert not sunday.is_trading()
        friday = sunday.shift(-1)
        assert friday == ChronoDay("2026-03-13")
        assert friday.is_trading()

        # Sunday looking forward 1 trading day -> Monday 2026-03-16
        monday = sunday.shift(1)
        assert monday == ChronoDay("2026-03-16")

        # Holiday 2026-05-01 (Labor Day)
        labor_day = ChronoDay("2026-05-01")
        assert not labor_day.is_trading()
        assert labor_day.shift(-1) == ChronoDay("2026-04-30")
        assert labor_day.shift(1) == ChronoDay("2026-05-06")


def test_chrono_day_session_start_and_end():
    with use_calendar("SSE"):
        day = ChronoDay("2026-03-10")
        assert day.session_start == ChronoTime("2026-03-10 09:30:00")
        assert day.session_end == ChronoTime("2026-03-10 15:00:00")
        assert day.to_session_start() == day.session_start
        assert day.to_session_end() == day.session_end

        # Non-trading day raises ValueError when querying session bounds
        sunday = ChronoDay("2026-03-15")
        with pytest.raises(ValueError, match="is not a valid trading day"):
            _ = sunday.session_start
        with pytest.raises(ValueError, match="is not a valid trading day"):
            _ = sunday.session_end


def test_chrono_day_futures_night_session_and_holidays():
    with use_calendar("CN_FUTURES_0230"):
        # Monday night 2026-03-09 21:30:00 belongs to trading day 2026-03-10
        night_t = ChronoTime("2026-03-09 21:30:00")
        assert night_t.trading_day == ChronoDay("2026-03-10")

        # Session open of 2026-03-10 trading day is Monday night 21:00:00
        assert night_t.trading_day.session_start == ChronoTime("2026-03-09 21:00:00")
        # Session close is Tuesday afternoon 15:00:00
        assert night_t.trading_day.session_end == ChronoTime("2026-03-10 15:00:00")

        # Shift 1 trading day to 2026-03-11
        next_day = night_t.trading_day.shift(1)
        assert next_day == ChronoDay("2026-03-11")
        assert next_day.session_start == ChronoTime("2026-03-10 21:00:00")

        # Holiday case: 2026-09-30 is last day before National Day
        # 2026-10-08 is the first day after National Day (has NO night session on 2026-09-30)
        day_before_holiday = ChronoDay("2026-09-30")
        day_after_holiday = day_before_holiday.shift(1)
        assert day_after_holiday == ChronoDay("2026-10-08")
        # Opens in morning at 09:00:00, not night!
        assert day_after_holiday.session_start == ChronoTime("2026-10-08 09:00:00")


def test_chrono_day_delta_and_trading_times():
    with use_calendar("SSE"):
        day1 = ChronoDay("2026-03-10")
        day2 = ChronoDay("2026-03-13")

        # Distance between Tue and Fri across 4 trading days [Tue, Wed, Thu, Fri]
        assert day1.delta(day2) == 4
        assert day2.delta(day1) == -4
        assert day1.delta(day1) == 1

        # Trading times of a single day
        times = day1.trading_times()
        assert isinstance(times, pd.Series)
        assert times.iloc[0] == ChronoTime("2026-03-10 09:30:00")
        assert times.iloc[-1] == ChronoTime("2026-03-10 14:59:00")


def test_time_shift_purified_step_and_validation():
    with use_calendar("SSE"):
        t = ChronoTime("2026-03-10 10:00:00")

        # shift step='1day' is no longer supported on ChronoTime, guides user to trading_day
        with pytest.raises(ValueError, match="only supports step='1min'"):
            t.shift(1, step="1day")

        # Non-trading minute raises ValueError
        t_break = ChronoTime("2026-03-10 12:00:00")
        with pytest.raises(ValueError, match="is not a valid trading minute"):
            t_break.shift(1)


@pytest.mark.parametrize("calendar_name", ["SSE"])
def test_scheduler_is_trading_day(calendar_name, scheduler):
    # Trading day (tz-aware and tz-naive)
    assert scheduler.is_trading_day(ts("2026-03-10 10:00:00"))
    assert scheduler.is_trading_day(ts("2026-03-10"))
    assert scheduler.is_trading_day(ts("2026-03-10 10:00:00", tz="Asia/Shanghai"))
    # Weekend (SSE sessions never span across weekend)
    assert not scheduler.is_trading_day(ts("2026-03-14"))
    assert not scheduler.is_trading_day(ts("2026-03-15"))
    assert not scheduler.is_trading_day(ts("2026-03-15 12:00:00"))

    # Holidays (New Year, Spring Festival, Labor Day, National Day)
    assert not scheduler.is_trading_day(ts("2026-01-01"))
    assert not scheduler.is_trading_day(ts("2026-02-16"))
    assert not scheduler.is_trading_day(ts("2026-05-01"))
    assert not scheduler.is_trading_day(ts("2026-10-01"))
    assert not scheduler.is_trading_day(ts("2026-10-02"))


@pytest.mark.parametrize("calendar_name", ["CN_FUTURES_0230"])
def test_scheduler_is_trading_day_futures(calendar_name, scheduler):
    assert scheduler.is_trading_day(ts("2026-03-09"))
    assert scheduler.is_trading_day(ts("2026-03-10"))

    # Holidays
    assert not scheduler.is_trading_day(ts("2026-01-01"))
    assert not scheduler.is_trading_day(ts("2026-02-16"))
    assert not scheduler.is_trading_day(ts("2026-05-01"))
    assert not scheduler.is_trading_day(ts("2026-10-01"))
    assert not scheduler.is_trading_day(ts("2026-10-02"))


@pytest.mark.parametrize("calendar_name", ["SSE"])
def test_scheduler_shift_trading_day(calendar_name, scheduler):
    # 1. Trading day - normal shifts and delta == 0
    # Accepts ChronoDay only
    assert scheduler.shift_trading_day(ChronoDay("2026-03-10"), 0) == pd.Timestamp(
        "2026-03-10"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-10"), 1) == pd.Timestamp(
        "2026-03-11"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-10"), -1) == pd.Timestamp(
        "2026-03-09"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-10"), 2) == pd.Timestamp(
        "2026-03-12"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-10"), -2) == pd.Timestamp(
        "2026-03-06"
    )

    # 2. Skips weekends and holidays when shifting from a trading day
    # 2026-03-13 is Friday; +1 -> 2026-03-16 (Monday)
    assert scheduler.shift_trading_day(ChronoDay("2026-03-13"), 1) == pd.Timestamp(
        "2026-03-16"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-16"), -1) == pd.Timestamp(
        "2026-03-13"
    )
    # 2026-04-30 is Thursday before Labor Day holiday (2026-05-01 to 05-05)
    assert scheduler.shift_trading_day(ChronoDay("2026-04-30"), 1) == pd.Timestamp(
        "2026-05-06"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-05-06"), -1) == pd.Timestamp(
        "2026-04-30"
    )

    # 3. Non-trading day (weekend / holiday) shifting
    # Sunday 2026-03-15:
    assert scheduler.shift_trading_day(ChronoDay("2026-03-15"), 1) == pd.Timestamp(
        "2026-03-16"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-15"), 2) == pd.Timestamp(
        "2026-03-17"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-15"), -1) == pd.Timestamp(
        "2026-03-13"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-15"), -2) == pd.Timestamp(
        "2026-03-12"
    )

    # Saturday 2026-03-14:
    assert scheduler.shift_trading_day(ChronoDay("2026-03-14"), 1) == pd.Timestamp(
        "2026-03-16"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-03-14"), -1) == pd.Timestamp(
        "2026-03-13"
    )

    # Holiday 2026-05-01 (Labor Day):
    assert scheduler.shift_trading_day(ChronoDay("2026-05-01"), 1) == pd.Timestamp(
        "2026-05-06"
    )
    assert scheduler.shift_trading_day(ChronoDay("2026-05-01"), -1) == pd.Timestamp(
        "2026-04-30"
    )

    # Non-trading day with delta == 0 raises ValueError
    with pytest.raises(ValueError, match="is not a valid trading day"):
        scheduler.shift_trading_day(ChronoDay("2026-03-15"), 0)
    with pytest.raises(ValueError, match="is not a valid trading day"):
        scheduler.shift_trading_day(ChronoDay("2026-05-01"), 0)


def test_scheduler_shift_trading_day_out_of_range():
    from chronosx_quant.scheduler import StaticMinuteScheduler

    # Use a bounded schedule window to test boundaries
    scheduler = StaticMinuteScheduler("SSE", start="2026-03-02", end="2026-03-06")
    # Schedule trading days: Mon 2026-03-02 to Fri 2026-03-06 (5 days)
    first_day = scheduler.schedule.index[0]
    last_day = scheduler.schedule.index[-1]

    # Valid shifts within boundary
    assert scheduler.shift_trading_day(first_day, 4) == last_day
    assert scheduler.shift_trading_day(last_day, -4) == first_day

    # Out of range shifts for valid trading days
    with pytest.raises(IndexError, match="Shift result out of range"):
        scheduler.shift_trading_day(first_day, -1)
    with pytest.raises(IndexError, match="Shift result out of range"):
        scheduler.shift_trading_day(last_day, 1)

    # Out of range shifts from non-trading dates before start or after end
    with pytest.raises(IndexError, match="Shift result out of range"):
        scheduler.shift_trading_day(ChronoDay("2026-03-01"), -1)  # Sunday before start
    with pytest.raises(IndexError, match="Shift result out of range"):
        scheduler.shift_trading_day(ChronoDay("2026-03-07"), 1)  # Saturday after end


def test_chrono_day_previous_and_next():
    with use_calendar("SSE"):
        # 1. On a trading day (Tuesday 2026-03-10)
        tue = ChronoDay("2026-03-10")
        assert tue.previous_trading_day() == tue
        assert tue.previous() == tue
        assert tue.next_trading_day() == tue
        assert tue.next() == tue

        # Exclusive
        assert tue.previous(inclusive=False) == ChronoDay("2026-03-09")
        assert tue.next(inclusive=False) == ChronoDay("2026-03-11")

        # 2. Friday (2026-03-13)
        fri = ChronoDay("2026-03-13")
        assert fri.next(inclusive=True) == fri
        assert fri.next(inclusive=False) == ChronoDay("2026-03-16")

        # 3. Non-trading day: Weekend (Sunday 2026-03-15)
        sun = ChronoDay("2026-03-15")
        assert not sun.is_trading()
        assert sun.previous() == ChronoDay("2026-03-13")
        assert sun.previous(inclusive=False) == ChronoDay("2026-03-13")
        assert sun.next() == ChronoDay("2026-03-16")
        assert sun.next(inclusive=False) == ChronoDay("2026-03-16")

        # 4. Non-trading day: Holiday (Labor Day 2026-05-01)
        labor_day = ChronoDay("2026-05-01")
        assert not labor_day.is_trading()
        assert labor_day.previous() == ChronoDay("2026-04-30")
        assert labor_day.next() == ChronoDay("2026-05-06")


@pytest.mark.parametrize("calendar_name", ["SSE"])
def test_scheduler_previous_and_next_trading_day(calendar_name, scheduler):
    # Trading day
    t_mar10 = pd.Timestamp("2026-03-10")
    assert scheduler.previous_trading_day(t_mar10, inclusive=True) == pd.Timestamp(
        "2026-03-10"
    )
    assert scheduler.previous_trading_day(t_mar10, inclusive=False) == pd.Timestamp(
        "2026-03-09"
    )
    assert scheduler.next_trading_day(t_mar10, inclusive=True) == pd.Timestamp(
        "2026-03-10"
    )
    assert scheduler.next_trading_day(t_mar10, inclusive=False) == pd.Timestamp(
        "2026-03-11"
    )

    # Non-trading day (Sunday)
    t_mar15 = pd.Timestamp("2026-03-15")
    assert scheduler.previous_trading_day(t_mar15, inclusive=True) == pd.Timestamp(
        "2026-03-13"
    )
    assert scheduler.previous_trading_day(t_mar15, inclusive=False) == pd.Timestamp(
        "2026-03-13"
    )
    assert scheduler.next_trading_day(t_mar15, inclusive=True) == pd.Timestamp(
        "2026-03-16"
    )
    assert scheduler.next_trading_day(t_mar15, inclusive=False) == pd.Timestamp(
        "2026-03-16"
    )

    # Different timezone (UTC 2026-03-09 20:00:00 is Asia/Shanghai 2026-03-10 04:00:00)
    t_utc = pd.Timestamp("2026-03-09 20:00:00", tz="UTC")
    assert scheduler.previous_trading_day(t_utc, inclusive=True) == pd.Timestamp(
        "2026-03-10"
    )
    assert scheduler.next_trading_day(t_utc, inclusive=True) == pd.Timestamp(
        "2026-03-10"
    )


def test_timezone_conversion_before_index_lookup():
    with use_calendar("SSE") as scheduler:
        # 1. shift_trading_day with UTC timestamp that equals 00:00 in Asia/Shanghai
        # 2026-03-09 16:00:00 UTC == 2026-03-10 00:00:00+08:00
        t_utc_midnight = pd.Timestamp("2026-03-09 16:00:00", tz="UTC")
        res = scheduler.shift_trading_day(t_utc_midnight, 1)
        assert res == pd.Timestamp("2026-03-11")

        # 2. trading_day_delta with UTC timestamps
        t_start_utc = pd.Timestamp(
            "2026-03-09 16:00:00", tz="UTC"
        )  # 2026-03-10 Shanghai
        t_end_utc = pd.Timestamp("2026-03-11 16:00:00", tz="UTC")  # 2026-03-12 Shanghai
        assert scheduler.trading_day_delta(t_start_utc, t_end_utc) == 3

        # 3. ChronoDay initialized from UTC timestamp still recognizes trading day correctly
        day_utc = ChronoDay(pd.Timestamp("2026-03-09 16:00:00", tz="UTC"))
        assert day_utc == ChronoDay("2026-03-10")
        assert day_utc.is_trading()
        assert day_utc.session_start == ChronoTime("2026-03-10 09:30:00")

        # 4. is_trading with naive, Shanghai-aware, and UTC-aware timestamps
        # 2026-03-10 09:31:00 is trading
        t_naive = pd.Timestamp("2026-03-10 09:31:00")
        t_shanghai = pd.Timestamp("2026-03-10 09:31:00", tz="Asia/Shanghai")
        t_utc = pd.Timestamp("2026-03-10 01:31:00", tz="UTC")
        assert scheduler.is_trading(t_naive)
        assert scheduler.is_trading(t_shanghai)
        assert scheduler.is_trading(t_utc)

        # 5. get_trading_date with naive, Shanghai-aware, and UTC-aware timestamps
        expected_date = pd.Timestamp("2026-03-10")
        assert scheduler.get_trading_date(t_naive) == expected_date
        assert scheduler.get_trading_date(t_shanghai) == expected_date
        assert scheduler.get_trading_date(t_utc) == expected_date

        # 6. to_session_start & to_session_end
        expected_open = pd.Timestamp("2026-03-10 09:30:00", tz="Asia/Shanghai")
        expected_close = pd.Timestamp("2026-03-10 15:00:00", tz="Asia/Shanghai")
        assert scheduler.to_session_start(t_naive) == expected_open
        assert scheduler.to_session_start(t_utc) == expected_open
        assert scheduler.to_session_end(t_naive) == expected_close
        assert scheduler.to_session_end(t_utc) == expected_close

        # 7. shift with naive and UTC
        assert scheduler.shift(t_naive, 1) == pd.Timestamp(
            "2026-03-10 09:32:00", tz="Asia/Shanghai"
        )
        assert scheduler.shift(t_utc, 1) == pd.Timestamp(
            "2026-03-10 09:32:00", tz="Asia/Shanghai"
        )

        # 8. previous_trading_time & next_trading_time with naive and UTC
        assert scheduler.previous_trading_time(t_naive) == pd.Timestamp(
            "2026-03-10 09:31:00", tz="Asia/Shanghai"
        )
        assert scheduler.previous_trading_time(t_utc) == pd.Timestamp(
            "2026-03-10 09:31:00", tz="Asia/Shanghai"
        )
        assert scheduler.next_trading_time(t_naive) == pd.Timestamp(
            "2026-03-10 09:31:00", tz="Asia/Shanghai"
        )
        assert scheduler.next_trading_time(t_utc) == pd.Timestamp(
            "2026-03-10 09:31:00", tz="Asia/Shanghai"
        )

        # 9. trading_times with naive and UTC
        times_naive = scheduler.trading_times(
            pd.Timestamp("2026-03-10 09:30:00"), pd.Timestamp("2026-03-10 09:33:00")
        )
        times_utc = scheduler.trading_times(
            pd.Timestamp("2026-03-10 01:30:00", tz="UTC"),
            pd.Timestamp("2026-03-10 01:33:00", tz="UTC"),
        )
        assert len(times_naive) == 3
        assert len(times_utc) == 3
        assert (times_naive == times_utc).all()
