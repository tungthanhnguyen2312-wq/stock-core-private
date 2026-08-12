from datetime import datetime, timezone

from dnse_current_regime_price_basis import (
    promotion_analysis, qualify_event, query_for_window, reconcile, select_cohort, snapshot_coverage,
)


def event(record_id="event", ticker="HPG", code="DIV", exdate="2026-05-11", value=500.0, public="2026-05-05"):
    return {"record_id": record_id, "provider": "VCI", "ticker": ticker, "event_code": code,
            "exright_date": exdate, "exercise_ratio": .1 if code == "ISS" else .05,
            "value_per_share": None if code == "ISS" else value, "public_date": public,
            "revision_status": "observed", "coverage_status": "retained"}


UNIVERSE = {symbol: {"instrument_class": "EQUITY", "exchange_raw": "STO"} for symbol in ("HPG", "VNM", "VCB")}


def response(*, ok=True, body=None, error_code="http_status_500"):
    sessions = ["2026-05-07", "2026-05-08", "2026-05-09", "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14"]
    return {"ok": ok, "body": body or {"t": [int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) for day in sessions],
                                           "o": [100, 100, 100, 102, 103, 104, 105], "h": [101] * 7, "l": [99] * 7,
                                           "c": [100, 100, 100, 102, 103, 104, 105], "v": [1] * 7},
            "error_code": error_code, "raw_payload_hash": "hash", "request_identity": "request"}


def test_cohort_selection_is_deterministic_and_requires_explicit_exdate():
    selected = select_cohort([event("b", "VNM", exdate="2026-06-26", value=1850), event("a"), event("missing", exdate=None)], UNIVERSE)
    assert [case["record_id"] for case in selected["eligible"]] == ["a", "b"]
    assert selected["excluded"] == [{"ticker": "HPG", "record_id": "missing", "exright_date": None, "reason": "explicit_exright_date_required"}]


def test_selection_excludes_post_exdate_publication_and_unsupported_event():
    late = event("late", code="ISS", exdate="2026-06-15", public="2026-06-16")
    meeting = event("meeting", code="AGME")
    selected = select_cohort([late, meeting], UNIVERSE)
    assert not selected["eligible"]
    assert {row["reason"] for row in selected["excluded"]} == {"event_publication_after_exright_date", "event_type_not_supported_by_existing_deterministic_contract"}


def test_cash_window_is_insufficient_without_reference_or_pre_event_snapshot():
    case = select_cohort([event()], UNIVERSE)["eligible"][0]
    result = qualify_event(case, response())
    assert result["verdict"] == "UNKNOWN/INSUFFICIENT_EVIDENCE"
    assert result["blocker"] == "cash_dividend_requires_independent_reference_or_pre_event_snapshot"


def test_stock_adjusted_pattern_does_not_become_retroactive_authority_without_snapshot():
    case = select_cohort([event(code="ISS")], UNIVERSE)["eligible"][0]
    result = qualify_event(case, response())
    assert result["adjusted_hypothesis_result"] == "SUPPORTED"
    assert result["verdict"] == "UNKNOWN/INSUFFICIENT_EVIDENCE"
    assert result["blocker"] == "current_query_has_no_pre_event_snapshot_to_establish_retroactive_rewrite"


def test_request_failure_and_reconciliation_are_explicit():
    case = select_cohort([event()], UNIVERSE)["eligible"][0]
    failed = qualify_event(case, response(ok=False))
    summary = reconcile([failed])
    assert failed["qualification_status"] == "REQUEST_FAILURE"
    assert summary["provider_request_failures"] == 1
    assert summary["exact_reconciliation"]


def test_promotion_candidate_is_not_active_and_constrained_by_unresolved_cases():
    unresolved = {"qualification_status": "INSUFFICIENT_EVIDENCE", "ticker": "HPG", "exchange_raw": "STO", "event_type": "cash_dividend", "official_exright_date": "2026-05-11"}
    result = promotion_analysis([unresolved])
    assert result["result"] == "NO_BROADER_PROMOTION_SUPPORTED"
    assert "unresolved_event_cases_present" in result["blockers"]
    assert result["proposed_scope"] is None


def test_contradictions_prevent_unsafe_promotion():
    result = promotion_analysis([
        {"ticker": "AAA", "exchange_raw": "STO", "event_type": "cash_dividend", "official_exright_date": "2026-05-01", "qualification_status": "CONTRADICTION", "verdict": "CONTRADICTORY", "record_id": "conflict"},
    ])
    assert result["result"] == "NO_BROADER_PROMOTION_SUPPORTED"
    assert result["contradictions"] == ["conflict"]
    assert "contradictory_event_verdicts_present" in result["blockers"]


def test_snapshot_coverage_counts_only_active_known_basis():
    coverage = snapshot_coverage([{"price_basis_status": "UNKNOWN"}, {"price_basis_status": "ADJUSTED_RETROSPECTIVE"}, {}])
    assert coverage == {"candidates": 3, "known_basis_under_active_authority": 1, "unknown_basis": 2}


def test_ohlc_query_carries_the_explicit_symbol_required_by_the_provider():
    assert query_for_window({"from": "2026-05-01", "to": "2026-05-21"}, symbol="hpg")["symbol"] == "HPG"
