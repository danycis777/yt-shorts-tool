"""End-to-end: demo YouTube backend + real ShortsRadar server, exercised over HTTP."""
import http.client
import json
import os
import tempfile
import unittest
from pathlib import Path

from shortsradar import ai, config
from shortsradar.config import Settings
from shortsradar.context import App
from shortsradar.demo import DemoServer
from shortsradar.server import Server


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = DemoServer(seed=11).start()
        cls.demo.configure()
        cls.old_ai_base = os.environ.get("SHORTSRADAR_ANTHROPIC_BASE")
        os.environ["SHORTSRADAR_ANTHROPIC_BASE"] = cls.demo.base
        config.ANTHROPIC_BASE = cls.demo.base
        tmp = Path(tempfile.mkdtemp(prefix="sr-int-"))
        cls.app = App(Settings(tmp / "config.json"), db_path=tmp / "db.sqlite")
        cls.app.settings.update({"youtube_api_key": "test-key", "niche_keywords": ["minecraft redstone"]})
        cls.app.suggest("en", "US").min_interval = 0
        cls.server = Server(cls.app, port=0).start_background()
        cls.vid, cls.cid, cls.handle = cls.demo.sample()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.demo.stop()
        if cls.old_ai_base is None:
            os.environ.pop("SHORTSRADAR_ANTHROPIC_BASE", None)
        config.ANTHROPIC_BASE = "https://api.anthropic.com"
        config.YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
        config.SUGGEST_BASE = "https://suggestqueries.google.com/complete/search"
        config.YOUTUBE_WEB_BASE = "https://www.youtube.com"

    def call(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=60)
        hdrs = {"X-ShortsRadar": "1", "Host": host or f"127.0.0.1:{self.server.port}"}
        if headers:
            hdrs.update(headers)
        payload = json.dumps(body).encode() if body is not None else None
        if payload:
            hdrs["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=hdrs)
        res = conn.getresponse()
        raw = res.read()
        conn.close()
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw
        return res.status, data

    def ok(self, method, path, body=None):
        status, data = self.call(method, path, body)
        self.assertEqual(status, 200, f"{method} {path} -> {status}: {data}")
        return data

    # --- security -------------------------------------------------------------------------------
    def test_security_checks(self):
        self.assertEqual(self.call("GET", "/api/status", headers={"X-ShortsRadar": ""})[0], 403)
        self.assertEqual(self.call("GET", "/api/status", host="attacker.example")[0], 421)
        self.assertEqual(self.call("GET", "/api/status", headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("GET", "/api/status", headers={"Origin": "chrome-extension://abc"})[0], 200)
        self.assertEqual(self.call("OPTIONS", "/api/status")[0], 403)
        status, body = self.call("GET", "/../shortsradar/config.py")
        self.assertIn(status, (200, 404))
        self.assertNotIn(b"SECRET_KEYS", body if isinstance(body, bytes) else b"")

    def test_settings_never_leak_keys(self):
        data = self.ok("GET", "/api/settings")
        self.assertNotEqual(data["youtube_api_key"], "test-key")
        # posting the masked value back must not overwrite the real key
        self.ok("POST", "/api/settings", {"youtube_api_key": data["youtube_api_key"], "region": "US"})
        self.assertEqual(self.app.settings.get("youtube_api_key"), "test-key")

    # --- research ---------------------------------------------------------------------------------
    def test_keyword_research(self):
        r = self.ok("GET", "/api/keyword?q=minecraft%20redstone")
        s = r["scores"]
        for k in ("volume", "competition", "overall"):
            self.assertIsNotNone(s[k])
            self.assertTrue(0 <= s[k] <= 100, (k, s[k]))
        self.assertTrue(r["api_used"])
        self.assertEqual(r["quota_units"], 102)
        self.assertTrue(r["top_videos"])
        quick = self.ok("GET", "/api/keyword/quick?q=minecraft%20redstone")
        self.assertIsNotNone(quick["volume"])
        self.assertEqual(self.call("GET", "/api/keyword?q=")[0], 400)

    def test_outliers_and_trending(self):
        r = self.ok("GET", "/api/outliers?q=minecraft&format=short&within=3months")
        self.assertTrue(r["results"])
        scores = [v["outlier_score"] for v in r["results"] if v["outlier_score"] is not None]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(v["format"] == "short" for v in r["results"]))
        filtered = self.ok("GET", "/api/outliers?q=minecraft&format=short&within=3months&min_score=3")
        self.assertTrue(all(v["outlier_score"] >= 3 for v in filtered["results"]))
        chan = self.ok("GET", f"/api/outliers?channels={self.handle}&format=any&within=all")
        self.assertTrue(all(v["channel_id"] == self.cid for v in chan["results"]))
        t = self.ok("GET", "/api/trending?format=any")
        self.assertTrue(t["videos"] and t["categories"])
        n = self.ok("GET", "/api/trending/niche?q=cooking&hours=720&format=any")
        vph = [v["vph"] for v in n["videos"]]
        self.assertEqual(vph, sorted(vph, reverse=True))

    def test_video_scorecard_and_tag_ranks(self):
        r = self.ok("GET", f"/api/video?id=https://www.youtube.com/shorts/{self.vid}")
        self.assertEqual(r["mode"], "api")
        self.assertTrue(r["video"]["is_short"])
        self.assertIsNotNone(r["outlier"])
        self.assertTrue(0 <= r["seo"]["score"] <= 100)
        ranks = self.ok("POST", "/api/video/tag-ranks", {"id": self.vid, "tags": r["video"]["tags"][:2]})
        self.assertEqual(len(ranks["ranks"]), min(2, len(r["video"]["tags"])))
        self.assertEqual(self.call("GET", "/api/video?id=not%20a%20video")[0], 400)   # not an ID/URL
        self.assertEqual(self.call("GET", "/api/video?id=AAAAAAAAAAA")[0], 404)        # valid ID, no such video

    def test_channel_audit(self):
        r = self.ok("GET", f"/api/channel?id={self.handle}")
        self.assertEqual(r["channel"]["id"], self.cid)
        self.assertGreater(r["analyzed_videos"], 10)
        self.assertEqual(len(r["cadence"]["weekly"]), 12)
        self.assertEqual(len(r["posting"]["days"]), 7)
        self.assertTrue(r["recommendations"])

    def test_competitors_flow(self):
        added = self.ok("POST", "/api/competitors", {"ref": self.handle})
        self.assertEqual(added["channel_id"], self.cid)
        data = self.ok("GET", "/api/competitors")
        self.assertTrue(any(c["channel_id"] == self.cid for c in data["competitors"]))
        self.ok("POST", "/api/competitors/refresh")
        feed = self.ok("GET", "/api/competitors/feed?format=any&days=60")
        self.assertTrue(feed["videos"])
        self.ok("DELETE", f"/api/competitors?id={self.cid}")
        data = self.ok("GET", "/api/competitors")
        self.assertFalse(any(c["channel_id"] == self.cid for c in data["competitors"]))

    def test_competitors_fall_back_to_api_when_rss_is_down(self):
        from shortsradar import rss
        others = [c for c in self.demo.world.channels if c != self.cid]
        old_delay, rss.RETRY_BASE_DELAY = rss.RETRY_BASE_DELAY, 0
        self.demo.world.rss_down = True
        try:
            added = self.ok("POST", "/api/competitors", {"ref": others[0]})
            self.assertEqual(added["channel_id"], others[0])
            self.assertGreater(added["uploads_30d_tracked"], 0)
            self.app.settings.update({"youtube_api_key": ""})
            status, data = self.call("POST", "/api/competitors", {"ref": others[1]})
            self.assertEqual(status, 400)
            self.assertIn("API key", data["error"])
        finally:
            self.app.settings.update({"youtube_api_key": "test-key"})
            self.demo.world.rss_down = False
            rss.RETRY_BASE_DELAY = old_delay
            self.ok("DELETE", f"/api/competitors?id={others[0]}")

    # --- tools --------------------------------------------------------------------------------------
    def test_tools(self):
        seo = self.ok("POST", "/api/seo/score", {"title": "Minecraft Redstone Door in 60 Seconds", "description": "", "tags": "a, b", "keyword": "minecraft redstone", "format": "short"})
        self.assertIn("title_score", seo)
        titles = self.ok("POST", "/api/titles/score", {"titles": "one\nI Tried Minecraft Redstone for 24 Hours", "keyword": "minecraft redstone"})
        self.assertEqual(titles["results"][0]["title"], "I Tried Minecraft Redstone for 24 Hours")
        self.assertTrue(self.ok("GET", "/api/titles/generate?q=minecraft%20redstone")["titles"])
        tags = self.ok("GET", "/api/tags?q=minecraft%20redstone&format=short")
        self.assertLessEqual(tags["char_count"], 500)
        self.assertEqual(tags["selected"][0], "minecraft redstone")
        self.assertIn("#shorts", tags["hashtags"])
        e = self.ok("GET", "/api/earnings?views=1000000&category=Gaming&country=US&shorts_share=100")
        self.assertEqual(e["format"], "mix")
        ideas = self.ok("GET", "/api/ideas?niches=minecraft%20redstone&format=short")
        self.assertTrue(ideas["ideas"])

    def test_saved_and_history(self):
        item = self.ok("POST", "/api/saved", {"kind": "keyword", "ref": "abc", "title": "abc"})
        items = self.ok("GET", "/api/saved")["items"]
        self.assertTrue(any(i["id"] == item["id"] for i in items))
        self.ok("DELETE", f"/api/saved?id={item['id']}")
        self.assertEqual(self.call("POST", "/api/saved", {"kind": "evil", "ref": "x"})[0], 400)
        self.assertIn("items", self.ok("GET", "/api/history"))

    def test_ai_modes(self):
        r = self.ok("POST", "/api/ai", {"task": "script", "topic": "redstone door", "mode": "template"})
        self.assertEqual(r["mode"], "template")
        self.assertTrue(r["result"]["beats"])
        p = self.ok("POST", "/api/ai", {"task": "hooks", "topic": "redstone door", "mode": "prompt"})
        self.assertIsNone(p["result"])
        self.assertIn("redstone door", p["prompt"])
        self.assertEqual(self.call("POST", "/api/ai", {"task": "nope", "topic": "x"})[0], 502)

    @unittest.skipUnless(ai.sdk_available(), "anthropic SDK not installed")
    def test_ai_claude_path(self):
        self.app.settings.update({"anthropic_api_key": "sk-ant-test"})
        try:
            r = self.ok("POST", "/api/ai", {"task": "titles", "topic": "redstone door", "keyword": "minecraft redstone"})
            self.assertEqual(r["mode"], "claude")
            self.assertEqual(len(r["result"]["titles"]), 10)
            req = self.demo.world.ai_requests[-1]
            self.assertEqual(req["body"]["model"], "claude-opus-5")
            self.assertEqual(req["body"]["fallbacks"], "default")
            self.assertEqual(req["body"]["thinking"], {"type": "adaptive"})
            self.assertIn("server-side-fallback-2026-07-01", req["headers"].get("anthropic-beta", ""))
            self.assertEqual(req["body"]["output_config"]["format"]["type"], "json_schema")
        finally:
            self.app.settings.update({"anthropic_api_key": ""})

    # --- errors & quota ---------------------------------------------------------------------------------
    def test_youtube_error_mapping(self):
        before = self.ok("GET", "/api/quota")["used"]
        self.app.settings.update({"youtube_api_key": "quota"})
        try:
            status, data = self.call("GET", "/api/trending?format=any&region=GB")
            self.assertEqual(status, 429)
            self.assertEqual(data["code"], "quotaExceeded")
            self.app.settings.update({"youtube_api_key": "bad"})
            status, data = self.call("GET", "/api/trending?format=any&region=FR")
            self.assertEqual(data["code"], "keyInvalid")
            self.app.settings.update({"youtube_api_key": ""})
            status, data = self.call("GET", "/api/trending?format=any&region=DE")
            self.assertEqual((status, data["code"]), (400, "no_api_key"))
        finally:
            self.app.settings.update({"youtube_api_key": "test-key"})
        self.assertGreaterEqual(self.ok("GET", "/api/quota")["used"], before)

    def test_keyless_scorecard(self):
        self.app.settings.update({"youtube_api_key": ""})
        try:
            r = self.ok("GET", f"/api/video?id={self.vid}")
            self.assertEqual(r["mode"], "keyless")
            self.assertTrue(r["limited"])
            self.assertIsNotNone(r["video"]["views"])  # from the RSS feed
        finally:
            self.app.settings.update({"youtube_api_key": "test-key"})


if __name__ == "__main__":
    unittest.main()
