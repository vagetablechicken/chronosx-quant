from __future__ import annotations

import pytest

from chronosx_quant.performance import PerformanceRegistry


@pytest.fixture(autouse=True)
def clear_performance_registry():
    PerformanceRegistry.clear()
    yield
    PerformanceRegistry.clear()
