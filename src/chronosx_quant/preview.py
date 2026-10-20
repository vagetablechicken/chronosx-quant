from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
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
NAME_TO_CALENDAR_ID = {name: cid for cid, name in CALENDAR_IDS.items()}
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
    assert isinstance(timestamp, pd.Timestamp)
    res = (
        timestamp.tz_localize(timezone)
        if timestamp.tzinfo is None
        else timestamp.tz_convert(timezone)
    )
    assert isinstance(res, pd.Timestamp)
    return res


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
        today if start is None else _to_calendar_timezone(start, calendar.tz).date()
    )
    end_date = start_date + timedelta(days=days_ahead)
    holiday_dates: list[date] = []
    for value in calendar.holidays().kwds["holidays"]:
        ts_val = pd.Timestamp(value)
        if isinstance(ts_val, pd.Timestamp):
            holiday_dates.append(ts_val.date())
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
        "is_trading_day": scheduler.is_trading_day(query_time),
        "is_trading_time": scheduler.is_trading(query_time),
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


def _format_day_offset(offset: int) -> str:
    if offset == 0:
        return "T"
    if offset < 0:
        return f"T{offset}"
    return f"T+{offset}"


def _find_normal_trading_week(
    scheduler: Any,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp] | None:
    schedule = getattr(scheduler, "schedule", None)
    if schedule is None or len(schedule) < 5:
        return None

    for idx in schedule.index:
        if idx.dayofweek == 0:
            tue = idx + pd.Timedelta(days=1)
            wed = idx + pd.Timedelta(days=2)
            thu = idx + pd.Timedelta(days=3)
            fri = idx + pd.Timedelta(days=4)
            next_mon = idx + pd.Timedelta(days=7)
            if (
                tue in schedule.index
                and wed in schedule.index
                and thu in schedule.index
                and fri in schedule.index
                and next_mon in schedule.index
            ):
                return idx, wed, fri, next_mon

    for idx in schedule.index:
        if idx.dayofweek == 0:
            tue = idx + pd.Timedelta(days=1)
            wed = idx + pd.Timedelta(days=2)
            thu = idx + pd.Timedelta(days=3)
            fri = idx + pd.Timedelta(days=4)
            if (
                tue in schedule.index
                and wed in schedule.index
                and thu in schedule.index
                and fri in schedule.index
            ):
                return idx, wed, fri, idx

    return None


def _session_payload(scheduler: Any) -> dict[str, object]:
    calendar = getattr(scheduler, "calendar", None)
    calendar_name = getattr(calendar, "name", str(calendar))
    calendar_full_name = getattr(calendar, "full_name", calendar_name)
    calendar_id = NAME_TO_CALENDAR_ID.get(calendar_name)
    alias = CALENDAR_SHORT_NAMES.get(calendar_id) if calendar_id else None
    tz = getattr(scheduler, "tz", getattr(calendar, "tz", "UTC"))

    target_scheduler = scheduler
    normal_week = _find_normal_trading_week(target_scheduler)
    if normal_week is None:
        try:
            sample_scheduler = StaticMinuteScheduler(
                calendar_name,
                start="2026-03-02",
                end="2026-03-16",
            )
            normal_week = _find_normal_trading_week(sample_scheduler)
            if normal_week is not None:
                target_scheduler = sample_scheduler
        except Exception:
            normal_week = None

    if normal_week is None:
        return {
            "calendar_id": calendar_id,
            "calendar_name": calendar_name,
            "calendar_full_name": calendar_full_name,
            "alias": alias,
            "timezone": str(tz),
            "session_start": "09:30 (T)",
            "session_end": "15:00 (T)",
            "session_start_time": "09:30",
            "session_start_day_offset": 0,
            "session_end_time": "15:00",
            "session_end_day_offset": 0,
            "has_night_session": False,
            "total_trading_minutes": 240,
            "total_trading_hours": "4h 00m",
            "trading_intervals": [],
            "friday_night_open": False,
            "friday_night_time": None,
            "friday_night_description": "closed on Friday night",
            "saturday_trading": False,
            "saturday_open": False,
            "saturday_trading_description": "closed on Saturday",
            "sunday_trading": False,
            "sunday_open": False,
            "sunday_trading_description": "closed on Sunday",
            "sunday_night_open": False,
            "sunday_night_time": None,
            "sunday_night_description": "closed on Sunday night",
            "monday_session_open": "Monday 09:30",
            "friday_session_close": "Friday 15:00",
        }

    mon, wed, fri, next_mon = normal_week
    schedule = target_scheduler.schedule
    wed_row = schedule.loc[wed]
    wed_open = wed_row["market_open"]
    wed_close = wed_row["market_close"]
    open_offset = (wed_open.date() - wed.date()).days
    close_offset = (wed_close.date() - wed.date()).days

    wed_intervals = [
        iv
        for iv in target_scheduler.intervals
        if iv.left >= wed_open and iv.right <= wed_close
    ]
    intervals_payload: list[dict[str, object]] = []
    total_trading_minutes = 0
    for iv in wed_intervals:
        left_offset = (iv.left.date() - wed.date()).days
        right_offset = (iv.right.date() - wed.date()).days
        duration_min = int((iv.right - iv.left).total_seconds() // 60)
        total_trading_minutes += duration_min
        intervals_payload.append(
            {
                "start": iv.left.strftime("%H:%M"),
                "start_day": _format_day_offset(left_offset),
                "end": iv.right.strftime("%H:%M"),
                "end_day": _format_day_offset(right_offset),
                "duration_minutes": duration_min,
                "display": (
                    f"{iv.left.strftime('%H:%M')} ({_format_day_offset(left_offset)}) - "
                    f"{iv.right.strftime('%H:%M')} ({_format_day_offset(right_offset)})"
                ),
            }
        )

    hours = total_trading_minutes // 60
    minutes = total_trading_minutes % 60
    total_hours_str = f"{hours}h {minutes:02d}m" if hours > 0 else f"{minutes}m"

    fri_start = pd.Timestamp(fri.date(), tz=target_scheduler.tz) + pd.Timedelta(hours=18)
    fri_end = pd.Timestamp(fri.date(), tz=target_scheduler.tz) + pd.Timedelta(
        hours=23, minutes=59
    )
    fri_night_intervals = [
        iv
        for iv in target_scheduler.intervals
        if iv.left <= fri_end and iv.right > fri_start
    ]
    friday_night_open = len(fri_night_intervals) > 0
    if friday_night_open:
        first_fri_iv = fri_night_intervals[0]
        friday_night_time = first_fri_iv.left.strftime("%H:%M")
        fri_close_day = first_fri_iv.right.strftime("%A %H:%M")
        friday_night_description = (
            f"opens Friday {friday_night_time}, closes {fri_close_day}, part of Monday session"
        )
    else:
        friday_night_time = None
        friday_night_description = "closed on Friday night"

    sat_date = (fri + pd.Timedelta(days=1)).date()
    sat_start = pd.Timestamp(sat_date, tz=target_scheduler.tz)
    sat_end = sat_start + pd.Timedelta(days=1)
    sat_intervals = [
        iv
        for iv in target_scheduler.intervals
        if iv.left < sat_end and iv.right > sat_start
    ]
    saturday_trading = len(sat_intervals) > 0
    if saturday_trading:
        sat_ranges = []
        for iv in sat_intervals:
            iv_start = max(iv.left, sat_start)
            iv_end = min(iv.right, sat_end)
            start_str = iv_start.strftime("%H:%M")
            end_str = "24:00" if iv_end == sat_end else iv_end.strftime("%H:%M")
            sat_ranges.append(f"{start_str} - {end_str}")
        saturday_trading_description = ", ".join(sat_ranges)
    else:
        saturday_trading_description = "closed on Saturday"

    sun_date = (next_mon - pd.Timedelta(days=1)).date()
    sun_start = pd.Timestamp(sun_date, tz=target_scheduler.tz)
    sun_end = sun_start + pd.Timedelta(days=1)
    sun_intervals = [
        iv
        for iv in target_scheduler.intervals
        if iv.left < sun_end and iv.right > sun_start
    ]
    sunday_trading = len(sun_intervals) > 0
    if sunday_trading:
        sun_ranges = []
        for iv in sun_intervals:
            iv_start = max(iv.left, sun_start)
            iv_end = min(iv.right, sun_end)
            start_str = iv_start.strftime("%H:%M")
            end_str = "24:00" if iv_end == sun_end else iv_end.strftime("%H:%M")
            sun_ranges.append(f"{start_str} - {end_str}")
        sunday_trading_description = ", ".join(sun_ranges)
    else:
        sunday_trading_description = "closed on Sunday"

    sunday_night_open = any(
        iv.left <= sun_end and iv.right > (sun_start + pd.Timedelta(hours=17))
        for iv in sun_intervals
    )
    if sunday_night_open:
        first_sun_iv = [
            iv
            for iv in sun_intervals
            if iv.left <= sun_end and iv.right > (sun_start + pd.Timedelta(hours=17))
        ][0]
        sunday_night_time = first_sun_iv.left.strftime("%H:%M")
        sunday_night_description = (
            f"opens Sunday {sunday_night_time}, part of Monday session"
        )
    else:
        sunday_night_time = None
        sunday_night_description = "closed on Sunday night"

    mon_open = (
        schedule.loc[next_mon, "market_open"]
        if next_mon in schedule.index
        else schedule.loc[mon, "market_open"]
    )
    fri_close = schedule.loc[fri, "market_close"]

    has_night_session = open_offset < 0 or any(
        iv["start_day"] == "T-1" or int(str(iv["start"]).split(":")[0]) >= 18
        for iv in intervals_payload
    )

    return {
        "calendar_id": calendar_id,
        "calendar_name": calendar_name,
        "calendar_full_name": calendar_full_name,
        "alias": alias,
        "timezone": str(tz),
        "session_start": f"{wed_open.strftime('%H:%M')} ({_format_day_offset(open_offset)})",
        "session_end": f"{wed_close.strftime('%H:%M')} ({_format_day_offset(close_offset)})",
        "session_start_time": wed_open.strftime("%H:%M"),
        "session_start_day_offset": open_offset,
        "session_end_time": wed_close.strftime("%H:%M"),
        "session_end_day_offset": close_offset,
        "has_night_session": has_night_session,
        "total_trading_minutes": total_trading_minutes,
        "total_trading_hours": total_hours_str,
        "trading_intervals": intervals_payload,
        "friday_night_open": friday_night_open,
        "friday_night_time": friday_night_time,
        "friday_night_description": friday_night_description,
        "saturday_trading": saturday_trading,
        "saturday_open": saturday_trading,
        "saturday_trading_description": saturday_trading_description,
        "sunday_trading": sunday_trading,
        "sunday_open": sunday_trading,
        "sunday_trading_description": sunday_trading_description,
        "sunday_night_open": sunday_night_open,
        "sunday_night_time": sunday_night_time,
        "sunday_night_description": sunday_night_description,
        "monday_session_open": mon_open.strftime("%A %H:%M"),
        "friday_session_close": fri_close.strftime("%A %H:%M"),
    }


def build_session_preview(
    calendar_name: str | int,
    *,
    scheduler_start: str | pd.Timestamp | None = None,
    scheduler_end: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Return calendar session start/end, trading intervals, and weekend openings."""
    scheduler = _make_scheduler(
        calendar_name,
        scheduler_start=scheduler_start,
        scheduler_end=scheduler_end,
    )
    with SchedulerManager.use_scheduler(scheduler):
        return _session_payload(scheduler)


build_calendar_session_preview = build_session_preview


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
        result["session"] = _session_payload(scheduler)
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


def _print_session(payload: dict[str, Any]) -> None:
    id_str = f" [ID: {payload['calendar_id']}]" if payload.get("calendar_id") else ""
    alias_str = f" [alias: {payload['alias']}]" if payload.get("alias") else ""
    print(
        f"Calendar:              {payload['calendar_name']} ({payload['calendar_full_name']}){id_str}{alias_str}"
    )
    print(f"Timezone:              {payload['timezone']}")
    print(f"Session start:         {payload['session_start']}")
    print(f"Session end:           {payload['session_end']}")
    print(
        f"Trading duration:      {payload['total_trading_hours']} ({payload['total_trading_minutes']} min)"
    )
    print("Trading intervals:")
    for interval in payload["trading_intervals"]:
        print(f"  {interval['display']:<26} ({interval['duration_minutes']} min)")
    fri_info = (
        f"yes ({payload['friday_night_description']})"
        if payload["friday_night_open"]
        else "no"
    )
    sat_info = (
        f"yes ({payload['saturday_trading_description']})"
        if payload.get("saturday_trading")
        else "no"
    )
    sun_info_day = (
        f"yes ({payload['sunday_trading_description']})"
        if payload.get("sunday_trading")
        else "no"
    )
    sun_info = (
        f"yes ({payload['sunday_night_description']})"
        if payload["sunday_night_open"]
        else "no"
    )
    print(f"Friday night open:     {fri_info}")
    print(f"Saturday trading:      {sat_info}")
    print(f"Sunday trading:        {sun_info_day}")
    print(f"Sunday night open:     {sun_info}")
    print(f"Monday session open:   {payload['monday_session_open']}")
    print(f"Friday session close:  {payload['friday_session_close']}")


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
        description="Inspect market-calendar holidays, timestamps, and session details."
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    calendars_cmd = commands.add_parser(
        "calendars", aliases=["ls"], help="list calendar IDs and aliases"
    )
    calendars_cmd.add_argument(
        "calendar_pos",
        nargs="?",
        type=_calendar_argument,
        metavar="CALENDAR",
        help="optional calendar ID, alias, or name to inspect (if omitted, list all)",
    )
    _add_calendar_argument(calendars_cmd)
    _add_scheduler_arguments(calendars_cmd)

    calendar_cmd = commands.add_parser(
        "calendar",
        aliases=["cal", "c", "session", "sessions", "info"],
        help="inspect calendar session start/end, trading intervals, and weekend openings",
    )
    calendar_cmd.add_argument(
        "calendar_pos",
        nargs="?",
        type=_calendar_argument,
        metavar="CALENDAR",
        help="optional calendar ID, alias, or name to inspect",
    )
    _add_calendar_argument(calendar_cmd)
    _add_scheduler_arguments(calendar_cmd)

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

    check = commands.add_parser("check", aliases=["q"], help="inspect one timestamp")
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
        calendar_target = getattr(args, "calendar_pos", None)
        if calendar_target is not None:
            payload = build_session_preview(
                calendar_target,
                scheduler_start=args.scheduler_start,
                scheduler_end=args.scheduler_end,
            )
            _print_session(payload)
            return

        print("ID  Alias  Calendar")
        for calendar_id, calendar_name in CALENDAR_IDS.items():
            default = " (default)" if calendar_id == DEFAULT_PREVIEW_CALENDAR_ID else ""
            alias = CALENDAR_SHORT_NAMES[calendar_id]
            print(f"{calendar_id:<3} {alias:<6} {calendar_name}{default}")
        return

    if args.command in {"calendar", "cal", "c", "session", "sessions", "info"}:
        calendar_target = getattr(args, "calendar_pos", None) or args.calendar
        payload = build_session_preview(
            calendar_target,
            scheduler_start=args.scheduler_start,
            scheduler_end=args.scheduler_end,
        )
        _print_session(payload)
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
