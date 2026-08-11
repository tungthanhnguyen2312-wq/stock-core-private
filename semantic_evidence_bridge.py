"""Fail-closed reader linking cited official evidence to canonical observation records."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from financial_observations import read_observations, store_path
from provider_price_basis_registry import ineligibility_reason, raw_as_traded_eligible

VERSION = "1.0.0"
MANIFEST_RELATIVE = Path("data") / "official-evidence" / "manifest.json"
CITATIONS_RELATIVE = Path("data") / "official-evidence" / "qualification_citations.jsonl"
SHARE_BASIS_RELATIVE = Path("data") / "official-evidence" / "share_basis_citations.jsonl"
MARKET_PRICE_RELATIVE = Path("data") / "official-evidence" / "market_price_citations.jsonl"
CASH_DIVIDEND_RELATIVE = Path("data") / "official-evidence" / "cash_dividend_citations.jsonl"
NON_CASH_EVENT_RELATIVE = Path("data") / "official-evidence" / "non_cash_event_citations.jsonl"
DB_RELATIVE = "vn_stock.db"
MANIFEST_SCHEMA_VERSION = "1.0.0"
SIGNED_ISSUER_ACCEPTANCE_RULE = "signed_issuer_document_with_official_source_corroboration_v1"
# Generic, versioned acceptance path for an audited issuer document retained from a
# third-party mirror with no embedded signature -- e.g. a national disclosure mirror
# standing in for an issuer domain that is unreachable from this environment. Hash
# equality is never sufficient on its own for this weaker hosting class: a record
# opts in by declaring the three classification facts below, and every identity/
# audit/scope/exact-match fact in its evidence_acceptance block must then be
# explicit or the record fails closed. Never implies issuer-hosted or signed status.
THIRD_PARTY_MIRROR_UNSIGNED_ACCEPTANCE_RULE = "third_party_mirrored_unsigned_audited_issuer_document_v1"
THIRD_PARTY_MIRROR_HOSTING_WARNING = "third_party_mirror_hosting_is_weaker_than_issuer_hosted_evidence"
_SUPPORTED_EMBEDDED_SIGNATURE_STATUSES_FOR_MIRROR_RULE = {"absent", "unverified"}
# This status records one thing only: that **this repository** applied no back-adjustment
# to the cited row. It is not a statement about the provider, and it was read as one until
# 2026-08-04. Passing it is now necessary and not sufficient -- the provider must also be
# raw-as-traded eligible in provider_price_basis_registry, which VCI is not.
#
# The original note here reasoned about corporate actions *unsettled as of the
# trading_date*. That is the wrong direction: a back-adjustment is applied by events that
# happen **after** the cited date, so a citation can be correct when written and be
# rewritten by the provider months later.
_SUPPORTED_ADJUSTMENT_STATUSES = {"raw_as_quoted_no_adjustment_applied"}
_REQUIRED_MARKET_PRICE_FIELDS = ("citation_id", "ticker", "trading_date", "price_field", "value",
    "provider", "adjustment_status")
_SUPPORTED_SCOPES = {"consolidated"}
_RESOLVED_WARNINGS = {"statement_scope_unknown", "currency_or_scale_unknown"}
_REQUIRED_CITATION_FIELDS = ("citation_id", "observation_id", "evidence_id", "ticker", "reporting_frequency",
    "reporting_period", "raw_statement_type", "raw_item_id", "raw_value", "official_value",
    "statement_scope", "currency", "unit_scale")

# Three strictly distinct share-count identities -- never aliased or substituted for
# one another. "valuation_date_shares_outstanding" is listed as a supported identity
# type (the schema is ready for it) but no citation of that type exists yet: VCI's
# Company.overview() issue_share field carries no basis/as-of-date/currency metadata,
# so it is not eligible for citation the way a PDF-note figure is.
_SUPPORTED_SHARE_IDENTITIES = {
    "period_end_shares_outstanding",
    "weighted_average_basic_shares_outstanding",
    "weighted_average_diluted_shares_outstanding",
    "valuation_date_shares_outstanding",
    "treasury_shares_outstanding",
}
_REQUIRED_SHARE_BASIS_FIELDS = ("citation_id", "ticker", "identity_type", "reporting_frequency",
    "reporting_period", "value", "evidence_id")

# Metric-level source-presentation sign rules -- never ticker-specific. Each entry
# must be independently cited and tested before being added. Absent an entry here,
# verification requires an exact signed match; this module never compares by
# absolute value.
_SIGN_RULES: dict[tuple[str, str], dict[str, Any]] = {
    ("income_statement", "interest_expenses"): {
        "version": "v1",
        "citation": "Circular 202/2014/TT-BTC consolidated income statement (form B02-DN/HN) prints "
                    "'Trong do: Chi phi di vay' as an unsigned breakdown of Chi phi tai chinh; VCI's "
                    "income_statement raw_value sign convention for this item is negative.",
        "reconcile": lambda raw, official: raw == -official,
    },
    # VCB FY2024 (Circular 49/2014/TT-NHNN consolidated income statement, form
    # B03/TCTD-HN): these four lines are subtraction terms in the statement's own
    # printed running total (e.g. XI = IX - X) and are shown in parentheses on the
    # page; KBS's raw_value for each is the plain positive magnitude. Not
    # ticker-specific -- applies to any bank sharing this raw item vocabulary.
    ("income_statement", "interest_expense_and_similar_expenses"): {
        "version": "v1",
        "citation": "Form B03/TCTD-HN line 2 'Chi phi lai va cac chi phi tuong tu' is printed in "
                    "parentheses (subtracted from line 1 to give I. Thu nhap lai thuan); KBS's "
                    "raw_value sign convention for this item is positive.",
        "reconcile": lambda raw, official: raw == -official,
    },
    ("income_statement", "operating_expenses"): {
        "version": "v1",
        "citation": "Form B03/TCTD-HN line VIII 'Chi phi hoat dong' is printed in parentheses "
                    "(subtracted per the statement's own IX = I+...+VII-VIII formula); KBS's "
                    "raw_value sign convention for this item is positive.",
        "reconcile": lambda raw, official: raw == -official,
    },
    ("income_statement", "provision_for_credit_losses"): {
        "version": "v1",
        "citation": "Form B03/TCTD-HN line X 'Chi phi du phong rui ro tin dung' is printed in "
                    "parentheses (subtracted per the statement's own XI = IX-X formula); KBS's "
                    "raw_value sign convention for this item is positive.",
        "reconcile": lambda raw, official: raw == -official,
    },
    ("income_statement", "corporate_income_tax"): {
        "version": "v1",
        "citation": "Form B03/TCTD-HN line XII 'Chi phi thue TNDN' is printed in parentheses "
                    "(subtracted from XI to give XIII. Loi nhuan sau thue); KBS's raw_value sign "
                    "convention for this item is positive.",
        "reconcile": lambda raw, official: raw == -official,
    },
}

# Generic derived-metric composition, mirroring cash_flow_debt_mapping.py's own
# _derive_total_debt/_derive_shareholders_equity component sets. Not ticker-specific:
# applies to any ticker's canonical records.
_DERIVED_COMPONENTS: dict[str, tuple[str, ...]] = {
    "total_interest_bearing_debt": ("short_term_borrowings", "long_term_borrowings"),
    "shareholders_equity": ("total_equity", "minority_interest_equity"),
    "total_operating_income": ("operating_profit_before_credit_provision", "bank_operating_expenses"),
}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_value(statement_type: str, raw_item_id: str, raw_value: Any, official_value: Any) -> tuple[bool, str]:
    rule = _SIGN_RULES.get((statement_type, raw_item_id))
    if rule is None:
        return raw_value == official_value, "exact"
    return bool(rule["reconcile"](raw_value, official_value)), rule["version"]


def _third_party_mirror_provenance_declared(record: Mapping[str, Any]) -> bool:
    """A record opts into the weaker third-party-mirror provenance class by setting
    any one of these three top-level classification facts. Once any one is present,
    all three plus a matching evidence_acceptance block become mandatory -- a
    record can never partially declare this class and fall back to hash-only."""
    return any(field in record for field in ("issuer_hosted", "source_host_classification", "embedded_signature_status"))


def _third_party_mirror_acceptance_ok(record: Mapping[str, Any]) -> bool:
    """Fail-closed acceptance for an audited issuer document retained from a
    third-party mirror with no embedded signature (see THIRD_PARTY_MIRROR_UNSIGNED_
    ACCEPTANCE_RULE above). Generic and reusable: keyed entirely on explicit field
    values, never on ticker or issuer identity. Document hash equality (checked
    separately by the caller) is necessary but never sufficient here -- every
    identity, audit, scope, and exact-match fact below must also be explicit."""
    if (record.get("issuer_hosted") is not False
            or record.get("source_host_classification") != "third_party_mirror"
            or record.get("embedded_signature_status") not in _SUPPORTED_EMBEDDED_SIGNATURE_STATUSES_FOR_MIRROR_RULE):
        return False
    acceptance = record.get("evidence_acceptance")
    if not isinstance(acceptance, Mapping) or acceptance.get("rule_version") != THIRD_PARTY_MIRROR_UNSIGNED_ACCEPTANCE_RULE:
        return False
    if not bool(acceptance.get("issuer_identity")) or not bool(acceptance.get("auditor_identity")):
        return False
    if not bool(acceptance.get("audit_opinion")) or not bool(acceptance.get("report_date")):
        return False
    if acceptance.get("reporting_scope") not in _SUPPORTED_SCOPES or not bool(acceptance.get("reporting_period")):
        return False
    document_sha256 = acceptance.get("document_sha256")
    if not bool(document_sha256) or document_sha256 != record.get("sha256"):
        return False
    if acceptance.get("provider_exact_match_status") != "exact_match":
        return False
    warnings = acceptance.get("warnings")
    if not isinstance(warnings, list) or THIRD_PARTY_MIRROR_HOSTING_WARNING not in warnings:
        return False
    return True


def _manifest_acceptance_ok(record: Mapping[str, Any]) -> bool:
    """Validate an optional, versioned non-URL evidence acceptance assertion."""
    if _third_party_mirror_provenance_declared(record):
        return _third_party_mirror_acceptance_ok(record)
    acceptance = record.get("evidence_acceptance")
    if acceptance is None:
        return True
    if not isinstance(acceptance, Mapping):
        return False
    if acceptance.get("rule_version") != SIGNED_ISSUER_ACCEPTANCE_RULE:
        return False
    signer = acceptance.get("embedded_signer")
    corroboration = acceptance.get("official_source_corroboration")
    return (
        isinstance(signer, Mapping)
        and bool(signer.get("identity"))
        and bool(signer.get("tax_identifier"))
        and isinstance(corroboration, Mapping)
        and bool(corroboration.get("source_url"))
        and bool(corroboration.get("audit_report_number"))
        and acceptance.get("direct_document_url_status") == "unavailable_recorded"
    )

def _resolve_manifest_document(manifest_path: Path, record: Mapping[str, Any]) -> Path | None:
    """Resolve one manifest-declared document without directory searching.

    Older retained evidence keeps the document flat beside ``manifest.json`` via
    ``filename``.  Governed retained artifacts instead declare an explicit
    ``archive_document_path`` relative to this Producer checkout.  The latter is
    authoritative when present: a missing archive document must not fall back to
    a same-named flat file.
    """
    archive_document_path = record.get("archive_document_path")
    if archive_document_path is not None:
        if not isinstance(archive_document_path, str) or not archive_document_path.strip():
            return None
        document = Path(archive_document_path)
        if not document.is_absolute():
            if ".." in document.parts:
                return None
            producer_root = Path(__file__).resolve().parent
            document = producer_root / document
        return document

    filename = record.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        return None
    flat_document = Path(filename)
    # ``filename`` is deliberately a flat manifest representation.  Never turn
    # it into a search key or permit it to escape the evidence directory.
    if flat_document.is_absolute() or len(flat_document.parts) != 1:
        return None
    return manifest_path.parent / flat_document


def _load_manifest(runtime_root: Path) -> dict[str, dict[str, Any]] | None:
    """Return {evidence_id: record} restricted to hash-verified, qualified evidence.

    None means the manifest itself is missing/malformed (fail closed globally).
    An empty dict is a distinct, valid state: the manifest parsed fine but no
    entry hash-verified -- callers must still report per-citation rejections.
    """
    path = runtime_root / MANIFEST_RELATIVE
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        return None
    verified: dict[str, dict[str, Any]] = {}
    for record in manifest.get("records", []):
        if not isinstance(record, dict):
            continue
        evidence_id = record.get("evidence_id")
        if not evidence_id or record.get("qualification_state") != "qualified":
            continue
        if not _manifest_acceptance_ok(record):
            continue
        document = _resolve_manifest_document(path, record)
        if document is None:
            continue
        if not document.is_file() or _sha256_file(document) != record.get("sha256"):
            continue
        verified[evidence_id] = record
    return verified


def _manifest_declares_evidence_id(runtime_root: Path, evidence_id: Any) -> bool:
    """Whether the authority manifest declares an ID, regardless of verification.

    This intentionally does not make a document usable.  It only lets callers
    distinguish a registration absence from a declared document that then fails
    qualification, path resolution, or hash verification.
    """
    path = runtime_root / MANIFEST_RELATIVE
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (isinstance(manifest, dict) and manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
            and any(isinstance(record, dict) and record.get("evidence_id") == evidence_id
                    for record in manifest.get("records", [])))


def _load_citation_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / CITATIONS_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def load_verified_citations(runtime_root: Path) -> dict[str, Any]:
    """Read and verify the evidence manifest and citation file; fails closed per record.

    Returns {"status": "available"|"unavailable", "version": VERSION,
    "by_observation_id": {observation_id: verified_citation}, "rejected": [...]}.
    A missing manifest or citations file yields an empty by_observation_id, so
    canonical projection behaves exactly as it did before this module existed.
    """
    evidence_by_id = _load_manifest(runtime_root)
    rows = _load_citation_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if evidence_by_id is None or rows is None:
        return {"status": "unavailable", "version": VERSION, "by_observation_id": {}, "rejected": rejected}

    observations_by_id = {row["observation_id"]: row for row in read_observations(store_path(runtime_root))}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_CITATION_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        grouped.setdefault(raw["observation_id"], []).append(raw)

    by_observation: dict[str, dict[str, Any]] = {}
    for observation_id, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            rejected.append({"observation_id": observation_id, "reason": "conflicting_citations"})
            continue
        citation = next(iter(unique_by_content.values()))

        expected_id = _hash({"observation_id": citation["observation_id"], "evidence_id": citation["evidence_id"],
                              "raw_item_id": citation["raw_item_id"], "matched_value": citation["official_value"]})
        if citation["citation_id"] != expected_id:
            rejected.append({"observation_id": observation_id, "reason": "citation_id_not_deterministic"})
            continue

        evidence = evidence_by_id.get(citation["evidence_id"])
        if evidence is None:
            rejected.append({"observation_id": observation_id, "reason": "evidence_missing_or_hash_mismatch"})
            continue

        if citation["statement_scope"] not in _SUPPORTED_SCOPES:
            rejected.append({"observation_id": observation_id, "reason": "unsupported_scope"})
            continue

        observation = observations_by_id.get(observation_id)
        if observation is None:
            rejected.append({"observation_id": observation_id, "reason": "observation_id_not_found_in_current_store"})
            continue

        identity_fields = ("ticker", "reporting_frequency", "reporting_period", "raw_statement_type", "raw_item_id")
        if any(observation.get(field) != citation.get(field) for field in identity_fields):
            rejected.append({"observation_id": observation_id, "reason": "observation_identity_mismatch"})
            continue

        if observation.get("raw_value") != citation["raw_value"]:
            rejected.append({"observation_id": observation_id, "reason": "raw_value_drifted_from_citation"})
            continue

        ok, rule_version = _verify_value(citation["raw_statement_type"], citation["raw_item_id"], observation["raw_value"], citation["official_value"])
        if not ok:
            rejected.append({"observation_id": observation_id, "reason": "value_mismatch_after_sign_rule"})
            continue

        by_observation[observation_id] = {
            "observation_id": observation_id,
            "evidence_id": citation["evidence_id"],
            "citation_id": citation["citation_id"],
            "statement_scope": citation["statement_scope"],
            "currency": citation["currency"],
            "unit_scale": citation["unit_scale"],
            "match_method": citation.get("match_method", "exact_numeric_match"),
            "sign_rule_version": rule_version,
            "citation": citation.get("citation"),
            "qualification_version": VERSION,
            "verified_at": citation.get("verified_at"),
            # Retained document metadata is passed through only after the manifest
            # record itself has hash-verified above.  These remain provenance, not
            # a substitute for the reporting period or citation.
            "publication_date": evidence.get("publication_date"),
            "retrieved_at": evidence.get("retrieved_at"),
            "document_sha256": evidence.get("sha256"),
            "source_url": evidence.get("source_url"),
        }

    return {"status": "available" if by_observation else "unavailable", "version": VERSION,
            "by_observation_id": by_observation, "rejected": rejected}


def _load_share_basis_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / SHARE_BASIS_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def load_verified_share_basis(runtime_root: Path) -> dict[str, Any]:
    """Read and verify data/official-evidence/share_basis_citations.jsonl; fails closed per record.

    Each entry is a standalone, PDF-cited fact -- share counts are never part
    of a VCI raw observation, so unlike load_verified_citations there is no
    observation_id to cross-check against. The three share-count identities
    (period-end, valuation-date, weighted-average basic/diluted) are kept
    strictly separate by identity_type; nothing here ever infers one from
    another or from a price.

    Returns {"status": ..., "version": VERSION,
    "by_identity": {(ticker, identity_type, reporting_period): verified_entry},
    "rejected": [...]}. A missing manifest or citations file yields an empty result.
    """
    evidence_by_id = _load_manifest(runtime_root)
    rows = _load_share_basis_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if evidence_by_id is None or rows is None:
        return {"status": "unavailable", "version": VERSION, "by_identity": {}, "rejected": rejected}

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_SHARE_BASIS_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        key = (raw["ticker"], raw["identity_type"], raw["reporting_period"])
        grouped.setdefault(key, []).append(raw)

    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            ids = {c.get("citation_id") for c in unique_by_content.values()}
            successors = [c for c in unique_by_content.values()
                          if isinstance(c.get("supersedes_citation_ids"), list)
                          and set(c["supersedes_citation_ids"]) == ids - {c.get("citation_id")}
                          and all(c.get("value") == other.get("value") for other in unique_by_content.values() if other is not c)]
            if len(successors) != 1:
                rejected.append({"key": key, "reason": "conflicting_citations"})
                continue
            citation = successors[0]
        else:
            citation = next(iter(unique_by_content.values()))

        expected_id = _hash({"ticker": citation["ticker"], "identity_type": citation["identity_type"],
                              "reporting_period": citation["reporting_period"], "evidence_id": citation["evidence_id"],
                              "value": citation["value"]})
        if citation["citation_id"] != expected_id:
            rejected.append({"key": key, "reason": "citation_id_not_deterministic"})
            continue

        if citation["identity_type"] not in _SUPPORTED_SHARE_IDENTITIES:
            rejected.append({"key": key, "reason": "unsupported_identity_type"})
            continue

        evidence = evidence_by_id.get(citation["evidence_id"])
        if evidence is None:
            rejected.append({"key": key, "reason": "evidence_missing_or_hash_mismatch"})
            continue

        by_identity[key] = {
            "ticker": citation["ticker"],
            "identity_type": citation["identity_type"],
            "reporting_frequency": citation["reporting_frequency"],
            "reporting_period": citation["reporting_period"],
            "value": citation["value"],
            "evidence_id": citation["evidence_id"],
            "citation_id": citation["citation_id"],
            "citation": citation.get("citation"),
            "qualification_version": VERSION,
            "verified_at": citation.get("verified_at"),
            "unit": citation.get("unit"),
            "share_class": citation.get("share_class"),
            "publication_date": evidence.get("publication_date"),
            "retrieved_at": evidence.get("retrieved_at"),
            "document_sha256": evidence.get("sha256"),
            "source_url": evidence.get("source_url"),
        }

    return {"status": "available" if by_identity else "unavailable", "version": VERSION,
            "by_identity": by_identity, "rejected": rejected}


def latest_share_basis(by_identity: Mapping[tuple[str, str, str], dict[str, Any]], ticker: str,
                        identity_type: str, frequency: str = "annual") -> dict[str, Any] | None:
    """The most recent verified entry for (ticker, identity_type, frequency), or None.

    Never falls back to a different identity_type -- an absent period-end
    entry is not satisfied by a weighted-average or valuation-date one.
    """
    candidates = [entry for (entry_ticker, entry_identity, _), entry in by_identity.items()
                  if entry_ticker == ticker and entry_identity == identity_type
                  and entry["reporting_frequency"] == frequency]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry["reporting_period"])


_REQUIRED_CASH_DIVIDEND_FIELDS = (
    "citation_id", "ticker", "event_type", "resolution_number",
    "declaration_date", "cash_amount", "currency", "evidence_id"
)
_SUPPORTED_DIVIDEND_EVENT_TYPES = {"cash_dividend"}


def _load_cash_dividend_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / CASH_DIVIDEND_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def load_verified_cash_dividends(runtime_root: Path) -> dict[str, Any]:
    """Read and verify data/official-evidence/cash_dividend_citations.jsonl; fails closed per record.

    Emits Producer-owned canonical cash-dividend event objects referencing verified evidence IDs,
    document hashes, and citations. Emits 0 adjustment factors and 0 adjusted returns.

    Returns {"status": ..., "version": VERSION, "by_event_key": {...}, "events": [...], "rejected": [...]}.
    """
    evidence_by_id = _load_manifest(runtime_root)
    rows = _load_cash_dividend_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if evidence_by_id is None or rows is None:
        return {"status": "unavailable", "version": VERSION, "by_event_key": {}, "events": [], "rejected": rejected}

    grouped: dict[tuple[str, str, str, str, float], list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_CASH_DIVIDEND_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        key = (raw["ticker"], raw["event_type"], str(raw["resolution_number"]), str(raw["declaration_date"]), float(raw["cash_amount"]))
        grouped.setdefault(key, []).append(raw)

    by_event_key: dict[tuple[str, str, str, str, float], dict[str, Any]] = {}
    canonical_events: list[dict[str, Any]] = []

    for key, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            ids = {c.get("citation_id") for c in unique_by_content.values()}
            successors = [c for c in unique_by_content.values()
                          if isinstance(c.get("supersedes_citation_ids"), list)
                          and set(c["supersedes_citation_ids"]) == ids - {c.get("citation_id")}]
            if len(successors) != 1:
                rejected.append({"key": key, "reason": "conflicting_citations"})
                continue
            citation = successors[0]
        else:
            citation = next(iter(unique_by_content.values()))

        expected_id = _hash({
            "ticker": citation["ticker"],
            "event_type": citation["event_type"],
            "resolution_number": citation["resolution_number"],
            "declaration_date": citation["declaration_date"],
            "cash_amount": citation["cash_amount"],
            "payment_date": citation.get("payment_date"),
            "event_status": citation.get("event_status"),
            "evidence_id": citation["evidence_id"]
        })
        if citation["citation_id"] != expected_id:
            rejected.append({"key": key, "reason": "citation_id_not_deterministic"})
            continue

        if citation["event_type"] not in _SUPPORTED_DIVIDEND_EVENT_TYPES:
            rejected.append({"key": key, "reason": "unsupported_event_type"})
            continue

        if citation["currency"] != "VND":
            rejected.append({"key": key, "reason": "unsupported_currency"})
            continue

        evidence = evidence_by_id.get(citation["evidence_id"])
        if evidence is None:
            rejected.append({"key": key, "reason": "evidence_missing_or_hash_mismatch"})
            continue

        event_object = {
            "event_id": citation["citation_id"],
            "ticker": citation["ticker"],
            "issuer": evidence.get("issuer"),
            "event_type": citation["event_type"],
            "resolution_number": citation["resolution_number"],
            "declaration_date": citation["declaration_date"],
            "record_date": citation.get("record_date"),
            "ex_dividend_date": citation.get("ex_dividend_date"),
            "payment_date": citation.get("payment_date"),
            "effective_date": citation.get("effective_date"),
            "cash_amount": float(citation["cash_amount"]),
            "dividend_rate_pct": citation.get("dividend_rate_pct"),
            "currency": citation["currency"],
            "share_class": citation.get("share_class", "common"),
            "event_status": citation.get("event_status", "completed"),
            "supersedes_citation_ids": citation.get("supersedes_citation_ids", []),
            "evidence": {
                "evidence_id": citation["evidence_id"],
                "citation_id": citation["citation_id"],
                "citation": citation.get("citation"),
                "document_sha256": evidence.get("sha256"),
                "publication_date": evidence.get("publication_date"),
                "source_url": evidence.get("source_url"),
                "authority": evidence.get("authority"),
            },
            "qualification_version": VERSION,
            "verified_at": citation.get("verified_at"),
        }

        by_event_key[key] = event_object
        canonical_events.append(event_object)

    return {
        "status": "available" if canonical_events else "unavailable",
        "version": VERSION,
        "by_event_key": by_event_key,
        "events": canonical_events,
        "rejected": rejected
    }


_REQUIRED_NON_CASH_EVENT_FIELDS = (
    "citation_id", "ticker", "event_type", "resolution_number",
    "declaration_date", "ratio_numerator", "ratio_denominator", "evidence_id"
)
_SUPPORTED_NON_CASH_EVENT_TYPES = {"stock_dividend", "bonus_share"}


def _load_non_cash_event_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / NON_CASH_EVENT_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def load_verified_non_cash_events(runtime_root: Path) -> dict[str, Any]:
    """Read and verify data/official-evidence/non_cash_event_citations.jsonl; fails closed per record.

    Emits Producer-owned canonical non-cash corporate action event objects (stock_dividend, bonus_share)
    referencing verified evidence IDs, document hashes, and citations.
    Emits 0 adjustment factors and 0 adjusted returns.

    Returns {"status": ..., "version": VERSION, "by_event_key": {...}, "events": [...], "rejected": [...]}.
    """
    evidence_by_id = _load_manifest(runtime_root)
    rows = _load_non_cash_event_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if evidence_by_id is None or rows is None:
        return {"status": "unavailable", "version": VERSION, "by_event_key": {}, "events": [], "rejected": rejected}

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_NON_CASH_EVENT_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        key = (raw["ticker"], raw["event_type"], str(raw["resolution_number"]), str(raw["declaration_date"]))
        grouped.setdefault(key, []).append(raw)

    by_event_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    canonical_events: list[dict[str, Any]] = []

    for key, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            ids = {c.get("citation_id") for c in unique_by_content.values()}
            successors = [c for c in unique_by_content.values()
                          if isinstance(c.get("supersedes_citation_ids"), list)
                          and set(c["supersedes_citation_ids"]) == ids - {c.get("citation_id")}]
            if len(successors) != 1:
                rejected.append({"key": key, "reason": "conflicting_citations"})
                continue
            citation = successors[0]
        else:
            citation = next(iter(unique_by_content.values()))

        expected_id = _hash({
            "ticker": citation["ticker"],
            "event_type": citation["event_type"],
            "resolution_number": citation["resolution_number"],
            "declaration_date": citation["declaration_date"],
            "ratio_numerator": citation["ratio_numerator"],
            "ratio_denominator": citation["ratio_denominator"],
            "ex_rights_date": citation.get("ex_rights_date"),
            "event_status": citation.get("event_status"),
            "evidence_id": citation["evidence_id"]
        })
        if citation["citation_id"] != expected_id:
            rejected.append({"key": key, "reason": "citation_id_not_deterministic"})
            continue

        if citation["event_type"] not in _SUPPORTED_NON_CASH_EVENT_TYPES:
            rejected.append({"key": key, "reason": "unsupported_event_type"})
            continue

        evidence = evidence_by_id.get(citation["evidence_id"])
        if evidence is None:
            rejected.append({"key": key, "reason": "evidence_missing_or_hash_mismatch"})
            continue

        num = int(citation["ratio_numerator"])
        den = int(citation["ratio_denominator"])
        ratio_float = num / den if den > 0 else None
        if ratio_float is None:
            rejected.append({"key": key, "reason": "invalid_entitlement_ratio"})
            continue

        event_object = {
            "event_id": citation["citation_id"],
            "ticker": citation["ticker"],
            "issuer": evidence.get("issuer"),
            "event_type": citation["event_type"],
            "resolution_number": citation["resolution_number"],
            "declaration_date": citation["declaration_date"],
            "record_date": citation.get("record_date"),
            "ex_rights_date": citation.get("ex_rights_date"),
            "distribution_date": citation.get("distribution_date"),
            "effective_date": citation.get("effective_date"),
            "entitlement_ratio": {"new_shares": num, "existing_shares": den, "ratio_float": ratio_float},
            "funding_source": citation.get("funding_source"),
            "share_class": citation.get("share_class", "common"),
            "pre_action_shares": citation.get("pre_action_shares"),
            "post_action_shares": citation.get("post_action_shares"),
            "fractional_share_treatment": citation.get("fractional_share_treatment"),
            "event_status": citation.get("event_status", "completed"),
            "supersedes_citation_ids": citation.get("supersedes_citation_ids", []),
            "evidence": {
                "evidence_id": citation["evidence_id"],
                "citation_id": citation["citation_id"],
                "citation": citation.get("citation"),
                "document_sha256": evidence.get("sha256"),
                "publication_date": evidence.get("publication_date"),
                "source_url": evidence.get("source_url"),
                "authority": evidence.get("authority"),
            },
            "qualification_version": VERSION,
            "verified_at": citation.get("verified_at"),
        }

        by_event_key[key] = event_object
        canonical_events.append(event_object)

    return {
        "status": "available" if canonical_events else "unavailable",
        "version": VERSION,
        "by_event_key": by_event_key,
        "events": canonical_events,
        "rejected": rejected
    }


def _load_market_price_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / MARKET_PRICE_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def _query_ohlcv(db_path: Path, ticker: str, trading_date: str) -> dict[str, Any] | None:
    """Read-only lookup of one (ticker, date) row. Never opens the database for writing."""
    if not db_path.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            "SELECT ticker, date, open, high, low, close, source FROM ohlcv WHERE ticker=? AND date=?",
            (ticker, trading_date),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def load_verified_market_price(runtime_root: Path) -> dict[str, Any]:
    """Read and verify data/official-evidence/market_price_citations.jsonl.

    Each entry cites one specific (ticker, trading_date) row in the read-only
    ohlcv table. There is no PDF/manifest hash here -- the database row itself
    is the evidence, re-queried on every call and required to still match the
    cited price_field/value/provider exactly. Fails closed on a missing row, a
    drifted value, a non-deterministic citation_id, two differing citations
    for the same (ticker, trading_date), or an adjustment_status outside the
    supported set. Never opens the database for writing, and never derives a
    "nearest prior trading day" -- only the exact date actually cited.

    Returns {"status": ..., "version": VERSION,
    "by_ticker_date": {(ticker, trading_date): verified_entry}, "rejected": [...]}.
    """
    rows = _load_market_price_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if rows is None:
        return {"status": "unavailable", "version": VERSION, "by_ticker_date": {}, "rejected": rejected}

    db_path = runtime_root / DB_RELATIVE
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_MARKET_PRICE_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        grouped.setdefault((raw["ticker"], raw["trading_date"]), []).append(raw)

    by_ticker_date: dict[tuple[str, str], dict[str, Any]] = {}
    for key, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            rejected.append({"key": key, "reason": "conflicting_citations"})
            continue
        citation = next(iter(unique_by_content.values()))

        expected_id = _hash({"ticker": citation["ticker"], "trading_date": citation["trading_date"],
                              "price_field": citation["price_field"], "value": citation["value"],
                              "provider": citation["provider"]})
        if citation["citation_id"] != expected_id:
            rejected.append({"key": key, "reason": "citation_id_not_deterministic"})
            continue

        if citation["adjustment_status"] not in _SUPPORTED_ADJUSTMENT_STATUSES:
            rejected.append({"key": key, "reason": "unsupported_adjustment_status"})
            continue

        # The status above records that *this repository* applied no adjustment. Whether
        # the provider already did is a separate question, and it is the one every caller
        # of this function is actually asking.
        if not raw_as_traded_eligible(citation["provider"]):
            rejected.append(
                {
                    "key": key,
                    "reason": ineligibility_reason(citation["provider"]),
                    "provider": citation["provider"],
                }
            )
            continue

        live = _query_ohlcv(db_path, citation["ticker"], citation["trading_date"])
        if live is None:
            rejected.append({"key": key, "reason": "ohlcv_row_missing"})
            continue
        if live.get(citation["price_field"]) != citation["value"] or live.get("source") != citation["provider"]:
            rejected.append({"key": key, "reason": "ohlcv_value_drifted_from_citation"})
            continue

        by_ticker_date[key] = {**citation, "qualification_version": VERSION}

    return {"status": "available" if by_ticker_date else "unavailable", "version": VERSION,
            "by_ticker_date": by_ticker_date, "rejected": rejected}


EBITDA_COMPONENTS_RELATIVE = Path("data") / "official-evidence" / "ebitda_component_citations.jsonl"
# HPG's consolidated income statement prints "Lợi nhuận thuần từ hoạt động kinh doanh"
# (mã số 30, operating profit) net of financial income/expense -- {30 = 20 + (21-22) -
# (25+26)} per its own printed formula -- so it is not a pre-interest figure and is
# never used as the EBIT-equivalent input here. profit_before_tax + interest_expense
# correctly reverses out tax and the disclosed interest component of financial expense,
# matching the literal Earnings-Before-Interest-and-Tax meaning of the acronym.
# operating_profit is audited and available (13,267,005,585,330 for HPG FY2024) but is
# deliberately excluded -- see docs/hpg_fy2024_ebitda_qualification.md.
EBITDA_FORMULA_VERSION = "ebitda_v1_profit_before_tax_plus_interest_expense_plus_depreciation_and_amortization"
# Carried on every derived ebitda record (never omitted, never merged into "reason",
# which this codebase reserves for explaining non-availability): this figure is a
# specific, versioned derivation from the audited statements, not a reported provider
# field and not normalized/adjusted for one-off items -- comparisons to a provider's
# own EBITDA field or to peer EBITDA under a different formula may not be meaningful.
EBITDA_COMPARABILITY_WARNING = (
    "derived_ebitda_specific_formula_version_" + EBITDA_FORMULA_VERSION + "_not_a_reported_or_normalized_ebitda_"
    "and_may_not_be_comparable_to_provider_reported_or_differently_formulated_peer_ebitda"
)
_SUPPORTED_EBITDA_COMPONENTS = {"profit_before_tax", "interest_expense", "depreciation_and_amortization"}
_REQUIRED_EBITDA_COMPONENT_FIELDS = ("citation_id", "ticker", "metric", "reporting_frequency", "reporting_period",
    "statement_scope", "currency", "unit_scale", "value", "evidence_id")


def _load_ebitda_component_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / EBITDA_COMPONENTS_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def load_verified_ebitda_components(runtime_root: Path) -> dict[str, Any]:
    """Read and verify data/official-evidence/ebitda_component_citations.jsonl; fails closed per record.

    Each entry is a standalone, PDF-cited fact (profit_before_tax, interest_expense, or
    depreciation_and_amortization) -- like share_basis_citations.jsonl, none of these is
    part of a retained VCI raw observation, so there is no observation_id to cross-check
    against. Verification is limited to: the cited evidence document still hash-verifies
    against the manifest, the citation_id is the deterministic hash of its own content,
    the metric is in the supported set, the scope is supported, and no two citations
    conflict for the same (ticker, metric, reporting_period).

    Returns {"status": ..., "version": VERSION, "by_key": {(ticker, metric,
    reporting_period): verified_entry}, "rejected": [...]}.
    """
    evidence_by_id = _load_manifest(runtime_root)
    rows = _load_ebitda_component_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if evidence_by_id is None or rows is None:
        return {"status": "unavailable", "version": VERSION, "by_key": {}, "rejected": rejected}

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_EBITDA_COMPONENT_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        key = (raw["ticker"], raw["metric"], raw["reporting_period"])
        grouped.setdefault(key, []).append(raw)

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            rejected.append({"key": key, "reason": "conflicting_citations"})
            continue
        citation = next(iter(unique_by_content.values()))

        expected_id = _hash({"ticker": citation["ticker"], "metric": citation["metric"],
                              "reporting_period": citation["reporting_period"], "evidence_id": citation["evidence_id"],
                              "value": citation["value"]})
        if citation["citation_id"] != expected_id:
            rejected.append({"key": key, "reason": "citation_id_not_deterministic"})
            continue

        if citation["metric"] not in _SUPPORTED_EBITDA_COMPONENTS:
            rejected.append({"key": key, "reason": "unsupported_metric"})
            continue

        if citation["statement_scope"] not in _SUPPORTED_SCOPES:
            rejected.append({"key": key, "reason": "unsupported_scope"})
            continue

        evidence = evidence_by_id.get(citation["evidence_id"])
        if evidence is None:
            rejected.append({"key": key, "reason": "evidence_missing_or_hash_mismatch"})
            continue
        if str(evidence.get("ticker") or "").upper() != str(citation["ticker"]).upper():
            rejected.append({"key": key, "reason": "evidence_ticker_mismatch"})
            continue

        by_key[key] = {
            "ticker": citation["ticker"], "metric": citation["metric"],
            "reporting_frequency": citation["reporting_frequency"], "reporting_period": citation["reporting_period"],
            "statement_scope": citation["statement_scope"], "currency": citation["currency"],
            "unit_scale": citation["unit_scale"], "value": citation["value"],
            "evidence_id": citation["evidence_id"], "citation_id": citation["citation_id"],
            "citation": citation.get("citation"), "qualification_version": VERSION,
            "verified_at": citation.get("verified_at"),
        }

    return {"status": "available" if by_key else "unavailable", "version": VERSION, "by_key": by_key, "rejected": rejected}


def latest_ebitda_component(by_key: Mapping[tuple[str, str, str], dict[str, Any]], ticker: str,
                             metric: str, frequency: str = "annual") -> dict[str, Any] | None:
    """The most recent verified entry for (ticker, metric, frequency), or None.

    Never falls back to a different metric -- an absent profit_before_tax entry is not
    satisfied by interest_expense or depreciation_and_amortization, even if numerically
    plausible.
    """
    candidates = [entry for (entry_ticker, entry_metric, _), entry in by_key.items()
                  if entry_ticker == ticker and entry_metric == metric and entry["reporting_frequency"] == frequency]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry["reporting_period"])


def derive_ebitda(by_key: Mapping[tuple[str, str, str], dict[str, Any]], ticker: str,
                   frequency: str = "annual") -> dict[str, Any] | None:
    """ebitda = profit_before_tax + interest_expense + depreciation_and_amortization.

    All three components must be independently verified (load_verified_ebitda_components)
    and must agree exactly on reporting_period, statement_scope, currency, and unit_scale --
    never combined across a mismatch. Returns None (the canonical record is simply absent,
    same convention as every other evidence-gated helper in this module) when any component
    is missing or the three disagree on identity. Depreciation and amortization are combined
    only because the cited cash-flow-statement line ("Khấu hao và phân bổ") already reports
    them combined; the separate goodwill-amortization line on the same statement ("Phân bổ
    lợi thế thương mại") is a distinct, non-operating M&A-related item and is never folded
    in here -- see docs/hpg_fy2024_ebitda_qualification.md.

    The returned record always carries `warnings: [EBITDA_COMPARABILITY_WARNING]` alongside
    `formula_version` -- this is a derived, versioned figure, never a reported provider
    field and never normalized/adjusted, so it is never presented as if it were either.
    """
    pbt = latest_ebitda_component(by_key, ticker, "profit_before_tax", frequency)
    interest = latest_ebitda_component(by_key, ticker, "interest_expense", frequency)
    da = latest_ebitda_component(by_key, ticker, "depreciation_and_amortization", frequency)
    if pbt is None or interest is None or da is None:
        return None
    components = (pbt, interest, da)
    if (len({c["reporting_period"] for c in components}) != 1 or len({c["statement_scope"] for c in components}) != 1
            or len({c["currency"] for c in components}) != 1 or len({c["unit_scale"] for c in components}) != 1):
        return None
    return {
        "canonical_metric": "ebitda", "value": pbt["value"] + interest["value"] + da["value"],
        "source": "ebitda_component_evidence",
        "source_field": "profit_before_tax+interest_expense+depreciation_and_amortization",
        "source_statement": "income_statement_and_cash_flow_statement",
        "period_identity": {"period": pbt["reporting_period"], "period_type": frequency},
        "statement_scope": pbt["statement_scope"], "currency": pbt["currency"], "unit_scale": pbt["unit_scale"],
        "derivation_status": "derived", "quality_state": "available", "reason": None,
        "restatement_state": "unknown", "formula_version": EBITDA_FORMULA_VERSION,
        "warnings": [EBITDA_COMPARABILITY_WARNING],
        "derivation_lineage": {
            "formula": "profit_before_tax + interest_expense + depreciation_and_amortization",
            "formula_version": EBITDA_FORMULA_VERSION,
            "components": [{"metric": c["metric"], "value": c["value"], "evidence_id": c["evidence_id"],
                             "citation_id": c["citation_id"], "citation": c["citation"]} for c in components],
            "excluded": [
                    "operating_profit (line code 30): excluded because the printed formula already nets financial income and expense; it is not a pre-interest figure.",
                    "goodwill amortization (line code 02): excluded because it is a distinct cash-flow-statement addback separate from the cited combined depreciation_and_amortization line; it is never folded into EBITDA.",
                ],
        },
    }


def _clear_resolved_reason(reason: Any) -> str | None:
    if not reason:
        return None
    remaining = [warning for warning in str(reason).split(";") if warning not in _RESOLVED_WARNINGS]
    return ";".join(remaining) or None


def _enrich_direct(record: dict[str, Any], by_observation_id: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    if record.get("derivation_status") != "direct":
        return record
    observation_ids = record.get("observation_ids") or []
    if len(observation_ids) != 1:
        return record
    verified = by_observation_id.get(observation_ids[0])
    if verified is None:
        return record
    enriched = dict(record)
    enriched["statement_scope"] = verified["statement_scope"]
    enriched["currency"] = verified["currency"]
    enriched["unit_scale"] = verified["unit_scale"]
    enriched["quality_state"] = "available"
    enriched["reason"] = _clear_resolved_reason(record.get("reason"))
    enriched["evidence"] = {
        "evidence_id": verified["evidence_id"],
        "citation_id": verified["citation_id"],
        "match_method": verified["match_method"],
        "sign_rule_version": verified["sign_rule_version"],
        "citation": verified["citation"],
        "qualification_version": verified["qualification_version"],
    }
    return enriched


def _enrich_derived(record: dict[str, Any], siblings: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if record.get("derivation_status") != "derived":
        return record
    components = _DERIVED_COMPONENTS.get(record.get("canonical_metric"))
    if not components:
        return record
    period_identity = record.get("period_identity")
    matches: list[dict[str, Any]] = []
    for metric in components:
        sibling = next((s for s in siblings if s.get("canonical_metric") == metric
                         and s.get("period_identity") == period_identity
                         and s.get("derivation_status") == "direct"), None)
        if sibling is None or "evidence" not in sibling:
            return record
        matches.append(sibling)
    scopes, currencies, scales = ({m["statement_scope"] for m in matches}, {m["currency"] for m in matches}, {m["unit_scale"] for m in matches})
    if len(scopes) != 1 or len(currencies) != 1 or len(scales) != 1:
        return record
    enriched = dict(record)
    enriched["statement_scope"], enriched["currency"], enriched["unit_scale"] = scopes.pop(), currencies.pop(), scales.pop()
    enriched["quality_state"] = "available"
    enriched["reason"] = _clear_resolved_reason(record.get("reason"))
    enriched["observation_ids"] = sorted({obs_id for m in matches for obs_id in (m.get("observation_ids") or [])})
    enriched["evidence"] = {"components": [
        {
            "canonical_metric": m["canonical_metric"],
            "derivation_role": "required_component",
            "value": m.get("value"),
            "period_identity": m.get("period_identity"),
            "statement_scope": m.get("statement_scope"),
            "currency": m.get("currency"),
            "unit_scale": m.get("unit_scale"),
            "source": m.get("source"),
            "observation_ids": m.get("observation_ids"),
            **m["evidence"],
        }
        for m in sorted(matches, key=lambda item: item["canonical_metric"])
    ]}
    return enriched


def enrich_canonical_records(by_ticker: Mapping[str, list[dict[str, Any]]], runtime_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Return a new by_ticker structure enriched only where citation linkage is exact.

    Never mutates the input records or observations.jsonl. Contains no
    ticker-specific logic: a record is enriched only when its backing
    observation_id (or, for a derived record, every required component's
    observation_id) has a verified, uniquely-cited, compatible-scope entry in
    qualification_citations.jsonl. Everything else passes through unchanged.
    """
    verified = load_verified_citations(runtime_root)
    by_observation_id = verified["by_observation_id"]
    if not by_observation_id:
        return {ticker: [dict(record) for record in records] for ticker, records in by_ticker.items()}
    result: dict[str, list[dict[str, Any]]] = {}
    for ticker, records in by_ticker.items():
        direct_pass = [_enrich_direct(dict(record), by_observation_id) for record in records]
        result[ticker] = [_enrich_derived(record, direct_pass) for record in direct_pass]
    return result


# Centralized downstream metric-identity reconciliation. Each entry is a reasoned,
# documented equivalence between the canonical name this pipeline produces and the
# name a downstream contract asks for -- never a blind alias. See
# docs/semantic_evidence_bridge_contract.md for the full reasoning.
_METRIC_IDENTITY_MAP: dict[str, dict[str, str]] = {
    "total_interest_bearing_debt": {
        "downstream_name": "total_debt",
        "version": "v1",
        "reason": "fundamental_quality.financial_strength, intrinsic_valuation.fcff_dcf, and "
                  "relative_valuation.ev_ebitda/ev_sales all use total_debt as an enterprise-value "
                  "/ net-debt input (market_cap + debt - cash); by convention that is "
                  "interest-bearing borrowings, not total liabilities.",
    },
    "net_income_attributable_to_parent": {
        "downstream_name": "net_income",
        "version": "v1",
        "reason": "fundamental_quality's DuPont ROE, Piotroski, and net-margin ratios, and "
                  "relative_valuation's P/E denominator, pair net_income against parent-only "
                  "shareholders_equity/EPS; by convention that is income attributable to parent, "
                  "not consolidated income including non-controlling interest.",
    },
}


def reconcile_metric_identities(by_ticker: Mapping[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Expose already evidence-qualified records under the name a downstream contract expects.

    Never activates for a record without a verified "evidence" block from
    enrich_canonical_records: an unresolved identity leaves the downstream
    input unavailable rather than being aliased into existence. The original,
    precisely-named record is always kept alongside the reconciled copy.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for ticker, records in by_ticker.items():
        extra: list[dict[str, Any]] = []
        for record in records:
            mapping = _METRIC_IDENTITY_MAP.get(record.get("canonical_metric"))
            if mapping is None or "evidence" not in record or record.get("quality_state") != "available":
                continue
            reconciled = dict(record)
            reconciled["canonical_metric"] = mapping["downstream_name"]
            reconciled["identity_reconciliation"] = {
                "reconciled_from": record["canonical_metric"],
                "version": mapping["version"],
                "reason": mapping["reason"],
            }
            extra.append(reconciled)
        result[ticker] = records + extra
    return result


# ==========================================================================
# Standalone PDF-cited balance-sheet identities (Altman/distress inputs)
# ==========================================================================
# Same "standalone, PDF-cited fact" pattern as share_basis_citations.jsonl and
# ebitda_component_citations.jsonl: financial_observations.py's retention allowlist
# (_CODES) has never included `current_liabilities` or `undistributed_earnings` for any
# ticker or period, so `observations.jsonl` holds no raw VCI observation for either and
# the observation-store cross-check used by qualification_citations.jsonl cannot apply.
# Verification is therefore the same as the EBITDA components': the cited evidence
# document must still hash-verify against manifest.json, the citation_id must be the
# deterministic hash of its own content, the metric must be in the supported set, the
# scope must be supported, and no two citations may conflict for the same
# (ticker, metric, reporting_period). Fails closed otherwise.

FINANCIAL_IDENTITY_RELATIVE = Path("data") / "official-evidence" / "financial_identity_citations.jsonl"
_FINANCIAL_IDENTITY_STATEMENT_FAMILIES = {
    "current_liabilities": "balance_sheet",
    "retained_earnings": "balance_sheet",
    "net_income": "income_statement",
    # Annual issuer statements can directly supply the complete, conservative
    # corporate-research input set.  These identities remain document-cited; they
    # are not inferred from provider payloads or quarterly aliases.
    "operating_cash_flow": "cash_flow",
    "cash_and_equivalents": "balance_sheet",
    "total_interest_bearing_debt": "balance_sheet",
    "shareholders_equity": "balance_sheet",
}
_SUPPORTED_FINANCIAL_IDENTITIES = frozenset(_FINANCIAL_IDENTITY_STATEMENT_FAMILIES)
_REQUIRED_FINANCIAL_IDENTITY_FIELDS = ("citation_id", "ticker", "metric", "reporting_frequency", "reporting_period",
    "statement_scope", "currency", "unit_scale", "value", "evidence_id")


def _valid_financial_extraction(citation: Mapping[str, Any]) -> bool:
    """Validate optional page/line extraction metadata without invalidating legacy rows.

    A direct annual line is retained as a document line item.  The only allowed
    calculation is an explicit sum of documented components from that same annual
    statement; it exists for interest-bearing debt where the report publishes
    short- and long-term borrowing separately.  No synthetic balance-sheet or
    cash-flow arithmetic is accepted.
    """
    extraction = citation.get("extraction")
    if extraction is None:
        return True
    if not isinstance(extraction, Mapping):
        return False
    method = extraction.get("method")
    pages = extraction.get("source_pages")
    labels = extraction.get("raw_labels")
    if method not in {"document_line_item", "document_line_item_sum"}:
        return False
    if not (isinstance(pages, list) and pages and all(isinstance(page, int) and page > 0 for page in pages)):
        return False
    if not (isinstance(labels, list) and labels and all(isinstance(label, str) and label.strip() for label in labels)):
        return False
    materialization = extraction.get("materialization")
    if materialization is not None:
        # A scan-derived candidate binds its OCR sidecar to the immutable PDF.
        # Old direct/manual rows deliberately remain valid without this optional
        # v1 metadata, but malformed new metadata can never be silently ignored.
        if not isinstance(materialization, Mapping):
            return False
        if method == "document_line_item":
            required = ("contract", "document_sha256", "page", "page_citation_id", "text_sha256",
                        "materialization_id", "verification")
            if not all(materialization.get(field) for field in required):
                return False
            if not (materialization.get("ocr_engine") or materialization.get("extraction_engine")):
                return False
            if materialization.get("verification") != "source_page_visual":
                return False
            if materialization.get("page") not in pages:
                return False
            if not (isinstance(materialization.get("document_sha256"), str)
                    and len(materialization["document_sha256"]) == 64):
                return False
        elif method == "document_line_item_sum":
            components_meta = materialization.get("components")
            if (materialization.get("contract") != "annual_financial_ocr_materialization/v1"
                    or materialization.get("verification") != "source_page_visual"
                    or not isinstance(components_meta, list) or len(components_meta) < 2):
                return False
            if not all(isinstance(item, Mapping) and item.get("page_citation_id") and item.get("materialization_id")
                       and item.get("document_sha256") for item in components_meta):
                return False
    if method == "document_line_item":
        return "components" not in extraction
    components = extraction.get("components")
    if not (isinstance(components, list) and len(components) >= 2):
        return False
    if not all(isinstance(component, Mapping) and isinstance(component.get("label"), str)
               and component["label"].strip() for component in components):
        return False
    try:
        total = sum(float(component["value"]) for component in components)
    except (KeyError, TypeError, ValueError):
        return False
    try:
        return total == float(citation["value"])
    except (TypeError, ValueError):
        return False


def financial_identity_is_stock_metric(metric: str) -> bool:
    """Whether a supported official financial identity describes a balance-sheet instant.

    This is deliberately sourced from the financial-identity authority rather than the
    canonical metric registry: the latter currently does not materialize every accepted
    identity (notably ``current_liabilities``).  It permits only the existing annual
    year-end -> Q4 alias; it never aliases flows or another quarter.
    """
    return _FINANCIAL_IDENTITY_STATEMENT_FAMILIES.get(str(metric)) == "balance_sheet"


def _load_financial_identity_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / FINANCIAL_IDENTITY_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def load_verified_financial_identities(runtime_root: Path) -> dict[str, Any]:
    """Read and verify data/official-evidence/financial_identity_citations.jsonl.

    Returns {"status": ..., "version": VERSION, "by_key": {(ticker, metric,
    reporting_period): verified_entry}, "rejected": [...]}. Fails closed per record.
    """
    evidence_by_id = _load_manifest(runtime_root)
    rows = _load_financial_identity_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if evidence_by_id is None or rows is None:
        return {"status": "unavailable", "version": VERSION, "by_key": {}, "rejected": rejected}

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_FINANCIAL_IDENTITY_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        grouped.setdefault((raw["ticker"], raw["metric"], raw["reporting_period"]), []).append(raw)

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            rejected.append({"key": key, "reason": "conflicting_citations"})
            continue
        citation = next(iter(unique_by_content.values()))

        identity = {"ticker": citation["ticker"], "metric": citation["metric"],
                    "reporting_period": citation["reporting_period"], "evidence_id": citation["evidence_id"],
                    "value": citation["value"]}
        # Old retained rows predate page/line metadata. New rows bind that metadata
        # into their identity so a cited extraction cannot later be substituted.
        if citation.get("extraction") is not None:
            identity["extraction"] = citation["extraction"]
        expected_id = _hash(identity)
        if citation["citation_id"] != expected_id:
            rejected.append({"key": key, "reason": "citation_id_not_deterministic"})
            continue
        if citation["metric"] not in _SUPPORTED_FINANCIAL_IDENTITIES:
            rejected.append({"key": key, "reason": "unsupported_metric"})
            continue
        if not _valid_financial_extraction(citation):
            rejected.append({"key": key, "reason": "invalid_extraction_metadata"})
            continue
        if citation["statement_scope"] not in _SUPPORTED_SCOPES:
            rejected.append({"key": key, "reason": "unsupported_scope"})
            continue
        evidence = evidence_by_id.get(citation["evidence_id"])
        if evidence is None:
            rejected.append({
                "key": key,
                "reason": "evidence_missing_or_hash_mismatch",
                "authority_status": ("declared_document_failed_verification"
                                     if _manifest_declares_evidence_id(runtime_root, citation["evidence_id"])
                                     else "document_not_registered_in_authority"),
            })
            continue
        extraction = citation.get("extraction") or {}
        materialization = extraction.get("materialization")
        if isinstance(materialization, Mapping):
            hashes = ([materialization.get("document_sha256")]
                      if extraction.get("method") != "document_line_item_sum"
                      else [item.get("document_sha256") for item in materialization.get("components", [])
                            if isinstance(item, Mapping)])
            if not hashes or any(value != evidence.get("sha256") for value in hashes):
                rejected.append({"key": key, "reason": "materialization_source_hash_mismatch"})
                continue
        if str(evidence.get("ticker") or "").upper() != str(citation["ticker"]).upper():
            rejected.append({"key": key, "reason": "evidence_ticker_mismatch"})
            continue

        by_key[key] = {
            "ticker": citation["ticker"], "metric": citation["metric"],
            "reporting_frequency": citation["reporting_frequency"], "reporting_period": citation["reporting_period"],
            "statement_scope": citation["statement_scope"], "currency": citation["currency"],
            "unit_scale": citation["unit_scale"], "value": citation["value"],
            "evidence_id": citation["evidence_id"], "citation_id": citation["citation_id"],
            "citation": citation.get("citation"), "qualification_version": VERSION,
            "verified_at": citation.get("verified_at"), "extraction": citation.get("extraction"),
            "document_sha256": evidence.get("sha256"),
        }

    return {"status": "available" if by_key else "unavailable", "version": VERSION, "by_key": by_key, "rejected": rejected}


def latest_financial_identity(by_key: Mapping[tuple[str, str, str], dict[str, Any]], ticker: str,
                               metric: str, frequency: str = "annual") -> dict[str, Any] | None:
    """The most recent verified entry for (ticker, metric, frequency), or None. Never
    falls back to a different metric."""
    candidates = [entry for (entry_ticker, entry_metric, _), entry in by_key.items()
                  if entry_ticker == ticker and entry_metric == metric and entry["reporting_frequency"] == frequency]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry["reporting_period"])
