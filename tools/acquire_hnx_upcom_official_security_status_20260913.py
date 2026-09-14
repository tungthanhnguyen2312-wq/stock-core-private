"""Bounded live HNX/UPCoM official control/trading-status acquisition for one narrow cohort.

Reuses ``hnx_official_issuer_profile_multi_gate.py``'s own ``fetch``/``retain``/``parse_profile``
(and the two normalization helpers this milestone added to it) unchanged -- this is not a new
Security Master or a competing profile parser, only a wider ticker loop over the same primitives
``build()`` already exercises for its 3-ticker gate-unlock sample.

Scope, deliberately bounded (see AGENTS.md acquisition-budget norms and the milestone brief):
    - the exact 50 tickers the retained 2026-09-11 diagnostic classified
      NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW (loaded from retained evidence, never
      hand-maintained here);
    - the 6 residual provider-rejected names (BCG, BCR, DAN, DVT, LTG, VTS), kept in a separate
      cohort and never merged into the 50's denominator.

Each ticker costs at most 2 requests (autocomplete identity lookup + profile page). No disclosure
crawl, no recursive link-following, no other ticker population touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hnx_official_issuer_profile_multi_gate import SEARCH, PROFILE, fetch, retain, parse_profile, _identity

STATUS_PATH = ROOT / "operations-review" / "current-universe-status-and-session-coverage-resolution-v1-20260911" / "current_universe_status_and_session_coverage_resolution_artifact.json"
OUT = ROOT / "operations-review" / "hnx-upcom-official-security-status-enrichment-v1-20260913"
SIX_RESIDUAL = ("BCG", "BCR", "DAN", "DVT", "LTG", "VTS")


def load_50_population() -> list[str]:
    """Deterministic load from retained evidence -- never a hand-maintained ticker list."""
    records = json.loads(STATUS_PATH.read_text(encoding="utf-8"))["records"]
    population = sorted(
        ticker for ticker, record in records.items()
        if record.get("activity_and_session_reason_code") == "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"
    )
    if len(population) != 50:
        raise ValueError(f"EXPECTED_50_NO_BAR_POPULATION_GOT:{len(population)}")
    if set(population) & set(SIX_RESIDUAL):
        raise ValueError("SIX_RESIDUAL_MUST_NOT_OVERLAP_50_POPULATION")
    return population


def acquire_one(ticker: str, *, destination: Path) -> dict:
    """Two bounded requests: autocomplete identity, then the profile page if an exact match exists."""
    search_response = fetch(SEARCH + "?" + urlencode({"pSymbol": ticker}))
    search_capture = retain(response=search_response, destination=destination, ticker=ticker, surface="issuer_search")
    if search_response["http_status"] != 200:
        return {"ticker": ticker, "outcome": "SEARCH_FETCH_FAILED", "captures": [search_capture], "profile": None}
    try:
        rows = json.loads(search_response["data"].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"ticker": ticker, "outcome": "SEARCH_RESPONSE_MALFORMED", "captures": [search_capture], "profile": None}
    exact = [row for row in rows if str(row.get("STOCK_CODE", "")).upper() == ticker]
    if len(exact) != 1:
        return {"ticker": ticker, "outcome": "CURRENT_PROFILE_NOT_FOUND", "captures": [search_capture], "profile": None,
                "search_candidates": [str(row.get("STOCK_CODE")) for row in rows]}
    identity = exact[0]
    profile_response = fetch(PROFILE.format(link=identity["Link_To_Detail"]))
    profile_capture = retain(response=profile_response, destination=destination, ticker=ticker, surface="issuer_profile")
    if profile_response["http_status"] != 200 or profile_response["content_type"] != "text/html":
        return {"ticker": ticker, "outcome": "PROFILE_FETCH_FAILED", "captures": [search_capture, profile_capture], "profile": None}
    profile = parse_profile(profile_response["data"], identity=identity, retention=profile_capture)
    return {"ticker": ticker, "outcome": "CURRENT_PROFILE_FOUND", "captures": [search_capture, profile_capture], "profile": profile}


def main() -> None:
    population_50 = load_50_population()
    results_50 = {ticker: acquire_one(ticker, destination=OUT) for ticker in population_50}
    results_six = {ticker: acquire_one(ticker, destination=OUT) for ticker in SIX_RESIDUAL}

    all_captures = [capture for row in list(results_50.values()) + list(results_six.values()) for capture in row["captures"]]

    artifact = {
        "schema_version": "1.0.0",
        "contract_version": "hnx_upcom_official_security_status/v1",
        "target_session": "2026-09-11",
        "acquired_at_date": "2026-09-13",
        "cohort_50_no_bar": {ticker: {k: v for k, v in row.items() if k != "captures"} for ticker, row in results_50.items()},
        "cohort_six_residual": {ticker: {k: v for k, v in row.items() if k != "captures"} for ticker, row in results_six.items()},
        "captures": all_captures,
        "authority_boundary": {
            "official_exchange_presence": "NOT_REDEFINED_HERE",
            "active_universe_promotion": "NOT_PERFORMED",
            "membership_from_status": "NEVER_INFERRED",
            "note": "official_exchange_presence, official_control_status, official_trading_status, and target_session_observation are kept as four separate dimensions; a security may be officially current-listed, under a control/trading restriction, and have no target-session bar all at once.",
        },
        "network_used": True, "canonical_store_mutated": False, "missing_is_zero": False,
    }
    digest = _identity(artifact)
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = "hnx_upcom_official_security_status:" + digest

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hnx_upcom_official_security_status_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(artifact["artifact_identity"])
    outcome_counts_50 = {}
    for row in results_50.values():
        outcome_counts_50[row["outcome"]] = outcome_counts_50.get(row["outcome"], 0) + 1
    print("50-cohort outcomes:", outcome_counts_50)
    outcome_counts_six = {}
    for row in results_six.values():
        outcome_counts_six[row["outcome"]] = outcome_counts_six.get(row["outcome"], 0) + 1
    print("six-cohort outcomes:", outcome_counts_six)


if __name__ == "__main__":
    main()
