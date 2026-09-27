"""Live checks against the real (keyless) YouTube endpoints. Opt-in: SHORTSRADAR_LIVE=1."""
import os
import unittest

from shortsradar import config
from shortsradar.keywords import estimate_volume
from shortsradar.resolve import channel_id_from_web, oembed
from shortsradar.rss import FeedError, fetch_channel_feed
from tests.helpers import temp_app

LIVE = os.environ.get("SHORTSRADAR_LIVE") == "1"


@unittest.skipUnless(LIVE, "set SHORTSRADAR_LIVE=1 to run live network tests")
class LiveTests(unittest.TestCase):
    def setUp(self):
        config.YOUTUBE_WEB_BASE = "https://www.youtube.com"
        config.SUGGEST_BASE = "https://suggestqueries.google.com/complete/search"

    def test_autocomplete_volume_ordering(self):
        app, _ = temp_app()
        sug = app.suggest("en", "US")
        head = estimate_volume("minecraft", sug)
        mid = estimate_volume("minecraft redstone", sug)
        junk = estimate_volume("purple elephant spreadsheet tutorial", sug)
        self.assertGreater(head["score"], mid["score"])
        self.assertGreater(mid["score"], junk["score"])

    def test_rss_feed(self):
        try:
            feed = fetch_channel_feed("UCBR8-60-B28hp2BmDPdntcQ")  # the official YouTube channel
        except FeedError as err:  # YouTube's feed endpoint has multi-hour outages; not a code failure
            self.skipTest(f"YouTube RSS endpoint unavailable right now: {err}")
        self.assertTrue(feed["videos"])
        self.assertTrue(all(isinstance(v["views"], int) for v in feed["videos"]))

    def test_handle_resolution_and_oembed(self):
        self.assertEqual(channel_id_from_web("handle", "@YouTube"), "UCBR8-60-B28hp2BmDPdntcQ")
        meta = oembed("dQw4w9WgXcQ")
        self.assertIsNotNone(meta)
        self.assertGreater(meta["aspect"], 1.2)  # a horizontal video
