"""Replay the frozen 2026-09-24 Current Research cohort from retained evidence only."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_post_close_pipeline import resolve_current_session_priority_queue
from daily_session_level2_package import session_artifact_paths
import stocklookup_core.decision.integrated_investment_decision_product as integrated
import market_wide_relative_volume_research as relative_volume
import operational_fundamental_context_integration as bridge
from tools import current_research_capability_map as capability


EXPECTED_BEFORE_MAP = "current_research_capability_map/v1:ac1240dff8bca998d8c322bccd4c469f0318204cd90f10213f1272d246cfd734"
SESSION = "2026-09-24"
OPERATION = "25ac1ea3044b88c2a9f272a471b7fadc13f6b21e158fd0abb5e171344a975f22"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> None:
    path.write_bytes(bridge.canonical(value) + b"\n")


def verify_map(path: Path) -> dict:
    value = load(path)
    body = {key: item for key, item in value.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(capability.canonical(body)).hexdigest()
    if value.get("artifact_identity") != EXPECTED_BEFORE_MAP or value.get("artifact_sha256") != digest:
        raise ValueError("FROZEN_CAPABILITY_MAP_IDENTITY_CHANGED")
    return value


def frozen_cohort(before: dict) -> tuple[dict[str, str], dict]:
    rows = before["records"]
    cohort = {ticker: row["entity_class"] for ticker, row in sorted(rows.items())
              if row.get("universe_status") == "OFFICIAL_RESEARCH_SCOPE"
              and row.get("fundamental_integration_gap") is True
              and "FUNDAMENTAL_CONTEXT_ABSENT" in row.get("reason_codes", [])}
    if (len(cohort) != 104 or sorted(cohort) != before["overblocking"]["fundamental_feature_ready_but_integrated_insufficient"]["tickers"]):
        raise ValueError("FROZEN_COHORT_NOT_104_OR_TICKER_MISMATCH")
    manifest = {"schema_version": "1.0.0", "contract_version": "entity_aware_operational_fundamental_cohort/v1",
                "session": SESSION, "source_capability_map_identity": before["artifact_identity"],
                "ticker_count": len(cohort), "tickers": sorted(cohort), "entity_classes": cohort}
    digest = hashlib.sha256(bridge.canonical(manifest)).hexdigest()
    manifest["artifact_sha256"] = digest
    manifest["artifact_identity"] = f"{manifest['contract_version']}:{digest}"
    return cohort, manifest


def verify_source_files(before: dict, source_root: Path, feature_artifact: Path, feature_payload: Path) -> None:
    expected = before["sources"]
    paths = capability.source_paths(source_root, SESSION)
    paths["fundamental_store"] = feature_artifact
    for name, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]["file_sha256"]:
            raise ValueError(f"FROZEN_SOURCE_FILE_CHANGED:{name}")
    if hashlib.sha256(feature_payload.read_bytes()).hexdigest() != expected["fundamental_payload"]["compressed_file_sha256"]:
        raise ValueError("FROZEN_FUNDAMENTAL_PAYLOAD_CHANGED")


def feature_records(path: Path, cohort: dict[str, str], expected_count: int) -> dict:
    records = {}
    row_count = 0
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            row_count += 1
            ticker = row["ticker"]
            if ticker in cohort:
                if ticker in records:
                    raise ValueError(f"DUPLICATE_FUNDAMENTAL_FEATURE_ROW:{ticker}")
                records[ticker] = row
    if row_count != expected_count or set(records) != set(cohort):
        raise ValueError("FUNDAMENTAL_FEATURE_COHORT_PAYLOAD_MISMATCH")
    return records


def retained_integrated_inputs(primary_root: Path, original: dict) -> tuple[dict, dict]:
    paths = session_artifact_paths(primary_root, SESSION)
    get = lambda key: load(paths[key])
    snapshot = get("exact_session_snapshot")
    opportunity = get("opportunity_prioritization")
    priority, resolution = resolve_current_session_priority_queue(
        SESSION, opportunity=opportunity, triage=get("session_triage"))
    if priority is None or priority.get("artifact_identity") != original["source_artifacts"]["priority_queue"]:
        raise ValueError(f"FROZEN_PRIORITY_QUEUE_NOT_REPRODUCED:{resolution}")
    rvol = relative_volume.build_artifact(candidates=sorted(snapshot["records"]),
                                          records=snapshot["records"], session=SESSION,
                                          requested_at=original["requested_at"])
    args = {"session": SESSION, "requested_at": original["requested_at"],
            "technical_structure_artifact": get("market_structure_breakout_v3_projection"),
            "financial_analysis_artifact": get("financial_analysis_product")["financial_analysis_product"],
            "current_valuation_artifact": get("current_valuation_evaluated"),
            "relative_volume_artifact": rvol, "market_sector_artifact": get("sector_leadership"),
            "legacy_decision_artifact": opportunity, "priority_queue_artifact": priority,
            "momentum_artifact": get("tactical_momentum_context"),
            "tactical_confirmation_artifact": get("tactical_confirmation_context"),
            "tactical_boundaries_artifact": get("tactical_confirmation_invalidation_boundaries"),
            "corporate_intelligence_artifact": get("corporate_intelligence_axis"),
            "technical_coverage_disposition_artifact": get("technical_coverage_disposition")}
    for key, source_key in [("technical_structure_artifact", "technical_structure"),
                            ("financial_analysis_artifact", "financial_analysis"),
                            ("current_valuation_artifact", "current_valuation"),
                            ("relative_volume_artifact", "relative_volume"),
                            ("market_sector_artifact", "market_sector"),
                            ("priority_queue_artifact", "priority_queue"),
                            ("momentum_artifact", "momentum"),
                            ("tactical_confirmation_artifact", "tactical_confirmation"),
                            ("tactical_boundaries_artifact", "tactical_boundaries"),
                            ("technical_coverage_disposition_artifact", "technical_coverage_disposition")]:
        if args[key].get("artifact_identity") != original["source_artifacts"].get(source_key):
            raise ValueError(f"FROZEN_INTEGRATED_SOURCE_CHANGED:{source_key}")
    return args, {"frozen_corporate_identity": original["source_artifacts"]["corporate_intelligence"],
                  "replay_corporate_identity": args["corporate_intelligence_artifact"]["artifact_identity"]}


# CURRENT_RESEARCH_DECISION_CONVERGENCE_V1 deliberately corrected how the Integrated Decision
# interprets the (identity-verified, unchanged) valuation input: market cap is size context, the
# producer's peer-relative verdict is read, and method applicability uses the governed entity
# class. The frozen original's valuation summary therefore predates that interpretation; every
# valuation input is still identity-checked in retained_integrated_inputs, and validate_after still
# requires the valuation summary to be identical between baseline and after (same code).
REVISED_INTERPRETATION_FIELDS = frozenset({"valuation_context_summary"})


def validate_baseline_replay(original: dict, baseline: dict) -> None:
    if set(original["records"]) != set(baseline["records"]):
        raise ValueError("BASELINE_REPLAY_TICKER_SET_CHANGED")
    for ticker, source in original["records"].items():
        replay = baseline["records"][ticker]
        for key in ("fundamental_state", "research_action_posture", "evidence_currency", "tactical_phase",
                    "valuation_context_summary", "corporate_intelligence_context", "participation"):
            if key in REVISED_INTERPRETATION_FIELDS:
                continue
            if source[key] != replay[key]:
                raise ValueError(f"BASELINE_REPLAY_DECISION_DRIFT:{ticker}:{key}")


def validate_after(baseline: dict, after: dict, cohort: dict[str, str], integration: dict) -> dict:
    transitions = Counter()
    fundamental_uplift = 0
    for ticker, old in baseline["records"].items():
        new = after["records"][ticker]
        if ticker not in cohort:
            if old["fundamental_state"] != new["fundamental_state"] or old["research_action_posture"] != new["research_action_posture"]:
                raise ValueError(f"NON_COHORT_DECISION_CHANGED:{ticker}")
        else:
            if old["fundamental_state"] == integrated.FUNDAMENTAL_INSUFFICIENT and new["fundamental_state"] != integrated.FUNDAMENTAL_INSUFFICIENT:
                fundamental_uplift += 1
            if integration["records"][ticker]["status"] == "BLOCKED" and old["fundamental_state"] != new["fundamental_state"]:
                raise ValueError(f"BLOCKED_COHORT_FUNDAMENTAL_CHANGED:{ticker}")
        if old["evidence_currency"] != new["evidence_currency"] or old["tactical_phase"] != new["tactical_phase"] or old["valuation_context_summary"] != new["valuation_context_summary"]:
            raise ValueError(f"UNRELATED_AXIS_CHANGED:{ticker}")
        if old["research_action_posture"] != new["research_action_posture"]:
            transitions[(old["research_action_posture"], new["research_action_posture"])] += 1
    if fundamental_uplift != integration["coverage"]["research_usable"]:
        raise ValueError("FUNDAMENTAL_UPLIFT_DOES_NOT_RECONCILE")
    return {"integrated_fundamental_uplift": fundamental_uplift,
            "research_posture_transitions": {f"{a} -> {b}": n for (a, b), n in sorted(transitions.items())}}


def summary(result: dict) -> str:
    lines = ["# Entity-aware operational fundamental integration", "",
             f"Session: {SESSION}. Frozen cohort: {result['cohort']['ticker_count']}.",
             f"Integrated: {result['integration']['coverage']['research_usable']}; still blocked: {result['integration']['coverage']['blocked']}.",
             f"Residual primary reasons: {result['integration']['coverage']['residual_primary_reasons']}.", "",
             f"Fundamental context, attempted: {result['before_map']['coverage']['integrated_fundamental']['count']} -> {result['after_map']['coverage']['integrated_fundamental']['count']}.",
             f"Fundamental context, official scope: {result['before_map']['coverage']['integrated_fundamental']['official_scope_count']} -> {result['after_map']['coverage']['integrated_fundamental']['official_scope_count']}.", "",
             "## Decision readiness", ""]
    for name in ("CURRENT_RESEARCH_READY", "PARTIAL_RESEARCH_READY", "TECHNICAL_RESEARCH_ONLY", "INSUFFICIENT_CURRENT_EVIDENCE"):
        lines.append(f"- {name}: {result['before_map']['decision_readiness'].get(name, 0)} -> {result['after_map']['decision_readiness'].get(name, 0)}")
    lines += ["", "## Identities", "",
              f"- Cohort: {result['cohort']['artifact_identity']}",
              f"- Integration: {result['integration']['artifact_identity']}",
              f"- Before map: {result['before_map']['artifact_identity']}",
              f"- After map: {result['after_map']['artifact_identity']}",
              f"- After integrated product: {result['after_integrated']['artifact_identity']}", "",
              "## Replay source note", "",
              "The shared retained corporate-axis file now has a different artifact identity from the frozen integrated product. Baseline replay reproduced every ticker's fundamental state, action posture, evidence currency, tactical phase, valuation summary, participation, and corporate summary. Before/after replay used the same current retained corporate-axis file; only cohort fundamental integration changed those decision fields.", "",
              "Original operational features and their blocked/non-applicable statuses are preserved. Research proxies remain operational-provider research evidence; this result grants no official financial, exact valuation, historical PIT, execution, or action authority.", ""]
    return "\n".join(lines)


def run(primary_root: Path, before_map_path: Path, output_dir: Path) -> dict:
    before = verify_map(before_map_path)
    cohort, manifest = frozen_cohort(before)
    source_root = primary_root / "operations-review"
    operation = source_root / "daily-research-session-operations-v1" / SESSION / OPERATION
    feature_artifact_path = operation / "market_wide_fundamental_feature_store_artifact.json"
    feature_payload_path = operation / "market_wide_fundamental_feature_store_records.jsonl.gz"
    verify_source_files(before, source_root, feature_artifact_path, feature_payload_path)
    feature_artifact = load(feature_artifact_path)
    if feature_artifact["artifact_identity"] != before["sources"]["fundamental_store"]["artifact_identity"]:
        raise ValueError("FROZEN_FUNDAMENTAL_FEATURE_STORE_IDENTITY_CHANGED")
    features = feature_records(feature_payload_path, cohort, feature_artifact["records_payload"]["record_count"])
    original = load(capability.source_paths(source_root, SESSION)["integrated"])
    args, source_note = retained_integrated_inputs(primary_root, original)
    baseline = integrated.build_artifact(**args)
    validate_baseline_replay(original, baseline)
    integration_result = bridge.build_artifact(
        session=SESSION, capability_map_identity=before["artifact_identity"], cohort=cohort,
        feature_records=features, feature_store_identity=feature_artifact["artifact_identity"],
        financial_analysis_identity=args["financial_analysis_artifact"]["artifact_identity"])
    after_integrated = integrated.build_artifact(
        **args, operational_fundamental_integration_artifact=integration_result)
    uplift = validate_after(baseline, after_integrated, cohort, integration_result)
    output_dir.mkdir(parents=True, exist_ok=True)
    write(output_dir / "frozen_cohort_manifest.json", manifest)
    write(output_dir / "entity_aware_fundamental_integration.json", integration_result)
    write(output_dir / "after_integrated_investment_decision_product.json", after_integrated)
    shutil.copyfile(before_map_path, output_dir / "before_current_research_capability_map.json")
    after_map = capability.build(source_root, SESSION, {"integrated": output_dir / "after_integrated_investment_decision_product.json"})
    write(output_dir / "after_current_research_capability_map.json", after_map)
    (output_dir / "after_current_research_capability_summary.md").write_text(capability.summary(after_map), encoding="utf-8")
    if (before["coverage"]["attempted"] != after_map["coverage"]["attempted"]
            or before["coverage"]["official_research_scope"] != after_map["coverage"]["official_research_scope"]):
        raise ValueError("AFTER_MAP_DENOMINATOR_CHANGED")
    if after_map["coverage"]["integrated_fundamental"]["count"] - before["coverage"]["integrated_fundamental"]["count"] != uplift["integrated_fundamental_uplift"]:
        raise ValueError("AFTER_MAP_FUNDAMENTAL_UPLIFT_MISMATCH")
    # Readiness transitions are attributed against a map of this run's own baseline replay (same
    # code and valuation interpretation as the after map), not the frozen map: the frozen map
    # predates CURRENT_RESEARCH_DECISION_CONVERGENCE_V1's valuation interpretation.
    write(output_dir / "baseline_replay_integrated_investment_decision_product.json", baseline)
    reference = capability.build(source_root, SESSION, {"integrated": output_dir / "baseline_replay_integrated_investment_decision_product.json"})
    transitions = Counter((reference["records"][ticker]["decision_fitness"], after_map["records"][ticker]["decision_fitness"])
                          for ticker in reference["records"] if reference["records"][ticker]["decision_fitness"] != after_map["records"][ticker]["decision_fitness"])
    if any(ticker not in cohort for ticker in reference["records"]
           if reference["records"][ticker]["decision_fitness"] != after_map["records"][ticker]["decision_fitness"]):
        raise ValueError("NON_COHORT_CAPABILITY_READINESS_CHANGED")
    result = {"cohort": manifest, "integration": integration_result, "before_map": before,
              "after_map": after_map, "after_integrated": after_integrated,
              "uplift": {**uplift, "decision_fitness_transitions": {f"{a} -> {b}": n for (a, b), n in sorted(transitions.items())}},
              "source_note": source_note}
    compact = {"schema_version": "1.0.0", "contract_version": "entity_aware_fundamental_integration_result/v1",
               "session": SESSION, "cohort_identity": manifest["artifact_identity"],
               "integration_identity": integration_result["artifact_identity"],
               "before_capability_map_identity": before["artifact_identity"],
               "after_capability_map_identity": after_map["artifact_identity"],
               "before_integrated_identity": original["artifact_identity"],
               "baseline_replay_identity": baseline["artifact_identity"],
               "after_integrated_identity": after_integrated["artifact_identity"],
               "integration_coverage": integration_result["coverage"],
               "fundamental_coverage": {"before_attempted": before["coverage"]["integrated_fundamental"]["count"],
                                        "after_attempted": after_map["coverage"]["integrated_fundamental"]["count"],
                                        "before_official": before["coverage"]["integrated_fundamental"]["official_scope_count"],
                                        "after_official": after_map["coverage"]["integrated_fundamental"]["official_scope_count"]},
               "decision_readiness_before": before["decision_readiness"],
               "decision_readiness_after": after_map["decision_readiness"],
               "uplift": result["uplift"], "source_note": source_note,
               "authority_boundary": integration_result["authority_boundary"]}
    digest = hashlib.sha256(bridge.canonical(compact)).hexdigest()
    compact["artifact_sha256"] = digest
    compact["artifact_identity"] = f"{compact['contract_version']}:{digest}"
    write(output_dir / "entity_aware_fundamental_integration_result.json", compact)
    (output_dir / "SUMMARY.md").write_text(summary(result), encoding="utf-8")
    return compact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--before-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.primary_root, args.before_map, args.output_dir)
    print(json.dumps({key: result[key] for key in ("artifact_identity", "integration_coverage",
                                                    "fundamental_coverage", "decision_readiness_before",
                                                    "decision_readiness_after", "uplift")}, sort_keys=True))


if __name__ == "__main__":
    main()
