"""Application context: settings + storage + API clients, shared by the CLI and the web server."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

from .config import Settings, data_dir
from .db import DB
from .quota import QuotaTracker
from .suggest import Suggest
from .youtube import YouTube


class App:
    def __init__(self, settings: Optional[Settings] = None, db_path: Optional[Path] = None):
        self.settings = settings or Settings()
        self.db = DB(db_path or (data_dir() / "shortsradar.db"))
        self.quota = QuotaTracker(self.db, int(self.settings.get("daily_quota") or 10000))
        self._suggesters: Dict[Tuple[str, str], Suggest] = {}
        self._lock = threading.Lock()

    def youtube(self) -> YouTube:
        """A fresh client per operation so key changes apply immediately and unit counts are per-request."""
        self.quota.daily_limit = int(self.settings.get("daily_quota") or 10000)
        return YouTube(self.settings.get("youtube_api_key"), self.db, self.quota)

    def suggest(self, language: Optional[str] = None, region: Optional[str] = None) -> Suggest:
        hl = (language or self.settings.get("language") or "en").lower()
        gl = (region or self.settings.get("region") or "US").upper()
        with self._lock:
            key = (hl, gl)
            if key not in self._suggesters:
                self._suggesters[key] = Suggest(self.db, hl=hl, gl=gl)
            return self._suggesters[key]

    @property
    def region(self) -> str:
        return (self.settings.get("region") or "US").upper()

    @property
    def language(self) -> str:
        return (self.settings.get("language") or "en").lower()

    @property
    def has_youtube_key(self) -> bool:
        return bool(self.settings.get("youtube_api_key"))

    @property
    def has_ai_key(self) -> bool:
        return bool(self.settings.get("anthropic_api_key"))
