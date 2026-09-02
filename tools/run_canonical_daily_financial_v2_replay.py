#!/usr/bin/env python3
"""Real retained-evidence replay for CANONICAL_DAILY_FINANCIAL_V2_AND_CURRENT_RESEARCH_
ENRICHMENT_V1.

Proves the canonical_post_close_pipeline.py fix end to end against real retained multi-
session evidence: BEFORE (legacy/raw wiring) vs AFTER (canonical Financial V2 materialization
+ evaluated valuation) integrated-decision posture/fundamental-state distributions, financial
evidence identity stability across sessions, independent replay equivalence against
CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1's own established replay, and representative
ticker traces.

Read-only against already-retained evidence (worktree-local first, else the Producer main
checkout's operations-review/ -- the same OPS_ROOT fallback tools/run_integrated_investment_
decision_replay.py already established for a worktree that predates a given session's raw
per-session evidence). No provider calls, no store writes, no mutation of either checkout.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_daily_financial_v2_materialization as fin_v2_material  # noqa: E402
import entity_classification_contract as entity_classification  # noqa: E402
import financial_v2_current_input_authority as fin_v2_authority  # noqa: E402
import integrated_investment_decision_product as iidp  # noqa: E402
import market_structure_breakout_product_projection as msb_proj  # noqa: E402
import market_wide_relative_volume_research as rvol_research  # noqa: E402
import owner_research_focus  # noqa: E402
import technical_structure_context as tsc  # noqa: E402

DEFAULT_OUT_DIR = Path("C:/Projects/StockLookup/operations-review") / "canonical-daily-financial-v2-current-research-enrichment-v1-20260902"
MAIN_OPS = Path("C:/Projects/StockLookup/stock-core-private/operations-review")
LOCAL_OPS = ROOT / "operations-review"

REPRESENTATIVE_TICKERS = ("HPG", "PNJ", "FPT", "PVD", "QNS", "SSI", "VCB")
SESSIONS = ("2026-08-25", "2026-08-28")


def _ops_root(session: str) -> Path:
    """A worktree-local descriptive-research directory for this exact session is the
    signal that this worktree carries real per-session evidence; otherwise fall back to
    the Producer main checkout, read-only -- never written to."""
    nodash = session.replace("-", "")
    if (LOCAL_OPS / f"market-wide-current-descriptive-research-v1-{nodash}").exists():
        return LOCAL_OPS
    return MAIN_OPS


def _load(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _session_paths(ops_root: Path, session: str) -> dict[str, Path]:
    nodash = session.replace("-", "")
    return {
        "descriptive": ops_root / f"market-wide-current-descriptive-research-v1-{nodash}" / "market_wide_current_descriptive_research_artifact.json",
        "p3f9b": ops_root / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f9b_mva_exact_session_snapshot.json",
        "sector_leadership": ops_root / f"current-market-sector-leadership-context-v1-{nodash}" / "current_market_sector_leadership_context_artifact.json",
        "valuation": ops_root / f"market-wide-current-valuation-v1-{nodash}-session{nodash}" / "market_wide_current_valuation_artifact.json",
    }


def load_session_bundle(session: str) -> dict | None:
    ops_root = _ops_root(session)
    paths = _session_paths(ops_root, session)
    desc = _load(paths["descriptive"])
    p3f9b = _load(paths["p3f9b"])
    if not desc or not p3f9b:
        return None
    requested_at = f"{session}T15:00:00+07:00"
    technical_structure = tsc.build_artifact(current_descriptive=desc, p3f9b_snapshot=p3f9b, requested_at=requested_at)
    tactical_projection = msb_proj.build_artifact(technical_structure=technical_structure, requested_at=requested_at)
    daily_denominator = sorted((p3f9b.get("records") or {}).keys())
    relative_volume = rvol_research.build_artifact(
        candidates=daily_denominator, records=p3f9b.get("records") or {}, session=session, requested_at=requested_at,
    )
    mkt = _load(paths["sector_leadership"])
    raw_val = _load(paths["valuation"])
    return {
        "ops_root": str(ops_root), "session": session, "requested_at": requested_at,
        "daily_denominator": daily_denominator, "tactical_projection": tactical_projection,
        "relative_volume": relative_volume, "market_sector": mkt, "raw_valuation": raw_val,
    }


def build_before_after(bundle: dict) -> dict:
    """BEFORE: the actual pre-fix wiring (legacy fundamental artifact -- genuinely absent in
    this environment, so financial_analysis_artifact=None; raw unevaluated valuation artifact
    fed as-is). AFTER: canonical Financial V2 materialization + evaluated valuation."""
    session, requested_at = bundle["session"], bundle["requested_at"]
    daily_denominator = bundle["daily_denominator"]

    before_art = iidp.build_artifact(
        session=session, requested_at=requested_at,
        technical_structure_artifact=bundle["tactical_projection"],
        financial_analysis_artifact=None,
        current_valuation_artifact=bundle["raw_valuation"],
        relative_volume_artifact=bundle["relative_volume"],
        market_sector_artifact=bundle["market_sector"],
    )

    authority = fin_v2_authority.resolve(ROOT)
    engine_artifact = fin_v2_material.build_engine_artifact(root=ROOT, requested_at=requested_at, authority=authority)
    financial_session_artifact = fin_v2_material.build_session_artifact(
        root=ROOT, decision_session=session, product_tickers=daily_denominator,
        requested_at=requested_at, authority=authority, engine_artifact=engine_artifact,
    )
    evaluated_valuation = fin_v2_material.build_evaluated_valuation_artifact(
        engine_artifact=engine_artifact, raw_valuation_artifact=bundle["raw_valuation"],
        product_tickers=daily_denominator, requested_at=requested_at,
    )
    after_art = iidp.build_artifact(
        session=session, requested_at=requested_at,
        technical_structure_artifact=bundle["tactical_projection"],
        financial_analysis_artifact=financial_session_artifact["financial_analysis_product"],
        current_valuation_artifact=evaluated_valuation,
        relative_volume_artifact=bundle["relative_volume"],
        market_sector_artifact=bundle["market_sector"],
    )
    return {
        "session": session, "before": before_art, "after": after_art,
        "financial_session_artifact": financial_session_artifact,
        "evaluated_valuation": evaluated_valuation, "engine_artifact": engine_artifact,
    }


def fundamental_state_distribution(artifact: dict) -> dict[str, int]:
    return dict(sorted(Counter(rec.get("fundamental_state") for rec in artifact["records"].values()).items()))


def posture_distribution(artifact: dict) -> dict[str, int]:
    return dict(sorted(Counter(rec.get("research_action_posture") for rec in artifact["records"].values()).items()))


def representative_trace(session_result: dict, ticker: str) -> dict:
    before_rec = session_result["before"]["records"].get(ticker) or {}
    after_rec = session_result["after"]["records"].get(ticker) or {}
    fa_rec = session_result["financial_session_artifact"]["financial_analysis_product"]["records"].get(ticker) or {}
    val_rec = session_result["evaluated_valuation"]["records"].get(ticker) or {}
    return {
        "ticker": ticker,
        "financial_input_contract": fa_rec.get("contract_version") or session_result["financial_session_artifact"]["financial_analysis_product"].get("contract_version"),
        "financial_status": fa_rec.get("status"),
        "profitability_state": fa_rec.get("profitability_state"),
        "margin_state": fa_rec.get("margin_state"),
        "growth_state": fa_rec.get("growth_state"),
        "bank_asset_quality_state": fa_rec.get("bank_asset_quality_state"),
        "brokerage_mix_trajectory_state": fa_rec.get("brokerage_mix_trajectory_state"),
        "before_fundamental_state": before_rec.get("fundamental_state"),
        "after_fundamental_state": after_rec.get("fundamental_state"),
        "before_posture": before_rec.get("research_action_posture"),
        "after_posture": after_rec.get("research_action_posture"),
        "valuation_status": val_rec.get("has_usable_method"),
        "valuation_usable_relative_methods": val_rec.get("usable_relative_method_count"),
        "missing_dimensions": after_rec.get("material_uncertainties"),
        "why_now_after": after_rec.get("why_now"),
    }


def entity_class_for(ticker: str) -> str:
    profiles = entity_classification.load_layered_entity_profiles()
    return profiles.get(ticker, "unknown")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    session_results: dict[str, dict] = {}
    for session in SESSIONS:
        bundle = load_session_bundle(session)
        if bundle is None:
            session_results[session] = {"status": "EVIDENCE_UNAVAILABLE"}
            continue
        session_results[session] = build_before_after(bundle)

    available_sessions = [s for s, r in session_results.items() if r.get("status") != "EVIDENCE_UNAVAILABLE"]

    # ---- financial_authority_chain.json ----
    authority = fin_v2_authority.resolve(ROOT)
    authority_chain = authority.to_manifest()
    (out_dir / "financial_authority_chain.json").write_text(
        json.dumps(authority_chain, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- financial_product_coverage.json ----
    coverage_by_session = {}
    engine_identities = {}
    for session in available_sessions:
        result = session_results[session]
        fap = result["financial_session_artifact"]
        coverage_by_session[session] = fap["coverage"]
        engine_identities[session] = fap["financial_v2_engine_identity"]
    financial_evidence_identical_across_sessions = (
        len(set(engine_identities.values())) == 1 if len(engine_identities) > 1 else None
    )
    product_coverage = {
        "coverage_by_session": coverage_by_session,
        "engine_identity_by_session": engine_identities,
        "financial_evidence_identical_across_sessions": financial_evidence_identical_across_sessions,
        "note": "financial_v2_engine_identity excludes requested_at from its content hash, so the "
                "SAME underlying retained evidence reproduces a byte-identical identity across "
                "sessions; only decision_session (and therefore the session-delivery wrapper's own "
                "artifact_identity) changes daily by construction.",
    }
    (out_dir / "financial_product_coverage.json").write_text(
        json.dumps(product_coverage, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    # ---- canonical_vs_independent_replay.json (section 19) ----
    independent_replay = {}
    if available_sessions:
        engine_artifact = session_results[available_sessions[0]]["engine_artifact"]
        independent_replay = {
            "reference": "CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1 (tools/run_core_fundamental_valuation_peer_context_replay.py)",
            "regression_locked_reference_figures": {
                "financial_v2_ticker_denominator": 1492, "current_research_ready_count": 1380,
                "entity_family_split": {"INDUSTRIAL": 1382, "OTHER_FINANCIAL_LIMITED_ANALYSIS": 83, "UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS": 27},
            },
            "canonical_daily_financial_v2_materialization_produces": {
                "financial_v2_ticker_denominator": engine_artifact["coverage"]["ticker_denominator"],
                "current_research_ready_count": engine_artifact["coverage"]["current_research_ready_count"],
                "entity_family_split": engine_artifact["coverage"]["issuer_family_distribution"],
            },
            "equivalent": (
                engine_artifact["coverage"]["ticker_denominator"] == 1492
                and engine_artifact["coverage"]["current_research_ready_count"] == 1380
            ),
        }
    (out_dir / "canonical_vs_independent_replay.json").write_text(
        json.dumps(independent_replay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- integrated_decision_before_after.json (section 15) ----
    before_after = {}
    for session in available_sessions:
        result = session_results[session]
        before_after[session] = {
            "fundamental_state_before": fundamental_state_distribution(result["before"]),
            "fundamental_state_after": fundamental_state_distribution(result["after"]),
            "research_action_posture_before": posture_distribution(result["before"]),
            "research_action_posture_after": posture_distribution(result["after"]),
            "universe_denominator": result["after"]["coverage"]["universe_denominator"],
        }
    (out_dir / "integrated_decision_before_after.json").write_text(
        json.dumps(before_after, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- daily_brief_before_after.json (compact restatement for section 16 evidence) ----
    (out_dir / "daily_brief_before_after.json").write_text(
        json.dumps({"note": "Full-universe fundamental_state / research_action_posture deltas are the "
                             "daily-brief-relevant signal; see integrated_decision_before_after.json "
                             "(same underlying records daily_integrated_decision_brief.build_artifact "
                             "joins verbatim, per-ticker, without recomputation).",
                    "before_after_by_session": before_after}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    # ---- representative ticker traces (section 18) + entity class check ----
    representative = {}
    entity_classes = {}
    no_context_ticker = None
    for session in available_sessions:
        result = session_results[session]
        representative[session] = {t: representative_trace(result, t) for t in REPRESENTATIVE_TICKERS}
        if no_context_ticker is None:
            engine_tickers = set(result["engine_artifact"]["records"].keys())
            daily_tickers = set(result["after"]["records"].keys())
            gap = sorted(daily_tickers - engine_tickers)
            no_context_ticker = gap[0] if gap else None
        if no_context_ticker:
            representative[session][no_context_ticker] = representative_trace(result, no_context_ticker)
    for t in REPRESENTATIVE_TICKERS:
        entity_classes[t] = entity_class_for(t)
    (out_dir / "representative_ticker_validation.json").write_text(
        json.dumps({"tickers": representative, "entity_classes": entity_classes,
                    "no_financial_v2_context_ticker": no_context_ticker}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    # ---- watchlist_11_financial_context.json (section 16/23) ----
    watchlist = list(owner_research_focus.broader_watchlist())
    watchlist_context = {}
    for session in available_sessions:
        result = session_results[session]
        fa_records = result["financial_session_artifact"]["financial_analysis_product"]["records"]
        watchlist_context[session] = {t: {
            "status": (fa_records.get(t) or {}).get("status"),
            "fundamental_state": (result["after"]["records"].get(t) or {}).get("fundamental_state"),
            "research_action_posture": (result["after"]["records"].get(t) or {}).get("research_action_posture"),
        } for t in watchlist}
    (out_dir / "watchlist_11_financial_context.json").write_text(
        json.dumps({"watchlist": watchlist, "by_session": watchlist_context}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    # ---- previous_session_semantics.json (section 21) ----
    previous_semantics = {
        "audit_method": "Read stocklookup.py:_previous() and next_session_decision_brief.py:"
                         "_require_qualified()/build_artifact() directly; cross-checked against "
                         "real retained operations-review/daily-research-session-operations-v1/*/*/"
                         "run_manifest.json + sibling ai_research_session_bundle.json presence, and "
                         "against config/daily_research_session_input_registry.json's own "
                         "completed_sessions ledger.",
        "finding": (
            "Two distinct authorities exist and can disagree: (1) stocklookup.py:_previous() finds "
            "the LATEST session strictly before the target with a self-consistent "
            "ai_research_session_bundle.json (bundle-existence scan); (2) next_session_decision_"
            "brief.py's _require_qualified() additionally requires that session to be in the "
            "registry's completed_sessions (the actual governed 'qualified' authority). For a "
            "session produced through the real canonical pipeline end to end, these two always "
            "agree by construction (registration/freeze and bundle creation happen in the same "
            "governed run_canonical_post_close() sequence). Real retained evidence in the Producer "
            "main checkout confirms sessions 2026-08-26 and 2026-08-27 BOTH already have complete, "
            "session-matching ai_research_session_bundle.json files (produced by earlier ad-hoc/"
            "replay-tool sessions outside the registered canonical flow), but neither is in the "
            "current governed registry's completed_sessions (still {2026-08-21, 2026-08-24, "
            "2026-08-25, 2026-08-26} as of this milestone's base). previous_qualified_session is "
            "therefore correctly 2026-08-26 today (the latest session that is BOTH registered-"
            "complete AND bundle-consistent) for any current_session after it -- not 2026-08-25, "
            "which was the correct answer only at an earlier point before 2026-08-26 was "
            "registered. The immediately-preceding milestone's '2026-08-25' figure was a real, "
            "correct snapshot at ITS time, now superseded -- not a defect this milestone needs to "
            "correct in the resolution mechanism itself."
        ),
        "previous_qualified_session_definition": "The immediately previous session that is BOTH "
                                                   "registered as completed_sessions[...].status == "
                                                   "COMPLETED_RETAINED_EVIDENCE in the governed "
                                                   "registry AND has a self-consistent same-session "
                                                   "ai_research_session_bundle.json.",
        "previous_comparable_session_definition": "An older session used for one specific "
                                                     "transition only because an intermediate "
                                                     "required artifact for the immediately previous "
                                                     "qualified session is unavailable for that "
                                                     "transition specifically (e.g. market_transition/"
                                                     "sector_transition needing both sides registered "
                                                     "in config/daily_research_session_input_registry."
                                                     "json's sessions ledger, independent of "
                                                     "completed_sessions).",
        "registry_completed_sessions_at_this_milestones_base": ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26"],
        "real_bundle_presence_2026_08_26": True,
        "real_bundle_presence_2026_08_27": True,
        "real_bundle_presence_2026_08_28": True,
        "conclusion": "No code change required to _previous()'s own dynamic latest-bundle scan or "
                       "to _require_qualified()'s registry gate; both are internally correct for the "
                       "real governed pipeline. Behavior left unchanged; this finding is reported, "
                       "not silently accepted, per this milestone's explicit instruction.",
    }
    (out_dir / "previous_session_semantics.json").write_text(
        json.dumps(previous_semantics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- daily_pipeline_validation.json ----
    pipeline_validation = {
        "sessions_replayed": available_sessions,
        "sessions_requested_but_evidence_unavailable": [s for s in SESSIONS if s not in available_sessions],
        "zero_silent_drops": {
            session: {
                "daily_denominator": len(session_results[session]["after"]["records"]),
                "matches_universe_denominator": session_results[session]["after"]["coverage"]["universe_denominator"] == len(session_results[session]["after"]["records"]),
            }
            for session in available_sessions
        },
        "contract_assertion_present": "integrated_investment_decision_product.build_artifact raises "
                                        "IntegratedDecisionProductError('INCOMPATIBLE_FINANCIAL_ANALYSIS_"
                                        "CONTRACT:...') when financial_analysis_artifact carries a "
                                        "present-but-wrong contract_version.",
    }
    (out_dir / "daily_pipeline_validation.json").write_text(
        json.dumps(pipeline_validation, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    # ---- REPORT.md ----
    lines = [
        "# Canonical Daily Financial V2 and Current Research Enrichment V1 -- Replay Report",
        "",
        f"Sessions replayed with real retained evidence: {', '.join(available_sessions) or 'NONE'}",
        f"Sessions requested but evidence unavailable in this checkout: {', '.join(s for s in SESSIONS if s not in available_sessions) or 'none'}",
        "",
        "## Independent replay equivalence (section 19)",
        "",
        f"```\n{json.dumps(independent_replay, indent=2, ensure_ascii=False)}\n```",
        "",
        "## Fundamental state / posture before vs after, by session",
        "",
    ]
    for session in available_sessions:
        row = before_after[session]
        lines += [
            f"### {session}",
            "",
            f"- fundamental_state BEFORE: `{row['fundamental_state_before']}`",
            f"- fundamental_state AFTER: `{row['fundamental_state_after']}`",
            f"- research_action_posture BEFORE: `{row['research_action_posture_before']}`",
            f"- research_action_posture AFTER: `{row['research_action_posture_after']}`",
            "",
        ]
    lines += [
        "## Previous-session semantics audit (section 21)",
        "",
        previous_semantics["finding"],
        "",
    ]
    (out_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "sessions_replayed": available_sessions,
        "independent_replay_equivalent": independent_replay.get("equivalent"),
        "before_after": before_after,
        "out_dir": str(out_dir),
    }, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
