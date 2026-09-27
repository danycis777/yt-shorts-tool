"""Outlier finder: videos that got far more views than their channel normally gets.

Outlier score = video views / median views of the same channel's recent uploads *of the same
format* (Shorts are compared with Shorts, long-form with long-form), ignoring uploads younger than
3 days (still growing). A score of 5x means five times what that channel usually gets — a strong
sign the *idea/packaging* worked, not just the channel's size.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, List, Optional

from .stats import median, percentile
from .textutil import top_phrases
from .videos import normalize_channel, normalize_video
from .youtube import YouTubeError, uploads_playlist

WITHIN_DAYS = {"day": 1, "week": 7, "month": 30, "3months": 90, "6months": 182, "year": 365, "all": None}
MIN_AGE_DAYS = 3.0
SHORT_BUCKETS = ((0, 15, "0–15s"), (15, 30, "15–30s"), (30, 45, "30–45s"), (45, 60, "45–60s"),
                 (60, 90, "60–90s"), (90, 181, "90s–3m"))
LONG_BUCKETS = ((0, 300, "<5m"), (300, 600, "5–10m"), (600, 1200, "10–20m"), (1200, 2400, "20–40m"),
                (2400, 10 ** 9, "40m+"))


def iso_days_ago(days: float) -> str:
    """RFC 3339 timestamp `days` ago, rounded down to the hour so repeated searches hit the cache."""
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return t.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def channel_recent(app, yt, channel_id: str, fmt: str) -> Dict[str, Any]:
    """Recent uploads of one format for a channel: [{id, views, age_days, is_short}] (cached 24h)."""
    key = f"recent:{channel_id}:{fmt}"
    cached = app.db.cache_get(key)
    if cached is not None:
        return cached
    source = {"short": "UUSH", "long": "UULF"}.get(fmt, "UU")
    try:
        ids = yt.playlist_video_ids(uploads_playlist(channel_id, fmt), 50, ttl=24 * 3600)
    except YouTubeError as err:
        if err.reason not in ("playlistNotFound", "http404", "forbidden"):
            raise
        ids = []
    if not ids and fmt in ("short", "long"):
        # Special per-format playlists are missing for some channels: fall back to all uploads.
        source = "UU"
        try:
            ids = yt.playlist_video_ids(uploads_playlist(channel_id, "all"), 50, ttl=24 * 3600)
        except YouTubeError as err:
            if err.reason not in ("playlistNotFound", "http404", "forbidden"):
                raise
            ids = []
    vids = [normalize_video(v) for v in yt.videos(ids, max_age=24 * 3600)]
    rows = [{"id": v["id"], "views": v["views"], "age_days": v["age_days"], "is_short": v["is_short"],
             "published_ts": v["published_ts"]}
            for v in vids if v["views"] is not None and v["live"] == "none"]
    if source == "UU" and fmt in ("short", "long"):
        rows = [r for r in rows if bool(r["is_short"]) == (fmt == "short")]
    out = {"source": source, "videos": rows}
    app.db.cache_set(key, out, 24 * 3600)
    return out


def baseline(recent: Dict[str, Any], exclude_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    mature = [r["views"] for r in recent.get("videos", [])
              if r["id"] != exclude_id and (r.get("age_days") or 0) >= MIN_AGE_DAYS]
    if len(mature) < 3:
        return None
    return {"median": median(mature), "p75": percentile(mature, 75), "sample": len(mature),
            "source": recent.get("source")}


def score_videos(app, yt, videos: List[Dict[str, Any]], channels: Dict[str, Dict[str, Any]],
                 max_channels: int = 40) -> None:
    """Attach outlier scores in place (vs channel median of same format)."""
    by_channel: Dict[str, List[Dict[str, Any]]] = {}
    for v in videos:
        by_channel.setdefault(v["channel_id"], []).append(v)
    # Channels with the most promising candidates first (quota is bounded by max_channels).
    order = sorted(by_channel, key=lambda c: -max((v["views"] or 0) for v in by_channel[c]))
    recents: Dict[str, Dict[str, Any]] = {}
    for cid in order[:max_channels]:
        for fmt in {v["format"] for v in by_channel[cid]}:
            try:
                recents[f"{cid}:{fmt}"] = channel_recent(app, yt, cid, fmt)
            except YouTubeError as err:
                if err.reason in ("quotaExceeded", "dailyLimitExceeded", "keyInvalid", "accessNotConfigured"):
                    raise
    for v in videos:
        ch = channels.get(v["channel_id"]) or {}
        v["channel_subs"] = ch.get("subs")
        v["channel_thumbnail"] = ch.get("thumbnail")
        v["views_per_sub"] = round(v["views"] / ch["subs"], 2) if v.get("views") is not None and ch.get("subs") else None
        rec = recents.get(f"{v['channel_id']}:{v['format']}")
        base = baseline(rec, exclude_id=v["id"]) if rec else None
        if base and base["median"]:
            v["baseline_views"] = int(base["median"])
            v["baseline_sample"] = base["sample"]
            v["outlier_score"] = round((v["views"] or 0) / max(base["median"], 1.0), 2)
            v["score_basis"] = "channel median"
        elif ch.get("avg_views_per_video"):
            v["baseline_views"] = ch["avg_views_per_video"]
            v["baseline_sample"] = None
            v["outlier_score"] = round((v["views"] or 0) / max(ch["avg_views_per_video"], 1), 2)
            v["score_basis"] = "channel lifetime average"
        else:
            v["baseline_views"] = None
            v["baseline_sample"] = None
            v["outlier_score"] = None
            v["score_basis"] = None


def find_outliers(app, *, keyword: Optional[str] = None, channel_ids: Optional[List[str]] = None,
                  fmt: str = "short", within: str = "month", min_score: Optional[float] = None,
                  min_views: Optional[int] = None, max_views: Optional[int] = None,
                  min_subs: Optional[int] = None, max_subs: Optional[int] = None, sort: str = "score",
                  region: Optional[str] = None, language: Optional[str] = None, deep: bool = False,
                  limit: int = 50) -> Dict[str, Any]:
    if not keyword and not channel_ids:
        raise ValueError("Enter a keyword/niche or pick channels.")
    yt = app.youtube()
    yt.require()
    started = time.time()
    days = WITHIN_DAYS.get(within, 30)
    published_after = iso_days_ago(days) if days else None
    region = (region or app.region).upper()
    language = (language or app.language).lower()

    ids: List[str] = []
    if keyword:
        orders = ["relevance"] + (["viewCount", "date"] if deep else [])
        for order in orders:
            res = yt.search(keyword, max_results=50, order=order, published_after=published_after,
                            duration="short" if fmt == "short" else None, region=region, language=language)
            ids += [it["video_id"] for it in res["items"] if it.get("video_id")]
    for cid in channel_ids or []:
        try:
            ids += yt.playlist_video_ids(uploads_playlist(cid, fmt if fmt in ("short", "long") else "all"), 50)
        except YouTubeError as err:
            if err.reason not in ("playlistNotFound", "http404"):
                raise
            ids += yt.playlist_video_ids(uploads_playlist(cid, "all"), 50)

    videos = [normalize_video(v) for v in yt.videos(list(dict.fromkeys(ids)), max_age=6 * 3600)]
    cutoff = time.time() - days * 86400 if days else None
    videos = [v for v in videos if v["live"] == "none" and v["views"] is not None
              and (cutoff is None or (v["published_ts"] or 0) >= cutoff)
              and (fmt == "any" or v["format"] == fmt)]
    channels = {c["id"]: c for c in (normalize_channel(c) for c in yt.channels({v["channel_id"] for v in videos}))}
    score_videos(app, yt, videos, channels)

    def keep(v: Dict[str, Any]) -> bool:
        if min_score is not None and (v["outlier_score"] or 0) < min_score:
            return False
        if min_views is not None and (v["views"] or 0) < min_views:
            return False
        if max_views is not None and (v["views"] or 0) > max_views:
            return False
        subs = v.get("channel_subs")
        if min_subs is not None and (subs is None or subs < min_subs):
            return False
        if max_subs is not None and (subs is None or subs > max_subs):
            return False
        return True

    results = [v for v in videos if keep(v)]
    sort_keys = {
        "score": lambda v: -(v["outlier_score"] or 0),
        "views": lambda v: -(v["views"] or 0),
        "vph": lambda v: -(v["vph"] or 0),
        "recent": lambda v: -(v["published_ts"] or 0),
        "engagement": lambda v: -(v["engagement_rate"] or 0),
    }
    results.sort(key=sort_keys.get(sort, sort_keys["score"]))
    results = results[:limit]
    return {
        "keyword": keyword,
        "channel_ids": channel_ids or [],
        "format": fmt,
        "within": within,
        "results": [_slim(v) for v in results],
        "summary": summarize(results),
        "scanned": len(videos),
        "quota_units": yt.units_this_request,
        "elapsed_s": round(time.time() - started, 2),
    }


def summarize(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [v for v in videos if v.get("outlier_score") is not None]
    strong = [v for v in scored if v["outlier_score"] >= 2]
    pool = strong or scored
    buckets = SHORT_BUCKETS if pool and pool[0]["format"] == "short" else LONG_BUCKETS
    dur = []
    for lo, hi, label in buckets:
        vals = [v["outlier_score"] for v in pool if v.get("duration_s") is not None and lo <= v["duration_s"] < hi]
        if vals:
            dur.append({"bucket": label, "count": len(vals), "median_score": round(median(vals) or 0, 2)})
    return {
        "count": len(videos),
        "median_score": round(median([v["outlier_score"] for v in scored]) or 0, 2) if scored else None,
        "strong_outliers": len(strong),
        "title_phrases": [{"phrase": p, "count": c} for p, c in top_phrases([v["title"] for v in pool], limit=10)],
        "durations": dur,
        "small_channel_hits": sum(1 for v in strong if (v.get("channel_subs") or 0) < 10_000),
    }


def _slim(v: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("id", "url", "title", "thumbnail", "channel_id", "channel_title", "channel_subs", "channel_thumbnail",
            "views", "likes", "comments", "published_at", "age_days", "vph", "duration", "duration_s", "is_short",
            "format", "outlier_score", "baseline_views", "baseline_sample", "score_basis", "views_per_sub",
            "engagement_rate", "like_rate", "tags")
    return {k: v.get(k) for k in keys}
