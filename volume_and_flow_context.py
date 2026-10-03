"""Independent, non-voting volume / qualified participant VALUE context.

Technical owns native-volume measurements; this producer references those exact
features and adds bounded prior-20-relative trajectories. No acquisition or action
consumer exists here. All identities exclude wall-clock build time.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

import contextual_technical_features as technical
import dnse_foreign_flow_store as flow_store
import flow_price_divergence_shadow as divergence
import technical_structure_context as conventions

CONTRACT_VERSION = "volume_and_flow_context/v1"
ITEM_VERSION = "volume_and_flow_evidence/v1"
AUTHORITY_EFFECT = "NONE / DESCRIPTIVE_VOLUME_AND_PARTICIPANT_VALUE_CONTEXT_ONLY"
T0 = "T0_SEALED"
POST = "POST_T0_ENRICHED"
VOLUME_WINDOWS = (5, 20)
FLOW_WINDOWS = (1, 5, 10, 20)
PARTICIPANTS = ("FOREIGN", "PROPRIETARY", "DOMESTIC_INSTITUTIONAL", "OTHER")
USABLE = technical.USABLE


def seal(value, kind=CONTRACT_VERSION):
    value.update(technical.identity(value, kind=kind))
    return value


def verify(value, kind):
    if any(value.get(k) != v for k, v in technical.identity(value, kind=kind).items()):
        raise ValueError("VOLUME_FLOW_CONTENT_IDENTITY_INVALID:" + kind)


def relative_state(ratio):
    """Reuse the standing expansion/compression ratio family; never a score."""
    if ratio is None:
        return "UNDEFINED_ZERO_REFERENCE"
    return ("EXPANSION" if ratio >= conventions.EXPANSION_RATIO else
            "CONTRACTION" if ratio <= conventions.COMPRESSION_RATIO else "STABLE")


def _item(*, ticker, session, domain, sub_domain, horizon, participant, source,
          unit, semantics, stage, status, reasons, actual, required, freshness,
          temporal, basis, scope, source_ids, technical_id=None, values=None,
          observed_state="UNAVAILABLE", relationship=None, continuity=None):
    if stage not in {T0, POST}:
        raise ValueError("VOLUME_FLOW_KNOWLEDGE_STAGE_INVALID")
    return seal({"contract_version": ITEM_VERSION, "instrument": {"ticker": ticker},
        "session": session, "build_stage": POST, "domain": domain,
        "sub_domain": sub_domain, "horizon": horizon, "participant": participant,
        "source": source, "measure_semantics": semantics, "unit_semantics": unit,
        "knowledge_stage": stage, "status": status, "fitness": status,
        "reason_codes": sorted(set(reasons)), "blockers": sorted(set(reasons)) if status not in USABLE else [],
        "actual_observations": actual, "required_observations": required,
        "freshness": freshness, "temporal_fitness": temporal, "basis_fitness": basis,
        "coverage_scope": scope, "source_artifact_identities": sorted(set(source_ids)),
        "technical_context_identity": technical_id, "technical_relationship": relationship,
        "session_continuity": continuity, "observed_state": observed_state, "values": values,
        "allowed_use": "CURRENT_RESEARCH_DESCRIPTIVE_ONLY" if status in USABLE else "NONE",
        "non_voting": True, "is_actionable": False, "authority_effect": AUTHORITY_EFFECT}, ITEM_VERSION)


def verify_technical(context, ticker, session):
    if (context.get("contract_version") != technical.CONTRACT_VERSION or context.get("ticker") != ticker
            or context.get("as_of_session") != session or context.get("non_voting") is not True
            or context.get("authority_effect") != technical.AUTHORITY_EFFECT
            or set(context.get("timeframes",{})) != set(technical.TIMEFRAMES)):
        raise ValueError("VOLUME_TECHNICAL_BINDING_INVALID")
    verify(context, technical.CONTRACT_VERSION)
    for tf, frame in context["timeframes"].items():
        verify(frame, technical.CONTRACT_VERSION)
        verify(frame["context"], "contextual_technical_inputs/v1")
        inputs = frame["context"]
        if (inputs["ticker"] != ticker or inputs["as_of_session"] != session or inputs["timeframe"] != tf
                or inputs["knowledge_cutoff"] != context["knowledge_cutoff"] or inputs["non_voting"] is not True
                or inputs["historical_pit_authority"] is not False or frame["non_voting"] is not True
                or frame["authority_effect"] != technical.AUTHORITY_EFFECT):
            raise ValueError("VOLUME_TECHNICAL_FRAME_BINDING_INVALID")
        if inputs.get("knowledge_available_at") and technical.market._utc(inputs["knowledge_available_at"],"volume_known") > technical.market._utc(context["knowledge_cutoff"],"volume_cutoff"):
            raise ValueError("VOLUME_TECHNICAL_FUTURE_INPUTS")
        if set(frame["features"]) != set(technical.FAMILIES) or any(
                f["input_context_identity"] != inputs["artifact_identity"] or f["non_voting"] is not True
                for f in frame["features"].values()):
            raise ValueError("VOLUME_TECHNICAL_FEATURE_BINDING_INVALID")


def technical_relationship(frame, participation):
    """Join the existing categorical technical observations, without voting."""
    f = frame["features"]
    structure = f["structure"].get("values") if f["structure"]["status"] in USABLE else None
    base = f["base"].get("values") if f["base"]["status"] in USABLE else None
    interpretation = f["interpretation"].get("values") if f["interpretation"]["status"] in USABLE else None
    if not structure:
        return {"state": "TECHNICAL_CONTEXT_UNAVAILABLE", "participation": participation}
    return {"state": "DESCRIPTIVE_TECHNICAL_VOLUME_JOIN", "participation": participation,
        "breakout": (structure.get("breakout") or {}).get("breakout_state"),
        "base": (base or {}).get("state"), "direction": structure.get("direction"),
        "repair": (interpretation or {}).get("repair_context"),
        "technical_feature_identity": frame["artifact_identity"], "is_actionable": False}


class SealedTechnicalBindings:
    """Validate the retained snapshot once, extracting only exact feature refs."""
    def __init__(self, snapshot):
        import prospective_decision_retention as retention
        if not retention.validate_snapshot(snapshot):
            raise ValueError("VOLUME_SEALED_SNAPSHOT_INVALID")
        self.snapshot_identity = snapshot["snapshot_identity"]
        self.bindings = {}
        for ticker,row in snapshot["records"].items():
            original = row.get("integrated_decision_at_t0") or {}
            projection = (original.get("contextual_technical_context") or {}).get("projection") or {}
            if projection:
                verify_technical(projection,ticker,row["decision_session"])
                self.bindings[ticker] = (row["decision_session"],projection["artifact_identity"])


def _stage(context, sealed_snapshot):
    if sealed_snapshot is None:
        return POST, None
    bindings = sealed_snapshot if isinstance(sealed_snapshot,SealedTechnicalBindings) else SealedTechnicalBindings(sealed_snapshot)
    if bindings.bindings.get(context["ticker"]) != (context["as_of_session"],context["artifact_identity"]):
        raise ValueError("VOLUME_TECHNICAL_NOT_BOUND_IN_SEALED_T0")
    return T0, bindings.snapshot_identity


def volume_items(context, *, series=None, exhaustive_dates=(), registry_dates=(), sealed_snapshot=None):
    ticker, session = context["ticker"], context["as_of_session"]
    verify_technical(context, ticker, session)
    stage, t0_id = _stage(context, sealed_snapshot)
    items = []
    for tf in technical.TIMEFRAMES:
        frame = context["timeframes"][tf]
        c, f = frame["context"], frame["features"]["volume"]
        values = f.get("values") or {}
        state = relative_state(values.get("relative_to_median")) if f["status"] in USABLE else "UNAVAILABLE"
        common = dict(ticker=ticker, session=session, domain="VOLUME", participant=None,
            source=c.get("source"), unit={"native": c.get("volume_unit") or "UNKNOWN", "derived": "DIMENSIONLESS"},
            stage=stage, freshness=c["freshness"], temporal=c["temporal_fitness"],
            basis={"price": c["price_basis"], "volume": c["volume_basis"], "corporate_actions": c["corporate_action_comparability"]},
            scope={"kind": "OWN_HISTORY", "ticker": ticker, "timeframe": tf},
            source_ids=[context["artifact_identity"], frame["artifact_identity"]] + ([t0_id] if t0_id else []),
            technical_id=context["artifact_identity"])
        items.append(_item(**common, sub_domain="NATIVE_VOLUME_REFERENCE", horizon=tf,
            semantics="EXACT_TECHNICAL_FEATURE_REFERENCE_OWN_HISTORY_NOT_CROSS_SECTIONAL",
            status=f["status"], reasons=f["reason_codes"], actual=f["actual_available_lookback"],
            required=f["required_lookback"], observed_state=state,
            values={"feature_path": "timeframes." + tf + ".features.volume", "feature_identity": frame["artifact_identity"]},
            relationship=technical_relationship(frame, state), continuity={"state": "INHERITS_TECHNICAL_FITNESS_NOT_SESSION_MATURITY"}))
        for size in VOLUME_WINDOWS:
            required = 20 + size  # prior-20 median for EACH of the size observations
            rows = list((series or {}).get(tf, []))
            # Technical selected window is authoritative, including latest complete
            # W/M fallback. Never skip an incompatible or missing row inside it.
            rows = [b for b in rows if b["period_start"] <= (c.get("last_observed_session") or "")]
            rows.sort(key=lambda b: (b["period_start"], b["artifact_identity"]))
            window = rows[-required:]
            status, reasons = "INSUFFICIENT_HISTORY", ["CANONICAL_SERIES_NOT_SUPPLIED"]
            proof = {"proof_state": "UNVERIFIABLE"}
            measurements = None
            if rows:
                if len({b["period_start"] for b in rows}) != len(rows):
                    raise ValueError("VOLUME_DUPLICATE_PERIOD")
                for bar in window:
                    verify(bar, "canonical_market_bar")
                    if bar["instrument"]["ticker"] != ticker or bar["timeframe"] != tf:
                        raise ValueError("VOLUME_SERIES_INSTRUMENT_OR_TIMEFRAME_INVALID")
                    if bar["artifact_identity"] not in c["source_bar_identities"]:
                        raise ValueError("VOLUME_SERIES_NOT_BOUND_TO_TECHNICAL_INPUTS")
                if rows[-1]["artifact_identity"] != c.get("canonical_source_bar_identity"):
                    raise ValueError("VOLUME_CANONICAL_TECHNICAL_REFERENCE_MISMATCH")
                status, reasons = technical._gate(window, required, volume=True)
                if tf == "1D":
                    proof = flow_store._prove_continuity([b["last_trading_session"] for b in window],
                        exhaustive_dates=set(exhaustive_dates), registry_dates=frozenset(registry_dates)) if len(window) > 1 else proof
                else:
                    # Existing aggregate gate requires every exact completed constituent.
                    proof = {"proof_state": "PROVEN_CONTINUOUS" if status in USABLE else "UNVERIFIABLE",
                             "source": "GOVERNED_COMPLETE_CANONICAL_PERIODS"}
                    if status in USABLE and any(
                            date.fromisoformat(b["period_start"]) != date.fromisoformat(a["period_end"])+timedelta(days=1)
                            for a,b in zip(window,window[1:])):
                        proof["proof_state"] = "PROVEN_GAP"
                if status in USABLE and proof["proof_state"] != flow_store.PROOF_CONTINUOUS:
                    status, reasons = "BLOCKED_SESSION_CONTINUITY", reasons + [proof["proof_state"]]
                if status in USABLE:
                    ratios = []
                    for i in range(20, len(window)):
                        baseline = statistics.median(b["volume"] for b in window[i-20:i])
                        ratios.append(window[i]["volume"] / baseline if baseline else None)
                    if any(r is None for r in ratios):
                        status, reasons = "NOT_APPLICABLE_ZERO_REFERENCE", ["ZERO_PRIOR_20_MEDIAN"]
                    else:
                        states = [relative_state(r) for r in ratios]
                        half = size // 2
                        old, new = statistics.mean(ratios[:half]), statistics.mean(ratios[-half:])
                        measurements = {"prior_20_relative_ratios": ratios, "sequence": states,
                            "state_counts": dict(sorted(Counter(states).items())),
                            "current_state_streak": next((i for i in range(1, len(states)) if states[-1-i] != states[-1]), len(states)),
                            "trend": "RISING" if new > old else "FALLING" if new < old else "FLAT",
                            "recent_over_prior_mean": new / old if old else None,
                            "acceleration_difference": new-old,
                            "own_history_percentile": sum(r <= ratios[-1] for r in ratios) / size,
                            "method": "PRIOR_20_MEDIAN_PER_OBSERVATION; EQUAL_END_HALVES; OWN_HISTORY_ECDF",
                            "threshold_contract": {"expansion": conventions.EXPANSION_RATIO, "compression": conventions.COMPRESSION_RATIO}}
                if c["freshness"] == "STALE_OR_UNAVAILABLE":
                    reasons = reasons + ["NOT_CURRENT_SESSION"]
                    if status == "AVAILABLE": status = "DESCRIPTIVE_ONLY"
            # Never exceed the released technical family's fitness ceiling.
            if f["status"] not in USABLE:
                status, reasons, measurements = f["status"], f["reason_codes"], None
            # Newly computed trajectories were not sealed merely because their
            # inputs existed then. Only the exact referenced native feature is T0.
            items.append(_item(**{**common, "stage": POST}, sub_domain="RELATIVE_VOLUME_PERSISTENCE", horizon=f"{tf}/{size}",
                semantics="COMPATIBLE_OWN_SERIES_PRIOR_20_MEDIAN_TRAJECTORY", status=status, reasons=reasons,
                actual=len(window), required=required, values=measurements,
                observed_state=(measurements or {}).get("trend", "UNAVAILABLE"),
                relationship=technical_relationship(frame, (measurements or {}).get("trend", "UNAVAILABLE")), continuity=proof))
    return items


def foreign_items(ticker, session, series, *, in_cohort, exhaustive_dates=(), registry_dates=(), velocity_record=None):
    observations = list((series or {}).get("observations", []))
    if any(o.get("session_date", "") > session for o in observations):
        raise ValueError("FOREIGN_FUTURE_OBSERVATION")
    observations.sort(key=lambda o: o["session_date"])
    if len({o["session_date"] for o in observations}) != len(observations):
        raise ValueError("FOREIGN_DUPLICATE_SESSION")
    series = {**(series or {}), "observations": observations}
    source_id = divergence._series_identity(series)
    for o in observations:
        if (o.get("ticker") != ticker or o.get("source") != "DNSE" or
                o.get("source_contract_version") != flow_store.SOURCE_CONTRACT_VERSION or
                o.get("qualification_status") != flow_store.VALUE_QUALIFICATION_STATUS):
            raise ValueError("FOREIGN_VALUE_SEMANTICS_NOT_QUALIFIED")
        buy, sell = o.get("foreign_buy_value_vnd"), o.get("foreign_sell_value_vnd")
        if not all(technical._number(v) and v >= 0 for v in (buy, sell)) or o.get("foreign_net_value_vnd") != buy-sell:
            raise ValueError("FOREIGN_BUY_SELL_NET_IDENTITY_INVALID")
    counts = flow_store._streaks_and_counts(observations, exhaustive_dates=set(exhaustive_dates), registry_dates=frozenset(registry_dates))
    contiguous = observations[-1:] if observations else []
    for observation in reversed(observations[:-1]):
        proof = flow_store._prove_continuity([observation["session_date"],contiguous[0]["session_date"]],
            exhaustive_dates=set(exhaustive_dates),registry_dates=frozenset(registry_dates))
        if proof["proof_state"] != flow_store.PROOF_CONTINUOUS:
            break
        contiguous.insert(0,observation)
    relation = divergence._record(ticker=ticker, reference_session=session, series=series or {}, velocity_record=velocity_record)
    items = []
    for size in FLOW_WINDOWS:
        window = observations[-size:]
        summary = flow_store._window_summary(observations, window_size=size,
            exhaustive_dates=set(exhaustive_dates), registry_dates=frozenset(registry_dates))
        status, reasons = "DESCRIPTIVE_ONLY", ["PROVIDER_SCOPED_VALUE_ONLY_NO_INTENT"]
        if not in_cohort: status, reasons = "UNAVAILABLE", ["OUTSIDE_RETAINED_FOREIGN_COHORT"]
        elif len(window) < size: status, reasons = "INSUFFICIENT_HISTORY", ["INSUFFICIENT_HISTORY"]
        elif size > 1 and summary["coverage"] != "complete":
            status, reasons = "INSUFFICIENT_HISTORY", ["INSUFFICIENT_CONTIGUOUS_HISTORY", "FLOW_WINDOW_" + summary["coverage"].upper()]
        current = bool(observations and observations[-1]["session_date"] == session)
        freshness = "CURRENT_SESSION" if current else "STALE_OR_UNAVAILABLE"
        if not current and observations: reasons += ["NOT_CURRENT_SESSION"]
        values = None
        if status in USABLE:
            nets = [o["foreign_net_value_vnd"] for o in window]
            buy = sum(o["foreign_buy_value_vnd"] for o in window)
            sell = sum(o["foreign_sell_value_vnd"] for o in window)
            gross = buy + sell
            values = {"buy_value_vnd": buy, "sell_value_vnd": sell, "net_value_vnd": buy-sell,
                "gross_value_vnd": gross, "net_over_gross": (buy-sell)/gross if gross else None,
                "ratio_status": "AVAILABLE" if gross else "NOT_APPLICABLE_ZERO_GROSS",
                "mean_net_value_vnd": statistics.mean(nets), "median_net_value_vnd": statistics.median(nets),
                "positive_sessions": sum(v > 0 for v in nets), "negative_sessions": sum(v < 0 for v in nets),
                "neutral_sessions": sum(v == 0 for v in nets),
                "net_buy_streak": min(size, counts["current_consecutive_net_buy_sessions"]),
                "net_sell_streak": min(size, counts["current_consecutive_net_sell_sessions"]),
                "persistence": relation["flow"]["persistence"] if size >= 5 else "ONE_SESSION_OBSERVATION",
                "acceleration_net_difference": statistics.mean(nets[-(size//2):])-statistics.mean(nets[:size//2]) if size > 1 else None,
                "own_history_percentile": sum(v <= nets[-1] for v in nets)/size if size >= 20 else None,
                "percentile_status": "AVAILABLE" if size >= 20 else "INSUFFICIENT_HISTORY",
                "sessions": [o["session_date"] for o in window],
                "foreign_over_total_traded_value": {"status": "BLOCKED", "reason_codes": ["DENOMINATOR_TRADE_TYPE_INCLUSION_UNDOCUMENTED"]}}
        items.append(_item(ticker=ticker, session=session, domain="PARTICIPANT_FLOW", sub_domain="FOREIGN_VALUE",
            horizon=f"1D/{size}", participant="FOREIGN", source={"provider": "DNSE", "contract": flow_store.SOURCE_CONTRACT_VERSION},
            unit={"native": "VND", "derived_ratio": "DIMENSIONLESS"}, semantics="SESSION_CUMULATIVE_FOREIGN_VALUE_TRADE_TYPE_UNDOCUMENTED",
            stage=POST, status=status, reasons=reasons, actual=len(window), required=size,
            freshness=freshness, temporal="POST_HANDOFF_RETAINED_NOT_HISTORICAL_T0", basis="QUALIFIED_VALUE_ONLY",
            scope={"kind": "OBSERVED_FOREIGN_COHORT", "in_cohort": in_cohort,
                "retained_observations_available": len(observations),
                "trailing_contiguous_observations_available": len(contiguous),
                "trailing_contiguous_sessions": [o["session_date"] for o in contiguous]}, source_ids=[source_id],
            values=values, observed_state=relation["flow"]["state"],
            relationship={"state": relation["relationship"], "method_contract": divergence.CONTRACT_VERSION,
                "record_identity": relation["record_identity"], "evidence_quality": relation["evidence_quality"]},
            continuity=summary["continuity_reference"]))
    return items


def unavailable_participant(ticker, session, participant):
    return _item(ticker=ticker, session=session, domain="PARTICIPANT_FLOW", sub_domain="PARTICIPANT_VALUE",
        horizon="1D", participant=participant, source=None, unit={"native": "UNKNOWN"},
        semantics="UNQUALIFIED_PRODUCTION_SOURCE", stage=POST, status="UNAVAILABLE", reasons=["SOURCE_NOT_QUALIFIED"],
        actual=0, required=1, freshness="UNAVAILABLE", temporal="UNAVAILABLE", basis="UNAVAILABLE",
        scope={"kind": "NO_QUALIFIED_PRODUCTION_SERIES"}, source_ids=[])


def aggregates(records, sectors):
    """Partition normalized measurements by exact semantic source; never sum native volume."""
    groups = defaultdict(list)
    foreign = []
    for ticker, row in records.items():
        for item in row["items"]:
            if item["sub_domain"] == "NATIVE_VOLUME_REFERENCE" and item["horizon"] == "1D":
                # A stale observation can describe own history but not current breadth.
                signature = technical.market.canonical([item["source"], item["unit_semantics"], item["basis_fitness"]["volume"], item["measure_semantics"]]).decode()
                groups[signature].append((ticker, item))
            if item["sub_domain"] == "FOREIGN_VALUE" and item["required_observations"] == 1 and item["coverage_scope"]["in_cohort"]:
                foreign.append((ticker, item))
    result = []
    for signature, group in sorted(groups.items()):
        for sector in [None] + sorted({sectors[t] for t, _ in group if t in sectors}):
            cohort = [(t, i) for t, i in group if sector is None or sectors.get(t) == sector]
            eligible = [(t, i) for t, i in cohort if i["status"] in USABLE and i["freshness"] == "CURRENT_SESSION"]
            exclusions = Counter("STALE_OR_UNAVAILABLE" if i["status"] in USABLE else i["status"] for _, i in cohort if (i["status"] not in USABLE or i["freshness"] != "CURRENT_SESSION"))
            expanded = sum(i["observed_state"] == "EXPANSION" for _, i in eligible)
            result.append(seal({"kind": "VOLUME_PARTICIPATION_BREADTH", "scope": "SAME_SEMANTIC_CURRENT_RESEARCH_COHORT",
                "sector": sector, "eligible_universe_definition": "IN_SCOPE_NAMES_WITH_IDENTICAL_SOURCE_UNIT_BASIS_AND_CURRENT_USABLE_TECHNICAL_VOLUME",
                "semantic_signature": signature, "total_cohort_denominator": len(cohort), "eligible_denominator": len(eligible),
                "expansion_numerator": expanded, "expansion_percentage": 100*expanded/len(eligible) if eligible else None,
                "coverage_numerator": len(eligible), "coverage_denominator": len(cohort),
                "coverage_percentage": 100*len(eligible)/len(cohort) if cohort else None,
                "exclusion_reasons": dict(sorted(exclusions.items())), "is_market_representative": False,
                "reason_codes": ["CURRENT_RESEARCH_COHORT_NOT_FULL_ACTIVE_MARKET"],
                "source_item_identities": sorted(i["artifact_identity"] for _, i in cohort)}, "volume_flow_aggregate/v1"))
    qualified = [(t,i) for t,i in foreign if i["status"] in USABLE and i["freshness"] == "CURRENT_SESSION"]
    gross = sum(i["values"]["gross_value_vnd"] for _, i in qualified)
    concentration = [{"ticker": t, "gross_value_vnd": i["values"]["gross_value_vnd"],
        "share_of_observed_cohort_gross": i["values"]["gross_value_vnd"]/gross if gross else None}
        for t,i in sorted(qualified, key=lambda pair: (-pair[1]["values"]["gross_value_vnd"], pair[0]))]
    result.append(seal({"kind": "FOREIGN_FLOW_COHORT_CONTEXT", "scope": "OBSERVED_COHORT_ONLY",
        "eligible_universe_definition": "EXPLICIT_RETAINED_FOREIGN_STORE_COHORT",
        "cohort_tickers": sorted(t for t,_ in foreign), "cohort_denominator": len(foreign),
        "current_qualified_numerator": len(qualified), "coverage_percentage": 100*len(qualified)/len(foreign) if foreign else None,
        "outside_cohort_count": len(records)-len(foreign), "gross_value_vnd": gross if qualified else None,
        "net_value_vnd": sum(i["values"]["net_value_vnd"] for _, i in qualified) if qualified else None,
        "concentration_denominator": "CURRENT_QUALIFIED_OBSERVED_COHORT_GROSS_VALUE_VND", "concentration": concentration,
        "sector_observed_counts": dict(sorted(Counter(sectors.get(t,"UNKNOWN_SECTOR") for t,_ in qualified).items())),
        "exclusion_reasons": dict(sorted(Counter(i["status"] if i["status"] not in USABLE else "STALE_OR_UNAVAILABLE" for _,i in foreign if i["status"] not in USABLE or i["freshness"] != "CURRENT_SESSION").items())),
        "source_item_identities": sorted(i["artifact_identity"] for _,i in foreign), "is_market_representative": False,
        "reason_codes": ["SMALL_COHORT_NOT_FOREIGN_MARKET_OR_SECTOR_BREADTH"]}, "volume_flow_aggregate/v1"))
    return result


def build_artifact(*, session, tickers, technical_contexts, flow_series, canonical_series=None,
                   exhaustive_dates=None, registry_dates=(), sectors=None, velocity_records=None, sealed_snapshot=None,
                   source_artifact_identities=(), prepared_volume_items=None):
    records = {}
    if sealed_snapshot is not None and not isinstance(sealed_snapshot,SealedTechnicalBindings):
        sealed_snapshot = SealedTechnicalBindings(sealed_snapshot)
    universe = sorted(set(tickers))
    if not set(technical_contexts) <= set(universe) or not set(flow_series) <= set(universe):
        raise ValueError("VOLUME_FLOW_INPUT_OUTSIDE_DECLARED_UNIVERSE")
    for ticker in universe:
        if ticker in technical_contexts:
            verify_technical(technical_contexts[ticker], ticker, session)
        items = list(prepared_volume_items[ticker]) if prepared_volume_items is not None and ticker in prepared_volume_items else volume_items(technical_contexts[ticker], series=(canonical_series or {}).get(ticker),
            exhaustive_dates=(exhaustive_dates or {}).get(ticker, ()), registry_dates=registry_dates,
            sealed_snapshot=sealed_snapshot) if ticker in technical_contexts else []
        for item in items:
            verify(item, ITEM_VERSION)
            if (item["instrument"]["ticker"] != ticker or item["session"] != session or
                    item["technical_context_identity"] != technical_contexts[ticker]["artifact_identity"]):
                raise ValueError("VOLUME_PREPARED_ITEM_BINDING_INVALID")
            if item["knowledge_stage"] == T0:
                stage,snapshot_id = _stage(technical_contexts[ticker],sealed_snapshot)
                if (stage != T0 or item["sub_domain"] != "NATIVE_VOLUME_REFERENCE" or
                        snapshot_id not in item["source_artifact_identities"]):
                    raise ValueError("VOLUME_PREPARED_ITEM_NOT_SEALED_T0")
        items += foreign_items(ticker, session, flow_series.get(ticker), in_cohort=ticker in flow_series,
            exhaustive_dates=(exhaustive_dates or {}).get(ticker, ()), registry_dates=registry_dates,
            velocity_record=(velocity_records or {}).get(ticker))
        items += [unavailable_participant(ticker, session, p) for p in PARTICIPANTS[1:]]
        records[ticker] = seal({"ticker": ticker, "session": session, "instrument": {"ticker": ticker},
            "build_stage": POST, "in_current_research_scope": ticker in technical_contexts,
            "technical_context_identity": technical_contexts.get(ticker, {}).get("artifact_identity"),
            "sector": (sectors or {}).get(ticker), "items": items, "non_voting": True}, "volume_flow_instrument/v1")
    return seal({"contract_version": CONTRACT_VERSION, "session": session, "build_stage": POST,
        "source_artifact_identities": sorted(set(source_artifact_identities)), "records": records,
        "universe_denominator": len(universe), "current_research_scope": len(technical_contexts),
        "aggregates": aggregates(records, sectors or {}), "authority_effect": AUTHORITY_EFFECT,
        "no_action_path": True, "historical_t0_rewrite": False, "provider_network_requests": 0})


def t0_projection(artifact):
    """Prospective adapters must project items, never the combined artifact's stage."""
    verify(artifact, CONTRACT_VERSION)
    for row in artifact["records"].values():
        for item in row["items"]:
            if item["knowledge_stage"] == T0 and (item["domain"] != "VOLUME" or item["sub_domain"] != "NATIVE_VOLUME_REFERENCE"):
                raise ValueError("POST_T0_EVIDENCE_CANNOT_ENTER_T0_PROJECTION")
    return {ticker: [item for item in row["items"] if item["knowledge_stage"] == T0 and item["status"] in USABLE]
            for ticker, row in artifact["records"].items()}


def research_reference(artifact, ticker):
    verify(artifact, CONTRACT_VERSION)
    return _research_reference(artifact, ticker)


def _research_reference(artifact, ticker):
    row = artifact["records"][ticker]
    return {"contract_version": CONTRACT_VERSION, "artifact_identity": artifact["artifact_identity"],
        "instrument_context_identity": row["artifact_identity"], "session": artifact["session"],
        "build_stage": POST, "non_voting": True, "allowed_use": "OWNER_RESEARCH_PRESENTATION_ONLY"}


def research_references(artifact):
    """Validate the batch once; owner/AI surfaces can join these compact refs."""
    verify(artifact, CONTRACT_VERSION)
    return {ticker: _research_reference(artifact,ticker) for ticker in artifact["records"]}
