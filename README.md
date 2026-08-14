# Chronosx Quant

A Python library for trading calendar management, execution profiling, and temporal backtesting (Time Travel).

## Installation

Install the library:

```bash
uv build
pip install dist/chronosx_quant-*-py3-none-any.whl

# install from pypi
pip install chronosx-quant

# `cxq` stands for ChronosX Quant. It is the short command for
# `chronosx-preview`; both commands provide the same functionality.
# shortest forms: q=check, h=holidays, ls=calendars
# calendar aliases: sse, cme, f23, f01, f02
cxq ls
cxq q "2026-08-10 21:00" -c f23
cxq h -c sse -s 2026-08-10 -d 10

# full command:
# list holidays (the default command, SSE by default)
chronosx-preview
chronosx-preview --start 2026-08-10 --days 60

# show the stable numeric calendar IDs
chronosx-preview calendars

# list holidays for another calendar (3 = CN_FUTURES_2300)
chronosx-preview holidays -c 3 --start 2026-08-10

# inspect one timestamp
chronosx-preview check "2026-08-10 21:00" -c 3

# optionally control the scheduler's preloaded window
chronosx-preview check "2026-08-10 21:00" -c 3 \
  --scheduler-start 2026-01-01 --scheduler-end 2027-01-01
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

Source: `.benchmarks/chrono.json`, generated on 2026-08-14 with
chronosx-quant `0.3.0b3`, Windows 10, an Intel Core i9-14900HX (32 logical
CPUs), and CPython 3.10.19.

Each parameterized benchmark case has its own median. The representative value
below is the median of those case medians; the range shows the lowest and
highest case median in the file. This is more robust than reporting raw maximum
samples, but the wide ranges still show that Windows scheduling affected some
cases during this run.

| Operation | Representative median | Case median range |
| --- | ---: | ---: |
| `ChronoTime(...)` | 8.75 µs | 8.75 µs |
| `shift` | 14.00 µs | 12.90–144.10 µs |
| `is_trading` | 1.06 µs | 0.87–9.26 µs |
| `is_trading_day` | 35.85 µs | 28.00–410.70 µs |
| `trading_times` (one-hour range) | 31.85 µs | 28.90–280.50 µs |
| `previous_trading_time` | 8.32 µs | 6.75–76.45 µs |
| `next_trading_time` | 9.55 µs | 6.90–85.35 µs |
| `ChronoTime.now()` | 28.62 µs | 2.74–28.90 µs |
| mocked `ChronoTime.now()` | 0.48 µs | 0.14–0.97 µs |

The schedule-size cases below use the median of the early, middle, and late
query-position medians for each window. `to_session_end` remained stable in this
run; the wider `get_trading_date` and `to_session_start` results reflect the
same host-level timing noise visible above and should not be interpreted as an
algorithmic schedule-size trend.

| Schedule window | Sessions | Total scheduler memory | `get_trading_date` | `to_session_start` | `to_session_end` |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 years | 727 | 1.36 MiB | 33.48 µs | 3.23 µs | 3.12 µs |
| 6 years | 1,455 | 2.73 MiB | 34.25 µs | 3.15 µs | 3.12 µs |
| 10 years | 2,430 | 4.56 MiB | 2.95 µs | 3.15 µs | 3.12 µs |

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
curl "http://localhost:8000/calendar_preview?calendar_name=SSE&check_time=2026-08-10%2009:30"
```

The preview response helps verify upcoming holidays and recent holiday definitions for a calendar. It includes:

- `calendar_name`
- `calendar_full_name`
- `today`
- `range_start`
- `days_ahead`
- `range_end`
- `latest_holidays`
- `upcoming_holidays`

When `check_time` is supplied, `check` also includes the calendar-local time,
date, weekday, whether the date is a trading day, whether the instant is a
trading time, and the session's `trading_date` (or `null` outside a session).

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

Chronosx uses `HdrHistogram` as the profiling backend for `performance`. The
main reason is predictability: profiling should add consistently low recording
overhead, with memory usage that can be determined from the configured range and
precision.

Execution latency is a good match for this model. It is a positive duration,
recorded as integer microseconds, and expected to remain within a configurable
range. `HdrHistogram` can therefore map each observation directly to a latency
bucket instead of dynamically maintaining a set of floating-point centroids.

This gives the profiler:

- predictable memory usage after the maximum latency and significant figures
  are configured
- consistently low-cost recording, which reduces the profiler's effect on the
  function being measured
- direct support for tail-latency percentiles such as `p99`, `p999`, and
  `p9999`
- a natural integer-microsecond representation

`TDigest` is not unsuitable; it solves a more general problem. It approximates
the observed distribution with data-dependent centroids, which is especially
useful when the value range is unknown or highly dynamic, or when summaries need
to be merged across distributed nodes. Chronosx instead prefers fixed,
configurable precision: `HdrHistogram` quantizes values into deterministic
latency buckets whose relative error is controlled by `significant_figures`.
This makes the accuracy, memory usage, and recording overhead easier to reason
about than an adaptive centroid summary.

`HdrHistogram` is still an approximate summary; it does not retain every raw
latency measurement. Applications that require mathematically exact percentiles
must store the raw samples, or maintain exact counts at every required latency
resolution, at a substantially higher and potentially unbounded memory cost.
The default here favors predictable, explicitly bounded error and low overhead,
not a claim of zero-error percentile calculation or universal performance
superiority.

Configuration model:

- the default profile remains microsecond-based: `1 us` minimum,
  `60 s` maximum, `3` significant figures
- you can override the global default through
  `PerformanceRegistry.configure_default(...)`
- you can configure a named metric through `PerformanceRegistry.configure(...)`
  or pass the same options directly to `@performance(...)` and
  `with performance(...)`

All ranges use integer microseconds. `significant_figures` accepts values from
`1` to `5`; the default `3` is a practical balance between relative precision
and memory usage.

```python
from chronosx_quant.performance import PerformanceRegistry, performance

# Change the defaults used by metrics created after this call.
PerformanceRegistry.configure_default(
    min_value_us=1,
    max_value_us=10_000_000,  # 10 seconds
    significant_figures=3,
)

# Configure one named metric before it records its first value.
PerformanceRegistry.configure(
    "database.query",
    min_value_us=10,
    max_value_us=2_000_000,  # 2 seconds
    significant_figures=4,
)

@performance("database.query")
def query_database():
    ...

# Alternatively, keep a metric's configuration next to its decorator.
@performance(
    "strategy.calculate",
    min_value_us=1,
    max_value_us=500_000,
    significant_figures=3,
)
def calculate_strategy():
    ...

# The same options are available for one measured block.
with performance(
    "market_data.update",
    min_value_us=1,
    max_value_us=100_000,
    significant_figures=3,
):
    update_market_data()
```

Configure each metric before its first measurement. Once its histogram backend
has been created, changing the registry configuration does not rebuild that
backend. `PerformanceRegistry.clear()` removes all collected measurements and
restores the library defaults when a complete reconfiguration is required.

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
