from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import stocklookup_core.decision.current_research_decision_input as decision_input
import stocklookup_core.valuation.current_research_valuation_context as valuation
import monetary_basis_contract as basis
import provider_financial_monetary_basis_verdict as pin
import provider_financial_semantic_basis as semantic


ROOT = Path(__file__).resolve().parents[1]


def _cap() -> dict:
    envelope = basis.build_basis(currency="VND", scale="units", basis_source="DNSE contract * shares",
                                 basis_status=basis.RESEARCH_CONTRACT_QUALIFIED,
                                 multiplier_to_vnd=1, normalized_unit="VND")
    return {"status": "RESEARCH_USABLE", "value": 2_000_000, "monetary_basis": envelope}


def _equity(period: str = "2026-Q1", value: int = 1_000_000, **changes) -> dict:
    year, quarter = int(period[:4]), int(period[-1])
    end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    row = {"ticker": "AAA", "canonical_metric": "shareholders_equity",
           "native_period_label": period, "period_end": f"{year}-{end}",
           "period_semantic_state": "POINT_IN_TIME_BALANCE_SHEET",
           "reported_value": value, "source_status": "provider_reported",
           "lineage_complete": True, "source_conflicts": [], "statement_scope": "consolidated",
           "source_lineage": {"provider": "VCI", "source_file": "AAA_balance_sheet_quarter.parquet",
                              "source_sha256": "fixture"}}
    row.update(changes)
    return row


def _pb(*, entity="corporate", rows=None, cap=None, verdict="pinned", session="2026-09-24") -> dict:
    return valuation._book_value_method(
        ticker="AAA", entity=entity, share_class="CURRENT_SHARE_RESEARCH_PROXY",
        market_cap=_cap() if cap is None else cap,
        equity_rows=[_equity()] if rows is None else rows, decision_session=session,
        verdict=pin.resolve(ROOT) if verdict == "pinned" else verdict)


def test_anchor_classes_distinguish_scale_from_value_and_rounding() -> None:
    assert semantic._anchor_class(999_999, 1_000_000)[0] == semantic.EXACT_OR_DISPLAY_ROUNDED
    assert semantic._anchor_class(1_000_000_000, 1_000_000)[0] == semantic.SCALE_CONTRADICTION
    assert semantic._anchor_class(1_000_000_000_000, 1_000_000)[0] == semantic.SCALE_CONTRADICTION
    assert semantic._anchor_class(36_174_402_829_663, 37_165_930_000_000)[0] == semantic.SAME_SCALE_VALUE_DEVIATION
    assert semantic._anchor_class(3_000_000, 1_000_000)[0] == semantic.UNEXPLAINED_DEVIATION


def test_retained_verdict_is_one_shape_only_and_tamper_fails_closed(tmp_path: Path) -> None:
    artifact = pin.resolve(ROOT)
    assert artifact["qualified_shapes"] == ["VCI:balance_sheet"]
    counts = artifact["source_reconciliation"]["shapes"]["('VCI', 'balance_sheet')"]["classification_counts"]
    assert counts[semantic.EXACT_OR_DISPLAY_ROUNDED] >= 5
    assert counts[semantic.SAME_SCALE_VALUE_DEVIATION] == 1
    assert counts[semantic.SCALE_CONTRADICTION] == counts[semantic.UNEXPLAINED_DEVIATION] == 0
    assert counts[semantic.ANCHOR_INELIGIBLE_CURRENCY_MISMATCH_NO_FX_CONTRACT] == 2
    anchors = artifact["source_reconciliation"]["shapes"]["('VCI', 'balance_sheet')"]["anchors"]
    assert all(row["classification"] == semantic.ANCHOR_INELIGIBLE_CURRENCY_MISMATCH_NO_FX_CONTRACT
               for row in anchors if row["ticker"] == "PVD")
    assert next(row for row in anchors if row["ticker"] == "VNM"
                and row["canonical_metric"] == "shareholders_equity")["classification"] == semantic.SAME_SCALE_VALUE_DEVIATION
    for ticker in ("PVD", "VNM"):
        conflicted = {"ticker": ticker, "provider": "VCI", "statement_family": "balance_sheet",
                      "status": "conflicted", "conflicts": [{"kind": "official_citation_disagrees"}]}
        assert semantic.classify_provider_exact_research_usable(
            conflicted, registry=artifact["semantic_basis_registry"])["eligible"] is False
    unavailable = {"provider": "VCI", "statement_family": "balance_sheet",
                   "status": "unavailable", "value": None}
    assert semantic.classify_provider_exact_research_usable(
        unavailable, registry=artifact["semantic_basis_registry"])["eligible"] is False
    fake = tmp_path / "operations-review" / pin.DIRECTORY
    fake.mkdir(parents=True)
    (fake / pin.FILENAME).write_text('{"artifact_identity":"wrong"}', encoding="utf-8")
    try:
        pin.resolve(tmp_path)
    except pin.MonetaryBasisVerdictUnavailable:
        pass
    else:
        raise AssertionError("tampered verdict was accepted")


def test_pb_research_usable_with_explicit_proxy_limitations_and_peer_context() -> None:
    method = _pb()
    assert method["status"] == "RESEARCH_USABLE" and method["value"] == 2
    assert method["equity_definition"] == "TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT"
    assert method["book_period_lag_quarters"] == 2
    assert "NCI_NOT_DEDUCTED" in method["limitations"]
    assert "PROVIDER_EQUITY_VALUE_NOT_INDEPENDENTLY_RECONCILED" in method["limitations"]
    assert method["is_actionable"] is False
    assert method["target_price"] is method["fair_value"] is method["probability"] is None
    assert _pb(verdict=None)["blocker_reason_codes"] == ["MONETARY_BASIS_VERDICT_UNAVAILABLE"]
    rows = {f"T{i}": {"entity_class": "corporate", "usable_relative_method_count": 1,
                       "methods": {valuation.PB_CURRENT_RESEARCH: {**method, "value": i + 1}}}
            for i in range(5)}
    peers = valuation.attach_peer_relative(rows)
    assert peers["T0"]["peer_relative"][valuation.PB_CURRENT_RESEARCH]["status"] == "READY_RESEARCH_ONLY"
    rows["T4"]["methods"][valuation.PB_CURRENT_RESEARCH]["ttm_compatibility_class"] += ":OTHER_SCOPE"
    separated = valuation.attach_peer_relative(rows)
    assert separated["T0"]["peer_relative"][valuation.PB_CURRENT_RESEARCH]["status"] == "INSUFFICIENT_PEER_COUNT"
    dimension = decision_input._valuation(
        {"valuation_methods": {valuation.PB_CURRENT_RESEARCH: method},
         "valuation_context_summary": {"status": "AVAILABLE", "peer_relative_state": "MID_RANGE_VS_PEERS"}},
        None, {"applicability_status": "RESOLVED"})
    assert valuation.PB_CURRENT_RESEARCH in dimension["usable_methods"]


def test_pb_fail_closed_on_negative_stale_conflict_entity_and_basis() -> None:
    assert _pb(rows=[_equity(value=-1)])["status"] == "PB_NOT_MEANINGFUL"
    assert _pb(rows=[_equity(value=-1)])["blocker_reason_codes"] == ["NON_POSITIVE_BOOK_EQUITY"]
    assert _pb(rows=[_equity(period="2025-Q2")])["blocker_reason_codes"] == ["BOOK_EQUITY_PERIOD_STALE"]
    latest = _equity(period="2026-Q2", source_conflicts=[{"kind": "source_conflict"}])
    fallback = _pb(rows=[latest, _equity(period="2026-Q1")])
    assert fallback["status"] == "RESEARCH_USABLE"
    assert "LATEST_BALANCE_SHEET_PERIOD_UNUSABLE_EARLIER_PERIOD_USED" in fallback["warnings"]
    assert _pb(rows=[latest])["status"] == "INPUT_BLOCKED"
    assert _pb(entity="insurance")["status"] == "NOT_APPLICABLE"
    assert _pb(entity="unknown")["blocker_reason_codes"] == ["ENTITY_CLASS_UNRESOLVED"]
    incompatible = deepcopy(_cap())
    incompatible["monetary_basis"] = basis.build_basis(currency="USD", scale="units", basis_source="bad")
    assert _pb(cap=incompatible)["status"] == "INPUT_BLOCKED"


def test_pb_does_not_replace_legacy_on_scope_period_or_missing_scope() -> None:
    from official_legacy_precedence import NOT_COMPARABLE
    from tests.test_financial_evidence_currency_refresh import _fact, _pb_official

    baseline = _pb(rows=[_equity(period="2025-Q4")])
    same_period_scope = _pb_official([
        _fact("AAA", "shareholders_equity", "2025", 9_000_000, statement_scope="standalone"),
    ])
    assert same_period_scope["formula"] == "research_usable_market_cap / VCI_total_owners_equity"
    assert abs(same_period_scope["value"] - baseline["value"]) < 1e-12
    same_period_metric = _pb_official([_fact("AAA", "total_equity", "2025", 9_000_000)])
    assert same_period_metric["official_legacy_precedence"] == NOT_COMPARABLE
    assert same_period_metric["formula"] == "research_usable_market_cap / VCI_total_owners_equity"
    different_period = _pb_official([_fact("AAA", "shareholders_equity", "2024", 9_000_000)])
    assert different_period["official_legacy_precedence"] == NOT_COMPARABLE
    missing_scope = _pb_official([_fact("AAA", "shareholders_equity", "2025", 9_000_000, statement_scope=None)])
    assert valuation._official_equity_row(
        [_fact("AAA", "shareholders_equity", "2025", 9_000_000, statement_scope=None)], "AAA",
    ) is None
    assert missing_scope["formula"] == "research_usable_market_cap / VCI_total_owners_equity"
    exact = _pb_official([_fact("AAA", "shareholders_equity", "2025", 1_000_000)])
    assert exact["formula"] == "research_usable_market_cap / official_total_owners_equity"
    conflicted = _pb_official([_fact("AAA", "shareholders_equity", "2025", 2_000_000)])
    assert conflicted["status"] == "INPUT_BLOCKED"
