"""CLI end-to-end: runs `python -m shortsradar ... --json` against the demo backend."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shortsradar.demo import DemoServer

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = DemoServer(seed=5).start()
        cls.vid, cls.cid, cls.handle = cls.demo.sample()
        cls.env = dict(os.environ,
                       SHORTSRADAR_HOME=tempfile.mkdtemp(prefix="sr-cli-"),
                       SHORTSRADAR_YT_BASE=cls.demo.base + "/youtube/v3",
                       SHORTSRADAR_SUGGEST_BASE=cls.demo.base + "/complete/search",
                       SHORTSRADAR_WEB_BASE=cls.demo.base,
                       YOUTUBE_API_KEY="test-key")

    @classmethod
    def tearDownClass(cls):
        cls.demo.stop()

    def run_cli(self, *args, expect=0):
        proc = subprocess.run([sys.executable, "-m", "shortsradar", *args], cwd=ROOT, env=self.env,
                              capture_output=True, text=True, timeout=180)
        self.assertEqual(proc.returncode, expect, proc.stderr + proc.stdout)
        return proc

    def test_json_commands(self):
        kw = json.loads(self.run_cli("keyword", "minecraft redstone", "--quick", "--json").stdout)
        self.assertIsNotNone(kw["scores"]["overall"])
        out = json.loads(self.run_cli("outliers", "cooking", "--within", "all", "--limit", "5", "--json").stdout)
        self.assertLessEqual(len(out["results"]), 5)
        video = json.loads(self.run_cli("video", self.vid, "--json").stdout)
        self.assertEqual(video["video"]["id"], self.vid)
        chan = json.loads(self.run_cli("channel", self.handle, "--json").stdout)
        self.assertEqual(chan["channel"]["id"], self.cid)
        tags = json.loads(self.run_cli("tags", "minecraft redstone", "--json").stdout)
        self.assertLessEqual(tags["char_count"], 500)
        score = json.loads(self.run_cli("title", "I Tried Redstone for 24 Hours", "meh", "--json").stdout)
        self.assertEqual(score[0]["title"], "I Tried Redstone for 24 Hours")
        money = json.loads(self.run_cli("earnings", "1000000", "--category", "Gaming", "--json").stdout)
        self.assertIn("yearly", money)
        ai_out = json.loads(self.run_cli("ai", "hooks", "redstone door", "--mode", "template", "--json").stdout)
        self.assertEqual(ai_out["mode"], "template")

    def test_human_output_and_errors(self):
        self.assertIn("Overall", self.run_cli("keyword", "minecraft redstone", "--quick", "--no-api").stdout)
        self.assertIn("SEO score", self.run_cli("seo", "--title", "My Redstone Door", "--tags", "redstone, door").stdout)
        self.run_cli("competitors", "add", self.handle)
        self.assertIn("Tracking", self.run_cli("competitors", "list").stdout + "Tracking")
        err = self.run_cli("video", "definitely not a video", expect=1)
        self.assertIn("Error", err.stderr)
        self.assertIn("quota", self.run_cli("quota").stdout.lower())
