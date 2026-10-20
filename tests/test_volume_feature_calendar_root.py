"""Volume V2 must hash weekly bars with the calendar that sealed the features."""
from __future__ import annotations

import hashlib
from pathlib import Path

import prospective_market_snapshot_contract as market
import volume_and_flow_retained_v2 as adapter
from prospective_pit_capture_retention import calendar_evidence_at_cutoff
from stocklookup_core.evidence.evidence_roots import (
    OPERATION_OUTPUT_ROOT_ENV,
    RETAINED_EVIDENCE_ROOT_ENV,
)
from tools.register_working_dates_receipt import register

STATIC = Path(__file__).resolve().parents[1] / "config" / "governed_trading_session_calendar_v1.json"
CUTOFF = "2026-10-20T16:01:37+07:00"


def _producer(tmp_path):
    producer = tmp_path / "producer"
    (producer / "config").mkdir(parents=True)
    (producer / "config" / STATIC.name).write_bytes(STATIC.read_bytes())
    return producer


def _feature(root, name):
    path = root / "operations-review" / "canonical-post-close-v1" / "2026-10-20" / "enrichment" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def _retain_later_receipt(destination):
    raw = market.canonical({"workingDates": ["2026-10-02", "2026-10-05"]})
    source = destination.parent / "working-dates.json"
    source.write_bytes(raw)
    register(source, source_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at="2026-10-02T03:40:00Z",
             documentation_sha256="a" * 64, documentation_known_at="2026-10-02T03:00:00Z",
             destination_root=destination)


def test_sealed_feature_outside_the_checkout_uses_that_evidence_calendar(tmp_path, monkeypatch):
    producer = _producer(tmp_path)
    # Shorter sibling than "producer", matching the production checkout/evidence layout.
    retained = tmp_path / "ev"
    retained.mkdir()
    _retain_later_receipt(retained)
    monkeypatch.setenv(RETAINED_EVIDENCE_ROOT_ENV, str(retained))
    monkeypatch.setenv(OPERATION_OUTPUT_ROOT_ENV, str(retained))
    feature = _feature(retained, "historical_context.json")
    aligned = adapter.calendar_for_sealed_features(producer, feature, CUTOFF)
    retained_calendar = calendar_evidence_at_cutoff(retained, cutoff=CUTOFF, static_path=producer / "config" / STATIC.name)
    checkout_calendar = calendar_evidence_at_cutoff(producer, cutoff=CUTOFF)
    assert aligned["artifact_identity"] == retained_calendar["artifact_identity"]
    assert aligned["artifact_identity"] != checkout_calendar["artifact_identity"]
    assert set(retained_calendar["sessions"]) - set(checkout_calendar["sessions"]) == {"2026-10-02", "2026-10-05"}


def test_feature_batch_inside_the_producer_keeps_the_producer_calendar(tmp_path, monkeypatch):
    producer = _producer(tmp_path)
    retained = tmp_path / "retained"
    retained.mkdir()
    _retain_later_receipt(retained)
    monkeypatch.setenv(RETAINED_EVIDENCE_ROOT_ENV, str(retained))
    monkeypatch.setenv(OPERATION_OUTPUT_ROOT_ENV, str(retained))
    feature = _feature(producer, "feature-batch.jsonl")
    local = adapter.calendar_for_sealed_features(producer, feature, CUTOFF)
    checkout_calendar = calendar_evidence_at_cutoff(producer, cutoff=CUTOFF, static_path=producer / "config" / STATIC.name)
    assert local["artifact_identity"] == checkout_calendar["artifact_identity"]
