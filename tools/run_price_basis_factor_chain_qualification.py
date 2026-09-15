"""Demonstrate PRICE_BASIS_FACTOR_CHAIN_AND_PIT_SERIES_QUALIFICATION_V1 against real retained
evidence and a bounded synthetic-mechanics fixture, and write one deterministic gap-table
artifact.

WHAT THIS SCRIPT DOES
    1. Classifies real, retained official corporate-event evidence
       (operations-review/current-official-event-context-integration-v1-20260824/
       current_official_event_context_artifact.json -- the real HNX official rights-event
       index) against the six-bucket factor-chain taxonomy, using only that source's own real
       field values. It does not feed this data through official_corporate_action_ledger.py --
       that source carries no stock_ratio/executed-lifecycle evidence, so it is structurally
       out of that module's schema, and this script says so rather than inventing a bridge.
    2. Builds a small, clearly-labelled SYNTHETIC ledger cohort (ticker "TST*") through the real
       official_corporate_action_ledger.py + qualified_corporate_action_factor_chain.py pipeline
       to prove the positive QUALIFIED mechanics work end-to-end -- something the real corpus in
       this repository cannot currently demonstrate on its own.
    3. Demonstrates pit_price_series_qualification.py against DNSE's real, bounded
       ADJUSTED_RETROSPECTIVE authority windows (HPG/VCB) combined with the synthetic qualified
       factor chain, plus a real-scope-boundary BLOCKED control (a ticker outside DNSE's bounded
       windows).
    4. Runs price_basis_feature_fitness.evaluate_feature_fitness() for every required use case
       (MA, RSI, MOMENTUM_RETURN, LOCAL_PRICE_ACTION, PIT_BACKTEST, EXECUTION_RAW_REPLAY) against
       both the real-evidence-blocked context and the synthetic-qualified PIT context.
    5. Writes one deterministic JSON artifact under
       operations-review/price-basis-factor-chain-and-pit-series-qualification-v1-20260915/.

This script performs no network or provider call and writes only under operations-review/; it
never touches data/official-evidence/ or any Daily/production runtime path.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import official_corporate_action_ledger as ledger  # noqa: E402
import pit_price_series_qualification as pit  # noqa: E402
import price_basis_feature_fitness as fitness  # noqa: E402
import provider_price_basis_registry as basis_registry  # noqa: E402
import qualified_corporate_action_factor_chain as factor_chain  # noqa: E402

REAL_EVENT_CONTEXT_ARTIFACT = (
    REPO_ROOT / "operations-review" / "current-official-event-context-integration-v1-20260824"
    / "current_official_event_context_artifact.json"
)
GAP_TABLE_OUTPUT_DIR = (
    REPO_ROOT / "operations-review" / "price-basis-factor-chain-and-pit-series-qualification-v1-20260915"
)
GAP_TABLE_OUTPUT_FILE = GAP_TABLE_OUTPUT_DIR / "price_basis_factor_chain_and_pit_series_qualification_gap_table_20260915.json"

SHARE_AFFECTING_EVENT_TYPES = ("STOCK_DIVIDEND", "BONUS", "RIGHTS")


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 1. Real evidence: HNX official rights-event index (real, retained, ratio-less)
# ---------------------------------------------------------------------------

def classify_real_official_event_index() -> dict:
    if not REAL_EVENT_CONTEXT_ARTIFACT.exists():
        return {
            "source_status": "NOT_PRESENT_IN_THIS_CHECKOUT",
            "source_path": str(REAL_EVENT_CONTEXT_ARTIFACT.relative_to(REPO_ROOT)),
        }
    with REAL_EVENT_CONTEXT_ARTIFACT.open(encoding="utf-8") as handle:
        artifact = json.load(handle)
    records = artifact.get("records") or {}

    total_events = 0
    share_affecting = 0
    with_explicit_ex_date = 0
    missing_ex_date = 0
    with_execution_date = 0
    tickers_with_share_affecting_events = set()
    examples: list[dict] = []
    for ticker, record in records.items():
        for event in record.get("events") or []:
            total_events += 1
            if event.get("event_type") not in SHARE_AFFECTING_EVENT_TYPES:
                continue
            share_affecting += 1
            tickers_with_share_affecting_events.add(ticker)
            if event.get("ex_date"):
                with_explicit_ex_date += 1
            else:
                missing_ex_date += 1
            if event.get("execution_date"):
                with_execution_date += 1
            if len(examples) < 6:
                examples.append({
                    "ticker": ticker,
                    "event_type": event.get("event_type"),
                    "ex_date": event.get("ex_date"),
                    "record_date": event.get("record_date"),
                    "execution_date": event.get("execution_date"),
                    "qualification": event.get("qualification"),
                    "classification": (
                        "MISSING_EXPLICIT_EX_DATE" if not event.get("ex_date")
                        else "OTHER_EVIDENCE_GAP"
                    ),
                    "reason": (
                        "no explicit official ex-date in this source"
                        if not event.get("ex_date") else
                        "source is an event calendar (hnx_official_rights_event_index/v1): it "
                        "retains no stock_ratio/share-count and no ledger-grade executed-lifecycle "
                        "evidence, so no adjustment factor can be computed from it regardless of "
                        "ex-date presence"
                    ),
                })

    return {
        "source_status": "PRESENT_REAL_RETAINED_EVIDENCE",
        "source_path": str(REAL_EVENT_CONTEXT_ARTIFACT.relative_to(REPO_ROOT)),
        "source_contract": "current_official_event_context/v1",
        "underlying_source": "hnx_official_rights_event_index/v1",
        "authority_boundary_declared_by_source": artifact.get("authority_boundary"),
        "total_event_records": total_events,
        "total_tickers": len(records),
        "share_affecting_event_types_scanned": list(SHARE_AFFECTING_EVENT_TYPES),
        "share_affecting_event_count": share_affecting,
        "share_affecting_tickers": len(tickers_with_share_affecting_events),
        "with_explicit_official_ex_date": with_explicit_ex_date,
        "missing_explicit_ex_date": missing_ex_date,
        "with_execution_date_populated": with_execution_date,
        "ledger_grade_ratio_or_share_count_fields_present": False,
        "out_of_official_corporate_action_ledger_schema_scope": True,
        "factor_chain_qualified_count": 0,
        "verdict": (
            "Real, retained official ex-date evidence exists for {0} share-affecting events "
            "across {1} tickers, but this source carries no stock_ratio/share-count and no "
            "ledger-grade executed-lifecycle evidence. Zero of these events can reach "
            "FACTOR_CHAIN_QUALIFIED from this source alone; every one is, at best, "
            "MISSING_EXPLICIT_EX_DATE or OTHER_EVIDENCE_GAP."
        ).format(share_affecting, len(tickers_with_share_affecting_events)),
        "examples": examples,
    }


# ---------------------------------------------------------------------------
# 2. Synthetic mechanics cohort (clearly labelled, ticker "TST*")
# ---------------------------------------------------------------------------

def _synthetic_observation(ticker="TST", event_type="stock_dividend", observation_id="o1",
                           document_id="d1", content_sha256="a" * 64, **overrides):
    record = {
        "observation_id": observation_id, "ticker": ticker, "event_type": event_type,
        "lifecycle_state": "executed", "document_id": document_id, "document_type": "listing_change_notice",
        "source_authority": "HNX", "source_url": "https://www.hnx.vn/synthetic",
        "content_sha256": content_sha256, "announcement_date": "2026-05-10",
        "ex_date": None, "record_date": None, "payment_or_execution_date": "2026-05-20",
        "shares_before": None, "shares_issued": 100_000, "shares_after": 1_100_000,
        "cash_amount_per_share": None, "stock_ratio": 0.1, "ratio_basis": "new_shares_per_existing_share",
        "citations": [], "absent_fields": {}, "warnings": [],
    }
    record.update(overrides)
    return record


def build_synthetic_mechanics_cohort() -> dict:
    observations = [
        _synthetic_observation(ticker="TST_QUALIFIED", ex_date="2026-05-26"),
        _synthetic_observation(ticker="TST_MISSING_EX_DATE", observation_id="o2", document_id="d2",
                               content_sha256="b" * 64, record_date="2026-05-24"),
        _synthetic_observation(ticker="TST_NOT_EXECUTED", observation_id="o3", document_id="d3",
                               content_sha256="c" * 64, ex_date="2026-05-26", lifecycle_state="announced"),
        _synthetic_observation(ticker="TST_FACTOR_NOT_APPLICABLE", observation_id="o4", document_id="d4",
                               content_sha256="d" * 64, event_type="cash_dividend",
                               cash_amount_per_share=1000.0, ex_date="2026-05-26"),
    ]
    conflicting_a = _synthetic_observation(ticker="TST_CONFLICTING", observation_id="o5", document_id="d5",
                                           content_sha256="e" * 64, ex_date="2026-05-26")
    conflicting_b = _synthetic_observation(ticker="TST_CONFLICTING", observation_id="o6", document_id="d6",
                                           content_sha256="f" * 64, shares_after=9_000_000, ex_date="2026-05-26")
    built_ledger = ledger.build_ledger(observations + [conflicting_a, conflicting_b])

    def knowledge_cutoff_resolver(entry):
        # Synthetic mechanics-only publication evidence: qualifying events become knowable the
        # evening before their ex-date under the owner's EOD research convention.
        if entry.get("ex_date"):
            return f"{entry['ex_date']}T00:00:00+00:00", []
        return None, []

    cohort = factor_chain.build_factor_chain_cohort(built_ledger, knowledge_cutoff_resolver=knowledge_cutoff_resolver)
    qualified_entry = next(
        (event["factor_chain"] for event in cohort["events"]
         if event["classification"] == factor_chain.CLASSIFICATION_FACTOR_CHAIN_QUALIFIED), None)
    return {"evidence_type": "SYNTHETIC_FIXTURE_MECHANICS_ONLY_NOT_REAL_EVIDENCE", "cohort": cohort,
            "qualified_entry": qualified_entry}


# ---------------------------------------------------------------------------
# 3. PIT series demonstration (real DNSE bounded windows + synthetic factor chain)
# ---------------------------------------------------------------------------

def demonstrate_pit_series(qualified_entry: dict | None) -> dict:
    demo: dict = {}
    if qualified_entry is not None:
        hpg_entry = dict(qualified_entry)
        hpg_entry["source_event_id"] = "synthetic_demo_event"
        qualified_within_window = pit.qualify_pit_price_series(
            ticker="HPG", provider="DNSE", dataset="ohlc_1D", instrument="HPG",
            sessions=["2026-05-16", "2026-05-17", "2026-05-18"],
            decision_as_of="2026-06-01", factor_chain_entries=[hpg_entry],
        )
        demo["synthetic_qualified_within_dnse_bounded_window"] = qualified_within_window
    unbounded = pit.qualify_pit_price_series(
        ticker="SSI", provider="DNSE", dataset="ohlc_1D", instrument="SSI",
        sessions=["2026-05-16"], decision_as_of="2026-06-01",
    )
    demo["real_dnse_scope_boundary_control_ssi_blocked"] = unbounded
    demo["dnse_active_bounded_authorities"] = list(basis_registry.active_bounded_authorities())
    return demo


# ---------------------------------------------------------------------------
# 4. Feature fitness demonstration
# ---------------------------------------------------------------------------

REQUIRED_FEATURES = (
    fitness.MA20, fitness.RSI, fitness.MOMENTUM_RETURN, fitness.LOCAL_PRICE_ACTION,
    fitness.PIT_BACKTEST, fitness.EXECUTION_RAW_REPLAY,
)


def demonstrate_feature_fitness(qualified_entry: dict | None) -> dict:
    real_blocked_context = fitness.price_series_context(
        ticker="HPG", provider=None, source_identity="market_wide_current_descriptive_research",
        session_start="2026-09-15", session_end="2026-09-15",
        observed_basis="CURRENT_DESCRIPTIVE_NOT_PROMOTED_RAW_AS_TRADED",
        basis_provenance=["market_wide_current_descriptive_research"],
    )
    real_blocked = {
        feature: fitness.evaluate_feature_fitness(feature=feature, current_context=real_blocked_context,
                                                   decision_as_of="2026-09-15")
        for feature in REQUIRED_FEATURES
    }

    # A realistic CURRENT_RETROSPECTIVE_ADJUSTED technical-history context (the basis
    # historical_series_failover.py actually stamps): demonstrates the expected principle --
    # current research stays BASIS_COMPATIBLE_RESEARCH_ONLY while PIT_BACKTEST/EXECUTION_RAW_REPLAY
    # stay blocked, because no factor chain was supplied for it either.
    current_retrospective_context = fitness.price_series_context(
        ticker="HPG", provider="DNSE", source_identity="historical_series_failover_demo",
        session_start="2026-09-01", session_end="2026-09-15",
        observed_basis=fitness.CURRENT_RETROSPECTIVE_ADJUSTED,
        basis_provenance=["historical_series_failover_demo"],
    )
    current_retrospective = {
        feature: fitness.evaluate_feature_fitness(feature=feature, current_context=current_retrospective_context,
                                                   decision_as_of="2026-09-15")
        for feature in REQUIRED_FEATURES
    }

    synthetic_pit_results: dict = {}
    if qualified_entry is not None:
        synthetic_entry = dict(qualified_entry)
        synthetic_entry["source_event_id"] = "synthetic_demo_event"
        series = pit.qualify_pit_price_series(
            ticker="HPG", provider="DNSE", dataset="ohlc_1D", instrument="HPG",
            sessions=["2026-05-16", "2026-05-17"], decision_as_of="2026-06-01",
            factor_chain_entries=[synthetic_entry],
        )
        pit_context = pit.price_series_context_for_pit(
            ticker="HPG", provider="DNSE", source_identity="synthetic_demo_series",
            session_start="2026-05-16", session_end="2026-05-17",
            series_qualification=series, factor_chain_entry=synthetic_entry,
        )
        synthetic_pit_results = {
            feature: fitness.evaluate_feature_fitness(feature=feature, current_context=pit_context,
                                                       decision_as_of="2026-06-01")
            for feature in REQUIRED_FEATURES
        }

    return {
        "real_evidence_blocked_context": {
            "context": real_blocked_context,
            "fitness": {feature: verdict["state"] for feature, verdict in real_blocked.items()},
            "full_verdicts": real_blocked,
        },
        "current_retrospective_adjusted_research_only_context": {
            "context": current_retrospective_context,
            "fitness": {feature: verdict["state"] for feature, verdict in current_retrospective.items()},
            "full_verdicts": current_retrospective,
        },
        "synthetic_fully_qualified_pit_context": {
            "evidence_type": "SYNTHETIC_FIXTURE_MECHANICS_ONLY_NOT_REAL_EVIDENCE",
            "fitness": {feature: verdict["state"] for feature, verdict in synthetic_pit_results.items()},
            "full_verdicts": synthetic_pit_results,
        } if synthetic_pit_results else None,
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_gap_table() -> dict:
    real_evidence = classify_real_official_event_index()
    synthetic = build_synthetic_mechanics_cohort()
    pit_demo = demonstrate_pit_series(synthetic.get("qualified_entry"))
    fitness_demo = demonstrate_feature_fitness(synthetic.get("qualified_entry"))

    artifact = {
        "contract_version": "price_basis_factor_chain_and_pit_series_qualification_gap_table/v1",
        "schema_version": "1.0.0",
        "milestone": "PRICE_BASIS_FACTOR_CHAIN_AND_PIT_SERIES_QUALIFICATION_V1",
        "session": "2026-09-15",
        "authority_boundary": {
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_PROMOTED_MARKET_WIDE_BOUNDED_MECHANICS_ONLY",
            "record_date_inferred_as_ex_date": False,
            "planned_issuance_treated_as_executed": False,
            "provider_or_network_calls": False,
            "runtime_root_written": False,
            "daily_or_canonical_classifications_modified": False,
        },
        "real_official_event_index_evidence": real_evidence,
        "synthetic_mechanics_cohort": synthetic,
        "pit_series_demonstration": pit_demo,
        "feature_fitness_demonstration": fitness_demo,
        "contract_summaries": {
            "qualified_corporate_action_factor_chain": factor_chain.contract_summary(),
            "pit_price_series_qualification": pit.contract_summary(),
            "price_basis_feature_fitness": fitness.contract_summary(),
        },
    }
    artifact["artifact_sha256"] = _sha256(artifact)
    artifact["artifact_identity"] = "price_basis_factor_chain_and_pit_series_qualification_gap_table:" + artifact["artifact_sha256"]
    return artifact


def main() -> None:
    artifact = build_gap_table()
    GAP_TABLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with GAP_TABLE_OUTPUT_FILE.open("w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    print(f"Wrote {GAP_TABLE_OUTPUT_FILE.relative_to(REPO_ROOT)}")
    print(f"artifact_identity: {artifact['artifact_identity']}")
    real = artifact["real_official_event_index_evidence"]
    print(f"real share-affecting events: {real.get('share_affecting_event_count')}, "
          f"factor_chain_qualified: {real.get('factor_chain_qualified_count')}")
    print(f"synthetic cohort classification_counts: "
          f"{artifact['synthetic_mechanics_cohort']['cohort']['classification_counts']}")


if __name__ == "__main__":
    main()
