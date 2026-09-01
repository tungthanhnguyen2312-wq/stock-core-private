"""Market-wide raw financial observation extraction.

WHAT THIS IS
    The first layer of the market-wide canonical financial pipeline: it turns one retained
    statement payload (`<runtime_root>/data_bctc/<TICKER>_<family>_<freq>.parquet`) into
    fully-provenanced raw observations -- one per (raw line item x populated reporting
    period column).

WHY IT RETAINS EVERYTHING
    `financial_observations.py` (the bounded Phase 14B pilot) keeps only the ~50 `item_id`
    values in its `_CODES` allowlist. That is the right shape for proving one contract on
    three tickers and the wrong shape for a market-wide platform: every later canonical
    mapping that needs an item nobody thought of yet would require re-fetching the whole
    universe from the provider. This module therefore has **no allowlist**. Selection is a
    mapping-layer concern, not a retention concern.

        retention_policy = "all_raw_items"

WHAT IT DOES NOT DO
    It resolves *identity*, never *meaning*. Statement scope (consolidated vs separate),
    currency, unit scale and cumulative-vs-discrete basis are not carried in the retained
    payloads, so every observation leaves them `unknown` and carries the matching warning.
    Nothing here is ever `qualified`; the highest state it can reach is `retained_raw`.
    Promoting an observation to a canonical, qualified fact is the next layer's job.

THE TWO IDENTITY HAZARDS THIS LAYER EXISTS TO MAKE VISIBLE
    1. `item_id` is not unique within a payload. HPG's income statement carries `revenue`
       twice -- gross revenue (line 1) and net revenue (line 3) -- and its balance sheet
       carries `short_term_investments` twice. Over a sample of 40 payloads, 21 had at
       least one repeated `item_id`. Any mapping keyed on `item_id` alone silently picks
       whichever row pandas happened to return first. Every observation therefore carries
       `row_ordinal` and `item_id_occurrence`, and repeated ids are flagged
       `ambiguous_raw_item_id` so a downstream mapping must disambiguate deliberately.
    2. Reporting-period columns repeat. A payload can carry both `2025-Q4` and
       `2025-Q4_1`; the suffix is a writer-side de-duplication artifact, not a period.
       Both normalize to the same `reporting_period`, are distinguished by
       `period_variant_index`, and every non-primary variant is flagged
       `duplicate_period_column` -- a restatement candidate, never silently collapsed.

DETERMINISM
    `observation_id` and `identity_key` are SHA-256 over canonical JSON of the identity
    fields only. The same payload bytes always produce the same ids, in the same order,
    with no timestamp anywhere in the record. Retrieval time comes from the payload's own
    `scraped_at` column, not from the clock.

RECONCILIATION
    `extract_payload` returns every input column in exactly one of `period_columns` or
    `non_period_columns`, and every input row in exactly one of `observations` (one or
    more) or `rows_without_values`. `reconciliation.inputs_fully_accounted` asserts it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

# Changes to source metadata must invalidate every observation shard.  In particular, VCI
# report metadata is evidence about the provider's representation, not a cosmetic payload
# annotation, so a store built before it was retained cannot remain current.
SCHEMA_VERSION = "1.1.0"

#: The three statement families the retained payloads cover.
STATEMENT_FAMILIES = ("balance_sheet", "income_statement", "cash_flow")
REPORTING_FREQUENCIES = ("quarter", "year")

#: No allowlist. See the module docstring.
RETENTION_POLICY = "all_raw_items"

#: The only qualification state this layer can assign. Scope/unit/basis are unknown here.
QUALIFICATION_STATE = "retained_raw"

_PAYLOAD_NAME_RE = re.compile(
    r"^(?P<ticker>[A-Za-z0-9]+)_(?P<family>balance_sheet|income_statement|cash_flow)"
    r"_(?P<frequency>quarter|year)(?:__(?P<provider>[A-Za-z0-9_-]+))?$"
)

# `2026-Q1`, `2025-Q4_1`, `2025Q4`, `2024`, `2024-Năm`, `2024_1`, `2024.1`
_PERIOD_COLUMN_RE = re.compile(
    r"^(?P<year>\d{4})(?:[-_.]?Q(?P<quarter>[1-4])|[-_.]?(?:YEAR|NĂM))?(?:[._-](?P<variant>\d+))?$",
    re.IGNORECASE,
)

_META_COLUMNS = ("ticker", "report_type", "source", "scraped_at", "item", "item_en", "item_id")


class PayloadNameError(ValueError):
    """A payload filename does not follow `<TICKER>_<family>_<frequency>`."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_payload_name(stem: str) -> dict[str, str]:
    """`HPG_balance_sheet_quarter` -> ticker/family/frequency. Raises on anything else.

    Raising rather than returning None is deliberate: an unparseable payload name means an
    unknown file landed in `data_bctc/`, and the caller must account for it explicitly
    instead of dropping it.
    """
    match = _PAYLOAD_NAME_RE.match(str(stem))
    if match is None:
        raise PayloadNameError(
            f"payload name {stem!r} does not match <TICKER>_<family>_<frequency>")
    identity = {
        "ticker": match.group("ticker").upper(),
        "statement_family": match.group("family"),
        "reporting_frequency": match.group("frequency"),
    }
    if match.group("provider"):
        identity["provider_suffix"] = match.group("provider")
    return identity


def normalize_period_column(column: Any) -> dict[str, Any] | None:
    """Parse one column header into a reporting period, or None when it is not one.

    Returns `{"reporting_period", "period_type", "variant_suffix"}`. `variant_suffix` is
    the writer-side de-duplication suffix (`_1` in `2025-Q4_1`) or None; it is *not* the
    variant index, which depends on how many columns share the period and is assigned by
    `extract_payload`.
    """
    text = str(column).strip()
    match = _PERIOD_COLUMN_RE.match(text)
    if match is None:
        return None
    year = match.group("year")
    quarter = match.group("quarter")
    variant = match.group("variant")
    if quarter:
        return {"reporting_period": f"{year}-Q{quarter}", "period_type": "quarterly",
                "variant_suffix": variant}
    return {"reporting_period": year, "period_type": "annual", "variant_suffix": variant}


def _number(value: Any) -> tuple[float | int | None, str | None]:
    """Coerce a cell to a JSON-safe number. Returns (value, malformed_reason)."""
    if value is None or isinstance(value, bool):
        return None, None if value is None else "value_not_numeric"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "value_not_numeric"
    if math.isnan(number):
        return None, None
    if math.isinf(number):
        return None, "value_not_finite"
    return (int(number) if number.is_integer() else number), None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def extract_payload(frame: Any, *, ticker: str, statement_family: str,
                    reporting_frequency: str, source_file: str,
                    source_sha256: str,
                    period_metadata: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Extract every raw observation carried by one retained statement payload.

    Pure: takes an already-loaded frame, performs no I/O, reads no clock. `frame` needs
    only `columns`, `iterrows()` and `__len__` -- a pandas DataFrame in production.
    """
    columns = [str(column) for column in frame.columns]
    parsed_columns: list[dict[str, Any]] = []
    non_period_columns: list[str] = []
    for position, column in enumerate(columns):
        parsed = normalize_period_column(column)
        if parsed is None:
            non_period_columns.append(column)
            continue
        parsed_columns.append({"column": column, "position": position, **parsed})

    # `period_variant_index` is assigned from the suffix, not from column order: the
    # payloads carry `2025-Q4_1` *before* `2025-Q4`, so ordering by position would make the
    # writer's de-duplication artifact the primary column. The unsuffixed column is index 0.
    by_period: dict[str, list[dict[str, Any]]] = {}
    for parsed in parsed_columns:
        by_period.setdefault(parsed["reporting_period"], []).append(parsed)
    for candidates in by_period.values():
        candidates.sort(key=lambda item: (
            item["variant_suffix"] is not None,
            int(item["variant_suffix"]) if item["variant_suffix"] is not None else -1,
            item["position"]))
        for variant_index, candidate in enumerate(candidates):
            candidate["variant_index"] = variant_index
    period_columns = sorted(parsed_columns, key=lambda item: item["position"])

    rows = list(frame.iterrows())
    # `item_id` repeats within a payload; count occurrences up front so the *first* row of
    # a repeated id is flagged too, not only the later ones.
    id_totals: dict[str, int] = {}
    for _, row in rows:
        raw_id = _text(row.get("item_id")) or ""
        id_totals[raw_id] = id_totals.get(raw_id, 0) + 1

    provider = None
    scraped_at = None
    if rows:
        provider = _text(rows[0][1].get("source"))
        scraped_at = _text(rows[0][1].get("scraped_at"))
    has_english_labels = "item_en" in columns

    observations: list[dict[str, Any]] = []
    rows_without_values: list[dict[str, Any]] = []
    malformed_values: list[dict[str, Any]] = []
    id_seen: dict[str, int] = {}

    for row_ordinal, (_, row) in enumerate(rows):
        raw_item_id = _text(row.get("item_id")) or ""
        occurrence = id_seen.get(raw_item_id, 0) + 1
        id_seen[raw_item_id] = occurrence
        ambiguous = id_totals.get(raw_item_id, 0) > 1
        label_vi = _text(row.get("item"))
        label_en = _text(row.get("item_en")) if has_english_labels else None

        emitted = 0
        for period_column in period_columns:
            value, malformed = _number(row.get(period_column["column"]))
            if malformed is not None:
                malformed_values.append({
                    "row_ordinal": row_ordinal, "raw_item_id": raw_item_id,
                    "column": period_column["column"], "reason": malformed,
                })
                continue
            if value is None:
                continue

            identity = {
                "schema_version": SCHEMA_VERSION,
                "ticker": ticker.upper(),
                "provider": provider,
                "statement_family": statement_family,
                "reporting_frequency": reporting_frequency,
                "reporting_period": period_column["reporting_period"],
                "period_type": period_column["period_type"],
                "period_variant_index": period_column["variant_index"],
                "period_column": period_column["column"],
                "raw_item_id": raw_item_id,
                "item_id_occurrence": occurrence,
                "row_ordinal": row_ordinal,
            }

            warnings = ["statement_scope_unknown", "currency_and_scale_unknown"]
            if ambiguous:
                warnings.append("ambiguous_raw_item_id")
            if period_column["variant_index"] > 0:
                warnings.append("duplicate_period_column")
            if not raw_item_id:
                warnings.append("raw_item_id_absent")
            if label_en is None:
                warnings.append("raw_label_en_absent")

            # A metadata sidecar is keyed by the already-normalised report period.  Its
            # values are preserved verbatim; extraction deliberately does not translate
            # `lengthReport` into standalone-quarter or YTD semantics.
            metadata = dict((period_metadata or {}).get(period_column["reporting_period"], {}))
            observation = {
                **identity,
                "identity_key": _fingerprint(identity),
                "observation_id": _fingerprint({**identity, "raw_value": value,
                                                "source_sha256": source_sha256}),
                "raw_label_vi": label_vi,
                "raw_label_en": label_en,
                "raw_value": value,
                "raw_currency": None,
                "raw_scale": None,
                "statement_scope": "unknown",
                "cumulative_state": "unknown",
                "restatement_state": "unknown",
                "retention_policy": RETENTION_POLICY,
                "qualification_state": QUALIFICATION_STATE,
                "source_file": source_file,
                "source_sha256": source_sha256,
                "scraped_at": scraped_at,
                "provider_report_metadata": metadata,
                "warnings": sorted(set(warnings)),
            }
            observations.append(observation)
            emitted += 1

        if emitted == 0:
            rows_without_values.append({
                "row_ordinal": row_ordinal, "raw_item_id": raw_item_id,
                "reason": "no_reporting_period_column_carried_a_value",
            })

    observations.sort(key=lambda record: (
        record["statement_family"], record["reporting_period"],
        record["period_variant_index"], record["row_ordinal"]))

    repeated_ids = sorted(raw_id for raw_id, total in id_totals.items() if total > 1)
    duplicate_periods = sorted({column["reporting_period"] for column in period_columns
                                if column["variant_index"] > 0})

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker.upper(),
        "statement_family": statement_family,
        "reporting_frequency": reporting_frequency,
        "provider": provider,
        "scraped_at": scraped_at,
        "source_file": source_file,
        "source_sha256": source_sha256,
        "retention_policy": RETENTION_POLICY,
        "observations": observations,
        "period_columns": period_columns,
        "non_period_columns": non_period_columns,
        "reporting_periods": sorted({column["reporting_period"] for column in period_columns}),
        "raw_item_ids": sorted(id_totals),
        "repeated_raw_item_ids": repeated_ids,
        "duplicate_period_columns": duplicate_periods,
        "rows_without_values": rows_without_values,
        "malformed_values": malformed_values,
        "reconciliation": {
            "input_rows": len(rows),
            "input_columns": len(columns),
            "period_columns": len(period_columns),
            "non_period_columns": len(non_period_columns),
            "rows_emitting_observations": len(rows) - len(rows_without_values),
            "rows_without_values": len(rows_without_values),
            "observations": len(observations),
            "columns_fully_accounted": len(columns) == len(period_columns) + len(non_period_columns),
            "rows_fully_accounted": (
                len(rows) == (len(rows) - len(rows_without_values)) + len(rows_without_values)),
            "observation_ids_unique": len({o["observation_id"] for o in observations}) == len(observations),
        },
    }


def read_payload(path: Path) -> Any:
    """Load one retained payload. Parquet only -- the CSV twin is a human-readable export."""
    import pandas as pd

    return pd.read_parquet(Path(path))


def extract_payload_file(path: Path) -> dict[str, Any]:
    """`extract_payload` over a payload on disk, resolving identity from its filename."""
    path = Path(path)
    identity = parse_payload_name(path.stem)
    return extract_payload(
        read_payload(path),
        ticker=identity["ticker"],
        statement_family=identity["statement_family"],
        reporting_frequency=identity["reporting_frequency"],
        source_file=path.name,
        source_sha256=sha256_file(path),
    )


def observation_lines(observations: Iterable[Mapping[str, Any]]) -> str:
    """Canonical JSONL body for a shard: sorted keys, no whitespace, LF terminated."""
    return "".join(_canonical_json(dict(observation)) + "\n" for observation in observations)


def content_fingerprint(observations: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 over the canonical JSONL body -- the value determinism is claimed about."""
    return hashlib.sha256(observation_lines(observations).encode("utf-8")).hexdigest()
