from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from contextlib import contextmanager
from threading import Lock

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from chronosx_quant import __version__
from chronosx_quant.preview import build_calendar_preview
from chronosx_quant.scheduler import (
    SchedulerManager,
    StaticMinuteScheduler,
    get_default_calendar_name,
)
from chronosx_quant.time import ChronoTime

DEFAULT_HOST = os.getenv("HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("PORT", "8000"))
DEFAULT_CALENDAR_NAME = get_default_calendar_name()

_SCHEDULER_CACHE: dict[str, StaticMinuteScheduler] = {}
_SCHEDULER_LOCK = Lock()


@dataclass(frozen=True)
class TradingSnapshot:
    server_version: str
    calendar_name: str
    timezone: str
    query_time: str
    is_trading_day: bool
    is_trading_time: bool
    session_start: str | None
    session_end: str | None
    previous_trading_time: str | None
    next_trading_time: str | None


def _isoformat(value: pd.Timestamp | None) -> str | None:
    return None if value is None else value.isoformat()


def _get_scheduler(calendar_name: str) -> StaticMinuteScheduler:
    with _SCHEDULER_LOCK:
        scheduler = _SCHEDULER_CACHE.get(calendar_name)
        if scheduler is None:
            scheduler = StaticMinuteScheduler(calendar_name)
            _SCHEDULER_CACHE[calendar_name] = scheduler
        return scheduler


@contextmanager
def _use_scheduler(calendar_name: str):
    with SchedulerManager.use_scheduler(_get_scheduler(calendar_name)):
        yield SchedulerManager.get_scheduler()


def _session_bounds_for_day(
    scheduler: StaticMinuteScheduler, time: ChronoTime
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    day_start = time.normalize()
    day_end = day_start + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    target_interval = pd.Interval(day_start, day_end, closed="left")
    overlaps = scheduler.session_intervals.overlaps(target_interval)
    if not overlaps.any():
        return None, None

    trading_day = scheduler.schedule.loc[overlaps].iloc[0]
    return trading_day["market_open"], trading_day["market_close"]


def _build_trading_snapshot(
    *, time_value: str | None = None, calendar_name: str | None = None
) -> TradingSnapshot:
    active_calendar = calendar_name or DEFAULT_CALENDAR_NAME
    server_version = f"chronosx-quant/{__version__}"

    with _use_scheduler(active_calendar) as scheduler:
        query_time = ChronoTime.now() if time_value is None else ChronoTime(time_value)
        is_trading_day = bool(query_time.is_trading_day())
        is_trading_time = bool(query_time.is_trading())
        session_start, session_end = _session_bounds_for_day(scheduler, query_time)

        return TradingSnapshot(
            server_version=server_version,
            calendar_name=active_calendar,
            timezone=str(scheduler.tz),
            query_time=query_time.isoformat(),
            is_trading_day=is_trading_day,
            is_trading_time=is_trading_time,
            session_start=_isoformat(session_start),
            session_end=_isoformat(session_end),
            previous_trading_time=_isoformat(
                query_time.previous_trading_time(inclusive=True)
            ),
            next_trading_time=_isoformat(query_time.next_trading_time(inclusive=True)),
        )


def build_query_payload(
    *, time_value: str | None = None, calendar_name: str | None = None
) -> dict[str, object]:
    return asdict(
        _build_trading_snapshot(time_value=time_value, calendar_name=calendar_name)
    )


def build_metrics_payload() -> str:
    snapshot = _build_trading_snapshot()
    registry = CollectorRegistry()
    label_names = ("calendar_name", "timezone")
    label_values = (
        snapshot.calendar_name,
        snapshot.timezone,
    )

    service_info = Gauge(
        "chronosx_service_info",
        "Static service metadata.",
        labelnames=(*label_names, "server_version"),
        registry=registry,
    )
    service_info.labels(*label_values, snapshot.server_version).set(1)

    is_trading_day = Gauge(
        "chronosx_trading_day",
        "Whether the evaluated time falls on a trading day.",
        labelnames=label_names,
        registry=registry,
    )
    is_trading_day.labels(*label_values).set(1 if snapshot.is_trading_day else 0)

    is_trading_time = Gauge(
        "chronosx_trading_time",
        "Whether the evaluated time falls inside trading hours.",
        labelnames=label_names,
        registry=registry,
    )
    is_trading_time.labels(*label_values).set(1 if snapshot.is_trading_time else 0)

    return generate_latest(registry).decode("utf-8")


def create_app() -> FastAPI:
    app = FastAPI(
        title="chronosx-quant service",
        version=__version__,
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "chronosx-quant service",
            "version": __version__,
            "status": "ok",
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/query")
    def query(
        time_value: str | None = Query(default=None, alias="time"),
        calendar_name: str | None = Query(default=None),
    ) -> dict[str, object]:
        try:
            return build_query_payload(
                time_value=time_value,
                calendar_name=calendar_name,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/calendar_preview")
    def calendar_preview(
        calendar_name: str | None = Query(default=None),
        days_ahead: int = Query(default=32, ge=1, le=366),
        check_time: str | None = Query(default=None),
    ) -> dict[str, object]:
        try:
            return build_calendar_preview(
                calendar_name or DEFAULT_CALENDAR_NAME,
                days_ahead=days_ahead,
                check_time=check_time,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> PlainTextResponse:
        try:
            payload = build_metrics_payload()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return PlainTextResponse(
            payload,
            media_type="text/plain; version=0.0.4",
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    print(
        f"chronosx-quant service listening on http://{DEFAULT_HOST}:{DEFAULT_PORT}",
        flush=True,
    )
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)


if __name__ == "__main__":
    main()
