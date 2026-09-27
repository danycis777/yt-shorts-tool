import os
import tempfile
import time
import unittest
from pathlib import Path

from shortsradar.config import Settings, mask
from shortsradar.db import DB


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "config.json"

    def test_persist_and_coerce(self):
        s = Settings(self.path)
        s.update({"region": "gb", "daily_quota": "20000", "niche_keywords": "a, b ,,c", "default_format": "weird",
                  "ai_effort": "bogus", "unknown_key": 1})
        s2 = Settings(self.path)
        self.assertEqual(s2.get("region"), "GB")
        self.assertEqual(s2.get("daily_quota"), 20000)
        self.assertEqual(s2.get("niche_keywords"), ["a", "b", "c"])
        self.assertEqual(s2.get("default_format"), "short")
        self.assertEqual(s2.get("ai_effort"), "medium")
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_secrets_are_masked(self):
        s = Settings(self.path)
        s.update({"youtube_api_key": "AIzaSyExampleExampleExample1234"})
        pub = s.public()
        self.assertTrue(pub["youtube_api_key_set"])
        self.assertNotIn("Example", pub["youtube_api_key"])
        self.assertEqual(pub["youtube_api_key"], mask("AIzaSyExampleExampleExample1234"))

    def test_env_override(self):
        s = Settings(self.path)
        os.environ["YOUTUBE_API_KEY"] = "from-env-key"
        try:
            self.assertEqual(s.get("youtube_api_key"), "from-env-key")
            self.assertTrue(s.public()["youtube_api_key_from_env"])
        finally:
            del os.environ["YOUTUBE_API_KEY"]

    def test_corrupt_file_falls_back_to_defaults(self):
        self.path.write_text("{not json")
        self.assertEqual(Settings(self.path).get("region"), "US")


class DbTests(unittest.TestCase):
    def setUp(self):
        self.db = DB(Path(tempfile.mkdtemp()) / "db.sqlite")

    def test_cache_ttl(self):
        self.db.cache_set("k", {"a": 1}, ttl=60)
        self.assertEqual(self.db.cache_get("k"), {"a": 1})
        self.db.cache_set("old", 1, ttl=-1)
        self.assertIsNone(self.db.cache_get("old"))

    def test_snapshots_throttled_and_pruned(self):
        now = time.time()
        self.db.add_video_snapshot("v", 100, ts=now - 3600)
        self.db.add_video_snapshot("v", 150, ts=now - 3500)   # < 5 min gap: ignored
        self.db.add_video_snapshot("v", 200, ts=now)
        self.assertEqual([s["views"] for s in self.db.video_snapshots("v")], [100, 200])
        self.db.add_video_snapshot("old", 1, ts=now - 40 * 86400)
        self.db.prune()
        self.assertEqual(self.db.video_snapshots("old"), [])
        self.assertEqual(len(self.db.video_snapshots("v")), 2)

    def test_saved_and_history(self):
        i = self.db.save_item("keyword", "k1", "K1", {"x": 1})
        self.db.save_item("keyword", "k1", "K1 again", {"x": 2})  # upsert on (kind, ref)
        items = self.db.saved_items("keyword")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["data"], {"x": 2})
        self.db.delete_saved(items[0]["id"])
        self.assertEqual(self.db.saved_items(), [])
        self.assertTrue(i)
        self.db.add_history("keyword", "q", {"v": 1})
        self.db.add_history("keyword", "q", {"v": 2})
        hist = self.db.recent_history()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["summary"], {"v": 2})


if __name__ == "__main__":
    unittest.main()
