from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import canonical_post_close_pipeline as cpc
from daily_research_session_operations import load_registry
import session_registry_gap_reconciliation as recon

ROOT = Path(__file__).resolve().parents[1]


def _registry_copy_at(tmp_path: Path, *, completed: dict | None = None, sessions: dict | None = None) -> Path:
    registry = {
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": completed or {},
        "sessions": sessions or {},
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_coherent_session_artifacts(tmp_path: Path, session: str) -> dict[str, Path]:
    """A minimal, fully coherent set of retained artifacts satisfying
    ``daily_research_session_operations.validate_coherence`` exactly, so
    ``validate_and_freeze_completed_session`` can genuinely succeed against them.
    """
    descriptive_id = f"market_wide_current_descriptive_research:{session}"
    screening_id = f"current_market_screening_opportunity_comparison_foundation:{session}"
    tactical_id = f"watchlist_tactical_entry_classifier:{session}"

    paths = {
        "descriptive_research": tmp_path / "descriptive.json",
        "screening_foundation": tmp_path / "screening.json",
        "tactical_classifier": tmp_path / "tactical.json",
        "session_triage": tmp_path / "triage.json",
        "fundamental": tmp_path / "fundamental.json",
        "valuation": tmp_path / "valuation.json",
        "catalyst": tmp_path / "catalyst.json",
        "corporate_intelligence": tmp_path / "corporate_intelligence.json",
        "official_universe": tmp_path / "official_universe.json",
        "official_event_context": tmp_path / "event_context.json",
    }
    _write(paths["descriptive_research"], {
        "artifact_identity": descriptive_id, "session": session,
        "records": {"HPG": {}},
        "market_breadth": {
            "same_session_technical_feature_available_count": 1,
            "current_active_equity_denominator": 1,
            "observed_session_cohort": 1,
        },
        "input_lineage": {"technical_history_recovery_artifact_identity": "technical_recovery:fake"},
    })
    _write(paths["screening_foundation"], {
        "artifact_identity": screening_id, "session": session,
        "input_lineage": {"current_descriptive_artifact_identity": descriptive_id},
    })
    _write(paths["tactical_classifier"], {
        "artifact_identity": tactical_id, "session": session,
        "source_artifacts": {"descriptive": descriptive_id, "screening": screening_id},
        "coverage": {"classified_count": 1},
    })
    _write(paths["session_triage"], {
        "artifact_identity": f"full_universe_entry_candidate_triage:{session}", "source_market_session": session,
    })
    _write(paths["fundamental"], {"artifact_identity": "market_wide_current_fundamental_research:fixed"})
    _write(paths["valuation"], {
        "artifact_identity": f"market_wide_current_valuation:{session}", "valuation_session": session,
    })
    _write(paths["catalyst"], {"artifact_identity": "catalyst_event_research_context:fixed"})
    _write(paths["corporate_intelligence"], {
        "artifact_identity": f"market_wide_current_corporate_intelligence:{session}",
        "contract_version": "market_wide_current_corporate_intelligence/v1", "session": session,
        "source_artifact_identities": {"descriptive": descriptive_id},
        "records": {"HPG": {}},
    })
    _write(paths["official_universe"], {"artifact_identity": "current_official_market_universe:fixed"})
    _write(paths["official_event_context"], {"artifact_identity": "current_official_event_context:fixed"})
    return paths


@pytest.fixture
def coherent_fixture(tmp_path, monkeypatch):
    session = "2026-08-28"
    paths = _write_coherent_session_artifacts(tmp_path, session)
    monkeypatch.setattr(cpc.level2, "session_artifact_paths", lambda root, s: paths)
    registry_path = _registry_copy_at(tmp_path)
    return session, registry_path


# 1. GOVERNED_COMPLETED short-circuit: already-governed sessions are never re-derived.

def test_already_governed_session_short_circuits_without_touching_evidence(tmp_path):
    session = "2026-08-25"
    registry_path = _registry_copy_at(tmp_path, completed={
        session: {"status": "COMPLETED_RETAINED_EVIDENCE", "frozen_input_identities": {}},
    })
    before = registry_path.read_text(encoding="utf-8")
    result = recon.reconcile_session(ROOT, session, registry_path=registry_path)
    assert result["classification"] == recon.GOVERNED_COMPLETED
    assert registry_path.read_text(encoding="utf-8") == before  # never mutated


# 7. an unqualified historical session (not a trading day) is NOT_APPLICABLE, never blocked.

def test_weekend_session_classified_not_applicable(tmp_path):
    registry_path = _registry_copy_at(tmp_path)
    result = recon.reconcile_session(ROOT, "2026-08-23", registry_path=registry_path)  # a Sunday
    assert result["classification"] == recon.NOT_APPLICABLE
    assert "WEEKEND" in result["reason_codes"][0]


# 5. missing frozen input identity blocks registration (INSUFFICIENT_RETAINED_EVIDENCE).

def test_missing_required_artifact_is_insufficient_retained_evidence(tmp_path, monkeypatch):
    session = "2026-08-27"

    def missing_paths(root, s):
        return {key: tmp_path / f"{key}_does_not_exist.json" for key in cpc.REGISTRY_KEY_TO_LEVEL2_KEY.values()}

    monkeypatch.setattr(cpc.level2, "session_artifact_paths", missing_paths)
    registry_path = _registry_copy_at(tmp_path)
    result = recon.reconcile_session(ROOT, session, registry_path=registry_path)
    assert result["classification"] == recon.INSUFFICIENT_RETAINED_EVIDENCE
    assert "REQUIRED_REGISTRY_INPUT_UNAVAILABLE" in result["reason_codes"][0]
    # a rejected session must never be written into "sessions" or "completed_sessions"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert session not in registry.get("sessions", {})
    assert session not in registry.get("completed_sessions", {})


# 8. an eligible historical session can be retroactively registered deterministically
# (QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION), using real production coherence logic.

def test_coherent_retained_evidence_qualifies_for_retroactive_registration(coherent_fixture):
    session, registry_path = coherent_fixture
    result = recon.reconcile_session(ROOT, session, registry_path=registry_path)
    assert result["classification"] == recon.QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["completed_sessions"][session]["status"] == "COMPLETED_RETAINED_EVIDENCE"
    # a second, independent build reproduces byte-identical frozen identities.
    second = json.loads(registry_path.read_text(encoding="utf-8"))["completed_sessions"][session]["frozen_input_identities"]
    assert second == result["detail"]["frozen_input_identities"]


# 6. an incompatible/incoherent source input blocks registration
# (PUBLISHED_BUT_NOT_PROVABLY_GOVERNED), never silently accepted.

def test_incoherent_retained_evidence_is_published_but_not_provably_governed(tmp_path, monkeypatch):
    session = "2026-08-28"
    paths = _write_coherent_session_artifacts(tmp_path, session)
    # Break coherence: tactical claims a different upstream descriptive identity than the real one.
    tactical = json.loads(paths["tactical_classifier"].read_text(encoding="utf-8"))
    tactical["source_artifacts"]["descriptive"] = "market_wide_current_descriptive_research:SOMETHING_ELSE"
    paths["tactical_classifier"].write_text(json.dumps(tactical), encoding="utf-8")
    monkeypatch.setattr(cpc.level2, "session_artifact_paths", lambda root, s: paths)
    registry_path = _registry_copy_at(tmp_path)
    result = recon.reconcile_session(ROOT, session, registry_path=registry_path)
    assert result["classification"] == recon.PUBLISHED_BUT_NOT_PROVABLY_GOVERNED
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert session not in registry.get("completed_sessions", {})


# apply=False (dry run) never mutates the real registry file, whatever the outcome.

def test_dry_run_never_mutates_the_real_registry(coherent_fixture):
    session, registry_path = coherent_fixture
    before = registry_path.read_text(encoding="utf-8")
    result = recon.reconcile_session(ROOT, session, registry_path=registry_path, apply=False)
    assert result["classification"] == recon.QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION
    assert registry_path.read_text(encoding="utf-8") == before


# 2. an already-registered-identical session is idempotent: reconciling twice never
# duplicates or destabilizes the registry entry.

def test_reconciling_twice_is_idempotent(coherent_fixture):
    session, registry_path = coherent_fixture
    first = recon.reconcile_session(ROOT, session, registry_path=registry_path)
    assert first["classification"] == recon.QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION
    after_first = registry_path.read_text(encoding="utf-8")
    second = recon.reconcile_session(ROOT, session, registry_path=registry_path)
    assert second["classification"] == recon.GOVERNED_COMPLETED
    assert registry_path.read_text(encoding="utf-8") == after_first


# 3. mutation is rejected: retroactive registration must never rewrite an already
# governed session with different content -- this is the exact conservative rule
# that the underlying register_session_inputs/validate_and_freeze_completed_session
# guard clauses already enforce; reconcile_session must surface, not swallow, that
# fail-closed refusal rather than silently reporting success.

def test_conflicting_content_against_an_already_governed_session_is_never_silently_accepted(tmp_path, monkeypatch):
    session = "2026-08-25"  # already governed in the real registry copy below
    real_registry = load_registry(ROOT)
    registry_path = _registry_copy_at(
        tmp_path,
        completed=copy.deepcopy(real_registry.get("completed_sessions", {})),
        sessions=copy.deepcopy(real_registry.get("sessions", {})),
    )
    fake_paths = {}
    for reg_key, l2_key in cpc.REGISTRY_KEY_TO_LEVEL2_KEY.items():
        p = tmp_path / f"{l2_key}.json"
        p.write_text(json.dumps({"artifact_identity": f"fake:{reg_key}"}), encoding="utf-8")
        fake_paths[l2_key] = p
    monkeypatch.setattr(cpc.level2, "session_artifact_paths", lambda root, s: fake_paths)
    result = recon.reconcile_session(ROOT, session, registry_path=registry_path)
    # the session is already GOVERNED_COMPLETED in this registry copy, so reconcile_session
    # must short-circuit before ever attempting (and conflicting with) a re-registration.
    assert result["classification"] == recon.GOVERNED_COMPLETED


# reconcile_sessions processes each session independently, in ascending order, and a
# failure for one session never affects another's outcome.

def test_reconcile_sessions_is_independent_per_session(tmp_path, monkeypatch):
    good_session, bad_session = "2026-08-28", "2026-08-27"
    paths = _write_coherent_session_artifacts(tmp_path, good_session)

    def route(root, s):
        if s == good_session:
            return paths
        return {key: tmp_path / f"missing_{key}.json" for key in cpc.REGISTRY_KEY_TO_LEVEL2_KEY.values()}

    monkeypatch.setattr(cpc.level2, "session_artifact_paths", route)
    registry_path = _registry_copy_at(tmp_path)
    results = recon.reconcile_sessions(ROOT, [bad_session, good_session], registry_path=registry_path)
    by_session = {r["session"]: r["classification"] for r in results}
    assert by_session[bad_session] == recon.INSUFFICIENT_RETAINED_EVIDENCE
    assert by_session[good_session] == recon.QUALIFIES_FOR_RETROACTIVE_GOVERNED_REGISTRATION
