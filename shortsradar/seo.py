"""Metadata SEO scorecard for a video (published or draft): title, description, tags, hashtags, chapters."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .textutil import (
    NOISE_WORDS, contains_all_tokens, contains_phrase, emoji_count, hashtags, ngrams, normalize, normalize_keyword,
    tokens, youtube_tag_length,
)

PASS, WARN, FAIL, NA = "pass", "warn", "fail", "na"
CREDIT = {PASS: 1.0, WARN: 0.5, FAIL: 0.0}
TIMESTAMP = re.compile(r"(?m)^\s*(?:\(?)(\d{1,2}:)?\d{1,2}:\d{2}(?:\)?)\s+\S")


def detect_keyword(title: str, tags: List[str], description: str = "") -> Optional[str]:
    """Guess the phrase a video targets (first tag found in the title, else the best title n-gram)."""
    for tag in tags:
        t = normalize_keyword(tag)
        if len(t) > 2 and contains_phrase(title, t):
            return t
    words = tokens(title)
    best: Optional[str] = None
    best_score = 0.0
    tag_text = " , ".join(tags)
    for n in (4, 3, 2):
        for gram in ngrams(words, n):
            if gram[0] in NOISE_WORDS or gram[-1] in NOISE_WORDS:
                continue
            phrase = " ".join(gram)
            score = 0.0
            if contains_phrase(tag_text, phrase):
                score += 2.0
            if contains_phrase(description, phrase):
                score += 1.0
            score += 0.1 * n
            if score > best_score:
                best, best_score = phrase, score
    if best and best_score >= 1.0:
        return best
    if tags:
        return normalize_keyword(tags[0])
    content = [w for w in words if w not in NOISE_WORDS and len(w) > 2]
    if len(content) >= 2:
        return " ".join(content[:2])
    return content[0] if content else None


def _check(checks: List[Dict[str, Any]], cid: str, label: str, weight: float, status: str,
           detail: str, tip: str = "") -> None:
    checks.append({"id": cid, "label": label, "weight": weight, "status": status, "detail": detail,
                   "tip": tip if status in (WARN, FAIL) else ""})


def score_metadata(
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    *,
    keyword: Optional[str] = None,
    fmt: str = "short",
    duration_s: Optional[int] = None,
    caption: Optional[bool] = None,
    language_set: Optional[bool] = None,
) -> Dict[str, Any]:
    title = (title or "").strip()
    description = description or ""
    tags = [t.strip() for t in (tags or []) if t and t.strip()]
    is_short = fmt == "short"
    kw = normalize_keyword(keyword) if keyword else detect_keyword(title, tags, description)
    checks: List[Dict[str, Any]] = []

    # --- title length
    n = len(title)
    if is_short:
        status = PASS if 15 <= n <= 60 else WARN if 8 <= n <= 80 else FAIL
        _check(checks, "title_length", "Title length", 8, status, f"{n} characters (Shorts: 15–60 is ideal).",
               "Keep Shorts titles short and punchy — they sit on top of the video on mobile.")
    else:
        status = PASS if 30 <= n <= 70 else WARN if 20 <= n <= 90 else FAIL
        _check(checks, "title_length", "Title length", 8, status, f"{n} characters (30–70 is ideal).",
               "Titles over ~70 characters get cut off in search and suggested videos.")

    # --- keyword in title / near start
    if kw:
        if contains_phrase(title, kw):
            pos = normalize(title).find(kw)
            _check(checks, "keyword_in_title", "Keyword in title", 16, PASS, f'Title contains "{kw}".')
            early = pos >= 0 and pos <= max(0.4 * n, 12)
            _check(checks, "keyword_title_start", "Keyword near the start of the title", 6, PASS if early else WARN,
                   "Keyword appears early." if early else "Keyword appears late in the title.",
                   "Front-load the keyword — the first words carry the most weight for search and viewers.")
        elif contains_all_tokens(title, kw):
            _check(checks, "keyword_in_title", "Keyword in title", 16, WARN,
                   f'Title has the words of "{kw}" but not as an exact phrase.',
                   f'Use the exact phrase "{kw}" in the title if it reads naturally.')
            _check(checks, "keyword_title_start", "Keyword near the start of the title", 6, WARN,
                   "Exact phrase not found.", "Front-load the keyword.")
        else:
            _check(checks, "keyword_in_title", "Keyword in title", 16, FAIL, f'Title does not contain "{kw}".',
                   f'Put "{kw}" (or a close variation people search for) in the title.')
            _check(checks, "keyword_title_start", "Keyword near the start of the title", 6, FAIL,
                   "Keyword missing from title.", "Front-load the keyword.")
    else:
        _check(checks, "keyword_in_title", "Keyword in title", 16, WARN, "No target keyword could be identified.",
               "Decide which search phrase this video should rank for and use it in the title, description and tags.")

    # --- description
    d = len(description.strip())
    if is_short:
        status = PASS if d >= 100 else WARN if d >= 30 else FAIL
        _check(checks, "description_length", "Description length", 4, status, f"{d} characters.",
               "Add 1–3 sentences describing the Short with your keyword and 2–3 hashtags.")
    else:
        status = PASS if d >= 1000 else WARN if d >= 250 else FAIL
        _check(checks, "description_length", "Description length", 8, status, f"{d} characters (1,000+ recommended).",
               "Write a fuller description (200+ words): summary, keywords, chapters, links.")

    first = description[:150]
    kw_weight = 6 if is_short else 10
    if kw:
        in_top = contains_phrase(first, kw) or contains_all_tokens(first, kw)
        anywhere = contains_phrase(description, kw) or contains_all_tokens(description, kw)
        status = PASS if in_top else WARN if anywhere else FAIL
        _check(checks, "keyword_description_top", "Keyword in first 150 characters of description", kw_weight, status,
               "Found above the fold." if in_top else "Found later in the description." if anywhere else "Not in description.",
               "Mention the keyword in the first sentence — it's what shows in search results.")
        count = len(re.findall(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", normalize(description)))
        if count > 6:
            status, detail = WARN, f"Keyword used {count} times — may look like keyword stuffing."
        elif count >= 2:
            status, detail = PASS, f"Keyword used {count} times."
        elif count == 1:
            status, detail = WARN, "Keyword used once."
        else:
            status, detail = FAIL, "Exact keyword not used in description."
        _check(checks, "keyword_repeats", "Keyword repeated naturally in description", 2 if is_short else 4, status, detail,
               "Use the keyword 2–4 times naturally (plus close variations).")

    # --- tags
    tag_chars = youtube_tag_length(tags)
    count = len(tags)
    min_tags = 3 if is_short else 5
    status = PASS if count >= min_tags else WARN if count >= 1 else FAIL
    _check(checks, "tags_count", "Tags", 6 if is_short else 8, status, f"{count} tag{'' if count == 1 else 's'}.",
           "Add tags: your exact keyword first, then variations, then broader topic tags.")
    if tag_chars > 500:
        status, detail = FAIL, f"{tag_chars}/500 characters — over YouTube's limit, upload will fail."
    elif tag_chars >= 200 or (is_short and tag_chars >= 100):
        status, detail = PASS, f"{tag_chars}/500 characters used."
    elif tag_chars >= 60:
        status, detail = WARN, f"{tag_chars}/500 characters used."
    else:
        status, detail = FAIL, f"{tag_chars}/500 characters used."
    _check(checks, "tags_chars", "Tag space used", 4, status, detail,
           "Use more of the 500-character tag budget with relevant variations." if tag_chars <= 500
           else "Remove the least relevant tags to get under 500 characters.")
    if kw:
        norm_tags = [normalize_keyword(t) for t in tags]
        if norm_tags and (norm_tags[0] == kw or contains_phrase(norm_tags[0], kw)):
            status, detail = PASS, "First tag is the target keyword."
        elif any(t == kw or contains_phrase(t, kw) for t in norm_tags):
            status, detail = WARN, "Keyword is in the tags but not first."
        else:
            status, detail = FAIL, "Keyword is not in the tags."
        _check(checks, "keyword_first_tag", "Target keyword is the first tag", 6, status, detail,
               f'Make "{kw}" your first tag.')
        places = sum([contains_phrase(title, kw), contains_phrase(description, kw),
                      any(contains_phrase(t, kw) for t in norm_tags)])
        _check(checks, "triple_dip", "Keyword in title, description AND tags", 4,
               PASS if places == 3 else WARN if places == 2 else FAIL, f"Found in {places} of 3 places.",
               "Using the same phrase in all three strongly signals the topic to YouTube.")
    if tags:
        body = title + " " + description
        relevant = sum(1 for t in tags if contains_all_tokens(body, t))
        ratio = relevant / len(tags)
        _check(checks, "tags_relevance", "Tags match the title/description", 6,
               PASS if ratio >= 0.6 else WARN if ratio >= 0.3 else FAIL,
               f"{relevant} of {len(tags)} tags are reflected in the title or description.",
               "Remove tags unrelated to the video — irrelevant tags can be treated as misleading metadata.")

    # --- hashtags
    tags_found = hashtags(title) + hashtags(description)
    h = len(tags_found)
    if h > 15:
        status, detail = FAIL, f"{h} hashtags — YouTube ignores ALL hashtags when there are more than 15."
    elif 1 <= h <= 5:
        status, detail = PASS, f"{h} hashtags: {' '.join(tags_found[:5])}"
    elif h == 0:
        status, detail = WARN, "No hashtags."
    else:
        status, detail = WARN, f"{h} hashtags — 3–5 focused ones work better."
    _check(checks, "hashtags", "Hashtags", 6 if is_short else 4, status, detail,
           "Add 2–4 relevant hashtags (the first 3 in the description show above the title)."
           + (" #shorts is optional but harmless." if is_short else ""))

    # --- chapters (long-form > 5 min)
    if not is_short and (duration_s is None or duration_s >= 300):
        stamps = TIMESTAMP.findall(description)
        has_zero = bool(re.search(r"(?m)^\s*\(?0?0:00\)?\s+\S", description))
        if len(stamps) >= 3 and has_zero:
            status, detail = PASS, f"{len(stamps)} chapters."
        elif stamps:
            status, detail = WARN, "Timestamps found, but chapters need 3+ timestamps starting at 0:00."
        else:
            status, detail = FAIL, "No chapters."
        _check(checks, "chapters", "Chapters (timestamps)", 5, status, detail,
               "Add chapters (0:00 Intro, 1:23 …) — they can appear as key moments in Google and YouTube search.")

    # --- links / CTA
    has_link = bool(re.search(r"https?://", description))
    has_cta = bool(re.search(r"\b(subscribe|follow|join|comment|like)\b", description, re.I))
    _check(checks, "cta", "Call to action or links in description", 3, PASS if (has_link or has_cta) else WARN,
           "Found." if (has_link or has_cta) else "No links or call to action.",
           "Add a subscribe prompt or link to a related video/playlist to keep viewers on your channel.")

    # --- title style
    words = [w for w in re.findall(r"[A-Za-z]{2,}", title)]
    caps = sum(1 for w in words if w.isupper())
    ratio = caps / len(words) if words else 0
    _check(checks, "title_caps", "Title isn't shouting", 3, PASS if ratio <= 0.3 else WARN if ratio <= 0.6 else FAIL,
           f"{caps} of {len(words)} words in ALL CAPS.", "Use capitals for 1–2 emphasis words at most.")
    spam = bool(re.search(r"[!?]{3,}", title)) or emoji_count(title) > (2 if is_short else 1)
    _check(checks, "title_spam", "No punctuation/emoji spam in title", 3, WARN if spam else PASS,
           "Repeated punctuation or many emojis." if spam else "Clean.",
           "Drop repeated !!!/??? and keep emojis to 1–2.")

    # --- published-video extras
    if caption is not None:
        _check(checks, "captions", "Manual captions uploaded", 3, PASS if caption else WARN,
               "Captions available." if caption else "Only auto-captions (or none).",
               "Upload or correct captions — they improve accessibility and give YouTube accurate text.")
    if language_set is not None:
        _check(checks, "language", "Video language set", 2, PASS if language_set else WARN,
               "Language set." if language_set else "Video/audio language not set.",
               "Set the video language in YouTube Studio so it's recommended to the right audience.")

    applicable = [c for c in checks if c["status"] != NA]
    total_w = sum(c["weight"] for c in applicable) or 1
    score = 100.0 * sum(c["weight"] * CREDIT[c["status"]] for c in applicable) / total_w
    return {
        "score": round(score),
        "grade": grade(score),
        "keyword": kw,
        "keyword_detected": not bool(keyword),
        "checks": checks,
        "fixes": [c["tip"] for c in sorted(applicable, key=lambda c: (CREDIT[c["status"]], -c["weight"])) if c["tip"]][:8],
        "stats": {
            "title_chars": n,
            "description_chars": d,
            "description_words": len(description.split()),
            "tag_count": len(tags),
            "tag_chars": tag_chars,
            "hashtags": tags_found,
        },
    }


def grade(score: float) -> str:
    return "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "F"
