"""Local-only, read-only market-wide replay for ASYMMETRIC_DISLOCATION_RESEARCH_V1.

Reads the retained `integrated_investment_decision_product/v1` artifact for the
latest governed completed research session and joins it into the new
`asymmetric_dislocation_research/v1` product. Makes no provider/network call, writes
no database, does not touch canonical Daily Producer orchestration, Daily Brief
generation, AI delivery, the Integrated Investment Decision production path, or
Portfolio V2 decision semantics, and does not publish to Dashboard/AI. Standalone
research artifact only.

Retained evidence (the completed-session registry and the per-session
`operations-review/canonical-post-close-v1/<session>/enrichment/` artifacts) is read
from `--runtime-root` (or `STOCK_LOOKUP_RUNTIME_ROOT`), which may point at a different
checkout than this tool's own repository root -- a fresh dedicated worktree does not
itself retain runtime evidence. Output is always written under this repository's own
`operations-review/` so it can be committed on this milestone's branch.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asymmetric_dislocation_research as adr  # noqa: E402
import runtime_paths  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise adr.AsymmetricDislocationResearchError(f"RETAINED_ARTIFACT_NOT_FOUND: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_latest_completed_session(runtime_root: Path) -> str:
    """Reuse the standing governed completed-session ledger and resolver
    (`daily_producer_pipeline.resolve_latest_registered_completed_session`) -- never
    civil time, never a directory listing sort."""
    import daily_producer_pipeline as producer

    registry_path = runtime_root / "config" / "daily_research_session_input_registry.json"
    registry = _load(registry_path)
    return producer.resolve_latest_registered_completed_session(registry)


def _enrichment_path(runtime_root: Path, session: str) -> Path:
    return runtime_root / "operations-review" / "canonical-post-close-v1" / session / "enrichment" / "integrated_investment_decision_product.json"


def _entity_families(runtime_root: Path, tickers: list[str]) -> dict[str, str]:
    """Best-effort, read-only join to the existing entity classification contract for
    descriptive `sector_model_applicability` context only. A resolution failure for any
    ticker never blocks classification -- it degrades to 'unknown' for that ticker."""
    try:
        import entity_classification_contract as entity
    except Exception:
        return {}
    families: dict[str, str] = {}
    for ticker in tickers:
        try:
            result = entity.resolve_layered_entity_classification(ticker)
            families[ticker] = result.resolved_entity_class.value
        except Exception:
            continue
    return families


def run(*, runtime_root: Path, output_dir: Path, session: str | None = None) -> dict[str, Any]:
    session = session or resolve_latest_completed_session(runtime_root)
    integrated_product = _load(_enrichment_path(runtime_root, session))
    entity_families = _entity_families(runtime_root, sorted((integrated_product.get("records") or {}).keys()))

    artifact = adr.build_artifact(
        session=session, integrated_product=integrated_product, entity_families=entity_families,
    )

    token = session.replace("-", "")
    _write(output_dir / f"asymmetric_dislocation_research_{token}.json", artifact)
    summary = {
        "session": artifact["session"],
        "artifact_identity": artifact["artifact_identity"],
        "source_integrated_decision_identity": artifact["source_integrated_decision_identity"],
        "coverage": artifact["coverage"],
        "top_candidate_count": len(artifact["top_candidates"]),
        "top_candidates_sample": artifact["top_candidates"][:20],
    }
    _write(output_dir / f"market_wide_summary_{token}.json", summary)
    return {"artifact": artifact, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=None, help="Where retained evidence is read from (defaults to STOCK_LOOKUP_RUNTIME_ROOT or this repository root).")
    parser.add_argument("--session", default=None, help="Explicit session (default: latest governed completed session).")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "operations-review" / "asymmetric-dislocation-research-v1-20260909", help="Always written under this repository, regardless of --runtime-root.")
    args = parser.parse_args()

    resolved_runtime_root = runtime_paths.runtime_root(default=args.runtime_root or ROOT)
    result = run(runtime_root=resolved_runtime_root, output_dir=args.output_dir, session=args.session)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
