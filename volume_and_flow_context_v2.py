"""Independent participation research over the neutral technical relationship view.

No Technical V2 fields, private technical gate, intent inference or action policy.
Qualified foreign VALUE formulas remain frozen; V2 evidence has its own identities.
"""
from __future__ import annotations
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
import prospective_market_snapshot_contract as market
import canonical_market_bars as bars
import technical_relationship_view as bridge
import contextual_technical_dispatch as dispatch
from contextual_technical_primitives import USABLE, canonical_window_fitness, finite_number
import volume_and_flow_context as frozen
import dnse_foreign_flow_store as flow_store
import flow_price_divergence_shadow as divergence
import technical_structure_context as conventions

CONTRACT_VERSION = "volume_and_flow_context/v2"
ITEM_VERSION = "volume_and_flow_evidence/v2"
AUTHORITY_EFFECT = frozen.AUTHORITY_EFFECT
T0, POST = frozen.T0, frozen.POST
VOLUME_WINDOWS, FLOW_WINDOWS, PARTICIPANTS = frozen.VOLUME_WINDOWS, frozen.FLOW_WINDOWS, frozen.PARTICIPANTS
TIMEFRAMES = ("1D", "1W", "1M")
PARTICIPATION_MEASURES = {"NATIVE_RELATIVE_STATE": bridge.NATIVE_VOLUME_STATES,
    "PRIOR_20_TRAJECTORY_TREND": ("RISING", "FALLING", "FLAT", "UNKNOWN")}
# Every producer value has an explicit consumer entry. Unknown future values fail closed.
CONSUMER_VOCABULARY = {name: {value: value for value in values} for name, values in bridge.VOCABULARY_MANIFEST.items()}
VOCABULARY_MANIFEST = {**bridge.VOCABULARY_MANIFEST, **PARTICIPATION_MEASURES,
    "participation_measure": tuple(PARTICIPATION_MEASURES), "knowledge_stage": (T0, POST),
    "relationship_state": ("DESCRIPTIVE_TECHNICAL_PARTICIPATION_JOIN", "TECHNICAL_CONTEXT_UNAVAILABLE")}
FRESH_TEMPORAL = {"CURRENT_SESSION", "CURRENT_PERIOD_COMPLETED", "IMMEDIATELY_PREVIOUS_COMPLETED_PERIOD"}

def seal(value, kind=CONTRACT_VERSION):
    value.update(market.content_identity(value, kind=kind))
    return value

def verify(value, kind):
    if any(value.get(k) != v for k, v in market.content_identity(value, kind=kind).items()):
        raise ValueError("VOLUME_FLOW_V2_CONTENT_IDENTITY_INVALID:" + kind)

def relative_state(ratio):
    return frozen.relative_state(ratio)

def technical_participation_relationship(view, measure, state, stage):
    bridge.verify_view(view)
    bridge.checked(measure, PARTICIPATION_MEASURES, "participation_measure")
    bridge.checked(state, PARTICIPATION_MEASURES[measure], "participation_state")
    concepts = {}
    for name in ("breakout_relation", "failed_breakout", "pivot_test", "range_consolidation", "trend_reading", "swing_relation", "setup_state"):
        value = view["concepts"][name]
        bridge.checked(value, CONSUMER_VOCABULARY[name], name)
        concepts[name] = {"value": CONSUMER_VOCABULARY[name][value], "pointer": "concepts." + name,
            "evidence_keys": view["evidence_keys"][name]}
    return {"state": "DESCRIPTIVE_TECHNICAL_PARTICIPATION_JOIN" if view["availability"]["structure_status"] in USABLE else "TECHNICAL_CONTEXT_UNAVAILABLE",
        "view_identity": view["view_identity"], "technical_contract_version": view["source"]["technical_contract_version"],
        "concepts": concepts, "participation_measure": measure, "participation_state": state,
        "knowledge_stage": stage, "concept_knowledge_stage": POST if view["source"]["technical_contract_version"] == dispatch.V1 else stage,
        "non_voting": True, "is_actionable": False}

def _item(**kwargs):
    relationship = kwargs.pop("relationship", None)
    measure = kwargs.pop("participation_measure", None)
    state = kwargs.pop("participation_state", None)
    keys = kwargs.pop("evidence_keys", None)
    item = frozen._item(**kwargs)
    item.pop("technical_relationship")
    for key in ("artifact_identity", "artifact_sha256"): item.pop(key, None)
    item.update(contract_version=ITEM_VERSION, technical_participation_relationship=relationship,
        participation_measure=measure, participation_state=state, evidence_keys=keys)
    return seal(item, ITEM_VERSION)

class SealedTechnicalBindings:
    def __init__(self, snapshot):
        import prospective_decision_retention as retention
        if not retention.validate_snapshot(snapshot): raise ValueError("VOLUME_SEALED_SNAPSHOT_INVALID")
        self.snapshot_identity = snapshot["snapshot_identity"]
        self.bindings = {}
        for ticker, row in snapshot["records"].items():
            projection = ((row.get("integrated_decision_at_t0") or {}).get("contextual_technical_context") or {}).get("projection")
            if projection:
                version = dispatch.verify_context(projection, ticker=ticker, session=row["decision_session"])
                self.bindings[ticker] = (row["decision_session"], version, projection["artifact_identity"])

def _stage(view, sealed_snapshot):
    if sealed_snapshot is not None and not isinstance(sealed_snapshot, SealedTechnicalBindings):
        sealed_snapshot = SealedTechnicalBindings(sealed_snapshot)
    expected = (view["as_of_session"], dispatch.V2, view["source"]["context_identity"])
    if (view["as_of_session"] >= dispatch.PRODUCTION_V2_START_SESSION and
        view["source"]["technical_contract_version"] == dispatch.V2 and sealed_snapshot is not None and
        sealed_snapshot.bindings.get(view["instrument"]["ticker"]) == expected):
        return T0, sealed_snapshot.snapshot_identity, []
    return POST, None, ["TECHNICAL_IDENTITY_NOT_SEALED_IN_T0"]

def volume_items(views, *, series=None, exhaustive_dates=(), registry_dates=(), sealed_snapshot=None):
    verify_views(views, views["1D"]["instrument"]["ticker"], views["1D"]["as_of_session"])
    items = []
    for tf in TIMEFRAMES:
        view = bridge.verify_view(views[tf])
        ticker, session = view["instrument"]["ticker"], view["as_of_session"]
        if view["timeframe"] != tf: raise ValueError("VOLUME_VIEW_TIMEFRAME_INVALID")
        c, f, native = view["source"], view["availability"], view["concepts"]["native_volume_reference"]
        stage, t0_id, seal_reasons = _stage(view, sealed_snapshot)
        temporal = view["fitness"]["temporal"]["state"]
        fresh = temporal in FRESH_TEMPORAL
        stale_reasons = [] if fresh else [temporal]
        common = dict(ticker=ticker, session=session, domain="VOLUME", participant=None,
            source=c.get("provider"), unit={"native": view["fitness"].get("volume_unit") or "UNKNOWN", "derived": "DIMENSIONLESS"},
            stage=stage, freshness="CURRENT_SESSION" if tf == "1D" and fresh else "FRESH_COMPLETED_PERIOD" if fresh else "STALE_OR_UNAVAILABLE",
            temporal=temporal, basis={"price": view["fitness"]["price_basis"], "volume": view["fitness"]["volume_basis"],
                "corporate_actions": view["fitness"]["corporate_action_comparability"]},
            scope={"kind": "OWN_HISTORY", "ticker": ticker, "timeframe": tf, "fresh_participation_eligible": fresh},
            source_ids=[c["context_identity"], c["frame_identity"], view["view_identity"]] + ([t0_id] if t0_id else []),
            technical_id=c["context_identity"], evidence_keys=view["evidence_keys"]["native_volume_reference"])
        state = native["state"]
        items.append(_item(**common, sub_domain="NATIVE_VOLUME_REFERENCE", horizon=tf,
            semantics="EXACT_TECHNICAL_FEATURE_REFERENCE_LAST_20_INCLUDING_CURRENT_NOT_CROSS_SECTIONAL",
            status=f["volume_status"], reasons=native["reason_codes"] + seal_reasons + stale_reasons,
            actual=native["actual_available_lookback"], required=native["required_lookback"], observed_state=state,
            participation_measure="NATIVE_RELATIVE_STATE", participation_state=state,
            values={"feature_path": native["feature_pointer"], "feature_identity": c["frame_identity"],
                "view_identity": view["view_identity"], "window_basis": native["window_basis"], "relative_to_median": native["relative_to_median"]},
            relationship=technical_participation_relationship(view, "NATIVE_RELATIVE_STATE", state, stage),
            continuity={"state": "INHERITS_TECHNICAL_FITNESS_NOT_SESSION_MATURITY"}))
        for size in VOLUME_WINDOWS:
            required = 20 + size
            selected_period = view["fitness"]["temporal"].get("selected_period")
            rows = sorted([b for b in (series or {}).get(tf, []) if
                c["canonical_source_bar_identity"] and selected_period and b["period_start"] <= selected_period["start"]],
                key=lambda b: (b["period_start"], b["artifact_identity"]))
            window = rows[-required:]
            status, reasons, measurements = "INSUFFICIENT_HISTORY", ["CANONICAL_SERIES_NOT_SUPPLIED"], None
            proof = {"proof_state": "UNVERIFIABLE"}
            if rows:
                if len({b["period_start"] for b in rows}) != len(rows): raise ValueError("VOLUME_DUPLICATE_PERIOD")
                for bar in window:
                    verify(bar, "canonical_market_bar")
                    if bar["instrument"]["ticker"] != ticker or bar["timeframe"] != tf: raise ValueError("VOLUME_SERIES_SCOPE_INVALID")
                    if bar["artifact_identity"] not in c["source_bar_identities"]: raise ValueError("VOLUME_SERIES_NOT_BOUND_TO_VIEW")
                if rows[-1]["artifact_identity"] != c["canonical_source_bar_identity"]: raise ValueError("VOLUME_CANONICAL_VIEW_REFERENCE_MISMATCH")
                status, reasons = canonical_window_fitness(window, required, volume=True)
                if tf == "1D":
                    observed_dates = [b.get("last_trading_session") for b in window]
                    if len(window) > 1 and all(isinstance(day, str) for day in observed_dates):
                        proof = flow_store._prove_continuity(observed_dates,
                            exhaustive_dates=set(exhaustive_dates), registry_dates=frozenset(registry_dates))
                    else:
                        proof = {"proof_state": "UNVERIFIABLE", "reason": "CANONICAL_OBSERVATION_SESSION_UNAVAILABLE"}
                else:
                    proof = {"proof_state": "PROVEN_CONTINUOUS" if status in USABLE else "UNVERIFIABLE", "source": "GOVERNED_COMPLETE_CANONICAL_PERIODS"}
                    if status in USABLE and any(date.fromisoformat(b["period_start"]) != date.fromisoformat(a["period_end"])+timedelta(days=1) for a,b in zip(window,window[1:])):
                        proof["proof_state"] = "PROVEN_GAP"
                if status in USABLE and proof["proof_state"] != flow_store.PROOF_CONTINUOUS:
                    status, reasons = "BLOCKED_SESSION_CONTINUITY", reasons + [proof["proof_state"]]
                if status in USABLE:
                    ratios = []
                    for i in range(20, len(window)):
                        baseline = statistics.median(b["volume"] for b in window[i-20:i])
                        ratios.append(window[i]["volume"] / baseline if baseline else None)
                    if any(r is None for r in ratios): status, reasons = "NOT_APPLICABLE_ZERO_REFERENCE", ["ZERO_PRIOR_20_MEDIAN"]
                    else:
                        states = [relative_state(r) for r in ratios]
                        half = size // 2
                        old_mean, new_mean = statistics.mean(ratios[:half]), statistics.mean(ratios[-half:])
                        measurements = {"prior_20_relative_ratios": ratios, "sequence": states, "state_counts": dict(sorted(Counter(states).items())),
                            "current_state_streak": next((i for i in range(1, len(states)) if states[-1-i] != states[-1]), len(states)),
                            "trend": "RISING" if new_mean > old_mean else "FALLING" if new_mean < old_mean else "FLAT",
                            "recent_over_prior_mean": new_mean / old_mean if old_mean else None, "acceleration_difference": new_mean-old_mean,
                            "own_history_percentile": sum(r <= ratios[-1] for r in ratios) / size,
                            "method": "PRIOR_20_MEDIAN_PER_OBSERVATION; EQUAL_END_HALVES; OWN_HISTORY_ECDF",
                            "threshold_contract": {"expansion": conventions.EXPANSION_RATIO, "compression": conventions.COMPRESSION_RATIO}}
            if f["volume_status"] not in USABLE: status, reasons, measurements = f["volume_status"], native["reason_codes"], None
            if not fresh and status in USABLE: status = "DESCRIPTIVE_ONLY"
            state = (measurements or {}).get("trend", "UNKNOWN")
            items.append(_item(**{**common, "stage": POST, "source_ids": [c["context_identity"], c["frame_identity"], view["view_identity"]],
                "evidence_keys": bridge.evidence_keys(ticker, session, tf, c["canonical_source_bar_identity"], "prior_20_trajectory/"+str(size), "NATIVE_VOLUME_SERIES")},
                sub_domain="RELATIVE_VOLUME_PERSISTENCE", horizon=f"{tf}/{size}", semantics="COMPATIBLE_OWN_SERIES_PRIOR_20_MEDIAN_TRAJECTORY",
                status=status, reasons=reasons + stale_reasons, actual=len(window), required=required, values=measurements, observed_state=state,
                participation_measure="PRIOR_20_TRAJECTORY_TREND", participation_state=state,
                relationship=technical_participation_relationship(view, "PRIOR_20_TRAJECTORY_TREND", state, POST), continuity=proof))
    return items

def foreign_items(*args, **kwargs):
    result = []
    for original in frozen.foreign_items(*args, **kwargs):
        value = {k: v for k, v in original.items() if k not in {"artifact_identity", "artifact_sha256", "technical_relationship"}}
        ticker, session = value["instrument"]["ticker"], value["session"]
        value.update(contract_version=ITEM_VERSION, technical_participation_relationship=None,
            price_flow_relationship=original["technical_relationship"], participation_measure=None, participation_state=None,
            evidence_keys=bridge.evidence_keys(ticker, session, "1D", value["source_artifact_identities"][0], "foreign_value/"+value["horizon"], "FOREIGN_VALUE_SERIES"))
        result.append(seal(value, ITEM_VERSION))
    return result

def unavailable_participant(ticker, session, participant):
    value = {k: v for k, v in frozen.unavailable_participant(ticker, session, participant).items() if k not in {"artifact_identity", "artifact_sha256", "technical_relationship"}}
    value.update(contract_version=ITEM_VERSION, technical_participation_relationship=None, participation_measure=None, participation_state=None, evidence_keys=None)
    return seal(value, ITEM_VERSION)

def aggregates(records, sectors):
    """Partition normalized measurements by exact semantic source; never sum native volume."""
    groups = defaultdict(list)
    foreign = []
    for ticker, row in records.items():
        for item in row["items"]:
            if item["sub_domain"] == "NATIVE_VOLUME_REFERENCE":
                # A stale observation can describe own history but not current breadth.
                signature = market.canonical([item["horizon"], item["source"], item["unit_semantics"], item["basis_fitness"]["volume"], item["measure_semantics"]]).decode()
                groups[signature].append((ticker, item))
            if item["sub_domain"] == "FOREIGN_VALUE" and item["required_observations"] == 1 and item["coverage_scope"]["in_cohort"]:
                foreign.append((ticker, item))
    result = []
    for signature, group in sorted(groups.items()):
        for sector in [None] + sorted({sectors[t] for t, _ in group if t in sectors}):
            cohort = [(t, i) for t, i in group if sector is None or sectors.get(t) == sector]
            eligible = [(t, i) for t, i in cohort if i["status"] in USABLE and i["temporal_fitness"] in FRESH_TEMPORAL]
            exclusions = Counter("STALE_OR_UNAVAILABLE" if i["status"] in USABLE else i["status"] for _, i in cohort if (i["status"] not in USABLE or i["temporal_fitness"] not in FRESH_TEMPORAL))
            expanded = sum(i["observed_state"] == "EXPANSION" for _, i in eligible)
            result.append(seal({"kind": "VOLUME_PARTICIPATION_BREADTH", "scope": "SAME_SEMANTIC_CURRENT_RESEARCH_COHORT",
                "sector": sector, "timeframe": cohort[0][1]["horizon"], "eligible_universe_definition": "IN_SCOPE_NAMES_WITH_IDENTICAL_SOURCE_UNIT_BASIS_AND_CURRENT_USABLE_TECHNICAL_VOLUME",
                "semantic_signature": signature, "total_cohort_denominator": len(cohort), "eligible_denominator": len(eligible),
                "expansion_numerator": expanded, "expansion_percentage": 100*expanded/len(eligible) if eligible else None,
                "coverage_numerator": len(eligible), "coverage_denominator": len(cohort),
                "coverage_percentage": 100*len(eligible)/len(cohort) if cohort else None,
                "exclusion_reasons": dict(sorted(exclusions.items())), "is_market_representative": False,
                "reason_codes": ["CURRENT_RESEARCH_COHORT_NOT_FULL_ACTIVE_MARKET"],
                "source_item_identities": sorted(i["artifact_identity"] for _, i in cohort)}, "volume_flow_aggregate/v2"))
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
        "reason_codes": ["SMALL_COHORT_NOT_FOREIGN_MARKET_OR_SECTOR_BREADTH"]}, "volume_flow_aggregate/v2"))
    return result


def verify_views(views, ticker, session):
    if set(views) != set(TIMEFRAMES): raise ValueError("VOLUME_VIEW_TIMEFRAMES_INVALID")
    versions, ids = set(), set()
    for tf, view in views.items():
        bridge.verify_view(view)
        if view["instrument"]["ticker"] != ticker or view["as_of_session"] != session or view["timeframe"] != tf:
            raise ValueError("VOLUME_VIEW_SCOPE_INVALID")
        versions.add(view["source"]["technical_contract_version"])
        ids.add(view["source"]["context_identity"])
    if len(versions) != 1: raise ValueError("TECHNICAL_VERSION_MIXED")
    if len(ids) != 1: raise ValueError("VOLUME_VIEW_CONTEXT_IDENTITY_MIXED")
    return next(iter(versions))

def build_artifact(*, session, tickers, relationship_views, flow_series, canonical_series=None,
    exhaustive_dates=None, registry_dates=(), sectors=None, velocity_records=None, sealed_snapshot=None,
    source_artifact_identities=(), prepared_volume_items=None, allow_legacy_bridge=False):
    universe, records = sorted(set(tickers)), {}
    if not set(relationship_views) <= set(universe) or not set(flow_series) <= set(universe): raise ValueError("VOLUME_FLOW_INPUT_OUTSIDE_DECLARED_UNIVERSE")
    versions = {verify_views(v, t, session) for t, v in relationship_views.items()}
    if len(versions) > 1: raise ValueError("TECHNICAL_VERSION_MIXED")
    version = next(iter(versions), dispatch.V2)
    if version == dispatch.V1 and not allow_legacy_bridge: raise ValueError("V1_TO_V2_BRIDGE_REQUIRES_EXPLICIT_DIAGNOSTIC")
    if sealed_snapshot is not None and not isinstance(sealed_snapshot, SealedTechnicalBindings): sealed_snapshot = SealedTechnicalBindings(sealed_snapshot)
    for ticker in universe:
        views = relationship_views.get(ticker)
        items = list(prepared_volume_items[ticker]) if prepared_volume_items is not None and ticker in prepared_volume_items else volume_items(views,
            series=(canonical_series or {}).get(ticker), exhaustive_dates=(exhaustive_dates or {}).get(ticker, ()), registry_dates=registry_dates,
            sealed_snapshot=sealed_snapshot) if views else []
        for item in items:
            verify(item, ITEM_VERSION)
            tf = item["horizon"].split("/")[0]
            relation = item.get("technical_participation_relationship") or {}
            if (not views or item["instrument"]["ticker"] != ticker or item["session"] != session or
                item["technical_context_identity"] != views[tf]["source"]["context_identity"] or relation.get("view_identity") != views[tf]["view_identity"]):
                raise ValueError("VOLUME_PREPARED_ITEM_BINDING_INVALID")
            bridge.checked(item["participation_measure"], PARTICIPATION_MEASURES, "participation_measure")
            bridge.checked(item["participation_state"], PARTICIPATION_MEASURES[item["participation_measure"]], "participation_state")
            if item["knowledge_stage"] == T0:
                stage, snapshot_id, _ = _stage(views[tf], sealed_snapshot)
                if stage != T0 or item["sub_domain"] != "NATIVE_VOLUME_REFERENCE" or snapshot_id not in item["source_artifact_identities"]:
                    raise ValueError("VOLUME_PREPARED_ITEM_NOT_SEALED_T0")
        items += foreign_items(ticker, session, flow_series.get(ticker), in_cohort=ticker in flow_series,
            exhaustive_dates=(exhaustive_dates or {}).get(ticker, ()), registry_dates=registry_dates, velocity_record=(velocity_records or {}).get(ticker))
        items += [unavailable_participant(ticker, session, p) for p in PARTICIPANTS[1:]]
        records[ticker] = seal({"ticker": ticker, "session": session, "instrument": {"ticker": ticker}, "build_stage": POST,
            "in_current_research_scope": views is not None, "technical_contract_version": version if views else None,
            "technical_context_identity": views["1D"]["source"]["context_identity"] if views else None,
            "relationship_view_identities": {tf: v["view_identity"] for tf, v in (views or {}).items()},
            "sector": (sectors or {}).get(ticker), "items": items, "non_voting": True}, "volume_flow_instrument/v2")
    return seal({"contract_version": CONTRACT_VERSION, "session": session, "build_stage": POST, "technical_contract_version": version,
        "source_artifact_identities": sorted(set(source_artifact_identities)), "records": records, "universe_denominator": len(universe),
        "current_research_scope": len(relationship_views), "aggregates": aggregates(records, sectors or {}), "authority_effect": AUTHORITY_EFFECT,
        "no_action_path": True, "historical_t0_rewrite": False, "provider_network_requests": 0,
        "evaluation_scope": "REPLAY_DIAGNOSTIC_NON_AUTHORITATIVE" if allow_legacy_bridge or session < dispatch.PRODUCTION_V2_START_SESSION else "CURRENT_RESEARCH_DESCRIPTIVE"})

def t0_projection(artifact):
    verify(artifact, CONTRACT_VERSION)
    result = {}
    for ticker, row in artifact["records"].items():
        selected = []
        for item in row["items"]:
            verify(item, ITEM_VERSION)
            if item["knowledge_stage"] == T0:
                if (item["domain"] != "VOLUME" or item["sub_domain"] != "NATIVE_VOLUME_REFERENCE" or
                    (item.get("technical_participation_relationship") or {}).get("technical_contract_version") != dispatch.V2 or
                    "TECHNICAL_IDENTITY_NOT_SEALED_IN_T0" in item["reason_codes"]):
                    raise ValueError("POST_T0_EVIDENCE_CANNOT_ENTER_T0_PROJECTION")
                if item["status"] in USABLE: selected.append(item)
        result[ticker] = selected
    return result

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
