"""YouTube Data API quota accounting. Google resets the quota at midnight Pacific Time."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict

# Unit cost per call (https://developers.google.com/youtube/v3/determine_quota_cost)
COSTS = {
    "search": 100,
    "videos": 1,
    "channels": 1,
    "playlistItems": 1,
    "videoCategories": 1,
    "commentThreads": 1,
    "i18nRegions": 1,
}


def _us_pacific_offset(now_utc: dt.datetime) -> dt.timedelta:
    """UTC offset of US Pacific time without needing tz database files (works on Windows)."""
    year = now_utc.year
    # DST: second Sunday in March 10:00 UTC (2am PST) .. first Sunday in November 09:00 UTC (2am PDT)
    march = dt.datetime(year, 3, 8, 10, tzinfo=dt.timezone.utc)
    dst_start = march + dt.timedelta(days=(6 - march.weekday()) % 7)
    november = dt.datetime(year, 11, 1, 9, tzinfo=dt.timezone.utc)
    dst_end = november + dt.timedelta(days=(6 - november.weekday()) % 7)
    return dt.timedelta(hours=-7) if dst_start <= now_utc < dst_end else dt.timedelta(hours=-8)


def pacific_now(now_utc: dt.datetime | None = None) -> dt.datetime:
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    return (now_utc + _us_pacific_offset(now_utc)).replace(tzinfo=None)


def quota_day(now_utc: dt.datetime | None = None) -> str:
    return pacific_now(now_utc).strftime("%Y-%m-%d")


def seconds_until_reset(now_utc: dt.datetime | None = None) -> int:
    local = pacific_now(now_utc)
    tomorrow = (local + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - local).total_seconds())


class QuotaTracker:
    def __init__(self, db, daily_limit: int = 10000):
        self.db = db
        self.daily_limit = daily_limit

    def record(self, units: int) -> None:
        day = quota_day()
        self.db.execute(
            "INSERT INTO quota (day, units, calls) VALUES (?, ?, 1) "
            "ON CONFLICT(day) DO UPDATE SET units = units + excluded.units, calls = calls + 1",
            (day, units),
        )

    def used_today(self) -> int:
        row = self.db.query_one("SELECT units FROM quota WHERE day = ?", (quota_day(),))
        return int(row["units"]) if row else 0

    def status(self) -> Dict[str, Any]:
        used = self.used_today()
        return {
            "used": used,
            "limit": self.daily_limit,
            "remaining": max(0, self.daily_limit - used),
            "resets_in_seconds": seconds_until_reset(),
            "day": quota_day(),
        }
