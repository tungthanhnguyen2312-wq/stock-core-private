"""Operational materialization of prospective research cohort diagnostics."""
from __future__ import annotations

import json
from pathlib import Path

from prospective_research_cohort_diagnostics import (
    build_cohort_diagnostics,
    render_cohort_diagnostics_summary,
)
from prospective_research_learning import write_immutable

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / 'operations-review/prospective-research-cohort-diagnostics-v1-20260821'


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def run() -> tuple[dict, str]:
    ledger = _load('operations-review/prospective-daily-rollforward-v1-20260821/prospective_learning_ledger.json')
    first_attribution = _load('operations-review/first-real-prospective-attribution-v1-20260821/first_real_prospective_attribution_artifact.json')
    snap_20 = _load('operations-review/prospective-research-learning-v1-20260820/caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a.json')
    snap_21 = _load('operations-review/prospective-daily-rollforward-v1-20260821/2026-08-21.snapshot.json')
    ext_20 = _load('operations-review/prospective-research-context-extension-v1-successor-20260820/6cc76efaaf55b4262b6d94d53abda75dc1a0289d17c7d195014e11a07e987807.json')

    diagnostics = build_cohort_diagnostics(
        ledger=ledger,
        attributions=[first_attribution],
        snapshots=[snap_20, snap_21],
        extensions=[ext_20],
    )
    summary_md = render_cohort_diagnostics_summary(diagnostics)
    return diagnostics, summary_md


if __name__ == '__main__':
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact, summary = run()
    
    artifact_path = OUT_DIR / 'prospective_research_cohort_diagnostics_artifact.json'
    summary_path = OUT_DIR / 'prospective_research_cohort_diagnostics_summary.md'
    
    write_immutable(artifact_path, artifact)
    
    # Summary markdown is written deterministically
    summary_path.write_text(summary, encoding='utf-8')
    
    print(f"Cohort Diagnostics Artifact Identity: {artifact['artifact_identity']}")
    print(f"Total Cohort Summaries: {artifact['cohort_summary_count']}")
    print(f"Saved to: {artifact_path}")
