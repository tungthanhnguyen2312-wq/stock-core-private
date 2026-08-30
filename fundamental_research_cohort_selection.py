"""Versioned, fail-closed selection of the current fundamental research cohort.

The wide cohort is the prospective current-research default.  The frozen cohort
remains available solely through an explicit legacy selector for reproduction and
historical replay; selection never discovers a "latest" artifact and never falls
back from wide to legacy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CURRENT_WIDE_GOVERNED_V1 = "CURRENT_WIDE_GOVERNED_V1"
LEGACY_HISTORICAL_FROZEN_523_V1 = "LEGACY_HISTORICAL_FROZEN_523_V1"
DEFAULT_COHORT_SELECTOR = CURRENT_WIDE_GOVERNED_V1

WIDE_COHORT_RELATIVE_PATH = (
    "operations-review/market-wide-fundamental-research-cohort-scaleout-v1-20260830/"
    "fundamental_cross_sectional_scoring_wide_artifact.json"
)
WIDE_RECONCILIATION_RELATIVE_PATH = (
    "operations-review/market-wide-fundamental-research-cohort-scaleout-v1-20260830/"
    "root_cause_reconciliation_report.json"
)
LEGACY_COHORT_RELATIVE_PATH = (
    "operations-review/fundamental-cross-sectional-scoring-and-ranking-v1-20260828/artifact.json"
)


class FundamentalResearchCohortSelectionError(ValueError):
    """The selected retained cohort is absent, corrupt, or not self-consistent."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _read_json(root: Path, relative_path: str, code: str) -> dict[str, Any]:
    path = root / relative_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FundamentalResearchCohortSelectionError(code + "_MISSING") from exc
    except json.JSONDecodeError as exc:
        raise FundamentalResearchCohortSelectionError(code + "_CORRUPT") from exc
    if not isinstance(value, dict):
        raise FundamentalResearchCohortSelectionError(code + "_INVALID")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact_sha256(artifact: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in artifact.items() if key not in {"artifact_sha256", "artifact_identity", "source_artifact_sha256"}}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _validate_scoring_artifact(artifact: Mapping[str, Any], *, code: str) -> None:
    records = artifact.get("records")
    if artifact.get("contract_version") != "fundamental_cross_sectional_scoring_and_ranking/v1":
        raise FundamentalResearchCohortSelectionError(code + "_CONTRACT_INVALID")
    if not isinstance(records, Mapping) or artifact.get("denominator") != len(records) or artifact.get("residual") != 0:
        raise FundamentalResearchCohortSelectionError(code + "_COVERAGE_INVALID")
    artifact_sha = artifact.get("artifact_sha256")
    if not isinstance(artifact_sha, str) or artifact_sha != _artifact_sha256(artifact):
        raise FundamentalResearchCohortSelectionError(code + "_IDENTITY_INVALID")


def resolve_current_fundamental_cohort(
    root: Path,
    *,
    selector: str | None = None,
    cohort_relative_path: str | None = None,
    reconciliation_relative_path: str | None = None,
) -> dict[str, Any]:
    """Return one explicitly selected retained scoring artifact with selector lineage.

    Optional paths exist only as a bounded test/replay seam.  An unknown selector,
    malformed retained artifact, or a wide-artifact/reconciliation disagreement is
    an integrity failure.  Missing ordinary retained evidence is deliberately
    local to this research dimension and is never replaced with legacy data.
    """
    selected = DEFAULT_COHORT_SELECTOR if selector is None else selector
    source_root = Path(root)
    if selected == CURRENT_WIDE_GOVERNED_V1:
        cohort_path = cohort_relative_path or WIDE_COHORT_RELATIVE_PATH
        reconciliation_path = reconciliation_relative_path or WIDE_RECONCILIATION_RELATIVE_PATH
        try:
            artifact = _read_json(source_root, cohort_path, "CURRENT_WIDE_GOVERNED_COHORT")
            reconciliation = _read_json(source_root, reconciliation_path, "CURRENT_WIDE_GOVERNED_RECONCILIATION")
        except FundamentalResearchCohortSelectionError as exc:
            if "_MISSING" not in str(exc) or cohort_relative_path or reconciliation_relative_path:
                raise
            try:
                from fundamental_research_cohort_scaleout import rebuild_wide_governed_cohort_from_retained_root
                artifact, reconciliation = rebuild_wide_governed_cohort_from_retained_root(source_root)
                _write_json(source_root / cohort_path, artifact)
                _write_json(source_root / reconciliation_path, reconciliation)
            except (FileNotFoundError, ValueError, json.JSONDecodeError) as rebuild_exc:
                raise FundamentalResearchCohortSelectionError("CURRENT_WIDE_GOVERNED_COHORT_MISSING") from rebuild_exc
        _validate_scoring_artifact(artifact, code="CURRENT_WIDE_GOVERNED_COHORT")
        root_cause = reconciliation.get("root_cause_reconciliation")
        if not isinstance(root_cause, Mapping):
            raise FundamentalResearchCohortSelectionError("CURRENT_WIDE_GOVERNED_RECONCILIATION_INVALID")
        if (
            reconciliation.get("wide_cohort_identity") != artifact["artifact_sha256"]
            or root_cause.get("wide_cohort_size") != artifact["denominator"]
            or root_cause.get("residual_zero") is not True
        ):
            raise FundamentalResearchCohortSelectionError("CURRENT_WIDE_GOVERNED_LINEAGE_CONFLICT")
        evidence_identity = reconciliation.get("report_sha256")
        if not isinstance(evidence_identity, str):
            raise FundamentalResearchCohortSelectionError("CURRENT_WIDE_GOVERNED_RECONCILIATION_IDENTITY_INVALID")
        status = "CURRENT_RESEARCH_DEFAULT"
    elif selected == LEGACY_HISTORICAL_FROZEN_523_V1:
        cohort_path = cohort_relative_path or LEGACY_COHORT_RELATIVE_PATH
        artifact = _read_json(source_root, cohort_path, "LEGACY_HISTORICAL_COHORT")
        _validate_scoring_artifact(artifact, code="LEGACY_HISTORICAL_COHORT")
        evidence_identity = artifact["artifact_sha256"]
        status = "LEGACY_HISTORICAL_REPLAY_ONLY"
    else:
        raise FundamentalResearchCohortSelectionError("FUNDAMENTAL_COHORT_SELECTOR_UNKNOWN")

    return {
        "selector": selected,
        "selection_status": status,
        "cohort_relative_path": cohort_path,
        "cohort_artifact_identity": artifact["artifact_sha256"],
        "cohort_denominator": artifact["denominator"],
        "evidence_identity": evidence_identity,
        "artifact": artifact,
    }
