import inspect
from pathlib import Path

import canonical_financial_facts as facts
import financial_fact_coverage_recovery as ffcr
import market_wide_current_fundamental_research as mwcfr
import provider_financial_semantic_basis as pfsb

ROOT = Path(__file__).resolve().parents[1]


def _agreeing_fact(*, ticker="AAA", metric="shareholders_equity", provider="VCI",
                    statement_family="balance_sheet", period="2024-Q4", value=1000,
                    statement_scope="consolidated", currency="VND", scale="units"):
    return {
        "ticker": ticker, "canonical_metric": metric, "provider": provider,
        "statement_family": statement_family, "reporting_period": period,
        "period_type": "quarterly", "status": facts.STATUS_QUALIFIED,
        "unit_authority": "official_citation_agreement",
        "statement_scope": statement_scope, "currency": currency, "scale": scale,
        "value": value, "conflicts": [],
    }


def _disagreeing_fact(*, ticker="BBB", metric="shareholders_equity", provider="VCI",
                       statement_family="balance_sheet", period="2024-Q4",
                       provider_value=999, official_value=1):
    return {
        "ticker": ticker, "canonical_metric": metric, "provider": provider,
        "statement_family": statement_family, "reporting_period": period,
        "period_type": "quarterly", "status": facts.STATUS_CONFLICTED,
        "unit_authority": None, "statement_scope": "consolidated",
        "currency": "unknown", "scale": "unknown", "value": provider_value,
        "conflicts": [{"kind": "official_citation_disagrees", "official_value": official_value,
                       "provider_value": provider_value}],
    }


# ---------------------------------------------------------------------------
# 1. Provider-specific, endpoint-specific qualification
# ---------------------------------------------------------------------------

def test_kbs_and_vci_are_evaluated_independently_not_as_one_provider_verdict():
    kbs = pfsb.evaluate_semantic_basis_contract(provider="KBS", statement_family="income_statement")
    vci = pfsb.evaluate_semantic_basis_contract(provider="VCI", statement_family="income_statement")
    assert kbs["provider"] == "KBS" and vci["provider"] == "VCI"
    assert kbs["endpoint_contract"] != vci["endpoint_contract"]
    # Same statement family, different providers: independently derived evidence, not shared.
    assert kbs["qualification_evidence"]["schema_evidence"] != vci["qualification_evidence"]["schema_evidence"]


def test_same_provider_different_statement_family_are_independent_shapes():
    kbs_income = pfsb.evaluate_semantic_basis_contract(provider="KBS", statement_family="income_statement")
    kbs_balance = pfsb.evaluate_semantic_basis_contract(provider="KBS", statement_family="balance_sheet")
    # KBS balance_sheet is empirically empty market-wide; income_statement is not. Must not share a verdict.
    assert kbs_balance["verdict"] == pfsb.NOT_APPLICABLE
    assert kbs_income["verdict"] != pfsb.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# 2. No provider-wide semantic generalization
# ---------------------------------------------------------------------------

def test_agreement_elsewhere_never_qualifies_a_ticker_with_no_evidence_of_its_own():
    registry = pfsb.build_semantic_basis_registry({"shapes": {}})
    # No shape anywhere reaches PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED against real evidence, so an
    # ordinary provider_reported fact (no citation of its own) must never become eligible.
    plain_fact = {
        "ticker": "ZZZ", "canonical_metric": "total_assets", "provider": "VCI",
        "statement_family": "balance_sheet", "status": "provider_reported",
        "unit_authority": "unknown", "statement_scope": "unknown",
        "currency": "unknown", "scale": "unknown", "value": 123,
    }
    decision = pfsb.classify_provider_exact_research_usable(plain_fact, registry=registry)
    assert decision["eligible"] is False


def test_shape_route_only_fires_when_the_shape_itself_is_qualified():
    fake_registry = {"contracts": {"VCI:balance_sheet": {"verdict": pfsb.PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED}}}
    matching = {"provider": "VCI", "statement_family": "balance_sheet", "status": "provider_reported"}
    other_shape = {"provider": "KBS", "statement_family": "income_statement", "status": "provider_reported"}
    assert pfsb.classify_provider_exact_research_usable(matching, registry=fake_registry)["eligible"] is True
    assert pfsb.classify_provider_exact_research_usable(other_shape, registry=fake_registry)["eligible"] is False


# ---------------------------------------------------------------------------
# 3. Currency cannot be inferred from numeric magnitude alone
# ---------------------------------------------------------------------------

def test_unschematized_provider_never_qualifies_even_with_perfect_reconciliation():
    recon = {
        "agree_count": 5, "disagree_count": 0,
        "agreeing_tickers": ["A", "B", "C", "D", "E"],
        "magnitude_min": 1.0, "magnitude_max": 1000.0,
    }
    contract = pfsb.evaluate_semantic_basis_contract(
        provider="SOME_UNSCHEMATIZED_PROVIDER", statement_family="balance_sheet", reconciliation=recon,
    )
    # No canonical identity is even registered for a provider outside METRIC_REGISTRY's own
    # statement-family universe under a made-up provider label, but the schema-evidence leg alone
    # (absent here) is what actually blocks qualification -- verified explicitly below.
    assert contract["verdict"] != pfsb.PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED


def test_missing_schema_evidence_blocks_qualification_regardless_of_reconciliation_strength():
    strong_recon = {
        "agree_count": 10, "disagree_count": 0,
        "agreeing_tickers": [f"T{i}" for i in range(10)],
        "magnitude_min": 1.0, "magnitude_max": 1_000_000.0,
    }
    contract = pfsb.evaluate_semantic_basis_contract(
        provider="NO_SCHEMA_PROVIDER", statement_family="balance_sheet", reconciliation=strong_recon,
    )
    assert contract["qualification_evidence"]["schema_evidence"] is None
    assert contract["verdict"] != pfsb.PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED


# ---------------------------------------------------------------------------
# 4. Scale cannot be inferred from one official match
# ---------------------------------------------------------------------------

def test_single_issuer_agreement_is_not_discriminating():
    single_issuer = {
        "agree_count": 1, "disagree_count": 0,
        "agreeing_tickers": ["HPG"], "magnitude_min": 1_000_000.0, "magnitude_max": 1_000_000.0,
    }
    assert pfsb._is_discriminating(single_issuer) is False
    contract = pfsb.evaluate_semantic_basis_contract(
        provider="VCI", statement_family="balance_sheet", reconciliation=single_issuer,
    )
    assert contract["verdict"] != pfsb.PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED


def test_real_vci_balance_sheet_reconciliation_has_disagreement_and_stays_unresolved():
    """Real, already-observed evidence: 6 issuers agree on VCI balance-sheet shareholders_equity
    (8.86T-114.6T VND) but PVD and VNM disagree on the same shape/metric. This is the concrete case
    the milestone's 'no single-ticker proof may become market-wide authority' guards against."""
    facts_by_ticker = {
        "FPT": [_agreeing_fact(ticker="FPT", value=43_748_040_747_539)],
        "HPG": [_agreeing_fact(ticker="HPG", value=114_647_457_983_699)],
        "NVL": [_agreeing_fact(ticker="NVL", value=47_291_024_358_614)],
        "PAN": [_agreeing_fact(ticker="PAN", value=8_859_450_516_042)],
        "POW": [_agreeing_fact(ticker="POW", value=34_680_634_910_666)],
        "QNS": [_agreeing_fact(ticker="QNS", value=10_001_517_079_259)],
        "PVD": [_disagreeing_fact(ticker="PVD", provider_value=16_052_342_324_403, official_value=635_711_153)],
        "VNM": [_disagreeing_fact(ticker="VNM", provider_value=36_174_402_829_663, official_value=37_165_930_000_000)],
    }
    recon = pfsb.reconcile_official_anchors(facts_by_ticker)
    shape = recon["shapes"]["('VCI', 'balance_sheet')"]
    assert shape["agree_count"] == 6 and shape["disagree_count"] == 2
    assert pfsb._is_discriminating(shape) is True  # would pass the discriminating bar alone
    assert pfsb._is_consistent(shape) is False      # but fails on consistency
    contract = pfsb.evaluate_semantic_basis_contract(provider="VCI", statement_family="balance_sheet", reconciliation=shape)
    assert contract["verdict"] == pfsb.SEMANTIC_BASIS_UNRESOLVED


# ---------------------------------------------------------------------------
# 5. Consolidated/separate mismatch fails
# ---------------------------------------------------------------------------

def test_unresolved_statement_scope_blocks_per_fact_promotion_even_when_qualified():
    fact = _agreeing_fact(statement_scope="unknown")
    decision = pfsb.classify_provider_exact_research_usable(fact, registry=None)
    assert decision["eligible"] is False
    assert "scope" in decision["reason"]


def test_resolved_consolidated_scope_with_qualified_status_is_eligible():
    fact = _agreeing_fact(statement_scope="consolidated")
    decision = pfsb.classify_provider_exact_research_usable(fact, registry=None)
    assert decision["eligible"] is True
    assert decision["tier"] == pfsb.PROVIDER_EXACT_RESEARCH_USABLE


# ---------------------------------------------------------------------------
# 6. Quarterly/YTD/FY mismatch fails (enforced upstream; verified end to end here)
# ---------------------------------------------------------------------------

def test_flow_metric_annual_citation_never_matches_a_quarterly_fact():
    """canonical_fact_store.load_official_citations deliberately never aliases a flow metric's
    annual citation onto a quarterly period (only point-in-time balance-sheet stocks get the
    annual->Q4 alias). Confirmed here directly against build_facts so this module's reconciliation
    can never see a spurious flow-metric agreement across incompatible period types."""
    observations = [
        {"statement_family": "income_statement", "reporting_period": "2024-Q4", "period_variant_index": 0,
         "raw_item_id": "net_profit", "item_id_occurrence": 1, "row_ordinal": 0, "raw_value": 500,
         "provider": "VCI", "source_file": "T_income_statement_quarter.parquet", "source_sha256": "s",
         "observation_id": "o1", "warnings": []},
    ]
    citations = {("TST", "net_income", "2024"): {"citation_id": "c", "value": 500, "currency": "VND", "scale": "units"}}
    built = facts.build_facts("TST", observations, official_citations=citations)
    net_income = next(f for f in built["facts"] if f["canonical_metric"] == "net_income")
    assert net_income["status"] != facts.STATUS_QUALIFIED
    assert net_income["reporting_period"] == "2024-Q4"


# ---------------------------------------------------------------------------
# 7. KBS period bounds propagated when genuinely retained
# ---------------------------------------------------------------------------

def test_kbs_duration_evidence_is_cited_and_matches_the_existing_mechanism():
    schema = pfsb.KBS_FINANCE_INFO_SCHEMA_EVIDENCE
    assert schema["period_basis_evidence"]["Q1"] == "SINGLE_QUARTER"
    assert schema["period_basis_evidence"]["basis"] == mwcfr.KBS_KQKD_QUARTER_SEMANTICS["evidence"]
    contract = pfsb.evaluate_semantic_basis_contract(provider="KBS", statement_family="income_statement")
    assert contract["period_basis"] == mwcfr.KBS_KQKD_QUARTER_SEMANTICS["evidence"]


# ---------------------------------------------------------------------------
# 8. VCI duration remains UNKNOWN if evidence still lacks duration semantics
# ---------------------------------------------------------------------------

def test_vci_duration_stays_unknown():
    schema = pfsb.VCI_FINANCE_SCHEMA_EVIDENCE
    assert set(schema["period_basis_evidence"].values()) == {"UNKNOWN"}
    contract = pfsb.evaluate_semantic_basis_contract(provider="VCI", statement_family="income_statement")
    assert contract["period_basis"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 9. Official-anchor corroboration requires aligned identity/period/scope
# ---------------------------------------------------------------------------

def test_reconciliation_only_counts_facts_that_actually_carry_a_citation_check():
    plain = {"ticker": "T", "canonical_metric": "revenue", "provider": "VCI",
             "statement_family": "income_statement", "reporting_period": "2024-Q1",
             "status": "provider_reported", "conflicts": []}
    recon = pfsb.reconcile_official_anchors({"T": [plain]})
    assert recon["shapes"] == {}


# ---------------------------------------------------------------------------
# 10. A per-fact-qualified provider fact cannot become OFFICIAL_QUALIFIED
# ---------------------------------------------------------------------------

def test_provider_exact_research_usable_never_reaches_official_qualified():
    record = {"authority_tier": mwcfr.PROVIDER_TIER, "entity_class": "corporate",
              "entity_class_provenance": {"conflict": False}, "provider_series_trends": {"metrics": {}}}
    evidence = {"shareholders_equity": [{"route": "PER_FACT_OFFICIAL_CITATION_AGREEMENT"}]}
    result = ffcr.classify_identity_cell(
        ticker_record=record, identity="shareholders_equity", canonical_presence={"shareholders_equity": True},
        provider_exact_research_evidence=evidence,
    )
    assert result["state"] == "PROVIDER_EXACT_RESEARCH_USABLE"
    assert result["state"] != "OFFICIAL_QUALIFIED"


def test_official_tier_branch_never_consults_provider_exact_evidence():
    """OFFICIAL_TIER classification must be unaffected by provider_exact_research_evidence being
    present -- the two authority tiers stay on strictly separate evidentiary chains."""
    record = {"authority_tier": mwcfr.OFFICIAL_TIER, "entity_class": "corporate",
              "entity_class_provenance": {"conflict": False}}
    evidence = {"shareholders_equity": [{"route": "PER_FACT_OFFICIAL_CITATION_AGREEMENT"}]}
    result = ffcr.classify_identity_cell(
        ticker_record=record, identity="shareholders_equity", canonical_presence={},
        official_facts={}, provider_exact_research_evidence=evidence,
    )
    assert result["state"] == "MISSING"  # unaffected: no official panel fact, evidence dict ignored


# ---------------------------------------------------------------------------
# 11 & 13. Provider exact research use remains non-authoritative; no target/recommendation/ranking/sizing
# ---------------------------------------------------------------------------

def test_provider_exact_research_usable_carries_only_nonauthoritative_uses():
    fact = _agreeing_fact()
    decision = pfsb.classify_provider_exact_research_usable(fact, registry=None)
    assert pfsb.CURRENT_RESEARCH_NONAUTHORITATIVE_VALUATION_INPUT in decision["allowed_uses"]
    forbidden = set(decision["forbidden_uses"])
    for banned in ("authoritative_valuation_input", "target_price", "buy_sell_recommendation",
                   "cross_sectional_ranking", "portfolio_sizing", "backtesting", "execution_actionability"):
        assert banned in forbidden


# ---------------------------------------------------------------------------
# 12. No VALUE activation anywhere in this module
# ---------------------------------------------------------------------------

def test_module_never_imports_or_touches_the_valuation_engine():
    source = inspect.getsource(pfsb)
    for token in ("import market_wide_current_valuation", "from market_wide_current_valuation",
                  "build_current_valuation_artifact(", "value_strategy_readiness"):
        assert token not in source, f"unexpected valuation-activation token found: {token}"


# ---------------------------------------------------------------------------
# 14. No cross-ticker/provider propagation
# ---------------------------------------------------------------------------

def test_classification_is_independent_per_ticker():
    record_a = {"authority_tier": mwcfr.PROVIDER_TIER, "entity_class": "corporate",
                "entity_class_provenance": {"conflict": False}, "provider_series_trends": {"metrics": {}}}
    record_b = {"authority_tier": mwcfr.PROVIDER_TIER, "entity_class": "corporate",
                "entity_class_provenance": {"conflict": False}, "provider_series_trends": {"metrics": {}}}
    evidence_a_only = {"A": {"total_assets": [{"route": "PER_FACT_OFFICIAL_CITATION_AGREEMENT"}]}}
    result_a = ffcr.classify_identity_cell(ticker_record=record_a, identity="total_assets",
                                           canonical_presence={"total_assets": True},
                                           provider_exact_research_evidence=evidence_a_only.get("A"))
    result_b = ffcr.classify_identity_cell(ticker_record=record_b, identity="total_assets",
                                           canonical_presence={"total_assets": True},
                                           provider_exact_research_evidence=evidence_a_only.get("B"))
    assert result_a["state"] == "PROVIDER_EXACT_RESEARCH_USABLE"
    assert result_b["state"] == "UNIT_OR_SCALE_UNRESOLVED"


def test_reconciliation_evidence_bounded_to_tickers_with_a_citation_never_touches_others(monkeypatch):
    """load_provider_exact_research_evidence must only ever call build_ticker_facts for tickers
    that appear as an official-citation key -- a ticker with none is structurally unreachable."""
    import canonical_fact_store as store
    calls = []
    original = store.build_ticker_facts

    def _spy(runtime_root, ticker, **kwargs):
        calls.append(ticker)
        return original(runtime_root, ticker, **kwargs)

    monkeypatch.setattr(store, "build_ticker_facts", _spy)
    monkeypatch.setattr(store, "load_official_citations", lambda root: {("HPG", "shareholders_equity", "2024-Q4"): {
        "citation_id": "c", "value": 1, "currency": "VND", "scale": "units"}})
    pfsb.load_provider_exact_research_evidence(ROOT.parent / "dashboard-runtime")
    assert calls == ["HPG"]


# ---------------------------------------------------------------------------
# 15. Residual-zero inventory (integration with the new evidence parameter)
# ---------------------------------------------------------------------------

def test_identity_inventory_residual_zero_with_provider_exact_evidence_present():
    artifact = {"records": {
        "PRO": {"authority_tier": mwcfr.PROVIDER_TIER, "entity_class": "corporate",
                "entity_class_provenance": {"conflict": False}, "provider_series_trends": {"metrics": {}}},
    }}
    evidence = {"PRO": {"shareholders_equity": [{"route": "PER_FACT_OFFICIAL_CITATION_AGREEMENT"}]}}
    inventory = ffcr.build_financial_identity_inventory(
        artifact, canonical_presence_by_ticker={}, provider_exact_research_evidence_by_ticker=evidence,
    )
    assert inventory["residual"] == 0
    assert inventory["state_counts"]["PROVIDER_EXACT_RESEARCH_USABLE"] == 1


def test_omitting_the_new_parameter_reproduces_prior_behavior_exactly():
    artifact = {"records": {
        "PRO": {"authority_tier": mwcfr.PROVIDER_TIER, "entity_class": "corporate",
                "entity_class_provenance": {"conflict": False}, "provider_series_trends": {"metrics": {}}},
    }}
    with_default = ffcr.build_financial_identity_inventory(artifact, canonical_presence_by_ticker={})
    with_empty = ffcr.build_financial_identity_inventory(
        artifact, canonical_presence_by_ticker={}, provider_exact_research_evidence_by_ticker={},
    )
    assert with_default == with_empty
    assert with_default["state_counts"].get("PROVIDER_EXACT_RESEARCH_USABLE", 0) == 0


# ---------------------------------------------------------------------------
# 16. Deterministic replay
# ---------------------------------------------------------------------------

def test_semantic_basis_registry_is_byte_deterministic():
    recon = pfsb.reconcile_official_anchors({
        "HPG": [_agreeing_fact(ticker="HPG"), _agreeing_fact(ticker="HPG", metric="cash_and_cash_equivalents")],
    })
    one = pfsb.build_semantic_basis_registry(recon)
    two = pfsb.build_semantic_basis_registry(recon)
    assert one == two
    assert one["artifact_sha256"] == two["artifact_sha256"]


# ---------------------------------------------------------------------------
# 17 / 18. No live network call anywhere in this module; py_compile is covered by tooling.
# ---------------------------------------------------------------------------

def test_module_makes_no_live_network_call():
    source = inspect.getsource(pfsb)
    for token in ("requests.get(", "requests.post(", "urlopen(", "socket.connect", "http.client"):
        assert token not in source, f"unexpected live network call pattern: {token}"
    # Endpoint URLs are retained as inert documentation strings only, matching the existing,
    # already-shipped precedent in market_wide_current_fundamental_research.KBS_KQKD_QUARTER_SEMANTICS.
    for banned_import in ("import requests", "import urllib", "\nimport socket"):
        assert banned_import not in source


def test_no_ticker_specific_branch_in_semantic_basis_module():
    source = Path(ROOT / "provider_financial_semantic_basis.py").read_text(encoding="utf-8")
    for pattern in ('ticker == "', "ticker == '", 'if ticker in {"', "if ticker in ('"):
        assert pattern not in source, f"found ticker-specific branch pattern: {pattern}"
