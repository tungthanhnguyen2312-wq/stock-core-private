"""Generated, provenance-carrying statement-taxonomy sidecar.

WHAT THIS IS
    A reproducible, machine-generated observation of which financial-statement *reporting
    template* each ticker files under, derived from the retained balance-sheet payloads by
    `statement_taxonomy_classifier.classify_statement_taxonomy`.

WHAT THIS IS NOT
    It is NOT an entity-profile registry and it never carries an `issuer_entity_type`.
    `config/ticker_entity_profiles.csv` remains the sole authority for that, and this
    module never reads it for resolution, never writes it, and never proposes a backfill.

    Three separate concepts stay separate throughout:
        statement_taxonomy  -- which Circular template the filing's vocabulary belongs to.
                               Directly observable. This file.
        issuer_entity_type  -- what kind of institution the issuer is. Manual registry only.
        model_applicability -- whether a model may run. `altman_applicability.py`.

AUTHORITY ORDER (`resolve_entity_authority`)
    1. manually verified entity profile   -> authority "manual_profile"
    2. generated statement-taxonomy evidence, and only to WITHHOLD a corporate model
       (a specialized financial template) -> authority "generated_taxonomy"
    3. unknown                            -> authority "unknown"
    `corporate_vas` never resolves an entity type: a corporate *template* is not evidence
    the issuer is a non-financial corporate, and reading absence of financial markers as
    "corporate" is precisely the fail-open route this project refuses.

DETERMINISM
    `records` are fully sorted and derived only from the input payloads, so
    `records_fingerprint` is byte-stable across rebuilds on unchanged inputs.
    `generated_at` / `session_identity` are session metadata and are deliberately excluded
    from that fingerprint -- they are the only fields expected to differ between two runs
    over identical inputs.

RECONCILIATION
    Every input payload lands in exactly one of `records` or `omitted`, each omission
    carrying an explicit reason. `reconciliation.inputs_fully_accounted` asserts this.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from statement_taxonomy_classifier import VERSION as CLASSIFIER_VERSION
from statement_taxonomy_classifier import classify_statement_taxonomy

SIDECAR_SCHEMA_VERSION = "1.0.0"
SIDECAR_FILENAME = "statement_taxonomy_sidecar.json"

#: The one taxonomy that is a candidate for the corporate archetype. Never sufficient on
#: its own to resolve an entity type -- see `resolve_entity_authority`.
CORPORATE_TAXONOMY = "corporate_vas"

#: Taxonomies that positively evidence a specialized *financial* reporting template.
#: Enough to withhold a corporate model even with no resolved issuer entity type.
FINANCIAL_TAXONOMIES = frozenset({
    "credit_institution", "securities_company", "financial_specialized_ambiguous",
})

#: Absence of evidence. Never resolves anything, in either direction.
NON_EVIDENTIAL_TAXONOMIES = frozenset({"unknown", "unresolved"})

_INPUT_GLOB = "*_balance_sheet_quarter.parquet"

_AUTHORITY_UNKNOWN = "unknown"
_AUTHORITY_MANUAL = "manual_profile"
_AUTHORITY_GENERATED = "generated_taxonomy"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _record_identity(ticker: str, taxonomy: str, first: Any, last: Any, source_sha256: str) -> str:
    """Deterministic record identity: same inputs -> same id, different inputs -> different id."""
    return hashlib.sha256("|".join([
        SIDECAR_SCHEMA_VERSION, CLASSIFIER_VERSION, ticker, taxonomy,
        str(first), str(last), source_sha256,
    ]).encode("utf-8")).hexdigest()


def _classify_payload(path: Path) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Classify every retained reporting period in one payload.

    Returns (per-period classifications, provider source, omission reason).
    """
    import pandas as pd

    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # unreadable payload is an omission, never a taxonomy
        return [], None, f"payload_unreadable:{type(exc).__name__}"
    periods = [column for column in frame.columns if str(column)[:4].isdigit()]
    if not periods:
        return [], None, "payload_has_no_reporting_period_columns"
    source = str(frame["source"].iloc[0]) if "source" in frame.columns and len(frame) else None
    ticker = path.name.split("_")[0].upper()
    results: list[dict[str, Any]] = []
    for period in sorted(str(p) for p in periods):
        present = frame.loc[frame[period].notna(), "item_id"].astype(str)
        if present.empty:
            continue
        results.append(classify_statement_taxonomy(
            set(present), ticker=ticker, source=source,
            reporting_period=str(period), statement_scope="unknown",
        ))
    if not results:
        return [], source, "no_reporting_period_carried_any_populated_item"
    return results, source, None


def _record_for_ticker(ticker: str, path: Path, source_sha256: str,
                       classifications: list[dict[str, Any]], source: str | None) -> dict[str, Any]:
    taxonomies = sorted({row["statement_taxonomy"] for row in classifications})
    periods = sorted(str(row["reporting_period"]) for row in classifications)
    stable = len(taxonomies) == 1
    taxonomy = taxonomies[0] if stable else "unresolved"

    positive: dict[str, list[str]] = {}
    exclusion: dict[str, list[str]] = {}
    for row in classifications:
        for family, markers in (row.get("matched_markers") or {}).items():
            bucket = exclusion if family != "corporate" else positive
            merged = set(bucket.get(family, [])) | set(markers or [])
            bucket[family] = sorted(merged)
    # `corporate` markers are positive evidence of the corporate template; every
    # specialized-financial family is an exclusion marker for the corporate models.
    abstentions = sorted({row["abstention_reason"] for row in classifications
                          if row.get("abstention_reason")})
    if not stable:
        classification_status = "unstable_across_periods"
        abstention_reason = ("statement taxonomy is not stable across retained periods "
                             f"({', '.join(taxonomies)}); never collapsed to one value")
    elif abstentions:
        classification_status = "abstained"
        abstention_reason = abstentions[0]
    else:
        classification_status = "observed"
        abstention_reason = None

    if taxonomy in FINANCIAL_TAXONOMIES:
        ambiguity = ("ambiguous_specialized_financial"
                     if taxonomy == "financial_specialized_ambiguous" else "resolved")
    elif taxonomy == CORPORATE_TAXONOMY:
        ambiguity = "resolved"
    else:
        ambiguity = "unresolved"

    return {
        "record_id": _record_identity(ticker, taxonomy, periods[0], periods[-1], source_sha256),
        "ticker": ticker,
        "statement_taxonomy": taxonomy,
        "authority_level": "generated_evidence",
        "classification_status": classification_status,
        "abstention_reason": abstention_reason,
        "ambiguity_status": ambiguity,
        "cross_period_stable": stable,
        "distinct_taxonomies": taxonomies,
        "source": source,
        "source_file": path.name,
        "source_sha256": source_sha256,
        "statement_scope": "unknown",
        "classifier_version": CLASSIFIER_VERSION,
        "periods_evaluated": len(classifications),
        "first_observed_period": periods[0],
        "last_observed_period": periods[-1],
        "observed_period_range": periods,
        "matched_positive_markers": {k: v for k, v in sorted(positive.items()) if v},
        "matched_exclusion_markers": {k: v for k, v in sorted(exclusion.items()) if v},
    }


def build_sidecar(runtime_root: str | os.PathLike[str], *, generated_at: str,
                  session_identity: str, producer_contract_version: str | None = None) -> dict[str, Any]:
    """Build the complete sidecar payload from the retained statement payloads.

    Read-only: touches nothing but `<runtime_root>/data_bctc/*_balance_sheet_quarter.parquet`.
    """
    root = Path(runtime_root)
    paths = sorted((root / "data_bctc").glob(_INPUT_GLOB), key=lambda p: p.name)

    records: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    input_index: list[list[str]] = []
    for path in paths:
        ticker = path.name.split("_")[0].upper()
        source_sha256 = _sha256_file(path)
        input_index.append([path.name, source_sha256])
        classifications, source, omission = _classify_payload(path)
        if omission is not None:
            omitted.append({"ticker": ticker, "source_file": path.name,
                            "source_sha256": source_sha256, "omission_reason": omission})
            continue
        records.append(_record_for_ticker(ticker, path, source_sha256, classifications, source))

    records.sort(key=lambda record: record["ticker"])
    omitted.sort(key=lambda record: record["ticker"])

    counts: dict[str, int] = {}
    for record in records:
        counts[record["statement_taxonomy"]] = counts.get(record["statement_taxonomy"], 0) + 1

    payload = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "artifact": SIDECAR_FILENAME,
        "authority_level": "generated_evidence",
        "authority_note": (
            "Generated statement-taxonomy evidence. This is NOT a manually verified issuer "
            "entity type and NOT an entity-profile registry. config/ticker_entity_profiles.csv "
            "remains the sole authority for issuer_entity_type and is never read for "
            "resolution, written, or backfilled by this artifact."),
        "generated_at": generated_at,
        "session_identity": session_identity,
        "producer_contract_version": producer_contract_version,
        "classifier_version": CLASSIFIER_VERSION,
        "input_glob": f"data_bctc/{_INPUT_GLOB}",
        "input_file_count": len(paths),
        "input_fingerprint": _fingerprint(sorted(input_index)),
        "taxonomy_counts": dict(sorted(counts.items())),
        "records": records,
        "omitted": omitted,
        "reconciliation": {
            "input_payloads": len(paths),
            "classified_records": len(records),
            "omitted_records": len(omitted),
            "inputs_fully_accounted": len(paths) == len(records) + len(omitted),
            "taxonomy_counts_sum_to_records": sum(counts.values()) == len(records),
        },
    }
    payload["records_fingerprint"] = _fingerprint({"records": records, "omitted": omitted})
    return payload


def sidecar_path(runtime_root: str | os.PathLike[str]) -> Path:
    return Path(runtime_root) / SIDECAR_FILENAME


def load_sidecar(runtime_root: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Read the sidecar if present and structurally valid; otherwise None (fail-closed).

    A missing or malformed sidecar yields no taxonomy evidence at all, which leaves every
    downstream model on `insufficient_evidence` rather than on an assumed archetype.
    """
    path = sidecar_path(runtime_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if payload.get("schema_version") != SIDECAR_SCHEMA_VERSION:
        return None
    if not isinstance(payload.get("records"), list):
        return None
    return dict(payload)


def taxonomy_index(sidecar: Mapping[str, Any] | None) -> dict[str, str]:
    """ticker -> statement_taxonomy, for the records this sidecar actually carries."""
    if not isinstance(sidecar, Mapping):
        return {}
    index: dict[str, str] = {}
    for record in sidecar.get("records") or []:
        if not isinstance(record, Mapping):
            continue
        ticker = str(record.get("ticker") or "").strip().upper()
        taxonomy = record.get("statement_taxonomy")
        if ticker and isinstance(taxonomy, str):
            index[ticker] = taxonomy
    return index


def resolve_taxonomy(sidecar: Mapping[str, Any] | None, ticker: str) -> str | None:
    """The generated taxonomy for `ticker`, or None when this sidecar has no record."""
    return taxonomy_index(sidecar).get(str(ticker or "").strip().upper())


def resolve_entity_authority(manual_entity_type: Any, statement_taxonomy: Any) -> dict[str, Any]:
    """Resolve issuer archetype under the fixed authority order.

    Returns {"entity_type", "authority", "statement_taxonomy", "reason"}.

    A manually verified profile always wins. Generated taxonomy is consulted only to
    withhold the corporate archetype -- `corporate_vas` never grants one, and an
    unknown/unresolved taxonomy never defaults to corporate.
    """
    manual = str(manual_entity_type or "").strip()
    taxonomy = str(statement_taxonomy or "").strip() or None
    if manual and manual.lower() not in {"unknown", "none", "null"}:
        return {"entity_type": manual, "authority": _AUTHORITY_MANUAL,
                "statement_taxonomy": taxonomy,
                "reason": "manually verified entity profile takes precedence over generated evidence"}
    if taxonomy in FINANCIAL_TAXONOMIES:
        return {"entity_type": None, "authority": _AUTHORITY_GENERATED,
                "statement_taxonomy": taxonomy,
                "reason": (f"statement_taxonomy={taxonomy!r} positively evidences a specialized "
                           "financial reporting template; sufficient to withhold corporate models, "
                           "not sufficient to name the issuer's institution type")}
    return {"entity_type": None, "authority": _AUTHORITY_UNKNOWN,
            "statement_taxonomy": taxonomy,
            "reason": ("no manually verified profile and no positive specialized-financial "
                       "evidence; an absent archetype is never read as corporate")}


def sidecar_provenance(sidecar: Mapping[str, Any] | None, ticker: str) -> dict[str, Any] | None:
    """The full generated record for `ticker`, for embedding as provenance."""
    if not isinstance(sidecar, Mapping):
        return None
    wanted = str(ticker or "").strip().upper()
    for record in sidecar.get("records") or []:
        if isinstance(record, Mapping) and str(record.get("ticker") or "").upper() == wanted:
            return dict(record)
    return None


def iter_records(sidecar: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]:
    if not isinstance(sidecar, Mapping):
        return ()
    return tuple(r for r in (sidecar.get("records") or []) if isinstance(r, Mapping))
