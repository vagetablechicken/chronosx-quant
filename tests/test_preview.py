from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

import chronosx_quant.preview as preview_module


def fake_scheduler(**overrides):
    calendar = SimpleNamespace(
        name="TEST",
        full_name="Test Exchange",
        tz="Asia/Shanghai",
        holidays=lambda: SimpleNamespace(
            kwds={
                "holidays": [
                    pd.Timestamp("2026-08-09"),
                    pd.Timestamp("2026-08-12"),
                ]
            }
        ),
    )
    values = {
        "calendar": calendar,
        "tz": calendar.tz,
        "is_trading_day": Mock(return_value=True),
        "is_trading": Mock(return_value=True),
        "get_trading_date": Mock(return_value=pd.Timestamp("2026-08-11")),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_holiday_preview_filters_range_and_passes_scheduler_window():
    scheduler = fake_scheduler()

    with patch.object(
        preview_module,
        "StaticMinuteScheduler",
        return_value=scheduler,
    ) as scheduler_type:
        result = preview_module.build_holiday_preview(
            "TEST",
            start="2026-08-10",
            days_ahead=7,
            scheduler_start="2026-01-01",
            scheduler_end="2027-01-01",
        )

    scheduler_type.assert_called_once_with("TEST", start="2026-01-01", end="2027-01-01")
    assert result["range_start"] == "2026-08-10"
    assert result["range_end"] == "2026-08-17"
    assert result["upcoming_holidays"] == ["2026-08-12"]


def test_build_time_preview_reports_weekday_and_trading_information():
    scheduler = fake_scheduler()

    with (
        patch.object(preview_module, "StaticMinuteScheduler", return_value=scheduler),
        patch.object(
            preview_module.SchedulerManager,
            "use_scheduler",
            return_value=nullcontext(),
        ),
    ):
        result = preview_module.build_time_preview("TEST", "2026-08-10 13:00:00+00:00")

    query_time = pd.Timestamp("2026-08-10 21:00:00+08:00")
    scheduler.is_trading_day.assert_called_once_with(query_time)
    scheduler.is_trading.assert_called_once_with(query_time)
    scheduler.get_trading_date.assert_called_once_with(query_time)
    assert result == {
        "calendar_name": "TEST",
        "calendar_full_name": "Test Exchange",
        "timezone": "Asia/Shanghai",
        "time": "2026-08-10T21:00:00+08:00",
        "date": "2026-08-10",
        "weekday": "Monday",
        "is_trading_day": True,
        "is_trading_time": True,
        "trading_date": "2026-08-11",
    }


def test_build_time_preview_distinguishes_break_from_non_trading_day():
    scheduler = fake_scheduler(
        is_trading=Mock(return_value=False),
        is_trading_day=Mock(return_value=True),
    )

    with (
        patch.object(preview_module, "StaticMinuteScheduler", return_value=scheduler),
        patch.object(
            preview_module.SchedulerManager,
            "use_scheduler",
            return_value=nullcontext(),
        ),
    ):
        result = preview_module.build_time_preview("TEST", "2026-08-10 22:30")

    assert result["is_trading_day"] is True
    assert result["is_trading_time"] is False
    assert result["trading_date"] == "2026-08-11"


def test_build_time_preview_has_no_trading_date_outside_session():
    scheduler = fake_scheduler(
        is_trading=Mock(return_value=False),
        is_trading_day=Mock(return_value=False),
        get_trading_date=Mock(side_effect=ValueError("outside session")),
    )

    with (
        patch.object(preview_module, "StaticMinuteScheduler", return_value=scheduler),
        patch.object(
            preview_module.SchedulerManager,
            "use_scheduler",
            return_value=nullcontext(),
        ),
    ):
        result = preview_module.build_time_preview("TEST", "2026-08-16 03:00")

    assert result["weekday"] == "Sunday"
    assert result["is_trading_day"] is False
    assert result["is_trading_time"] is False
    assert result["trading_date"] is None


def test_combined_preview_remains_compatible_for_service():
    scheduler = fake_scheduler()

    with (
        patch.object(preview_module, "StaticMinuteScheduler", return_value=scheduler),
        patch.object(
            preview_module.SchedulerManager,
            "use_scheduler",
            return_value=nullcontext(),
        ),
    ):
        result = preview_module.build_calendar_preview(
            "TEST",
            start="2026-08-10",
            days_ahead=7,
            check_time="2026-08-10 21:00",
        )

    assert result["upcoming_holidays"] == ["2026-08-12"]
    check = result["check"]
    assert isinstance(check, dict)
    assert check["weekday"] == "Monday"
    assert check["is_trading_day"] is True


def test_main_holidays_command(capsys):
    payload = {
        "calendar_name": "TEST",
        "calendar_full_name": "Test Exchange",
        "timezone": "Asia/Shanghai",
        "range_start": "2026-08-10",
        "range_end": "2026-08-17",
        "upcoming_holidays": ["2026-08-12"],
    }

    with patch.object(
        preview_module, "build_holiday_preview", return_value=payload
    ) as build:
        preview_module.main(["h", "-c", "TEST", "-s", "2026-08-10", "-d", "7"])

    build.assert_called_once_with(
        "TEST",
        start="2026-08-10",
        days_ahead=7,
        scheduler_start=None,
        scheduler_end=None,
    )
    assert capsys.readouterr().out.splitlines()[-2:] == [
        "Holidays: 1",
        "  2026-08-12  Wednesday",
    ]


def test_main_defaults_to_holidays_without_command(capsys):
    payload = {
        "calendar_name": "SSE",
        "calendar_full_name": "Shanghai Stock Exchange",
        "timezone": "Asia/Shanghai",
        "range_start": "2026-08-12",
        "range_end": "2026-09-13",
        "upcoming_holidays": [],
    }

    with patch.object(
        preview_module, "build_holiday_preview", return_value=payload
    ) as build:
        preview_module.main([])

    build.assert_called_once_with(
        "SSE",
        start=None,
        days_ahead=32,
        scheduler_start=None,
        scheduler_end=None,
    )
    assert "Holidays: 0" in capsys.readouterr().out


def test_main_accepts_holiday_options_without_command():
    payload = {
        "calendar_name": "TEST",
        "calendar_full_name": "Test Exchange",
        "timezone": "Asia/Shanghai",
        "range_start": "2026-08-10",
        "range_end": "2026-08-17",
        "upcoming_holidays": [],
    }

    with patch.object(
        preview_module, "build_holiday_preview", return_value=payload
    ) as build:
        preview_module.main(["-c", "TEST", "--start", "2026-08-10", "--days", "7"])

    build.assert_called_once_with(
        "TEST",
        start="2026-08-10",
        days_ahead=7,
        scheduler_start=None,
        scheduler_end=None,
    )


def test_main_resolves_numeric_calendar_id():
    payload = {
        "calendar_name": "CN_FUTURES_2300",
        "calendar_full_name": "China Futures",
        "timezone": "Asia/Shanghai",
        "range_start": "2026-08-10",
        "range_end": "2026-08-17",
        "upcoming_holidays": [],
    }

    with patch.object(
        preview_module, "build_holiday_preview", return_value=payload
    ) as build:
        preview_module.main(["-c", "3", "--start", "2026-08-10", "--days", "7"])

    assert build.call_args.args[0] == "CN_FUTURES_2300"


def test_main_lists_calendar_ids(capsys):
    preview_module.main(["ls"])

    assert capsys.readouterr().out.splitlines() == [
        "ID  Alias  Calendar",
        "1   sse    SSE (default)",
        "2   cme    CME Globex Crypto",
        "3   f23    CN_FUTURES_2300",
        "4   f01    CN_FUTURES_0100",
        "5   f02    CN_FUTURES_0230",
    ]


def test_calendar_short_aliases():
    assert preview_module.resolve_calendar("sse") == "SSE"
    assert preview_module.resolve_calendar("CME") == "CME Globex Crypto"
    assert preview_module.resolve_calendar("f23") == "CN_FUTURES_2300"
    assert preview_module.resolve_calendar("f01") == "CN_FUTURES_0100"
    assert preview_module.resolve_calendar("f02") == "CN_FUTURES_0230"


def test_main_check_command(capsys):
    payload = {
        "calendar_name": "CN_FUTURES_2300",
        "calendar_full_name": "China Futures",
        "timezone": "Asia/Shanghai",
        "time": "2026-08-10T21:00:00+08:00",
        "weekday": "Monday",
        "is_trading_day": True,
        "is_trading_time": True,
        "trading_date": "2026-08-11",
    }

    with patch.object(
        preview_module, "build_time_preview", return_value=payload
    ) as build:
        preview_module.main(
            [
                "check",
                "2026-08-10 21:00",
                "-c",
                "CN_FUTURES_2300",
                "--scheduler-start",
                "2026-01-01",
                "--scheduler-end",
                "2027-01-01",
            ]
        )

    build.assert_called_once_with(
        "CN_FUTURES_2300",
        "2026-08-10 21:00",
        scheduler_start="2026-01-01",
        scheduler_end="2027-01-01",
    )
    assert capsys.readouterr().out.splitlines()[-4:] == [
        "Weekday:      Monday",
        "Trading day:  yes",
        "Trading time: yes",
        "Trading date: 2026-08-11",
    ]


def test_main_accepts_short_check_and_calendar_alias():
    payload = {
        "calendar_name": "CN_FUTURES_2300",
        "calendar_full_name": "China Futures",
        "timezone": "Asia/Shanghai",
        "time": "2026-08-10T21:00:00+08:00",
        "weekday": "Monday",
        "is_trading_day": True,
        "is_trading_time": True,
        "trading_date": "2026-08-11",
    }

    with patch.object(
        preview_module, "build_time_preview", return_value=payload
    ) as build:
        preview_module.main(["q", "2026-08-10 21:00", "-c", "f23"])

    assert build.call_args.args == (
        "CN_FUTURES_2300",
        "2026-08-10 21:00",
    )


def test_build_session_preview_real_calendars():
    sse = preview_module.build_session_preview("SSE")
    assert sse["calendar_name"] == "SSE"
    assert sse["session_start"] == "09:30 (T)"
    assert sse["session_end"] == "15:00 (T)"
    assert sse["total_trading_minutes"] == 240
    assert sse["friday_night_open"] is False
    assert sse["saturday_trading"] is False
    assert sse["sunday_trading"] is False
    assert sse["sunday_night_open"] is False
    assert sse["monday_session_open"] == "Monday 09:30"
    assert sse["friday_session_close"] == "Friday 15:00"

    cme = preview_module.build_session_preview("cme")
    assert cme["calendar_name"] == "CME Globex Crypto"
    assert cme["session_start"] == "17:00 (T-1)"
    assert cme["session_end"] == "16:00 (T)"
    assert cme["total_trading_minutes"] == 1380
    assert cme["friday_night_open"] is False
    assert cme["saturday_trading"] is False
    assert cme["sunday_trading"] is True
    assert "17:00" in str(cme["sunday_trading_description"])
    assert cme["sunday_night_open"] is True
    assert cme["monday_session_open"] == "Sunday 17:00"
    assert cme["friday_session_close"] == "Friday 16:00"

    f23 = preview_module.build_session_preview("f23")
    assert f23["calendar_name"] == "CN_FUTURES_2300"
    assert f23["session_start"] == "21:00 (T-1)"
    assert f23["session_end"] == "15:00 (T)"
    assert f23["total_trading_minutes"] == 345
    assert f23["friday_night_open"] is True
    assert f23["saturday_trading"] is False
    assert f23["sunday_trading"] is False
    assert f23["sunday_night_open"] is False
    assert f23["monday_session_open"] == "Friday 21:00"
    assert f23["friday_session_close"] == "Friday 15:00"

    f02 = preview_module.build_session_preview("f02")
    assert f02["calendar_name"] == "CN_FUTURES_0230"
    assert f02["total_trading_minutes"] == 555
    assert f02["friday_night_open"] is True
    assert f02["saturday_trading"] is True
    assert "00:00 - 02:30" in str(f02["saturday_trading_description"])
    assert f02["sunday_trading"] is False
    assert f02["sunday_night_open"] is False


def test_combined_preview_includes_session():
    preview = preview_module.build_calendar_preview("SSE", days_ahead=7)
    assert "upcoming_holidays" in preview
    assert "session" in preview
    session = preview["session"]
    assert isinstance(session, dict)
    assert session["calendar_name"] == "SSE"
    assert session["session_start"] == "09:30 (T)"


def test_main_calendar_command(capsys):
    preview_module.main(["calendar", "-c", "f23"])
    output = capsys.readouterr().out
    assert "CN_FUTURES_2300" in output
    assert "Session start:         21:00 (T-1)" in output
    assert "Session end:           15:00 (T)" in output
    assert "Friday night open:     yes" in output
    assert "Saturday trading:      no" in output
    assert "Sunday trading:        no" in output
    assert "Sunday night open:     no" in output
    assert "Monday session open:   Friday 21:00" in output
    assert "Friday session close:  Friday 15:00" in output


def test_main_cal_alias_and_positional(capsys):
    preview_module.main(["cal", "cme"])
    output = capsys.readouterr().out
    assert "CME Globex Crypto" in output
    assert "Sunday night open:     yes" in output
    assert "Friday night open:     no" in output


def test_main_calendars_with_positional_calendar(capsys):
    preview_module.main(["calendars", "sse"])
    output = capsys.readouterr().out
    assert "Session start:         09:30 (T)" in output
    assert "Friday night open:     no" in output
