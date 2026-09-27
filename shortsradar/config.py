"""Settings: stored as JSON in the data directory, overridable by environment variables."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "youtube_api_key": "",
    "anthropic_api_key": "",
    "ai_model": "claude-opus-5",
    "ai_effort": "medium",     # low | medium | high | xhigh | max (higher = slower, more thorough)
    "region": "US",            # ISO 3166-1 alpha-2, used for search/trending/autocomplete
    "language": "en",          # ISO 639-1, used for relevanceLanguage/autocomplete
    "timezone": "",            # IANA name for "best time to post"; empty = computer's local time
    "default_format": "short",  # short | long | any
    "niche_keywords": [],      # used by the Daily Ideas page
    "auto_refresh_minutes": 60,  # competitor RSS refresh while the server runs (0 = off)
    "daily_quota": 10000,      # YouTube Data API daily quota for your key
    "autocomplete_budget": 150,  # max new autocomplete requests per keyword research
}

SECRET_KEYS = ("youtube_api_key", "anthropic_api_key")
# Environment variables that override stored secrets (first one set wins). The SHORTSRADAR_* names
# avoid clashing with other tools that read ANTHROPIC_API_KEY (e.g. when running inside Claude Code).
ENV_OVERRIDES = {
    "youtube_api_key": ("SHORTSRADAR_YOUTUBE_API_KEY", "YOUTUBE_API_KEY"),
    "anthropic_api_key": ("SHORTSRADAR_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
}


def env_secret(key: str) -> str:
    for name in ENV_OVERRIDES.get(key, ()):
        if os.environ.get(name):
            return os.environ[name]
    return ""

# Base URLs can be overridden (used by the test-suite's fake servers).
YOUTUBE_API_BASE = os.environ.get("SHORTSRADAR_YT_BASE", "https://www.googleapis.com/youtube/v3")
SUGGEST_BASE = os.environ.get("SHORTSRADAR_SUGGEST_BASE", "https://suggestqueries.google.com/complete/search")
YOUTUBE_WEB_BASE = os.environ.get("SHORTSRADAR_WEB_BASE", "https://www.youtube.com")
ANTHROPIC_BASE = os.environ.get("SHORTSRADAR_ANTHROPIC_BASE", "https://api.anthropic.com")


def data_dir() -> Path:
    base = os.environ.get("SHORTSRADAR_HOME")
    path = Path(base).expanduser() if base else Path.home() / ".shortsradar"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings:
    """Thread-safe settings store backed by <data_dir>/config.json."""

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "config.json")
        self._lock = threading.Lock()
        self._values: Dict[str, Any] = dict(DEFAULTS)
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text("utf-8"))
                if isinstance(stored, dict):
                    for key, value in stored.items():
                        if key in DEFAULTS:
                            self._values[key] = value
            except (OSError, ValueError):
                pass  # a corrupt config falls back to defaults

    def get(self, key: str) -> Any:
        from_env = env_secret(key)
        if from_env:
            return from_env
        with self._lock:
            return self._values.get(key, DEFAULTS.get(key))

    def update(self, changes: Dict[str, Any]) -> None:
        with self._lock:
            for key, value in changes.items():
                if key not in DEFAULTS:
                    continue
                self._values[key] = _coerce(key, value)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._values, indent=2), "utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)

    def public(self) -> Dict[str, Any]:
        """Settings safe to send to the browser: secrets are masked."""
        out: Dict[str, Any] = {}
        for key in DEFAULTS:
            value = self.get(key)
            if key in SECRET_KEYS:
                out[key] = mask(value)
                out[key + "_set"] = bool(value)
                out[key + "_from_env"] = bool(env_secret(key))
            else:
                out[key] = value
        out["data_dir"] = str(self.path.parent)
        return out


def mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]


def _coerce(key: str, value: Any) -> Any:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, list):
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return default
    if isinstance(default, str):
        value = "" if value is None else str(value).strip()
        if key in ("region",):
            value = value.upper()[:2]
        if key in ("language",):
            value = value.lower()[:5]
        if key == "default_format" and value not in ("short", "long", "any"):
            value = default
        if key == "ai_effort" and value not in ("low", "medium", "high", "xhigh", "max"):
            value = default
        return value
    return value
