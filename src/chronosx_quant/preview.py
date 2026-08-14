from __future__ import annotations

import argparse
import sys
from typing import Any

import pandas as pd

from . import __version__
from .scheduler import SchedulerManager, StaticMinuteScheduler

CALENDAR_IDS = {
    1: "SSE",
    2: "CME Globex Crypto",
    3: "CN_FUTURES_2300",
    4: "CN_FUTURES_0100",
    5: "CN_FUTURES_0230",
}
CALENDAR_ALIASES = {
    "sse": "SSE",
    "cme": "CME Globex Crypto",
    "f23": "CN_FUTURES_2300",
    "f01": "CN_FUTURES_0100",
    "f02": "CN_FUTURES_0230",
}
CALENDAR_SHORT_NAMES = {
    1: "sse",
    2: "cme",
    3: "f23",
    4: "f01",
    5: "f02",
}
DEFAULT_PREVIEW_CALENDAR_ID = 1


def resolve_calendar(value: str | int) -> str:
    """Resolve a numeric ID or short alias, preserving full calendar names."""
    text = str(value).strip()
    alias = CALENDAR_ALIASES.get(text.lower())
    if alias is not None:
        return alias
    if not text.isdigit():
        return text
    calendar_id = int(text)
    try:
        return CALENDAR_IDS[calendar_id]
    except KeyError as exc:
        valid_ids = ", ".join(str(key) for key in CALENDAR_IDS)
        raise ValueError(
            f"Unknown calendar ID {calendar_id}; valid IDs: {valid_ids}"
        ) from exc


def _calendar_argument(value: str) -> str:
    try:
        return resolve_calendar(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _to_calendar_timezone(value: str | pd.Timestamp, timezone) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(timezone)
    return timestamp.tz_convert(timezone)


def _make_scheduler(
    calendar_name: str | int,
    *,
    scheduler_start: str | pd.Timestamp | None = None,
    scheduler_end: str | pd.Timestamp | None = None,
) -> StaticMinuteScheduler:
    kwargs: dict[str, str | pd.Timestamp] = {}
    if scheduler_start is not None:
        kwargs["start"] = scheduler_start
    if scheduler_end is not None:
        kwargs["end"] = scheduler_end
    return StaticMinuteScheduler(resolve_calendar(calendar_name), **kwargs)


def _holiday_payload(
    scheduler: StaticMinuteScheduler,
    *,
    start: str | pd.Timestamp | None,
    days_ahead: int,
) -> dict[str, object]:
    calendar = scheduler.calendar
    today = pd.Timestamp.now(tz=calendar.tz).date()
    start_date = (
        today
        if start is None
        else _to_calendar_timezone(start, calendar.tz).date()
    )
    end_date = start_date + pd.Timedelta(days=days_ahead)
    holiday_dates = [
        pd.Timestamp(value).date()
        for value in calendar.holidays().kwds["holidays"]
    ]
    holidays_in_range = [
        holiday.isoformat()
        for holiday in holiday_dates
        if start_date <= holiday < end_date
    ]
    return {
        "calendar_name": calendar.name,
        "calendar_full_name": calendar.full_name,
        "timezone": str(calendar.tz),
        "today": today.isoformat(),
        "range_start": start_date.isoformat(),
        "days_ahead": days_ahead,
        "range_end": end_date.isoformat(),
        "latest_holidays": [holiday.isoformat() for holiday in holiday_dates[-5:]],
        "upcoming_holidays": holidays_in_range,
    }


def _time_payload(
    scheduler: StaticMinuteScheduler,
    value: str | pd.Timestamp,
) -> dict[str, object]:
    query_time = _to_calendar_timezone(value, scheduler.tz)
    try:
        trading_date = scheduler.get_trading_date(query_time)
    except ValueError:
        trading_date = None

    return {
        "calendar_name": scheduler.calendar.name,
        "calendar_full_name": scheduler.calendar.full_name,
        "timezone": str(scheduler.tz),
        "time": query_time.isoformat(),
        "date": query_time.date().isoformat(),
        "weekday": query_time.day_name(),
        "is_trading_day": bool(scheduler.is_trading_day(query_time)),
        "is_trading_time": bool(scheduler.is_trading(query_time)),
        "trading_date": (
            trading_date.date().isoformat() if trading_date is not None else None
        ),
    }


def build_holiday_preview(
    calendar_name: str | int,
    *,
    start: str | pd.Timestamp | None = None,
    days_ahead: int = 32,
    scheduler_start: str | pd.Timestamp | None = None,
    scheduler_end: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Return holidays in ``[start, start + days_ahead)``."""
    if days_ahead < 1:
        raise ValueError("days_ahead must be at least 1")
    scheduler = _make_scheduler(
        calendar_name,
        scheduler_start=scheduler_start,
        scheduler_end=scheduler_end,
    )
    return _holiday_payload(scheduler, start=start, days_ahead=days_ahead)


def build_time_preview(
    calendar_name: str | int,
    value: str | pd.Timestamp,
    *,
    scheduler_start: str | pd.Timestamp | None = None,
    scheduler_end: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Return trading-calendar information about one timestamp."""
    scheduler = _make_scheduler(
        calendar_name,
        scheduler_start=scheduler_start,
        scheduler_end=scheduler_end,
    )
    with SchedulerManager.use_scheduler(scheduler):
        return _time_payload(scheduler, value)


def build_calendar_preview(
    calendar_name: str | int,
    *,
    start: str | pd.Timestamp | None = None,
    days_ahead: int = 32,
    scheduler_start: str | pd.Timestamp | None = None,
    scheduler_end: str | pd.Timestamp | None = None,
    check_time: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Backward-compatible combined preview used by the HTTP service."""
    if days_ahead < 1:
        raise ValueError("days_ahead must be at least 1")
    scheduler = _make_scheduler(
        calendar_name,
        scheduler_start=scheduler_start,
        scheduler_end=scheduler_end,
    )
    with SchedulerManager.use_scheduler(scheduler):
        result = _holiday_payload(scheduler, start=start, days_ahead=days_ahead)
        if check_time is not None:
            result["check"] = _time_payload(scheduler, check_time)
        return result


def _print_holidays(payload: dict[str, Any]) -> None:
    print(f"Calendar: {payload['calendar_name']} ({payload['calendar_full_name']})")
    print(f"Timezone: {payload['timezone']}")
    print(f"Range:    [{payload['range_start']}, {payload['range_end']})")
    holidays = payload["upcoming_holidays"]
    print(f"Holidays: {len(holidays)}")
    if not holidays:
        print("  (none)")
        return
    for holiday in holidays:
        print(f"  {holiday}  {pd.Timestamp(holiday).day_name()}")


def _yes_no(value: object) -> str:
    return "yes" if value else "no"


def _print_time(payload: dict[str, Any]) -> None:
    print(f"Calendar:     {payload['calendar_name']} ({payload['calendar_full_name']})")
    print(f"Timezone:     {payload['timezone']}")
    print(f"Time:         {payload['time']}")
    print(f"Weekday:      {payload['weekday']}")
    print(f"Trading day:  {_yes_no(payload['is_trading_day'])}")
    print(f"Trading time: {_yes_no(payload['is_trading_time'])}")
    print(f"Trading date: {payload['trading_date'] or '-'}")


def _add_calendar_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--calendar",
        "--calendar-name",
        type=_calendar_argument,
        default=str(DEFAULT_PREVIEW_CALENDAR_ID),
        metavar="ID|ALIAS|NAME",
        help=(
            f"calendar ID, alias, or full name (default: {DEFAULT_PREVIEW_CALENDAR_ID}, "
            f"{CALENDAR_IDS[DEFAULT_PREVIEW_CALENDAR_ID]})"
        ),
    )


def _add_scheduler_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("scheduler window")
    group.add_argument("--scheduler-start", metavar="TIME")
    group.add_argument("--scheduler-end", metavar="TIME")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect market-calendar holidays and timestamps."
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "calendars", aliases=["ls"], help="list calendar IDs and aliases"
    )

    holidays = commands.add_parser(
        "holidays", aliases=["h"], help="list holidays in a date range"
    )
    _add_calendar_argument(holidays)
    holidays.add_argument(
        "-s",
        "--start",
        metavar="DATE",
        help="range start in the calendar timezone (default: today)",
    )
    holidays.add_argument(
        "-d",
        "--days",
        "--days-ahead",
        type=int,
        default=32,
        metavar="N",
        help="number of calendar days (default: 32)",
    )
    _add_scheduler_arguments(holidays)

    check = commands.add_parser(
        "check", aliases=["q"], help="inspect one timestamp"
    )
    check.add_argument("time", metavar="TIME", help="timestamp to inspect")
    _add_calendar_argument(check)
    _add_scheduler_arguments(check)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Holidays are the common, read-only preview. Make that command optional
    # while keeping `check` explicit and top-level help/version discoverable.
    if not arguments:
        arguments.append("holidays")
    elif arguments[0].startswith("-") and arguments[0] not in {
        "-h",
        "--help",
        "--version",
    }:
        arguments.insert(0, "holidays")
    args = parser.parse_args(arguments)

    if args.command in {"calendars", "ls"}:
        print("ID  Alias  Calendar")
        for calendar_id, calendar_name in CALENDAR_IDS.items():
            default = " (default)" if calendar_id == DEFAULT_PREVIEW_CALENDAR_ID else ""
            alias = CALENDAR_SHORT_NAMES[calendar_id]
            print(f"{calendar_id:<3} {alias:<6} {calendar_name}{default}")
        return

    if args.command in {"holidays", "h"}:
        if args.days < 1:
            parser.error("--days must be at least 1")
        payload = build_holiday_preview(
            args.calendar,
            start=args.start,
            days_ahead=args.days,
            scheduler_start=args.scheduler_start,
            scheduler_end=args.scheduler_end,
        )
        _print_holidays(payload)
        return

    payload = build_time_preview(
        args.calendar,
        args.time,
        scheduler_start=args.scheduler_start,
        scheduler_end=args.scheduler_end,
    )
    _print_time(payload)


if __name__ == "__main__":  # pragma: no cover
    main()
