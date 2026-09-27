"""Video scorecard: stats, views/hour, outlier score, SEO audit, title score, tags, earnings."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from . import earnings
from .channels import resolve_channel_id
from .outliers import baseline, channel_recent
from .resolve import ResolveError, oembed, parse_channel_ref, parse_video_id
from .rss import FeedError, fetch_channel_feed
from .seo import score_metadata
from .stats import median
from .textutil import normalize_keyword
from .titles import score_title
from .videos import normalize_channel, normalize_video, vph_from_snapshots
from .youtube import YouTubeError


def scorecard(app, ref: str, *, keyword: Optional[str] = None) -> Dict[str, Any]:
    vid = parse_video_id(ref)
    if not vid:
        raise ResolveError("Paste a YouTube video or Shorts URL (or an 11-character video ID).")
    yt = app.youtube()
    if not yt.enabled:
        return keyless_scorecard(app, vid, keyword=keyword)
    started = time.time()
    items = yt.videos([vid], max_age=300)
    if not items:
        raise YouTubeError("videoNotFound", "Video not found.")
    v = normalize_video(items[0])
    ch_items = yt.channels([v["channel_id"]], max_age=6 * 3600)
    ch = normalize_channel(ch_items[0]) if ch_items else {}
    base = None
    try:
        rec = channel_recent(app, yt, v["channel_id"], v["format"])
        base = baseline(rec, exclude_id=vid)
    except YouTubeError as err:
        if err.reason in ("quotaExceeded", "keyInvalid", "accessNotConfigured"):
            raise
    snaps = app.db.video_snapshots(vid)
    live_vph = vph_from_snapshots(snaps)
    seo = score_metadata(v["title"], v["description"], v["tags"], keyword=keyword, fmt=v["format"],
                         duration_s=v["duration_s"], caption=v["caption"],
                         language_set=bool(v["default_language"] or v["audio_language"]))
    title = score_title(v["title"], fmt=v["format"], keyword=seo["keyword"])
    category = earnings.category_from_youtube(v["category_id"])
    money = earnings.estimate(v["views"] or 0, category=category, country=ch.get("country") or "US", fmt=v["format"])
    outlier = None
    if base and base["median"]:
        outlier = {"score": round((v["views"] or 0) / max(base["median"], 1), 2), "baseline_views": int(base["median"]),
                   "sample": base["sample"], "basis": f"median of the channel's last {base['sample']} "
                   f"{'Shorts' if v['format'] == 'short' else 'long-form videos'}"}
    elif ch.get("avg_views_per_video"):
        outlier = {"score": round((v["views"] or 0) / max(ch["avg_views_per_video"], 1), 2),
                   "baseline_views": ch["avg_views_per_video"], "sample": None, "basis": "channel lifetime average"}
    result = {
        "mode": "api",
        "video": v,
        "channel": ch,
        "stats": _stats(v, ch, live_vph),
        "outlier": outlier,
        "seo": seo,
        "title_score": title,
        "earnings": money,
        "history": [{"ts": s["ts"], "views": s["views"], "likes": s["likes"], "comments": s["comments"]} for s in snaps[-200:]],
        "quota_units": yt.units_this_request,
        "elapsed_s": round(time.time() - started, 2),
    }
    app.db.add_history("video", v["title"], {"id": vid})
    return result


def _stats(v: Dict[str, Any], ch: Dict[str, Any], live_vph: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "views": v.get("views"),
        "likes": v.get("likes"),
        "comments": v.get("comments"),
        "vph_lifetime": v.get("vph"),
        "vph_recent": live_vph["vph"] if live_vph else None,
        "vph_recent_window_h": live_vph["hours"] if live_vph else None,
        "views_per_day": v.get("vpd"),
        "like_rate": v.get("like_rate"),
        "comment_rate": v.get("comment_rate"),
        "engagement_rate": v.get("engagement_rate"),
        "views_per_sub": round(v["views"] / ch["subs"], 2) if v.get("views") is not None and ch.get("subs") else None,
        "age_hours": v.get("age_hours"),
    }


def keyless_scorecard(app, vid: str, *, keyword: Optional[str] = None) -> Dict[str, Any]:
    """Limited scorecard without an API key: oEmbed (title/format) + the channel RSS feed (views/likes)."""
    meta = oembed(vid)
    if not meta:
        raise ResolveError("Couldn't load that video (it may be private). Add a YouTube API key for full data.")
    is_short = meta["aspect"] is not None and meta["aspect"] <= 1.01
    fmt = "short" if is_short else "long"
    feed_video: Optional[Dict[str, Any]] = None
    feed: Optional[Dict[str, Any]] = None
    cid = None
    try:
        kind, value = parse_channel_ref(meta["author_url"])
        cid = value if kind == "id" else resolve_channel_id(app, meta["author_url"])
        feed = fetch_channel_feed(cid)
        feed_video = next((x for x in feed["videos"] if x["id"] == vid), None)
    except (ResolveError, FeedError):
        pass
    v: Dict[str, Any] = {"id": vid, "title": meta["title"], "channel_title": meta["author"], "channel_id": cid,
                         "thumbnail": meta["thumbnail"], "is_short": is_short, "format": fmt, "tags": [],
                         "url": f"https://www.youtube.com/{'shorts/' + vid if is_short else 'watch?v=' + vid}",
                         "description": feed_video["description"] if feed_video else "",
                         "views": None, "likes": None, "comments": None, "published_at": None}
    stats: Dict[str, Any] = {}
    outlier = None
    if feed_video:
        age_h = max((time.time() - (feed_video["published_ts"] or time.time())) / 3600.0, 1.0)
        v.update(views=feed_video["views"], likes=feed_video["likes"], published_at=feed_video["published_at"],
                 age_hours=round(age_h, 1))
        app.db.add_video_snapshot(vid, feed_video["views"], feed_video["likes"])
        live = vph_from_snapshots(app.db.video_snapshots(vid))
        stats = {
            "views": feed_video["views"], "likes": feed_video["likes"], "comments": None,
            "vph_lifetime": round(feed_video["views"] / age_h, 1) if feed_video["views"] is not None else None,
            "vph_recent": live["vph"] if live else None,
            "like_rate": round(100.0 * feed_video["likes"] / feed_video["views"], 2) if feed_video["views"] and feed_video["likes"] is not None else None,
            "age_hours": round(age_h, 1),
        }
        same = [x["views"] for x in feed["videos"] if x["id"] != vid and x["is_short"] == is_short
                and x["views"] is not None and (time.time() - (x["published_ts"] or 0)) >= 3 * 86400]
        med = median(same)
        if med and len(same) >= 3 and feed_video["views"] is not None:
            outlier = {"score": round(feed_video["views"] / med, 2), "baseline_views": int(med), "sample": len(same),
                       "basis": "median of the channel's recent uploads in its RSS feed"}
    seo = score_metadata(v["title"], v["description"], [], keyword=keyword, fmt=fmt)
    return {
        "mode": "keyless",
        "video": v,
        "channel": {"id": cid, "title": meta["author"], "url": meta["author_url"]},
        "stats": stats,
        "outlier": outlier,
        "seo": seo,
        "title_score": score_title(v["title"], fmt=fmt, keyword=seo["keyword"]),
        "earnings": earnings.estimate(v["views"] or 0, fmt=fmt) if v["views"] else None,
        "history": [],
        "limited": True,
        "note": "Limited data (no YouTube API key): tags, comments and full stats need a free API key — add one in Settings.",
        "quota_units": 0,
    }


def tag_ranks(app, video_id: str, tags: List[str], *, region: Optional[str] = None) -> List[Dict[str, Any]]:
    """Where the video ranks in YouTube search for each tag (100 quota units per tag)."""
    yt = app.youtube()
    yt.require()
    out = []
    for tag in [normalize_keyword(t) for t in tags if t.strip()][:5]:
        res = yt.search(tag, max_results=50, region=(region or app.region), language=app.language)
        ids = [it["video_id"] for it in res["items"] if it.get("video_id")]
        out.append({"tag": tag, "rank": ids.index(video_id) + 1 if video_id in ids else None, "searched": len(ids)})
    return out
