"""Tiny HTTP client on top of urllib (no third-party dependencies)."""

from __future__ import annotations

import gzip
import json
import random
import time
import urllib.error
import urllib.request
import zlib
from typing import Any, Dict, Optional, Tuple

from . import __version__

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
TOOL_UA = f"ShortsRadar/{__version__} (+self-hosted)"


class HttpError(Exception):
    def __init__(self, status: int, body: bytes, url: str):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status}")

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except ValueError:
            return None


class NetworkError(Exception):
    pass


def _decode_body(raw: bytes, encoding: Optional[str]) -> bytes:
    encoding = (encoding or "").lower()
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def request(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[bytes] = None,
    timeout: float = 20.0,
    retries: int = 2,
    retry_statuses: Tuple[int, ...] = (429, 500, 502, 503, 504),
) -> Tuple[int, Dict[str, str], bytes]:
    """Perform an HTTP request with gzip support and retry/backoff on transient failures."""
    hdrs = {"User-Agent": TOOL_UA, "Accept-Encoding": "gzip, deflate"}
    if headers:
        hdrs.update(headers)
    attempt = 0
    while True:
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                body = _decode_body(raw, resp.headers.get("Content-Encoding"))
                return resp.status, dict(resp.headers.items()), body
        except urllib.error.HTTPError as err:
            raw = err.read() if hasattr(err, "read") else b""
            try:
                body = _decode_body(raw, err.headers.get("Content-Encoding") if err.headers else None)
            except (OSError, zlib.error):
                body = raw
            if err.code in retry_statuses and attempt < retries:
                attempt += 1
                time.sleep(_backoff(attempt, err.headers.get("Retry-After") if err.headers else None))
                continue
            raise HttpError(err.code, body, url) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
            if attempt < retries:
                attempt += 1
                time.sleep(_backoff(attempt, None))
                continue
            reason = getattr(err, "reason", err)
            raise NetworkError(f"Could not reach {url.split('?')[0]}: {reason}") from None


def _backoff(attempt: int, retry_after: Optional[str]) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 10.0)
        except ValueError:
            pass
    return min(0.6 * (2 ** (attempt - 1)) + random.uniform(0, 0.3), 8.0)


def get_json(url: str, **kw: Any) -> Any:
    _, headers, body = request(url, **kw)
    return json.loads(body.decode(_charset(headers) or "utf-8", "replace"))


def get_text(url: str, **kw: Any) -> str:
    _, headers, body = request(url, **kw)
    return body.decode(_charset(headers) or "utf-8", "replace")


def post_json(url: str, payload: Any, headers: Optional[Dict[str, str]] = None, **kw: Any) -> Any:
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    _, resp_headers, body = request(
        url, method="POST", headers=hdrs, data=json.dumps(payload).encode("utf-8"), **kw
    )
    return json.loads(body.decode(_charset(resp_headers) or "utf-8", "replace"))


def _charset(headers: Dict[str, str]) -> Optional[str]:
    for key, value in headers.items():
        if key.lower() == "content-type" and "charset=" in value.lower():
            charset = value.lower().split("charset=", 1)[1].split(";")[0].strip()
            try:
                "".encode(charset)
                return charset
            except LookupError:
                return None
    return None
