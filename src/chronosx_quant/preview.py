from __future__ import annotations

import pandas as pd

from . import __version__
from .scheduler import SchedulerManager, StaticMinuteScheduler


def build_calendar_preview(
    calendar_name: str, *, days_ahead: int = 32
) -> dict[str, object]:
    with SchedulerManager.use_scheduler(StaticMinuteScheduler(calendar_name)):
        cal = SchedulerManager.get_scheduler().calendar
        holidays = cal.holidays()
        today = pd.Timestamp.now().date()
        end_date = today + pd.Timedelta(days=days_ahead)
        holiday_dates = [pd.Timestamp(h).date() for h in holidays.kwds["holidays"]]
        holidays_in_range = [
            holiday.isoformat()
            for holiday in holiday_dates
            if holiday >= today and holiday < end_date
        ]

        return {
            "calendar_name": calendar_name,
            "calendar_full_name": cal.full_name,
            "today": today.isoformat(),
            "days_ahead": days_ahead,
            "range_end": end_date.isoformat(),
            "latest_holidays": [holiday.isoformat() for holiday in holiday_dates[-5:]],
            "upcoming_holidays": holidays_in_range,
        }


def calendar_preview(calendar_name):
    preview = build_calendar_preview(calendar_name)
    print(f"---{preview['calendar_full_name']}---")
    print(f"latest holidays {preview['latest_holidays']}")
    print(
        f"next {preview['days_ahead']} days [{preview['today']}, {preview['range_end']}) have holidays: "
        f"{preview['upcoming_holidays']}"
    )


def main():
    import pandas_market_calendars as mcal

    print(
        f"chronosx_quant={__version__}, dependency: "
        f"pandas={pd.__version__}, pandas_market_calendars={mcal.__version__}"
    )
    calendar_preview("SSE")
    calendar_preview("CME Globex Crypto")


if __name__ == "__main__":  # pragma: no cover
    main()
