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
# use SCHEDULE_START / SCHEDULE_END to control the preloaded schedule window
# defaults: SCHEDULE_START=2022-01-01, SCHEDULE_END=now+3y
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
  aliases: `SC.INE`, `AG.SHF`
  session: previous day `21:00` to trading day `15:00`
  hours: `21:00-02:30 | 09:00-10:15 | 10:30-11:30 | 13:30-15:00`

- `CN_FUTURES_0100`
  aliases: `BC.INE`, `CU.SHF`
  session: previous day `21:00` to trading day `15:00`
  hours: `21:00-01:00 | 09:00-10:15 | 10:30-11:30 | 13:30-15:00`

- `CN_FUTURES_2300`
  aliases: `DCE`, `CZC`
  session: previous day `21:00` to trading day `15:00`
  hours: `21:00-23:00 | 09:00-10:15 | 10:30-11:30 | 13:30-15:00`

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

To run benchmark suites for stabilized performance metrics and export results:

```bash
uv run pytest tests/benchmark_chrono.py --benchmark-only --benchmark-json=.benchmarks/chrono.json --benchmark-warmup=on --benchmark-calibration-precision=100
```

Useful notes:

- `tests/benchmark_chrono.py` runs benchmarks across `SSE`, `CME Globex Crypto`,
  `ICE`, and `CN_FUTURES_2300`, sampling trading times near the early, middle,
  and late portions of each loaded schedule
- `--benchmark-only` runs only benchmark tests and skips normal tests
- if you want the usual pytest output without benchmark filtering, you can run `uv run pytest tests/benchmark_chrono.py`

Benchmark preview:

Measured on Windows 10 with an Intel Core i9-14900HX (32 logical CPUs) and
CPython 3.10.19. Values below are approximate median latencies; maximum values
are omitted because microbenchmarks are sensitive to OS scheduling outliers.

| Operation | Approximate time |
| --- | ---: |
| `ChronoTime(...)` | 11.5 µs |
| `shift` | 12.5–14.4 µs |
| `is_trading` | 30.8–45.5 µs |
| `is_trading_day` | 30.1–32.8 µs |
| `trading_times` (one-hour range) | 44.7–49.4 µs |
| `previous_trading_time` / `next_trading_time` | 7.8–8.3 µs |
| `ChronoTime.now()` | 2.8–2.9 µs |
| mocked `ChronoTime.now()` | 0.15 µs |
| `get_trading_date` | 2.7–2.8 µs |
| `to_session_start` / `to_session_end` | 3.2–3.3 µs |

Session lookup remains effectively constant as the precomputed SSE schedule grows:

| Schedule window | Sessions | Total scheduler memory | `get_trading_date` | `to_session_start` | `to_session_end` |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 years | 727 | 1.36 MiB | 2.8 µs | 3.3 µs | 3.2 µs |
| 6 years | 1,455 | 2.73 MiB | 2.7 µs | 3.3 µs | 3.2 µs |
| 10 years | 2,430 | 4.56 MiB | 2.8 µs | 3.3 µs | 3.3 µs |

## Docker Service

The container service is implemented with `FastAPI` and exposes a JSON query API plus a Prometheus-compatible metrics endpoint.

Run locally without Docker:

```bash
uv run --group docker -m docker.service
```

Build and run with Docker:

```bash
# build docker image
docker build -t chronosx-quant .
# run container
docker run --rm -p 8000:8000 -e CALENDAR_NAME=SSE chronosx-quant
docker run --rm -p 8000:8000 -e CALENDAR_NAME=SSE -e SCHEDULE_START=2022-01-01 -e SCHEDULE_END=2030-12-31 chronosx-quant
```

Service schedule window:

- `SCHEDULE_START` defaults to `2022-01-01`
- `SCHEDULE_END` defaults to `now + 3 years`
- if you set `SCHEDULE_END`, use str in any format which `pandas.Timestamp(...)` can parse, for example `2030-12-31`

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

## Performance Design

Chronosx uses `HdrHistogram` as the profiling backend for `performance`
instead of `TDigest`.

This choice is intentional: our profiling data is execution latency, measured in
microseconds, always positive, and expected to stay within a configurable but
bounded range. That shape matches `HdrHistogram` very well.

Why `HdrHistogram` fits this project:

- latency is recorded in integer `us`, so the histogram keeps a natural
  time-unit representation instead of approximating around floating-point
  centroids
- high-percentile queries such as `p99`, `p999`, and `p9999` are a first-class
  use case for runtime profiling, and `HdrHistogram` is built for this style of
  tail-latency analysis
- writes and percentile reads are both very fast, which is important when the
  profiler itself should add as little overhead as possible
- the storage model is predictable once the trackable range and significant
  figures are chosen

Why not `TDigest` by default:

- `TDigest` is more general-purpose and is excellent when the value range is
  unknown, highly dynamic, or needs to be merged across distributed nodes
- that flexibility is less important for this library, because function latency
  is already naturally modeled as bounded positive durations
- for our use case, the extra abstraction of centroid-based summaries is not as
  compelling as keeping direct microsecond-scale latency buckets

Configuration model:

- the default profile remains microsecond-based: `1 us` minimum,
  `60 s` maximum, `3` significant figures
- you can override the global default through
  `PerformanceRegistry.configure_default(...)`
- you can override a specific metric through `@performance(...)` or
  `with performance(...)`, including `min_value_us`, `max_value_us`, and
  `significant_figures`

Why `performance` does not use `ContextDecorator`:

- Chronosx wants one API that works as both a decorator and a `with` block, but
  it does not want to share mutable timing state between those two modes
- a plain `ContextDecorator` style implementation usually stores `start_time`
  on `self`, which is easy to reason about for a single `with` block, but is
  much easier to misuse once the same decorator object is entered by concurrent
  calls
- in Chronosx, decorated functions keep timing state in the local wrapper call
  frame, so every invocation gets an independent `start_time`
- `with performance(...)` still creates a fresh instance per `with` statement,
  so context-manager usage also gets isolated state naturally
- this separation keeps the API simple while avoiding accidental cross-thread or
  re-entrant state corruption from a shared timing attribute

Thread-safety model:

- metric aggregation is shared globally by name, but per-call timing state is
  not shared
- decorator mode is safe for concurrent calls because timing lives in local
  variables inside the wrapper, not on the profiler object
- context-manager mode is safe because each `with performance(...)` expression
  instantiates a new profiler object before entering the block
- the design goal is not lock-free mutation of every backend detail, but to
  avoid the much more common bug where overlapping calls overwrite each other's
  `start_time`

Overall, the design is optimized for practical in-process latency profiling:
`HdrHistogram` gives Chronosx efficient microsecond-level percentile tracking,
and the custom `performance` implementation keeps per-call timing state
isolated so the same API remains straightforward under concurrent use.
