import sys
from datetime import time

if sys.version_info >= (3, 9):
    from zoneinfo import ZoneInfo
else:
    from backports.zoneinfo import ZoneInfo

from pandas_market_calendars.class_registry import ProtectedDict
from pandas_market_calendars.market_calendar import MarketCalendar


class IDCCalendar(MarketCalendar):
    """
    Exchange calendar for IDC.

    Trading hours: Sunday 5:00 PM EST/EDT to Friday 5:00 PM EST/EDT.
    Closed on Saturdays and Sunday, no holidays.
    """

    aliases = ["IDC"]

    regular_market_times = ProtectedDict(
        {
            "market_open": ((None, time(17, 0), -1),),
            "market_close": ((None, time(17, 0)),),
        }
    )

    @property
    def name(self):
        return "IDC"

    @property
    def tz(self):
        return ZoneInfo("America/New_York")

    @property
    def weekmask(self):
        return "Mon Tue Wed Thu Fri"
