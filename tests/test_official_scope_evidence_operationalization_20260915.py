"""Focused regression coverage for
OFFICIAL_SCOPE_EVIDENCE_OPERATIONALIZATION_AND_DASHBOARD_CUTOVER_READINESS_V1.

Covers the durable-evidence resolver contract added to
``canonical_current_product_projections.resolve_current_research_official_universe_scope`` /
``current_official_market_universe.verify_retained_artifact``, the migration/seed tool
(``current_official_universe_evidence_retention.retain_evidence``), and the real-evidence
2026-09-14 replay this milestone requires. Tests that need the real, git-tracked retained
evidence at ``CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_RELATIVE`` (or the 2026-09-14 registry inputs
copied in for the replay) skip gracefully when a checkout genuinely lacks them -- the same
``_REQUIRES_REAL_EVIDENCE`` convention ``tests/test_current_research_official_universe_scope_
integration_20260913.py`` already uses -- never fabricate a substitute.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import canonical_current_product_projections as ccpp
import current_official_market_universe as com
from current_official_universe_evidence_retention import RetentionError, retain_evidence


ROOT = Path(__file__).resolve().parents[1]
REAL_EVIDENCE_PATH = ROOT / ccpp.CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_RELATIVE
_REQUIRES_REAL_EVIDENCE = pytest.mark.skipif(
    not REAL_EVIDENCE_PATH.is_file(), reason="Durable current-official-universe evidence not present in this checkout."
)

REAL_TACTICAL_20260914 = ROOT / "operations-review/watchlist-tactical-entry-decision-v1-20260914/watchlist_tactical_entry_classifier_artifact.json"
REAL_VALUATION_20260914 = ROOT / "operations-review/market-wide-current-valuation-v1-20260914-session20260914/market_wide_current_valuation_artifact.json"
_REQUIRES_20260914_REPLAY_INPUTS = pytest.mark.skipif(
    not (REAL_TACTICAL_20260914.is_file() and REAL_VALUATION_20260914.is_file()),
    reason="Real 2026-09-14 tactical/valuation registry inputs not present in this checkout.",
)


def _synthetic_official_artifact(*, observed_at: str = "2026-09-13T08:00:00Z") -> dict:
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": com.CONTRACT_VERSION,
        "records": {
            "AAA": {
                "stocklookup_candidate": True,
                "current_universe_status": com.OFFICIAL_CURRENT_EXCHANGE_SECURITY,
                "official_observed_at": observed_at,
                "official_security_status": "NORMAL_OR_NO_SPECIAL_STATUS",
                "qualification": None,
            },
            "BBB": {
                "stocklookup_candidate": True,
                "current_universe_status": None,
                "official_observed_at": observed_at,
                "official_security_status": None,
                "qualification": "UNRESOLVED",
            },
        },
    }
    artifact.update(com._identity(artifact))
    return artifact


def _write_pinned_evidence(tmp_root: Path, artifact: dict) -> Path:
    path = tmp_root / ccpp.CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------------------------
# 1. Durable evidence survives absence of the old worktree (worktree-independence proof)
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
def test_1_worktree_independent_resolution_from_a_bare_tmp_checkout(tmp_path):
    # Simulate "a clean checkout with none of the historical worktrees around": copy ONLY the
    # tracked evidence file into an unrelated tmp_path root that has never heard of any of the
    # `stock-core-*-20260913`/`20260914` worktrees, then resolve from there.
    artifact = json.loads(REAL_EVIDENCE_PATH.read_text(encoding="utf-8"))
    dest = _write_pinned_evidence(tmp_path, artifact)
    assert "worktrees" not in str(dest)
    scope = ccpp.resolve_current_research_official_universe_scope(tmp_path, "2026-09-20")
    assert scope is not None
    assert scope["source_reference_ticker_count"] == 1683
    assert scope["current_research_scope_ticker_count"] == 1504


# ---------------------------------------------------------------------------------------------
# 2. Missing canonical evidence fails closed
# ---------------------------------------------------------------------------------------------

def test_2_missing_evidence_fails_closed(tmp_path):
    scope = ccpp.resolve_current_research_official_universe_scope(tmp_path, "2026-09-20")
    assert scope is None


# ---------------------------------------------------------------------------------------------
# 3. Wrong hash (tampered content, stale self-identity) fails closed
# ---------------------------------------------------------------------------------------------

def test_3_wrong_hash_fails_closed(tmp_path):
    artifact = _synthetic_official_artifact()
    artifact["records"]["AAA"]["current_universe_status"] = "TAMPERED_AFTER_HASHING"
    _write_pinned_evidence(tmp_path, artifact)
    scope = ccpp.resolve_current_research_official_universe_scope(tmp_path, "2026-09-20")
    assert scope is None
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        com.verify_retained_artifact(artifact, label="T")


# ---------------------------------------------------------------------------------------------
# 4. Wrong artifact identity (self-consistent, but not the pinned one) fails closed
# ---------------------------------------------------------------------------------------------

def test_4_wrong_identity_fails_closed(tmp_path):
    artifact = _synthetic_official_artifact()
    _write_pinned_evidence(tmp_path, artifact)
    scope = ccpp.resolve_current_research_official_universe_scope(tmp_path, "2026-09-20")
    # Self-consistent (real _identity stamp) but this is not
    # CURRENT_OFFICIAL_UNIVERSE_EVIDENCE_EXPECTED_IDENTITY -- must still fail closed.
    assert scope is None
    with pytest.raises(ValueError, match="UNEXPECTED_IDENTITY"):
        com.verify_retained_artifact(artifact, label="T", expected_identity="current_official_market_universe:deadbeef")


# ---------------------------------------------------------------------------------------------
# 5. Wrong contract_version fails closed
# ---------------------------------------------------------------------------------------------

def test_5_wrong_contract_fails_closed(tmp_path):
    artifact = _synthetic_official_artifact()
    artifact.pop("artifact_sha256"); artifact.pop("artifact_identity")
    artifact["contract_version"] = "current_official_market_universe/v2"
    artifact.update(com._identity(artifact))
    _write_pinned_evidence(tmp_path, artifact)
    scope = ccpp.resolve_current_research_official_universe_scope(tmp_path, "2026-09-20")
    assert scope is None
    with pytest.raises(ValueError, match="CONTRACT_MISMATCH"):
        com.verify_retained_artifact(artifact, label="T")


# ---------------------------------------------------------------------------------------------
# 6. Conflicting retained destination refuses to overwrite
# ---------------------------------------------------------------------------------------------

def test_6_conflicting_destination_refuses(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_synthetic_official_artifact()), encoding="utf-8")

    other = _synthetic_official_artifact(observed_at="2026-09-14T08:00:00Z")
    dest = tmp_path / "destination.json"
    dest.write_text(json.dumps(other), encoding="utf-8")

    with pytest.raises(RetentionError, match="DESTINATION_CONFLICT"):
        retain_evidence(source_path=source, destination_path=dest)


# ---------------------------------------------------------------------------------------------
# 7. Identical seed/migration is idempotent
# ---------------------------------------------------------------------------------------------

def test_7_identical_retention_is_idempotent(tmp_path):
    artifact = _synthetic_official_artifact()
    source = tmp_path / "source.json"
    source.write_text(json.dumps(artifact), encoding="utf-8")
    dest = tmp_path / "nested" / "destination.json"

    first = retain_evidence(source_path=source, destination_path=dest)
    assert first["status"] == "RETAINED"
    assert dest.is_file()

    second = retain_evidence(source_path=source, destination_path=dest)
    assert second["status"] == "ALREADY_RETAINED_IDENTICAL"
    assert second["artifact_identity"] == first["artifact_identity"]


def test_7b_retention_rejects_missing_source(tmp_path):
    with pytest.raises(RetentionError, match="SOURCE_NOT_FOUND"):
        retain_evidence(source_path=tmp_path / "nope.json", destination_path=tmp_path / "dest.json")


def test_7c_retention_rejects_expected_identity_mismatch(tmp_path):
    artifact = _synthetic_official_artifact()
    source = tmp_path / "source.json"
    source.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(ValueError, match="UNEXPECTED_IDENTITY"):
        retain_evidence(
            source_path=source, destination_path=tmp_path / "dest.json",
            expected_identity="current_official_market_universe:deadbeef",
        )


# ---------------------------------------------------------------------------------------------
# 8. 2026-09-11 temporal negative control
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
def test_8_temporal_negative_control_20260911():
    scope = ccpp.resolve_current_research_official_universe_scope(ROOT, "2026-09-11")
    assert scope is not None
    assert scope["disposition"] == "TEMPORALLY_INELIGIBLE_FOR_SESSION"
    assert scope["temporally_eligible"] is False
    assert scope["current_research_scope_ticker_count"] is None


# ---------------------------------------------------------------------------------------------
# 9. 2026-09-14 scope is exactly 1504 / 1683 / 179
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
def test_9_20260914_scope_1504_of_1683():
    scope = ccpp.resolve_current_research_official_universe_scope(ROOT, "2026-09-14")
    assert scope is not None
    assert scope["disposition"] == "CURRENT_OBSERVED_EVIDENCE_AVAILABLE"
    assert scope["source_reference_ticker_count"] == 1683
    assert scope["current_research_scope_ticker_count"] == 1504
    outside = sum(1 for row in scope["records"].values() if row["current_research_scope_state"] != "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE")
    assert outside == 179


# ---------------------------------------------------------------------------------------------
# 10. Full 1683-row preservation (never a narrower denominator)
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
def test_10_full_1683_row_preservation():
    scope = ccpp.resolve_current_research_official_universe_scope(ROOT, "2026-09-14")
    assert scope is not None
    assert len(scope["records"]) == 1683 == scope["source_reference_ticker_count"]


# ---------------------------------------------------------------------------------------------
# 11. Real 2026-09-14 replay through the canonical materialization + local publisher rehearsal
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
@_REQUIRES_20260914_REPLAY_INPUTS
def test_11_real_20260914_replay_materializes_and_binds_price_tactical_crosstabs(tmp_path):
    tactical = json.loads(REAL_TACTICAL_20260914.read_text(encoding="utf-8"))
    valuation = json.loads(REAL_VALUATION_20260914.read_text(encoding="utf-8"))
    runtime_root = Path("C:/Projects/StockLookup/dashboard-runtime")
    if not (runtime_root / "screen_snapshot.csv").is_file():
        pytest.skip("dashboard-runtime screen_snapshot.csv not present on this machine.")

    operation_dir = tmp_path / "recovery_operation"
    result = ccpp.materialize_and_write_current_product_projections(
        root=ROOT,
        session="2026-09-14",
        operation_dir=operation_dir,
        registry_inputs={"tactical": tactical, "valuation": valuation},
        requested_at="2026-09-15T00:00:00+07:00",
        runtime_root_override=runtime_root,
    )
    assert result["status"] == "MATERIALIZED"
    scope_status = result["current_research_official_universe_scope"]
    assert scope_status["source_reference_ticker_count"] == 1683
    assert scope_status["current_research_scope_ticker_count"] == 1504

    screener = json.loads((operation_dir / "screener_master_projection.json").read_text(encoding="utf-8"))
    coverage = screener["coverage"]
    assert coverage["price_available_count"] == 853
    assert coverage["price_unavailable_explicit_count"] == 830
    assert coverage["tactical_available_count"] == 852

    cross = screener["official_scope_coverage"]
    assert cross["price_x_official_scope"] == {
        "in_scope_price_available": 853, "in_scope_price_unavailable": 651,
        "outside_scope_price_available": 0, "outside_scope_price_unavailable": 179,
    }
    assert cross["tactical_x_official_scope"] == {
        "in_scope_tactical_available": 852, "in_scope_tactical_unavailable": 652,
        "outside_scope_tactical_available": 0, "outside_scope_tactical_unavailable": 179,
    }

    workspace = json.loads((operation_dir / "investment_decision_workspace_projection.json").read_text(encoding="utf-8"))
    assert screener["source_artifacts"]["investment_decision_workspace"] == workspace["artifact_identity"]

    import dashboard_release_publisher as drp

    web_root = Path("C:/Projects/StockLookup/market-dashboard")
    if not web_root.is_dir():
        pytest.skip("market-dashboard checkout not present on this machine.")
    publish_result = drp.publish_dashboard_release(
        session="2026-09-14", operation_dir=operation_dir,
        runtime_root=runtime_root, web_root=web_root,
        replay_local=True, local_only=True,
    )
    assert publish_result["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
