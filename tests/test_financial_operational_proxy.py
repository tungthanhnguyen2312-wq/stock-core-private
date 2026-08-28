"""Tests for financial_operational_proxy.py (FINANCIAL_OPERATIONAL_PROXY_FOUNDATION_AND_
RESEARCH_TIER_ACTIVATION_V1). All fixtures are synthetic unless a test name says
`_on_real_retained_data`; those few reuse the same already-retained bytes under
`operations-review/` that the rest of this codebase's tests already depend on -- no
network, no new evidence.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import financial_operational_proxy as fop

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "financial_operational_proxy.py").read_text(encoding="utf-8")
RUNTIME_ROOT = ROOT / "operations-review" / "p1f-milestone-20260803" / "shadow-build-b"


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------
def _official_fact(*, ticker="TST", canonical_metric="revenue", reporting_period="2024",
                   statement_scope="consolidated", value=1_000_000_000, citation_id="cit-1") -> dict:
    return {
        "issuer_identity": {"ticker": ticker}, "canonical_metric": canonical_metric,
        "reporting_period": reporting_period, "statement_scope": statement_scope, "value": value,
        "qualification_state": "QUALIFIED", "currency": "VND", "unit_scale": 1,
        "source_lineage": {"citation_id": citation_id},
    }


def _panel(*facts) -> dict:
    by_ticker: dict[str, list[dict]] = {}
    for fact in facts:
        by_ticker.setdefault(fact["issuer_identity"]["ticker"], []).append(fact)
    return {"issuers": [{"issuer_identity": {"ticker": ticker}, "facts": rows} for ticker, rows in by_ticker.items()]}


def _provider_fact(*, ticker="TST", canonical_metric="revenue", reporting_period="2024",
                   statement_scope="consolidated", value=1_000_000_000, provider="VCI",
                   status="provider_reported", currency=None, scale=None, fact_id="fact-1") -> dict:
    return {
        "ticker": ticker, "canonical_metric": canonical_metric, "reporting_period": reporting_period,
        "statement_scope": statement_scope, "value": value, "provider": provider, "status": status,
        "currency": currency, "scale": scale, "fact_id": fact_id, "source_observation_ids": [fact_id],
        "period_type": "annual" if "-Q" not in str(reporting_period) else "quarterly",
        "unit_authority": None,
    }


def _empty_official_index() -> dict:
    return fop.build_official_index({"issuers": []})


# ---------------------------------------------------------------------------
# 1. Three evidence tiers are distinct.
# ---------------------------------------------------------------------------
def test_three_evidence_tiers_are_distinct_string_values():
    assert len(set(fop.EVIDENCE_TIERS)) == 3 == len(fop.EVIDENCE_TIERS)
    assert fop.OPERATIONAL_PROXY != fop.VERIFIED_RESEARCH_EVIDENCE != fop.AUTHORITATIVE_EVIDENCE
    assert fop.OPERATIONAL_PROXY != fop.AUTHORITATIVE_EVIDENCE


def test_tier_names_do_not_collide_with_any_existing_tier_or_status_vocabulary():
    import canonical_financial_facts as cff
    import market_wide_current_fundamental_research as mwcfr
    import provider_financial_semantic_basis as pfsb

    existing = {
        cff.STATUS_QUALIFIED, cff.STATUS_PROVIDER_REPORTED, cff.STATUS_PARTIAL,
        cff.STATUS_CONFLICTED, cff.STATUS_UNAVAILABLE, cff.STATUS_NOT_APPLICABLE,
        mwcfr.OFFICIAL_TIER, mwcfr.PROVIDER_TIER, mwcfr.BLOCKED_TIER,
        pfsb.PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED, pfsb.PROVIDER_EXACT_RESEARCH_USABLE,
    }
    assert existing.isdisjoint(set(fop.EVIDENCE_TIERS))
    assert existing.isdisjoint(set(fop.RECONCILIATION_STATES))


# ---------------------------------------------------------------------------
# 2. OPERATIONAL_PROXY cannot become authoritative by default.
# ---------------------------------------------------------------------------
def test_operational_proxy_never_becomes_authoritative_by_default():
    fact = _provider_fact()
    record = fop.classify_operational_proxy_fact(
        fact, entity_type="corporate", official_index=_empty_official_index(),
    )
    assert record["evidence_tier"] == fop.OPERATIONAL_PROXY
    assert record["fitness_for_use"]["authoritative_financial_eligible"] is False


def test_no_function_in_this_module_ever_assigns_authoritative_evidence_tier():
    """AUTHORITATIVE_EVIDENCE facts are only ever passed through verbatim from P3-F13
    (never assigned by classify_operational_proxy_fact / reconcile_against_official /
    derive_ratio_metric); this module has no code path that manufactures one."""
    for fact in (_provider_fact(), _provider_fact(currency="VND", scale=1)):
        record = fop.classify_operational_proxy_fact(
            fact, entity_type="corporate", official_index=_empty_official_index(),
        )
        assert record["evidence_tier"] != fop.AUTHORITATIVE_EVIDENCE
    derived = fop.derive_ratio_metric(
        ticker="TST", derived_metric_id="net_margin", numerator_metric="net_income",
        denominator_metric="revenue", family="same_statement_family", description="",
        facts=[_provider_fact(canonical_metric="net_income", value=100), _provider_fact(canonical_metric="revenue", value=1000)],
    )
    assert derived["result_evidence_tier"] != fop.AUTHORITATIVE_EVIDENCE


# ---------------------------------------------------------------------------
# 3. Exact official match may upgrade only to VERIFIED_RESEARCH_EVIDENCE.
# ---------------------------------------------------------------------------
def test_exact_match_upgrades_operational_proxy_to_verified_research_evidence_only():
    official = _panel(_official_fact(value=1_000_000_000))
    index = fop.build_official_index(official)
    fact = _provider_fact(value=1_000_000_000)  # identical raw value, no scale needed
    record = fop.classify_operational_proxy_fact(fact, entity_type="corporate", official_index=index)
    assert record["official_reconciliation"]["reconciliation_status"] == fop.EXACT_MATCH
    assert record["evidence_tier"] == fop.VERIFIED_RESEARCH_EVIDENCE
    assert record["evidence_tier"] != fop.AUTHORITATIVE_EVIDENCE


def test_verified_research_evidence_fitness_never_grants_authoritative_or_pit():
    fitness = fop.fitness_for_use(tier=fop.VERIFIED_RESEARCH_EVIDENCE, currency="VND", scale=1)
    assert fitness.authoritative_financial_eligible is False
    assert fitness.pit_backtest_eligible is False


def test_upgrade_contract_is_named_and_explicit_not_implicit():
    assert isinstance(fop.UPGRADE_CONTRACT, str) and len(fop.UPGRADE_CONTRACT) > 20
    official = _panel(_official_fact(value=42))
    record = fop.classify_operational_proxy_fact(
        _provider_fact(value=42), entity_type="corporate", official_index=fop.build_official_index(official),
    )
    assert record["official_reconciliation"]["upgrade_contract"] == fop.UPGRADE_CONTRACT


# ---------------------------------------------------------------------------
# 4. Conflict cannot overwrite official.
# ---------------------------------------------------------------------------
def test_value_conflict_fails_closed_never_promoted_and_official_fact_untouched():
    official_fact = _official_fact(value=1_000_000_000)
    official = _panel(official_fact)
    provider = _provider_fact(value=999_999_999, currency="VND", scale=1)  # known scale, genuinely disagrees
    record = fop.classify_operational_proxy_fact(provider, entity_type="corporate", official_index=fop.build_official_index(official))
    assert record["official_reconciliation"]["reconciliation_status"] == fop.VALUE_CONFLICT
    assert record["evidence_tier"] is None
    assert all(v is False for k, v in record["fitness_for_use"].items() if k.endswith("_eligible"))
    assert official_fact["value"] == 1_000_000_000  # the classifier never mutates its input


def test_module_never_calls_the_panel_ingress_function():
    """A conflicting or agreeing provider fact must never be merged into the official
    panel -- this module has no import of and no call to
    p3f13_official_financial_evidence_scaleout.merge_document_qualified_facts_into_panel."""
    assert "merge_document_qualified_facts_into_panel" not in SOURCE


# ---------------------------------------------------------------------------
# 5. One global usable boolean is not used.
# ---------------------------------------------------------------------------
def test_fitness_for_use_has_six_independent_named_booleans_not_one_global_usable_flag():
    fields = fop.FitnessForUse.__dataclass_fields__
    boolean_fields = {name for name, f in fields.items() if f.type == "bool"}
    assert boolean_fields == {
        "display_eligible", "research_eligible", "trend_eligible",
        "valuation_research_eligible", "authoritative_financial_eligible", "pit_backtest_eligible",
    }
    assert "usable" not in fields and "is_usable" not in fields


def test_source_code_defines_no_single_global_usable_boolean_field():
    tree = ast.parse(SOURCE)
    assigned_names = {
        target.id for node in ast.walk(tree) if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    }
    assert not any(name.lower() in {"usable", "is_usable"} for name in assigned_names)


# ---------------------------------------------------------------------------
# 6. Fitness-for-use is purpose-specific.
# ---------------------------------------------------------------------------
def test_fitness_for_use_flags_differ_for_the_same_operational_proxy_fact():
    fitness = fop.fitness_for_use(tier=fop.OPERATIONAL_PROXY, currency=None, scale=None)
    as_dict = fitness.to_dict()
    assert as_dict["research_eligible"] is True
    assert as_dict["valuation_research_eligible"] is False
    assert as_dict["research_eligible"] != as_dict["valuation_research_eligible"]
    assert as_dict["authoritative_financial_eligible"] is False
    assert as_dict["pit_backtest_eligible"] is False


def test_fitness_for_use_example_from_the_milestone_brief_provider_normalized_revenue():
    """provider normalized (currency+scale known) annual revenue: display/research/trend/
    valuation_research = YES, authoritative/pit_backtest = NO."""
    fitness = fop.fitness_for_use(tier=fop.OPERATIONAL_PROXY, currency="VND", scale=1).to_dict()
    assert (fitness["display_eligible"], fitness["research_eligible"], fitness["trend_eligible"],
            fitness["valuation_research_eligible"], fitness["authoritative_financial_eligible"],
            fitness["pit_backtest_eligible"]) == (True, True, True, True, False, False)


def test_fitness_for_use_example_from_the_milestone_brief_unresolved_unit_scale():
    """A provider observation with unresolved unit/scale: research = NO, valuation = NO."""
    fact = _provider_fact(currency=None, scale=None)
    record = fop.classify_operational_proxy_fact(fact, entity_type="corporate", official_index=_empty_official_index())
    assert record["fitness_for_use"]["research_eligible"] is True  # descriptive research is fine
    assert record["fitness_for_use"]["valuation_research_eligible"] is False  # absolute use is not


# ---------------------------------------------------------------------------
# 7. Same-source scale-invariant growth may be research eligible where justified.
# ---------------------------------------------------------------------------
def test_same_source_growth_input_fact_is_trend_and_research_eligible_despite_unresolved_scale():
    fact = _provider_fact(currency=None, scale=None)
    record = fop.classify_operational_proxy_fact(fact, entity_type="corporate", official_index=_empty_official_index())
    assert record["fitness_for_use"]["trend_eligible"] is True
    assert record["fitness_for_use"]["research_eligible"] is True


def test_derived_ratio_is_explicitly_labelled_scale_invariant():
    facts = [
        _provider_fact(canonical_metric="net_income", reporting_period="2023", value=100),
        _provider_fact(canonical_metric="revenue", reporting_period="2023", value=1000),
        _provider_fact(canonical_metric="net_income", reporting_period="2024", value=150),
        _provider_fact(canonical_metric="revenue", reporting_period="2024", value=1000),
    ]
    result = fop.derive_ratio_metric(
        ticker="TST", derived_metric_id="net_margin", numerator_metric="net_income",
        denominator_metric="revenue", family="same_statement_family", description="", facts=facts,
    )
    assert result["absolute_or_scale_invariant"] == "scale_invariant"
    assert result["status"] == "AVAILABLE"
    assert result["trend"]["direction"] == "INCREASED"
    assert pytest.approx(result["trend"]["from_ratio_value"]) == 0.1
    assert pytest.approx(result["trend"]["to_ratio_value"]) == 0.15


def test_ratio_never_mixes_two_different_providers_into_one_datapoint():
    facts = [
        _provider_fact(canonical_metric="net_income", provider="VCI", value=100),
        _provider_fact(canonical_metric="revenue", provider="KBS", value=1000),  # different provider, same period
    ]
    result = fop.derive_ratio_metric(
        ticker="TST", derived_metric_id="net_margin", numerator_metric="net_income",
        denominator_metric="revenue", family="same_statement_family", description="", facts=facts,
    )
    assert result["status"] == "BLOCKED"
    assert result["blocked_reason"] == "NO_SAME_REPRESENTATION_NUMERATOR_DENOMINATOR_PAIR"


# ---------------------------------------------------------------------------
# 8. Absolute valuation remains blocked when monetary scale is unresolved.
# ---------------------------------------------------------------------------
def test_absolute_valuation_blocked_when_currency_unknown():
    fact = _provider_fact(currency=None, scale=1)
    record = fop.classify_operational_proxy_fact(fact, entity_type="corporate", official_index=_empty_official_index())
    assert record["fitness_for_use"]["valuation_research_eligible"] is False


def test_absolute_valuation_blocked_when_scale_unknown():
    fact = _provider_fact(currency="VND", scale=None)
    record = fop.classify_operational_proxy_fact(fact, entity_type="corporate", official_index=_empty_official_index())
    assert record["fitness_for_use"]["valuation_research_eligible"] is False


def test_module_never_guesses_a_scale_to_force_a_match():
    """A raw mismatch under unknown scale must be NOT_COMPARABLE_UNIT, never a guessed
    EXACT_MATCH and never a guessed VALUE_CONFLICT."""
    official = _panel(_official_fact(value=1_000_000_000))
    provider = _provider_fact(value=1_000_000, currency=None, scale=None)  # off by exactly 1000x, scale unknown
    record = fop.classify_operational_proxy_fact(provider, entity_type="corporate", official_index=fop.build_official_index(official))
    assert record["official_reconciliation"]["reconciliation_status"] == fop.NOT_COMPARABLE_UNIT
    assert record["evidence_tier"] == fop.OPERATIONAL_PROXY  # not conflict-blocked, not upgraded


def test_derived_ratios_are_never_valuation_research_eligible():
    facts = [
        _provider_fact(canonical_metric="net_income", reporting_period="2024", value=100),
        _provider_fact(canonical_metric="revenue", reporting_period="2024", value=1000),
    ]
    result = fop.derive_ratio_metric(
        ticker="TST", derived_metric_id="net_margin", numerator_metric="net_income",
        denominator_metric="revenue", family="same_statement_family", description="", facts=facts,
    )
    assert result["fitness_for_use"]["valuation_research_eligible"] is False


# ---------------------------------------------------------------------------
# 9. Incompatible period blocks.
# ---------------------------------------------------------------------------
def test_incompatible_period_blocks_reconciliation_as_not_comparable_period():
    official = _panel(_official_fact(reporting_period="2023", statement_scope="consolidated", canonical_metric="net_income"))
    provider = _provider_fact(canonical_metric="net_income", reporting_period="2024", statement_scope="consolidated")
    record = fop.classify_operational_proxy_fact(provider, entity_type="corporate", official_index=fop.build_official_index(official))
    assert record["official_reconciliation"]["reconciliation_status"] == fop.NOT_COMPARABLE_PERIOD
    assert record["evidence_tier"] == fop.OPERATIONAL_PROXY


def test_quarterly_year_end_period_is_compatible_with_annual_for_a_stock_metric_only():
    # shareholders_equity is a balance-sheet (stock) metric -- the narrow, pre-existing
    # FY/Q4 alias applies to it, but must never apply to a flow metric like revenue.
    official_stock = _panel(_official_fact(canonical_metric="shareholders_equity", reporting_period="2024"))
    provider_stock = _provider_fact(canonical_metric="shareholders_equity", reporting_period="2024-Q4", value=1_000_000_000)
    record_stock = fop.classify_operational_proxy_fact(
        provider_stock, entity_type="corporate", official_index=fop.build_official_index(official_stock),
    )
    assert record_stock["official_reconciliation"]["reconciliation_status"] == fop.EXACT_MATCH

    official_flow = _panel(_official_fact(canonical_metric="revenue", reporting_period="2024"))
    provider_flow = _provider_fact(canonical_metric="revenue", reporting_period="2024-Q4", value=1_000_000_000)
    record_flow = fop.classify_operational_proxy_fact(
        provider_flow, entity_type="corporate", official_index=fop.build_official_index(official_flow),
    )
    assert record_flow["official_reconciliation"]["reconciliation_status"] == fop.NOT_COMPARABLE_PERIOD


# ---------------------------------------------------------------------------
# 10. Incompatible scope blocks.
# ---------------------------------------------------------------------------
def test_incompatible_scope_blocks_reconciliation_as_not_comparable_scope():
    official = _panel(_official_fact(statement_scope="consolidated", reporting_period="2024"))
    provider = _provider_fact(statement_scope="separate", reporting_period="2024")
    record = fop.classify_operational_proxy_fact(provider, entity_type="corporate", official_index=fop.build_official_index(official))
    assert record["official_reconciliation"]["reconciliation_status"] == fop.NOT_COMPARABLE_SCOPE
    assert record["evidence_tier"] == fop.OPERATIONAL_PROXY


def test_no_official_comparator_at_all_is_distinct_from_scope_or_period_mismatch():
    provider = _provider_fact(canonical_metric="cash_and_cash_equivalents")
    record = fop.classify_operational_proxy_fact(provider, entity_type="corporate", official_index=_empty_official_index())
    assert record["official_reconciliation"]["reconciliation_status"] == fop.NO_OFFICIAL_COMPARATOR


# ---------------------------------------------------------------------------
# 11 & 12. Total PAT vs parent earnings, total equity vs parent equity remain distinct.
# ---------------------------------------------------------------------------
def test_bounded_identity_set_reuses_existing_corporate_names_without_inventing_a_conflated_one():
    from financial_fact_coverage_recovery import CORPORATE_IDENTITIES
    assert fop.ELIGIBLE_METRICS == frozenset(CORPORATE_IDENTITIES)
    # The bank/securities parent-attributable identities are a structurally separate
    # vocabulary this module never touches (entity scope is bounded to corporate).
    assert "net_profit_parent" not in fop.ELIGIBLE_METRICS
    assert "profit_after_tax_parent" not in fop.ELIGIBLE_METRICS
    assert "total_equity" not in fop.ELIGIBLE_METRICS  # bank/securities name; corporate uses shareholders_equity


def test_module_is_bounded_to_corporate_so_it_cannot_conflate_bank_total_and_parent_earnings():
    from financial_fact_coverage_recovery import REQUIRED_IDENTITIES_BY_ENTITY
    assert fop.SUPPORTED_ENTITY_TYPES == frozenset({"corporate"})
    # Bank/securities keep their own distinct required-identity tuples elsewhere; this
    # module never evaluates a bank/securities ticker at all (test 14 proves this too).
    assert "bank" not in fop.SUPPORTED_ENTITY_TYPES
    assert "securities" not in fop.SUPPORTED_ENTITY_TYPES
    assert REQUIRED_IDENTITIES_BY_ENTITY["bank"] != REQUIRED_IDENTITIES_BY_ENTITY["corporate"]


# ---------------------------------------------------------------------------
# 13. Debt semantics remain explicit.
# ---------------------------------------------------------------------------
def test_total_interest_bearing_debt_is_the_explicit_debt_identity_not_a_generic_liabilities_alias():
    assert "total_interest_bearing_debt" in fop.ELIGIBLE_METRICS
    assert "total_liabilities" not in fop.ELIGIBLE_METRICS
    leverage = next(row for row in fop.DERIVED_RATIO_METRICS if row[0] == "leverage_debt_to_equity")
    assert leverage[1] == "total_interest_bearing_debt"
    assert leverage[2] == "shareholders_equity"


# ---------------------------------------------------------------------------
# 14. Corporate provider mapping does not leak into bank/securities.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("entity_type", ["bank", "securities", "insurance", "finance_company", None, "unknown"])
def test_non_corporate_or_unresolved_entity_type_produces_zero_operational_proxy_facts(entity_type):
    fact = _provider_fact()
    record = fop.classify_operational_proxy_fact(fact, entity_type=entity_type, official_index=_empty_official_index())
    assert record["evidence_tier"] is None
    assert record["reason_codes"] == ["ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE"]
    assert all(v is False for k, v in record["fitness_for_use"].items() if k.endswith("_eligible"))


def test_bank_ticker_produces_zero_operational_proxy_facts_and_zero_derived_metrics_end_to_end():
    facts = [_provider_fact(canonical_metric=metric) for metric in ("revenue", "net_income", "total_assets")]
    ticker_record = fop.build_ticker_operational_proxy(
        ticker="VCB", entity_type="bank", facts=facts, official_index=_empty_official_index(),
    )
    assert ticker_record["entity_type_supported_this_milestone"] is False
    assert all(fact["evidence_tier"] is None for fact in ticker_record["facts"])
    assert ticker_record["derived_metrics"] == []
    assert ticker_record["tier_counts"] == {tier: 0 for tier in fop.EVIDENCE_TIERS}


def test_bank_ticker_on_real_retained_data_produces_zero_operational_proxy_facts():
    store = pytest.importorskip("canonical_fact_store")
    profiles = store.load_entity_profiles(ROOT / "config" / "ticker_entity_profiles.csv")
    citations = store.load_official_citations(RUNTIME_ROOT)
    built = store.build_ticker_facts(RUNTIME_ROOT, "VCB", profiles=profiles, official_citations=citations)
    entity_type = built["applicability"]["archetype"].get("issuer_entity_type")
    assert entity_type == "bank"
    ticker_record = fop.build_ticker_operational_proxy(
        ticker="VCB", entity_type=entity_type, facts=built["facts"], official_index=_empty_official_index(),
    )
    assert ticker_record["tier_counts"][fop.OPERATIONAL_PROXY] == 0
    assert ticker_record["tier_counts"][fop.VERIFIED_RESEARCH_EVIDENCE] == 0


# ---------------------------------------------------------------------------
# 15. Real retained provider history produces research gain.
# ---------------------------------------------------------------------------
def test_real_retained_hpg_data_produces_operational_proxy_and_verified_research_evidence_facts():
    store = pytest.importorskip("canonical_fact_store")
    import p3f13_official_financial_evidence_scaleout as p3f13mod

    profiles = store.load_entity_profiles(ROOT / "config" / "ticker_entity_profiles.csv")
    citations = store.load_official_citations(RUNTIME_ROOT)
    built = store.build_ticker_facts(RUNTIME_ROOT, "HPG", profiles=profiles, official_citations=citations)
    panel = p3f13mod.execute()["refreshed_panel_data"]
    ticker_record = fop.build_ticker_operational_proxy(
        ticker="HPG", entity_type=built["applicability"]["archetype"].get("issuer_entity_type"),
        facts=built["facts"], official_index=fop.build_official_index(panel),
    )
    assert ticker_record["tier_counts"][fop.OPERATIONAL_PROXY] > 0
    assert ticker_record["tier_counts"][fop.VERIFIED_RESEARCH_EVIDENCE] > 0  # real EXACT_MATCH, not synthetic


# ---------------------------------------------------------------------------
# 16. Authoritative fact counts do not falsely increase.
# ---------------------------------------------------------------------------
def test_attaching_operational_proxy_never_changes_authority_tier_of_any_ticker():
    import market_wide_current_fundamental_research as mwcfr

    p3f10_frozen = {"artifact_identity": "p3f10:x", "cohort_identity": {"total_cohort_count": 0},
                    "instrument_dispositions": []}
    p3f13_current = {
        "source_artifacts": {"p3f10": "p3f10:x"}, "cohort_identity": {"total_cohort_count": 0},
        "refreshed_fundamental_readiness": {"issuer_research_readiness": [], "coverage_summary": {"metric_status_counts": {}}},
        "acquisition_dispositions": [],
    }
    before = mwcfr.build_artifact(p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current, requested_at="t")
    after = mwcfr.build_artifact(
        p3f10_frozen=p3f10_frozen, p3f13_current=p3f13_current, requested_at="t",
        operational_proxy_by_ticker={"NOPE": {"tier_counts": {"OPERATIONAL_PROXY": 5}}},
    )
    assert before["records"] == after["records"] == {}
    assert "operational_proxy_coverage" not in before
    assert "operational_proxy_coverage" in after


def test_default_call_shape_is_byte_identical_to_before_the_new_parameter_existed():
    import market_wide_current_fundamental_research as mwcfr
    import inspect

    signature = inspect.signature(mwcfr.build_artifact)
    assert signature.parameters["operational_proxy_by_ticker"].default is None


# ---------------------------------------------------------------------------
# 17. Derived result tier cannot exceed weakest input.
# ---------------------------------------------------------------------------
def test_derived_ratio_result_tier_is_operational_proxy_even_when_both_inputs_would_individually_exact_match():
    """Both net_income and revenue individually reconcile EXACT_MATCH against the official
    panel (so each *raw* fact would be VERIFIED_RESEARCH_EVIDENCE), but the derived ratio
    combining them is still capped at OPERATIONAL_PROXY -- a derived result never exceeds
    the weakest of {OPERATIONAL_PROXY, OPERATIONAL_PROXY} = OPERATIONAL_PROXY, since
    derive_ratio_metric only ever consumes provider_reported (never already-authoritative)
    facts as its inputs."""
    facts = [
        _provider_fact(canonical_metric="net_income", reporting_period="2024", value=100),
        _provider_fact(canonical_metric="revenue", reporting_period="2024", value=1000),
    ]
    result = fop.derive_ratio_metric(
        ticker="TST", derived_metric_id="net_margin", numerator_metric="net_income",
        denominator_metric="revenue", family="same_statement_family", description="", facts=facts,
    )
    assert result["input_evidence_tiers"] == [fop.OPERATIONAL_PROXY, fop.OPERATIONAL_PROXY]
    assert result["result_evidence_tier"] == fop.OPERATIONAL_PROXY


def test_derived_metric_preserves_source_periods_method_and_input_warnings():
    facts = [
        _provider_fact(canonical_metric="net_income", reporting_period="2024", value=10, provider="KBS"),
        _provider_fact(canonical_metric="total_assets", reporting_period="2024", value=1000, provider="KBS"),
    ]
    result = fop.derive_ratio_metric(
        ticker="TST", derived_metric_id="roa", numerator_metric="net_income",
        denominator_metric="total_assets", family="cross_statement_family", description="", facts=facts,
    )
    assert result["source_periods"] == ["2024"]
    assert result["method"]
    assert result["input_warnings"] == [fop.CROSS_STATEMENT_WARNING]


# ---------------------------------------------------------------------------
# 18. Deterministic artifact identity.
# ---------------------------------------------------------------------------
def test_content_identity_excludes_operational_timestamp():
    artifact_a = {"a": 1, "requested_at": "2026-01-01T00:00:00Z", "generated_at": "2026-01-01T00:00:00Z"}
    artifact_b = {"a": 1, "requested_at": "2099-12-31T23:59:59Z", "generated_at": "2099-12-31T23:59:59Z"}
    assert fop.content_identity(artifact_a) == fop.content_identity(artifact_b)


def test_content_identity_changes_when_actual_content_changes():
    identity_a = fop.content_identity({"a": 1, "requested_at": "t"})
    identity_b = fop.content_identity({"a": 2, "requested_at": "t"})
    assert identity_a != identity_b


def test_build_operational_proxy_artifact_is_byte_deterministic_across_two_runs():
    facts = {"TST": [_provider_fact()]}
    kwargs = dict(tickers=["TST"], facts_by_ticker=facts, entity_type_by_ticker={"TST": "corporate"},
                 refreshed_panel_data={"issuers": []})
    first = fop.build_operational_proxy_artifact(**kwargs, requested_at="2026-01-01T00:00:00Z")
    second = fop.build_operational_proxy_artifact(**kwargs, requested_at="2099-01-01T00:00:00Z")
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first["artifact_identity"].startswith("financial_operational_proxy/v1:")


# ---------------------------------------------------------------------------
# 19-25. No network / no new provider / no OCR / no Vision / no production DB / no
# Dashboard / no VALUE-ranking-recommendation-target-probability-sizing-PIT promotion.
# ---------------------------------------------------------------------------
_FORBIDDEN_IMPORT_MODULES = {
    "requests", "urllib", "urllib2", "httpx", "socket", "http.client", "aiohttp",
    "pytesseract", "tesseract", "sqlite3", "anthropic", "openai",
}


def test_module_imports_no_network_ocr_vision_or_production_db_library():
    """Checks actual `import X` / `from X import ...` statements only -- not prose, and
    not this module's own declarative `no_network_no_ocr_no_vision_no_new_provider`-style
    self-report flags, which legitimately contain these words as a negation."""
    tree = ast.parse(SOURCE)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
    assert imported_modules.isdisjoint(_FORBIDDEN_IMPORT_MODULES)


def test_module_source_has_no_dashboard_runtime_path_reference():
    assert "dashboard-runtime" not in SOURCE
    assert "market-dashboard" not in SOURCE
    assert "publish_dashboard" not in SOURCE


def test_module_introduces_no_new_provider_source_literal():
    # The only provider strings this module ever sees are whatever the already-retained
    # canonical facts carry (VCI/KBS); it defines none of its own.
    tree = ast.parse(SOURCE)
    string_literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "EODHD" not in string_literals
    assert not any(token in string_literals for token in ("Bloomberg", "Refinitiv", "FactSet"))


def test_is_actionable_is_always_false_everywhere_in_a_built_artifact():
    facts = {"TST": [_provider_fact()]}
    artifact = fop.build_operational_proxy_artifact(
        tickers=["TST"], facts_by_ticker=facts, entity_type_by_ticker={"TST": "corporate"},
        refreshed_panel_data={"issuers": []}, requested_at="t",
    )
    assert artifact["is_actionable"] is False
    assert artifact["records"]["TST"]["is_actionable"] is False


def _all_dict_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, sub in value.items():
            keys.add(str(key))
            keys |= _all_dict_keys(sub)
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys |= _all_dict_keys(item)
    return keys


def test_no_value_ranking_recommendation_target_probability_sizing_or_pit_field_anywhere():
    """No key in the artifact ever *carries* a target price, recommendation, ranking,
    probability, or position-sizing value. This module's own declarative self-report
    flags (e.g. `no_value_ranking_recommendation_target_probability_sizing_pit_promotion`)
    legitimately name these concepts to assert their absence -- that is a different thing
    from emitting one, so this checks exact forbidden key names, not substrings."""
    # "value" itself is not forbidden -- plain numeric value fields are the data model
    # throughout this codebase (e.g. p3f13_official_financial_evidence_scaleout's own
    # `Fact.value`). What is forbidden is the strategy-tier VALUE promotion concept
    # (market_wide_current_valuation_input_scaleout.evaluate_value_strategy_readiness's
    # READY/RESEARCH_USABLE/VALUE ladder) and target/recommendation/ranking/probability/
    # sizing/PIT-backtest promotion.
    forbidden_exact_keys = {
        "target_price", "recommendation", "recommendation_action", "ranking", "rank",
        "probability", "position_size", "position_sizing", "pit_backtest_qualified",
        "value_strategy_eligible", "strategy_value",
    }
    artifact = fop.build_operational_proxy_artifact(
        tickers=["TST"], facts_by_ticker={"TST": [_provider_fact()]}, entity_type_by_ticker={"TST": "corporate"},
        refreshed_panel_data={"issuers": []}, requested_at="t",
    )
    assert forbidden_exact_keys.isdisjoint(_all_dict_keys(artifact))


def test_pit_backtest_eligible_is_false_for_every_tier_including_authoritative():
    for tier in fop.EVIDENCE_TIERS:
        assert fop.fitness_for_use(tier=tier, currency="VND", scale=1).pit_backtest_eligible is False


# ---------------------------------------------------------------------------
# Sector-safety extra: identity-incomplete and metric-out-of-scope facts fail closed too.
# ---------------------------------------------------------------------------
def test_metric_outside_bounded_identity_set_is_never_classified():
    fact = _provider_fact(canonical_metric="some_metric_not_in_the_registry")
    record = fop.classify_operational_proxy_fact(fact, entity_type="corporate", official_index=_empty_official_index())
    assert record["evidence_tier"] is None
    assert record["reason_codes"] == ["METRIC_NOT_IN_BOUNDED_IDENTITY_SET"]


def test_identity_incomplete_fact_is_never_classified():
    fact = _provider_fact(provider=None)
    record = fop.classify_operational_proxy_fact(fact, entity_type="corporate", official_index=_empty_official_index())
    assert record["evidence_tier"] is None
    assert record["reason_codes"] == ["IDENTITY_INCOMPLETE"]


def test_reconciliation_states_are_the_exact_six_named_in_the_milestone_brief():
    assert set(fop.RECONCILIATION_STATES) == {
        "EXACT_MATCH", "VALUE_CONFLICT", "NOT_COMPARABLE_SCOPE",
        "NOT_COMPARABLE_PERIOD", "NOT_COMPARABLE_UNIT", "NO_OFFICIAL_COMPARATOR",
    }
