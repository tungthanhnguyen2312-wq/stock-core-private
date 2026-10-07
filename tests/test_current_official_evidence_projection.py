"""Offline field authority and exact-session consumer binding regressions."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import market_wide_current_fundamental_research as fundamental
import market_wide_current_corporate_intelligence as ci
import current_research_decision_packet as packet
import current_corporate_event_context as corporate
import current_official_event_context as official
from current_opportunity_prioritization import content_identity as opportunity_identity
from market_wide_current_valuation_input_scaleout import _financial_input

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-10-07"
CUTOFF = SESSION + "T15:00:00+07:00"


def baseline():
    value = {"contract_version": fundamental.CONTRACT_VERSION, "records": {
        ticker: {"authority_tier": "OFFICIAL_QUALIFIED", "authoritative_periods_available": [period],
                 "metrics": [{"metric_id": "net_margin", "status": "EXACT_QUALIFIED", "periods_used": [period], "value": 0.1}]}
        for ticker, period in (("PNJ", "2024"), ("VRE", "2025"), ("HPG", "2024"), ("PVD", "2024"))}}
    value.update(fundamental.content_identity(value))
    return value


def rows(currency='VND'):
    # These original VND boundary regressions deliberately use one fixed currency lane.
    return [r for line in (ROOT / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl").read_text(encoding="utf-8").splitlines()
            if (r := json.loads(line))['currency'] == currency
            and r['period_type'] == 'interim'
            and (currency != 'VND' or r['canonical_metric'] in {'revenue','net_income'})]


def all_rows():
    return [json.loads(line) for line in (ROOT / 'derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl').read_text(encoding='utf8').splitlines()]


def test_annual_ingress_cannot_strip_all_context_markers_to_escape_restriction():
    annual = [r for r in all_rows() if r['period_type']=='annual']
    assert len(annual)==8
    for row in annual:
        for key in ('context_kind','projection_period_policy','annual_context_contract'):
            row.pop(key)
    value = fundamental.project_session(baseline=baseline(),official_rows=annual,
        session=SESSION,cutoff=SESSION+'T23:00:00+07:00')
    assert not value['records']['HPG']['official_field_context']
    assert all('AUDITED_ANNUAL_CONTEXT_IDENTITY_NOT_QUALIFIED' in r['reasons']
               for r in value['official_projection']['rejected_fields'])


def test_reported_component_survives_consumers_with_unknown_recurrence_and_no_normalization():
    value = project(all_rows())
    assert value['official_projection']['current_official_field_count']==9
    quality = value['records']['VRE']['earnings_quality_context']
    assert quality['status']=='NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE'
    assert quality['recurrence_assessment']=='UNKNOWN' and quality['normalized_eps'] is None
    evidence = quality['component_evidence'][0]
    assert evidence['normalized_value']==184751000000
    assert evidence['valuation_use']=='NOT_PERMITTED_EARNINGS_COMPONENT_CONTEXT'
    assert _financial_input(value['records']['VRE'],value)['earnings_quality_context']==quality
    from ai_research_session_delivery import _compact_context
    assert _compact_context('VRE',{'product':{}},{'fundamental':value})['fundamental_context']['earnings_quality_context']==quality
    assert value['records']['PNJ']['earnings_quality_context']['status']=='UNKNOWN'
    from financial_evidence_currency_refresh import load_public_official_citations
    assert not any(k[1]=='investment_property_disposal_result' for k in load_public_official_citations(ROOT))


@pytest.mark.parametrize('change',[
    {'normalized_value':0}, {'knowledge_available_at':'2026-10-07T15:01:00+07:00'},
    {'reporting_period':'2025-H1'}, {'component_contract':None},
    {'ingress_contract':None}, {'period_type':'annual'}, {'currency':'USD'}, {'line_code':'31'},
    {'reported_component_evidence':{'literal_label':'other income'}},
])
def test_absent_stale_zero_or_unqualified_component_stays_unknown(change):
    source = all_rows()
    row = next(r for r in source if r.get('context_kind')=='EARNINGS_QUALITY_COMPONENT')
    row.update(change)
    assert project(source)['records']['VRE']['earnings_quality_context']['status']=='UNKNOWN'


def test_conflicting_component_cannot_become_known_quality():
    source = all_rows()
    other = deepcopy(next(r for r in source if r.get('context_kind')=='EARNINGS_QUALITY_COMPONENT'))
    other['normalized_value']+=1
    source.append(other)
    assert project(source)['records']['VRE']['earnings_quality_context']['status']=='UNKNOWN'


def test_usd_income_survives_consumers_without_fx_or_annual_input_promotion():
    old = baseline()
    old['records']['PVD'] = {'authority_tier': 'PROVIDER_RESEARCH', 'metrics': []}
    old.update(fundamental.content_identity(old))
    before = deepcopy(old)
    usd = rows('USD')
    assert {r['canonical_metric']: r['normalized_value'] for r in usd} == {
        'revenue':245730824, 'net_income':18272708, 'attributable_net_income':17920760}
    value = fundamental.project_session(baseline=old,official_rows=rows()+usd,session=SESSION,cutoff=CUTOFF)
    assert old == before and value['official_projection']['current_official_field_count'] == 7
    fields = value['records']['PVD']['official_field_context']
    assert len(fields) == 3
    assert all(f['currency']=='USD' and f['foreign_currency_conversion']=='NOT_PERMITTED'
               and f['valuation_use']=='NOT_PERMITTED_FOREIGN_CURRENCY_CONTEXT'
               and f['research_reason_codes']==['RESEARCH_PERIOD_NOT_ANNUAL'] for f in fields)
    assert _financial_input(value['records']['PVD'],value)['official_field_context'] == fields
    assert value['records']['PVD']['authority_tier'] == before['records']['PVD']['authority_tier']
    from financial_evidence_currency_refresh import load_public_official_citations
    assert not any(key[0]=='PVD' for key in load_public_official_citations(ROOT))
    from ai_research_session_delivery import _compact_context
    compact = _compact_context('PVD',{'product':{}},{'fundamental':value})
    assert compact['fundamental_context']['official_field_context'] == fields


@pytest.mark.parametrize('change,reason', [
    ({'projection_currency_policy':None},'OFFICIAL_VALUE_UNIT_NOT_QUALIFIED'),
    ({'unit_scale':1000},'OFFICIAL_VALUE_UNIT_NOT_QUALIFIED'),
    ({'knowledge_available_at':'2026-10-07T15:01:00+07:00'},'OFFICIAL_FACT_NOT_KNOWN_BY_SESSION_CUTOFF'),
    ({'currency':'EUR'},'OFFICIAL_VALUE_UNIT_NOT_QUALIFIED'),
])
def test_usd_context_is_bounded_and_invalid_row_does_not_widen_vnd_lane(change,reason):
    usd = rows('USD')
    assert len(usd)==3
    usd[0].update(change)
    value = project(rows()+usd)
    assert value['official_projection']['current_official_field_count']==6
    assert reason in value['official_projection']['rejected_fields'][0]['reasons']


def project(source=None):
    return fundamental.project_session(baseline=baseline(), official_rows=rows() if source is None else source,
                                       session=SESSION, cutoff=CUTOFF)


def test_reviewed_fact_is_current_without_annual_research_or_valuation_upgrade():
    old = baseline()
    before = deepcopy(old)
    value = fundamental.project_session(baseline=old, official_rows=rows(), session=SESSION, cutoff=CUTOFF)
    assert old == before
    assert value["official_projection"]["current_official_field_count"] == 4
    for ticker in ("PNJ", "VRE"):
        row = value["records"][ticker]
        assert {f['canonical_metric'] for f in row['official_field_context']} == {'revenue', 'net_income'}
        field = row["official_field_context"][0]
        assert field["temporal_status"] == "CURRENT_OFFICIAL_FACT"
        assert field["factual_status"] == "qualified"
        assert field["research_reason_codes"] == ["RESEARCH_PERIOD_NOT_ANNUAL"]
        assert field["ttm_derivation"] == "NOT_PERMITTED"
        assert row["metrics"] == before["records"][ticker]["metrics"]
        assert row["authoritative_periods_available"] == before["records"][ticker]["authoritative_periods_available"]
        assert row["baseline_metric_temporal_context"]["net_margin"]["temporal_status"] == "HISTORICAL_OFFICIAL_FACT"
        financial = _financial_input(row, value)
        assert financial["official_field_context"] == row["official_field_context"]
        assert financial["interim_context_does_not_supply_annual_valuation_inputs"]
    assert not value["records"]["HPG"]["official_field_context"]
    assert all(r["earnings_quality_context"]["status"] == "UNKNOWN" for r in value["records"].values())


@pytest.mark.parametrize("change,reason", [
    ({"knowledge_available_at": "2026-10-07T15:01:00+07:00"}, "OFFICIAL_FACT_NOT_KNOWN_BY_SESSION_CUTOFF"),
    ({"knowledge_available_at": None}, "OFFICIAL_FIELD_SEMANTICS_INCOMPLETE"),
    ({"unit_scale": None}, "OFFICIAL_VALUE_UNIT_NOT_QUALIFIED"),
    ({"audit_or_review_status": "unknown"}, "ASSURANCE_STATUS_NOT_ALLOWED"),
    ({"assurance_evidence": {}}, "REVIEWED_STATUS_WITHOUT_EVIDENCE"),
    ({"qualification_state": "BLOCKED"}, "VALUE_NOT_QUALIFIED_OR_OUTSIDE_FROZEN_COHORT"),
    ({"period_end": "2026-12-31"}, "FINANCIAL_PERIOD_END_AFTER_SESSION"),
])
def test_invalid_fields_remain_local(change, reason):
    source = rows()
    source[0].update(change)
    value = project(source)
    assert value["official_projection"]["current_official_field_count"] == 3
    assert reason in value["official_projection"]["rejected_fields"][0]["reasons"]


def test_conflicts_block_every_candidate_and_duplicate_evidence_does_not_add_coverage():
    source = rows()
    assert project(source + deepcopy(source))["official_projection"]["current_official_field_count"] == 4
    conflict = deepcopy(source[0]); conflict["normalized_value"] += 1
    value = project(source + [conflict])
    assert value["official_projection"]["current_official_field_count"] == 3
    assert all("TRUE_CONFLICT" in r["reasons"] for r in value["official_projection"]["rejected_fields"])


def test_old_interim_is_historical_and_never_current():
    source = rows()
    for row in source:
        row.update(reporting_period="2024-H1", period_start="2024-01-01", period_end="2024-06-30")
    value = project(source)
    assert value["official_projection"]["current_official_field_count"] == 0
    assert value["official_projection"]["historical_official_overlay_field_count"] == 4


def test_missing_metric_carries_no_official_or_provider_fact_claim():
    source = baseline()
    source["records"]["PNJ"]["metrics"].append({"metric_id": "cash_flow", "status": "MISSING"})
    source.update(fundamental.content_identity(source))
    value = fundamental.project_session(baseline=source, official_rows=rows(), session=SESSION, cutoff=CUTOFF)
    assert value["records"]["PNJ"]["baseline_metric_temporal_context"]["cash_flow"]["temporal_status"] == "UNKNOWN"


def event_context(session=SESSION):
    source = {"ticker": "PNJ", "event_type": "CASH_DIVIDEND", "event_state": "RECENT",
              "published_at": None, "record_date": "2026-10-06", "ex_date": "2026-10-05",
              "execution_date": None, "official_observed_at": "2026-10-06T01:00:00Z",
              "source": "OFFICIAL", "source_identity": "evidence:one", "source_url": None,
              "qualification": "EX_DATE_OFFICIAL_QUALIFIED", "materiality_status": "UNKNOWN_APPLICABILITY",
              "publication_availability": "UNKNOWN", "event_id": "official:one"}
    value = {"contract_version": official.CONTRACT_VERSION, "research_session": session,
             "corporate_intelligence_adapter": {"events": [source, deepcopy(source)]},
             "records": {"PNJ": {"events": [source]}}, "all_current_universe_event_records": [source]}
    value.update(official._identity(value))
    return value


def test_ci_uses_official_session_events_without_invented_governance_or_dates(monkeypatch):
    monkeypatch.setattr(ci, "load_retained_events", lambda root, session, context=None: ci._official_event_context_events(context, session))
    value = ci.build(descriptive={"session": SESSION, "records": {"PNJ": {}}, "artifact_identity": "desc"},
                     fundamental=project(), session=SESSION, root=ROOT, official_event_context=event_context())
    assert value["coverage"]["current_event_coverage"] == 1
    assert value["coverage"]["governance_coverage"] == value["coverage"]["ownership_coverage"] == 0
    event = value["events"][0]
    assert event["announcement_date"] is None
    assert event["status"] == "OFFICIAL_EVENT_CONTEXT"
    assert event["ex_date"] != event["record_date"]
    assert event["materiality_status"] == "UNKNOWN_APPLICABILITY"
    with pytest.raises(ValueError, match="SESSION_OR_CONTRACT"):
        ci._official_event_context_events(event_context("2026-10-06"), SESSION)


def test_packet_requires_same_event_identity_and_session():
    event = {"contract_version": corporate.CONTRACT_VERSION, "research_session": SESSION,
             "source_artifact_identities": {"current_official_event_context": "official:one"},
             "records": {"PNJ": {"events": [], "qualified_event_count": 0}}}
    event.update(corporate.content_identity(event))
    opportunity = {"contract_version": "current_opportunity_prioritization/v1", "research_session": SESSION,
                   "source_artifact_identities": {"event_context": "official:one"}, "records": {"PNJ": {}}}
    opportunity.update(opportunity_identity(opportunity))
    assert packet.build_artifact(opportunity=opportunity, corporate_event=event)["component_manifest"]["corporate_event"]["status"] == "PRESENT"
    for change in ({"research_session": "2026-10-06"}, {"source_artifact_identities": {"current_official_event_context": "different"}}):
        stale = deepcopy(event); stale.update(change); stale.update(corporate.content_identity(stale))
        result = packet.build_artifact(opportunity=opportunity, corporate_event=stale)
        assert result["component_manifest"]["corporate_event"]["authority_use_status"] == "EXACT_SESSION_EVENT_BINDING_MISMATCH"
        assert "corporate_event_context" not in result["records"]["PNJ"]["components"]


def test_event_session_projection_keeps_parent_bytes_dates_and_known_time():
    parent = event_context("2026-10-06")
    parent["coverage"] = {"event_context_records": 1, "event_context_tickers": 1}
    parent.update(official._identity(parent))
    before = deepcopy(parent)
    result = official.project_session_context(parent, session=SESSION, cutoff=CUTOFF)
    assert parent == before
    assert result["projection_source_artifact_identity"] == parent["artifact_identity"]
    assert result["research_session"] == SESSION
    event = result["all_current_universe_event_records"][0]
    assert event["days_since_ex_date"] == 2
    assert event["ex_date"] == "2026-10-05"
    assert event["record_date"] == "2026-10-06"
    assert event["published_at"] is None
    assert event["official_observed_at"] == "2026-10-06T01:00:00Z"
    assert official.project_session_context(result, session=SESSION, cutoff=CUTOFF) == result
    parent["all_current_universe_event_records"][0]["official_observed_at"] = "2026-10-07T15:01:00+07:00"
    parent.update(official._identity(parent))
    with pytest.raises(ValueError, match="NOT_KNOWN"):
        official.project_session_context(parent, session=SESSION, cutoff=CUTOFF)


def test_session_projection_is_registered_and_completed_locks_reject_replacement(tmp_path):
    import daily_session_level2_package as level2
    import canonical_post_close_pipeline as canonical
    registry_path = tmp_path / "config/daily_research_session_input_registry.json"
    registry_path.parent.mkdir()
    registry_path.write_text(json.dumps({"sessions": {}, "completed_sessions": {}}), encoding="utf-8")
    paths = level2.session_artifact_paths(tmp_path, SESSION)
    for key in canonical.REQUIRED_REGISTRY_KEYS:
        path = paths[canonical.REGISTRY_KEY_TO_LEVEL2_KEY[key]]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"artifact_identity": key + ":fixture"}), encoding="utf-8")
    value = project()
    output = level2.session_fundamental_path(tmp_path, SESSION)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value), encoding="utf-8")
    result = canonical.register_session_inputs(tmp_path, SESSION, corporate_frozen_inputs={})
    assert result["selection"]["fundamental"]["artifact_identity"] == value["artifact_identity"]
    registered = json.loads(registry_path.read_text(encoding="utf-8"))
    registered["completed_sessions"][SESSION] = {"status": "COMPLETED_RETAINED_EVIDENCE",
        "frozen_input_identities": {"fundamental": "frozen:old"}}
    registry_path.write_text(json.dumps(registered), encoding="utf-8")
    with pytest.raises(ValueError, match="COMPLETED_SESSION_FUNDAMENTAL_MUTATION_REJECTED"):
        canonical.register_session_inputs(tmp_path, SESSION, corporate_frozen_inputs={})


def test_delivery_preserves_field_context_beyond_the_generic_compactor():
    from ai_research_session_delivery import _compact_context
    value = project()
    context = _compact_context("PNJ", {"product": {}}, {
        "fundamental": value, "corporate_intelligence": {"session": SESSION,
            "source_artifact_identities": {"official_event_context": "official:exact"}}})
    assert context["fundamental_context"]["official_field_context"] == value["records"]["PNJ"]["official_field_context"]
    assert context["fundamental_context"]["source_artifact_identity"] == value["artifact_identity"]
    assert context["official_event_context_binding"]["artifact_identity"] == "official:exact"
    assert context["fundamental_context"]["official_field_context"][0]["research_reason_codes"] == ["RESEARCH_PERIOD_NOT_ANNUAL"]


def test_delivery_localizes_a_differently_bound_event_context():
    from ai_research_session_delivery import _compact_context
    context = _compact_context("PNJ", {"product": {}, "manifest": {"market_session": SESSION}}, {
        "event_context": {"artifact_identity": "official:selected"},
        "corporate_intelligence": {"session": SESSION,
            "source_artifact_identities": {"official_event_context": "official:different"}}})
    assert context["official_event_context_binding"]["status"] == "UNAVAILABLE"
    assert context["official_event_context_binding"]["reason"] == "EXACT_SESSION_EVENT_BINDING_MISMATCH"
