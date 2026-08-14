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

    scheduler_type.assert_called_once_with(
        "TEST", start="2026-01-01", end="2027-01-01"
    )
    assert result["range_start"] == "2026-08-10"
    assert result["range_end"] == "2026-08-17"
    assert result["upcoming_holidays"] == ["2026-08-12"]


def test_build_time_preview_reports_weekday_and_trading_information():
    scheduler = fake_scheduler()

    with (
        patch.object(
            preview_module, "StaticMinuteScheduler", return_value=scheduler
        ),
        patch.object(
            preview_module.SchedulerManager,
            "use_scheduler",
            return_value=nullcontext(),
        ),
    ):
        result = preview_module.build_time_preview(
            "TEST", "2026-08-10 13:00:00+00:00"
        )

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
        patch.object(
            preview_module, "StaticMinuteScheduler", return_value=scheduler
        ),
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
        patch.object(
            preview_module, "StaticMinuteScheduler", return_value=scheduler
        ),
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
        patch.object(
            preview_module, "StaticMinuteScheduler", return_value=scheduler
        ),
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
    assert result["check"]["weekday"] == "Monday"
    assert result["check"]["is_trading_day"] is True


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
        preview_module.main(
            ["-c", "TEST", "--start", "2026-08-10", "--days", "7"]
        )

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
