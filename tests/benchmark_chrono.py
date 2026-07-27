import pytest
from chronosx_quant import __version__
from chronosx_quant.mock import travel
from chronosx_quant.scheduler import StaticMinuteScheduler, SchedulerManager
from chronosx_quant.time import ChronoTime


CALENDARS = ["SSE", "CME Globex Crypto", "ICE", "CN_FUTURES_2300"]
SCHEDULE_WINDOWS = [
    pytest.param("2023-01-01", "2025-12-31", id="3_years"),
    pytest.param("2020-01-01", "2025-12-31", id="6_years"),
    pytest.param("2016-01-01", "2025-12-31", id="10_years"),
]


@pytest.fixture(autouse=True)
def record_package_version(benchmark):
    benchmark.extra_info["chronosx_quant_version"] = __version__


@pytest.fixture(params=CALENDARS, scope="session")
def switch_scheduler(request):
    """
    Switch the active scheduler for each benchmark case.

    ``request.param`` iterates over the entries in ``CALENDARS``.
    """
    name = request.param
    # The benchmark suite constructs schedulers by calendar name.
    scheduler = StaticMinuteScheduler(name)

    with SchedulerManager.use_scheduler(scheduler):
        yield scheduler


@pytest.fixture
def t_start(switch_scheduler):
    return ChronoTime("2026-03-10T09:30:00")


def test_perf_init(benchmark):
    benchmark(ChronoTime, "2026-03-10T09:30:00")


def test_perf_jump(benchmark, t_start):
    # This triggers full schedule expansion in current implementation
    benchmark(t_start.shift, 100)


def test_perf_is_trading(benchmark, t_start):
    benchmark(t_start.is_trading)


def test_perf_is_trading_day(benchmark, t_start):
    benchmark(t_start.is_trading_day)


def test_perf_trading_times(benchmark, t_start):
    t_end = "2026-03-10T10:30:00"
    benchmark(t_start.trading_times, t_end)


def test_perf_previous_trading_time(benchmark, t_start):
    benchmark(t_start.previous_trading_time)


def test_perf_next_trading_time(benchmark, t_start):
    benchmark(t_start.next_trading_time)


def record_scheduler_info(
    benchmark,
    scheduler,
    schedule_start,
    schedule_end,
):
    info = scheduler.info
    benchmark.extra_info.update(
        {
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "session_intervals_count": info.session_intervals_count,
            "session_intervals_memory_bytes": info.session_intervals_memory_bytes,
            "intervals_count": info.intervals_count,
            "intervals_memory_bytes": info.intervals_memory_bytes,
            "trading_minutes_count": info.trading_minutes_count,
            "trading_minutes_memory_bytes": info.trading_minutes_memory_bytes,
            "total_memory_bytes": info.total_memory_bytes,
        }
    )


@pytest.mark.parametrize(("schedule_start", "schedule_end"), SCHEDULE_WINDOWS)
def test_perf_get_trading_date_by_schedule_size(
    benchmark,
    monkeypatch,
    schedule_start,
    schedule_end,
):
    monkeypatch.setenv("SCHEDULE_START", schedule_start)
    monkeypatch.setenv("SCHEDULE_END", schedule_end)
    scheduler = StaticMinuteScheduler("SSE")
    query_time = scheduler.session_intervals[-1].left
    record_scheduler_info(benchmark, scheduler, schedule_start, schedule_end)

    result = benchmark(scheduler.get_trading_date, query_time)
    assert result == scheduler.schedule.index[-1]


@pytest.mark.parametrize(("schedule_start", "schedule_end"), SCHEDULE_WINDOWS)
def test_perf_to_session_start_by_schedule_size(
    benchmark,
    monkeypatch,
    schedule_start,
    schedule_end,
):
    monkeypatch.setenv("SCHEDULE_START", schedule_start)
    monkeypatch.setenv("SCHEDULE_END", schedule_end)
    scheduler = StaticMinuteScheduler("SSE")
    query_time = scheduler.session_intervals[-1].left
    record_scheduler_info(benchmark, scheduler, schedule_start, schedule_end)

    result = benchmark(scheduler.to_session_start, query_time)
    assert result == scheduler.schedule["market_open"].iloc[-1]


@pytest.mark.parametrize(("schedule_start", "schedule_end"), SCHEDULE_WINDOWS)
def test_perf_to_session_end_by_schedule_size(
    benchmark,
    monkeypatch,
    schedule_start,
    schedule_end,
):
    monkeypatch.setenv("SCHEDULE_START", schedule_start)
    monkeypatch.setenv("SCHEDULE_END", schedule_end)
    scheduler = StaticMinuteScheduler("SSE")
    query_time = scheduler.session_intervals[-1].left
    record_scheduler_info(benchmark, scheduler, schedule_start, schedule_end)

    result = benchmark(scheduler.to_session_end, query_time)
    assert result == scheduler.schedule["market_close"].iloc[-1]


def test_perf_now(benchmark, switch_scheduler):
    """Benchmark real time with each scheduler provided by ``switch_scheduler``."""
    result = benchmark(ChronoTime.now)
    assert isinstance(result, ChronoTime)


def test_perf_now_with_travel(benchmark, t_start):
    """Benchmark mocked time with the same scheduler parameterization.

    The ``t_start`` fixture depends on ``switch_scheduler``, so this test runs
    once for every calendar in ``CALENDARS`` just like ``test_perf_now``.
    """
    with travel(t_start):
        result = benchmark(ChronoTime.now)

    assert result == t_start
