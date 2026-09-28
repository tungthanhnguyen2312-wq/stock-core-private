"""Retained 2026-09-24 P/B proof: guarded Daily assembly, baseline, rerun, and maps."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import daily_session_level2_package as level2
import financial_v2_current_input_authority as financial_authority
import provider_financial_monetary_basis_verdict as verdict_pin
from tools import current_research_capability_map as capability
from tools import run_current_research_decision_convergence_proof as convergence

CONTRACT = "current_research_book_value_valuation_proof/v1"
METHOD = "P/B_CURRENT_RESEARCH"
SESSION = "2026-09-24"
TECHNICAL_FIELDS = convergence.TECHNICAL_FIELDS
SANITY = ("FPT", "HPG", "VNM", "ACB", "MWG", "GAS", "PVD", "VIC", "BID", "CTG", "MBB", "SSI", "VCB")


def _write(path: Path, value: dict) -> None:
    path.write_bytes(convergence.canonical(value) + b"\n")


def _hashes(roots: list[Path]) -> dict[str, str]:
    return {str(path): convergence.sha256_file(path) for path in roots}


def _counts(rows: dict, key) -> dict[str, int]:
    return dict(sorted(Counter(key(row) for row in rows.values()).items()))


def _percentile(values: list[float], percentage: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage
    lower = int(position)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower])


def prove(*, producer_root: Path, baseline_root: Path, work_root: Path,
          output_dir: Path, reference_dir: Path) -> dict:
    producer_root, baseline_root, work_root = producer_root.resolve(), baseline_root.resolve(), work_root.resolve()
    expected_work = Path("C:/Projects/StockLookup/tmp/book-value-proof-work").resolve()
    if work_root != expected_work or any((work_root / child).resolve().parent != expected_work
                                         for child in ("baseline", "after", "rerun")):
        raise ValueError("PROOF_WORK_ROOT_OUTSIDE_NAMED_TARGET")
    if output_dir.resolve() != Path("C:/Projects/StockLookup/operations-review/current-research-book-value-valuation-v1-20260924").resolve():
        raise ValueError("PROOF_OUTPUT_ROOT_OUTSIDE_NAMED_TARGET")
    verdict = verdict_pin.resolve(ROOT)
    authority = financial_authority.resolve(ROOT)
    evidence_paths = [authority.semantics_artifact_path, authority.semantics_facts_path,
                      authority.feature_store_artifact_path, authority.feature_store_records_path,
                      authority.classification_diagnostics_path]
    for relative in verdict["input_sha256"]:
        evidence_paths.append((producer_root.parent / "dashboard-runtime" / relative)
                              if relative.startswith("data/") else ROOT / relative)
    before_hashes = _hashes(evidence_paths)
    if any(before_hashes[str(path)] != expected for relative, expected in verdict["input_sha256"].items()
           for path in [((producer_root.parent / "dashboard-runtime" / relative)
                         if relative.startswith("data/") else ROOT / relative)]):
        raise ValueError("PINNED_VERDICT_SOURCE_SHA_CHANGED")
    runs = {name: convergence._run_assembly(code_root, producer_root, work_root / name, SESSION)
            for name, code_root in (("baseline", baseline_root), ("after", ROOT), ("rerun", ROOT))}
    if _hashes(evidence_paths) != before_hashes:
        raise ValueError("RETAINED_EVIDENCE_SHA_CHANGED")
    if not (runs["baseline"]["staged_session_inputs"] == runs["after"]["staged_session_inputs"]
            == runs["rerun"]["staged_session_inputs"]):
        raise ValueError("STAGED_SESSION_INPUTS_DIFFER")
    if any(run["write_guard"]["violations"] or run["provider_calls"] != 0
           or run["runtime_store_reads"] != 0 for run in runs.values()):
        raise ValueError("EVIDENCE_GUARD_OR_PROVIDER_CALL_VIOLATION")
    paths = {name: work_root / name / "outputs" / "integrated_investment_decision_product.json"
             for name in runs}
    products = {name: convergence.load(path) for name, path in paths.items()}
    reference = convergence.load(reference_dir / "after_integrated_investment_decision_product.json")
    if products["baseline"]["artifact_identity"] != reference.get("artifact_identity"):
        raise ValueError("BASELINE_CONVERGENCE_REFERENCE_NOT_REPRODUCED")
    if products["after"]["artifact_identity"] != products["rerun"]["artifact_identity"]:
        raise ValueError("AFTER_REPLAY_IDENTITY_NOT_DETERMINISTIC")
    evaluated_paths = {name: level2.session_artifact_paths(work_root / name / "artifact-root", SESSION)["current_valuation_evaluated"]
                       for name in runs}
    evaluated = {name: convergence.load(path) for name, path in evaluated_paths.items()}
    if evaluated["after"]["artifact_identity"] != evaluated["rerun"]["artifact_identity"]:
        raise ValueError("VALUATION_REPLAY_IDENTITY_NOT_DETERMINISTIC")
    ops = producer_root / "operations-review"
    maps = {name: capability.build(ops, SESSION, {"integrated": paths[name]}) for name in ("baseline", "after")}
    baseline_rows, after_rows = products["baseline"]["records"], products["after"]["records"]
    if set(baseline_rows) != set(after_rows):
        raise ValueError("DECISION_DENOMINATOR_CHANGED")
    official = {ticker for ticker, row in maps["baseline"]["records"].items()
                if row.get("universe_status") == "OFFICIAL_RESEARCH_SCOPE"}
    usable = {ticker: row["methods"][METHOD] for ticker, row in evaluated["after"]["records"].items()
              if ticker in official and row["methods"][METHOD]["status"] == "RESEARCH_USABLE"}
    if abs(len(usable) - 738) > 738 * .05:
        raise ValueError(f"PB_USABLE_COUNT_DIFF_EXCEEDS_FIVE_PERCENT:{len(usable)}")
    if any(after_rows[t][field] != baseline_rows[t][field] for t in baseline_rows for field in TECHNICAL_FIELDS):
        raise ValueError("TECHNICAL_FIELD_CHANGED")
    if any(after_rows[t]["fundamental_state"] != baseline_rows[t]["fundamental_state"] for t in baseline_rows):
        raise ValueError("FUNDAMENTAL_STATE_CHANGED")
    old_to_new = Counter()
    attribution = []
    method_status_diffs = defaultdict(Counter)
    for ticker in sorted(baseline_rows):
        old, new = baseline_rows[ticker], after_rows[ticker]
        if old["research_action_posture"] != new["research_action_posture"]:
            if old["valuation_context_summary"] == new["valuation_context_summary"]:
                raise ValueError(f"POSTURE_CHANGED_WITHOUT_VALUATION_CHANGE:{ticker}")
            old_to_new[f"{old['research_action_posture']} -> {new['research_action_posture']}"] += 1
            attribution.append({"ticker": ticker, "before": old["research_action_posture"],
                                "after": new["research_action_posture"],
                                "old_valuation": old["valuation_context_summary"].get("status"),
                                "new_valuation": new["valuation_context_summary"].get("status")})
        for method in ("P/E_TTM", "P/S_TTM", "P/B"):
            before_status = (old.get("valuation_methods") or {}).get(method, {}).get("status")
            after_status = (new.get("valuation_methods") or {}).get(method, {}).get("status")
            if before_status != after_status:
                method_status_diffs[method][f"{before_status} -> {after_status}"] += 1
    if method_status_diffs:
        raise ValueError(f"EXISTING_VALUATION_METHOD_STATUS_CHANGED:{dict(method_status_diffs)}")
    values = [float(row["value"]) for row in usable.values()]
    by_entity = Counter(evaluated["after"]["records"][t]["entity_class"] for t in usable)
    by_period = Counter(row["book_period"] for row in usable.values())
    by_scope = Counter(row["statement_scope"] for row in usable.values())
    peer = Counter((evaluated["after"]["records"][t].get("peer_relative") or {}).get(METHOD, {}).get("status") for t in usable)
    peer_verdicts = Counter(evaluated["after"]["records"][t].get("relative_research_state") for t in usable)
    sanity = []
    for ticker in SANITY:
        record = evaluated["after"]["records"].get(ticker) or {}
        method = (record.get("methods") or {}).get(METHOD) or {}
        periods = ((record.get("calculation_readiness_context") or {}).get("calculation_readiness") or [])
        readiness = periods[-1] if periods else {}
        pb = readiness.get("pb") or {}
        comparable = (method.get("status") == "RESEARCH_USABLE" and method.get("book_period") == readiness.get("reporting_period")
                      and pb.get("readiness") == "ready"
                      and record["methods"]["market_cap"].get("value") is not None
                      and record["methods"]["market_cap"].get("value") == (readiness.get("market_capitalisation") or {}).get("value"))
        sanity.append({"ticker": ticker, "method_status": method.get("status"), "book_period": method.get("book_period"),
                       "current_research_pb": method.get("value"), "readiness_pb": pb.get("value"),
                       "same_period_and_market_cap": comparable,
                       "absolute_difference": abs(method["value"] - pb["value"]) if comparable else None})
    def dimension(rows: dict) -> dict:
        return _counts(rows, lambda row: ((row.get("current_research_decision_input") or {}).get("dimensions") or {}).get("VALUATION", {}).get("state"))
    def evidence_class(rows: dict) -> dict:
        return _counts(rows, lambda row: (row.get("current_research_decision_input") or {}).get("evidence_class"))
    result = {
        "contract_version": CONTRACT, "session": SESSION, "baseline_commit": convergence._git(baseline_root, "rev-parse", "HEAD"),
        "pinned_monetary_basis_verdict_identity": verdict["artifact_identity"],
        "shape_verdicts": {key: row["verdict"] for key, row in verdict["semantic_basis_registry"]["contracts"].items()},
        "vci_balance_sheet_anchor_table": verdict["source_reconciliation"]["shapes"].get("('VCI', 'balance_sheet')"),
        "baseline_integrated_identity": products["baseline"]["artifact_identity"],
        "after_integrated_identity": products["after"]["artifact_identity"],
        "after_valuation_identity": evaluated["after"]["artifact_identity"],
        "before_capability_map_identity": maps["baseline"]["artifact_identity"],
        "after_capability_map_identity": maps["after"]["artifact_identity"],
        "rerun_identical": True, "retained_evidence_sha_identical": True,
        "guard": {name: {"violations": runs[name]["write_guard"]["violations"],
                          "provider_calls": runs[name]["provider_calls"],
                          "runtime_store_reads": runs[name]["runtime_store_reads"]} for name in runs},
        "official_scope": len(official),
        "pb_coverage": {"usable_official": len(usable), "priced_official": sum(
            evaluated["after"]["records"][t]["methods"]["market_cap"]["status"] in {"READY", "RESEARCH_USABLE"}
            for t in official), "by_entity": dict(sorted(by_entity.items())),
            "by_book_period": dict(sorted(by_period.items())), "by_statement_scope": dict(sorted(by_scope.items())),
            "non_positive_equity": sum((evaluated["after"]["records"][t]["methods"][METHOD]["status"] == "PB_NOT_MEANINGFUL") for t in official),
            "distribution": {"p10": _percentile(values, .1), "median": statistics.median(values) if values else None,
                             "p90": _percentile(values, .9), "max": max(values) if values else None},
            "peer_status": dict(sorted(peer.items())), "peer_verdicts": dict(sorted(peer_verdicts.items()))},
        "sanity": sanity,
        "evidence_class_before": evidence_class(baseline_rows), "evidence_class_after": evidence_class(after_rows),
        "valuation_dimension_before": dimension(baseline_rows), "valuation_dimension_after": dimension(after_rows),
        "decision_readiness_before": maps["baseline"]["decision_readiness"],
        "decision_readiness_after": maps["after"]["decision_readiness"],
        "posture_transitions": dict(sorted(old_to_new.items())), "posture_attribution": attribution,
        "existing_method_status_transitions": {},
    }
    digest = hashlib.sha256(convergence.canonical(result)).hexdigest()
    result["artifact_sha256"] = digest
    result["artifact_identity"] = f"{CONTRACT}:{digest}"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write(output_dir / "current_research_book_value_proof.json", result)
    _write(output_dir / "before_current_research_capability_map.json", maps["baseline"])
    _write(output_dir / "after_current_research_capability_map.json", maps["after"])
    summary = (f"# Current Research book-value valuation\n\nProof: {result['artifact_identity']}\n"
               f"Verdict: {verdict['artifact_identity']}\nOfficial P/B usable: {len(usable)}/{len(official)}; "
               f"median {result['pb_coverage']['distribution']['median']:.6f}.\n"
               f"Baseline map: {maps['baseline']['artifact_identity']}\n"
               f"After map: {maps['after']['artifact_identity']}\n"
               "Retained evidence SHA-256 unchanged; zero provider calls and write-guard violations.\n")
    (output_dir / "SUMMARY.md").write_text(summary, encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer-root", type=Path, required=True)
    parser.add_argument("--baseline-code-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.reference_dir.is_dir():
        raise ValueError("REFERENCE_DIR_UNAVAILABLE")
    result = prove(producer_root=args.producer_root, baseline_root=args.baseline_code_root,
                   work_root=args.work_root, output_dir=args.output_dir, reference_dir=args.reference_dir)
    print(json.dumps({key: result[key] for key in ("artifact_identity", "pb_coverage", "evidence_class_before",
                                                    "evidence_class_after", "posture_transitions")}, sort_keys=True))


if __name__ == "__main__":
    main()
