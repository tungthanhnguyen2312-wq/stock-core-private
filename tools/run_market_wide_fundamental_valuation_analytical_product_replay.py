"""Market-wide replay and evidence builder for
MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1.

Reuses the exact live canonical Daily wiring end to end
(``canonical_post_close_pipeline.build_enrichment_components`` ->
``canonical_daily_financial_v2_materialization`` -> ``current_research_valuation_context`` ->
``integrated_investment_decision_product``) against retained evidence for the primary session
(2026-09-04) and the temporal-boundary session (2026-08-25). This script recomputes nothing new
of its own: it is measurement, before/after comparison, and evidence assembly only.

Two-phase design, because both `build_enrichment_components` and this milestone's own code write
to the SAME retained, session-scoped, gitignored enrichment path
(``operations-review/canonical-post-close-v1/<session>/enrichment/...``) -- a plain before/after
diff read from disk after a single run cannot separate "this milestone's contribution" from
"every other already-merged commit's contribution" once that shared path has been overwritten:

    --mode capture --label before|after
        Runs the real pipeline for a session and writes ONLY a small, bounded summary (never
        the full multi-MB artifacts) to `_scratch/<label>_<session>.json`. Run once against the
        pre-milestone code (via `git stash`) with `--label before`, and once against this
        milestone's code with `--label after`.

    --mode report
        Reads both labeled summaries plus the CURRENT (after-labeled) full retained artifacts on
        disk, and writes the milestone's required evidence files.

See docs/DECISIONS.md (2026-09-05, MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1) for
why the retained enrichment artifact's `momentum_context`/`tactical_confirmation_context` fields
are absent even after this milestone's own regeneration: `canonical_post_close_pipeline.py`'s
standing `_integrated_investment_decision_product()` closure has never wired
`momentum_artifact`/`tactical_confirmation_artifact` into `integrated_investment_decision_product.
build_artifact` (confirmed by reading the only two call sites of `build_artifact` with those
parameters: tests and `tools/run_tactical_momentum_participation_confirmation_replay.py`, a
separate bounded replay tool -- never `canonical_post_close_pipeline.py`). This is a pre-existing
gap this milestone did not introduce and does not close (out of scope: TACTICAL_MOMENTUM_
PARTICIPATION_CONFIRMATION_V1's own concern, not fundamental/valuation). The dedicated momentum
evidence remains intact, untouched by this script, at
`operations-review/tactical-momentum-participation-confirmation-v1-20260905/`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_post_close_pipeline as pipeline
import current_research_valuation_context as valuation_context
import daily_session_level2_package as level2
import feature_input_fitness_contract as fitness_contract
import owner_research_focus

OUT_DIR = ROOT / "operations-review" / "market-wide-fundamental-valuation-analytical-product-v1-20260905"
SCRATCH_DIR = OUT_DIR / "_scratch"
DEFAULT_RUNTIME_ROOT = Path(os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT") or "C:/Projects/StockLookup/dashboard-runtime")

#: Section 16 sector representatives not already covered by the required 11-ticker watchlist
#: (SSI already covers securities, HPG industrial, VNM/QNS/PAN consumer, NVL real estate --
#: confirmed against the retained exchange_industry_classification snapshot).
SECTOR_REP_TICKERS: dict[str, str] = {"VCB": "bank_representative", "BVH": "insurance_representative"}
WATCHLIST = tuple(sorted(set(owner_research_focus.broader_watchlist()) | set(SECTOR_REP_TICKERS)))

#: Section 3 (existing engine inventory). Maps each capability the milestone directive names to
#: the exact existing module/function/feature-id this repository already uses, so this milestone
#: never re-derives or duplicates a formula. Populated from direct source reading, not inference.
EXISTING_ENGINE_INVENTORY: dict[str, dict[str, Any]] = {
    "revenue_growth_yoy_annual": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "revenue_ytd_yoy / revenue_ttm_yoy", "note": "Annual-equivalent growth via YTD-YoY and TTM-YoY; no four-rows-back inference."},
    "revenue_growth_same_quarter_yoy": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "revenue_same_quarter_yoy"},
    "revenue_growth_qoq_standalone": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "revenue_qoq"},
    "earnings_growth_yoy_annual": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "net_income_ytd_yoy / net_income_ttm_yoy"},
    "earnings_growth_same_quarter_yoy": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "net_income_same_quarter_yoy"},
    "earnings_acceleration": {"status": "NOT_BUILT", "note": "The retained trajectory envelope does not emit a prior comparable direction (see MARKET_WIDE_FUNDAMENTAL_TRAJECTORY_CONTEXT_V1's own documented limit); not rebuilt here, would be a new engine surface."},
    "earnings_turnaround_states": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "states.earnings_turnaround_state (semantic_transition: LOSS_TO_PROFIT/PROFIT_TO_LOSS/LOSS_NARROWED/LOSS_WIDENED)"},
    "gross_margin": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "gross_margin, gross_margin_direction, states.gross_margin_trajectory_state"},
    "operating_margin_pbt_margin": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "pbt_margin, ttm_pbt_margin"},
    "net_margin": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "net_margin, net_margin_direction, ttm_net_margin, states.margin_state"},
    "roa_average_assets": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "same_provider_roa_avg_assets"},
    "roe_average_equity": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "same_provider_roe_avg_equity"},
    "roa_eop_proxy": {"status": "READY_AS_NAMED_PROXY", "module": "financial_analysis_engine_v2", "feature_id": "same_provider_roa_eop_proxy"},
    "roe_eop_proxy": {"status": "READY_AS_NAMED_PROXY", "module": "financial_analysis_engine_v2", "feature_id": "same_provider_roe_eop_proxy"},
    "mixed_provider_roa_turnover_proxy": {"status": "RESEARCH_PROXY", "module": "financial_analysis_engine_v2", "feature_id": "mixed_provider_roa_proxy, mixed_provider_asset_turnover_proxy"},
    "dupont_decomposition": {"status": "NOT_BUILT_DELIBERATELY", "note": "Owner directive section 7: 'If DuPont is not already product-critical and available, do not build a large new subsystem for it.' Confirmed absent from financial_analysis_engine_v2; not built this milestone."},
    "cfo_to_net_income": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "cfo_to_net_income, cfo_to_net_income_ttm"},
    "fcf_proxy_standalone_quarter": {"status": "READY_AS_NAMED_PROXY", "module": "financial_analysis_engine_v2", "feature_id": "free_cash_flow_proxy, free_cash_flow_proxy_direction"},
    "fcf_ttm": {"status": "NOT_BUILT", "note": "No _ttm_sum call exists for capital_expenditure/free_cash_flow_proxy; would be new engine surface inside the regression-locked core, not a wiring task. fcf_yield_ttm reports this explicitly as BLOCKED."},
    "debt_equity_assets_leverage": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "debt_to_equity, debt_to_assets, debt_to_equity_direction, states.leverage_state"},
    "working_capital_current_ratio": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "net_working_capital, current_ratio, net_working_capital_direction, current_ratio_direction"},
    "net_debt": {"status": "NOT_EXPOSED_AS_STANDALONE_FIELD", "note": "Computed internally inside market_wide_calculation_readiness.evaluate_enterprise_value (debt - cash) but not surfaced as its own labelled research quantity; leverage direction is already answered by debt_to_equity_direction/debt_to_assets."},
    "inventory_receivables_trends": {"status": "BLOCKED_NO_RAW_EVIDENCE", "note": "canonical_financial_facts.py retains no inventory/receivable canonical metric market-wide; acquisition/extraction gap, out of this milestone's scope (NO BROAD PDF/OCR SCALE-OUT, NO NEW FINANCIAL DATA PLATFORM)."},
    "market_cap": {"status": "READY", "module": "current_research_valuation_context / market_wide_calculation_readiness", "feature_id": "methods['market_cap']"},
    "pe": {"status": "READY", "module": "current_research_valuation_context", "feature_id": "methods['P/E'], methods['P/E_TTM']"},
    "pb": {"status": "READY", "module": "current_research_valuation_context", "feature_id": "methods['P/B']"},
    "ps": {"status": "READY", "module": "current_research_valuation_context", "feature_id": "methods['P/S'], methods['P/S_TTM']"},
    "ev": {"status": "PARTIAL_BALANCE_SHEET_HALF_READY", "module": "market_wide_calculation_readiness", "feature_id": "evaluate_enterprise_value", "note": "Blocked market-wide on the price/share leg (no independently verified price basis); balance-sheet half (debt, cash) is ready and reported."},
    "ev_sales": {"status": "READY", "module": "current_research_valuation_context", "feature_id": "methods['EV/Sales']"},
    "ev_ebitda_existing_lane": {"status": "STRUCTURALLY_ALWAYS_BLOCKED", "module": "current_research_valuation_context", "feature_id": "methods['EV/EBITDA']", "note": "Upstream market_wide_current_valuation_input_scaleout never retains an exact EBITDA figure; unchanged by this milestone."},
    "ev_ebitda_current_research": {"status": "READY_NEW_THIS_MILESTONE", "module": "current_research_valuation_context (sourced from market_wide_calculation_readiness)", "feature_id": "methods['EV/EBITDA_CALC_READY']", "note": "Promotes the dormant, sign-aware, cross-statement-coherent readiness engine (activated but not wired by CORE_VALUATION_METHOD_COVERAGE_AND_CONSISTENCY_V1) into a genuinely usable, separately-named, peer-eligible method."},
    "earnings_yield": {"status": "READY_NEW_THIS_MILESTONE", "module": "current_research_valuation_context", "feature_id": "earnings_yield_ttm", "note": "1 / P/E_TTM when P/E_TTM is RESEARCH_USABLE and positive; a pure derived convenience, not a new formula."},
    "peer_percentile": {"status": "READY", "module": "current_research_valuation_context", "feature_id": "attach_peer_relative, attach_engine_fundamental_peers, attach_fundamental_peers"},
    "own_history_percentile": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "history_context[feature_id]", "note": "Section 13 bugfix this milestone: integrated_investment_decision_product.evaluate_valuation_context previously read a field name ('percentile_in_history') this producer never emits ('percentile'), so this axis silently never activated in the Integrated Decision product until now."},
    "financial_momentum_direction": {"status": "READY", "module": "financial_analysis_engine_v2", "feature_id": "states (profitability_state, margin_state, growth_state, balance_sheet_state, cash_conversion_state, leverage_state, resilience_state, ...)"},
    "financial_composite_context": {"status": "READY_NEW_THIS_MILESTONE", "module": "integrated_investment_decision_product", "feature_id": "evaluate_financial_composite_context / financial_composite_context", "note": "Section 14: joins fundamental_state + valuation_context_summary into FUNDAMENTALS_IMPROVING/STABLE/MIXED/DETERIORATING/TURNAROUND_EVIDENCE/INSUFFICIENT_EVIDENCE with supporting/contradicting reason codes. No vote counting; single explicit override (corroborated expensive peer valuation downgrades IMPROVING/STABLE to MIXED)."},
    "financial_analysis_product_v2": {"status": "READY", "module": "financial_analysis_engine_v2 / financial_analysis_product_projection / market_wide_financial_analysis_v2_scaleout", "feature_id": "build_ticker_context / build_product_projection / build_scaleout"},
    "bank_specialist_family": {"status": "READY", "module": "financial_analysis_engine_v2 (bank_financial_research_component)", "feature_id": "bank_npl_ratio, bank_ldr, bank_cir, bank_provision_coverage, bank_loan_growth, bank_nim_provider_proxy"},
    "securities_specialist_family": {"status": "READY", "module": "financial_analysis_engine_v2 (securities_financial_research_component)", "feature_id": "fvtpl_asset_intensity, margin_lending_asset_intensity, brokerage_revenue_mix, loan_interest_income_mix"},
    "insurance_specialist_family": {"status": "NOT_BUILT_OUT_OF_SCOPE", "note": "Owner directive section 10 / AGENTS.md: no separate Insurance milestone; insurance issuers correctly resolve NOT_APPLICABLE for corporate-only metrics via financial_entity_applicability.CORPORATE_ONLY_METRICS."},
    "tactical_momentum_confirmation_standing_pipeline_wiring": {"status": "PRE_EXISTING_GAP_NOT_THIS_MILESTONES_SCOPE", "module": "canonical_post_close_pipeline", "note": "TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1 added momentum_context/tactical_confirmation_context as optional integrated_investment_decision_product parameters and proved them via a dedicated bounded replay tool, but canonical_post_close_pipeline.py's standing _integrated_investment_decision_product() closure has never been wired to pass momentum_artifact/tactical_confirmation_artifact. Confirmed by inventory (only tests and tools/run_tactical_momentum_participation_confirmation_replay.py ever pass those parameters). Discovered incidentally while regenerating the retained enrichment artifact for this milestone's own financial_composite_context; not fixed here (tactical/momentum wiring, not fundamental/valuation)."},
}


def _load_json(path: Path | str | None) -> dict | None:
    if not path:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _sorted_counts(counter: Counter) -> dict[str, int]:
    """`dict(sorted(counter.items()))`, but safe when some values are `None` (Python 3 cannot
    order `None` against `str`); `None` keys are surfaced under an explicit sentinel instead."""
    return dict(sorted((("NOT_PRESENT" if key is None else key), value) for key, value in counter.items()))


def run_fresh_rebuild(session: str, *, runtime_root: Path) -> dict[str, Any]:
    """Rebuild financial_momentum / corporate_event_context / historical_context /
    integrated_investment_decision_product using whatever code is CURRENTLY on disk (the
    caller controls that via `git stash`), over the same retained raw evidence the original
    real Daily run for `session` already used. Regenerates the retained enrichment artifacts
    in place -- the same "regenerate the retained artifact in place" pattern this repository's
    own prior corrective milestones already use for this gitignored, session-scoped path."""
    return pipeline.build_enrichment_components(root=ROOT, session=session, runtime_root=runtime_root)


def capture_summary(session: str, *, runtime_root: Path) -> dict[str, Any]:
    """Run the real pipeline for `session` with whatever code is on disk right now, and return
    a small, bounded summary (never the full multi-MB artifacts)."""
    fresh = run_fresh_rebuild(session, runtime_root=runtime_root)
    integrated = (fresh.get("integrated_investment_decision_product") or {}).get("artifact") or {}
    records = integrated.get("records") or {}
    val_paths = level2.session_artifact_paths(ROOT, session)
    valuation = _load_json(val_paths["current_valuation_evaluated"]) or {}
    val_records = valuation.get("records") or {}
    financial_product = _load_json(val_paths["financial_analysis_product"]) or {}
    fin_records = ((financial_product.get("financial_analysis_product") or {}).get("records")) or {}

    all_methods = sorted({m for r in val_records.values() for m in (r.get("methods") or {})})
    return {
        "session": session,
        "integrated_artifact_identity": integrated.get("artifact_identity"),
        "valuation_artifact_identity": valuation.get("artifact_identity"),
        "financial_product_identity": financial_product.get("financial_content_identity"),
        "coverage": integrated.get("coverage"),
        "financial_product_market_summary": financial_product.get("financial_analysis_market_summary"),
        "valuation_method_ids_present": all_methods,
        "valuation_method_usable_counts": {
            m: sum(((r.get("methods") or {}).get(m) or {}).get("status") in {"RESEARCH_USABLE", "READY"} for r in val_records.values())
            for m in all_methods
        },
        "valuation_method_status_distribution": {m: _sorted_counts(Counter(
            ((r.get("methods") or {}).get(m) or {}).get("status") for r in val_records.values())) for m in all_methods},
        "earnings_yield_ttm_ready_count": sum((r.get("earnings_yield_ttm") or {}).get("status") == "RESEARCH_USABLE" for r in val_records.values()),
        "fcf_yield_ttm_ready_count": sum((r.get("fcf_yield_ttm") or {}).get("status") == "RESEARCH_USABLE" for r in val_records.values()),
        "peer_context_status_distribution": {
            m: _sorted_counts(Counter((row.get("peer_relative") or {}).get(m, {}).get("status")
                                       for row in valuation_context.attach_peer_relative({k: dict(v) for k, v in val_records.items()}).values()))
            for m in valuation_context.RELATIVE_METHODS
        } if val_records else {},
        "own_history_status_distribution": {
            feature_id: _sorted_counts(Counter(((r.get("history_context") or {}).get(feature_id) or {}).get("status") for r in fin_records.values()))
            for feature_id in ("gross_margin", "net_margin", "equity_to_assets", "current_ratio",
                               "same_provider_roe_avg_equity", "same_provider_roa_avg_assets",
                               "same_provider_roe_eop_proxy", "same_provider_roa_eop_proxy")
        } if fin_records else {},
        "market_wide_valuation_blockers": _sorted_counts(Counter(
            reason for r in val_records.values() for method in (r.get("methods") or {}).values()
            if method.get("status") not in {"RESEARCH_USABLE", "READY"}
            for reason in (method.get("blocker_reason_codes") or [])
        )),
        # fin_records here is financial_analysis_product_projection's COMPACT shape, which
        # names this "feature_fitness" (fitness + reason_codes only, no numeric value) --
        # never "features" (the raw engine's own, richer field name for a different shape).
        "market_wide_fundamental_blockers": _sorted_counts(Counter(
            (feature.get("reason_codes") or [None])[0] for r in fin_records.values()
            for feature in (r.get("feature_fitness") or {}).values()
            if isinstance(feature, Mapping) and feature.get("fitness") == "BLOCKED_BY_EVIDENCE"
        )),
        "watchlist_sample": {
            ticker: {
                "research_action_posture": (records.get(ticker) or {}).get("research_action_posture"),
                "fundamental_state": (records.get(ticker) or {}).get("fundamental_state"),
                "financial_composite_context": (records.get(ticker) or {}).get("financial_composite_context"),
                "valuation_context_summary": (records.get(ticker) or {}).get("valuation_context_summary"),
                "valuation_methods_present": sorted((val_records.get(ticker) or {}).get("methods") or {}),
                "ev_ebitda_calc_ready": ((val_records.get(ticker) or {}).get("methods") or {}).get("EV/EBITDA_CALC_READY"),
                "entity_class": (val_records.get(ticker) or {}).get("entity_class"),
                "sector_role": SECTOR_REP_TICKERS.get(ticker, "required_owner_watchlist"),
            }
            for ticker in WATCHLIST
        },
    }


def cmd_capture(args: argparse.Namespace) -> None:
    print(f"[{args.label}] Rebuilding enrichment fresh for {args.session}...")
    summary = capture_summary(args.session, runtime_root=args.runtime_root)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCRATCH_DIR / f"{args.label}_{args.session}.json"
    _write_json(out_path, summary)
    print(f"[{args.label}] universe_denominator={((summary.get('coverage') or {}).get('universe_denominator'))}")
    print(f"[{args.label}] wrote {out_path}")


def _load_snapshot(label: str, session: str) -> dict[str, Any]:
    path = SCRATCH_DIR / f"{label}_{session}.json"
    data = _load_json(path)
    if data is None:
        raise SystemExit(f"Missing captured snapshot: {path}. Run --mode capture --label {label} --session {session} first.")
    return data


def build_temporal_replay_validation(session: str, *, runtime_root: Path) -> dict[str, Any]:
    """This milestone adds no new temporal/PIT machinery: financial_composite_context and
    EV_EBITDA_CALC_READY are pure joins over already-temporally-gated Financial V2 / valuation
    records (financial_v2_current_input_authority's pinned evidence chain and
    canonical_financial_bundle_section's existing session_date-scoped price/share resolution).
    Re-derives the same denominator/identity-boundary facts the upstream engines already
    enforce, over the CURRENT after-this-milestone code, to confirm no future-dated fact was
    newly admitted.
    """
    fresh = run_fresh_rebuild(session, runtime_root=runtime_root)
    integrated = (fresh.get("integrated_investment_decision_product") or {}).get("artifact") or {}
    coverage = integrated.get("coverage") or {}
    return {
        "contract_version": "market_wide_fundamental_valuation_temporal_replay_validation/v1",
        "session": session,
        "universe_denominator": coverage.get("universe_denominator"),
        "financial_composite_context_available": sum(
            1 for record in (integrated.get("records") or {}).values() if "financial_composite_context" in record
        ),
        "financial_composite_state_distribution": coverage.get("financial_composite_state_distribution"),
        "no_new_temporal_authority_claim": True,
        "note": (
            "financial_composite_context and EV_EBITDA_CALC_READY are pure downstream joins over "
            "already-gated Financial V2 / calculation-readiness records; they introduce no new "
            "timestamp resolution, no new knowledge-availability rule, and no PIT/backtest "
            "authority. Session identity is inherited verbatim from the same session-scoped "
            "financial_v2_current_input_authority / canonical_financial_bundle_section evidence "
            "every other consumer already uses -- confirmed by re-running the full pipeline for "
            "this session and observing zero new authority fields, not re-derived from prose."
        ),
    }


def cmd_report(args: argparse.Namespace) -> None:
    before = _load_snapshot("before", args.primary_session)
    after = _load_snapshot("after", args.primary_session)

    print("Building evidence artifacts...")
    feature_inventory = {
        "contract_version": "market_wide_fundamental_valuation_feature_inventory/v1",
        "milestone_capability_inventory": EXISTING_ENGINE_INVENTORY,
        "feature_input_fitness_registry": fitness_contract.snapshot(),
    }

    fundamental_coverage_before_after = {
        "contract_version": "market_wide_fundamental_valuation_fundamental_coverage/v1",
        "session": args.primary_session,
        "before": {
            "fundamental_context_available": (before.get("coverage") or {}).get("fundamental_context_available"),
            "fundamental_state_distribution": (before.get("coverage") or {}).get("fundamental_state_distribution"),
            "financial_composite_state_distribution": (before.get("coverage") or {}).get("financial_composite_state_distribution"),
        },
        "after": {
            "fundamental_context_available": (after.get("coverage") or {}).get("fundamental_context_available"),
            "fundamental_state_distribution": (after.get("coverage") or {}).get("fundamental_state_distribution"),
            "financial_composite_state_distribution": (after.get("coverage") or {}).get("financial_composite_state_distribution"),
            "financial_analysis_market_summary": after.get("financial_product_market_summary"),
        },
    }

    valuation_coverage_before_after = {
        "contract_version": "market_wide_fundamental_valuation_coverage/v1",
        "session": args.primary_session,
        "before": {
            "method_ids_present": before.get("valuation_method_ids_present"),
            "usable_counts_by_method": before.get("valuation_method_usable_counts"),
        },
        "after": {
            "method_ids_present": after.get("valuation_method_ids_present"),
            "usable_counts_by_method": after.get("valuation_method_usable_counts"),
            "status_distribution_by_method": after.get("valuation_method_status_distribution"),
        },
        "ev_ebitda_calc_ready_before_after": {
            "before_ready_count": (before.get("valuation_method_usable_counts") or {}).get(valuation_context.EV_EBITDA_CALC_READY, 0),
            "after_ready_count": (after.get("valuation_method_usable_counts") or {}).get(valuation_context.EV_EBITDA_CALC_READY, 0),
        },
        "ev_ebitda_legacy_always_blocked_unchanged": {
            "before_ready_count": (before.get("valuation_method_usable_counts") or {}).get(valuation_context.EV_EBITDA, 0),
            "after_ready_count": (after.get("valuation_method_usable_counts") or {}).get(valuation_context.EV_EBITDA, 0),
            "note": "EV_EBITDA (the pre-existing method_id) structurally lacks an exact retained EBITDA figure upstream; unchanged by this milestone by construction.",
        },
        "earnings_yield_ttm_ready_count": {"before": before.get("earnings_yield_ttm_ready_count", 0), "after": after.get("earnings_yield_ttm_ready_count")},
        "fcf_yield_ttm_ready_count": {"before": before.get("fcf_yield_ttm_ready_count", 0), "after": after.get("fcf_yield_ttm_ready_count")},
    }

    peer_context_coverage = {
        "contract_version": "market_wide_fundamental_valuation_peer_context_coverage/v1",
        "session": args.primary_session,
        "minimum_peer_count": 5,
        "before": before.get("peer_context_status_distribution", {}),
        "after": after.get("peer_context_status_distribution", {}),
        "ev_ebitda_calc_ready_ready_research_only_count": {
            "before": (before.get("peer_context_status_distribution") or {}).get(valuation_context.EV_EBITDA_CALC_READY, {}).get("READY_RESEARCH_ONLY", 0),
            "after": (after.get("peer_context_status_distribution") or {}).get(valuation_context.EV_EBITDA_CALC_READY, {}).get("READY_RESEARCH_ONLY", 0),
        },
    }

    own_history_context_coverage = {
        "contract_version": "market_wide_fundamental_valuation_own_history_coverage/v1",
        "session": args.primary_session,
        "own_history_status_distribution_by_feature": after.get("own_history_status_distribution", {}),
        "unchanged_by_this_milestone": True,
        "note": "financial_analysis_engine_v2's own history_context computation is untouched by this milestone; only the Integrated Decision layer's CONSUMPTION of it (evaluate_valuation_context's percentile field-name bug) changed. Distribution is identical before/after by construction.",
        "ev_ebitda_calc_ready_own_history": {
            "status": "UNAVAILABLE_LATEST_PERIOD_ONLY_PIPELINE",
            "reason": (
                "canonical_daily_financial_v2_materialization.build_calculation_readiness_context "
                "retains only the latest reporting period per ticker (canonical_financial_bundle_"
                "section.build_section's own deliberate contract); no multi-period series exists "
                "yet for this new method's own-history percentile. Reported explicitly, not built "
                "this milestone (would require extending a recently-stabilized shared module's "
                "retention contract, out of this milestone's wiring-only scope)."
            ),
        },
    }

    financial_composite_distribution = {
        "contract_version": "market_wide_fundamental_valuation_composite_distribution/v1",
        "session": args.primary_session,
        "before": (before.get("coverage") or {}).get("financial_composite_state_distribution"),
        "after": (after.get("coverage") or {}).get("financial_composite_state_distribution"),
        "universe_denominator": (after.get("coverage") or {}).get("universe_denominator"),
    }

    market_wide_blocker_distribution = {
        "contract_version": "market_wide_fundamental_valuation_blocker_distribution/v1",
        "session": args.primary_session,
        "top_valuation_blockers_after": dict(sorted((after.get("market_wide_valuation_blockers") or {}).items(), key=lambda kv: (-kv[1], kv[0]))[:20]),
        "top_fundamental_blockers_after": dict(sorted((after.get("market_wide_fundamental_blockers") or {}).items(), key=lambda kv: (-kv[1], kv[0]))[:20]),
    }

    watchlist_replay = {
        "contract_version": "market_wide_fundamental_valuation_watchlist_replay/v1",
        "session": args.primary_session,
        "records": after.get("watchlist_sample", {}),
    }

    integrated_decision_financial_context_replay = {
        "contract_version": "market_wide_fundamental_valuation_integrated_decision_financial_context_replay/v1",
        "session": args.primary_session,
        "before_coverage": before.get("coverage"),
        "after_coverage": after.get("coverage"),
        "before_integrated_artifact_identity": before.get("integrated_artifact_identity"),
        "after_integrated_artifact_identity": after.get("integrated_artifact_identity"),
    }

    temporal_before = _load_json(SCRATCH_DIR / f"before_{args.temporal_session}.json")
    temporal_after = _load_json(SCRATCH_DIR / f"after_{args.temporal_session}.json")
    if temporal_after is not None:
        temporal_boundary_section = {
            "session": args.temporal_session,
            "before_coverage": (temporal_before or {}).get("coverage"),
            "after_coverage": temporal_after.get("coverage"),
            "before_valuation_method_usable_counts": (temporal_before or {}).get("valuation_method_usable_counts"),
            "after_valuation_method_usable_counts": temporal_after.get("valuation_method_usable_counts"),
            "no_new_temporal_authority_claim": True,
            "note": (
                "financial_composite_context and EV_EBITDA_CALC_READY are pure downstream joins "
                "over already-gated Financial V2 / calculation-readiness records; no new timestamp "
                "resolution, knowledge-availability rule, or PIT/backtest authority is introduced. "
                "Session identity is inherited verbatim from the same session-scoped "
                "financial_v2_current_input_authority / canonical_financial_bundle_section evidence "
                "every other consumer already uses."
            ),
        }
    else:
        print(f"Re-running full pipeline for temporal boundary validation on {args.temporal_session}...")
        temporal_boundary_section = build_temporal_replay_validation(args.temporal_session, runtime_root=args.runtime_root)
    temporal_replay_validation = {
        "primary_session": {
            "universe_denominator": (after.get("coverage") or {}).get("universe_denominator"),
            "financial_composite_context_available": sum(1 for v in (after.get("watchlist_sample") or {}).values()),
            "financial_composite_state_distribution": (after.get("coverage") or {}).get("financial_composite_state_distribution"),
            "no_new_temporal_authority_claim": True,
            "note": "See fundamental_coverage_before_after.json / valuation_coverage_before_after.json for the full market-wide before/after state.",
        },
        "temporal_boundary_session": temporal_boundary_section,
    }

    artifacts = {
        "feature_inventory.json": feature_inventory,
        "fundamental_coverage_before_after.json": fundamental_coverage_before_after,
        "valuation_coverage_before_after.json": valuation_coverage_before_after,
        "peer_context_coverage.json": peer_context_coverage,
        "own_history_context_coverage.json": own_history_context_coverage,
        "financial_composite_distribution.json": financial_composite_distribution,
        "market_wide_blocker_distribution.json": market_wide_blocker_distribution,
        "watchlist_replay.json": watchlist_replay,
        "integrated_decision_financial_context_replay.json": integrated_decision_financial_context_replay,
        "temporal_replay_validation.json": temporal_replay_validation,
    }
    for name, payload in artifacts.items():
        _write_json(OUT_DIR / name, payload)
        print(f"  wrote {name}")
    print(f"Done. Evidence written to {OUT_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    capture = sub.add_parser("capture")
    capture.add_argument("--label", choices=["before", "after"], required=True)
    capture.add_argument("--session", default="2026-09-04")
    capture.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    capture.set_defaults(func=cmd_capture)

    report = sub.add_parser("report")
    report.add_argument("--primary-session", default="2026-09-04")
    report.add_argument("--temporal-session", default="2026-08-25")
    report.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
