import pytest
from chronosx_quant.mock import travel
from chronosx_quant.scheduler import StaticMinuteScheduler, SchedulerManager
from chronosx_quant.time import ChronoTime


CALENDARS = ["SSE", "CME Globex Crypto", "ICE", "CN_FUTURES_2300"]


@pytest.fixture(params=CALENDARS)
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


def test_perf_to_session_start(benchmark, t_start):
    benchmark(t_start.to_session_start)


def test_perf_to_session_end(benchmark, t_start):
    benchmark(t_start.to_session_end)


def test_travel(benchmark, t_start):
    with travel(t_start):
        benchmark(ChronoTime.now().shift, -100)
