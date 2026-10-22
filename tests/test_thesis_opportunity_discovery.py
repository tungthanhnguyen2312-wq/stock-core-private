"""Thesis lanes reuse the comparison's findings; inspection order and authority stay unchanged."""
import copy
import json

import pytest

from tests.test_integrated_opportunity_comparison import source, request, SESSION, BIND
from tests.test_sector_relative_financial_resilience import scenario
from tests.test_valuation_balance_sheet_divergence import run
from stocklookup_core.decision import integrated_investment_decision_product as iid
from stocklookup_core.research import evidence_aware_candidate_comparison as comparison
import personal_investment_decision_action_center as action_center


def test_lane_membership_is_exactly_the_comparison_findings_and_source_is_unchanged():
    product = source()
    saved = copy.deepcopy(product)
    discovery = comparison.build_thesis_discovery(integrated_decision=product, bind_scenarios=BIND)
    assert product == saved
    profiles = comparison.build_integrated_comparison(
        {"research_session": SESSION, "tickers": sorted(product["records"])[:5]}, integrated_decision=product, bind_scenarios=BIND)["profiles"]
    for ticker, profile in profiles.items():
        expected = {lane for lane, (_text, rule) in comparison.THESIS_LANES.items() if rule(profile["finding_codes"])}
        listed = {lane for lane, row in discovery["lanes"].items() if ticker in [m["ticker"] for m in row["members"]]}
        assert listed == expected, ticker
    assert any(row["count"] for row in discovery["lanes"].values())
    assert discovery["denominator"]["issuers"] == len(product["records"])
    assert discovery["authority_boundary"]["is_actionable"] is False
    blob = json.dumps(discovery)
    assert "score" not in blob.lower().replace("no_composite_score_or_winner", "")


def test_members_follow_existing_priority_tier_then_ticker_and_exclusions_are_counted_not_listed():
    product = source()
    discovery = comparison.build_thesis_discovery(integrated_decision=product, bind_scenarios=BIND, excluded_tickers=frozenset({"T1"}))
    for row in discovery["lanes"].values():
        keys = [(comparison._TIER_ORDER.get(m["research_priority_tier"], 4), m["ticker"]) for m in row["members"]]
        assert keys == sorted(keys)
        assert "T1" not in [m["ticker"] for m in row["members"]]
    assert discovery["denominator"]["owner_excluded"] == 1


def test_identity_protects_discovery_delivery_and_markdown():
    discovery = comparison.build_thesis_discovery(integrated_decision=source(), bind_scenarios=BIND)
    text = comparison.thesis_discovery_markdown(discovery)
    assert "Thesis-based opportunity discovery" in text and "research lists" in text.lower()
    tampered = copy.deepcopy(discovery)
    lane = next(name for name, row in tampered["lanes"].items() if row["members"])
    tampered["lanes"][lane]["members"][0]["research_action_posture"] = "ENTER"
    with pytest.raises(ValueError, match="IDENTITY_INVALID"):
        comparison.thesis_discovery_markdown(tampered)
    with pytest.raises(ValueError, match="REQUIRES_VERIFIED"):
        comparison.build_thesis_discovery(integrated_decision=None, bind_scenarios=BIND)


def test_action_center_and_ai_delivery_are_opt_in_and_additive(monkeypatch):
    import ai_research_session_delivery as delivery
    from tests.test_ai_research_session_delivery import _operation
    product = source()
    plain = action_center.build_artifact(session=SESSION, requested_at="retained", integrated_decision_artifact=product)
    rich = action_center.build_artifact(session=SESSION, requested_at="retained", integrated_decision_artifact=product, include_thesis_discovery=True)
    assert {k: v for k, v in rich.items() if k not in {"thesis_opportunity_discovery", "artifact_identity", "artifact_sha256"}} == \
        {k: v for k, v in plain.items() if k not in {"artifact_identity", "artifact_sha256"}}
    assert "Thesis-based opportunity discovery" in action_center.markdown(rich)
    summary = action_center.public_console_summary(rich)
    assert set(summary["thesis_discovery_lane_counts"]) == set(comparison.THESIS_LANES)
    assert not any(t in json.dumps(summary) for t in product["records"])
    monkeypatch.setattr(delivery, "owner_focus_tickers", lambda: ())
    operation = _operation()
    operation["manifest"].update(market_session=SESSION, session_coherence={"session": SESSION})
    inputs = {"descriptive": {"records": {t: {} for t in product["records"]}}, "integrated_investment_decision_product": product}
    base = json.loads(delivery.build_delivery(operation, inputs)["primary"])
    shipped = json.loads(delivery.build_delivery(operation, inputs, include_thesis_discovery=True)["primary"])
    assert shipped.pop("thesis_opportunity_discovery") == json.loads(json.dumps(rich["thesis_opportunity_discovery"]))
    assert shipped == base


def test_cross_sector_pairs_get_own_cohort_positions_never_level_comparisons():
    product = source()
    profiles = comparison.build_integrated_comparison(request(), integrated_decision=product, bind_scenarios=BIND)["profiles"]
    assert profiles["T0"]["valuation_financial_research"]["valuation"]["peer_context"]["status"] == "READY_RESEARCH_ONLY"
    other = copy.deepcopy(profiles["T1"])
    valuation = other["valuation_financial_research"]["valuation"]
    valuation["cohort_id"] = "SECTOR:different"
    valuation["source_method"]["book_period"] = "2025-Q4"  # different basis: level comparison must fail closed
    pair = comparison._integrated_pair("T0", "X1", {"T0": profiles["T0"], "X1": other})
    assert "research_pb" not in pair["qualified_numerical_axes"]
    assert pair["exclusions"]["research_pb"].startswith("SAME_SECTOR")
    position = pair["qualified_numerical_axes"]["research_pb_own_sector_position"]
    assert position["left_percentile"] == profiles["T0"]["valuation_financial_research"]["valuation"]["peer_context"]["percentile"]
    assert position["right_cohort"] == "SECTOR:different" != position["left_cohort"]
    assert position["basis"].startswith("EACH_PERCENTILE_WITHIN_ITS_OWN")
    level_axes = [a for a in pair["qualified_numerical_axes"] if a != "research_pb_own_sector_position" and not a.endswith("_own_sector_relative_change")]
    assert pair["comparability"] == ("PARTIALLY_COMPARABLE" if level_axes else "RELATIVE_POSITION_ONLY")
    if not level_axes:
        assert all(row["basis"].startswith("EACH_CHANGE_VERSUS_ITS_OWN") for a, row in pair["qualified_numerical_axes"].items()
                   if a.endswith("_own_sector_relative_change"))
    pairs_md = comparison.integrated_comparison_markdown(
        comparison.build_integrated_comparison(request(), integrated_decision=product, bind_scenarios=BIND))
    assert "versus" in pairs_md
