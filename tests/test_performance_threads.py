import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import chronosx_quant.performance as performance_module
from chronosx_quant.performance import performance


class RecordingBackend:
    def __init__(self):
        self.values = []
        self._lock = threading.Lock()

    def record_value(self, value):
        with self._lock:
            self.values.append(value)


def test_decorated_function_uses_independent_timing_per_thread():
    backend = RecordingBackend()
    durations_by_thread = {
        "worker_0": [100.0, 100.005],
        "worker_1": [200.0, 200.007],
        "worker_2": [300.0, 300.011],
        "worker_3": [400.0, 400.013],
    }
    barrier = threading.Barrier(len(durations_by_thread))

    def fake_perf_counter():
        return durations_by_thread[threading.current_thread().name].pop(0)

    with patch.object(
        performance_module.PerformanceRegistry,
        "get_backend",
        return_value=backend,
    ) as get_backend:

        @performance("threaded")
        def work():
            barrier.wait(timeout=1)
            return threading.current_thread().name

        with patch.object(
            performance_module.time,
            "perf_counter",
            side_effect=fake_perf_counter,
        ):
            with ThreadPoolExecutor(
                max_workers=4, thread_name_prefix="worker"
            ) as executor:
                results = list(executor.map(lambda _: work(), range(4)))

    assert sorted(results) == ["worker_0", "worker_1", "worker_2", "worker_3"]
    get_backend.assert_called_once_with(
        "threaded",
        performance_module.PerformanceConfig(),
    )
    assert sorted(backend.values) == [4999, 7000, 11000, 12999]


def test_with_performance_records_each_thread_separately():
    backend = RecordingBackend()
    durations_by_thread = {
        "scope_0": [10.0, 10.003],
        "scope_1": [20.0, 20.006],
        "scope_2": [30.0, 30.009],
    }
    barrier = threading.Barrier(len(durations_by_thread))

    def fake_perf_counter():
        return durations_by_thread[threading.current_thread().name].pop(0)

    def run_scope():
        barrier.wait(timeout=1)
        with performance("threaded-scope"):
            return threading.current_thread().name

    with (
        patch.object(
            performance_module.PerformanceRegistry,
            "get_backend",
            return_value=backend,
        ) as get_backend,
        patch.object(
            performance_module.time,
            "perf_counter",
            side_effect=fake_perf_counter,
        ),
    ):
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="scope") as executor:
            results = list(executor.map(lambda _: run_scope(), range(3)))

    assert sorted(results) == ["scope_0", "scope_1", "scope_2"]
    assert get_backend.call_count == 3
    assert all(
        call.args == ("threaded-scope", performance_module.PerformanceConfig())
        for call in get_backend.call_args_list
    )
    assert sorted(backend.values) == [3000, 6000, 9000]
