"""Title click-through potential: an explainable heuristic score (0-100) plus offline title ideas.

The score rewards patterns that consistently correlate with high CTR on YouTube (specificity,
curiosity, stakes, direct address, proven formats, clean length) and penalises spammy or vague
titles. Every point is explained so you can see *why* a title scores the way it does.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional

from .textutil import (
    contains_all_tokens, contains_phrase, emoji_count, hashtags, normalize, normalize_keyword, smart_title, tokens,
)

POWER_WORDS = {
    "secret", "secrets", "insane", "crazy", "shocking", "hidden", "truth", "never", "stop", "mistake", "mistakes",
    "worst", "best", "ultimate", "proven", "finally", "instantly", "easy", "easiest", "simple", "fast", "fastest",
    "free", "hack", "hacks", "trick", "tricks", "genius", "impossible", "unbelievable", "incredible", "epic",
    "brutal", "dangerous", "illegal", "banned", "forbidden", "rare", "weird", "strange", "terrifying", "scary",
    "perfect", "powerful", "massive", "tiny", "giant", "biggest", "smallest", "first", "last", "only", "every",
    "nobody", "everyone", "exposed", "revealed", "real", "fake", "expensive", "cheap", "million", "billion",
    "survive", "survived", "destroyed", "broke", "broken", "wrong", "actually", "literally", "unexpected",
    "satisfying", "legendary", "viral", "challenge", "tested", "ranked", "rating",
}
EMOTION_WORDS = {
    "love", "hate", "angry", "happy", "sad", "cry", "cried", "crying", "funny", "hilarious", "scared", "shocked",
    "amazing", "awesome", "beautiful", "disgusting", "cute", "wholesome", "heartbreaking", "emotional", "rage",
    "regret", "proud", "lonely", "fear", "panic", "wow", "omg",
}
CURIOSITY_PATTERNS = (
    r"\bwhy\b", r"\bhow\b", r"\bwhat happens\b", r"\bthis is why\b", r"\bnobody\b", r"\bno one\b",
    r"\bsecret", r"\btruth\b", r"\byou won'?t believe\b", r"\buntil\b", r"\bturns out\b", r"\bwait\b",
    r"\bthis\b", r"\bthe reason\b", r"\bwhat if\b", r"\.\.\.|…$", r"\bdid(n'?t)? (you )?know\b",
)
FORMAT_PATTERNS = (
    (r"^i (tried|tested|spent|built|made|bought|survived|ate|became|lived|asked|paid|found|went)\b",
     "Personal experiment/story format (\"I tried…\")"),
    (r"\b\d+\s*(hours?|days?|weeks?|months?|years?|minutes?|seconds?)\b", "Specific timeframe"),
    (r"\$\s?\d|\b\d+\s*(dollars?|k|million)\b", "Money / stakes"),
    (r"\bvs\.?\b|\bversus\b", "Comparison (\"X vs Y\")"),
    (r"\b(ranking|ranked|tier list|top \d+)\b", "Ranking / list format"),
    (r"^(how to|how i)\b", "How-to / tutorial format"),
    (r"\bchallenge\b", "Challenge format"),
    (r"\bpov\b", "POV format (popular on Shorts)"),
)
SPAM_PATTERNS = (r"not clickbait", r"must watch", r"gone wrong", r"\bfree (money|robux|vbucks)\b",
                 r"100% (real|working)", r"sub ?4 ?sub", r"\bplease (subscribe|watch)\b")
WEAK_OPENERS = ("video", "my video", "new video", "part", "episode", "vlog", "untitled", "clip", "update")


def score_title(title: str, *, fmt: str = "short", keyword: Optional[str] = None) -> Dict[str, Any]:
    raw = (title or "").strip()
    text = normalize(raw)
    words = tokens(raw)
    is_short = fmt == "short"
    signals: List[Dict[str, Any]] = []
    score = 50.0

    def add(points: float, label: str, detail: str = "") -> None:
        nonlocal score
        score += points
        signals.append({"points": round(points, 1), "label": label, "detail": detail})

    if not raw:
        return {"title": raw, "score": 0, "grade": "F", "signals": [], "suggestions": ["Write a title first."]}

    n = len(raw)
    lo, hi = (20, 55) if is_short else (40, 65)
    if lo <= n <= hi:
        add(10, "Good length", f"{n} characters")
    elif n < 12:
        add(-10, "Too short to intrigue", f"{n} characters")
    elif n < lo:
        add(2, "A bit short", f"{n} characters — room for a hook or detail")
    elif n <= hi + 15:
        add(3, "Slightly long", f"{n} characters — may truncate on mobile")
    else:
        add(-8, "Too long", f"{n} characters — will be cut off")

    wc = len(words)
    if 3 <= wc <= 10:
        add(4, "Easy to scan", f"{wc} words")
    elif wc <= 2:
        add(-6, "Too few words", f"{wc} words")
    elif wc > 14:
        add(-6, "Wordy", f"{wc} words")

    if re.search(r"\d", raw):
        add(6, "Uses a number", "specifics and numbers make titles concrete")
        if re.match(r"^\d", raw):
            add(2, "Opens with a number")

    power = sorted({w for w in words if w in POWER_WORDS})
    if power:
        pts = min(8, 4 + 2 * (len(power) - 1))
        add(pts, "Power words", ", ".join(power[:4]))
        if len(power) >= 4:
            add(-4, "Too many hype words", "can read as clickbait")
    emotion = sorted({w for w in words if w in EMOTION_WORDS})
    if emotion:
        add(3, "Emotional language", ", ".join(emotion[:3]))

    curiosity = [p for p in CURIOSITY_PATTERNS if re.search(p, text)]
    if curiosity:
        add(min(6, 3 + len(curiosity)), "Curiosity gap", "invites the viewer to find out")
    if raw.endswith("?"):
        add(3, "Asks a question")

    if re.search(r"\byou(r|'re|’re)?\b", text):
        add(4, "Speaks to the viewer (you/your)")

    fmts = [label for pattern, label in FORMAT_PATTERNS if re.search(pattern, text)]
    for label in fmts[:2]:
        add(4, label)

    if keyword:
        kw = normalize_keyword(keyword)
        if contains_phrase(raw, kw):
            pos = text.find(kw)
            add(8, "Contains the target keyword", f'"{kw}"')
            if 0 <= pos <= max(0.4 * n, 10):
                add(4, "Keyword near the start")
        elif contains_all_tokens(raw, kw):
            add(3, "Contains the keyword's words", "not as an exact phrase")
        else:
            add(-8, "Missing the target keyword", f'"{kw}"')

    letters = re.findall(r"[A-Za-z]{2,}", raw)
    caps = [w for w in letters if w.isupper()]
    if letters and len(caps) == len(letters) and len(letters) > 1:
        add(-8, "ALL CAPS", "reads as shouting")
    elif 1 <= len(caps) <= 2:
        add(2, "Strategic capitalisation", ", ".join(caps))
    elif len(caps) > 3:
        add(-4, "Too many capitalised words")

    emojis = emoji_count(raw)
    if is_short and emojis == 1:
        add(1, "One emoji")
    elif emojis > (2 if is_short else 1):
        add(-4, "Too many emojis")

    if re.search(r"[!?]{3,}", raw):
        add(-5, "Punctuation spam", "!!! or ???")
    tags_in_title = hashtags(raw)
    if tags_in_title:
        if is_short and len(tags_in_title) <= 2:
            add(0, "Hashtags in title", "fine for Shorts in moderation")
        else:
            add(-4, "Hashtags clutter the title", " ".join(tags_in_title))

    if any(re.search(p, text) for p in SPAM_PATTERNS):
        add(-8, "Spammy phrasing", "phrases like this lower trust")
    if any(text.startswith(w) for w in WEAK_OPENERS):
        add(-6, "Weak opener", "start with the hook, not a label")

    long_words = [w for w in words if len(w) >= 12]
    if words and sum(len(w) for w in words) / len(words) > 7.5:
        add(-4, "Hard to read", "many long words")
    elif len(long_words) >= 3:
        add(-2, "Several long words")

    lowered = [w for w in words if len(w) > 3]
    if len(lowered) != len(set(lowered)) and not re.search(r"\bvs\.?\b|\bversus\b", text):
        add(-3, "Repeated words")

    if not is_short:
        if re.search(r"[\[(].+[\])]", raw):
            add(2, "Bracketed detail", "e.g. (Full Guide) / [2026]")
        year = dt.date.today().year
        if re.search(rf"\b({year}|{year + 1})\b", raw):
            add(2, "Current year", "signals fresh information")

    score = max(0.0, min(100.0, score))
    return {
        "title": raw,
        "score": round(score),
        "grade": "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D" if score >= 35 else "F",
        "signals": signals,
        "suggestions": _suggestions(signals, is_short, bool(keyword)),
        "length": n,
    }


def _suggestions(signals: List[Dict[str, Any]], is_short: bool, has_kw: bool) -> List[str]:
    labels = {s["label"] for s in signals}
    tips = []
    if "Uses a number" not in labels:
        tips.append("Add a specific number (time, count, money) to make it concrete.")
    if "Curiosity gap" not in labels and "Asks a question" not in labels:
        tips.append("Open a curiosity gap — hint at an outcome without giving it away.")
    if "Speaks to the viewer (you/your)" not in labels:
        tips.append("Speak to the viewer: 'you/your' makes it personal.")
    if "Power words" not in labels and "Emotional language" not in labels:
        tips.append("Add one strong word (e.g. secret, mistake, finally, insane) — but only one or two.")
    if any(s["label"] in ("Too long", "Slightly long") for s in signals):
        tips.append("Cut filler words; Shorts titles work best under ~55 characters." if is_short
                    else "Trim to under ~65 characters so it isn't truncated.")
    if has_kw and "Missing the target keyword" in labels:
        tips.append("Work the target keyword into the title, ideally near the start.")
    return tips[:5]


def compare_titles(titles: List[str], *, fmt: str = "short", keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    scored = [score_title(t, fmt=fmt, keyword=keyword) for t in titles if t and t.strip()]
    return sorted(scored, key=lambda r: -r["score"])


SHORT_TEMPLATES = (
    "{K} in 60 Seconds",
    "This {K} Trick Changes Everything",
    "Stop Doing {K} Like This",
    "The {K} Secret Nobody Talks About",
    "I Tried {K} So You Don't Have To",
    "You've Been Doing {K} Wrong",
    "Why {K} Is Harder Than It Looks",
    "{K}: Wait for the End",
    "POV: You Finally Master {K}",
    "3 {K} Mistakes You're Making",
    "The Fastest Way to Get Better at {K}",
    "Only 1% Know This {K} Hack",
    "{K} Level 1 vs Level 100",
    "I Spent 24 Hours on {K}",
)
LONG_TEMPLATES = (
    "{K}: The Complete Beginner's Guide ({Y})",
    "7 {K} Mistakes You're Probably Making",
    "I Tried {K} for 30 Days — Here's What Happened",
    "The Truth About {K} Nobody Tells You",
    "{K} Explained in 10 Minutes",
    "{K} Tips That Actually Work in {Y}",
    "Why Most People Fail at {K} (and How to Fix It)",
    "I Tested Every {K} Method — This One Won",
    "{K} for Beginners: Everything You Need to Know",
    "Stop Wasting Time on {K} — Do This Instead",
    "The Ultimate {K} Tier List ({Y})",
    "How I Got Good at {K} Fast (Step-by-Step)",
)


HOWTO_SHORT_TEMPLATES = (
    "How to {V} in 60 Seconds",
    "How to {V} (The Easy Way)",
    "The Fastest Way to {V}",
    "Stop Trying to {V} Like This",
    "You've Been Trying to {V} Wrong",
    "I Learned to {V} in 7 Days",
    "3 Tips to {V} Better Instantly",
    "How to {V} — The Secret Nobody Tells You",
    "Why You Can't {V} (Yet)",
    "{V} — Beginner vs Pro",
)
HOWTO_LONG_TEMPLATES = (
    "How to {V}: The Complete Beginner's Guide ({Y})",
    "How to {V} Step by Step (Easy Method)",
    "I Learned to {V} in 30 Days — Here's How",
    "7 Mistakes People Make When They {V}",
    "The Fastest Way to {V} in {Y}",
    "How I Learned to {V} (and You Can Too)",
    "Stop Struggling: How to {V} the Right Way",
    "Everything You Need to Know to {V}",
)


def generate_titles(keyword: str, *, fmt: str = "short", limit: int = 12) -> List[Dict[str, Any]]:
    """Template-based title ideas (no AI needed), ranked by the CTR heuristic."""
    kw = normalize_keyword(keyword)
    if not kw:
        return []
    year = dt.date.today().year
    if kw.startswith("how to ") and len(kw) > 7:
        verb_phrase = smart_title(kw[7:])
        verb_phrase = verb_phrase[:1].upper() + verb_phrase[1:]
        templates = HOWTO_SHORT_TEMPLATES if fmt == "short" else HOWTO_LONG_TEMPLATES
        titles = [tpl.format(V=verb_phrase, Y=year) for tpl in templates]
    else:
        K = smart_title(kw)
        templates = SHORT_TEMPLATES if fmt == "short" else LONG_TEMPLATES
        titles = [tpl.format(K=K, Y=year) for tpl in templates]
    scored = [score_title(t, fmt=fmt, keyword=kw) for t in titles]
    scored.sort(key=lambda r: -r["score"])
    return [{"title": r["title"], "score": r["score"], "grade": r["grade"]} for r in scored[:limit]]
