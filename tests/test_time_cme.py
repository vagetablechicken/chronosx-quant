from chronosx_quant.scheduler import SchedulerManager
from chronosx_quant.time import ChronoTime


def test_cme_specials(get_scheduler):
    with SchedulerManager.use_scheduler(get_scheduler("CME Globex Crypto")):
        t1 = ChronoTime("2025-10-24T00:00:00")
        assert t1.isoformat() == "2025-10-24T00:00:00-05:00"
        t1 = ChronoTime("2025-12-24T00:00:00")
        assert t1.isoformat() == "2025-12-24T00:00:00-06:00"
        t1 = ChronoTime("2025-12-24T16:00:00")
        assert t1.isoformat() == "2025-12-24T16:00:00-06:00"

        assert not ChronoTime("2025-12-24T16:00:00").is_trading()
        assert not ChronoTime("2025-12-24 21:00:00+00:00").is_trading()
        assert ChronoTime("2025-12-25 17:00:00-06:00").is_trading()
        assert ChronoTime("2025-12-25 23:00:00+00:00").is_trading()
        assert ChronoTime("2025-12-26T10:01:00").is_trading()
        assert ChronoTime("2025-12-07T15:58:00").is_trading_day()
        assert ChronoTime("2025-12-08T16:30:00").is_trading_day()

        tts = ChronoTime("2025-12-26T15:58:00").trading_times("2025-12-28T17:02:00")
        assert len(tts) == 4
        assert tts.iloc[0].strftime("%Y-%m-%dT%H:%M") == "2025-12-26T15:58"
        assert tts.iloc[-1].strftime("%Y-%m-%dT%H:%M") == "2025-12-28T17:01"

        t1 = ChronoTime("2025-12-24T00:00:00").to_session_end()
        assert t1.isoformat() == "2025-12-24T12:15:00-06:00"
