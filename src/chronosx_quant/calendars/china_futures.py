from abc import ABC, abstractmethod
from datetime import time
from functools import cached_property

import pandas as pd
from pandas_market_calendars.calendars.sse import SSEExchangeCalendar


class _BaseChinaFuturesNightCalendar(SSEExchangeCalendar, ABC):
    """
    Chinese futures calendars that share SSE holidays and Asia/Shanghai timezone.
    """

    aliases = []
    regular_market_times = {
        "break_end_1": ((None, time(9, 0)),),
        "break_start_2": ((None, time(10, 15)),),
        "break_end_2": ((None, time(10, 30)),),
        "break_start_3": ((None, time(11, 30)),),
        "break_end_3": ((None, time(13, 30)),),
        "market_close": ((None, time(15, 0)),),
    }

    open_close_map = {
        "market_open": True,
        "break_start_1": False,
        "break_end_1": True,
        "break_start_2": False,
        "break_end_2": True,
        "break_start_3": False,
        "break_end_3": True,
        "market_close": False,
    }

    @cached_property
    def _holiday_dates(self):
        holiday_start = "1990-01-01"
        holiday_end = "2100-12-31"

        regular_holidays = (
            self.regular_holidays.holidays(holiday_start, holiday_end)
            if self.regular_holidays is not None
            else pd.DatetimeIndex([])
        )
        adhoc_holidays = pd.DatetimeIndex(self.adhoc_holidays)

        return regular_holidays.union(adhoc_holidays).sort_values().normalize()

    @cached_property
    def _post_holiday_trading_dates(self):
        if self._holiday_dates.empty:
            return pd.DatetimeIndex([])

        holiday_series = self._holiday_dates.to_series(index=self._holiday_dates)
        holiday_block_ends = holiday_series[
            holiday_series.diff(-1).ne(-pd.Timedelta(days=1)).fillna(True)
        ].index

        post_holiday_trading_days = []
        for holiday_end in holiday_block_ends:
            next_trading_days = self.valid_days(
                holiday_end + pd.Timedelta(days=1),
                holiday_end + pd.Timedelta(days=7),
                tz=None,
            )
            if len(next_trading_days) > 0:
                post_holiday_trading_days.append(next_trading_days[0])

        return (
            pd.DatetimeIndex(post_holiday_trading_days).drop_duplicates().sort_values()
        )

    @cached_property
    def _monday_trading_dates(self):
        trading_days = self.valid_days("1990-01-01", "2100-12-31", tz=None)
        monday_trading_days = trading_days[trading_days.weekday == 0]
        return monday_trading_days.difference(
            self._post_holiday_trading_dates
        ).sort_values()

    @property
    def _special_market_open_adhoc(self):
        return []

    @property
    def _special_break_start_1_adhoc(self):
        return []

    def get_special_times(self, market_time):
        if market_time == "market_open":
            return [*super().get_special_times(market_time), *self.special_opens]
        if market_time == "market_close":
            return [*super().get_special_times(market_time), *self.special_closes]
        return super().get_special_times(market_time)

    def get_special_times_adhoc(self, market_time):
        if market_time == "market_open":
            return [*self._special_market_open_adhoc, *self.special_opens_adhoc]
        if market_time == "market_close":
            return [
                *super().get_special_times_adhoc(market_time),
                *self.special_closes_adhoc,
            ]
        if market_time == "break_start_1":
            return [*self._special_break_start_1_adhoc]
        return super().get_special_times_adhoc(market_time)

    @property
    def special_opens_adhoc(self):
        # The first trading day after a holiday block has no prior-night session,
        # so that session starts from the daytime reopen at 09:00.
        return [(time(9, 0), self._post_holiday_trading_dates)]

    @property
    @abstractmethod
    def name(self):
        raise NotImplementedError


class ChinaFuturesNight0230Calendar(_BaseChinaFuturesNightCalendar):
    aliases = ["CN_FUTURES_0230", "SC.INE", "AG.SHF"]
    regular_market_times = {
        "market_open": ((None, time(21, 0), -1),),
        "break_start_1": ((None, time(2, 30)),),
        **_BaseChinaFuturesNightCalendar.regular_market_times,
    }

    @property
    def name(self):
        return "CN_FUTURES_0230"

    @property
    def full_name(self):
        return "China Futures Night Session 02:30 Close"

    @property
    def _special_market_open_adhoc(self):
        return [((time(21, 0), -3), self._monday_trading_dates)]

    @property
    def _special_break_start_1_adhoc(self):
        return [((time(2, 30), -2), self._monday_trading_dates)]


class ChinaFuturesNight0100Calendar(_BaseChinaFuturesNightCalendar):
    aliases = ["CN_FUTURES_0100", "BC.INE", "CU.SHF"]
    regular_market_times = {
        "market_open": ((None, time(21, 0), -1),),
        "break_start_1": ((None, time(1, 0)),),
        **_BaseChinaFuturesNightCalendar.regular_market_times,
    }

    @property
    def name(self):
        return "CN_FUTURES_0100"

    @property
    def full_name(self):
        return "China Futures Night Session 01:00 Close"

    @property
    def _special_market_open_adhoc(self):
        return [((time(21, 0), -3), self._monday_trading_dates)]

    @property
    def _special_break_start_1_adhoc(self):
        return [((time(1, 0), -2), self._monday_trading_dates)]


class ChinaFuturesNight2300Calendar(_BaseChinaFuturesNightCalendar):
    aliases = ["CN_FUTURES_2300", "DCE", "CZC"]
    regular_market_times = {
        "market_open": ((None, time(21, 0), -1),),
        "break_start_1": ((None, time(23, 0), -1),),
        **_BaseChinaFuturesNightCalendar.regular_market_times,
    }

    @property
    def name(self):
        return "CN_FUTURES_2300"

    @property
    def full_name(self):
        return "China Futures Night Session 23:00 Close"

    @property
    def _special_market_open_adhoc(self):
        return [((time(21, 0), -3), self._monday_trading_dates)]

    @property
    def _special_break_start_1_adhoc(self):
        return [((time(23, 0), -3), self._monday_trading_dates)]
