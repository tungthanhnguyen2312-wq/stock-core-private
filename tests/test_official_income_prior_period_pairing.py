"""Prior-period pairing: qualified cross-document pairs, adversarial semantics and portable real data."""
import copy
import inspect
import json
from pathlib import Path

import pytest

import market_wide_current_fundamental_research as fundamental
from stocklookup_core.financial.fundamental_signal_consumption_contract import official_income_research_context
from stocklookup_core.financial.official_income_prior_period_pairing import (
    COMPARATIVE_GATE, OWNER_GATES, UNREVIEWED_GATE, attach_prior_period_pairing, literal_row_identity,
    load_comparative_column_observations, load_prior_official_income_rows, official_income_prior_period_context,
    prior_rows_from_governed_citations, prior_rows_from_promoted_closeout, validate_comparative_observation,
)
from stocklookup_core.financial.official_income_prior_period_pairing import _hash
from tools.run_comparative_column_observations import observations_for_document, period_label_binding

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "derived/financial-evidence-currency-refresh-v1"
CUTOFF = "2026-10-23T15:00:00+07:00"
SHA_CURRENT, SHA_PRIOR = "c" * 64, "a" * 64


def current(metric="net_income", value=120, *, period="2025", start="2025-01-01", end="2025-12-31", **overrides):
    line = {"revenue": "10", "net_income": "60", "attributable_net_income": "61"}[metric]
    return dict(ticker="SYN", canonical_metric=metric, line_code=line, normalized_value=value, unit_scale=1,
                already_normalized=True, currency="VND", statement_family="income_statement",
                statement_scope="consolidated", reporting_period=period, period_type="annual" if len(period) == 4 else "interim",
                period_start=start, period_end=end, qualification_state="QUALIFIED", factual_status="qualified",
                audit_or_review_status="audited", document_sha256=SHA_CURRENT, citation_id=f"current:{metric}:{period}",
                source_identity="official:current", knowledge_available_at="2026-10-07T15:33:12Z") | overrides


def record(*facts, entity="corporate"):
    rec = {"entity_class": entity, "official_field_context": list(facts)}
    rec["official_income_research_context"] = official_income_research_context(rec, cutoff=CUTOFF, ticker="SYN")
    return rec


def governed(value=100, *, label="Lợi nhuận sau thuế thu nhập doanh nghiệp", metric="net_income", period="2024",
             currency="VND", scope="consolidated", evidence="ev1", verified="2026-08-09T00:00:00Z", **overrides):
    citation = {"ticker": "SYN", "metric": metric, "reporting_period": period, "reporting_frequency": "annual",
                "value": value, "currency": currency, "unit_scale": 1, "statement_scope": scope,
                "citation_id": f"prior:{metric}:{period}:{value}", "evidence_id": evidence, "verified_at": verified,
                "extraction": {"raw_labels": [label], "source_pages": [11]}} | overrides
    return citation


MANIFEST = [{"evidence_id": "ev1", "sha256": SHA_PRIOR, "document_class": "audited_annual_financial_statements",
             "audit_status": "audited", "qualification_state": "qualified", "published_at": "2025-03-24",
             "source_url": "https://issuer.example/fy2024.pdf"}]


def prior(*citations, manifest=MANIFEST, corrections=()):
    return prior_rows_from_governed_citations(citations, manifest, corrections)


def observation(value, *, metric="net_income", period="2024", start="2024-01-01", end="2024-12-31", raw=None,
                blockers=(), known="2026-10-23T05:00:00Z"):
    row = {"contract_version": "comparative_column_observation/v1", "ticker": "SYN", "canonical_metric": metric,
           "line_code": {"revenue": "10", "net_income": "60"}[metric],
           "accounting_identity": {"revenue": "NET_REVENUE", "net_income": "TOTAL_PROFIT_AFTER_TAX"}[metric],
           "reporting_period": period, "period_start": start, "period_end": end, "value": value,
           "raw_token": raw if raw is not None else str(value), "currency": "VND", "statement_scope": "consolidated",
           "source_document_sha256": SHA_CURRENT, "source_page": 10, "blockers": list(blockers),
           "knowledge_available_at": known, "admission_state": "CANDIDATE_OWNER_GATE",
           "existing_consumer_usable": False, "official_fact_admitted": False}
    row["observation_id"] = _hash({k: row.get(k) for k in (
        "ticker", "canonical_metric", "reporting_period", "source_document_sha256", "source_page", "raw_token")})
    return row


def pair(rec, prior_rows, observations=(), **kwargs):
    return official_income_prior_period_context(rec, prior_rows=prior_rows, comparative_observations=observations,
                                                cutoff=kwargs.pop("cutoff", CUTOFF), ticker="SYN", **kwargs)


def reasons(result):
    return {code for row in result["rejected"] for code in row["reason_codes"]}


def test_independent_audited_prior_pairs_and_comparative_column_corroborates():
    rec = record(current(value=120))
    saved = copy.deepcopy(rec)
    result = pair(rec, prior(governed(100)), [observation(100)])
    comparison, = result["comparisons"]
    assert (comparison["prior_value"], comparison["current_value"], comparison["direction"]) == (100, 120, "INCREASED")
    assert comparison["growth_ratio"] == pytest.approx(0.2)
    assert comparison["restatement_check"] == "COMPARATIVE_COLUMN_MATCHES_ORIGINAL"
    assert comparison["prior_basis"] == "INDEPENDENTLY_QUALIFIED_ORIGINAL_REPORT"
    assert result["earnings_direction_research"] == "INCREASED" and result["direction_status"] == "MEASURED_REPORTED_CHANGE"
    assert (result["vote_effect"], result["strict_valuation_effect"], result["ttm_effect"], result["is_actionable"]) == (
        "NONE", "NONE", "NONE", False)
    assert rec == saved


def test_wrong_comparative_period_never_pairs():
    result = pair(record(current()), prior(governed(100, period="2023")))
    assert not result["comparisons"] and "NO_INDEPENDENTLY_QUALIFIED_PRIOR_PERIOD_FACT" in reasons(result)
    assert period_label_binding("Kỳ này", "Kỳ trước", current_year=2026) == "PRIOR_PERIOD_PHRASE_YEAR_NOT_LITERAL"
    assert period_label_binding("2025", "2024", current_year=2025) == "EXPLICIT_PRIOR_YEAR_LABEL"
    assert period_label_binding("Năm nay", "Năm trước", current_year=2025) == "PRIOR_YEAR_PHRASE"
    assert period_label_binding("2025", "2023", current_year=2025) == "UNBOUND"


def test_wrong_accounting_scope_or_currency_refuses_without_conversion():
    separate = pair(record(current()), prior(governed(100, scope="standalone")))
    usd = pair(record(current()), prior(governed(100, currency="USD")))
    assert not separate["comparisons"] and "PRIOR_STATEMENT_SCOPE_DIFFERS" in reasons(separate)
    assert not usd["comparisons"] and "PRIOR_CURRENCY_DIFFERS_NO_FX" in reasons(usd)


def test_unreviewed_tier_cannot_cross_d1_and_preview_stays_disabled():
    unreviewed = [dict(ticker="SYN", canonical_metric="net_income", value=v, reporting_period=p, column_role=role,
                       evidence_tier="UNREVIEWED_QUARTERLY", document_sha256="q" * 64,
                       knowledge_available_at="2026-09-29T11:31:14Z")
                  for v, p, role in ((50, "2026-Q2", "CURRENT_QUARTER"), (40, "2025-Q2", "PRIOR_YEAR_QUARTER"))]
    rec = record(current(), current(audit_or_review_status="unreviewed", evidence_tier="UNREVIEWED_QUARTERLY",
                                    citation_id="unreviewed"))
    default = pair(rec, prior(governed(100)), unreviewed_rows=unreviewed)
    assert all(c["current_citation_id"] != "unreviewed" for c in default["comparisons"])
    assert default["owner_gated_preview"]["unreviewed_quarterly_comparisons"] == []
    gated = pair(rec, prior(governed(100)), unreviewed_rows=unreviewed, enabled_owner_gates=[UNREVIEWED_GATE])
    preview, = gated["owner_gated_preview"]["unreviewed_quarterly_comparisons"]
    assert preview["d1_existing_consumer_usable"] is False and preview["direction"] == "INCREASED"
    assert gated["comparisons"] == default["comparisons"]
    unreviewed_prior = prior(governed(100), manifest=[MANIFEST[0] | {"audit_status": "unreviewed"}])
    assert "APPROVED_AUDITED_OR_REVIEWED_STATEMENT_DOCUMENT_REQUIRED" in unreviewed_prior[0]["reason_codes"]


def test_quarter_ytd_and_half_year_never_mix_with_annual():
    h1 = record(current(period="2026-H1", start="2026-01-01", end="2026-06-30", audit_or_review_status="reviewed"))
    nine_month = record(current(period="2026-Q3", start="2026-01-01", end="2026-09-30", period_type="nine_month",
                                audit_or_review_status="reviewed"))
    for rec in (h1, nine_month):
        result = pair(rec, prior(governed(100, period="2025")))
        assert not result["comparisons"]
    quarterly_citation = prior(governed(100, reporting_frequency="quarter"))
    assert "EXPLICIT_ANNUAL_PERIOD_REQUIRED" in quarterly_citation[0]["reason_codes"]
    result = pair(record(current()), quarterly_citation)
    assert result["ttm_inputs"]["status"] == "UNAVAILABLE"
    assert result["ttm_inputs"]["synthetic_q4_or_ytd_subtraction"] == "NOT_PERMITTED"


def test_misidentified_ocr_row_is_not_admitted():
    parent = prior(governed(100, label="Lợi nhuận sau thuế của công ty mẹ"))
    assert parent[0]["admission_state"] == "BLOCKED"
    assert "PRIOR_ROW_LITERAL_IDENTITY_NOT_PROVEN" in parent[0]["reason_codes"]
    assert literal_row_identity("revenue", "Doanh thu thudn") is None  # OCR damage is never repaired
    assert literal_row_identity("revenue", "Doanh thu thuan") == "NET_REVENUE"
    facts = [current("net_income", 120), current("attributable_net_income", 110)]
    box = {"x0": 1, "x1": 2}
    qualification = {"qualified_facts": [
        {"canonical_metric": metric, "value": value, "currency": "VND", "unit_scale": 1,
         "source_lineage": {"line_code": line, "source_page": 10, "row_object": {
             "current_period_label": "Năm nay", "comparative_period_label": "Năm trước",
             "comparative_value_bbox": box, "current_value_bbox": {"x0": value}},
             "ocr_derived_text_evidence": {"comparative_raw": "100", "materialization_id": "m"}}}
        for metric, value, line in (("net_income", 120, "60"), ("attributable_net_income", 110, "61"),
                                    ("revenue", 999, "10"))]}
    rows = observations_for_document(facts, qualification, observed_at="2026-10-23T05:00:00Z")
    assert len(rows) == 2  # revenue's current value differs from any admitted row: no observation
    assert all("COMPARATIVE_TOKEN_SHARED_ACROSS_ROWS" in row["blockers"] for row in rows)


def test_false_reconciliation_does_not_prove_identity():
    unlabelled = prior(governed(100, label="Doanh thu", metric="revenue"))
    result = pair(record(current("revenue", 120)), unlabelled, [observation(100, metric="revenue")])
    assert not result["comparisons"]
    assert "PRIOR_ROW_LITERAL_IDENTITY_NOT_PROVEN" in reasons(result)


def test_restated_later_comparative_refuses_and_gate_never_substitutes():
    rec = record(current(value=120))
    for gates in ((), OWNER_GATES):
        result = pair(rec, prior(governed(100)), [observation(95)], enabled_owner_gates=gates)
        assert not result["comparisons"] and "PRIOR_PERIOD_DIFFERS_IN_LATER_REPORT" in reasons(result)
        assert result["owner_gated_preview"]["comparative_column_comparisons"] == []
    ambiguous = pair(rec, prior(governed(100)), [observation(None, raw="1²0", blockers=["OCR_NUMERIC_AMBIGUITY"])])
    assert ambiguous["comparisons"][0]["restatement_check"] == "COMPARATIVE_CROSS_CHECK_OCR_AMBIGUOUS"


def test_comparative_only_pair_requires_explicit_owner_gate():
    rec = record(current(value=120))
    default = pair(rec, [], [observation(100)])
    assert not default["comparisons"] and default["owner_gated_preview"]["comparative_column_comparisons"] == []
    gated = pair(rec, [], [observation(100)], enabled_owner_gates=[COMPARATIVE_GATE])
    preview, = gated["owner_gated_preview"]["comparative_column_comparisons"]
    assert preview["prior_basis"] == "COMPARATIVE_COLUMN_OF_LATER_REPORT" and not gated["comparisons"]
    blocked = pair(rec, [], [observation(100, blockers=["COMPARATIVE_PERIOD_LABEL_NOT_YEAR_BOUND"])],
                   enabled_owner_gates=[COMPARATIVE_GATE])
    assert blocked["owner_gated_preview"]["comparative_column_comparisons"] == []
    with pytest.raises(ValueError, match="UNKNOWN_OWNER_GATE"):
        pair(rec, [], enabled_owner_gates=["ADMIT_EVERYTHING"])


def test_unsupported_historical_known_at_is_excluded():
    late_prior = pair(record(current()), prior(governed(100, verified="2026-10-24T00:00:00Z")))
    assert not late_prior["comparisons"] and "PRIOR_FACT_NOT_KNOWN_AT_CUTOFF" in reasons(late_prior)
    late_observation = pair(record(current(value=120)), prior(governed(100)),
                            [observation(95, known="2026-10-24T00:00:00Z")])
    assert late_observation["comparisons"][0]["restatement_check"] == "COMPARATIVE_CROSS_CHECK_NOT_AVAILABLE"
    assert late_observation["owner_gated_preview"]["comparative_candidate_count"] == 0


def test_missing_eligible_components_and_semantic_corrections_block():
    no_document = prior(governed(100, evidence="missing"))[0]
    assert "QUALIFIED_SOURCE_DOCUMENT_IDENTITY_REQUIRED" in no_document["reason_codes"]
    corrected = prior(governed(100), corrections=[{"ticker": "SYN", "old_metric": "net_income", "reporting_period": "2024",
                                                   "old_value": 100, "supersedes_fact_identity": {}}])[0]
    assert "HISTORICAL_SEMANTIC_CORRECTION_SUPERSEDES_ROW" in corrected["reason_codes"]
    conflicting = pair(record(current()), prior(governed(100), governed(101)))
    assert "CONFLICTING_QUALIFIED_PRIOR_PERIOD_VALUES" in reasons(conflicting)
    bank = pair(record(current(), entity="bank"), prior(governed(100)))
    assert not bank["comparisons"]


def test_no_qualifying_data_is_unknown_not_an_error(tmp_path):
    result = pair({"entity_class": "corporate"}, [])
    assert result["direction_status"] == "UNKNOWN"
    assert "NO_ADMITTED_CURRENT_OFFICIAL_INCOME_FACT" in result["blocker_reason_codes"]
    loaded = load_prior_official_income_rows(runtime_root=tmp_path, repo_root=tmp_path)
    assert loaded == {"rows": [], "load_blockers": ["GOVERNED_OFFICIAL_EVIDENCE_NOT_RETAINED_ON_HOST"]}


def test_producer_wiring_is_opt_in_and_additive():
    assert inspect.signature(fundamental.project_session).parameters["prior_period_inputs"].default is None
    records = {"SYN": record(current(value=120)), "BLK": {"entity_class": "corporate"}}
    original = copy.deepcopy(records)
    attach_prior_period_pairing(records, prior_rows=prior(governed(100)), cutoff=CUTOFF)
    pairing = records["SYN"]["official_income_research_context"].pop("prior_period_pairing")
    assert pairing["direction_status"] == "MEASURED_REPORTED_CHANGE"
    assert records == original


def test_committed_comparative_observations_and_real_hpg_revenue_pair():
    future = "2026-10-26T15:00:00+07:00"  # observations were re-read after the 2026-10-23 cutoff
    observations = load_comparative_column_observations(PUBLIC)
    assert observations and not any(validate_comparative_observation(row) for row in observations)
    assert not any(row["admission_state"] == "QUALIFIED" or row["existing_consumer_usable"] for row in observations)
    from stocklookup_core.financial.multi_period_financial_panel import load_promoted_fundamental_coverage_closeout_citations
    documents = json.loads((ROOT / "config/promoted_fundamental_coverage_closeout_evidence.json").read_text(encoding="utf-8"))
    rows = prior_rows_from_promoted_closeout(load_promoted_fundamental_coverage_closeout_citations(ROOT),
                                             documents["evidence_documents"])
    hpg_prior = [row for row in rows if row["ticker"] == "HPG" and row["canonical_metric"] == "revenue"]
    assert hpg_prior[0]["admission_state"] == "QUALIFIED_PRIOR_PERIOD_FACT"
    facts = [json.loads(line) for line in (PUBLIC / "qualified_official_facts.jsonl").read_text(encoding="utf-8").splitlines()]
    hpg = [row | {"factual_status": "qualified", "source_identity": "official-document:" + row["document_sha256"]}
           for row in facts if row["ticker"] == "HPG" and row["canonical_metric"] == "revenue"]
    rec = {"entity_class": "corporate", "official_field_context": hpg}
    rec["official_income_research_context"] = official_income_research_context(rec, cutoff=CUTOFF, ticker="HPG")
    result = official_income_prior_period_context(rec, prior_rows=rows, comparative_observations=observations,
                                                  cutoff=future, ticker="HPG")
    comparison, = result["comparisons"]
    assert (comparison["prior_value"], comparison["current_value"]) == (138855112131387, 156116094618482)
    assert comparison["restatement_check"] == "COMPARATIVE_COLUMN_MATCHES_ORIGINAL"
    sealed = official_income_prior_period_context(rec, prior_rows=rows, comparative_observations=observations,
                                                  cutoff=CUTOFF, ticker="HPG")
    assert sealed["comparisons"][0]["restatement_check"] == "COMPARATIVE_CROSS_CHECK_NOT_AVAILABLE"
    year_unbound = [row for row in observations if row["period_type"] == "interim"]
    assert year_unbound and all("COMPARATIVE_PERIOD_LABEL_NOT_YEAR_BOUND" in row["blockers"] for row in year_unbound)
