"""Evidence-packet acceptance. Situations are generic; tickers are labels only."""
from __future__ import annotations

import pytest

import stocklookup_core.decision.human_ai_decision_evidence_packet as packet


SITUATIONS = {
    "HPG": {"fundamental_quality": "PRESENT", "technical_structure": "WEAK"},
    "PAN": {"earnings_flag": "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE", "valuation_use": "STRICT_VALUATION_QUARANTINED"},
    "POW": {"catalyst": "CAPITAL_INTENSIVE"},
    "SSI": {"entity_class": "securities", "valuation_status": "NOT_COMPARABLE"},
    "EVF": {"entity_class": "finance_company", "valuation_status": "NOT_COMPARABLE"},
    "FPT": {"share_basis": "SHARE_BASIS_MISMATCH"},
    "NVL": {"corporate_action": "DILUTION_POSSIBLE", "ex_date": None},
    "PNJ": {"earnings_flag": "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE", "provision": "PRESENT"},
    "QNS": {"technical_structure": "UPTREND"},
}


def test_feature_vector_keeps_measurements_and_refuses_a_scalar():
    built = packet.feature_vector({"rsi": 28, "breadth": "MIXED", "valuation_status": "UNKNOWN"})
    assert built["collapsed_scalar"] is None
    assert list(built["measurements"]) == ["breadth", "rsi", "valuation_status"]
    with pytest.raises(ValueError):
        packet.feature_vector({"value": 7})
    with pytest.raises(ValueError):
        packet.feature_vector({"buy_score": 80, "rsi": 28})


def test_analogue_order_is_preserved_and_incomplete_disclosure_is_ineligible():
    built = packet.build_packet(ticker="HPG", analogues=[
        {"matching_method": "SAME_REGIME", "evidence_tier": "RECONSTRUCTED_RESEARCH", "sample_size": 5, "regime_similarity": "MIXED", "missing_dimensions": ["flow"], "forward_outcome": -0.02},
        {"matching_method": "SAME_REGIME", "evidence_tier": "RECONSTRUCTED_RESEARCH", "sample_size": 5, "regime_similarity": "MIXED", "missing_dimensions": ["flow"], "forward_outcome": 0.20},
        {"forward_outcome": 0.90},
    ])
    analogues = built["sections"]["history"]["analogues"]
    assert [item["forward_outcome"] for item in analogues] == [-0.02, 0.20, 0.90]
    assert analogues[0]["eligible"] is True
    assert analogues[2]["eligible"] is False
    assert analogues[2]["status"] == "INCOMPLETE"
    assert built["sections"]["history"]["cherry_pick"] is False


def test_capital_decision_stays_with_the_human():
    built = packet.build_packet(ticker="PAN", capital_decision="BUY", ai_narration="Disposal may distort trailing earnings.")
    assert built["capital_decision"] == {"owner": "HUMAN", "status": "NOT_DELEGATED", "value": None}
    assert built["ai_narration"]["authority"] == "NARRATION_ONLY"
    assert built["buy_score"] is None
    assert built["probability"] is None
    assert built["target_price"] is None
    assert built["is_actionable"] is False


def test_missing_section_blocks_only_its_own_fields():
    built = packet.build_packet(ticker="PNJ", sections={
        "stock": {"earnings_flag": {"claim": {"present": True, "warning": True}, "value": "NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE"}},
    })
    assert built["sections"]["stock"]["fields"]["earnings_flag"]["claim"] == "DATA_WARNING"
    assert built["sections"]["market"]["status"] == "MISSING"
    assert built["sections"]["tactical"]["status"] == "MISSING"
    assert built["canonical_packet_identity"] is None


def test_nine_situations_use_the_same_builder():
    identities = set()
    for ticker, fields in SITUATIONS.items():
        built = packet.build_packet(
            ticker=ticker,
            sections={"stock": fields, "uncertainty": {"gap": None}},
            feature_measurements=fields,
            canonical_packet_identity="current_research_decision_packet:pointer",
        )
        assert built["ticker"] == ticker
        assert built["buy_score"] is None
        assert built["feature_vector"]["collapsed_scalar"] is None
        assert built["sections"]["uncertainty"]["fields"]["gap"]["claim"] == "MISSING"
        identities.add(built["packet_identity"])
    assert len(identities) == len(SITUATIONS)


def test_rebuild_identity_is_stable():
    kwargs = dict(ticker="QNS", sections={"tactical": {"structure": "UPTREND"}}, feature_measurements={"structure": "UPTREND"})
    assert packet.build_packet(**kwargs)["packet_identity"] == packet.build_packet(**kwargs)["packet_identity"]
