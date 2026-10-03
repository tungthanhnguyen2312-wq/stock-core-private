"""Pure additive capture, representation and later verification contracts.

No acquisition, clock, price normalization, signal declaration or authority
promotion. Existing receipts/snapshots are only referenced, never enriched in place.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

import prospective_market_snapshot_contract as market

CAPTURE_CONTRACT = "prospective_market_capture_binding/v1"
LISTING_CONTRACT = "prospective_listing_presence/v1"
VERIFICATION_CONTRACT = "prospective_market_official_verification/v1"
CAPTURE_START_NOT_BEFORE = "2026-10-03"  # Release boundary; never a fabricated first-capture marker.
ECONOMIC = "ECONOMIC_UNIT_DOCUMENTED"
NATIVE = "SOURCE_NATIVE_SCALE_CONSISTENT"
UNKNOWN = "UNKNOWN_OR_INCONSISTENT"
K = 2.0
OHLC = ("open", "high", "low", "close")
LISTING_SOURCES = {"hnx_official_equity_universe/v1", "hose_public_stock_master/v1"}
SCALE_BEHAVIORS = {"INVARIANT", "COVARIANT_1", "NOT_SCALE_SAFE"}
# Calculation contracts only. This is NOT a registry of trading signals.
CALCULATION_SCALE_BEHAVIOR = {
    "single_bar_wick_ratio": "INVARIANT", "bar_range_over_close": "INVARIANT",
    "percentage_return": "INVARIANT", "log_return": "INVARIANT", "close_over_sma": "INVARIANT",
    "close_above_sma": "INVARIANT", "breakout_comparison": "INVARIANT", "normalized_distance": "INVARIANT",
    "atr_over_close": "INVARIANT", "hh_hl_lh_ll_comparison": "INVARIANT",
    "absolute_sma": "COVARIANT_1", "absolute_atr": "COVARIANT_1",
    "price_times_volume": "NOT_SCALE_SAFE", "vnd_threshold": "NOT_SCALE_SAFE",
    "transaction_cost": "NOT_SCALE_SAFE", "cross_provider_absolute_price": "NOT_SCALE_SAFE",
    "liquidity_execution": "NOT_SCALE_SAFE",
}
CONTINUOUS_CALCULATIONS = frozenset(CALCULATION_SCALE_BEHAVIOR) - {
    "single_bar_wick_ratio", "bar_range_over_close", "absolute_sma", "absolute_atr",
    "price_times_volume", "vnd_threshold", "transaction_cost", "cross_provider_absolute_price", "liquidity_execution"}


def identified(body, kind):
    result = dict(body)
    result.update(market.content_identity(result, kind=kind))
    return result


def verify(value, kind):
    expected = market.content_identity(value, kind=kind)
    if any(value.get(k) != v for k, v in expected.items()):
        raise ValueError("CAPTURE_ARTIFACT_INTEGRITY_INVALID:" + kind)
    return value


def batch(contract, rows, *, session, created_at, **bindings):
    market._utc(created_at, "created_at")
    body = {"contract_version": contract, "session": session, "created_at": created_at,
            "records": sorted(rows, key=lambda r: (r.get("ticker", ""), r.get("receipt_id", ""), r["artifact_identity"])),
            "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY", **bindings}
    market._reject_secrets(body)
    return identified(body, contract + ":batch")


def capture_window(session, *, next_session=None):
    start = datetime.fromisoformat(session + "T15:00:00").replace(tzinfo=market.VN_TZ)
    end = (datetime.fromisoformat(next_session + "T09:00:00").replace(tzinfo=market.VN_TZ) if next_session else
           datetime.fromisoformat(session + "T09:00:00").replace(tzinfo=market.VN_TZ) + timedelta(days=1))
    if end <= start:
        raise ValueError("INVALID_CAPTURE_WINDOW")
    return start.isoformat(), end.isoformat()


def listing_presence(row, *, session, source_artifact_identity, source_row=None):
    known = row.get("official_observed_at") or row.get("knowledge_available_at")
    ticker = row.get("ticker")
    source = row.get("official_source")
    row_id = row.get("official_source_row_identity")
    exchange = row.get("exchange_or_market")
    proper = bool(ticker and source in LISTING_SOURCES and row_id and source_artifact_identity and
                  exchange in {"HOSE", "HNX", "UPCOM"} and known)
    same_session = False
    if known:
        same_session = market._utc(known, "listing_known_at").astimezone(market.VN_TZ).date().isoformat() == session
    raw = dict(source_row or row)
    raw_status = raw.get("listing_status_id", raw.get("listingStatusId", raw.get("status_code")))
    # Normalized NORMAL/ACTIVE labels are insufficient: this release has no
    # qualified official ACTIVE vocabulary. No effective interval is inferred.
    body = {"contract_version": LISTING_CONTRACT, "session": session, "ticker": ticker,
            "exchange": exchange or "UNKNOWN", "board": raw.get("board") or "UNKNOWN",
            "source": source or "UNKNOWN", "source_artifact_identity": source_artifact_identity,
            "row_identity": row_id, "exact_row_sha256": market.sha256_hex(market.canonical(raw)),
            "known_at": known, "raw_status_code": raw_status,
            "status_semantic_qualification": "UNQUALIFIED_FOR_ACTIVE",
            "membership_claim": "LISTED_PRESENT_AT_SESSION" if proper and same_session else "UNKNOWN",
            "binding_class": "SAME_SESSION_POSITIVE" if proper and same_session else
                             "PRIOR_CONTEXT_ONLY" if known and market._utc(known, "known").astimezone(market.VN_TZ).date().isoformat() < session else
                             "LATER_NOT_BACKFILL" if known else "UNKNOWN"}
    return identified(body, LISTING_CONTRACT)


def qualifying_presence(row, *, ticker, session, cutoff):
    try:
        verify(row, LISTING_CONTRACT)
        return (row.get("contract_version") == LISTING_CONTRACT and row.get("ticker") == ticker and row.get("session") == session and
                row.get("membership_claim") == "LISTED_PRESENT_AT_SESSION" and row.get("binding_class") == "SAME_SESSION_POSITIVE" and
                row.get("source") in LISTING_SOURCES and row.get("row_identity") and row.get("source_artifact_identity") and
                row.get("exchange") in {"HOSE", "HNX", "UPCOM"} and
                market._utc(row.get("known_at"), "known_at") <= market._utc(cutoff, "cutoff") and
                market._utc(row["known_at"], "known_at").astimezone(market.VN_TZ).date().isoformat() == session)
    except (ValueError, TypeError):
        return False


def _request_representation(request):
    # Dates and symbol values vary by session/instrument. Their shapes still bind.
    return {"keys": sorted(request), "representation_parameters": {k: v for k, v in request.items()
            if k not in {"symbol", "ticker", "from", "to", "start", "end", "start_date", "end_date"}}}


def representation(bar, *, provider, route, request, previous=None, qualified_relation=None):
    fields = bar.get("field_representation") or {}
    transform = bar.get("transformation_identity")
    descriptor = {"provider": provider, "route": route, "request_representation": _request_representation(request or {}),
                  "native_price_representation": fields, "transformation_identity": transform,
                  "literal_unit_claim": bar.get("price_unit") or "UNKNOWN"}
    fingerprint = market.sha256_hex(market.canonical(descriptor))
    reasons = []
    if (set(fields) != set(OHLC) or not all(isinstance(v, str) and v for v in fields.values()) or len(set(fields.values())) != 1 or
        not transform or not route or not provider or not request):
        reasons.append("REPRESENTATION_PROVENANCE_INCOMPLETE_OR_MIXED")
    values = [bar.get(k) for k in OHLC]
    if (not all(market._finite_number(x) and x > 0 for x in values) or
        not (values[2] <= min(values[0], values[3]) <= max(values[0], values[3]) <= values[1])):
        reasons.append("INVALID_OHLC_GEOMETRY")
    explained = bool(qualified_relation and qualified_relation.get("status") == "QUALIFIED" and
                     qualified_relation.get("factor_chain_identity") and qualified_relation.get("official_execution_status") == "EXECUTED" and
                     qualified_relation.get("ex_date_status") == "EXPLICIT_OFFICIAL" and
                     qualified_relation.get("ex_date") == bar.get("session") and
                     qualified_relation.get("previous_binding_identity") == (previous or {}).get("artifact_identity") and
                     qualified_relation.get("current_fingerprint") == fingerprint and
                     qualified_relation.get("knowledge_cutoff") and
                     market._utc(qualified_relation["knowledge_cutoff"], "factor_known") <= market._utc(bar["retrieved_at"], "bar_known") and
                     market._finite_number(qualified_relation.get("adjustment_factor")) and qualified_relation["adjustment_factor"] > 0)
    ratio = None
    if previous:
        verify(previous, CAPTURE_CONTRACT)
        if previous.get("representation_fingerprint") != fingerprint:
            reasons.append("REPRESENTATION_FINGERPRINT_CHANGED")
        if previous.get("transformation_identity") != transform:
            reasons.append("TRANSFORMATION_CHANGED")
        prior_close = previous.get("integrity_reference_close")
        if market._finite_number(prior_close) and prior_close > 0 and market._finite_number(bar.get("close")) and bar["close"] > 0:
            ratio = max(bar["close"] / prior_close, prior_close / bar["close"])
            relation_ratio = bar["close"] / (prior_close * qualified_relation["adjustment_factor"]) if explained else None
            explained = explained and max(relation_ratio, 1 / relation_ratio) <= K
            if ratio > K and not explained:
                reasons.append("UNEXPLAINED_SCALE_DISCONTINUITY_GT_K")
        else:
            reasons.append("PREVIOUS_SCALE_REFERENCE_MISSING")
    tier = UNKNOWN if reasons else NATIVE
    documentation = bar.get("price_unit_documentation") or {}
    if not reasons and (documentation.get("status") == "QUALIFIED" and documentation.get("source_identity") and
                        documentation.get("provider") == provider and documentation.get("route") == route and
                        documentation.get("fields") == list(OHLC) and documentation.get("unit") == descriptor["literal_unit_claim"] and
                        documentation.get("unit") not in {None, "UNKNOWN", "SOURCE_PRICE_UNIT_UNDOCUMENTED"} and
                        documentation.get("known_at") and market._utc(documentation["known_at"], "unit_known") <=
                        market._utc(bar["retrieved_at"], "bar_known")):
        tier = ECONOMIC
    return {**descriptor, "representation_fingerprint": fingerprint, "representation_tier": tier,
            "representation_reason_codes": sorted(reasons), "scale_tripwire_k": K, "consecutive_ratio": ratio,
            "previous_binding_identity": previous.get("artifact_identity") if previous else None,
            "qualified_relation_identity": qualified_relation.get("factor_chain_identity") if explained else None,
            "economic_unit_evidence": documentation if tier == ECONOMIC else None}


def capture_binding(receipt, bar, source_record, *, source_snapshot_identity, created_at, capture_window_close,
                    presence=None, previous=None, qualified_relation=None):
    verify(receipt, "prospective_market_receipt")
    observation = receipt["observation"]
    ticker, session = observation["instrument"]["ticker"], observation["trading_session"]
    if bar.get("session") != session:
        raise ValueError("CAPTURE_BAR_SESSION_MISMATCH")
    if (observation.get("snapshot_identity") != market.CONTRACT_VERSION + ":" + market.sha256_hex(market.canonical(
            {k: v for k, v in observation.items() if k != "snapshot_identity"})) or
        any(bar.get(k) != observation["normalized"]["ohlc"].get(k) for k in OHLC) or
        market.sha256_hex(market.canonical({"ticker": ticker, "observation": bar})) != observation["payload"]["sha256"]):
        raise ValueError("CAPTURE_EXACT_OBSERVATION_BINDING_MISMATCH")
    known = observation["acquisition"]["knowledge_available_at_utc"]
    if market._utc(created_at, "created_at") < market._utc(known, "receipt_known_at"):
        raise ValueError("COMPANION_BEFORE_MARKET_RECEIPT")
    # Do not reuse the old snapshot contract's hard-coded /price/ohlc route.
    provider = bar.get("provider")
    route = bar.get("provider_endpoint") or source_record.get("provider_endpoint")
    request = bar.get("request") or source_record.get("request") or {}
    requested_instrument = request.get("symbol") or request.get("ticker")
    if requested_instrument and str(requested_instrument).upper() != ticker:
        raise ValueError("CAPTURE_SOURCE_INSTRUMENT_MISMATCH")
    payload_hash = source_record.get("payload_hash")
    if payload_hash and (not isinstance(payload_hash, str) or len(payload_hash) != 64 or any(c not in "0123456789abcdef" for c in payload_hash)):
        raise ValueError("PROVIDER_PAYLOAD_HASH_INVALID")
    representation_state = representation(bar, provider=provider, route=route, request=request, previous=previous,
                                          qualified_relation=qualified_relation)
    if presence:
        verify(presence, LISTING_CONTRACT)
    positive = bool(presence and qualifying_presence(presence, ticker=ticker, session=session, cutoff=created_at))
    body = {"contract_version": CAPTURE_CONTRACT, "receipt_id": receipt["receipt_id"],
            "receipt_artifact_identity": receipt["artifact_identity"], "snapshot_identity": observation["snapshot_identity"],
            "source_snapshot_identity": source_snapshot_identity, "ticker": ticker, "session": session,
            "provider": provider, "actual_provider_route": route, "request_shape": dict(request),
            "provider_payload_identity": "provider_payload:" + payload_hash if payload_hash else None,
            "provider_payload_sha256": payload_hash, "provider_payload_hash_kind":
                "canonical_json_of_provider_payload" if payload_hash and provider == "DNSE" else
                "canonical_json_of_provider_native_payload" if payload_hash else "NOT_RETAINED",
            "retained_observation_payload": observation["payload"], **representation_state,
            "exchange": presence["exchange"] if positive else "UNKNOWN", "board": presence["board"] if positive else "UNKNOWN",
            "listing_observation_identity": presence["artifact_identity"] if presence else None,
            "listing_source": presence["source"] if presence else None, "listing_known_at": presence["known_at"] if presence else None,
            "listing_binding_class": "SAME_SESSION_POSITIVE" if positive else presence["binding_class"] if presence else "UNKNOWN",
            "source_instrument_identity": request.get("symbol") or request.get("ticker") or source_record.get("source_instrument_identity"),
            "provider_finality_state": bar.get("finality") or observation.get("finality") or "UNKNOWN",
            "source_basis_claim": bar.get("source_basis_claim", market.SOURCE_BASIS_UNDOCUMENTED),
            "source_basis_label": bar.get("price_basis"), "created_at": created_at, "capture_window_close": capture_window_close,
            "integrity_reference_close": bar.get("close"), "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY"}
    market._reject_secrets(body)
    return identified(body, CAPTURE_CONTRACT)


def effective_receipt(receipt, companions, cutoff, *, first_complete_capture_session=None):
    """Resolve known-at additive evidence; never mutate or rehash the old receipt."""
    verify(receipt, "prospective_market_receipt")
    observation = receipt["observation"]
    session = observation["trading_session"]
    instant = market._utc(cutoff, "cutoff")
    expected = session >= CAPTURE_START_NOT_BEFORE and (not first_complete_capture_session or session >= first_complete_capture_session)
    base = {"receipt": receipt, "companion": None, "capture_state": "INCOMPLETE_CAPTURE" if expected else "LEGACY_CAPTURE_INCOMPLETE",
            "missing_components": ["CAPTURE_COMPANION", "SAME_SESSION_EXCHANGE", "PRICE_REPRESENTATION", "LISTING_PRESENCE"],
            "authority_effect": "NONE"}
    eligible = []
    for row in companions:
        verify(row, CAPTURE_CONTRACT)
        if row.get("receipt_artifact_identity") == receipt["artifact_identity"]:
            if (row.get("receipt_id") != receipt["receipt_id"] or row.get("snapshot_identity") != observation["snapshot_identity"] or
                row.get("ticker") != observation["instrument"]["ticker"] or row.get("session") != session):
                raise ValueError("COMPANION_SCOPE_MISMATCH")
            if market._utc(row["created_at"], "created_at") <= instant:
                eligible.append(row)
    # Old sessions are never retroactively completed, even by a retained late companion.
    if not expected:
        return base
    if not eligible:
        return base
    qualified = []
    for row in eligible:
        close = market._utc(row["capture_window_close"], "window_close")
        earliest_close = market._utc(capture_window(session)[0], "session_close")
        created = market._utc(row["created_at"], "created_at")
        receipt_known = market._utc(observation["acquisition"]["knowledge_available_at_utc"], "receipt_known")
        conservative_close = market._utc(capture_window(session)[1], "conservative_close")
        if earliest_close <= receipt_known <= created < close <= conservative_close and observation["acquisition"]["capture_timing"] == market.PROSPECTIVE_SAME_SESSION_CAPTURE:
            qualified.append(row)
    candidates = qualified or eligible
    earliest = min(market._utc(r["created_at"], "created_at") for r in candidates)
    candidates = [r for r in candidates if market._utc(r["created_at"], "created_at") == earliest]
    if len({r["artifact_identity"] for r in candidates}) != 1:
        return {**base, "missing_components": ["CONFLICTING_CAPTURE_COMPANIONS"]}
    row = candidates[0]
    missing = []
    if not row.get("actual_provider_route") or not row.get("request_shape") or not row.get("provider_payload_identity") or not row.get("source_instrument_identity"):
        missing.append("PROVIDER_PROVENANCE")
    if row.get("exchange") == "UNKNOWN" or row.get("listing_binding_class") != "SAME_SESSION_POSITIVE" or not row.get("listing_observation_identity"):
        missing.append("SAME_SESSION_LISTING_AND_EXCHANGE")
    if row.get("representation_tier") == UNKNOWN:
        missing.append("PRICE_REPRESENTATION")
    return {**base, "companion": row, "effective_known_at": row["created_at"], "capture_state": "LATE_NOT_T0_QUALIFIED" if not qualified else
            "INCOMPLETE_CAPTURE" if missing else "T0_CAPTURE_COMPLETE", "missing_components": missing}


def calculation_allowed(calculation, tier, *, same_series, decision_predicate=True):
    behavior = CALCULATION_SCALE_BEHAVIOR.get(calculation, "NOT_SCALE_SAFE")
    if behavior not in SCALE_BEHAVIORS:
        raise ValueError("SCALE_BEHAVIOR_INVALID")
    return bool(same_series and decision_predicate and behavior == "INVARIANT" and tier in {NATIVE, ECONOMIC})


def official_verification(binding, observation, official=None, *, verification_known_at, unavailable=False):
    """A later comparison has its own time, and never becomes T0 knowledge."""
    verify(binding, CAPTURE_CONTRACT)
    if (observation.get("snapshot_identity") != binding["snapshot_identity"] or
        observation.get("instrument", {}).get("ticker") != binding["ticker"] or observation.get("trading_session") != binding["session"]):
        raise ValueError("VERIFICATION_T0_OBSERVATION_SCOPE_MISMATCH")
    when = market._utc(verification_known_at, "verification_known_at")
    if when < market._utc(binding["created_at"], "binding_known_at"):
        raise ValueError("VERIFICATION_BEFORE_BINDING")
    state = "OFFICIAL_SOURCE_UNAVAILABLE" if unavailable else "PENDING_VERIFICATION"
    reason, relation, reconciliation = None, None, None
    if official is not None:
        if (official.get("provider") != "HOSE" or official.get("source_id") != "HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT" or
            official.get("ticker") != binding["ticker"] or official.get("session") != binding["session"] or binding["exchange"] != "HOSE" or
            not official.get("exact_row") or not official.get("source_artifact_identity") or not official.get("source_artifact_sha256") or
            not official.get("official_known_at")):
            state, reason = "NOT_VERIFIABLE", "OFFICIAL_SOURCE_SCOPE_OR_LINEAGE_INCOMPLETE"
        else:
            if market._utc(official["official_known_at"], "official_known_at") > when:
                raise ValueError("VERIFICATION_BEFORE_OFFICIAL_EVIDENCE")
            original = observation["normalized"]["ohlc"]
            values = official.get("ohlc") or {}
            if not all(market._finite_number(values.get(k)) and values[k] > 0 for k in OHLC):
                state, reason = "NOT_VERIFIABLE", "OFFICIAL_OHLC_MISSING"
            else:
                ratios = {k: values[k] / original[k] for k in OHLC}
                uniform = max(ratios.values()) - min(ratios.values()) <= 1e-8 * max(ratios.values())
                relation = {"official_over_provider_ratios": ratios, "uniform_ratio": ratios["close"] if uniform else None,
                            "relation": "IDENTICAL_NUMERIC" if uniform and abs(ratios["close"] - 1) < 1e-8 else
                                        "UNIFORM_RATIO_EMPIRICAL_ONLY" if uniform else "NON_UNIFORM_MISMATCH",
                            "unit_inferred": False}
                declared = official.get("comparison_transformation") or {}
                factor = declared.get("factor", 1.0)
                qualified_transform = bool(declared.get("status") == "QUALIFIED" and declared.get("identity") and
                                           declared.get("known_at") and market._utc(declared["known_at"], "transform_known") <= when and
                                           market._finite_number(factor) and factor > 0)
                numeric_equal = relation["relation"] == "IDENTICAL_NUMERIC"
                comparable = numeric_equal or qualified_transform
                reconciliation = {k: {"provider_value": original[k], "official_value": values[k],
                    "match": abs(original[k] * (factor if qualified_transform else 1) - values[k]) <= 1e-6} for k in OHLC}
                if comparable and all(x["match"] for x in reconciliation.values()):
                    state = "VERIFIED_MATCH"
                elif not uniform or qualified_transform:
                    state, reason = "VERIFIED_MISMATCH", "OHLC_RECONCILIATION_MISMATCH"
                else:
                    state, reason = "NOT_VERIFIABLE", "UNIFORM_RATIO_WITHOUT_QUALIFIED_TRANSFORMATION"
    body = {"contract_version": VERIFICATION_CONTRACT, "receipt_id": binding["receipt_id"],
            "t0_receipt_identity": binding["receipt_artifact_identity"], "capture_binding_identity": binding["artifact_identity"],
            "ticker": binding["ticker"], "session": binding["session"], "state": state,
            "exact_official_row": (official or {}).get("exact_row"),
            "official_row_identity": (official or {}).get("row_identity"),
            "source_artifact_identity": (official or {}).get("source_artifact_identity"),
            "source_artifact_sha256": (official or {}).get("source_artifact_sha256"),
            "official_known_at": (official or {}).get("official_known_at"), "verification_known_at": verification_known_at,
            "ohlc_reconciliation": reconciliation, "ratio_transformation_relation": relation, "mismatch_reason": reason,
            "unit_semantics": {"provider_literal_claim": binding["literal_unit_claim"], "official_literal_claim": (official or {}).get("price_unit", "UNKNOWN"),
                               "economic_unit_qualified": binding["representation_tier"] == ECONOMIC and
                               binding["literal_unit_claim"] == (official or {}).get("price_unit")},
            "basis_semantics": {"source_basis_claim": binding["source_basis_claim"],
                                "official_basis_claim": (official or {}).get("source_basis_claim", market.SOURCE_BASIS_UNDOCUMENTED),
                                "empirical_basis_evidence": (official or {}).get("empirical_basis_evidence", "NOT_TESTED")},
            "t0_modified": False, "authority_effect": "NONE"}
    return identified(body, VERIFICATION_CONTRACT)


def raw_use_state(effective, verifications=(), *, cutoff, ca_comparability="UNKNOWN"):
    binding = effective.get("companion") or {}
    available = []
    for row in verifications:
        verify(row, VERIFICATION_CONTRACT)
        if (row.get("t0_receipt_identity") == effective["receipt"]["artifact_identity"] and
            market._utc(row["verification_known_at"], "verification_known_at") <= market._utc(cutoff, "cutoff")):
            available.append(row)
    states = {r["state"] for r in available}
    official_state = ("VERIFIED_MISMATCH" if "VERIFIED_MISMATCH" in states else "VERIFIED_MATCH" if "VERIFIED_MATCH" in states else
                     max(available, key=lambda r: market._utc(r["verification_known_at"], "known"))["state"] if available else "PENDING_VERIFICATION")
    observed = effective["capture_state"] == "T0_CAPTURE_COMPLETE"
    repr_safe = binding.get("representation_tier") in {NATIVE, ECONOMIC}
    basis = binding.get("source_basis_claim", market.SOURCE_BASIS_UNDOCUMENTED)
    empirical = sorted({str(r["basis_semantics"]["empirical_basis_evidence"]) for r in available}) or ["NOT_TESTED"]
    adjusted = basis == market.SOURCE_DOCUMENTS_ADJUSTED or any(x in {"ADJUSTED_ACROSS_EVENT", market.EMPIRICAL_ADJUSTED_ACROSS_EVENT} for x in empirical)
    uses = []
    if observed and repr_safe:
        uses += ["T0_OBSERVED_PRICE", "SAME_BAR_SCALE_INVARIANT_MORPHOLOGY"]
        if ca_comparability == "QUALIFIED_COMPARABLE" and official_state != "VERIFIED_MISMATCH":
            uses.append("SAME_SERIES_SCALE_INVARIANT_CONTINUOUS_TRANSFORMS")
        if official_state == "VERIFIED_MATCH" and not adjusted:
            uses.append("OFFICIAL_NUMERIC_MATCH_OBSERVED_PRICE")
    return {"t0_captured_observed_price": observed, "source_basis_claim": basis, "official_match_status": official_state,
            "empirical_basis_evidence": empirical, "ca_comparability": ca_comparability,
            "representation_tier": binding.get("representation_tier", UNKNOWN), "allowed_uses": uses,
            "global_raw_authority": "NOT_PROMOTED", "pit_backtest": "BLOCKED", "execution": "BLOCKED",
            "authority_effect": "NONE"}
