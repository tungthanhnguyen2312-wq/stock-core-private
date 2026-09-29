"""Permanent regression boundary for the retired Vnstock acquisition family."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import multi_source_exact_session_resolver as resolver
import provider_execution_guard as guard
import provider_runtime_state as runtime
from tools.audit_zero_active_vnstock import RETAINED_SUMMARY, build_audit

ROOT = Path(__file__).resolve().parents[1]


def test_reachable_product_import_graph_and_requirements_are_zero_active():
    result = build_audit(ROOT)
    hermetic_findings = [item for item in result["findings"] if not item.startswith("RETAINED_")]
    assert hermetic_findings == []
    assert result["active_vnstock_import_count"] == 0
    assert result["active_vnai_import_count"] == 0
    assert result["active_kbs_vci_acquisition_path_count"] == 0
    assert result["active_dependency_count"] == 0
    assert result["forbidden_import_findings"] == []
    assert result["retired_runtime_files_present"] == []
    assert result["runtime_policy_state"] == "RETIRED_PROVIDER"
    assert result["provider_requirements_state"]["vnstock_or_vnai_declared"] == []
    assert result["canonical_base_sha"] == "3137441656019e4b7974978f034915d361b5c307"
    assert result["content_identity"].startswith("zero_active_vnstock_audit/v1:")


def test_retired_policy_and_worker_files_cannot_launch():
    policy = runtime.load_provider_policy()
    assert policy.policy == runtime.POLICY_RETIRED_PROVIDER
    for filename in ("vnstock_worker_process.py", "vnstock_worker_client.py",
                     "vnstock_worker_protocol.py", "vnstock_rate_governor.py", "vn_stock_pipeline.py"):
        assert not (ROOT / filename).exists()


def test_legacy_acquisition_operation_refused_before_any_provider_import():
    for item in guard.registry_record()["operations"]:
        with pytest.raises(guard.RetiredProviderOperation):
            guard.require_governed_provider_execution(item["operation"])


def test_public_resolver_cannot_accept_a_live_recovery_fetcher():
    args = {"dnse_snapshot": {"records": {}}, "target_session": "2026-09-28",
            "requested_at": "2026-09-28T20:00:00+07:00"}
    with pytest.raises(resolver.MultiSourceResolverError, match="RETIRED_PROVIDER_FETCH_INJECTION_FORBIDDEN"):
        resolver.resolve_multi_source_exact_session_snapshot(**args, fetch_single_source=lambda *_: None)
    with pytest.raises(resolver.MultiSourceResolverError, match="RETIRED_PROVIDER_CANNOT_BE_AVAILABLE"):
        resolver.resolve_multi_source_exact_session_snapshot(**args, supplemental_runtime_state={"state": "AVAILABLE"})


@pytest.mark.retained_evidence(RETAINED_SUMMARY.as_posix())
def test_retained_research_lineage_is_still_readable_and_not_official():
    result = build_audit(ROOT)
    assert result["retained_historical_lineage_count"] == {"KBS": 31389, "VCI": 94836}
    summary = json.loads((ROOT / RETAINED_SUMMARY).read_text(encoding="utf-8"))
    assert summary["authority_boundary"]["official_or_owner_promotion"] is False
    assert summary["authority_boundary"]["projection_only"] is True
