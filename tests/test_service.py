import sys
import types

import pytest

# Pandas imports pyarrow opportunistically; a broken local pyarrow wheel should
# not prevent service tests from collecting.
sys.modules.setdefault("pyarrow", types.SimpleNamespace(__version__="0.0.0"))

pytest.importorskip("fastapi")
pytest.importorskip("prometheus_client")
pytest.importorskip("pandas_market_calendars")

from fastapi import HTTPException  # noqa: E402
from fastapi.responses import PlainTextResponse  # noqa: E402

from chronosx_quant import __version__  # noqa: E402
from docker.service import app, build_metrics_payload, build_query_payload  # noqa: E402


def _route_endpoint(path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint
    raise AssertionError(f"Route {path} not found")


def test_root_endpoint_describes_service():
    root = _route_endpoint("/")

    assert root() == {
        "name": "chronosx-quant service",
        "version": __version__,
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


def test_build_query_payload_for_trading_time():
    payload = build_query_payload(time_value="2026-03-10T11:29:00", calendar_name="SSE")

    assert payload["server_version"] == f"chronosx-quant/{__version__}"
    assert payload["calendar_name"] == "SSE"
    assert payload["is_trading_day"] is True
    assert payload["is_trading_time"] is True
    assert payload["session_start"] == "2026-03-10T09:30:00+08:00"
    assert payload["session_end"] == "2026-03-10T15:00:00+08:00"


def test_build_query_payload_for_break_time():
    payload = build_query_payload(time_value="2026-03-10T12:00:00", calendar_name="SSE")

    assert payload["is_trading_day"] is True
    assert payload["is_trading_time"] is False
    assert payload["previous_trading_time"] == "2026-03-10T11:29:00+08:00"
    assert payload["next_trading_time"] == "2026-03-10T13:00:00+08:00"


def test_build_metrics_payload():
    payload = build_metrics_payload()

    assert "# TYPE chronosx_service_info gauge" in payload
    assert "# TYPE chronosx_trading_day gauge" in payload
    assert "# TYPE chronosx_trading_time gauge" in payload
    assert f'server_version="chronosx-quant/{__version__}"' in payload
    assert 'calendar_name="SSE",timezone="Asia/Shanghai"' in payload
    assert 'query_time="' not in payload
    assert "chronosx_service_info" in payload
    assert "chronosx_trading_day" in payload
    assert "chronosx_trading_time" in payload
    assert payload.rstrip().endswith("0")


def test_query_endpoint_returns_json():
    query = _route_endpoint("/query")
    payload = query(time_value="2026-03-10T11:29:00", calendar_name=None)

    assert payload["server_version"] == f"chronosx-quant/{__version__}"
    assert payload["is_trading_day"] is True
    assert payload["is_trading_time"] is True


def test_metrics_endpoint_returns_prometheus_text():
    metrics = _route_endpoint("/metrics")
    response = metrics()

    assert isinstance(response, PlainTextResponse)
    body = response.body.decode("utf-8")
    content_type = response.media_type

    assert "query_time=" not in body
    assert "chronosx_service_info" in body
    assert content_type.startswith("text/plain; version=0.0.4")
    assert "chronosx_trading_day" in body
    assert "chronosx_trading_time" in body
    assert body.rstrip().endswith("0")


def test_calendar_preview_endpoint_returns_upcoming_holidays():
    calendar_preview = _route_endpoint("/calendar_preview")
    payload = calendar_preview(
        calendar_name="SSE", days_ahead=32, check_time=None
    )

    assert payload["calendar_name"] == "SSE"
    assert payload["days_ahead"] == 32
    assert "calendar_full_name" in payload
    assert "latest_holidays" in payload
    assert "upcoming_holidays" in payload
    assert isinstance(payload["latest_holidays"], list)
    assert isinstance(payload["upcoming_holidays"], list)


def test_calendar_preview_endpoint_checks_trading_time():
    calendar_preview = _route_endpoint("/calendar_preview")
    payload = calendar_preview(
        calendar_name="SSE",
        days_ahead=32,
        check_time="2026-03-10 09:30",
    )

    assert payload["check"]["time"] == "2026-03-10T09:30:00+08:00"
    assert payload["check"]["weekday"] == "Tuesday"
    assert payload["check"]["is_trading_day"] is True
    assert payload["check"]["is_trading_time"] is True
    assert payload["check"]["trading_date"] == "2026-03-10"


def test_query_endpoint_rejects_invalid_time():
    query = _route_endpoint("/query")

    with pytest.raises(HTTPException) as exc_info:
        query(time_value="not-a-time", calendar_name=None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail
