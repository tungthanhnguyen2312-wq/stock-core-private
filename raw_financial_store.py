"""Incremental, hash-stated store for market-wide raw financial observations.

LAYOUT (all beneath the runtime root -- generated runtime data, never the source repo)

    data/market-wide-financials/
        observations/<TICKER>.jsonl.gz   one deterministic shard per ticker
        ingest_state.json                per-ticker input hashes + shard hashes
        coverage_report.json             deterministic coverage statistics
        coverage_by_ticker.csv           the same coverage, one row per ticker

WHY A SHARD PER TICKER
    The universe produces ~1.6M observations. A single append-only JSONL (the Phase 14B
    pilot's shape) cannot express "this ticker's payload changed, nothing else did"
    without rewriting or scanning the whole file, and its append semantics silently keep
    superseded rows forever. A shard per ticker makes the incremental unit the same as the
    unit of change, and makes each unit independently hash-verifiable.

INCREMENTAL CONTRACT
    A ticker is rebuilt only when its `inputs_fingerprint` (the sorted set of its payload
    filenames and their SHA-256s) differs from the recorded one, or when its shard is
    missing or its bytes no longer match `shard_sha256`. Everything else is reported
    `unchanged` and not rewritten. A second run over untouched inputs therefore writes
    nothing at all and reports `rebuilt: 0`.

DETERMINISM
    Shard bytes are gzip with `mtime=0` over the canonical JSONL body, so a shard is
    byte-identical across rebuilds on identical inputs -- on any machine, at any time.
    `ingest_state.json` carries `generated_at`, which is the one field expected to differ
    between two runs; it is excluded from `state_fingerprint`.

ORPHANS ARE REPORTED, NEVER DELETED
    A shard whose ticker no longer has any payload is listed in `orphaned_shards`. Removing
    retained observations is a data-loss decision and is left to the operator.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from atomic_io import atomic_write_file, atomic_write_json
from raw_financial_observations import (
    PayloadNameError,
    SCHEMA_VERSION as OBSERVATION_SCHEMA_VERSION,
    STATEMENT_FAMILIES,
    content_fingerprint,
    extract_payload,
    observation_lines,
    parse_payload_name,
    read_payload,
    sha256_file,
)

STORE_SCHEMA_VERSION = "1.0.0"

STORE_RELATIVE = Path("data") / "market-wide-financials"
OBSERVATIONS_RELATIVE = STORE_RELATIVE / "observations"
STATE_FILENAME = "ingest_state.json"
SOURCE_RELATIVE = Path("data_bctc")

_SHARD_SUFFIX = ".jsonl.gz"


def store_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / STORE_RELATIVE


def observations_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / OBSERVATIONS_RELATIVE


def state_path(runtime_root: Path | str) -> Path:
    return store_root(runtime_root) / STATE_FILENAME


def shard_path(runtime_root: Path | str, ticker: str) -> Path:
    return observations_root(runtime_root) / f"{ticker.upper()}{_SHARD_SUFFIX}"


def source_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / SOURCE_RELATIVE


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def encode_shard(observations: Iterable[Mapping[str, Any]]) -> bytes:
    """Deterministic gzip bytes for a shard. `mtime=0` keeps the bytes clock-independent."""
    body = observation_lines(observations).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=9) as handle:
        handle.write(body)
    return buffer.getvalue()


def decode_shard(raw: bytes) -> list[dict[str, Any]]:
    text = gzip.decompress(raw).decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def read_shard(runtime_root: Path | str, ticker: str) -> list[dict[str, Any]]:
    path = shard_path(runtime_root, ticker)
    if not path.exists():
        return []
    return decode_shard(path.read_bytes())


def discover_payloads(runtime_root: Path | str) -> dict[str, Any]:
    """Index `data_bctc/*.parquet` by ticker, accounting for every file found.

    Unparseable names land in `unparsed` rather than being dropped -- an unknown file in
    the source directory is a fact the operator needs to see.
    """
    root = source_root(runtime_root)
    by_ticker: dict[str, list[dict[str, str]]] = {}
    unparsed: list[dict[str, str]] = []
    paths = sorted(root.glob("*.parquet"), key=lambda path: path.name) if root.is_dir() else []
    for path in paths:
        try:
            identity = parse_payload_name(path.stem)
        except PayloadNameError as exc:
            unparsed.append({"source_file": path.name, "reason": str(exc)})
            continue
        by_ticker.setdefault(identity["ticker"], []).append({
            "source_file": path.name,
            "statement_family": identity["statement_family"],
            "reporting_frequency": identity["reporting_frequency"],
        })
    for entries in by_ticker.values():
        entries.sort(key=lambda entry: entry["source_file"])
    return {
        "source_root": str(root),
        "payload_count": len(paths),
        "ticker_count": len(by_ticker),
        "by_ticker": dict(sorted(by_ticker.items())),
        "unparsed": unparsed,
    }


def _ticker_inputs(runtime_root: Path | str, entries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    root = source_root(runtime_root)
    inputs = []
    for entry in entries:
        path = root / str(entry["source_file"])
        inputs.append({
            "source_file": entry["source_file"],
            "statement_family": entry["statement_family"],
            "reporting_frequency": entry["reporting_frequency"],
            "source_sha256": sha256_file(path),
        })
    inputs.sort(key=lambda item: item["source_file"])
    return inputs


def _inputs_fingerprint(inputs: list[Mapping[str, Any]]) -> str:
    """Identity of everything a shard's bytes depend on.

    The extraction schema version is part of it deliberately. Keying only on the source
    payload hashes would leave every existing shard looking `unchanged` after a change to
    the extraction logic itself, so the store would keep serving observations built by code
    that no longer exists -- a silent staleness the `--check` pass would then report as
    `not_byte_reproducible` with no way to fix it short of deleting the store by hand.
    """
    return _fingerprint({
        "observation_schema_version": OBSERVATION_SCHEMA_VERSION,
        "store_schema_version": STORE_SCHEMA_VERSION,
        "payloads": [[item["source_file"], item["source_sha256"]] for item in inputs],
    })


def build_ticker_shard(runtime_root: Path | str, ticker: str,
                       inputs: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Extract every payload for one ticker into a single ordered observation set."""
    root = source_root(runtime_root)
    observations: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for item in inputs:
        path = root / str(item["source_file"])
        try:
            extracted = extract_payload(
                read_payload(path),
                ticker=ticker,
                statement_family=str(item["statement_family"]),
                reporting_frequency=str(item["reporting_frequency"]),
                source_file=str(item["source_file"]),
                source_sha256=str(item["source_sha256"]),
            )
        except Exception as exc:  # an unreadable payload is a reported failure, never a gap
            failures.append({"source_file": item["source_file"],
                             "reason": f"payload_unreadable:{type(exc).__name__}"})
            continue
        observations.extend(extracted["observations"])
        payloads.append({
            "source_file": extracted["source_file"],
            "source_sha256": extracted["source_sha256"],
            "statement_family": extracted["statement_family"],
            "reporting_frequency": extracted["reporting_frequency"],
            "provider": extracted["provider"],
            "scraped_at": extracted["scraped_at"],
            "observations": len(extracted["observations"]),
            "reporting_periods": extracted["reporting_periods"],
            "raw_item_id_count": len(extracted["raw_item_ids"]),
            "repeated_raw_item_ids": len(extracted["repeated_raw_item_ids"]),
            "duplicate_period_columns": extracted["duplicate_period_columns"],
            "rows_without_values": len(extracted["rows_without_values"]),
            "malformed_values": len(extracted["malformed_values"]),
            "reconciliation": extracted["reconciliation"],
        })
    observations.sort(key=lambda record: (
        record["statement_family"], record["reporting_frequency"],
        record["reporting_period"], record["period_variant_index"],
        record["row_ordinal"], record["observation_id"]))
    return {"ticker": ticker.upper(), "observations": observations,
            "payloads": payloads, "failures": failures}


def _shard_record(ticker: str, inputs: list[Mapping[str, Any]], built: Mapping[str, Any],
                  shard_bytes: bytes) -> dict[str, Any]:
    observations = built["observations"]
    families = sorted({str(record["statement_family"]) for record in observations})
    periods = sorted({str(record["reporting_period"]) for record in observations})
    providers = sorted({str(record["provider"]) for record in observations
                        if record.get("provider")})
    return {
        "ticker": ticker.upper(),
        "shard": f"{ticker.upper()}{_SHARD_SUFFIX}",
        "shard_sha256": hashlib.sha256(shard_bytes).hexdigest(),
        "shard_bytes": len(shard_bytes),
        "content_fingerprint": content_fingerprint(observations),
        "inputs_fingerprint": _inputs_fingerprint(list(inputs)),
        "observation_count": len(observations),
        "statement_families": families,
        "missing_statement_families": [family for family in STATEMENT_FAMILIES
                                       if family not in families],
        "providers": providers,
        "reporting_periods": periods,
        "first_reporting_period": periods[0] if periods else None,
        "last_reporting_period": periods[-1] if periods else None,
        "payloads": built["payloads"],
        "failures": built["failures"],
    }


def load_state(runtime_root: Path | str) -> dict[str, Any]:
    path = state_path(runtime_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, Mapping) or payload.get("schema_version") != STORE_SCHEMA_VERSION:
        return {}
    return dict(payload)


def state_index(state: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(state, Mapping):
        return {}
    return {str(record["ticker"]): dict(record)
            for record in (state.get("tickers") or [])
            if isinstance(record, Mapping) and record.get("ticker")}


def ingest(runtime_root: Path | str, *, generated_at: str, execute: bool = False,
           tickers: Iterable[str] | None = None) -> dict[str, Any]:
    """Ingest every retained payload into the store, rebuilding only what changed.

    With `execute=False` nothing is written: the plan is computed in full (including the
    hashes that decide `unchanged` vs `rebuilt`) and returned, so a dry run answers "what
    would this do" exactly rather than approximately.
    """
    runtime_root = Path(runtime_root)
    discovered = discover_payloads(runtime_root)
    previous = state_index(load_state(runtime_root))
    wanted = {ticker.upper() for ticker in tickers} if tickers is not None else None

    records: list[dict[str, Any]] = []
    rebuilt: list[str] = []
    unchanged: list[str] = []
    skipped: list[str] = []
    failures: list[dict[str, Any]] = []

    for ticker, entries in discovered["by_ticker"].items():
        if wanted is not None and ticker not in wanted:
            if ticker in previous:
                records.append(previous[ticker])
                skipped.append(ticker)
            continue
        inputs = _ticker_inputs(runtime_root, entries)
        fingerprint = _inputs_fingerprint(inputs)
        prior = previous.get(ticker)
        path = shard_path(runtime_root, ticker)
        if (prior is not None
                and prior.get("inputs_fingerprint") == fingerprint
                and path.exists()
                and sha256_file(path) == prior.get("shard_sha256")):
            records.append(prior)
            unchanged.append(ticker)
            continue

        built = build_ticker_shard(runtime_root, ticker, inputs)
        shard_bytes = encode_shard(built["observations"])
        record = _shard_record(ticker, inputs, built, shard_bytes)
        if built["failures"]:
            failures.extend({"ticker": ticker, **failure} for failure in built["failures"])
        if execute:
            atomic_write_file(path, shard_bytes)
        records.append(record)
        rebuilt.append(ticker)

    records.sort(key=lambda record: record["ticker"])
    known = {record["ticker"] for record in records}
    orphaned = sorted(
        path.name[: -len(_SHARD_SUFFIX)]
        for path in (observations_root(runtime_root).glob(f"*{_SHARD_SUFFIX}")
                     if observations_root(runtime_root).is_dir() else [])
        if path.name[: -len(_SHARD_SUFFIX)] not in known
    )

    state = {
        "schema_version": STORE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_root": discovered["source_root"],
        "store_root": str(store_root(runtime_root)),
        "payload_count": discovered["payload_count"],
        "unparsed_payloads": discovered["unparsed"],
        "ticker_count": len(records),
        "observation_count": sum(int(record["observation_count"]) for record in records),
        "tickers": records,
        "orphaned_shards": orphaned,
        "extraction_failures": failures,
    }
    state["state_fingerprint"] = _fingerprint(
        {key: value for key, value in state.items() if key != "generated_at"})
    if execute:
        atomic_write_json(state_path(runtime_root), state)

    return {
        "executed": execute,
        "state": state,
        "rebuilt": rebuilt,
        "unchanged": unchanged,
        "skipped": skipped,
        "orphaned_shards": orphaned,
        "extraction_failures": failures,
        "counts": {
            "payloads": discovered["payload_count"],
            "tickers": len(records),
            "rebuilt": len(rebuilt),
            "unchanged": len(unchanged),
            "skipped": len(skipped),
            "observations": state["observation_count"],
            "unparsed_payloads": len(discovered["unparsed"]),
            "extraction_failures": len(failures),
        },
    }


def verify(runtime_root: Path | str) -> dict[str, Any]:
    """Re-derive every shard in memory and compare against what is on disk.

    Never writes. Reports `shard_missing`, `shard_sha256_mismatch` (the bytes on disk are
    not what the recorded state says) and `content_drift` (the bytes on disk are stale
    relative to the current payloads) separately, because they mean different things.
    """
    runtime_root = Path(runtime_root)
    state = load_state(runtime_root)
    if not state:
        return {"ok": False, "reason": "state_missing_or_unsupported_schema", "findings": []}
    discovered = discover_payloads(runtime_root)
    findings: list[dict[str, Any]] = []
    checked = 0
    for record in state.get("tickers") or []:
        ticker = str(record["ticker"])
        path = shard_path(runtime_root, ticker)
        if not path.exists():
            findings.append({"ticker": ticker, "finding": "shard_missing"})
            continue
        actual = sha256_file(path)
        if actual != record.get("shard_sha256"):
            findings.append({"ticker": ticker, "finding": "shard_sha256_mismatch",
                             "recorded": record.get("shard_sha256"), "actual": actual})
            continue
        entries = discovered["by_ticker"].get(ticker)
        if entries is None:
            findings.append({"ticker": ticker, "finding": "payloads_missing_for_recorded_ticker"})
            continue
        inputs = _ticker_inputs(runtime_root, entries)
        if _inputs_fingerprint(inputs) != record.get("inputs_fingerprint"):
            findings.append({"ticker": ticker, "finding": "content_drift",
                             "reason": "source payloads changed since the shard was built"})
            continue
        rebuilt = encode_shard(build_ticker_shard(runtime_root, ticker, inputs)["observations"])
        if hashlib.sha256(rebuilt).hexdigest() != actual:
            findings.append({"ticker": ticker, "finding": "not_byte_reproducible"})
            continue
        checked += 1
    missing_from_state = sorted(set(discovered["by_ticker"]) - {
        str(record["ticker"]) for record in (state.get("tickers") or [])})
    findings.extend({"ticker": ticker, "finding": "ticker_not_in_state"}
                    for ticker in missing_from_state)
    return {"ok": not findings, "checked": checked, "findings": findings,
            "state_fingerprint": state.get("state_fingerprint")}
