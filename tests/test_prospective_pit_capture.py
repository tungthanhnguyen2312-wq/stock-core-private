"""Hermetic capture acceptance: real I/O semantics with synthetic evidence only."""
import copy
import json
import math
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import completed_market_session_gate as gate
import governed_session_chain as chains
import market_only_pit_eligibility as eligibility
import prospective_market_evidence_retention as old_retention
import prospective_market_snapshot_contract as market
import prospective_pit_capture as capture
import prospective_pit_capture_retention as store

DAY = "2026-10-05"
TIME = DAY + "T12:00:00Z"


def snapshot(day=DAY, *, ticker="AAA", scale=1., **changes):
    bar = {"session": day, "retrieved_at": day + "T11:00:00Z", "provider": "DNSE", "dataset": "DNSE_OHLC_1D",
           "open": 10 * scale, "high": 12 * scale, "low": 9 * scale, "close": 11 * scale, "volume": 100,
           "price_unit": "SOURCE_PRICE_UNIT_UNDOCUMENTED", "price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_UNDOCUMENTED",
           "field_representation": {k: "DNSE_PROVIDER_NATIVE_RAW" for k in capture.OHLC},
           "transformation_identity": "identity_provider_numeric_ohlc/v1",
           "request": {"symbol": ticker, "resolution": "1D", "from": day, "to": day}}
    bar.update(changes)
    value = {"resolved_completed_session": day, "retained_snapshot_session": day, "requested_at": day + "T11:00:00Z",
             "contract_version": "p3f9_exact_session_mva_snapshot/v2", "attempted_candidate_count": 1,
             "exact_session_observed_count": 1, "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
             "unattempted_without_explicit_disposition": 0,
             "records": {ticker: {"observations": [bar], "provider_endpoint": "/price/ohlc", "request": bar["request"],
                                  "payload_hash": market.sha256_hex(market.canonical({"provider": "fixture", "bar": bar}))}}}
    digest = market.sha256_hex(market.canonical(value))
    value.update(snapshot_identity="p3f9_exact_session_snapshot:" + digest, snapshot_sha256=digest)
    return value


def receipt_for(value):
    session = value["resolved_completed_session"]
    observation = market.build_session_manifest(value, session=session)["records"][0]
    body = {"contract_version": old_retention.CONTRACT_VERSION, "receipt_id": "fixture:" + observation["snapshot_identity"].split(":")[-1],
            "series_key": {"session": session}, "observation": observation, "previous_version_identity": None}
    return capture.identified(body, "prospective_market_receipt")


def presence(day=DAY, *, ticker="AAA", known=None, exchange="HOSE", **changes):
    row = {"ticker": ticker, "exchange_or_market": exchange, "official_source": "hose_public_stock_master/v1",
           "official_source_row_identity": "retained:row:" + ticker, "official_observed_at": known or day + "T02:00:00Z"}
    row.update(changes)
    return capture.listing_presence(row, session=day, source_artifact_identity="official:fixture")


def binding(value=None, *, listed=None, previous=None, created_at=None, close=None, relation=None):
    value = value or snapshot()
    day = value["resolved_completed_session"]
    ticker = next(iter(value["records"]))
    source = value["records"][ticker]
    return capture.capture_binding(receipt_for(value), source["observations"][0], source,
        source_snapshot_identity=value["snapshot_identity"], created_at=created_at or day + "T12:00:00Z",
        capture_window_close=close or capture.capture_window(day)[1], presence=listed or presence(day, ticker=ticker), previous=previous,
        qualified_relation=relation)


def calendar(days, *, known=None):
    return gate.build_working_dates_calendar_receipt(market.canonical({"workingDates": days}),
        retrieved_at=known or days[0] + "T01:00:00Z", documentation_sha256="a" * 64,
        documentation_retrieved_at="2026-10-02T03:40:00Z")


def completed_record(day, *, known=None):
    return capture.identified({"contract_version": "prospective_capture_complete_session/v1", "session": day,
        "completion_known_at": known or day + "T12:05:00Z", "completion_gate_status": "READY", "completion_gate_identity": "gate:" + day,
        "capture_binding_identity": "binding:" + day, "listing_presence_identity": "listing:" + day,
        "market_manifest_identity": "manifest:" + day}, "prospective_capture_complete_session")


def chain(days, realized=None, *, as_of="2026-12-31T12:00:00Z", receipts=None):
    return chains.GovernedSessionChain([completed_record(d) for d in (realized if realized is not None else days)],
        calendar=chains.CalendarCoverage(receipts or [calendar(days)], cutoff=as_of), as_of=as_of,
        first_complete_capture_session=days[0])


def capture_session(root, day=DAY, *, calendar_days=None, scale=1., include_listing=True, completion_state="READY"):
    value = snapshot(day, scale=scale)
    known = day + "T12:00:00Z"
    days = calendar_days or [day]
    raw = market.canonical({"workingDates": days})
    store.retain_existing_calendar_probe({"raw_bytes": raw, "retrieved_at": days[0] + "T04:00:00Z"}, root=root)
    listings = {"contract_version": old_retention.CONTRACT_VERSION, "source_identity": "official:fixture",
        "records": [{"source_observation": {"ticker": "AAA", "exchange_or_market": "HOSE",
          "official_source": "hose_public_stock_master/v1", "official_source_row_identity": "official:AAA",
          "official_observed_at": day + "T02:00:00Z"}}] if include_listing else []}
    listings = capture.identified(listings, "prospective_universe_observations")
    path = root / "listing-source.json"
    path.write_bytes(market.canonical(listings))
    evidence = {"market": old_retention.retain_market(value, session=day, root=root),
                "universe": {"path": str(path), "artifact_identity": listings["artifact_identity"]}}
    evidence["capture"] = store.retain_capture_bindings(value, session=day, evidence=evidence, root=root, created_at=known)
    g = gate.evaluate_completed_market_session_gate(requested_at=known, requested_session=day,
        working_dates_evidence={"workingDates": days}, exact_session_evidence=value)
    assert g["completion_gate_status"] == "READY"
    if completion_state != "READY":
        g["completion_gate_status"] = completion_state
    result = store.daily_boundary(root, session=day, gate=g, evidence=evidence, known_at=day + "T12:05:00Z",
                                 t0_snapshot_identity="sealed:actual-fixture")
    return value, evidence, g, result


def test_capture_companion_additive_exact_hash_domain_and_actual_route():
    value = snapshot(provider="KBS")
    value["records"]["AAA"]["provider_endpoint"] = "KBS_QUOTE_ACTUAL_ROUTE"
    receipt = receipt_for(value)
    original = market.canonical(receipt)
    row = binding(value)
    assert row["actual_provider_route"] == "KBS_QUOTE_ACTUAL_ROUTE"
    assert row["provider_payload_hash_kind"] == "canonical_json_of_provider_native_payload"
    assert row["retained_observation_payload"]["hash_kind"] == "canonical_json_of_retained_observation"
    assert "ohlc" not in row and row["exchange"] == "HOSE" and row["board"] == "UNKNOWN"
    assert capture.effective_receipt(receipt, [row], TIME)["capture_state"] == "T0_CAPTURE_COMPLETE"
    assert market.canonical(receipt) == original and receipt["observation"]["instrument"]["exchange"] is None


def test_companion_cutoff_late_and_forged_extended_window_never_t0():
    value = snapshot()
    receipt = receipt_for(value)
    row = binding(value)
    assert capture.effective_receipt(receipt, [row], DAY + "T11:59:59Z")["capture_state"] == "INCOMPLETE_CAPTURE"
    later = binding(value, created_at="2026-10-06T12:00:00Z")
    assert capture.effective_receipt(receipt, [later], "2026-10-06T12:00:00Z")["capture_state"] == "LATE_NOT_T0_QUALIFIED"
    forged = binding(value, created_at="2026-10-06T12:00:00Z", close="2027-10-06T12:00:00Z")
    assert capture.effective_receipt(receipt, [forged], "2026-10-06T12:00:00Z")["capture_state"] == "LATE_NOT_T0_QUALIFIED"
    assert capture.effective_receipt(receipt, [later, row], "2026-10-06T12:00:00Z")["companion"] == row


def test_legacy_marker_boundary_and_missing_post_release_capture():
    old = receipt_for(snapshot("2026-10-02"))
    assert capture.effective_receipt(old, [], TIME)["capture_state"] == "LEGACY_CAPTURE_INCOMPLETE"
    current = receipt_for(snapshot())
    assert capture.effective_receipt(current, [], TIME)["capture_state"] == "INCOMPLETE_CAPTURE"
    assert capture.effective_receipt(current, [], TIME, first_complete_capture_session="2026-10-06")["capture_state"] == "LEGACY_CAPTURE_INCOMPLETE"
    assert capture.effective_receipt(old, [binding(snapshot("2026-10-02"))], TIME)["companion"] is None


@pytest.mark.parametrize("field", ["ticker", "session", "snapshot_identity", "receipt_id"])
def test_rehashed_wrong_companion_scope_refused(field):
    row = binding()
    row[field] = "wrong"
    row = capture.identified(row, capture.CAPTURE_CONTRACT)
    with pytest.raises(ValueError, match="SCOPE_MISMATCH"):
        capture.effective_receipt(receipt_for(snapshot()), [row], TIME)


@pytest.mark.parametrize("known,claim", [("2026-10-02T02:00:00Z", "PRIOR_CONTEXT_ONLY"),
    ("2026-10-06T02:00:00Z", "LATER_NOT_BACKFILL"), (None, "UNKNOWN")])
def test_prior_later_unknown_listing_not_same_session(known, claim):
    row = presence(known=known, official_observed_at=known)
    assert row["membership_claim"] == "UNKNOWN" and row["binding_class"] == claim
    assert not capture.qualifying_presence(row, ticker="AAA", session=DAY, cutoff="2026-10-10T12:00:00Z")
    companion = binding(listed=row)
    assert companion["exchange"] == "UNKNOWN"


def test_listing_status_code_and_normalized_active_never_effective_membership():
    row = capture.listing_presence({"ticker": "AAA", "exchange_or_market": "HOSE", "official_source": "hose_public_stock_master/v1",
        "official_source_row_identity": "official:row", "official_observed_at": DAY + "T02:00:00Z", "listingStatusId": 11,
        "official_security_status": "ACTIVE"}, session=DAY, source_artifact_identity="source:fixture")
    assert row["membership_claim"] == "LISTED_PRESENT_AT_SESSION" and row["raw_status_code"] == 11
    assert row["status_semantic_qualification"] == "UNQUALIFIED_FOR_ACTIVE"
    assert not capture.qualifying_presence(row, ticker="BBB", session=DAY, cutoff=TIME)


@pytest.mark.parametrize("change", [{"field_representation": {"open": "x"}}, {"transformation_identity": None},
    {"field_representation": {**{k: "x" for k in capture.OHLC}, "close": "y"}}, {"close": 500}, {"price_unit": "VND"}])
def test_scale_semantics_never_invent_unit_or_accept_mixed_geometry(change):
    row = binding(snapshot(**change))
    assert row["representation_tier"] == (capture.NATIVE if change == {"price_unit": "VND"} else capture.UNKNOWN)
    assert row["economic_unit_evidence"] is None


@pytest.mark.parametrize("scale", [0.001, 0.2, 3., 1000., 100000.])
def test_positive_scale_metamorphic_invariant_calculations(scale):
    bars = [{"open": 10 + i, "high": 12 + i, "low": 9 + i, "close": 11 + i} for i in range(20)]
    def compute(rows):
        close = [r["close"] for r in rows]
        sma = sum(close) / len(close)
        atr = sum(max(r["high"] - r["low"], abs(r["high"] - rows[i-1]["close"]), abs(r["low"] - rows[i-1]["close"])) for i,r in enumerate(rows[1:], 1)) / (len(rows)-1)
        return (close[-1]/close[0]-1, math.log(close[-1]/close[0]), close[-1]/sma, close[-1] > sma,
                close[-1] > max(close[:-1]), (close[-1]-sma)/sma, atr/close[-1], rows[-1]["high"] > rows[-2]["high"])
    scaled = [{k: v * scale for k,v in r.items()} for r in bars]
    assert compute(scaled) == pytest.approx(compute(bars))
    assert binding(snapshot(scale=scale))["representation_tier"] == capture.NATIVE
    for calculation, behavior in capture.CALCULATION_SCALE_BEHAVIOR.items():
        assert capture.calculation_allowed(calculation, capture.NATIVE, same_series=True) == (behavior == "INVARIANT")
        assert not capture.calculation_allowed(calculation, capture.NATIVE, same_series=False)


@pytest.mark.parametrize("ratio,expected", [(2., capture.NATIVE), (2.00001, capture.UNKNOWN), (.5, capture.NATIVE), (.49999, capture.UNKNOWN)])
def test_k_integrity_tripwire_both_directions(ratio, expected):
    prior = binding(snapshot())
    current = binding(snapshot("2026-10-06", scale=ratio), previous=prior)
    assert current["representation_tier"] == expected
    if expected == capture.UNKNOWN:
        assert "UNEXPLAINED_SCALE_DISCONTINUITY_GT_K" in current["representation_reason_codes"]


@pytest.mark.parametrize("change", [{"transformation_identity": "new_transform"}, {"request": {"symbol": "AAA", "resolution": "1W"}}, {"provider": "KBS"}])
def test_same_series_fingerprint_cannot_silently_change(change):
    current = binding(snapshot("2026-10-06", **change), previous=binding())
    assert current["representation_tier"] == capture.UNKNOWN


def official(value=None, **changes):
    value = value or snapshot()
    row = {"provider": "HOSE", "source_id": "HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT", "ticker": "AAA", "session": DAY,
           "exact_row": {"symbol": "AAA", "native": "exact fixture"}, "row_identity": "official:row",
           "source_artifact_identity": "official:body", "source_artifact_sha256": "b" * 64,
           "official_known_at": "2026-10-06T10:00:00Z", "ohlc": {k: value["records"]["AAA"]["observations"][0][k] for k in capture.OHLC}}
    row.update(changes)
    return row


def test_official_later_knowledge_and_mismatch_retained_without_t0_change():
    value = snapshot(); receipt = receipt_for(value); row = binding(value)
    before = market.canonical(receipt)
    verified = capture.official_verification(row, receipt["observation"], official(), verification_known_at="2026-10-06T11:00:00Z")
    assert verified["state"] == "VERIFIED_MATCH" and verified["official_known_at"] > TIME
    mismatch = capture.official_verification(row, receipt["observation"], official(ohlc={"open": 10, "high": 50, "low": 9, "close": 11}),
                                             verification_known_at="2026-10-07T11:00:00Z")
    effective = capture.effective_receipt(receipt, [row], TIME)
    assert capture.raw_use_state(effective, [verified, mismatch], cutoff=TIME)["official_match_status"] == "PENDING_VERIFICATION"
    assert capture.raw_use_state(effective, [verified, mismatch], cutoff="2026-10-08T11:00:00Z")["official_match_status"] == "VERIFIED_MISMATCH"
    assert mismatch["mismatch_reason"] and market.canonical(receipt) == before
    assert verified["unit_semantics"]["economic_unit_qualified"] is False


@pytest.mark.parametrize("change,state", [(None, "PENDING_VERIFICATION"), ({"ticker": "BBB"}, "NOT_VERIFIABLE"),
    ({"ohlc": {"open": 10000, "high": 12000, "low": 9000, "close": 11000}}, "NOT_VERIFIABLE")])
def test_official_absent_wrong_scope_or_unqualified_ratio(change, state):
    row = capture.official_verification(binding(), receipt_for(snapshot())["observation"], official(**change) if change else None,
        verification_known_at="2026-10-07T11:00:00Z")
    assert row["state"] == state


def test_calendar_overlapping_forward_windows_keep_prior_depth_and_record_revision():
    first = calendar([DAY, "2026-10-06", "2026-10-07", "2026-10-08"])
    later = calendar(["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"])
    receipts = [first, later]
    coverage = chains.CalendarCoverage(receipts, cutoff="2026-10-09T12:00:00Z")
    assert coverage.window_ending("2026-10-09", 5) == [DAY, "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
    assert gate.pit_calendar_at_cutoff([], receipts, session="2026-10-09", knowledge_cutoff="2026-10-09T12:00:00Z") == coverage.components[0]["sessions"]
    changed = calendar(["2026-10-06", "2026-10-08", "2026-10-09"])
    revised = chains.CalendarCoverage([first, changed], cutoff="2026-10-09T12:00:00Z")
    assert revised.conflicts[0]["sessions"] == ["2026-10-07"]
    assert revised.window_ending("2026-10-09", 5) == ["2026-10-08", "2026-10-09"]
    assert not revised.connected(DAY, "2026-10-09")


def test_calendar_disjoint_gap_and_future_receipt_never_stitched():
    receipts = [calendar([DAY, "2026-10-06"]), calendar(["2026-10-09", "2026-10-12"])]
    coverage = chains.CalendarCoverage(receipts, cutoff="2026-10-12T12:00:00Z", base_sessions=["2026-09-03", "2026-09-04"])
    assert coverage.window_ending("2026-10-12", 20) == ["2026-10-09", "2026-10-12"]
    assert not coverage.supported("2026-09-30") and not coverage.connected("2026-09-04", DAY)
    assert chains.CalendarCoverage(receipts, cutoff=TIME).window_ending("2026-10-12", 20) == []


def test_chain_missed_session_and_projection_never_completed_evidence():
    days = [DAY, "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
    actual = chain(days, [DAY, "2026-10-07", "2026-10-08"])
    assert actual.window_ending("2026-10-08", 5) == ["2026-10-07", "2026-10-08"]
    assert actual.next_n_sessions(DAY, 3)["state"] == "MISSED_CAPTURE"
    assert actual.realized_prefix_after(DAY, 3) == []
    assert actual.gaps()[0]["sessions"] == ["2026-10-06"]
    current = chain(days, [DAY], as_of=DAY + "T12:05:00Z")
    projected = current.next_n_sessions(DAY, 3)
    assert projected["state"] == "PROJECTED_ONLY" and projected["realized_sessions"] == []
    assert projected["projection_is_evidence"] is False


def test_shared_feedback_chain_missing_session_cannot_mature_returns():
    import integrated_decision_prospective_feedback as forward
    days = [DAY, "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"]
    actual = chain(days, [d for d in days if d != "2026-10-06"])
    observations = {d: {"close": 11, "price_basis": "native"} for d in days}
    future = forward._forward_horizon(as_of_session=DAY, horizon_sessions=5, chain=actual, observations=observations)
    legacy = forward._forward_horizon(as_of_session=DAY, horizon_sessions=5, chain=list(actual), observations=observations)
    assert future["status"] == "MISSED_CAPTURE" and future["return"] is None
    assert legacy["status"] == "MATURE"  # Explicitly preserved prior semantics.


def test_daily_marker_written_once_complete_record_not_manifest(tmp_path):
    _, evidence, g, result = capture_session(tmp_path, calendar_days=[DAY, "2026-10-06"])
    assert result["session_capture"]["status"] == "RETAINED"
    marker_path = tmp_path / store.STORE / "first_complete_capture_session.json"
    original = marker_path.read_bytes()
    assert store.load_marker(tmp_path)["session"] == DAY
    _, _, _, next_result = capture_session(tmp_path, "2026-10-06", calendar_days=[DAY, "2026-10-06"])
    assert next_result["readiness"]["complete_session_count"] == 2 and marker_path.read_bytes() == original
    repeat = store.daily_boundary(tmp_path, session=DAY, gate=g, evidence=evidence, known_at="2026-10-06T13:00:00Z")
    assert repeat["session_capture"]["status"] == "ALREADY_CAPTURED"
    assert repeat["readiness"]["complete_session_count"] == 2


@pytest.mark.parametrize("include_listing,state", [(False, "READY"), (True, "TOO_EARLY")])
def test_incomplete_capture_never_creates_marker(tmp_path, include_listing, state):
    _, _, _, result = capture_session(tmp_path, include_listing=include_listing, completion_state=state)
    assert result["session_capture"]["status"] == "INCOMPLETE_CAPTURE" and store.load_marker(tmp_path) is None
    assert result["readiness"]["complete_session_count"] == 0


def test_no_probe_no_calendar_receipt_and_exact_raw_bytes_retained(tmp_path):
    assert store.retain_existing_calendar_probe({"workingDates": [DAY]}, root=tmp_path)["status"] == "NOT_CAPTURED"
    assert store.load_calendars(tmp_path) == []
    raw = b'{ "workingDates" : ["2026-10-05", "2026-10-06"] }'
    result = store.retain_existing_calendar_probe({"raw_bytes": raw, "retrieved_at": DAY + "T04:00:00Z"}, root=tmp_path)
    receipt = json.loads(Path(result["path"]).read_bytes())
    path = tmp_path / "operations-review/prospective-calendar-evidence-v1/raw" / receipt["payload_sha256"]
    assert path.read_bytes() == raw and receipt["knowledge_available_at"] == DAY + "T04:00:00+00:00"


def test_readiness_reproducible_without_promotion_and_exact_registered_horizon(tmp_path):
    capture_session(tmp_path, calendar_days=[DAY, "2026-10-06"])
    index = store.CaptureIndex(tmp_path, cutoff=DAY + "T12:05:00Z")
    first = index.readiness(session=DAY)
    assert index.readiness(session=DAY) == first
    assert first["status"] == "DEPTH_PENDING" and first["complete_session_count"] == 1
    assert first["per_ticker"]["AAA"]["contiguous_capture_depth"] == 1
    assert all(v == 0 for v in first["counts_at_depth"].values())
    assert first["calendar"]["max_registered_horizon"] == max(chains.registered_outcome_horizons()) == 60
    assert first["calendar"]["refresh_state"] == "CALENDAR_REFRESH_NEEDED"
    assert not first["evaluation_authorized"] and first["new_signals_declared"] == 0
    assert first["performance"]["scans"]["latest_receipts"] == 1
    assert first["future_ca_seam"]["status"] == "INTEGRATION_SEAM_ONLY"


def test_positive_membership_every_session_invariant_gate_and_standing_signal_unchanged():
    days = [DAY, "2026-10-06"]
    values = [snapshot(d) for d in days]
    receipts = [receipt_for(v) for v in values]
    bindings = [binding(v) for v in values]
    listings = [presence(d) for d in days]
    requirements = eligibility.SignalRequirements("HERMETIC_REQUIREMENT_NOT_A_DECLARED_SIGNAL", 2,
        price_mode=eligibility.OBSERVED_SCALE_INVARIANT, comparable_ca_required=False, membership_claim="LISTED_PRESENT",
        membership_mode="POSITIVE_PRESENCE_EVERY_SESSION", scale_behavior="INVARIANT", calculation_id="single_bar_wick_ratio")
    index = eligibility.CaptureEligibilityIndex(receipts, bindings, listings)
    args = dict(requirements=requirements, ticker="AAA", session=days[-1], knowledge_cutoff=days[-1]+"T13:00:00Z",
        market_versions=[], calendar_sessions=days, governed_chain=chain(days), capture_receipts=index)
    assert eligibility.evaluate(**args)["state"] == "ELIGIBLE"
    args["requirements"] = replace(requirements, calculation_id="close_above_sma")
    assert "CA_FACTOR_REQUIRED_UNAVAILABLE" in eligibility.evaluate(**args)["reason_codes"]
    args["requirements"] = requirements
    args["capture_receipts"] = eligibility.CaptureEligibilityIndex(receipts, bindings, listings[:1])
    assert "LISTED_PRESENCE_WINDOW_INCOMPLETE" in eligibility.evaluate(**args)["reason_codes"]
    args["requirements"] = replace(requirements, comparable_ca_required=True)
    assert "CA_FACTOR_REQUIRED_UNAVAILABLE" in eligibility.evaluate(**args)["reason_codes"]
    standing = eligibility.requirements_payload(eligibility.existing_vnm_requirements())
    assert standing["lookback_sessions"] == 50 and standing["ticker_scope"] == ("VNM",)
    assert "membership_mode" not in standing and "scale_behavior" not in standing


def test_offline_actual_capture_boundary_network_zero_and_old_bytes_unchanged(tmp_path):
    from test_production_call_shape_smoke import _offline_smoke_guard
    value = snapshot("2026-10-02")
    retained = old_retention.retain_market(value, session="2026-10-02", root=tmp_path)
    before = {p: p.read_bytes() for p in Path(retained["path"]).parent.parent.glob("*/*.json")}
    t0 = tmp_path / "historical-t0.json"
    t0.write_bytes(b'{"immutable":"original T0"}')
    with _offline_smoke_guard() as counters:
        capture_session(tmp_path, calendar_days=[DAY, "2026-10-06"])
        index = store.CaptureIndex(tmp_path, cutoff=DAY + "T12:05:00Z")
        assert index.readiness(session=DAY)["legacy_incomplete_receipt_versions"] == 1
    assert all(v == 0 for v in counters.values())
    assert all(p.read_bytes() == original for p,original in before.items())
    assert t0.read_bytes() == b'{"immutable":"original T0"}'


def test_documented_economic_unit_requires_exact_scoped_known_at_evidence():
    documentation = {"status": "QUALIFIED", "source_identity": "retained:unit-doc", "provider": "DNSE", "route": "/price/ohlc",
                     "fields": list(capture.OHLC), "unit": "VND", "known_at": DAY + "T02:00:00Z"}
    assert binding(snapshot(price_unit="VND", price_unit_documentation=documentation))["representation_tier"] == capture.ECONOMIC
    for change in ({"provider": "OTHER"}, {"route": "wrong"}, {"known_at": "2026-10-06T02:00:00Z"}, {"source_identity": None}):
        assert binding(snapshot(price_unit="VND", price_unit_documentation={**documentation, **change}))["representation_tier"] == capture.NATIVE


def test_k_qualified_factor_explanation_is_scoped_and_cannot_excuse_arbitrary_jump():
    prior = binding()
    value = snapshot("2026-10-06", scale=10)
    bar = value["records"]["AAA"]["observations"][0]
    descriptor = capture.representation(bar, provider="DNSE", route="/price/ohlc", request=bar["request"])
    relation = {"status": "QUALIFIED", "factor_chain_identity": "official:qualified-factor", "official_execution_status": "EXECUTED",
                "ex_date_status": "EXPLICIT_OFFICIAL", "ex_date": "2026-10-06", "previous_binding_identity": prior["artifact_identity"],
                "current_fingerprint": descriptor["representation_fingerprint"], "knowledge_cutoff": "2026-10-06T02:00:00Z", "adjustment_factor": 10.}
    assert binding(value, previous=prior, relation=relation)["representation_tier"] == capture.NATIVE
    for change in ({"adjustment_factor": 1.}, {"previous_binding_identity": "other"}, {"knowledge_cutoff": "2026-10-07T02:00:00Z"},
                   {"official_execution_status": "PLANNED"}):
        assert binding(value, previous=prior, relation={**relation, **change})["representation_tier"] == capture.UNKNOWN


def test_raw_dimensions_morphology_lower_than_continuous_returns():
    receipt = receipt_for(snapshot())
    effective = capture.effective_receipt(receipt, [binding()], TIME)
    raw = capture.raw_use_state(effective, cutoff=TIME)
    assert raw["source_basis_claim"] == market.SOURCE_BASIS_UNDOCUMENTED
    assert "SAME_BAR_SCALE_INVARIANT_MORPHOLOGY" in raw["allowed_uses"]
    assert "SAME_SERIES_SCALE_INVARIANT_CONTINUOUS_TRANSFORMS" not in raw["allowed_uses"]
    qualified = capture.raw_use_state(effective, cutoff=TIME, ca_comparability="QUALIFIED_COMPARABLE")
    assert "SAME_SERIES_SCALE_INVARIANT_CONTINUOUS_TRANSFORMS" in qualified["allowed_uses"]
    assert raw["global_raw_authority"] == qualified["global_raw_authority"] == "NOT_PROMOTED"


def test_exact_official_ledger_uses_native_rows_no_scale_guess_and_retains_mismatch(tmp_path):
    _, evidence, _, _ = capture_session(tmp_path)
    official_row = {"symbol": "AAA", "reportDate": int(datetime(2026, 10, 5, tzinfo=timezone.utc).timestamp() * 1000),
                    "openPrice": 10, "highPrice": 50, "lowPrice": 9, "closePrice": 11}
    # Current retained operator ledgers use seconds (preserve their contract).
    official_row["reportDate"] //= 1000
    raw = market.canonical({"data": {"list": [official_row]}})
    digest = market.sha256_hex(raw)
    directory = tmp_path / "operator"
    (directory / "raw").mkdir(parents=True)
    (directory / "raw" / (digest + ".bin")).write_bytes(raw)
    ledger = directory / "ledger.jsonl"
    entry = {"outcome": "OK", "sha256": digest, "retrieved_at": "2026-10-06T10:00:00Z",
             "request": {"url": "https://api.hsx.vn/mk/api/v1/market/securities/tradingresult"}}
    ledger.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    result = store.retain_verifications(tmp_path, session=DAY, capture_ref=evidence["capture"]["capture_binding"],
        verification_known_at="2026-10-06T11:00:00Z", ledger_paths=[ledger])
    retained = json.loads(Path(result["path"]).read_bytes())
    assert retained["records"][0]["state"] == "VERIFIED_MISMATCH"
    assert retained["records"][0]["exact_official_row"] == official_row
    assert store.CaptureIndex(tmp_path, cutoff="2026-10-06T12:00:00Z").readiness(session=DAY)["retained_mismatch_receipts"] == 1
    (directory / "raw" / (digest + ".bin")).write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="BODY_HASH_MISMATCH"):
        store.retained_official_rows([ledger])


def test_actual_existing_probe_once_and_true_response_time(tmp_path, monkeypatch):
    import canonical_daily_operation as daily
    import dnse_access
    import dnse_bulk_market_data
    import dnse_secrets_env
    from test_production_call_shape_smoke import _offline_smoke_guard
    raw = b'{ "workingDates" : ["2026-10-05", "2026-10-06"] }'
    calls = []
    monkeypatch.setattr(dnse_secrets_env, "ensure_credentials_loaded", lambda: None)
    monkeypatch.setattr(dnse_access, "credential_status", lambda: {"configured": True})
    monkeypatch.setattr(dnse_access, "credentials_for_request", lambda: ("fixture", "fixture"))
    monkeypatch.setattr(store, "io_known_at", lambda: DAY + "T04:00:00Z")
    def fetch(capability, **kwargs):
        assert capability == "working_dates" and kwargs["retain_raw_bytes"] is True and kwargs["query"] == {}
        calls.append(capability)
        return {"ok": True, "raw_bytes": raw}
    monkeypatch.setattr(dnse_bulk_market_data, "fetch_capability_raw", fetch)
    with _offline_smoke_guard() as counters:
        evidence = daily._working_dates_probe()
        retained = store.retain_existing_calendar_probe(evidence, root=tmp_path)
    assert evidence["raw_bytes"] == raw and evidence["retrieved_at"] == DAY + "T04:00:00Z"
    assert calls == ["working_dates"] and retained["status"] == "RETAINED"
    assert all(v == 0 for v in counters.values())


def test_normal_daily_boundary_publishes_once_after_phase_b_and_preserves_sealed_record(tmp_path, monkeypatch):
    import canonical_daily_operation as daily
    from test_canonical_daily_operation import _run, _acquired
    from test_production_call_shape_smoke import _offline_smoke_guard
    monkeypatch.setattr(store, "io_known_at", lambda: DAY + "T12:05:00Z")
    monkeypatch.setattr(daily, "evaluate_dashboard_runtime_readiness", lambda *_a, **_k: {"ready": True, "resolved_session": DAY})
    raw = market.canonical({"workingDates": [DAY, "2026-10-06"]})
    value = snapshot()
    listing = capture.identified({"contract_version": old_retention.CONTRACT_VERSION, "source_identity": "official:test",
        "records": [{"source_observation": {"ticker": "AAA", "exchange_or_market": "HOSE", "official_source": "hose_public_stock_master/v1",
          "official_source_row_identity": "row:AAA", "official_observed_at": DAY + "T02:00:00Z"}}]}, "prospective_universe_observations")
    path = tmp_path / "listing.json"
    path.write_bytes(market.canonical(listing))
    def acquire(*_args, **_kwargs):
        result = _acquired(tmp_path, DAY)
        result["snapshot"] = value
        evidence = {"market": old_retention.retain_market(value, session=DAY, root=tmp_path),
                    "universe": {"path": str(path), "artifact_identity": listing["artifact_identity"]}}
        evidence["capture"] = store.retain_capture_bindings(value, session=DAY, evidence=evidence, root=tmp_path, created_at=DAY + "T12:00:00Z")
        result["prospective_market_evidence"] = evidence
        return result
    with _offline_smoke_guard() as counters:
        result = _run(tmp_path, monkeypatch, session=DAY, now=datetime.fromisoformat(DAY + "T19:00:00+07:00"), acquire_fn=acquire,
                      working={"body": json.loads(raw), "raw_bytes": raw, "retrieved_at": DAY + "T04:00:00Z"})
    assert result["phase_b"]["status"] == "READY"
    assert result["prospective_pit_capture_readiness"]["readiness"]["complete_session_count"] == 1
    assert store.load_marker(tmp_path)["session"] == DAY and result["_calls"]["acquire"] == 1
    persisted = json.loads((Path(result["operation_directory"]) / "daily_operation_record.json").read_bytes())
    assert "prospective_pit_capture_readiness" not in persisted
    assert all(v == 0 for v in counters.values())


def test_capture_gate_tampering_and_late_completion_refused(tmp_path):
    _, evidence, g, _ = capture_session(tmp_path, completion_state="TOO_EARLY")
    g["completion_gate_status"] = "READY"
    g["gate_identity"] = "gate:invented"
    with pytest.raises(ValueError, match="GATE_IDENTITY"):
        store.complete_capture_session(tmp_path, session=DAY, gate=g, evidence=evidence, completion_known_at=TIME)


def test_version_index_equivalent_and_legacy_outcomes_unchanged_before_marker():
    from test_market_only_pit_eligibility import inputs
    args = inputs()
    before = eligibility.evaluate(**args)
    args["market_versions"] = eligibility.MarketVersionIndex(args["market_versions"])
    assert eligibility.evaluate(**args) == before
    from test_prospective_decision_outcome_measurement import _case, _sessions
    from prospective_decision_outcome_measurement import evaluate_case
    sessions = _sessions()
    old = evaluate_case(_case(), sessions)
    assert evaluate_case(_case(), sessions, governed_chain=chain([DAY, "2026-10-06"])) == old


def test_future_outcome_measurement_and_learning_use_same_strict_prefix():
    from test_prospective_decision_outcome_measurement import _case, _t0
    from prospective_decision_outcome_measurement import evaluate_case
    days = [DAY, "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"]
    actual = chain(days, [d for d in days if d != "2026-10-06"])
    t0 = _t0(); t0["completed_session"] = DAY
    sessions = [{"session": d, "completed_session_gate": {"completion_gate_status": "READY"},
                 "prices": {"AAA": {"close": 100., "price_basis_identity": "basis:adjusted-research"}}} for d in list(actual)[1:]]
    assert evaluate_case(_case(t0=t0), sessions, governed_chain=actual)["horizons"]["T5"]["status"] != "MATURE"
    assert actual.realized_prefix_after(DAY, 5) == []
    from prospective_daily_rollforward import build_learning_ledger, _with_identity
    attribution = _with_identity({"precondition": {"t_session": DAY, "future_session": "2026-10-07"}, "outcomes": []},
                                 "first_real_prospective_attribution:", "artifact_identity")
    snapshots = [{"research_session": DAY, "snapshot_identity": "synthetic:t0", "cohort": {"members": ["AAA"]}}]
    learning = build_learning_ledger(snapshots, attribution, list(actual), governed_chain=actual)
    assert all(h["resolved_future_session"] is None for h in learning["rows"][0]["horizons"].values())
    legacy = build_learning_ledger(snapshots, attribution, list(actual))
    assert legacy["rows"][0]["horizons"]["H1"]["status"] == "OBSERVED"


def test_not_captured_readiness_has_no_fabricated_marker(tmp_path):
    result = store.CaptureIndex(tmp_path, cutoff=TIME).readiness(session=DAY)
    assert result["status"] == "NOT_CAPTURED" and result["first_complete_capture_session"] is None
    assert result["per_ticker"] == {} and result["complete_session_count"] == 0
