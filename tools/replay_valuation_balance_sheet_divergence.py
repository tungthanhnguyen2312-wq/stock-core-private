"""Retained-only same-cohort divergence acceptance; no Daily, providers or evidence writes."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import canonical_daily_financial_v2_materialization as material
from stocklookup_core.financial import financial_analysis_engine_v2 as engine_owner
from stocklookup_core.financial import financial_v2_current_input_authority as authority_owner
from stocklookup_core.valuation import current_research_valuation_context as valuation
from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import content_identity as raw_identity
from stocklookup_core.decision import integrated_investment_decision_product as decision
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery, _decision_card
from stocklookup_core.decision import current_research_decision_packet as packet_owner


def load(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf8") as handle:
        return json.load(handle)


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def summarize(records, names):
    rows = [records[t] for t in sorted(names)]
    context_only = {"UNKNOWN", "NOT_APPLICABLE", "MID_RANGE_PB_WITH_FINANCIAL_CONTEXT",
        "HIGH_PB_INSUFFICIENT_FINANCIAL_EVIDENCE", "LOW_PB_INSUFFICIENT_FINANCIAL_EVIDENCE", "INSUFFICIENT_FINANCIAL_EVIDENCE"}
    return {"issuers": len(rows), "status": dict(Counter(r["status"] for r in rows)),
        "assessments": dict(Counter(r["assessment"] for r in rows)),
        "specific_support_or_counterthesis_findings": sum(r["assessment"] not in context_only for r in rows),
        "paired_issuers": sum(r["valid_paired_comparisons"] > 0 for r in rows),
        "valid_paired_comparisons": sum(r["valid_paired_comparisons"] for r in rows),
        "paired_peer_comparisons": sum(r["status"] == "AVAILABLE" and m["peer_comparison_usable"] for r in rows for m in r["financial_measures"].values()),
        "paired_by_measure": {f: sum(r["status"] == "AVAILABLE" and r["financial_measures"][f]["status"] == "AVAILABLE" for r in rows)
                              for f in valuation.DIVERGENCE_FEATURES},
        "measure_exclusion_reason_occurrences": dict(Counter(code for r in rows for codes in r["material_gaps"].values() for code in codes)),
        "issuer_gap_reason_counts": dict(Counter(code for r in rows for code in
            {c for codes in r["material_gaps"].values() for c in codes})),
        "unknown_issuer_reason_counts": dict(Counter(code for r in rows if r["status"] == "UNKNOWN" for code in
            {c for codes in r["material_gaps"].values() for c in codes}))}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retained-root", required=True, type=Path)
    p.add_argument("--valuation-engine", required=True, type=Path, help="Exact original engine named by the retained evaluated valuation.")
    p.add_argument("--financial-engine", required=True, type=Path, help="Completed scaleout engine; numerical-feature parity is mandatory.")
    p.add_argument("--evaluated-valuation", required=True, type=Path)
    p.add_argument("--raw-valuation", required=True, type=Path)
    p.add_argument("--session", required=True)
    p.add_argument("--opportunity-artifact", type=Path, help="Optional exact-session retained opportunity input for research-packet acceptance.")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    root, output = args.retained_root.resolve(), args.output.resolve()
    if output.exists() or output == root or root in output.parents:
        raise ValueError("OUTPUT_MUST_BE_NEW_OUTSIDE_RETAINED_ROOT")
    authority = authority_owner.resolve(root)
    paths = [args.valuation_engine.resolve(), args.financial_engine.resolve(), args.evaluated_valuation.resolve(),
        args.raw_valuation.resolve(), authority.industry_snapshot_path, authority.semantics_artifact_path,
        authority.semantics_facts_path, authority.feature_store_artifact_path, authority.feature_store_records_path,
        authority.classification_diagnostics_path]
    if args.opportunity_artifact:
        paths.append(args.opportunity_artifact.resolve())
    if any(output == path or output in path.parents or output == path.parent for path in paths):
        raise ValueError("OUTPUT_OVERLAPS_INPUTS")
    hashes = {str(path): sha(path) for path in paths}
    old_engine, financial, evaluated, raw = map(load, paths[:4])
    for engine in (old_engine, financial):
        assert engine_owner.content_identity(engine)["artifact_identity"] == engine["artifact_identity"]
        assert engine["source_identities"]["period_semantics_identity"] == authority.expected_semantics_identity
    assert material._identity(evaluated)["artifact_identity"] == evaluated["artifact_identity"]
    assert raw_identity(raw)["artifact_identity"] == raw["artifact_identity"]
    assert raw["valuation_session"] == args.session
    assert evaluated["source_valuation_identity"] == raw["artifact_identity"]
    assert evaluated["source_financial_v2_identity"] == old_engine["artifact_identity"]
    assert set(old_engine["records"]) == set(financial["records"])
    for ticker, record in old_engine["records"].items():
        assert record["features"] == financial["records"][ticker]["features"], ticker
    # New local derivative, with an explicit verified cross-version numerical binding.
    # Original artifact/files and original method objects remain unchanged.
    before = copy.deepcopy(evaluated)
    before["source_financial_v2_identity"] = financial["artifact_identity"]
    before["numerical_source_binding"] = {"original_evaluated_identity": evaluated["artifact_identity"],
        "original_financial_engine_identity": old_engine["artifact_identity"],
        "current_financial_engine_identity": financial["artifact_identity"],
        "basis": "ALL_1492_NUMERICAL_FEATURE_OBJECTS_IDENTICAL_NO_VALUATION_RECOMPUTATION"}
    before.update(material._identity(before))
    names = set(before["records"])
    wrapper = material.build_session_artifact(root=root, decision_session=args.session,
        product_tickers=sorted(names), requested_at=args.session+"T16:00:00+07:00", authority=authority, engine_artifact=financial)
    peers = wrapper["engine_fundamental_peer_context"]
    candidates = {t for t in names if before["records"][t].get("methods", {}).get(valuation.PB_CURRENT_RESEARCH, {}).get("status") in {"READY", "RESEARCH_USABLE"}
        and any(m.get("status") == "READY_RESEARCH_ONLY" for m in peers.get(t, {}).values())}
    assert len(candidates) == 337, "CANDIDATE_COHORT_DRIFT_MUST_BE_EXPLAINED"
    after = copy.deepcopy(before)
    material.attach_balance_sheet_divergence(after, financial_materialization=wrapper,
        industry_by_ticker=material.load_industry_by_ticker(authority), decision_session=args.session, raw_valuation_artifact=raw)
    assert after["records"] == evaluated["records"]
    for key in before:
        if key not in {"artifact_identity", "artifact_sha256"}:
            assert before[key] == after[key], key
    kwargs = dict(session=args.session, requested_at=args.session+"T16:00:00+07:00",
        technical_structure_artifact={"records": {}}, financial_analysis_artifact=wrapper["financial_analysis_product"],
        financial_peer_materialization_artifact=wrapper)
    baseline_product = decision.build_artifact(**kwargs, current_valuation_artifact=before)
    result_product = decision.build_artifact(**kwargs, current_valuation_artifact=after)
    research_packet = packet_owner.build_artifact(opportunity=load(args.opportunity_artifact), integrated_decision=result_product) if args.opportunity_artifact else None
    context = after[valuation.DIVERGENCE_MEMBER]
    output.mkdir(parents=True)
    with gzip.open(output/"research-records.jsonl.gz", "wt", encoding="utf8") as handle:
        for ticker in sorted(names):
            old, new = baseline_product["records"][ticker], result_product["records"][ticker]
            assert "valuation_balance_sheet_divergence" not in old
            for field in ("research_action_posture", "fundamental_state", "fundamental_synthesis", "valuation_methods", "evidence_axis_coherence"):
                assert old[field] == new[field], (ticker, field)
            delivered = project_integrated_decision_for_ai_delivery(new)
            expected = new["valuation_balance_sheet_divergence"]
            assert delivered["valuation_balance_sheet_divergence"] == expected
            assert delivered["current_research_decision_input"]["dimensions"]["VALUATION"]["balance_sheet_divergence"] == expected
            assert delivered["evidence_axes"]["VALUATION"]["context"]["balance_sheet_divergence"] == expected
            assert _decision_card(ticker, new, None, source_session=args.session)["valuation"]["balance_sheet_divergence"] == expected
            if research_packet and ticker in research_packet["records"]:
                assert research_packet["records"][ticker]["components"]["valuation_balance_sheet_divergence"] == expected
            handle.write(json.dumps(expected, ensure_ascii=True)+"\n")
    for path in paths:
        assert sha(path) == hashes[str(path)], path
    summary = {"session": args.session, "before": {"issuers": len(names), "candidate_issuers": len(candidates),
        "combined_divergence_cases": 0, "valid_paired_divergence_comparisons": 0},
        "result": summarize(context["records"], names), "candidate_result": summarize(context["records"], candidates),
        "candidate_tickers": sorted(candidates), "input_hashes_unchanged": hashes,
        "numerical_source_binding": before["numerical_source_binding"],
        "derivative_before_identity": before["artifact_identity"], "derivative_after_identity": after["artifact_identity"],
        "divergence_identity": context["artifact_identity"], "existing_valuation_methods_and_numerical_features_unchanged": True,
        "policy_and_posture_unchanged": True, "decision_ai_delivery_verified": True,
        "compact_card_delivery_verified": True, "research_packet_issuers_verified": len(research_packet["records"]) if research_packet else 0,
        "mode": "ISOLATED_RETAINED_FINANCIAL_JOIN_NOT_REWRITTEN_DAILY_OR_T0", "new_metric_input_coverage": 0,
        "provider_daily_runtime_writes": False}
    (output/"acceptance.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n", encoding="utf8")
    print(json.dumps({"issuers": len(names), "candidates": len(candidates),
        "paired_issuers": summary["result"]["paired_issuers"],
        "paired_observations": summary["result"]["valid_paired_comparisons"],
        "specific_findings": summary["result"]["specific_support_or_counterthesis_findings"],
        "research_packet_issuers_verified": summary["research_packet_issuers_verified"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
