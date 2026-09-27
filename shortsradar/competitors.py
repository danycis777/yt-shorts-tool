"""Competitor tracking. Uses free RSS feeds (no quota) for uploads/views/likes, snapshots every refresh
to compute real views-per-hour, and (optionally) the API for subscriber counts."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .channels import resolve_channel_id
from .rss import FeedError, fetch_channel_feed
from .stats import median
from .videos import normalize_channel, normalize_video, vph_from_snapshots
from .youtube import YouTubeError, uploads_playlist

MATURE_DAYS = 3.0


def fetch_uploads(app, cid: str) -> Dict[str, Any]:
    """Latest uploads for a channel: the free RSS feed first; if YouTube's feed endpoint is down
    (it periodically answers 404 for every channel) fall back to the Data API (2 quota units)."""
    try:
        feed = fetch_channel_feed(cid)
        feed["source"] = "rss"
        return feed
    except FeedError as rss_error:
        yt = app.youtube()
        if not yt.enabled:
            raise FeedError(f"{rss_error} YouTube's RSS feeds are sometimes down for hours; add a YouTube API key "
                            "so ShortsRadar can fall back to the API (2 units per channel refresh).") from None
    ids = yt.playlist_video_ids(uploads_playlist(cid), 15, ttl=1800)
    videos = [normalize_video(v) for v in yt.videos(ids, max_age=1800)]
    ch_items = yt.channels([cid], max_age=6 * 3600)
    title = ch_items[0].get("snippet", {}).get("title") if ch_items else (videos[0]["channel_title"] if videos else cid)
    return {
        "source": "api",
        "channel": {"id": cid, "title": title, "url": f"https://www.youtube.com/channel/{cid}"},
        "videos": [{
            "id": v["id"], "channel_id": cid, "title": v["title"], "url": v["url"], "is_short": bool(v["is_short"]),
            "published_ts": v["published_ts"], "published_at": v["published_at"], "views": v["views"],
            "likes": v["likes"], "thumbnail": v["thumbnail"], "description": v["description"],
        } for v in videos if v["live"] == "none"],
    }


def add(app, ref: str) -> Dict[str, Any]:
    cid = resolve_channel_id(app, ref)
    existing = app.db.query_one("SELECT channel_id FROM competitors WHERE channel_id = ?", (cid,))
    feed = fetch_uploads(app, cid)
    title = feed["channel"].get("title") or cid
    if existing is None:
        app.db.execute(
            "INSERT INTO competitors (channel_id, title, added, last_refresh) VALUES (?,?,?,?)",
            (cid, title, time.time(), time.time()),
        )
    _store_feed(app, cid, feed)
    _refresh_stats(app, [cid])
    return next((c for c in list_competitors(app) if c["channel_id"] == cid), {"channel_id": cid, "title": title})


def remove(app, channel_id: str) -> None:
    app.db.execute("DELETE FROM competitors WHERE channel_id = ?", (channel_id,))
    app.db.execute("DELETE FROM feed_videos WHERE channel_id = ?", (channel_id,))


def _store_feed(app, cid: str, feed: Dict[str, Any]) -> None:
    now = time.time()
    for v in feed["videos"]:
        app.db.execute(
            "INSERT INTO feed_videos (video_id, channel_id, title, published, is_short, thumbnail, views, likes, first_seen, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET title=excluded.title, "
            "views=excluded.views, likes=excluded.likes, is_short=excluded.is_short, updated=excluded.updated",
            (v["id"], cid, v["title"], v["published_ts"], int(v["is_short"]), v["thumbnail"], v["views"], v["likes"],
             now, now),
        )
        app.db.add_video_snapshot(v["id"], v["views"], v["likes"], ts=now)
    title = feed["channel"].get("title")
    app.db.execute("UPDATE competitors SET last_refresh = ?, last_error = NULL, title = COALESCE(?, title) WHERE channel_id = ?",
                   (now, title, cid))


def _refresh_stats(app, ids: List[str]) -> Optional[str]:
    yt = app.youtube()
    if not yt.enabled or not ids:
        return None
    try:
        for item in yt.channels(ids, max_age=6 * 3600):
            ch = normalize_channel(item)
            app.db.execute(
                "UPDATE competitors SET title = ?, handle = ?, thumbnail = ?, subs = ?, total_views = ?, video_count = ? "
                "WHERE channel_id = ?",
                (ch["title"], ch["handle"], ch["thumbnail"], ch["subs"], ch["views"], ch["video_count"], ch["id"]),
            )
    except YouTubeError as err:
        return str(err)
    return None


def refresh(app, channel_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    rows = app.db.query("SELECT channel_id FROM competitors")
    ids = [r["channel_id"] for r in rows if not channel_ids or r["channel_id"] in channel_ids]
    errors = []

    def one(cid: str) -> Optional[str]:
        try:
            _store_feed(app, cid, fetch_uploads(app, cid))
            return None
        except (FeedError, YouTubeError) as err:
            app.db.execute("UPDATE competitors SET last_error = ? WHERE channel_id = ?", (str(err), cid))
            return f"{cid}: {err}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        for err in pool.map(one, ids):
            if err:
                errors.append(err)
    stats_error = _refresh_stats(app, ids)
    if stats_error:
        errors.append(stats_error)
    return {"refreshed": len(ids) - len([e for e in errors if e != stats_error]), "errors": errors,
            "at": time.time()}


def _channel_baselines(app) -> Dict[str, Dict[str, Optional[float]]]:
    now = time.time()
    out: Dict[str, Dict[str, Optional[float]]] = {}
    rows = app.db.query("SELECT channel_id, is_short, views, published FROM feed_videos")
    groups: Dict[tuple, List[int]] = {}
    young: Dict[tuple, List[int]] = {}
    for r in rows:
        if r["views"] is None or r["published"] is None:
            continue
        key = (r["channel_id"], "short" if r["is_short"] else "long")
        (groups if now - r["published"] >= MATURE_DAYS * 86400 else young).setdefault(key, []).append(r["views"])
    for key in set(groups) | set(young):
        vals = groups.get(key, [])
        approx = False
        if len(vals) < 3:
            vals = vals + young.get(key, [])
            approx = True
        out.setdefault(key[0], {})[key[1]] = median(vals) if len(vals) >= 3 else None
        out[key[0]][key[1] + "_approx"] = approx
    return out


def list_competitors(app) -> List[Dict[str, Any]]:
    now = time.time()
    base = _channel_baselines(app)
    out = []
    for r in app.db.query("SELECT * FROM competitors ORDER BY added"):
        cid = r["channel_id"]
        vids = app.db.query("SELECT * FROM feed_videos WHERE channel_id = ? ORDER BY published DESC", (cid,))
        uploads_7d = sum(1 for v in vids if v["published"] and now - v["published"] <= 7 * 86400)
        uploads_30d = sum(1 for v in vids if v["published"] and now - v["published"] <= 30 * 86400)
        snaps = app.db.channel_snapshots(cid)
        subs_growth = None
        if len(snaps) >= 2 and snaps[-1]["subs"] is not None and snaps[0]["subs"] is not None:
            days = max((snaps[-1]["ts"] - snaps[0]["ts"]) / 86400.0, 1e-9)
            if days >= 0.25:
                subs_growth = {"per_day": round((snaps[-1]["subs"] - snaps[0]["subs"]) / days, 1), "days": round(days, 1)}
        latest = vids[0] if vids else None
        out.append({
            "channel_id": cid,
            "title": r["title"],
            "handle": r["handle"],
            "thumbnail": r["thumbnail"],
            "url": f"https://www.youtube.com/channel/{cid}",
            "subs": r["subs"],
            "total_views": r["total_views"],
            "video_count": r["video_count"],
            "added": r["added"],
            "last_refresh": r["last_refresh"],
            "last_error": r["last_error"],
            "uploads_7d": uploads_7d,
            "uploads_30d_tracked": uploads_30d,
            "median_short_views": base.get(cid, {}).get("short"),
            "median_long_views": base.get(cid, {}).get("long"),
            "shorts_share": round(100.0 * sum(1 for v in vids if v["is_short"]) / len(vids), 1) if vids else None,
            "subs_growth": subs_growth,
            "latest": {"id": latest["video_id"], "title": latest["title"], "published": latest["published"],
                       "views": latest["views"], "is_short": bool(latest["is_short"])} if latest else None,
        })
    return out


def feed(app, *, fmt: str = "any", days: int = 14, sort: str = "score", limit: int = 100) -> List[Dict[str, Any]]:
    now = time.time()
    base = _channel_baselines(app)
    names = {r["channel_id"]: r["title"] for r in app.db.query("SELECT channel_id, title FROM competitors")}
    rows = app.db.query(
        "SELECT * FROM feed_videos WHERE published >= ? ORDER BY published DESC", (now - days * 86400,)
    )
    out = []
    for r in rows:
        if r["channel_id"] not in names:
            continue
        f = "short" if r["is_short"] else "long"
        if fmt in ("short", "long") and f != fmt:
            continue
        age_h = max((now - (r["published"] or now)) / 3600.0, 1.0)
        med = base.get(r["channel_id"], {}).get(f)
        live = vph_from_snapshots(app.db.video_snapshots(r["video_id"]), window_hours=24)
        score = round(r["views"] / med, 2) if med and r["views"] is not None else None
        out.append({
            "id": r["video_id"],
            "url": f"https://www.youtube.com/{'shorts/' + r['video_id'] if r['is_short'] else 'watch?v=' + r['video_id']}",
            "title": r["title"],
            "thumbnail": r["thumbnail"],
            "channel_id": r["channel_id"],
            "channel_title": names.get(r["channel_id"]),
            "format": f,
            "published": r["published"],
            "age_hours": round(age_h, 1),
            "views": r["views"],
            "likes": r["likes"],
            "vph": round(r["views"] / age_h, 1) if r["views"] is not None else None,
            "vph_recent": live["vph"] if live else None,
            "outlier_score": score,
            "baseline_views": int(med) if med else None,
            "baseline_approx": base.get(r["channel_id"], {}).get(f + "_approx", False),
            "trending": bool(score and score >= 2.0 and age_h <= 7 * 24),
        })
    keys = {
        "score": lambda v: -(v["outlier_score"] or 0),
        "vph": lambda v: -(v["vph_recent"] if v["vph_recent"] is not None else (v["vph"] or 0)),
        "views": lambda v: -(v["views"] or 0),
        "recent": lambda v: -(v["published"] or 0),
    }
    out.sort(key=keys.get(sort, keys["score"]))
    return out[:limit]


def alerts(app, limit: int = 10) -> List[Dict[str, Any]]:
    items = [v for v in feed(app, days=7, sort="score") if v["trending"]]
    out = []
    for v in items[:limit]:
        out.append({
            "video": v,
            "text": f"{v['channel_title']}: “{v['title']}” has {v['outlier_score']:.1f}× their usual views "
                    f"after {v['age_hours'] / 24:.1f} days",
        })
    return out
