"""Retained PNJ/PVD/FPT acceptance and adversarial temporal/authority boundaries."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import long_term_company_economics_evidence as economics
from stocklookup_core.research.thesis_evidence_contract import make_item, verify_identity

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl"
CUTOFF = "2026-10-08T15:00:00+07:00"
BEFORE = "2026-10-07T15:00:00+07:00"


@pytest.fixture
def retained():
    # Read just the existing compact tracked overlay; no PDF/OCR, lake or T0 scan.
    return [json.loads(line) for line in OVERLAY.read_text(encoding="utf8").splitlines()
            if json.loads(line)["ticker"] in {"PNJ", "PVD", "FPT"}]


def build(retained, ticker="PNJ", **kwargs):
    return economics.build(ticker=ticker, knowledge_cutoff=kwargs.pop("knowledge_cutoff", CUTOFF),
                           official_rows=retained, **kwargs)


def observations(result, dimension):
    return result["dimensions"][dimension]["observations"]


@pytest.mark.parametrize("ticker,count", [("PNJ", 6), ("PVD", 7), ("FPT", 3)])
def test_exact_retained_sources_and_fitness_survive(retained, ticker, count):
    before = deepcopy(retained)
    result = build(retained, ticker)
    verify_identity(result, economics.CONTRACT_VERSION)
    actual = [o for d in result["dimensions"].values() for o in d["observations"]]
    assert len(actual) == count and retained == before
    for observation in actual:
        source = next(r for r in retained if r["citation_id"] == observation["source"]["citation_id"])
        for key in ("document_sha256", "citation_id", "source_page", "line_code",
                    "knowledge_available_at", "observed_at", "publication_date"):
            assert observation["source"][key] == source[key]
        assert observation["normalized_value"] == source["normalized_value"]
        assert observation["reporting_period"] == source["reporting_period"]
        assert observation["statement_scope"] == source["statement_scope"]
        assert observation["factual_status"] == "qualified"
        assert observation["assurance_reference"]["evidence_id"] == source["assurance_evidence"]["evidence_id"]
        assert observation["annualization"] == observation["ttm_derivation"] == "NOT_PERMITTED"
    assert not result["excluded_evidence"]
    assert result["flags"]["INSUFFICIENT_STRUCTURAL_EVIDENCE"]["status"] == "KNOWN"
    assert result["flags"]["STRUCTURAL_THESIS_SUPPORTED"]["status"] == "UNKNOWN"
    assert result["flags"]["STRUCTURAL_THESIS_CHALLENGED"]["status"] == "UNKNOWN"


def test_pnj_reviewed_income_and_provision_do_not_fill_missing_current_economics(retained):
    result = build(retained)
    income = observations(result, "revenue_profit_economics")
    assert {o["canonical_metric"]: o["normalized_value"] for o in income} == {
        "revenue": 25709196846401, "net_income": 728386009054,
        "attributable_net_income": 728529788872}
    assert {o["reporting_period"] for o in income} == {"2026-H1"}
    assert result["dimensions"]["revenue_profit_economics"]["observation_status"] == "KNOWN"
    assert result["dimensions"]["revenue_profit_economics"]["interpretation_status"] == "UNKNOWN"
    provision = observations(result, "earnings_quality")[0]
    assert provision["normalized_value"] == 2667248523366
    assert provision["recurrence_assessment"] == "UNKNOWN"
    assert provision["source"]["document_sha256"] == "db877169e7c19b4b81d60b37d5aab8f9938129a66b582c2229ffffebdca2a43d"
    for dimension in ("balance_sheet_resilience", "cash_generation_reinvestment"):
        assert result["dimensions"][dimension]["current_observation_status"] == "UNKNOWN"
        assert {o["reporting_period"] for o in observations(result, dimension)} == {"2025"}


def test_pvd_usd_interim_and_vnd_annual_are_separate_source_facts(retained):
    result = build(retained, "PVD")
    income = observations(result, "revenue_profit_economics")
    usd = [o for o in income if o["currency"] == "USD"]
    vnd = [o for o in income if o["currency"] == "VND"]
    assert {o["reporting_period"] for o in usd} == {"2026-H1"}
    assert {o["reporting_period"] for o in vnd} == {"2025"}
    assert {o["normalized_value"] for o in usd} == {245730824, 18272708, 17920760}
    assert {o["source"]["document_sha256"] for o in usd} == {"a7360d2fc9a8a67a1535820813cda2bb8ef288466cd36c949e050c2f2a1b290a"}
    assert {o["source"]["document_sha256"] for o in vnd} == {"6ee20a554891c449a8ee72fffe6358bc9b32145d066a7e52d8492d88f305139c"}
    assert all(o["valuation_use"] == "NOT_PERMITTED_FOREIGN_CURRENCY_CONTEXT" for o in usd)
    assert all(o["valuation_use"] == "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT" for o in vnd)
    assert result["dimensions"]["cyclicality"]["observation_status"] == "UNKNOWN"
    assert result["flags"]["CYCLICAL_RECOVERY_POSSIBLE"]["status"] == "UNKNOWN"


def test_fpt_annual_observations_leave_current_parent_earnings_and_shares_unknown(retained):
    result = build(retained, "FPT")
    actual = [o for d in result["dimensions"].values() for o in d["observations"]]
    assert {o["normalized_value"] for o in actual} == {70112825100710, 43748040747539, 651406282654}
    assert {o["reporting_period"] for o in actual} == {"2025"}
    assert {o["source"]["document_sha256"] for o in actual} == {"bb14bafff1a7849217f34cf4b50e0e3d69d91968f217a66d7c68f07d4c1af284"}
    assert all(o["temporal_status"] == "HISTORICAL_OFFICIAL_FACT" for o in actual)
    assert all(d["current_observation_status"] == "UNKNOWN" for d in result["dimensions"].values())
    assert "attributable_net_income" not in {o["canonical_metric"] for o in actual}
    assert result["strict_share_qualification"] == result["strict_valuation_qualification"] == "NOT_PROVIDED"


@pytest.mark.parametrize("ticker", ["PNJ", "PVD", "FPT"])
def test_unproven_recurrence_blocks_normalization_without_addbacks(retained, ticker):
    result = build(retained, ticker)
    assert result["normalization"]["status"] == "NORMALIZED_ECONOMICS_NOT_QUALIFIED"
    assert "RECURRENCE_TREATMENT_UNPROVEN" in result["normalization"]["blockers"]
    assert result["flags"]["EARNINGS_QUALITY_UNCERTAIN"]["status"] == "KNOWN"
    assert result["flags"]["VALUATION_UNQUALIFIED"]["status"] == "KNOWN"
    assert result["dimensions"]["earnings_quality"]["interpretation_status"] == "UNKNOWN"
    assert "normalized_eps" not in json.dumps(result)


@pytest.mark.parametrize("ticker,expected", [("PNJ", 3), ("PVD", 3), ("FPT", 0)])
def test_october7_keeps_old_facts_and_excludes_october8_knowledge(retained, ticker, expected):
    result = build(retained, ticker, knowledge_cutoff=BEFORE)
    actual = [o for d in result["dimensions"].values() for o in d["observations"]]
    assert len(actual) == expected
    assert all(economics._time(o["source"]["knowledge_available_at"]) <= economics._time(BEFORE) for o in actual)
    assert all("KNOWLEDGE_AVAILABLE_AT_AFTER_CUTOFF" in r["reasons"] for r in result["excluded_evidence"])
    if ticker == "FPT":
        assert all(d["observation_status"] == "UNKNOWN" for d in result["dimensions"].values())


def test_later_conflicting_revision_cannot_poison_earlier_cutoff(retained):
    row = deepcopy(next(r for r in retained if r["ticker"] == "PNJ" and r["canonical_metric"] == "revenue"))
    row["normalized_value"] += 1
    row["knowledge_available_at"] = "2026-10-09T00:00:00Z"
    result = build(retained + [row])
    assert len(observations(result, "revenue_profit_economics")) == 3
    assert result["excluded_evidence"][0]["reasons"] == ["KNOWLEDGE_AVAILABLE_AT_AFTER_CUTOFF"]


def test_known_conflict_blocks_exact_fact_and_duplicates_do_not_add_coverage(retained):
    assert build(retained) == build(list(reversed(retained)) + deepcopy(retained))
    row = deepcopy(next(r for r in retained if r["ticker"] == "PNJ" and r["canonical_metric"] == "revenue"))
    row["normalized_value"] += 1
    result = build(retained + [row])
    assert "revenue" not in {o["canonical_metric"] for o in observations(result, "revenue_profit_economics")}
    assert all("TRUE_CONFLICT" in r["reasons"] for r in result["excluded_evidence"])


@pytest.mark.parametrize("change", [
    {"knowledge_available_at": None}, {"knowledge_available_at": "2026-10-08T01:00:00"},
    {"observed_at": "2026-10-09T00:00:00Z"}, {"publication_date": "2026-10-09"},
    {"qualification_state": "BLOCKED"}, {"unit_scale": 1000}, {"currency": "EUR"},
    {"assurance_evidence": {}}, {"document_sha256": ""}, {"normalized_value": True},
    {"normalized_value": float("nan")}, {"statement_scope": "parent_only"},
])
def test_bad_source_time_value_and_fitness_fail_closed(retained, change):
    rows = deepcopy(retained)
    row = next(r for r in rows if r["ticker"] == "PNJ" and r["canonical_metric"] == "revenue")
    row.update(change)
    result = build(rows)
    assert "revenue" not in {o["canonical_metric"] for o in observations(result, "revenue_profit_economics")}
    assert result["excluded_evidence"]


def context(axis, state="UNKNOWN", sub_axis="profitability", contract="financial_analysis_context/v2"):
    item = make_item(ticker="PNJ", session="2026-10-08", axis=axis, sub_axis=sub_axis,
                     state=state, source={"identity": "retained:synthetic", "contract_version": contract,
                                          "pointer": "/records/PNJ"}, fact_eligible=True,
                     facts=[{"name": "profitability_state", "value": "PROFITABLE", "semantic": "PROVIDER_REPORTED_STATE",
                             "unit": "STATE", "fitness": "RESEARCH_PROXY", "source_pointer": "/records/PNJ/states"}])
    return {"item": item, "observed_at": "2026-10-08T01:00:00Z", "knowledge_available_at": "2026-10-08T01:00:00Z"}


def test_provider_profit_tactical_adversity_sector_leadership_never_vote_on_core(retained):
    items = [context("FUNDAMENTAL", "SUPPORTS"), context("TECHNICAL", "OPPOSES", "trend", "contextual_technical_features/v2"),
             context("MACRO_SECTOR", "SUPPORTS", "sector", "sector_relative_research_context/v1")]
    before = deepcopy(items)
    result = build(retained, context_items=items)
    assert items == before and len(result["research_context"]) == 3
    assert build(retained)["flags"] == result["flags"]
    assert all(d["interpretation_status"] == "UNKNOWN" for d in result["dimensions"].values())
    assert result["research_context"][0]["authority"] == "RESEARCH_CONTEXT_ONLY_NOT_QUALIFIED_COMPANY_ECONOMICS"
    assert not build([], context_items=[items[0]])["dimensions"]["revenue_profit_economics"]["observations"]


def test_context_identity_subject_and_knowledge_are_required(retained):
    envelope = context("FUNDAMENTAL")
    envelope["item"]["state"] = "SUPPORTS"
    with pytest.raises(ValueError, match="CONTENT_IDENTITY"):
        build(retained, context_items=[envelope])
    envelope = context("FUNDAMENTAL")
    envelope["knowledge_available_at"] = "2026-10-09T00:00:00Z"
    assert not build(retained, context_items=[envelope])["research_context"]
    with pytest.raises(ValueError, match="SUBJECT_MISMATCH"):
        build(retained, "FPT", context_items=[context("FUNDAMENTAL")])


def valuation(method="P/B", status="READY_RESEARCH_ONLY", percentile=0.9):
    return {"observed_at": "2026-10-08T01:00:00Z", "knowledge_available_at": "2026-10-08T01:00:00Z",
            "payload": {"source_identity": "valuation:synthetic", "session": "2026-10-08", "fitness": "READY_RESEARCH",
                        "relative_research_state": "EXPENSIVE_RELATIVE_RESEARCH",
                        "peer_methods": {method: {"status": status, "percentile": percentile, "peer_count": 12, "basis": {"method_id": method}}}}}


@pytest.mark.parametrize("method,status,percentile,qualified", [
    ("P/B", "READY_RESEARCH_ONLY", 0.9, True), ("P/B", "BLOCKED", 0.9, False),
    ("market_cap", "READY_RESEARCH_ONLY", 0.9, False), ("P/B", "READY_RESEARCH_ONLY", 0.1, False),
])
def test_valuation_trim_context_requires_actual_method_fitness_but_keeps_strict_gates_closed(retained, method, status, percentile, qualified):
    result = build(retained, valuation_context=valuation(method, status, percentile))
    dimension = result["dimensions"]["valuation_fitness"]
    assert dimension["research_context"][0]["valuation_qualified"] is qualified
    assert dimension["interpretation_status"] == ("PARTIALLY_KNOWN" if qualified else "UNKNOWN")
    assert result["flags"]["VALUATION_UNQUALIFIED"]["status"] == "KNOWN"
    assert result["strict_valuation_qualification"] == "NOT_PROVIDED"
    assert "VALUATION_TRIM_REVIEW" not in json.dumps(result)


def test_late_or_wrong_session_valuation_cannot_enter_matrix(retained):
    source = valuation()
    source["knowledge_available_at"] = "2026-10-09T00:00:00Z"
    assert not build(retained, valuation_context=source)["dimensions"]["valuation_fitness"]["research_context"]
    source = valuation()
    source["payload"]["session"] = "2026-10-07"
    with pytest.raises(ValueError, match="SESSION_MISMATCH"):
        build(retained, valuation_context=source)


def test_no_cutoff_no_build_and_no_missing_evidence_as_negative(retained):
    with pytest.raises(ValueError, match="TIMEZONE"):
        build(retained, knowledge_cutoff="2026-10-08")
    result = build([])
    assert set(result["dimensions"]) == set(economics.DIMENSIONS)
    assert all(d["observation_status"] == d["interpretation_status"] == "UNKNOWN" for d in result["dimensions"].values())
    assert result["flags"]["STRUCTURAL_THESIS_CHALLENGED"]["status"] == "UNKNOWN"


def test_human_view_has_exact_source_references_and_no_new_action_or_engine(retained):
    result = build(retained)
    text = economics.render_research_boundaries(result)
    for row in retained:
        if row["ticker"] == "PNJ":
            assert row["document_sha256"] in text and row["citation_id"] in text
            assert row["knowledge_available_at"] in text and row["observed_at"] in text
    assert result["non_voting"] is True and result["is_actionable"] is False
    forbidden = {"research_action_posture", "score", "probability", "target_price", "size", "leverage", "execution_action"}
    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(result)


# Canonical full-output hashes captured from approved candidate 99b2c9a before
# removing its Stage 1 dependency. Equality includes every fact, restriction,
# source reference, unknown state and identity; it is not just value parity.
@pytest.mark.parametrize("ticker,cutoff,expected", [
    ("PNJ", BEFORE, "ea079afd26e147f2374eabb96e8d516944c5d0b3d781e90f4213aa3c5e5b1faa"),
    ("PNJ", CUTOFF, "4cba4ac02b36d3a0fad56105e32f7f7148e7ebf83f0e444481ed9746a19ba22f"),
    ("PVD", BEFORE, "fbd5f42b1beb537094e236f91e986b129e682988c6a7a9b365ea98ee28cb28fd"),
    ("PVD", CUTOFF, "e1bcd0f7644beca7380f4c553809f8c29ce24a703d7a16a3637105760d691e4e"),
    ("FPT", BEFORE, "f950238e7885bb97a6dbf1d69f2d652676b1b440edbc9f237a6b9fa233a4f41f"),
    ("FPT", CUTOFF, "c345b485582620a20b73161d1e86796000b34b4fd922a9c00e535249de00dff3"),
])
def test_corrective_preserves_exact_approved_issuer_output(retained, ticker, cutoff, expected):
    result = build(retained, ticker, knowledge_cutoff=cutoff)
    assert result["artifact_sha256"] == expected
    assert result == build(list(reversed(retained)) + deepcopy(retained), ticker, knowledge_cutoff=cutoff)


@pytest.mark.parametrize("kind,expected", [
    ("context", "ed47fb21e3add7307d69a818fac50854c6233ab3a694fe4c89087fb642a8954c"),
    ("valuation", "f9942cf38e250b726ad0db0b5cda466487f62fee2e885c798b81456b6114affe"),
])
def test_corrective_preserves_exact_valid_reference_output(retained, kind, expected):
    kwargs = {"context_items": [context("FUNDAMENTAL", "SUPPORTS")]} if kind == "context" else {"valuation_context": valuation()}
    result = build(retained, **kwargs)
    assert result["artifact_sha256"] == expected
    assert result == build(list(reversed(retained)), **kwargs)


@pytest.mark.parametrize("key", ["overallScore", "probability", "forecast-return", "confidence", "weighted", "rating"])
def test_independent_consumer_preserves_nested_forbidden_key_semantics(retained, key):
    from stocklookup_core.research.thesis_evidence_contract import seal
    envelope = context("FUNDAMENTAL")
    envelope["item"]["coverage"] = {"nested": [{key: 1}]}
    envelope["item"] = seal(envelope["item"], "evidence_item/v1")
    with pytest.raises(ValueError, match="FORBIDDEN_JUDGMENT_FIELD"):
        build(retained, context_items=[envelope])


@pytest.mark.parametrize("change", [
    {"source": {"identity": "", "contract_version": "financial_analysis_context/v2", "pointer": "/records/PNJ"}},
    {"fitness": {"fact_eligible": 1, "direction_eligible": False}},
    {"state": "UNMAPPED"}, {"non_voting": False}, {"is_actionable": True},
    {"lens_binding": {"LONG_TERM_INVESTOR": "CONTEXT"}},
    {"factual_values": [{"name": "profit", "value": 1}]},
    {"knowledge_stage": "T0_SEALED", "seal_reference": None},
])
def test_independent_reference_verifier_keeps_source_schema_and_authority_gates(retained, change):
    from stocklookup_core.research.thesis_evidence_contract import seal, verify_item
    envelope = context("FUNDAMENTAL")
    envelope["item"].update(change)
    envelope["item"] = seal(envelope["item"], "evidence_item/v1")
    with pytest.raises(ValueError):
        verify_item(envelope["item"])
    with pytest.raises(ValueError):
        build(retained, context_items=[envelope])


def test_independent_seal_and_scanner_do_not_sanitize_nonfinite_values():
    from stocklookup_core.research.thesis_evidence_contract import seal, scan_forbidden
    for value in (float("nan"), float("inf"), float("-inf")):
        payload = {"fact": [value]}
        for sealer in (seal, economics._seal):
            with pytest.raises(ValueError):
                sealer(payload, "evidence_item/v1")
        for scanner in (scan_forbidden, economics._scan_forbidden):
            with pytest.raises(ValueError, match="NON_FINITE_FACT"):
                scanner(payload)
