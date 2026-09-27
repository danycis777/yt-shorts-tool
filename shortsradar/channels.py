"""Channel audit: performance by format, upload cadence, best posting times, title insights, growth."""

from __future__ import annotations

import datetime as dt
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from . import earnings
from .outliers import LONG_BUCKETS, MIN_AGE_DAYS, SHORT_BUCKETS
from .resolve import ResolveError, channel_id_from_web, oembed, parse_channel_ref
from .stats import mean, median, percentile, stdev
from .textutil import content_tokens, emoji_count
from .videos import normalize_channel, normalize_video
from .youtube import YouTubeError, uploads_playlist

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def resolve_channel_id(app, ref: str) -> str:
    kind, value = parse_channel_ref(ref)
    if kind == "id":
        return value
    key = f"resolve:{kind}:{value.lower()}"
    cached = app.db.cache_get(key)
    if cached:
        return cached
    yt = app.youtube()
    cid: Optional[str] = None
    if kind == "video":
        if yt.enabled:
            items = yt.videos([value], max_age=86400)
            if items:
                cid = items[0].get("snippet", {}).get("channelId")
        if not cid:
            meta = oembed(value)
            if meta and meta.get("author_url"):
                k2, v2 = parse_channel_ref(meta["author_url"])
                cid = v2 if k2 == "id" else channel_id_from_web(k2, v2)
    elif yt.enabled and kind in ("handle", "username"):
        try:
            item = yt.channel_by_handle(value) if kind == "handle" else yt.channel_by_username(value)
            cid = item["id"] if item else None
        except YouTubeError as err:
            if err.reason in ("quotaExceeded", "keyInvalid", "accessNotConfigured"):
                raise
    if not cid:
        cid = channel_id_from_web(kind, value)
    if not cid:
        raise ResolveError(f"Couldn't find channel {value}.")
    app.db.cache_set(key, cid, 30 * 86400)
    return cid


def _tz(name: str):
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            pass
    return dt.datetime.now().astimezone().tzinfo


def audit(app, ref: str, *, max_videos: int = 100, tz_name: Optional[str] = None) -> Dict[str, Any]:
    yt = app.youtube()
    yt.require()
    started = time.time()
    cid = resolve_channel_id(app, ref)
    items = yt.channels([cid], max_age=3600)
    if not items:
        raise YouTubeError("channelNotFound", "Channel not found.")
    ch = normalize_channel(items[0])
    ids = yt.playlist_video_ids(ch["uploads_playlist"] or uploads_playlist(cid), max(10, min(max_videos, 500)))
    videos = [normalize_video(v) for v in yt.videos(ids, max_age=6 * 3600)]
    videos = [v for v in videos if v["live"] == "none" and v["views"] is not None]
    videos.sort(key=lambda v: -(v["published_ts"] or 0))
    tz = _tz(tz_name if tz_name is not None else (app.settings.get("timezone") or ""))
    now = time.time()

    # ---- per-format baselines & outlier scores
    formats: Dict[str, Dict[str, Any]] = {}
    for fmt in ("short", "long"):
        group = [v for v in videos if v["format"] == fmt]
        mature = [v for v in group if (v["age_days"] or 0) >= MIN_AGE_DAYS]
        med = median(v["views"] for v in mature)
        for v in group:
            v["outlier_score"] = round(v["views"] / med, 2) if med else None
        formats[fmt] = {
            "count": len(group),
            "median_views": med,
            "mean_views": mean(v["views"] for v in mature),
            "p90_views": percentile([v["views"] for v in mature], 90),
            "total_views": sum(v["views"] for v in group),
            "median_engagement": median(v["engagement_rate"] for v in group),
            "median_like_rate": median(v["like_rate"] for v in group),
            "median_duration_s": median(v["duration_s"] for v in group),
            "median_vph_first_week": median(v["vph"] for v in group if (v["age_days"] or 99) <= 7),
        }
    total_recent_views = sum(v["views"] for v in videos) or 1
    for fmt in formats:
        formats[fmt]["view_share"] = round(100.0 * formats[fmt]["total_views"] / total_recent_views, 1)
        formats[fmt]["upload_share"] = round(100.0 * formats[fmt]["count"] / max(1, len(videos)), 1)

    # ---- cadence
    stamps = sorted(v["published_ts"] for v in videos if v["published_ts"])
    gaps = [(b - a) / 86400.0 for a, b in zip(stamps, stamps[1:])]
    last90 = [t for t in stamps if now - t <= 90 * 86400]
    last30 = [t for t in stamps if now - t <= 30 * 86400]
    weekly = []
    for w in range(11, -1, -1):
        start, end = now - (w + 1) * 7 * 86400, now - w * 7 * 86400
        weekly.append({"week_start": dt.datetime.fromtimestamp(start, dt.timezone.utc).strftime("%Y-%m-%d"),
                       "uploads": sum(1 for t in stamps if start <= t < end)})
    recent_gaps = gaps[-20:]
    consistency = None
    if len(recent_gaps) >= 4 and mean(recent_gaps):
        cv = (stdev(recent_gaps) or 0) / mean(recent_gaps)
        consistency = round(max(0.0, 100.0 * (1 - min(cv, 1.5) / 1.5)))
    cadence = {
        "uploads_last_30d": len(last30),
        "uploads_last_90d": len(last90),
        "per_week_90d": round(len(last90) / (90 / 7.0), 2),
        "median_gap_days": round(median(recent_gaps), 2) if recent_gaps else None,
        "days_since_last_upload": round((now - stamps[-1]) / 86400.0, 1) if stamps else None,
        "consistency": consistency,
        "weekly": weekly,
    }

    # ---- posting times (local timezone)
    cells: Dict[tuple, List[float]] = defaultdict(list)
    day_scores: Dict[int, List[float]] = defaultdict(list)
    hour_scores: Dict[int, List[float]] = defaultdict(list)
    for v in videos:
        if v.get("outlier_score") is None or not v["published_ts"] or (v["age_days"] or 0) < MIN_AGE_DAYS:
            continue
        local = dt.datetime.fromtimestamp(v["published_ts"], tz)
        cells[(local.weekday(), local.hour)].append(v["outlier_score"])
        day_scores[local.weekday()].append(v["outlier_score"])
        hour_scores[local.hour].append(v["outlier_score"])
    heatmap = [{"day": d, "hour": h, "count": len(s), "median_score": round(median(s) or 0, 2)}
               for (d, h), s in sorted(cells.items())]
    days = [{"day": WEEKDAYS[d], "count": len(day_scores[d]),
             "median_score": round(median(day_scores[d]) or 0, 2) if day_scores[d] else None} for d in range(7)]
    windows = []
    for start in range(0, 24, 3):
        s = [x for h in range(start, start + 3) for x in hour_scores.get(h, [])]
        windows.append({"window": f"{start:02d}:00–{start + 3:02d}:00", "count": len(s),
                        "median_score": round(median(s) or 0, 2) if s else None})
    best_day = max((d for d in days if d["count"] >= 3), key=lambda d: d["median_score"], default=None)
    best_window = max((w for w in windows if w["count"] >= 3), key=lambda w: w["median_score"], default=None)
    tz_label = getattr(tz, "key", None) or dt.datetime.now(tz).strftime("%Z") or "local"
    posting = {"timezone": tz_label, "heatmap": heatmap, "days": days, "windows": windows,
               "best_day": best_day, "best_window": best_window}

    # ---- durations
    duration_insights = {}
    for fmt, buckets in (("short", SHORT_BUCKETS), ("long", LONG_BUCKETS)):
        rows = []
        for lo, hi, label in buckets:
            vals = [v["outlier_score"] for v in videos if v["format"] == fmt and v.get("outlier_score") is not None
                    and v["duration_s"] is not None and lo <= v["duration_s"] < hi]
            if vals:
                rows.append({"bucket": label, "count": len(vals), "median_score": round(median(vals) or 0, 2)})
        duration_insights[fmt] = rows

    # ---- title insights (word lift)
    scored = [v for v in videos if v.get("outlier_score") is not None and (v["age_days"] or 0) >= MIN_AGE_DAYS]
    overall_med = median(v["outlier_score"] for v in scored) or 1.0
    word_map: Dict[str, List[float]] = defaultdict(list)
    for v in scored:
        for w in set(content_tokens(v["title"])):
            if len(w) >= 3:
                word_map[w].append(v["outlier_score"])
    lifts = []
    for w, vals in word_map.items():
        if 3 <= len(vals) <= 0.8 * len(scored):
            lifts.append({"word": w, "count": len(vals), "lift": round((median(vals) or 0) / overall_med, 2)})
    lifts.sort(key=lambda r: -r["lift"])
    features = []
    for label, pred in (
        ("Has a number", lambda t: bool(re.search(r"\d", t))),
        ("Is a question", lambda t: t.strip().endswith("?")),
        ("Has an emoji", lambda t: emoji_count(t) > 0),
        ("Has an ALL-CAPS word", lambda t: any(w.isupper() and len(w) > 2 for w in re.findall(r"[A-Za-z]+", t))),
        ("Under 40 characters", lambda t: len(t) < 40),
        ("Uses 'I' / 'my'", lambda t: bool(re.search(r"\b(i|my|i'm)\b", t.lower()))),
        ("Uses 'you'", lambda t: bool(re.search(r"\byou(r)?\b", t.lower()))),
    ):
        with_ = [v["outlier_score"] for v in scored if pred(v["title"])]
        without = [v["outlier_score"] for v in scored if not pred(v["title"])]
        if len(with_) >= 3 and len(without) >= 3:
            features.append({"feature": label, "with": len(with_), "without": len(without),
                             "lift": round((median(with_) or 0) / max(median(without) or 1e-9, 1e-9), 2)})
    title_insights = {"top_words": lifts[:10], "weak_words": sorted(lifts[-6:], key=lambda r: r["lift"]),
                      "features": sorted(features, key=lambda r: -r["lift"])}

    # ---- tags & descriptions
    meta = {
        "no_tags_share": round(100.0 * sum(1 for v in videos if not v["tags"]) / max(1, len(videos)), 1),
        "avg_tags": round(mean(len(v["tags"]) for v in videos) or 0, 1),
        "median_description_chars": median(len(v["description"]) for v in videos),
        "top_tags": _top_tags(videos),
    }

    # ---- growth (from local snapshots)
    snaps = app.db.channel_snapshots(cid)
    growth = None
    if len(snaps) >= 2 and snaps[-1]["ts"] - snaps[0]["ts"] >= 6 * 3600:
        span_days = (snaps[-1]["ts"] - snaps[0]["ts"]) / 86400.0
        first, last = snaps[0], snaps[-1]
        growth = {
            "days_tracked": round(span_days, 1),
            "subs_per_day": round(((last["subs"] or 0) - (first["subs"] or 0)) / span_days, 1)
            if last["subs"] is not None and first["subs"] is not None else None,
            "views_per_day": round(((last["views"] or 0) - (first["views"] or 0)) / span_days)
            if last["views"] is not None and first["views"] is not None else None,
            "series": snaps[-60:],
        }

    # ---- earnings (rough)
    if growth and growth.get("views_per_day"):
        monthly_views = growth["views_per_day"] * 30
        basis = "tracked channel views"
    else:
        monthly_views = sum(v["views"] for v in videos if (v["age_days"] or 999) <= 30) * 1.3
        basis = "views on uploads from the last 30 days (+30% for older videos)"
    shorts_views = sum(v["views"] for v in videos if v["format"] == "short" and (v["age_days"] or 999) <= 90)
    all_views = sum(v["views"] for v in videos if (v["age_days"] or 999) <= 90) or 1
    cats = [v["category_id"] for v in videos if v.get("category_id")]
    category = earnings.category_from_youtube(max(set(cats), key=cats.count) if cats else None)
    money = earnings.calculator(monthly_views, category=category, country=ch.get("country") or "US",
                                shorts_share=shorts_views / all_views)
    money["basis"] = basis
    money["monetization_likely"] = (ch.get("subs") or 0) >= 1000

    top = sorted(scored, key=lambda v: -v["outlier_score"])[:8]
    bottom = sorted(scored, key=lambda v: v["outlier_score"])[:5]
    result = {
        "channel": ch,
        "analyzed_videos": len(videos),
        "formats": formats,
        "cadence": cadence,
        "posting": posting,
        "durations": duration_insights,
        "titles": title_insights,
        "metadata": meta,
        "growth": growth,
        "earnings": money,
        "top_videos": [_slim(v) for v in top],
        "bottom_videos": [_slim(v) for v in bottom],
        "videos": [_slim(v) for v in videos],
        "recommendations": recommendations(ch, formats, cadence, posting, duration_insights, title_insights, meta, top),
        "quota_units": yt.units_this_request,
        "elapsed_s": round(time.time() - started, 2),
    }
    app.db.add_history("channel", ch["title"] or cid, {"id": cid, "subs": ch.get("subs")})
    return result


def _top_tags(videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = defaultdict(int)
    for v in videos:
        for t in {t.lower() for t in v["tags"]}:
            counts[t] += 1
    return [{"tag": t, "count": c} for t, c in sorted(counts.items(), key=lambda kv: -kv[1])[:15]]


def _slim(v: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("id", "url", "title", "thumbnail", "published_at", "age_days", "views", "likes", "comments", "vph",
            "duration", "duration_s", "format", "outlier_score", "engagement_rate", "like_rate")
    return {k: v.get(k) for k in keys}


def recommendations(ch, formats, cadence, posting, durations, titles, meta, top) -> List[Dict[str, str]]:
    recs: List[Dict[str, str]] = []
    s, l = formats.get("short", {}), formats.get("long", {})
    if s.get("count", 0) >= 5 and l.get("count", 0) >= 5 and s.get("median_views") and l.get("median_views"):
        ratio = s["median_views"] / l["median_views"]
        if ratio >= 1.5:
            recs.append({"type": "good", "text": f"Your Shorts get {ratio:.1f}× the median views of your long-form videos — lean into Shorts and use them to funnel viewers to long-form."})
        elif ratio <= 0.67:
            recs.append({"type": "info", "text": f"Your long-form videos get {1 / ratio:.1f}× the median views of your Shorts — Shorts may work better as trailers for long-form."})
    per_week = cadence.get("per_week_90d") or 0
    if cadence.get("days_since_last_upload") and cadence["days_since_last_upload"] > 14:
        recs.append({"type": "bad", "text": f"No uploads in {cadence['days_since_last_upload']:.0f} days — the algorithm favours active channels. Schedule your next upload."})
    if s.get("upload_share", 0) >= 50 and per_week < 3:
        recs.append({"type": "warn", "text": f"You post {per_week:.1f} times a week. Growing Shorts channels typically post 1–3 Shorts a day; batch-produce to raise volume."})
    elif per_week < 1:
        recs.append({"type": "warn", "text": f"You post {per_week:.1f} times a week. Aim for at least one upload every week."})
    if cadence.get("consistency") is not None and cadence["consistency"] < 40:
        recs.append({"type": "warn", "text": "Your upload schedule is irregular. A predictable schedule builds returning viewers."})
    if posting.get("best_day") and posting.get("best_window"):
        recs.append({"type": "info", "text": f"Your best-performing uploads tend to go out on {posting['best_day']['day']} around {posting['best_window']['window']} ({posting['timezone']}). Small samples — treat as a hint and test it."})
    for fmt, label in (("short", "Shorts"), ("long", "videos")):
        rows = [r for r in durations.get(fmt, []) if r["count"] >= 3]
        if len(rows) >= 2:
            best = max(rows, key=lambda r: r["median_score"])
            recs.append({"type": "info", "text": f"Your {label} of {best['bucket']} perform best ({best['median_score']:.1f}× your median, {best['count']} uploads)."})
    if titles.get("top_words"):
        words = ", ".join(f"“{w['word']}”" for w in titles["top_words"][:3] if w["lift"] >= 1.3)
        if words:
            recs.append({"type": "good", "text": f"Titles containing {words} outperform your average — these topics/formats resonate. Make more of them."})
    if top:
        v = top[0]
        if v["outlier_score"] and v["outlier_score"] >= 3:
            recs.append({"type": "good", "text": f"“{v['title']}” got {v['outlier_score']:.1f}× your usual views. Make a follow-up or a new take on the same idea."})
    if meta.get("no_tags_share", 0) >= 50:
        recs.append({"type": "warn", "text": f"{meta['no_tags_share']:.0f}% of your uploads have no tags. Tags help YouTube with misspellings and related searches — add 5–15."})
    if (meta.get("median_description_chars") or 0) < 100:
        recs.append({"type": "warn", "text": "Most descriptions are very short. Add a keyword-rich first sentence and 2–3 hashtags."})
    eng = s.get("median_engagement") if s.get("count") else l.get("median_engagement")
    if eng is not None and eng < 2.0:
        recs.append({"type": "warn", "text": f"Median engagement is {eng:.1f}% (likes+comments per view). Ask a specific question or add a comment prompt to boost interaction."})
    return recs
