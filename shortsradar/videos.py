"""Normalise YouTube API video/channel resources into flat dicts with derived metrics."""

from __future__ import annotations

import datetime as dt
import re
import time
from typing import Any, Dict, List, Optional

from .stats import safe_div
from .youtube import best_thumbnail, parse_iso_duration, to_int

SHORTS_MAX_SECONDS = 180  # YouTube allows Shorts up to 3 minutes (since Oct 2024)


def parse_time(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def fmt_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return ""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _player_aspect(player: Optional[Dict[str, Any]]) -> Optional[float]:
    if not player:
        return None
    w, h = to_int(player.get("embedWidth")), to_int(player.get("embedHeight"))
    if not (w and h):
        html = player.get("embedHtml", "") or ""
        mw = re.search(r'width="(\d+)"', html)
        mh = re.search(r'height="(\d+)"', html)
        if mw and mh:
            w, h = int(mw.group(1)), int(mh.group(1))
    if w and h:
        return w / h
    return None


def detect_short(duration_s: Optional[int], aspect: Optional[float], text: str,
                 live: str = "none") -> Optional[bool]:
    """Best-effort Shorts detection from API data.

    Shorts are vertical/square videos up to 3 minutes. The embed aspect ratio (requested via
    maxWidth) is the most reliable signal; hashtags and very short durations are fallbacks.
    """
    if live and live != "none":
        return False
    if duration_s is None:
        return None
    if duration_s == 0 or duration_s > SHORTS_MAX_SECONDS:
        return False
    if aspect is not None:
        return aspect <= 1.01
    lowered = text.lower()
    if "#shorts" in lowered or "#short " in lowered or lowered.endswith("#short"):
        return True
    return duration_s <= 60


def normalize_video(item: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    now = now or time.time()
    sn = item.get("snippet", {}) or {}
    st = item.get("statistics", {}) or {}
    cd = item.get("contentDetails", {}) or {}
    status = item.get("status", {}) or {}
    topics = (item.get("topicDetails", {}) or {}).get("topicCategories", []) or []
    vid = item.get("id")
    published_ts = parse_time(sn.get("publishedAt"))
    age_hours = max((now - published_ts) / 3600.0, 0.0) if published_ts else None
    duration = parse_iso_duration(cd.get("duration"))
    title = sn.get("title", "") or ""
    description = sn.get("description", "") or ""
    tags = sn.get("tags", []) or []
    aspect = _player_aspect(item.get("player"))
    live = sn.get("liveBroadcastContent", "none") or "none"
    is_short = detect_short(duration, aspect, f"{title} {description} {' '.join(tags)}", live)
    views = to_int(st.get("viewCount"))
    likes = to_int(st.get("likeCount"))
    comments = to_int(st.get("commentCount"))
    hours = max(age_hours or 0.0, 1.0)
    return {
        "id": vid,
        "url": f"https://www.youtube.com/shorts/{vid}" if is_short else f"https://www.youtube.com/watch?v={vid}",
        "title": title,
        "description": description,
        "tags": tags,
        "channel_id": sn.get("channelId"),
        "channel_title": sn.get("channelTitle", ""),
        "published_at": sn.get("publishedAt"),
        "published_ts": published_ts,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "age_days": round(age_hours / 24.0, 2) if age_hours is not None else None,
        "duration_s": duration,
        "duration": fmt_duration(duration),
        "is_short": is_short,
        "format": "short" if is_short else "long",
        "aspect": round(aspect, 3) if aspect else None,
        "views": views,
        "likes": likes,
        "comments": comments,
        "like_rate": _pct(likes, views),
        "comment_rate": _pct(comments, views),
        "engagement_rate": _pct((likes or 0) + (comments or 0), views) if views else None,
        "vph": round(views / hours, 1) if views is not None and age_hours is not None else None,
        "vpd": round(views / max(hours / 24.0, 1.0), 1) if views is not None and age_hours is not None else None,
        "category_id": sn.get("categoryId"),
        "thumbnail": best_thumbnail(sn.get("thumbnails")) or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""),
        "caption": str(cd.get("caption", "")).lower() == "true",
        "definition": cd.get("definition"),
        "licensed": bool(cd.get("licensedContent")),
        "made_for_kids": bool(status.get("madeForKids")),
        "privacy": status.get("privacyStatus"),
        "live": live,
        "default_language": sn.get("defaultLanguage"),
        "audio_language": sn.get("defaultAudioLanguage"),
        "topics": [t.rsplit("/", 1)[-1].replace("_", " ") for t in topics],
    }


def normalize_channel(item: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    now = now or time.time()
    sn = item.get("snippet", {}) or {}
    st = item.get("statistics", {}) or {}
    branding = (item.get("brandingSettings", {}) or {}).get("channel", {}) or {}
    topics = (item.get("topicDetails", {}) or {}).get("topicCategories", []) or []
    created = parse_time(sn.get("publishedAt"))
    hidden = bool(st.get("hiddenSubscriberCount"))
    subs = None if hidden else to_int(st.get("subscriberCount"))
    views = to_int(st.get("viewCount"))
    count = to_int(st.get("videoCount"))
    handle = sn.get("customUrl", "") or ""
    return {
        "id": item.get("id"),
        "title": sn.get("title", ""),
        "handle": handle if handle.startswith("@") or not handle else "@" + handle,
        "url": f"https://www.youtube.com/channel/{item.get('id')}",
        "description": sn.get("description", ""),
        "thumbnail": best_thumbnail(sn.get("thumbnails")),
        "country": sn.get("country"),
        "created_at": sn.get("publishedAt"),
        "age_years": round((now - created) / (365.25 * 86400), 1) if created else None,
        "subs": subs,
        "subs_hidden": hidden,
        "views": views,
        "video_count": count,
        "avg_views_per_video": round(views / count) if views and count else None,
        "uploads_playlist": ((item.get("contentDetails", {}) or {}).get("relatedPlaylists", {}) or {}).get("uploads"),
        "keywords": _split_channel_keywords(branding.get("keywords", "")),
        "topics": [t.rsplit("/", 1)[-1].replace("_", " ") for t in topics],
    }


def _split_channel_keywords(raw: str) -> List[str]:
    # Channel keywords are space-separated, with multi-word keywords wrapped in quotes.
    return [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', raw or "")][:50]


def _pct(part: Optional[int], whole: Optional[int]) -> Optional[float]:
    ratio = safe_div(part, whole)
    return round(ratio * 100.0, 2) if ratio is not None else None


def vph_from_snapshots(snaps: List[Dict[str, Any]], window_hours: float = 48.0) -> Optional[Dict[str, Any]]:
    """Real views-per-hour between the latest snapshot and one at least 15 minutes older
    (preferring one about `window_hours` back)."""
    if len(snaps) < 2:
        return None
    latest = snaps[-1]
    target = latest["ts"] - window_hours * 3600
    best = None
    for s in snaps[:-1]:
        if latest["ts"] - s["ts"] < 15 * 60 or s.get("views") is None:
            continue
        if best is None or abs(s["ts"] - target) < abs(best["ts"] - target):
            best = s
    if best is None or latest.get("views") is None:
        return None
    hours = (latest["ts"] - best["ts"]) / 3600.0
    gained = latest["views"] - best["views"]
    return {"vph": round(max(gained, 0) / hours, 1), "hours": round(hours, 2), "gained": gained}
