from __future__ import annotations

from dnse_closed_session_ohlc_representation import IDENTITY_TRANSFORMATION
from dnse_provider_native_closed_ohlc import (
    ADJUSTMENT_BASIS, FORMAL_PRICE_UNIT, RAW_AS_TRADED, closed_historical_session_gate,
    cross_provider_native_agreement, qualify_provider_native_closed_ohlc, scale_invariant_return,
)


def _anchor(*, retrieved_at: str = "2026-08-21T22:05:17+07:00", representation: str = IDENTITY_TRANSFORMATION) -> dict:
    return {"status": "UNIFORM_REPRESENTATION_READY", "instrument": "HPG", "session": "2026-08-20",
            "field_representation": {field: representation for field in ("open", "high", "low", "close")},
            "source_evidence": {"endpoint": "/price/ohlc", "retrieved_at": retrieved_at, "source_payload_identity": "test"}}


def test_provider_native_contract_requires_uniform_identity_and_closed_session() -> None:
    result = qualify_provider_native_closed_ohlc(_anchor())
    assert result["status"] == "QUALIFIED_FOR_BOUNDED_REPRESENTATION_SAFE_USES"
    assert result["unknown_semantics"] == {"formal_price_unit": FORMAL_PRICE_UNIT, "adjustment_basis": ADJUSTMENT_BASIS, "raw_as_traded": RAW_AS_TRADED}
    assert result["authority_effect"] == "NONE"
    assert "MONETARY_VALUATION" in result["prohibited_use_classes"]
    assert result == qualify_provider_native_closed_ohlc(_anchor())


def test_current_or_incomplete_and_historical_p3f9b_v1_mixed_representation_fail_closed() -> None:
    assert closed_historical_session_gate(_anchor(retrieved_at="2026-08-20T22:05:17+07:00"))["reason"] == "CURRENT_OR_INCOMPLETE_SESSION"
    mixed = _anchor()
    mixed["field_representation"]["close"] = "close_only_x1000"
    assert qualify_provider_native_closed_ohlc(mixed)["reason"] == "MIXED_OR_NON_IDENTITY_FIELD_REPRESENTATION"


def test_same_representation_return_is_scale_invariant_and_cross_representation_is_rejected() -> None:
    first = scale_invariant_return(previous=20.0, current=22.0, previous_representation="native", current_representation="native", basis_continuity="CONFIRMED_COMPATIBLE_INTERVAL")
    scaled = scale_invariant_return(previous=20000.0, current=22000.0, previous_representation="native", current_representation="native", basis_continuity="CONFIRMED_COMPATIBLE_INTERVAL")
    assert first["return"] == scaled["return"] == 0.1
    assert scale_invariant_return(previous=20, current=22, previous_representation="native", current_representation="other", basis_continuity="CONFIRMED_COMPATIBLE_INTERVAL")["reason"] == "CROSS_REPRESENTATION_RETURN"
    assert scale_invariant_return(previous=20, current=22, previous_representation="native", current_representation="native", basis_continuity="UNKNOWN")["reason"] == "BASIS_OR_CORPORATE_ACTION_CONTINUITY_UNCONFIRMED"


def test_twelve_field_provider_agreement_is_non_authoritative() -> None:
    agreement = cross_provider_native_agreement([{"raw_to_raw_numeric_equal": True} for _ in range(12)])
    assert agreement["status"] == "CROSS_PROVIDER_NATIVE_REPRESENTATION_AGREEMENT"
    assert agreement["authority_effect"] == "NONE"
