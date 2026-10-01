"""Bounded, read-only financial-peer integration acceptance over an accepted checkpoint."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canonical_daily_financial_v2_materialization as financial
import daily_session_level2_package as paths_module
import financial_analysis_product_projection as compact
import integrated_investment_decision_product as product
import market_wide_relative_volume_research as participation
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery
from canonical_post_close_pipeline import resolve_current_session_priority_queue
from replay_current_research_structural_conditions import changed_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--checkpoint-output", type=Path, required=True)
    parser.add_argument("--engine-input", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--session", choices=["2026-09-30"], required=True)
    args = parser.parse_args()
    retained, checkpoint, output = args.retained_root.resolve(), args.checkpoint_output.resolve(), args.output_root.resolve()
    if output == retained or retained in output.parents or output == checkpoint or checkpoint in output.parents:
        raise ValueError("OUTPUT_MUST_BE_EXTERNAL_AND_SEPARATE_FROM_ACCEPTED_CHECKPOINT")
    hashes = {}

    def load(path):
        raw = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    paths = paths_module.session_artifact_paths(retained, args.session)
    before = load(checkpoint / "integrated_investment_decision_product_artifact.json")
    checkpoint_summary = load(checkpoint / "replay_summary.json")
    for path, sha in checkpoint_summary["retained_input_hashes_unchanged"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
        hashes[path] = sha
    expected = "integrated_investment_decision_product/v1:a2caac22ad63b0fd5ecdadb12255bfff2abcb8db3b897e0cfe926fe92d76d12c"
    assert before["artifact_identity"] == expected
    assert product.content_identity(before)["artifact_identity"] == expected
    wrapper = load(paths["financial_analysis_product"])
    assert financial._identity(wrapper)["artifact_identity"] == wrapper["artifact_identity"]
    engine = load(args.engine_input)
    assert compact._identity(engine)["artifact_identity"] == engine["artifact_identity"] == wrapper["financial_v2_engine_identity"]
    # Reuse the already-qualified producer, not a new comparison engine or provider request.
    authority = financial.input_authority.resolve(retained)
    industry_path = authority.industry_snapshot_path
    if industry_path.is_file():
        hashes[str(industry_path)] = hashlib.sha256(industry_path.read_bytes()).hexdigest()
    peers = financial.build_peer_context(engine_artifact=engine, authority=authority)
    assert set(peers) == set(wrapper["engine_fundamental_peer_context"])
    # The retained corpus's provider/entity/period partition already satisfies the hardened key.
    # Numeric results and every source blocker must therefore be unchanged.
    for ticker, metrics in peers.items():
        for metric, entry in metrics.items():
            assert {k: v for k, v in entry.items() if k != "comparability_basis"} == wrapper["engine_fundamental_peer_context"][ticker][metric], (ticker, metric)
    upgraded = copy.deepcopy(wrapper)
    upgraded["engine_fundamental_peer_context"] = peers
    upgraded.update(financial._identity(upgraded))
    snapshot = load(paths["exact_session_snapshot"])
    stamp = before["requested_at"]
    queue, resolution = resolve_current_session_priority_queue(
        args.session, opportunity=load(paths["opportunity_prioritization"]), triage=load(paths["session_triage"]))
    assert queue is not None, resolution
    kwargs = dict(session=args.session, requested_at=stamp,
        technical_structure_artifact=load(checkpoint / "market_structure_breakout_v3_projection_artifact.json"),
        financial_analysis_artifact=wrapper["financial_analysis_product"],
        current_valuation_artifact=load(paths["current_valuation_evaluated"]),
        relative_volume_artifact=participation.build_artifact(candidates=sorted(snapshot["records"]), records=snapshot["records"], session=args.session, requested_at=stamp),
        market_sector_artifact=load(paths["sector_leadership"]),
        legacy_decision_artifact=load(paths["opportunity_prioritization"]), priority_queue_artifact=queue,
        momentum_artifact=load(paths["tactical_momentum_context"]),
        tactical_confirmation_artifact=load(paths["tactical_confirmation_context"]),
        tactical_boundaries_artifact=load(paths["tactical_confirmation_invalidation_boundaries"]),
        corporate_intelligence_artifact=load(paths["corporate_intelligence_axis"]),
        technical_coverage_disposition_artifact=load(paths["technical_coverage_disposition"]),
        operational_fundamental_integration_artifact=load(paths["operational_fundamental_context_integration"]),
        liquidity_research_artifact=load(paths["liquidity_research"]),
        entity_applicability_artifact=load(paths["current_research_entity_applicability"]))
    # A single nocontext build verifies the new integration has no compatibility-side effect.
    assert product.build_artifact(**kwargs)["artifact_identity"] == expected
    kwargs["financial_peer_materialization_artifact"] = upgraded
    after = product.build_artifact(**kwargs)
    assert product.build_artifact(**kwargs)["artifact_identity"] == after["artifact_identity"]
    assert set(before["records"]) == set(after["records"]) == set(wrapper["financial_analysis_product"]["records"])
    changes = Counter()
    statuses = Counter()
    metric_statuses = Counter()
    explanation_changed = 0
    usable_issuers = []
    delivered = {}
    allowed = {"financial_peer_context", "evidence_axes.FUNDAMENTAL.context.financial_peer_context",
               "current_research_decision_input.dimensions.FUNDAMENTAL.financial_peer_context",
               "source_identities.financial_peer_materialization_identity", "decision_identity",
               "current_research_decision_input.provenance.decision_identity"}
    for ticker, old in before["records"].items():
        new = after["records"][ticker]
        diff = set(changed_paths(old, new))
        assert diff <= allowed, (ticker, diff - allowed)
        changes.update(diff)
        ctx = new["financial_peer_context"]
        assert ctx == new["evidence_axes"]["FUNDAMENTAL"]["context"]["financial_peer_context"]
        assert ctx == new["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["financial_peer_context"]
        statuses[ctx["status"]] += 1
        metric_statuses.update(m["status"] for m in ctx["metrics"].values())
        if ctx["usable_metric_count"]:
            assert ctx["issuer_type"] == "corporate"
            usable_issuers.append(ticker)
            explanation_changed += 1
        for field in ("research_action_posture", "counter_thesis", "why_now", "fundamental_synthesis",
                      "valuation_context_summary", "financial_composite_context", "evidence_currency",
                      "exact_capabilities_unavailable", "authority_boundary", "evidence_axis_coherence"):
            assert new[field] == old[field], (ticker, field)
        view = project_integrated_decision_for_ai_delivery(new, integrated_identity=after["artifact_identity"])
        assert view["financial_peer_context"] == ctx
        assert view["is_actionable"] is False
        delivered[ticker] = view
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in hashes.items())
    summary = {"session": args.session, "input_denominator": len(before["records"]), "output_denominator": len(after["records"]),
               "eligible_corporate_peer_denominator": len(usable_issuers), "eligible_tickers": usable_issuers,
               "engine_peer_denominator": len(peers),
               "governed_peer_record_denominator": sum(bool(r["financial_peer_context"]["metrics"]) for r in after["records"].values()),
               "context_status_counts": dict(statuses), "metric_status_counts": dict(metric_statuses),
               "explanation_enriched_records": explanation_changed, "no_usable_peer_enrichment_records": len(after["records"]) - explanation_changed,
               "explicit_context_status_records": len(after["records"]), "posture_changes": 0, "counter_thesis_changes": 0,
               "why_now_text_changes": 0, "silent_drops": 0, "unexplained_changes": 0,
               "before_identity": expected, "after_identity": after["artifact_identity"],
               "source_materialization_identity": upgraded["artifact_identity"], "deterministic_identity": True,
               "source_peer_numeric_and_blocker_results_unchanged": True, "attributed_changed_fields": dict(changes),
               "retained_input_sha256": hashes, "provider_calls": 0, "authority_effect": "NONE"}
    representatives = ["ACC", "HPG", "AAA", "F88", "VCB", "SSI", "AAM"]
    small = next((t for t, r in after["records"].items() if r["financial_peer_context"]["issuer_type"] == "corporate"
                  and any(m["status"] == "INSUFFICIENT_PEER_COUNT" for m in r["financial_peer_context"]["metrics"].values())), None)
    if small:
        representatives.append(small)
    period_blocked = next((t for t, r in after["records"].items() if r["financial_peer_context"]["issuer_type"] == "corporate"
                          and any("MISSING_SAME_PROVIDER_TICKER_PERIOD_SCOPE_REPRESENTATION" in m.get("reason", [])
                                  for m in r["financial_peer_context"]["metrics"].values())), None)
    if period_blocked:
        representatives.append(period_blocked)
    traces = {t: {"posture_before": before["records"][t]["research_action_posture"],
                  "posture_after": after["records"][t]["research_action_posture"],
                  "fundamental_state": after["records"][t]["fundamental_state"],
                  "financial_peer_context": after["records"][t]["financial_peer_context"]} for t in representatives if t in after["records"]}
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [("financial_peer_replay_summary.json", summary), ("financial_peer_representative_traces.json", traces),
                        ("financial_peer_materialization_artifact.json", upgraded),
                        ("integrated_investment_decision_product_artifact.json", after),
                        ("integrated_decision_delivery_records.json", delivered)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"retained_input_sha256", "eligible_tickers", "attributed_changed_fields"}}))


if __name__ == "__main__":
    main()
