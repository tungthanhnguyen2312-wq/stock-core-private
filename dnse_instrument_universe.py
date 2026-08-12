"""Dynamic DNSE market-universe / security-master discovery.

Source: DNSE OpenAPI ``/market/instruments`` (capability ``"instruments"`` in
``dnse_bulk_market_data.MARKET_DATA_ENDPOINTS``, family ``"security_master"``),
called with no symbol/index/market filter so the provider itself returns its
complete instrument population, paginated. Termination is driven entirely by
the response's own ``total``/``page``/``pageSize`` fields (empirically
observed 2026-08-10, see
``operations-review/dnse-market-data-qualification-20260810/probe_results.json``,
capability ``instruments``) -- this module never hardcodes a page count, a
ticker count, or a fixed ticker list.

CLASSIFICATION IS DATA-DRIVEN, NEVER GUESSED
    The only DNSE ``securityGroupId`` value directly observed in retained
    evidence is ``"ST"`` (10 examples: HPG, VNM, QNS, ACB, BID, BSR, CTG,
    FPT, VPL, VRE -- all well-known common stocks), so only ``"ST"`` maps to
    ``EQUITY``. Every other or not-yet-seen code maps to
    ``UNKNOWN_SECURITY_GROUP`` with the raw code retained -- never a
    plausible-looking guess at WARRANT/BOND/ETF/RIGHT/DERIVATIVE. Extending
    the table is future semantic work, done only once a new code is actually
    observed in a live response (this milestone's "unknown classification
    must remain explicit rather than guessed" requirement).

EXCHANGE IS CARRIED, NOT LABELLED
    ``marketId`` (``"STO"``, ``"UPX"``, and other codes not yet seen in an
    ``/market/instruments`` response specifically) is retained verbatim as
    ``exchange_raw`` -- enough to *distinguish* instruments by exchange,
    which is what this milestone asks for. This module does not map it to a
    human HOSE/HNX/UPCOM label: doing that from two data points (``STO``
    with HOSE-listed HPG/VNM, ``UPX`` with UPCoM-listed QNS) would itself be
    a guess (AI_RULES.md 8a/8g/8i). That mapping is future semantic work.

ACTIVE/INACTIVE STATE
    The ``/market/instruments`` record carries no status/halt/delisted field
    (unlike the trades/quotes endpoints, which separately carry
    ``securityStatus``). ``listing_status`` is therefore always the explicit
    ``"unknown_not_provided_by_dataset"`` here, per the milestone's "where
    available" qualifier -- it genuinely is not available from this dataset.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd

from dnse_bulk_market_data import fetch_capability_raw

SCHEMA_VERSION = "1.0.0"
PROVIDER = "DNSE"
DATASET = "instruments"
SOURCE_REFERENCE = "dnse_openapi:/market/instruments"

EQUITY = "EQUITY"
ETF = "ETF"
WARRANT = "WARRANT"
RIGHT = "RIGHT"
BOND = "BOND"
DERIVATIVE = "DERIVATIVE"
UNKNOWN_SECURITY_GROUP = "UNKNOWN_SECURITY_GROUP"

INSTRUMENT_CLASSES = frozenset({EQUITY, ETF, WARRANT, RIGHT, BOND, DERIVATIVE, UNKNOWN_SECURITY_GROUP})

# Empirically observed 2026-08-10 (see module docstring). Extend only when a
# new code is directly observed in a real /market/instruments response --
# never speculatively.
_SECURITY_GROUP_CLASS: dict[str, str] = {
    "ST": EQUITY,
}

DEFAULT_PAGE_SIZE = 100
#: A defensive circuit breaker against a misbehaving/looping response, not an
#: assumption about the true universe size -- at DEFAULT_PAGE_SIZE this is
#: headroom for ~5,000 instruments, comfortably above every ticker-count
#: figure this project has ever measured (~1,500-1,700).
DEFAULT_MAX_PAGES = 50


class DnseInstrumentUniverseError(ValueError):
    """Fail-closed rejection while normalizing a DNSE instruments response."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def classify_instrument(security_group_id: str | None) -> dict[str, Any]:
    """Map a raw DNSE ``securityGroupId`` to an instrument class, never guessing."""
    code = (security_group_id or "").strip()
    if not code:
        return {"instrument_class": UNKNOWN_SECURITY_GROUP,
                "classification_basis": "security_group_id_absent",
                "raw_security_group_id": None}
    mapped = _SECURITY_GROUP_CLASS.get(code)
    if mapped is None:
        return {"instrument_class": UNKNOWN_SECURITY_GROUP,
                "classification_basis": "security_group_id_not_yet_observed",
                "raw_security_group_id": code}
    return {"instrument_class": mapped, "classification_basis": "empirically_observed_security_group_id",
            "raw_security_group_id": code}


def normalize_instrument_record(raw: Mapping[str, Any], *, retrieved_at: str, page: int) -> dict[str, Any]:
    """One raw DNSE instrument record -> an identity-rich, classified record.

    Raises ``DnseInstrumentUniverseError`` only for a record missing its
    identifying ``symbol``. Everything else is retained even when absent or
    malformed, with explicit unknown markers -- this milestone's "never
    discard for incomplete semantics" doctrine.
    """
    if not isinstance(raw, Mapping):
        raise DnseInstrumentUniverseError("instrument_record_not_a_mapping")
    symbol = _text(raw.get("symbol"))
    if symbol is None:
        raise DnseInstrumentUniverseError("instrument_record_missing_symbol")
    symbol = symbol.upper()
    classification = classify_instrument(_text(raw.get("securityGroupId")))
    index_membership = raw.get("indexName")
    if index_membership is not None and (
        isinstance(index_membership, (str, bytes)) or not isinstance(index_membership, Sequence)
    ):
        index_membership = None
    return {
        "symbol": symbol,
        "provider": PROVIDER,
        "provider_identity": f"dnse:symbol:{symbol.casefold()}",
        "identity_basis": "dnse_instruments_symbol",
        "exchange_raw": _text(raw.get("marketId")),
        "instrument_class": classification["instrument_class"],
        "classification_basis": classification["classification_basis"],
        "raw_security_group_id": classification["raw_security_group_id"],
        "symbol_type_raw": _text(raw.get("symbolType")),
        "listing_status": "unknown_not_provided_by_dataset",
        "name": _text(raw.get("name")),
        "short_name": _text(raw.get("shortName")),
        "listed_date": _text(raw.get("listedDate")),
        "index_membership": list(index_membership) if index_membership is not None else None,
        "discovered_at": retrieved_at,
        "source_page": page,
        "raw_record_json": _canonical_json(dict(raw)),
    }


def fetch_universe_page(*, api_key: str, api_secret: str, page: int, page_size: int,
                        request_get: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One ``/market/instruments`` page fetch -- no filter beyond pagination,
    so the provider returns its own complete population one page at a time."""
    return fetch_capability_raw(
        "instruments", api_key=api_key, api_secret=api_secret,
        query={"page": page, "limit": page_size}, request_get=request_get,
    )


def discover_universe(*, api_key: str, api_secret: str, retrieved_at: str,
                      page_size: int = DEFAULT_PAGE_SIZE, max_pages: int | None = DEFAULT_MAX_PAGES,
                      request_get: Callable[..., Any] | None = None,
                      on_page_success: Callable[[int, Mapping[str, Any]], None] | None = None) -> dict[str, Any]:
    """Page through the complete DNSE instrument universe.

    An empty page always ends the sweep, regardless of whether ``total``/
    ``pageSize`` were present on any response -- that is the primary,
    always-available termination signal. When both are present and
    self-consistent for the current page, they let the sweep stop one round
    trip earlier instead of waiting for a final empty page. ``max_pages`` is
    a defensive circuit breaker only, never a target.

    ``on_page_success``, if given, is called once per successfully fetched
    page with ``(page, response)`` -- ``response`` is the full
    ``dnse_bulk_market_data.fetch_capability_raw`` result, letting a caller
    (e.g. the discovery CLI) persist each page's raw envelope through
    ``market_raw_lake`` for immutable provenance, in addition to the
    per-record ``raw_record_json`` already carried on every normalized row.
    This sweep is short (page_size=100 puts the whole known universe at
    ~15-20 requests), so it is not itself checkpointed page-by-page the way
    the much larger per-symbol bulk dataset ingestion is -- see
    ``tools/discover_market_universe.py``'s module docstring for that scoping
    decision.
    """
    records: list[dict[str, Any]] = []
    pages_fetched: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    duplicate_identities: list[str] = []
    page = 1
    declared_total: int | None = None

    while True:
        response = fetch_universe_page(api_key=api_key, api_secret=api_secret, page=page,
                                       page_size=page_size, request_get=request_get)
        page_report: dict[str, Any] = {
            "page": page, "ok": bool(response.get("ok")),
            "http_status": response.get("http_status"), "error_code": response.get("error_code"),
        }
        if not response.get("ok"):
            pages_fetched.append(page_report)
            return _assemble_result(
                status="PROVIDER_ERROR_MID_PAGINATION", records=records, pages_fetched=pages_fetched,
                malformed=malformed, duplicate_identities=duplicate_identities,
                declared_total=declared_total, retrieved_at=retrieved_at, page_size=page_size,
                last_error={k: v for k, v in response.items() if k != "body"},
            )

        body = response.get("body")
        rows = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(rows, list):
            page_report["error_code"] = "data_field_not_a_list"
            pages_fetched.append(page_report)
            return _assemble_result(
                status="MALFORMED_RESPONSE_MID_PAGINATION", records=records, pages_fetched=pages_fetched,
                malformed=malformed, duplicate_identities=duplicate_identities,
                declared_total=declared_total, retrieved_at=retrieved_at, page_size=page_size,
                last_error={"page": page, "reason": "data_field_not_a_list"},
            )

        total = body.get("total")
        response_page_size = body.get("pageSize")
        if isinstance(total, int):
            declared_total = total
        page_report["row_count"] = len(rows)
        pages_fetched.append(page_report)
        if on_page_success is not None:
            on_page_success(page, response)

        for raw in rows:
            try:
                normalized = normalize_instrument_record(raw, retrieved_at=retrieved_at, page=page)
            except DnseInstrumentUniverseError as exc:
                malformed.append({"page": page, "reason": str(exc),
                                  "raw_record_json": _canonical_json(raw)})
                continue
            if normalized["provider_identity"] in seen_identities:
                duplicate_identities.append(normalized["provider_identity"])
                continue
            seen_identities.add(normalized["provider_identity"])
            records.append(normalized)

        if not rows:
            break
        if (isinstance(declared_total, int) and isinstance(response_page_size, int)
                and response_page_size > 0 and page * response_page_size >= declared_total):
            break
        if max_pages is not None and page >= max_pages:
            return _assemble_result(
                status="MAX_PAGES_REACHED", records=records, pages_fetched=pages_fetched,
                malformed=malformed, duplicate_identities=duplicate_identities,
                declared_total=declared_total, retrieved_at=retrieved_at, page_size=page_size,
            )
        page += 1

    return _assemble_result(
        status="COMPLETE", records=records, pages_fetched=pages_fetched, malformed=malformed,
        duplicate_identities=duplicate_identities, declared_total=declared_total,
        retrieved_at=retrieved_at, page_size=page_size,
    )


def _assemble_result(*, status: str, records: list[dict[str, Any]], pages_fetched: list[dict[str, Any]],
                     malformed: list[dict[str, Any]], duplicate_identities: list[str],
                     declared_total: int | None, retrieved_at: str, page_size: int,
                     last_error: Mapping[str, Any] | None = None) -> dict[str, Any]:
    by_exchange: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for record in records:
        exchange = record["exchange_raw"] or "unknown"
        by_exchange[exchange] = by_exchange.get(exchange, 0) + 1
        by_class[record["instrument_class"]] = by_class.get(record["instrument_class"], 0) + 1
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "provider": PROVIDER,
        "dataset": DATASET,
        "source_reference": SOURCE_REFERENCE,
        "retrieved_at": retrieved_at,
        "page_size": page_size,
        "pages_fetched": pages_fetched,
        "declared_total": declared_total,
        "discovered_count": len(records),
        "by_exchange_raw": dict(sorted(by_exchange.items())),
        "by_instrument_class": dict(sorted(by_class.items())),
        "malformed_record_count": len(malformed),
        "malformed_records": malformed,
        "duplicate_identity_count": len(duplicate_identities),
        "duplicate_identities": sorted(set(duplicate_identities)),
        "records": records,
    }
    if last_error is not None:
        result["last_error"] = dict(last_error)
    return result


def snapshot_manifest(discovery_result: Mapping[str, Any]) -> dict[str, Any]:
    """A deterministic, content-hashed manifest for one discovery run's
    records -- independent of fetch/insertion order."""
    records = sorted(discovery_result["records"], key=lambda r: r["provider_identity"])
    content_hash = hashlib.sha256(_canonical_json(records).encode("utf-8")).hexdigest()
    identity = _canonical_json([
        discovery_result["schema_version"], discovery_result["provider"], discovery_result["dataset"],
        discovery_result["retrieved_at"], content_hash,
    ])
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "schema_version": discovery_result["schema_version"],
        "provider": discovery_result["provider"],
        "dataset": discovery_result["dataset"],
        "source_reference": discovery_result["source_reference"],
        "retrieved_at": discovery_result["retrieved_at"],
        "status": discovery_result["status"],
        "declared_total": discovery_result["declared_total"],
        "discovered_count": discovery_result["discovered_count"],
        "by_exchange_raw": discovery_result["by_exchange_raw"],
        "by_instrument_class": discovery_result["by_instrument_class"],
        "malformed_record_count": discovery_result["malformed_record_count"],
        "duplicate_identity_count": discovery_result["duplicate_identity_count"],
        "content_hash": content_hash,
        "pages_fetched": len(discovery_result["pages_fetched"]),
    }


def build_snapshot_frame(records: list[Mapping[str, Any]]) -> pd.DataFrame:
    """A flat, columnar table of normalized instrument records, sorted by
    symbol for a deterministic on-disk snapshot."""
    if not records:
        return pd.DataFrame(columns=[
            "symbol", "provider", "provider_identity", "identity_basis", "exchange_raw",
            "instrument_class", "classification_basis", "raw_security_group_id", "symbol_type_raw",
            "listing_status", "name", "short_name", "listed_date", "index_membership_json",
            "discovered_at", "source_page", "raw_record_json",
        ])
    rows = []
    for record in records:
        row = dict(record)
        row["index_membership_json"] = _canonical_json(row.pop("index_membership"))
        rows.append(row)
    frame = pd.DataFrame(rows)
    return frame.sort_values("symbol", kind="stable").reset_index(drop=True)
