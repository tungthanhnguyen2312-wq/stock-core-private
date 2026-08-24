"""Extract one deterministic row from ai_research_full_universe.ndjson."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract one ticker from the AI full-universe delivery companion.")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    ticker = args.ticker.strip().upper()
    for line in args.bundle.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("ticker") == ticker:
            args.output.write_text(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            print(args.output)
            return
    raise SystemExit(f"TICKER_NOT_FOUND:{ticker}")


if __name__ == "__main__":
    main()
