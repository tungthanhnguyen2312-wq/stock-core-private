"""Replay the fixed reviewed-H1 report and statement pages after zero-candidate native extraction."""
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
DOCUMENTS = ({"ticker": "NVL", "sha256": "20aa7254735542d470f12ada8d02786dfa5e673035274e42d3404352e266a007", "pages": tuple(range(8, 15))},)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landing-root", type=Path, default=Path(r"C:\Projects\StockLookup\data-landing\official-financial-filings-v1"))
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_ARTIFACT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = run(landing_root=args.landing_root, document_specs=DOCUMENTS,
                 reporting_period="2026-H1", allow_unqualified_native_fallback=True,
                 evidence_subdir="nvl-reviewed-evidence-20261008", front_matter_pages=(6, 7))
    if args.write:
        write_outputs(result, args.public_root, preserve_other_documents=True,
                      append_new_facts_only=True, report_name="nvl_reviewed_h1_ingress_report.json")
    print(json.dumps(result["report"], ensure_ascii=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
