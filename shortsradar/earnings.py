"""Ad-revenue estimates: category RPM x audience-country multiplier, with a much lower Shorts RPM.

RPM = what the creator earns per 1,000 views after YouTube's share. Figures are typical public
ranges for monetised channels (2024-2026); real RPMs vary widely with audience, season and ad
demand, so results are shown as a low / mid / high range.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Long-form creator RPM in USD for a US audience: (low, mid, high)
CATEGORY_RPM = {
    "Finance": (8.0, 13.0, 25.0),
    "Business": (6.0, 10.0, 18.0),
    "Technology": (4.0, 6.5, 12.0),
    "Education": (4.0, 6.0, 10.0),
    "Health": (3.5, 5.5, 9.0),
    "Autos-&-Vehicles": (3.5, 5.5, 9.0),
    "Travel": (2.5, 4.0, 7.0),
    "Food": (2.5, 4.0, 6.5),
    "Lifestyle": (2.0, 3.5, 6.0),
    "Sports": (2.0, 3.2, 5.5),
    "News-&-Politics": (2.0, 3.0, 5.0),
    "Science": (3.0, 5.0, 8.0),
    "Pets-&-Animals": (1.5, 2.6, 4.5),
    "Entertainment": (1.5, 2.5, 4.5),
    "Gaming": (1.2, 2.3, 4.0),
    "Comedy": (1.2, 2.2, 4.0),
    "Religion": (1.0, 1.8, 3.0),
    "Music": (0.8, 1.4, 2.5),
    "Kids": (0.5, 1.0, 2.0),
}
# Shorts ad-revenue-share creator RPM (USD, US audience): (low, mid, high)
SHORTS_RPM = (0.02, 0.06, 0.12)
SHORTS_CATEGORY_FACTOR = {"Finance": 1.6, "Business": 1.4, "Technology": 1.3, "Education": 1.2, "Music": 0.7,
                          "Kids": 0.6, "Gaming": 0.9}

# Relative ad value of an audience vs the US (1.0).
COUNTRY_MULTIPLIER = {
    "US": 1.0, "AU": 0.9, "CA": 0.85, "NO": 0.95, "CH": 0.95, "GB": 0.8, "DE": 0.8, "DK": 0.8, "NZ": 0.75,
    "NL": 0.75, "SE": 0.75, "IE": 0.7, "AT": 0.7, "FI": 0.7, "BE": 0.65, "FR": 0.6, "JP": 0.6, "SG": 0.6,
    "KR": 0.55, "AE": 0.5, "IL": 0.5, "IT": 0.45, "ES": 0.45, "HK": 0.5, "TW": 0.4, "SA": 0.4, "QA": 0.45,
    "PL": 0.35, "CZ": 0.35, "PT": 0.35, "GR": 0.3, "ZA": 0.3, "CL": 0.3, "MY": 0.25, "BR": 0.25, "MX": 0.25,
    "AR": 0.15, "CO": 0.2, "TR": 0.15, "RU": 0.15, "UA": 0.12, "TH": 0.2, "RO": 0.25, "HU": 0.25,
    "IN": 0.12, "ID": 0.12, "PH": 0.12, "VN": 0.1, "PK": 0.08, "BD": 0.07, "NG": 0.1, "EG": 0.1, "KE": 0.1,
}
DEFAULT_COUNTRY_MULTIPLIER = 0.3

# YouTube category id -> our RPM category
YT_CATEGORY = {
    "1": "Entertainment", "2": "Autos-&-Vehicles", "10": "Music", "15": "Pets-&-Animals", "17": "Sports",
    "19": "Travel", "20": "Gaming", "22": "Lifestyle", "23": "Comedy", "24": "Entertainment",
    "25": "News-&-Politics", "26": "Lifestyle", "27": "Education", "28": "Technology", "29": "Lifestyle",
    "30": "Entertainment", "43": "Entertainment", "44": "Entertainment",
}


def category_from_youtube(category_id: Optional[str]) -> str:
    return YT_CATEGORY.get(str(category_id or ""), "Entertainment")


def rpm(category: str, country: str = "US", fmt: str = "long") -> Dict[str, float]:
    mult = COUNTRY_MULTIPLIER.get((country or "US").upper(), DEFAULT_COUNTRY_MULTIPLIER)
    if fmt == "short":
        f = SHORTS_CATEGORY_FACTOR.get(category, 1.0)
        # Shorts revenue is pooled and less geo-sensitive than long-form ads.
        geo = 0.5 + 0.5 * mult
        lo, mid, hi = (x * f * geo for x in SHORTS_RPM)
    else:
        lo, mid, hi = (x * mult for x in CATEGORY_RPM.get(category, CATEGORY_RPM["Entertainment"]))
    return {"low": round(lo, 3), "mid": round(mid, 3), "high": round(hi, 3)}


def estimate(views: float, *, category: str = "Entertainment", country: str = "US", fmt: str = "long",
             shorts_share: Optional[float] = None) -> Dict[str, Any]:
    """Estimated earnings for a number of views. For a channel mix pass shorts_share (0..1)."""
    views = max(0.0, float(views or 0))
    if shorts_share is not None:
        share = min(1.0, max(0.0, shorts_share))
        r_long = rpm(category, country, "long")
        r_short = rpm(category, country, "short")
        blended = {k: r_long[k] * (1 - share) + r_short[k] * share for k in ("low", "mid", "high")}
    else:
        blended = rpm(category, country, fmt)
    return {
        "views": int(views),
        "rpm": {k: round(v, 3) for k, v in blended.items()},
        "earnings": {k: round(views / 1000.0 * v, 2) for k, v in blended.items()},
        "category": category,
        "country": (country or "US").upper(),
        "format": "mix" if shorts_share is not None else fmt,
        "note": "Estimate for a monetised channel (YouTube Partner Program). Real RPM varies by audience, "
                "season and advertiser demand.",
    }


def calculator(monthly_views: float, *, category: str = "Entertainment", country: str = "US",
               fmt: str = "long", shorts_share: Optional[float] = None) -> Dict[str, Any]:
    month = estimate(monthly_views, category=category, country=country, fmt=fmt, shorts_share=shorts_share)
    month["yearly"] = {k: round(v * 12, 2) for k, v in month["earnings"].items()}
    month["daily"] = {k: round(v / 30.0, 2) for k, v in month["earnings"].items()}
    return month


CATEGORIES = sorted(CATEGORY_RPM)
