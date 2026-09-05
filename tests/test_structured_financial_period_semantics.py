"""Boundary tests for market_wide_structured_financial_period_semantics/v1."""
from copy import deepcopy

import inspect

import structured_financial_period_semantics as s


def fact(**overrides):
    row = {
        "ticker": "AAA", "canonical_metric": "revenue", "provider": "KBS",
        "statement_family": "income_statement", "statement_scope": "consolidated",
        "reporting_period": "2025-Q2", "period_type": "quarterly",
        "period_start": "2025-04-01", "period_end": "2025-06-30", "source_sha256": "a" * 64,
        "source_file": "AAA_income_statement_quarter.parquet", "fact_id": "f-1",
        "source_observation_ids": ["o-1"], "status": "provider_reported",
        "qualification_state": "provider_reported", "value": 100.0, "currency": "VND", "scale": 1,
        "observed_at": "2025-08-01T00:00:00Z", "conflicts": [], "warnings": [],
        "cumulative_state": "period_only",
    }
    row.update(overrides)
    return row


def artifact(rows):
    return s.build_artifact(facts=rows, source_contract={"source": "fixture"}, requested_at="t")


def test_exact_contract_version_is_exposed():
    assert artifact([fact()])["contract_version"] == s.CONTRACT_VERSION


def test_balance_sheet_is_point_in_time():
    row = s.project_fact(fact(statement_family="balance_sheet", canonical_metric="total_assets"))
    assert row["period_semantic_state"] == s.POINT_IN_TIME_BALANCE_SHEET


def test_kbs_income_contract_is_standalone_quarter():
    assert s.project_fact(fact())["period_semantic_state"] == s.STANDALONE_QUARTER


def test_vci_income_quarter_label_does_not_infer_duration():
    assert s.project_fact(fact(provider="VCI"))["period_semantic_state"] == s.UNKNOWN_DURATION


def test_dates_alone_do_not_infer_vci_income_duration():
    assert s.project_fact(fact(provider="VCI", period_start="2025-04-01", period_end="2025-06-30"))["period_semantic_state"] == s.UNKNOWN_DURATION


def test_cash_flow_period_only_resolver_is_standalone():
    assert s.project_fact(fact(statement_family="cash_flow", canonical_metric="operating_cash_flow", provider="VCI"))["period_semantic_state"] == s.STANDALONE_QUARTER


def test_cash_flow_ytd_is_preserved():
    assert s.project_fact(fact(statement_family="cash_flow", canonical_metric="operating_cash_flow", provider="VCI", cumulative_state="cumulative_ytd"))["period_semantic_state"] == s.YTD_CUMULATIVE_INTERIM


def test_native_annual_is_accepted_without_synthesis():
    assert s.project_fact(fact(period_type="annual", reporting_period="2025"))["period_semantic_state"] == s.ANNUAL


def test_missing_raw_hash_blocks_lineage():
    row = s.project_fact(fact(source_sha256=None))
    assert s.LINEAGE_INCOMPLETE in row["blocker_reason_codes"]


def test_missing_provider_blocks_lineage():
    row = s.project_fact(fact(provider=None))
    assert "provider" in row["missing_lineage_fields"]


def test_missing_timestamp_is_preserved_not_lineage_fabricated():
    row = s.project_fact(fact(observed_at=None))
    assert row["metadata_missing"]["timestamp"] is True and row["lineage_complete"] is True


def test_period_end_observed_and_published_timestamps_remain_distinct():
    row = s.project_fact(fact(period_end="2025-06-30", observed_at="2025-08-01T00:00:00Z", published_at="2025-07-30T00:00:00Z"))
    assert row["period_end"] != row["retrieval_or_observation_timestamp"] != row["published_timestamp"]


def test_unknown_unit_is_preserved():
    row = s.project_fact(fact(currency="unknown", scale="unknown"))
    assert row["metadata_missing"]["unit"] is True


def test_unknown_scope_is_preserved():
    row = s.project_fact(fact(statement_scope="unknown"))
    assert row["metadata_missing"]["scope"] is True


def test_provider_schema_rule_reuses_across_tickers():
    left, right = s.project_fact(fact(ticker="AAA")), s.project_fact(fact(ticker="BBB"))
    assert left["period_semantic_method"] == right["period_semantic_method"]


def test_no_ticker_specific_branch_exists():
    assert "ticker ==" not in inspect.getsource(s._period_state)


def test_unsupported_provider_schema_fails_locally():
    row = s.project_fact(fact(provider="UNSUPPORTED", period_start=None, period_end="2025-06-30"))
    assert "UNSUPPORTED_PROVIDER_SCHEMA_PERIOD_CONTRACT" in row["blocker_reason_codes"]


def test_malformed_record_is_retained_without_aborting_batch():
    built = artifact([fact(), {"ticker": "BAD"}])
    assert built["coverage"]["emitted_fact_count"] == 2
    assert s.LINEAGE_INCOMPLETE in built["records"][1]["blocker_reason_codes"]


def test_zero_is_not_missing():
    row = s.project_fact(fact(value=0.0))
    assert row["reported_value"] == 0.0 and row["metadata_missing"]["unit"] is False


def test_missing_value_is_not_zero():
    row = s.project_fact(fact(value=None))
    assert row["reported_value"] is None and row["reported_value"] != 0


def test_stock_and_flow_are_explicitly_separated():
    stock = s.project_fact(fact(statement_family="balance_sheet", canonical_metric="total_assets"))
    flow = s.project_fact(fact(statement_family="income_statement", canonical_metric="revenue"))
    assert stock["metric_nature"] == "STOCK_POINT_IN_TIME"
    assert flow["metric_nature"] == "FLOW_DURATION"


def test_conflict_is_never_chosen_or_dropped():
    row = s.project_fact(fact(conflicts=[{"kind": "VALUE_CONFLICT"}], status="conflicted"))
    assert row["source_conflicts"] == [{"kind": "VALUE_CONFLICT"}]
    assert "SOURCE_STATUS_CONFLICTED" in row["blocker_reason_codes"]


def test_blocked_status_remains_blocked():
    assert "SOURCE_STATUS_UNAVAILABLE" in s.project_fact(fact(status="unavailable"))["blocker_reason_codes"]


def test_value_is_passed_through_without_transformation():
    row = s.project_fact(fact(value=-12.5))
    assert row["reported_value"] == row["normalized_candidate_value"] == -12.5
    assert row["normalization_method"].startswith("PASSTHROUGH")


def test_negative_earnings_have_no_special_score_or_feature():
    row = s.project_fact(fact(canonical_metric="net_income", value=-12.5))
    assert row["reported_value"] == -12.5 and "score" not in row


def test_authority_is_never_promoted():
    row = s.project_fact(fact())
    assert row["authoritative_financial_eligible"] is False and row["authority_state"] == "OPERATIONAL_PROVIDER_FACT_NOT_AUTHORITATIVE"


def test_artifact_never_overwrites_authoritative_namespace():
    built = artifact([fact()])
    assert built["authority_boundary"]["authoritative_namespace_overwritten"] is False


def test_no_silent_drops():
    built = artifact([fact(), fact(ticker="BBB", source_sha256=None)])
    assert built["coverage"]["input_fact_count"] == built["coverage"]["emitted_fact_count"] == 2
    assert built["coverage"]["zero_silent_drops"] is True


def test_deterministic_identity_ignores_request_time_only():
    first = s.build_artifact(facts=[fact()], source_contract={"source": "fixture"}, requested_at="one")
    second = s.build_artifact(facts=[fact()], source_contract={"source": "fixture"}, requested_at="two")
    assert first["artifact_identity"] == second["artifact_identity"]


def test_same_period_yoy_requires_compatible_unit_scope_and_duration():
    prior = fact(reporting_period="2024-Q2", value=80.0)
    assert artifact([prior, fact()])["compatibility"]["same_period_yoy_compatible_candidate_count"] == 1


def test_yoy_does_not_cross_unknown_unit():
    prior = fact(reporting_period="2024-Q2", currency="unknown")
    assert artifact([prior, fact()])["compatibility"]["same_period_yoy_compatible_candidate_count"] == 0


def test_margin_requires_revenue_and_income_same_period_scope_unit():
    income = fact(canonical_metric="net_income", value=20.0)
    assert artifact([fact(), income])["compatibility"]["period_margin_compatible_candidate_count"] == 1


def test_margin_does_not_cross_scope():
    income = fact(canonical_metric="net_income", statement_scope="separate")
    assert artifact([fact(), income])["compatibility"]["period_margin_compatible_candidate_count"] == 0


def test_balance_trajectory_is_point_in_time_only():
    first = fact(statement_family="balance_sheet", canonical_metric="total_assets", reporting_period="2025-Q1", period_end="2025-03-31")
    second = fact(statement_family="balance_sheet", canonical_metric="total_assets", reporting_period="2025-Q2", period_end="2025-06-30")
    assert artifact([first, second])["compatibility"]["point_in_time_balance_trajectory_compatible_candidate_count"] == 1


def test_conflict_never_enters_compatibility_count():
    prior = fact(reporting_period="2024-Q2", status="conflicted", conflicts=[{"kind": "VALUE_CONFLICT"}])
    assert artifact([prior, fact()])["compatibility"]["same_period_yoy_compatible_candidate_count"] == 0


def test_original_input_is_not_mutated():
    source = fact(); before = deepcopy(source)
    s.project_fact(source)
    assert source == before


def test_resolved_duration_has_no_root_cause():
    row = s.project_fact(fact())
    assert row["period_semantic_state"] == s.STANDALONE_QUARTER
    assert row["period_duration_root_cause"] is None


def test_no_raw_observation_is_the_duration_root_cause_for_unavailable_facts():
    row = s.project_fact(fact(status="unavailable", value=None, provider=None))
    assert row["period_semantic_state"] == s.UNKNOWN_DURATION
    assert row["period_duration_root_cause"] == s.DURATION_ROOT_CAUSE_NO_RAW_OBSERVATION


def test_vci_no_basis_marker_is_distinct_from_no_raw_observation():
    """A genuinely reported VCI value with unresolved duration is a different root cause than
    a placeholder with no value at all -- both currently land on UNKNOWN_DURATION, but they
    must not be reported as the same reason (owner directive section 4: not one homogeneous
    blocker)."""
    row = s.project_fact(fact(provider="VCI"))
    assert row["period_semantic_state"] == s.UNKNOWN_DURATION
    assert row["period_duration_root_cause"] == s.DURATION_ROOT_CAUSE_VCI_NO_BASIS_MARKER
    placeholder = s.project_fact(fact(status="unavailable", value=None, provider=None))
    assert placeholder["period_duration_root_cause"] != row["period_duration_root_cause"]


def test_unsupported_provider_duration_root_cause():
    row = s.project_fact(fact(provider="UNSUPPORTED", period_start=None, period_end="2025-06-30"))
    assert row["period_duration_root_cause"] == s.DURATION_ROOT_CAUSE_UNSUPPORTED_PROVIDER


def test_cash_flow_unresolved_cumulative_state_root_cause():
    row = s.project_fact(fact(statement_family="cash_flow", canonical_metric="operating_cash_flow", cumulative_state="unknown"))
    assert row["period_semantic_state"] == s.UNKNOWN_DURATION
    assert row["period_duration_root_cause"] == s.DURATION_ROOT_CAUSE_CASH_FLOW_INSUFFICIENT_DEPTH


def test_timestamp_root_cause_is_none_once_a_timestamp_exists():
    row = s.project_fact(fact())
    assert row["timestamp_root_cause"] is None


def test_timestamp_root_cause_no_raw_observation_for_placeholder_facts():
    row = s.project_fact(fact(status="unavailable", value=None, provider=None, observed_at=None))
    assert row["timestamp_root_cause"] == s.TIMESTAMP_ROOT_CAUSE_NO_RAW_OBSERVATION


def test_timestamp_root_cause_missing_scraped_at_for_real_facts_without_a_timestamp():
    row = s.project_fact(fact(observed_at=None))
    assert row["source_status"] == "provider_reported"
    assert row["timestamp_root_cause"] == s.TIMESTAMP_ROOT_CAUSE_MISSING_SCRAPED_AT


def test_root_cause_distributions_are_reported_in_artifact_coverage():
    rows = [fact(provider="VCI"), fact(ticker="BBB", status="unavailable", value=None, provider=None)]
    built = artifact(rows)
    assert built["coverage"]["duration_root_cause_distribution"][s.DURATION_ROOT_CAUSE_VCI_NO_BASIS_MARKER] == 1
    assert built["coverage"]["duration_root_cause_distribution"][s.DURATION_ROOT_CAUSE_NO_RAW_OBSERVATION] == 1


def test_every_unknown_duration_record_gets_a_root_cause():
    """No silent gap: every UNKNOWN_DURATION record must carry a non-null root cause."""
    rows = [fact(provider="VCI"), fact(ticker="BBB", statement_family="balance_sheet",
                                       canonical_metric="total_assets", period_end=None),
            fact(ticker="CCC", status="unavailable", value=None, provider=None)]
    for row in [s.project_fact(r) for r in rows]:
        if row["period_semantic_state"] == s.UNKNOWN_DURATION:
            assert row["period_duration_root_cause"] is not None
