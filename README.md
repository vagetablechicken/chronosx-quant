# Chronosx Quant

A Python library for trading calendar management, execution profiling, and temporal backtesting (Time Travel).

## Installation

Install the library:

```bash
uv build
pip install dist/chronosx_quant-*-py3-none-any.whl

# install from pypi
pip install chronosx-quant

# check holidays in the next month
uv run chronosx-preview
chronosx-preview
```

Install the extra dependencies for the HTTP service:

```bash
uv sync --group docker
```

Install the default development dependencies for tests and benchmarks:

```bash
uv sync
```

## Usage

```python
from chronosx_quant.time import ChronoTime
import pandas as pd

# use CALENDAR_NAME to select default calendar, e.g. SSE
time = ChronoTime.now()
time = ChronoTime("2026-03-09 11:29:00+08:00")

# time about trading, only support 1min step now
time.is_trading()
# move 2 steps forward(2min), auto skip breaks and weekends
# e.g. 2026-03-09 11:29:00+08:00" -> "2026-03-09 13:01:00+08:00"
time.shift(2)

# shift preserve second and microsecond
time = ChronoTime("2026-03-09 11:29:33.123456+08:00")
# 2026-03-09 11:29:33.123456+08:00" -> "2026-03-09 13:01:33.123456+08:00"
time.shift(2)

# select valid trading times from self to end
# return series of 2 items, 11:29:00 and 13:00:00
time.trading_times(end=pd.Timestamp("2026-03-09 13:01:00+08:00"))
# series can aggregate, e.g. get all date in trading series
time.trading_times(end=pd.Timestamp("2026-03-09 13:01:00+08:00")).resample('D').first()

# simpler trading day calculation
print(ChronoTime("2026-04-08").trading_day_delta("2026-04-09"))

# move to the beginning of trading session which the time belongs to
# e.g. SSE "2026-03-08 11:29:00+08:00" belongs to session '2026-03-08', so the session start is '2026-03-08 09:30:00+08:00'
# e.g. CME session '2026-03-08' starts from '2026-03-07 17:00:00-06:00', so the session start is '2026-03-07 17:00:00-06:00', not '2026-03-08 00:00:00+00:00'
time.to_session_start()

# performance profiling
from chronosx_quant.performance import performance, PerformanceRegistry
@performance("slug_name")
def f1():
    ...
f1()
# get report of this function
print(PerformanceRegistry.get_report("slug_name"))
# get report of all functions
print(PerformanceRegistry.full_report())
# if you want to reset
PerformanceRegistry.clear()

# time travel
from chronosx_quant.mock import travel
with travel("2026-03-09 11:29:00+08:00"):
    # only effect ChronoTime, datetime or pd.Timestamp still work
    # thread-local mock, thread-safe
    ChronoTime.now()
```

### Add calendar

Chronosx based on pandas_market_calendars, so it can use all calendars in the project, and support to add custom calendars.

Project custom calendars live in [chronosx_quant/calendars](./chronosx_quant/calendars).

For the China futures night-session calendars below, we intentionally diverge
from the original upstream calendar model.

The original `pandas_market_calendars` calendars do not support our multi-break
use case cleanly enough, so Chronosx forcefully extends the market-time map with
extra open/close events such as `break_start_1`, `break_end_1`, `break_start_2`,
`break_end_2`, `break_start_3`, and `break_end_3`. These calendars are meant to
be consumed by Chronosx's custom scheduler path, especially
`StaticMinuteScheduler`, which scans our custom `open_close_map` and builds
trading intervals from it.

Because of that, these are Chronosx-specific calendars. Please follow the
Chronosx calling pattern when using them:

- use them through `ChronoTime`, `SchedulerManager`, `StaticMinuteScheduler`, or the service API
- do not assume they are interchangeable with upstream built-in calendars in generic `pandas_market_calendars` workflows
- do not reuse the original single-break calendar assumptions when extending these calendars
- if you add more China futures calendars, keep the custom event naming and Chronosx scheduler contract consistent

For SHF/DCE in China, calendars have multiple breaks. These three built-in variants are available:

- `CN_FUTURES_0230`
  aliases: `SC.INE AG.SHF`, `SC.INE`, `AG.SHF`
  hours: `09:00-10:15 | 10:30-11:30 | 13:30-15:00 | 21:00-02:30+1`

- `CN_FUTURES_0100`
  aliases: `BC.INE CU.SHF`, `BC.INE`, `CU.SHF`
  hours: `09:00-10:15 | 10:30-11:30 | 13:30-15:00 | 21:00-01:00+1`

- `CN_FUTURES_2300`
  aliases: `DCE/CZC`, `DCE`, `CZC`
  hours: `09:00-10:15 | 10:30-11:30 | 13:30-15:00 | 21:00-23:00`

### Add scheduler

I use static minute scheduler for speed, don't support multi step in the same time, and don't support extend schedule time range. It's ok to add new scheduler to support multi step or dynamic time range.

## Benchmark

The benchmark suite uses `pytest-benchmark`.

Run the full benchmark file:

```bash
uv run pytest tests/benchmark_chrono.py --benchmark-only
```

Run a single benchmark:

```bash
uv run pytest tests/benchmark_chrono.py -k test_perf_is_trading --benchmark-only
```

Save benchmark results:

```bash
uv run pytest tests/benchmark_chrono.py --benchmark-only --benchmark-json=.benchmarks/chrono.json
```

Useful notes:

- `tests/benchmark_chrono.py` runs each benchmark across `SSE`, `CME Globex Crypto`, and `ICE`
- `--benchmark-only` runs only benchmark tests and skips normal tests
- if you want the usual pytest output without benchmark filtering, you can run `uv run pytest tests/benchmark_chrono.py`

Benchmark preview:

- test machine: Intel Core i9-14900HX with 5600 MT/s memory
- most operations are in the `7-100 us` range
- `trading_times` is around `40-45 us`
- the slowest operations are `to_session_start` and `to_session_end`, typically around `0.2-0.26 ms`
- no benchmark in the current preview has an average latency above `1 ms`
- benchmark results may vary across machines and Python versions

## Docker Service

The container service is implemented with `FastAPI` and exposes a JSON query API plus a Prometheus-compatible metrics endpoint.

Build and run with Docker:

```bash
docker build -t chronosx-quant .
docker run --rm -p 8000:8000 -e CALENDAR_NAME=SSE chronosx-quant
```

Run locally without Docker:

```bash
uv run --group docker python -m docker.service
```

Health check:

```bash
curl "http://localhost:8000/health"
```

Query the current trading status:

```bash
curl "http://localhost:8000/query"
```

Query a specific time:

```bash
curl "http://localhost:8000/query?time=2026-03-10T11:29:00"
curl "http://localhost:8000/query?time=2026-03-10T12:00:00&calendar_name=SSE"
```

The JSON response includes:

- `server_version`
- `calendar_name`
- `timezone`
- `query_time`
- `is_trading_day`
- `is_trading_time`
- `session_start`
- `session_end`
- `previous_trading_time`
- `next_trading_time`

Calendar preview:

```bash
curl "http://localhost:8000/calendar_preview"
curl "http://localhost:8000/calendar_preview?calendar_name=SSE&days_ahead=32"
```

The preview response helps verify upcoming holidays and recent holiday definitions for a calendar. It includes:

- `calendar_name`
- `calendar_full_name`
- `today`
- `days_ahead`
- `range_end`
- `latest_holidays`
- `upcoming_holidays`

Prometheus metrics:

```bash
curl "http://localhost:8000/metrics"
```

Example output:

```text
# HELP chronosx_service_info Static service metadata.
# TYPE chronosx_service_info gauge
chronosx_service_info{calendar_name="SSE",timezone="Asia/Shanghai",server_version="chronosx-quant/0.2.2"} 1
# HELP chronosx_trading_day Whether the evaluated time falls on a trading day.
# TYPE chronosx_trading_day gauge
chronosx_trading_day{calendar_name="SSE",timezone="Asia/Shanghai"} 1
# HELP chronosx_trading_time Whether the evaluated time falls inside trading hours.
# TYPE chronosx_trading_time gauge
chronosx_trading_time{calendar_name="SSE",timezone="Asia/Shanghai"} 0
```

The metrics response is generated with `prometheus_client` and a per-request custom registry. It avoids global collector state and does not expose `query_time` as a label.

You can scrape `/metrics` from Prometheus and alert with:

- `chronosx_trading_day == 1` when alerts should only run on trading days.
- `chronosx_trading_time == 1` when alerts must be active only during market hours.
