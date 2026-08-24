import pytest

from historical_matched_value_existing_store_requalification import (build_artifact, fhsc_anchor_interpretation,
                                                                       inventory_record)


def prior():
    rows = [{"ticker": ticker, "session": session} for ticker in ("FPT", "HPG", "SSI", "VCB") for session in ("2026-08-07", "2026-08-10", "2026-08-11")]
    return {"fhsc_reconciliation_contract": {"reconciliation_counts": {"EXACT": 12}}, "qualified_rows": rows}


def test_execution_schema_is_not_an_explicit_value_schema():
    row = inventory_record(dataset="trades", file_count=1, columns=["price", "quantity", "board_id"], source_kind="CANONICAL", semantic_note="fixture")
    assert row["execution_tick_price_quantity"] is True
    assert row["explicit_matched_traded_value"] is False


def test_daily_ohlcv_has_no_value_semantic():
    row = inventory_record(dataset="daily", file_count=1, columns=["open", "high", "low", "close", "volume"], source_kind="DAILY", semantic_note="fixture")
    assert row["only_ohlcv"] is True
    assert row["explicit_total_traded_value"] is False


def test_anchor_scope_stays_restricted_to_twelve_rows():
    result = fhsc_anchor_interpretation(prior())
    assert result["generalization"].startswith("NOT_JUSTIFIED")


def test_incomplete_anchor_shape_fails_closed():
    bad = prior(); bad["qualified_rows"] = bad["qualified_rows"][:-1]
    with pytest.raises(ValueError):
        fhsc_anchor_interpretation(bad)


def test_artifact_blocks_adv20_without_widening_contract():
    artifact = build_artifact(inventories=[], database_inventory=[], prior=prior(), raw_counter_fields=["grossTradeAmount"])
    assert artifact["authority_result"] == "EXISTING_STORE_CANNOT_UNLOCK_ADV20"
    assert artifact["qualified_matched_value"]["adv20"]["ready"] is False
    assert artifact["raw_trades_field_observation"]["gross_trade_amount_semantics"].startswith("UNRESOLVED")


def test_artifact_identity_is_deterministic():
    first = build_artifact(inventories=[], database_inventory=[], prior=prior(), raw_counter_fields=[])
    second = build_artifact(inventories=[], database_inventory=[], prior=prior(), raw_counter_fields=[])
    assert first["artifact_identity"] == second["artifact_identity"]
