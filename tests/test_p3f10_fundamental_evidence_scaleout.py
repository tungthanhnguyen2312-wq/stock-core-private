from __future__ import annotations

import inspect

from p3f10_fundamental_evidence_scaleout import build_scaleout_artifact


def _cohort():
    return {"name": "COHORT_EMPIRICALLY_ACTIVE", "cohort_identity": "cohort:test", "as_of_session": "2026-08-20", "members": ["AAA", "BBB", "CCC"], "authority": "DERIVED_SHADOW_DENOMINATOR_ONLY", "observed_session_requirement": "complete"}


def test_generic_dispositions_preserve_raw_without_qualification_and_are_deterministic():
    artifact = build_scaleout_artifact(
        cohort=_cohort(),
        raw_records={"AAA": {"observation_count": 1, "statement_families": ["balance_sheet"], "providers": ["VCI"]}, "BBB": {"observation_count": 1, "statement_families": ["income_statement"], "providers": ["KBS"]}},
        canonical_records={"AAA": {"fact_count": 2, "status_counts": {"provider_reported": 2}, "template_family": None}, "BBB": {"fact_count": 0, "status_counts": {}, "template_family": "credit_institution"}},
        qualified_readiness={"AAA": {"fundamental_research_readiness": "PARTIAL"}}, qualified_sectors={"AAA": "corporate"},
        qualified_metric_counts={"EXACT_QUALIFIED": 1, "DERIVED_PROXY": 0}, source_inventory=[], source_artifacts={},
    )
    assert artifact["coverage"]["raw_retained"] == 2
    assert artifact["coverage"]["evidence_qualified_instruments"] == 1
    assert {row["ticker"]: row["disposition"] for row in artifact["instrument_dispositions"]} == {"AAA": "EVIDENCE_QUALIFIED", "BBB": "SCHEMA_UNSUPPORTED", "CCC": "SOURCE_MISSING"}
    assert artifact["instrument_dispositions"][0]["statement_scope"] == "consolidated"
    assert artifact["authority_boundaries"]["source_authority_promoted"] is False
    assert artifact["ticker_specific_branch_audit"]["production_ticker_literals"] == []
    repeat = build_scaleout_artifact(
        cohort=_cohort(),
        raw_records={"AAA": {"observation_count": 1, "statement_families": ["balance_sheet"], "providers": ["VCI"]}, "BBB": {"observation_count": 1, "statement_families": ["income_statement"], "providers": ["KBS"]}},
        canonical_records={"AAA": {"fact_count": 2, "status_counts": {"provider_reported": 2}, "template_family": None}, "BBB": {"fact_count": 0, "status_counts": {}, "template_family": "credit_institution"}},
        qualified_readiness={"AAA": {"fundamental_research_readiness": "PARTIAL"}}, qualified_sectors={"AAA": "corporate"},
        qualified_metric_counts={"EXACT_QUALIFIED": 1, "DERIVED_PROXY": 0}, source_inventory=[], source_artifacts={},
    )
    assert artifact["artifact_identity"] == repeat["artifact_identity"]


def test_production_contract_has_no_ticker_specific_branch_and_banks_remain_sector_gated():
    source = inspect.getsource(build_scaleout_artifact)
    assert "if ticker ==" not in source
    artifact = build_scaleout_artifact(
        cohort={**_cohort(), "members": ["BANK"]}, raw_records={"BANK": {"observation_count": 2, "statement_families": [], "providers": ["VCI"]}},
        canonical_records={"BANK": {"fact_count": 2, "status_counts": {"provider_reported": 2}, "template_family": "credit_institution"}},
        qualified_readiness={}, qualified_sectors={}, qualified_metric_counts={}, source_inventory=[], source_artifacts={},
    )
    assert artifact["sector_breakdown"]["bank"]["BLOCKED"] == 1
    assert artifact["readiness_contract"]["bank_and_securities_industrial_fcff_gate"] == "NOT_APPLICABLE"
