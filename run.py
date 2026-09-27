#!/usr/bin/env python3
"""Start ShortsRadar: `python run.py` opens the dashboard in your browser.

Any CLI command works too, e.g. `python run.py keyword "minecraft redstone"` or `python run.py --demo`.
"""
import sys

if sys.version_info < (3, 9):
    sys.exit("ShortsRadar needs Python 3.9 or newer. Download it from https://www.python.org/downloads/")

from shortsradar.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
