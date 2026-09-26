"""Scratch copies of retained Level-2 evidence for tests that execute Level-2 builders.

A builder such as ``canonical_post_close_pipeline.build_enrichment_components`` writes its
session outputs next to its inputs (``artifact_root``). Pointing it at the retained-evidence root
rebuilt the retained 2026-08-25/2026-09-04 Integrated Decision folders in place
(RETAINED_EVIDENCE_INCIDENT_20260925). Tests instead copy exactly the inputs the builder reads
into ``tmp_path`` as real files -- never a junction or symlink -- and pass that scratch tree as
``artifact_root``/``output_root``; the retained root is only ever read.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import daily_session_level2_package as level2

import _canonical_evidence_write_guard as write_guard
from _test_tiers import retained_evidence_root

# Session-specific Level-2 inputs build_enrichment_components reads from ``artifact_root``.
# Everything it writes there (IID folder, financial-analysis-product-v2, corporate-intelligence
# axis) is deliberately absent, so the build produces those outputs fresh in scratch.
ENRICHMENT_ARTIFACT_INPUT_KEYS = (
    "universe_resolution",
    "exact_session_snapshot",
    "technical_recovery",
    "strategy",
    "valuation",
    "descriptive_research",
    "sector_leadership",
    "screening_foundation",
    "opportunity_prioritization",
    "tactical_classifier",
    "technical_coverage_disposition",
    "session_triage",
)


def _is_link(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", None)
    return path.is_symlink() or bool(is_junction and is_junction(path))


def copy_session_inputs(
    session: str, scratch_root: Path, *, keys: tuple[str, ...] = ENRICHMENT_ARTIFACT_INPUT_KEYS,
    source_root: Path | None = None,
) -> dict[str, Path]:
    """Copy the named retained session inputs that exist into ``scratch_root`` (real files).

    Returns ``{key: scratch_path}`` for every copied input. Refuses a protected or linked
    destination and a linked source."""
    source_root = source_root if source_root is not None else retained_evidence_root()
    if write_guard.is_protected(scratch_root):
        raise AssertionError(f"SCRATCH_ROOT_IS_PROTECTED_EVIDENCE:{scratch_root}")
    source_paths = level2.session_artifact_paths(source_root, session)
    scratch_paths = level2.session_artifact_paths(scratch_root, session)
    pairs = [(source_paths[key], scratch_paths[key], key) for key in keys]
    if "technical_recovery" in keys:
        pairs.append((
            level2._technical_recovery_revalidated_path(source_paths["technical_recovery"]),
            level2._technical_recovery_revalidated_path(scratch_paths["technical_recovery"]),
            "technical_recovery_revalidated",
        ))
    copied: dict[str, Path] = {}
    for source, target, key in pairs:
        if not source.is_file():
            continue
        if _is_link(source) or _is_link(source.parent):
            raise AssertionError(f"RETAINED_SOURCE_IS_A_LINK:{source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if _is_link(target) or _is_link(target.parent):
            raise AssertionError(f"SCRATCH_TARGET_IS_A_LINK:{target}")
        copied[key] = target
    return copied


def enrichment_roots(session: str, tmp_path: Path) -> dict[str, Path]:
    """Keyword roots for build_enrichment_components: read retained inputs, write only scratch."""
    artifact_root = tmp_path / "artifact-root"
    copy_session_inputs(session, artifact_root)
    return {
        "artifact_root": artifact_root,
        "retained_evidence_root": retained_evidence_root(),
        "output_root": tmp_path / "output-root",
    }
