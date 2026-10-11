"""Offline accounting basis, cutoff, reconciliation and opt-in consumer acceptance."""
import argparse
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys

import pytest

from stocklookup_core.decision.opportunity_axis_freshness import reporting_period_basis as basis
from stocklookup_core.decision.opportunity_axis_freshness import reporting_period_relation as relation
from stocklookup_core.decision.human_ai_decision_evidence_packet import build_packet
from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.financial import financial_analysis_product_projection as product
from stocklookup_core.financial import financial_reporting_currency as currency
from stocklookup_core.financial import financial_v2_current_input_authority as pin
from tools import inspect_decision_research as cli

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl"
REPORT = ROOT / "derived/financial-evidence-currency-refresh-v1/cohort_report.json"
CUTOFF = "2026-10-08T15:00:00+07:00"
BEFORE = "2026-09-05T00:00:00Z"


def official(**updates):
    rows = [json.loads(line) for line in FACTS.read_text(encoding="utf8").splitlines()]
    row = next(r for r in rows if r["ticker"] == "PNJ" and r["canonical_metric"] == "revenue")
    row.update(updates)
    return row


def provider(metric="revenue", amount=100, ticker="PNJ", period="2026-Q1", **updates):
    instant = metric in {"total_assets", "shareholders_equity"}
    row = {"ticker": ticker, "canonical_metric": metric, "reported_value": amount,
           "native_period_label": period, "period_start": "2026-01-01", "period_end": "2026-03-31",
           "period_semantic_state": "POINT_IN_TIME_BALANCE_SHEET" if instant else "STANDALONE_QUARTER",
           "statement_family": "balance_sheet" if instant else "income_statement", "statement_scope": "consolidated",
           "source_status": "provider_reported", "lineage_complete": True, "source_conflicts": [],
           "reported_currency": "VND", "reported_scale": 1, "normalized_candidate_unit": {"currency": "VND", "scale": 1},
           "retrieval_or_observation_timestamp": BEFORE, "published_timestamp": None,
           "source_lineage": {"provider": "VCI", "source_file": "synthetic", "source_sha256": "a" * 64,
                              "fact_id": f"{ticker}-{metric}-{period}", "source_observation_ids": ["synthetic-1"]}}
    row.update(updates)
    return row


def financial(rows=None, names=("PNJ",), types=None):
    rows = rows if rows is not None else [provider(), provider("net_income", 10), provider("total_assets", 200), provider("shareholders_equity", 80)]
    artifact = engine.build_artifact(tickers=names, rows=rows, issuer_types=types or {t: "corporate" for t in names},
        source_identities={"period_semantics_identity": pin._EXPECTED_SEMANTICS_IDENTITY,
                           "feature_store_artifact_identity": pin._EXPECTED_FEATURE_STORE_IDENTITY,
                           "period_semantics_knowledge_time": BEFORE}, requested_at=BEFORE)
    return product.build_product_projection(financial_context=artifact, product_tickers=names, requested_at=BEFORE)


def build(rows=None, **updates):
    args = {"financial_product": financial(), "official_rows": rows if rows is not None else [official()],
            "tickers": ["PNJ"], "decision_session": "2026-10-08", "knowledge_cutoff": CUTOFF,
            "provider_observations": [provider(), provider("net_income", 10), provider("total_assets", 200), provider("shareholders_equity", 80)]}
    args.update(updates)
    return currency.build(**args)


def check(**updates):
    row = {"ticker": "PNJ", "kind": "RETAINED_DOCUMENT", "reporting_period": "2026-Q3",
           "source_identity": "synthetic-retention-receipt", "document_sha256": "b" * 64,
           "citation_id": "synthetic-citation", "observed_at": "2026-10-07T00:00:00Z",
           "knowledge_available_at": "2026-10-07T00:00:00Z", "publication_date": None,
           "checked_scope": {"route": "synthetic-official-route", "reporting_period": "2026-Q3"},
           "blocker": "UNREVIEWED_ASSURANCE_NOT_ADMITTED"}
    row.update(updates)
    return row


@pytest.mark.parametrize("label,family", [("2026-Q1", "QUARTER"), ("2026-Q2", "QUARTER"), ("2026-Q3", "QUARTER"), ("2026-Q4", "QUARTER"), ("2026-H1", "HALF_YEAR"), ("2026-9M", "NINE_MONTH"), ("2025", "ANNUAL"), ("2025-FY", "ANNUAL"), ("2026-Q5", "UNKNOWN"), ("Q3-2026", "UNKNOWN"), (None, "UNKNOWN")])
def test_native_period_families_never_infer_calendar_or_duration(label, family):
    value = basis({"reporting_period": label})
    assert value["period_family"] == family
    assert value["fiscal_calendar"] == "UNKNOWN" and value["duration_days"] is None
    assert value["cumulative_basis"] == "UNKNOWN"
    assert "EXPLICIT_REPORTING_BOUNDS_UNPROVEN" in value["reason_codes"]


@pytest.mark.parametrize("start,end", [("2026-02-30", "2026-06-30"), ("2026-07-01", "2026-06-30"), ("20260101", "2026-06-30"), (True, "2026-06-30")])
def test_malformed_explicit_dates_are_unresolved(start, end):
    value = basis({"reporting_period": "2026-H1", "period_start": start, "period_end": end})
    assert value["period_end"] is None and "MALFORMED_EXPLICIT_PERIOD_BOUNDS" in value["reason_codes"]


def test_noncalendar_explicit_bounds_remain_native_not_backdated():
    value = basis({"reporting_period": "2026-Q4", "period_start": "2026-04-01", "period_end": "2026-06-30",
                   "fiscal_calendar": "NON_CALENDAR_YEAR", "period_semantic_state": "STANDALONE_QUARTER"})
    assert value["fiscal_calendar"] == "NON_CALENDAR_YEAR" and value["period_end"] == "2026-06-30"
    assert value["duration_days"] == 91
    assert relation(value, basis({"reporting_period": "2026-Q3"})) == "OLDER_NATIVE_PERIOD_POSITION"


def test_h1_is_not_q2_and_bs_is_instant():
    h1 = basis(official())
    q2 = basis({**provider(period="2026-Q2"), "period_start": "2026-04-01", "period_end": "2026-06-30"})
    assert relation(q2, h1) == "SAME_EXPLICIT_END"
    comparison = currency.compatible_measurement(q2, h1)
    assert comparison["status"] == "NOT_COMPARABLE" and "DURATION_MISMATCH" in comparison["reason_codes"]
    assert basis(provider("total_assets"))["time_basis"] == "INSTANT"
    assert basis(provider("total_assets"))["duration_days"] is None


def test_projection_preserves_measurements_provenance_and_separate_five_dimensions():
    context = financial()
    original = deepcopy(context)
    row = official(normalized_value=0)
    view = build([row], financial_product=context)
    record = view["records"]["PNJ"]
    for key in ("report_period_coverage", "source_update", "newer_period_evidence", "knowledge_cutoff_eligibility", "investor_interpretation"):
        assert key in record
    assert context == original and record["qualified_official_fields"][0]["normalized_value"] == 0
    assert record["frozen_provider_baseline"]["source_update_state"] == "FROZEN_PROVIDER_PIN"
    assert record["qualified_official_fields"][0]["source"]["publication_date"] is None
    assert record["qualified_official_fields"][0]["formal_temporal_status"] == "CURRENT_OFFICIAL_FACT"
    assert record["newer_period_evidence"]["known_progress_kinds"] == ["QUALIFIED_EXACT_FACT"]
    for measurement in record["frozen_provider_baseline"]["measurements"]:
        assert measurement["measurement"] == context["records"]["PNJ"]["feature_fitness"][measurement["feature_id"]]["source_feature_context"]
    assert not view["is_actionable"] and view["authority_effect"] == "NONE"


def test_historical_annual_remains_useful_and_year_transition_changes_only_legacy_label():
    annual = official(reporting_period="2025", period_type="annual", period_start="2025-01-01", period_end="2025-12-31", assurance="audited")
    # Use an actual admitted annual field rather than manufacturing a new annual ingress.
    annual = next(json.loads(x) for x in FACTS.read_text(encoding="utf8").splitlines() if json.loads(x)["ticker"] == "HPG" and json.loads(x)["canonical_metric"] == "revenue")
    view = build([annual], financial_product=financial(names=("HPG",)), tickers=["HPG"], provider_observations=[])
    assert view["records"]["HPG"]["qualified_official_fields"][0]["formal_temporal_status"] == "HISTORICAL_OFFICIAL_FACT"
    now, later = build(), build(decision_session="2027-01-05", knowledge_cutoff="2027-01-05T15:00:00+07:00")
    a, b = now["records"]["PNJ"]["qualified_official_fields"][0], later["records"]["PNJ"]["qualified_official_fields"][0]
    assert a["normalized_value"] == b["normalized_value"] and a["basis"] == b["basis"]
    assert b["formal_temporal_status"] == "HISTORICAL_OFFICIAL_FACT"
    assert later["records"]["PNJ"]["newer_period_evidence"]["known_progress_kinds"] == ["QUALIFIED_EXACT_FACT"]


@pytest.mark.parametrize("field,value", [("observed_at", "2026-10-09T00:00:00Z"), ("knowledge_available_at", "2026-10-09T00:00:00Z"), ("publication_date", "2026-10-09"), ("publication_date", "2026-10-09T00:00:00Z"), ("observed_at", None), ("knowledge_available_at", "2026-10-01")])
def test_future_or_unknown_time_excluded_before_conflict_detector(field, value):
    old = official()
    future = official(**{field: value, "normalized_value": old["normalized_value"] + 1})
    view = build([old, future])
    record = view["records"]["PNJ"]
    assert len(record["qualified_official_fields"]) == 1
    assert not record["newer_period_evidence"]["conflicts"]
    assert record["knowledge_cutoff_eligibility"]["excluded_facts"]
    assert "normalized_value" not in currency.canonical(record["knowledge_cutoff_eligibility"])


def test_duplicate_rows_collapse_but_conflicts_do_not_choose_winner():
    assert len(build([official(), official()])["records"]["PNJ"]["qualified_official_fields"]) == 1
    view = build([official(), official(normalized_value=1)])
    record = view["records"]["PNJ"]
    assert not record["qualified_official_fields"] and record["newer_period_evidence"]["conflicts"]
    assert record["investor_interpretation"]["ticker_rejected"] is False


@pytest.mark.parametrize("change", [{"audit_or_review_status": "unreviewed"}, {"qualification_state": "BLOCKED"}, {"assurance_evidence": None}, {"reporting_period": "2026-Q3", "period_end": "2026-09-30"}, {"normalized_value": True}, {"normalized_value": None}])
def test_standing_official_gates_stay_closed(change):
    record = build([official(**change)])["records"]["PNJ"]
    assert not record["qualified_official_fields"]
    assert record["newer_period_evidence"]["qualification_rejections"] or record["knowledge_cutoff_eligibility"]["excluded_facts"]


def test_retained_notice_negative_and_approved_route_are_independent_states():
    checks = [check(), check(kind="SOURCE_NOTICE", document_sha256=None, citation_id="notice"),
              check(kind="CHECKED_NO_POSITIVE_EVIDENCE", document_sha256=None, reporting_period="2025", citation_id="checked"),
              check(kind="BLOCKED_OR_UNCHECKED", document_sha256=None, reporting_period="2026-9M", citation_id="approved-route-no-check")]
    record = build([], source_checks=checks)["records"]["PNJ"]
    assert record["newer_period_evidence"]["known_progress_kinds"] == ["RETAINED_DOCUMENT", "SOURCE_NOTICE"]
    assert record["newer_period_evidence"]["global_latest_status"] == "UNPROVEN"
    assert not record["qualified_official_fields"]
    only_approved = build([], source_checks=[checks[-1]])["records"]["PNJ"]
    assert only_approved["source_update"]["official_route"] == "BLOCKED_OR_UNCHECKED"
    assert not only_approved["newer_period_evidence"]["known_progress_kinds"]


def test_repeated_document_observation_retains_receipts_counts_once():
    checks = [check(), check(observed_at="2026-10-07T01:00:00Z", knowledge_available_at="2026-10-07T01:00:00Z")]
    record = build([], source_checks=checks)["records"]["PNJ"]
    assert len(record["source_update"]["checks"]) == 1
    assert len(record["source_update"]["checks"][0]["observation_receipts"]) == 2
    assert record["newer_period_evidence"]["known_progress_kinds"] == ["RETAINED_DOCUMENT"]


def test_latest_anchor_prevents_old_history_false_newer_claim():
    q2 = provider(period="2026-Q2", period_start="2026-04-01", period_end="2026-06-30")
    rows = [provider(), q2, provider("net_income", 10), provider("net_income", 20, period="2026-Q2", period_start="2026-04-01", period_end="2026-06-30")]
    view = build(financial_product=financial(rows), provider_observations=rows)
    assert not view["records"]["PNJ"]["newer_period_evidence"]["known_progress_kinds"]


@pytest.mark.parametrize("field,value", [("canonical_metric", "net_income"), ("currency", "USD"), ("statement_scope", "separate"), ("unit_scale", 1000), ("statement_family", "cash_flow")])
def test_comparability_requires_full_accounting_basis(field, value):
    a = basis(official())
    b = deepcopy(a); b[field] = value
    assert currency.compatible_measurement(a, b)["status"] == "NOT_COMPARABLE"


def test_group_comparisons_keep_currency_scope_duration_and_entity_apart():
    rows = [provider(ticker=t) for t in ("PNJ", "VCB", "SSI")]
    context = financial(rows, names=("PNJ", "VCB", "SSI"), types={"PNJ": "corporate", "VCB": "bank", "SSI": "securities"})
    view = build(financial_product=context, tickers=["PNJ", "VCB", "SSI"], provider_observations=rows)
    assert view["coverage"]["selected_ticker_denominator"] == 3 and len(view["records"]) == 3
    assert view["records"]["VCB"]["report_period_coverage"]["method_applicability"]["ordinary_corporate_debt_ebitda"] == "NOT_APPLICABLE"
    assert view["records"]["SSI"]["report_period_coverage"]["method_applicability"]["securities"] == "FOLLOW_SECURITIES_OWNER"
    assert view["selected_comparison"]["cross_basis_comparison"] == "NOT_PERMITTED"


def test_input_order_stability_and_no_missing_or_null_becomes_zero():
    checks = [check(), check(kind="SOURCE_NOTICE", citation_id="notice")]
    a = build([official(), official()], source_checks=checks)
    b = build([official(), official()], source_checks=list(reversed(checks)), provider_observations=list(reversed([provider(), provider("net_income", 10), provider("total_assets", 200), provider("shareholders_equity", 80)])))
    assert a == b
    assert not build([])["records"]["PNJ"]["qualified_official_fields"]
    assert not build([official(normalized_value=None)])["records"]["PNJ"]["qualified_official_fields"]
    assert build([official(normalized_value=0)])["records"]["PNJ"]["qualified_official_fields"][0]["normalized_value"] == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_anywhere_fails_closed(value):
    with pytest.raises(ValueError):
        build([official(normalized_value=value)])


def test_packet_and_readable_consumer_preserve_capital_and_default_identity():
    default = build_packet(ticker="PNJ", sections={"stock": {"revenue": 123}, "uncertainty": {"gap": None}}, feature_measurements={"price": 5}, ai_narration="bounded research", capital_decision="BUY")
    assert default["packet_identity"] == "human_ai_decision_evidence_packet:bca218936fbe45cd37c9d8a9131a6e7a21e66b0860d930627e9418a266a810b3"
    projection = build(source_checks=[check()])
    packet = build_packet(ticker="PNJ", decision_session="2026-10-08", financial_reporting_currency=projection, capital_decision="BUY")
    assert packet["sections"]["stock"]["fields"]["financial_reporting_currency"]["value"]["record"] == projection["records"]["PNJ"]
    assert packet["capital_decision"]["value"] is None and not packet["is_actionable"]
    text = currency.render_markdown(projection)
    for label in ("FROZEN_PROVIDER_PIN", "synthetic-citation", "CURRENT_OFFICIAL_FACT", "publication unknown", "No metric replacement"):
        assert label in text


@pytest.mark.parametrize("section,field", [("stock", "financial_reporting_currency"), ("uncertainty", "financial_reporting_limits"), ("counter_thesis", "financial_reporting_gaps")])
def test_packet_reserved_fields_fail_closed(section, field):
    with pytest.raises(ValueError, match="COLLISION"):
        build_packet(ticker="PNJ", financial_reporting_currency=build(), sections={section: {field: None}})


@pytest.mark.parametrize("change", [lambda v: v.update(non_voting=False), lambda v: v.update(is_actionable=True), lambda v: v.update(authority_effect="PROMOTED"), lambda v: v.update(production="DAILY"), lambda v: v.update(temporal_use="PIT"), lambda v: v["research_boundaries"].clear(), lambda v: v["records"]["PNJ"]["qualified_official_fields"][0]["source"].update(observed_at="2026-10-09T00:00:00Z")])
def test_resealed_invalid_packet_boundary_rejected(change):
    view = build(); change(view); view.update(currency.identity(view))
    with pytest.raises(ValueError):
        build_packet(ticker="PNJ", financial_reporting_currency=view)


def arguments(tmp_path, *extra):
    path = tmp_path / "financial.json"; path.write_text(json.dumps(financial()))
    parser = argparse.ArgumentParser(); cli.configure_parser(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(["research", "financial-currency", "--financial-product", str(path), "--facts", str(FACTS), "--session", "2026-10-08", "--cutoff", CUTOFF, "--ticker", "PNJ", *extra])


def test_cli_read_only_json_and_markdown(tmp_path, capsys):
    args = arguments(tmp_path, "--cohort-report", str(REPORT))
    before = {p: p.read_bytes() for p in (FACTS, REPORT, args.financial_product)}
    result = cli.inspect(args)
    assert result["persisted"] is False and result["authority_effect"] == "NONE"
    assert "financial_reporting_currency" in result["packets"]["PNJ"]["sections"]["stock"]["fields"]
    assert "SOURCE_REPORT_IDENTITY_MISMATCH" in result["presentation"]
    args.format = "markdown"; assert cli.run(args) == 0
    assert capsys.readouterr().out.startswith("# Financial reporting basis")
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("body", ['{"ticker":"PNJ","x":NaN}', '{"ticker":"PNJ","x":1e999}', '{"ticker":"PNJ","ticker":"HPG"}'])
def test_cli_strict_json_rejection(tmp_path, body, capsys):
    args = arguments(tmp_path); path = tmp_path / "bad.jsonl"; path.write_text(body); args.facts = path
    assert cli.run(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "UNAVAILABLE" and str(tmp_path) not in json.dumps(result)


def test_cli_exact_observation_gzip_and_source_changes(tmp_path, monkeypatch):
    path = tmp_path / "observations.jsonl.gz"
    with gzip.open(path, "wt") as handle:
        handle.write(json.dumps(provider()) + "\n")
    args = arguments(tmp_path, "--provider-observations", str(path))
    assert cli.inspect(args)["projection"]["records"]["PNJ"]["frozen_provider_baseline"]["matched_observations"]
    original = cli._financial_currency
    def changed(*args):
        result = original(*args); path.write_bytes(b"changed"); return result
    monkeypatch.setattr(cli, "_financial_currency", changed)
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        cli.inspect(args)


def test_existing_entrypoint_routes_opt_in(tmp_path):
    args = arguments(tmp_path)
    proc = subprocess.run([sys.executable, str(ROOT / "stocklookup.py"), "research", "financial-currency", "--financial-product", str(args.financial_product), "--facts", str(FACTS), "--session", args.session, "--cutoff", args.cutoff, "--ticker", "PNJ"], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["contract_version"] == currency.CONTRACT_VERSION


def test_public_overlay_real_counts_and_unverified_retention_claims():
    from financial_evidence_currency_contract import COHORT

    rows = [json.loads(x) for x in FACTS.read_text(encoding="utf8").splitlines()]
    view = build(rows, financial_product=financial(names=COHORT), tickers=COHORT,
                 provider_observations=[], cohort_report=json.loads(REPORT.read_text(encoding="utf8")))
    assert view["coverage"]["selected_ticker_denominator"] == 14
    assert view["coverage"]["qualified_fact_count"] == 27
    assert view["coverage"]["qualified_ticker_count"] == 7
    assert view["coverage"]["verified_retained_document_count"] == 0
    assert view["coverage"]["unverified_document_claim_count"] == 9
    assert sum(q["source"]["publication_date"] is None for r in view["records"].values() for q in r["qualified_official_fields"]) == 27
    assert {t: len(r["qualified_official_fields"]) for t, r in view["records"].items() if r["qualified_official_fields"]} == {
        "FPT": 3, "HPG": 2, "PNJ": 6, "PVD": 7, "QNS": 1, "VNM": 1, "VRE": 7}


def test_sealed_report_receipt_can_establish_bounded_retention_not_field_authority():
    report = {"contract_version": "financial_evidence_currency_refresh/v1", "observed_at": "2026-10-07T00:00:00Z",
              "issuers": {"PNJ": {"periods": {"2026-Q3": {"immutable_raw_retained": True, "document_found": True,
                           "hash": "b" * 64, "requested": True, "http_status": 200, "scope": "consolidated",
                           "route": "synthetic-citation", "blocker": "UNREVIEWED_ASSURANCE"}}}}}
    import hashlib
    digest = hashlib.sha256(currency.canonical(report).encode()).hexdigest()
    report.update(artifact_sha256=digest, artifact_identity="financial_evidence_currency_refresh:" + digest)
    view = build([], cohort_report=report)
    assert view["coverage"]["verified_retained_document_count"] == 1
    assert view["coverage"]["qualified_fact_count"] == 0
    assert view["records"]["PNJ"]["newer_period_evidence"]["known_progress_kinds"] == ["RETAINED_DOCUMENT"]


def test_provider_cutoff_unknown_and_after_withhold_values_without_mutating_input():
    for knowledge in (None, "2026-10-09T00:00:00Z"):
        context = financial()
        context["records"]["PNJ"]["lineage"]["source_identities"]["period_semantics_knowledge_time"] = knowledge
        context.update(product._identity(context))
        original = deepcopy(context)
        view = build([], financial_product=context)
        baseline = view["records"]["PNJ"]["frozen_provider_baseline"]
        assert not baseline["measurements"] and baseline["compact_context"] is None
        assert baseline["excluded_measurement_references"]
        assert all("reported_value" not in r for r in baseline["matched_observations"])
        assert context == original
        currency.packet_context(view, ticker="PNJ")


@pytest.mark.parametrize("change", [lambda q: q.update(valuation_use="PROMOTED_VALUATION"),
                                  lambda q: q.update(formal_temporal_status="LATEST_OFFICIAL_FACT"),
                                  lambda q: q["eligibility"].update(decision_time_eligibility="PIT"),
                                  lambda q: q["basis"].update(native_label="2026-Q3"),
                                  lambda q: q.update(target_price=1)])
def test_packet_rejects_forged_resealed_financial_authority(change):
    view = build(); change(view["records"]["PNJ"]["qualified_official_fields"][0]); view.update(currency.identity(view))
    with pytest.raises(ValueError):
        currency.packet_context(view, ticker="PNJ")


@pytest.mark.parametrize("field,value", [("currency", "unknown"), ("unit_scale", "unknown"), ("unit_scale", True),
                                         ("unit_scale", 0), ("statement_scope", "unknown"), ("statement_family", None)])
def test_unknown_or_invalid_unit_scope_cannot_join_comparison(field, value):
    b = basis(official()); b[field] = value
    assert currency.comparison_basis(b) is None


def test_selected_absent_subject_preserved_and_packet_session_subject_guard():
    view = build(financial_product=financial(), tickers=["PNJ", "ZZZ"])
    assert view["records"]["ZZZ"]["frozen_provider_baseline"]["status"] == "ABSENT"
    assert view["coverage"]["selected_ticker_denominator"] == 2
    with pytest.raises(ValueError, match="SUBJECT"):
        build_packet(ticker="OTHER", financial_reporting_currency=view)
    with pytest.raises(ValueError, match="SESSION"):
        build_packet(ticker="PNJ", decision_session="2026-10-07", financial_reporting_currency=view)


def test_no_currency_import_or_default_activation_in_production_owners():
    for name in ("canonical_daily_financial_v2_materialization.py", "daily_analysis_pipeline.py",
                 "daily_producer_pipeline.py", "current_research_ai_handoff_packet.py"):
        path = ROOT / name
        if not path.exists():
            continue
        assert "financial_reporting_currency" not in path.read_text(encoding="utf8")


def test_released_default_financial_golden_values_and_identity():
    # Captured by executing the exact 3d9abf8 main engine and compact sources:
    # both full dictionaries matched the candidate default sources byte-for-byte.
    context = financial()
    assert context["source_context_identity"] == "financial_analysis_context/v2:80ff5d53015302a6bb630b8e94a58990a2a9e111012cb1b176691bbb20f72a50"
    assert context["artifact_identity"] == "financial_analysis_product_integration/v1:d6298fd7fbf91bee1ff0c58167e6850460e2ea94976d777b23f18d7b1ef481d7"
    fields = context["records"]["PNJ"]["feature_fitness"]
    assert fields["net_margin"]["source_feature_context"]["value"] == 0.1
    assert fields["equity_to_assets"]["source_feature_context"]["value"] == 0.4
    original = deepcopy(context)
    build(financial_product=context)
    assert context == original


def test_malformed_native_family_duration_cannot_be_comparable():
    b = basis({**official(), "period_start": "2026-06-30"})
    assert "NATIVE_PERIOD_FAMILY_DURATION_CONFLICT" in b["reason_codes"]
    assert currency.comparison_basis(b) is None
    assert basis({"reporting_period": "0000-Q1"})["period_family"] == "UNKNOWN"


def test_mixed_flow_stock_feature_does_not_become_single_statement_duration():
    b = basis({"reporting_period": "2026-Q1", "period_semantics": ["POINT_IN_TIME_BALANCE_SHEET", "STANDALONE_QUARTER"]})
    assert b["time_basis"] == "MIXED" and b["duration_days"] is None
    assert "MIXED_STATEMENT_TIMING_BASIS" in b["reason_codes"]
    assert basis({"reporting_period": "2026-Q1"})["time_basis"] == "UNKNOWN"


def test_packet_rejects_future_check_and_promoted_unverified_receipt():
    view = build([], source_checks=[check()])
    view["records"]["PNJ"]["source_update"]["checks"][0]["source"]["observed_at"] = "2026-10-09T00:00:00Z"
    view.update(currency.identity(view))
    with pytest.raises(ValueError, match="CHECK_CUTOFF"):
        currency.packet_context(view, ticker="PNJ")
    view = build([], cohort_report=json.loads(REPORT.read_text(encoding="utf8")))
    view["records"]["PNJ"]["source_update"]["checks"][0]["kind"] = "RETAINED_DOCUMENT"
    view.update(currency.identity(view))
    with pytest.raises(ValueError, match="RECEIPT_PROMOTED"):
        currency.packet_context(view, ticker="PNJ")
