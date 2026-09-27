"""Shared test helpers."""
import os
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def temp_app():
    """An App with isolated settings + database in a temp folder."""
    from shortsradar.config import Settings
    from shortsradar.context import App
    tmp = Path(tempfile.mkdtemp(prefix="sr-test-"))
    return App(Settings(tmp / "config.json"), db_path=tmp / "db.sqlite"), tmp


class FakeSuggest:
    """Autocomplete stand-in backed by a dict {prefix: [suggestions]} (missing prefixes -> [])."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def get(self, q, budget=None):
        if budget is not None and q not in self.table and not budget.take():
            return None
        self.calls.append(q)
        return list(self.table.get(q, []))

    def many(self, queries, budget=None):
        return {q: self.get(q, budget) or [] for q in queries}


os.environ.setdefault("SHORTSRADAR_HOME", tempfile.mkdtemp(prefix="sr-home-"))
