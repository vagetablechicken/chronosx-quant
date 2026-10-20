from __future__ import annotations

from typing import Callable

import pytest

from chronosx_quant.performance import PerformanceRegistry
from chronosx_quant.scheduler import StaticMinuteScheduler
from tests.helpers import get_scheduler as _get_scheduler
from tests.helpers import use_tz


@pytest.fixture(autouse=True)
def clear_performance_registry():
    PerformanceRegistry.clear()
    yield
    PerformanceRegistry.clear()


@pytest.fixture(autouse=True)
def auto_calendar_tz_context(request: pytest.FixtureRequest):
    """Automatically activate the timezone context if calendar_name or scheduler is in test parameters."""
    if "calendar_name" in request.fixturenames:
        try:
            cal_name = request.getfixturevalue("calendar_name")
            if isinstance(cal_name, str):
                scheduler = _get_scheduler(cal_name)
                with use_tz(scheduler):
                    yield
                return
        except Exception:
            pass
    elif "scheduler" in request.fixturenames:
        try:
            scheduler = request.getfixturevalue("scheduler")
            with use_tz(scheduler):
                yield
            return
        except Exception:
            pass
    yield


@pytest.fixture
def scheduler(request: pytest.FixtureRequest) -> StaticMinuteScheduler:
    """Fixture providing a cached StaticMinuteScheduler based on the test's calendar_name."""
    if "calendar_name" in request.fixturenames:
        cal_name = request.getfixturevalue("calendar_name")
        return _get_scheduler(cal_name)
    raise ValueError(
        "Fixture 'scheduler' requires 'calendar_name' to be parametrized in the test"
    )


@pytest.fixture
def get_scheduler() -> Callable[[str], StaticMinuteScheduler]:
    """Fixture providing the get_scheduler function directly as a test argument."""
    return _get_scheduler
