"""Tag & hashtag generator: target keyword + autocomplete variations + tags used by top-ranking videos."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .keywords import analyze_serp, estimate_volume
from .suggest import Budget
from .textutil import (
    content_tokens, normalize_keyword, singular, token_set, tokens, top_phrases, youtube_tag_length,
)

TAG_CHAR_LIMIT = 500


def _signature(tag: str) -> str:
    return " ".join(sorted(singular(t) for t in tokens(tag)))


def suggest_tags(app, keyword: str, *, fmt: str = "short", title: Optional[str] = None,
                 region: Optional[str] = None, language: Optional[str] = None, use_api: bool = True,
                 limit: int = 30, with_volume: bool = True) -> Dict[str, Any]:
    kw = normalize_keyword(keyword)
    if not kw:
        raise ValueError("Enter a keyword.")
    sug = app.suggest(language, region)
    budget = Budget(45)
    cands: Dict[str, Dict[str, Any]] = {}
    seen_sigs: Dict[str, str] = {}

    def add(tag: str, score: float, source: str) -> None:
        tag = normalize_keyword(tag)
        tag = re.sub(r"[<>,]", "", tag).strip()
        if not tag or len(tag) > 60 or len(tag) < 2:
            return
        sig = _signature(tag)
        key = seen_sigs.get(sig, tag)
        seen_sigs.setdefault(sig, tag)
        c = cands.setdefault(key, {"tag": key, "score": 0.0, "sources": []})
        c["score"] = max(c["score"], score) + (4 if source not in c["sources"] and c["sources"] else 0)
        if source not in c["sources"]:
            c["sources"].append(source)

    add(kw, 100, "keyword")
    results = sug.many([kw, kw + " "], budget)
    for rank, s in enumerate(results.get(kw) or [], 1):
        add(s, 88 - rank * 3, "autocomplete")
    for rank, s in enumerate(results.get(kw + " ") or [], 1):
        add(s, 86 - rank * 3, "autocomplete")

    serp_error = None
    yt = app.youtube()
    if use_api and yt.enabled:
        try:
            serp = analyze_serp(yt, kw, region=(region or app.region), language=(language or app.language))
            counts: Dict[str, int] = {}
            channel_names = {v["channel_title"].lower() for v in serp["videos"]}
            for v in serp["videos"][:25]:
                for t in {normalize_keyword(t) for t in v.get("tags") or []}:
                    if t and t not in channel_names and len(t) <= 60:
                        counts[t] = counts.get(t, 0) + 1
            if counts:
                top = max(counts.values())
                for t, c in counts.items():
                    if c >= 2 or top == 1:
                        add(t, 40 + 48 * c / top, "top videos")
            for phrase, count in top_phrases([v["title"] for v in serp["videos"][:25]], limit=10):
                add(phrase, 45 + 3 * count, "top titles")
        except Exception as err:  # the free parts still work
            serp_error = str(err)

    if title:
        for phrase, _ in top_phrases([title, title], min_count=1, limit=5):
            add(phrase, 55, "your title")
    toks = [t for t in content_tokens(kw) if len(t) > 2]
    if len(tokens(kw)) > 1:
        for t in toks:
            add(t, 38, "broad")

    ranked = sorted(cands.values(), key=lambda c: -c["score"])[:limit]
    kw_tokens = token_set(kw)
    for c in ranked:
        c["relevance"] = round(len(kw_tokens & token_set(c["tag"])) / max(1, len(kw_tokens)), 2)
        c["score"] = round(min(100.0, c["score"]), 1)

    if with_volume:
        vol_budget = Budget(40)
        with ThreadPoolExecutor(max_workers=4) as pool:
            vols = list(pool.map(lambda c: estimate_volume(c["tag"], sug, vol_budget, known_query=True), ranked[:15]))
        for c, v in zip(ranked, vols):
            c["volume"] = v["score"]
            c["band"] = v.get("band")

    selected: List[str] = []
    for c in ranked:
        if youtube_tag_length(selected + [c["tag"]]) <= TAG_CHAR_LIMIT:
            selected.append(c["tag"])
    hashtags = _hashtags(kw, [c["tag"] for c in ranked], fmt)
    return {
        "keyword": kw,
        "tags": ranked,
        "selected": selected,
        "copy": ", ".join(selected),
        "char_count": youtube_tag_length(selected),
        "hashtags": hashtags,
        "hashtag_copy": " ".join(hashtags),
        "api_used": bool(yt.enabled and use_api and not serp_error),
        "api_error": serp_error,
        "quota_units": yt.units_this_request,
    }


def _hashtags(kw: str, tags: List[str], fmt: str) -> List[str]:
    out: List[str] = []

    def tagify(text: str) -> str:
        words = [w for w in tokens(text) if w]
        return "#" + "".join(words) if words else ""

    main = tagify(kw)
    if main and len(main) <= 30:
        out.append(main)
    for t in tags:
        if len(out) >= 4:
            break
        h = tagify(t)
        if h and h not in out and len(h) <= 24 and len(tokens(t)) <= 2:
            out.append(h)
    if fmt == "short" and "#shorts" not in out:
        out.append("#shorts")
    return out[:5]
