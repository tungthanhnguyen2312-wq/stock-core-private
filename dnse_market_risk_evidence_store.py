"""Retained store for qualified DNSE OHLC evidence backing the current-state
HPG x VNINDEX market-risk contract (dnse_current_state_market_risk.py).

LAYOUT (beneath the runtime root -- generated runtime data, never the source repo)

    data/dnse-market-risk-evidence/stock-ohlc/<TICKER>.json
    data/dnse-market-risk-evidence/benchmark-ohlc/<BENCHMARK>.json
        one deterministic file per symbol: schema_version, symbol, kind, provider,
        the exact bounded raw_ohlc window (o/h/l/c/t only) already used by the
        qualified current-state contracts, plus provenance recording where this
        evidence was materialized from.

SCOPE -- BOUNDED, DELIBERATELY
    This store holds only the two qualified evidence windows the current-state
    market-risk contract actually needs (currently 19 sessions each, 2026-07-14
    to 2026-08-07 for HPG and VNINDEX) -- not a general OHLC history cache, not
    a daily-refreshed price series, and not a replacement for vn_stock.db. There
    is no fetch/refresh code path here; materialization is a separate, explicit,
    offline step (see tools/ingest_dnse_market_risk_evidence.py).

WHY RAW OHLC, NOT PRE-COMPUTED RETURNS
    Persisting the same ``{"o","h","l","c","t"}`` shape the qualified contracts
    already parse (``dnse_current_state_price_analytics.normalize_bars()``,
    reused as-is by ``dnse_index_return_series_capability.py``) means the
    existing, already-tested qualification/gap-detection/return pipeline runs
    completely unmodified on top of this store -- zero change to the frozen
    beta/correlation math contract in ``dnse_current_state_market_risk.py``.

NO NETWORK I/O, NO SECRETS
    This module never calls DNSE and never reads secrets.env. It only reads and
    writes local JSON files under the runtime root. ``"v"`` (volume) and any
    pagination cursor (``"nextTime"``) are stripped before persistence -- never
    retained, never read back.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from atomic_io import atomic_write_file, validate_json_file

STORE_SCHEMA_VERSION = "1.0.0"
PROVIDER = "DNSE"
STORE_RELATIVE = Path("data") / "dnse-market-risk-evidence"
STOCK_OHLC_RELATIVE = STORE_RELATIVE / "stock-ohlc"
BENCHMARK_OHLC_RELATIVE = STORE_RELATIVE / "benchmark-ohlc"

# The only fields this store ever persists or reads back -- matches
# dnse_current_state_price_analytics._REQUIRED_OHLC_FIELDS exactly (not
# imported, so this store's own contract does not silently drift if that
# module's tuple ever changes; a mismatch would surface as a normalize_bars()
# error at read time, not a silent gap).
REQUIRED_OHLC_FIELDS: tuple[str, ...] = ("o", "h", "l", "c", "t")


class DnseMarketRiskEvidenceStoreError(ValueError):
    """Fail-closed rejection when persisting structurally invalid evidence."""


def stock_ohlc_path(runtime_root: Path | str, ticker: str) -> Path:
    return Path(runtime_root) / STOCK_OHLC_RELATIVE / f"{str(ticker).strip().upper()}.json"


def benchmark_ohlc_path(runtime_root: Path | str, benchmark_id: str) -> Path:
    return Path(runtime_root) / BENCHMARK_OHLC_RELATIVE / f"{str(benchmark_id).strip().upper()}.json"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _sanitize_ohlc(raw_ohlc: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Keep only o/h/l/c/t -- never volume, never a pagination cursor, never
    any other field a provider response happens to carry. Fails closed on a
    missing field or a parallel-array length mismatch."""
    for key in REQUIRED_OHLC_FIELDS:
        if key not in raw_ohlc or not isinstance(raw_ohlc[key], list):
            raise DnseMarketRiskEvidenceStoreError(f"raw_ohlc_missing_or_invalid_field:{key}")
    lengths = {len(raw_ohlc[key]) for key in REQUIRED_OHLC_FIELDS}
    if len(lengths) != 1:
        raise DnseMarketRiskEvidenceStoreError(f"raw_ohlc_field_length_mismatch:{lengths}")
    return {key: list(raw_ohlc[key]) for key in REQUIRED_OHLC_FIELDS}


def _write(path: Path, symbol: str, kind: str, raw_ohlc: Mapping[str, Any],
          *, provenance: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_ohlc(raw_ohlc)
    payload = {
        "schema_version": STORE_SCHEMA_VERSION,
        "symbol": str(symbol).strip().upper(),
        "kind": kind,
        "provider": PROVIDER,
        "raw_ohlc": sanitized,
        "session_count": len(sanitized["t"]),
        "provenance": dict(provenance),
    }
    atomic_write_file(path, _canonical_json(payload), validator=validate_json_file)
    return payload


def write_stock_ohlc(
    runtime_root: Path | str, ticker: str, raw_ohlc: Mapping[str, Any], *, provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Deterministically persist a stock ticker's qualified raw OHLC window.
    Re-ingesting overwrites the prior file atomically (last write wins) --
    replaying the same input produces a byte-identical file."""
    return _write(stock_ohlc_path(runtime_root, ticker), ticker, "stock", raw_ohlc, provenance=provenance)


def write_benchmark_ohlc(
    runtime_root: Path | str, benchmark_id: str, raw_ohlc: Mapping[str, Any], *, provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Deterministically persist a benchmark's qualified raw OHLC window. Same
    overwrite-is-idempotent contract as write_stock_ohlc."""
    return _write(benchmark_ohlc_path(runtime_root, benchmark_id), benchmark_id, "benchmark",
                 raw_ohlc, provenance=provenance)


def read_stock_ohlc(runtime_root: Path | str, ticker: str) -> dict[str, Any] | None:
    """None when nothing has been retained for this ticker (the expected,
    common case for every ticker outside the evidence-bounded set) -- never
    raises for a missing file. A malformed retained file (corrupt JSON) does
    raise; the caller's own fail-closed wrapper is responsible for catching
    that, matching dnse_foreign_flow_store.read_observations()'s convention."""
    path = stock_ohlc_path(runtime_root, ticker)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_benchmark_ohlc(runtime_root: Path | str, benchmark_id: str) -> dict[str, Any] | None:
    """Same contract as read_stock_ohlc, for the benchmark side."""
    path = benchmark_ohlc_path(runtime_root, benchmark_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
