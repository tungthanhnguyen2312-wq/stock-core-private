from __future__ import annotations

import json

import pytest

import fundamental_research_cohort_selection as selection
import fundamental_cross_sectional_scoring as scoring


def _artifact(records: dict[str, dict]) -> dict:
    value = {
        "contract_version": "fundamental_cross_sectional_scoring_and_ranking/v1",
        "denominator": len(records), "residual": 0, "records": records,
    }
    value["artifact_sha256"] = selection._artifact_sha256(value)
    return value


def _write(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _retained_cohorts(root):
    legacy = _artifact({"OLD": {}})
    wide = _artifact({"OLD": {}, "NEW": {}})
    reconciliation = {
        "report_sha256": "reconciliation:wide",
        "wide_cohort_identity": wide["artifact_sha256"],
        "root_cause_reconciliation": {"wide_cohort_size": len(wide["records"]), "residual_zero": True},
    }
    _write(root, selection.LEGACY_COHORT_RELATIVE_PATH, legacy)
    _write(root, selection.WIDE_COHORT_RELATIVE_PATH, wide)
    _write(root, selection.WIDE_RECONCILIATION_RELATIVE_PATH, reconciliation)
    return legacy, wide


def test_default_selects_the_retained_governed_wide_cohort(tmp_path):
    _, wide = _retained_cohorts(tmp_path)
    resolved = selection.resolve_current_fundamental_cohort(tmp_path)
    assert resolved["selector"] == selection.CURRENT_WIDE_GOVERNED_V1
    assert resolved["selection_status"] == "CURRENT_RESEARCH_DEFAULT"
    assert resolved["cohort_artifact_identity"] == wide["artifact_sha256"]
    assert resolved["cohort_denominator"] == 2


def test_legacy_is_explicit_and_reproducible_only(tmp_path):
    legacy, _ = _retained_cohorts(tmp_path)
    resolved = selection.resolve_current_fundamental_cohort(
        tmp_path, selector=selection.LEGACY_HISTORICAL_FROZEN_523_V1,
    )
    assert resolved["selection_status"] == "LEGACY_HISTORICAL_REPLAY_ONLY"
    assert resolved["artifact"] == legacy


def test_unknown_or_conflicting_wide_selection_fails_closed(tmp_path):
    _retained_cohorts(tmp_path)
    with pytest.raises(selection.FundamentalResearchCohortSelectionError, match="SELECTOR_UNKNOWN"):
        selection.resolve_current_fundamental_cohort(tmp_path, selector="UNQUALIFIED")
    reconciliation_path = tmp_path / selection.WIDE_RECONCILIATION_RELATIVE_PATH
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation["wide_cohort_identity"] = "conflict"
    reconciliation_path.write_text(json.dumps(reconciliation), encoding="utf-8")
    with pytest.raises(selection.FundamentalResearchCohortSelectionError, match="LINEAGE_CONFLICT"):
        selection.resolve_current_fundamental_cohort(tmp_path)


def test_missing_current_wide_never_falls_back_to_legacy(tmp_path):
    legacy, _ = _retained_cohorts(tmp_path)
    (tmp_path / selection.WIDE_COHORT_RELATIVE_PATH).unlink()
    with pytest.raises(selection.FundamentalResearchCohortSelectionError, match="CURRENT_WIDE_GOVERNED_COHORT_MISSING"):
        selection.resolve_current_fundamental_cohort(tmp_path)
    assert selection.resolve_current_fundamental_cohort(
        tmp_path, selector=selection.LEGACY_HISTORICAL_FROZEN_523_V1,
    )["artifact"] == legacy


def test_scoring_execute_uses_the_same_default_selection_boundary(monkeypatch, tmp_path):
    expected = _artifact({"WIDE": {}})
    calls = []

    def resolve(root, *, selector=None):
        calls.append((root, selector))
        return {"artifact": expected}

    monkeypatch.setattr(scoring, "resolve_current_fundamental_cohort", resolve)
    assert scoring.execute(root=tmp_path) == expected
    assert calls == [(tmp_path, None)]
