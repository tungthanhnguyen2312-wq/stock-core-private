"""Read-only, exact-session retained structural-condition integration replay."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_session_level2_package as paths_module
import integrated_investment_decision_product as product
import market_structure_breakout_product_projection as projection
import market_wide_relative_volume_research as participation
from canonical_post_close_pipeline import resolve_current_session_priority_queue


def changed_paths(before, after, prefix=""):
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in before or key not in after:
                yield path
            else:
                yield from changed_paths(before[key], after[key], path)
    elif before != after:
        yield prefix


def replay_delivery(retained: Path, output: Path, session: str):
    from ai_research_session_delivery import project_integrated_decision_for_ai_delivery as project
    before_path = paths_module.session_artifact_paths(retained, session)["integrated_investment_decision_product"]
    raw = before_path.read_bytes()
    before = json.loads(raw)
    after = json.loads((output / "integrated_investment_decision_product_artifact.json").read_bytes())
    base_source = subprocess.check_output(["git", "show", "59580f6cda300dce8013af284d2ce11e026e3029:ai_research_session_delivery.py"], text=True, encoding="utf-8")
    namespace = {"__name__": "retained_base_delivery"}
    exec(compile(base_source, "retained_base_delivery", "exec"), namespace)
    base_project = namespace["project_integrated_decision_for_ai_delivery"]
    delivered = {}
    dropped = Counter()
    for ticker, record in after["records"].items():
        view = project(record, integrated_identity=after["artifact_identity"])
        legacy_view = base_project(record, integrated_identity=after["artifact_identity"])
        for role in ["trigger", "invalidation"]:
            assert view[role]["condition"] == record[role]["condition"]
            assert view[role]["watchlist_condition"] == record[role]["watchlist_condition"]
            stripped = {k:v for k,v in view[role].items() if k not in {"condition", "watchlist_condition"}}
            assert stripped == legacy_view[role]
            legacy_view[role] = view[role]
            old = base_project(before["records"][ticker], integrated_identity=before["artifact_identity"])
            dropped[role] += int("condition" not in old[role] and "condition" in before["records"][ticker][role])
        assert legacy_view == view
        assert view["is_actionable"] is False
        delivered[ticker] = view
    assert before_path.read_bytes() == raw
    summary = {"session": session, "input_denominator": len(after["records"]), "output_denominator": len(delivered),
               "previously_dropped_conditions": dict(dropped), "all_conditions_and_reasons_preserved": True,
               "other_projection_fields_unchanged": True, "retained_input_unchanged": True,
               "retained_input_sha256": hashlib.sha256(raw).hexdigest(), "provider_calls": 0, "authority_effect": "NONE",
               "source_identity": after["artifact_identity"]}
    (output / "integrated_decision_delivery_records.json").write_text(json.dumps(delivered, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
    (output / "delivery_replay_summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--delivery-only", action="store_true")
    args = parser.parse_args()
    retained = args.retained_root.resolve(); output = args.output_root.resolve()
    if output == retained or retained in output.parents:
        raise ValueError("OUTPUT_MUST_BE_OUTSIDE_RETAINED_ROOT")
    if args.delivery_only:
        replay_delivery(retained, output, args.session)
        return
    paths = paths_module.session_artifact_paths(retained, args.session)
    hashes = {}

    def load(path):
        raw = path.read_bytes(); hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    before = load(paths["integrated_investment_decision_product"])
    structure = load(paths["technical_structure_context"])
    old_projection = load(paths["market_structure_breakout_v3_projection"])
    stamp = before.get("requested_at") or f"{args.session}T15:00:00+07:00"
    new_projection = projection.build_artifact(technical_structure=structure, requested_at=stamp)
    snapshot = load(paths["exact_session_snapshot"])
    relative_volume = participation.build_artifact(candidates=sorted(snapshot["records"]), records=snapshot["records"], session=args.session, requested_at=stamp)
    operations_dir = retained / "operations-review" / "daily-research-session-operations-v1" / args.session
    # Exactly one frozen bundle is required; never recursively discover substitutes.
    queue_paths = list(operations_dir.glob("*/daily_opportunity_decision_queue_artifact.json"))
    if len(queue_paths) != 1:
        raise ValueError("EXACT_RETAINED_DAILY_QUEUE_AMBIGUOUS_OR_ABSENT")
    kwargs = dict(session=args.session, requested_at=stamp,
        technical_structure_artifact=old_projection,
        financial_analysis_artifact=load(paths["financial_analysis_product"])["financial_analysis_product"],
        current_valuation_artifact=load(paths["current_valuation_evaluated"]),
        relative_volume_artifact=relative_volume,
        market_sector_artifact=load(paths["sector_leadership"]),
        legacy_decision_artifact=load(paths["opportunity_prioritization"]),
        priority_queue_artifact=load(queue_paths[0]),
        momentum_artifact=load(paths["tactical_momentum_context"]),
        tactical_confirmation_artifact=load(paths["tactical_confirmation_context"]),
        tactical_boundaries_artifact=load(paths["tactical_confirmation_invalidation_boundaries"]),
        corporate_intelligence_artifact=load(paths["corporate_intelligence_axis"]),
        technical_coverage_disposition_artifact=load(paths["technical_coverage_disposition"]),
        operational_fundamental_integration_artifact=load(paths["operational_fundamental_context_integration"]),
        liquidity_research_artifact=load(paths["liquidity_research"]),
        entity_applicability_artifact=load(paths["current_research_entity_applicability"]))
    kwargs["priority_queue_artifact"], queue_resolution = resolve_current_session_priority_queue(
        args.session, opportunity=kwargs["legacy_decision_artifact"], triage=load(paths["session_triage"]))
    if kwargs["priority_queue_artifact"] is None:
        raise ValueError(f"PRIORITY_RESOLUTION_FAILED:{queue_resolution}")
    # Reproduce the old product with its own base implementation, read from Git.
    base_source = subprocess.check_output(["git", "show", "59580f6cda300dce8013af284d2ce11e026e3029:integrated_investment_decision_product.py"], text=True, encoding="utf-8")
    namespace = {"__name__": "retained_base_product"}
    exec(compile(base_source, "retained_base_product", "exec"), namespace)
    started = time.perf_counter()
    reproduced = namespace["build_artifact"](**kwargs)
    baseline_elapsed = time.perf_counter() - started
    if reproduced["artifact_identity"] != before["artifact_identity"]:
        print("BASELINE_TOP_LEVEL_DIFFERENCES", [k for k in set(before) | set(reproduced) if before.get(k) != reproduced.get(k)])
        differences = Counter()
        for ticker, old in before["records"].items():
            for key in set(old) | set(reproduced["records"].get(ticker, {})):
                if old.get(key) != reproduced["records"].get(ticker, {}).get(key):
                    differences[key] += 1
        print("BASELINE_RECORD_DIFFERENCES", dict(differences))
        print("BASELINE_EXAMPLE_SOURCE", before["records"]["HPG"].get("source_identities"), reproduced["records"]["HPG"].get("source_identities"))
        print("BASELINE_SOURCE_DIFFERENCES", before.get("source_artifacts"), reproduced.get("source_artifacts"))
        raise ValueError(f"BASELINE_IDENTITY_MISMATCH:{reproduced['artifact_identity']}:{before['artifact_identity']}")
    kwargs["technical_structure_artifact"] = new_projection
    started = time.perf_counter()
    after = product.build_artifact(**kwargs)
    corrected_elapsed = time.perf_counter() - started
    assert product.build_artifact(**kwargs)["artifact_identity"] == after["artifact_identity"]
    assert set(before["records"]) == set(after["records"])
    invariant_fields = ["research_action_posture", "fundamental_state", "tactical_phase", "evidence_currency", "exact_capabilities_unavailable"]
    attributed_changes = Counter()
    allowed = (
        "trigger.condition.", "trigger.watchlist_condition", "invalidation.condition.",
        "invalidation.watchlist_condition", "invalidation.invalidation_method", "decision_identity",
        "evidence_axes.TACTICAL_STRUCTURE.lineage.source_artifact_identity",
        "current_research_decision_input.dimensions.TECHNICAL.components.trigger.condition_",
        "current_research_decision_input.dimensions.TECHNICAL.components.invalidation.condition_",
        "current_research_decision_input.dimensions.TECHNICAL.components.invalidation.method",
        "current_research_decision_input.provenance.decision_identity",
        "current_research_decision_input.synthesis.confirms.condition_identity",
        "current_research_decision_input.synthesis.invalidates.condition_identity",
        "current_research_decision_input.synthesis.invalidates.method",
        "valuation_context_summary.status", "valuation_context_summary.unavailable_reason_codes",
        "evidence_axes.VALUATION.state", "evidence_axes.VALUATION.fitness", "evidence_axes.VALUATION.blocker_reason_codes",
        "current_research_decision_input.dimensions.VALUATION.reason_codes",
        "current_research_decision_input.synthesis.missing_primary_factors.VALUATION",
        "valuation_context_summary.own_history_state", "valuation_context_summary.own_history_reason_codes",
        "evidence_axes.VALUATION.context.own_history_state", "evidence_axes.VALUATION.supporting_reason_codes",
        "evidence_axes.VALUATION.contradicting_reason_codes", "counter_thesis",
        "financial_composite_context.joined_axes.valuation_own_history_state",
        "financial_composite_context.supporting_reason_codes", "financial_composite_context.contradicting_reason_codes",
        "current_research_decision_input.synthesis.constructive_reason_codes",
        "current_research_decision_input.synthesis.weak_reason_codes",
        "market_sector_context.", "evidence_axes.MARKET_SECTOR.context.",
        "evidence_axes.MARKET_SECTOR.blocker_reason_codes",
    )
    for ticker, old in before["records"].items():
        new = after["records"][ticker]
        assert new["counter_thesis"] == [code for code in old["counter_thesis"] if code != "RATIOS_ELEVATED_VS_OWN_HISTORICAL_RANGE"], ticker
        for key, removed in [("supporting_reason_codes", "RATIOS_LOW_VS_OWN_HISTORICAL_RANGE"),
                             ("contradicting_reason_codes", "RATIOS_ELEVATED_VS_OWN_HISTORICAL_RANGE")]:
            assert new["financial_composite_context"][key] == [code for code in old["financial_composite_context"][key] if code != removed], (ticker, key)
        assert new["financial_composite_context"]["financial_composite_state"] == old["financial_composite_context"]["financial_composite_state"], ticker
        assert new["valuation_context_summary"]["peer_relative_state"] == old["valuation_context_summary"]["peer_relative_state"], ticker
        assert new["valuation_context_summary"]["own_history_state"] == "UNAVAILABLE", ticker
        sector = ((kwargs["market_sector_artifact"].get("ticker_contexts") or {}).get(ticker) or {}).get("sector_leadership_context") or {}
        assert new["market_sector_context"]["sector_leadership"] == (sector.get("leadership_state") or "UNKNOWN"), ticker
        assert new["market_sector_context"]["market_regime"] == old["market_sector_context"]["market_regime"], ticker
        assert new["evidence_axes"]["MARKET_SECTOR"]["fitness"] == old["evidence_axes"]["MARKET_SECTOR"]["fitness"], ticker
        assert new["market_sector_context"]["sector_group_key"] == sector.get("group_key"), ticker
        assert new["market_sector_context"]["sector_group_coverage_ratio"] == sector.get("group_coverage_ratio"), ticker
        if old["valuation_context_summary"]["status"] != new["valuation_context_summary"]["status"]:
            assert old["current_research_decision_input"]["dimensions"]["VALUATION"]["evidence_class"] == "PE_NOT_MEANINGFUL_ONLY", ticker
            assert old["valuation_context_summary"]["status"] == "AVAILABLE" and new["valuation_context_summary"]["status"] == "PARTIAL", ticker
        changes = list(changed_paths(old, after["records"][ticker]))
        assert all(path.startswith(allowed) for path in changes), (ticker, changes)
        attributed_changes.update(changes)
        assert old["authority_boundary"] == after["records"][ticker]["authority_boundary"]
        for field in invariant_fields:
            assert old.get(field) == after["records"][ticker].get(field), (ticker, field)
        for role in ["trigger", "invalidation"]:
            new = after["records"][ticker][role]
            assert old[role]["condition"] == new["watchlist_condition"], (ticker, role, "watchlist preservation")
            if new["condition"]["status"] == "MACHINE_EVALUABLE":
                assert new["condition"]["reference_level"] == new[f"{role}_level"]
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in hashes.items())
    summary = {"session": args.session, "input_denominator": len(before["records"]), "output_denominator": len(after["records"]),
        "baseline_identity": before["artifact_identity"], "output_identity": after["artifact_identity"],
        "baseline_reproduced_exactly": True, "deterministic": True, "retained_input_hashes_unchanged": hashes,
        "invariant_fields": invariant_fields, "authority_effect": "NONE", "provider_calls": 0,
        "attributed_changed_fields": dict(attributed_changes), "unexplained_changes": 0,
        "elapsed_seconds": {"base_build": baseline_elapsed, "corrected_build": corrected_elapsed},
        "decision_identities_changed": sum(r["decision_identity"] != before["records"][t]["decision_identity"] for t,r in after["records"].items()),
        "distributions": {}, "traces": {}}
    for role in ["trigger", "invalidation"]:
        summary["distributions"][role] = {label: dict(Counter(r[role]["condition"]["status"] for r in artifact["records"].values())) for label,artifact in [("before",before),("after",after)]}
    for field in ["research_action_posture", "tactical_phase", "evidence_currency"]:
        summary["distributions"][field] = dict(Counter(r[field] for r in after["records"].values()))
    summary["distributions"]["entity_applicability"] = dict(Counter(
        json.dumps(r.get("entity_class") or r.get("entity_type") or r.get("issuer_type"), sort_keys=True)
        for r in kwargs["entity_applicability_artifact"]["records"].values()))
    summary["distributions"]["fundamental_state"] = dict(Counter(r["fundamental_state"] for r in after["records"].values()))
    summary["distributions"]["valuation_summary_status"] = {label: dict(Counter(
        r["valuation_context_summary"]["status"] for r in artifact["records"].values()))
        for label, artifact in [("before", before), ("after", after)]}
    summary["distributions"]["valuation_own_history_state"] = {label: dict(Counter(
        r["valuation_context_summary"]["own_history_state"] for r in artifact["records"].values()))
        for label, artifact in [("before", before), ("after", after)]}
    summary["spurious_valuation_history_counters_removed"] = sum(
        "RATIOS_ELEVATED_VS_OWN_HISTORICAL_RANGE" in r["counter_thesis"] for r in before["records"].values())
    summary["distributions"]["sector_leadership"] = {label: dict(Counter(
        r["market_sector_context"]["sector_leadership"] for r in artifact["records"].values()))
        for label, artifact in [("before", before), ("after", after)]}
    summary["distributions"]["sector_leadership_status"] = dict(Counter(
        r["market_sector_context"]["sector_leadership_status"] for r in after["records"].values()))
    summary["distributions"]["fundamental_freshness"] = dict(Counter(
        ((r["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"].get("freshness") or {}).get("freshness_status"))
        for r in after["records"].values()))
    summary["distributions"]["dimension_states"] = {dimension: dict(Counter(
        r["current_research_decision_input"]["dimensions"][dimension]["state"] for r in after["records"].values()))
        for dimension in ["TECHNICAL", "FUNDAMENTAL", "VALUATION", "CORPORATE", "LIQUIDITY"]}
    for ticker in ["HPG", "VCB", "SSI", "POW", "AAA"]:
        summary["traces"][ticker] = {label: {field: artifact["records"][ticker].get(field) for field in ["research_action_posture", "trigger", "invalidation"]} for label,artifact in [("before",before),("after",after)]}
    output.mkdir(parents=True, exist_ok=True)
    for name,value in [("replay_summary.json",summary),("integrated_investment_decision_product_artifact.json",after),("market_structure_breakout_v3_projection_artifact.json",new_projection)]:
        (output/name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+"\n",encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ["input_denominator", "output_denominator", "baseline_reproduced_exactly", "decision_identities_changed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
