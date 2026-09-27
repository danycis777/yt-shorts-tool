"""YouTube search autocomplete (the same suggestions you see while typing in the YouTube search box)."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional

from . import config
from .net import BROWSER_UA, HttpError, NetworkError, request
from .textutil import normalize

CACHE_TTL = 3 * 86400


class Budget:
    """Caps how many *network* autocomplete requests one operation may make (cache hits are free)."""

    def __init__(self, limit: int):
        self.remaining = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            self.used += 1
            return True


class Suggest:
    def __init__(self, db, hl: str = "en", gl: str = "US", base: Optional[str] = None,
                 workers: int = 4, min_interval: float = 0.06):
        self.db = db
        self.hl = (hl or "en").lower()
        self.gl = (gl or "US").upper()
        self.base = base or config.SUGGEST_BASE
        self.workers = workers
        self.min_interval = min_interval
        self._rate_lock = threading.Lock()
        self._last_request = 0.0
        self._blocked_until = 0.0
        self.network_calls = 0

    def _cache_key(self, q: str) -> str:
        return f"sug:{self.hl}:{self.gl}:{q}"

    def cached(self, q: str) -> Optional[List[str]]:
        return self.db.cache_get(self._cache_key(normalize_query(q)))

    def get(self, q: str, budget: Optional[Budget] = None) -> Optional[List[str]]:
        """Suggestions for q (lowercased). None if not cached and the budget/cooldown forbids a request."""
        q = normalize_query(q)
        if not q:
            return []
        hit = self.db.cache_get(self._cache_key(q))
        if hit is not None:
            return hit
        if time.time() < self._blocked_until:
            return None
        if budget is not None and not budget.take():
            return None
        return self._fetch(q)

    def _fetch(self, q: str) -> Optional[List[str]]:
        with self._rate_lock:
            wait = self._last_request + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.time()
        params = {"client": "firefox", "ds": "yt", "q": q, "hl": self.hl, "gl": self.gl,
                  "ie": "utf-8", "oe": "utf-8"}
        url = f"{self.base}?{urllib.parse.urlencode(params)}"
        try:
            _, headers, body = request(url, headers={"User-Agent": BROWSER_UA}, timeout=12, retries=1)
        except HttpError as err:
            if err.status in (403, 429):
                self._blocked_until = time.time() + 120  # back off when Google throttles us
            return None
        except NetworkError:
            return None
        self.network_calls += 1
        suggestions = parse_response(body.decode("utf-8", "replace"))
        if suggestions is None:
            return None
        self.db.cache_set(self._cache_key(q), suggestions, CACHE_TTL)
        return suggestions

    def many(self, queries: Iterable[str], budget: Optional[Budget] = None) -> Dict[str, List[str]]:
        """Fetch several queries concurrently (politely). Missing/failed ones map to []."""
        qs = [q for q in dict.fromkeys(normalize_query(q) for q in queries) if q]
        out: Dict[str, List[str]] = {}
        todo = []
        for q in qs:
            hit = self.db.cache_get(self._cache_key(q))
            if hit is not None:
                out[q] = hit
            else:
                todo.append(q)
        if todo:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                for q, res in zip(todo, pool.map(lambda x: self.get(x, budget), todo)):
                    out[q] = res or []
        return out


def normalize_query(q: str) -> str:
    """Normalise a probe but keep one trailing space: 'minecraft ' asks for multi-word completions,
    which YouTube answers differently from 'minecraft'."""
    base = normalize(q or "")
    if not base:
        return ""
    return base + " " if q[-1:].isspace() else base


def parse_response(text: str) -> Optional[List[str]]:
    """Parse both the JSON (client=firefox) and JSONP (client=youtube) formats."""
    text = text.strip()
    m = re.match(r"^[\w.$]+\((.*)\)\s*;?$", text, re.S)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        return None
    out: List[str] = []
    for item in data[1]:
        if isinstance(item, list) and item:
            item = item[0]
        if isinstance(item, str):
            s = normalize(item)
            if s and s not in out:
                out.append(s)
    return out
