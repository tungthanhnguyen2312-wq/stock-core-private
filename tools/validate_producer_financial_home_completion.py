"""Offline qualification of retained Producer checkpoints; never publishes or admits facts.

Inputs and output locations are explicit. Candidate code must be an exact clean
checkpoint, loaded in a separate process by invoking this script. No Daily runner,
OCR subprocess, database, network, or release publisher is called.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

FIELDS = ("ticker", "as_of_session", "research_action_posture", "entry_state",
          "evidence_currency", "position_context", "why", "reference_trigger", "counter_thesis")
READY = {"READY", "RESEARCH_PROXY", "STALE_BUT_RESEARCH_USABLE"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_input(root, relative):
    root = Path(root).resolve()
    result = (root / relative).resolve()
    require(result.is_relative_to(root), "INPUT_PATH_ESCAPES_ROOT")
    return result


def snapshot(paths):
    paths = [str(Path(p).resolve()) for p in paths]
    require(len(paths) == len(set(paths)), "DUPLICATE_PROTECTED_PATH")
    return {p: {"sha256": digest(p), "bytes": Path(p).stat().st_size} for p in sorted(paths)}


def compare_snapshot(before):
    after = snapshot(before)
    require(after == before, "PROTECTED_INPUT_CHANGED")
    return {"file_count": len(before), "exact_byte_parity": True, "files": after}


def check_output(output, inputs):
    output = Path(output).resolve()
    for value in inputs:
        source = Path(value).resolve()
        require(output != source and not source.is_relative_to(output)
                and (not source.is_dir() or not output.is_relative_to(source)),
                "OUTPUT_OVERLAPS_INPUT")
    require(not output.exists(), "OUTPUT_ALREADY_EXISTS")
    return output


def verify_checkpoint(root, checkpoint):
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    require(len(checkpoint) == 40 and git("rev-parse", "HEAD") == checkpoint,
            "CANDIDATE_CHECKPOINT_MISMATCH")
    require(not git("status", "--porcelain"), "CANDIDATE_NOT_CLEAN")


def coverage(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(bool(rows), "EMPTY_METRIC_MATRIX")
    require(len({(r["ticker"], r["metric"]) for r in rows}) == len(rows), "DUPLICATE_METRIC_ROW")
    result = {}
    for metric in sorted({r["metric"] for r in rows}):
        selected = [r for r in rows if r["metric"] == metric]
        reasons = Counter(reason for r in selected for reason in json.loads(r["blockers"]))
        result[metric] = {"available": sum(bool(r["value"]) and r["fitness"] in READY for r in selected),
                          "fitness": dict(sorted(Counter(r["fitness"] for r in selected).items())),
                          "refusal_reasons": dict(sorted(reasons.items()))}
    return result


def compatible_income(asset, income, record, session):
    """Validate source semantics only. Does not calculate any return or create a panel row."""
    lineage = asset["source_lineage"]
    sha = record["sha256"]
    require(asset["canonical_metric"] == "total_assets" and income["canonical_metric"] == "net_income",
            "ASSETS_REQUIRE_TOTAL_NET_INCOME")
    require(lineage["document_sha256"] == income["document_sha256"] == sha,
            "INCOME_ASSETS_DOCUMENT_MISMATCH")
    require(lineage["statement_scope_evidence"]["statement_scope"] == income["statement_scope"] == "consolidated",
            "INCOME_ASSETS_SCOPE_MISMATCH")
    require(asset["currency"] == income["currency"] == "VND" and asset["unit_scale"] == income["source_unit_scale"]
            and income["already_normalized"] is True and income["unit_scale"] == 1,
            "INCOME_ASSETS_CURRENCY_SCALE_MISMATCH")
    require(asset["reporting_period"] == income["reporting_period"] == "2026-H1"
            and income["period_start"] == "2026-01-01" and income["period_end"] == "2026-06-30"
            and income["temporal_nature"] == "duration", "INCOME_ASSETS_PERIOD_MISMATCH")
    observed = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
    known = datetime.fromisoformat(income["knowledge_available_at"].replace("Z", "+00:00"))
    require(observed == known and known.date().isoformat() <= session, "INPUT_NOT_KNOWN_BY_SESSION")
    assurance = income.get("assurance_evidence") or {}
    require(assurance.get("state") == "QUALIFIED" and assurance.get("document_sha256") == sha
            and assurance.get("scope_of_assurance") == "consolidated_interim_statements",
            "SAME_DOCUMENT_CONSOLIDATED_ASSURANCE_REQUIRED")
    return {"total_net_income_vnd": income["value"], "income_citation_id": income["citation_id"],
            "period_start": income["period_start"], "period_end": income["period_end"],
            "knowledge_available_at": income["knowledge_available_at"], "statement_scope": "consolidated",
            "raw_observed_at": record["observed_at"],
            "asset_knowledge_available_at": "UNADMITTED_CANDIDATE_NOT_INFERRED_FROM_RAW_OBSERVATION",
            "asset_metric_knowledge_time_eligible": False,
            "publication_time_qualified": False, "historical_pit_authority": False,
            "assurance_evidence": assurance, "calculation_performed": False}


def financial_probe(probe_path, evidence_root, manifest_path, official_path, matrix_path, session):
    import official_financial_ocr_table_evidence as ocr
    probe = read_json(probe_path)
    record = probe["record"]
    retained = read_json(manifest_path)["records"]
    require(sum(r == record for r in retained) == 1, "ACQUISITION_RECORD_NOT_EXACTLY_RETAINED")
    source = safe_input(evidence_root, record["relative_path"])
    require(digest(source) == record["sha256"], "RETAINED_DOCUMENT_HASH_MISMATCH")
    temporal = record["temporal_retention"]
    require(temporal["observation_identity"] == record["sha256"]
            and temporal["observation_identity_method"] == "RAW_BYTES_SHA256", "OBSERVATION_IDENTITY_MISMATCH")
    require(record["source_id"] == "issuer_ir" and record["ticker"] == "VRE"
            and record["canonical_url"].startswith("https://ir.vincom.com.vn/")
            and record["final_url"] == record["canonical_url"], "RETAINED_ISSUER_ROUTE_MISMATCH")
    material = probe["material"]
    require(material["document_sha256"] == record["sha256"] and material["materialization_id"] ==
            ocr._hash({"document_sha256": record["sha256"], "pages": material["pages"]}), "OCR_MATERIAL_IDENTITY_MISMATCH")
    unit = ocr.resolve_scoped_unit_evidence(material)
    scope = ocr.resolve_scoped_statement_scope_evidence(material)
    facts = ocr.qualify_table_facts(material, ticker="VRE", reporting_period="2026-H1",
                                  scoped_unit_evidence=unit, scoped_statement_scope_evidence=scope)
    require(facts == probe["facts"] and unit == probe["unit"] and scope == probe["scope"], "OCR_REQUALIFICATION_CHANGED")
    assets = [r for r in facts["qualified_facts"] if r["canonical_metric"] == "total_assets"]
    require(len(assets) == 1, "UNIQUE_QUALIFIED_ASSETS_REQUIRED")
    asset = assets[0]
    require(asset["value"] == 62_806_214_000_000 and asset["unit_scale"] == 1_000_000
            and asset["source_lineage"]["line_code"] == "280", "ASSET_VALUE_OR_SCALE_MISMATCH")
    official = read_json(official_path)
    income = [r for r in official if r["ticker"] == "VRE" and r["canonical_metric"] == "net_income"
              and r["reporting_period"] == "2026-H1"]
    require(len(income) == 1, "UNIQUE_H1_TOTAL_INCOME_REQUIRED")
    semantics = compatible_income(asset, income[0], record, session)
    require(not any(r["ticker"] == "VRE" and r["canonical_metric"] == "total_assets"
                    and r["reporting_period"] == "2026-H1" for r in official), "ASSETS_ALREADY_ADMITTED")
    inventory = coverage(matrix_path)
    return {"asset_candidate": asset, "source_record": record, "income_compatibility": semantics,
            "candidate_admitted_to_panel": False, "new_inputs_published": 0, "new_metrics_published": 0,
            "before": inventory, "after": inventory, "matrix_sha256": digest(matrix_path),
            "admitted_fact_count": len(official), "metric_coverage_changed": False,
            "refusal": "COMPLETE_LOCAL_LEASES_AND_EQUITY_ONLY_REPORTED_PERIOD_RETURN_CONTRACT"}


def card_parity(summary, index):
    import dashboard_home_summary as home
    require(home.content_identity(summary)["artifact_identity"] == summary["artifact_identity"], "HOME_IDENTITY_MISMATCH")
    block = summary["notable_cards"]
    require(block.get("contract_version") == "dashboard_home_notable_cards/v1"
            and block.get("source_contract_version") == index.get("contract_version") == "workspace_index/v1"
            and block.get("selection") == "PUBLISHED_INSERTION_ORDER_NOTABLE_MEMBERSHIP_V1"
            and block.get("selection_limit") == 4, "CARD_CONTRACT_MISMATCH")
    require(block["as_of_session"] == index["as_of_session"] == summary["as_of_session"]
            and block["source_artifact_identity"] == index["source_artifact_identity"], "CARD_SOURCE_BINDING_MISMATCH")
    expected = []
    for card in index["cards"].values():
        posture = card["research_action_posture"]
        if (posture in {"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST", "EARLY_WATCH"}
                or (card["entry_state"] in {"BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE", "BASE_BUILDING"}
                    and posture not in {"AVOID", "REDUCE"})):
            require(all(field in card for field in FIELDS), "THIN_CARD_FIELD_MISSING")
            expected.append({field: card[field] for field in FIELDS})
            if len(expected) == 4:
                break
    require(block["cards"] == expected, "VERBATIM_CARD_ORDER_OR_FIELD_MISMATCH")
    return [card["ticker"] for card in expected]


def home_probe(presentation):
    import dashboard_home_summary as home
    from workspace_public_read_model import build_public_read_model
    from canonical_dashboard_runtime_release import _derive_restaged_home_summary
    presentation = Path(presentation)
    screener = read_json(presentation / "screener_master_projection.json")
    workspace = read_json(presentation / "investment_decision_workspace_projection.json")
    legacy = read_json(presentation / "dashboard_home_summary.json")
    index, _ = build_public_read_model(workspace)
    session = legacy["as_of_session"]
    old = _derive_restaged_home_summary(screener, workspace=workspace, session=session,
                                      fallback_requested_at=legacy["requested_at"], include_notable_cards=False)
    require(old == legacy, "LEGACY_HOME_TWIN_CHANGED")
    extended = home.with_notable_cards(legacy, index)
    restaged = _derive_restaged_home_summary(screener, workspace=workspace, session=session,
                                           fallback_requested_at=legacy["requested_at"], include_notable_cards=True)
    require(extended == restaged, "HOME_RESTAGE_PARITY_FAILED")
    tickers = card_parity(extended, index)
    empty = home.with_notable_cards(legacy, {**index, "cards": {}})
    require(empty["notable_cards"]["cards"] == [] and empty["artifact_identity"] != legacy["artifact_identity"],
            "EMPTY_AND_ABSENT_COLLAPSED")
    # Exercise the real source publication writer with retained owners supplied
    # as fixtures. No acquisition/financial computation or production root read.
    import canonical_current_product_projections as publication
    with tempfile.TemporaryDirectory(prefix="producer-home-staging-") as scratch:
        root = Path(scratch)
        overrides = {
            "resolve_supplementary_inputs": {}, "resolve_velocity_and_flow_price_inputs": {},
            "resolve_current_research_official_universe_scope": None,
            "materialize_current_fundamental_feature_store_context": {"status": "UNAVAILABLE"},
            "materialize_current_tactical_behavior_context": {"status": "UNAVAILABLE"},
            "materialize_current_investment_decision_workspace": {"workspace": workspace},
            "materialize_current_screener_master_projection": screener,
        }
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name, value in overrides.items():
                stack.enter_context(patch.object(publication, name, return_value=value))
            staged = publication.materialize_and_write_current_product_projections(
                root=root, session=session, operation_dir=root / "operation", registry_inputs={},
                requested_at=legacy["requested_at"], runtime_root_override=root / "runtime")
        require(staged["status"] == "MATERIALIZED"
                and staged["dashboard_home_summary"]["status"] == "MATERIALIZED", "SOURCE_HOME_STAGING_FAILED")
        staged_json = read_json(root / "operation" / "dashboard_home_summary.json")
        staged_js = (root / "operation" / "dashboard_home_summary.js").read_text(encoding="utf-8")
        require(staged_json == extended and staged_js == home.js_fallback(extended), "SOURCE_JSON_JS_STAGING_PARITY_FAILED")
    return {"session": session, "legacy_identity": legacy["artifact_identity"],
            "fixture_identity": extended["artifact_identity"], "source_identity": index["source_artifact_identity"],
            "notable_tickers": tickers, "nine_field_parity": True, "legacy_twin_parity": True,
            "restage_parity": True, "empty_distinct_from_absent": True,
            "source_publication_staging_parity": True,
            "publication": "FIXTURE_ONLY_EXISTING_CHECKPOINT_NOT_INTEGRATED_CURRENT_MAIN"}, extended


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-checkout", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--acquisition-manifest", required=True, type=Path)
    parser.add_argument("--official-facts", required=True, type=Path)
    parser.add_argument("--metric-matrix", required=True, type=Path)
    parser.add_argument("--presentation", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--protected-snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    inputs = [args.candidate_checkout, args.probe, args.evidence_root, args.acquisition_manifest,
              args.official_facts, args.metric_matrix, args.presentation, args.protected_snapshot]
    protected = read_json(args.protected_snapshot)
    output = check_output(args.output, [*inputs, *protected])
    verify_checkpoint(args.candidate_checkout, args.candidate_sha)
    sys.path.insert(0, str(args.candidate_checkout.resolve()))
    input_hashes = snapshot(p for p in inputs if p.is_file())
    financial = financial_probe(args.probe, args.evidence_root, args.acquisition_manifest,
                                args.official_facts, args.metric_matrix, args.session)
    home, fixture = home_probe(args.presentation)
    compare_snapshot(input_hashes)
    preservation = compare_snapshot(protected)
    verify_checkpoint(args.candidate_checkout, args.candidate_sha)
    result = {"disposition": "PARTIAL_BLOCKED_NATIVE_LEASE_TRANSFER_UNAVAILABLE",
              "candidate_sha": args.candidate_sha, "financial": financial, "home": home,
              "protected_outputs": preservation, "input_hashes": input_hashes,
              "authority_effect": "NONE", "production_operation": False}
    output.mkdir(parents=True)
    for name, value in (("acceptance.json", result), ("home-fixture.json", fixture)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"disposition": result["disposition"], "home": home,
                      "new_metrics_published": 0, "protected_file_count": len(protected)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
