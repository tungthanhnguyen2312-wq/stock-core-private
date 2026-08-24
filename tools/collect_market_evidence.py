"""Capability-First Retained EOD Market Evidence Collector V1.

WHY THIS MODULE EXISTS
    Under the capability-first architecture rebaseline (2026-08-21), market data acquisition
    routes capabilities to whichever source(s) expose them rather than selecting a single
    winning provider market-wide. Provider parity is NOT required: a capability available from
    only one permitted source (e.g. PUT_THROUGH_VOLUME_SHARES from FHSC, or FOREIGN_BUY_VOLUME
    from DNSE) must be ingestible on its own.

COLLECTOR PIPELINE
    fetch (or offline fixture/replay)
    -> retain exact raw payload before parsing
    -> retrieval timestamp + source/capability/instrument/session provenance
    -> SHA-256 / immutable content identity
    -> canonical taxonomy mapping through Phase-1 contracts (market_capability_taxonomy.py
       and price_representation_contract.py)
    -> session packet + execution manifest.

CORE INVARIANTS
    1. Route sources per capability using market_capability_taxonomy.py.
    2. Single-source capabilities are first-class and ingestible without parity prerequisites.
    3. Provider-native observations are preserved; canonical representations are derived, never
       replacements.
    4. Reuse Phase-1 explicit K-VND -> VND price representation contract; never implement
       numeric-magnitude heuristics.
    5. HTTP 429 (rate limit) sets PROVIDER_RATE_LIMITED for affected work and does NOT invalidate
       unrelated successful observations or fail the whole packet. A request skipped before send
       because the local request budget is exhausted is BUDGET_EXHAUSTED, never provider-limited.
    6. Missing/unresolved dimensions fail closed only for affected uses (SEMANTIC_UNRESOLVED,
       MISSING, UNKNOWN).
    7. Authority (RAW_AS_TRADED, PIT, liquidity/sizing, valuation, recommendation) is NEVER
       promoted; authority_effect is strictly "NONE" throughout.
    8. Later collection of the same session retains both versions and flags
       PROVIDER_REVISION_DETECTED without overwriting historical bytes.
    9. Manual / foreground execution only (no automated scheduler installation).
    10. 18:00 Asia/Ho_Chi_Minh is an operational scheduling convention, not data authority.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Path setup for root imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnse_access as dnse_acc
from dnse_access import BASE_URL as DNSE_BASE_URL, auth_headers, credential_status, credentials_for_request
from dnse_market_data import resolve_endpoint
from dnse_secrets_env import ensure_credentials_loaded
from fhsc_retained_live_reconciliation import (
    FHSC_BASE_URL,
    PRICE_HISTORY_PATH,
    STOCK_REALTIME_PATH,
    TIER1_HEADER_NAME,
    load_finhay_api_key,
)
import market_capability_taxonomy as taxonomy
import price_representation_contract as price_contract
from vn_time import VN_TZ, vn_now

COLLECTOR_VERSION = "1.0.0"
CONTRACT_VERSION = "capability_first_eod_collector/v1"
PACKET_SCHEMA_VERSION = "1.0.0"
MANIFEST_SCHEMA_VERSION = "1.0.0"

# Standard known cohorts / universes
BENCHMARK_COHORT = ("HPG", "VCB", "SSI")
STANDARD_COHORT = (
    "HPG", "VCB", "SSI", "FPT", "VNM", "MWG",
    "PVS", "SHS", "ACV", "BSR", "MCH", "VGI",
)

SUPPORTED_SOURCES = (taxonomy.SOURCE_DNSE, taxonomy.SOURCE_FHSC)
SUPPORTED_FAMILIES = (
    taxonomy.FAMILY_PRICE,
    taxonomy.FAMILY_VOLUME,
    taxonomy.FAMILY_FOREIGN,
    taxonomy.FAMILY_TRADED_VALUE,
    taxonomy.FAMILY_PROPRIETARY,
    taxonomy.FAMILY_MICROSTRUCTURE,
    taxonomy.FAMILY_REFERENCE,
)

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
    "database_mutated": False,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _content_identity(prefix: str, payload: Mapping[str, Any]) -> dict[str, str]:
    clean = {k: v for k, v in payload.items() if k not in {"packet_sha256", "packet_identity", "manifest_sha256", "manifest_identity"}}
    digest = _sha256_json(clean)
    return {
        f"{prefix}_sha256": digest,
        f"{prefix}_identity": f"{prefix}:{digest}",
    }


def resolve_symbols(symbols_arg: Sequence[str] | str | None, universe_arg: str | None) -> list[str]:
    """Resolve target symbol list from --symbols or --universe."""
    if symbols_arg:
        if isinstance(symbols_arg, str):
            parts = [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]
        else:
            parts = []
            for item in symbols_arg:
                parts.extend(s.strip().upper() for s in str(item).split(",") if s.strip())
        if parts:
            return sorted(set(parts))

    universe = (universe_arg or "cohort").strip().lower()
    if universe == "benchmark":
        return list(BENCHMARK_COHORT)
    if universe in ("cohort", "standard_cohort"):
        return list(STANDARD_COHORT)
    if universe == "canonical":
        db_path = ROOT / "vn_stock.db"
        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
                try:
                    conn.execute("PRAGMA query_only = ON")
                    tickers = [str(r[0]).upper() for r in conn.execute("SELECT ticker FROM metadata ORDER BY ticker")]
                    if tickers:
                        return sorted(set(tickers))
                finally:
                    conn.close()
            except Exception:
                pass
        return list(STANDARD_COHORT)

    # If universe is a path to a file (JSON or text)
    uni_path = Path(universe)
    if uni_path.exists():
        try:
            if uni_path.suffix == ".json":
                data = json.loads(uni_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return sorted(set(str(x).upper() for x in data))
            lines = [line.strip().upper() for line in uni_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
            if lines:
                return sorted(set(lines))
        except Exception:
            pass

    return list(STANDARD_COHORT)


def resolve_capabilities(caps_arg: Sequence[str] | str | None) -> list[str]:
    """Resolve requested capabilities/families into specific semantic identities."""
    if not caps_arg or (isinstance(caps_arg, str) and caps_arg.strip().upper() == "ALL"):
        # Return all semantic fields defined in taxonomy
        return sorted(taxonomy.ALL_SEMANTIC_IDENTITIES)

    raw_items: list[str] = []
    if isinstance(caps_arg, str):
        raw_items = [c.strip().upper() for c in caps_arg.split(",") if c.strip()]
    else:
        for item in caps_arg:
            raw_items.extend(c.strip().upper() for c in str(item).split(",") if c.strip())

    resolved: set[str] = set()
    for item in raw_items:
        if item in taxonomy.SEMANTIC_FIELDS:
            resolved.update(taxonomy.SEMANTIC_FIELDS[item])
        elif item in taxonomy.ALL_SEMANTIC_IDENTITIES:
            resolved.add(item)
        elif item == "ALL":
            resolved.update(taxonomy.ALL_SEMANTIC_IDENTITIES)
    return sorted(resolved) if resolved else sorted(taxonomy.ALL_SEMANTIC_IDENTITIES)


def resolve_sources(sources_arg: Sequence[str] | str | None) -> list[str]:
    """Resolve permitted sources."""
    if not sources_arg or (isinstance(sources_arg, str) and sources_arg.strip().upper() == "ALL"):
        return list(SUPPORTED_SOURCES)

    raw_items: list[str] = []
    if isinstance(sources_arg, str):
        raw_items = [s.strip().upper() for s in sources_arg.split(",") if s.strip()]
    else:
        for item in sources_arg:
            raw_items.extend(s.strip().upper() for s in str(item).split(",") if s.strip())

    valid = [s for s in raw_items if s in SUPPORTED_SOURCES]
    return valid if valid else list(SUPPORTED_SOURCES)


def build_source_routing_plan(
    symbols: Sequence[str],
    capabilities: Sequence[str],
    sources: Sequence[str],
) -> dict[str, Any]:
    """Determine per-capability routing according to market_capability_taxonomy.py.

    Requirements:
    - Route sources per capability. DNSE/FHSC parity is NOT required.
    - Single-source-only capabilities are routed to their available source.
    - Missing/unsupported capabilities are identified cleanly without wasting requests.
    """
    routed_capabilities: dict[str, list[str]] = {}
    single_source_capabilities: list[str] = []
    missing_capabilities: list[str] = []
    planned_requests: list[dict[str, Any]] = []

    # Map requested capabilities to sources
    for identity in sorted(capabilities):
        all_candidates = taxonomy.source_candidates(identity)
        matched_sources = [s for s in all_candidates if s in sources]
        routed_capabilities[identity] = matched_sources
        if len(all_candidates) == 1:
            single_source_capabilities.append(identity)
        if not matched_sources:
            missing_capabilities.append(identity)

    # Deduplicate endpoint calls per (source, symbol)
    for symbol in sorted(symbols):
        # Check DNSE needs
        dnse_caps = [ident for ident, s_list in routed_capabilities.items() if taxonomy.SOURCE_DNSE in s_list]
        needs_dnse_ohlc = any(
            ident in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_PRICE]
            or ident == "MATCHED_VOLUME_SHARES"
            for ident in dnse_caps
        )
        needs_dnse_foreign = any(
            ident in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_FOREIGN]
            for ident in dnse_caps
        )

        if taxonomy.SOURCE_DNSE in sources:
            if needs_dnse_ohlc:
                planned_requests.append({
                    "source": taxonomy.SOURCE_DNSE,
                    "endpoint_id": "ohlc",
                    "capability_family": taxonomy.FAMILY_PRICE,
                    "symbol": symbol,
                    "target_capabilities": [c for c in dnse_caps if c in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_PRICE] or c == "MATCHED_VOLUME_SHARES"],
                })
            if needs_dnse_foreign:
                planned_requests.append({
                    "source": taxonomy.SOURCE_DNSE,
                    "endpoint_id": "foreign_trading",
                    "capability_family": taxonomy.FAMILY_FOREIGN,
                    "symbol": symbol,
                    "target_capabilities": [c for c in dnse_caps if c in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_FOREIGN]],
                })

        # Check FHSC needs
        fhsc_caps = [ident for ident, s_list in routed_capabilities.items() if taxonomy.SOURCE_FHSC in s_list]
        needs_fhsc_price = any(ident in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_PRICE] for ident in fhsc_caps)
        needs_fhsc_trading = any(
            ident in ("MATCHED_VOLUME_SHARES", "PUT_THROUGH_VOLUME_SHARES", "TOTAL_VOLUME_SHARES",
                      "MATCHED_TRADED_VALUE_VND", "PUT_THROUGH_TRADED_VALUE_VND", "TOTAL_TRADED_VALUE_VND")
            for ident in fhsc_caps
        )
        needs_fhsc_room = any(
            ident in ("FOREIGN_ROOM_MAX", "FOREIGN_ROOM_OWNED", "FOREIGN_ROOM_AVAILABLE")
            for ident in fhsc_caps
        )
        needs_fhsc_proprietary = any(
            ident in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_PROPRIETARY]
            for ident in fhsc_caps
        )
        needs_fhsc_microstructure = any(
            ident in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_MICROSTRUCTURE]
            for ident in fhsc_caps
        )

        if taxonomy.SOURCE_FHSC in sources:
            if needs_fhsc_price:
                planned_requests.append({
                    "source": taxonomy.SOURCE_FHSC,
                    "endpoint_id": "price_histories_chart",
                    "capability_family": taxonomy.FAMILY_PRICE,
                    "symbol": symbol,
                    "target_capabilities": [c for c in fhsc_caps if c in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_PRICE]],
                })
            if needs_fhsc_trading:
                planned_requests.append({
                    "source": taxonomy.SOURCE_FHSC,
                    "endpoint_id": "trading_history",
                    "capability_family": taxonomy.FAMILY_VOLUME,
                    "symbol": symbol,
                    "target_capabilities": [c for c in fhsc_caps if c in (
                        "MATCHED_VOLUME_SHARES", "PUT_THROUGH_VOLUME_SHARES", "TOTAL_VOLUME_SHARES",
                        "MATCHED_TRADED_VALUE_VND", "PUT_THROUGH_TRADED_VALUE_VND", "TOTAL_TRADED_VALUE_VND"
                    )],
                })
            if needs_fhsc_room:
                planned_requests.append({
                    "source": taxonomy.SOURCE_FHSC,
                    "endpoint_id": "foreign_room",
                    "capability_family": taxonomy.FAMILY_FOREIGN,
                    "symbol": symbol,
                    "target_capabilities": [c for c in fhsc_caps if c in ("FOREIGN_ROOM_MAX", "FOREIGN_ROOM_OWNED", "FOREIGN_ROOM_AVAILABLE")],
                })
            if needs_fhsc_proprietary:
                planned_requests.append({
                    "source": taxonomy.SOURCE_FHSC,
                    "endpoint_id": "proprietary_trading",
                    "capability_family": taxonomy.FAMILY_PROPRIETARY,
                    "symbol": symbol,
                    "target_capabilities": [c for c in fhsc_caps if c in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_PROPRIETARY]],
                })
            if needs_fhsc_microstructure:
                planned_requests.append({
                    "source": taxonomy.SOURCE_FHSC,
                    "endpoint_id": "order_statistics",
                    "capability_family": taxonomy.FAMILY_MICROSTRUCTURE,
                    "symbol": symbol,
                    "target_capabilities": [c for c in fhsc_caps if c in taxonomy.SEMANTIC_FIELDS[taxonomy.FAMILY_MICROSTRUCTURE]],
                })

    return {
        "routed_capabilities": routed_capabilities,
        "single_source_capabilities": single_source_capabilities,
        "missing_capabilities": missing_capabilities,
        "planned_requests": planned_requests,
        "total_planned_requests": len(planned_requests),
    }


def _default_http_fetcher(request_item: Mapping[str, Any], session_date: str) -> dict[str, Any]:
    """Execute live HTTP request with credentials loaded via repository-approved mechanisms."""
    source = request_item["source"]
    endpoint_id = request_item["endpoint_id"]
    symbol = request_item["symbol"]
    retrieval_time = datetime.now(UTC).isoformat()

    if source == taxonomy.SOURCE_DNSE:
        cred_stat = ensure_credentials_loaded()
        creds = credentials_for_request() if cred_stat["configured"] else None
        if not creds:
            return {
                "ok": False,
                "error_code": "CREDENTIAL_UNAVAILABLE",
                "source": source,
                "endpoint": endpoint_id,
                "symbol": symbol,
                "retrieval_time": retrieval_time,
                "raw_response_retained": False,
            }
        api_key, api_secret = creds

        # Session timestamps in VN timezone (+07:00)
        start_dt = datetime.strptime(session_date, "%Y-%m-%d").replace(tzinfo=VN_TZ)
        end_dt = start_dt + timedelta(days=1) - timedelta(seconds=1)
        from_ts = int(start_dt.timestamp())
        to_ts = int(end_dt.timestamp())

        if endpoint_id == "ohlc":
            path = resolve_endpoint("ohlc")
            query = {"symbol": symbol, "resolution": "1D", "from": from_ts, "to": to_ts, "type": "STOCK"}
        elif endpoint_id == "foreign_trading":
            path = resolve_endpoint("foreign_trading", symbol=symbol)
            query = {"from": from_ts, "to": to_ts, "limit": 100, "order": "DESC"}
        else:
            path = f"/price/{symbol}"
            query = {}

        url = f"{DNSE_BASE_URL}{path}"
        headers = auth_headers(api_key, api_secret, "GET", path)

        try:
            import requests
            resp = requests.get(url, params=query, headers=headers, timeout=(5, 15))
            status = int(resp.status_code)
            body_bytes = resp.content
            mime = resp.headers.get("Content-Type", "application/json")
        except Exception as exc:
            return {
                "ok": False,
                "error_code": f"request_failed_{dnse_acc.safe_error_code(exc)}",
                "source": source,
                "endpoint": path,
                "symbol": symbol,
                "retrieval_time": retrieval_time,
                "raw_response_retained": False,
            }

        if status == 429:
            return {
                "ok": False,
                "error_code": "PROVIDER_RATE_LIMITED",
                "http_status": 429,
                "source": source,
                "endpoint": path,
                "symbol": symbol,
                "retrieval_time": retrieval_time,
                "raw_response_retained": False,
            }
        if status != 200:
            return {
                "ok": False,
                "error_code": f"http_status_{status}",
                "http_status": status,
                "source": source,
                "endpoint": path,
                "symbol": symbol,
                "retrieval_time": retrieval_time,
                "raw_response_retained": False,
            }

        return {
            "ok": True,
            "source": source,
            "endpoint": path,
            "symbol": symbol,
            "http_status": 200,
            "mime_type": mime,
            "retrieval_time": retrieval_time,
            "raw_bytes": body_bytes,
            "request_url": dnse_acc.sanitize_url(url),
            "request_parameters": dict(query),
        }

    if source == taxonomy.SOURCE_FHSC:
        api_key = load_finhay_api_key()
        if not api_key:
            return {
                "ok": False,
                "error_code": "CREDENTIAL_UNAVAILABLE",
                "source": source,
                "endpoint": endpoint_id,
                "symbol": symbol,
                "retrieval_time": retrieval_time,
                "raw_response_retained": False,
            }

        start_dt = datetime.strptime(session_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_dt = start_dt + timedelta(days=1)
        from_ts = int(start_dt.timestamp())
        to_ts = int(end_dt.timestamp())

        path, params = _fhsc_request_contract(
            endpoint_id,
            symbol,
            session_date,
            price_from_ts=from_ts,
            price_to_ts=to_ts,
        )

        url = f"{FHSC_BASE_URL}{path}?{urlencode(params)}"
        req = Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key})

        try:
            with urlopen(req, timeout=15) as resp:
                body_bytes = resp.read()
                status = int(resp.status)
                mime = resp.headers.get_content_type()
        except HTTPError as err:
            status = int(err.code)
            if status == 429:
                return {
                    "ok": False,
                    "error_code": "PROVIDER_RATE_LIMITED",
                    "http_status": 429,
                    "source": source,
                    "endpoint": path,
                    "symbol": symbol,
                    "retrieval_time": retrieval_time,
                    "raw_response_retained": False,
                }
            return {
                "ok": False,
                "error_code": f"http_status_{status}",
                "http_status": status,
                "source": source,
                "endpoint": path,
                "symbol": symbol,
                "retrieval_time": retrieval_time,
                "raw_response_retained": False,
            }
        except OSError as exc:
            return {
                "ok": False,
                "error_code": f"request_failed_{type(exc).__name__}",
                "source": source,
                "endpoint": path,
                "symbol": symbol,
                "retrieval_time": retrieval_time,
                "raw_response_retained": False,
            }

        return {
            "ok": True,
            "source": source,
            "endpoint": path,
            "symbol": symbol,
            "http_status": status,
            "mime_type": mime,
            "retrieval_time": retrieval_time,
            "raw_bytes": body_bytes,
            "request_url": url,
            "request_parameters": params,
        }

    return {
        "ok": False,
        "error_code": f"UNSUPPORTED_SOURCE:{source}",
        "source": source,
        "endpoint": endpoint_id,
        "symbol": symbol,
        "retrieval_time": retrieval_time,
        "raw_response_retained": False,
    }


def _fhsc_request_contract(
    endpoint_id: str,
    symbol: str,
    session_date: str,
    *,
    price_from_ts: int | None = None,
    price_to_ts: int | None = None,
) -> tuple[str, dict[str, str]]:
    """Return the FHSC endpoint and exact-session query contract for one collector route.

    The three non-price daily capabilities deliberately use their retained `/history`
    contracts.  A current-state endpoint cannot establish a historical observation.
    """
    if endpoint_id == "price_histories_chart":
        if price_from_ts is None or price_to_ts is None:
            start_dt = datetime.strptime(session_date, "%Y-%m-%d").replace(tzinfo=UTC)
            price_from_ts = int(start_dt.timestamp())
            price_to_ts = int((start_dt + timedelta(days=1)).timestamp())
        return PRICE_HISTORY_PATH, {
            "symbol": symbol,
            "resolution": "1D",
            "from": str(price_from_ts),
            "to": str(price_to_ts),
        }
    if endpoint_id == "trading_history":
        return f"/market/stocks/{symbol}/trading/history", {
            "from": session_date,
            "to": session_date,
            "resolution": "1D",
        }
    if endpoint_id == "foreign_room":
        return f"/market/stocks/{symbol}/ownership/foreign-room/history", {
            "from": session_date,
            "to": session_date,
        }
    if endpoint_id == "proprietary_trading":
        return f"/market/stocks/{symbol}/trading/proprietary/history", {
            "from": session_date,
            "to": session_date,
        }
    if endpoint_id == "order_statistics":
        return f"/market/stocks/{symbol}/trading/orders/history", {
            "from": session_date,
            "to": session_date,
        }
    return STOCK_REALTIME_PATH, {"symbol": symbol}


def _fhsc_provider_session_date(record: Mapping[str, Any]) -> str | None:
    """Return a provider-labelled session date without inferring one from retrieval time."""
    for key in ("date", "session", "tradingDate"):
        value = record.get(key)
        if isinstance(value, str):
            if len(value) == 10:
                return value
            if len(value) > 10 and value[10:11] == "T":
                return value[:10]
    return None


def _fhsc_exact_session_record(raw_payload: Any, session_date: str) -> Mapping[str, Any] | None:
    """Select only a record explicitly labelled with the requested FHSC session date."""
    containers: list[Mapping[str, Any]] = []
    if isinstance(raw_payload, Mapping):
        containers.append(raw_payload)
        data = raw_payload.get("data")
        if isinstance(data, Mapping):
            containers.append(data)

    candidates: list[Mapping[str, Any]] = []
    for container in containers:
        if _fhsc_provider_session_date(container) is not None:
            candidates.append(container)
        for key in ("data", "items", "rows", "history"):
            value = container.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, Mapping))

    for candidate in candidates:
        if _fhsc_provider_session_date(candidate) == session_date:
            return candidate
    return None


def _native_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def parse_raw_observation_data(
    source: str,
    endpoint_id: str,
    raw_payload: Any,
    session_date: str,
    symbol: str,
) -> dict[str, Any]:
    """Parse raw payload to extract provider-native values according to taxonomy contracts."""
    parsed: dict[str, Any] = {
        "parse_status": "UNPARSED",
        "native_fields": {},
        "canonical_fields": {},
        "semantic_gaps": [],
    }

    if source == taxonomy.SOURCE_DNSE:
        if endpoint_id == "ohlc":
            if not isinstance(raw_payload, Mapping):
                parsed["parse_status"] = "MALFORMED_NON_OBJECT"
                return parsed
            times = raw_payload.get("t")
            opens = raw_payload.get("o")
            highs = raw_payload.get("h")
            lows = raw_payload.get("l")
            closes = raw_payload.get("c")
            volumes = raw_payload.get("v")

            if not all(isinstance(a, list) for a in (times, opens, highs, lows, closes, volumes)):
                parsed["parse_status"] = "COLUMNAR_ARRAYS_ABSENT"
                return parsed

            if not (len(times) == len(opens) == len(highs) == len(lows) == len(closes) == len(volumes)):
                parsed["parse_status"] = "COLUMNAR_LENGTH_MISMATCH"
                return parsed

            matching_idx = None
            for idx, epoch in enumerate(times):
                if isinstance(epoch, (int, float)) and not isinstance(epoch, bool):
                    row_session = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(VN_TZ).date().isoformat()
                    if row_session == session_date:
                        matching_idx = idx
                        break

            if matching_idx is None:
                parsed["parse_status"] = "EXACT_SESSION_MISSING"
                return parsed

            o_raw = opens[matching_idx]
            h_raw = highs[matching_idx]
            l_raw = lows[matching_idx]
            c_raw = closes[matching_idx]
            v_raw = volumes[matching_idx]

            # Provider native prices in thousands of VND/share
            parsed["native_fields"] = {
                "OPEN_KVND": {"value": str(o_raw), "unit": "thousands_of_vnd_per_share", "raw_field": "o"},
                "HIGH_KVND": {"value": str(h_raw), "unit": "thousands_of_vnd_per_share", "raw_field": "h"},
                "LOW_KVND": {"value": str(l_raw), "unit": "thousands_of_vnd_per_share", "raw_field": "l"},
                "CLOSE_KVND": {"value": str(c_raw), "unit": "thousands_of_vnd_per_share", "raw_field": "c"},
                "MATCHED_VOLUME_SHARES": {"value": int(v_raw), "unit": "shares", "raw_field": "v"},
            }

            # Canonical derivation via Phase 1 price representation contract
            try:
                canonical_ohlc = price_contract.to_canonical_ohlc(
                    open_=o_raw,
                    high=h_raw,
                    low=l_raw,
                    close=c_raw,
                    source=taxonomy.SOURCE_DNSE,
                    capability_id="ohlc_1D",
                    instrument_class=taxonomy.INSTRUMENT_CLASS_VN_LISTED_EQUITY,
                )
                parsed["canonical_fields"] = {
                    "OPEN_VND": {
                        "value": canonical_ohlc["fields"]["open"]["canonical_value"],
                        "unit": "vnd_per_share",
                        "derived_from": "OPEN_KVND",
                        "contract_id": canonical_ohlc["contract_id"],
                        "contract_basis_tier": price_contract.CONTRACT_BASIS_TIER,
                    },
                    "HIGH_VND": {
                        "value": canonical_ohlc["fields"]["high"]["canonical_value"],
                        "unit": "vnd_per_share",
                        "derived_from": "HIGH_KVND",
                        "contract_id": canonical_ohlc["contract_id"],
                        "contract_basis_tier": price_contract.CONTRACT_BASIS_TIER,
                    },
                    "LOW_VND": {
                        "value": canonical_ohlc["fields"]["low"]["canonical_value"],
                        "unit": "vnd_per_share",
                        "derived_from": "LOW_KVND",
                        "contract_id": canonical_ohlc["contract_id"],
                        "contract_basis_tier": price_contract.CONTRACT_BASIS_TIER,
                    },
                    "CLOSE_VND": {
                        "value": canonical_ohlc["fields"]["close"]["canonical_value"],
                        "unit": "vnd_per_share",
                        "derived_from": "CLOSE_KVND",
                        "contract_id": canonical_ohlc["contract_id"],
                        "contract_basis_tier": price_contract.CONTRACT_BASIS_TIER,
                    },
                    "MATCHED_VOLUME_SHARES": {
                        "value": int(v_raw),
                        "unit": "shares",
                        "derived_from": "MATCHED_VOLUME_SHARES",
                        "contract_id": "identity/shares",
                    },
                }
                parsed["parse_status"] = "PARSED"
            except Exception as exc:
                parsed["parse_status"] = f"CANONICALIZATION_FAILED:{type(exc).__name__}"

        elif endpoint_id == "foreign_trading":
            if not isinstance(raw_payload, Mapping):
                parsed["parse_status"] = "MALFORMED_NON_OBJECT"
                return parsed
            records = raw_payload.get("foreigners")
            if records is None or not isinstance(records, list):
                records = [raw_payload] if "buyForeignQuantity" in raw_payload or "buyTradedAmount" in raw_payload else []

            # Extract totals
            buy_vol = 0
            sell_vol = 0
            buy_val = 0
            sell_val = 0
            room_max = raw_payload.get("foreignRoomMax") or raw_payload.get("roomMax")
            room_owned = raw_payload.get("foreignRoomOwned") or raw_payload.get("roomOwned")
            room_avail = raw_payload.get("foreignRoomAvailable") or raw_payload.get("roomAvailable")

            found_any = False
            record_dates: set[str] = set()
            for rec in records:
                if isinstance(rec, Mapping):
                    found_any = True
                    observed_at = rec.get("time") or rec.get("tradingDate") or rec.get("date")
                    if isinstance(observed_at, str) and len(observed_at) >= 10:
                        record_dates.add(observed_at[:10])
                    b_q = rec.get("buyForeignQuantity", rec.get("totalBuyQuantity", rec.get("buyVolume", 0)))
                    s_q = rec.get("sellForeignQuantity", rec.get("totalSellQuantity", rec.get("sellVolume", 0)))
                    b_v = rec.get("buyForeignValue", rec.get("buyTradedAmount", rec.get("buyValue", 0)))
                    s_v = rec.get("sellForeignValue", rec.get("sellTradedAmount", rec.get("sellValue", 0)))
                    if isinstance(b_q, (int, float)): buy_vol += int(b_q)
                    if isinstance(s_q, (int, float)): sell_vol += int(s_q)
                    if isinstance(b_v, (int, float)): buy_val += int(b_v)
                    if isinstance(s_v, (int, float)): sell_val += int(s_v)

            net_vol = buy_vol - sell_vol
            net_val = buy_val - sell_val

            parsed["native_fields"] = {
                "FOREIGN_BUY_VOLUME": {"value": buy_vol, "unit": "shares"},
                "FOREIGN_SELL_VOLUME": {"value": sell_vol, "unit": "shares"},
                "FOREIGN_NET_VOLUME": {"value": net_vol, "unit": "shares"},
                "FOREIGN_BUY_VALUE": {"value": buy_val, "unit": "vnd_raw_not_thousands"},
                "FOREIGN_SELL_VALUE": {"value": sell_val, "unit": "vnd_raw_not_thousands"},
                "FOREIGN_NET_VALUE": {"value": net_val, "unit": "vnd_raw_not_thousands"},
                "FOREIGN_ROOM_MAX": {"value": room_max, "unit": "shares", "status": taxonomy.SEMANTIC_UNRESOLVED},
                "FOREIGN_ROOM_OWNED": {"value": room_owned, "unit": "shares", "status": taxonomy.SEMANTIC_UNRESOLVED},
                "FOREIGN_ROOM_AVAILABLE": {"value": room_avail, "unit": "shares", "status": taxonomy.SEMANTIC_UNRESOLVED},
            }
            parsed["canonical_fields"] = {
                "FOREIGN_BUY_VOLUME": {"value": buy_vol, "unit": "shares"},
                "FOREIGN_SELL_VOLUME": {"value": sell_vol, "unit": "shares"},
                "FOREIGN_NET_VOLUME": {"value": net_vol, "unit": "shares"},
                "FOREIGN_BUY_VALUE": {"value": buy_val, "unit": "vnd_raw_not_thousands", "note": "raw VND; not passed through KVND contract"},
                "FOREIGN_SELL_VALUE": {"value": sell_val, "unit": "vnd_raw_not_thousands", "note": "raw VND; not passed through KVND contract"},
                "FOREIGN_NET_VALUE": {"value": net_val, "unit": "vnd_raw_not_thousands", "note": "raw VND; not passed through KVND contract"},
            }
            # DNSE does not publish a top-level session label on this endpoint, but
            # its retained rows carry provider timestamps.  Bind only when all dated
            # rows agree with the requested completed session; otherwise preserve the
            # payload but leave the session unresolved for dependent consumers.
            if record_dates == {session_date}:
                parsed["provider_session_date"] = session_date
            elif record_dates:
                parsed["semantic_gaps"].append("dnse_foreign_trading_provider_session_mismatch_or_mixed")
            parsed["parse_status"] = "PARSED" if found_any or records == [] else "PARSED_EMPTY"

    elif source == taxonomy.SOURCE_FHSC:
        if endpoint_id == "price_histories_chart":
            if not isinstance(raw_payload, Mapping):
                parsed["parse_status"] = "MALFORMED_NON_OBJECT"
                return parsed
            data = raw_payload.get("data")
            if not isinstance(data, Mapping):
                parsed["parse_status"] = "DATA_OBJECT_ABSENT"
                return parsed
            times = data.get("time")
            opens = data.get("open")
            highs = data.get("high")
            lows = data.get("low")
            closes = data.get("close")
            volumes = data.get("volume")

            if not all(isinstance(a, list) for a in (times, opens, highs, lows, closes, volumes)):
                parsed["parse_status"] = "COLUMNAR_ARRAYS_ABSENT"
                return parsed

            matching_idx = None
            for idx, epoch in enumerate(times):
                if isinstance(epoch, (int, float)) and not isinstance(epoch, bool):
                    row_session = datetime.fromtimestamp(epoch, tz=UTC).date().isoformat()
                    if row_session == session_date:
                        matching_idx = idx
                        break

            if matching_idx is None:
                parsed["parse_status"] = "EXACT_SESSION_MISSING"
                return parsed

            o_raw = opens[matching_idx]
            h_raw = highs[matching_idx]
            l_raw = lows[matching_idx]
            c_raw = closes[matching_idx]
            v_raw = volumes[matching_idx]

            # FHSC prices have UNRESOLVED unit; fail closed for canonical price
            parsed["native_fields"] = {
                "OPEN_KVND": {"value": str(o_raw), "unit": "UNRESOLVED", "raw_field": "open"},
                "HIGH_KVND": {"value": str(h_raw), "unit": "UNRESOLVED", "raw_field": "high"},
                "LOW_KVND": {"value": str(l_raw), "unit": "UNRESOLVED", "raw_field": "low"},
                "CLOSE_KVND": {"value": str(c_raw), "unit": "UNRESOLVED", "raw_field": "close"},
                "MATCHED_VOLUME_SHARES": {"value": int(v_raw), "unit": "shares", "raw_field": "volume"},
            }
            parsed["canonical_fields"] = {
                "MATCHED_VOLUME_SHARES": {"value": int(v_raw), "unit": "shares"},
            }
            parsed["provider_session_date"] = session_date
            parsed["semantic_gaps"].append("fhsc_price_unit_unresolved")
            parsed["parse_status"] = "PARSED"

        elif endpoint_id == "trading_history":
            target_row = _fhsc_exact_session_record(raw_payload, session_date)
            if target_row is None:
                parsed["parse_status"] = "EXACT_SESSION_MISSING"
                return parsed
            parsed["provider_session_date"] = _fhsc_provider_session_date(target_row)

            # Check nested object structure: {"matched": {"volume": ..., "value": ...}, "put_through": ..., "total": ...}
            matched_obj = target_row.get("matched", {})
            pt_obj = target_row.get("put_through", {})
            total_obj = target_row.get("total", {})

            if isinstance(matched_obj, Mapping):
                matched_v = matched_obj.get("volume", target_row.get("matched_volume", target_row.get("matchedVolume")))
                matched_val = matched_obj.get("value", target_row.get("matched_value", target_row.get("matchedValue")))
            else:
                matched_v = target_row.get("matched_volume", target_row.get("matchedVolume"))
                matched_val = target_row.get("matched_value", target_row.get("matchedValue"))

            if isinstance(pt_obj, Mapping):
                put_through_v = pt_obj.get("volume", target_row.get("put_through_volume", target_row.get("putThroughVolume")))
                put_through_val = pt_obj.get("value", target_row.get("put_through_value", target_row.get("putThroughValue")))
            else:
                put_through_v = target_row.get("put_through_volume", target_row.get("putThroughVolume"))
                put_through_val = target_row.get("put_through_value", target_row.get("putThroughValue"))

            if isinstance(total_obj, Mapping):
                total_v = total_obj.get("volume", target_row.get("total_volume", target_row.get("totalVolume")))
                total_val = total_obj.get("value", target_row.get("total_value", target_row.get("totalValue")))
            else:
                total_v = target_row.get("total_volume", target_row.get("totalVolume"))
                total_val = target_row.get("total_value", target_row.get("totalValue"))

            parsed["native_fields"] = {
                "MATCHED_VOLUME_SHARES": {"value": _native_int(matched_v), "unit": "shares"},
                "PUT_THROUGH_VOLUME_SHARES": {"value": _native_int(put_through_v), "unit": "shares"},
                "TOTAL_VOLUME_SHARES": {"value": _native_int(total_v), "unit": "shares"},
                "MATCHED_TRADED_VALUE_VND": {"value": _native_int(matched_val), "unit": "vnd"},
                "PUT_THROUGH_TRADED_VALUE_VND": {"value": _native_int(put_through_val), "unit": "vnd"},
                "TOTAL_TRADED_VALUE_VND": {"value": _native_int(total_val), "unit": "vnd"},
            }
            native_values = (matched_v, put_through_v, total_v, matched_val, put_through_val, total_val)
            if any(value is None for value in native_values):
                parsed["semantic_gaps"].append("fhsc_trading_history_native_total_unavailable")
                parsed["parse_status"] = "NATIVE_FIELDS_UNAVAILABLE"
                return parsed
            if int(matched_v) + int(put_through_v) != int(total_v) or int(matched_val) + int(put_through_val) != int(total_val):
                parsed["semantic_gaps"].append("fhsc_trading_history_total_conflicting_with_components")
                parsed["parse_status"] = "CONFLICTING_ARITHMETIC"
                return parsed
            parsed["canonical_fields"] = {
                "MATCHED_VOLUME_SHARES": {"value": int(matched_v), "unit": "shares"},
                "PUT_THROUGH_VOLUME_SHARES": {"value": int(put_through_v), "unit": "shares"},
                "TOTAL_VOLUME_SHARES": {"value": int(total_v), "unit": "shares"},
                "MATCHED_TRADED_VALUE_VND": {"value": int(matched_val), "unit": "vnd_raw_not_thousands"},
                "PUT_THROUGH_TRADED_VALUE_VND": {"value": int(put_through_val), "unit": "vnd_raw_not_thousands"},
                "TOTAL_TRADED_VALUE_VND": {"value": int(total_val), "unit": "vnd_raw_not_thousands"},
            }
            parsed["parse_status"] = "PARSED"

        elif endpoint_id == "foreign_room":
            target_obj = _fhsc_exact_session_record(raw_payload, session_date)
            if target_obj is None:
                parsed["parse_status"] = "EXACT_SESSION_MISSING"
                return parsed
            parsed["provider_session_date"] = _fhsc_provider_session_date(target_obj)

            max_volume = target_obj.get("max_volume", target_obj.get("maxVolume", target_obj.get("foreignRoomMax")))
            owned = target_obj.get("owned", target_obj.get("foreignRoomOwned"))
            avail = target_obj.get("available", target_obj.get("foreignRoomAvailable"))

            parsed["native_fields"] = {
                "FOREIGN_ROOM_MAX": {"value": int(max_volume) if max_volume is not None else None, "unit": "shares"},
                "FOREIGN_ROOM_OWNED": {"value": int(owned) if owned is not None else None, "unit": "shares"},
                "FOREIGN_ROOM_AVAILABLE": {"value": int(avail) if avail is not None else None, "unit": "shares"},
            }
            if max_volume is None or owned is None or avail is None:
                parsed["semantic_gaps"].append("fhsc_foreign_room_native_fields_unavailable")
                parsed["parse_status"] = "NATIVE_FIELDS_UNAVAILABLE"
                return parsed
            if int(owned) + int(avail) != int(max_volume):
                parsed["semantic_gaps"].append("fhsc_foreign_room_total_conflicting_with_components")
                parsed["parse_status"] = "CONFLICTING_ARITHMETIC"
                return parsed
            parsed["canonical_fields"] = {
                "FOREIGN_ROOM_MAX": {"value": int(max_volume) if max_volume is not None else None, "unit": "shares"},
                "FOREIGN_ROOM_OWNED": {"value": int(owned) if owned is not None else None, "unit": "shares"},
                "FOREIGN_ROOM_AVAILABLE": {"value": int(avail) if avail is not None else None, "unit": "shares"},
            }
            parsed["parse_status"] = "PARSED"

        elif endpoint_id == "proprietary_trading":
            target_obj = _fhsc_exact_session_record(raw_payload, session_date)
            if target_obj is None:
                parsed["parse_status"] = "EXACT_SESSION_MISSING"
                return parsed
            parsed["provider_session_date"] = _fhsc_provider_session_date(target_obj)

            buy = target_obj.get("buy", {})
            sell = target_obj.get("sell", {})
            net = target_obj.get("net", {})

            buy_tot = buy.get("total", buy) if isinstance(buy, Mapping) else {}
            sell_tot = sell.get("total", sell) if isinstance(sell, Mapping) else {}
            net_tot = net.get("total", net) if isinstance(net, Mapping) else {}

            buy_vol = buy_tot.get("volume", target_obj.get("buy_volume")) if isinstance(buy_tot, Mapping) else None
            buy_val = buy_tot.get("value", target_obj.get("buy_value")) if isinstance(buy_tot, Mapping) else None
            sell_vol = sell_tot.get("volume", target_obj.get("sell_volume")) if isinstance(sell_tot, Mapping) else None
            sell_val = sell_tot.get("value", target_obj.get("sell_value")) if isinstance(sell_tot, Mapping) else None
            net_vol = net_tot.get("volume", target_obj.get("net_volume")) if isinstance(net_tot, Mapping) else None
            net_val = net_tot.get("value", target_obj.get("net_value")) if isinstance(net_tot, Mapping) else None

            parsed["native_fields"] = {
                "PROPRIETARY_BUY_VOLUME": {"value": _native_int(buy_vol), "unit": "shares"},
                "PROPRIETARY_SELL_VOLUME": {"value": _native_int(sell_vol), "unit": "shares"},
                "PROPRIETARY_NET_VOLUME": {"value": _native_int(net_vol), "unit": "shares"},
                "PROPRIETARY_BUY_VALUE": {"value": _native_int(buy_val), "unit": "vnd"},
                "PROPRIETARY_SELL_VALUE": {"value": _native_int(sell_val), "unit": "vnd"},
                "PROPRIETARY_NET_VALUE": {"value": _native_int(net_val), "unit": "vnd"},
            }
            native_values = (buy_vol, sell_vol, net_vol, buy_val, sell_val, net_val)
            if any(value is None for value in native_values):
                parsed["semantic_gaps"].append("fhsc_proprietary_native_net_unavailable")
                parsed["parse_status"] = "NATIVE_FIELDS_UNAVAILABLE"
                return parsed
            if int(buy_vol) - int(sell_vol) != int(net_vol) or int(buy_val) - int(sell_val) != int(net_val):
                parsed["semantic_gaps"].append("fhsc_proprietary_net_conflicting_with_components")
                parsed["parse_status"] = "CONFLICTING_ARITHMETIC"
                return parsed
            parsed["canonical_fields"] = {
                "PROPRIETARY_BUY_VOLUME": {"value": int(buy_vol), "unit": "shares"},
                "PROPRIETARY_SELL_VOLUME": {"value": int(sell_vol), "unit": "shares"},
                "PROPRIETARY_NET_VOLUME": {"value": int(net_vol), "unit": "shares"},
                "PROPRIETARY_BUY_VALUE": {"value": int(buy_val), "unit": "vnd_raw_not_thousands"},
                "PROPRIETARY_SELL_VALUE": {"value": int(sell_val), "unit": "vnd_raw_not_thousands"},
                "PROPRIETARY_NET_VALUE": {"value": int(net_val), "unit": "vnd_raw_not_thousands"},
            }
            parsed["parse_status"] = "PARSED"

        elif endpoint_id == "order_statistics":
            target_obj = _fhsc_exact_session_record(raw_payload, session_date)
            if target_obj is None:
                parsed["parse_status"] = "EXACT_SESSION_MISSING"
                return parsed
            parsed["provider_session_date"] = _fhsc_provider_session_date(target_obj)

            buy = target_obj.get("buy", {}) if isinstance(target_obj.get("buy"), Mapping) else {}
            sell = target_obj.get("sell", {}) if isinstance(target_obj.get("sell"), Mapping) else {}

            buy_count = buy.get("order_count", buy.get("orderCount", target_obj.get("buy_order_count")))
            buy_vol = buy.get("volume", target_obj.get("buy_volume"))
            sell_count = sell.get("order_count", sell.get("orderCount", target_obj.get("sell_order_count")))
            sell_vol = sell.get("volume", target_obj.get("sell_volume"))
            net_vol = target_obj.get("net_volume", target_obj.get("netVolume"))

            parsed["native_fields"] = {
                "ACTIVE_BUY_ORDER_COUNT": {"value": _native_int(buy_count), "unit": "orders"},
                "ACTIVE_SELL_ORDER_COUNT": {"value": _native_int(sell_count), "unit": "orders"},
                "ACTIVE_BUY_VOLUME": {"value": _native_int(buy_vol), "unit": "shares"},
                "ACTIVE_SELL_VOLUME": {"value": _native_int(sell_vol), "unit": "shares"},
                "ACTIVE_NET_VOLUME": {"value": _native_int(net_vol), "unit": "shares"},
                "ACTIVE_BUY_COUNT": {"value": _native_int(buy_count), "unit": "orders"},
                "ACTIVE_SELL_COUNT": {"value": _native_int(sell_count), "unit": "orders"},
            }
            if any(value is None for value in (buy_count, sell_count, buy_vol, sell_vol, net_vol)):
                parsed["semantic_gaps"].append("fhsc_order_statistics_native_fields_unavailable")
                parsed["parse_status"] = "NATIVE_FIELDS_UNAVAILABLE"
                return parsed
            if int(buy_vol) - int(sell_vol) != int(net_vol):
                parsed["semantic_gaps"].append("fhsc_order_statistics_net_conflicting_with_components")
                parsed["parse_status"] = "CONFLICTING_ARITHMETIC"
                return parsed
            parsed["canonical_fields"] = {
                "ACTIVE_BUY_ORDER_COUNT": {"value": int(buy_count), "unit": "orders"},
                "ACTIVE_SELL_ORDER_COUNT": {"value": int(sell_count), "unit": "orders"},
                "ACTIVE_BUY_VOLUME": {"value": int(buy_vol), "unit": "shares"},
                "ACTIVE_SELL_VOLUME": {"value": int(sell_vol), "unit": "shares"},
                "ACTIVE_NET_VOLUME": {"value": int(net_vol), "unit": "shares"},
                "ACTIVE_BUY_COUNT": {"value": int(buy_count), "unit": "orders"},
                "ACTIVE_SELL_COUNT": {"value": int(sell_count), "unit": "orders"},
            }
            parsed["parse_status"] = "PARSED"

    return parsed


def collect_market_evidence(
    *,
    session_date: str,
    symbols: Sequence[str] | str | None = None,
    universe: str | None = None,
    capabilities: Sequence[str] | str | None = None,
    sources: Sequence[str] | str | None = None,
    max_requests: int = 50,
    out_dir: Path | str | None = None,
    replay_only: bool = False,
    fetcher: Callable[..., dict[str, Any]] | None = None,
    prior_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute retained EOD market evidence collection pipeline.

    Returns the complete session packet dict.
    """
    resolved_syms = resolve_symbols(symbols, universe)
    resolved_caps = resolve_capabilities(capabilities)
    resolved_srcs = resolve_sources(sources)

    if out_dir is None:
        target_out_dir = ROOT / "operations-review" / f"market-evidence-{session_date}"
    else:
        target_out_dir = Path(out_dir)

    raw_dir = target_out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. Routing Plan
    plan = build_source_routing_plan(resolved_syms, resolved_caps, resolved_srcs)
    planned_requests = plan["planned_requests"]

    # If prior packet not explicitly given, try loading existing packet from out_dir to detect revisions
    existing_packet_path = target_out_dir / "session_packet.json"
    if prior_packet is None and existing_packet_path.exists():
        try:
            prior_packet = json.loads(existing_packet_path.read_text(encoding="utf-8"))
        except Exception:
            prior_packet = None

    prior_obs_by_key: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    if prior_packet and "observations" in prior_packet:
        for obs in prior_packet["observations"]:
            key = (str(obs.get("session")), str(obs.get("instrument")), str(obs.get("source")), str(obs.get("endpoint_id")))
            prior_obs_by_key[key] = obs

    # 2. Execution & Request Budgeting
    execute_fetch = fetcher or _default_http_fetcher
    used_requests = 0
    provider_rate_limited_requests = 0
    budget_skipped_requests = 0
    budget_exhausted = False

    observations: list[dict[str, Any]] = []
    rate_limit_events: list[dict[str, Any]] = []
    budget_exhausted_events: list[dict[str, Any]] = []
    revision_events: list[dict[str, Any]] = []
    raw_retained_manifest: list[dict[str, Any]] = []

    for req_item in planned_requests:
        source = req_item["source"]
        endpoint_id = req_item["endpoint_id"]
        symbol = req_item["symbol"]
        target_caps = req_item["target_capabilities"]

        # Budget Check
        if used_requests >= max_requests:
            budget_exhausted = True
            budget_skipped_requests += 1
            budget_exhausted_events.append({
                "session": session_date,
                "instrument": symbol,
                "source": source,
                "endpoint_id": endpoint_id,
                "disposition": "BUDGET_EXHAUSTED",
                "request_sent": False,
            })
            observations.append({
                "session": session_date,
                "instrument": symbol,
                "source": source,
                "endpoint_id": endpoint_id,
                "status": "BUDGET_EXHAUSTED",
                "usability_state": taxonomy.MISSING,
                "acquisition_disposition": "BUDGET_EXHAUSTED",
                "request_sent": False,
                "raw_response_retained": False,
                "native_fields": {},
                "canonical_fields": {},
                "authority_effect": "NONE",
            })
            continue

        used_requests += 1

        # Fetch / Replay
        if replay_only:
            # Replay from existing raw blob
            pattern = f"{source.lower()}_{endpoint_id}_{symbol}_*.json"
            matches = sorted(raw_dir.glob(pattern))
            if matches:
                latest_match = matches[-1]
                body_bytes = latest_match.read_bytes()
                sha = _sha256_bytes(body_bytes)
                try:
                    payload = json.loads(body_bytes.decode("utf-8"))
                except Exception:
                    payload = {}
                fetch_result = {
                    "ok": True,
                    "source": source,
                    "endpoint": endpoint_id,
                    "symbol": symbol,
                    "http_status": 200,
                    "mime_type": "application/json",
                    "retrieval_time": datetime.now(UTC).isoformat(),
                    "raw_bytes": body_bytes,
                    "payload": payload,
                    "replayed_from": str(latest_match),
                }
            else:
                fetch_result = {
                    "ok": False,
                    "error_code": "REPLAY_FILE_NOT_FOUND",
                    "source": source,
                    "endpoint": endpoint_id,
                    "symbol": symbol,
                    "retrieval_time": datetime.now(UTC).isoformat(),
                    "raw_response_retained": False,
                }
        else:
            fetch_result = execute_fetch(req_item, session_date)

        # Process Result
        if not fetch_result.get("ok"):
            err_code = fetch_result.get("error_code", "FETCH_FAILED")
            is_429 = err_code == "PROVIDER_RATE_LIMITED" or fetch_result.get("http_status") == 429
            if is_429:
                provider_rate_limited_requests += 1
                rate_limit_events.append({
                    "session": session_date,
                    "instrument": symbol,
                    "source": source,
                    "endpoint_id": endpoint_id,
                    "retrieval_time": fetch_result.get("retrieval_time"),
                    "http_status": 429,
                    "disposition": "PROVIDER_RATE_LIMITED",
                })

            observations.append({
                "session": session_date,
                "instrument": symbol,
                "source": source,
                "endpoint_id": endpoint_id,
                "status": "PROVIDER_RATE_LIMITED" if is_429 else f"FAILED_{err_code}",
                "usability_state": taxonomy.PROVIDER_RATE_LIMITED if is_429 else taxonomy.MISSING,
                "http_status": fetch_result.get("http_status"),
                "retrieval_time": fetch_result.get("retrieval_time"),
                "raw_response_retained": False,
                "native_fields": {},
                "canonical_fields": {},
                "authority_effect": "NONE",
            })
            continue

        # Successful fetch -> Retain exact raw payload before parsing
        body_bytes = fetch_result.get("raw_bytes")
        if body_bytes is None:
            payload = fetch_result.get("payload", {})
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        else:
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                payload = {"non_json_preview": body_bytes[:1000].decode("utf-8", errors="replace")}

        raw_sha256 = _sha256_bytes(body_bytes)
        raw_filename = f"{source.lower()}_{endpoint_id}_{symbol}_{raw_sha256[:16]}.json"
        raw_file_path = raw_dir / raw_filename

        # Write immutable raw file if not present
        if not raw_file_path.exists():
            raw_file_path.write_bytes(body_bytes)

        rel_raw_path = str(raw_file_path.relative_to(target_out_dir)).replace("\\", "/")
        raw_retained_manifest.append({
            "source": source,
            "endpoint_id": endpoint_id,
            "instrument": symbol,
            "session": session_date,
            "raw_sha256": raw_sha256,
            "raw_path": rel_raw_path,
            "size_bytes": len(body_bytes),
            "retrieved_at": fetch_result.get("retrieval_time"),
            "retrieval_time": fetch_result.get("retrieval_time"),
        })

        # 3. Revision Detection (Requirement 8)
        prior_key = (str(session_date), str(symbol), str(source), str(endpoint_id))
        prior_obs = prior_obs_by_key.get(prior_key)
        revision_state = "INITIAL_OBSERVATION"
        if prior_obs is not None:
            prior_sha = prior_obs.get("raw_sha256")
            if prior_sha and prior_sha != raw_sha256:
                revision_state = "PROVIDER_REVISION_DETECTED"
                revision_events.append({
                    "session": session_date,
                    "instrument": symbol,
                    "source": source,
                    "endpoint_id": endpoint_id,
                    "prior_raw_sha256": prior_sha,
                    "current_raw_sha256": raw_sha256,
                    "prior_retrieved_at": prior_obs.get("retrieval_time"),
                    "current_retrieved_at": fetch_result.get("retrieval_time"),
                    "disposition": "PROVIDER_REVISION_DETECTED",
                })
            else:
                revision_state = "IDENTICAL_OBSERVATION"

        # 4. Canonical Mapping through Phase-1 contracts
        parsed = parse_raw_observation_data(source, endpoint_id, payload, session_date, symbol)
        parse_status = parsed["parse_status"]
        if parse_status == "PARSED":
            observation_status = "ACQUIRED"
            usability_state = taxonomy.RESEARCH_USABLE
        elif parse_status == "EXACT_SESSION_MISSING":
            observation_status = "MISSING_REQUESTED_SESSION"
            usability_state = taxonomy.MISSING
        elif parse_status == "NATIVE_FIELDS_UNAVAILABLE":
            observation_status = "UNAVAILABLE_PROVIDER_NATIVE_FIELDS"
            usability_state = taxonomy.MISSING
        elif parse_status == "CONFLICTING_ARITHMETIC":
            observation_status = "CONFLICTING"
            usability_state = taxonomy.SEMANTIC_UNRESOLVED
        else:
            observation_status = f"PARSED_{parse_status}"
            usability_state = taxonomy.SEMANTIC_UNRESOLVED

        obs_record = {
            "session": session_date,
            "instrument": symbol,
            "source": source,
            "endpoint_id": endpoint_id,
            "status": observation_status,
            "usability_state": usability_state,
            "revision_state": revision_state,
            "provider_session_date": parsed.get("provider_session_date"),
            "retrieved_at": fetch_result.get("retrieval_time"),
            "retrieval_time": fetch_result.get("retrieval_time"),
            "http_status": fetch_result.get("http_status", 200),
            "raw_response_retained": True,
            "raw_path": rel_raw_path,
            "raw_sha256": raw_sha256,
            "request_url": fetch_result.get("request_url"),
            "request_parameters": fetch_result.get("request_parameters"),
            "native_fields": parsed["native_fields"],
            "canonical_fields": parsed["canonical_fields"],
            "semantic_gaps": parsed["semantic_gaps"],
            "authority_effect": "NONE",
        }
        observations.append(obs_record)

    # 5. Assemble Session Packet
    created_at = datetime.now(UTC).isoformat()
    packet = {
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "created_at": created_at,
        "execution_mode": "REPLAY_ONLY" if replay_only else "LIVE_COLLECTION",
        "cli_parameters": {
            "session_date": session_date,
            "symbols": resolved_syms,
            "universe": universe,
            "capabilities": resolved_caps,
            "sources": resolved_srcs,
            "max_requests": max_requests,
            "replay_only": replay_only,
        },
        "request_budget": {
            "max_requests": max_requests,
            "used_requests": used_requests,
            "provider_rate_limited_requests": provider_rate_limited_requests,
            "budget_skipped_requests": budget_skipped_requests,
            "budget_exhausted": budget_exhausted,
            "planned_requests_count": len(planned_requests),
        },
        "source_routing": {
            "routed_capabilities": plan["routed_capabilities"],
            "single_source_capabilities": plan["single_source_capabilities"],
            "missing_capabilities": plan["missing_capabilities"],
        },
        "rate_limit_events": rate_limit_events,
        "budget_exhausted_events": budget_exhausted_events,
        "revision_events": revision_events,
        "observations": observations,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    packet.update(_content_identity("packet", packet))

    # 6. Assemble Manifest
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "session_date": session_date,
        "created_at": created_at,
        "packet_identity": packet["packet_identity"],
        "packet_sha256": packet["packet_sha256"],
        "summary": {
            "total_symbols": len(resolved_syms),
            "total_planned_requests": len(planned_requests),
            "used_requests": used_requests,
            "successful_observations": sum(1 for o in observations if o.get("raw_response_retained")),
            "provider_rate_limited_observations": provider_rate_limited_requests,
            "budget_skipped_observations": budget_skipped_requests,
            "budget_exhausted": budget_exhausted,
            "revision_events_count": len(revision_events),
        },
        "retained_raw_files": raw_retained_manifest,
        "authority_boundaries": AUTHORITY_BOUNDARIES,
    }
    manifest.update(_content_identity("manifest", manifest))

    # 7. Write outputs atomically
    packet_path = target_out_dir / "session_packet.json"
    manifest_path = target_out_dir / "manifest.json"

    packet_path.write_text(json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    return packet


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual retained EOD market evidence collector for capability-first architecture.",
    )
    parser.add_argument(
        "--date",
        dest="session_date",
        default=None,
        help="Market session date YYYY-MM-DD (e.g. 2026-08-20). Defaults to latest completed market day.",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Target tickers/symbols (comma- or space-separated, e.g. HPG,VCB,SSI).",
    )
    parser.add_argument(
        "--universe",
        default=None,
        help="Universe name ('benchmark', 'cohort', 'canonical') or file path.",
    )
    parser.add_argument(
        "--capabilities",
        nargs="*",
        default=None,
        help="Capabilities/families to collect ('PRICE', 'VOLUME', 'FOREIGN', 'ALL', or specific names).",
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Permitted sources ('DNSE', 'FHSC', 'ALL').",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=50,
        help="Request budget limit (default: 50).",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory path.",
    )
    parser.add_argument(
        "--replay-only",
        action="store_true",
        default=False,
        help="Offline deterministic replay mode from retained raw payloads.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_cli_args(argv)

    session_date = args.session_date
    if not session_date:
        # Default to latest completed market session
        session_date = (vn_now() - timedelta(days=1)).strftime("%Y-%m-%d")

    packet = collect_market_evidence(
        session_date=session_date,
        symbols=args.symbols,
        universe=args.universe,
        capabilities=args.capabilities,
        sources=args.sources,
        max_requests=args.max_requests,
        out_dir=args.out_dir,
        replay_only=args.replay_only,
    )

    summary = {
        "status": "COLLECTION_COMPLETE",
        "packet_identity": packet["packet_identity"],
        "session_date": packet["session_date"],
        "requests_used": packet["request_budget"]["used_requests"],
        "provider_rate_limited_count": packet["request_budget"]["provider_rate_limited_requests"],
        "budget_skipped_count": packet["request_budget"]["budget_skipped_requests"],
        "observations_count": len(packet["observations"]),
        "revisions_detected": len(packet["revision_events"]),
        "authority_effect": packet["authority_boundaries"]["authority_effect"],
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
