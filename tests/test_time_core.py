import pytest

from chronosx_quant.scheduler import SchedulerManager
from chronosx_quant.time import ChronoTime
from tests.helpers import get_scheduler


def test_init():
    t1 = ChronoTime("2024-01-01T00:00:00")
    assert t1.isoformat() == "2024-01-01T00:00:00+08:00"

    with SchedulerManager.use_scheduler(get_scheduler("SSE")):
        t1 = ChronoTime("2024-01-01T09:30:00")
        assert t1.isoformat() == "2024-01-01T09:30:00+08:00"


def test_time_shift():
    with pytest.raises(KeyError):
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
    assert len(tts) == 1

    tts = ChronoTime("2026-03-10T09:30:00").trading_times("2026-03-10T15:00:00")
    assert len(tts) == 240
    tts = ChronoTime("2026-03-10T09:30:00").trading_times("2026-03-10T14:59:00")
    assert len(tts) == 239

    days = tts.resample("D").first().dt.date
    assert len(days) == 1


def test_trading_day_delta():
    assert (
        ChronoTime("2026-03-10T09:30:00").trading_day_delta("2026-03-10T14:59:00") == 1
    )
    assert (
        ChronoTime("2026-03-10T00:01:00").trading_day_delta("2026-03-10T23:59:00") == 1
    )
    assert (
        ChronoTime("2026-03-10T11:29:00").trading_day_delta("2026-03-12T13:00:00") == 3
    )
    assert (
        ChronoTime("2026-03-10T08:00:00").trading_day_delta("2026-03-12T20:00:00") == 3
    )
    assert (
        ChronoTime("2026-03-13T14:59:00").trading_day_delta("2026-03-16T09:30:00") == 2
    )
    assert (
        ChronoTime("2026-03-13T20:00:00").trading_day_delta("2026-03-16T08:00:00") == 2
    )
    assert (
        ChronoTime("2026-03-16T09:30:00").trading_day_delta("2026-03-13T14:59:00") == -2
    )
    assert (
        ChronoTime("2026-03-16T20:00:00").trading_day_delta("2026-03-13T08:00:00") == -2
    )
    assert (
        ChronoTime("2026-03-15T09:30:00").trading_day_delta("2026-03-15T14:59:00") == 0
    )
    assert (
        ChronoTime("2026-03-15T00:01:00").trading_day_delta("2026-03-16T00:01:00") == 1
    )
    assert (
        ChronoTime("2026-03-14T12:00:00").trading_day_delta("2026-03-15T12:00:00") == 0
    )


def test_previous_and_next():
    t1 = ChronoTime("2026-03-10T11:29:00")
    assert t1.is_trading()
    assert t1.previous_trading_time() == t1
    t2 = ChronoTime("2026-03-10T11:30:00")
    assert not t2.is_trading()
    assert t2.previous_trading_time() == t1


def test_session_start_and_end():
    t1 = ChronoTime("2026-03-10T11:29:00")
    assert t1.is_trading()
    t2 = t1.to_session_end()
    assert not t2.is_trading()
    assert t2.isoformat() == "2026-03-10T15:00:00+08:00"
    t3 = t1.to_session_start()
    assert t3.is_trading()
    assert t3.isoformat() == "2026-03-10T09:30:00+08:00"
    assert str(t1) == "2026-03-10 11:29:00+08:00"


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
