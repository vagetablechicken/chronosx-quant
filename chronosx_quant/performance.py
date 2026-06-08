from __future__ import annotations
from functools import wraps
import inspect
import io
import time
from fastdigest import TDigest
from contextlib import ContextDecorator
from typing import Dict


class PerformanceRegistry:
    """全局存储不同函数的统计数据"""

    _metrics: Dict[str, TDigest] = {}

    @classmethod
    def update(cls, name: str, value: float):
        if name not in cls._metrics:
            cls._metrics[name] = TDigest()
        cls._metrics[name].update(value)

    @classmethod
    def get_count(cls, name: str):
        if name in cls._metrics:
            return cls._metrics[name].n_values
        return 0

    @classmethod
    def get_percentile(cls, name: str, p: float):
        if name in cls._metrics:
            return cls._metrics[name].percentile(p * 100)
        return None

    @classmethod
    def get_report(cls, name: str):
        if name in cls._metrics:
            di = cls._metrics[name]
            return f"{name}: sum={di.sum()}, count={di.n_values}, mean={di.mean()}, p50={di.percentile(50)}, p90={di.percentile(90)}, p99={di.percentile(99)}, p999={di.percentile(99.9)}, p9999={di.percentile(99.99)}, max={di.max()}"
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


class performance(ContextDecorator):
    def __init__(self, name: str = None):
        self.name = name
        self.start_wall = 0.0

    def __call__(self, func):
        # 当作为装饰器使用时，如果没传 name，自动获取函数名
        if self.name is None:
            self.name = func.__qualname__

        # if generator function
        if inspect.isgeneratorfunction(func):

            @wraps(func)
            def generator_wrapper(*args, **kwargs):
                gen = func(*args, **kwargs)
                total_source_time = 0.0
                try:
                    while True:
                        start = time.perf_counter()
                        try:
                            item = next(gen)
                        except StopIteration:
                            total_source_time += time.perf_counter() - start
                            break
                        except Exception:
                            total_source_time += time.perf_counter() - start
                            raise
                        total_source_time += time.perf_counter() - start
                        yield item  # 挂起并交出控制权，暂停计时
                finally:
                    elapsed_ms = total_source_time * 1000
                    PerformanceRegistry.update(self.name, elapsed_ms)

            return generator_wrapper
        # if normal function
        return super().__call__(func)

    def __enter__(self):
        # 如果是 with 块且没传 name，尝试获取文件名和行号
        if self.name is None:
            caller_frame = inspect.currentframe().f_back
            file_name = caller_frame.f_code.co_filename.split("/")[-1]
            line_no = caller_frame.f_lineno
            self.name = f"{file_name}:{line_no}"

        self.start_wall = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed_ms = (time.perf_counter() - self.start_wall) * 1000
        PerformanceRegistry.update(self.name, elapsed_ms)
