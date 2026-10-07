"""Run the bounded Cohort-1 official financial currency refresh.

Default is network-off (framework/report only).  Pass --allow-network to spend
the remaining HTTP budget against admitted issuer-IR hosts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT, PUBLIC_ARTIFACT_DIR  # noqa: E402
from financial_evidence_currency_refresh import run_refresh  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-ocr", action="store_true")
    parser.add_argument("--refresh-indexes", action="store_true",
                        help="Recheck approved index pages; preserve cached PDF bytes and original observation times")
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    args = parser.parse_args(argv)
    report = run_refresh(
        landing_root=args.landing_root, public_root=args.public_root,
        allow_network=args.allow_network, allow_ocr=args.allow_ocr,
        refresh_indexes=args.refresh_indexes,
    )
    print(json.dumps({
        "http_requests": report["http_requests"],
        "documents_retained": report["documents_retained"],
        "new_qualified_core_fact_count": report["new_qualified_core_fact_count"],
        "tickers_with_ge1_new_qualified_core_fact": report["tickers_with_ge1_new_qualified_core_fact"],
        "financial_v2_pin": report["financial_v2_pin"],
        "stopped_reason": report["stopped_reason"],
        "implementation_success_gate": report["implementation_success_gate"],
        "artifact_identity": report["artifact_identity"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
