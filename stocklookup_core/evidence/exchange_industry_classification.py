"""Exchange-provider ICB industry/sector classification snapshot.

WHAT THIS IS
    A reproducible, provenance-carrying snapshot of the ICB (Industry Classification
    Benchmark) sector label the exchange data vendor (VCI, via ``meta_sync.py``'s
    ``sync_exchange_industry``) assigns each ticker, retained in
    ``<runtime_root>/vn_stock.db``'s ``metadata`` table (``industry`` column, ICB level 2,
    ~19 groups). That sync is unconditional and market-wide ("2 requests for the whole
    market"), so its coverage is not limited to any hand-curated ticker list.

WHAT THIS IS NOT
    It is NOT an entity-profile registry and never carries an ``issuer_entity_type``
    directly -- it carries a governed *sector* label, and a fixed, versioned vocabulary
    (`ICB_SECTOR_ENTITY_HINT`) maps a sub-set of unambiguous labels to a classification
    hint. ``config/promoted_entity_classifications*.json`` remain the sole authority for
    ``issuer_entity_type``; this module only supplies one input to the reconciliation in
    ``entity_classification_scaleout.py``.

WHY "Dịch vụ tài chính" (Financial Services) HAS NO HINT
    ICB's "Financial Services" bucket lumps securities brokers, finance/leasing companies,
    fund managers, and financial holding companies together. Naming it as a specific
    `EntityClass` from the sector label alone would be exactly the "financial-sector
    absence/presence read as sufficient on its own" shortcut this milestone prohibits, so
    it is deliberately mapped to ``None`` here (informative-only) rather than guessed --
    `entity_classification_scaleout.py` only resolves it when independent statement-
    template or charter evidence positively names the specific subtype.

WHY THE OTHER 16 LABELS DO MAP TO CORPORATE
    Each remaining ICB level-2 label (Real Estate, Construction & Materials, Food &
    Beverage, ...) is a governed, third-party sector classification for a genuinely
    non-financial line of business -- this is "qualified industry/sector classification"
    positive evidence for INDUSTRIAL_CORPORATE, not an inference from the *absence* of a
    financial label. An unrecognized future label (schema drift at the vendor) maps to
    ``None`` rather than either bucket, so classification fails closed instead of
    silently mis-sorting a sector this module has never seen.

DETERMINISM
    ``records`` are fully sorted and derived only from the retained `metadata` table
    contents at query time; `records_fingerprint` is byte-stable across rebuilds on an
    unchanged table. Read-only: this module never writes to ``vn_stock.db``.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "EXCHANGE_INDUSTRY_CLASSIFICATION_SNAPSHOT"
SOURCE_ID = "vn_stock.db:metadata.industry"
SOURCE_PROVIDER = "VCI"
SOURCE_TAXONOMY = "ICB_LEVEL_2"

#: BANK and INSURANCE are unambiguous ICB level-2 labels under this taxonomy: no other
#: business is permitted to hold the corresponding license, so the label alone is
#: positive evidence of the specific `EntityClass`.
ICB_BANK_LABEL = "Ngân hàng"
ICB_INSURANCE_LABEL = "Bảo hiểm"

#: Ambiguous financial-sector label -- see module docstring. Deliberately maps to no
#: EntityClass hint; recorded separately so callers can distinguish "we know this is
#: financial-services-adjacent but not which subtype" from "we have no sector data at all".
ICB_AMBIGUOUS_FINANCIAL_LABEL = "Dịch vụ tài chính"

#: The 16 remaining retained ICB level-2 labels observed in the metadata table as of this
#: milestone (2026-09-01) that denote a genuinely non-financial line of business. Positive
#: evidence for EntityClass.CORPORATE when nothing else contradicts it.
ICB_NON_FINANCIAL_LABELS = frozenset({
    "Xây dựng và Vật liệu",             # Construction & Materials
    "Hàng & Dịch vụ Công nghiệp",        # Industrial Goods & Services
    "Thực phẩm và đồ uống",              # Food & Beverage
    "Điện, nước & xăng dầu khí đốt",     # Utilities
    "Bất động sản",                     # Real Estate
    "Tài nguyên Cơ bản",                # Basic Resources
    "Hàng cá nhân & Gia dụng",           # Personal & Household Goods
    "Hóa chất",                         # Chemicals
    "Y tế",                             # Health Care
    "Du lịch và Giải trí",              # Travel & Leisure
    "Truyền thông",                     # Media
    "Công nghệ Thông tin",              # Information Technology
    "Bán lẻ",                           # Retail
    "Ô tô và phụ tùng",                 # Automobiles & Parts
    "Dầu khí",                          # Oil & Gas
    "Viễn thông",                       # Telecommunications
})

HINT_CORPORATE = "CORPORATE"
HINT_BANK = "BANK"
HINT_INSURANCE = "INSURANCE"
HINT_AMBIGUOUS_FINANCIAL = "AMBIGUOUS_FINANCIAL_SECTOR"


class ExchangeIndustryClassificationError(ValueError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def resolve_industry_hint(icb_label: str | None) -> tuple[str | None, str]:
    """Map one retained ICB level-2 label to a classification hint + reason.

    Returns (hint, reason). `hint` is one of HINT_CORPORATE / HINT_BANK /
    HINT_INSURANCE / HINT_AMBIGUOUS_FINANCIAL / None (no label, or a label this
    module does not recognize -- fails closed rather than guessing).
    """
    label = str(icb_label).strip() if icb_label else ""
    if not label:
        return None, "NO_RETAINED_INDUSTRY_SYNC_RECORD"
    if label == ICB_BANK_LABEL:
        return HINT_BANK, f"icb_level_2_label={label!r} is the exchange's exclusive Banks sector"
    if label == ICB_INSURANCE_LABEL:
        return HINT_INSURANCE, f"icb_level_2_label={label!r} is the exchange's exclusive Insurance sector"
    if label == ICB_AMBIGUOUS_FINANCIAL_LABEL:
        return HINT_AMBIGUOUS_FINANCIAL, (
            f"icb_level_2_label={label!r} (Financial Services) spans securities/finance/holding "
            "subtypes; not sufficient on its own to name a specific EntityClass"
        )
    if label in ICB_NON_FINANCIAL_LABELS:
        return HINT_CORPORATE, f"icb_level_2_label={label!r} is a governed non-financial sector"
    return None, f"UNRECOGNIZED_ICB_LEVEL_2_LABEL:{label!r}"


def build_industry_classification_snapshot(
    runtime_root: str | Path,
    *,
    generated_at: str,
    session_identity: str,
) -> dict[str, Any]:
    """Build the complete snapshot from ``<runtime_root>/vn_stock.db``'s ``metadata`` table.

    Read-only: opens the database in SQLite URI read-only mode and never writes to it.
    """
    db_path = Path(runtime_root) / "vn_stock.db"
    if not db_path.is_file():
        raise ExchangeIndustryClassificationError(f"VN_STOCK_DB_NOT_FOUND:{db_path}")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        cur = conn.cursor()
        cur.execute("SELECT ticker, industry, updated FROM metadata ORDER BY ticker")
        rows = cur.fetchall()
    finally:
        conn.close()

    records: list[dict[str, Any]] = []
    for ticker, industry, updated in rows:
        clean_ticker = str(ticker).upper().strip()
        if not clean_ticker:
            continue
        hint, reason = resolve_industry_hint(industry)
        records.append({
            "ticker": clean_ticker,
            "icb_level_2_label": industry,
            "classification_hint": hint,
            "reason": reason,
            "row_updated_at": updated,
        })
    records.sort(key=lambda r: r["ticker"])

    hint_counts: dict[str, int] = {}
    label_counts: dict[str, int] = {}
    for record in records:
        key = record["classification_hint"] or "NONE"
        hint_counts[key] = hint_counts.get(key, 0) + 1
        label_key = record["icb_level_2_label"] or "NULL"
        label_counts[label_key] = label_counts.get(label_key, 0) + 1

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "authority_level": "generated_evidence",
        "authority_note": (
            "Generated exchange-provider sector-classification evidence, retained read-only "
            "from vn_stock.db's metadata table. This is NOT a manually verified issuer entity "
            "type and NOT an entity-profile registry -- config/ticker_entity_profiles.csv and "
            "the promoted_entity_classifications*.json manifests remain the sole authority for "
            "issuer_entity_type. See entity_classification_scaleout.py for how this evidence is "
            "reconciled against retained statement-template evidence before any promotion."
        ),
        "source_id": SOURCE_ID,
        "source_provider": SOURCE_PROVIDER,
        "source_taxonomy": SOURCE_TAXONOMY,
        "generated_at": generated_at,
        "session_identity": session_identity,
        "runtime_root": str(Path(runtime_root)),
        "record_count": len(records),
        "classification_hint_counts": dict(sorted(hint_counts.items())),
        "icb_level_2_label_counts": dict(sorted(label_counts.items())),
        "records": records,
    }
    payload["records_fingerprint"] = _fingerprint(records)
    return payload


def snapshot_path(evidence_dir: str | Path) -> Path:
    return Path(evidence_dir) / "exchange_industry_classification_snapshot.json"


def load_snapshot(path: str | Path) -> dict[str, Any] | None:
    """Read a previously materialized snapshot; None if absent or malformed (fail closed)."""
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SCHEMA_VERSION:
        return None
    if not isinstance(payload.get("records"), list):
        return None
    return dict(payload)


def industry_index(snapshot: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """ticker -> full record, for the records this snapshot actually carries."""
    if not isinstance(snapshot, Mapping):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for record in snapshot.get("records") or []:
        if not isinstance(record, Mapping):
            continue
        ticker = str(record.get("ticker") or "").strip().upper()
        if ticker:
            index[ticker] = dict(record)
    return index
