import inspect
import json
from pathlib import Path

import market_wide_current_fundamental_research as mwcfr
import p3f10_fundamental_evidence_scaleout as p3f10mod
import p3f13_official_financial_evidence_scaleout as p3f13mod
import financial_fact_coverage_recovery as ffcr

ROOT = Path(__file__).resolve().parents[1]


def _official_record(entity_class: str) -> dict:
    return {"authority_tier": mwcfr.OFFICIAL_TIER, "entity_class": entity_class,
            "entity_class_provenance": {"conflict": False}}


def _provider_record(entity_class: str, *, trends: dict | None = None) -> dict:
    return {
        "authority_tier": mwcfr.PROVIDER_TIER, "entity_class": entity_class,
        "entity_class_provenance": {"conflict": False},
        "provider_series_trends": {"metrics": trends or {}},
    }


def _blocked_record(entity_class: str) -> dict:
    return {"authority_tier": mwcfr.BLOCKED_TIER, "entity_class": entity_class,
            "entity_class_provenance": {"conflict": False}}


def _unknown_record() -> dict:
    return {"authority_tier": mwcfr.BLOCKED_TIER, "entity_class": "unknown",
            "entity_class_provenance": {"conflict": False, "unresolved_reason": "NO_RETAINED_ENTITY_CLASS_SOURCE"}}


# ---------------------------------------------------------------------------
# 1. Exact financial identity required for OFFICIAL_QUALIFIED
# ---------------------------------------------------------------------------

def test_official_tier_requires_exact_qualification_state():
    record = _official_record("corporate")
    facts = {"revenue": {"qualification_state": "QUALIFIED", "reconciliation_status": "EXACT_MATCH"}}
    result = ffcr.classify_identity_cell(ticker_record=record, identity="revenue", canonical_presence={}, official_facts=facts)
    assert result["state"] == "OFFICIAL_QUALIFIED"

    facts_missing = {"revenue": {"qualification_state": "MISSING"}}
    result_missing = ffcr.classify_identity_cell(ticker_record=record, identity="revenue", canonical_presence={}, official_facts=facts_missing)
    assert result_missing["state"] == "MISSING"

    # No fact retained for the identity at all -- also MISSING, never guessed QUALIFIED.
    result_absent = ffcr.classify_identity_cell(ticker_record=record, identity="revenue", canonical_presence={}, official_facts={})
    assert result_absent["state"] == "MISSING"


# ---------------------------------------------------------------------------
# 2. A provider trend can never become an absolute/official fact
# ---------------------------------------------------------------------------

def test_provider_trend_never_becomes_official_qualified():
    record = _provider_record("corporate", trends={"revenue_growth": {"status": "AVAILABLE"}})
    result = ffcr.classify_identity_cell(ticker_record=record, identity="revenue", canonical_presence={"revenue": True})
    assert result["state"] == "PROVIDER_DESCRIPTIVE_ONLY"
    assert result["state"] != "OFFICIAL_QUALIFIED"
    assert result["state"] != "PROVIDER_EXACT_RESEARCH_USABLE"


# ---------------------------------------------------------------------------
# 3 & 4. Annual/quarter period mismatch and consolidated/separate scope mismatch block
#         the existing trend-comparison layer (unmodified function, exercised directly).
# ---------------------------------------------------------------------------

def test_period_duration_mismatch_blocks_trend_comparison():
    annual = {"reporting_period": "2025", "source_sha256": "same", "statement_scope": "consolidated",
              "period_end": None, "provider": "VCI"}
    quarterly = {"reporting_period": "2026-Q1", "source_sha256": "same", "statement_scope": "consolidated",
                 "period_end": None, "provider": "VCI"}
    eligible, blocker, _ = mwcfr._pair_basis_eligibility(annual, quarterly, "revenue")
    assert eligible is False
    assert blocker is not None


def test_statement_scope_mismatch_blocks_trend_comparison():
    prior = {"reporting_period": "2025-Q4", "source_sha256": "same", "statement_scope": "consolidated", "provider": "VCI"}
    current = {"reporting_period": "2026-Q1", "source_sha256": "same", "statement_scope": "separate", "provider": "VCI"}
    eligible, blocker, _ = mwcfr._pair_basis_eligibility(prior, current, "revenue")
    assert eligible is False
    assert blocker == "STATEMENT_SCOPE_NOT_COMPARABLE"


# ---------------------------------------------------------------------------
# 5. Currency/unit unresolved blocks absolute usability, but is distinguished from MISSING
# ---------------------------------------------------------------------------

def test_unresolved_scope_currency_scale_reported_distinctly_from_missing():
    record = _provider_record("corporate")
    with_fact = ffcr.classify_identity_cell(ticker_record=record, identity="cash_and_cash_equivalents", canonical_presence={"cash_and_cash_equivalents": True})
    without_fact = ffcr.classify_identity_cell(ticker_record=record, identity="cash_and_cash_equivalents", canonical_presence={})
    assert with_fact["state"] == "UNIT_OR_SCALE_UNRESOLVED"
    assert without_fact["state"] == "MISSING"
    assert with_fact["state"] != without_fact["state"]


# ---------------------------------------------------------------------------
# 6 & 7. Bank/securities applicability preserved (only their own required identities)
# ---------------------------------------------------------------------------

def test_bank_required_identities_are_bank_specific():
    identities = ffcr.required_identities_for_entity("bank")
    assert identities == ("net_profit_parent", "total_equity")


def test_securities_required_identities_are_securities_specific():
    identities = ffcr.required_identities_for_entity("securities")
    assert identities == ("profit_after_tax_parent", "total_equity")


# ---------------------------------------------------------------------------
# 8. Industrial EV metrics are never forced onto bank/securities/insurance/finance_company
# ---------------------------------------------------------------------------

def test_industrial_ev_identities_absent_from_intermediary_required_sets():
    industrial_only = {"revenue", "total_assets", "cash_and_cash_equivalents", "total_interest_bearing_debt",
                        "profit_before_tax", "interest_expense", "depreciation_and_amortization"}
    for entity_class in ("bank", "securities", "insurance", "finance_company"):
        required = set(ffcr.required_identities_for_entity(entity_class))
        assert not (required & industrial_only), f"{entity_class} must not require industrial identities: {required & industrial_only}"


# ---------------------------------------------------------------------------
# 9 & 10. One recovered fact upgrades only its own ticker; no cross-ticker propagation
# ---------------------------------------------------------------------------

def test_classification_depends_only_on_its_own_ticker_record():
    record_a = _provider_record("corporate", trends={"revenue_growth": {"status": "AVAILABLE"}})
    record_b_before = _provider_record("corporate")
    result_a = ffcr.classify_identity_cell(ticker_record=record_a, identity="revenue", canonical_presence={"revenue": True})
    result_b_before_change = ffcr.classify_identity_cell(ticker_record=record_b_before, identity="revenue", canonical_presence={"revenue": True})

    # Mutate ticker A's record heavily; ticker B's classification must be byte-identical, proving
    # no shared/global state and no cross-ticker propagation.
    record_a["provider_series_trends"]["metrics"]["revenue_growth"]["status"] = "BLOCKED"
    result_b_after_change = ffcr.classify_identity_cell(ticker_record=record_b_before, identity="revenue", canonical_presence={"revenue": True})
    assert result_b_before_change == result_b_after_change
    assert result_a["state"] == "PROVIDER_DESCRIPTIVE_ONLY"


def test_widening_cohort_is_byte_identical_for_the_narrow_subset():
    """Real end-to-end proof: rerunning the wide artifact never changes a single already-covered
    ticker's own record. This is the central safety property of the whole recovery approach."""
    raw_state = _read(p3f10mod.DEFAULT_RAW_STATE)
    canonical_state = _read(p3f10mod.DEFAULT_CANONICAL_STATE)
    p3e = _read(p3f10mod.DEFAULT_P3E)
    registry = _read(p3f10mod.DEFAULT_REGISTRY)
    manifest = _read(p3f13mod.DEFAULT_MANIFEST)

    narrow_bundle = _read(p3f10mod.DEFAULT_BUNDLE)
    narrow_members = sorted({str(t).upper() for t in narrow_bundle["empirical_active_cohort"]["members"]})
    official_universe = _read(ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json")
    official_tickers = ffcr.official_research_universe_tickers(official_universe)

    p3f10_narrow = p3f10mod.execute()
    p3f13_narrow = p3f13mod.execute()
    provider_series = mwcfr.load_retained_provider_series(mwcfr.DEFAULT_CANONICAL_FACTS_ROOT)
    fundamental_narrow = mwcfr.build_artifact(
        p3f10_frozen=p3f10_narrow, p3f13_current=p3f13_narrow,
        requested_at="2026-08-27T00:00:00Z", provider_series_by_ticker=provider_series,
    )

    p3f10_wide = ffcr.build_extended_p3f10_artifact(
        official_tickers=official_tickers, raw_state=raw_state, canonical_state=canonical_state,
        p3e=p3e, registry=registry, as_of_session="2026-08-26",
    )
    p3f13_wide = ffcr.build_extended_p3f13_artifact(
        p3f10_wide=p3f10_wide, p3e=p3e, registry=registry, manifest_records=manifest.get("records", []),
        evidence_root=p3f13mod.DEFAULT_EVIDENCE_ROOT, raw_obs_dir=p3f13mod.DEFAULT_RAW_OBS_DIR,
    )
    fundamental_wide = ffcr.build_extended_fundamental_artifact(
        p3f10_wide=p3f10_wide, p3f13_wide=p3f13_wide,
        requested_at="2026-08-27T00:00:00Z", provider_series_by_ticker=provider_series,
    )

    assert len(narrow_members) == len(fundamental_narrow["records"])
    mismatches = [
        t for t in narrow_members
        if fundamental_narrow["records"].get(t) != fundamental_wide["records"].get(t)
    ]
    assert mismatches == [], f"widening changed {len(mismatches)} previously-covered tickers: {mismatches[:5]}"
    # Official tier count must be unchanged: widening never promotes new official authority.
    assert fundamental_narrow["coverage"]["issuers_with_official_facts"] == fundamental_wide["coverage"]["issuers_with_official_facts"]
    newly_examined = set(fundamental_wide["records"]) - set(narrow_members)
    assert len(newly_examined) > 0


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 11. Entity routing defect repaired generically -- no ticker-specific branch
# ---------------------------------------------------------------------------

def test_no_ticker_specific_branch_in_recovery_module():
    source = Path(ROOT / "financial_fact_coverage_recovery.py").read_text(encoding="utf-8")
    for pattern in ('ticker == "', "ticker == '", 'if ticker in {"', "if ticker in ('"):
        assert pattern not in source, f"found ticker-specific branch pattern: {pattern}"


# ---------------------------------------------------------------------------
# 12. Unknown entity remains explicit, never guessed
# ---------------------------------------------------------------------------

def test_unknown_entity_produces_explicit_sentinel_never_guessed():
    artifact = {"records": {"ZZZ": _unknown_record()}}
    inventory = ffcr.build_financial_identity_inventory(artifact, canonical_presence_by_ticker={})
    assert inventory["cells"]["ZZZ"] == [{
        "identity": "ENTITY_CLASS", "state": "ENTITY_IDENTITY_MISMATCH",
        "reason": "NO_RETAINED_ENTITY_CLASS_SOURCE",
    }]
    assert inventory["residual"] == 0


# ---------------------------------------------------------------------------
# 13. Residual-zero inventory over a small synthetic multi-entity universe
# ---------------------------------------------------------------------------

def test_residual_zero_over_synthetic_multi_entity_universe():
    artifact = {"records": {
        "OFF": _official_record("corporate"),
        "PRO": _provider_record("bank"),
        "BLK": _blocked_record("securities"),
        "INS": _official_record("insurance"),
        "UNK": _unknown_record(),
    }}
    inventory = ffcr.build_financial_identity_inventory(artifact, canonical_presence_by_ticker={}, official_facts_by_ticker={})
    assert inventory["residual"] == 0
    assert inventory["residual_zero"] is True
    # corporate=9 + bank=2 + securities=2 + insurance=0 + unknown-sentinel=1
    assert inventory["expected_cell_count"] == 9 + 2 + 2 + 0 + 1


# ---------------------------------------------------------------------------
# 14. Research-usable is never conflated with authoritative
# ---------------------------------------------------------------------------

def test_research_usable_state_distinct_from_official_qualified():
    provider_row = ffcr.classify_identity_cell(
        ticker_record=_provider_record("corporate", trends={"revenue_growth": {"status": "AVAILABLE"}}),
        identity="revenue", canonical_presence={"revenue": True},
    )
    official_row = ffcr.classify_identity_cell(
        ticker_record=_official_record("corporate"), identity="revenue", canonical_presence={},
        official_facts={"revenue": {"qualification_state": "QUALIFIED", "reconciliation_status": "EXACT_MATCH"}},
    )
    assert provider_row["state"] == "PROVIDER_DESCRIPTIVE_ONLY"
    assert official_row["state"] == "OFFICIAL_QUALIFIED"
    assert provider_row["state"] != official_row["state"]


# ---------------------------------------------------------------------------
# 15. No VALUE activation and no recommendation/ranking/target/probability/sizing (16)
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS = {
    "recommendation", "ranking", "target_price", "probability", "position_size",
    "sizing", "expected_return", "score", "cheap", "expensive",
}


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key).lower()
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def test_identity_inventory_contains_no_forbidden_authority_keys():
    artifact = {"records": {
        "OFF": _official_record("corporate"), "PRO": _provider_record("bank"), "UNK": _unknown_record(),
    }}
    inventory = ffcr.build_financial_identity_inventory(artifact, canonical_presence_by_ticker={})
    keys = set(_walk_keys(inventory))
    hits = keys & FORBIDDEN_KEYS
    assert not hits, f"forbidden authority keys leaked into inventory: {hits}"


def test_ai_handoff_projection_is_never_actionable():
    projection = ffcr.ai_handoff_financial_fact_projection(
        valuation_metric_row={"status": "READY", "first_blocker": None}, fundamental_record={"authority_tier": "OFFICIAL_QUALIFIED"},
    )
    assert projection["is_actionable"] is False
    assert "recommendation" not in projection
    assert "target_price" not in projection


# ---------------------------------------------------------------------------
# 17. AI handoff preserves fact-authority-state distinctions
# ---------------------------------------------------------------------------

def test_ai_handoff_projection_distinguishes_all_five_required_states():
    cases = [
        ({"status": "READY", "first_blocker": None}, {"authority_tier": "OFFICIAL_QUALIFIED"}, "OFFICIAL_QUALIFIED_FACT_AVAILABLE"),
        ({"status": "RESEARCH_USABLE", "first_blocker": None}, {"authority_tier": "OFFICIAL_QUALIFIED"}, "EXACT_RESEARCH_FINANCIAL_FACT_AVAILABLE"),
        ({"status": "BLOCKED", "first_blocker": None}, {"authority_tier": "PROVIDER_RESEARCH"}, "DESCRIPTIVE_PROVIDER_CONTEXT_ONLY"),
        ({"status": "NOT_APPLICABLE", "first_blocker": "NOT_APPLICABLE"}, {"authority_tier": "BLOCKED"}, "ENTITY_NOT_APPLICABLE"),
        ({"status": "BLOCKED", "first_blocker": "FINANCIAL_FACT_MISSING"}, {"authority_tier": "BLOCKED"}, "MISSING_FINANCIAL_FACT"),
    ]
    seen_labels = set()
    for metric_row, fundamental_record, expected_label in cases:
        projection = ffcr.ai_handoff_financial_fact_projection(valuation_metric_row=metric_row, fundamental_record=fundamental_record)
        assert projection["ai_handoff_financial_fact_state"] == expected_label
        seen_labels.add(expected_label)
    assert len(seen_labels) == 5


# ---------------------------------------------------------------------------
# 18. No network access anywhere in this module
# ---------------------------------------------------------------------------

def test_module_makes_no_network_calls():
    source = inspect.getsource(ffcr)
    for token in ("requests.", "urlopen", "http://", "https://", "socket.", "vnstock"):
        assert token not in source, f"unexpected network-related token in module: {token}"
