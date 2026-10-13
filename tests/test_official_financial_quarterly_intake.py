"""Candidate semantics are separate from source admission; fixtures grant no authority."""
import copy
import hashlib

import pytest

from official_financial_period_identity import recognize_statement_period
from stocklookup_core.financial.structured_financial_period_semantics import recognize_reported_column_period
from official_financial_value_evidence import parse_accounting_integer
from stocklookup_core.evidence.approved_issuer_ir_financial_evidence import prepare_financial_intake_candidate, APPROVED_ROUTES
from stocklookup_core.evidence.financial_row_identity import resolve_reported_row_identity


def inputs(*, family="income_statement", code="10", label="Net sales", period="2026-Q3", value="3,187,288,759,647", scope="consolidated"):
    raw = f"SYNTHETIC OFFLINE SOURCE. {label} {value}".encode()
    sha = hashlib.sha256(raw).hexdigest()
    document = dict(ticker="KBC", issuer_identity="KBC", sha256=sha, source_id="issuer_ir",
                    source_url="https://kinhbaccity.vn/test.pdf", document_class="quarterly_financial_statements",
                    statement_scope=scope, currency="VND", unit_scale=1, page_count=57,
                    audit_or_review_status="unreviewed", assurance_scope="INSPECTED_FRONT_MATTER_ONLY",
                    observed_at="2026-10-13T08:20:56+07:00", published_at=None)
    candidate = dict(ticker="KBC", document_sha256=sha, statement_family=family, line_code=code,
                     raw_row_label=label, raw_value_text=value, native_period_label=period,
                     statement_scope=scope, currency="VND", unit_scale=1, source_page=9,
                     source_span=dict(document_sha256=sha, citation_id="review-p9", source_page=9, text=f"{label} {value}"),
                     periodicity="quarterly", knowledge_available_at="2026-10-13T08:20:56+07:00")
    return candidate, document, raw


def prepared(candidate=None, document=None, raw=None, **changes):
    if candidate is None:
        candidate, document, raw = inputs(**changes)
    return prepare_financial_intake_candidate(candidate, document=document, retained_bytes=raw,
        value_parser=parse_accounting_integer, period_resolver=recognize_reported_column_period,
        cutoff="2026-10-13T15:00:00+07:00")


def test_quarter_and_cumulative_values_are_candidates_not_official_facts():
    q3 = prepared()
    cumulative = prepared(period="2026-9M", value="5,111,910,086,988")
    assert q3["candidate"]["normalized_value"] == 3187288759647
    assert cumulative["candidate"]["normalized_value"] == 5111910086988
    assert q3["semantic_valid"] and cumulative["semantic_valid"]
    assert q3["candidate"]["period_semantic_state"] == "STANDALONE_QUARTER"
    assert cumulative["candidate"]["period_semantic_state"] == "YTD_CUMULATIVE_INTERIM"
    assert "TICKER_NOT_IN_APPROVED_COHORT" in q3["source_admission_blockers"]
    assert not q3["official_fact_admitted"] and not q3["existing_consumer_usable"]
    assert q3["knowledge_cutoff_eligible"]
    assert "SOURCE_PUBLICATION_TIMESTAMP_UNKNOWN_NO_HISTORICAL_PIT" in q3["publication_blockers"]
    assert "HPG" not in APPROVED_ROUTES and "KBC" not in APPROVED_ROUTES


def test_existing_q3_source_gate_is_unchanged():
    assert recognize_statement_period("Quarter 3 2026")["status"] == "OUT_OF_SCOPE_Q3_2026"


@pytest.mark.parametrize("label,period,state", [
    ("Quarter III 2026", "2026-Q3", "STANDALONE_QUARTER"),
    ("2026-Q3", "2026-Q3", "STANDALONE_QUARTER"),
    ("2026-9m", "2026-9M", "YTD_CUMULATIVE_INTERIM"),
    ("nine months ended September 30 2026", "2026-9M", "YTD_CUMULATIVE_INTERIM"),
    ("2026-H1", "2026-H1", "UNKNOWN_DURATION"),
    ("Six-month period ended 30 June 2026", "2026-H1", "UNKNOWN_DURATION"),
])
def test_column_period_never_invents_covered_dates(label, period, state):
    result = recognize_reported_column_period(label, statement_family="income_statement")
    assert result["reporting_period"] == period and result["period_semantic_state"] == state
    assert result["period_start"] is None and result["period_end"] is None


def test_quarter_vs_nine_months_ambiguous_header_is_not_a_column():
    result = recognize_reported_column_period("2026-Q3 and 2026-9M", statement_family="income_statement")
    assert "QUARTER_CUMULATIVE_COLUMN_AMBIGUOUS" in result["blockers"]


def test_total_parent_and_separate_profits_never_alias():
    total = prepared(code="60", label="Profit after tax", value="937,236,264,331")
    parent = prepared(code="61", label="Profit attributable to the parent", value="911,255,360,018")
    separate = prepared(code="60", label="Profit after tax", value="542,827,055,633", scope="standalone")
    assert total["candidate"]["canonical_metric"] == "net_income"
    assert parent["candidate"]["canonical_metric"] == "attributable_net_income"
    assert separate["candidate"]["statement_scope"] == "standalone"
    assert {r["candidate"]["value"] for r in (total, parent, separate)} == {937236264331, 911255360018, 542827055633}
    assert "PARENT_PROFIT_IS_NOT_TOTAL_NET_INCOME" in parent["valuation_blockers"]
    wrong = resolve_reported_row_identity("income_statement", "60", "Profit attributable to the parent")
    assert wrong["blockers"]


def test_cash_flow_negative_and_nine_months_not_q3():
    result = prepared(family="cash_flow", code="20", label="Net cash used in operating activities",
                      period="2026-9M", value="(7,265,926,402,957)")
    assert result["semantic_valid"]
    assert result["candidate"]["value"] == -7265926402957
    wrong = prepared(family="cash_flow", code="20", label="Net cash used in operating activities", period="2026-Q3")
    assert "CASH_FLOW_QUARTER_DURATION_NOT_PROVEN" in wrong["semantic_blockers"]


def test_equity_including_nci_and_lease_debt_stay_distinct():
    equity = prepared(family="balance_sheet", code="400", label="Owners' equity", period="2026-09-30")
    # Instant without an explicitly proven date remains blocked.
    assert "BALANCE_INSTANT_NOT_PROVEN" in equity["semantic_blockers"]
    assert "TOTAL_EQUITY_IS_NOT_PARENT_BOOK_EQUITY" in equity["valuation_blockers"]
    debt = prepared(family="balance_sheet", code="321", label="Short-term borrowings and finance lease liabilities", period="2026-09-30")
    assert debt["candidate"]["canonical_metric"] is None
    assert "LEASE_INCLUSIVE_LOANS_ARE_NOT_PURE_BORROWINGS" in debt["valuation_blockers"]


@pytest.mark.parametrize("field,value,blocker", [
    ("canonical_metric", "attributable_net_income", "CANONICAL_METRIC_IDENTITY_CONFLICT"),
    ("statement_scope", "standalone", "STATEMENT_SCOPE_NOT_BOUND"),
    ("currency", "USD", "DOCUMENT_CURRENCY_SCALE_MISMATCH"),
    ("unit_scale", 1000000, "DOCUMENT_CURRENCY_SCALE_MISMATCH"),
    ("unit_scale", True, "UNIT_SCALE_NOT_EXPLICIT"),
    ("raw_value_text", "3,187.288", "ACCOUNTING_INTEGER_INVALID_OR_CONFLICTING"),
    ("raw_value_text", "3,18", "ACCOUNTING_INTEGER_INVALID_OR_CONFLICTING"),
    ("reported_column_kind", "YTD_CUMULATIVE_INTERIM", "QUARTER_CUMULATIVE_OR_INSTANT_MISMATCH"),
    ("audit_or_review_status", "audited", "ASSURANCE_IDENTITY_CONFLICT"),
])
def test_semantic_adversaries(field, value, blocker):
    row, doc, raw = inputs()
    row[field] = value
    result = prepared(row, doc, raw)
    assert blocker in result["semantic_blockers"] and not result["semantic_valid"]


def test_hash_page_and_exact_citation_fail_closed():
    row, doc, raw = inputs()
    assert "ORIGINAL_DOCUMENT_HASH_MISMATCH" in prepared(row, doc, raw + b"changed")["citation_blockers"]
    row["source_page"] = 58
    assert "SOURCE_PAGE_OUT_OF_RANGE_OR_MISSING" in prepared(row, doc, raw)["citation_blockers"]
    row["source_page"] = 9
    row["source_span"] = "malformed"
    assert "EXACT_CITATION_NOT_DOCUMENT_BOUND" in prepared(row, doc, raw)["citation_blockers"]


@pytest.mark.parametrize("known,reason", [("2026-10-13", "EXACT_OBSERVATION_KNOWLEDGE_TIMESTAMP_UNKNOWN"),
    ("2026-10-12T15:00:00+07:00", "KNOWLEDGE_PRECEDES_OBSERVATION"),
    ("2026-10-13T15:01:00+07:00", "AFTER_KNOWLEDGE_CUTOFF")])
def test_knowledge_and_publication_are_independent(known, reason):
    row, doc, raw = inputs()
    row["knowledge_available_at"] = known
    result = prepared(row, doc, raw)
    assert reason in result["knowledge_blockers"] and not result["knowledge_cutoff_eligible"]


def test_reviewed_integer_without_original_lexeme_is_honestly_labeled():
    row, doc, raw = inputs()
    del row["raw_value_text"]
    row["reviewed_integer_value"] = 3187288759647
    result = prepared(row, doc, raw)
    assert result["candidate"]["value"] == 3187288759647 and result["semantic_valid"]
    assert not result["native_numeric_literal_proven"] and not result["official_fact_admitted"]


def test_unreviewed_never_becomes_reviewed_from_pdf_creation_metadata():
    row, doc, raw = inputs()
    doc["pdf_creation_time"] = "D:20261012025535Z"
    result = prepared(row, doc, raw)
    assert result["candidate"]["audit_or_review_status"] == "unreviewed"
    assert result["candidate"]["publication_date"] is None


def test_eps_shares_and_numerator_never_become_current_shares_or_parent_profit():
    row, doc, raw = inputs(family="eps_note", code="", label="Number of ordinary shares in circulation for the period", period="2026-H1", value="8,442,964,520")
    row["unit"] = "shares"
    row["currency"] = None
    result = prepared(row, doc, raw)
    assert result["semantic_valid"]
    assert result["candidate"]["value"] == 8442964520
    assert result["candidate"]["canonical_metric"] is None
    assert "EPS_SHARE_BASIS_IS_NOT_CURRENT_OUTSTANDING_SHARES" in result["valuation_blockers"]
    assert not result["strict_valuation_eligible"]
    profit = resolve_reported_row_identity("eps_note", "", "Profit attributable to ordinary shareholders (VND)")
    assert profit["accounting_identity"] == "EPS_ORDINARY_SHAREHOLDER_PROFIT" and profit["canonical_metric"] is None


def test_reclassified_comparative_state_is_preserved_not_inferred():
    row, doc, raw = inputs(period="2025-Q3")
    row["restatement_state"] = "RECLASSIFIED_AS_PRINTED"
    result = prepared(row, doc, raw)
    assert result["candidate"]["restatement_state"] == "RECLASSIFIED_AS_PRINTED"
    plain = prepared(period="2026-Q3")
    assert "restatement_state" not in plain["candidate"]


def test_quarter_and_scope_conflicts_use_existing_conflict_owner():
    from stocklookup_core.evidence.approved_issuer_ir_financial_evidence import classify_conflict
    q3 = prepared()["candidate"]
    nine = prepared(period="2026-9M")["candidate"]
    separate = prepared(scope="standalone")["candidate"]
    assert classify_conflict(q3, nine) == "PERIOD_DIFFERENCE"
    assert classify_conflict(q3, separate) == "SCOPE_DIFFERENCE"
    assert classify_conflict(q3, {**q3, "value": 1}) == "TRUE_CONFLICT"


def test_source_candidate_is_blocked_by_existing_common_admission():
    from official_financial_filing_evidence import admit_official_financial_fact
    result = prepared()
    admitted = admit_official_financial_fact(result["candidate"], cutoff="2026-10-13T15:00:00+07:00")
    assert admitted["state"] != "ADMITTED"
    assert "FACT_QUALIFICATION_BLOCKED" in admitted["reason_codes"]


def test_real_candidate_cannot_enable_existing_reported_period_ratios():
    from stocklookup_core.valuation import current_research_valuation_context as valuation
    from tests.test_current_financial_valuation_input_unlock import raw as market_input
    result = prepared()
    artifact = valuation.evaluate_ticker_valuation(ticker="KBC", feature_record=None,
        valuation_record=market_input(), decision_session="2026-10-13", official_financial_facts=[result["candidate"]])
    method = artifact["methods"][valuation.PS_REPORTED_PERIOD]
    assert method["value"] is None and method["status"] == valuation.INPUT_BLOCKED


def test_document_class_cannot_make_unreviewed_rows_reviewed_or_news_financial():
    row, doc, raw = inputs()
    doc["document_class"] = "reviewed_interim_financial_statements"
    result = prepared(row, doc, raw)
    assert "DECLARED_DOCUMENT_CLASS_ASSURANCE_CONFLICT" in result["semantic_blockers"]
    doc["document_class"] = "issuer_operating_update"
    assert "FINANCIAL_DOCUMENT_CLASS_NOT_SUPPORTED" in prepared(row, doc, raw)["semantic_blockers"]


def test_composite_depreciation_and_capital_amount_do_not_become_ebitda_or_shares():
    depreciation = resolve_reported_row_identity("cash_flow", "02", "Depreciation and amortisation of fixed assets, investment properties, goodwill allocation and land rental costs")
    assert depreciation["canonical_metric"] is None
    assert depreciation["accounting_identity"] == "COMPOSITE_CASH_FLOW_DEPRECIATION_ADJUSTMENT"
    capital = resolve_reported_row_identity("balance_sheet", "411a", "Ordinary shares carrying voting rights")
    assert capital["canonical_metric"] is None and capital["accounting_identity"] == "ORDINARY_VOTING_SHARE_CAPITAL_AMOUNT"


@pytest.mark.parametrize("label", ["2026-9M and 2025-9M", "2026-H1 and 2026-9M"])
def test_multiple_cumulative_columns_cannot_select_one_period(label):
    result = prepared(period=label)
    assert not result["semantic_valid"]
    assert "MULTIPLE_REPORTED_CUMULATIVE_COLUMNS" in result["semantic_blockers"]
    assert result["candidate"]["reporting_period"] is None


@pytest.mark.parametrize("label", ["Profit after tax of non-controlling interests", "Profit after tax of non controlling interests"])
def test_nci_profit_cannot_masquerade_as_total_profit(label):
    result = prepared(code="60", label=label)
    assert not result["semantic_valid"]
    assert "TOTAL_PARENT_PROFIT_IDENTITY_CONFLICT" in result["semantic_blockers"]


@pytest.mark.parametrize("span_page", [None, -1, 8, 58, True])
def test_review_span_page_must_match_original_row_page(span_page):
    row, doc, raw = inputs()
    row["source_span"]["source_page"] = span_page
    result = prepared(row, doc, raw)
    assert not result["semantic_valid"] and not result["native_numeric_literal_proven"]
    assert "REVIEW_SPAN_PAGE_NOT_BOUND" in result["citation_blockers"]


@pytest.mark.parametrize("proof_page,proof_text", [(-1, "2026-09-30"), (58, "2026-09-30"), (9, "unrelated note")])
def test_covered_date_proof_must_bind_a_real_page_and_endpoint(proof_page, proof_text):
    row, doc, raw = inputs(family="balance_sheet", code="280", label="Total assets", period="2026-09-30")
    row.update(period_end="2026-09-30", period_bounds_evidence=dict(document_sha256=doc["sha256"], source_page=proof_page, text=proof_text))
    result = prepared(row, doc, raw)
    assert not result["semantic_valid"]
    assert any(code.startswith("COVERED_DATE_ENDPOINT") for code in result["semantic_blockers"])


@pytest.mark.parametrize("text", ["As at 30 September 2026", "September 30, 2026", "2026-09-30"])
def test_reviewed_date_formats_preserve_proven_balance_instant(text):
    row, doc, raw = inputs(family="balance_sheet", code="280", label="Total assets", period="2026-09-30")
    row.update(period_end="2026-09-30", period_bounds_evidence=dict(document_sha256=doc["sha256"], source_page=9, text=text))
    result = prepared(row, doc, raw)
    assert result["semantic_valid"]
    assert result["candidate"]["period_semantic_state"] == "POINT_IN_TIME_BALANCE_SHEET"


@pytest.mark.parametrize("quantity,row_scale", [(True, 1), (True, 1000000), (False, 1), (False, 1000000)])
def test_document_monetary_scale_never_multiplies_eps_or_share_quantities(quantity, row_scale):
    row, doc, raw = inputs(family="eps_note" if quantity else "income_statement", code="" if quantity else "70",
        label="Number of ordinary shares in circulation for the period" if quantity else "Basic earnings per share", value="1,000")
    doc["unit_scale"] = 1000000
    row["unit_scale"] = row_scale
    if quantity:
        row.update(currency=None, unit="shares")
    result = prepared(row, doc, raw)
    assert not result["semantic_valid"] and result["candidate"]["normalized_value"] is None
    assert "EPS_OR_SHARE_MIXED_UNIT_SCALE_NOT_SUPPORTED" in result["semantic_blockers"]


@pytest.mark.parametrize("family,label,start,end,blocker", [
    ("income_statement", "2026-Q3", "2026-01-01", "2026-09-30", "COVERED_DURATION_CONFLICTS_WITH_REPORTED_COLUMN"),
    ("balance_sheet", "2026-09-30", None, "2026-06-30", "REPORTED_BALANCE_INSTANT_CONFLICT"),
    ("balance_sheet", "As at 30 September 2026", None, "2026-06-30", "REPORTED_BALANCE_INSTANT_CONFLICT"),
])
def test_conflicting_explicit_column_bounds_fail_closed(family, label, start, end, blocker):
    result = recognize_reported_column_period(label, statement_family=family, explicit_start=start, explicit_end=end)
    assert blocker in result["blockers"]


@pytest.mark.parametrize("start,end", [("2026-06-01", "2026-08-31"), ("2026-01-31", "2026-04-30")])
def test_proven_quarter_bounds_do_not_require_a_july_fiscal_start(start, end):
    result = recognize_reported_column_period("2026-Q3", statement_family="income_statement", explicit_start=start, explicit_end=end)
    assert not result["blockers"]
    assert result["period_start"] == start and result["period_end"] == end
