from unittest.mock import patch

import chronosx_quant.performance as performance_module
from chronosx_quant.performance import PerformanceRegistry, performance


def test_performance_supports_metric_level_configuration():
    perf_counter_values = iter([10.0, 10.0006, 20.0, 20.0048])

    with patch.object(
        performance_module.time,
        "perf_counter",
        side_effect=lambda: next(perf_counter_values),
    ):
        with performance(
            "configured",
            min_value_us=500,
            max_value_us=4000,
            significant_figures=4,
        ):
            pass
        with performance(
            "configured",
            min_value_us=500,
            max_value_us=4000,
            significant_figures=4,
        ):
            pass

    assert PerformanceRegistry.get_count("configured") == 2
    assert PerformanceRegistry.get_config("configured").min_value_us == 500
    assert PerformanceRegistry.get_config("configured").max_value_us == 4000
    assert PerformanceRegistry.get_config("configured").significant_figures == 4
    assert PerformanceRegistry.get_percentile("configured", 0.5) >= 500
    assert 4000 <= PerformanceRegistry.get_percentile("configured", 0.99) <= 4095


def test_registry_default_configuration_can_be_overridden():
    PerformanceRegistry.configure_default(
        min_value_us=10,
        max_value_us=1_000_000,
        significant_figures=2,
    )

    config = PerformanceRegistry.get_config("new-metric")
    backend = PerformanceRegistry.get_backend("new-metric")

    assert config.min_value_us == 10
    assert config.max_value_us == 1_000_000
    assert config.significant_figures == 2
    assert backend.lowest_trackable_value == 10
    assert backend.highest_trackable_value == 1_000_000
