"""Targeted tests for canonical_post_close_pipeline.run_current_foreign_flow_enrichment --
the post-handoff, best-effort integration point (Phase 17/18/24/25 of
CURRENT_FOREIGN_FLOW_RETENTION_PRODUCTIONIZATION_V1). Never invokes the full
run_canonical_post_close pipeline (expensive, broad fixture surface); isolates this one step,
matching the existing convention in tests/test_flow_price_divergence_shadow.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import canonical_post_close_pipeline as cpc
import current_foreign_flow_retention as retention

ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-09-18"
_REAL_BUILD_MANIFEST_FROM_ROOT = retention.build_manifest_from_root


def test_default_network_off_reports_pending_network_and_touches_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "build_manifest_from_root", lambda _root, session: _REAL_BUILD_MANIFEST_FROM_ROOT(ROOT, session))
    result = cpc.run_current_foreign_flow_enrichment(tmp_path, tmp_path / "runtime", SESSION)
    assert result["status"] == "PENDING_NETWORK"
    assert result["network_calls_made"] == 0
    assert result["requested_count"] == 11
    written = json.loads((tmp_path / result["path"]).read_text(encoding="utf-8"))
    assert written["network"]["allow_network"] is False
    # Never writes anywhere inside the real repository root.
    assert not (ROOT / "operations-review" / "current-foreign-flow-enrichment-v1" / SESSION).exists()


def test_allow_network_true_still_needs_credentials_and_never_raises(tmp_path, monkeypatch):
    # Never let this test reach a real network call, even on a machine with a real, valid
    # C:\Users\...\.stocklookup\secrets.env: clear the env-var path AND redirect the file path
    # this process would otherwise fall back to, to one that provably does not exist.
    for key in ("DNSE_API_KEY", "DNSE_API_SECRET", "LIVESPEED_API_KEY", "LIVESPEED_API_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("STOCK_LOOKUP_SECRETS_FILE", str(tmp_path / "no_such_secrets.env"))
    monkeypatch.setattr(retention, "build_manifest_from_root", lambda _root, session: _REAL_BUILD_MANIFEST_FROM_ROOT(ROOT, session))
    result = cpc.run_current_foreign_flow_enrichment(tmp_path, tmp_path / "runtime", SESSION, allow_network=True)
    assert result["status"] == "FAILED_OPERATIONAL"  # credentials unavailable for every ticker
    assert result["network_calls_made"] == 0


def test_manifest_failure_degrades_to_unavailable_never_raises(tmp_path):
    result = cpc.run_current_foreign_flow_enrichment(tmp_path, tmp_path / "runtime", "not-a-real-session")
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"].startswith("CURRENT_FOREIGN_FLOW_ENRICHMENT_FAILED:")


def test_cli_flag_wires_through_to_run_canonical_post_close_default_false():
    import inspect
    signature = inspect.signature(cpc.run_canonical_post_close)
    assert signature.parameters["enable_current_foreign_flow_live"].default is False
