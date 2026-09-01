"""Retain explicitly requested VCI financial statements; dry-run never writes."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from vci_financial_statement_retention import FAMILIES, FREQUENCIES, retain_statement

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--ticker", action="append", required=True)
    parser.add_argument("--family", action="append", choices=FAMILIES, default=None)
    parser.add_argument("--frequency", action="append", choices=FREQUENCIES, default=None)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    results = [retain_statement(args.runtime_root, ticker, family, frequency, execute=args.execute)
               for ticker in sorted({item.upper() for item in args.ticker})
               for family in (args.family or FAMILIES) for frequency in (args.frequency or FREQUENCIES)]
    print(json.dumps({"executed": args.execute, "results": results}, ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
