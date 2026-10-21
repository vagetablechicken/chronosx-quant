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
# shortest forms: cal=calendar/session, ls=calendars, h=holidays, q=check
# calendar aliases: sse, cme, f23, f01, f02, idc
cxq ls
cxq cal f23                           # inspect session timing, breaks, and weekend trading
cxq cal cme
cxq q "2026-08-10 21:00" -c f23       # inspect one timestamp
cxq h -c sse -s 2026-08-10 -d 10      # list holidays in a range

# full command:
# inspect session start/end, trading intervals, and weekend openings
chronosx-preview calendar -c f23
chronosx-preview calendar cme

# list holidays (the default command, SSE by default)
chronosx-preview
chronosx-preview --start 2026-08-10 --days 60

# show supported numeric calendar IDs and aliases
chronosx-preview calendars
chronosx-preview calendars f23

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
from chronosx_quant import ChronoTime, use_calendar
import pandas as pd

# use CALENDAR_NAME to select default calendar, e.g. SSE
# use SCHEDULE_START / SCHEDULE_END to control the preloaded schedule window
# defaults: SCHEDULE_START=2022-01-01, SCHEDULE_END=now+3y
time = ChronoTime.now()
time = ChronoTime("2026-03-09 11:29:00+08:00")
```

> [!WARNING]
> Every time the `use_calendar()` context is entered, it creates a new scheduler
> and precomputes the complete schedule window. Initialization is slow, so this
> convenience API is not suitable for latency-sensitive code. Enter the context
> once outside the hot path and reuse its scheduler instead of calling it in a
> loop or for every event.

```python
# Temporarily use another calendar; the previous one is restored when the
# block exits. Optional start/end arguments control its preloaded window.
with use_calendar("CME Globex Crypto") as scheduler:
    time = ChronoTime("2026-03-09 17:00:00")
    print(scheduler.calendar.name)
    print(time.is_trading())

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

- [ ] dynamic range scheduler cache?

## Calendar Preview (CLI & API)

Chronosx provides both a command-line tool (`cxq` / `chronosx-preview`) and Python APIs to inspect trading session hours, intra-day trading breaks, upcoming holidays, and weekend trading schedules.

### Supported Calendars & Aliases

| ID | Alias | Calendar Name | Description |
|---|---|---|---|
| 1 | `sse` | `SSE` *(default)* | Shanghai Stock Exchange (`09:30 - 15:00`) |
| 2 | `cme` | `CME Globex Crypto` | CME Crypto futures (`17:00 (T-1) - 16:00 (T)`, Sunday night open) |
| 3 | `f23` | `CN_FUTURES_2300` | China futures (`21:00 (T-1) - 23:00 (T-1)` night session) |
| 4 | `f01` | `CN_FUTURES_0100` | China futures (`21:00 (T-1) - 01:00 (T)` night session) |
| 5 | `f02` | `CN_FUTURES_0230` | China futures (`21:00 (T-1) - 02:30 (T)` night session) |

Any valid `pandas_market_calendars` calendar name is also accepted.

### CLI Usage (`cxq` / `chronosx-preview`)

`cxq` is the short alias for `chronosx-preview`. Short subcommands: `cal` (session), `ls` (calendars), `h` (holidays), `q` (check).

```bash
# 1. Inspect session details (start/end, breaks, Friday night, Saturday/Sunday trading)
cxq cal f02
cxq cal cme
cxq session sse

# 2. List calendars or inspect a specific calendar
cxq ls
cxq ls f23

# 3. Check a specific timestamp
cxq q "2026-08-10 21:00" -c f23

# 4. List upcoming holidays (default: today + 32 days)
cxq h -c sse -s 2026-08-10 -d 30
```

Example session output (`cxq cal f02`):

```text
Calendar:              CN_FUTURES_0230 (China Futures Night Session 02:30 Close) [ID: 5] [alias: f02]
Timezone:              Asia/Shanghai
Session start:         21:00 (T-1)
Session end:           15:00 (T)
Trading duration:      9h 15m (555 min)
Trading intervals:
  21:00 (T-1) - 02:30 (T)    (330 min)
  09:00 (T) - 10:15 (T)      (75 min)
  10:30 (T) - 11:30 (T)      (60 min)
  13:30 (T) - 15:00 (T)      (90 min)
Friday night open:     yes (opens Friday 21:00, closes Saturday 02:30, part of Monday session)
Saturday trading:      yes (00:00 - 02:30)
Sunday trading:        no
Sunday night open:     no
Monday session open:   Friday 21:00
Friday session close:  Friday 15:00
```

### Python API

```python
from chronosx_quant.preview import (
    build_session_preview,
    build_holiday_preview,
    build_time_preview,
    build_calendar_preview,
)

# Inspect trading session timing, breaks, and weekend trading
session = build_session_preview("f02")
print(session["session_start"])               # "21:00 (T-1)"
print(session["total_trading_hours"])         # "9h 15m"
print(session["saturday_trading"])            # True (00:00 - 02:30)
print(session["sunday_trading"])              # False

# Check CME Sunday trading
cme_session = build_session_preview("cme")
print(cme_session["sunday_trading"])          # True (17:00 - 24:00)
print(cme_session["sunday_night_open"])       # True

# List upcoming holidays
holidays = build_holiday_preview("SSE", start="2026-01-01", days_ahead=60)
print(holidays["upcoming_holidays"])

# Inspect whether a specific timestamp is trading time / trading day
info = build_time_preview("f23", "2026-08-10 21:00")
print(info["is_trading_time"])                # True
print(info["trading_date"])                   # "2026-08-11"
```

## Benchmark

The benchmark suite uses `pytest-benchmark`.

Run the full benchmark file:

```bash
uv run pytest tests/benchmark_chrono.py --benchmark-only \
  --benchmark-warmup=on \
  --benchmark-calibration-precision=100
```

Run a single benchmark:

```bash
uv run pytest tests/benchmark_chrono.py -k test_perf_is_trading \
  --benchmark-only \
  --benchmark-warmup=on \
  --benchmark-calibration-precision=100
```

Export the full result for later analysis:

```bash
uv run pytest tests/benchmark_chrono.py --benchmark-only \
  --benchmark-warmup=on \
  --benchmark-calibration-precision=100 \
  --benchmark-json=.benchmarks/chrono.json
```

Run and export only the schedule-size cases:

```bash
uv run pytest tests/benchmark_chrono.py -k by_schedule_size \
  --benchmark-only \
  --benchmark-warmup=on \
  --benchmark-calibration-precision=100 \
  --benchmark-json=.benchmarks/schedule-size.json
```

Useful notes:

- `tests/benchmark_chrono.py` runs benchmarks across `SSE`, `CME Globex Crypto`,
  `ICE`, and `CN_FUTURES_2300`, sampling trading times near the early, middle,
  and late portions of each loaded schedule
- `--benchmark-only` runs only benchmark tests and skips normal tests
- warmup and higher calibration precision reduce startup and timer-calibration
  noise, but benchmarks should still be repeated on an otherwise idle machine
- if you want the usual pytest output without benchmark filtering, you can run `uv run pytest tests/benchmark_chrono.py`

Benchmark preview:

Source: `.benchmarks/chrono.json`, generated on 2026-09-15 with
chronosx-quant `0.3.1`, Windows 11, an Intel Core i9-14900HX (32 logical
CPUs), and CPython 3.10.19.

Each parameterized benchmark case has its own median. The representative value
below is the median of those case medians; the range shows the lowest and
highest case median in the file. This is more robust than reporting raw maximum
samples, but the wide ranges still show that Windows scheduling affected some
cases during this run.

| Operation | Representative median | Case median range |
| --- | ---: | ---: |
| `ChronoTime(...)` | 9.05 µs | 9.05 µs |
| `shift` | 14.25 µs | 13.50–15.10 µs |
| `is_trading` | 0.88 µs | 0.85–0.94 µs |
| `is_trading_day` | 16.80 µs | 16.00–17.50 µs |
| `trading_times` (one-hour range) | 28.15 µs | 26.80–31.10 µs |
| `previous_trading_time` | 7.25 µs | 7.00–8.00 µs |
| `next_trading_time` | 7.40 µs | 7.15–7.80 µs |
| `ChronoTime.now()` | 2.70 µs | 2.64–2.78 µs |
| mocked `ChronoTime.now()` | 0.24 µs | 0.22–0.24 µs |

Schedule-size preview:

Source: `.benchmarks/schedule-size.json`, generated on 2026-09-15 with the
schedule-size command above on the same host and Python version. These are
warm-state lookup measurements; scheduler construction is not included.

Each cell uses the median of the early, middle, and late query-position case
medians for that window. The three lookup methods share the same `O(log N)`
session search. Differences this small are normal measurement noise and should
not be interpreted as a schedule-size performance trend; memory use, by
contrast, grows approximately linearly with the loaded window.

| Schedule window | Sessions | Total scheduler memory | `get_trading_date` | `to_session_start` | `to_session_end` |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3 years | 727 | 1.36 MiB | 2.88 µs | 3.52 µs | 3.27 µs |
| 6 years | 1,455 | 2.73 MiB | 2.95 µs | 3.40 µs | 3.45 µs |
| 10 years | 2,430 | 4.56 MiB | 2.86 µs | 3.45 µs | 3.40 µs |

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

The preview response helps verify upcoming holidays, session timings, and recent holiday definitions for a calendar. It includes:

- `calendar_name`
- `calendar_full_name`
- `today`
- `range_start`
- `days_ahead`
- `range_end`
- `latest_holidays`
- `upcoming_holidays`
- `session` (session start/end, trading duration, intra-day intervals, Friday night open, Saturday/Sunday trading)

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
