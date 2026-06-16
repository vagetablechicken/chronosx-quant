import pandas as pd
import pytest

from tests.helpers import get_scheduler


@pytest.mark.parametrize(
    "calendar_name",
    ["CN_FUTURES_0230", "CN_FUTURES_0100", "CN_FUTURES_2300"],
)
def test_builtin_china_futures_calendar_has_no_night_session_after_holidays(
    calendar_name,
):
    scheduler = get_scheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

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
    scheduler = get_scheduler(calendar_name)

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
    scheduler = get_scheduler(calendar_name)

    def ts(value):
        return pd.Timestamp(value, tz=scheduler.tz)

    assert scheduler.is_trading(ts("2024-12-31 14:59:00"))
    assert not scheduler.is_trading(ts("2024-12-31 15:00:00"))
    assert not scheduler.is_trading(ts("2025-01-01 20:59:00"))
    assert not scheduler.is_trading(ts("2025-01-01 21:00:00"))
    assert scheduler.next_trading_time(
        ts("2025-01-01 21:00:00"), step="1min", inclusive=True
    ) == ts("2025-01-02 09:00:00")
