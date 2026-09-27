import json
import unittest

from shortsradar import textutil
from shortsradar.resolve import ResolveError, parse_channel_ref, parse_video_id
from shortsradar.rss import FeedError, parse_feed
from shortsradar.suggest import Budget, normalize_query, parse_response
from shortsradar.youtube import YouTubeError, _to_youtube_error, parse_iso_duration, uploads_playlist
from shortsradar.net import HttpError
from tests.helpers import FIXTURES


class TextUtilTests(unittest.TestCase):
    def test_normalize_and_tokens(self):
        self.assertEqual(textutil.normalize("  Minecraft   REDSTONE "), "minecraft redstone")
        self.assertEqual(textutil.normalize_keyword('"How to draw?"'), "how to draw")
        self.assertEqual(textutil.tokens("It's a DIY-hack!"), ["it's", "a", "diy", "hack"])

    def test_phrase_matching(self):
        self.assertTrue(textutil.contains_phrase("The BEST Minecraft Redstone door!", "minecraft redstone"))
        self.assertFalse(textutil.contains_phrase("redstone in minecraft", "minecraft redstone"))
        self.assertTrue(textutil.contains_all_tokens("redstone doors in minecraft", "minecraft redstone door"))
        # generic YouTube words must still be matched (they are not grammatical stopwords)
        self.assertFalse(textutil.contains_all_tokens("grow your channel", "youtube shorts growth tips"))

    def test_hashtags_emoji_and_tag_length(self):
        self.assertEqual(textutil.hashtags("Great #shorts video #Minecraft_Tips and mail@x.com #1"), ["#shorts", "#Minecraft_Tips", "#1"])
        self.assertEqual(textutil.emoji_count("wow 🔥🔥 ok"), 2)
        # "a b" counts 3 + 2 quotes, plus a comma
        self.assertEqual(textutil.youtube_tag_length(["a b", "cd"]), 5 + 1 + 2)

    def test_smart_title_and_phrases(self):
        self.assertEqual(textutil.smart_title("how to draw anime eyes"), "How to Draw Anime Eyes")
        self.assertEqual(textutil.smart_title("iphone 17 pro vs AI"), "Iphone 17 Pro vs AI")
        phrases = dict(textutil.top_phrases(["redstone door build", "hidden redstone door", "redstone door tutorial"]))
        self.assertEqual(phrases.get("redstone door"), 3)


class ResolveTests(unittest.TestCase):
    def test_video_ids(self):
        vid = "dQw4w9WgXcQ"
        for url in [vid, f"https://www.youtube.com/watch?v={vid}&t=10s", f"youtube.com/watch?v={vid}", f"https://youtu.be/{vid}?si=x",
                    f"https://www.youtube.com/shorts/{vid}", f"https://m.youtube.com/shorts/{vid}?feature=share",
                    f"https://www.youtube.com/embed/{vid}", f"https://www.youtube.com/live/{vid}", f"https://music.youtube.com/watch?v={vid}"]:
            self.assertEqual(parse_video_id(url), vid, url)
        for bad in ["", "hello world", "https://example.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/@mrbeast"]:
            self.assertIsNone(parse_video_id(bad), bad)

    def test_channel_refs(self):
        cid = "UCX6OQ3DkcsbYNE6H8uQQuVA"
        self.assertEqual(parse_channel_ref(cid), ("id", cid))
        self.assertEqual(parse_channel_ref(f"https://www.youtube.com/channel/{cid}/videos"), ("id", cid))
        self.assertEqual(parse_channel_ref("@MrBeast"), ("handle", "@MrBeast"))
        self.assertEqual(parse_channel_ref("https://www.youtube.com/@MrBeast/shorts"), ("handle", "@MrBeast"))
        self.assertEqual(parse_channel_ref("youtube.com/user/pewdiepie"), ("username", "pewdiepie"))
        self.assertEqual(parse_channel_ref("https://www.youtube.com/c/SomeName"), ("custom", "SomeName"))
        self.assertEqual(parse_channel_ref("https://youtu.be/dQw4w9WgXcQ")[0], "video")
        with self.assertRaises(ResolveError):
            parse_channel_ref("two words")


class RssTests(unittest.TestCase):
    def test_shorts_feed(self):
        feed = parse_feed((FIXTURES / "rss_youtube_channel.xml").read_bytes())
        self.assertTrue(feed["channel"]["id"].startswith("UC"))
        self.assertEqual(len(feed["videos"]), 15)
        v = feed["videos"][0]
        self.assertTrue(v["is_short"])
        self.assertIsInstance(v["views"], int)
        self.assertIsInstance(v["likes"], int)
        self.assertTrue(v["published_ts"] > 0)

    def test_longform_feed(self):
        feed = parse_feed((FIXTURES / "rss_longform_channel.xml").read_bytes())
        self.assertTrue(all(not v["is_short"] for v in feed["videos"]))
        self.assertTrue(all(v["url"].startswith("https://www.youtube.com/watch") for v in feed["videos"]))

    def test_rejects_html_and_entities(self):
        with self.assertRaises(FeedError):
            parse_feed(b"<!DOCTYPE html><html><title>Error 500</title></html>")
        with self.assertRaises(FeedError):
            parse_feed(b'<?xml version="1.0"?><!DOCTYPE lol [<!ENTITY a "aaaa">]><feed>&a;</feed>')


class SuggestParsingTests(unittest.TestCase):
    def test_json_and_jsonp(self):
        data = json.loads((FIXTURES / "suggest_minecraft_r.json").read_text())
        self.assertEqual(parse_response(json.dumps(data))[:2], ["minecraft roleplay", "minecraft redstone"])
        jsonp = 'window.google.ac.h(["x",[["x one",0,[512]],["x two",0,[512]]],{"k":"v"}])'
        self.assertEqual(parse_response(jsonp), ["x one", "x two"])
        self.assertIsNone(parse_response("<html>blocked</html>"))

    def test_normalize_query_keeps_trailing_space(self):
        self.assertEqual(normalize_query("Minecraft  "), "minecraft ")
        self.assertEqual(normalize_query("Minecraft"), "minecraft")
        self.assertEqual(normalize_query("   "), "")

    def test_budget(self):
        b = Budget(2)
        self.assertTrue(b.take())
        self.assertTrue(b.take())
        self.assertFalse(b.take())
        self.assertEqual(b.used, 2)


class YouTubeHelperTests(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(parse_iso_duration("PT1H2M3S"), 3723)
        self.assertEqual(parse_iso_duration("PT45S"), 45)
        self.assertEqual(parse_iso_duration("P0D"), 0)
        self.assertEqual(parse_iso_duration("P1DT1S"), 86401)
        self.assertIsNone(parse_iso_duration("garbage"))

    def test_uploads_playlists(self):
        self.assertEqual(uploads_playlist("UCabc"), "UUabc")
        self.assertEqual(uploads_playlist("UCabc", "short"), "UUSHabc")
        self.assertEqual(uploads_playlist("UCabc", "long"), "UULFabc")

    def test_error_mapping(self):
        def err(status, payload):
            return _to_youtube_error(HttpError(status, json.dumps(payload).encode(), "u"))
        e = err(403, {"error": {"code": 403, "message": "quota", "errors": [{"reason": "quotaExceeded"}]}})
        self.assertEqual(e.reason, "quotaExceeded")
        self.assertIn("quota", str(e).lower())
        e = err(400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "errors": [{"reason": "badRequest"}]}})
        self.assertEqual(e.reason, "keyInvalid")
        e = err(403, {"error": {"message": "YouTube Data API v3 has not been used in project 123 before or it is disabled."}})
        self.assertEqual(e.reason, "accessNotConfigured")
        self.assertIsInstance(e, YouTubeError)


if __name__ == "__main__":
    unittest.main()
