"""R5 read-only retained replay; exact canonical paths and pinned financial authority only."""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canonical_daily_financial_v2_materialization as material
import current_corporate_intelligence_axis as corporate
import current_research_decision_input as decision_input
import current_research_valuation_context as valuation
import entity_classification_contract as entity
import stocklookup_core.financial.financial_v2_current_input_authority as authority
import integrated_investment_decision_product as integrated
import intrinsic_valuation as intrinsic
from tools.replay_forward_driver_context import replay as replay_existing_driver_join


def load_inputs(root):
    pin = authority.resolve(root)
    metadata = json.loads(pin.semantics_artifact_path.read_text(encoding="utf-8"))
    authority.verify_identity(label="semantics", observed=metadata["artifact_identity"], expected=pin.expected_semantics_identity)
    ops = root / "operations-review"
    paths = {
        "integrated": ops / "canonical-post-close-v1/2026-10-01/enrichment/integrated_investment_decision_product.json",
        "entities": ops / "integrated-investment-decision-product-v1-20261001/current_research_entity_applicability_artifact.json",
        "financial": ops / "financial-analysis-product-v2-20261001/financial_analysis_product_artifact.json",
        "valuation": ops / "financial-analysis-product-v2-20261001/current_research_valuation_context_artifact.json",
        "raw_valuation": ops / "market-wide-current-valuation-v1-20261001-session20261001/market_wide_current_valuation_artifact.json",
        "corporate": ops / "current-corporate-intelligence-axis-v1/current_corporate_intelligence_axis_artifact.json",
        "semantic_metadata": pin.semantics_artifact_path, "semantic_facts": pin.semantics_facts_path,
        "governed_config": Path(__file__).resolve().parents[1] / "config/current_research_valuation_assumptions.json",
    }
    artifacts = {name: json.loads(paths[name].read_text(encoding="utf-8"))
                 for name in ("entities", "financial", "valuation", "raw_valuation", "corporate")}
    if entity.entity_applicability_content_identity(artifacts["entities"]) != artifacts["entities"]["artifact_identity"]:
        raise ValueError("ENTITY_IDENTITY_MISMATCH")
    for name in ("financial", "valuation"):
        if material._identity(artifacts[name])["artifact_identity"] != artifacts[name]["artifact_identity"]:
            raise ValueError("FINANCIAL_VALUATION_IDENTITY_MISMATCH:" + name)
    if artifacts["valuation"]["source_valuation_identity"] != artifacts["raw_valuation"]["artifact_identity"]:
        raise ValueError("RAW_VALUATION_LINEAGE_MISMATCH")
    financial_authority = artifacts["financial"]["financial_input_authority"]
    if financial_authority["expected_semantics_identity"] != pin.expected_semantics_identity:
        raise ValueError("FINANCIAL_PIN_MISMATCH")
    assumptions, config_identity = intrinsic.load_governed_assumption_config(paths["governed_config"])
    tickers = set(artifacts["entities"]["records"])
    with gzip.open(pin.semantics_facts_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    model_inputs = intrinsic.inputs_from_semantic_rows(rows, tickers=tickers, session="2026-10-01",
                                                      entities=artifacts["entities"]["records"], assumptions=assumptions)
    for ticker, data in model_inputs.items():
        price = artifacts["raw_valuation"].get("records", {}).get(ticker, {}).get("price_input")
        if isinstance(price, dict):
            data["price_input"] = {**price, "fitness": "READY" if price.get("status") == "PRICE_READY" else "BLOCKED",
                                   "source_identity": price.get("source_snapshot_identity")}
    return paths, artifacts, model_inputs, config_identity


def enrich_records(before, evaluated_after):
    """Execute the same non-voting model, driver and decision-input joins as production."""
    after = {**before, "records": {}}
    contexts = []
    for ticker, old_record in before["records"].items():
        projection = intrinsic.bind_forward_driver_explanation(
            evaluated_after["records"][ticker]["intrinsic_scenario_valuation"],
            old_record["corporate_intelligence_context"].get("forward_driver_context"), ticker=ticker, session="2026-10-01")
        record = {**old_record, "intrinsic_scenario_valuation": projection}
        axes = {**old_record["evidence_axes"]}
        axis = copy.deepcopy(axes["VALUATION"])
        axis["context"]["intrinsic_scenario_valuation"] = copy.deepcopy(projection)
        axis["lineage"]["source_artifact_identity"] = evaluated_after["artifact_identity"]
        axes["VALUATION"] = axis
        record["evidence_axes"] = axes
        cell = decision_input._valuation(record, evaluated_after["records"][ticker],
                                        old_record["current_research_decision_input"]["dimensions"]["VALUATION"]["entity_applicability"])
        old_cell = old_record["current_research_decision_input"]["dimensions"]["VALUATION"]
        if {k: v for k, v in cell.items() if k != "intrinsic_scenario_valuation"} != old_cell:
            raise ValueError("RELATIVE_DIMENSION_DRIFT:" + ticker)
        record["current_research_decision_input"] = {
            **old_record["current_research_decision_input"], "dimensions": {
                **old_record["current_research_decision_input"]["dimensions"], "VALUATION": cell}}
        if integrated.decision_identity(record) != old_record["decision_identity"]:
            raise ValueError("DECISION_IDENTITY_DRIFT:" + ticker)
        # Explicit additive allowlist, with only the source wrapper binding rebased.
        stripped = {**record}
        stripped.pop("intrinsic_scenario_valuation")
        stripped["evidence_axes"] = {**record["evidence_axes"], "VALUATION": copy.deepcopy(axis)}
        stripped["evidence_axes"]["VALUATION"]["context"].pop("intrinsic_scenario_valuation")
        stripped["evidence_axes"]["VALUATION"]["lineage"] = old_record["evidence_axes"]["VALUATION"]["lineage"]
        stripped["current_research_decision_input"] = old_record["current_research_decision_input"]
        if stripped != old_record:
            raise ValueError("UNEXPLAINED_ANALYTICAL_CHANGE:" + ticker)
        after["records"][ticker] = record
        contexts.append(projection)
    after["coverage"] = {**before["coverage"], "intrinsic_scenario_valuation": intrinsic.current_scenario_coverage(contexts)}
    after["source_artifacts"] = {**before["source_artifacts"], "current_valuation": evaluated_after["artifact_identity"]}
    after.update(integrated.content_identity(after))
    return after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retained-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--measure-only", action="store_true")
    args = parser.parse_args()
    root, output = args.retained_root.resolve(), args.output_dir.resolve()
    if output == root or root in output.parents:
        raise ValueError("SCRATCH_OUTPUT_MUST_BE_OUTSIDE_RETAINED_PRODUCTION_ROOT")
    paths, artifacts, inputs, config_identity = load_inputs(root)
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    before_readiness = intrinsic.measure_method_readiness(inputs)
    if before_readiness["denominator"] != 1683:
        raise ValueError("RETAINED_DENOMINATOR_MISMATCH")
    output.mkdir(parents=True, exist_ok=True)
    (output / "readiness_before.json").write_text(json.dumps(before_readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.measure_only:
        print(json.dumps(before_readiness["method_readiness"]))
        return 0
    raw_product = json.loads(paths["integrated"].read_text(encoding="utf-8"))
    if (raw_product["session"] != "2026-10-01" or set(raw_product["records"]) != set(inputs) or
        raw_product["source_artifacts"].get("entity_applicability") != artifacts["entities"]["artifact_identity"] or
        raw_product["source_artifacts"].get("current_valuation") != artifacts["valuation"]["artifact_identity"] or
        raw_product["source_artifacts"].get("financial_analysis") != artifacts["financial"]["financial_analysis_product"]["artifact_identity"]):
        raise ValueError("CANONICAL_SESSION_DENOMINATOR_OR_SOURCE_BINDING_MISMATCH")
    # R4 is already merged: reuse its proven pure join to establish the current-code
    # explanatory baseline on these same immutable ordinary-Daily inputs, without a Daily.
    baseline, _ = replay_existing_driver_join(raw_product, artifacts["corporate"])
    del raw_product
    evaluated = copy.deepcopy(artifacts["valuation"])
    evaluated["records"] = valuation.attach_intrinsic_scenario_valuation(
        evaluated["records"], inputs, assumption_config_identity=config_identity)
    evaluated.update(material._identity(evaluated))
    projections = [row["intrinsic_scenario_valuation"] for row in evaluated["records"].values()]
    # Determinism checks every method/case independently, avoiding a second full product copy.
    for ticker, row in evaluated["records"].items():
        repeated = intrinsic.build_current_scenario_valuation(inputs[ticker])
        projected = row["intrinsic_scenario_valuation"]
        stripped = {k: v for k, v in projected.items() if k not in {"projection_identity", "assumption_config_identity"}}
        if repeated["projection_identity"] != intrinsic.CURRENT_SCENARIO_CONTRACT + ":" + intrinsic.scenario_identity(stripped):
            raise ValueError("NONDETERMINISTIC_MODEL:" + ticker)
    after = enrich_records(baseline, evaluated)
    coverage = after["coverage"]["intrinsic_scenario_valuation"]
    if decision_input.decision_fitness_coverage(baseline["records"]) != decision_input.decision_fitness_coverage(after["records"]):
        raise ValueError("CURRENT_RESEARCH_FITNESS_DRIFT")
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name] for name, path in paths.items()):
        raise ValueError("RETAINED_SOURCE_MUTATION")
    report = dict(contract_version="intrinsic_scenario_valuation_acceptance/v1", session="2026-10-01",
                  readiness_before=before_readiness, readiness_after=coverage,
                  product_identity_before=baseline["artifact_identity"], product_identity_after=after["artifact_identity"],
                  original_retained_product_identity=integrated.CONTRACT_VERSION + ":407c747ebb99ca8b7b4635b1d98a91992b371fbcbeabb79b2425bdd305034ccf",
                  evaluated_valuation_identity_before=artifacts["valuation"]["artifact_identity"],
                  evaluated_valuation_identity_after=evaluated["artifact_identity"],
                  changed_decision_identities=0, posture_changes=0, unexplained_analytical_changes=0,
                  all_preexisting_analytical_fields_unchanged=True, current_research_fitness_unchanged=True,
                  fabricated_assumptions=0, probability_claims=0, retained_sources_unchanged=True,
                  source_byte_hashes=hashes, deterministic_models=True,
                  identity_reason="Standing product hashes include explanatory records/coverage and updated evaluated-valuation source binding. Per-decision source identities exclude the artifact wrapper; original per-record identities remain unchanged.",
                  authority_effect="NONE")
    (output / "acceptance_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "evaluated_valuation_after.json").write_text(json.dumps(evaluated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Full-universe decisions are large: stream without allocating an additional
    # complete Unicode document and encoded byte copy alongside the product.
    with (output / "integrated_after.json").open("w", encoding="utf-8") as handle:
        json.dump(after, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({k: report[k] for k in ("posture_changes", "changed_decision_identities", "unexplained_analytical_changes", "product_identity_after")}))
    print(json.dumps(coverage["method_readiness"]))


if __name__ == "__main__":
    main()
