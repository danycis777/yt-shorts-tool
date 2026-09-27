"""Demo backend: a deterministic fake of the YouTube Data API v3, autocomplete, RSS feeds, oEmbed and
channel pages. Used by the test-suite and by `run.py --demo` so the UI can be explored without an API
key. All data is synthetic and clearly labelled as demo data in the UI."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

NICHES = {
    "minecraft": {
        "subjects": ["redstone door", "redstone farm", "survival house", "hardcore world", "piston trick",
                     "hidden base", "iron farm", "speedrun", "mob farm", "starter house", "nether portal",
                     "villager trading hall"],
        "tags": ["minecraft", "minecraft shorts", "minecraft redstone", "redstone", "minecraft build",
                 "minecraft tutorial", "minecraft survival", "gaming", "minecraft hacks"],
        "category": "20",
    },
    "cooking": {
        "subjects": ["pasta", "garlic bread", "fried rice", "smash burger", "ramen hack", "chocolate cake",
                     "air fryer chicken", "5 minute breakfast", "meal prep", "street food", "pancakes"],
        "tags": ["cooking", "recipe", "easy recipe", "food", "cooking shorts", "quick recipes", "dinner ideas"],
        "category": "26",
    },
    "fitness": {
        "subjects": ["ab workout", "push ups", "home workout", "fat loss", "glute exercise", "morning routine",
                     "pull up progression", "10 minute workout", "stretching", "gym mistakes"],
        "tags": ["fitness", "workout", "gym", "home workout", "fitness motivation", "exercise", "gym tips"],
        "category": "17",
    },
    "ai tools": {
        "subjects": ["chatgpt trick", "ai video generator", "ai website builder", "free ai tool", "prompt hack",
                     "ai voice", "ai thumbnail", "automation workflow", "ai side hustle", "ai image editor"],
        "tags": ["ai", "ai tools", "artificial intelligence", "chatgpt", "ai video", "productivity", "tech"],
        "category": "28",
    },
}
SHORT_PATTERNS = [
    "This {s} trick is insane", "I tried the viral {s}", "{s} in 30 seconds", "Nobody knows this {s} secret",
    "{s} level 1 vs level 100", "Stop doing {s} like this", "The easiest {s} ever", "POV: your first {s}",
    "Wait for the {s}...", "Rating every {s}", "{s} but it gets better", "Why your {s} fails",
]
LONG_PATTERNS = [
    "The Ultimate {S} Guide for Beginners", "I Spent 100 Days on {S}", "10 {S} Mistakes Everyone Makes",
    "{S}: Everything You Need to Know", "I Tested Every {S} Method", "How to Master {S} (Step by Step)",
    "The Truth About {S}", "{S} Tier List 2026",
]
CATEGORIES = [("1", "Film & Animation"), ("2", "Autos & Vehicles"), ("10", "Music"), ("15", "Pets & Animals"),
              ("17", "Sports"), ("20", "Gaming"), ("22", "People & Blogs"), ("23", "Comedy"),
              ("24", "Entertainment"), ("25", "News & Politics"), ("26", "Howto & Style"), ("27", "Education"),
              ("28", "Science & Technology")]


def _id(prefix: str, seed: str, length: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    h = hashlib.sha256(seed.encode()).digest()
    return prefix + "".join(alphabet[b % 64] for b in h[:length])


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dur(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return "PT" + (f"{h}H" if h else "") + (f"{m}M" if m else "") + (f"{s}S" if s or not (h or m) else "")


class DemoWorld:
    def __init__(self, seed: int = 7, now: Optional[float] = None):
        rng = random.Random(seed)
        self.now = now or time.time()
        self.channels: Dict[str, Dict[str, Any]] = {}
        self.videos: Dict[str, Dict[str, Any]] = {}
        self.uploads: Dict[str, List[str]] = {}
        adjectives = ["Pixel", "Daily", "Quick", "Epic", "Chill", "Smart", "Mega", "Tiny", "Pro", "Lazy", "Wild",
                      "Clever", "Happy", "Bold"]
        nouns = {"minecraft": ["Blocks", "Crafter", "Redstone", "Builds", "Miner"],
                 "cooking": ["Kitchen", "Chef", "Eats", "Bites", "Cook"],
                 "fitness": ["Fit", "Gains", "Lifts", "Coach", "Moves"],
                 "ai tools": ["AI", "Bots", "Prompts", "Tech", "Labs"]}
        n = 0
        for niche, info in NICHES.items():
            for i in range(10):
                n += 1
                name = f"{rng.choice(adjectives)} {rng.choice(nouns[niche])}"
                if any(c["title"] == name for c in self.channels.values()):
                    name += f" {i + 2}"
                cid = _id("UC", f"chan-{niche}-{i}", 22)
                subs = int(10 ** rng.uniform(2.7, 6.6))
                shorts_ratio = rng.choice([0.9, 0.8, 0.6, 0.3])
                handle = "@" + name.lower().replace(" ", "")
                self.channels[cid] = {
                    "id": cid, "title": name, "handle": handle, "niche": niche, "subs": subs,
                    "created": self.now - rng.uniform(1, 8) * 365 * 86400, "country": rng.choice(["US", "US", "GB", "CA", "IN", "AU"]),
                    "shorts_ratio": shorts_ratio, "base": max(80.0, subs * rng.uniform(0.02, 0.4)),
                }
                self.uploads[cid] = []
                count = rng.randint(35, 70)
                t = self.now - rng.uniform(0.1, 1.5) * 86400
                for j in range(count):
                    is_short = rng.random() < shorts_ratio
                    subject = rng.choice(info["subjects"])
                    if is_short:
                        title = rng.choice(SHORT_PATTERNS).format(s=subject)
                        title = title[0].upper() + title[1:]
                        duration = rng.choice([rng.randint(8, 59), rng.randint(8, 59), rng.randint(61, 170)])
                    else:
                        title = rng.choice(LONG_PATTERNS).format(S=subject.title())
                        duration = rng.randint(300, 1800)
                    age_days = (self.now - t) / 86400.0
                    growth = 1 - math.exp(-max(age_days, 0.05) / 3.0)
                    mult = 10 ** rng.gauss(0, 0.35)
                    if rng.random() < 0.08:
                        mult *= rng.uniform(4, 25)  # outliers
                    base = self.channels[cid]["base"] * (2.2 if is_short else 1.0)
                    views = max(12, int(base * mult * growth))
                    vid = _id("", f"vid-{cid}-{j}", 11)
                    self.videos[vid] = {
                        "id": vid, "channel_id": cid, "title": title, "published": t, "short": is_short,
                        "duration": duration, "views": views, "likes": int(views * rng.uniform(0.015, 0.07)),
                        "comments": int(views * rng.uniform(0.0005, 0.004)),
                        "tags": rng.sample(info["tags"], k=rng.randint(0, min(7, len(info["tags"])))) + [subject],
                        "description": f"{title}. In this {'short' if is_short else 'video'} I show {subject}. "
                                       f"#{niche.replace(' ', '')} #{subject.replace(' ', '')}"
                                       + (" #shorts" if is_short else "\n\n0:00 Intro\n1:10 Setup\n4:20 Result\n\nSubscribe for more!"),
                        "category": info["category"], "niche": niche,
                    }
                    self.uploads[cid].append(vid)
                    t -= rng.uniform(0.4, 4.5) * 86400
        self.by_handle = {c["handle"].lower(): cid for cid, c in self.channels.items()}
        self.ai_requests: List[Dict[str, Any]] = []
        self.rss_down = False  # simulate YouTube's periodic RSS outages

    # --- API resources ------------------------------------------------------------------------------
    def video_resource(self, vid: str) -> Dict[str, Any]:
        v = self.videos[vid]
        c = self.channels[v["channel_id"]]
        w, h = (270, 480) if v["short"] else (480, 270)
        return {
            "kind": "youtube#video", "id": vid,
            "snippet": {
                "publishedAt": _iso(v["published"]), "channelId": c["id"], "title": v["title"],
                "description": v["description"], "channelTitle": c["title"], "tags": v["tags"],
                "categoryId": v["category"], "liveBroadcastContent": "none", "defaultAudioLanguage": "en",
                "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}},
            },
            "contentDetails": {"duration": _dur(v["duration"]), "definition": "hd", "caption": "false"},
            "statistics": {"viewCount": str(v["views"]), "likeCount": str(v["likes"]), "commentCount": str(v["comments"])},
            "status": {"privacyStatus": "public", "madeForKids": False},
            "player": {"embedHtml": f'<iframe width="{w}" height="{h}"></iframe>', "embedWidth": str(w), "embedHeight": str(h)},
        }

    def channel_resource(self, cid: str) -> Dict[str, Any]:
        c = self.channels[cid]
        vids = self.uploads[cid]
        return {
            "kind": "youtube#channel", "id": cid,
            "snippet": {"title": c["title"], "description": f"{c['title']} makes {c['niche']} videos.",
                        "customUrl": c["handle"], "publishedAt": _iso(c["created"]), "country": c["country"],
                        "thumbnails": {"high": {"url": "https://yt3.ggpht.com/demo-avatar"}}},
            "statistics": {"viewCount": str(sum(self.videos[v]["views"] for v in vids) * 3),
                           "subscriberCount": str(c["subs"]), "hiddenSubscriberCount": False,
                           "videoCount": str(len(vids))},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}},
            "brandingSettings": {"channel": {"keywords": f'{c["niche"]} "{c["niche"]} shorts" tutorials'}},
        }

    def search(self, q: str, order: str, after: Optional[float], duration: Optional[str],
               channel_id: Optional[str]) -> List[str]:
        words = [w for w in q.lower().split() if len(w) > 2]
        scored = []
        for vid, v in self.videos.items():
            if after and v["published"] < after:
                continue
            if channel_id and v["channel_id"] != channel_id:
                continue
            if duration == "short" and v["duration"] >= 240:
                continue
            text = (v["title"] + " " + " ".join(v["tags"]) + " " + v["niche"]).lower()
            hits = sum(1 for w in words if w in text)
            if words and hits == 0:
                continue
            scored.append((vid, hits))
        if order == "viewCount":
            scored.sort(key=lambda x: -self.videos[x[0]]["views"])
        elif order == "date":
            scored.sort(key=lambda x: -self.videos[x[0]]["published"])
        else:
            scored.sort(key=lambda x: (-x[1], -math.log10(self.videos[x[0]]["views"] + 1)
                                       - 0.3 * math.log10(self.channels[self.videos[x[0]]["channel_id"]]["subs"])))
        return [vid for vid, _ in scored]

    def suggestions(self, q: str) -> List[str]:
        q = q.lower()
        pool = []
        for niche, info in NICHES.items():
            pool.append(niche)
            pool += [f"{niche} {s}" for s in info["subjects"]]
            pool += [f"how to {s}" for s in info["subjects"]]
            pool += info["tags"]
        pool += ["minecraft", "minecraft live", "mrbeast", "music", "movie trailer", "cooking asmr", "fitness motivation"]
        out = []
        for p in dict.fromkeys(pool):
            if p.startswith(q) and p != q.strip() or p == q.strip():
                out.append(p)
        out.sort(key=lambda s: (s != q.strip(), len(s), s))
        return out[:10]

    def rss(self, cid: str) -> str:
        c = self.channels[cid]
        entries = []
        for vid in self.uploads[cid][:15]:
            v = self.videos[vid]
            link = f"https://www.youtube.com/shorts/{vid}" if v["short"] else f"https://www.youtube.com/watch?v={vid}"
            entries.append(f"""
 <entry>
  <id>yt:video:{vid}</id><yt:videoId>{vid}</yt:videoId><yt:channelId>{cid}</yt:channelId>
  <title>{escape(v['title'])}</title>
  <link rel="alternate" href="{link}"/>
  <published>{_iso(v['published'])}</published><updated>{_iso(self.now)}</updated>
  <media:group>
   <media:title>{escape(v['title'])}</media:title>
   <media:thumbnail url="https://i.ytimg.com/vi/{vid}/hqdefault.jpg" width="480" height="360"/>
   <media:description>{escape(v['description'])}</media:description>
   <media:community><media:starRating count="{v['likes']}" average="5.00" min="1" max="5"/><media:statistics views="{v['views']}"/></media:community>
  </media:group>
 </entry>""")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <yt:channelId>{cid[2:]}</yt:channelId><title>{escape(c['title'])}</title>
 <link rel="alternate" href="https://www.youtube.com/channel/{cid}"/>{''.join(entries)}
</feed>"""

    def tick(self) -> None:
        """Advance the world a little (views grow) so snapshots show movement."""
        now = time.time()
        rng = random.Random(int(now // 60))
        for v in self.videos.values():
            age = max((now - v["published"]) / 86400.0, 0.05)
            if age < 10:
                bump = int(v["views"] * rng.uniform(0.0005, 0.004) / age)
                v["views"] += bump
                v["likes"] += int(bump * 0.04)


class _Handler(BaseHTTPRequestHandler):
    world: DemoWorld = None  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # silence
        pass

    def _send(self, status: int, body: Any, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype + "; charset=UTF-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, reason: str, message: str) -> None:
        self._send(status, {"error": {"code": status, "message": message, "errors": [{"reason": reason, "message": message}]}})

    def do_POST(self) -> None:
        """Fake Anthropic Messages API (used by the test-suite to exercise the real SDK call path)."""
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "bad json"}})
        if urllib.parse.urlparse(self.path).path != "/v1/messages":
            return self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": "not found"}})
        self.world.ai_requests.append({"headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        if self.headers.get("x-api-key") == "bad-ai-key":
            return self._send(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
        props = (((body.get("output_config") or {}).get("format") or {}).get("schema") or {}).get("properties") or {}
        topic = json.dumps(body.get("messages", [{}])[0].get("content", ""))[:40]
        if "titles" in props:
            data = {"titles": [{"title": f"I Tried This For 7 Days {i}", "angle": "experiment", "why": "stakes"} for i in range(10)]}
        elif "hooks" in props:
            data = {"hooks": [{"text": "Stop scrolling right now", "type": "pattern interrupt", "why": "breaks the scroll"}]}
        elif "beats" in props:
            data = {"title": "t", "hook": "h", "beats": [{"time": "0:00", "voiceover": "v", "on_screen_text": "o", "visual": "x"}],
                    "cta": "c", "loop": "l", "caption": "cap", "hashtags": ["#shorts"]}
        elif "ideas" in props:
            data = {"ideas": [{"title": "Idea", "hook": "Hook", "concept": "Concept", "why_it_works": "Why"}]}
        elif "description" in props:
            data = {"description": "Minecraft redstone door tutorial. Subscribe!", "hashtags": ["#minecraft"], "pinned_comment": "?"}
        else:
            data = {"tags": ["minecraft redstone", "redstone"], "hashtags": ["#minecraft"]}
        return self._send(200, {
            "id": "msg_demo", "type": "message", "role": "assistant", "model": body.get("model", "demo"),
            "content": [{"type": "thinking", "thinking": "", "signature": "demo"}, {"type": "text", "text": json.dumps(data)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 42, "output_tokens": 99, "note": topic},
        })

    def do_GET(self) -> None:  # noqa: C901
        url = urllib.parse.urlparse(self.path)
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        w = self.world
        path = url.path
        if path.startswith("/youtube/v3/"):
            key = qs.get("key", "")
            if not key:
                return self._error(403, "forbidden", "Method doesn't allow unregistered callers")
            if key == "bad":
                return self._error(400, "badRequest", "API key not valid. Please pass a valid API key.")
            if key == "quota":
                return self._error(403, "quotaExceeded", "The request cannot be completed because you have exceeded your quota.")
            return self._api(path[len("/youtube/v3/"):], qs)
        if path == "/complete/search":
            q = qs.get("q", "")
            return self._send(200, json.dumps([q, w.suggestions(q), [], {}]), "text/javascript")
        if path == "/feeds/videos.xml":
            cid = qs.get("channel_id", "")
            if cid not in w.channels or w.rss_down:
                return self._send(404, "<html>not found</html>", "text/html")
            return self._send(200, w.rss(cid), "application/atom+xml")
        if path == "/oembed":
            vid = urllib.parse.parse_qs(urllib.parse.urlparse(qs.get("url", "")).query).get("v", [""])[0]
            v = w.videos.get(vid)
            if not v:
                return self._send(404, "Not Found", "text/plain")
            c = w.channels[v["channel_id"]]
            wd, ht = (113, 200) if v["short"] else (200, 113)
            return self._send(200, {"title": v["title"], "author_name": c["title"],
                                    "author_url": f"https://www.youtube.com/{c['handle']}", "width": wd, "height": ht,
                                    "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
        if path.startswith("/@"):
            cid = w.by_handle.get(urllib.parse.unquote(path[1:]).lower())
            if not cid:
                return self._send(404, "<html>404</html>", "text/html")
            return self._send(200, f'<html><head><link rel="canonical" href="https://www.youtube.com/channel/{cid}"></head></html>', "text/html")
        return self._send(404, {"error": "not found"})

    def _api(self, endpoint: str, qs: Dict[str, str]) -> None:  # noqa: C901
        w = self.world
        max_results = int(qs.get("maxResults", "5"))
        if endpoint == "search":
            after = None
            if qs.get("publishedAfter"):
                after = dt.datetime.fromisoformat(qs["publishedAfter"].replace("Z", "+00:00")).timestamp()
            ids = w.search(qs.get("q", ""), qs.get("order", "relevance"), after, qs.get("videoDuration"), qs.get("channelId"))
            start = int(qs.get("pageToken", "0") or 0)
            page = ids[start:start + max_results]
            items = []
            for vid in page:
                v = w.videos[vid]
                c = w.channels[v["channel_id"]]
                items.append({"kind": "youtube#searchResult", "id": {"kind": "youtube#video", "videoId": vid},
                              "snippet": {"publishedAt": _iso(v["published"]), "channelId": c["id"],
                                          "title": v["title"].replace("'", "&#39;"), "description": v["description"][:150],
                                          "channelTitle": c["title"], "liveBroadcastContent": "none",
                                          "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}}}})
            nxt = str(start + max_results) if start + max_results < len(ids) else None
            return self._send(200, {"items": items, "pageInfo": {"totalResults": len(ids), "resultsPerPage": max_results},
                                    **({"nextPageToken": nxt} if nxt else {})})
        if endpoint == "videos":
            if qs.get("chart") == "mostPopular":
                cutoff = w.now - 7 * 86400
                ids = sorted((v for v in w.videos.values() if v["published"] >= cutoff and
                              (not qs.get("videoCategoryId") or v["category"] == qs["videoCategoryId"])),
                             key=lambda v: -v["views"] / max((w.now - v["published"]) / 3600, 1))
                start = int(qs.get("pageToken", "0") or 0)
                page = [v["id"] for v in ids[start:start + max_results]]
                nxt = str(start + max_results) if start + max_results < min(len(ids), 200) else None
                return self._send(200, {"items": [w.video_resource(v) for v in page], **({"nextPageToken": nxt} if nxt else {})})
            ids = [i for i in qs.get("id", "").split(",") if i in w.videos]
            return self._send(200, {"items": [w.video_resource(v) for v in ids]})
        if endpoint == "channels":
            if qs.get("forHandle"):
                cid = w.by_handle.get(qs["forHandle"].lower() if qs["forHandle"].startswith("@") else "@" + qs["forHandle"].lower())
                return self._send(200, {"items": [w.channel_resource(cid)] if cid else []})
            ids = [i for i in qs.get("id", "").split(",") if i in w.channels]
            return self._send(200, {"items": [w.channel_resource(c) for c in ids]})
        if endpoint == "playlistItems":
            pl = qs.get("playlistId", "")
            prefix = "UUSH" if pl.startswith("UUSH") else "UULF" if pl.startswith("UULF") else "UU"
            cid = "UC" + pl[len(prefix):]
            if cid not in w.channels:
                return self._error(404, "playlistNotFound", "The playlist identified with the request's playlistId parameter cannot be found.")
            vids = w.uploads[cid]
            if prefix == "UUSH":
                vids = [v for v in vids if w.videos[v]["short"]]
            elif prefix == "UULF":
                vids = [v for v in vids if not w.videos[v]["short"]]
            if not vids:
                return self._error(404, "playlistNotFound", "The playlist identified with the request's playlistId parameter cannot be found.")
            start = int(qs.get("pageToken", "0") or 0)
            page = vids[start:start + max_results]
            nxt = str(start + max_results) if start + max_results < len(vids) else None
            return self._send(200, {"items": [{"contentDetails": {"videoId": v, "videoPublishedAt": _iso(w.videos[v]["published"])}} for v in page],
                                    **({"nextPageToken": nxt} if nxt else {})})
        if endpoint == "videoCategories":
            return self._send(200, {"items": [{"id": i, "snippet": {"title": t, "assignable": True}} for i, t in CATEGORIES]})
        if endpoint == "commentThreads":
            return self._send(200, {"items": [{"snippet": {"topLevelComment": {"snippet": {"textDisplay": t, "likeCount": n, "authorDisplayName": "viewer", "publishedAt": _iso(w.now)}}, "totalReplyCount": 0}}
                                              for t, n in (("How did you make this?", 12), ("Part 2 please!", 30), ("This worked for me", 4))]})
        return self._error(404, "notFound", "Unknown endpoint")


class DemoServer:
    """Runs the fake backend in a background thread."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, seed: int = 7, grow: bool = False):
        handler = type("DemoHandler", (_Handler,), {"world": DemoWorld(seed)})
        self.world = handler.world
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.base = f"http://{host}:{self.port}"
        self._grow = grow
        self._stop = threading.Event()

    def start(self) -> "DemoServer":
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        if self._grow:
            threading.Thread(target=self._grower, daemon=True).start()
        return self

    def _grower(self) -> None:
        while not self._stop.wait(60):
            self.world.tick()

    def stop(self) -> None:
        self._stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()

    def configure(self) -> None:
        """Point ShortsRadar's clients at this server."""
        from . import config
        config.YOUTUBE_API_BASE = self.base + "/youtube/v3"
        config.SUGGEST_BASE = self.base + "/complete/search"
        config.YOUTUBE_WEB_BASE = self.base

    def sample(self) -> Tuple[str, str, str]:
        """(a Short's video id, a channel id, a channel handle) for examples."""
        vid = next(v["id"] for v in self.world.videos.values() if v["short"])
        cid = next(iter(self.world.channels))
        return vid, cid, self.world.channels[cid]["handle"]
