"""AI_HANDOFF_FRESHNESS_AND_SOURCE_CONVERGENCE_V1: macro_presentation_context.py is a
descriptive, cadence-aware wrapper around the retained macro_sync.py web snapshot. It must
never be confused with current_macro_regime/v1 (no regime classification, no retained raw
provider payload, distinct contract_version) and must never call a network."""
from __future__ import annotations

import macro_presentation_context as mpc


def _row(key, *, source="FRED", frequency="daily", period="2026-09-11", value=1.23):
    return {
        "key": key, "label": key, "category": "rates", "value": value, "unit": "%",
        "period": period, "frequency": frequency, "source": source,
        "source_url": "https://example.invalid/" + key,
        "pipeline_updated_at": "2026-09-11T09:00:00+07:00",
    }


def _snapshot(rows, foreign_flow=None):
    return {
        "schema_version": 1, "generated_at": "2026-09-11T09:00:00+07:00",
        "data_as_of": "2026-09-11", "indicators": rows,
        "foreign_flow": foreign_flow or {"status": "unavailable", "reason": "no data"},
    }


def test_contract_version_distinct_from_current_macro_regime():
    artifact = mpc.build(None, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["contract_version"] == "macro_presentation_context/v1"
    assert artifact["contract_version"] != "current_macro_regime/v1"


def test_missing_snapshot_is_explicit_unavailable_not_an_exception():
    artifact = mpc.build(None, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["status"] == "UNAVAILABLE"
    assert artifact["reason_code"] == "NO_RETAINED_MACRO_SNAPSHOT"
    assert artifact["indicators"] == {}


def test_all_fresh_series_yields_available():
    snapshot = _snapshot([_row("us_fedfunds", period="2026-09-11")])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["status"] == "AVAILABLE"
    assert artifact["indicators"]["us_fedfunds"]["freshness"]["freshness_status"] == "current"


def test_stale_series_is_reported_stale_not_silently_current():
    snapshot = _snapshot([_row("us_fedfunds", frequency="daily", period="2026-07-01")])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["indicators"]["us_fedfunds"]["freshness"]["freshness_status"] == "stale"
    assert artifact["status"] in {"PARTIAL", "UNAVAILABLE"}


def test_mixed_fresh_and_stale_is_partial():
    snapshot = _snapshot([
        _row("us_fedfunds", frequency="daily", period="2026-09-11"),
        _row("dxy", frequency="daily", period="2026-06-01"),
    ])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["status"] == "PARTIAL"


def test_annual_series_is_not_misjudged_stale_against_quarterly_cadence():
    # ~250 days old: would be "stale" under a 92+35-day quarterly rule but is normal for
    # an annual series under its own dedicated macro_annual cadence.
    snapshot = _snapshot([_row("vn_gdp_yoy", frequency="annual", period="2026-01-05", source="World Bank")])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["indicators"]["vn_gdp_yoy"]["freshness_domain"] == "macro_annual"
    assert artifact["indicators"]["vn_gdp_yoy"]["freshness"]["freshness_status"] == "current"


def test_yahoo_source_tagged_unofficial_not_promoted_by_freshness():
    snapshot = _snapshot([_row("sp500", source="Yahoo Finance", period="2026-09-11")])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["indicators"]["sp500"]["source_authority"] == "UNOFFICIAL_MARKET_DATA_SOURCE"


def test_fred_and_world_bank_tagged_official():
    snapshot = _snapshot([
        _row("us_fedfunds", source="FRED", period="2026-09-11"),
        _row("vn_gdp_yoy", source="World Bank", frequency="annual", period="2026-01-01"),
    ])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["indicators"]["us_fedfunds"]["source_authority"] == "OFFICIAL_PUBLIC_SOURCE"
    assert artifact["indicators"]["vn_gdp_yoy"]["source_authority"] == "OFFICIAL_MULTILATERAL_SOURCE"


def test_vcb_and_sjc_tagged_first_party_not_official():
    snapshot = _snapshot([
        _row("usdvnd_vcb", source="Vietcombank", period="2026-09-11"),
        _row("gold_sjc", source="SJC", period="2026-09-11"),
    ])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["indicators"]["usdvnd_vcb"]["source_authority"] == "FIRST_PARTY_QUOTE_UNOFFICIAL_TRANSPORT"
    assert artifact["indicators"]["gold_sjc"]["source_authority"] == "FIRST_PARTY_QUOTE_UNOFFICIAL_TRANSPORT"


def test_foreign_flow_slot_preserved_and_labelled_unavailable():
    snapshot = _snapshot([_row("us_fedfunds")], foreign_flow={"status": "unavailable", "reason": "no data"})
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert artifact["foreign_flow"]["status"] == "UNAVAILABLE"
    assert artifact["foreign_flow"]["source"] == "macro_sync_runtime_snapshot"


def test_failed_refresh_with_no_retained_snapshot_still_never_raises():
    artifact = mpc.build(None, generated_at="2026-09-11T09:00:00+07:00", refresh_status="FAILED", refresh_reason_code="MACRO_SYNC_EXTERNAL_OR_PIPELINE_FAILURE")
    assert artifact["status"] == "UNAVAILABLE"
    assert artifact["reason_code"] == "MACRO_SNAPSHOT_REFRESH_FAILED_AND_NO_RETAINED_SNAPSHOT"
    assert artifact["refresh_status"] == "FAILED"


def test_failed_refresh_still_uses_older_retained_snapshot_when_present():
    snapshot = _snapshot([_row("us_fedfunds", period="2026-09-11")])
    artifact = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00", refresh_status="FAILED")
    assert artifact["status"] == "AVAILABLE"
    assert artifact["refresh_status"] == "FAILED"


def test_load_snapshot_missing_file_returns_none(tmp_path):
    assert mpc.load_snapshot(tmp_path / "does_not_exist.json") is None


def test_load_snapshot_corrupt_file_returns_none_not_exception(tmp_path):
    path = tmp_path / "macro_snapshot.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert mpc.load_snapshot(path) is None


def test_deterministic_identity_across_rebuilds():
    snapshot = _snapshot([_row("us_fedfunds", period="2026-09-11")])
    one = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    two = mpc.build(snapshot, generated_at="2026-09-11T09:00:00+07:00")
    assert one["artifact_identity"] == two["artifact_identity"]
