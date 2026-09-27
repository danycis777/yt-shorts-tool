"""YouTube Data API v3 client with caching, quota accounting and friendly errors."""

from __future__ import annotations

import html
import re
import time
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import config
from .net import HttpError, NetworkError, get_json
from .quota import COSTS, QuotaTracker

VIDEO_PARTS = ("snippet", "statistics", "contentDetails", "status", "topicDetails", "player")
CHANNEL_PARTS = ("snippet", "statistics", "contentDetails", "brandingSettings", "topicDetails")
PLAYER_MAX_WIDTH = 480  # asks the API for embed dimensions, which reveal vertical (Shorts) videos

FRIENDLY_ERRORS = {
    "quotaExceeded": "Your YouTube API daily quota is used up. It resets at midnight Pacific Time; cached "
                     "results keep working until then. For a permanently higher limit, request a quota "
                     "extension from Google (YouTube API Services audit form).",
    "dailyLimitExceeded": "Your YouTube API daily quota is used up. It resets at midnight Pacific Time.",
    "rateLimitExceeded": "YouTube is rate-limiting requests. Wait a minute and try again.",
    "keyInvalid": "Your YouTube API key is not valid. Check it in Settings.",
    "keyExpired": "Your YouTube API key has expired. Create a new one in Google Cloud Console.",
    "accessNotConfigured": "The YouTube Data API v3 is not enabled for your API key's Google Cloud project. "
                           "Enable it in Google Cloud Console → APIs & Services → Library.",
    "ipRefererBlocked": "Your API key has application restrictions that block this computer. "
                        "Edit the key in Google Cloud Console and remove the HTTP-referrer/IP restriction.",
    "forbidden": "YouTube refused this request (the resource may be private or restricted).",
    "commentsDisabled": "Comments are disabled on this video.",
    "videoNotFound": "Video not found (it may be private, deleted or the ID is wrong).",
    "channelNotFound": "Channel not found.",
    "playlistNotFound": "Playlist not found.",
    "videoChartNotFound": "YouTube has no trending chart for that category in this region. Try another category.",
}


class YouTubeError(Exception):
    def __init__(self, reason: str, message: str, status: Optional[int] = None):
        self.reason = reason
        self.status = status
        self.raw_message = message
        super().__init__(FRIENDLY_ERRORS.get(reason, message or reason))


class NoApiKey(YouTubeError):
    def __init__(self) -> None:
        super().__init__(
            "noApiKey",
            "This feature needs a free YouTube Data API key. Add one in Settings (takes ~5 minutes).",
        )


def _unescape(text: Optional[str]) -> str:
    return html.unescape(text or "")


class YouTube:
    def __init__(self, api_key: str, db, quota: QuotaTracker, base: Optional[str] = None):
        self.api_key = (api_key or "").strip()
        self.db = db
        self.quota = quota
        self.base = (base or config.YOUTUBE_API_BASE).rstrip("/")
        self.units_this_request = 0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def require(self) -> None:
        if not self.enabled:
            raise NoApiKey()

    # -- low level -----------------------------------------------------------
    def _call(self, endpoint: str, params: Dict[str, Any], ttl: float = 0) -> Dict[str, Any]:
        self.require()
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        cache_key = "yt:" + endpoint + "?" + urllib.parse.urlencode(sorted(clean.items()))
        if ttl > 0:
            cached = self.db.cache_get(cache_key)
            if cached is not None:
                return cached
        query = dict(clean)
        query["key"] = self.api_key
        url = f"{self.base}/{endpoint}?{urllib.parse.urlencode(query)}"
        cost = COSTS.get(endpoint, 1)
        try:
            data = get_json(url, timeout=25, retries=2, retry_statuses=(500, 502, 503, 504))
        except HttpError as err:
            # Google still bills quota for most failed requests, except auth failures.
            if err.status not in (400, 401):
                self.quota.record(cost)
                self.units_this_request += cost
            raise _to_youtube_error(err) from None
        except NetworkError as err:
            raise YouTubeError("network", str(err)) from None
        self.quota.record(cost)
        self.units_this_request += cost
        if ttl > 0:
            self.db.cache_set(cache_key, data, ttl)
        return data

    # -- search ----------------------------------------------------------------
    def search(
        self,
        q: Optional[str] = None,
        *,
        max_results: int = 50,
        order: str = "relevance",
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        duration: Optional[str] = None,
        region: Optional[str] = None,
        language: Optional[str] = None,
        channel_id: Optional[str] = None,
        kind: str = "video",
        page_token: Optional[str] = None,
        ttl: float = 12 * 3600,
    ) -> Dict[str, Any]:
        """search.list (100 units). Returns {'items': [...], 'total': int, 'next': token}."""
        params = {
            "part": "snippet",
            "q": q,
            "type": kind,
            "maxResults": max(1, min(50, max_results)),
            "order": order,
            "publishedAfter": published_after,
            "publishedBefore": published_before,
            "videoDuration": duration if kind == "video" and duration in ("short", "medium", "long") else None,
            "regionCode": region,
            "relevanceLanguage": language,
            "channelId": channel_id,
            "pageToken": page_token,
        }
        data = self._call("search", params, ttl=ttl)
        items = []
        for it in data.get("items", []):
            id_obj = it.get("id", {})
            sn = it.get("snippet", {})
            items.append({
                "kind": id_obj.get("kind", "").replace("youtube#", ""),
                "video_id": id_obj.get("videoId"),
                "channel_id": id_obj.get("channelId") or sn.get("channelId"),
                "playlist_id": id_obj.get("playlistId"),
                "title": _unescape(sn.get("title")),
                "description": _unescape(sn.get("description")),
                "channel_title": _unescape(sn.get("channelTitle")),
                "published_at": sn.get("publishedAt"),
                "thumbnail": _best_thumb(sn.get("thumbnails")),
                "live": sn.get("liveBroadcastContent"),
            })
        return {
            "items": items,
            "total": data.get("pageInfo", {}).get("totalResults"),
            "next": data.get("nextPageToken"),
        }

    # -- videos ----------------------------------------------------------------
    def videos(self, ids: Iterable[str], *, max_age: float = 6 * 3600) -> List[Dict[str, Any]]:
        """videos.list for any number of ids (1 unit per 50). Items come back in input order.

        Items are cached individually so different features share fetched data; `max_age`
        controls how fresh cached statistics must be.
        """
        ids = [i for i in dict.fromkeys(ids) if i]
        found: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []
        now = time.time()
        for vid in ids:
            cached = self.db.cache_get("ytv:" + vid)
            if cached and now - cached.get("ts", 0) <= max_age:
                found[vid] = cached["item"]
            else:
                missing.append(vid)
        for chunk in _chunks(missing, 50):
            data = self._call("videos", {
                "part": ",".join(VIDEO_PARTS),
                "id": ",".join(chunk),
                "maxWidth": PLAYER_MAX_WIDTH,
            })
            for item in data.get("items", []):
                vid = item.get("id")
                if not vid:
                    continue
                found[vid] = item
                self.db.cache_set("ytv:" + vid, {"ts": now, "item": item}, 7 * 86400)
                st = item.get("statistics", {})
                self.db.add_video_snapshot(vid, _int(st.get("viewCount")), _int(st.get("likeCount")),
                                           _int(st.get("commentCount")), ts=now)
        return [found[v] for v in ids if v in found]

    def most_popular(self, region: str, category_id: Optional[str] = None, max_results: int = 50,
                     ttl: float = 1800) -> List[Dict[str, Any]]:
        """The 'Trending' chart for a region (1 unit per 50)."""
        items: List[Dict[str, Any]] = []
        token = None
        while len(items) < max_results:
            data = self._call("videos", {
                "part": ",".join(VIDEO_PARTS),
                "chart": "mostPopular",
                "regionCode": region,
                "videoCategoryId": category_id,
                "maxResults": min(50, max_results - len(items)),
                "maxWidth": PLAYER_MAX_WIDTH,
                "pageToken": token,
            }, ttl=ttl)
            items.extend(data.get("items", []))
            token = data.get("nextPageToken")
            if not token:
                break
        now = time.time()
        for item in items:
            if item.get("id"):
                self.db.cache_set("ytv:" + item["id"], {"ts": now, "item": item}, 7 * 86400)
        return items

    # -- channels ----------------------------------------------------------------
    def channels(self, ids: Iterable[str] = (), *, max_age: float = 12 * 3600) -> List[Dict[str, Any]]:
        ids = [i for i in dict.fromkeys(ids) if i]
        found: Dict[str, Dict[str, Any]] = {}
        missing: List[str] = []
        now = time.time()
        for cid in ids:
            cached = self.db.cache_get("ytc:" + cid)
            if cached and now - cached.get("ts", 0) <= max_age:
                found[cid] = cached["item"]
            else:
                missing.append(cid)
        for chunk in _chunks(missing, 50):
            data = self._call("channels", {"part": ",".join(CHANNEL_PARTS), "id": ",".join(chunk)})
            for item in data.get("items", []):
                self._store_channel(item, now)
                found[item["id"]] = item
        return [found[c] for c in ids if c in found]

    def channel_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        handle = handle if handle.startswith("@") else "@" + handle
        data = self._call("channels", {"part": ",".join(CHANNEL_PARTS), "forHandle": handle}, ttl=86400)
        items = data.get("items") or []
        if items:
            self._store_channel(items[0], time.time())
        return items[0] if items else None

    def channel_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        data = self._call("channels", {"part": ",".join(CHANNEL_PARTS), "forUsername": username}, ttl=86400)
        items = data.get("items") or []
        if items:
            self._store_channel(items[0], time.time())
        return items[0] if items else None

    def _store_channel(self, item: Dict[str, Any], now: float) -> None:
        cid = item.get("id")
        if not cid:
            return
        self.db.cache_set("ytc:" + cid, {"ts": now, "item": item}, 7 * 86400)
        st = item.get("statistics", {})
        subs = None if st.get("hiddenSubscriberCount") else _int(st.get("subscriberCount"))
        self.db.add_channel_snapshot(cid, subs, _int(st.get("viewCount")), _int(st.get("videoCount")), ts=now)

    # -- playlists -------------------------------------------------------------------
    def playlist_video_ids(self, playlist_id: str, max_items: int = 50, ttl: float = 3 * 3600) -> List[str]:
        """Most recent video ids in a playlist (1 unit per 50). Uploads playlists are newest-first."""
        out: List[str] = []
        token = None
        while len(out) < max_items:
            data = self._call("playlistItems", {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
                "pageToken": token,
            }, ttl=ttl)
            for item in data.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid:
                    out.append(vid)
            token = data.get("nextPageToken")
            if not token:
                break
        return out[:max_items]

    # -- misc ------------------------------------------------------------------------
    def categories(self, region: str, language: str = "en") -> List[Dict[str, str]]:
        data = self._call("videoCategories", {"part": "snippet", "regionCode": region, "hl": language},
                          ttl=30 * 86400)
        return [
            {"id": it["id"], "title": it.get("snippet", {}).get("title", "")}
            for it in data.get("items", [])
            if it.get("snippet", {}).get("assignable")
        ]

    def comments(self, video_id: str, max_results: int = 100, order: str = "relevance") -> List[Dict[str, Any]]:
        data = self._call("commentThreads", {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max(1, min(100, max_results)),
            "order": order,
            "textFormat": "plainText",
        }, ttl=6 * 3600)
        out = []
        for it in data.get("items", []):
            top = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            out.append({
                "text": top.get("textDisplay", ""),
                "likes": _int(top.get("likeCount")) or 0,
                "author": top.get("authorDisplayName", ""),
                "published_at": top.get("publishedAt"),
                "replies": _int(it.get("snippet", {}).get("totalReplyCount")) or 0,
            })
        return out


# -- helpers -----------------------------------------------------------------------------

def uploads_playlist(channel_id: str, kind: str = "all") -> str:
    """Channel uploads playlists: UU = all, UUSH = Shorts only, UULF = long-form only."""
    suffix = channel_id[2:] if channel_id.startswith("UC") else channel_id
    prefix = {"short": "UUSH", "long": "UULF"}.get(kind, "UU")
    return prefix + suffix


def _to_youtube_error(err: HttpError) -> YouTubeError:
    payload = err.json() or {}
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    message = error.get("message", "") if isinstance(error, dict) else ""
    reason = ""
    details = error.get("errors") if isinstance(error, dict) else None
    if details:
        reason = details[0].get("reason", "")
    if not reason and isinstance(error, dict):
        for d in error.get("details", []) or []:
            if d.get("reason"):
                reason = d["reason"]
                break
    lowered = message.lower()
    if "api key not valid" in lowered or reason in ("API_KEY_INVALID", "keyInvalid"):
        reason = "keyInvalid"
    elif "has not been used in project" in lowered or "is disabled" in lowered or reason in (
        "SERVICE_DISABLED", "accessNotConfigured"
    ):
        reason = "accessNotConfigured"
    elif reason in ("API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED", "API_KEY_SERVICE_BLOCKED"):
        reason = "ipRefererBlocked"
    elif "quota" in lowered and not reason:
        reason = "quotaExceeded"
    return YouTubeError(reason or f"http{err.status}", message or f"YouTube API error {err.status}", err.status)


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _best_thumb(thumbs: Optional[Dict[str, Any]]) -> str:
    if not thumbs:
        return ""
    for key in ("maxres", "standard", "high", "medium", "default"):
        if key in thumbs and thumbs[key].get("url"):
            return thumbs[key]["url"]
    return ""


def parse_iso_duration(value: Optional[str]) -> Optional[int]:
    """'PT1H2M3S' -> 3723 seconds; 'P0D' -> 0."""
    if not value:
        return None
    m = re.fullmatch(
        r"P(?:(?P<w>\d+)W)?(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?",
        value,
    )
    if not m:
        return None
    parts = {k: float(v) if v else 0.0 for k, v in m.groupdict().items()}
    total = parts["w"] * 604800 + parts["d"] * 86400 + parts["h"] * 3600 + parts["m"] * 60 + parts["s"]
    return int(round(total))


best_thumbnail = _best_thumb
to_int = _int
