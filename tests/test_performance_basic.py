from itertools import chain
from unittest.mock import Mock, patch

import chronosx_quant.performance as performance_module
from chronosx_quant.performance import PerformanceRegistry, performance


def test_performance():
    assert len(PerformanceRegistry._metrics) == 0

    @performance("test")
    def f1():
        return None

    perf_counter_values = iter(
        chain.from_iterable((float(i), float(i) + 0.1) for i in range(10, 20))
    )

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        for _ in range(10):
            f1()

    assert PerformanceRegistry.get_count("test") == 10
    assert 100_000 <= PerformanceRegistry.get_percentile("test", 0.9)
    report = PerformanceRegistry.get_report("test")
    assert "test" in report
    assert "count=10" in report

    report = PerformanceRegistry.full_report()
    assert len(report.splitlines()) == 1
    assert "test" in report
    assert "count=10" in report


def test_with_performance_accumulates_total_time_in_registry():
    perf_counter_values = iter([10.0, 10.005, 20.0, 20.009, 30.0, 30.012])

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        with performance("scoped"):
            pass
        with performance("scoped"):
            pass
        with performance("scoped"):
            pass

    assert PerformanceRegistry.get_count("scoped") == 3
    assert PerformanceRegistry.get_percentile("scoped", 0.5) >= 5000
    report = PerformanceRegistry.get_report("scoped")
    assert "count=3" in report
    assert "max=12007" in report


def test_normal_function_caps_elapsed_time_at_sixty_seconds_in_us():
    perf_counter_values = iter([10.0, 75.0])
    backend = Mock()

    with patch.object(
        performance_module.PerformanceRegistry,
        "get_backend",
        return_value=backend,
    ):

        @performance("slow")
        def slow():
            return "ok"

        with patch.object(
            performance_module.time,
            "perf_counter",
            side_effect=lambda: next(perf_counter_values),
        ):
            assert slow() == "ok"

    backend.record_value.assert_called_once_with(60_000_000)
