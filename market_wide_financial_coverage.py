"""Deterministic market-wide coverage statistics over the raw financial observation store.

WHAT IT MEASURES
    Three separate questions, deliberately not collapsed into one number:

    1. **Retention coverage** -- which active-universe tickers have a retained payload for
       each statement family, and how many raw observations each carries.
    2. **Archetype coverage** -- how many issuers have a resolved archetype, under which
       authority, and what that implies for EBITDA / EV-EBITDA applicability.
    3. **Canonical identity coverage** -- for each canonical metric, how many *applicable*
       tickers carry at least one raw line item that is a known candidate for it.

WHAT "CANONICAL IDENTITY COVERAGE" IS AND IS NOT
    It answers "is the raw line item there to map from", not "is the value qualified".
    Statement scope, currency, unit scale, sign convention and cumulative-vs-discrete basis
    are all still `unknown` in the retained payloads, so nothing measured here is an
    evidence-qualified value and this module never claims otherwise. It exists to size the
    next milestone honestly: a metric at 0% identity coverage needs data acquisition, a
    metric at 99% identity coverage needs a mapping rule.

THE TWO PROVIDER DIALECTS
    The retained cash-flow payloads use two mutually exclusive vocabularies -- 905 of 1,243
    corporate payloads say `depreciation_of_fixed_assets_and_investment_properties` and the
    other 338 say `depreciation_and_amortization`; likewise `operating_cash_flow` vs
    `net_cash_inflows_outflows_from_operating_activities`. A candidate set that knows only
    one dialect reports ~73% coverage on a metric that is actually present for ~100% of
    filers. `config/canonical_metric_candidates.csv` carries a `dialect` column for exactly
    this reason, and the per-metric breakdown reports coverage by dialect so a future
    single-dialect regression is visible instead of silent.

DETERMINISM
    Every number is derived from the retained payload bytes and the two tracked config
    files. `generated_at` is the only clock-dependent field and is excluded from
    `coverage_fingerprint`.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from financial_entity_applicability import (
    CORPORATE_ONLY_METRICS,
    VERSION as APPLICABILITY_VERSION,
    evaluate_ticker,
    load_entity_profiles,
)
from raw_financial_observations import STATEMENT_FAMILIES, sha256_file
from raw_financial_store import load_state, read_shard, shard_path
from statement_taxonomy_sidecar import load_sidecar, taxonomy_index

COVERAGE_SCHEMA_VERSION = "1.0.0"
COVERAGE_FILENAME = "coverage_report.json"
COVERAGE_CSV_FILENAME = "coverage_by_ticker.csv"

CANDIDATES_RELATIVE = Path("config") / "canonical_metric_candidates.csv"
PROFILES_RELATIVE = Path("config") / "ticker_entity_profiles.csv"
UNIVERSE_FILENAME = "screen_snapshot.csv"

#: Mirrors `live_universe.py`. Membership of the *financial* universe must not depend on
#: whether a ticker happened to trade on the reference date -- a company that did not trade
#: on Thursday still filed its statements.
ACTIVE_EXCHANGES = frozenset({"HSX", "HNX", "UPCOM"})
EQUITY_TYPES = frozenset({"STOCK", "EQUITY", "COMMON_STOCK"})
INDEX_OR_SYNTHETIC = frozenset({"VNINDEX", "HNXINDEX", "UPCOMINDEX"})

#: The project's derived-EBITDA identity (`docs/hpg_fy2024_ebitda_qualification.md`).
EBITDA_INPUT_METRICS = ("profit_before_tax", "interest_expense", "depreciation_amortization")
#: Enterprise value also needs market capitalisation, which stays blocked on the price
#: basis. These are the balance-sheet inputs only.
ENTERPRISE_VALUE_BALANCE_INPUTS = ("cash_and_equivalents", "short_term_debt", "long_term_debt")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def load_candidates(path: Path | str) -> dict[str, list[dict[str, Any]]]:
    """`config/canonical_metric_candidates.csv` -> {canonical_metric: [candidate, ...]}."""
    path = Path(path)
    candidates: dict[str, list[dict[str, Any]]] = {}
    if not path.is_file():
        return candidates
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            metric = str(row.get("canonical_metric") or "").strip()
            item_id = str(row.get("raw_item_id") or "").strip()
            if not metric or not item_id:
                continue
            candidates.setdefault(metric, []).append({
                "template_family": str(row.get("template_family") or "").strip(),
                "statement_family": str(row.get("statement_family") or "").strip(),
                "raw_item_id": item_id,
                "dialect": str(row.get("dialect") or "").strip() or "common",
                "priority": int(str(row.get("priority") or "0").strip() or 0),
            })
    for entries in candidates.values():
        entries.sort(key=lambda entry: (-entry["priority"], entry["template_family"],
                                        entry["statement_family"], entry["raw_item_id"]))
    return dict(sorted(candidates.items()))


def load_universe(runtime_root: Path | str) -> dict[str, Any]:
    """The active listed-equity universe, read from the runtime screening snapshot.

    A missing snapshot is reported, never silently replaced by "every ticker in the store".
    """
    import pandas as pd

    path = Path(runtime_root) / UNIVERSE_FILENAME
    if not path.is_file():
        return {"source_file": UNIVERSE_FILENAME, "source_sha256": None,
                "available": False, "reason": "screen_snapshot_absent",
                "tickers": [], "by_exchange": {}, "row_count": 0}
    frame = pd.read_csv(path)
    rows: list[dict[str, str]] = []
    for record in frame.to_dict("records"):
        ticker = str(record.get("ticker") or "").strip().upper()
        if not ticker or ticker in INDEX_OR_SYNTHETIC:
            continue
        exchange = (str(record.get("listing_exchange") or "").strip().upper()
                    or str(record.get("exchange") or "").strip().upper())
        instrument = str(record.get("instrument_type") or "").strip().upper()
        if exchange not in ACTIVE_EXCHANGES:
            continue
        if instrument and instrument not in EQUITY_TYPES:
            continue
        rows.append({"ticker": ticker, "exchange": exchange})
    by_exchange: dict[str, int] = {}
    for row in rows:
        by_exchange[row["exchange"]] = by_exchange.get(row["exchange"], 0) + 1
    exchange_of = {row["ticker"]: row["exchange"] for row in rows}
    return {
        "source_file": UNIVERSE_FILENAME,
        "source_sha256": sha256_file(path),
        "available": True,
        "row_count": int(len(frame)),
        "tickers": sorted(exchange_of),
        "exchange_of": exchange_of,
        "by_exchange": dict(sorted(by_exchange.items())),
    }


def _shard_index(runtime_root: Path | str, ticker: str) -> dict[str, Any]:
    """Reduce one ticker's shard to the facts coverage needs, without holding the rows."""
    observations = read_shard(runtime_root, ticker)
    ids_by_family: dict[str, set[str]] = {}
    periods: set[str] = set()
    providers: set[str] = set()
    ambiguous = 0
    duplicate_periods = 0
    for observation in observations:
        family = str(observation.get("statement_family") or "")
        ids_by_family.setdefault(family, set()).add(str(observation.get("raw_item_id") or ""))
        periods.add(str(observation.get("reporting_period") or ""))
        if observation.get("provider"):
            providers.add(str(observation["provider"]))
        warnings = observation.get("warnings") or []
        if "ambiguous_raw_item_id" in warnings:
            ambiguous += 1
        if "duplicate_period_column" in warnings:
            duplicate_periods += 1
    return {
        "observation_count": len(observations),
        "ids_by_family": ids_by_family,
        "all_ids": set().union(*ids_by_family.values()) if ids_by_family else set(),
        "families": sorted(ids_by_family),
        "reporting_periods": sorted(periods),
        "providers": sorted(providers),
        "ambiguous_observations": ambiguous,
        "duplicate_period_observations": duplicate_periods,
    }


def _metric_present(index: Mapping[str, Any], candidates: Iterable[Mapping[str, Any]],
                    template_family: str | None) -> dict[str, Any]:
    """Is at least one candidate raw identity for this metric present for this ticker?"""
    matched: list[dict[str, str]] = []
    for candidate in candidates:
        wanted_family = candidate["template_family"]
        if wanted_family and template_family and wanted_family != template_family:
            continue
        if wanted_family and not template_family and wanted_family != "corporate_vas":
            # With no resolved template we only consider the corporate candidate set, and
            # the result is reported as unresolved-archetype rather than as a corporate fact.
            continue
        present = index["ids_by_family"].get(candidate["statement_family"], set())
        if candidate["raw_item_id"] in present:
            matched.append({"raw_item_id": candidate["raw_item_id"],
                            "statement_family": candidate["statement_family"],
                            "dialect": candidate["dialect"]})
    return {"present": bool(matched), "matched": matched,
            "dialects": sorted({entry["dialect"] for entry in matched})}


def build_coverage(runtime_root: Path | str, *, source_root: Path | str,
                   generated_at: str) -> dict[str, Any]:
    """Compute the full coverage report. Read-only over the store and the two config files."""
    runtime_root = Path(runtime_root)
    source_root = Path(source_root)

    state = load_state(runtime_root)
    store_tickers = sorted({str(record["ticker"]) for record in (state.get("tickers") or [])})
    universe = load_universe(runtime_root)
    universe_tickers = set(universe.get("tickers") or [])
    exchange_of = universe.get("exchange_of") or {}

    profiles = load_entity_profiles(source_root / PROFILES_RELATIVE)
    candidates = load_candidates(source_root / CANDIDATES_RELATIVE)
    taxonomies = taxonomy_index(load_sidecar(runtime_root))

    metric_names = sorted(candidates)
    records: list[dict[str, Any]] = []

    for ticker in store_tickers:
        index = _shard_index(runtime_root, ticker)
        verdict = evaluate_ticker(
            ticker,
            manual_entity_type=profiles.get(ticker),
            balance_sheet_taxonomy=taxonomies.get(ticker),
            income_statement_item_ids=(index["ids_by_family"].get("income_statement")
                                       if "income_statement" in index["ids_by_family"] else None),
        )
        archetype = verdict["archetype"]
        template_family = archetype.get("template_family")
        metric_presence = {
            metric: _metric_present(index, candidates[metric], template_family)
            for metric in metric_names
        }
        applicability = verdict["metric_applicability"]
        ebitda_inputs = {metric: metric_presence.get(metric, {}).get("present", False)
                         for metric in EBITDA_INPUT_METRICS}
        ev_inputs = {metric: metric_presence.get(metric, {}).get("present", False)
                     for metric in ENTERPRISE_VALUE_BALANCE_INPUTS}
        records.append({
            "ticker": ticker,
            "exchange": exchange_of.get(ticker),
            "in_active_universe": ticker in universe_tickers,
            "issuer_entity_type": archetype.get("issuer_entity_type"),
            "archetype_authority": archetype.get("authority"),
            "template_family": template_family,
            "evidence_agreement": archetype.get("evidence_agreement"),
            "statement_families": index["families"],
            "missing_statement_families": [family for family in STATEMENT_FAMILIES
                                           if family not in index["families"]],
            "providers": index["providers"],
            "observation_count": index["observation_count"],
            "ambiguous_observations": index["ambiguous_observations"],
            "duplicate_period_observations": index["duplicate_period_observations"],
            "first_reporting_period": (index["reporting_periods"][0]
                                       if index["reporting_periods"] else None),
            "last_reporting_period": (index["reporting_periods"][-1]
                                      if index["reporting_periods"] else None),
            "reporting_period_count": len(index["reporting_periods"]),
            "metric_applicability": {metric: applicability[metric]["status"]
                                     for metric in CORPORATE_ONLY_METRICS},
            "canonical_identity_present": sorted(metric for metric in metric_names
                                                 if metric_presence[metric]["present"]),
            "canonical_identity_dialects": {
                metric: metric_presence[metric]["dialects"]
                for metric in metric_names if metric_presence[metric]["dialects"]},
            "ebitda_inputs_present": ebitda_inputs,
            "ebitda_inputs_complete": all(ebitda_inputs.values()),
            "enterprise_value_balance_inputs_complete": all(ev_inputs.values()),
        })

    records.sort(key=lambda record: record["ticker"])
    active = [record for record in records if record["in_active_universe"]]

    def _tally(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = row.get(key)
            label = "null" if value is None else str(value)
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items()))

    family_presence = {
        family: sum(1 for record in active if family in record["statement_families"])
        for family in STATEMENT_FAMILIES
    }

    metric_summary = []
    for metric in metric_names:
        applicable = [record for record in active
                      if not (metric in CORPORATE_ONLY_METRICS
                              and record["metric_applicability"].get(metric) == "not_applicable")]
        present = [record for record in applicable
                   if metric in record["canonical_identity_present"]]
        dialects: dict[str, int] = {}
        for record in present:
            for dialect in record["canonical_identity_dialects"].get(metric, []):
                dialects[dialect] = dialects.get(dialect, 0) + 1
        metric_summary.append({
            "canonical_metric": metric,
            "candidate_item_ids": len(candidates[metric]),
            "active_universe_tickers": len(active),
            "raw_identity_present": len(present),
            "raw_identity_absent": len(active) - len(present),
            "coverage_ratio": (round(len(present) / len(active), 6) if active else 0.0),
            "by_dialect": dict(sorted(dialects.items())),
        })

    # "Not excluded" is not the same as "applicable": it is every ticker the archetype layer
    # has not positively ruled out, which includes the large `insufficient_evidence` block.
    # Naming it honestly keeps the denominator from reading as a stronger claim than it is.
    not_excluded = [record for record in active
                    if record["metric_applicability"].get("ebitda") != "not_applicable"]
    ebitda_ready = [record for record in not_excluded if record["ebitda_inputs_complete"]]
    ev_ready = [record for record in not_excluded
                if record["enterprise_value_balance_inputs_complete"]]
    confirmed_applicable = [record for record in not_excluded
                            if record["metric_applicability"].get("ebitda")
                            == "applicable_subject_to_inputs"]

    report = {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "applicability_version": APPLICABILITY_VERSION,
        "runtime_root": str(runtime_root),
        "universe": {key: value for key, value in universe.items()
                     if key not in {"tickers", "exchange_of"}},
        "store": {
            "state_fingerprint": state.get("state_fingerprint"),
            "ticker_count": len(store_tickers),
            "observation_count": state.get("observation_count"),
            "payload_count": state.get("payload_count"),
        },
        "reconciliation": {
            "store_tickers": len(store_tickers),
            "active_universe_tickers": len(universe_tickers),
            "in_store_and_active_universe": len(active),
            "in_store_not_in_active_universe": len(records) - len(active),
            "in_active_universe_without_store_shard": len(
                universe_tickers - set(store_tickers)),
            "active_universe_tickers_missing_from_store": sorted(
                universe_tickers - set(store_tickers)),
        },
        "statement_family_coverage": {
            "active_universe_tickers": len(active),
            "with_family": family_presence,
            "with_all_three_families": sum(
                1 for record in active if not record["missing_statement_families"]),
            "with_no_family": sum(1 for record in active if not record["statement_families"]),
        },
        "archetype_coverage": {
            "by_authority": _tally(active, "archetype_authority"),
            "by_template_family": _tally(active, "template_family"),
            "by_issuer_entity_type": _tally(active, "issuer_entity_type"),
            "by_evidence_agreement": _tally(active, "evidence_agreement"),
        },
        "metric_applicability": {
            metric: dict(sorted(
                (status, sum(1 for record in active
                             if record["metric_applicability"].get(metric) == status))
                for status in sorted({record["metric_applicability"].get(metric)
                                      for record in active} - {None})))
            for metric in CORPORATE_ONLY_METRICS
        },
        "canonical_identity_coverage": metric_summary,
        "derived_metric_readiness": {
            "ebitda": {
                "formula": "profit_before_tax + interest_expense + depreciation_and_amortization",
                "not_excluded_tickers": len(not_excluded),
                "confirmed_applicable_tickers": len(confirmed_applicable),
                "all_raw_identities_present": len(ebitda_ready),
                "coverage_ratio": (round(len(ebitda_ready) / len(not_excluded), 6)
                                   if not_excluded else 0.0),
                "input_presence": {
                    metric: sum(1 for record in not_excluded
                                if record["ebitda_inputs_present"].get(metric))
                    for metric in EBITDA_INPUT_METRICS
                },
                "note": ("raw identity availability only; scope, unit, sign and cumulative "
                         "basis are unqualified, so no EBITDA value is asserted here. The "
                         "denominator is every ticker not positively ruled out, which still "
                         "includes the issuers whose archetype is unresolved"),
            },
            "enterprise_value": {
                "balance_sheet_inputs": list(ENTERPRISE_VALUE_BALANCE_INPUTS),
                "not_excluded_tickers": len(not_excluded),
                "balance_inputs_complete": len(ev_ready),
                "coverage_ratio": (round(len(ev_ready) / len(not_excluded), 6)
                                   if not_excluded else 0.0),
                "blocked_by": "market_capitalisation_requires_a_qualified_price_basis",
            },
        },
        "data_quality": {
            "observations_with_ambiguous_raw_item_id": sum(
                record["ambiguous_observations"] for record in records),
            "observations_from_duplicate_period_columns": sum(
                record["duplicate_period_observations"] for record in records),
            "tickers_with_both_providers": sum(1 for record in records
                                               if len(record["providers"]) > 1),
        },
        "records": records,
    }
    report["coverage_fingerprint"] = _fingerprint(
        {key: value for key, value in report.items() if key != "generated_at"})
    return report


CSV_COLUMNS = (
    "ticker", "exchange", "in_active_universe", "issuer_entity_type", "archetype_authority",
    "template_family", "evidence_agreement", "statement_families", "providers",
    "observation_count", "first_reporting_period", "last_reporting_period",
    "reporting_period_count", "ebitda_status", "ev_ebitda_status", "ebitda_inputs_complete",
    "enterprise_value_balance_inputs_complete", "canonical_identities_present",
)


def coverage_csv(report: Mapping[str, Any]) -> str:
    """One row per ticker, deterministic column order, LF line endings."""
    lines = [",".join(CSV_COLUMNS)]
    for record in report.get("records") or []:
        applicability = record.get("metric_applicability") or {}
        values = [
            record["ticker"],
            record.get("exchange") or "",
            "true" if record.get("in_active_universe") else "false",
            record.get("issuer_entity_type") or "",
            record.get("archetype_authority") or "",
            record.get("template_family") or "",
            record.get("evidence_agreement") or "",
            "|".join(record.get("statement_families") or []),
            "|".join(record.get("providers") or []),
            str(record.get("observation_count") or 0),
            record.get("first_reporting_period") or "",
            record.get("last_reporting_period") or "",
            str(record.get("reporting_period_count") or 0),
            applicability.get("ebitda") or "",
            applicability.get("ev_ebitda") or "",
            "true" if record.get("ebitda_inputs_complete") else "false",
            "true" if record.get("enterprise_value_balance_inputs_complete") else "false",
            str(len(record.get("canonical_identity_present") or [])),
        ]
        lines.append(",".join(str(value).replace(",", ";") for value in values))
    return "\n".join(lines) + "\n"
