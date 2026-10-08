"""Replay the two fixed auditor pages and seven FY2025 statement pages for FPT."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from financial_evidence_currency_contract import PUBLIC_ARTIFACT_DIR
from tools.run_reviewed_interim_canonical_ingress import run, write_outputs
DOCUMENTS = ({"ticker": "FPT", "sha256": "bb14bafff1a7849217f34cf4b50e0e3d69d91968f217a66d7c68f07d4c1af284", "pages": tuple(range(8, 15))},)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(r"C:\Projects\StockLookup\data-landing\official-financial-filings-v1"))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = run(landing_root=args.landing_root, document_specs=DOCUMENTS,
                 reporting_period="2025", allow_audited_annual_context=True,
                 evidence_subdir="fpt-evidence-20261008", front_matter_pages=(6, 7))
    if args.write:
        write_outputs(result, args.public_root, preserve_other_documents=True,
                      append_new_facts_only=True, report_name="fpt_annual_provision_component_report.json")
    print(json.dumps(result["report"], ensure_ascii=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
