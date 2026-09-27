#!/usr/bin/env python3
"""Re-check the search-volume model against reference keywords using LIVE YouTube autocomplete.

    python scripts/calibrate_volume.py [scripts/calibration_keywords.csv]

Each CSV row is `keyword,approximate monthly YouTube searches`. Prints each estimate, the log10
error, and the pairwise ordering agreement (the share of keyword pairs the model ranks in the same
order as the reference). The reference numbers are rough public estimates, so focus on ordering.
"""
import math
import statistics
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shortsradar.context import App  # noqa: E402
from shortsradar.keywords import estimate_volume  # noqa: E402


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("calibration_keywords.csv"))
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        kw, ref = line.rsplit(",", 1)
        rows.append((kw.strip(), float(ref)))
    sug = App().suggest("en", "US")
    results = []
    for kw, ref in rows:
        est = estimate_volume(kw, sug)
        results.append((est, kw, ref))
    errs = []
    for est, kw, ref in sorted(results, key=lambda r: -(r[0]["log"] or -9)):
        err = (est["log"] - math.log10(ref)) if ref > 0 else float("nan")
        if ref > 0:
            errs.append(err)
        print(f"{est['score']:5.1f}  ~{est['monthly']:>11,}/mo  ref ~{ref:>11,.0f}  err {err:+.2f}  {kw}")
    pairs = [(a, b) for a, b in combinations(results, 2) if a[2] > 0 and b[2] > 0 and a[2] != b[2]]
    agree = sum(1 for a, b in pairs if (a[0]["log"] - b[0]["log"]) * (a[2] - b[2]) > 0) / max(1, len(pairs))
    print(f"\nmean log10 error {statistics.mean(errs):+.2f} · stdev {statistics.pstdev(errs):.2f} · "
          f"pairwise ordering agreement {agree:.1%} · autocomplete requests {sug.network_calls}")


if __name__ == "__main__":
    main()
