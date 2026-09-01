"""Focused tests for the shared monetary-basis contract."""
from __future__ import annotations

import monetary_basis_contract as basis_contract
import pytest


def test_unknown_unit_remains_unknown():
    basis = basis_contract.build_basis(currency=None, scale="ONE", basis_source="x")
    assert basis["basis_status"] == basis_contract.UNKNOWN
    basis = basis_contract.build_basis(currency="VND", scale=None, basis_source="x")
    assert basis["basis_status"] == basis_contract.UNKNOWN
    basis = basis_contract.build_basis(currency="unknown", scale="unknown", basis_source="x")
    assert basis["basis_status"] == basis_contract.UNKNOWN


@pytest.mark.parametrize("sentinel", ["None", "none", "NONE", "null", "NULL", "N/A", "n/a", "", "unknown", "UNKNOWN"])
def test_str_none_and_other_sentinels_cannot_become_a_known_basis(sentinel):
    # The exact accidental-stringification defect this module exists to close:
    # str(None) == "None" must never read back as a known currency or scale.
    assert basis_contract.known(sentinel) is False
    basis = basis_contract.build_basis(currency=sentinel, scale="ONE", basis_source="x")
    assert basis["basis_status"] == basis_contract.UNKNOWN
    basis = basis_contract.build_basis(currency="VND", scale=sentinel, basis_source="x")
    assert basis["basis_status"] == basis_contract.UNKNOWN


def test_agree_never_treats_a_stringified_none_as_a_shared_value():
    # Two rows each missing `normalized_candidate_unit.currency` (Python None, not the
    # string "unknown") must not "agree" on the fake shared value str(None) == "None".
    assert basis_contract.agree({None, None}) is None
    assert basis_contract.agree({None, "unknown"}) is None
    assert basis_contract.agree({"VND", None}) is None
    assert basis_contract.agree({"VND", "VND"}) == "VND"
    assert basis_contract.agree({"VND", "USD"}) is None


def test_explicit_vnd_normalization():
    basis = basis_contract.build_basis(
        currency="VND", scale=basis_contract.BASE_UNIT_SCALE_LABEL, multiplier_to_vnd=1,
        normalized_unit="VND", basis_status=basis_contract.QUALIFIED, basis_source="audited citation",
    )
    assert basis["currency"] == "VND"
    assert basis["native_scale"] == "units"
    assert basis["multiplier_to_vnd"] == 1
    assert basis["normalized_unit"] == "VND"
    assert basis["basis_status"] == basis_contract.QUALIFIED


def test_explicit_scaled_vnd_normalization():
    basis = basis_contract.build_basis(
        currency="VND", scale="THOUSAND", multiplier_to_vnd=1000, normalized_unit="VND",
        basis_source="kbs unit=1000 request contract",
    )
    assert basis["native_scale"] == "THOUSAND"
    assert basis["multiplier_to_vnd"] == 1000
    assert basis["normalized_unit"] == "VND"
    # Known native components but no explicit QUALIFIED claim -> the weaker, non-official tier.
    assert basis["basis_status"] == basis_contract.RESEARCH_CONTRACT_QUALIFIED


def test_market_cap_formula_preserves_native_and_normalized_identity():
    basis = basis_contract.build_basis(currency="VND", scale="THOUSAND", multiplier_to_vnd=1000,
                                       normalized_unit="VND", basis_source="x")
    assert basis_contract.normalize_value(22.2, basis) == pytest.approx(22200.0)
    # The native value itself is never mutated by normalization.
    assert basis["native_scale"] == "THOUSAND"


def test_compatible_normalized_bases_allow_comparison():
    revenue_basis = basis_contract.build_basis(currency="VND", scale="units", basis_source="x")
    cap_basis = basis_contract.build_basis(currency="VND", scale="units", basis_source="y")
    ok, reason = basis_contract.compatible(revenue_basis, cap_basis)
    assert ok is True
    assert reason is None


def test_different_native_scales_but_same_normalized_vnd_may_compare():
    thousand = basis_contract.build_basis(currency="VND", scale="THOUSAND", multiplier_to_vnd=1000,
                                          normalized_unit="VND", basis_source="a")
    base = basis_contract.build_basis(currency="VND", scale="units", multiplier_to_vnd=1,
                                      normalized_unit="VND", basis_source="b")
    ok, reason = basis_contract.compatible(thousand, base)
    assert ok is True
    assert reason is None
    normalized_thousand = basis_contract.normalize_value(5.0, thousand)
    normalized_base = basis_contract.normalize_value(5000.0, base)
    assert normalized_thousand == pytest.approx(normalized_base)


def test_unknown_multiplier_blocks_when_native_scales_differ():
    thousand_no_multiplier = basis_contract.build_basis(currency="VND", scale="THOUSAND", basis_source="a")
    base = basis_contract.build_basis(currency="VND", scale="units", basis_source="b")
    ok, reason = basis_contract.compatible(thousand_no_multiplier, base)
    assert ok is False
    assert reason == basis_contract.INCOMPATIBLE_REASON


def test_currency_mismatch_blocks():
    vnd = basis_contract.build_basis(currency="VND", scale="units", basis_source="a")
    usd = basis_contract.build_basis(currency="USD", scale="units", basis_source="b")
    ok, reason = basis_contract.compatible(vnd, usd)
    assert ok is False
    assert reason == basis_contract.INCOMPATIBLE_REASON


def test_unknown_basis_never_compatible_with_another_unknown_basis():
    a = basis_contract.build_basis(currency=None, scale=None, basis_source="a")
    b = basis_contract.build_basis(currency=None, scale=None, basis_source="b")
    ok, reason = basis_contract.compatible(a, b)
    assert ok is False
    assert reason == basis_contract.INCOMPATIBLE_REASON
    assert a["basis_status"] == b["basis_status"] == basis_contract.UNKNOWN


def test_no_value_magnitude_heuristic():
    # compatible() takes only basis envelopes, never the underlying value -- an
    # implausibly large or small number must not change the outcome either way.
    unknown = basis_contract.build_basis(currency="VND", scale=None, basis_source="x")
    known = basis_contract.build_basis(currency="VND", scale="units", basis_source="y")
    for _ in (1, 1_000_000_000_000, 0.0001):
        ok, _ = basis_contract.compatible(unknown, known)
        assert ok is False


def test_deterministic_identity():
    kwargs = dict(currency="VND", scale="THOUSAND", multiplier_to_vnd=1000,
                  normalized_unit="VND", basis_source="same inputs")
    first = basis_contract.build_basis(**kwargs)
    second = basis_contract.build_basis(**kwargs)
    assert first == second
