"""Retained-only, indexed source adapter for the independent research context.

Each large price/history corpus is parsed once. Canonical bars are bounded to one
ticker at a time. The producer accepts explicit roots; never discovers providers.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import canonical_market_bars as bars
import daily_session_level2_package as level2
import dnse_foreign_flow_store as store
import market_wide_historical_research_context as history
import volume_and_flow_context_v2 as context
import contextual_technical_dispatch as dispatch
import technical_relationship_view as bridge
from bounded_artifact_stream import header, source_hash, stream_artifact
from daily_session_completion_reference import load_qualified_completed_sessions


def trading_date_index(runtime_root):
    path = Path(runtime_root) / "vn_stock.db"
    dates = defaultdict(set)
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=1")
            for ticker, day in conn.execute("SELECT DISTINCT ticker, date FROM ohlcv"):
                dates[ticker].add(day)
    return dates


def flow_index(runtime_root, session, dates, registry_dates, calendar_evidence=None):
    result = {}
    for path in sorted(store.observations_root(runtime_root).glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        ticker = path.stem.upper()
        raw = payload.get("observations", [])
        # Values only; reported shares never enter the analytical index.
        for row in raw:
            if (row.get("value_unit") != "vnd" or row.get("source") != "DNSE" or
                    row.get("source_contract_version") != store.SOURCE_CONTRACT_VERSION or row.get("ticker") != ticker):
                raise ValueError("RETAINED_FOREIGN_SOURCE_SEMANTICS_INVALID")
        observations = sorted([store._value_observation(row) for row in raw if row["session_date"] <= session], key=lambda o:o["session_date"])
        if not observations:
            continue
        counts = store._streaks_and_counts(observations, exhaustive_dates=dates.get(ticker,set()), registry_dates=registry_dates, calendar_evidence=calendar_evidence)
        result[ticker] = {"schema_version": store.SERIES_SCHEMA_VERSION, "ticker": ticker,
            "status": store.STATUS_AVAILABLE, "source": "DNSE", "source_contract_version": store.SOURCE_CONTRACT_VERSION,
            "observations": observations, "latest_session": observations[-1],
            "freshness": store._freshness(observations[-1]["session_date"], session, dates.get(ticker,set())),
            **counts, "window_summaries": {f"{n}_session": store._window_summary(observations, window_size=n,
                exhaustive_dates=dates.get(ticker,set()), registry_dates=registry_dates, calendar_evidence=calendar_evidence) for n in (5,10)}}
    return result


def collect(*, source_root, runtime_root, session, feature_batch=None, feature_batch_sha256=None,
            velocity_artifact=None, sealed_snapshot=None, allow_legacy_bridge=False):
    root = Path(source_root)
    paths = level2.session_artifact_paths(root, session)
    paths = {k: paths[k] for k in ("exact_session_snapshot", "universe_resolution", "technical_recovery")}
    paths["input_registry"] = root / "config/daily_research_session_input_registry.json"
    registry = json.loads(paths["input_registry"].read_text(encoding="utf-8"))
    binding = registry["sessions"][session]
    paths["events"] = root / binding["event_context"]["path"]
    paths["descriptive"] = root / binding["descriptive"]["path"]
    paths["calendar"] = root / "config/governed_trading_session_calendar_v1.json"
    paths.update({"flow_"+p.stem: p for p in store.observations_root(runtime_root).glob("*.json")})
    db = Path(runtime_root)/"vn_stock.db"
    if db.exists(): paths["trading_date_reference"] = db
    if feature_batch:
        if not feature_batch_sha256: raise ValueError("FEATURE_BATCH_HASH_REQUIRED")
        paths["technical_batch"] = Path(feature_batch)
        if source_hash(paths["technical_batch"]) != feature_batch_sha256:
            raise ValueError("FEATURE_BATCH_HASH_INVALID")
    else:
        paths["technical_batch"] = root / "operations-review/canonical-post-close-v1" / session / "enrichment/historical_context.json"
    before = {k: source_hash(p) for k,p in paths.items()}
    universe = json.loads(paths["universe_resolution"].read_text(encoding="utf-8"))
    history._verify_hashed_identity(universe, label="VOLUME_UNIVERSE")
    recovery = json.loads(paths["technical_recovery"].read_text(encoding="utf-8"))
    history._verify_hashed_identity(recovery, label="VOLUME_RECOVERY")
    source_header = header(paths["exact_session_snapshot"])
    if source_header["resolved_completed_session"] != session or recovery["source_lineage"]["p3f9b_snapshot_identity"] != source_header["snapshot_identity"]:
        raise ValueError("VOLUME_RETAINED_SOURCE_SESSION_MISMATCH")
    calendar = bars.governed_calendar_projection(json.loads(paths["calendar"].read_text(encoding="utf-8")))
    events_artifact = json.loads(paths["events"].read_text(encoding="utf-8"))
    import current_official_event_context as event_module
    if (any(events_artifact.get(k) != v for k,v in event_module._identity(events_artifact).items()) or
            events_artifact["artifact_identity"] != binding["event_context"]["artifact_identity"]):
        raise ValueError("VOLUME_EVENT_BINDING_INVALID")
    events = defaultdict(list)
    for row in events_artifact["records"].values():
        for event in row.get("events",[]): events[event["ticker"]].append(event)
    technical = {}
    if feature_batch:
        with paths["technical_batch"].open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                if row["ticker"] in technical: raise ValueError("FEATURE_BATCH_DUPLICATE_TICKER")
                technical[row["ticker"]] = row["contextual_technical"]
    else:
        meta, digest, _ = stream_artifact(paths["technical_batch"], excluded={"artifact_identity","artifact_sha256"},
            on_record=lambda t,r:technical.update({t:r["contextual_technical"]}) if "contextual_technical" in r else None)
        if digest != meta["artifact_sha256"] or meta["session"] != session:
            raise ValueError("VOLUME_HISTORICAL_CONTEXT_IDENTITY_INVALID")
        if not technical: raise ValueError("RETAINED_CONTEXTUAL_TECHNICAL_FEATURES_ABSENT")
    version = dispatch.verify_batch(technical, session=session)
    expected_scope = {t for t,r in universe["records"].items() if r["activity_and_session_state"] in history.IN_SCOPE_ACTIVITY_STATES}
    if set(technical) != expected_scope: raise ValueError("VOLUME_TECHNICAL_SCOPE_MISMATCH")
    # Pair by the retained batch's actual contract, including historical imports.
    if version == dispatch.V1 and not allow_legacy_bridge:
        import volume_and_flow_context as producer
    else:
        producer = context
    v2_consumer = version == dispatch.V2 or allow_legacy_bridge
    if v2_consumer:
        from prospective_pit_capture_retention import calendar_evidence_at_cutoff
        calendar = calendar_evidence_at_cutoff(root, cutoff=source_header["requested_at"])
    if sealed_snapshot is not None and not (producer._is_sealed_bindings(sealed_snapshot) if v2_consumer else isinstance(sealed_snapshot, producer.SealedTechnicalBindings)):
        sealed_snapshot = producer.SealedTechnicalBindings(sealed_snapshot)
    views = {t: bridge.build_views(c) for t,c in technical.items()} if v2_consumer else technical
    dates = trading_date_index(runtime_root)
    registry_dates = load_qualified_completed_sessions(paths["input_registry"])
    flow = flow_index(runtime_root, session, dates, registry_dates, calendar if v2_consumer else None)
    prepared, tickers = {}, set()
    def price_record(ticker, row):
        tickers.add(ticker)
        if ticker not in technical: return
        override = recovery.get("recovered_history_overrides", {}).get(ticker,{})
        recovered = override.get("state") == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
        observations = override.get("observations",[]) if recovered else row.get("observations",[])
        series = bars.research_series(observations,ticker=ticker,target_session=session,
            knowledge_cutoff=source_header["requested_at"], source_identity=recovery["artifact_identity"] if recovered else source_header["snapshot_identity"],
            calendar_evidence=calendar, ca_events=events[ticker])
        prepared[ticker] = producer.volume_items(views[ticker],series=series,exhaustive_dates=dates.get(ticker,()),
            registry_dates=registry_dates,sealed_snapshot=sealed_snapshot, **({"calendar_evidence": calendar} if v2_consumer else {}))
        if len(prepared)%200 == 0: print("VOLUME_CONTEXT",len(prepared),flush=True)
    meta, digest, count = stream_artifact(paths["exact_session_snapshot"], excluded={"snapshot_identity","snapshot_sha256"},on_record=price_record,sanitize=True)
    if digest != source_header["snapshot_sha256"] or tickers != set(universe["records"]):
        raise ValueError("VOLUME_PRICE_CORPUS_IDENTITY_OR_DENOMINATOR_INVALID")
    sectors = {}
    def sector_record(t,r):
        classification = r.get("sector_classification") or {}
        # Same classification tuple as current_market_sector_leadership_context.
        import current_market_sector_leadership_context as leadership
        key = leadership._classification_key(r)
        if key is not None: sectors[t] = "|".join(key)
    descriptive_meta, descriptive_digest, _ = stream_artifact(paths["descriptive"], excluded={"artifact_identity","artifact_sha256"},on_record=sector_record)
    if descriptive_digest != descriptive_meta["artifact_sha256"] or descriptive_meta["artifact_identity"] != binding["descriptive"]["artifact_identity"]:
        raise ValueError("VOLUME_SECTOR_CLASSIFICATION_SOURCE_INVALID")
    exclusions = {}
    velocity = context.divergence.accept_velocity_for_flow(velocity_artifact, reference_session=session,
        exclusions=exclusions) if velocity_artifact else {}

    paired_inputs = {"relationship_views": views, "allow_legacy_bridge": allow_legacy_bridge, "calendar_evidence": calendar} if v2_consumer else {"technical_contexts": technical}
    artifact = producer.build_artifact(session=session,tickers=tickers,**paired_inputs,flow_series=flow,
        exhaustive_dates=dates,registry_dates=registry_dates,sectors=sectors,velocity_records=velocity,
        source_artifact_identities=[source_header["snapshot_identity"], recovery["artifact_identity"],
            universe["artifact_identity"], events_artifact["artifact_identity"], descriptive_meta["artifact_identity"]],
        prepared_volume_items=prepared,sealed_snapshot=sealed_snapshot)
    if velocity_artifact:
        artifact["velocity_compatibility"] = {"source_artifact_identity": velocity_artifact.get("artifact_identity"),
            "record_exclusions": exclusions, "non_voting": True}
        producer.seal(artifact)
    if before != {k:source_hash(p) for k,p in paths.items()}: raise ValueError("VOLUME_RETAINED_SOURCE_BYTES_CHANGED")
    return artifact, {"source_hashes": before, "source_bytes_unchanged": True, "velocity_record_exclusions": exclusions,
        "input_bytes_parsed": sum(p.stat().st_size for k,p in paths.items() if k != "trading_date_reference"),
        "price_corpora_parsed": 1, "technical_batches_parsed": 1,
        "foreign_sessions": {t:[o["session_date"] for o in s["observations"]] for t,s in flow.items()},
        "technical_identities": {t:c["artifact_identity"] for t,c in technical.items()},
        "canonical_series_peak_scope": "ONE_INSTRUMENT", "universe_denominator": count}
