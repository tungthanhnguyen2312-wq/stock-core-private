"""Materialize the retained 2026-08-24 same-session technical coverage disposition ledger."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from same_session_technical_coverage_disposition import build

OPS = ROOT / "operations-review"
OUT = OPS / "same-session-technical-coverage-recovery-v1-20260824" / "same_session_technical_coverage_disposition_artifact.json"


def _load(relative: str) -> dict:
    return json.loads((OPS / relative).read_text(encoding="utf-8"))


def main() -> None:
    artifact = build(
        descriptive=_load("market-wide-current-descriptive-research-v1-20260824/market_wide_current_descriptive_research_artifact.json"),
        official_universe=_load("current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json"),
        p3f9b_snapshot=_load("p3f9b-market-wide-exact-session-scaleout-20260824/p3f9b_mva_exact_session_snapshot.json"),
        universe_status=_load("current-universe-status-and-session-coverage-resolution-v1-20260824/current_universe_status_and_session_coverage_resolution_artifact.json"),
        tactical=_load("watchlist-tactical-entry-decision-v1-20260824/watchlist_tactical_entry_classifier_artifact.json"),
        recovery=_load("market-wide-current-technical-coverage-scaleout-v1-20260824/market_wide_current_technical_coverage_recovery_artifact.json"),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_COVERAGE_DISPOSITION_CONTENT_CONFLICT")
    OUT.write_text(payload, encoding="utf-8")
    print(artifact["artifact_identity"])
    print(OUT)


if __name__ == "__main__":
    main()
