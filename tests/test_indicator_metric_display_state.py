"""Focused tests for indicator_metric_display_state.py.

Includes the milestone's mandatory forbidden-technical-language gate: the presentation
projection must never render backend/pipeline/provider wording, reason codes, or raw
internal enum names (Phase 23 of the milestone brief).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import indicator_metric_availability as availability
import indicator_metric_display_state as display

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT.parent / "market-dashboard"
WORKSPACE_ARTIFACT_PATH = DASHBOARD / "data" / "investment_decision_workspace.json"
COHORT = frozenset({"EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM"})

FORBIDDEN_SUBSTRINGS = (
    "backend", "frontend", "python", "dnse", "vci", "kbs", "cohort", "shadow", "pipeline",
    "contract", "artifact", "reason_code", "raw_as_traded", "pit", "runtime", "projection",
    "blocked_by_evidence", "not_promoted",
)


def _ready_record(**overrides):
    base = {
        "contract_version": availability.CONTRACT_VERSION, "metric_id": "gross_margin", "family": "FUNDAMENTALS",
        "applicability": "APPLICABLE", "availability_state": "READY", "value_present": True, "value": 0.21,
        "as_of_session": "2026-09-18", "evidence_fitness": "READY_RESEARCH_PROXY", "blocker_class": "READY",
        "recoverability": "NOT_APPLICABLE", "requires_future_observation": False,
        "current_research_allowed": True, "historical_pit_allowed": False,
        "recovery_action_code": None, "source_identity": None,
    }
    base.update(overrides)
    return base


def test_available_state_shows_the_value_not_a_placeholder():
    record = display.to_display_state(_ready_record())
    assert record["display_state"] == "AVAILABLE"
    assert record["display_text"] is None
    assert record["value"] == 0.21


def test_insufficient_data_state_shows_vietnamese_placeholder_never_the_blocker_code():
    record = display.to_display_state(_ready_record(
        availability_state="INSUFFICIENT_DATA", value_present=False, value=None,
        blocker_class="MISSING_FINANCIAL_COMPONENT", recovery_action_code="ebitda_not_ready",
    ))
    assert record["display_state"] == "INSUFFICIENT_DATA"
    assert record["display_text"] == "Chưa đủ dữ liệu"
    assert "ebitda_not_ready" not in json.dumps(record, ensure_ascii=False)
    assert "MISSING_FINANCIAL_COMPONENT" not in json.dumps(record, ensure_ascii=False)


def test_building_history_state_text():
    record = display.to_display_state(_ready_record(availability_state="BUILDING_HISTORY", value_present=False, value=None))
    assert record["display_text"] == "Đang tích lũy chuỗi phiên"


def test_not_applicable_state_text():
    record = display.to_display_state(_ready_record(availability_state="NOT_APPLICABLE", value_present=False, value=None))
    assert record["display_text"] == "Không áp dụng"


def test_not_tracked_state_text():
    record = display.to_display_state(_ready_record(availability_state="NOT_TRACKED", value_present=False, value=None))
    assert record["display_text"] == "Chưa theo dõi"


def test_temporarily_unavailable_state_text():
    record = display.to_display_state(_ready_record(availability_state="TEMPORARILY_UNAVAILABLE", value_present=False, value=None))
    assert record["display_text"] == "Tạm chưa có dữ liệu"


def test_unrecognized_availability_state_fails_closed_to_insufficient_data():
    record = display.to_display_state(_ready_record(availability_state="SOME_FUTURE_STATE_NOT_YET_KNOWN"))
    assert record["display_state"] == "INSUFFICIENT_DATA"


def test_metric_never_disappears_project_ticker_returns_all_input_metrics():
    records = {
        "gross_margin": _ready_record(),
        "ebitda": _ready_record(metric_id="ebitda", availability_state="TEMPORARILY_UNAVAILABLE",
                                 value_present=False, value=None),
    }
    projected = display.project_ticker(records)
    assert set(projected) == {"gross_margin", "ebitda"}
    assert projected["ebitda"]["display_state"] == "TEMPORARILY_UNAVAILABLE"


def test_project_workspace_covers_every_ticker_and_market_wide():
    evaluation = {
        "as_of_session": "2026-09-18",
        "tickers": {"HPG": {"gross_margin": _ready_record()}},
        "market_wide": {"market_index_level_change": _ready_record(
            metric_id="market_index_level_change", availability_state="TEMPORARILY_UNAVAILABLE",
            value_present=False, value=None)},
    }
    projected = display.project_workspace(evaluation)
    assert "HPG" in projected["tickers"]
    assert projected["market_wide"]["market_index_level_change"]["display_state"] == "TEMPORARILY_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 10. Frontend projection contains no internal reason codes / technical language
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("availability_state", availability.AVAILABILITY_STATES)
def test_no_forbidden_technical_language_for_any_state(availability_state):
    record = display.to_display_state(_ready_record(
        availability_state=availability_state,
        value_present=(availability_state == "READY"),
        value=("some value" if availability_state == "READY" else None),
        blocker_class="PRESENTATION_TRANSPORT_GAP", recoverability="REQUIRES_AUTHORITY_DECISION",
        recovery_action_code="OWNER_DECISION_TO_ENABLE_CALCULATION_READINESS_BUNDLE_SECTION",
        source_identity="investment_decision_workspace_projection/v1:deadbeef",
        evidence_fitness="CALCULATION_READINESS_PROVIDER_REPORTED",
    ))
    rendered = json.dumps(record, ensure_ascii=False).lower()
    # keys that are always present are allowed to contain governed vocabulary
    # (e.g. "contract_version"); only check the strings actually shown to a user.
    visible_text = " ".join(str(v) for k, v in record.items() if k in ("display_text", "value"))
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in visible_text.lower(), f"leaked {forbidden!r} into display text: {visible_text!r}"


@pytest.mark.skipif(not WORKSPACE_ARTIFACT_PATH.exists(), reason="sibling market-dashboard checkout not present")
def test_real_workspace_projection_has_no_forbidden_language_in_display_text():
    artifact = json.loads(WORKSPACE_ARTIFACT_PATH.read_text(encoding="utf-8"))
    evaluation = availability.evaluate_workspace_artifact(artifact, cohort_tickers=COHORT)
    projected = display.project_workspace(evaluation)
    for ticker_records in projected["tickers"].values():
        for record in ticker_records.values():
            visible_text = " ".join(str(v) for k, v in record.items() if k in ("display_text", "value") and v is not None
                                     and isinstance(v, str))
            lowered = visible_text.lower()
            for forbidden in FORBIDDEN_SUBSTRINGS:
                assert forbidden not in lowered, f"leaked {forbidden!r} in {record['metric_id']}: {visible_text!r}"
