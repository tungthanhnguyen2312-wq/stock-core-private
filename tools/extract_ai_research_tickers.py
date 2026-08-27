"""Extract bounded ticker research cards from one exact Daily Producer session."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_research_ticker_extractor import TickerExtractorError, extract_ai_research_tickers, write_packet


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract a bounded AI ticker research packet from one exact Daily Producer session/run. No network, no latest-file inference."
    )
    parser.add_argument("--session", required=True, help="Exact market session YYYY-MM-DD.")
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers, for example HPG,PAN,SSI.")
    parser.add_argument("--run-identity", help="Exact daily_producer_run identity when the session has more than one run.")
    parser.add_argument("--output", type=Path, default=Path("ai_ticker_research_packet.json"))
    parser.add_argument("--root", type=Path, default=ROOT, help="Producer repository root. Defaults to this checkout.")
    args = parser.parse_args()
    try:
        packet = extract_ai_research_tickers(
            args.root,
            session=args.session,
            tickers=args.tickers,
            run_identity=args.run_identity,
        )
    except TickerExtractorError as exc:
        print(f"STATUS: REFUSE_TICKER_EXTRACT")
        print(f"REASON: {exc}")
        raise SystemExit(2)
    output = write_packet(args.output, packet)
    print(f"SESSION: {packet['session']}")
    print(f"RUN_IDENTITY: {packet['run_identity']}")
    print(f"REQUESTED: {','.join(packet['requested_tickers'])}")
    print(f"PRESENT: {','.join(packet['coverage']['present']) or 'none'}")
    print(f"MISSING: {','.join(packet['coverage']['missing']) or 'none'}")
    print(f"OUTPUT: {output}")


if __name__ == "__main__":
    main()
