from __future__ import annotations

from copy import deepcopy

import financial_analysis_engine_v2 as engine
import structured_financial_depth_recovery as recovery


def _row(metric: str, value: float, *, ticker: str = "AAA", period: str = "2026-Q2",
         provider: str = "VCI", source: str = "AAA_balance", scope: str = "consolidated") -> dict:
    return {
        "ticker": ticker, "canonical_metric": metric, "reported_value": value,
        "native_period_label": period, "period_end": period,
        "period_semantic_state": "POINT_IN_TIME_BALANCE_SHEET", "source_status": "provider_reported",
        "lineage_complete": True, "source_conflicts": [], "statement_scope": scope,
        "normalized_candidate_unit": {"currency": "unknown", "scale": "unknown"},
        "source_lineage": {"provider": provider, "source_file": source, "source_sha256": "sha",
                           "fact_id": f"{ticker}-{metric}-{period}", "source_observation_ids": [metric]},
    }


def test_explicit_same_source_borrowings_recover_a_provenanced_total_and_exact_leverage():
    rows = [_row("short_term_interest_bearing_debt", 30), _row("long_term_interest_bearing_debt", 20),
            _row("shareholders_equity", 100), _row("total_assets", 200)]
    before = deepcopy(rows)
    result = recovery.recover(rows, requested_at="t")
    recovered = result["recovered_rows"]
    assert rows == before
    assert len(recovered) == 1
    total = recovered[0]
    assert total["reported_value"] == 50
    assert total["derived_from"] == list(recovery.EXPLICIT_DEBT_COMPONENTS)
    assert total["source_lineage"]["provider"] == "VCI"
    assert total["source_lineage"]["source_file"] == "AAA_balance"
    context = engine.build_ticker_context("AAA", [*rows, *recovered], issuer_type="corporate", source_identities={})
    assert context["features"]["debt_to_equity"]["fitness"] == "READY"
    assert context["features"]["debt_to_equity"]["value"] == 0.5
    assert context["features"]["debt_to_assets"]["value"] == 0.25
    assert context["leverage_basis"] == "EXPLICIT_SAME_PROVIDER_SHORT_AND_LONG_TERM_BORROWINGS"


def test_no_total_is_recovered_when_explicit_component_set_is_incomplete():
    result = recovery.recover([_row("short_term_interest_bearing_debt", 30)], requested_at="t")
    record = result["artifact"]["records"]["AAA"]
    assert result["recovered_rows"] == []
    missing = {item["canonical_metric"]: item for item in record["missing_components"]}
    assert missing["total_interest_bearing_debt"]["disposition"] == "DEBT_COMPONENT_SET_INCOMPLETE"


def test_no_liabilities_substitution_or_cross_provider_leverage_is_allowed():
    rows = [_row("total_liabilities", 90), _row("shareholders_equity", 100)]
    result = recovery.recover(rows, requested_at="t")
    assert result["recovered_rows"] == []
    context = engine.build_ticker_context("AAA", rows, issuer_type="corporate", source_identities={})
    assert context["features"]["debt_to_equity"]["fitness"] == "BLOCKED_BY_EVIDENCE"


def test_current_assets_and_liabilities_are_explicitly_source_exposes_not_retained():
    result = recovery.recover([_row("total_assets", 200)], requested_at="t")
    missing = result["artifact"]["records"]["AAA"]["missing_components"]
    dispositions = {item["canonical_metric"]: item["disposition"] for item in missing}
    assert dispositions["current_assets"] == "SOURCE_EXPOSES_NOT_RETAINED"
    assert dispositions["current_liabilities"] == "SOURCE_EXPOSES_NOT_RETAINED"


def test_recovery_identity_is_deterministic_and_not_actionable():
    rows = [_row("short_term_interest_bearing_debt", 30), _row("long_term_interest_bearing_debt", 20)]
    first = recovery.recover(rows, requested_at="one")["artifact"]
    second = recovery.recover(rows, requested_at="two")["artifact"]
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["authority_boundary"]["is_actionable"] is False
    assert first["authority_boundary"]["fcf_fabricated"] is False
