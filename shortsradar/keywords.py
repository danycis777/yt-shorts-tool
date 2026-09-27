"""Keyword research: search volume, competition and an overall opportunity score (0-100 each).

Search volume
    Estimated from YouTube autocomplete with a "suggestion chain" model. Autocomplete ranks
    completions by popularity, so we walk the keyword prefix by prefix: at each probe we look at
    which suggestions continue along the keyword, estimate what share of the prefix's search mass
    they carry (Zipf-weighted by rank), jump ahead, and finally read the keyword's own rank. The
    product of shares gives an estimated monthly search count. Head terms surface after typing one
    letter; long-tail phrases only when typed (almost) completely; nonsense never.

Competition (needs a YouTube API key)
    From the top search results: how many titles/tags explicitly target the phrase, how big the
    ranking channels are, how many views the ranking videos have and how many come from 1M+
    channels.

Overall
    Weighted geometric blend of volume and (100 - competition): high only when there is demand
    AND room to rank.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from .stats import clamp, geometric_blend, log_scale, median
from .suggest import Budget, Suggest
from .textutil import (
    QUESTION_WORDS, STOPWORDS, contains_all_tokens, contains_phrase, content_tokens, normalize_keyword,
    singular, token_set, tokens, top_phrases,
)
from .videos import normalize_channel, normalize_video

# ---- volume model constants (calibrated against reference keywords; see README) -------------
LOG_TOTAL = 9.7            # log10 of the monthly search "mass" the model starts from
ZIPF = 0.9                 # rank decay of autocomplete suggestions (share of a single query)
ZIPF_HOP = 0.6             # rank weighting when estimating the share of a whole prefix family
HOP_SMOOTH = 0.0
CAP_FACTOR = 30.0          # soft cap on mid-word continuations absent from suggestions
FIRST_CHAR_BRANCHING = 16.0  # narrowing from 'all searches' to searches starting with one letter
BRANCHING = (7.0, 3.0, 3.0, 2.0, 1.6, 1.4)  # narrowing per typed char, by position inside a word
_ZN = sum(1.0 / (r ** ZIPF) for r in range(1, 11))
SCORE_LOG_MIN, SCORE_LOG_MAX = 1.0, 7.3  # 10/month -> 0, ~20M/month -> 100

VOLUME_BANDS = (
    (1_000_000, "Very high"),
    (100_000, "High"),
    (10_000, "Medium"),
    (1_000, "Low"),
    (0, "Very low"),
)


def _branch(k: str, i: int) -> float:
    if i == 0:
        return FIRST_CHAR_BRANCHING
    ws = k.rfind(" ", 0, i) + 1
    return BRANCHING[min(i - ws, len(BRANCHING) - 1)]


def _coverage(log_mass: float) -> float:
    """Share of a prefix's mass held by its top-10 suggestions (small for broad prefixes)."""
    t = (8.0 - log_mass) / 4.0
    return clamp(0.12 + t * 0.73, 0.12, 0.85)


def _hit_share(rank: int, log_mass: float) -> float:
    return _coverage(log_mass) * (1.0 / rank ** ZIPF) / _ZN


def _lcp(a: str, b: str) -> int:
    n = min(len(a), len(b))
    k = 0
    while k < n and a[k] == b[k]:
        k += 1
    return k


def volume_score(log_volume: Optional[float]) -> Optional[float]:
    if log_volume is None:
        return None
    return round(100 * clamp((log_volume - SCORE_LOG_MIN) / (SCORE_LOG_MAX - SCORE_LOG_MIN)), 1)


def volume_band(monthly: Optional[float]) -> str:
    if monthly is None:
        return "Unknown"
    for threshold, label in VOLUME_BANDS:
        if monthly >= threshold:
            return label
    return "Very low"


def estimate_volume(keyword: str, sug: Suggest, budget: Optional[Budget] = None,
                    known_query: bool = False) -> Dict[str, Any]:
    """Estimate monthly YouTube searches for a keyword from autocomplete (see module docstring).

    known_query: the phrase was itself seen as a suggestion somewhere (so it is a real search even
    if its own prefix chain never surfaces it)."""
    k = normalize_keyword(keyword)
    n = len(k)
    out: Dict[str, Any] = {"keyword": k, "log": None, "monthly": None, "score": None, "hit": None,
                           "path": [], "complete": True, "approx": False}
    if not n:
        return out
    i = 1
    log_mass = LOG_TOTAL - math.log10(_branch(k, 0))
    path: List[str] = []
    guard = 0
    while guard < 200:
        guard += 1
        probe = k[:i]
        sugs = sug.get(probe, budget)
        if sugs is None:
            # Out of budget / offline. The phrase was not surfaced yet, so assume it would need about
            # half of the remaining characters typed before appearing near the top.
            remaining = sum(math.log10(_branch(k, c)) for c in range(i, n))
            base = log_mass - 0.5 * remaining
            out.update(complete=False, approx=True)
            return _finish(out, base + math.log10(_hit_share(3, base)), path + [f"{probe!r}: not fetched"])
        if k in sugs:
            rank = sugs.index(k) + 1
            path.append(f"typed {probe!r} -> suggested #{rank}")
            out["hit"] = {"prefix": probe, "rank": rank, "typed_chars": len(probe), "length": n}
            return _finish(out, log_mass + math.log10(_hit_share(rank, log_mass)), path)
        reach = max([_lcp(s, k) for s in sugs] + [0])
        if reach > i:
            j = reach
            if j < n and k[j] != " ":
                jb = k.rfind(" ", 0, j)
                if jb > i:
                    j = jb
            if j > 0 and k[j - 1] == " " and j - 1 > i:
                j -= 1
            weights = [1.0 / (r ** ZIPF_HOP) for r in range(1, len(sugs) + 1)]
            matched = sum(w for w, s in zip(weights, sugs) if s.startswith(k[:j]))
            mass = matched / (sum(weights) + HOP_SMOOTH)
            if mass > 0:
                jumped = log_mass + math.log10(min(1.0, mass))
                typed = log_mass - sum(math.log10(_branch(k, c)) for c in range(i, j))
                if jumped >= typed:
                    path.append(f"typed {probe!r} -> suggestions continue to {k[:j]!r}")
                    log_mass, i = jumped, j
                    continue
        if i >= n:
            extended = any(s.startswith(k) for s in sugs)
            path.append(f"typed full phrase, not suggested{' (longer phrases are)' if extended else ''}")
            factor = 0.05 if known_query else 0.03 if extended else 0.003
            return _finish(out, log_mass + math.log10(factor), path)
        if reach <= i and k[i] != " " and i > 0 and k[i - 1] != " ":
            # Mid-word and no suggestion continues along the keyword: this spelling is a rare
            # continuation of the prefix, so narrow at least as much as a family of queries that
            # all rank below the 10th suggestion would.
            cap = log_mass + math.log10(CAP_FACTOR * _hit_share(10, log_mass))
            log_mass = min(log_mass - math.log10(_branch(k, i)), cap)
        else:
            log_mass -= math.log10(_branch(k, i))
        i += 1
    return _finish(out, log_mass - 3, path)


def _finish(out: Dict[str, Any], log_v: float, path: List[str]) -> Dict[str, Any]:
    out["log"] = round(log_v, 3)
    out["monthly"] = int(round(10 ** log_v)) if log_v > 0 else 0
    out["score"] = volume_score(log_v)
    out["band"] = volume_band(out["monthly"])
    out["path"] = path
    return out


# ---- search results (SERP) analysis ------------------------------------------------------------

def analyze_serp(yt, keyword: str, *, region: Optional[str] = None, language: Optional[str] = None,
                 max_results: int = 50, order: str = "relevance", duration: Optional[str] = None,
                 published_after: Optional[str] = None) -> Dict[str, Any]:
    """Top YouTube search results for a keyword, enriched with stats and channel sizes (~102 units)."""
    res = yt.search(keyword, max_results=max_results, order=order, region=region, language=language,
                    duration=duration, published_after=published_after)
    ids = [it["video_id"] for it in res["items"] if it.get("video_id")]
    rank_of = {vid: i + 1 for i, vid in enumerate(ids)}
    videos = [normalize_video(v) for v in yt.videos(ids, max_age=12 * 3600)]
    videos.sort(key=lambda v: rank_of.get(v["id"], 999))
    channels = {c["id"]: c for c in (normalize_channel(ch) for ch in yt.channels({v["channel_id"] for v in videos}))}
    for v in videos:
        v["rank"] = rank_of.get(v["id"])
        ch = channels.get(v["channel_id"]) or {}
        v["channel_subs"] = ch.get("subs")
        v["views_per_sub"] = round(v["views"] / ch["subs"], 2) if v.get("views") is not None and ch.get("subs") else None
        v["keyword_in_title"] = contains_phrase(v["title"], keyword)
    return {"videos": videos, "total_results": res.get("total"), "channels": channels}


def competition_from_serp(keyword: str, videos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    top = videos[:20]
    top10 = videos[:10]
    if not top:
        return None
    phrase_ratio = sum(1 for v in top if contains_phrase(v["title"], keyword)) / len(top)
    token_ratio = sum(
        1 for v in top if contains_all_tokens(v["title"] + " " + " ".join(v.get("tags") or []), keyword)
    ) / len(top)
    optimization = 0.6 * phrase_ratio + 0.4 * token_ratio
    subs = [v["channel_subs"] for v in top10 if v.get("channel_subs") is not None]
    views = [v["views"] for v in top10 if v.get("views") is not None]
    authority = log_scale(median(subs), 1e3, 1e7) if subs else 0.5
    strength = log_scale(median(views), 1e3, 1e7) if views else 0.5
    big_share = sum(1 for s in subs if s >= 1_000_000) / len(subs) if subs else 0.0
    score = 100 * (0.40 * optimization + 0.25 * authority + 0.20 * strength + 0.15 * big_share)
    return {
        "score": round(score, 1),
        "components": {
            "title_targeting": round(optimization * 100, 1),
            "exact_phrase_titles": round(phrase_ratio * 100, 1),
            "channel_authority": round(authority * 100, 1),
            "result_strength": round(strength * 100, 1),
            "big_channel_share": round(big_share * 100, 1),
        },
        "median_subs_top10": median(subs),
        "median_views_top10": median(views),
    }


def serp_insights(keyword: str, videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    top = videos[:20]
    top10 = videos[:10]
    ages = [v["age_days"] for v in top if v.get("age_days") is not None]
    vpd = [v["views"] / max(v["age_days"], 1.0) for v in top10 if v.get("views") is not None and v.get("age_days")]
    fresh = sum(1 for a in ages if a <= 30)
    shorts = sum(1 for v in top if v.get("is_short"))
    small = sum(1 for v in top10 if v.get("channel_subs") is not None and v["channel_subs"] < 10_000)
    exact = sum(1 for v in top if contains_phrase(v["title"], keyword))
    notes: List[Dict[str, str]] = []
    if top10 and small >= 2:
        notes.append({"type": "good", "text": f"{small} of the top 10 videos come from channels under 10K subscribers — small channels can rank here."})
    elif top10 and small == 0 and any(v.get("channel_subs") for v in top10):
        notes.append({"type": "warn", "text": "Every top-10 video is from an established channel (10K+ subscribers)."})
    if top and exact == 0:
        notes.append({"type": "good", "text": f"None of the top {len(top)} titles contain the exact phrase — a well-targeted title can stand out."})
    elif top and exact / len(top) < 0.3:
        notes.append({"type": "good", "text": f"Only {exact} of the top {len(top)} titles contain the exact phrase — a well-targeted title can stand out."})
    elif top and exact / len(top) > 0.7:
        notes.append({"type": "warn", "text": f"{exact} of the top {len(top)} titles already target this exact phrase — consider a longer, more specific variation."})
    if ages:
        med_age = median(ages) or 0
        if fresh / len(ages) >= 0.3:
            notes.append({"type": "good", "text": f"{fresh} of the top {len(ages)} results are under 30 days old — YouTube is actively surfacing new videos for this topic."})
        elif med_age > 730:
            notes.append({"type": "info", "text": f"Top results are old (median age {med_age / 365:.1f} years). Evergreen topic — a fresher, better video can displace them."})
    if top:
        share = shorts / len(top)
        if share >= 0.5:
            notes.append({"type": "info", "text": f"{shorts} of the top {len(top)} results are Shorts — this search favours short-form."})
        elif share == 0:
            notes.append({"type": "info", "text": "No Shorts rank in the top results — long-form dominates this search."})
    trend = "unknown"
    if ages:
        if fresh / len(ages) >= 0.3:
            trend = "rising"
        elif (median(ages) or 0) > 730:
            trend = "evergreen"
        else:
            trend = "steady"
    return {
        "notes": notes,
        "trend": trend,
        "median_age_days": median(ages),
        "fresh_share": round(fresh / len(ages) * 100, 1) if ages else None,
        "shorts_share": round(shorts / len(top) * 100, 1) if top else None,
        "median_views_per_day_top10": median(vpd),
        "demand_score": round(100 * log_scale(median(vpd), 10, 100_000), 1) if vpd else None,
    }


def overall_score(volume: Optional[float], competition: Optional[float]) -> Optional[float]:
    if volume is None or competition is None:
        return None
    return round(100 * geometric_blend(volume / 100.0, 1 - competition / 100.0, 0.55), 1)


# ---- related keyword expansion --------------------------------------------------------------------

QUESTION_PREFIXES = ("how to", "how", "what", "why", "is", "can", "does", "which")
MODIFIER_PROBES = ("best {k}", "{k} for", "{k} vs", "{k} how", "top {k}", "new {k}")


def classify(candidate: str, seed: str) -> str:
    words = candidate.split()
    if (words and words[0] in QUESTION_WORDS) or candidate.endswith("?") or any(
        f" {q} " in f" {candidate} " for q in ("how to", "what is", "how do", "how does", "why is", "why does", "what are")
    ):
        return "question"
    seed_toks = {singular(t) for t in tokens(seed) if t not in STOPWORDS} or token_set(seed)
    if seed_toks and seed_toks <= token_set(candidate):
        return "matching"
    return "related"


def expansion_probes(seed: str, deep: bool = True) -> List[str]:
    probes = [seed, seed + " "]
    if deep:
        probes += [f"{seed} {c}" for c in "abcdefghijklmnopqrstuvwxyz"]
    if seed.split()[0] not in QUESTION_WORDS:  # "how to how to draw" helps nobody
        probes += [f"{q} {seed}" for q in QUESTION_PREFIXES]
    probes += [m.format(k=seed) for m in MODIFIER_PROBES]
    words = content_tokens(seed)
    if len(tokens(seed)) > 1:
        for w in dict.fromkeys(words):
            if len(w) > 2:
                probes.append(w)
    return list(dict.fromkeys(probes))


def gather_candidates(seed: str, results: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    cands: Dict[str, Dict[str, Any]] = {}
    for probe, sugs in results.items():
        for rank, s in enumerate(sugs or [], 1):
            if s == seed or len(s) > 90 or len(s) < 3:
                continue
            c = cands.setdefault(s, {"keyword": s, "hits": 0, "best_rank": rank, "prelim": 0.0, "probes": []})
            c["hits"] += 1
            c["best_rank"] = min(c["best_rank"], rank)
            c["prelim"] += 1.0 / (rank ** ZIPF)
            if len(c["probes"]) < 3:
                c["probes"].append(probe)
    for c in cands.values():
        c["type"] = classify(c["keyword"], seed)
    return cands


def related_competition(candidate: str, serp: List[Dict[str, Any]], seed_comp: Dict[str, Any]) -> Optional[float]:
    """Rough competition estimate for a related keyword, reusing the seed's search results:
    authority of the niche's ranking channels + how saturated the seed results are with the phrase."""
    if not serp or not seed_comp:
        return None
    toks = {singular(t) for t in content_tokens(candidate)}
    if not toks:
        return None
    sat = sum(1 for v in serp if toks <= token_set(v["title"] + " " + " ".join(v.get("tags") or []))) / len(serp)
    comp = seed_comp["components"]
    authority = (comp["channel_authority"] + comp["result_strength"] + comp["big_channel_share"]) / 300.0
    return round(100 * (0.5 * min(1.0, sat / 0.5) + 0.5 * authority), 1)


# ---- main entry point ----------------------------------------------------------------------------

def research(app, keyword: str, *, fmt: str = "any", region: Optional[str] = None,
             language: Optional[str] = None, deep: bool = True, use_api: bool = True,
             related_limit: int = 60) -> Dict[str, Any]:
    seed = normalize_keyword(keyword)
    if not seed:
        raise ValueError("Enter a keyword.")
    region = (region or app.region).upper()
    language = (language or app.language).lower()
    sug = app.suggest(language, region)
    budget = Budget(int(app.settings.get("autocomplete_budget") or 90))
    started = time.time()

    probe_results = sug.many(expansion_probes(seed, deep), budget)
    seed_vol = estimate_volume(seed, sug, budget)
    cands = gather_candidates(seed, probe_results)

    yt = app.youtube()
    serp: Optional[Dict[str, Any]] = None
    competition = None
    insights = None
    api_error = None
    if use_api and yt.enabled:
        try:
            serp = analyze_serp(yt, seed, region=region, language=language)
            competition = competition_from_serp(seed, serp["videos"])
            insights = serp_insights(seed, serp["videos"])
        except Exception as err:  # keep autocomplete results even if the API fails
            api_error = str(err)

    # Candidates from the ranking videos' tags / titles (semantic neighbours autocomplete misses)
    common_tags: List[Tuple[str, int]] = []
    title_phrases: List[Tuple[str, int]] = []
    if serp and serp["videos"]:
        tag_counter: Dict[str, int] = {}
        channel_names = {v["channel_title"].lower() for v in serp["videos"]}
        for v in serp["videos"][:30]:
            for t in {t.lower().strip() for t in v.get("tags") or []}:
                if 2 < len(t) <= 60 and t not in channel_names:
                    tag_counter[t] = tag_counter.get(t, 0) + 1
        common_tags = sorted(((t, c) for t, c in tag_counter.items() if c >= 2), key=lambda kv: (-kv[1], kv[0]))[:30]
        title_phrases = top_phrases([v["title"] for v in serp["videos"][:30]], limit=15)
        for tag, count in common_tags[:15]:
            if count >= 2 and tag != seed and tag not in cands:
                cands[tag] = {"keyword": tag, "hits": 0, "best_rank": 10, "prelim": 0.25 * count,
                              "probes": ["top video tags"], "type": classify(tag, seed)}

    ranked = sorted(cands.values(), key=lambda c: -c["prelim"])[:related_limit]

    def _est(c: Dict[str, Any]) -> Dict[str, Any]:
        v = estimate_volume(c["keyword"], sug, budget, known_query=c["hits"] > 0)
        return {**c, "volume": v["score"], "monthly": v["monthly"], "band": v.get("band"), "approx": v["approx"]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(_est, ranked))

    # Blend autocomplete volume with demand seen in the ranking videos (views/day), when available.
    volume = seed_vol["score"]
    if insights and insights.get("demand_score") is not None and volume is not None:
        volume = round(0.75 * volume + 0.25 * insights["demand_score"], 1)
    elif volume is None and insights:
        volume = insights.get("demand_score")
    comp_score = competition["score"] if competition else None
    overall = overall_score(volume, comp_score)

    serp_videos = serp["videos"] if serp else []
    for r in rows:
        r["competition"] = related_competition(r["keyword"], serp_videos, competition) if competition else None
        r["overall"] = overall_score(r["volume"], r["competition"])
        r.pop("prelim", None)

    def _sort_key(r: Dict[str, Any]) -> Tuple[float, float]:
        return (-(r["overall"] if r["overall"] is not None else -1), -(r["volume"] or 0))

    questions = sorted([r for r in rows if r["type"] == "question"], key=_sort_key)
    matching = sorted([r for r in rows if r["type"] == "matching"], key=_sort_key)
    related = sorted([r for r in rows if r["type"] == "related"], key=_sort_key)

    top_videos = []
    for v in serp_videos[:25]:
        top_videos.append({k: v.get(k) for k in (
            "id", "rank", "title", "channel_title", "channel_id", "channel_subs", "views", "likes", "comments",
            "published_at", "age_days", "vph", "is_short", "duration", "thumbnail", "url", "keyword_in_title",
            "engagement_rate", "views_per_sub")})
        top_videos[-1]["tag_count"] = len(v.get("tags") or [])

    result = {
        "keyword": seed,
        "region": region,
        "language": language,
        "format": fmt,
        "scores": {
            "volume": volume,
            "competition": comp_score,
            "overall": overall,
            "autocomplete_volume": seed_vol["score"],
            "demand": insights.get("demand_score") if insights else None,
        },
        "search_volume": {
            "monthly_estimate": seed_vol["monthly"],
            "band": seed_vol.get("band", "Unknown"),
            "approx": seed_vol["approx"],
            "hit": seed_vol["hit"],
            "path": seed_vol["path"],
        },
        "competition": competition,
        "insights": insights,
        "related": related[:30],
        "matching": matching[:30],
        "questions": questions[:20],
        "top_videos": top_videos,
        "common_tags": [{"tag": t, "count": c} for t, c in common_tags],
        "title_phrases": [{"phrase": p, "count": c} for p, c in title_phrases],
        "api_used": bool(serp),
        "api_error": api_error,
        "quota_units": yt.units_this_request,
        "autocomplete_requests": budget.used,
        "elapsed_s": round(time.time() - started, 2),
    }
    app.db.add_history("keyword", seed, {"volume": volume, "competition": comp_score, "overall": overall})
    return result


def quick_score(app, keyword: str, *, region: Optional[str] = None, language: Optional[str] = None,
                with_competition: bool = False) -> Dict[str, Any]:
    """Cheap volume-only (or volume + competition) score, used for tags and the browser extension."""
    seed = normalize_keyword(keyword)
    sug = app.suggest(language, region)
    vol = estimate_volume(seed, sug, Budget(25))
    out = {"keyword": seed, "volume": vol["score"], "monthly": vol["monthly"], "band": vol.get("band"),
           "competition": None, "overall": None}
    if with_competition and app.has_youtube_key:
        yt = app.youtube()
        serp = analyze_serp(yt, seed, region=(region or app.region), language=(language or app.language))
        comp = competition_from_serp(seed, serp["videos"])
        ins = serp_insights(seed, serp["videos"])
        v = vol["score"]
        if v is not None and ins.get("demand_score") is not None:
            v = round(0.75 * v + 0.25 * ins["demand_score"], 1)
        out.update(volume=v, competition=comp["score"] if comp else None,
                   overall=overall_score(v, comp["score"] if comp else None), quota_units=yt.units_this_request)
    return out

