import json
from pathlib import Path
import pandas as pd
import provider_financial_source_metadata as m


def _request(): return m.plan_for_tickers(["AAA"])[0]

def _raw():
    return {"Audit":[{"AuditedStatusCode":"A","Description":"Audited"}], "Unit":[{"UnitedCode":"HN","UnitedName":"Hợp nhất"}],
            "Head":[{"ID":1,"YearPeriod":2024,"TermName":"Năm","PeriodBegin":"2024-01-01","PeriodEnd":"2024-12-31","ReportDate":"2025-03-01","LastUpdate":"2025-03-02","United":"HN","AuditedStatus":"A"}],
            "Content":{"Kết quả kinh doanh":[{"ID":1,"Name":"Revenue","NameEn":"Revenue","Unit":"VND","Value1":12.5}]}}

def test_raw_hash_is_exact_and_deterministic(tmp_path):
    body = json.dumps(_raw(), separators=(",", ":")).encode()
    assert m._hash_bytes(body) == m._hash_bytes(bytes(body))
    p = m.raw_response_path(tmp_path, _request(), m._hash_bytes(body)); p.parent.mkdir(); p.write_bytes(body)
    assert p.read_bytes() == body

def test_sidecar_retains_only_source_metadata_and_no_scope_inference():
    request = {**_request(), "retrieved_at":"2026-08-27T00:00:00Z"}
    row = m.metadata_rows(request, _raw(), raw_hash="raw", adapter_payload_sha256="adapter")[0]
    assert row["period_start"] == "2024-01-01" and row["audit_review_status"] == "Audited"
    assert row["statement_scope"] == "consolidated" and row["currency"] is None and row["scale"] is None
    assert row["unit"] is None  # source `United` is its scope label, not a numeric unit.

def test_exact_payload_lineage_is_required_for_join():
    obs = {"provider":"KBS","ticker":"AAA","statement_family":"income_statement","reporting_period":"2024","source_sha256":"right","observation_id":"o"}
    meta = {"provider":"KBS","ticker":"AAA","statement_family":"income_statement","fiscal_period":"2024","adapter_payload_sha256":"wrong"}
    assert m.join_metadata_exact([obs], [meta])[0]["metadata_joined"] is False

def test_kbs_and_vci_contracts_cannot_cross_propagate():
    assert {x["provider"] for x in m.plan_for_tickers(["AAA"])} == {"KBS"}
    assert all(x["request_mode"] == "annual" for x in m.plan_for_tickers(["AAA"]))

def test_no_numeric_unit_inference_in_source_module():
    source = Path(m.__file__).read_text(encoding="utf-8")
    assert "value <" not in source and "looks right" not in source

def test_flow_reconciliation_keeps_missing_currency_explicit():
    fact = {"ticker":"AAA","provider":"KBS","statement_family":"income_statement","reporting_period":"2024",
            "source_sha256":"payload","canonical_metric":"revenue","value":100}
    meta = {"provider":"KBS","ticker":"AAA","statement_family":"income_statement","fiscal_period":"2024",
            "adapter_payload_sha256":"payload","statement_scope":"consolidated","currency":None,"unit":None,"scale":None}
    result = m.reconcile_annual_flow_facts([fact], [meta], {("AAA","revenue","2024"):{"value":100}})
    assert result["counts"]["NOT_COMPARABLE_CURRENCY_UNKNOWN"] == 1 and result["residual_zero"]

def test_scope_and_unit_gates_remain_distinct():
    fact = {"ticker":"AAA","provider":"KBS","statement_family":"income_statement","reporting_period":"2024","source_sha256":"p","canonical_metric":"revenue","value":100}
    base = {"provider":"KBS","ticker":"AAA","statement_family":"income_statement","fiscal_period":"2024","adapter_payload_sha256":"p","currency":"VND","unit":None,"scale":None}
    scope = m.reconcile_annual_flow_facts([fact], [{**base,"statement_scope":None}], {("AAA","revenue","2024"):{"value":100}})
    unit = m.reconcile_annual_flow_facts([fact], [{**base,"statement_scope":"consolidated"}], {("AAA","revenue","2024"):{"value":100}})
    assert scope["counts"]["NOT_COMPARABLE_SCOPE_UNKNOWN"] == 1
    assert unit["counts"]["NOT_COMPARABLE_UNIT_UNKNOWN"] == 1

def test_fiscal_year_mismatch_is_explicit_missing_provider():
    result = m.reconcile_annual_flow_facts([], [], {("AAA","revenue","2024"):{"value":100}})
    assert result["counts"]["MISSING_PROVIDER"] == 1 and result["residual_zero"]
