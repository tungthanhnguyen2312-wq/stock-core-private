"""Retained 2026-09-24 proof for FINANCIAL_V2_ANALYSIS_INPUT_INTEGRITY_V1.

``prove`` runs the real Daily Integrated Decision assembly (``run_current_research_decision_
convergence_proof assemble``) three times over byte-copied retained inputs under the audit-hook
write guard: once under the P/B checkpoint code (baseline), twice under this checkout (after,
rerun). ``summarize`` then derives the proof from that work root alone -- feature recovery,
downstream decision classes, P/B regression, peer statement scope, freshness and the three
denominators -- so rerunning it over the same work root must reproduce the artifact identity.
No provider, runtime store, publication or pointer is touched.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_daily_financial_v2_materialization as fin_v2_material
import current_research_valuation_context as valuation_context
import daily_session_level2_package as level2
import stocklookup_core.financial.financial_v2_current_input_authority as financial_authority
from operational_fundamental_context_integration import MAX_COMPLETED_QUARTER_LAG
from opportunity_axis_freshness import classify_financial_period_freshness
import provider_financial_monetary_basis_verdict as verdict_pin
from tools import current_research_capability_map as capability
from tools import run_current_research_decision_convergence_proof as convergence

CONTRACT = "financial_v2_analysis_input_integrity_proof/v1"
SESSION = "2026-09-24"
BASELINE_COMMIT = "4c46328ad1949c9643afee746eacabf0c16745c8"
WORKSPACE = Path("C:/Projects/StockLookup")
EXPECTED_WORK_ROOT = WORKSPACE / "tmp" / "fv2-input-integrity-proof-work"
EXPECTED_OUTPUT_DIR = WORKSPACE / "operations-review" / "financial-v2-analysis-input-integrity-v1-20260924"
PB_PROOF_DIR = WORKSPACE / "operations-review" / "current-research-book-value-valuation-v1-20260924"
PB_METHOD = "P/B_CURRENT_RESEARCH"
RUNS = ("baseline", "after", "rerun")
ATTEMPTED, OFFICIAL, PRICED = "ATTEMPTED_COHORT", "OFFICIAL_RESEARCH_SCOPE", "PRICED_OFFICIAL_SCOPE"
FEATURE_GROUPS = {
    "margins": ("net_margin", "pbt_margin", "gross_margin", "ttm_net_margin", "ttm_pbt_margin",
                "net_margin_direction", "gross_margin_direction"),
    "revenue_earnings": ("net_income_sign", "revenue_ttm", "profit_before_tax_ttm", "net_income_ttm"),
    "growth": ("revenue_qoq", "profit_before_tax_qoq", "net_income_qoq", "revenue_same_quarter_yoy",
               "profit_before_tax_same_quarter_yoy", "net_income_same_quarter_yoy", "revenue_ytd_yoy",
               "net_income_ytd_yoy", "revenue_ttm_yoy", "profit_before_tax_ttm_yoy", "net_income_ttm_yoy"),
    "cash_flow_quality": ("operating_cash_flow_sign", "operating_cash_flow_qoq", "operating_cash_flow_same_quarter_yoy",
                          "operating_cash_flow_ttm", "operating_cash_flow_ttm_yoy", "cfo_to_net_income",
                          "cfo_to_net_income_ttm", "free_cash_flow_proxy", "free_cash_flow_proxy_direction"),
    "balance_sheet_leverage": ("equity_to_assets", "cash_to_assets", "debt_to_equity", "debt_to_assets",
                               "debt_to_equity_direction", "equity_to_assets_direction", "current_ratio",
                               "net_working_capital", "assets_yoy", "equity_yoy", "cash_yoy"),
    "profitability_quality": ("same_provider_roe_avg_equity", "same_provider_roa_avg_assets",
                              "same_provider_roe_eop_proxy", "same_provider_roa_eop_proxy",
                              "mixed_provider_roa_proxy", "mixed_provider_asset_turnover_proxy"),
}
SANITY = ("HPG", "FPT", "VNM", "MWG", "GAS", "PVD", "KTT", "FIR", "ACB", "SSI")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(convergence.canonical(value) + b"\n")


def _counts(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _transitions(pairs: Iterable[tuple[Any, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(f"{a} -> {b}" for a, b in pairs if a != b).items()))


def _evidence_paths(producer_root: Path) -> list[Path]:
    authority = financial_authority.resolve(ROOT)
    verdict = verdict_pin.resolve(ROOT)
    paths = [authority.semantics_artifact_path, authority.semantics_facts_path, authority.feature_store_artifact_path,
             authority.feature_store_records_path, authority.classification_diagnostics_path,
             authority.industry_snapshot_path]
    for relative in verdict["input_sha256"]:
        paths.append((producer_root.parent / "dashboard-runtime" / relative) if relative.startswith("data/") else ROOT / relative)
    session_paths = level2.session_artifact_paths(producer_root, SESSION)
    paths.extend(session_paths[key] for key in convergence.SESSION_INPUT_KEYS)
    return sorted({path.resolve() for path in paths if path.is_file()})


def _hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path): convergence.sha256_file(path) for path in paths}


def _pinned_authority_equal(baseline_root: Path) -> dict[str, bool]:
    here, there = financial_authority.resolve(ROOT), financial_authority.resolve(baseline_root)
    fields = ("semantics_artifact_path", "semantics_facts_path", "feature_store_artifact_path",
              "feature_store_records_path", "classification_diagnostics_path")
    return {field: convergence.sha256_file(getattr(here, field)) == convergence.sha256_file(getattr(there, field))
            for field in fields}


def prove(args: argparse.Namespace) -> dict:
    producer_root, baseline_root = Path(args.producer_root).resolve(), Path(args.baseline_code_root).resolve()
    work_root, output_dir = Path(args.work_root).resolve(), Path(args.output_dir).resolve()
    if work_root != EXPECTED_WORK_ROOT.resolve() or output_dir != EXPECTED_OUTPUT_DIR.resolve():
        raise SystemExit("PROOF_ROOTS_OUTSIDE_NAMED_TARGETS")
    if convergence._git(baseline_root, "rev-parse", "HEAD") != BASELINE_COMMIT:
        raise SystemExit("BASELINE_CODE_ROOT_NOT_AT_P_B_CHECKPOINT")
    if not all(_pinned_authority_equal(baseline_root).values()):
        raise SystemExit("PINNED_FINANCIAL_V2_EVIDENCE_DIFFERS_BETWEEN_CODE_ROOTS")
    evidence = _evidence_paths(producer_root)
    before = _hashes(evidence)
    for name, code_root in (("baseline", baseline_root), ("after", ROOT), ("rerun", ROOT)):
        convergence._run_assembly(code_root, producer_root, work_root / name, SESSION)
    if _hashes(evidence) != before:
        raise SystemExit("RETAINED_EVIDENCE_SHA_CHANGED")
    _write(work_root / "retained_evidence_sha256.json", before)
    return summarize(argparse.Namespace(producer_root=str(producer_root), baseline_code_root=str(baseline_root),
                                        work_root=str(work_root), output_dir=str(output_dir)))


def _load_run(work_root: Path, name: str) -> dict[str, Any]:
    outputs = work_root / name / "outputs"
    return {
        "assembly": convergence.load(outputs / "assembly_result.json"),
        "iid_path": outputs / "integrated_investment_decision_product.json",
        "iid": convergence.load(outputs / "integrated_investment_decision_product.json"),
        "compact": convergence.load(outputs / "financial_analysis_product.json"),
        "valuation": convergence.load(level2.session_artifact_paths(work_root / name / "artifact-root", SESSION)["current_valuation_evaluated"]),
    }


def _baseline_capability_tool(baseline_root: Path):
    spec = importlib.util.spec_from_file_location("baseline_capability_map", baseline_root / "tools" / "current_research_capability_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _peer_label(entry: Mapping[str, Any]) -> str:
    reason = entry.get("reason")
    return f"{entry.get('status')}:{','.join(reason)}" if isinstance(reason, list) and reason else str(entry.get("status"))


def _fitness(compact: Mapping[str, Any], ticker: str, feature: str) -> str:
    record = (compact.get("records") or {}).get(ticker) or {}
    if record.get("status") != "AVAILABLE":
        return "ABSENT"
    return str(((record.get("feature_fitness") or {}).get(feature) or {}).get("fitness") or "MISSING")


def _feature_recovery(before: Mapping[str, Any], after: Mapping[str, Any], populations: Mapping[str, set[str]]) -> dict[str, Any]:
    features = sorted({feature for compact in (before, after) for record in compact["records"].values()
                       for feature in (record.get("feature_fitness") or {})})
    out: dict[str, Any] = {}
    for feature in features:
        entry: dict[str, Any] = {}
        for population, tickers in populations.items():
            pairs = [(_fitness(before, t, feature), _fitness(after, t, feature)) for t in sorted(tickers)]
            entry[population] = {
                "ready_before": sum(a == "READY" for a, _ in pairs), "ready_after": sum(b == "READY" for _, b in pairs),
                "proxy_before": sum(a == "RESEARCH_PROXY" for a, _ in pairs), "proxy_after": sum(b == "RESEARCH_PROXY" for _, b in pairs),
                "transitions": _transitions(pairs),
            }
        official = sorted(populations[OFFICIAL])
        entry["still_blocked_reason_codes_official"] = _counts(
            code for t in official if _fitness(after, t, feature) == "BLOCKED_BY_EVIDENCE"
            for code in (((after["records"][t].get("feature_fitness") or {}).get(feature) or {}).get("reason_codes") or ["UNSPECIFIED"])[:1])
        out[feature] = entry
    return out


def _restored_detail(engine: Mapping[str, Any], feature: str, tickers: Iterable[str]) -> dict[str, Any]:
    rows = [((engine["records"].get(t) or {}).get("features") or {}).get(feature) or {} for t in tickers]
    rows = [row for row in rows if row.get("fitness") == "READY"]
    latest = [str((row.get("period_identity") or [None])[-1]) for row in rows]
    return {
        "ticker_count": len(rows),
        "method": _counts(row.get("method") for row in rows),
        "as_of_period": _counts(latest),
        "freshness": _counts(classify_financial_period_freshness(
            source_period=period, decision_session=SESSION, maximum_completed_quarter_lag=MAX_COMPLETED_QUARTER_LAG)["freshness_status"]
            for period in latest),
        "statement_scope": _counts("|".join(row.get("scope") or []) for row in rows),
        "provider": _counts("|".join(sorted({str(item.get("provider")) for item in row.get("provider_source_provenance") or []})) for row in rows),
        "lineage_method": _counts(item.get("lineage_method") or "RAW_SEMANTIC_FACT"
                                  for row in rows for item in row.get("provider_source_provenance") or []),
        "provenance_complete": all(item.get(key) for row in rows for item in row.get("provider_source_provenance") or []
                                   for key in ("provider", "source_file", "source_sha256", "fact_id")),
        "distinct_source_files_per_feature": _counts(len({item.get("source_file") for item in row.get("provider_source_provenance") or []}) for row in rows),
        "qualification_tier": _counts(row.get("fitness") for row in rows),
        "warnings": _counts(code for row in rows for code in row.get("warnings") or []),
        "reason_codes": _counts(code for row in rows for code in row.get("reason_codes") or []),
        "is_actionable": sorted({row.get("is_actionable") for row in rows}),
    }


def _pb_regression(before: Mapping[str, Any], after: Mapping[str, Any], official: set[str], verdict: Mapping[str, Any]) -> dict[str, Any]:
    method_field_diffs: dict[str, Counter] = defaultdict(Counter)
    market_cap_value_diffs = []
    for ticker in sorted(after["records"]):
        old_methods, new_methods = before["records"][ticker]["methods"], after["records"][ticker]["methods"]
        for method in sorted(set(old_methods) | set(new_methods)):
            old, new = old_methods.get(method) or {}, new_methods.get(method) or {}
            for field in sorted(set(old) | set(new)):
                if old.get(field) != new.get(field):
                    method_field_diffs[method][field] += 1
        if old_methods["market_cap"].get("value") != new_methods["market_cap"].get("value"):
            market_cap_value_diffs.append(ticker)
    usable = {t: after["records"][t]["methods"][PB_METHOD] for t in sorted(official)
              if after["records"][t]["methods"][PB_METHOD]["status"] == "RESEARCH_USABLE"}

    def peer(artifact: Mapping[str, Any]) -> dict[str, Any]:
        by_scope: dict[str, Counter] = defaultdict(Counter)
        for t, method in usable.items():
            status = ((artifact["records"][t].get("peer_relative") or {}).get(PB_METHOD) or {})
            by_scope[str(method.get("statement_scope"))][f"{status.get('status')}:{status.get('reason') or ''}".rstrip(":")] += 1
        ready = sum(((artifact["records"][t].get("peer_relative") or {}).get(PB_METHOD) or {}).get("status") == "READY_RESEARCH_ONLY" for t in usable)
        return {"peer_ready": ready, "by_statement_scope": {k: dict(sorted(v.items())) for k, v in sorted(by_scope.items())}}

    contract = ((verdict.get("semantic_basis_registry") or {}).get("contracts") or {}).get("VCI:balance_sheet") or {}
    return {
        "pinned_verdict_identity": verdict.get("artifact_identity"),
        "vci_balance_sheet_verdict": contract.get("verdict"),
        "usable_official": len(usable),
        "usable_by_statement_scope": _counts(method.get("statement_scope") for method in usable.values()),
        "method_field_differences_baseline_to_after": {method: dict(sorted(fields.items())) for method, fields in sorted(method_field_diffs.items())},
        "market_cap_value_differences": market_cap_value_diffs,
        "nci_limitation_on_every_usable_row": all("NCI_NOT_DEDUCTED" in (m.get("limitations") or []) for m in usable.values()),
        "equity_definition": _counts(m.get("equity_definition") for m in usable.values()),
        "research_only_limitations": all({"CURRENT_RESEARCH_ONLY", "NOT_AUTHORITATIVE", "NOT_FOR_TARGET_PRICE"} <= set(m.get("limitations") or [])
                                         for m in usable.values()),
        "is_actionable": sorted({str(m.get("is_actionable")) for m in usable.values()}),
        "exact_pb_status_transitions": _transitions(((before["records"][t]["methods"].get("P/B") or {}).get("status"),
                                                     (after["records"][t]["methods"].get("P/B") or {}).get("status"))
                                                    for t in after["records"]),
        "peer_before": peer(before), "peer_after": peer(after),
        "relative_research_state_transitions_official": _transitions(
            (before["records"][t].get("relative_research_state"), after["records"][t].get("relative_research_state")) for t in sorted(official)),
    }


def _decision_changes(before: Mapping[str, Any], after: Mapping[str, Any], tickers: Iterable[str]) -> dict[str, Any]:
    tickers = sorted(tickers)
    b, a = before["records"], after["records"]

    def dim(record: Mapping[str, Any], name: str) -> Mapping[str, Any]:
        return ((record.get("current_research_decision_input") or {}).get("dimensions") or {}).get(name) or {}

    fundamental_changed = {t for t in tickers if b[t]["fundamental_state"] != a[t]["fundamental_state"]}
    valuation_changed = {t for t in tickers if b[t]["valuation_context_summary"] != a[t]["valuation_context_summary"]}
    posture_changed = [t for t in tickers if b[t]["research_action_posture"] != a[t]["research_action_posture"]]
    gained = Counter(code for t in tickers for code in set(a[t].get("counter_thesis") or []) - set(b[t].get("counter_thesis") or []))
    lost = Counter(code for t in tickers for code in set(b[t].get("counter_thesis") or []) - set(a[t].get("counter_thesis") or []))
    qualified_delta = Counter(len(dim(a[t], "FUNDAMENTAL").get("metrics", {}).get("qualified") or [])
                              - len(dim(b[t], "FUNDAMENTAL").get("metrics", {}).get("qualified") or []) for t in tickers)
    return {
        "records": len(tickers),
        "fundamental_state_transitions": _transitions((b[t]["fundamental_state"], a[t]["fundamental_state"]) for t in tickers),
        "fundamental_support_changed": sum(b[t].get("fundamental_support") != a[t].get("fundamental_support") for t in tickers),
        "financial_composite_state_transitions": _transitions(
            ((b[t].get("financial_composite_context") or {}).get("financial_composite_state"),
             (a[t].get("financial_composite_context") or {}).get("financial_composite_state")) for t in tickers),
        "financial_composite_context_changed": sum(b[t].get("financial_composite_context") != a[t].get("financial_composite_context") for t in tickers),
        "evidence_axis_coherence_transitions": _transitions(
            ((b[t].get("evidence_axis_coherence") or {}).get("state"), (a[t].get("evidence_axis_coherence") or {}).get("state")) for t in tickers),
        "counter_thesis_changed": sum(b[t].get("counter_thesis") != a[t].get("counter_thesis") for t in tickers),
        "counter_thesis_tags_gained": dict(sorted(gained.items())), "counter_thesis_tags_lost": dict(sorted(lost.items())),
        "valuation_peer_relative_state_transitions": _transitions(
            (b[t]["valuation_context_summary"].get("peer_relative_state"), a[t]["valuation_context_summary"].get("peer_relative_state")) for t in tickers),
        "valuation_own_history_state_transitions": _transitions(
            (b[t]["valuation_context_summary"].get("own_history_state"), a[t]["valuation_context_summary"].get("own_history_state")) for t in tickers),
        "valuation_status_transitions": _transitions(
            (b[t]["valuation_context_summary"].get("status"), a[t]["valuation_context_summary"].get("status")) for t in tickers),
        "evidence_class_transitions": _transitions(
            ((b[t].get("current_research_decision_input") or {}).get("evidence_class"),
             (a[t].get("current_research_decision_input") or {}).get("evidence_class")) for t in tickers),
        "fundamental_dimension_transitions": _transitions((dim(b[t], "FUNDAMENTAL").get("state"), dim(a[t], "FUNDAMENTAL").get("state")) for t in tickers),
        "valuation_dimension_transitions": _transitions((dim(b[t], "VALUATION").get("state"), dim(a[t], "VALUATION").get("state")) for t in tickers),
        "valuation_evidence_class_transitions": _transitions(
            (dim(b[t], "VALUATION").get("evidence_class"), dim(a[t], "VALUATION").get("evidence_class")) for t in tickers),
        "fundamental_qualified_metric_count_delta": dict(sorted((str(k), v) for k, v in qualified_delta.items())),
        "decision_identity_changed": sum(b[t]["decision_identity"] != a[t]["decision_identity"] for t in tickers),
        "research_action_posture": {
            "transitions": _transitions((b[t]["research_action_posture"], a[t]["research_action_posture"]) for t in posture_changed),
            "attribution": [{"ticker": t, "before": b[t]["research_action_posture"], "after": a[t]["research_action_posture"],
                             "fundamental_state": [b[t]["fundamental_state"], a[t]["fundamental_state"]],
                             "valuation_summary_changed": t in valuation_changed} for t in posture_changed],
            "unexplained": [t for t in posture_changed if t not in fundamental_changed and t not in valuation_changed],
        },
    }


def summarize(args: argparse.Namespace) -> dict:
    producer_root, baseline_root = Path(args.producer_root).resolve(), Path(args.baseline_code_root).resolve()
    work_root, output_dir = Path(args.work_root).resolve(), Path(args.output_dir).resolve()
    if work_root != EXPECTED_WORK_ROOT.resolve() or output_dir != EXPECTED_OUTPUT_DIR.resolve():
        raise SystemExit("PROOF_ROOTS_OUTSIDE_NAMED_TARGETS")
    runs = {name: _load_run(work_root, name) for name in RUNS}
    for name, run in runs.items():
        guard = run["assembly"]
        if (guard["write_guard"]["violations"] or guard["provider_calls"] or guard["runtime_store_reads"]
                or guard.get("network_audit_events") is None or any(guard["network_audit_events"].values())):
            raise SystemExit(f"EVIDENCE_GUARD_OR_PROVIDER_CALL_VIOLATION:{name}")
    if len({json.dumps(run["assembly"]["staged_session_inputs"], sort_keys=True) for run in runs.values()}) != 1:
        raise SystemExit("STAGED_SESSION_INPUTS_DIFFER")
    for key in ("iid", "compact", "valuation"):
        if runs["after"][key]["artifact_identity"] != runs["rerun"][key]["artifact_identity"]:
            raise SystemExit(f"AFTER_REPLAY_NOT_DETERMINISTIC:{key}")
    pb_proof = convergence.load(PB_PROOF_DIR / "current_research_book_value_proof.json")
    if runs["baseline"]["iid"]["artifact_identity"] != pb_proof["after_integrated_identity"]:
        raise SystemExit("BASELINE_DOES_NOT_REPRODUCE_P_B_CHECKPOINT_DECISION")
    if runs["baseline"]["valuation"]["artifact_identity"] != pb_proof["after_valuation_identity"]:
        raise SystemExit("BASELINE_DOES_NOT_REPRODUCE_P_B_CHECKPOINT_VALUATION")
    ops = producer_root / "operations-review"
    baseline_tool_map = _baseline_capability_tool(baseline_root).build(ops, SESSION, {"integrated": runs["baseline"]["iid_path"]})
    if baseline_tool_map["artifact_identity"] != pb_proof["after_capability_map_identity"]:
        raise SystemExit("BASELINE_CAPABILITY_MAP_DOES_NOT_REPRODUCE_P_B_CHECKPOINT")
    maps = {name: capability.build(ops, SESSION, {"integrated": runs[name]["iid_path"]}) for name in RUNS}
    if maps["after"]["artifact_identity"] != maps["rerun"]["artifact_identity"]:
        raise SystemExit("CAPABILITY_MAP_NOT_DETERMINISTIC")
    rows = maps["after"]["records"]
    attempted = set(rows)
    official = {t for t, row in rows.items() if row["universe_status"] == "OFFICIAL_RESEARCH_SCOPE"}
    priced = {t for t in official if rows[t]["research_market_cap_usable"]}
    baseline_priced = {t for t, row in maps["baseline"]["records"].items()
                       if row["universe_status"] == "OFFICIAL_RESEARCH_SCOPE" and row["research_market_cap_usable"]}
    if not (priced <= official <= attempted) or priced != baseline_priced or len(priced) != pb_proof["pb_coverage"]["priced_official"]:
        raise SystemExit("DENOMINATORS_DO_NOT_RECONCILE")
    populations = {ATTEMPTED: attempted, OFFICIAL: official}

    engine = fin_v2_material.build_engine_artifact(root=ROOT, requested_at=f"{SESSION}T15:00:00+07:00")
    if engine["artifact_identity"] != runs["after"]["compact"]["source_context_identity"]:
        raise SystemExit("IN_PROCESS_ENGINE_DOES_NOT_MATCH_ASSEMBLED_ENGINE")
    before_compact, after_compact = runs["baseline"]["compact"], runs["after"]["compact"]
    recovery = _feature_recovery(before_compact, after_compact, populations)
    restored = sorted(feature for feature, entry in recovery.items() if entry[OFFICIAL]["ready_after"] > entry[OFFICIAL]["ready_before"])
    reduced = sorted(feature for feature, entry in recovery.items() if entry[OFFICIAL]["ready_after"] < entry[OFFICIAL]["ready_before"])
    missing_before = sorted(feature for feature in restored if recovery[feature][OFFICIAL]["ready_before"] == 0)
    gained_tickers = {feature: sorted(t for t in official if _fitness(before_compact, t, feature) != "READY"
                                      and _fitness(after_compact, t, feature) == "READY") for feature in restored}
    affected = sorted({t for tickers in gained_tickers.values() for t in tickers}
                      | {t for feature in reduced for t in official
                         if _fitness(before_compact, t, feature) == "READY" and _fitness(after_compact, t, feature) != "READY"})
    ytd = {feature: recovery[feature][OFFICIAL] for feature in ("revenue_ytd_yoy", "net_income_ytd_yoy")}
    semantics = convergence.load(financial_authority.resolve(ROOT).semantics_artifact_path)
    iid_b, iid_a = runs["baseline"]["iid"], runs["after"]["iid"]
    verdict = verdict_pin.resolve(ROOT)
    fund_dim = lambda t: ((iid_a["records"][t].get("current_research_decision_input") or {}).get("dimensions") or {}).get("FUNDAMENTAL") or {}
    engine_peers = valuation_context.attach_engine_fundamental_peers(
        engine["records"], industry_by_ticker=fin_v2_material.load_industry_by_ticker(financial_authority.resolve(ROOT)))
    result: dict[str, Any] = {
        "schema_version": "1.0.0", "contract_version": CONTRACT, "session": SESSION,
        "baseline_identity": {
            "baseline_commit": BASELINE_COMMIT, "after_code_head": runs["after"]["assembly"]["code_head"],
            "after_code_tracked_changes": runs["after"]["assembly"]["code_tracked_changes"],
            "pinned_financial_v2_authority": financial_authority.resolve(ROOT).to_manifest(),
            "semantics_identity": semantics.get("artifact_identity"),
            "reproduces_p_b_checkpoint": {"integrated_identity": pb_proof["after_integrated_identity"],
                                          "valuation_identity": pb_proof["after_valuation_identity"],
                                          "capability_map_identity": pb_proof["after_capability_map_identity"]},
            "staged_session_inputs": runs["after"]["assembly"]["staged_session_inputs"],
            "retained_evidence_sha256": convergence.load(work_root / "retained_evidence_sha256.json"),
        },
        "identities": {name: {"integrated": runs[name]["iid"]["artifact_identity"],
                              "financial_analysis_product": runs[name]["compact"]["artifact_identity"],
                              "financial_engine": runs[name]["compact"]["source_context_identity"],
                              "evaluated_valuation": runs[name]["valuation"]["artifact_identity"],
                              "capability_map": maps[name]["artifact_identity"]} for name in RUNS},
        "guard": {name: {"violations": runs[name]["assembly"]["write_guard"]["violations"],
                         "network_audit_events": runs[name]["assembly"].get("network_audit_events"),
                         "provider_calls": runs[name]["assembly"]["provider_calls"],
                         "runtime_store_reads": runs[name]["assembly"]["runtime_store_reads"],
                         "publication": runs[name]["assembly"]["publication"]} for name in RUNS},
        "denominators": {ATTEMPTED: len(attempted), OFFICIAL: len(official), PRICED: len(priced),
                         "priced_within_official_within_attempted": True,
                         "priced_matches_p_b_checkpoint": len(priced) == pb_proof["pb_coverage"]["priced_official"]},
        "root_cause": {
            "semantic_join_defect": ("financial_analysis_engine_v2._source_key keyed series on source_file; flow-bridge rows carried "
                                     "source_file='qualified_standalone_flow_bridge/v2' while gross_profit and capital_expenditure "
                                     "stayed raw, so same-statement pairs never met"),
            "status_relabel_defect": ("financial_flow_semantics_ttm_bridge.engine_rows_from_artifact stamped every bridge quarter "
                                      "provider_reported, admitting partial operands the engine gate rejects"),
            "composed_lineage_defect": ("registry-composed facts (total_interest_bearing_debt) lose provider/source_file/sha in the "
                                        "semantic projection although their components carry exact observation linkage"),
            "ytd_yoy_not_a_join_defect": ytd,
            "engine_input_integrity": engine["coverage"].get("input_integrity"),
            "composed_fact_lineage": engine["coverage"].get("composed_fact_lineage"),
        },
        "affected_cohort": {
            "official_tickers": len(affected),
            "by_entity_class": _counts(rows[t]["entity_class"] or "unknown" for t in affected),
            "by_exchange": _counts(rows[t]["exchange"] for t in affected),
            "gained_by_feature": {feature: len(tickers) for feature, tickers in sorted(gained_tickers.items())},
        },
        "feature_recovery": {"groups": {group: {feature: recovery.get(feature) for feature in features}
                                        for group, features in FEATURE_GROUPS.items()},
                             "missing_before": missing_before, "restored": restored, "reduced_fail_closed": reduced,
                             "all_feature_transitions_official": {feature: entry[OFFICIAL]["transitions"] for feature, entry in recovery.items()
                                                                  if entry[OFFICIAL]["transitions"]}},
        "restored_feature_detail": {feature: _restored_detail(engine, feature, gained_tickers[feature]) for feature in restored},
        "still_blocked": {feature: {"ready_after_official": recovery[feature][OFFICIAL]["ready_after"],
                                    "reason_codes": recovery[feature]["still_blocked_reason_codes_official"]}
                          for group in FEATURE_GROUPS.values() for feature in group if feature in recovery},
        "decision_changes": {ATTEMPTED: _decision_changes(iid_b, iid_a, attempted), OFFICIAL: _decision_changes(iid_b, iid_a, official)},
        "current_research_classes": {
            "evidence_class": {OFFICIAL: {"before": _counts((iid_b["records"][t].get("current_research_decision_input") or {}).get("evidence_class") for t in official),
                                          "after": _counts((iid_a["records"][t].get("current_research_decision_input") or {}).get("evidence_class") for t in official)},
                               PRICED: {"before": _counts((iid_b["records"][t].get("current_research_decision_input") or {}).get("evidence_class") for t in priced),
                                        "after": _counts((iid_a["records"][t].get("current_research_decision_input") or {}).get("evidence_class") for t in priced)}},
            "decision_readiness_v1_rule": {ATTEMPTED: {"before": maps["baseline"]["decision_readiness"], "after": maps["after"]["decision_readiness"]}},
            "integrated_fundamental": {population: {"before": sum(iid_b["records"][t]["fundamental_state"] != "INSUFFICIENT" for t in tickers),
                                                    "after": sum(iid_a["records"][t]["fundamental_state"] != "INSUFFICIENT" for t in tickers)}
                                       for population, tickers in ((ATTEMPTED, attempted), (OFFICIAL, official))},
        },
        "p_b_regression": _pb_regression(runs["baseline"]["valuation"], runs["after"]["valuation"], official, verdict),
        "engine_fundamental_peers_after": {
            feature: _counts(_peer_label(engine_peers[t].get(feature) or {}) for t in sorted(official) if t in engine_peers)
            for feature in valuation_context.ENGINE_PEER_FEATURES},
        "freshness": {
            "denominator": OFFICIAL,
            "fundamental_dimension_available": sum(fund_dim(t).get("state") == "AVAILABLE" for t in official),
            "status_when_fundamental_available": _counts(fund_dim(t).get("freshness", {}).get("freshness_status") for t in official
                                                         if fund_dim(t).get("state") == "AVAILABLE"),
            "as_of_period_when_fundamental_available": _counts(fund_dim(t).get("as_of_financial_period") for t in official
                                                               if fund_dim(t).get("state") == "AVAILABLE"),
            "completed_quarter_lag_when_fundamental_available": _counts(fund_dim(t).get("freshness", {}).get("completed_quarter_lag") for t in official
                                                                        if fund_dim(t).get("state") == "AVAILABLE"),
            "tickers_with_stale_but_research_usable_metrics": sum(bool(fund_dim(t).get("freshness", {}).get("stale_but_research_usable_metrics"))
                                                                   for t in official),
            "maximum_completed_quarter_lag": MAX_COMPLETED_QUARTER_LAG,
            "p_b_book_period_lag_quarters": _counts(runs["after"]["valuation"]["records"][t]["methods"][PB_METHOD].get("book_period_lag_quarters")
                                                    for t in official if runs["after"]["valuation"]["records"][t]["methods"][PB_METHOD]["status"] == "RESEARCH_USABLE"),
        },
        "capability_maps": {name: {"identity": maps[name]["artifact_identity"], "denominators": maps[name]["denominators"],
                                   "decision_readiness": maps[name]["decision_readiness"],
                                   "decision_input_official": {key: maps[name]["current_research_decision_input"][key] for key in (
                                       "evidence_class_distribution", "dimension_state_distribution", "valuation_evidence_class_distribution",
                                       "fundamental_freshness_distribution", "priced_official_scope")}}
                            for name in ("baseline", "after")},
        "samples": {t: {"fundamental_state": [iid_b["records"][t]["fundamental_state"], iid_a["records"][t]["fundamental_state"]],
                        "research_action_posture": [iid_b["records"][t]["research_action_posture"], iid_a["records"][t]["research_action_posture"]],
                        "fundamental_freshness": fund_dim(t).get("freshness"),
                        "features": {feature: {key: ((engine["records"].get(t) or {}).get("features") or {}).get(feature, {}).get(key)
                                               for key in ("fitness", "value", "method", "period_identity", "scope", "reason_codes", "warnings")}
                                     for feature in ("gross_margin", "free_cash_flow_proxy", "debt_to_equity", "cfo_to_net_income", "net_margin")}}
                    for t in SANITY if t in iid_a["records"]},
        "authority_boundary": {"current_research_only": True, "provider_financial_official_authority": False,
                               "exact_valuation_authority": False, "historical_pit_financial_authority": False,
                               "execution_or_sizing_authority": False, "posture_thresholds_or_policy_changed": False,
                               "provider_calls": 0, "financial_data_acquired": False, "publication": "NONE"},
    }
    result["artifact_sha256"] = hashlib.sha256(convergence.canonical(result)).hexdigest()
    result["artifact_identity"] = f"{CONTRACT}:{result['artifact_sha256']}"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / "financial_v2_analysis_input_integrity_proof.json", result)
    _write(output_dir / "before_current_research_capability_map.json", maps["baseline"])
    _write(output_dir / "after_current_research_capability_map.json", maps["after"])
    (output_dir / "after_current_research_capability_summary.md").write_text(capability.summary(maps["after"]), encoding="utf-8")
    (output_dir / "SUMMARY.md").write_text(_summary(result), encoding="utf-8")
    return result


def _summary(result: Mapping[str, Any]) -> str:
    d = result["denominators"]
    rec = result["feature_recovery"]["groups"]
    lines = ["# Financial V2 analysis-input integrity (retained 2026-09-24)", "",
             f"Proof: `{result['artifact_identity']}`", f"Baseline: `{BASELINE_COMMIT}` (reproduces the P/B checkpoint decision, valuation and map).",
             f"Denominators: attempted {d[ATTEMPTED]}; official research scope {d[OFFICIAL]}; priced official scope {d[PRICED]}.", "",
             "## Feature READY counts, official research scope (before -> after)", ""]
    for group, features in rec.items():
        for feature, entry in features.items():
            if entry is None:
                continue
            o = entry[OFFICIAL]
            if o["ready_before"] != o["ready_after"] or feature in ("revenue_ytd_yoy", "net_income_ytd_yoy"):
                lines.append(f"- {group}/{feature}: {o['ready_before']} -> {o['ready_after']}")
    changes = result["decision_changes"][OFFICIAL]
    pb = result["p_b_regression"]
    lines += ["", "## Downstream (official research scope)", "",
              f"- fundamental_state: {changes['fundamental_state_transitions']}",
              f"- evidence class: {changes['evidence_class_transitions']}",
              f"- valuation evidence class: {changes['valuation_evidence_class_transitions']}",
              f"- research_action_posture: {changes['research_action_posture']['transitions']} "
              f"(unexplained: {changes['research_action_posture']['unexplained']})",
              "", "## P/B regression", "",
              f"- usable {pb['usable_official']} of {d[OFFICIAL]} official ({d[PRICED]} priced); scopes {pb['usable_by_statement_scope']}",
              f"- peer-ready {pb['peer_before']['peer_ready']} -> {pb['peer_after']['peer_ready']}",
              f"- method field differences: {pb['method_field_differences_baseline_to_after'] or 'none'}; market-cap value differences: {len(pb['market_cap_value_differences'])}",
              f"- verdict {pb['vci_balance_sheet_verdict']}; NCI limitation on every row: {pb['nci_limitation_on_every_usable_row']}",
              "", "## Freshness (official, fundamental available)", "",
              f"- {result['freshness']['status_when_fundamental_available']}",
              "", "Retained evidence SHA-256 unchanged; zero provider calls, runtime-store reads and write-guard violations.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prove", "summarize"):
        one = sub.add_parser(name)
        one.add_argument("--producer-root", required=True)
        one.add_argument("--baseline-code-root", required=True)
        one.add_argument("--work-root", required=True)
        one.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = prove(args) if args.command == "prove" else summarize(args)
    print(json.dumps({"artifact_identity": result["artifact_identity"], "denominators": result["denominators"],
                      "restored": result["feature_recovery"]["restored"],
                      "reduced": result["feature_recovery"]["reduced_fail_closed"],
                      "posture": result["decision_changes"][OFFICIAL]["research_action_posture"]["transitions"]}, sort_keys=True))


if __name__ == "__main__":
    main()
