"""Qualify the three retained FY2025 campaign filings; no acquisition or valuation writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT, PUBLIC_ARTIFACT_DIR
from tools.run_reviewed_interim_canonical_ingress import run, write_outputs

DOCUMENTS = (
    {"ticker": "HPG", "sha256": "f38c5f75becf7d3f145d27183eec81f119fd4f75e378b983a2763ddc3f7e0c07", "pages": (7, 8, 9, 10, 11, 12)},
    {"ticker": "PNJ", "sha256": "309f86836d9f00b37e3cccb25da9e7ffd0dab6c531be995618542004acccdf1d", "pages": (7, 8, 9, 10, 11)},
    {"ticker": "PVD", "sha256": "6ee20a554891c449a8ee72fffe6358bc9b32145d066a7e52d8492d88f305139c", "pages": (7, 8, 9, 10)},
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(DEFAULT_LANDING_ROOT))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--tickers", nargs="+", choices=[doc["ticker"] for doc in DOCUMENTS])
    parser.add_argument("--report-name", default="audited_annual_context_report.json")
    parser.add_argument("--resolve-cash-flow-code-cells", action="store_true")
    parser.add_argument("--append-new-facts-only", action="store_true")
    args = parser.parse_args()
    selected = tuple(doc for doc in DOCUMENTS if not args.tickers or doc["ticker"] in args.tickers)
    if Path(args.report_name).name != args.report_name:
        raise ValueError("REPORT_NAME_MUST_BE_BASENAME")
    result = run(landing_root=args.landing_root, document_specs=selected,
                 reporting_period="2025", allow_audited_annual_context=True,
                 resolve_cash_flow_code_cells=args.resolve_cash_flow_code_cells)
    if args.write:
        write_outputs(result, args.public_root, preserve_other_documents=True,
                      report_name=args.report_name, append_new_facts_only=args.append_new_facts_only)
    # Source-token text can contain Vietnamese glyphs; escaped JSON also works
    # under the Windows console's legacy encoding without losing those tokens.
    print(json.dumps(result["report"], ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
