from __future__ import annotations
from dataclasses import dataclass
from functools import wraps
import inspect
import io
import time
from hdrh.histogram import HdrHistogram
from typing import Dict


@dataclass(frozen=True)
class PerformanceConfig:
    min_value_us: int = 1
    max_value_us: int = 60_000_000
    significant_figures: int = 3


class PerformanceRegistry:
    """Global storage for per-metric latency histograms."""

    _metrics: Dict[str, HdrHistogram] = {}
    _configs: Dict[str, PerformanceConfig] = {}
    _default_config = PerformanceConfig()

    @classmethod
    def configure_default(
        cls,
        *,
        min_value_us: int = 1,
        max_value_us: int = 60_000_000,
        significant_figures: int = 3,
    ) -> PerformanceConfig:
        cls._default_config = cls._build_config(
            min_value_us=min_value_us,
            max_value_us=max_value_us,
            significant_figures=significant_figures,
        )
        return cls._default_config

    @classmethod
    def configure(
        cls,
        name: str,
        *,
        min_value_us: int | None = None,
        max_value_us: int | None = None,
        significant_figures: int | None = None,
    ) -> PerformanceConfig:
        config = cls._resolve_config(
            min_value_us=min_value_us,
            max_value_us=max_value_us,
            significant_figures=significant_figures,
        )
        cls._configs[name] = config
        return config

    @classmethod
    def get_config(cls, name: str) -> PerformanceConfig:
        return cls._configs.get(name, cls._default_config)

    @classmethod
    def get_backend(
        cls, name: str, config: PerformanceConfig | None = None
    ) -> HdrHistogram:
        if name not in cls._metrics:
            resolved_config = config or cls.get_config(name)
            cls._configs.setdefault(name, resolved_config)
            cls._metrics[name] = HdrHistogram(
                resolved_config.min_value_us,
                resolved_config.max_value_us,
                resolved_config.significant_figures,
            )
        return cls._metrics[name]

    @classmethod
    def _build_config(
        cls, *, min_value_us: int, max_value_us: int, significant_figures: int
    ) -> PerformanceConfig:
        if min_value_us < 1:
            raise ValueError("min_value_us must be >= 1")
        if max_value_us < min_value_us:
            raise ValueError("max_value_us must be >= min_value_us")
        if not 1 <= significant_figures <= 5:
            raise ValueError("significant_figures must be between 1 and 5")
        return PerformanceConfig(
            min_value_us=min_value_us,
            max_value_us=max_value_us,
            significant_figures=significant_figures,
        )

    @classmethod
    def _resolve_config(
        cls,
        *,
        min_value_us: int | None = None,
        max_value_us: int | None = None,
        significant_figures: int | None = None,
    ) -> PerformanceConfig:
        return cls._build_config(
            min_value_us=(
                cls._default_config.min_value_us
                if min_value_us is None
                else min_value_us
            ),
            max_value_us=(
                cls._default_config.max_value_us
                if max_value_us is None
                else max_value_us
            ),
            significant_figures=(
                cls._default_config.significant_figures
                if significant_figures is None
                else significant_figures
            ),
        )

    @classmethod
    def get_count(cls, name: str):
        if name in cls._metrics:
            return cls._metrics[name].get_total_count()
        return 0

    @classmethod
    def get_percentile(cls, name: str, p: float):
        if name in cls._metrics:
            return cls._metrics[name].get_value_at_percentile(p * 100)
        return None

    @classmethod
    def get_report(cls, name: str):
        if name in cls._metrics:
            di = cls._metrics[name]
            return (
                f"{name}(us): sum={di.get_mean_value() * di.get_total_count()}, "
                f"count={di.get_total_count()}, mean={di.get_mean_value()}, "
                f"p50={di.get_value_at_percentile(50)}, "
                f"p90={di.get_value_at_percentile(90)}, "
                f"p99={di.get_value_at_percentile(99)}, "
                f"p999={di.get_value_at_percentile(99.9)}, "
                f"p9999={di.get_value_at_percentile(99.99)}, "
                f"max={di.get_max_value()}"
            )
        return f"{name}: not found"

    @classmethod
    def full_report(cls):
        b = io.StringIO()
        for name in cls._metrics.keys():
            b.write(f"{cls.get_report(name)}\n")
        return b.getvalue()

    @classmethod
    def clear(cls):
        cls._metrics.clear()
        cls._configs.clear()
        cls._default_config = PerformanceConfig()


class performance:
    """
    Dual-use latency profiler for decorators and ``with`` blocks.

    Usage:
        @performance("query")
        def run():
            ...

        with performance("query.build"):
            ...

    Each ``with`` block gets a fresh instance. Decorator mode keeps timing
    state inside the wrapper call frame, so overlapping calls do not share a
    mutable ``start_time`` attribute, which keeps the profiler safe for
    concurrent calls across threads.

    Generator functions are also supported. When decorating a function that
    uses ``yield``, the profiler records the elapsed time of each ``next(...)``
    step, including the final step that ends with ``StopIteration``.
    """

    def __init__(
        self,
        name: str = None,
        *,
        min_value_us: int | None = None,
        max_value_us: int | None = None,
        significant_figures: int | None = None,
    ):
        self.name = name
        self.config = PerformanceRegistry._resolve_config(
            min_value_us=min_value_us,
            max_value_us=max_value_us,
            significant_figures=significant_figures,
        )
        # don't store time here for thread-safe

    @staticmethod
    def _elapsed_us(start_time: float, min_value_us: int) -> int:
        return max(
            min_value_us,
            int((time.perf_counter() - start_time) * 1_000_000),
        )

    def __call__(self, func):
        """Build the wrapper used by ``@performance(...)``."""
        metric_name = self.name or func.__qualname__
        backend = PerformanceRegistry.get_backend(metric_name, self.config)

        # Support generator functions by recording each ``next(...)`` segment.
        if hasattr(inspect, "isgeneratorfunction") and inspect.isgeneratorfunction(
            func
        ):

            @wraps(func)
            def generator_wrapper(*args, **kwargs):
                gen = func(*args, **kwargs)
                try:
                    while True:
                        start = time.perf_counter()
                        try:
                            item = next(gen)
                        except StopIteration:
                            backend.record_value(
                                self._elapsed_us(start, self.config.min_value_us)
                            )
                            break
                        except Exception:
                            backend.record_value(
                                self._elapsed_us(start, self.config.min_value_us)
                            )
                            raise
                        backend.record_value(
                            self._elapsed_us(start, self.config.min_value_us)
                        )
                        yield item
                finally:
                    pass

            return generator_wrapper

        # Regular synchronous function.
        @wraps(func)
        def normal_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                try:
                    backend.record_value(
                        min(
                            self._elapsed_us(start_time, self.config.min_value_us),
                            self.config.max_value_us,
                        )
                    )
                except Exception:
                    pass

        return normal_wrapper

    def __enter__(self):
        """Start timing for ``with performance(...):`` usage."""
        if self.name is None:
            # Use the caller location as a fallback metric name.
            cf = inspect.currentframe().f_back
            self.name = f"{cf.f_code.co_filename.split('/')[-1]}:{cf.f_lineno}"

        self.local_start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Record elapsed time when leaving the ``with`` block."""
        try:
            PerformanceRegistry.get_backend(self.name, self.config).record_value(
                min(
                    self._elapsed_us(self.local_start, self.config.min_value_us),
                    self.config.max_value_us,
                )
            )
        except Exception:
            pass
        return False
