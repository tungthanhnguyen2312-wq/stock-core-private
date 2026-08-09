"""Read-only Pillar A qualification-promotion report; no runtime artifact is written."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_fact_store import _load_state, read_facts  # noqa: E402
from canonical_financial_qualification_policy import (  # noqa: E402
    candidate_manifest, inventory, load_evidence_index, ticker_frontier,
)
from research_financial_fact_projection import CORPORATE_REQUIRED_METRICS  # noqa: E402
from runtime_paths import RUNTIME_ROOT_ENV, runtime_root  # noqa: E402

DEFAULT_COHORT = ("POW", "SSI", "HPG", "EVF", "PAN", "PNJ", "FPT", "QNS", "VNM", "PVD", "NVL")


def build_report(root: Path, *, focus_tickers: tuple[str, ...] = DEFAULT_COHORT) -> dict:
    state = _load_state(root)
    records = [item for item in state.get("tickers") or [] if isinstance(item, dict)]
    facts_by_ticker = {str(item.get("ticker") or "").upper(): read_facts(root, str(item.get("ticker") or ""))
                       for item in sorted(records, key=lambda item: str(item.get("ticker") or ""))}
    entity_types = {str(item.get("ticker") or "").upper(): str(item.get("issuer_entity_type") or "unknown")
                    for item in records}
    evidence_index = load_evidence_index(root)
    manifest = candidate_manifest(facts_by_ticker, required_metrics=CORPORATE_REQUIRED_METRICS,
                                  entity_types=entity_types, evidence_index=evidence_index)
    production = {}
    for ticker in focus_tickers:
        facts = facts_by_ticker.get(ticker, [])
        production[ticker] = ticker_frontier(ticker, facts, required_metrics=CORPORATE_REQUIRED_METRICS,
                                             entity_type=entity_types.get(ticker), evidence_index=evidence_index)
        production[ticker]["fact_status_counts"] = {
            status: sum(1 for fact in facts if fact.get("status") == status)
            for status in ("qualified", "provider_reported", "partial", "conflicted", "unavailable")
        }
    return {
        "schema_version": "1.0.0", "report_kind": "pillar_a_qualification_candidate_manifest",
        "runtime_root_configured": True, "global_inventory": inventory(
            [fact for facts in facts_by_ticker.values() for fact in facts], evidence_index=evidence_index)["counts"],
        "candidate_manifest": manifest, "production_cohort": production,
        "is_actionable": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Non-runtime report destination")
    parser.add_argument("--focus-tickers", default=",".join(DEFAULT_COHORT))
    args = parser.parse_args()
    if not os.getenv(RUNTIME_ROOT_ENV, "").strip():
        raise ValueError(f"{RUNTIME_ROOT_ENV} is required for runtime data")
    configured = runtime_root()
    focus = tuple(sorted({item.strip().upper() for item in args.focus_tickers.split(",") if item.strip()}))
    report = build_report(configured, focus_tickers=focus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
