import json
from pathlib import Path

import pytest

import completed_market_session_gate as gate
import prospective_market_snapshot_contract as market
import market_only_pit_eligibility as eligibility
from prospective_market_evidence_retention import retain_working_dates_calendar

RAW = json.dumps({"workingDates":["2026-10-02","2026-10-05","2026-10-07"]}).encode()
ARGS = dict(retrieved_at="2026-10-02T03:36:00Z", documentation_sha256="a"*64,
            documentation_retrieved_at="2026-10-02T03:40:00Z")


def receipt():
    return gate.build_working_dates_calendar_receipt(RAW, **ARGS)


def test_exact_source_dates_no_weekday_holiday_or_exchange_inference():
    value = receipt()
    assert value["sessions"] == ["2026-10-02","2026-10-05","2026-10-07"]
    assert "2026-10-06" not in value["sessions"]
    assert value["knowledge_available_at"] == "2026-10-02T03:40:00+00:00"
    assert value["source"]["scope"].endswith("EXCHANGES_UNSPECIFIED")
    assert value["allowed_uses"] == ["DNSE_FORWARD_WORKING_DATE_IDENTITY"]


def test_later_calendar_cannot_repair_t0_or_september_gap():
    old = ["2026-09-03","2026-09-04"]
    for day,cutoff in (("2026-10-02","2026-10-02T03:39:00Z"),
                       ("2026-09-30","2026-10-02T05:00:00Z")):
        assert gate.pit_calendar_at_cutoff(old,[receipt()],session=day,knowledge_cutoff=cutoff) == old
    assert gate.pit_calendar_at_cutoff(old,[receipt()],session="2026-10-02",
        knowledge_cutoff="2026-10-02T03:40:00Z") == receipt()["sessions"]


@pytest.mark.parametrize("dates", [[],["2026-10-05","2026-10-02"],
    ["2026-10-02","2026-10-02"],["2026-09-30"],["2026-10-02T00:00:00Z"]])
def test_invalid_or_historical_forward_dates_refused(dates):
    with pytest.raises(ValueError):
        gate.build_working_dates_calendar_receipt(json.dumps({"workingDates":dates}).encode(),**ARGS)


def test_tampered_calendar_refused():
    value = receipt(); value["sessions"].append("2026-10-06")
    with pytest.raises(ValueError,match="INTEGRITY"):
        gate.pit_calendar_at_cutoff([], [value],session="2026-10-02",knowledge_cutoff="2026-10-02T05:00:00Z")


def test_rehashed_calendar_cannot_backdate_documentation_knowledge():
    value = receipt(); value["knowledge_available_at"] = ARGS["retrieved_at"]
    value.update(market.content_identity(value,kind="dnse_working_dates_calendar_receipt"))
    with pytest.raises(ValueError,match="INTEGRITY"):
        gate.pit_calendar_at_cutoff([], [value],session="2026-10-02",knowledge_cutoff="2026-10-02T03:39:00Z")


def test_immutable_retention_reuses_bytes_and_preserves_source(tmp_path):
    source=tmp_path/'source.json';source.write_bytes(RAW)
    first=retain_working_dates_calendar(source.read_bytes(),root=tmp_path/'output',**ARGS)
    before=Path(first['path']).read_bytes()
    assert retain_working_dates_calendar(source.read_bytes(),root=tmp_path/'output',**ARGS) == first
    assert Path(first['path']).read_bytes() == before and source.read_bytes() == RAW


def test_documentation_hash_and_actual_time_required():
    for changed in ({"documentation_sha256":"UNKNOWN"},{"documentation_retrieved_at":"2026-10-02"}):
        with pytest.raises(ValueError):
            gate.build_working_dates_calendar_receipt(RAW,**{**ARGS,**changed})


def test_coverage_reports_forward_neighbors_without_joining_historical_gap():
    rows = [{"signal_requirements":{"signal_id":"fixture"},"state":"ELIGIBLE","ticker":"VNM",
             "session":day,"exchange":"HOSE","reason_codes":[]} for day in ("2026-09-04","2026-10-02","2026-10-05")]
    result = eligibility.contiguous_coverage(rows,calendar_sessions=["2026-09-04"],
        calendar_windows=[["2026-09-04"],receipt()["sessions"]])["fixture"]
    assert [r["sessions"] for r in result["contiguous_regions"]] == [1,2]
