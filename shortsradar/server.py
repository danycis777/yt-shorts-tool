"""Local web dashboard + JSON API (stdlib only). Binds to 127.0.0.1 by default.

Security: the API only answers requests that (1) target this server's own host name (blocks DNS
rebinding), (2) carry the custom `X-ShortsRadar` header (a cross-site page cannot add it without a
CORS preflight, which this server never approves) and (3) come from this origin or a browser
extension. Your API keys never leave this machine except in calls to Google/Anthropic.
"""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import (
    __version__, ai, channels, competitors, earnings, ideas, keywords, outliers, scorecard, tags, titles, trending,
)
from .config import SECRET_KEYS, mask
from .context import App
from .net import HttpError, NetworkError
from .resolve import ResolveError
from .rss import FeedError
from .seo import score_metadata
from .youtube import NoApiKey, YouTubeError

WEB_DIR = Path(__file__).parent / "web"
API_HEADER = "X-ShortsRadar"


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str = "error"):
        self.status = status
        self.code = code
        super().__init__(message)


Handler = Callable[[App, Dict[str, str], Any], Any]
ROUTES: Dict[Tuple[str, str], Handler] = {}


def route(method: str, path: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        ROUTES[(method, path)] = fn
        return fn
    return deco


# ---- helpers ----------------------------------------------------------------------------------------

def _b(q: Dict[str, str], key: str, default: bool = False) -> bool:
    v = q.get(key)
    if v is None or v == "":
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _i(q: Dict[str, str], key: str, default: Optional[int] = None) -> Optional[int]:
    v = q.get(key)
    if v is None or v == "":
        return default
    try:
        return int(float(v))
    except ValueError:
        raise ApiError(400, f"'{key}' must be a number") from None


def _f(q: Dict[str, str], key: str, default: Optional[float] = None) -> Optional[float]:
    v = q.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        raise ApiError(400, f"'{key}' must be a number") from None


def _req(q: Dict[str, str], key: str, label: str) -> str:
    v = (q.get(key) or "").strip()
    if not v:
        raise ApiError(400, f"Enter {label}.")
    return v


def _fmt(q: Dict[str, str], app: App, key: str = "format") -> str:
    v = (q.get(key) or app.settings.get("default_format") or "short").lower()
    return v if v in ("short", "long", "any") else "short"


# ---- status & settings ----------------------------------------------------------------------------

@route("GET", "/api/status")
def status(app: App, q, body):
    return {
        "version": __version__,
        "youtube_key": app.has_youtube_key,
        "ai": ai.status(app),
        "quota": app.quota.status(),
        "demo": bool(getattr(app, "demo", False)),
        "competitors": len(app.db.query("SELECT channel_id FROM competitors")),
        "settings": app.settings.public(),
    }


@route("GET", "/api/settings")
def get_settings(app: App, q, body):
    return app.settings.public()


@route("POST", "/api/settings")
def save_settings(app: App, q, body):
    if not isinstance(body, dict):
        raise ApiError(400, "Expected a JSON object")
    changes = {}
    for key, value in body.items():
        if key in SECRET_KEYS:
            current = app.settings.get(key) or ""
            if isinstance(value, str) and "*" in value and value == mask(current):
                continue  # unchanged masked value sent back by the form
        changes[key] = value
    app.settings.update(changes)
    app.quota.daily_limit = int(app.settings.get("daily_quota") or 10000)
    return app.settings.public()


@route("POST", "/api/settings/test-youtube")
def test_youtube(app: App, q, body):
    yt = app.youtube()
    yt.require()
    cats = yt.categories(app.region, app.language)
    return {"ok": True, "message": f"Your key works ({len(cats)} categories for {app.region}).",
            "quota_units": yt.units_this_request}


@route("POST", "/api/cache/clear")
def clear_cache(app: App, q, body):
    return {"cleared": app.db.cache_clear()}


@route("GET", "/api/quota")
def quota(app: App, q, body):
    return app.quota.status()


@route("GET", "/api/history")
def history(app: App, q, body):
    return {"items": app.db.recent_history(_i(q, "limit", 20) or 20)}


# ---- research ---------------------------------------------------------------------------------------

@route("GET", "/api/suggest")
def suggest(app: App, q, body):
    text = (q.get("q") or "").strip()
    if not text:
        return {"suggestions": []}
    return {"suggestions": app.suggest(q.get("language"), q.get("region")).get(text) or []}


@route("GET", "/api/keyword")
def keyword(app: App, q, body):
    return keywords.research(app, _req(q, "q", "a keyword"), fmt=_fmt(q, app), region=q.get("region") or None,
                             language=q.get("language") or None, deep=_b(q, "deep", True),
                             use_api=_b(q, "api", True))


@route("GET", "/api/keyword/quick")
def keyword_quick(app: App, q, body):
    return keywords.quick_score(app, _req(q, "q", "a keyword"), region=q.get("region") or None,
                                language=q.get("language") or None, with_competition=_b(q, "competition"))


@route("GET", "/api/outliers")
def outlier_search(app: App, q, body):
    chans = [c.strip() for c in (q.get("channels") or "").split(",") if c.strip()]
    chan_ids = [channels.resolve_channel_id(app, c) for c in chans]
    return outliers.find_outliers(
        app, keyword=(q.get("q") or "").strip() or None, channel_ids=chan_ids or None, fmt=_fmt(q, app),
        within=q.get("within") or "month", min_score=_f(q, "min_score"), min_views=_i(q, "min_views"),
        max_views=_i(q, "max_views"), min_subs=_i(q, "min_subs"), max_subs=_i(q, "max_subs"),
        sort=q.get("sort") or "score", region=q.get("region") or None, language=q.get("language") or None,
        deep=_b(q, "deep"), limit=_i(q, "limit", 50) or 50)


@route("GET", "/api/video")
def video(app: App, q, body):
    return scorecard.scorecard(app, _req(q, "id", "a video URL or ID"), keyword=q.get("keyword") or None)


@route("POST", "/api/video/tag-ranks")
def video_tag_ranks(app: App, q, body):
    body = body or {}
    vid = str(body.get("id") or "")
    tag_list = [str(t) for t in (body.get("tags") or [])][:5]
    if not vid or not tag_list:
        raise ApiError(400, "Provide a video id and up to 5 tags.")
    return {"ranks": scorecard.tag_ranks(app, vid, tag_list)}


@route("GET", "/api/channel")
def channel(app: App, q, body):
    return channels.audit(app, _req(q, "id", "a channel URL, @handle or ID"), max_videos=_i(q, "max", 100) or 100)


@route("GET", "/api/trending")
def trending_chart(app: App, q, body):
    return trending.chart(app, region=q.get("region") or None, category=q.get("category") or None,
                          fmt=(q.get("format") or "any"), limit=_i(q, "limit", 50) or 50)


@route("GET", "/api/trending/niche")
def trending_niche(app: App, q, body):
    return trending.niche(app, _req(q, "q", "a niche keyword"), hours=_i(q, "hours", 72) or 72,
                          fmt=_fmt(q, app), region=q.get("region") or None, language=q.get("language") or None)


# ---- competitors ---------------------------------------------------------------------------------------

@route("GET", "/api/competitors")
def competitor_list(app: App, q, body):
    return {"competitors": competitors.list_competitors(app), "alerts": competitors.alerts(app)}


@route("POST", "/api/competitors")
def competitor_add(app: App, q, body):
    ref = str((body or {}).get("ref") or "").strip()
    if not ref:
        raise ApiError(400, "Paste a channel URL, @handle or channel ID.")
    return competitors.add(app, ref)


@route("DELETE", "/api/competitors")
def competitor_remove(app: App, q, body):
    competitors.remove(app, _req(q, "id", "a channel id"))
    return {"ok": True}


@route("POST", "/api/competitors/refresh")
def competitor_refresh(app: App, q, body):
    return competitors.refresh(app)


@route("GET", "/api/competitors/feed")
def competitor_feed(app: App, q, body):
    return {"videos": competitors.feed(app, fmt=(q.get("format") or "any"), days=_i(q, "days", 14) or 14,
                                       sort=q.get("sort") or "score")}


# ---- tools ----------------------------------------------------------------------------------------------

@route("POST", "/api/seo/score")
def seo_score(app: App, q, body):
    body = body or {}
    tag_list = body.get("tags") or []
    if isinstance(tag_list, str):
        tag_list = [t.strip() for t in tag_list.split(",")]
    fmt = body.get("format") or "short"
    res = score_metadata(str(body.get("title") or ""), str(body.get("description") or ""), tag_list,
                         keyword=body.get("keyword") or None, fmt=fmt,
                         duration_s=body.get("duration_s"))
    res["title_score"] = titles.score_title(str(body.get("title") or ""), fmt=fmt, keyword=res["keyword"])
    return res


@route("POST", "/api/titles/score")
def title_score(app: App, q, body):
    body = body or {}
    items = body.get("titles") or []
    if isinstance(items, str):
        items = items.splitlines()
    return {"results": titles.compare_titles([str(t) for t in items][:50], fmt=body.get("format") or "short",
                                             keyword=body.get("keyword") or None)}


@route("GET", "/api/titles/generate")
def title_generate(app: App, q, body):
    return {"titles": titles.generate_titles(_req(q, "q", "a keyword"), fmt=_fmt(q, app), limit=20)}


@route("GET", "/api/tags")
def tag_suggest(app: App, q, body):
    return tags.suggest_tags(app, _req(q, "q", "a keyword"), fmt=_fmt(q, app), title=q.get("title") or None,
                             region=q.get("region") or None, language=q.get("language") or None,
                             use_api=_b(q, "api", True))


@route("GET", "/api/earnings")
def earnings_calc(app: App, q, body):
    share = _f(q, "shorts_share")
    return earnings.calculator(_f(q, "views", 0) or 0, category=q.get("category") or "Entertainment",
                               country=q.get("country") or app.region, fmt=q.get("format") or "short",
                               shorts_share=share / 100.0 if share is not None and share > 1 else share)


@route("GET", "/api/earnings/meta")
def earnings_meta(app: App, q, body):
    return {"categories": earnings.CATEGORIES, "countries": sorted(earnings.COUNTRY_MULTIPLIER)}


@route("GET", "/api/ai/status")
def ai_status(app: App, q, body):
    return {**ai.status(app), "tasks": ai.TASK_LIST}


@route("POST", "/api/ai")
def ai_run(app: App, q, body):
    body = body or {}
    task = str(body.pop("task", "") or q.get("task") or "")
    mode = str(body.pop("mode", "auto") or "auto")
    return ai.run(app, task, body, mode=mode)


@route("GET", "/api/ideas")
def daily_ideas(app: App, q, body):
    niches = [n.strip() for n in (q.get("niches") or "").split(",") if n.strip()] or None
    return ideas.daily_ideas(app, niches, fmt=_fmt(q, app), refresh=_b(q, "refresh"))


# ---- saved items ------------------------------------------------------------------------------------------

@route("GET", "/api/saved")
def saved_list(app: App, q, body):
    return {"items": app.db.saved_items(q.get("kind") or None)}


@route("POST", "/api/saved")
def saved_add(app: App, q, body):
    body = body or {}
    kind, ref = str(body.get("kind") or ""), str(body.get("ref") or "")
    if kind not in ("keyword", "video", "channel", "idea", "title", "outlier") or not ref:
        raise ApiError(400, "Invalid item.")
    return {"id": app.db.save_item(kind, ref[:500], str(body.get("title") or ref)[:300], body.get("data"))}


@route("DELETE", "/api/saved")
def saved_delete(app: App, q, body):
    app.db.delete_saved(_i(q, "id") or 0)
    return {"ok": True}


# ---- HTTP plumbing --------------------------------------------------------------------------------------------

def _error_payload(err: Exception) -> Tuple[int, Dict[str, Any]]:
    if isinstance(err, ApiError):
        return err.status, {"error": str(err), "code": err.code}
    if isinstance(err, NoApiKey):
        return 400, {"error": str(err), "code": "no_api_key"}
    if isinstance(err, YouTubeError):
        status = 429 if err.reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded") else \
            404 if err.reason.endswith("NotFound") else 502
        return status, {"error": str(err), "code": err.reason}
    if isinstance(err, ai.AIError):
        return 502, {"error": str(err), "code": "ai_error"}
    if isinstance(err, (ResolveError, FeedError, ValueError)):
        return 400, {"error": str(err), "code": "bad_request"}
    if isinstance(err, (NetworkError, HttpError)):
        return 502, {"error": str(err), "code": "network"}
    traceback.print_exc(file=sys.stderr)
    return 500, {"error": f"Unexpected error: {err}", "code": "internal"}


class RequestHandler(BaseHTTPRequestHandler):
    app: App = None  # type: ignore[assignment]
    allowed_hosts: List[str] = []
    server_version = f"ShortsRadar/{__version__}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "verbose", False):
            sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- responses
    def _send(self, status: int, payload: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    # -- checks
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in self.allowed_hosts

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        o = origin.lower()
        if o.startswith(("chrome-extension://", "moz-extension://", "safari-web-extension://")):
            return True
        return any(o == f"http://{h}" for h in self.allowed_hosts)

    # -- verbs
    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_HEAD(self) -> None:
        self._dispatch("GET")

    def do_OPTIONS(self) -> None:
        # No CORS: cross-origin pages are never allowed to call the API.
        self._send(403, b"", "text/plain")

    def _dispatch(self, method: str) -> None:
        if not self._host_ok():
            return self._send(421, b"Misdirected request", "text/plain")
        url = urllib.parse.urlparse(self.path)
        if url.path.startswith("/api/"):
            return self._api(method, url)
        return self._static(url.path)

    def _api(self, method: str, url: urllib.parse.ParseResult) -> None:
        if self.headers.get(API_HEADER) != "1" or not self._origin_ok():
            return self._json(403, {"error": "Forbidden", "code": "forbidden"})
        handler = ROUTES.get((method, url.path))
        if handler is None:
            return self._json(404, {"error": f"No such endpoint: {method} {url.path}", "code": "not_found"})
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
        body: Any = None
        if method in ("POST", "DELETE"):
            length = int(self.headers.get("Content-Length") or 0)
            if length > 2_000_000:
                return self._json(413, {"error": "Request too large"})
            raw = self.rfile.read(length) if length else b""
            if raw:
                try:
                    body = json.loads(raw.decode("utf-8"))
                except ValueError:
                    return self._json(400, {"error": "Invalid JSON body"})
        try:
            result = handler(self.app, q, body)
            self._json(200, result)
        except Exception as err:  # noqa: BLE001 - map every failure to a JSON error
            status, payload = _error_payload(err)
            self._json(status, payload)

    def _static(self, path: str) -> None:
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in target.parents and target != WEB_DIR.resolve():
            return self._send(404, b"Not found", "text/plain")
        if not target.is_file():
            target = WEB_DIR / "index.html"  # single-page app
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        csp = ("default-src 'self'; img-src 'self' https://*.ytimg.com https://*.ggpht.com https://yt3.googleusercontent.com data:; "
               "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self._send(200, target.read_bytes(), ctype, {"Content-Security-Policy": csp, "X-Frame-Options": "DENY"})


class Server:
    def __init__(self, app: App, host: str = "127.0.0.1", port: int = 8765, verbose: bool = False):
        self.app = app
        allowed = [f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"]
        if host not in ("127.0.0.1", "localhost", "::1", ""):
            allowed.append(f"{host}:{port}".lower())
        handler = type("Handler", (RequestHandler,), {"app": app, "allowed_hosts": allowed})
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.httpd.verbose = verbose  # type: ignore[attr-defined]
        if port == 0:  # ephemeral port (tests): fix up the allowed hosts
            real = self.httpd.server_address[1]
            handler.allowed_hosts = [f"127.0.0.1:{real}", f"localhost:{real}", f"[::1]:{real}"]
        self.port = self.httpd.server_address[1]
        self._stop = threading.Event()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start_background(self) -> "Server":
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        threading.Thread(target=self._maintenance, daemon=True).start()
        return self

    def serve_forever(self) -> None:
        threading.Thread(target=self._maintenance, daemon=True).start()
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()

    def _maintenance(self) -> None:
        """Background: prune old data daily; refresh competitor feeds (free RSS) on a schedule."""
        last_prune = 0.0
        last_refresh = time.time()
        while not self._stop.wait(30):
            now = time.time()
            try:
                if now - last_prune > 86400:
                    self.app.db.prune()
                    last_prune = now
                minutes = int(self.app.settings.get("auto_refresh_minutes") or 0)
                if minutes > 0 and now - last_refresh >= minutes * 60:
                    last_refresh = now
                    if self.app.db.query("SELECT channel_id FROM competitors LIMIT 1"):
                        competitors.refresh(self.app)
            except Exception:  # noqa: BLE001 - never let the maintenance thread die
                traceback.print_exc(file=sys.stderr)
