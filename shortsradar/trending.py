"""Trending: YouTube's regional trending chart, and 'what's blowing up in my niche' by views per hour."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .outliers import iso_days_ago
from .stats import median
from .videos import normalize_channel, normalize_video


def chart(app, *, region: Optional[str] = None, category: Optional[str] = None, fmt: str = "any",
          limit: int = 50) -> Dict[str, Any]:
    """The official trending chart (1 quota unit per 50 videos)."""
    yt = app.youtube()
    yt.require()
    region = (region or app.region).upper()
    items = yt.most_popular(region, category or None, max_results=max(1, min(limit, 200)))
    videos = [normalize_video(v) for v in items]
    for pos, v in enumerate(videos, 1):
        v["chart_position"] = pos
    if fmt in ("short", "long"):
        videos = [v for v in videos if v["format"] == fmt]
    try:
        categories = yt.categories(region, app.language)
    except Exception:
        categories = []
    return {"region": region, "category": category, "format": fmt, "videos": [_slim(v) for v in videos],
            "categories": categories, "quota_units": yt.units_this_request}


def niche(app, keyword: str, *, hours: int = 72, fmt: str = "short", region: Optional[str] = None,
          language: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
    """Recent uploads for a keyword ranked by views per hour (~102 quota units)."""
    yt = app.youtube()
    yt.require()
    started = time.time()
    res = yt.search(keyword, max_results=50, order="viewCount", published_after=iso_days_ago(hours / 24.0),
                    duration="short" if fmt == "short" else None, region=(region or app.region).upper(),
                    language=(language or app.language), ttl=3600)
    ids = [it["video_id"] for it in res["items"] if it.get("video_id")]
    videos = [normalize_video(v) for v in yt.videos(ids, max_age=3600)]
    videos = [v for v in videos if v["live"] == "none" and (fmt == "any" or v["format"] == fmt)]
    channels = {c["id"]: c for c in (normalize_channel(c) for c in yt.channels({v["channel_id"] for v in videos}))}
    for v in videos:
        ch = channels.get(v["channel_id"]) or {}
        v["channel_subs"] = ch.get("subs")
        v["views_per_sub"] = round(v["views"] / ch["subs"], 2) if v.get("views") is not None and ch.get("subs") else None
    videos.sort(key=lambda v: -(v["vph"] or 0))
    return {
        "keyword": keyword,
        "hours": hours,
        "format": fmt,
        "videos": [_slim(v) for v in videos[:limit]],
        "median_vph": median(v["vph"] for v in videos),
        "quota_units": yt.units_this_request,
        "elapsed_s": round(time.time() - started, 2),
    }


def _slim(v: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("id", "url", "title", "thumbnail", "channel_id", "channel_title", "channel_subs", "views", "likes",
            "comments", "published_at", "age_hours", "age_days", "vph", "duration", "is_short", "format",
            "engagement_rate", "views_per_sub", "chart_position", "category_id")
    return {k: v.get(k) for k in keys}
