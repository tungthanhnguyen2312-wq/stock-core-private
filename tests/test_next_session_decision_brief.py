from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_handoff_publication import _unsafe
from daily_research_session_operations import load_registry
from next_session_decision_brief import (
    AVAILABLE,
    NOT_APPLICABLE,
    PARTIAL,
    UNAVAILABLE,
    NextSessionDecisionBriefError,
    build_artifact,
    build_from_previous_bundle_path,
    content_identity,
)
from stocklookup import _latest_operation, _previous

CURRENT_SESSION = "2026-08-28"
PREVIOUS_SESSION = "2026-08-27"

# The governed, gitignored operations-review/ evidence this suite replays against is
# local to the primary checkout -- git worktrees only carry tracked files, so a fresh
# worktree (this one included) never has it. `next_session_decision_brief.build_artifact`
# itself is fully parameterized by `root`/`source`/`previous` and has no opinion about
# where evidence lives; this constant exists only so the *test* can point at real data
# while exercising the *worktree's* corrected code. Skip cleanly wherever that data isn't
# available (a different machine, a true CI checkout) rather than failing opaquely.
ROOT = Path("C:/Projects/StockLookup/stock-core-private")
_LATEST_POINTER = ROOT / "operations-review/daily-producer-runs-v1/LATEST_COMPLETED_RUN.json"
pytestmark = pytest.mark.skipif(not _LATEST_POINTER.is_file(), reason="real 2026-08-27/2026-08-28 operations-review evidence not present at " + str(ROOT))


def _current_and_previous_dirs() -> tuple[Path, Path]:
    session, operation_dir, _run_identity = _latest_operation(ROOT)
    assert session == CURRENT_SESSION, "fixture assumption: LATEST_COMPLETED_RUN.json still points at 2026-08-28"
    previous_bundle = _previous(session, ROOT)
    assert previous_bundle is not None
    return operation_dir, previous_bundle.parent


def _forbidden_scan(value, path=""):
    """Recursively assert no probability/target/sizing keys appear anywhere in the artifact."""
    forbidden_keys = {"probability", "target_price", "position_size", "recommended_allocation", "order_size"}
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden_keys, f"forbidden key {key!r} at {path}"
            _forbidden_scan(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _forbidden_scan(item, f"{path}[{index}]")


class TestReal27To28Replay:
    """The money test: replays the real, already-governed 2026-08-27 -> 2026-08-28 pair."""

    @staticmethod
    @pytest.fixture(scope="class")
    def brief():
        current_dir, previous_dir = _current_and_previous_dirs()
        return build_artifact(
            root=ROOT,
            current_session=CURRENT_SESSION,
            current_source=current_dir,
            previous_session=PREVIOUS_SESSION,
            previous_source=previous_dir,
            run_identity="daily_producer_run:test-replay",
        )

    def test_top_level_binding(self, brief):
        assert brief["current_session"] == CURRENT_SESSION
        assert brief["previous_qualified_session"] == PREVIOUS_SESSION
        assert brief["binding"]["run_identity"] == "daily_producer_run:test-replay"
        assert brief["binding"]["current_session_bundle"]["sha256"]
        assert brief["binding"]["previous_session_bundle"]["sha256"]

    def test_market_transition_available_with_real_breadth_delta(self, brief):
        market = brief["market_transition"]
        assert market["availability"] == AVAILABLE
        assert market["previous"]["advance_ratio"] == pytest.approx(0.34009546539379476)
        assert market["current"]["advance_ratio"] == pytest.approx(0.321656050955414)
        assert market["transition"]["advance_ratio_direction"] == "WEAKENING"
        assert market["current"]["same_session_technical_feature_available_count"] == 942
        assert market["previous"]["same_session_technical_feature_available_count"] == 838

    def test_market_transition_advance_ratio_delta_units_are_explicit_and_correct(self, brief):
        """E/F: raw delta (0-1 share) vs its *100 percentage-point restatement must both be
        present, separately labeled, and numerically consistent -- never an unlabeled bare
        delta a reader has to guess the unit of."""
        transition = brief["market_transition"]["transition"]
        raw = transition["advance_ratio_delta_raw"]
        pct_points = transition["advance_ratio_delta_percentage_points"]
        assert raw == pytest.approx(0.321656050955414 - 0.34009546539379476)
        assert raw == pytest.approx(-0.018439414438380758)
        assert pct_points == pytest.approx(raw * 100)
        assert pct_points == pytest.approx(-1.8439414438380758)

    def test_market_transition_technical_coverage_is_an_unambiguous_previous_current_delta_triplet(self, brief):
        """G/H: technical coverage must be exposed as three explicitly named fields, and the
        delta must be the real 838->942 count difference (+104), never an overloaded or
        differently-sourced number masquerading under the same name."""
        transition = brief["market_transition"]["transition"]
        assert transition["technical_covered_count_previous"] == 838
        assert transition["technical_covered_count_current"] == 942
        assert transition["technical_covered_count_delta"] == 104
        assert transition["technical_covered_count_delta"] == transition["technical_covered_count_current"] - transition["technical_covered_count_previous"]
        assert transition["observed_session_cohort_previous"] == 839
        assert transition["observed_session_cohort_current"] == 943
        assert transition["observed_session_cohort_delta"] == 104

    def test_sector_transition_covers_24_sectors_with_a_real_insufficient_evidence_case(self, brief):
        sector = brief["sector_transition"]
        assert sector["availability"] == AVAILABLE
        assert len(sector["sectors"]) == 24
        assert sector["previous_counts"]["sector_count_total"] == 24
        assert sector["current_counts"]["sector_count_total"] == 24
        assert sector["previous_counts"]["sector_count_available"] == 21
        assert sector["current_counts"]["sector_count_available"] == 20
        telecom = next(row for key, row in sector["sectors"].items() if key.endswith("|viễn thông"))
        assert telecom["previous"]["status"] == "AVAILABLE"
        assert telecom["current"]["status"] == "UNAVAILABLE_INSUFFICIENT_COVERAGE"
        assert telecom["transition"] == "INSUFFICIENT_EVIDENCE"

    def test_opportunity_transition_matches_real_set_differences(self, brief):
        opportunity = brief["opportunity_transition"]
        assert opportunity["availability"] == AVAILABLE
        assert len(opportunity["new_entry_relevant"]) == 65
        assert len(opportunity["lost_entry_relevant"]) == 48
        assert len(opportunity["persisting_entry_relevant"]) == 48
        assert len(opportunity["new_high_priority"]) == 33
        assert len(opportunity["lost_high_priority"]) == 20
        assert len(opportunity["persisting_high_priority"]) == 131
        assert opportunity["new_entry_relevant"] == sorted(opportunity["new_entry_relevant"])

    def test_opportunity_transition_consumes_the_full_governed_queue_not_a_session_bundle_subset(self, brief):
        """A/B/C/D: the corrective concern was that opportunity_transition might silently
        collapse onto the narrower Session Bundle `ticker_research_contexts` cohort (106/123
        tickers) instead of the full governed `daily_opportunity_decision_queue_artifact.json`
        (1,507 tickers). Prove the record counts and totals match the full queue, and that they
        are NOT the much-smaller Session Bundle card counts."""
        current_dir, previous_dir = _current_and_previous_dirs()
        current_queue = json.loads((current_dir / "daily_opportunity_decision_queue_artifact.json").read_text(encoding="utf-8"))
        previous_queue = json.loads((previous_dir / "daily_opportunity_decision_queue_artifact.json").read_text(encoding="utf-8"))
        lineage = brief["opportunity_transition"]["source_lineage"]
        assert lineage["current_record_count"] == len(current_queue["records"]) == 1507
        assert lineage["previous_record_count"] == len(previous_queue["records"]) == 1507
        assert lineage["current_entry_relevant_count"] == 113
        assert lineage["previous_entry_relevant_count"] == 96
        assert lineage["current_high_priority_count"] == 164
        assert lineage["previous_high_priority_count"] == 151
        # The Session Bundle cohort (106/123 cards) is a much smaller, different number --
        # confirm the Brief's counts are NOT that narrower cohort.
        current_bundle = json.loads((current_dir / "ai_research_session_bundle.json").read_text(encoding="utf-8"))
        previous_bundle = json.loads((previous_dir / "ai_research_session_bundle.json").read_text(encoding="utf-8"))
        assert len(current_bundle["ticker_research_contexts"]) == 123
        assert len(previous_bundle["ticker_research_contexts"]) == 106
        assert lineage["current_record_count"] != len(current_bundle["ticker_research_contexts"])
        assert lineage["previous_record_count"] != len(previous_bundle["ticker_research_contexts"])
        # Reconciliation arithmetic: new + persisting == current total; lost + persisting == previous total.
        opportunity = brief["opportunity_transition"]
        assert len(opportunity["new_entry_relevant"]) + len(opportunity["persisting_entry_relevant"]) == lineage["current_entry_relevant_count"]
        assert len(opportunity["lost_entry_relevant"]) + len(opportunity["persisting_entry_relevant"]) == lineage["previous_entry_relevant_count"]
        assert len(opportunity["new_high_priority"]) + len(opportunity["persisting_high_priority"]) == lineage["current_high_priority_count"]
        assert len(opportunity["lost_high_priority"]) + len(opportunity["persisting_high_priority"]) == lineage["previous_high_priority_count"]

    def test_source_identities_present_on_both_sides_for_every_comparative_section(self, brief):
        """I: every comparative section names its exact source artifact identity on both sides
        -- never a generic 'current data' label."""
        assert set(brief["market_transition"]["source_lineage"]) >= {"previous_descriptive_artifact_identity", "current_descriptive_artifact_identity"}
        assert set(brief["sector_transition"]["source_lineage"]) >= {"previous_descriptive_artifact_identity", "current_descriptive_artifact_identity"}
        assert set(brief["opportunity_transition"]["source_lineage"]) >= {"previous_opportunity_decision_queue_identity", "current_opportunity_decision_queue_identity"}
        assert set(brief["tactical_transition"]["source_lineage"]) >= {"previous_tactical_artifact_identity", "current_tactical_artifact_identity"}
        assert brief["lifecycle"]["source_lineage"]["source_artifacts"]["previous"] is not None
        assert brief["lifecycle"]["source_lineage"]["source_artifacts"]["current"] is not None
        for section_name in ("market_transition", "sector_transition", "opportunity_transition", "tactical_transition"):
            for identity in brief[section_name]["source_lineage"].values():
                if isinstance(identity, str):
                    assert identity, f"{section_name} has a blank source identity"

    def test_lifecycle_reuses_existing_artifact_with_58_comparable_records(self, brief):
        lifecycle = brief["lifecycle"]
        assert lifecycle["availability"] == AVAILABLE
        assert lifecycle["comparable_count"] == 58
        # records covers the full current-session ticker_research_contexts (123 tickers);
        # comparable_count (58) is the subset that also existed in the previous session's
        # bundle -- the other 65 are legitimately INITIAL_OBSERVATION, not an error.
        assert lifecycle["denominator"] == 123
        assert len(lifecycle["records"]) == 123
        initial_observation = [t for t, r in lifecycle["records"].items() if r["thesis_lifecycle_state"] == "INITIAL_OBSERVATION"]
        assert len(initial_observation) == 123 - 58
        for record in lifecycle["records"].values():
            assert record["thesis_lifecycle_state"] in {"UNCHANGED", "STATE_TRANSITION", "INITIAL_OBSERVATION", "CONFIRMED", "INVALIDATED", "INSUFFICIENT_EVIDENCE"}

    def test_recommendation_and_invalidation_transition_are_partial_missing_previous_context(self, brief):
        recommendation = brief["recommendation_transition"]
        invalidation = brief["invalidation_transition"]
        assert recommendation["availability"] == PARTIAL
        assert invalidation["availability"] == PARTIAL
        assert recommendation["comparable_count"] == 58
        assert invalidation["comparable_count"] == 58
        for record in recommendation["records"].values():
            assert "MISSING_PREVIOUS_CONTEXT" in record["reason_codes"]
            assert record["previous"] is None
        for record in invalidation["records"].values():
            assert "MISSING_PREVIOUS_CONTEXT" in record["reason_codes"]

    def test_tactical_transition_matches_real_breakout_ready_deltas(self, brief):
        tactical = brief["tactical_transition"]
        assert tactical["availability"] == AVAILABLE
        assert tactical["confirmation_states"] == ["BREAKOUT_READY"]
        assert len(tactical["gained_confirmation"]) == 12
        assert len(tactical["lost_confirmation"]) == 20
        assert len(tactical["retained_confirmation"]) == 5

    def test_c2_is_not_applicable(self, brief):
        c2 = brief["correlation_concentration_context"]
        assert c2["availability"] == NOT_APPLICABLE
        assert "NO_QUALIFIED_PAIR_BOUND_C2_ARTIFACT" in c2["reason_codes"]

    def test_watch_conditions_are_normalized_from_existing_trigger_invalidation_text(self, brief):
        watch = brief["next_session_watch_conditions"]
        assert watch["availability"] == AVAILABLE
        assert watch["conditions"]
        for condition in watch["conditions"]:
            assert condition["condition_type"] in {"TRIGGER", "INVALIDATION"}
            assert condition["if_satisfied"] in {"REEVALUATE_CLASSIFICATION", "FLAG_INVALIDATION"}

    def test_no_forecast_probability_target_or_sizing_anywhere(self, brief):
        assert brief["authority_boundary"]["no_probability"] is True
        assert brief["authority_boundary"]["no_target_price"] is True
        assert brief["authority_boundary"]["no_sizing"] is True
        _forbidden_scan(brief)

    def test_no_local_absolute_paths_or_secrets(self, brief):
        assert _unsafe(brief) is False
        blob = json.dumps(brief).lower()
        for needle in ("api_key", "password", "secret_key", "authorization: bearer"):
            assert needle not in blob

    def test_deterministic_content_identity(self):
        current_dir, previous_dir = _current_and_previous_dirs()
        first = build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir, previous_session=PREVIOUS_SESSION, previous_source=previous_dir)
        second = build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir, previous_session=PREVIOUS_SESSION, previous_source=previous_dir)
        assert first["artifact_sha256"] == second["artifact_sha256"]
        assert content_identity(first) == content_identity(second)

    def test_deterministic_ordering_independent_of_dict_iteration(self, brief):
        assert brief["opportunity_transition"]["new_entry_relevant"] == sorted(brief["opportunity_transition"]["new_entry_relevant"])
        assert list(brief["sector_transition"]["sectors"]) == sorted(brief["sector_transition"]["sectors"])
        assert list(brief["lifecycle"]["records"]) == sorted(brief["lifecycle"]["records"])

    def test_build_from_previous_bundle_path_matches_direct_build(self):
        current_dir, previous_dir = _current_and_previous_dirs()
        previous_bundle_path = previous_dir / "ai_research_session_bundle.json"
        via_path = build_from_previous_bundle_path(root=ROOT, session=CURRENT_SESSION, source=current_dir, previous=previous_bundle_path)
        direct = build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir, previous_session=PREVIOUS_SESSION, previous_source=previous_dir)
        assert via_path["artifact_sha256"] == direct["artifact_sha256"]

    def test_handoff_inclusion(self, brief, tmp_path):
        from ai_handoff_publication import build_package

        current_dir, _previous_dir = _current_and_previous_dirs()
        brief_path = tmp_path / "next_session_decision_brief.json"
        brief_path.write_text(json.dumps(brief, sort_keys=True), encoding="utf-8")
        files, payload = build_package(current_dir, CURRENT_SESSION, producer_checkpoint="test", decision_brief=brief_path)
        assert "next_session_decision_brief.json" in files
        assert "next_session_decision_brief.json" in payload["files"]
        assert payload["lineage"]["next_session_decision_brief_identity"] == brief["artifact_identity"]


class TestNoPreviousQualifiedSession:
    def test_initial_observation_everywhere_when_no_previous_exists(self):
        current_dir, _previous_dir = _current_and_previous_dirs()
        brief = build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir)
        assert brief["previous_qualified_session"] is None
        assert brief["market_transition"]["transition"] == "INITIAL_OBSERVATION"
        assert brief["market_transition"]["availability"] == UNAVAILABLE
        assert brief["opportunity_transition"]["availability"] == UNAVAILABLE
        assert brief["lifecycle"]["availability"] == UNAVAILABLE
        assert brief["recommendation_transition"]["availability"] == UNAVAILABLE
        assert brief["invalidation_transition"]["availability"] == UNAVAILABLE
        assert brief["tactical_transition"]["availability"] == UNAVAILABLE
        # Missingness must never collapse into a false 0/UNCHANGED/NEUTRAL reading.
        assert brief["market_transition"]["current"] is not None


class TestFailClosed:
    def test_run_manifest_session_mismatch_raises(self, tmp_path):
        current_dir, _previous_dir = _current_and_previous_dirs()
        tampered = tmp_path / "tampered"
        _copy_operation_dir(current_dir, tampered)
        manifest = json.loads((tampered / "run_manifest.json").read_text(encoding="utf-8"))
        manifest["market_session"] = "2099-01-01"
        (tampered / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(NextSessionDecisionBriefError, match="RUN_MANIFEST_SESSION_MISMATCH"):
            build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=tampered)

    def test_bundle_operation_identity_mismatch_raises(self, tmp_path):
        current_dir, _previous_dir = _current_and_previous_dirs()
        tampered = tmp_path / "tampered"
        _copy_operation_dir(current_dir, tampered)
        bundle = json.loads((tampered / "ai_research_session_bundle.json").read_text(encoding="utf-8"))
        bundle["operation_identity"] = "daily_research_session_operation:not-the-real-one"
        (tampered / "ai_research_session_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        with pytest.raises(NextSessionDecisionBriefError, match="SESSION_BUNDLE_OPERATION_IDENTITY_MISMATCH"):
            build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=tampered)

    def test_previous_not_strictly_before_current_raises_no_calendar_subtraction(self):
        current_dir, previous_dir = _current_and_previous_dirs()
        with pytest.raises(NextSessionDecisionBriefError, match="PREVIOUS_SESSION_NOT_STRICTLY_BEFORE_CURRENT_SESSION"):
            build_artifact(root=ROOT, current_session=PREVIOUS_SESSION, current_source=previous_dir, previous_session=CURRENT_SESSION, previous_source=current_dir)

    def test_session_not_governed_qualified_raises(self, tmp_path):
        current_dir, _previous_dir = _current_and_previous_dirs()
        registry = dict(load_registry(ROOT))
        registry = json.loads(json.dumps(registry))  # deep copy
        registry["completed_sessions"][CURRENT_SESSION]["status"] = "INTRADAY"
        with pytest.raises(NextSessionDecisionBriefError, match="SESSION_NOT_GOVERNED_QUALIFIED"):
            build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir, registry=registry)

    def test_previous_session_and_source_must_both_be_given_or_both_absent(self):
        current_dir, previous_dir = _current_and_previous_dirs()
        with pytest.raises(NextSessionDecisionBriefError, match="PREVIOUS_SESSION_AND_SOURCE_MUST_BOTH_BE_GIVEN_OR_BOTH_ABSENT"):
            build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir, previous_session=PREVIOUS_SESSION, previous_source=None)


class TestRegistryUntouched:
    """J: the governed input registry is existing operational state (see
    known_operational_diff_allowlist in docs/ROADMAP_STATE.json) -- this module must only ever
    read it, never write it, regardless of how many times a brief is built."""

    def test_building_briefs_never_writes_the_registry(self):
        registry_path = ROOT / "config" / "daily_research_session_input_registry.json"
        before = registry_path.read_bytes()
        current_dir, previous_dir = _current_and_previous_dirs()
        build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir, previous_session=PREVIOUS_SESSION, previous_source=previous_dir)
        build_artifact(root=ROOT, current_session=CURRENT_SESSION, current_source=current_dir)
        after = registry_path.read_bytes()
        assert after == before


def _copy_operation_dir(source: Path, destination: Path) -> None:
    import shutil

    destination.mkdir(parents=True, exist_ok=True)
    for name in ("run_manifest.json", "ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json"):
        candidate = source / name
        if candidate.is_file():
            shutil.copyfile(candidate, destination / name)


class TestDailyIntegrationHelper:
    """Exercises stocklookup.py's own wiring, against a scratch copy -- never the real,
    already-published evidence directory under operations-review/."""

    def test_decision_brief_writes_into_a_copy_and_is_immutable_on_rerun(self, tmp_path):
        from stocklookup import _decision_brief

        current_dir, previous_dir = _current_and_previous_dirs()
        scratch = tmp_path / "operation_copy"
        _copy_operation_dir(current_dir, scratch)
        path = _decision_brief(CURRENT_SESSION, scratch, previous_dir / "ai_research_session_bundle.json", "daily_producer_run:test", root=ROOT)
        assert path == scratch / "next_session_decision_brief.json"
        assert path.is_file()
        first_bytes = path.read_bytes()
        again = _decision_brief(CURRENT_SESSION, scratch, previous_dir / "ai_research_session_bundle.json", "daily_producer_run:test", root=ROOT)
        assert again == path
        assert path.read_bytes() == first_bytes

    def test_decision_brief_never_raises_it_degrades_to_none(self, tmp_path):
        from stocklookup import _decision_brief

        empty = tmp_path / "empty_operation"
        empty.mkdir()
        assert _decision_brief(CURRENT_SESSION, empty, None, None, root=ROOT) is None

    def test_latest_operation_returns_run_identity(self):
        session, operation_dir, run_identity = _latest_operation(ROOT)
        assert session == CURRENT_SESSION
        assert operation_dir.is_dir()
        assert run_identity.startswith("daily_producer_run:")
