"""Deterministic market-wide coverage report -- composes an already-discovered
universe with already-run ingestion manifests. No network I/O, no ticker
qualification: this is explicitly not a per-ticker qualification table (the
milestone this module supports says so directly), only a factual rollup of
what the universe looks like and what raw ingestion has and has not reached.

INPUTS ARE ALREADY-PRODUCED DATA, NEVER RE-DERIVED
    Every count here is taken from a ``dnse_instrument_universe.
    discover_universe``/``snapshot_manifest`` result and one or more
    ``market_raw_lake.build_manifest`` results. This module never talks to a
    provider, a checkpoint file, or the raw lake directly -- it is a pure
    projection, matching this project's established "coverage/rollup layers
    read, never recompute" convention (see e.g. ``research_financial_fact_
    projection.py``'s own doctrine).

"MISSING" HAS TWO DIFFERENT MEANINGS, KEPT SEPARATE
    A universe symbol a dataset run never attempted (``never_requested``) and
    a symbol it attempted but failed on (``failed``) are different facts
    (AI_RULES.md 8g: different kinds of "no value" are different facts, never
    collapsed together). Both feed ``not_yet_covered``, the actionable
    backlog, but are reported separately too.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
from typing import Any

from atomic_io import atomic_write_json

SCHEMA_VERSION = "1.0.0"

#: Already-established, already-documented semantic open questions this
#: milestone was explicitly told not to rediscover or silently resolve (see
#: the milestone brief's "EXISTING DNSE SEMANTICS" section and AI_RULES.md).
#: Surfaced here so a reader of the coverage report sees them without a
#: second document -- none of these block raw retention.
KNOWN_SEMANTIC_UNKNOWNS: tuple[dict[str, str], ...] = (
    {
        "topic": "board_code_semantics",
        "note": "G1=round lot, G4=odd lot, T1/T3=put-through round lot, T4/T6=put-through "
                "odd lot are established first-party mappings and are not rediscovered here.",
    },
    {
        "topic": "ohlc_price_basis",
        "note": "DNSE OHLC is ADJUSTED_CONFIRMED/retrospective for the evidenced HPG/VCB "
                "scope only; this is not promoted into universal raw-as-traded/PIT authority "
                "for the bulk-ingested universe.",
    },
    {
        "topic": "volume_unit_transform",
        "note": "No x10 or other volume-unit multiplier is assumed for any ticker beyond the "
                "prior HPG-specific observation; unresolved volume-unit/aggregation semantics "
                "do not block raw ingestion.",
    },
    {
        "topic": "exchange_market_id_label",
        "note": "DNSE marketId codes (e.g. STO, UPX) are retained verbatim as exchange_raw; "
                "mapping them to HOSE/HNX/UPCOM display labels is deferred semantic work, not "
                "yet backed by first-party documentation.",
    },
    {
        "topic": "instrument_class_coverage",
        "note": "Only securityGroupId=ST (equities) is empirically classified; ETF/WARRANT/"
                "RIGHT/BOND/DERIVATIVE codes are not yet observed and remain "
                "UNKNOWN_SECURITY_GROUP rather than guessed.",
    },
    {
        "topic": "foreign_flow_value_scope",
        "note": "DNSE foreign-flow VALUE production authority remains limited to its "
                "previously validated HPG/VNM/QNS scope; bulk raw ingestion elsewhere does not "
                "extend that authority.",
    },
)


def _sorted_list(values: Sequence[str]) -> list[str]:
    return sorted(set(values))


def _dataset_coverage(manifest: Mapping[str, Any], universe_symbols: set[str]) -> dict[str, Any]:
    requested = set(manifest.get("requested_units") or [])
    successful = set(manifest.get("successful_units") or [])
    failed_entries = list(manifest.get("failed_units") or [])
    failed_ids = {str(item.get("unit_id")) for item in failed_entries if isinstance(item, Mapping)}
    skipped = set(manifest.get("skipped_units") or [])
    never_requested = universe_symbols - requested
    not_yet_covered = sorted((universe_symbols - successful))

    return {
        "dataset": manifest.get("dataset"),
        "run_id": manifest.get("run_id"),
        "run_scope_id": manifest.get("run_scope_id"),
        "started_at": manifest.get("started_at"),
        "ended_at": manifest.get("ended_at"),
        "requested_unit_count": len(requested),
        "successful_unit_count": len(successful),
        "failed_unit_count": len(failed_ids),
        "skipped_unit_count": len(skipped),
        "coverage_ratio_of_requested": round(len(successful) / len(requested), 4) if requested else None,
        "coverage_ratio_of_universe": (round(len(successful) / len(universe_symbols), 4)
                                       if universe_symbols else None),
        "never_requested_count": len(never_requested),
        "never_requested_symbols": _sorted_list(never_requested),
        "failed_symbols": sorted(failed_ids),
        "not_yet_covered_count": len(not_yet_covered),
        "not_yet_covered_symbols": not_yet_covered,
        "output_dir": manifest.get("output_dir"),
        "checkpoint_file": manifest.get("checkpoint_file"),
    }


def build_coverage_report(
    *, generated_at: str,
    universe_status: str,
    universe_declared_total: int | None,
    universe_discovered_count: int,
    universe_by_exchange: Mapping[str, int],
    universe_by_instrument_class: Mapping[str, int],
    universe_symbols: Sequence[str],
    universe_malformed_record_count: int = 0,
    security_master_discovered_count: int | None = None,
    dataset_manifests: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Assemble the deterministic, non-qualification market-wide coverage report."""
    symbols_set = set(universe_symbols)
    datasets = [_dataset_coverage(manifest, symbols_set) for manifest in dataset_manifests]
    datasets.sort(key=lambda entry: (str(entry["dataset"]), str(entry["run_id"])))

    unknown_class_count = int(universe_by_instrument_class.get("UNKNOWN_SECURITY_GROUP", 0))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "universe": {
            "status": universe_status,
            "declared_total": universe_declared_total,
            "discovered_count": universe_discovered_count,
            "security_master_discovered_count": security_master_discovered_count,
            "by_exchange_raw": dict(sorted(universe_by_exchange.items())),
            "by_instrument_class": dict(sorted(universe_by_instrument_class.items())),
            "unknown_instrument_class_count": unknown_class_count,
            "malformed_record_count": universe_malformed_record_count,
        },
        "dataset_coverage": datasets,
        "dataset_count": len(datasets),
        "unresolved_semantic_issues": [dict(item) for item in KNOWN_SEMANTIC_UNKNOWNS],
        "is_ticker_qualification_table": False,
    }


def coverage_report_path(
    runtime_root: Path | str, *, provider: str, dataset: str, run_id: str,
    report: Mapping[str, Any],
) -> Path:
    """Return an immutable, content-addressed location for a coverage report."""
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    safe_run_id = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(run_id))
    return (Path(runtime_root) / "data" / "market_raw_lake" / "coverage"
            / f"{provider}__{dataset}__{safe_run_id}__{digest}.json")


def save_coverage_report(
    runtime_root: Path | str, *, provider: str, dataset: str, run_id: str,
    report: Mapping[str, Any],
) -> Path:
    """Persist one immutable coverage report, rejecting a hash collision mismatch."""
    path = coverage_report_path(
        runtime_root, provider=provider, dataset=dataset, run_id=run_id, report=report,
    )
    payload = dict(report)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError(f"coverage report collision at {path}")
        return path
    atomic_write_json(path, payload)
    return path
