"""Read-only replay of the forward-driver join against explicitly supplied retained inputs.

Writes only to the explicitly supplied scratch output directory. Never discovers sources,
acquires evidence, runs Daily, or edits an input. Rejects source identity or baseline drift.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import current_corporate_intelligence_axis as axis
import current_research_decision_input as decision_input
import integrated_investment_decision_product as product


def replay(before: dict, source: dict) -> tuple[dict, dict]:
    if before.get("contract_version") != product.CONTRACT_VERSION:
        raise ValueError("INTEGRATED_DECISION_CONTRACT_REQUIRED")
    if source.get("contract_version") != axis.CONTRACT_VERSION:
        raise ValueError("CORPORATE_AXIS_CONTRACT_REQUIRED")
    if product.content_identity(before)["artifact_identity"] != before.get("artifact_identity"):
        raise ValueError("RETAINED_PRODUCT_IDENTITY_MISMATCH")
    if axis.content_identity(source)["artifact_identity"] != source.get("artifact_identity"):
        raise ValueError("RETAINED_CORPORATE_IDENTITY_MISMATCH")
    if before["source_artifacts"].get("corporate_intelligence") != source["artifact_identity"]:
        raise ValueError("RETAINED_CORPORATE_LINEAGE_MISMATCH")
    after = copy.deepcopy(before)
    contexts = []
    enriched = 0
    for ticker, record in sorted(after["records"].items()):
        summary = product.evaluate_corporate_intelligence_context(
            source["records"].get(ticker), as_of_session=before["session"], ticker=ticker)
        context = summary.pop("forward_driver_context")
        if summary != record["corporate_intelligence_context"]:
            raise ValueError("RETAINED_SUMMARY_DRIFT:" + ticker)
        summary["forward_driver_context"] = context
        record["corporate_intelligence_context"] = summary
        record["evidence_axes"]["CORPORATE_INTELLIGENCE"]["context"]["forward_driver_context"] = copy.deepcopy(context)
        cell = decision_input._corporate(record)
        old_cell = before["records"][ticker]["current_research_decision_input"]["dimensions"]["CORPORATE"]
        stripped_cell = {k: v for k, v in cell.items() if k != "forward_driver_context"}
        if stripped_cell != old_cell:
            raise ValueError("RETAINED_DIMENSION_DRIFT:" + ticker)
        record["current_research_decision_input"]["dimensions"]["CORPORATE"] = cell
        contexts.append(context)
        enriched += bool(context["drivers"])
        if product.decision_identity(record) != record["decision_identity"]:
            raise ValueError("DECISION_IDENTITY_DRIFT:" + ticker)
    coverage = axis.forward_driver_coverage(contexts)
    after["coverage"]["forward_driver_context"] = coverage
    after.update(product.content_identity(after))
    # Exact additive allowlist: removing these four additions must reproduce all bytes
    # represented by the original parsed artifact, including every analytical field.
    stripped = copy.deepcopy(after)
    stripped["coverage"].pop("forward_driver_context")
    for record in stripped["records"].values():
        record["corporate_intelligence_context"].pop("forward_driver_context")
        record["evidence_axes"]["CORPORATE_INTELLIGENCE"]["context"].pop("forward_driver_context")
        record["current_research_decision_input"]["dimensions"]["CORPORATE"].pop("forward_driver_context")
    stripped.update(product.content_identity(stripped))
    if stripped != before:
        raise ValueError("UNEXPLAINED_REPLAY_CHANGE")
    states = dict(sorted(Counter(r["current_research_decision_input"]["dimensions"]["CORPORATE"]["state"]
                                 for r in before["records"].values()).items()))
    for state in ("AVAILABLE", "PARTIAL", "BLOCKED", "NON_APPLICABLE"):
        states.setdefault(state, 0)
    source_events = [event for record in source["records"].values() for event in record.get("events") or []]
    distributions_before = {
        label: dict(sorted(Counter(event.get(field) or "UNKNOWN" for event in source_events).items()))
        for label, field in (("event_type", "event_type"), ("status", "status"),
                             ("materiality", "materiality"), ("freshness", "freshness"))
    }
    if decision_input.decision_fitness_coverage(before["records"]) != decision_input.decision_fitness_coverage(after["records"]):
        raise ValueError("DECISION_FITNESS_DRIFT")
    report = dict(session=before["session"], denominator=len(contexts),
                  retained_distributions_before=distributions_before,
                  retained_distributions_after={"event_type": coverage["driver_type_distribution"],
                                                "status": coverage["canonical_status_distribution"],
                                                "materiality": coverage["materiality_distribution"],
                                                "freshness": coverage["freshness_distribution"]},
                  freshness_projection_reason="Existing recency rule evaluated at October 1 instead of retained September 5; original source freshness preserved per driver.",
                  decision_fitness_coverage_unchanged=True,
                  corporate_dimension_before=states, corporate_dimension_after=states,
                  qualified_driver_before="NOT_EXPOSED", qualified_driver_after=coverage,
                  records_with_retained_events_enriched=enriched,
                  records_without_events_with_explicit_absence=len(contexts)-enriched,
                  records_additively_projected=len(contexts),
                  preexisting_record_fields_unchanged=len(contexts),
                  decision_identities_changed=0, posture_changes=0, unexplained_changes=0,
                  product_identity_before=before["artifact_identity"], product_identity_after=after["artifact_identity"],
                  product_identity_reason="Standing content identity hashes all explanatory record/coverage additions; decision identity excludes them and retains original source identities.",
                  authority_effect="NONE")
    return after, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--integrated-input", type=Path, required=True)
    parser.add_argument("--corporate-input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.integrated_input.resolve(), args.corporate_input.resolve()]
    output = args.output_dir.resolve()
    if any(output == p.parent or output in p.parents for p in inputs):
        raise ValueError("OUTPUT_MUST_BE_SEPARATE_FROM_RETAINED_INPUTS")
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    before, source = [json.loads(p.read_text(encoding="utf-8")) for p in inputs]
    after, report = replay(before, source)
    if replay(before, source) != (after, report):
        raise ValueError("NONDETERMINISTIC_REPLAY")
    report["source_byte_hashes"] = hashes
    report["source_bytes_unchanged"] = all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in inputs)
    if not report["source_bytes_unchanged"]:
        raise ValueError("SOURCE_BYTES_CHANGED")
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("integrated_after.json", after), ("replay_report.json", report)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
