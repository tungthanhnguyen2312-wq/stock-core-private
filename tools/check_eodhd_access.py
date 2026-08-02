"""Check secret-safe EODHD access; network use requires explicit --live."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eodhd_access import credential_status, token_for_request
from eodhd_market_data import EodhdQualificationError, qualify_eod_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    args = parser.parse_args(argv)
    status = credential_status()
    if not args.live:
        print(json.dumps(status, sort_keys=True))
        return 0
    token = token_for_request()
    if not token:
        print(json.dumps({**status, "validation_status": "access_not_configured"}, sort_keys=True))
        return 2
    to_date = args.to_date or date.today().isoformat()
    from_date = args.from_date or (date.fromisoformat(to_date) - timedelta(days=10)).isoformat()
    try:
        result = qualify_eod_sample(token, from_date=from_date, to_date=to_date)
    except EodhdQualificationError as exc:
        print(json.dumps({"configured": True, "source": "environment", "validation_status": exc.code,
                          "ticker": exc.symbol}, sort_keys=True))
        return 3
    print(json.dumps({"configured": True, "source": "environment", "validation_status": "qualified",
                      "provider": result["provider"], "canonical_session_date": result["canonical_session_date"],
                      "tickers": [item["ticker"] for item in result["observations"]]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
