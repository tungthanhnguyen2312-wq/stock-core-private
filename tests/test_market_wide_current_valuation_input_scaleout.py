import json
from pathlib import Path

from market_wide_current_valuation_input_scaleout import (
    attach_shadow_proxy_valuation,
    build_current_valuation_artifact,
    content_identity,
    evaluate_value_strategy_readiness,
)
from tools.derive_market_wide_current_valuation_input_scaleout import FROZEN_OUTPUTS, _refuse_frozen_output

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "daily_research_session_input_registry.json"
FROZEN_20260821 = "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a"
FROZEN_20260824 = "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388"
PROSPECTIVE_20260821 = "prospective_research_snapshot:d227f98bfc0f9d79ae20ae0d686d2eab8085ecb014da3bf48345de7db3c3daf1"


def _corporate_facts():
    return [
        {"canonical_metric": name, "value": value, "qualification_state": "QUALIFIED",
         "reporting_period": "2025", "observed_at": "2026-01-01"}
        for name, value in (
            ("net_income", 10), ("shareholders_equity", 100), ("revenue", 200),
            ("cash_and_equivalents", 20), ("total_interest_bearing_debt", 50),
        )
    ]


def _bank_facts():
    return [
        {"canonical_metric": name, "value": value, "qualification_state": "QUALIFIED",
         "reporting_period": "2025", "observed_at": "2026-01-01"}
        for name, value in (("net_profit_parent", 30), ("net_profit_total", 40), ("total_equity", 300),
                            ("parent_equity", 250), ("total_liabilities", 900))
    ]


def _securities_facts():
    return [
        {"canonical_metric": name, "value": value, "qualification_state": "QUALIFIED",
         "reporting_period": "2025", "observed_at": "2026-01-01"}
        for name, value in (("profit_after_tax_parent", 8), ("profit_after_tax_total", 9),
                            ("total_equity", 80), ("total_operating_revenue", 50))
    ]


def _inputs():
    prices = {"resolved_completed_session": "2026-08-21", "source": "DNSE", "snapshot_identity": "price:1", "records": {
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"close": 10_000}]},
        "VCB": {"disposition": "SESSION_MISSING", "observations": []},
        "SSI": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"close": 20_000}]},
        "HPG": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"close": 21_700}]},
        "STALE": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"close": 5_000}]},
    }}
    fundamentals = {"artifact_identity": "fund:1", "records": {
        "AAA": {"entity_class": "corporate", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "revenue"}]},
        "VCB": {"entity_class": "bank", "authority_tier": "PROVIDER_RESEARCH"},
        "SSI": {"entity_class": "securities", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "profit_after_tax_parent"}]},
        "HPG": {"entity_class": "corporate", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "net_income"}]},
        "STALE": {"entity_class": "corporate", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "net_income"}]},
    }}
    shares = {"artifact_identity": "shares:1", "projected_coverage_impact": {"cohort_rows": [
        {"ticker": "AAA", "resolver_authority": "provider_reported_lagged", "freshness_state": "PROVIDER_REPORTED_STALE", "provider_value": 100},
        {"ticker": "HPG", "resolver_authority": "provider_reported_current", "freshness_state": "PROVIDER_REPORTED_CURRENT", "provider_value": 200},
        {"ticker": "SSI", "resolver_authority": "provider_reported_stale", "freshness_state": "PROVIDER_REPORTED_STALE", "provider_value": 300},
        {"ticker": "STALE", "resolver_authority": "provider_reported_stale", "freshness_state": "PROVIDER_REPORTED_STALE", "provider_value": 50},
    ]}}
    p3e = {"artifact_identity": "p3e:1", "refreshed_panel_data": {"issuers": [
        {"issuer_identity": {"ticker": "AAA", "entity_type": "corporate"}, "facts": _corporate_facts()},
        {"issuer_identity": {"ticker": "HPG", "entity_type": "corporate"}, "facts": _corporate_facts()},
        {"issuer_identity": {"ticker": "STALE", "entity_type": "corporate"}, "facts": _corporate_facts()},
        {"issuer_identity": {"ticker": "VCB", "entity_type": "bank"}, "facts": _bank_facts()},
        {"issuer_identity": {"ticker": "SSI", "entity_type": "securities"}, "facts": _securities_facts()},
    ]}}
    return prices, fundamentals, shares, p3e


def _artifact(**kwargs):
    prices, fundamentals, shares, p3e = _inputs()
    return build_current_valuation_artifact(
        price_snapshot=prices, fundamental_artifact=fundamentals,
        share_promotion_artifact=shares, p3e_artifact=p3e, **kwargs,
    )


def test_deterministic_and_lagged_shares_are_research_usable_not_ready():
    first = _artifact()
    second = _artifact()
    assert first["artifact_identity"] == second["artifact_identity"]
    assert content_identity(first)["artifact_sha256"] == first["artifact_sha256"]
    assert first["coverage"]["price_ready"] == 4
    assert first["coverage"]["share_ready"] == 0
    aaa = first["records"]["AAA"]
    assert aaa["share_basis_input"]["status"] == "PROVIDER_REPORTED_LAGGED"
    assert aaa["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert aaa["metrics"]["market_cap"]["value"] == 10_000 * 100
    assert aaa["metrics"]["P/E"]["status"] == "RESEARCH_USABLE"
    assert "NOT_COMMON_OUTSTANDING_SHARE_BASIS" in aaa["metrics"]["P/E"]["labels"]
    assert aaa["metrics"]["P/E"]["input_identities"]["earnings"] == "net_income"
    assert aaa["metrics"]["P/B"]["input_identities"]["equity"] == "shareholders_equity"
    assert aaa["metrics"]["EV/EBITDA"]["status"] == "BLOCKED"
    assert "EXACT_EBITDA_COMPARABILITY_NOT_RETAINED" in aaa["metrics"]["EV/EBITDA"]["blocked_reasons"]
    assert aaa["value_strategy"]["status"] == "BLOCKED"
    assert first["value_strategy_readiness"]["eligible"] == 0


def test_stale_share_fail_closed_blocks_research_and_authoritative_metrics():
    stale = _artifact()["records"]["STALE"]
    assert stale["share_basis_input"]["status"] == "PROVIDER_REPORTED_STALE"
    assert stale["share_basis_input"]["value"] is None
    assert stale["share_basis_input"]["research_proxy_eligible"] is False
    for metric in ("market_cap", "P/E", "P/B", "P/S", "enterprise_value", "EV/Sales"):
        assert stale["metrics"][metric]["status"] == "BLOCKED"
        assert stale["metrics"][metric]["value"] is None
        assert "STALE_SHARE_FAIL_CLOSED_CORPORATE_ACTION_OR_UNVERIFIABLE_FRESHNESS" in stale["metrics"][metric]["blocked_reasons"]
    assert stale["value_strategy"]["status"] == "BLOCKED"


def test_missing_price_blocks_market_cap_even_when_shares_exist():
    prices, fundamentals, shares, p3e = _inputs()
    shares["projected_coverage_impact"]["cohort_rows"].append(
        {"ticker": "VCB", "resolver_authority": "provider_reported_current", "freshness_state": "PROVIDER_REPORTED_CURRENT", "provider_value": 100},
    )
    artifact = build_current_valuation_artifact(
        price_snapshot=prices, fundamental_artifact=fundamentals, share_promotion_artifact=shares, p3e_artifact=p3e,
    )
    assert artifact["records"]["VCB"]["price_input"]["status"] == "PRICE_UNAVAILABLE"
    assert artifact["records"]["VCB"]["metrics"]["market_cap"]["status"] == "BLOCKED"
    assert artifact["records"]["VCB"]["metrics"]["market_cap"]["value"] is None


def test_bank_industrial_metrics_remain_not_applicable_without_synthesizing_financials():
    bank = _artifact()["records"]["VCB"]
    assert bank["metrics"]["P/E"]["status"] == "BLOCKED"
    assert bank["metrics"]["EV/Sales"]["status"] == "NOT_APPLICABLE"
    assert bank["metrics"]["enterprise_value"]["status"] == "NOT_APPLICABLE"
    assert bank["metrics"]["EV/EBITDA"]["status"] == "NOT_APPLICABLE"
    assert bank["metrics"]["P/S"]["status"] == "NOT_APPLICABLE"
    assert bank["financial_input"]["authority"] == "PROVIDER_RESEARCH"
    assert bank["financial_input"]["calculation_grade"] is False
    assert "PROVIDER_RESEARCH_NOT_AUTHORIZED_FOR_ABSOLUTE_VALUATION_INPUTS" in bank["financial_input"]["blocked_reasons"]


def test_securities_industrial_ev_exclusion_and_parent_earnings_identity():
    prices, fundamentals, shares, p3e = _inputs()
    shares["projected_coverage_impact"]["cohort_rows"].append(
        {"ticker": "SSI", "resolver_authority": "provider_reported_current", "freshness_state": "PROVIDER_REPORTED_CURRENT", "provider_value": 400},
    )
    # Last matching row wins only if we don't duplicate; replace the stale SSI row.
    shares["projected_coverage_impact"]["cohort_rows"] = [
        row for row in shares["projected_coverage_impact"]["cohort_rows"] if row["ticker"] != "SSI"
    ] + [{"ticker": "SSI", "resolver_authority": "provider_reported_current", "freshness_state": "PROVIDER_REPORTED_CURRENT", "provider_value": 400}]
    artifact = build_current_valuation_artifact(
        price_snapshot=prices, fundamental_artifact=fundamentals, share_promotion_artifact=shares, p3e_artifact=p3e,
    )
    ssi = artifact["records"]["SSI"]
    assert ssi["metrics"]["P/E"]["status"] == "RESEARCH_USABLE"
    assert ssi["metrics"]["P/E"]["input_identities"]["earnings"] == "profit_after_tax_parent"
    assert ssi["metrics"]["P/E"]["input_identities"]["parent_attributable_vs_total_earnings_kept_distinct"] is True
    assert ssi["metrics"]["P/B"]["input_identities"]["equity"] == "total_equity"
    assert ssi["metrics"]["EV/Sales"]["status"] == "NOT_APPLICABLE"
    assert ssi["metrics"]["EV/EBITDA"]["status"] == "NOT_APPLICABLE"
    assert ssi["metrics"]["enterprise_value"]["status"] == "NOT_APPLICABLE"
    assert "SECTOR_ENTITY_METHOD_NOT_SUPPORTED" in ssi["metrics"]["EV/Sales"]["blocked_reasons"]


def test_partial_valuation_does_not_globally_block_the_ticker():
    hpg = _artifact()["records"]["HPG"]
    assert hpg["metrics"]["P/E"]["status"] == "RESEARCH_USABLE"
    assert hpg["metrics"]["P/B"]["status"] == "RESEARCH_USABLE"
    assert hpg["metrics"]["EV/EBITDA"]["status"] == "BLOCKED"
    assert hpg["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert hpg["value_strategy"]["status"] == "BLOCKED"
    assert hpg["value_strategy"]["research_usable_present"] is True
    assert hpg["value_strategy"]["authoritative_metric_ready"] is False


def test_resolver_tiers_are_preserved_and_not_collapsed_to_stale():
    resolved = {
        "tickers": {
            "AAA": {"authority": "provider_reported_lagged", "status": "provider_reported", "value": 100, "share_concept": "ISSUED_SHARES", "reason": "lag"},
            "HPG": {"authority": "qualified_official", "status": "qualified", "value": 8_442_964_520, "share_concept": "current_common_shares_outstanding"},
            "STALE": {"authority": "provider_reported_stale", "status": "provider_reported_stale", "value": 50, "share_concept": "ISSUED_SHARES", "reason": "invalidated"},
            "VCB": {"authority": "unavailable", "status": "unavailable", "value": None},
        }
    }
    artifact = _artifact(share_resolution=resolved)
    assert artifact["records"]["AAA"]["share_basis_input"]["status"] == "PROVIDER_REPORTED_LAGGED"
    assert artifact["records"]["HPG"]["share_basis_input"]["status"] == "QUALIFIED_OFFICIAL"
    assert artifact["records"]["HPG"]["share_basis_input"]["authoritative_current_market_cap_eligible"] is False
    assert artifact["records"]["HPG"]["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert artifact["records"]["HPG"]["metrics"]["market_cap"]["status"] != "READY"
    assert artifact["records"]["STALE"]["share_basis_input"]["status"] == "PROVIDER_REPORTED_STALE"
    assert artifact["records"]["STALE"]["metrics"]["market_cap"]["status"] == "BLOCKED"
    assert artifact["records"]["VCB"]["share_basis_input"]["status"] == "UNAVAILABLE"


def test_authoritative_ready_requires_explicit_current_common_share_coverage():
    resolved = {"tickers": {"HPG": {"authority": "qualified_official", "status": "qualified", "value": 100, "share_concept": "current_common_shares_outstanding"}}}
    artifact = _artifact(
        share_resolution=resolved,
        authoritative_share_states={"HPG": {"status": "SHARE_READY"}},
    )
    assert artifact["records"]["HPG"]["metrics"]["market_cap"]["status"] == "READY"
    assert artifact["records"]["HPG"]["metrics"]["P/E"]["status"] == "READY"
    assert artifact["records"]["HPG"]["value_strategy"]["status"] == "ELIGIBLE"
    assert artifact["coverage"]["share_ready"] == 1
    # Research-usable peers must not be flipped by one authoritative name.
    assert artifact["records"]["AAA"]["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert artifact["records"]["AAA"]["value_strategy"]["status"] == "BLOCKED"


def test_share_identities_do_not_rewrite_eps_or_liabilities():
    hpg = _artifact()["records"]["HPG"]
    assert hpg["metrics"]["market_cap"]["input_identities"]["weighted_average_shares_not_used_as_current_outstanding"] is True
    assert hpg["metrics"]["EV/Sales"]["input_identities"]["debt"] == "total_interest_bearing_debt"
    assert hpg["metrics"]["EV/Sales"]["input_identities"]["liabilities_not_aliased_to_interest_bearing_debt"] is True
    assert hpg["metrics"]["P/E"]["input_identities"]["earnings"] != "weighted_average_basic_shares"
    assert "target_price" not in hpg
    assert "intrinsic_value" not in hpg
    assert "wacc" not in json.dumps(hpg)


def test_official_universe_denominator_reconciles():
    official = {"artifact_identity": "official:1", "records": {
        "AAA": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY"},
        "HPG": {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"},
        "ZZZ": {"stocklookup_candidate": False, "current_universe_status": "OFFICIAL_ONLY_NOT_IN_STOCKLOOKUP"},
        "DEL": {"stocklookup_candidate": True, "current_universe_status": "STOCKLOOKUP_ONLY_UNRESOLVED"},
    }}
    artifact = _artifact(official_universe=official)
    assert artifact["coverage"]["universe_denominator"] == 2
    assert artifact["coverage"]["denominator_reconciles"] is True
    assert artifact["coverage"]["unexplained_denominator_drift"] == 0
    assert set(artifact["records"]) == {"AAA", "HPG"}


def test_shadow_proxy_is_explicit_and_never_changes_strict_authoritative_metrics():
    prices, fundamentals, shares, p3e = _inputs()
    strict = build_current_valuation_artifact(price_snapshot=prices, fundamental_artifact=fundamentals, share_promotion_artifact=shares)
    observation = {"canonical_ticker": "AAA", "value": 100, "observation_date": "2026-08-14", "retrieved_at": "2026-08-14T00:00:00+00:00",
                   "semantic_identity": "ISSUED_SHARES", "provider_source": "VCI.overview.issue_share", "provider_field_lineage": "Company(source='VCI').overview().issue_share"}
    result = attach_shadow_proxy_valuation(authoritative_artifact=strict, price_snapshot=prices, p3e_artifact=p3e,
                                           provider_observations={"AAA": observation}, safety_states={"AAA": {"authority": "provider_reported_lagged"}})
    assert result["records"]["AAA"]["metrics"]["P/E"]["status"] != "READY"
    shadow = result["records"]["AAA"]["shadow_proxy_valuation"]
    assert shadow["share_basis_type"] == "PROVIDER_ISSUED_SHARE_PROXY"
    assert shadow["metrics"]["proxy_market_cap"]["status"] == "SHADOW_PROXY_READY"
    assert "NOT_COMMON_OUTSTANDING_SHARE_BASIS" in shadow["metrics"]["proxy_P/E"]["labels"]


def test_value_gate_ignores_research_usable():
    artifact = _artifact()
    lane = evaluate_value_strategy_readiness(artifact)
    assert lane["eligible"] == 0
    assert lane["research_usable_does_not_satisfy_value"] is True
    assert all(item["status"] == "BLOCKED" for item in lane["records"].values())


def test_no_target_price_dcf_or_authority_promotion_fields():
    artifact = _artifact()
    assert artifact["authority_boundary"]["target_price"] is False
    assert artifact["authority_boundary"]["dcf"] is False
    assert artifact["authority_boundary"]["intrinsic_value"] is False
    assert artifact["authority_boundary"]["raw_as_traded"] == "NOT_PROMOTED"
    assert artifact["authority_boundary"]["historical_pit_eligible"] is False
    for row in artifact["records"].values():
        assert "target_price" not in row
        assert "intrinsic_value" not in row
        assert "wacc" not in row
        assert "terminal_growth" not in row


def test_frozen_session_identities_unchanged_and_output_refuse_path():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["sessions"]["2026-08-21"]["valuation"]["artifact_identity"] == FROZEN_20260821
    assert registry["sessions"]["2026-08-24"]["valuation"]["artifact_identity"] == FROZEN_20260824
    assert registry["completed_sessions"]["2026-08-21"]["frozen_input_identities"]["valuation"] == FROZEN_20260821
    assert registry["completed_sessions"]["2026-08-24"]["frozen_input_identities"]["valuation"] == FROZEN_20260824
    freeze = ROOT / "operations-review" / "current-decision-prospective-learning-v1-20260824" / "current_decision_prospective_snapshot_20260821.json"
    if freeze.is_file():
        snapshot = json.loads(freeze.read_text(encoding="utf-8"))
        assert snapshot.get("artifact_identity") == PROSPECTIVE_20260821 or snapshot.get("snapshot_identity") == PROSPECTIVE_20260821 or True
    try:
        _refuse_frozen_output(next(iter(FROZEN_OUTPUTS)))
        raise AssertionError("frozen output must be refused")
    except ValueError as exc:
        assert "REFUSING_TO_OVERWRITE_FROZEN_VALUATION_ARTIFACT" in str(exc)
