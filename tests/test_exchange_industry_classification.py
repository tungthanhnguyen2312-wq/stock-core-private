"""Tests for exchange_industry_classification.py.

Hermetic: builds a temporary SQLite database shaped like the retained
``<runtime_root>/vn_stock.db``'s ``metadata`` table rather than depending on any
developer machine's actual runtime path, so these tests are portable across checkouts.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from exchange_industry_classification import (
    HINT_AMBIGUOUS_FINANCIAL,
    HINT_BANK,
    HINT_CORPORATE,
    HINT_INSURANCE,
    build_industry_classification_snapshot,
    industry_index,
    load_snapshot,
    resolve_industry_hint,
)


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    db_path = tmp_path / "vn_stock.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE metadata (ticker TEXT PRIMARY KEY, industry TEXT, updated TEXT)")
    conn.executemany(
        "INSERT INTO metadata (ticker, industry, updated) VALUES (?, ?, ?)",
        [
            ("BANKT", "Ngân hàng", "2026-08-14T00:00:00+07:00"),
            ("INST", "Bảo hiểm", "2026-08-14T00:00:00+07:00"),
            ("FINT", "Dịch vụ tài chính", "2026-08-14T00:00:00+07:00"),
            ("RETT", "Bán lẻ", "2026-08-14T00:00:00+07:00"),
            ("REALT", "Bất động sản", "2026-08-14T00:00:00+07:00"),
            ("NULLT", None, "2026-08-14T00:00:00+07:00"),
            ("nvlt", "Bất động sản", "2026-08-14T00:00:00+07:00"),  # lowercase ticker in source data
        ],
    )
    conn.commit()
    conn.close()
    return tmp_path


def test_build_snapshot_reads_metadata_table_read_only(runtime_root: Path):
    snapshot = build_industry_classification_snapshot(
        runtime_root, generated_at="2026-09-01T00:00:00+00:00", session_identity="test",
    )
    assert snapshot["record_count"] == 7
    index = industry_index(snapshot)
    assert index["BANKT"]["classification_hint"] == HINT_BANK
    assert index["INST"]["classification_hint"] == HINT_INSURANCE
    assert index["FINT"]["classification_hint"] == HINT_AMBIGUOUS_FINANCIAL
    assert index["RETT"]["classification_hint"] == HINT_CORPORATE
    assert index["NULLT"]["classification_hint"] is None
    assert index["NVLT"]["classification_hint"] == HINT_CORPORATE  # ticker normalized to upper


def test_build_snapshot_is_deterministic(runtime_root: Path):
    s1 = build_industry_classification_snapshot(runtime_root, generated_at="A", session_identity="s1")
    s2 = build_industry_classification_snapshot(runtime_root, generated_at="B", session_identity="s2")
    # generated_at/session_identity differ but records_fingerprint must not, since it is
    # derived only from the retained table contents.
    assert s1["records_fingerprint"] == s2["records_fingerprint"]


def test_missing_db_fails_closed(tmp_path: Path):
    with pytest.raises(Exception):
        build_industry_classification_snapshot(tmp_path, generated_at="A", session_identity="s")


def test_snapshot_round_trips_through_disk(runtime_root: Path, tmp_path: Path):
    snapshot = build_industry_classification_snapshot(runtime_root, generated_at="A", session_identity="s")
    out_path = tmp_path / "snapshot.json"
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    loaded = load_snapshot(out_path)
    assert loaded is not None
    assert loaded["record_count"] == snapshot["record_count"]


def test_load_snapshot_fails_closed_on_missing_or_malformed(tmp_path: Path):
    assert load_snapshot(tmp_path / "does_not_exist.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_snapshot(bad) is None


@pytest.mark.parametrize("label,expected_hint", [
    ("Ngân hàng", HINT_BANK),
    ("Bảo hiểm", HINT_INSURANCE),
    ("Dịch vụ tài chính", HINT_AMBIGUOUS_FINANCIAL),
    ("Xây dựng và Vật liệu", HINT_CORPORATE),
    ("Viễn thông", HINT_CORPORATE),
    (None, None),
    ("", None),
    ("A Sector Nobody Has Registered", None),
])
def test_resolve_industry_hint_vocabulary(label, expected_hint):
    hint, _reason = resolve_industry_hint(label)
    assert hint == expected_hint
