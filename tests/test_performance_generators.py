from unittest.mock import Mock, patch

import pytest

import chronosx_quant.performance as performance_module
from chronosx_quant.performance import performance


def test_generator_performance_records_source_time_only():
    perf_counter_values = iter([10.0, 10.003, 20.0, 20.004, 30.0, 30.0])
    backend = Mock()

    with patch.object(
        performance_module.PerformanceRegistry,
        "get_backend",
        return_value=backend,
    ) as get_backend:

        @performance("generator")
        def generate():
            yield 1
            yield 2

        with patch.object(
            performance_module.time,
            "perf_counter",
            side_effect=lambda: next(perf_counter_values),
        ):
            assert list(generate()) == [1, 2]

    get_backend.assert_called_once_with(
        "generator",
        performance_module.PerformanceConfig(),
    )
    assert backend.record_value.call_count == 3
    assert [call.args[0] for call in backend.record_value.call_args_list] == [
        3000,
        4000,
        1,
    ]


def test_generator_performance_updates_when_closed_early():
    perf_counter_values = iter([10.0, 10.002])
    backend = Mock()

    with patch.object(
        performance_module.PerformanceRegistry,
        "get_backend",
        return_value=backend,
    ) as get_backend:

        @performance("generator")
        def generate():
            yield 1
            yield 2

        with patch.object(
            performance_module.time,
            "perf_counter",
            side_effect=lambda: next(perf_counter_values),
        ):
            gen = generate()
            assert next(gen) == 1
            gen.close()

    get_backend.assert_called_once_with(
        "generator",
        performance_module.PerformanceConfig(),
    )
    backend.record_value.assert_called_once_with(2000)


def test_normal_function_records_even_when_exception_is_raised():
    perf_counter_values = iter([10.0, 10.012])
    backend = Mock()

    with patch.object(
        performance_module.PerformanceRegistry,
        "get_backend",
        return_value=backend,
    ) as get_backend:

        @performance("failing")
        def fail():
            raise RuntimeError("boom")

        with patch.object(
            performance_module.time,
            "perf_counter",
            side_effect=lambda: next(perf_counter_values),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                fail()

    get_backend.assert_called_once_with(
        "failing",
        performance_module.PerformanceConfig(),
    )
    backend.record_value.assert_called_once_with(12_000)
