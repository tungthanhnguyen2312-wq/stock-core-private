from run_sector_relative_research_context import run


def test_relative_context_is_deterministic_and_preserves_cohort_and_review_lineage():
    first, first_overlay = run(); second, second_overlay = run()
    assert first["artifact_identity"] == second["artifact_identity"]
    assert first_overlay["artifact_identity"] == second_overlay["artifact_identity"]
    assert len(first["records"]) == 523
    assert first["coverage"]["full_cohort_records"] == 523
    assert first_overlay["review_entries_with_relative_context"] <= 25
    assert len(first_overlay["review_entries"]) == 25
    assert first["cohort_scope"] == "EMPIRICAL_ACTIVE_SHADOW_ONLY"
    for record in first["records"]:
        for metric in record["relative_metrics"]:
            if metric["status"] == "AVAILABLE":
                assert metric["research_session"] == "2026-08-20"
                assert metric["source_lineage"]["subject_field"].startswith(f"daily_research.{record['ticker']}.")
                assert metric["cohort_member_count"] >= 5
            else:
                assert metric["missing_or_exclusion_reason"]
    assert first["authority_boundary"]["ranking"] == "NOT_EMITTED"
