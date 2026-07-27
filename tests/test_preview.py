from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pandas as pd

import chronosx_quant.preview as preview_module


class FixedTimestamp(pd.Timestamp):
    @classmethod
    def now(cls, tz=None):
        return cls("2026-03-10")


def test_build_calendar_preview_filters_upcoming_holidays():
    holidays = [
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-03-09"),
        pd.Timestamp("2026-03-10"),
        pd.Timestamp("2026-04-10"),
        pd.Timestamp("2026-04-11"),
    ]
    calendar = SimpleNamespace(
        full_name="Test Exchange",
        holidays=lambda: SimpleNamespace(kwds={"holidays": holidays}),
    )
    scheduler = SimpleNamespace(calendar=calendar)
    fake_pandas = SimpleNamespace(Timestamp=FixedTimestamp, Timedelta=pd.Timedelta)

    with (
        patch.object(preview_module, "pd", fake_pandas),
        patch.object(
            preview_module,
            "StaticMinuteScheduler",
            return_value=scheduler,
        ) as scheduler_type,
        patch.object(
            preview_module.SchedulerManager,
            "use_scheduler",
            return_value=nullcontext(),
        ) as use_scheduler,
        patch.object(
            preview_module.SchedulerManager,
            "get_scheduler",
            return_value=scheduler,
        ),
    ):
        result = preview_module.build_calendar_preview("TEST", days_ahead=32)

    scheduler_type.assert_called_once_with("TEST")
    use_scheduler.assert_called_once_with(scheduler)
    assert result == {
        "calendar_name": "TEST",
        "calendar_full_name": "Test Exchange",
        "today": "2026-03-10",
        "days_ahead": 32,
        "range_end": "2026-04-11",
        "latest_holidays": [
            "2026-01-01",
            "2026-03-09",
            "2026-03-10",
            "2026-04-10",
            "2026-04-11",
        ],
        "upcoming_holidays": ["2026-03-10", "2026-04-10"],
    }


def test_calendar_preview_prints_human_readable_summary(capsys):
    payload = {
        "calendar_full_name": "Test Exchange",
        "latest_holidays": ["2026-01-01"],
        "days_ahead": 32,
        "today": "2026-03-10",
        "range_end": "2026-04-11",
        "upcoming_holidays": ["2026-04-10"],
    }

    with patch.object(
        preview_module,
        "build_calendar_preview",
        return_value=payload,
    ) as build_preview:
        preview_module.calendar_preview("TEST")

    build_preview.assert_called_once_with("TEST")
    assert capsys.readouterr().out.splitlines() == [
        "---Test Exchange---",
        "latest holidays ['2026-01-01']",
        ("next 32 days [2026-03-10, 2026-04-11) have holidays: ['2026-04-10']"),
    ]


def test_main_prints_versions_and_previews_default_calendars(capsys):
    calendar_preview = Mock()

    with patch.object(preview_module, "calendar_preview", calendar_preview):
        preview_module.main()

    output = capsys.readouterr().out
    assert f"chronosx_quant={preview_module.__version__}" in output
    assert f"pandas={pd.__version__}" in output
    assert "pandas_market_calendars=" in output
    assert calendar_preview.call_args_list == [
        call("SSE"),
        call("CME Globex Crypto"),
    ]
