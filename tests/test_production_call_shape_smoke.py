"""Offline smoke for the owner Daily's production-default orchestration path.

This deliberately does *not* inject any of ``run_canonical_daily_operation``'s public
function arguments.  Instead, it replaces only the side-effecting implementation
boundaries on the imported module with deterministic temporary-fixture equivalents.
That leaves the production ``None -> default symbol`` resolution and its ordering in
place, including the pre-seal registry/comparator route that a convenience producer
injection used to skip.
"""
from __future__ import annotations

import http.client
import importlib
import importlib.abc
import json
import socket
import sys
import urllib.request
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pytest
import requests

import canonical_daily_operation as cdo
import canonical_post_close_pipeline as cpc
from vn_time import VN_TZ


SESSION = "2026-08-26"
POST_CLOSE = datetime(2026, 8, 26, 19, 19, tzinfo=VN_TZ)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PROVIDER_IMPORT_PREFIXES = (
    "dnse", "kbs", "vci", "fred", "yahoo", "world_bank", "vnstock", "vnai",
)


class OfflineSmokeViolation(AssertionError):
    """Raised immediately when the contained CI smoke reaches an external seam."""


class _ProviderImportGuard(importlib.abc.MetaPathFinder):
    def __init__(self, counters: dict[str, int]) -> None:
        self._counters = counters

    def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:  # type: ignore[override]
        root = fullname.partition(".")[0].lower()
        if root.startswith(_PROVIDER_IMPORT_PREFIXES):
            self._counters["provider"] += 1
            if root in {"vnstock", "vnai"}:
                self._counters["vnstock_import"] += 1
            raise OfflineSmokeViolation(f"PROVIDER_IMPORT_FORBIDDEN:{fullname}")
        return None


def _provider_modules_loaded() -> list[str]:
    return sorted(
        name for name in sys.modules
        if name.partition(".")[0].lower() in {"vnstock", "vnai"}
    )


@contextmanager
def _offline_smoke_guard() -> Iterator[dict[str, int]]:
    """Contain transport and provider-import blocks to one smoke invocation only."""
    assert not _provider_modules_loaded(), "VNSTOCK_OR_VNAI_ALREADY_IMPORTED_BEFORE_SMOKE"
    counters = {"network": 0, "provider": 0, "vnstock_import": 0}

    def blocked_network(*_args: object, **_kwargs: object) -> None:
        counters["network"] += 1
        raise OfflineSmokeViolation("NETWORK_FORBIDDEN_IN_PRODUCTION_CALL_SHAPE_SMOKE")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(requests.sessions.Session, "request", blocked_network)
        patch.setattr(urllib.request, "urlopen", blocked_network)
        patch.setattr(urllib.request.OpenerDirector, "open", blocked_network)
        patch.setattr(socket, "create_connection", blocked_network)
        patch.setattr(socket.socket, "connect", blocked_network)
        patch.setattr(http.client.HTTPConnection, "connect", blocked_network)
        patch.setattr(http.client.HTTPSConnection, "connect", blocked_network)
        patch.setattr(sys, "meta_path", [_ProviderImportGuard(counters), *sys.meta_path])
        yield counters
    assert not _provider_modules_loaded(), "VNSTOCK_OR_VNAI_IMPORTED_DURING_SMOKE"


def _snapshot(session: str) -> dict[str, Any]:
    return {
        "resolved_completed_session": session,
        "retained_snapshot_session": session,
        "snapshot_sha256": "a" * 64,
        "snapshot_identity": "p3f9_exact_session_snapshot:" + "a" * 64,
        "contract_version": "p3f9_exact_session_mva_snapshot/v2",
        "materialization_scope": "FULL_CANONICAL_CANDIDATE_SET",
        "unattempted_without_explicit_disposition": 0,
        "attempted_candidate_count": 1683,
        "exact_session_observed_count": 889,
        "requested_at": f"{session}T19:19:00+07:00",
    }


def _write_runtime(runtime_root: Path, session: str) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "bundle_manifest.json").write_text(json.dumps({
        "freshness": {"reference_session": session, "blocked": False, "status": "fresh"},
    }), encoding="utf-8")
    (runtime_root / "screen_snapshot.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{session}\n", encoding="utf-8"
    )
    (runtime_root / "market_breadth.csv").write_text(
        f"group,date\nALL,{session}\n", encoding="utf-8"
    )
    (runtime_root / "analysis_latest.json").write_text(json.dumps({
        "summary": {"session_date": session},
    }), encoding="utf-8")
    (runtime_root / "screen_snapshot_live.csv").write_text(
        f"ticker,exchange,date\nHPG,HSX,{session}\n", encoding="utf-8"
    )


def _producer_result(session: str) -> dict[str, Any]:
    return {
        "status": "COMPLETED",
        "session": session,
        "run_identity": "daily_producer_run:production-call-shape-smoke",
        "operation": {
            "opportunity": None,
            "manifest": {"operation_identity": "daily_research_session_operation:production-call-shape-smoke"},
        },
        "manifest": {
            "daily_session_shadow_recommendation": {
                "status": "REUSED",
                "session": session,
                "artifact_identity": "daily_session_shadow_recommendation:production-call-shape-smoke",
                "shadow_security_recommendation_identity": "shadow_security_recommendation:production-call-shape-smoke",
                "fundamental_invalidation_identity": "fundamental_thesis_invalidation_precision:production-call-shape-smoke",
                "source_artifact_identities": {},
            },
        },
    }


def _run_offline_production_shape(
    tmp_path: Path,
    *,
    producer_impl: Any | None = None,
    trace: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute the production-default branch with only synthetic side-effect boundaries."""
    trace = trace if trace is not None else {}
    repo_root = tmp_path / "producer"
    retained_root = tmp_path / "retained"
    output_root = tmp_path / "output"
    runtime_root = tmp_path / "runtime"
    repo_root.mkdir(parents=True)
    retained_root.mkdir(parents=True)
    _write_runtime(runtime_root, SESSION)
    registry_path = repo_root / "config" / "daily_research_session_input_registry.json"
    registry_path.parent.mkdir()
    registry_path.write_text(json.dumps({
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": {},
        "sessions": {},
    }), encoding="utf-8")

    with _offline_smoke_guard() as counters, pytest.MonkeyPatch.context() as patch:
        trace["counters"] = counters
        trace["events"] = events = []
        delivery = importlib.import_module("ai_research_session_delivery")
        next_brief = importlib.import_module("next_session_decision_brief")
        daily_brief = importlib.import_module("daily_integrated_decision_brief")
        comparison = importlib.import_module("session_comparison_semantics")

        def blocked_provider_boundary(*_args: Any, **_kwargs: Any) -> None:
            counters["provider"] += 1
            raise OfflineSmokeViolation("PROVIDER_ACQUISITION_FORBIDDEN_IN_PRODUCTION_CALL_SHAPE_SMOKE")

        def synthetic_acquire(root: Path, session: str, runtime: Path, **kwargs: Any) -> dict[str, Any]:
            events.append("acquire")
            assert root == repo_root and runtime == runtime_root
            assert kwargs["no_new_provider_acquisition"] is True
            snapshot = _snapshot(session)
            return {
                "snapshot": snapshot,
                "resolved_completed_session": session,
                "coverage": {"exact_session_retained_count": 889, "total_candidates": 1683, "ratio": 889 / 1683},
                "artifact_root": retained_root,
                "eligibility": {"reused_existing_eligible_artifact": True, "redirected": False},
                "provider_contribution_counts": {},
            }

        def synthetic_register(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            events.append("register")
            return {"status": "REGISTERED", "session": SESSION, "selection": {}}

        def synthetic_freeze(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            events.append("freeze")
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["completed_sessions"][SESSION] = {
                "status": "COMPLETED_RETAINED_EVIDENCE",
                "trading_day_valid": True,
                "smoke_marker": "FROZEN_BEFORE_PRODUCTION_DEFAULT_REGISTRY_READ",
            }
            registry_path.write_text(json.dumps(registry, sort_keys=True), encoding="utf-8")
            return {"status": "FROZEN", "session": SESSION}

        def synthetic_enrichment(_root: Path, session: str, **_kwargs: Any) -> dict[str, Any]:
            events.append("enrichment")
            return {"integrated_investment_decision_product": {"status": "BUILT", "artifact": {
                "contract_version": "integrated_investment_decision_product/v1",
                "session": session,
                "artifact_identity": "integrated_investment_decision_product/v1:production-call-shape-smoke",
                "records": {},
            }}}

        def synthetic_refresh(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            events.append("macro_refresh")
            return {"status": "FAILED", "reason_code": "SMOKE_MACRO_NETWORK_UNAVAILABLE"}

        def synthetic_macro_context(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            events.append("macro_context")
            return {"status": "UNAVAILABLE", "reason_code": "SMOKE_MACRO_NETWORK_UNAVAILABLE"}

        def synthetic_delivery(*_args: Any, **_kwargs: Any) -> dict[str, bytes]:
            events.append("preseal_delivery")
            return {"primary": b"{}"}

        def synthetic_next_brief(**kwargs: Any) -> dict[str, Any]:
            events.append("comparator")
            registry = kwargs["registry"]
            assert registry["completed_sessions"][SESSION]["smoke_marker"] == "FROZEN_BEFORE_PRODUCTION_DEFAULT_REGISTRY_READ"
            return {"comparison_metadata": comparison.build_comparison_metadata(
                registry=registry,
                current_session=kwargs["current_session"],
                comparison_session=kwargs["previous_session"],
            )}

        def synthetic_daily_brief(**kwargs: Any) -> dict[str, Any]:
            events.append("daily_brief")
            return {
                "contract_version": "daily_integrated_decision_brief/v1",
                "session": kwargs["session"],
                "artifact_identity": "daily_integrated_decision_brief/v1:production-call-shape-smoke",
                "comparison_metadata": kwargs["next_session_brief"]["comparison_metadata"],
            }

        def synthetic_producer(_root: Path, **kwargs: Any) -> dict[str, Any]:
            events.append("producer")
            builder = kwargs["daily_integrated_decision_brief_builder"]
            built = builder({
                "manifest": {"market_session": SESSION, "operation_identity": "preseal:production-call-shape-smoke"},
                "integrated_delivery": {"integrated_investment_decision_product": kwargs["integrated_investment_decision_product"]},
                "inputs": {},
                "decision_queue": None,
            })
            assert built["comparison_metadata"]["comparison_session_role"] == "NO_PREVIOUS_GOVERNED_SESSION"
            return _producer_result(SESSION)

        def synthetic_runtime(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            events.append("runtime")
            return {"session": SESSION, "live_count": 889}

        def synthetic_trusted(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            events.append("trusted")
            return {"session": SESSION, "trusted_subset_ready": True, "records_fingerprint": "smoke"}

        # Protect both provider acquisition seams for this invocation.  The canonical operation
        # receives a synthetic retained snapshot through its normal default-resolution name;
        # the underlying real wrapper and provider probe remain explicit fail-fast boundaries.
        patch.setattr(cpc, "acquire_and_materialize", blocked_provider_boundary)
        patch.setattr(cdo, "_working_dates_probe", blocked_provider_boundary)
        patch.setattr(cdo, "acquire_and_materialize", synthetic_acquire)
        patch.setattr(cdo, "register_session_inputs", synthetic_register)
        patch.setattr(cdo, "validate_and_freeze_completed_session", synthetic_freeze)
        patch.setattr(cdo, "build_enrichment_components", synthetic_enrichment)
        patch.setattr(cdo, "refresh_macro_snapshot", synthetic_refresh)
        patch.setattr(cdo, "build_macro_presentation_context", synthetic_macro_context)
        patch.setattr(delivery, "build_delivery", synthetic_delivery)
        patch.setattr(next_brief, "build_from_current_delivery_payload", synthetic_next_brief)
        patch.setattr(daily_brief, "build_from_session", synthetic_daily_brief)
        patch.setattr(cdo, "run_daily_producer", producer_impl or synthetic_producer)
        patch.setattr(cdo, "materialize_canonical_runtime_release", synthetic_runtime)
        patch.setattr(cdo, "materialize_canonical_trusted_subset", synthetic_trusted)
        patch.setattr(cdo, "retain_prospective_decision_snapshot", lambda *_a, **_k: {
            "status": "RETAINED", "artifact": {"snapshot_identity": "prospective:smoke", "source_integrated_decision_artifact": {"artifact_identity": "integrated:smoke"}},
        })
        patch.setattr(cdo, "build_decision_packet", lambda *_a, **_k: {"artifact_identity": "decision_packet:smoke"})
        patch.setattr(cdo, "run_prospective_collection", lambda *_a, **_k: {
            "status": "COLLECTED", "snapshot": {"snapshot_id": "prospective_cohort:smoke"},
        })
        patch.setattr(cdo, "run_tactical_reversal_shadow_collection", lambda *_a, **_k: {
            "status": "SHADOW_COLLECTION_FAILED", "session": SESSION, "reason": "SMOKE_OPTIONAL_FAILURE",
        })
        patch.setattr(cdo, "build_tiered_bundle", lambda *_a, **_k: {"bundle_dir": output_root / "bundle"})
        patch.setattr(cdo, "invoke_release_orchestrator_complete_publication", lambda *_a, **_k: pytest.fail("publication must be disabled"))
        patch.setattr(cdo, "_git_head", lambda *_a, **_k: "production-call-shape-smoke")

        record = cdo.run_canonical_daily_operation(
            repo_root,
            runtime_root,
            SESSION,
            now=POST_CLOSE,
            complete_publication=False,
            working_dates_evidence={"workingDates": [SESSION, "2026-08-27"]},
            exact_session_evidence=_snapshot(SESSION),
            retained_evidence_root=retained_root,
            operation_output_root=output_root,
            no_new_provider_acquisition=True,
        )
        assert counters == {"network": 0, "provider": 0, "vnstock_import": 0}
    return record, trace


def test_production_default_call_shape_is_offline_and_nonblocking(tmp_path: Path) -> None:
    record, trace = _run_offline_production_shape(tmp_path)
    assert record["daily_operation_state"] == cdo.STATE_LOCAL_COMPLETE
    assert record["publication"] is None
    assert record["macro_refresh"]["status"] == "FAILED"
    assert record["macro_presentation_context_status"] == "UNAVAILABLE"
    assert record["tactical_reversal_shadow_collection"]["status"] == "SHADOW_COLLECTION_FAILED"
    assert trace["events"].index("freeze") < trace["events"].index("producer") < trace["events"].index("comparator")
    assert trace["events"].index("macro_refresh") < trace["events"].index("producer")
    assert trace["counters"] == {"network": 0, "provider": 0, "vnstock_import": 0}
    assert Path(record["operation_directory"]).is_relative_to(tmp_path)


def test_owner_daily_entry_route_remains_canonical() -> None:
    """Keep the PowerShell -> CLI -> canonical-pipeline ownership route explicit in CI.

    The smoke below runs in-process so its transport guard cannot be escaped by a child process;
    this small structural assertion catches an accidental owner-entry route change separately.
    """
    powershell = (REPOSITORY_ROOT / "stocklookup.ps1").read_text(encoding="utf-8")
    owner_cli = (REPOSITORY_ROOT / "stocklookup.py").read_text(encoding="utf-8")
    daily_pipeline = (REPOSITORY_ROOT / "daily_analysis_pipeline.py").read_text(encoding="utf-8")
    assert "stocklookup.py" in powershell
    assert "daily_analysis_pipeline.py" in owner_cli
    assert '"--canonical-post-close"' in owner_cli
    assert "run_canonical_daily_operation(" in daily_pipeline


def test_production_default_smoke_is_deterministic_in_a_clean_temp_runtime(tmp_path: Path) -> None:
    first, _ = _run_offline_production_shape(tmp_path / "first")
    second, _ = _run_offline_production_shape(tmp_path / "second")
    assert first["operation_identity"] == second["operation_identity"]
    assert first["daily_operation_state"] == second["daily_operation_state"] == cdo.STATE_LOCAL_COMPLETE


def test_offline_guard_blocks_requests_urllib_and_vnstock_import() -> None:
    with _offline_smoke_guard() as counters:
        with pytest.raises(OfflineSmokeViolation, match="NETWORK_FORBIDDEN"):
            requests.get("https://example.invalid")
        with pytest.raises(OfflineSmokeViolation, match="NETWORK_FORBIDDEN"):
            urllib.request.urlopen("https://example.invalid")
        with pytest.raises(OfflineSmokeViolation, match="PROVIDER_IMPORT_FORBIDDEN:vnstock"):
            importlib.import_module("vnstock")
        assert counters == {"network": 2, "provider": 1, "vnstock_import": 1}


def test_smoke_fails_loudly_for_a_default_producer_signature_mismatch(tmp_path: Path) -> None:
    trace: dict[str, Any] = {}

    def broken_producer(_root: Path) -> dict[str, Any]:
        return _producer_result(SESSION)

    with pytest.raises(TypeError, match="unexpected keyword"):
        _run_offline_production_shape(tmp_path, producer_impl=broken_producer, trace=trace)
    assert trace["counters"] == {"network": 0, "provider": 0, "vnstock_import": 0}
