import time
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from chronosx_quant import ChronoDay, ChronoTime, use_calendar
from chronosx_quant.scheduler import SchedulerManager, StaticMinuteScheduler


def test_init():
    t1 = ChronoTime("2024-01-01T00:00:00")
    assert isinstance(t1, ChronoTime)
    assert t1.isoformat() == "2024-01-01T00:00:00+08:00"

    with use_calendar("SSE"):
        t1 = ChronoTime("2024-01-01T09:30:00")
        assert t1.isoformat() == "2024-01-01T09:30:00+08:00"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            datetime(2026, 3, 10, 9, 30),
            "2026-03-10T09:30:00+08:00",
        ),
        (
            datetime(2026, 3, 10, 1, 30, tzinfo=timezone.utc),
            "2026-03-10T09:30:00+08:00",
        ),
        (
            pd.Timestamp("2026-03-10T01:30:00Z"),
            "2026-03-10T09:30:00+08:00",
        ),
        (0, "1970-01-01T00:00:00+08:00"),
        (0.0, "1970-01-01T00:00:00+08:00"),
    ],
)
def test_init_accepts_supported_input_types_and_normalizes_timezone(value, expected):
    result = ChronoTime(value)

    assert isinstance(result, ChronoTime)
    assert result.isoformat() == expected


def test_init_accepts_an_existing_chronotime():
    original = ChronoTime("2026-03-10T09:30:00+08:00")

    result = ChronoTime(original)

    assert result is original


def test_init_none_returns_now():
    scheduler = SchedulerManager.get_scheduler()
    before = pd.Timestamp.now(scheduler.tz)

    t_empty = ChronoTime()
    t_none = ChronoTime(None)

    after = pd.Timestamp.now(scheduler.tz)
    assert isinstance(t_empty, ChronoTime)
    assert isinstance(t_none, ChronoTime)
    assert before <= t_empty <= after
    assert before <= t_none <= after


def test_now_returns_current_time_in_scheduler_timezone():
    scheduler = SchedulerManager.get_scheduler()
    before = pd.Timestamp.now(scheduler.tz)

    result = ChronoTime.now()

    after = pd.Timestamp.now(scheduler.tz)
    assert isinstance(result, ChronoTime)
    assert result.tz == scheduler.tz
    assert before <= result <= after


def test_now_rejects_tz_parameter():
    scheduler = SchedulerManager.get_scheduler()
    with pytest.raises(
        ValueError,
        match="ChronoTime.now\\(\\) does not accept 'tz'",
    ):
        ChronoTime.now(tz=scheduler.tz)


def test_now_matches_utc_epoch():
    utc_before = datetime.now(timezone.utc).timestamp()
    ct = ChronoTime.now()
    utc_after = datetime.now(timezone.utc).timestamp()

    assert isinstance(ct, ChronoTime)
    assert ct.tz == SchedulerManager.get_scheduler().tz
    # The UTC epoch timestamp must match real-world absolute time, independent of host timezone
    assert utc_before - 0.01 <= ct.timestamp() <= utc_after + 0.01


def test_now_across_calendars():
    # Verify that ChronoTime.now() across different market calendars reflects their local timezones
    # and accurately matches the global UTC time.
    with use_calendar("SSE"):
        t0 = time.time()
        ct_sse = ChronoTime.now()
        t1 = time.time()
        assert str(ct_sse.tz) == "Asia/Shanghai"
        assert t0 - 0.01 <= ct_sse.timestamp() <= t1 + 0.01

    with use_calendar("NYSE"):
        t0 = time.time()
        ct_nyse = ChronoTime.now()
        t1 = time.time()
        assert str(ct_nyse.tz) == "America/New_York"
        assert t0 - 0.01 <= ct_nyse.timestamp() <= t1 + 0.01


@pytest.mark.skipif(
    not hasattr(time, "tzset"),
    reason="time.tzset is only available on Unix/POSIX systems",
)
@pytest.mark.parametrize(
    "machine_tz",
    ["UTC", "America/New_York", "Asia/Tokyo", "Europe/London", "Australia/Sydney"],
)
def test_now_independent_of_system_timezone_unix(monkeypatch, machine_tz):
    monkeypatch.setenv("TZ", machine_tz)
    time.tzset()
    try:
        utc_before = datetime.now(timezone.utc).timestamp()
        ct = ChronoTime.now()
        utc_after = datetime.now(timezone.utc).timestamp()

        # Regardless of host machine's timezone, ChronoTime.now() is in the scheduler timezone
        assert ct.tz == SchedulerManager.get_scheduler().tz
        assert utc_before <= ct.timestamp() <= utc_after
    finally:
        time.tzset()


def test_time_shift():
    with pytest.raises(ValueError):
        ChronoTime("2026-01-01T00:00:00").shift(1, step="1min")

    t = ChronoTime("2026-03-10T09:30:00").shift(1, step="1min")
    assert t.isoformat() == "2026-03-10T09:31:00+08:00"

    t = ChronoTime("2026-03-10T11:29:00").shift(3, step="1min")
    assert t.isoformat() == "2026-03-10T13:02:00+08:00"
    t = ChronoTime("2026-03-10T11:29:00").shift(3)
    assert t.isoformat() == "2026-03-10T13:02:00+08:00"

    with pytest.raises(ValueError):
        ChronoTime("2026-03-10T11:29:00").shift(1, step="3min")

    t = ChronoTime("2026-03-10T11:29:03.1234").shift(-1, step="1min")
    assert t.isoformat() == "2026-03-10T11:28:03.123400+08:00"
    t = ChronoTime("2026-03-10T11:29:03.1234").shift(1, step="1min")
    assert t.isoformat() == "2026-03-10T13:00:03.123400+08:00"


def test_is_trading():
    assert ChronoTime("2026-03-10T11:29:00").is_trading()
    assert not ChronoTime("2026-03-10T11:30:00").is_trading()
    assert not ChronoTime("2026-03-10T12:59:59").is_trading()
    assert ChronoTime("2026-03-10T13:00:00").is_trading()
    assert not ChronoTime("2026-03-10T15:00:00").is_trading()

    assert ChronoTime("2026-03-10T00:30:00").is_trading_day()
    assert ChronoTime("2026-03-10T20:30:00").is_trading_day()
    assert not ChronoTime("2026-03-15T09:30:00").is_trading_day()


def test_trading_times():
    tts = ChronoTime("2026-03-10T11:29:00").trading_times("2026-03-10T13:00:00")
    assert isinstance(tts, pd.Series)
    assert len(tts) == 1

    tts = ChronoTime("2026-03-10T09:30:00").trading_times("2026-03-10T15:00:00")
    assert len(tts) == 240
    tts = ChronoTime("2026-03-10T09:30:00").trading_times("2026-03-10T14:59:00")
    assert len(tts) == 239

    days = tts.resample("D").first().dt.date
    assert len(days) == 1


@pytest.mark.parametrize(
    "end",
    [
        datetime(2026, 3, 10, 13, 0),
        pd.Timestamp("2026-03-10T13:00:00"),
        ChronoTime("2026-03-10T13:00:00"),
    ],
)
def test_trading_times_accepts_supported_end_types(end):
    result = ChronoTime("2026-03-10T11:29:00").trading_times(end)

    assert len(result) == 1


def test_trading_times_rejects_unsupported_step():
    with pytest.raises(ValueError):
        ChronoTime("2026-03-10T09:30:00").trading_times(
            "2026-03-10T10:30:00", step="3min"
        )


def test_previous_and_next():
    trading_time = ChronoTime("2026-03-10T11:29:00")
    break_time = ChronoTime("2026-03-10T11:30:00")

    assert trading_time.previous_trading_time() == trading_time
    assert trading_time.next_trading_time() == trading_time
    assert trading_time.previous_trading_time(inclusive=False) == ChronoTime(
        "2026-03-10T11:28:00"
    )
    assert trading_time.next_trading_time(inclusive=False) == ChronoTime(
        "2026-03-10T13:00:00"
    )
    assert break_time.previous_trading_time() == trading_time
    assert break_time.next_trading_time() == ChronoTime("2026-03-10T13:00:00")


def test_previous_and_next_return_none_at_loaded_schedule_boundaries():
    scheduler = SchedulerManager.get_scheduler()
    assert isinstance(scheduler, StaticMinuteScheduler)
    first = ChronoTime(scheduler.trading_minutes[0])
    last = ChronoTime(scheduler.trading_minutes[-1])

    assert first.previous_trading_time(inclusive=False) is None
    assert last.next_trading_time(inclusive=False) is None


@pytest.mark.parametrize("method_name", ["previous_trading_time", "next_trading_time"])
def test_previous_and_next_reject_unsupported_step(method_name):
    value = ChronoTime("2026-03-10T11:29:00")

    with pytest.raises(ValueError):
        getattr(value, method_name)(step="3min")


def test_session_start_and_end():
    break_time = ChronoTime("2026-03-10T12:00:00")

    session_start = break_time.to_session_start()
    session_end = break_time.to_session_end()

    assert isinstance(session_start, ChronoTime)
    assert isinstance(session_end, ChronoTime)
    assert session_start == ChronoTime("2026-03-10T09:30:00")
    assert session_end == ChronoTime("2026-03-10T15:00:00")


def test_get_trading_date_returns_chronotime_and_supports_date_conversion():
    t = ChronoTime("2026-03-10T12:00:00")
    result = t.get_trading_date()

    assert isinstance(result, ChronoDay)
    assert result == ChronoTime("2026-03-10")
    assert result.date() == date(2026, 3, 10)
    assert t.trading_day == result


@pytest.mark.parametrize(
    "method_name",
    ["to_session_start", "to_session_end", "get_trading_date"],
)
def test_session_methods_reject_time_outside_a_session(method_name):
    outside_session = ChronoTime("2026-03-15T12:00:00")

    with pytest.raises(ValueError, match="is not in trading interval"):
        getattr(outside_session, method_name)()


def test_operator():
    t1 = ChronoTime("2026-03-10T11:29:00")
    t2 = ChronoTime("2026-03-10T11:30:00")
    assert t1 < t2
    assert t1 <= t2
    assert t2 > t1
    assert t2 >= t1
    assert t1 != t2
    assert t1 == ChronoTime("2026-03-10T11:29:00")
    assert (t1 - t2).total_seconds() == -60
