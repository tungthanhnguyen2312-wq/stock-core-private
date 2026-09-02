"""Real retained multi-session replay for DAILY_INTEGRATED_DECISION_BRIEF_AND_PROSPECTIVE_FEEDBACK_V1.

Materializes integrated_investment_decision_product/v1 for two real retained sessions (default
2026-08-25 previous / 2026-08-28 current -- the latest pair with a COMPLETE retained upstream
artifact set: descriptive research, P3F9B, tactical classifier, sector leadership, and per-session
valuation all exist for both; 2026-08-26/2026-08-27 are each missing at least one and 2026-08-28 is
not yet registered in config/daily_research_session_input_registry.json's `sessions` ledger -- a
genuine, pre-existing, orthogonal registration gap this replay reports rather than papers over),
writes them at their canonical session-scoped paths under this worktree's own operations-review/
(never the primary checkout -- read-only there), then builds next_session_decision_brief/v2's
registry-free posture_transition plus its registry-backed market_transition/sector_transition
(honestly UNAVAILABLE where the session registration gap blocks them), and finally the full
daily_integrated_decision_brief/v1 artifact end to end.

Financial V2 does not vary session to session in this replay (same simplification the pre-existing
tools/run_integrated_investment_decision_replay.py already makes): it is built once from the shared
retained 2026-08-31 structured-period-semantics + fundamental-feature-store snapshot.

Outputs (under --out-dir):
- REPORT.md
- daily_integrated_decision_brief.json
- watchlist_11_brief.json
- opportunity_sets.json
- decision_transitions.json
- prospective_feedback_status.json
- pnj_transition_replay.json
- daily_pipeline_validation.json
- coverage.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_market_sector_leadership_context as sector_context
import current_research_valuation_context as valuation_context
import daily_integrated_decision_brief as brief_module
import daily_session_level2_package as level2
import entity_classification_contract as entity_classification
import financial_analysis_product_projection as fa_projection
import integrated_decision_prospective_feedback as feedback_bridge
import integrated_investment_decision_product as iidp
import market_structure_breakout_product_projection as msb_proj
import market_wide_financial_analysis_v2_scaleout as fa_scaleout
import market_wide_relative_volume_research as rvol_research
import next_session_decision_brief as nsdb
import owner_research_focus
import technical_structure_context as tsc

PREVIOUS_SESSION_DEFAULT = "2026-08-25"
CURRENT_SESSION_DEFAULT = "2026-08-28"
DEFAULT_OUT_DIR = ROOT / "operations-review" / "daily-integrated-decision-brief-prospective-feedback-v1-20260902"
MAIN_ROOT = Path("C:/Projects/StockLookup/stock-core-private")
# READ_ROOT is a repo ROOT (session_artifact_paths appends "operations-review" itself) -- prefer
# this worktree if it happens to carry the needed real evidence, else read (never write) from the
# primary checkout, mirroring the established tools/run_integrated_investment_decision_replay.py
# OPS_ROOT fallback pattern.
READ_ROOT = ROOT if (ROOT / "operations-review" / "market-wide-current-descriptive-research-v1-20260828").exists() else MAIN_ROOT
READ_OPS_ROOT = READ_ROOT / "operations-review"
SEMANTICS_DIR = READ_OPS_ROOT / "market-wide-structured-financial-period-semantics-v1-20260831"
FEATURE_STORE_DIR = READ_OPS_ROOT / "market-wide-fundamental-feature-store-v1-20260831"
CLASSIFICATION_DIR = READ_OPS_ROOT / "market-wide-financial-entity-classification-scaleout-v1-20260901"


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_shared_financial_v2(requested_at: str, candidate_tickers: list[str]) -> dict:
    """Session-independent Financial V2 PRODUCT PROJECTION (not the raw engine artifact), shared
    across every session in this replay. integrated_investment_decision_product.evaluate_fundamental
    _direction() reads a flat compact shape (status, profitability_state, margin_state, ...) --
    financial_analysis_product_projection/v1's shape, not financial_analysis_engine_v2's own
    deeply-nested states/features shape (confirmed empirically: the raw engine artifact produced
    fundamental_state=INSUFFICIENT for all 1,699 tickers). Mirrors tools/run_integrated_investment_
    decision_replay.py's own real wiring (financial_analysis_artifact=inputs["financial_v2_projection"]).
    """
    semantics_art = _load_json(SEMANTICS_DIR / "structured_financial_period_semantics_artifact.json")
    with gzip.open(SEMANTICS_DIR / "structured_financial_period_semantics_facts.jsonl.gz", "rt", encoding="utf-8") as handle:
        sem_rows = [json.loads(line) for line in handle if line.strip()]
    classification_diag = _load_json(CLASSIFICATION_DIR / "scaleout_classification_diagnostics.json")
    fs_records, fs_art = fa_scaleout.load_feature_store(
        FEATURE_STORE_DIR / "market_wide_fundamental_feature_store_artifact.json",
        FEATURE_STORE_DIR / "market_wide_fundamental_feature_store_records.jsonl.gz",
    )
    records_with_types = {ticker: dict(rec) for ticker, rec in fs_records.items()}
    for row in classification_diag.get("rows") or []:
        ticker = str(row.get("ticker") or "").upper()
        outcome = str(row.get("outcome") or "")
        if ticker in records_with_types and outcome in {"corporate", "bank", "securities", "insurance", "finance_company"}:
            records_with_types[ticker]["entity_type"] = outcome
    for ticker, entity_type in entity_classification.load_layered_entity_profiles().items():
        if ticker in records_with_types:
            records_with_types[ticker]["entity_type"] = entity_type
    engine_art = fa_scaleout.build_scaleout(
        semantic_rows=sem_rows, feature_records=records_with_types, feature_store_artifact=fs_art,
        period_semantics_identity=semantics_art["artifact_identity"], requested_at=requested_at,
        classification_diagnostics_identity=classification_diag.get("diagnostics_identity"),
    )
    projection_art = fa_projection.build_product_projection(financial_context=engine_art, product_tickers=candidate_tickers, requested_at=requested_at)
    return {"engine": engine_art, "projection": projection_art}


def build_session_integrated_decision(session: str, fa: dict) -> dict:
    """Build integrated_investment_decision_product/v1 for one real retained session, reading
    every session-scoped upstream input from the same canonical path registry
    canonical_post_close_pipeline.py itself resolves against (read-only, primary checkout)."""
    fa_engine_art, fa_proj_art = fa["engine"], fa["projection"]
    paths = level2.session_artifact_paths(READ_ROOT, session)
    requested_at = f"{session}T15:00:00+07:00"
    desc_art = _load_json(paths["descriptive_research"])
    p3f9b = _load_json(paths["exact_session_snapshot"])
    tac_art = tsc.build_artifact(current_descriptive=desc_art, p3f9b_snapshot=p3f9b, requested_at=requested_at)
    tac_proj_art = msb_proj.build_artifact(technical_structure=tac_art, requested_at=requested_at)
    val_raw = _load_json(paths["valuation"])
    all_candidate_tickers = sorted(p3f9b.get("records", {}).keys())
    # valuation_context.evaluate_ticker_valuation wants financial_analysis_engine_v2's own RAW
    # engine record shape (financial_analysis_record=...); integrated_investment_decision_product.
    # build_artifact wants the COMPACT financial_analysis_product_projection shape below -- two
    # different, real consumers of two different Financial V2 shapes, confirmed against
    # tools/run_integrated_investment_decision_replay.py's own real wiring of both.
    engine_records = fa_engine_art.get("records") or {}
    val_rows = {
        ticker: valuation_context.evaluate_ticker_valuation(
            ticker=ticker, feature_record=None, valuation_record=(val_raw.get("records") or {}).get(ticker),
            financial_analysis_record=engine_records.get(ticker), financial_analysis_context_identity=fa_engine_art.get("artifact_identity"),
        ) for ticker in all_candidate_tickers
    }
    val_rows_with_peers = valuation_context.attach_peer_relative(val_rows)
    current_val_art = {"artifact_identity": f"current_research_valuation_context/v1:replay-{session}", "contract_version": "current_research_valuation_context/v1", "records": val_rows_with_peers}
    rvol_art = rvol_research.build_artifact(candidates=all_candidate_tickers, records=p3f9b.get("records") or {}, session=session, requested_at=requested_at)
    mkt_sector_art = _load_json(paths["sector_leadership"]) if paths["sector_leadership"].exists() else {"market": {"current_breadth_state": "NEUTRAL_MIXED"}, "ticker_contexts": {}}
    legacy_opp = _load_json(paths["opportunity_prioritization"]) if paths["opportunity_prioritization"].exists() else None
    # integrated_investment_decision_product.build_artifact expects the COMPACT projection
    # (market_structure_breakout_product_projection's flat bos_state/choch_state/breakout_state_v3/
    # eligible shape), not technical_structure_context's own deeply-nested eligibility.status/
    # trend_context.* shape -- confirmed against tools/run_integrated_investment_decision_replay.py's
    # own real wiring (technical_structure_artifact=inputs["tactical_projection"]).
    artifact = iidp.build_artifact(
        session=session, requested_at=requested_at, technical_structure_artifact=tac_proj_art, financial_analysis_artifact=fa_proj_art,
        current_valuation_artifact=current_val_art, relative_volume_artifact=rvol_art, market_sector_artifact=mkt_sector_art,
        legacy_decision_artifact=legacy_opp,
    )
    return {"integrated_decision": artifact, "tactical": tac_proj_art, "descriptive": desc_art, "sector_leadership": mkt_sector_art, "opportunity_prioritization": legacy_opp, "p3f9b": p3f9b}


def persist_session_artifacts(root: Path, session: str, inputs: dict) -> None:
    """Write the materialized integrated_investment_decision_product artifact at the SAME
    canonical per-session path canonical_post_close_pipeline.py writes it to, but under this
    worktree's own operations-review/ (never the primary checkout)."""
    paths = level2.session_artifact_paths(root, session)
    _write_json(paths["integrated_investment_decision_product"], inputs["integrated_decision"])


def build_registry_backed_transitions(root: Path, current_session: str, previous_session: str) -> dict:
    """Best-effort market_transition/sector_transition via the SAME registry-driven resolver
    next_session_decision_brief.py itself uses; honestly UNAVAILABLE if either session is not
    registered in config/daily_research_session_input_registry.json's `sessions` ledger (a real,
    pre-existing, orthogonal registration gap -- not something this replay fabricates around)."""
    try:
        registry = nsdb.load_registry(root)
        market_transition = nsdb._market_transition(root=root, registry=registry, current_session=current_session, previous_session=previous_session)
        sector_transition = nsdb._sector_transition(root=root, registry=registry, current_session=current_session, previous_session=previous_session)
    except Exception as exc:
        reason = [f"REGISTRY_BACKED_TRANSITION_UNAVAILABLE:{exc}"]
        market_transition = {"availability": "UNAVAILABLE", "reason_codes": reason}
        sector_transition = {"availability": "UNAVAILABLE", "reason_codes": reason}
    return {"market_transition": market_transition, "sector_transition": sector_transition}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--current-session", default=CURRENT_SESSION_DEFAULT)
    parser.add_argument("--previous-session", default=PREVIOUS_SESSION_DEFAULT)
    parser.add_argument("--worktree-root", type=Path, default=ROOT, help="Where replayed per-session artifacts are written (never the primary checkout).")
    args = parser.parse_args()

    print(f"Building shared Financial V2 (session-independent)...")
    current_paths = level2.session_artifact_paths(READ_ROOT, args.current_session)
    candidate_tickers = sorted((_load_json(current_paths["exact_session_snapshot"]) or {}).get("records", {}).keys())
    fa = build_shared_financial_v2(f"{args.current_session}T00:00:00+07:00", candidate_tickers)

    print(f"Materializing integrated_investment_decision_product for {args.previous_session} (previous)...")
    previous_inputs = build_session_integrated_decision(args.previous_session, fa)
    print(f"Materializing integrated_investment_decision_product for {args.current_session} (current)...")
    current_inputs = build_session_integrated_decision(args.current_session, fa)

    persist_session_artifacts(args.worktree_root, args.previous_session, previous_inputs)
    persist_session_artifacts(args.worktree_root, args.current_session, current_inputs)

    print("Building posture_transition (registry-free) and registry-backed market/sector transitions...")
    posture_transition = nsdb._posture_transition(root=args.worktree_root, current_session=args.current_session, previous_session=args.previous_session)
    registry_backed = build_registry_backed_transitions(args.worktree_root, args.current_session, args.previous_session)
    next_session_brief_shaped = {
        "contract_version": nsdb.CONTRACT_VERSION, "current_session": args.current_session, "previous_qualified_session": args.previous_session,
        "artifact_identity": "next_session_decision_brief:replay-shaped-partial",
        "market_transition": registry_backed["market_transition"], "sector_transition": registry_backed["sector_transition"],
        "posture_transition": posture_transition,
    }

    print("Building prospective feedback status (forward-outcome bridge)...")
    governed_chain = feedback_bridge.governed_session_chain(READ_ROOT)
    watchlist_tickers = list(owner_research_focus.broader_watchlist())
    feedback_status = feedback_bridge.build_prospective_feedback_status(
        current_records=previous_inputs["integrated_decision"].get("records") or {},
        p3f9b_snapshot=current_inputs["p3f9b"], governed_chain=governed_chain, evaluate_watchlist_only=watchlist_tickers,
    )

    print("Building daily_integrated_decision_brief...")
    daily_brief = brief_module.build_artifact(
        session=args.current_session, requested_at=f"{args.current_session}T15:05:00+07:00",
        integrated_decision_current=current_inputs["integrated_decision"], next_session_brief=next_session_brief_shaped,
        descriptive_current=current_inputs["descriptive"], sector_leadership_current=current_inputs["sector_leadership"],
        tactical_current=current_inputs["tactical"], opportunity_prioritization_current=current_inputs["opportunity_prioritization"],
        feedback_status=feedback_status,
    )

    out_dir = args.out_dir
    _write_json(out_dir / "daily_integrated_decision_brief.json", daily_brief)
    _write_json(out_dir / "watchlist_11_brief.json", daily_brief["watchlist"])
    _write_json(out_dir / "opportunity_sets.json", daily_brief["opportunity_sets"])
    _write_json(out_dir / "decision_transitions.json", daily_brief["decision_transitions"])
    _write_json(out_dir / "prospective_feedback_status.json", feedback_status)

    pnj_row = (posture_transition.get("records") or {}).get("PNJ")
    _write_json(out_dir / "pnj_transition_replay.json", {
        "previous_session": args.previous_session, "current_session": args.current_session, "posture_transition_row": pnj_row,
        "previous_record": (previous_inputs["integrated_decision"].get("records") or {}).get("PNJ"),
        "current_record": (current_inputs["integrated_decision"].get("records") or {}).get("PNJ"),
    })

    coverage = current_inputs["integrated_decision"].get("coverage", {})
    validation = {
        "previous_session": args.previous_session, "current_session": args.current_session,
        "universe_denominator": coverage.get("universe_denominator"), "integrated_context_available": coverage.get("integrated_context_available"),
        "watchlist_coverage": daily_brief["watchlist"]["available_count"],
        "opportunity_set_counts": daily_brief["opportunity_sets"]["set_counts"],
        "research_action_posture_distribution": coverage.get("research_action_posture_distribution"),
        "posture_transition_counts": posture_transition.get("transition_counts"),
        "posture_transition_availability": posture_transition.get("availability"),
        "market_transition_availability": registry_backed["market_transition"].get("availability"),
        "sector_transition_availability": registry_backed["sector_transition"].get("availability"),
        "new_actionable_now": daily_brief["what_changed_today"]["new_actionable_now"],
        "new_early_setups": daily_brief["what_changed_today"]["new_early_setups"],
        "new_breakdowns": daily_brief["what_changed_today"]["new_breakdowns"],
        "zero_silent_drops": coverage.get("integrated_context_available") == coverage.get("universe_denominator"),
    }
    _write_json(out_dir / "daily_pipeline_validation.json", validation)
    _write_json(out_dir / "coverage.json", validation)

    report_lines = [
        "# Daily Integrated Decision Brief -- Real Multi-Session Replay", "",
        f"Previous session: `{args.previous_session}`  ", f"Current session: `{args.current_session}`", "",
        f"Universe denominator: **{validation['universe_denominator']}**; integrated context available: **{validation['integrated_context_available']}**; zero silent drops: **{validation['zero_silent_drops']}**", "",
        "## Posture distribution (current session)", "```json", json.dumps(validation["research_action_posture_distribution"], indent=2), "```", "",
        "## Posture transition counts (previous -> current)", "```json", json.dumps(validation["posture_transition_counts"], indent=2), "```", "",
        "## Opportunity set counts", "```json", json.dumps(validation["opportunity_set_counts"], indent=2), "```", "",
        f"## Registry-backed transitions", f"- market_transition availability: `{validation['market_transition_availability']}`", f"- sector_transition availability: `{validation['sector_transition_availability']}`",
        f"- NOTE: `{args.current_session}` is not yet registered in `config/daily_research_session_input_registry.json`'s `sessions` ledger (a pre-existing, orthogonal registration gap this replay reports rather than works around); posture_transition is registry-free by design and is unaffected.", "",
        "## PNJ regression", "```json", json.dumps(pnj_row, indent=2), "```",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Replay complete. Artifacts written to {out_dir}")


if __name__ == "__main__":
    main()
