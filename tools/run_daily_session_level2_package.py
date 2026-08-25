"""Foreground operational runner for the Level-2 current-session package.

Preferred post-close command (latest completed trading session, not wall-clock today):

    python tools/run_daily_session_level2_package.py --runtime-root ../dashboard-runtime

Explicit replay remains supported:

    python tools/run_daily_session_level2_package.py --session 2026-08-25 --runtime-root ../dashboard-runtime
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from daily_session_level2_package import main


if __name__ == "__main__":
    raise SystemExit(main())
