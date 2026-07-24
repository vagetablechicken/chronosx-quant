from contextlib import ContextDecorator

from .time import ChronoTime


class travel(ContextDecorator):
    def __init__(self, mock_time):
        self.mock_time = ChronoTime(mock_time)

    def __enter__(self):
        ChronoTime._get_stack().append(self.mock_time)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        stack = ChronoTime._get_stack()
        if stack:
            stack.pop()
