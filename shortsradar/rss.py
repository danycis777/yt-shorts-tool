"""Channel RSS feeds: free, keyless, zero-quota access to a channel's latest 15 uploads with views & likes."""

from __future__ import annotations

import datetime as dt
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from . import config
from .net import BROWSER_UA, HttpError, NetworkError, request

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


class FeedError(Exception):
    pass


RETRY_BASE_DELAY = 0.8  # seconds; grows linearly per attempt


def fetch_channel_feed(channel_id: str, attempts: int = 4) -> Dict[str, Any]:
    """Fetch and parse a channel feed. YouTube's feed endpoint intermittently answers 404/500 for
    valid channels, so those statuses are retried a few times before giving up."""
    url = f"{config.YOUTUBE_WEB_BASE}/feeds/videos.xml?{urllib.parse.urlencode({'channel_id': channel_id})}"
    last_error = ""
    for attempt in range(attempts):
        try:
            _, _, body = request(url, headers={"User-Agent": BROWSER_UA}, timeout=15, retries=0)
            return parse_feed(body)
        except HttpError as err:
            last_error = f"HTTP {err.status}"
            if err.status not in (404, 429, 500, 502, 503, 504):
                break
        except NetworkError as err:
            last_error = str(err)
        except FeedError as err:
            last_error = str(err)
        if attempt + 1 < attempts:
            time.sleep(RETRY_BASE_DELAY * (attempt + 1))
    raise FeedError(f"Could not load the channel feed for {channel_id} ({last_error}).")


def parse_feed(body: bytes) -> Dict[str, Any]:
    head = body[:2048].lower()
    if b"<!doctype" in head or b"<!entity" in body[:65536].lower():
        raise FeedError("Unexpected response (not an RSS feed).")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as err:
        raise FeedError(f"Malformed feed: {err}") from None
    channel_id = _text(root, "yt:channelId")
    if channel_id and not channel_id.startswith("UC"):
        channel_id = "UC" + channel_id
    channel = {
        "id": channel_id,
        "title": _text(root, "atom:title"),
        "url": _link(root),
    }
    videos: List[Dict[str, Any]] = []
    for entry in root.findall("atom:entry", NS):
        vid = _text(entry, "yt:videoId")
        if not vid:
            continue
        link = _link(entry)
        group = entry.find("media:group", NS)
        views = likes = None
        rating = None
        thumb = ""
        description = ""
        if group is not None:
            stats = group.find("media:community/media:statistics", NS)
            if stats is not None:
                views = _int(stats.get("views"))
            star = group.find("media:community/media:starRating", NS)
            if star is not None:
                likes = _int(star.get("count"))
                rating = _float(star.get("average"))
            th = group.find("media:thumbnail", NS)
            if th is not None:
                thumb = th.get("url", "")
            description = _text(group, "media:description")
        published = _parse_time(_text(entry, "atom:published"))
        videos.append({
            "id": vid,
            "channel_id": channel_id or _text(entry, "yt:channelId"),
            "title": _text(entry, "atom:title"),
            "url": link or f"https://www.youtube.com/watch?v={vid}",
            "is_short": "/shorts/" in (link or ""),
            "published_ts": published,
            "published_at": _iso(published),
            "updated_at": _iso(_parse_time(_text(entry, "atom:updated"))),
            "views": views,
            "likes": likes,
            "rating": rating,
            "thumbnail": thumb or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "description": description,
        })
    return {"channel": channel, "videos": videos}


def _text(node: ET.Element, path: str) -> str:
    el = node.find(path, NS)
    return (el.text or "").strip() if el is not None and el.text else ""


def _link(node: ET.Element) -> str:
    for el in node.findall("atom:link", NS):
        if el.get("rel") == "alternate":
            return el.get("href", "")
    return ""


def _int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _parse_time(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
