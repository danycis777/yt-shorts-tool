"""Small numeric helpers shared by the analysis modules."""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def median(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def percentile(values: Iterable[Optional[float]], p: float) -> Optional[float]:
    """Linear-interpolated percentile, p in [0, 100]."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return float(vals[0])
    k = (len(vals) - 1) * clamp(p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return float(vals[int(k)])
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def stdev(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def log_scale(x: Optional[float], lo: float, hi: float) -> float:
    """Map x onto 0..1 using log10 between lo and hi (both > 0)."""
    if x is None or x <= 0:
        return 0.0
    return clamp((math.log10(x) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or not b:
        return None
    return a / b


def round_or_none(x: Optional[float], digits: int = 2) -> Optional[float]:
    return None if x is None else round(x, digits)


def geometric_blend(a: float, b: float, weight_a: float) -> float:
    """Weighted geometric mean of two 0..1 values."""
    a, b = clamp(a), clamp(b)
    if a <= 0 or b <= 0:
        return 0.0
    return math.exp(weight_a * math.log(a) + (1 - weight_a) * math.log(b))


def ranks(values: List[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    for rank, idx in enumerate(order):
        out[idx] = rank / max(1, len(values) - 1)
    return out
