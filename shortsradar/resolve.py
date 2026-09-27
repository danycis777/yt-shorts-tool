"""Turn whatever the user pastes (URLs, @handles, IDs) into video / channel IDs."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from . import config
from .net import BROWSER_UA, HttpError, NetworkError, request

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
HANDLE = re.compile(r"^@?[A-Za-z0-9._\-À-￿]{3,100}$")


class ResolveError(Exception):
    pass


def parse_video_id(text: str) -> Optional[str]:
    text = (text or "").strip()
    if VIDEO_ID.match(text):
        return text
    if not re.match(r"^[a-z]+://", text, re.I) and ("youtube." in text or "youtu.be" in text):
        text = "https://" + text
    try:
        url = urllib.parse.urlparse(text)
    except ValueError:
        return None
    host = (url.hostname or "").lower()
    path = url.path or ""
    if host.endswith("youtu.be"):
        cand = path.strip("/").split("/")[0]
        return cand if VIDEO_ID.match(cand) else None
    if "youtube." in host or host.endswith("youtube-nocookie.com"):
        qs = urllib.parse.parse_qs(url.query)
        if "v" in qs and VIDEO_ID.match(qs["v"][0]):
            return qs["v"][0]
        m = re.match(r"^/(?:shorts|embed|live|v|e)/([A-Za-z0-9_-]{11})", path)
        if m:
            return m.group(1)
    return None


def parse_channel_ref(text: str) -> Tuple[str, str]:
    """Classify a channel reference -> (kind, value), kind in id|handle|username|custom|video."""
    text = (text or "").strip()
    if CHANNEL_ID.match(text):
        return "id", text
    if text.startswith("@") and HANDLE.match(text):
        return "handle", text
    if not re.match(r"^[a-z]+://", text, re.I) and "youtube." in text:
        text = "https://" + text
    if re.match(r"^[a-z]+://", text, re.I):
        url = urllib.parse.urlparse(text)
        parts = [urllib.parse.unquote(p) for p in (url.path or "").split("/") if p]
        if parts:
            if parts[0] == "channel" and len(parts) > 1 and CHANNEL_ID.match(parts[1]):
                return "id", parts[1]
            if parts[0].startswith("@"):
                return "handle", parts[0]
            if parts[0] == "user" and len(parts) > 1:
                return "username", parts[1]
            if parts[0] == "c" and len(parts) > 1:
                return "custom", parts[1]
        vid = parse_video_id(text)
        if vid:
            return "video", vid
        raise ResolveError("That URL doesn't look like a YouTube channel link.")
    if HANDLE.match(text) and " " not in text:
        return "handle", "@" + text.lstrip("@")
    raise ResolveError("Paste a channel URL, @handle or channel ID (starts with UC…).")


def channel_id_from_web(kind: str, value: str) -> str:
    """Keyless fallback: read the channel ID from the public channel page."""
    if kind == "handle":
        path = "/" + value if value.startswith("@") else "/@" + value
    elif kind == "username":
        path = "/user/" + urllib.parse.quote(value)
    elif kind == "custom":
        path = "/c/" + urllib.parse.quote(value)
    else:
        raise ResolveError("Unsupported channel reference.")
    url = config.YOUTUBE_WEB_BASE + urllib.parse.quote(path, safe="/@%")
    try:
        _, _, body = request(url, headers={
            "User-Agent": BROWSER_UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": "SOCS=CAI; CONSENT=YES+cb",
        }, timeout=20, retries=1)
    except HttpError as err:
        if err.status == 404:
            raise ResolveError(f"No YouTube channel found for {value}.") from None
        raise ResolveError(f"Couldn't look up {value} (HTTP {err.status}).") from None
    except NetworkError as err:
        raise ResolveError(str(err)) from None
    page = body.decode("utf-8", "replace")
    for pattern in (
        r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[A-Za-z0-9_-]{22})"',
        r'"externalId":"(UC[A-Za-z0-9_-]{22})"',
        r'<meta itemprop="identifier" content="(UC[A-Za-z0-9_-]{22})"',
        r'"browseId":"(UC[A-Za-z0-9_-]{22})"',
    ):
        m = re.search(pattern, page)
        if m:
            return m.group(1)
    raise ResolveError(f"Couldn't find the channel ID for {value}. Paste the channel ID (UC…) instead.")


def oembed(video_id: str) -> Optional[Dict[str, Any]]:
    """Official oEmbed endpoint: title, author and player size (vertical = Short). Keyless, no quota."""
    url = f"{config.YOUTUBE_WEB_BASE}/oembed?" + urllib.parse.urlencode({
        "url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"})
    try:
        _, _, body = request(url, headers={"User-Agent": BROWSER_UA}, timeout=12, retries=1)
        data = json.loads(body.decode("utf-8", "replace"))
    except (HttpError, NetworkError, ValueError):
        return None
    width, height = data.get("width"), data.get("height")
    aspect = None
    if isinstance(width, (int, float)) and isinstance(height, (int, float)) and height:
        aspect = width / height
    return {
        "title": data.get("title", ""),
        "author": data.get("author_name", ""),
        "author_url": data.get("author_url", ""),
        "thumbnail": data.get("thumbnail_url", ""),
        "aspect": aspect,
    }
