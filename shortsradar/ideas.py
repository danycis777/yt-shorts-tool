"""Daily video ideas from what is over-performing in your niches right now (+ keyword gaps)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from .keywords import estimate_volume, expansion_probes, gather_candidates
from .outliers import find_outliers
from .suggest import Budget
from .textutil import normalize_keyword, smart_title


def daily_ideas(app, niches: Optional[List[str]] = None, *, fmt: str = "short", refresh: bool = False,
                max_niches: int = 3) -> Dict[str, Any]:
    niches = [normalize_keyword(n) for n in (niches or app.settings.get("niche_keywords") or []) if n.strip()]
    if not niches:
        raise ValueError("Add your niche keywords (Settings → Niche keywords, or type them here).")
    niches = niches[:max_niches]
    today = dt.date.today().isoformat()
    key = f"ideas:{today}:{fmt}:{'|'.join(niches)}"
    if not refresh:
        cached = app.db.cache_get(key)
        if cached:
            cached["cached"] = True
            return cached
    ideas: List[Dict[str, Any]] = []
    units = 0
    errors = []
    if app.has_youtube_key:
        for niche in niches:
            try:
                res = find_outliers(app, keyword=niche, fmt=fmt, within="month", limit=20)
            except Exception as err:
                errors.append(f"{niche}: {err}")
                continue
            units += res["quota_units"]
            for v in res["results"]:
                if (v.get("outlier_score") or 0) < 2:
                    continue
                ideas.append({
                    "type": "outlier",
                    "niche": niche,
                    "idea": f"Your own take on “{v['title']}”",
                    "why": f"{v['outlier_score']:.1f}× the channel's usual views · {v['views']:,} views · "
                           f"{(v['vph'] or 0):,.0f} views/hour",
                    "score": min(100, round(40 + 12 * min(v["outlier_score"], 5))),
                    "video": v,
                })
    sug = app.suggest()
    budget = Budget(60)
    for niche in niches:
        results = sug.many(expansion_probes(niche, deep=False), budget)
        cands = sorted(gather_candidates(niche, results).values(), key=lambda c: -c["prelim"])
        picked = 0
        for c in cands:
            if picked >= 5:
                break
            if c["type"] == "related":
                continue
            vol = estimate_volume(c["keyword"], sug, budget, known_query=True)
            if (vol["score"] or 0) < 30:
                continue
            picked += 1
            verb = "Answer" if c["type"] == "question" else "Target"
            ideas.append({
                "type": "search",
                "niche": niche,
                "idea": f"{verb} the search “{c['keyword']}”",
                "why": f"People search this on YouTube (~{vol['monthly']:,}/month, {vol['band'].lower()} volume)",
                "score": round(vol["score"] or 0),
                "keyword": c["keyword"],
            })
    ideas.sort(key=lambda i: -i["score"])
    out = {"date": today, "niches": niches, "format": fmt, "ideas": ideas[:40], "quota_units": units,
           "errors": errors, "cached": False}
    app.db.cache_set(key, out, 20 * 3600)
    return out


def search_gap_ideas(app, niche: str, *, fmt: str = "short", limit: int = 12) -> List[Dict[str, Any]]:
    """Offline (no API key) idea list: real YouTube searches in the niche turned into video concepts."""
    niche = normalize_keyword(niche)
    sug = app.suggest()
    budget = Budget(50)
    results = sug.many(expansion_probes(niche, deep=True), budget)
    cands = sorted(gather_candidates(niche, results).values(), key=lambda c: -c["prelim"])
    out: List[Dict[str, Any]] = []
    for c in cands:
        if len(out) >= limit:
            break
        kw = c["keyword"]
        if c["type"] == "question":
            title = kw[:1].upper() + kw[1:] + ("" if kw.endswith("?") else "?")
            hook = f"Here's the real answer to '{kw}' in {'30 seconds' if fmt == 'short' else '5 minutes'}."
            concept = f"Answer the exact question people type into YouTube: {kw}."
        else:
            title = smart_title(kw) + (" in 60 Seconds" if fmt == "short" else ": What Nobody Tells You")
            hook = f"If you're into {kw}, you need to see this."
            concept = f"A focused video on '{kw}', a phrase people actively search for."
        out.append({"title": title, "hook": hook, "concept": concept,
                    "why": f"Real YouTube search (autocomplete rank #{c['best_rank']})", "keyword": kw})
    return out
