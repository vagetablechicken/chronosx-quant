import time
from unittest.mock import patch

import pytest

import chronosx_quant.performance as performance_module
from chronosx_quant.performance import performance, PerformanceRegistry


@pytest.fixture(autouse=True)
def clear_performance_registry():
    PerformanceRegistry.clear()
    yield
    PerformanceRegistry.clear()


def test_performance():
    assert len(PerformanceRegistry._metrics) == 0

    @performance("test")
    def f1():
        time.sleep(0.1)

    for _ in range(10):
        f1()
    assert PerformanceRegistry.get_count("test") == 10
    assert 100 <= PerformanceRegistry.get_percentile("test", 0.9)
    report = PerformanceRegistry.get_report("test")
    assert "test" in report
    assert "count=10" in report

    report = PerformanceRegistry.full_report()
    # one line
    assert len(report.splitlines()) == 1
    assert "test" in report
    assert "count=10" in report


def test_generator_performance_records_source_time_only():
    perf_counter_values = iter([10.0, 10.003, 20.0, 20.004, 30.0, 30.0])

    @performance("generator")
    def generate():
        yield 1
        yield 2

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        with patch.object(performance_module.PerformanceRegistry, "update") as update:
            assert list(generate()) == [1, 2]

    update.assert_called_once()
    name, elapsed_ms = update.call_args.args
    assert name == "generator"
    assert elapsed_ms == pytest.approx(7.0)


def test_generator_performance_updates_when_closed_early():
    perf_counter_values = iter([10.0, 10.002])

    @performance("generator")
    def generate():
        yield 1
        yield 2

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        with patch.object(performance_module.PerformanceRegistry, "update") as update:
            gen = generate()
            assert next(gen) == 1
            gen.close()

    update.assert_called_once()
    name, elapsed_ms = update.call_args.args
    assert name == "generator"
    assert elapsed_ms == pytest.approx(2.0)
