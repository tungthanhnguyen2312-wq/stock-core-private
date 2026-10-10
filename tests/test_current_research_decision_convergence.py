"""CURRENT_RESEARCH_DECISION_CONVERGENCE_V1: Daily binding, entity applicability, valuation
convergence, and the per-ticker Current Research decision input.

Every artifact below is built by the production builders; fixtures only supply retained-shaped
inputs. Nothing here reads canonical retained evidence or the runtime store.
"""
from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

import ai_research_session_delivery as delivery
import stocklookup_core.decision.current_research_decision_input as decision_input
import entity_classification_contract as entity_contract
import stocklookup_core.decision.integrated_investment_decision_product as iidp
import market_wide_fundamental_feature_store as feature_store
import operational_fundamental_context_integration as bridge
import same_session_technical_coverage_disposition as disposition_module
from _integrated_decision_fixture import disposition_artifact, disposition_record
from stocklookup_core.valuation.current_research_valuation_context import evaluate_ticker_valuation, readiness_period_blocker
from tools import current_research_capability_map as capability

SESSION = "2026-09-24"
REQUESTED_AT = f"{SESSION}T15:00:00+07:00"
FA_IDENTITY = "financial_analysis_product_integration/v1:fixture"


# ── fixtures ────────────────────────────────────────────────────────────────────────────────────

def _feature(feature_id: str, *, state: str | None = None, periods: tuple[str, ...] = ("2026-Q1",),
             status: str = "READY_RESEARCH_PROXY") -> dict:
    balance = feature_id.endswith("pit_trajectory")
    return {
        "feature_id": feature_id, "value": 1, "categorical_state": state, "status": status, "research_fitness": status,
        "method": "same_native_point_in_time_trajectory/v1" if balance else "same_native_latest_sign/v1",
        "compatibility_class": "POINT_IN_TIME_TRAJECTORY_COMPATIBLE" if balance else "SAME_NATIVE_SERIES_RESEARCH_COMPATIBLE",
        "compatibility_rule_version": feature_store.COMPATIBILITY_VERSION,
        "input_periods": list(periods),
        "duration_semantics": ["POINT_IN_TIME_BALANCE_SHEET" if balance else "STANDALONE_QUARTER"],
        "scope": ["unknown"],
        "provider_source_lineage": [{"provider": "KBS", "source_file": "native.parquet", "source_sha256": "abc"} for _ in periods],
        "blocker_reason_codes": [], "authority_tier": "OPERATIONAL_PROVIDER_RESEARCH_ONLY",
        "authoritative_financial_eligible": False, "pit_backtest_eligible": False, "is_actionable": False,
    }


def _store_record(ticker: str, entity: str | None) -> dict:
    financial = entity in {"bank", "securities", "insurance", "finance_company"}
    features = {"profit_state": _feature("profit_state", state="PROFITABLE"),
                "total_assets_pit_trajectory": _feature("total_assets_pit_trajectory", state="IMPROVING",
                                                        periods=("2025-Q4", "2026-Q1")),
                "gross_margin": _feature("gross_margin")}
    return {"ticker": ticker, "entity_type": entity,
            "entity_applicability": "GENERIC_CORPORATE_FEATURE_NOT_APPLICABLE" if financial else "GENERIC_RESEARCH_PRIMITIVES_ALLOWED",
            "features": features, "authority_boundary": {"authoritative": False, "pit": False, "actionable": False}}


def _feature_store(records: dict) -> dict:
    artifact = {"schema_version": feature_store.SCHEMA_VERSION, "contract_version": feature_store.CONTRACT_VERSION,
                "artifact_type": feature_store.ARTIFACT_TYPE, "requested_at": REQUESTED_AT,
                "input_period_semantics_identity": "market_wide_structured_financial_period_semantics/v1:fixture",
                "compatibility_rule_version": feature_store.COMPATIBILITY_VERSION, "records": records, "coverage": {}}
    artifact.update(feature_store.content_identity(artifact))
    return artifact


def _applicability(tmp_path: Path, tickers: list[str], seeds: dict[str, str], promoted: dict | None = None) -> dict:
    seed = tmp_path / "seed.csv"
    seed.write_text("ticker,entity_type\n" + "".join(f"{t},{e}\n" for t, e in seeds.items()), encoding="utf-8")
    promoted_path = tmp_path / "promoted.json"
    promoted_path.write_text(json.dumps({"promoted_records": promoted or {}}), encoding="utf-8")
    return entity_contract.resolve_current_research_entity_applicability(
        tickers, seed_path=seed, promoted_path=promoted_path,
        scaleout_promoted_path=tmp_path / "absent-scaleout.json", legacy_recovery_path=tmp_path / "absent-legacy.json")


ENTITY_SEEDS = {"BNK": "bank", "COR": "corporate", "INS": "insurance", "SEC": "securities",
                "FIN": "finance_company", "NOREC": "corporate"}
STORE_ENTITIES = {"BNK": "bank", "COR": "corporate", "INS": "insurance", "SEC": "securities",
                  "FIN": "finance_company", "UNK": None}


def _daily(tmp_path: Path, candidates: list[str]) -> tuple[dict, dict, dict]:
    store = _feature_store({t: _store_record(t, e) for t, e in STORE_ENTITIES.items()})
    applicability = _applicability(tmp_path, sorted(set(candidates) | set(STORE_ENTITIES) | set(ENTITY_SEEDS)), ENTITY_SEEDS)
    artifact = bridge.build_daily_artifact(session=SESSION, candidate_tickers=candidates, feature_store_artifact=store,
                                           entity_applicability_artifact=applicability, financial_analysis_identity=FA_IDENTITY)
    return artifact, store, applicability


def _tactical(eligible: bool = True) -> dict:
    return {"eligible": eligible, "market_structure_state": "UPTREND", "breakout_state_v3": "TESTING_PIVOT",
            "trigger_state": "APPROACHING", "trigger_type": "PIVOT_BREAKOUT_TRIGGER", "trigger_level": 40.0,
            "invalidation_level": 35.0, "distance_to_invalidation_pct": 0.1, "bos_state": "NO_BOS",
            "choch_state": "NO_CHOCH", "swing_high_sequence": "HH", "swing_low_sequence": "HL",
            "ma20_slope_state": "RISING"} if eligible else {"eligible": False}


def _financial(*, current_research_ready: bool = True) -> dict:
    # Engine vocabulary: GROWING (never the hypothesised EXPANDING), with each state's source feature
    # and period, which the fundamental signal contract gates against the decision session.
    return {"status": "AVAILABLE", "profitability_state": "PROFITABLE", "growth_state": "GROWING",
            "analysis_family": "INDUSTRIAL_FINANCIAL_ANALYSIS", "issuer_type": "corporate",
            "as_of_financial_period": "2026-Q2",
            "current_research_ready": current_research_ready,
            "feature_fitness": {"net_income_sign": {"fitness": "READY", "reason_codes": [], "as_of_period": "2026-Q2"},
                                "revenue_qoq": {"fitness": "READY", "reason_codes": [], "as_of_period": "2026-Q2"},
                                "net_margin": {"fitness": "READY", "reason_codes": []},
                                "equity_yoy": {"fitness": "RESEARCH_PROXY", "reason_codes": ["SAME_NATIVE_SERIES_ONLY"]},
                                "bank_asset_quality": {"fitness": "NOT_APPLICABLE", "reason_codes": []},
                                "working_capital_ratio": {"fitness": "BLOCKED_BY_EVIDENCE",
                                                          "reason_codes": ["MISSING_POINT_IN_TIME_CURRENT_ASSETS"]}}}


def _decision(ticker: str = "AAA", *, tactical=None, financial=None, valuation=None, disposition=None,
              liquidity=None, entity=None, market=None, bridge_record=None) -> dict:
    return iidp.build_ticker_integrated_decision(
        ticker=ticker, as_of_session=SESSION, tactical_record=tactical, financial_record=financial,
        valuation_record=valuation, relative_volume_record=None, market_sector_record=market,
        technical_coverage_disposition_record=disposition, liquidity_research_record=liquidity,
        entity_applicability_record=entity, operational_fundamental_context_record=bridge_record,
    )


CURRENT = {"ticker": "AAA", "disposition": "SAME_SESSION_TECHNICAL_COVERED", "has_exact_session_bar": True,
           "is_current_session": True, "feature_as_of_session": SESSION, "in_official_research_universe": True,
           "reason_code": "EXACT_SESSION_BAR_AND_COMPLETE_TECHNICAL_WINDOW"}
STALE = {"ticker": "AAA", "disposition": "PROVIDER_SESSION_UNAVAILABLE", "has_exact_session_bar": False,
         "is_current_session": False, "feature_as_of_session": "2026-09-19", "in_official_research_universe": True,
         "reason_code": "STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION"}
CORPORATE = {"entity_class": "corporate", "applicability_status": "RESOLVED", "authority_tier": "curated_seed_authority",
             "reason_codes": []}
SIZE_ONLY_VALUATION = {
    "entity_class": "corporate", "share_basis": "CURRENT_SHARE_RESEARCH_PROXY",
    "methods": {"P/E_TTM": {"status": "INPUT_BLOCKED", "applicability": "APPLICABLE", "blocker_reason_codes": ["TTM_INPUT_UNAVAILABLE"]},
                "P/B": {"status": "INPUT_BLOCKED", "applicability": "APPLICABLE",
                        "blocker_reason_codes": ["PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS"]},
                "market_cap": {"status": "RESEARCH_USABLE", "applicability": "APPLICABLE", "value": 1.0e12}},
    "has_usable_method": True, "relative_research_state": "UNAVAILABLE", "peer_relative": {},
}


# ── entity applicability ────────────────────────────────────────────────────────────────────────

def test_entity_applicability_is_governed_current_state_and_fails_closed(tmp_path: Path) -> None:
    promoted = {"CCC": {"entity_class": "corporate", "classification_status": "QUALIFIED"},
                "DDD": {"entity_class": "securities", "classification_status": "AMBIGUOUS"}}
    art = _applicability(tmp_path, ["aaa", "BBB", "CCC", "DDD", "EEE"], {"AAA": "corporate", "BBB": "bank", "CCC": "bank"}, promoted)
    records = art["records"]
    assert records["AAA"] == {"entity_class": "corporate", "applicability_status": "RESOLVED",
                              "authority_tier": "curated_seed_authority", "classification_status": "QUALIFIED", "reason_codes": []}
    assert records["BBB"]["entity_class"] == "bank"
    assert records["CCC"]["applicability_status"] == "CONFLICT" and records["CCC"]["entity_class"] == "unknown"
    assert records["DDD"]["reason_codes"] == ["ENTITY_CLASSIFICATION_NOT_QUALIFIED"]
    assert records["EEE"]["reason_codes"] == ["ENTITY_CLASS_UNRESOLVED"]
    assert art["authority_scope"] == "CURRENT_STATE_ONLY" and art["historical_pit_authority"] == "NOT_ESTABLISHED"
    assert entity_contract.entity_applicability_content_identity(art) == art["artifact_identity"]
    again = _applicability(tmp_path, ["EEE", "DDD", "CCC", "BBB", "AAA"], {"AAA": "corporate", "BBB": "bank", "CCC": "bank"}, promoted)
    assert again["artifact_identity"] == art["artifact_identity"]


# ── Daily binding ───────────────────────────────────────────────────────────────────────────────

def test_daily_binding_qualifies_generic_candidates_per_entity_and_explains_every_block(tmp_path: Path) -> None:
    candidates = ["BNK", "COR", "INS", "SEC", "FIN", "UNK", "NOREC"]
    artifact, store, applicability = _daily(tmp_path, candidates)
    records = artifact["records"]
    assert {t for t, r in records.items() if r["status"] == "RESEARCH_USABLE"} == {"BNK", "COR", "INS", "SEC", "FIN"}
    assert records["UNK"]["primary_reason"] == "ENTITY_CLASS_UNRESOLVED"
    assert records["NOREC"]["primary_reason"] == "FEATURE_STORE_RECORD_ABSENT"
    assert "gross_margin" in records["BNK"]["non_applicable_features"]  # industrial metric never erases bank context
    assert records["COR"]["usable_features"]["gross_margin"] == store["records"]["COR"]["features"]["gross_margin"]
    assert records["BNK"]["entity_applicability"]["authority_tier"] == "curated_seed_authority"
    assert artifact["binding_mode"] == bridge.DAILY_BINDING_MODE
    assert artifact["selection"] == {"rule": bridge.DAILY_SELECTION_RULE, "candidate_count": 7}
    assert artifact["source_artifact_identities"]["fundamental_feature_store"] == store["artifact_identity"]
    assert artifact["source_artifact_identities"]["entity_applicability"] == applicability["artifact_identity"]
    assert all(value is False for key, value in artifact["authority_boundary"].items()
               if key not in {"current_research_only", "source_authority_tier"})
    reordered, _, _ = _daily(tmp_path, list(reversed(candidates)))
    assert reordered["artifact_identity"] == artifact["artifact_identity"]


def test_daily_binding_source_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    artifact, store, applicability = _daily(tmp_path, ["BNK"])
    tampered_store = deepcopy(store)
    tampered_store["records"]["BNK"]["features"]["profit_state"]["categorical_state"] = "LOSS_MAKING"
    kwargs = dict(session=SESSION, candidate_tickers=["BNK"], financial_analysis_identity=FA_IDENTITY)
    with pytest.raises(bridge.OperationalFundamentalIntegrationError, match="FEATURE_STORE_SOURCE_IDENTITY_INVALID"):
        bridge.build_daily_artifact(feature_store_artifact=tampered_store, entity_applicability_artifact=applicability, **kwargs)
    tampered_entities = deepcopy(applicability)
    tampered_entities["records"]["BNK"]["entity_class"] = "corporate"
    with pytest.raises(bridge.OperationalFundamentalIntegrationError, match="ENTITY_APPLICABILITY_SOURCE_IDENTITY_INVALID"):
        bridge.build_daily_artifact(feature_store_artifact=store, entity_applicability_artifact=tampered_entities, **kwargs)
    pit_claim = deepcopy(applicability)
    pit_claim["historical_pit_authority"] = "ESTABLISHED"
    pit_claim["artifact_identity"] = entity_contract.entity_applicability_content_identity(pit_claim)
    with pytest.raises(bridge.OperationalFundamentalIntegrationError, match="ENTITY_APPLICABILITY_AUTHORITY_SCOPE_INVALID"):
        bridge.build_daily_artifact(feature_store_artifact=store, entity_applicability_artifact=pit_claim, **kwargs)
    with pytest.raises(bridge.OperationalFundamentalIntegrationError, match="DAILY_SELECTION_RULE_UNSUPPORTED"):
        bridge.build_daily_artifact(feature_store_artifact=store, entity_applicability_artifact=applicability,
                                    selection_rule="FROZEN_TICKER_LIST", **kwargs)
    with pytest.raises(bridge.OperationalFundamentalIntegrationError, match="ENTITY_APPLICABILITY_TICKER_MISSING"):
        bridge.build_daily_artifact(feature_store_artifact=store, entity_applicability_artifact=applicability,
                                    **{**kwargs, "candidate_tickers": ["ZZZ"]})
    mismatch = deepcopy(store)
    mismatch["records"]["BNK"]["entity_type"] = "corporate"
    mismatch = _feature_store(mismatch["records"])
    row = bridge.build_daily_artifact(feature_store_artifact=mismatch, entity_applicability_artifact=applicability, **kwargs)
    assert row["records"]["BNK"]["primary_reason"] == "ENTITY_CLASS_CONFLICT"


def _integrated(tmp_path: Path, *, fa_records: dict, candidates: list[str], **extra) -> dict:
    artifact, _, applicability = _daily(tmp_path, candidates)
    tickers = sorted(fa_records)
    return iidp.build_artifact(
        session=SESSION, requested_at=REQUESTED_AT,
        technical_structure_artifact={"artifact_identity": "technical_structure:fixture", "records": {t: {"ticker": t} for t in tickers}},
        financial_analysis_artifact={"artifact_identity": FA_IDENTITY, "records": fa_records},
        technical_coverage_disposition_artifact=disposition_artifact(
            {t: {**disposition_record(t, session=SESSION, currency="LAST_TRADE_AS_OF:2026-09-19"),
                 "in_official_research_universe": True} for t in tickers}, session=SESSION),
        operational_fundamental_integration_artifact=artifact, entity_applicability_artifact=applicability, **extra)


def test_integrated_decision_consumes_daily_binding_only_where_financial_v2_is_insufficient(tmp_path: Path) -> None:
    fa_records = {"BNK": {"status": "ABSENT"}, "COR": _financial()}
    candidates = [t for t, record in fa_records.items() if iidp.operational_fundamental_bridge_eligible(record)]
    assert candidates == ["BNK"]
    art = _integrated(tmp_path, fa_records=fa_records, candidates=candidates)
    bnk, cor = art["records"]["BNK"], art["records"]["COR"]
    assert bnk["fundamental_state"] == iidp.FUNDAMENTAL_STABLE
    assert bnk["evidence_axes"]["FUNDAMENTAL"]["method"] == bridge.CONTRACT_VERSION
    fundamental = bnk["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]
    assert fundamental["authority"] == decision_input.RESEARCH_PROXY
    assert fundamental["operational_bridge"]["state"] == "APPLIED"
    assert fundamental["entity_applicability"]["entity_class"] == "bank"
    assert "gross_margin" in fundamental["metrics"]["non_applicable"]
    assert "operational_fundamental_context" not in cor
    assert cor["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["operational_bridge"]["state"] == "NOT_CONSULTED"
    assert art["source_artifacts"]["entity_applicability"].startswith(entity_contract.CURRENT_RESEARCH_ENTITY_APPLICABILITY_CONTRACT)
    assert art["coverage"]["operational_fundamental_integration_usable"] == 1


def test_bridge_record_for_financial_v2_available_ticker_is_ignored_and_never_moves_identity(tmp_path: Path) -> None:
    artifact, _, _ = _daily(tmp_path, ["COR"])
    common = dict(tactical=_tactical(), financial=_financial(), disposition=CURRENT, entity=CORPORATE)
    without = _decision(**common)
    with_record = _decision(**common, bridge_record=artifact["records"]["COR"])
    assert "operational_fundamental_context" not in with_record
    assert with_record["decision_identity"] == without["decision_identity"]
    assert with_record["current_research_decision_input"] == without["current_research_decision_input"]


def test_integrated_decision_rejects_mismatched_binding_sources(tmp_path: Path) -> None:
    fa_records = {"BNK": {"status": "ABSENT"}}
    artifact, _, applicability = _daily(tmp_path, ["BNK"])
    base = dict(session=SESSION, requested_at=REQUESTED_AT,
                technical_structure_artifact={"artifact_identity": "ts", "records": {"BNK": {"ticker": "BNK"}}})
    with pytest.raises(iidp.IntegratedDecisionProductError, match="OPERATIONAL_FUNDAMENTAL_INTEGRATION_CONTRACT_INVALID"):
        iidp.build_artifact(**base, financial_analysis_artifact={"artifact_identity": "other:fa", "records": fa_records},
                            operational_fundamental_integration_artifact=artifact)
    (tmp_path / "other").mkdir()
    other = _applicability(tmp_path / "other", ["BNK"], {"BNK": "bank", "EXTRA": "corporate"})
    with pytest.raises(iidp.IntegratedDecisionProductError, match="OPERATIONAL_FUNDAMENTAL_ENTITY_APPLICABILITY_IDENTITY_MISMATCH"):
        iidp.build_artifact(**base, financial_analysis_artifact={"artifact_identity": FA_IDENTITY, "records": fa_records},
                            operational_fundamental_integration_artifact=artifact, entity_applicability_artifact=other)
    tampered = deepcopy(applicability)
    tampered["records"]["BNK"]["entity_class"] = "corporate"
    with pytest.raises(iidp.IntegratedDecisionProductError, match="ENTITY_APPLICABILITY_CONTRACT_INVALID"):
        iidp.build_artifact(**base, financial_analysis_artifact={"artifact_identity": FA_IDENTITY, "records": fa_records},
                            entity_applicability_artifact=tampered)


# ── valuation convergence ───────────────────────────────────────────────────────────────────────

def _raw_valuation(entity: str = "unknown") -> dict:
    return {"entity_class": entity,
            "share_basis_input": {"authority": "provider_current_share_research_proxy", "research_proxy_eligible": True,
                                  "status": "RESEARCH_PROXY"},
            "metrics": {"market_cap": {"status": "RESEARCH_USABLE", "value": 1.0e12, "blocked_reasons": []},
                        "P/E": {"status": "BLOCKED", "blocked_reasons": ["ENTITY_CLASS_UNRESOLVED"]}}}


@pytest.mark.parametrize("entity, pe, ps", [
    ("corporate", "APPLICABLE", "APPLICABLE"),
    ("bank", "APPLICABLE", "NOT_APPLICABLE"),
    ("securities", "APPLICABLE", "NOT_APPLICABLE"),
    ("insurance", "NOT_APPLICABLE", "NOT_APPLICABLE"),
    ("finance_company", "NOT_APPLICABLE", "NOT_APPLICABLE"),
])
def test_valuation_method_applicability_reads_governed_entity_class(entity: str, pe: str, ps: str) -> None:
    governed = {"entity_class": entity, "applicability_status": "RESOLVED", "authority_tier": "scaleout_promoted_record_authority"}
    row = evaluate_ticker_valuation(ticker="AAA", feature_record=None, valuation_record=_raw_valuation(),
                                    entity_applicability=governed)
    assert row["entity_class"] == entity
    assert row["entity_applicability"]["status"] == "RESOLVED"
    assert row["entity_applicability"]["sources"] == ["GOVERNED_CURRENT_STATE_AUTHORITY"]
    assert row["entity_applicability"]["upstream_valuation_lane_entity_class"] == "unknown"
    assert row["methods"]["P/E_TTM"]["applicability"] == pe
    assert row["methods"]["P/S_TTM"]["applicability"] == ps
    assert row["methods"]["P/E"]["blocker_reason_codes"] == ["ENTITY_CLASS_UNRESOLVED"]  # upstream lane verdict kept


def test_valuation_entity_conflict_and_absence_fail_closed() -> None:
    conflict = evaluate_ticker_valuation(
        ticker="AAA", feature_record=None, valuation_record=_raw_valuation("corporate"),
        entity_applicability={"entity_class": "bank", "applicability_status": "RESOLVED"})
    assert conflict["entity_class"] == "unknown" and conflict["entity_applicability"]["status"] == "CONFLICT"
    assert conflict["methods"]["P/E_TTM"]["applicability"] == "INPUT_BLOCKED"
    absent = evaluate_ticker_valuation(ticker="AAA", feature_record=None, valuation_record=_raw_valuation())
    assert absent["entity_applicability"]["status"] == "UNRESOLVED"
    assert absent["entity_applicability"]["reason_codes"] == ["ENTITY_CLASS_UNRESOLVED"]


def test_integrated_valuation_reads_producer_peer_verdict_and_size_is_never_valuation() -> None:
    producer = {"share_basis": "CURRENT_SHARE_RESEARCH_PROXY", "relative_research_state": "ATTRACTIVE_RELATIVE_RESEARCH",
                "methods": {"EV/EBITDA_CALC_READY": {"status": "RESEARCH_USABLE", "value": 7.5, "applicability": "APPLICABLE"},
                            "market_cap": {"status": "RESEARCH_USABLE", "value": 1.0e12, "applicability": "APPLICABLE"}},
                "peer_relative": {"EV/EBITDA_CALC_READY": {"status": "READY_RESEARCH_ONLY", "percentile": 0.2, "peer_count": 7},
                                  "market_cap": {"status": "READY_RESEARCH_ONLY", "percentile": 0.1, "peer_count": 9}}}
    summary, supports, _, _ = iidp.evaluate_valuation_context(producer, {})
    assert summary["status"] == "AVAILABLE" and summary["peer_relative_state"] == "CHEAP_VS_PEERS"
    assert "ATTRACTIVE_RELATIVE_RESEARCH_PEER_VALUATION" in supports
    assert summary["peer_relative_basis"] == {"EV/EBITDA_CALC_READY": {"percentile": 0.2, "peer_count": 7}}
    in_line, _, _, _ = iidp.evaluate_valuation_context({**producer, "relative_research_state": "IN_LINE_RELATIVE_RESEARCH"}, {})
    assert in_line["peer_relative_state"] == "MID_RANGE_VS_PEERS"
    size_only, _, _, _ = iidp.evaluate_valuation_context(SIZE_ONLY_VALUATION, {})
    assert size_only["status"] == "UNAVAILABLE"
    assert size_only["size_context"]["status"] == "AVAILABLE"
    assert size_only["unavailable_reason_codes"] == sorted([
        "PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS", "TTM_INPUT_UNAVAILABLE",
        "VALUATION_NO_USABLE_RELATIVE_METHOD"])


def test_unavailable_valuation_names_its_causes_and_never_erases_technical_or_fundamental() -> None:
    record = _decision(tactical=_tactical(), financial=_financial(), valuation=SIZE_ONLY_VALUATION,
                       disposition=CURRENT, entity=CORPORATE)
    axis = record["evidence_axes"]["VALUATION"]
    assert {"VALUATION_NO_USABLE_RELATIVE_METHOD", "TTM_INPUT_UNAVAILABLE"} <= set(axis["blocker_reason_codes"])
    assert axis["context"]["size_context_status"] == "AVAILABLE"
    item = record["current_research_decision_input"]
    valuation = item["dimensions"]["VALUATION"]
    assert valuation["state"] == decision_input.PARTIAL and valuation["evidence_class"] == decision_input.VALUATION_SIZE_ONLY
    assert valuation["exact_market_cap"]["state"] == decision_input.BLOCKED
    assert item["evidence_class"] == decision_input.CLASS_PARTIAL
    assert item["synthesis"]["usable_primary_factors"] == ["TECHNICAL", "FUNDAMENTAL"]
    assert "TTM_INPUT_UNAVAILABLE" in item["synthesis"]["missing_primary_factors"]["VALUATION"]
    no_valuation = _decision(tactical=_tactical(), financial=_financial(), valuation=None, disposition=CURRENT, entity=CORPORATE)
    assert no_valuation["research_action_posture"] == record["research_action_posture"]
    assert no_valuation["current_research_decision_input"]["dimensions"]["VALUATION"]["reason_codes"] == [
        "VALUATION_CONTEXT_NOT_PROVIDED"]


def test_missing_exact_session_price_is_named_as_the_valuation_root_cause() -> None:
    no_price = {"share_basis": "CURRENT_SHARE_RESEARCH_PROXY",
                "methods": {"P/E_TTM": {"status": "INPUT_BLOCKED", "applicability": "APPLICABLE",
                                        "blocker_reason_codes": ["TTM_INPUT_UNAVAILABLE"]},
                            "market_cap": {"status": "INPUT_BLOCKED", "applicability": "APPLICABLE",
                                           "blocker_reason_codes": ["PRICE_SESSION_MISSING"]}}}
    record = _decision(financial=_financial(), valuation=no_price, disposition=STALE, entity=CORPORATE)
    valuation = record["current_research_decision_input"]["dimensions"]["VALUATION"]
    assert valuation["state"] == decision_input.BLOCKED
    assert valuation["size_context"]["reason_codes"] == ["PRICE_SESSION_MISSING"]
    assert {"PRICE_SESSION_MISSING", "TTM_INPUT_UNAVAILABLE"} <= set(valuation["reason_codes"])
    assert "PRICE_SESSION_MISSING" in record["valuation_context_summary"]["unavailable_reason_codes"]
    assert record["current_research_decision_input"]["evidence_class"] == decision_input.CLASS_FINANCIAL


@pytest.mark.parametrize("period, session, expected", [
    ("2026-Q2", SESSION, None),
    ("2025-Q3", SESSION, None),                      # four completed quarters: the bridge's own bound
    ("2025-Q2", SESSION, "CALCULATION_READINESS_PERIOD_STALE"),
    ("2018-Q4", SESSION, "CALCULATION_READINESS_PERIOD_STALE"),
    ("2026-Q3", SESSION, "CALCULATION_READINESS_PERIOD_AFTER_DECISION_SESSION"),
    ("2026-Q3", "2026-09-30", None),
    ("2025", SESSION, "CALCULATION_READINESS_PERIOD_UNRESOLVED"),
    ("2018-Q4", None, None),                         # legacy ungated call
])
def test_readiness_denominator_period_must_be_current(period, session, expected) -> None:
    assert readiness_period_blocker(period, session) == expected


def _readiness_record(period: str) -> dict:
    return {"status": "AVAILABLE", "calculation_readiness": [{
        "reporting_period": period,
        "ev_ebitda": {"readiness": "ready", "status": "provider_reported", "value": 34.3, "blocked_by": [],
                      "formula": "enterprise_value / ebitda"}}]}


def test_stale_readiness_ev_ebitda_is_blocked_and_fresh_one_is_labelled_single_period() -> None:
    governed = {"entity_class": "corporate", "applicability_status": "RESOLVED"}
    stale = evaluate_ticker_valuation(ticker="AAA", feature_record=None, valuation_record=_raw_valuation(),
                                      calculation_readiness_record=_readiness_record("2018-Q4"),
                                      entity_applicability=governed, decision_session=SESSION)
    assert stale["methods"]["EV/EBITDA_CALC_READY"]["status"] == "INPUT_BLOCKED"
    assert stale["methods"]["EV/EBITDA_CALC_READY"]["blocker_reason_codes"] == ["CALCULATION_READINESS_PERIOD_STALE"]
    fresh = evaluate_ticker_valuation(ticker="AAA", feature_record=None, valuation_record=_raw_valuation(),
                                      calculation_readiness_record=_readiness_record("2026-Q2"),
                                      entity_applicability=governed, decision_session=SESSION)
    method = fresh["methods"]["EV/EBITDA_CALC_READY"]
    assert method["status"] == "RESEARCH_USABLE"
    assert method["denominator_period_semantics"] == "SINGLE_REPORTING_PERIOD_NOT_ANNUALIZED"
    assert "SINGLE_REPORTING_PERIOD_DENOMINATOR_NOT_TTM" in method["limitations"]
    record = _decision(valuation=fresh, disposition=CURRENT, entity=CORPORATE)
    valuation = record["current_research_decision_input"]["dimensions"]["VALUATION"]
    assert valuation["state"] == decision_input.AVAILABLE
    assert valuation["limitations"] == ["SINGLE_REPORTING_PERIOD_DENOMINATOR_NOT_TTM"]
    assert valuation["usable_method_period_basis"] == {"EV/EBITDA_CALC_READY": "2026-Q2"}
    assert "EV_EBITDA_SINGLE_REPORTING_PERIOD_NOT_TTM" in record["valuation_context_summary"]["limitations"]


def test_proxy_remains_proxy_and_exact_remains_exact() -> None:
    proxy = {"share_basis": "CURRENT_SHARE_RESEARCH_PROXY", "authoritative_current_market_cap_eligible": False,
             "methods": {"P/B": {"status": "RESEARCH_USABLE", "value": 1.1, "applicability": "APPLICABLE"}}}
    exact = {"share_basis": "EXACT_OR_QUALIFIED", "authoritative_current_market_cap_eligible": True,
             "methods": {"P/B": {"status": "READY", "value": 1.1, "applicability": "APPLICABLE"},
                         "market_cap": {"status": "READY", "value": 1.0e12, "applicability": "APPLICABLE"}}}
    proxy_dim = _decision(valuation=proxy, disposition=CURRENT)["current_research_decision_input"]["dimensions"]["VALUATION"]
    exact_dim = _decision(valuation=exact, disposition=CURRENT)["current_research_decision_input"]["dimensions"]["VALUATION"]
    assert proxy_dim["authority"] == decision_input.RESEARCH_PROXY
    assert proxy_dim["exact_market_cap"] == {"state": decision_input.BLOCKED, "reason_codes": ["CURRENT_COMMON_SHARE_AUTHORITY_NOT_QUALIFIED"]}
    assert exact_dim["authority"] == decision_input.EXACT_QUALIFIED
    assert exact_dim["exact_market_cap"]["state"] == decision_input.EXACT_QUALIFIED
    fundamental = _decision(financial=_financial(current_research_ready=False), disposition=CURRENT)
    assert fundamental["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["authority"] == decision_input.RESEARCH_PROXY


# ── authority boundaries and graceful degradation ─────────────────────────────────────────────

def test_pit_blocker_does_not_erase_current_technical_research() -> None:
    record = _decision(tactical=_tactical(), disposition=CURRENT)
    item = record["current_research_decision_input"]
    assert item["dimensions"]["TECHNICAL"]["state"] == decision_input.AVAILABLE
    assert item["dimensions"]["TECHNICAL"]["authority"] == decision_input.RESEARCH_QUALIFIED
    assert item["dimensions"]["MARKET"]["price_basis"] == {"current_research_use": "EXACT_SESSION_DESCRIPTIVE_ONLY",
                                                          "raw_as_traded": "NOT_PROMOTED", "historical_pit": "BLOCKED"}
    assert "PIT_BACKTEST_AUTHORITY_BLOCKED" in item["provenance"]["exact_capabilities_unavailable"]
    assert item["authority_boundary"]["historical_pit_authority"] is False
    assert item["evidence_class"] == decision_input.CLASS_TECHNICAL


def test_execution_liquidity_blocker_does_not_erase_research_liquidity() -> None:
    liquidity = {"disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE",
                 "liquidity_research_contract": {"CURRENT_SESSION_LIQUIDITY_RESEARCH": {"state": "ELIGIBLE"},
                                                 "EXECUTION_CAPACITY": {"state": "BLOCKED"},
                                                 "POSITION_SIZING": {"state": "BLOCKED"}}}
    dim = _decision(tactical=_tactical(), disposition=CURRENT, liquidity=liquidity)["current_research_decision_input"]["dimensions"]["LIQUIDITY"]
    assert dim["state"] == decision_input.AVAILABLE and dim["research"]["state"] == decision_input.AVAILABLE
    assert dim["authority"] == decision_input.CURRENT_DESCRIPTIVE_ONLY
    assert dim["execution"]["state"] == decision_input.BLOCKED
    assert dim["execution"]["reason_codes"] == ["EXECUTION_CAPACITY_BLOCKED", "POSITION_SIZING_BLOCKED",
                                                "QUALIFIED_LIQUIDITY_INPUTS_ABSENT"]


def test_missing_specialist_metric_does_not_erase_unrelated_valid_fundamental_metrics() -> None:
    dim = _decision(financial=_financial(), disposition=CURRENT)["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]
    assert dim["state"] == decision_input.AVAILABLE and dim["authority"] == decision_input.RESEARCH_QUALIFIED
    assert dim["metrics"]["qualified"] == ["net_income_sign", "net_margin", "revenue_qoq"]
    assert dim["metrics"]["proxy"] == ["equity_yoy"]
    assert dim["metrics"]["non_applicable"] == ["bank_asset_quality"]
    assert dim["metrics"]["blocked"] == {"working_capital_ratio": ["BLOCKED_BY_EVIDENCE", "MISSING_POINT_IN_TIME_CURRENT_ASSETS"]}


def test_evidence_classes_degrade_gracefully_and_scope_is_explicit() -> None:
    financial_only = _decision(financial=_financial(), disposition=STALE)
    item = financial_only["current_research_decision_input"]
    assert item["evidence_class"] == decision_input.CLASS_FINANCIAL
    assert item["dimensions"]["TECHNICAL"]["reason_codes"] == [
        "INSUFFICIENT_TECHNICAL_STRUCTURE_SERIES", "PROVIDER_SESSION_UNAVAILABLE", "STALE_PRIOR_SESSION_FEATURE_NOT_SAME_SESSION"]
    nothing = _decision(disposition={**STALE, "feature_as_of_session": None, "has_exact_session_bar": False})
    assert nothing["current_research_decision_input"]["evidence_class"] == decision_input.CLASS_INSUFFICIENT
    outside = _decision(financial=_financial(), disposition={**CURRENT, "in_official_research_universe": False})
    assert outside["current_research_decision_input"]["evidence_class"] == decision_input.CLASS_OUT_OF_SCOPE
    gated = _decision(financial=_financial(), disposition={"disposition": "PROVIDER_REJECTED_OR_INVALID_SYMBOL",
                                                           "has_exact_session_bar": False, "in_official_research_universe": True})
    assert gated["research_action_posture"] == iidp.POSTURE_INSUFFICIENT
    assert gated["current_research_decision_input"]["synthesis"]["action_posture_gated_by_current_evidence"] is True


def test_decision_input_is_deterministic_and_never_enters_decision_identity() -> None:
    common = dict(tactical=_tactical(), financial=_financial(), valuation=SIZE_ONLY_VALUATION, disposition=CURRENT, entity=CORPORATE)
    first, second = _decision(**common), _decision(**common)
    assert first["current_research_decision_input"] == second["current_research_decision_input"]
    stripped = deepcopy(first)
    stripped.pop("current_research_decision_input")
    assert iidp.decision_identity(stripped) == first["decision_identity"]
    assert json.dumps(first["current_research_decision_input"], sort_keys=True) == json.dumps(
        second["current_research_decision_input"], sort_keys=True)


def test_liquidity_research_artifact_must_match_session_and_contract() -> None:
    base = dict(session=SESSION, requested_at=REQUESTED_AT,
                technical_structure_artifact={"artifact_identity": "ts", "records": {"AAA": {"ticker": "AAA"}}})
    with pytest.raises(iidp.IntegratedDecisionProductError, match="LIQUIDITY_RESEARCH_SESSION_MISMATCH"):
        iidp.build_artifact(**base, liquidity_research_artifact={"contract_version": iidp.LIQUIDITY_RESEARCH_CONTRACT,
                                                                 "resolved_completed_session": "2026-09-23", "records": {}})
    with pytest.raises(iidp.IntegratedDecisionProductError, match="LIQUIDITY_RESEARCH_CONTRACT_MISMATCH"):
        iidp.build_artifact(**base, liquidity_research_artifact={"contract_version": "other/v1",
                                                                 "resolved_completed_session": SESSION, "records": {}})


def test_research_packet_passes_the_decision_input_through_unchanged() -> None:
    record = _decision(tactical=_tactical(), financial=_financial(), valuation=SIZE_ONLY_VALUATION,
                       disposition=CURRENT, entity=CORPORATE)
    delivered = delivery.project_integrated_decision_for_ai_delivery(record)
    assert delivered["current_research_decision_input"] == record["current_research_decision_input"]
    card = delivery._decision_card("AAA", record, None)
    assert card["evidence_quality"]["current_research_evidence_class"] == decision_input.CLASS_PARTIAL
    assert "VALUATION" in card["evidence_quality"]["missing_primary_factors"]


# ── Ordinary Daily wiring (real enrichment function, fixture builders) ────────────────────────

def _patch_daily_enrichment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, feature_store_status: str = "MATERIALIZED",
                            liquidity_session: str = SESSION) -> dict:
    import canonical_current_product_projections as ccp
    import canonical_daily_financial_v2_materialization as fin_material
    import canonical_post_close_pipeline as cpc
    import daily_session_level2_package as level2
    import stocklookup_core.financial.financial_v2_current_input_authority as fin_authority
    import market_structure_breakout_product_projection as msb
    import market_wide_relative_volume_research as rvol
    import tactical_confirmation_context as confirmation
    import tactical_momentum_context as momentum
    import technical_structure_context as tsc

    tickers = ["BNK", "COR"]
    store = _feature_store({"BNK": _store_record("BNK", "bank"), "COR": _store_record("COR", "corporate")})
    real_resolver = entity_contract.resolve_current_research_entity_applicability
    seed = tmp_path / "seed.csv"
    seed.write_text("ticker,entity_type\nBNK,bank\nCOR,corporate\n", encoding="utf-8")
    captured: dict = {"writes": {}}
    loads = {
        "p3f9b_mva_exact_session_snapshot.json": {"snapshot_identity": "snapshot:fixture", "records": {t: {} for t in tickers}},
        "market_wide_current_descriptive_research_artifact.json": {"records": {t: {} for t in tickers}},
        "market_wide_current_valuation_artifact.json": {"artifact_identity": "raw_valuation:fixture", "records": {}},
        "recovery.json": {"artifact_identity": "recovery:fixture"},
        "market_wide_current_liquidity_research_artifact.json": {
            "contract_version": iidp.LIQUIDITY_RESEARCH_CONTRACT, "resolved_completed_session": liquidity_session,
            "artifact_identity": "liquidity:fixture",
            "records": {"COR": {"disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", "liquidity_research_contract": {}}}},
    }
    import stocklookup_core.financial.financial_analysis_product_projection as fa_projection
    fa_product = {"contract_version": fa_projection.INTEGRATION_CONTRACT, "source_context_identity": "engine:fixture",
                  "records": {"BNK": {"status": "ABSENT"}, "COR": _financial()}}
    fa_product.update(fa_projection._identity(fa_product))
    fa_wrapper = {"contract_version": fin_material.CONTRACT_VERSION, "decision_session": SESSION,
                  "financial_analysis_product": fa_product, "financial_content_identity": fa_product["artifact_identity"],
                  "financial_v2_engine_identity": "engine:fixture", "engine_fundamental_peer_context": {}}
    fa_wrapper.update(fin_material._identity(fa_wrapper))
    real_build = iidp.build_artifact

    def capture_build(**kwargs):
        captured["integrated"] = kwargs
        return real_build(**kwargs)

    def capture_valuation(**kwargs):
        captured["valuation"] = kwargs
        return {"artifact_identity": "valuation:fixture", "records": {}}

    monkeypatch.setattr(cpc, "_load", lambda path: deepcopy(loads.get(Path(path).name)))
    monkeypatch.setattr(cpc, "_write_json", lambda path, value: captured["writes"].__setitem__(Path(path).name, value))
    monkeypatch.setattr(level2, "resolve_technical_recovery_artifact", lambda *a, **k: {"selected_path": tmp_path / "recovery.json"})
    monkeypatch.setattr(tsc, "build_artifact", lambda **k: {"artifact_identity": "tsc:fixture", "records": {}})
    monkeypatch.setattr(msb, "build_artifact", lambda **k: {"artifact_identity": "msb:fixture", "records": {t: {"ticker": t} for t in tickers}})
    monkeypatch.setattr(rvol, "build_artifact", lambda **k: {"artifact_identity": "rvol:fixture", "records": {}})
    monkeypatch.setattr(momentum, "build_artifact", lambda **k: {"artifact_identity": "momentum:fixture", "records": {}})
    monkeypatch.setattr(confirmation, "build_artifact", lambda **k: {"artifact_identity": "confirmation:fixture", "records": {}})
    monkeypatch.setattr(fin_authority, "resolve", lambda root: object())
    monkeypatch.setattr(fin_material, "build_engine_artifact", lambda **k: {"artifact_identity": "engine:fixture"})
    monkeypatch.setattr(fin_material, "build_session_artifact", lambda **k: fa_wrapper)
    monkeypatch.setattr(fin_material, "build_evaluated_valuation_artifact", capture_valuation)
    monkeypatch.setattr(ccp, "materialize_current_fundamental_feature_store_context",
                        lambda **k: ({"status": "MATERIALIZED", "artifact": store} if feature_store_status == "MATERIALIZED"
                                     else {"status": "UNAVAILABLE", "reason_code": "FIXTURE_UNAVAILABLE"}))
    monkeypatch.setattr(entity_contract, "resolve_current_research_entity_applicability",
                        lambda tickers_: real_resolver(tickers_, seed_path=seed, promoted_path=tmp_path / "p.json",
                                                       scaleout_promoted_path=tmp_path / "s.json",
                                                       legacy_recovery_path=tmp_path / "l.json"))
    monkeypatch.setattr(iidp, "build_artifact", capture_build)
    captured["results"] = cpc.build_enrichment_components(tmp_path, SESSION, artifact_root=tmp_path, runtime_root=None,
                                                          retained_evidence_root=tmp_path, output_root=tmp_path)
    return captured


def test_ordinary_daily_enrichment_binds_operational_fundamental_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _patch_daily_enrichment(monkeypatch, tmp_path)
    results = captured["results"]
    assert results["integrated_investment_decision_product"]["status"] == "BUILT"
    assert results["operational_fundamental_binding"]["status"] == "BOUND"
    assert results["operational_fundamental_binding"]["candidates"] == 1
    kwargs = captured["integrated"]
    assert kwargs["financial_peer_materialization_artifact"]["financial_analysis_product"] == kwargs["financial_analysis_artifact"]
    integration = kwargs["operational_fundamental_integration_artifact"]
    assert integration["cohort_tickers"] == ["BNK"] and integration["binding_mode"] == bridge.DAILY_BINDING_MODE
    assert kwargs["entity_applicability_artifact"]["artifact_identity"] == captured["valuation"]["entity_applicability_artifact"]["artifact_identity"]
    assert kwargs["liquidity_research_artifact"]["artifact_identity"] == "liquidity:fixture"
    assert {"operational_fundamental_context_integration_artifact.json",
            "current_research_entity_applicability_artifact.json"} <= set(captured["writes"])
    decision = results["integrated_investment_decision_product"]["artifact"]
    assert decision["records"]["BNK"]["evidence_axes"]["FUNDAMENTAL"]["method"] == bridge.CONTRACT_VERSION
    assert decision["records"]["COR"]["current_research_decision_input"]["dimensions"]["LIQUIDITY"]["state"] == decision_input.AVAILABLE


def test_ordinary_daily_binding_failure_degrades_to_no_bridge_without_losing_the_decision(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = _patch_daily_enrichment(monkeypatch, tmp_path, feature_store_status="UNAVAILABLE", liquidity_session="2026-09-23")
    results = captured["results"]
    assert results["integrated_investment_decision_product"]["status"] == "BUILT"
    assert results["operational_fundamental_binding"]["status"] == "UNAVAILABLE"
    assert "FUNDAMENTAL_FEATURE_STORE_UNAVAILABLE" in results["operational_fundamental_binding"]["reason"]
    assert captured["integrated"]["operational_fundamental_integration_artifact"] is None
    assert captured["integrated"]["liquidity_research_artifact"] is None  # other-session evidence is never substituted
    decision = results["integrated_investment_decision_product"]["artifact"]
    assert decision["records"]["BNK"]["fundamental_state"] == iidp.FUNDAMENTAL_INSUFFICIENT
    assert decision["records"]["BNK"]["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["operational_bridge"]["state"] == "NOT_CONSULTED"


# ── capability-map reconciliation ──────────────────────────────────────────────────────────────

def _map_sources(tmp_path: Path) -> dict[str, Path]:
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    official = {"AAA": True, "BBB": True, "CCC": True, "DDD": False}
    dispositions = {
        "AAA": CURRENT | {"ticker": "AAA"}, "BBB": STALE | {"ticker": "BBB"},
        "CCC": {**STALE, "ticker": "CCC", "feature_as_of_session": None},
        "DDD": {**CURRENT, "ticker": "DDD", "in_official_research_universe": False},
    }
    for ticker, row in dispositions.items():
        row["official_qualification"] = "OFFICIAL_FIXTURE" if official[ticker] else "OUTSIDE"
    disposition = {"contract_version": iidp.EVIDENCE_CURRENCY_SOURCE_CONTRACT, "session": SESSION,
                   "records": dispositions, "official_research_universe": {"count": 3}}
    disposition.update(disposition_module.content_identity(disposition))
    integrated = iidp.build_artifact(
        session=SESSION, requested_at=REQUESTED_AT,
        technical_structure_artifact={"artifact_identity": "ts", "records": {"AAA": _tactical(), "BBB": {"eligible": False},
                                                                             "CCC": {"eligible": False}, "DDD": _tactical()}},
        financial_analysis_artifact={"artifact_identity": FA_IDENTITY, "records": {
            "AAA": _financial(), "BBB": _financial(), "CCC": {"status": "ABSENT"}, "DDD": _financial()}},
        current_valuation_artifact={"artifact_identity": "valuation", "records": {"AAA": SIZE_ONLY_VALUATION}},
        technical_coverage_disposition_artifact=disposition)
    screener = {"cards": {t: {"listing_exchange": "HOSE", "sector": {"label": "Tech", "namespace": "VCI", "status": "AVAILABLE"},
                              "entity_type": {"value": "corporate"},
                              "liquidity": {"status": "AVAILABLE" if t == "AAA" else "UNKNOWN", "reason": None,
                                            "research_value_reason": "NO_QUALIFIED_MARKET_WIDE_NUMERIC_ADV20",
                                            "descriptive_state": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", "research_value": None}}
                          for t in tickers}, "artifact_identity": "screener"}
    valuation = {"artifact_identity": "raw_valuation", "valuation_session": SESSION, "records": {
        "AAA": {"entity_class": "unknown", "share_basis_input": {"status": "RESEARCH_PROXY", "blocked_reasons": []},
                "price_input": {"blocked_reasons": []},
                "metrics": {"market_cap": {"status": "RESEARCH_USABLE", "blocked_reasons": []},
                            "P/E": {"status": "BLOCKED", "blocked_reasons": ["ENTITY_CLASS_UNRESOLVED"]}}}}}
    payload_lines = [json.dumps({"ticker": t, "features": {}, "fundamental_feature_context": {"availability": "INSUFFICIENT_DATA"}},
                                sort_keys=True) + "\n" for t in ("AAA", "BBB")]
    with gzip.open(tmp_path / "store.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.writelines(payload_lines)
    store = {"artifact_identity": "store", "records_payload": {
        "path": "store.jsonl.gz", "record_count": 2,
        "canonical_jsonl_sha256": hashlib.sha256("".join(payload_lines).encode()).hexdigest()}}
    paths = {}
    for name, value in (("integrated", integrated), ("technical_disposition", disposition), ("valuation", valuation),
                        ("screener", screener), ("fundamental_store", store)):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(value), encoding="utf-8")
    return paths


def test_capability_map_projects_the_decision_input_and_reconciles_to_official_scope(tmp_path: Path) -> None:
    paths = _map_sources(tmp_path)
    result = capability.build(tmp_path, SESSION, paths)
    section = result["current_research_decision_input"]
    assert sum(section["evidence_class_distribution"].values()) == result["coverage"]["official_research_scope"] == 3
    assert section["evidence_class_distribution"] == {"FINANCIAL_RESEARCH_ONLY": 1, "INSUFFICIENT_CURRENT_EVIDENCE": 1,
                                                      "PARTIAL_MULTI_FACTOR_RESEARCH": 1}
    aaa = result["records"]["AAA"]
    assert aaa["decision_input"]["evidence_class"] == "PARTIAL_MULTI_FACTOR_RESEARCH"
    assert aaa["valuation_detail"]["current_research_evidence_class"] == "SIZE_CONTEXT_ONLY"
    assert aaa["valuation_fitness"] == "UNAVAILABLE"  # v1 field now reads the corrected IID valuation status
    assert result["records"]["DDD"]["decision_input"]["evidence_class"] == "OUTSIDE_CURRENT_RESEARCH_SCOPE"
    assert result["decision_readiness"] == {"INSUFFICIENT_CURRENT_EVIDENCE": 2, "PARTIAL_RESEARCH_READY": 2}
    again = capability.build(tmp_path, SESSION, paths)
    assert again["artifact_identity"] == result["artifact_identity"]
