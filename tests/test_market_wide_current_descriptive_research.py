import hashlib
import json
from datetime import date, timedelta

import pytest

from field_temporal_contract import stable_id as p3f9b_stable_id
from market_wide_current_liquidity_research import content_identity as liquidity_content_identity
from market_wide_current_descriptive_research import (
    MarketWideCurrentDescriptiveResearchError,
    build_artifact,
)

TARGET = "2026-08-21"


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _trading_days(end: str, count: int) -> list[str]:
    """count consecutive weekday sessions ending exactly at `end` (inclusive)."""
    d = date.fromisoformat(end)
    days = []
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(days))


def _observations(end: str, count: int, *, start_close: float, step: float) -> list[dict]:
    days = _trading_days(end, count)
    return [
        {"session": day, "open": start_close + step * i, "high": start_close + step * i,
         "low": start_close + step * i, "close": start_close + step * i, "volume": 100000 + i}
        for i, day in enumerate(days)
    ]


def universe_resolution(records, *, denominator, observed):
    payload = {
        "records": records,
        "current_active_equity_denominator": {"count": denominator},
        "observed_session_cohort": {"count": observed},
        "input_candidates": {"resolved_completed_session": TARGET},
    }
    digest = _hash(payload)
    return {**payload, "artifact_sha256": digest, "artifact_identity": f"current_universe_status_and_session_coverage_resolution:{digest}"}


def p3f9b_snapshot(records):
    payload = {"records": records, "resolved_completed_session": TARGET}
    digest = p3f9b_stable_id(payload)
    return {**payload, "snapshot_sha256": digest, "snapshot_identity": f"p3f9_exact_session_snapshot:{digest}"}


def liquidity_artifact(records, *, snapshot_identity):
    payload = {
        "records": records, "resolved_completed_session": TARGET,
        "universe": {"canonical_candidate_count": len(records), "source_snapshot_identity": snapshot_identity},
        "coverage": {"disposition_counts": {"CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE": sum(1 for r in records.values() if r.get("disposition") == "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE")}},
        "authority_boundary": {"QUALIFIED_LIQUIDITY_INPUTS": False},
    }
    identity = liquidity_content_identity(payload)
    return {**payload, **identity}


def _ur_record(ticker, state, membership="INCLUDED"):
    return {"ticker": ticker, "activity_and_session_state": state, "membership_state": membership}


def _liq_eligible_record(ticker):
    return {
        "ticker": ticker, "disposition": "CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE", "session": TARGET,
        "board_composition": {
            "MATCHED_ROUND_LOT": {"active_volume_raw_total": 1000.0, "provider_raw_composition_ratio": 1.0},
        },
        "g1_v_reconciliation": {"verdict": "EXACT_MATCH"},
        "current_ohlc_v": 10000.0,
        "liquidity_research_contract": {"CURRENT_SESSION_LIQUIDITY_RESEARCH": "ELIGIBLE"},
        "value_status": "GROSS_TRADE_AMOUNT_RETAINED_ONLY_NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED",
    }


def _liq_missing_record(ticker):
    return {"ticker": ticker, "disposition": "MISSING", "reason": "NO_CURRENT_SESSION_ACTIVE_BOARD"}


def _build_scenario():
    """5 same-session risers (sector A, 5 members -> AVAILABLE), 1 same-session decliner (no sector),
    1 stale-but-available (sector unassigned), 1 insufficient-history SESSION_MISSING, 1 delisted."""
    ur_records, pf_records, liq_records, classifications = {}, {}, {}, {}

    risers = [f"RIS{i}" for i in range(5)]
    for ticker in risers:
        ur_records[ticker] = _ur_record(ticker, "ACTIVE_LISTED_OBSERVED")
        pf_records[ticker] = {"disposition": "EXACT_SESSION_RETAINED",
                              "observations": _observations(TARGET, 20, start_close=100.0, step=1.0)}
        liq_records[ticker] = _liq_eligible_record(ticker)
        classifications[ticker] = {"classification_authority": "QUALIFIED_CLASSIFICATION",
                                   "classification_namespace": "NS", "entity_class": "SECTOR_A"}

    ur_records["DEC1"] = _ur_record("DEC1", "ACTIVE_LISTED_OBSERVED")
    pf_records["DEC1"] = {"disposition": "EXACT_SESSION_RETAINED",
                          "observations": _observations(TARGET, 20, start_close=100.0, step=-1.0)}
    liq_records["DEC1"] = _liq_missing_record("DEC1")

    stale_days = _trading_days(TARGET, 25)[:20]  # ends well before TARGET
    ur_records["STALE1"] = _ur_record("STALE1", "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION")
    pf_records["STALE1"] = {"disposition": "SESSION_MISSING",
                            "observations": [{"session": day, "close": 50.0 + i, "volume": 1000} for i, day in enumerate(stale_days)]}
    liq_records["STALE1"] = _liq_missing_record("STALE1")

    ur_records["THIN1"] = _ur_record("THIN1", "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION")
    pf_records["THIN1"] = {"disposition": "SESSION_MISSING", "observations": []}
    liq_records["THIN1"] = _liq_missing_record("THIN1")

    ur_records["OLD1"] = _ur_record("OLD1", "INACTIVE_OR_DELISTED", membership="UNKNOWN")
    pf_records["OLD1"] = {"disposition": "PROVIDER_REJECTED", "observations": []}
    liq_records["OLD1"] = _liq_missing_record("OLD1")

    ur = universe_resolution(ur_records, denominator=5 + 1 + 2, observed=6)
    pf = p3f9b_snapshot(pf_records)
    liq = liquidity_artifact(liq_records, snapshot_identity=pf["snapshot_identity"])
    return ur, pf, liq, classifications


def test_market_breadth_counts_only_same_session_records_and_keeps_denominators_distinct():
    ur, pf, liq, classifications = _build_scenario()
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)

    breadth = artifact["market_breadth"]
    assert breadth["current_active_equity_denominator"] == 8
    assert breadth["observed_session_cohort"] == 6
    assert breadth["same_session_technical_feature_available_count"] == 6  # 5 risers + 1 decliner
    assert breadth["advancing"] == 5
    assert breadth["declining"] == 1
    assert breadth["quality_state"] == "PARTIAL_COVERAGE_EXPLICIT"
    assert breadth["stale_feature_available_but_not_current_session_count"] == 1  # STALE1


def test_stale_session_features_never_counted_as_current_session_breadth():
    ur, pf, liq, classifications = _build_scenario()
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)
    stale_record = artifact["records"]["STALE1"]
    assert stale_record["technical_features"]["status"] == "SHADOW_ONLY"
    assert stale_record["technical_features"]["is_current_session"] is False
    assert stale_record["technical_features"]["feature_as_of_session"] != TARGET


def test_thin_session_missing_ticker_has_no_technical_features():
    ur, pf, liq, classifications = _build_scenario()
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)
    record = artifact["records"]["THIN1"]
    assert record["technical_features"]["status"] == "MISSING"
    assert record["in_current_descriptive_scope"] is True


def test_delisted_ticker_is_out_of_scope_with_not_applicable_features_and_liquidity():
    ur, pf, liq, classifications = _build_scenario()
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)
    record = artifact["records"]["OLD1"]
    assert record["in_current_descriptive_scope"] is False
    assert record["technical_features"]["status"] == "NOT_APPLICABLE"
    assert record["liquidity"]["status"] == "NOT_APPLICABLE"


def test_sector_breadth_available_with_five_same_session_members_and_fails_closed_otherwise():
    ur, pf, liq, classifications = _build_scenario()
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)
    sectors = artifact["sector_breadth"]["sectors"]
    key = next(iter(sectors))
    sector = sectors[key]
    assert sector["status"] == "AVAILABLE"
    assert sector["same_session_eligible_count"] == 5
    assert sector["advancing"] == 5
    assert len(sector["member_relative_positions"]) == 5
    assert artifact["sector_breadth"]["sector_count_available"] == 1


def test_sector_fails_closed_when_below_minimum_cohort_size():
    ur, pf, liq, classifications = _build_scenario()
    # Reclassify DEC1 alone into its own tiny sector -- only 1 same-session member, below MIN_COHORT_MEMBERS.
    classifications = dict(classifications)
    classifications["DEC1"] = {"classification_authority": "QUALIFIED_CLASSIFICATION", "classification_namespace": "NS", "entity_class": "SECTOR_TINY"}
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)
    tiny = next(s for s in artifact["sector_breadth"]["sectors"].values() if s["classification_label"] == "SECTOR_TINY")
    assert tiny["status"] == "UNAVAILABLE_INSUFFICIENT_COVERAGE"
    assert "advancing" not in tiny


def test_liquidity_features_only_counts_eligible_and_preserves_shb_style_residual_verdict():
    ur, pf, liq, classifications = _build_scenario()
    # Give one riser a non-exact G1/v residual, mirroring SHB's real OTHER verdict.
    liq = json.loads(json.dumps(liq))
    liq["records"]["RIS0"]["g1_v_reconciliation"] = {"verdict": "OTHER", "delta": 4.0}
    liq = {**liq, **liquidity_content_identity(liq)}
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)
    features = artifact["liquidity_features"]
    assert features["eligible_count"] == 5
    assert features["current_active_equity_denominator"] == 8
    assert any(w["ticker"] == "RIS0" and w["g1_v_reconciliation"]["verdict"] == "OTHER" for w in features["reconciliation_warnings"])
    assert artifact["records"]["RIS0"]["liquidity"]["g1_v_reconciliation"]["verdict"] == "OTHER"


def test_blocked_outputs_and_no_ranking_recommendation_fields_anywhere():
    ur, pf, liq, classifications = _build_scenario()
    artifact = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
                              entity_classifications=classifications)
    assert artifact["validation"]["blocked_outputs"]["stock_rankings"] == "RANKING_PROHIBITED"
    assert artifact["validation"]["blocked_outputs"]["buy_sell_recommendations"] == "RECOMMENDATION_PROHIBITED"
    assert artifact["authority_boundary"]["ranking_recommendation_valuation"] == "NOT_EMITTED"
    serialized_records = json.dumps(artifact["records"])
    for forbidden in ("recommendation_score", "target_price", "buy_signal", "sell_signal", "position_size", "\"rank\""):
        assert forbidden not in serialized_records


def test_deterministic_identity_across_repeated_builds():
    ur, pf, liq, classifications = _build_scenario()
    first = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq, entity_classifications=classifications)
    second = build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq, entity_classifications=classifications)
    assert first["artifact_identity"] == second["artifact_identity"]


def test_recovered_history_preserves_the_existing_feature_contract_and_provenance():
    ur, pf, liq, classifications = _build_scenario()
    pf_records = dict(pf["records"])
    pf_records["DEC1"] = {"disposition": "EXACT_SESSION_RETAINED", "observations": _observations(TARGET, 7, start_close=100.0, step=-1.0)}
    pf = p3f9b_snapshot(pf_records)
    liq = liquidity_artifact(liq["records"], snapshot_identity=pf["snapshot_identity"])
    recovered_observations = _observations(TARGET, 20, start_close=100.0, step=-1.0)
    recovery_payload = {
        "target_session": TARGET,
        "source_lineage": {"p3f9b_snapshot_identity": pf["snapshot_identity"]},
        "recovered_history_overrides": {
            "DEC1": {"state": "RECOVERED_COMPLETE_TECHNICAL_HISTORY", "payload_sha256": "retained",
                     "observations": recovered_observations}
        },
    }
    recovery = {
        **recovery_payload,
        "artifact_sha256": _hash(recovery_payload),
        "artifact_identity": "market_wide_current_technical_coverage_scaleout:retained",
    }

    artifact = build_artifact(
        universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq,
        entity_classifications=classifications, technical_history_recovery_artifact=recovery,
    )
    assert artifact["market_breadth"]["same_session_technical_feature_available_count"] == 6
    assert artifact["records"]["DEC1"]["technical_features"]["is_current_session"] is True
    assert artifact["records"]["DEC1"]["technical_features"]["technical_history_provenance"]["source"] == "RETAINED_DNSE_EXTENDED_HISTORY_RECOVERY"


def test_tampered_inputs_are_rejected():
    ur, pf, liq, classifications = _build_scenario()

    tampered_ur = dict(ur)
    tampered_ur["current_active_equity_denominator"] = {"count": 999}
    with pytest.raises(MarketWideCurrentDescriptiveResearchError):
        build_artifact(universe_resolution_artifact=tampered_ur, p3f9b_snapshot=pf, liquidity_artifact=liq, entity_classifications=classifications)

    tampered_pf = dict(pf)
    tampered_pf["resolved_completed_session"] = "2099-01-01"
    with pytest.raises(MarketWideCurrentDescriptiveResearchError):
        build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=tampered_pf, liquidity_artifact=liq, entity_classifications=classifications)

    tampered_liq = dict(liq)
    tampered_liq["resolved_completed_session"] = "2099-01-01"
    with pytest.raises(MarketWideCurrentDescriptiveResearchError):
        build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=tampered_liq, entity_classifications=classifications)


def test_session_mismatch_between_liquidity_snapshot_identity_and_p3f9b_raises():
    ur, pf, liq, classifications = _build_scenario()
    liq = dict(liq)
    liq["universe"] = {**liq["universe"], "source_snapshot_identity": "p3f9_exact_session_snapshot:wrong"}
    liq = {**liq, **liquidity_content_identity(liq)}
    with pytest.raises(MarketWideCurrentDescriptiveResearchError):
        build_artifact(universe_resolution_artifact=ur, p3f9b_snapshot=pf, liquidity_artifact=liq, entity_classifications=classifications)
