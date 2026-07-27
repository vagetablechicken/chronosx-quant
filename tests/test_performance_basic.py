from itertools import chain
from unittest.mock import Mock, patch

import pytest

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


def test_report_format_does_not_include_indentation_spaces():
    perf_counter_values = iter([10.0, 10.005])

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        with performance("format-check"):
            pass

    report = PerformanceRegistry.get_report("format-check")

    assert report.startswith("format-check(us): ")
    assert "count=1, mean=" in report
    assert ", p50=" in report
    assert ", p90=" in report


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


def test_missing_metric_returns_empty_results():
    assert PerformanceRegistry.get_count("missing") == 0
    assert PerformanceRegistry.get_percentile("missing", 0.99) is None
    assert PerformanceRegistry.get_report("missing") == "missing: not found"
    assert PerformanceRegistry.full_report() == ""


def test_decorator_uses_function_qualified_name_by_default():
    perf_counter_values = iter([10.0, 10.001])

    @performance()
    def automatically_named():
        return "ok"

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        assert automatically_named() == "ok"

    assert PerformanceRegistry.get_count(automatically_named.__qualname__) == 1


def test_context_manager_generates_name_from_caller_location():
    perf_counter_values = iter([10.0, 10.001])

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        with performance() as profiler:
            pass

    assert profiler.name
    assert "test_performance_basic.py:" in profiler.name
    assert PerformanceRegistry.get_count(profiler.name) == 1


def test_recording_failure_does_not_change_decorated_function_result():
    backend = Mock()
    backend.record_value.side_effect = RuntimeError("backend unavailable")

    with patch.object(
        performance_module.PerformanceRegistry,
        "get_backend",
        return_value=backend,
    ):

        @performance("unavailable")
        def work():
            return "ok"

        assert work() == "ok"


def test_recording_failure_does_not_hide_context_exception():
    backend = Mock()
    backend.record_value.side_effect = RuntimeError("backend unavailable")

    with (
        patch.object(
            performance_module.PerformanceRegistry,
            "get_backend",
            return_value=backend,
        ),
        pytest.raises(ValueError, match="business failure"),
    ):
        with performance("unavailable"):
            raise ValueError("business failure")
