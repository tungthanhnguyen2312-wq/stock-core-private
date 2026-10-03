"""Signal-specific market-input gates, independent of full research/economic PIT.

This computes eligibility and contiguous coverage, not signals or a backtester.
Strategy-owned requirements are explicit; no global ticker-ready state exists.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Mapping, Sequence

import prospective_market_snapshot_contract as market

CONTRACT_VERSION = "market_only_pit_eligibility/v1"
RAW_AS_TRADED = "RAW_AS_TRADED"
PIT_CA_ADJUSTED = "PIT_CA_ADJUSTED"
RETROSPECTIVE_ADJUSTED = "RETROSPECTIVE_ADJUSTED"
OBSERVED_SCALE_INVARIANT = "OBSERVED_SCALE_INVARIANT"
EXISTING_VNM_SIGNAL = "VNM_PIT_AVAILABILITY_TECHNICAL_CONFIRMATION_V1"


@dataclass(frozen=True)
class SignalRequirements:
    signal_id: str
    lookback_sessions: int
    volume_required: bool = False
    active_universe_required: bool = True
    comparable_ca_required: bool = True
    price_mode: str = RAW_AS_TRADED
    benchmark_required: bool = False
    benchmark_ticker: str | None = None
    timeframe: str = "D"
    ticker_scope: tuple[str, ...] = ()
    membership_claim: str = "ACTIVE"
    membership_mode: str = "EFFECTIVE_INTERVAL"
    scale_behavior: str = "NOT_SCALE_SAFE"
    calculation_id: str | None = None


def requirements_payload(requirements):
    body = asdict(requirements)
    # Preserve the exact standing signal/output identity under the legacy mode.
    if (requirements.membership_claim == "ACTIVE" and requirements.membership_mode == "EFFECTIVE_INTERVAL" and
        requirements.scale_behavior == "NOT_SCALE_SAFE" and requirements.calculation_id is None):
        for key in ("membership_claim", "membership_mode", "scale_behavior", "calculation_id"):
            body.pop(key)
    return body


class MarketVersionIndex:
    """One run-scoped index instead of a full version scan per ticker/session."""
    def __init__(self, rows):
        self.rows = defaultdict(lambda: defaultdict(list))
        for row in rows:
            self.rows[row.get("instrument", {}).get("ticker")][row.get("trading_session")].append(row)

    def window(self, ticker, days):
        return {day: self.rows.get(ticker, {}).get(day, []) for day in days}


def existing_vnm_requirements(*, replay_inputs: bool = False) -> SignalRequirements:
    # opportunity_ranking._technical reads above_sma50; scenario_analysis's bull
    # confirmation reads that same boolean. The signal has no volume threshold.
    # Existing next-session fill primitives additionally require positive volume.
    return SignalRequirements(EXISTING_VNM_SIGNAL, 50, volume_required=replay_inputs, ticker_scope=("VNM",))


def _known(value: Any, cutoff) -> bool:
    try:
        return market._utc(value, "knowledge_available_at") <= cutoff
    except (AttributeError, TypeError, ValueError):
        return False


def _price_ready(row: Mapping[str, Any], *, mode: str, cutoff) -> bool:
    ohlc = row.get("normalized", {}).get("ohlc", {})
    source = row.get("source", {})
    basis = row.get("basis", {})
    try:
        digest = market.sha256_hex(market.canonical({k:v for k,v in row.items() if k != "snapshot_identity"}))
    except (TypeError, ValueError):
        return False
    valid = (row.get("snapshot_identity") == market.CONTRACT_VERSION + ":" + digest and
             _known(row.get("acquisition", {}).get("knowledge_available_at_utc"),cutoff) and
             row.get("acquisition", {}).get("receipt_at_utc") == row.get("acquisition", {}).get("knowledge_available_at_utc") and
             source.get("source_id") and row.get("payload", {}).get("sha256") and
             row.get("instrument", {}).get("exchange") and row.get("board_basis", {}).get("unit") not in {None, "UNKNOWN", "SOURCE_PRICE_UNIT_UNDOCUMENTED"} and
             all(market._finite_number(ohlc.get(k)) and ohlc[k] > 0 for k in ("open", "high", "low", "close")) and
             ohlc["low"] <= min(ohlc["open"], ohlc["close"]) <= max(ohlc["open"], ohlc["close"]) <= ohlc["high"] and
             row.get("acquisition", {}).get("capture_timing") == market.PROSPECTIVE_SAME_SESSION_CAPTURE and
             row.get("finality") not in {"INTRADAY", "INCOMPLETE"})
    if not valid:
        return False
    if mode == RAW_AS_TRADED:
        return (market.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE in row.get("qualification", {}).get("allowed_uses", []) and
                basis.get("source_basis_claim") != market.SOURCE_DOCUMENTS_ADJUSTED and
                basis.get("empirical_basis_test") != market.EMPIRICAL_ADJUSTED_ACROSS_EVENT and
                row.get("price_mode", RAW_AS_TRADED) == RAW_AS_TRADED)
    if mode == PIT_CA_ADJUSTED:
        return row.get("price_mode") == mode and bool(row.get("raw_lineage_identities")) and _qualified_factors(row.get("factor_chain", []), cutoff, row.get("trading_session"))
    return False


def _qualified_factors(factors: Sequence[Mapping[str, Any]], cutoff, end: str) -> bool:
    if not factors:
        return False
    return all(f.get("status") == "QUALIFIED" and f.get("factor_chain_identity") and
               f.get("official_execution_status") == "EXECUTED" and f.get("ex_date_status") == "EXPLICIT_OFFICIAL" and
               f.get("ex_date") and f["ex_date"] <= end and _known(f.get("knowledge_cutoff"), cutoff) and
               market._finite_number(f.get("adjustment_factor")) and f["adjustment_factor"] > 0 for f in factors)


def _volume_ready(row: Mapping[str, Any]) -> bool:
    qualification = row.get("volume_qualification", {})
    volume = row.get("normalized", {}).get("volume_value", {}).get("volume")
    return ("PROSPECTIVE_AS_KNOWN_VOLUME_EVIDENCE" in qualification.get("allowed_uses", []) and
            qualification.get("unit") == "SHARES" and qualification.get("basis") == "AS_REPORTED" and
            market._finite_number(volume) and volume > 0)


def evaluate(*, requirements: SignalRequirements, ticker: str, session: str, knowledge_cutoff: str,
             market_versions: Sequence[Mapping[str, Any]], calendar_sessions: Sequence[str],
             universe_versions: Sequence[Mapping[str, Any]] = (), ca_versions: Sequence[Mapping[str, Any]] = (),
             benchmark_versions: Sequence[Mapping[str, Any]] = (), governed_chain=None,
             capture_receipts=(), capture_companions=(), listing_presence=(), official_verifications=()) -> dict[str, Any]:
    """Select only versions known at the explicit cutoff; future corrections cannot repair T0.

    Universe/CA bindings require explicit temporal scope and source identity, never
    current ticker presence or a default assumption that no event occurred.
    """
    if requirements.price_mode == OBSERVED_SCALE_INVARIANT:
        return _evaluate_capture(requirements=requirements, ticker=ticker, session=session, knowledge_cutoff=knowledge_cutoff,
            governed_chain=governed_chain, receipts=capture_receipts, companions=capture_companions,
            listing_presence=listing_presence, verifications=official_verifications, ca_versions=ca_versions)
    if (isinstance(requirements.lookback_sessions, bool) or not isinstance(requirements.lookback_sessions,int) or requirements.lookback_sessions < 1 or
        requirements.timeframe != "D" or requirements.price_mode not in {RAW_AS_TRADED, PIT_CA_ADJUSTED}):
        raise ValueError("UNSUPPORTED_SIGNAL_REQUIREMENTS")
    calendar = list(calendar_sessions)
    if calendar != sorted(set(calendar)):
        raise ValueError("GOVERNED_CALENDAR_NOT_SORTED_UNIQUE")
    for day in calendar:
        date.fromisoformat(day)
    cutoff = market._utc(knowledge_cutoff, "knowledge_cutoff")
    reasons = set()
    if requirements.ticker_scope and ticker not in requirements.ticker_scope:
        reasons.add("SIGNAL_TICKER_SCOPE_NOT_SUPPORTED")
    if date.fromisoformat(session) > cutoff.astimezone(market.VN_TZ).date():
        reasons.add("KNOWLEDGE_CUTOFF_VIOLATION")
    if session not in calendar:
        reasons.update({"SESSION_NOT_IN_GOVERNED_CALENDAR", "LOOKBACK_WINDOW_INSUFFICIENT"})
        window = [session]
    else:
        end_index = calendar.index(session) + 1
        window = calendar[max(0, end_index-requirements.lookback_sessions):end_index]
        if len(window) < requirements.lookback_sessions:
            reasons.add("LOOKBACK_WINDOW_INSUFFICIENT")
    by_session = (market_versions.window(ticker, window) if isinstance(market_versions, MarketVersionIndex) else
                  MarketVersionIndex(market_versions).window(ticker, window))
    selected = []
    for day in window:
        available = [r for r in by_session[day] if _known(r.get("acquisition", {}).get("knowledge_available_at_utc"), cutoff)]
        if not available:
            reasons.add("PRICE_NOT_PIT_ELIGIBLE")
            if by_session[day]:
                reasons.add("KNOWLEDGE_CUTOFF_VIOLATION")
            reasons.add("LOOKBACK_WINDOW_INSUFFICIENT")
            continue
        latest = max(market._utc(r["acquisition"]["knowledge_available_at_utc"], "known") for r in available)
        at_latest = [r for r in available if market._utc(r["acquisition"]["knowledge_available_at_utc"], "known") == latest]
        if len({r.get("snapshot_identity") for r in at_latest}) != 1 or not at_latest[0].get("snapshot_identity"):
            reasons.add("PRICE_NOT_PIT_ELIGIBLE")
            continue
        row = at_latest[0]
        selected.append(row)
        if not _price_ready(row, mode=requirements.price_mode, cutoff=cutoff):
            reasons.add("PRICE_NOT_PIT_ELIGIBLE")
        if requirements.volume_required and not _volume_ready(row):
            reasons.add("VOLUME_NOT_PIT_ELIGIBLE")
    bases = {(r.get("board_basis", {}).get("unit"), r.get("price_mode", RAW_AS_TRADED), r.get("instrument", {}).get("exchange")) for r in selected}
    if len(bases) != 1 or any(r.get("price_mode") == RETROSPECTIVE_ADJUSTED for r in selected):
        reasons.add("BASIS_INCOMPATIBLE")
    exchange = selected[-1].get("instrument", {}).get("exchange") if selected else None
    def scoped(rows):
        return [r for r in rows if r.get("ticker") == ticker and r.get("exchange") == exchange and r.get("source_identity") and
                _known(r.get("knowledge_available_at"), cutoff) and r.get("window_start", "9999") <= window[0] and
                r.get("window_end", "") >= session]
    memberships = scoped(universe_versions)
    if requirements.membership_mode == "POSITIVE_PRESENCE_EVERY_SESSION":
        from prospective_pit_capture import qualifying_presence
        if requirements.membership_claim != "LISTED_PRESENT" or any(not any(
            qualifying_presence(r, ticker=ticker, session=day, cutoff=knowledge_cutoff) and r.get("exchange") == exchange
            for r in listing_presence) for day in window):
            reasons.add("LISTED_PRESENCE_WINDOW_INCOMPLETE")
    elif requirements.membership_mode != "EFFECTIVE_INTERVAL":
        raise ValueError("UNSUPPORTED_MEMBERSHIP_MODE")
    elif requirements.active_universe_required and not any(r.get("active_universe_at_time") == "ACTIVE" and r.get("temporal_membership_qualified") is True for r in memberships):
        reasons.add("ACTIVE_UNIVERSE_UNKNOWN")
        if any(r.get("ticker") == ticker and not _known(r.get("knowledge_available_at"), cutoff) for r in universe_versions):
            reasons.add("KNOWLEDGE_CUTOFF_VIOLATION")
    if requirements.comparable_ca_required:
        ca = scoped(ca_versions)
        if not any(r.get("state") == "NO_APPLICABLE_CA_PROVEN" or
                   (requirements.price_mode == PIT_CA_ADJUSTED and r.get("state") == "QUALIFIED_FACTOR_CHAIN" and
                    _qualified_factors(r.get("factor_chain", []), cutoff, session)) for r in ca):
            reasons.add("CA_FACTOR_REQUIRED_UNAVAILABLE")
            if any(r.get("ticker") == ticker and not _known(r.get("knowledge_available_at"), cutoff) for r in ca_versions):
                reasons.add("KNOWLEDGE_CUTOFF_VIOLATION")
    if requirements.benchmark_required:
        if not requirements.benchmark_ticker:
            reasons.add("BENCHMARK_NOT_ELIGIBLE")
        else:
            benchmark_requirements = SignalRequirements(requirements.signal_id, requirements.lookback_sessions,
                active_universe_required=False, comparable_ca_required=requirements.comparable_ca_required,
                price_mode=requirements.price_mode)
            benchmark = evaluate(requirements=benchmark_requirements, ticker=requirements.benchmark_ticker, session=session,
                knowledge_cutoff=knowledge_cutoff, market_versions=benchmark_versions, calendar_sessions=calendar,
                ca_versions=ca_versions)
            if benchmark["state"] != "ELIGIBLE":
                reasons.add("BENCHMARK_NOT_ELIGIBLE")
    body = {"contract_version": CONTRACT_VERSION, "signal_requirements": requirements_payload(requirements), "ticker": ticker,
            "session": session, "exchange": exchange, "knowledge_cutoff": knowledge_cutoff,
            "price_basis_signature": sorted([list(b) for b in bases],key=str),
            "required_sessions": window, "selected_snapshot_identities": [r["snapshot_identity"] for r in selected],
            "state": "ELIGIBLE" if not reasons else "EXCLUDED", "reason_codes": sorted(reasons),
            "eligible_use": "GROSS_MARKET_RESEARCH_REPLAY_INPUTS" if requirements.volume_required else "MARKET_ONLY_SIGNAL_INPUTS",
            "authority_effect": "NONE", "net_execution_state": "UNAVAILABLE_WITHOUT_SEPARATE_EXECUTION_AND_COST_EVIDENCE"}
    body.update(market.content_identity(body, kind="market_only_pit_eligibility"))
    return body


class CaptureEligibilityIndex:
    """Reusable known-at receipt, companion, listing and verification lookup."""
    def __init__(self, receipts=(), companions=(), listing_presence=(), verifications=()):
        self.receipts, self.companions, self.listing, self.verifications = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
        for row in receipts:
            observation = row["observation"]
            self.receipts[(observation["instrument"]["ticker"], observation["trading_session"])].append(row)
        for row in companions:
            self.companions[row["receipt_artifact_identity"]].append(row)
        for row in listing_presence:
            self.listing[(row["ticker"], row["session"])].append(row)
        for row in verifications:
            self.verifications[row["t0_receipt_identity"]].append(row)


def _evaluate_capture(*, requirements, ticker, session, knowledge_cutoff, governed_chain, receipts,
                      companions, listing_presence, verifications, ca_versions):
    import prospective_pit_capture as capture
    if (requirements.membership_claim != "LISTED_PRESENT" or requirements.membership_mode != "POSITIVE_PRESENCE_EVERY_SESSION" or
        requirements.scale_behavior != "INVARIANT" or requirements.volume_required or requirements.benchmark_required or
        requirements.timeframe != "D" or isinstance(requirements.lookback_sessions, bool) or
        not isinstance(requirements.lookback_sessions, int) or requirements.lookback_sessions < 1):
        raise ValueError("UNSUPPORTED_PROSPECTIVE_REQUIREMENTS")
    if not governed_chain or not hasattr(governed_chain, "window_ending"):
        window = []
    else:
        window = governed_chain.window_ending(session, requirements.lookback_sessions)
    index = receipts if isinstance(receipts, CaptureEligibilityIndex) else CaptureEligibilityIndex(receipts, companions, listing_presence, verifications)
    reasons, selected, fingerprints, exchanges = set(), [], set(), set()
    cutoff = market._utc(knowledge_cutoff, "cutoff")
    if governed_chain and any(not _known(governed_chain.records[d]["completion_known_at"], cutoff) for d in window):
        reasons.add("KNOWLEDGE_CUTOFF_VIOLATION")
    if len(window) < requirements.lookback_sessions:
        reasons.add("LOOKBACK_WINDOW_INSUFFICIENT")
    if not window:
        reasons.add("SESSION_NOT_IN_GOVERNED_CAPTURE_CHAIN")
    if requirements.ticker_scope and ticker not in requirements.ticker_scope:
        reasons.add("SIGNAL_TICKER_SCOPE_NOT_SUPPORTED")
    if capture.CALCULATION_SCALE_BEHAVIOR.get(requirements.calculation_id) != "INVARIANT":
        reasons.add("CALCULATION_NOT_REGISTERED_SCALE_INVARIANT")
    for day in window:
        available = [r for r in index.receipts[(ticker, day)] if _known(r["observation"]["acquisition"]["knowledge_available_at_utc"], cutoff)]
        qualified = []
        for row in available:
            effective = capture.effective_receipt(row, index.companions[row["artifact_identity"]], knowledge_cutoff)
            if effective["capture_state"] == "T0_CAPTURE_COMPLETE":
                qualified.append(effective)
        # Select the actual first complete capture, not a later correction.
        qualified.sort(key=lambda e: (market._utc(e["companion"]["created_at"], "known"), e["receipt"]["receipt_id"]))
        if not qualified:
            reasons.add("PRICE_NOT_PIT_ELIGIBLE")
            continue
        effective = qualified[0]
        binding = effective["companion"]
        selected.append(binding["snapshot_identity"])
        fingerprints.add(binding["representation_fingerprint"])
        exchanges.add(binding["exchange"])
        positive = [r for r in index.listing[(ticker, day)] if capture.qualifying_presence(r, ticker=ticker, session=day, cutoff=knowledge_cutoff) and
                    r["artifact_identity"] == binding["listing_observation_identity"] and r["exchange"] == binding["exchange"]]
        if not positive:
            reasons.add("LISTED_PRESENCE_WINDOW_INCOMPLETE")
        if not capture.calculation_allowed(requirements.calculation_id, binding["representation_tier"], same_series=True):
            reasons.add("PRICE_REPRESENTATION_NOT_SCALE_SAFE")
        raw = capture.raw_use_state(effective, index.verifications[effective["receipt"]["artifact_identity"]], cutoff=knowledge_cutoff)
        if raw["official_match_status"] == "VERIFIED_MISMATCH":
            reasons.add("OFFICIAL_VERIFIED_MISMATCH")
    if len(fingerprints) != 1 or len(exchanges) != 1:
        reasons.add("BASIS_INCOMPATIBLE")
    exchange = next(iter(exchanges)) if len(exchanges) == 1 else None
    ca_required = requirements.comparable_ca_required or requirements.calculation_id in capture.CONTINUOUS_CALCULATIONS
    if ca_required and window and not any(r.get("ticker") == ticker and r.get("exchange") == exchange and
        r.get("source_identity") and _known(r.get("knowledge_available_at"), cutoff) and r.get("window_start", "9999") <= window[0] and
        r.get("window_end", "") >= session and r.get("state") == "NO_APPLICABLE_CA_PROVEN" for r in ca_versions):
        reasons.add("CA_FACTOR_REQUIRED_UNAVAILABLE")
    body = {"contract_version": CONTRACT_VERSION, "signal_requirements": requirements_payload(requirements), "ticker": ticker,
        "session": session, "exchange": exchange, "knowledge_cutoff": knowledge_cutoff, "required_sessions": window,
        "selected_snapshot_identities": selected, "representation_fingerprints": sorted(fingerprints),
        "session_chain_contract": "governed_session_chain/v1", "state": "ELIGIBLE" if not reasons else "EXCLUDED",
        "reason_codes": sorted(reasons), "eligible_use": "BOUNDED_SCALE_INVARIANT_MARKET_COMPONENT_INPUTS",
        "authority_effect": "NONE", "evaluation_authorized": False, "net_execution_state": "UNAVAILABLE"}
    body.update(market.content_identity(body, kind="market_only_pit_eligibility"))
    return body


def contiguous_coverage(rows: Sequence[Mapping[str, Any]], *, calendar_sessions: Sequence[str],
                        calendar_windows: Sequence[Sequence[str]] = ()) -> dict[str, Any]:
    """Report observed scope separately from eligible contiguous regions, per signal."""
    result = {}
    groups = defaultdict(list)
    for row in rows:
        groups[row["signal_requirements"]["signal_id"]].append(row)
    index = {s:i for i,s in enumerate(calendar_sessions)}
    window_indices = [{s:i for i,s in enumerate(window)} for window in calendar_windows] or [index]
    for signal, observations in sorted(groups.items()):
        eligible = [r for r in observations if r["state"] == "ELIGIBLE"]
        pairs = sorted({(r["ticker"],r["session"]) for r in eligible})
        regions = []
        for ticker in sorted({t for t,_ in pairs}):
            days = sorted(s for t,s in pairs if t == ticker)
            current = []
            for day in days:
                if current and not any(day in window and current[-1] in window and
                                       window[day] == window[current[-1]]+1 for window in window_indices):
                    regions.append({"ticker":ticker,"earliest":current[0],"latest":current[-1],"sessions":len(current)})
                    current = []
                current.append(day)
            if current:
                regions.append({"ticker":ticker,"earliest":current[0],"latest":current[-1],"sessions":len(current)})
        result[signal] = {"observed_ticker_sessions": len({(r["ticker"],r["session"]) for r in observations}),
                          "eligible_ticker_sessions": len(pairs), "eligible_tickers": len({t for t,_ in pairs}),
                          "eligible_sessions": len({s for _,s in pairs}),
                          "earliest": min((s for _,s in pairs), default=None), "latest": max((s for _,s in pairs), default=None),
                          "first_contiguous_region": min(regions,key=lambda r:(r["earliest"],r["ticker"]), default=None),
                          "contiguous_regions": sorted(regions,key=lambda r:(r["earliest"],r["ticker"])),
                          "by_exchange": dict(sorted(Counter(r["exchange"] or "UNKNOWN" for r in eligible).items())),
                          "exclusion_reason_counts": dict(sorted(Counter(reason for r in observations for reason in r["reason_codes"]).items()))}
    return result


def aggregate_period_eligibility(*, timeframe: str, period_end: str, knowledge_cutoff: str,
                                 constituent_rows: Sequence[Mapping[str, Any]], expected_sessions: Sequence[str]) -> dict[str, Any]:
    """D/W/M lineage guard only. Computes no new candle or technical feature."""
    if timeframe not in {"D", "W", "M"}:
        raise ValueError("UNSUPPORTED_TIMEFRAME")
    cutoff = market._utc(knowledge_cutoff, "knowledge_cutoff")
    reasons = set()
    sessions = [r["session"] for r in constituent_rows]
    if not expected_sessions or sorted(sessions) != sorted(set(expected_sessions)):
        reasons.add("LOOKBACK_WINDOW_INSUFFICIENT")
    if date.fromisoformat(period_end) > cutoff.astimezone(market.VN_TZ).date() or any(s > period_end for s in sessions):
        reasons.add("KNOWLEDGE_CUTOFF_VIOLATION")
    if any(not _known(r.get("knowledge_cutoff"), cutoff) for r in constituent_rows):
        reasons.add("KNOWLEDGE_CUTOFF_VIOLATION")
    if len({(r.get("ticker"),r.get("exchange"),r.get("signal_requirements",{}).get("signal_id"),
             market.canonical(r.get("price_basis_signature"))) for r in constituent_rows}) != 1:
        reasons.add("BASIS_INCOMPATIBLE")
    for row in constituent_rows:
        if row.get("artifact_identity") != market.content_identity(row,kind="market_only_pit_eligibility")["artifact_identity"]:
            reasons.add("CONSTITUENT_IDENTITY_MISMATCH")
        if row.get("state") != "ELIGIBLE":
            reasons.update(row.get("reason_codes") or ["PRICE_NOT_PIT_ELIGIBLE"])
    body = {"contract_version":CONTRACT_VERSION,"timeframe":timeframe,"period_end":period_end,
            "knowledge_cutoff":knowledge_cutoff,"constituent_identities":[r["artifact_identity"] for r in constituent_rows],
            "state":"ELIGIBLE" if not reasons else "EXCLUDED","reason_codes":sorted(reasons)}
    body.update(market.content_identity(body,kind="market_period_eligibility"))
    return body
