"""Tests for financial_v2_current_input_authority.py (CANONICAL_DAILY_FINANCIAL_V2_AND_
CURRENT_RESEARCH_ENRICHMENT_V1): the pinned, versioned Financial V2 input resolver.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import financial_v2_current_input_authority as auth

ROOT = Path(__file__).resolve().parents[1]


def test_resolve_against_real_repository_root_succeeds():
    """Real retained-evidence smoke test: the pinned directories exist in every checkout."""
    authority = auth.resolve(ROOT)
    assert authority.semantics_artifact_path.is_file()
    assert authority.semantics_facts_path.is_file()
    assert authority.feature_store_artifact_path.is_file()
    assert authority.feature_store_records_path.is_file()
    assert authority.classification_diagnostics_path.is_file()


def test_resolver_never_scans_filesystem_for_newest_folder():
    """Source-pattern guard: this module must remain a pinned, versioned pointer, never a
    glob/mtime-based 'pick the latest directory' resolver."""
    source = (ROOT / "financial_v2_current_input_authority.py").read_text(encoding="utf-8")
    assert ".glob(" not in source
    assert "iterdir(" not in source
    assert "st_mtime" not in source
    assert "getmtime" not in source


def test_resolve_fails_closed_when_evidence_missing(tmp_path):
    with pytest.raises(auth.FinancialV2InputAuthorityError, match="FINANCIAL_V2_INPUT_AUTHORITY_EVIDENCE_MISSING"):
        auth.resolve(tmp_path)


def test_resolve_is_deterministic_repeated_calls_identical():
    a1 = auth.resolve(ROOT)
    a2 = auth.resolve(ROOT)
    assert a1 == a2


def test_verify_identity_passes_on_exact_match():
    auth.verify_identity(label="x", observed="same", expected="same")  # does not raise


def test_verify_identity_fails_closed_on_drift():
    with pytest.raises(auth.FinancialV2InputAuthorityError, match="FINANCIAL_V2_INPUT_AUTHORITY_IDENTITY_DRIFT"):
        auth.verify_identity(label="semantics", observed="drifted", expected="expected-value")


def test_authority_manifest_names_no_specific_ticker():
    """No ticker hardcoding: the resolver's own manifest is universe-agnostic."""
    authority = auth.resolve(ROOT)
    manifest_text = " ".join(str(v) for v in authority.to_manifest().values())
    for ticker in ("HPG", "VCB", "SSI", "PNJ", "FPT"):
        assert ticker not in manifest_text
