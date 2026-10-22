#!/usr/bin/env python3
"""Contract cage CLI (human entry point).

The authoritative G3 gate is `python3 -m pytest tests/contracts -q`.
This script shares the same validation kernel and exists for fast manual checks:

  python3 scripts/validate.py --all
  python3 scripts/validate.py spec_pro
  python3 scripts/validate.py --list
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.cage.active_contracts import main as _main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(_main())
