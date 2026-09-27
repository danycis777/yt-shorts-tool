import datetime as dt
import unittest

from shortsradar import earnings, keywords, stats
from shortsradar.quota import pacific_now, quota_day, seconds_until_reset
from shortsradar.seo import detect_keyword, score_metadata
from shortsradar.suggest import Budget
from shortsradar.titles import compare_titles, generate_titles, score_title
from shortsradar.videos import detect_short, normalize_video, vph_from_snapshots
from tests.helpers import FakeSuggest

# A small synthetic autocomplete world: 'gaming' is a head term (suggested after 'g'),
# 'gaming chair' is mid-tail, 'gaming chair for kids under 10' only appears when typed fully.
TABLE = {
    "g": ["google", "gta 6", "gaming", "gym", "games"],
    "ga": ["gaming", "games", "garden"],
    "gam": ["gaming", "games", "gamer"],
    "gami": ["gaming", "gaming setup", "gaming chair"],
    "gamin": ["gaming", "gaming setup", "gaming chair"],
    "gaming": ["gaming", "gaming setup", "gaming chair", "gaming pc"],
    "gaming ": ["gaming setup", "gaming chair", "gaming pc", "gaming music"],
    "gaming c": ["gaming chair", "gaming clips", "gaming chair review"],
    "gaming ch": ["gaming chair", "gaming chair review"],
    "gaming chair": ["gaming chair", "gaming chair review", "gaming chair for kids"],
    "gaming chair ": ["gaming chair review", "gaming chair for kids"],
    "gaming chair f": ["gaming chair for kids"],
    "gaming chair fo": ["gaming chair for kids"],
    "gaming chair for": ["gaming chair for kids"],
    "gaming chair for ": ["gaming chair for kids"],
    "gaming chair for k": ["gaming chair for kids"],
    "gaming chair for ki": ["gaming chair for kids"],
    "gaming chair for kid": ["gaming chair for kids"],
    "gaming chair for kids": ["gaming chair for kids", "gaming chair for kids under 10"],
    "gaming chair for kids ": ["gaming chair for kids under 10"],
    "gaming chair for kids u": ["gaming chair for kids under 10"],
    "gaming chair for kids under 10": ["gaming chair for kids under 10"],
}


class VolumeEstimatorTests(unittest.TestCase):
    def setUp(self):
        self.sug = FakeSuggest(TABLE)

    def test_head_beats_mid_beats_long_tail_beats_nonsense(self):
        head = keywords.estimate_volume("gaming", self.sug)
        mid = keywords.estimate_volume("gaming chair", self.sug)
        tail = keywords.estimate_volume("gaming chair for kids under 10", self.sug)
        nonsense = keywords.estimate_volume("zzqx florbnik", self.sug)
        self.assertEqual(head["hit"]["prefix"], "g")
        self.assertGreater(head["score"], mid["score"])
        self.assertGreater(mid["score"], tail["score"])
        self.assertGreater(tail["score"], nonsense["score"])
        self.assertLess(nonsense["score"], 10)
        for r in (head, mid, tail, nonsense):
            self.assertGreaterEqual(r["score"], 0)
            self.assertLessEqual(r["score"], 100)
            self.assertTrue(r["path"])

    def test_known_query_floor(self):
        plain = keywords.estimate_volume("gaming chair ergonomic", self.sug)
        known = keywords.estimate_volume("gaming chair ergonomic", self.sug, known_query=True)
        self.assertGreater(known["log"], plain["log"])

    def test_budget_exhaustion_is_flagged(self):
        sug = FakeSuggest({})  # nothing cached -> every probe needs budget
        res = keywords.estimate_volume("gaming chair", sug, Budget(0))
        self.assertTrue(res["approx"])
        self.assertFalse(res["complete"])

    def test_bands_and_scores(self):
        self.assertEqual(keywords.volume_band(2_000_000), "Very high")
        self.assertEqual(keywords.volume_band(50), "Very low")
        self.assertEqual(keywords.volume_score(1.0), 0)
        self.assertEqual(keywords.volume_score(9.0), 100)


class CompetitionTests(unittest.TestCase):
    def video(self, title, subs, views, tags=()):
        return {"title": title, "channel_subs": subs, "views": views, "tags": list(tags), "age_days": 30, "is_short": True}

    def test_targeted_big_serp_is_harder(self):
        hard = [self.video("Gaming Chair Review 2026", 5_000_000, 3_000_000, ["gaming chair"]) for _ in range(20)]
        easy = [self.video("my new desk setup tour", 2_000, 3_000) for _ in range(20)]
        h = keywords.competition_from_serp("gaming chair", hard)
        e = keywords.competition_from_serp("gaming chair", easy)
        self.assertGreater(h["score"], 80)
        self.assertLess(e["score"], 20)
        self.assertIsNone(keywords.competition_from_serp("x", []))

    def test_overall_rewards_volume_and_low_competition(self):
        self.assertGreater(keywords.overall_score(80, 20), keywords.overall_score(80, 80))
        self.assertGreater(keywords.overall_score(80, 40), keywords.overall_score(20, 40))
        self.assertEqual(keywords.overall_score(0, 10), 0)
        self.assertIsNone(keywords.overall_score(50, None))

    def test_classify(self):
        self.assertEqual(keywords.classify("how to build a gaming chair", "gaming chair"), "question")
        self.assertEqual(keywords.classify("gaming chair review", "gaming chair"), "matching")
        self.assertEqual(keywords.classify("office desk", "gaming chair"), "related")


class SeoTests(unittest.TestCase):
    GOOD_DESC = ("Gaming chair review: I tested the most popular gaming chair for 30 days. " * 3 +
                 "\n\n0:00 Intro\n1:10 Comfort\n4:20 Verdict\n\nSubscribe for more! #gamingchair #setup #review")

    def test_good_vs_bad(self):
        good = score_metadata("Gaming Chair Review: 30 Days Later", self.GOOD_DESC * 4,
                              ["gaming chair", "gaming chair review", "best gaming chair", "gaming setup", "chair review"],
                              keyword="gaming chair", fmt="long", duration_s=600)
        bad = score_metadata("VIDEO!!!", "", [], keyword="gaming chair", fmt="long", duration_s=600)
        self.assertGreater(good["score"], 85)
        self.assertLess(bad["score"], 25)
        self.assertEqual(good["grade"], "A")
        self.assertTrue(bad["fixes"])

    def test_limits(self):
        many_tags = " ".join(f"#tag{i}" for i in range(20))
        res = score_metadata("A title about stuff", many_tags, ["x" * 60] * 10, fmt="short")
        by_id = {c["id"]: c for c in res["checks"]}
        self.assertEqual(by_id["hashtags"]["status"], "fail")
        self.assertEqual(by_id["tags_chars"]["status"], "fail")
        self.assertNotIn("chapters", by_id)  # Shorts don't need chapters

    def test_keyword_detection(self):
        self.assertEqual(detect_keyword("Minecraft Redstone Door Tutorial", ["minecraft redstone", "door"]), "minecraft redstone")
        self.assertTrue(detect_keyword("Easy Pasta Recipe for Beginners", []))


class TitleTests(unittest.TestCase):
    def test_ranking(self):
        good = score_title("I Tried Gaming Chairs for 30 Days — Here's the Truth", fmt="long", keyword="gaming chairs")
        bad = score_title("MY VIDEO!!!", fmt="long", keyword="gaming chairs")
        self.assertGreater(good["score"], bad["score"] + 30)
        labels = {s["label"] for s in bad["signals"]}
        self.assertIn("ALL CAPS", labels)
        self.assertIn("Missing the target keyword", labels)

    def test_compare_and_generate(self):
        ranked = compare_titles(["meh", "7 Gaming Chair Mistakes You're Making"], fmt="short")
        self.assertEqual(ranked[0]["title"], "7 Gaming Chair Mistakes You're Making")
        ideas = generate_titles("how to draw anime eyes", fmt="short")
        self.assertTrue(ideas)
        self.assertTrue(all("Draw Anime Eyes" in t["title"] for t in ideas))
        self.assertEqual(ideas, sorted(ideas, key=lambda r: -r["score"]))
        self.assertEqual(score_title("", fmt="short")["score"], 0)


class EarningsTests(unittest.TestCase):
    def test_shorts_pay_less_and_geo_matters(self):
        short = earnings.estimate(1_000_000, category="Gaming", fmt="short")
        long = earnings.estimate(1_000_000, category="Gaming", fmt="long")
        self.assertLess(short["earnings"]["mid"] * 5, long["earnings"]["mid"])
        us = earnings.estimate(1_000_000, category="Finance", country="US", fmt="long")
        india = earnings.estimate(1_000_000, category="Finance", country="IN", fmt="long")
        self.assertGreater(us["earnings"]["mid"], india["earnings"]["mid"] * 4)
        mix = earnings.estimate(1_000_000, category="Gaming", shorts_share=0.5)
        self.assertLess(short["earnings"]["mid"], mix["earnings"]["mid"])
        self.assertLess(mix["earnings"]["mid"], long["earnings"]["mid"])
        r = earnings.calculator(300_000, category="Education")
        self.assertAlmostEqual(r["yearly"]["mid"], r["earnings"]["mid"] * 12, places=1)


class QuotaAndStatsTests(unittest.TestCase):
    def test_pacific_day_with_dst(self):
        summer = dt.datetime(2026, 7, 1, 6, 30, tzinfo=dt.timezone.utc)   # 23:30 PDT on Jun 30
        winter = dt.datetime(2026, 1, 15, 7, 30, tzinfo=dt.timezone.utc)  # 23:30 PST on Jan 14
        self.assertEqual(quota_day(summer), "2026-06-30")
        self.assertEqual(quota_day(winter), "2026-01-14")
        self.assertEqual(pacific_now(summer).hour, 23)
        self.assertEqual(seconds_until_reset(summer), 30 * 60)

    def test_stats(self):
        self.assertEqual(stats.median([3, 1, 2]), 2)
        self.assertEqual(stats.median([1, 2, 3, 4]), 2.5)
        self.assertIsNone(stats.median([]))
        self.assertEqual(stats.percentile([0, 10], 50), 5)
        self.assertEqual(stats.log_scale(1000, 10, 100000), 0.5)
        self.assertEqual(stats.geometric_blend(0, 1, 0.5), 0)


class VideoNormalizationTests(unittest.TestCase):
    def test_detect_short(self):
        self.assertTrue(detect_short(30, 0.5625, ""))
        self.assertFalse(detect_short(30, 1.78, ""))            # horizontal 30s clip is not a Short
        self.assertTrue(detect_short(150, 0.5625, ""))           # Shorts can be up to 3 minutes
        self.assertFalse(detect_short(200, 0.5625, ""))
        self.assertTrue(detect_short(90, None, "cool #shorts"))
        self.assertFalse(detect_short(0, None, "", live="live"))

    def test_normalize_video_and_vph(self):
        now = 1_800_000_000
        item = {"id": "abcdefghijk", "snippet": {"title": "T", "publishedAt": "2027-01-15T08:00:00Z", "channelId": "UCx",
                "tags": ["a"], "liveBroadcastContent": "none"},
                "statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "5"},
                "contentDetails": {"duration": "PT45S", "caption": "true"},
                "player": {"embedWidth": "270", "embedHeight": "480"}}
        v = normalize_video(item, now=now)
        self.assertTrue(v["is_short"])
        self.assertEqual(v["engagement_rate"], 5.5)
        self.assertTrue(v["caption"])
        self.assertIn("/shorts/", v["url"])
        snaps = [{"ts": 0, "views": 100}, {"ts": 3600, "views": 400}]
        self.assertEqual(vph_from_snapshots(snaps)["vph"], 300.0)
        self.assertIsNone(vph_from_snapshots(snaps[:1]))


if __name__ == "__main__":
    unittest.main()
