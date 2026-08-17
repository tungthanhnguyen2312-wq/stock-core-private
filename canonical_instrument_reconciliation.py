"""Pure, provenance-preserving canonical instrument reconciliation foundation.

The output is a *candidate* master, not an authoritative instrument identity
registry. Exact symbols form deterministic candidate links only. They do not
prove that two providers refer to the same legal instrument, so every such
new link starts as ``PROVISIONAL_MATCH``.

No acquisition client, database connection, or implicit input path exists in
this module. The thin file adapter accepts explicit retained JSON artifacts;
the core accepts already-loaded mappings and is deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from atomic_io import atomic_write_json


SCHEMA_VERSION = "1.0.0"
LINK_RULE_VERSION = "exact_uppercase_symbol_candidate_link/v1"
STORE_RELATIVE = Path("data") / "canonical_instrument_reconciliation" / "artifacts"

PROVISIONAL_MATCH = "PROVISIONAL_MATCH"
QUALIFIED_MATCH = "QUALIFIED_MATCH"
UNRESOLVED = "UNRESOLVED"
CONFLICT = "CONFLICT"

LISTING_UNKNOWN = "UNKNOWN"
EXCHANGE_UNKNOWN = "UNKNOWN"


class CanonicalInstrumentReconciliationError(ValueError):
    """A retained input or reconciliation invariant is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _symbol(value: Any) -> str | None:
    text = _text(value)
    return text.upper() if text else None


def _provider_identity(provider: str, record: Mapping[str, Any], symbol: str) -> str:
    explicit = _text(record.get("provider_identity"))
    if provider == "DNSE":
        return explicit or f"dnse:symbol:{symbol.casefold()}"
    if provider == "VCI":
        return explicit or f"vci:symbol:{symbol.casefold()}"
    if provider == "LEGACY":
        return explicit or f"legacy:ticker:{symbol.casefold()}"
    if provider == "COMPANY_PROFILE":
        source = _text(record.get("source_name")) or "UNKNOWN"
        profile_identity = _text(record.get("provider_identity")) or symbol
        return f"company_profile:{source.upper()}:{profile_identity}"
    raise CanonicalInstrumentReconciliationError(f"unsupported_provider:{provider}")


def _source_reference(provider: str, record: Mapping[str, Any], default: str) -> str:
    return _text(record.get("source_reference")) or _text(record.get("identity_basis")) or default


def _observed_at(provider: str, record: Mapping[str, Any]) -> str | None:
    keys = {
        "DNSE": ("discovered_at", "retrieved_at"),
        "VCI": ("fetched_at",),
        "LEGACY": ("updated", "observed_at"),
        "COMPANY_PROFILE": ("fetched_at",),
    }[provider]
    return next((value for key in keys if (value := _text(record.get(key))) is not None), None)


def _raw_record(provider: str, record: Mapping[str, Any]) -> Any:
    if provider == "DNSE" and isinstance(record.get("raw_record_json"), str):
        try:
            return json.loads(record["raw_record_json"])
        except json.JSONDecodeError:
            return record["raw_record_json"]
    return record.get("raw_record", dict(record))


def _field_specs(provider: str, record: Mapping[str, Any], symbol: str) -> list[dict[str, Any]]:
    """Source-local observations. No cross-source mapping happens here."""
    raw_exchange = record.get("exchange_raw") if provider == "DNSE" else record.get("exchange")
    name = record.get("name") if provider == "DNSE" else record.get("organ_name")
    instrument_class = record.get("instrument_class") if provider == "DNSE" else record.get("instrument_type")
    if provider == "COMPANY_PROFILE":
        # Every COMPANY_PROFILE field lives under qualified_fields (see symbol extraction in
        # normalize_source_record); instrument_class must use the same nesting as name/exchange,
        # never the generic non-DNSE top-level default above.
        qualified = record.get("qualified_fields") if isinstance(record.get("qualified_fields"), Mapping) else {}
        name = qualified.get("organ_name")
        raw_exchange = qualified.get("exchange")
        instrument_class = qualified.get("instrument_type")
    if provider == "LEGACY":
        instrument_class = record.get("entity_type")
        name = record.get("name")
    class_status = "provider_reported" if provider == "DNSE" else "provider_raw_only_mapping_unknown"

    listing_raw = record.get("listing_status")
    # A legacy DELISTED marker is retained as a raw observation, but its mechanism is not
    # qualified in C.1 and therefore cannot become a selected listing state.
    listing_status = LISTING_UNKNOWN
    listing_quality = "unavailable_or_unqualified"
    if provider == "DNSE":
        listing_raw = record.get("listing_status", "unknown_not_provided_by_dataset")
    elif provider == "VCI":
        listing_raw = record.get("listing_status", "unavailable")

    return [
        {"field": "symbol", "raw_value": record.get("symbol", record.get("ticker", symbol)),
         "normalized_value": symbol, "semantic_status": "normalized_uppercase_symbol"},
        {"field": "exchange", "raw_value": raw_exchange, "normalized_value": None,
         "semantic_status": "provider_raw_only_mapping_unknown"},
        {"field": "name", "raw_value": name, "normalized_value": None,
         "semantic_status": "provider_reported" if name is not None else "missing"},
        {"field": "instrument_class", "raw_value": instrument_class, "normalized_value": None,
         "semantic_status": class_status if instrument_class is not None else "missing"},
        {"field": "listing_status", "raw_value": listing_raw, "normalized_value": listing_status,
         "semantic_status": listing_quality},
    ]


def normalize_source_record(provider: str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one source record without losing either its identity or raw record."""
    if not isinstance(record, Mapping):
        raise CanonicalInstrumentReconciliationError("source_record_not_a_mapping")
    provider = provider.upper()
    if provider == "COMPANY_PROFILE":
        qualified = record.get("qualified_fields") if isinstance(record.get("qualified_fields"), Mapping) else {}
        symbol = _symbol(qualified.get("symbol") or record.get("ticker"))
    else:
        symbol = _symbol(record.get("symbol") or record.get("ticker"))
    if symbol is None:
        raise CanonicalInstrumentReconciliationError(f"source_record_missing_symbol:{provider}")
    identity = _provider_identity(provider, record, symbol)
    return {
        "provider": provider,
        "provider_identity": identity,
        "symbol": symbol,
        "source_reference": _source_reference(provider, record, f"{provider.lower()}:retained_input"),
        "observed_at": _observed_at(provider, record),
        "raw_record": _raw_record(provider, record),
        "fields": _field_specs(provider, record, symbol),
    }


def _field_observation(identity: Mapping[str, Any], field: Mapping[str, Any]) -> dict[str, Any]:
    raw_value = field.get("raw_value")
    return {
        "observation_id": _hash([identity["provider_identity"], field["field"], raw_value, identity["observed_at"]]),
        "provider_identity": identity["provider_identity"],
        "provider": identity["provider"],
        "source_reference": identity["source_reference"],
        "observed_at": identity["observed_at"],
        "field": field["field"],
        "raw_value": raw_value,
        "normalized_value": field.get("normalized_value"),
        "semantic_status": field["semantic_status"],
        "selected": False,
        "conflict_id": None,
    }


def _select_fields(observations: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Select only an uncontested, explicitly usable source observation per field."""
    by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        by_field[observation["field"]].append(observation)
    selected: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for field, values in sorted(by_field.items()):
        usable = [
            v for v in values
            if v["raw_value"] is not None
            and v["semantic_status"] in {"provider_reported", "normalized_uppercase_symbol"}
        ]
        distinct = {_canonical_json(v["normalized_value"] if v["normalized_value"] is not None else v["raw_value"]) for v in usable}
        if len(distinct) > 1:
            conflict_id = _hash(["field_conflict", field, sorted(distinct), sorted(v["provider_identity"] for v in usable)])
            conflict = {
                "conflict_id": conflict_id,
                "field": field,
                "state": CONFLICT,
                "provider_identities": sorted(v["provider_identity"] for v in usable),
                "observation_ids": sorted(v["observation_id"] for v in usable),
                "reason": "distinct_provider_observations_no_field_precedence_in_c1",
            }
            conflicts.append(conflict)
            for value in values:
                value["conflict_id"] = conflict_id
            continue
        if len(distinct) == 1 and usable:
            for value in usable:
                value["selected"] = True
            representative = sorted(usable, key=lambda item: item["observation_id"])[0]
            selected[field] = {
                "observation_ids": sorted(value["observation_id"] for value in usable),
                "value": representative["normalized_value"]
                if representative["normalized_value"] is not None else representative["raw_value"],
                "selection_state": "single_provider_observation" if len(usable) == 1
                else "consistent_provider_observations",
            }
        elif field == "listing_status":
            selected[field] = {"observation_id": None, "value": LISTING_UNKNOWN,
                               "selection_state": "fail_closed_no_qualified_listing_observation"}
    return selected, conflicts


def reconcile(source_records: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Pure deterministic reconciliation over already-retained source records."""
    normalized: list[dict[str, Any]] = []
    for provider, records in sorted(source_records.items()):
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise CanonicalInstrumentReconciliationError(f"source_records_not_a_sequence:{provider}")
        normalized.extend(normalize_source_record(provider, record) for record in records)
    identities = {entry["provider_identity"]: entry for entry in normalized}
    if len(identities) != len(normalized):
        raise CanonicalInstrumentReconciliationError("duplicate_provider_identity_in_reconciliation_input")

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for identity in identities.values():
        by_symbol[identity["symbol"]].append(identity)

    candidates: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    all_observations: list[dict[str, Any]] = []
    all_conflicts: list[dict[str, Any]] = []
    for symbol, members in sorted(by_symbol.items()):
        members = sorted(members, key=lambda item: item["provider_identity"])
        provider_identities = [member["provider_identity"] for member in members]
        candidate_id = f"candidate:{_hash([LINK_RULE_VERSION, provider_identities])}"
        state = PROVISIONAL_MATCH if len(members) > 1 else UNRESOLVED
        link = {
            "link_id": f"link:{_hash([LINK_RULE_VERSION, provider_identities])}",
            "candidate_id": candidate_id,
            "provider_identities": provider_identities,
            "rule": LINK_RULE_VERSION,
            "resolution_state": state,
            "evidence_observation_ids": [],
        }
        observations = [_field_observation(member, field) for member in members for field in member["fields"]]
        selected, conflicts = _select_fields(observations)
        link["evidence_observation_ids"] = sorted(item["observation_id"] for item in observations)
        candidate_state = CONFLICT if conflicts else state
        candidates.append({
            "candidate_id": candidate_id,
            "candidate_symbol": symbol,
            "resolution_state": candidate_state,
            "provider_identities": provider_identities,
            "selected_fields": selected,
        })
        links.append(link)
        all_observations.extend(observations)
        all_conflicts.extend(conflicts)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "link_rule_version": LINK_RULE_VERSION,
        "provider_instrument_identities": sorted(identities.values(), key=lambda item: item["provider_identity"]),
        "canonical_instrument_candidates": candidates,
        "instrument_identity_links": links,
        "canonical_instrument_field_observations": sorted(all_observations, key=lambda item: item["observation_id"]),
        "canonical_instrument_conflicts": sorted(all_conflicts, key=lambda item: item["conflict_id"]),
    }
    content_hash = _hash(payload)
    return {**payload, "content_hash": content_hash, "artifact_id": f"canonical-instrument-reconciliation:{content_hash}"}


def artifact_path(output_root: Path | str, content_hash: str) -> Path:
    return Path(output_root) / STORE_RELATIVE / f"{content_hash}.json"


def write_artifact(output_root: Path | str, result: Mapping[str, Any]) -> dict[str, Any]:
    """Write one immutable, content-addressed modern-lane reconciliation artifact."""
    expected = _hash({key: value for key, value in result.items() if key not in {"content_hash", "artifact_id"}})
    if result.get("content_hash") != expected:
        raise CanonicalInstrumentReconciliationError("result_content_hash_invalid")
    path = artifact_path(output_root, expected)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing == dict(result):
            return {"path": str(path), "written": False, "reason": "already_present_identical", "content_hash": expected}
        raise CanonicalInstrumentReconciliationError("content_addressed_artifact_collision")
    atomic_write_json(path, dict(result))
    return {"path": str(path), "written": True, "content_hash": expected}


def _load_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise CanonicalInstrumentReconciliationError(f"required_retained_input_missing:{label}:{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalInstrumentReconciliationError(f"retained_input_not_valid_json:{label}:{path}") from exc


def _records_from_input(payload: Any, label: str) -> list[Mapping[str, Any]]:
    records = payload.get("records") if isinstance(payload, Mapping) else payload
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise CanonicalInstrumentReconciliationError(f"retained_input_records_missing:{label}")
    if any(not isinstance(record, Mapping) for record in records):
        raise CanonicalInstrumentReconciliationError(f"retained_input_nonrecord:{label}")
    return list(records)


def _records_from_retained_file(path: Path, label: str) -> list[Mapping[str, Any]]:
    """Read an explicit retained JSON or modern-lane Parquet snapshot only."""
    if path.suffix.lower() != ".parquet":
        return _records_from_input(_load_json(path, label), label)
    if not path.is_file():
        raise CanonicalInstrumentReconciliationError(f"required_retained_input_missing:{label}:{path}")
    import pandas as pd

    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - normalize backend/parser failures to the input contract
        raise CanonicalInstrumentReconciliationError(f"retained_input_not_readable_parquet:{label}:{path}") from exc
    # pandas null sentinels and NaN are neither retained raw values nor JSON values. Preserve
    # their missingness explicitly as None before the pure core hashes the input.
    return list(frame.where(pd.notna(frame), None).to_dict(orient="records"))


def build_from_retained_files(
    *, dnse_input: Path | str, output_root: Path | str, vci_input: Path | str | None = None,
    legacy_input: Path | str | None = None, company_profile_input: Path | str | None = None,
) -> dict[str, Any]:
    """Thin, no-network adapter. DNSE is required; other sources are additive."""
    source_records: dict[str, Sequence[Mapping[str, Any]]] = {
        "DNSE": _records_from_retained_file(Path(dnse_input), "dnse"),
    }
    if vci_input is not None:
        source_records["VCI"] = _records_from_retained_file(Path(vci_input), "vci")
    if legacy_input is not None:
        source_records["LEGACY"] = _records_from_retained_file(Path(legacy_input), "legacy")
    if company_profile_input is not None:
        source_records["COMPANY_PROFILE"] = _records_from_retained_file(Path(company_profile_input), "company_profile")
    result = reconcile(source_records)
    return {"result": result, "artifact": write_artifact(output_root, result)}


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile explicit retained instrument snapshots; never fetches providers.")
    parser.add_argument("--dnse-input", type=Path, required=True)
    parser.add_argument("--vci-input", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--legacy-input", type=Path)
    parser.add_argument("--company-profile-input", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    built = build_from_retained_files(
        dnse_input=args.dnse_input, vci_input=args.vci_input, output_root=args.output_root,
        legacy_input=args.legacy_input, company_profile_input=args.company_profile_input,
    )
    print(_canonical_json(built["artifact"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
