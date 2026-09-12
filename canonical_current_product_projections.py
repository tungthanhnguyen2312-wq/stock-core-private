"""canonical_current_product_projections/v1: session-parametric materialization of the two
recurring current-session product surfaces that sit between current-research decision inputs
and Dashboard release -- Investment Decision Workspace and Screener Master Projection.

Why this exists: ``investment_decision_workspace_projection.py`` and
``screener_master_projection.py`` were each materialized exactly once, by a hand-run,
milestone-dated tool (``tools/run_investment_decision_workspace_projection.py``,
``tools/run_screener_master_projection.py``) hardcoding a specific historical session and a
list of specific dated ``operations-review/...`` search paths. Neither tool is called by
``canonical_daily_operation.py``/``daily_producer_pipeline.py``, so both products have been
frozen at their original ``as_of_session`` (2026-08-28) ever since, while the Dashboard release
session moved on -- see ``docs/dashboard_current_session_surface_coherence_20260912.md`` in the
Dashboard repository.

This module is the clean, session-parametric materialization boundary the historical tools were
never designed to be. It performs ZERO search: every input is either passed in already-loaded
(the same ``daily_research_session_input_registry.json``-resolved values
``daily_producer_pipeline.run_daily_producer`` already has in scope for the current session) or
resolved via one explicit, deterministic path formula per axis
(``resolve_supplementary_inputs``) -- never a glob, a latest-mtime search, or a historical
dated fallback. A supplementary axis with no file at its one deterministic path resolves to
``None`` (a legitimately unavailable optional axis, exactly the same "missing enrichment
degrades an individual field, never the whole product" semantics
``current_valuation_opportunity_integration.py``/``investment_decision_workspace_projection.py``
already implement) -- never silently substituted for a different session's file.

``feature_store`` (fundamental feature store), ``tactical_behavior`` (BOS/CHoCH technical
structure detail), ``thesis_cases`` (catalyst/downside-invalidation cases), and
``portfolio`` (explicit portfolio-risk research) have no recurring, canonical-runtime source at
all today -- each was materialized exactly once, in a now-detached feature worktree, for the
original 2026-08-28/2026-08-31 milestone, and never regenerated since. Resurrecting those
worktree-local, one-off snapshots into a "canonical" recurring path would be the same defect
this module exists to remove, just relocated. They are passed as ``None`` here; every one is
already an optional, gracefully-degrading keyword argument in the builders this module calls,
so the Workspace/Screener product is not blocked, only that individual axis's field.

Never raises out of the top-level entry point (``materialize_and_write_current_product_projections``):
a failure here must never block core Daily / the decision cockpit / AI handoff, exactly like
``canonical_daily_operation.py``'s own macro-refresh step. It returns an explicit
status dict instead.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from atomic_io import atomic_write_file, atomic_write_json
import current_valuation_opportunity_integration
import investment_decision_workspace_projection
import screener_master_projection
from runtime_paths import runtime_root

CONTRACT_VERSION = "canonical_current_product_projections/v1"
MILESTONE = "CANONICAL_CURRENT_PRODUCT_PROJECTIONS_AND_DASHBOARD_BINDING_V1"

#: Session-neutral reference data (VCI industry labels rarely change; not a market-session
#: fact). Reuses the exact same retained snapshot ``sector_relative_research_context.py``
#: already treats as the current authoritative industry-label source -- not a one-off pick.
VCI_INDUSTRY_SNAPSHOT_RELATIVE = "registry_snapshots/metadata/vnstock_metadata_snapshot_20260728T122548Z_16fe54ee3497.jsonl"

WORKSPACE_ARTIFACT_FILENAME = "investment_decision_workspace_projection.json"
SCREENER_MASTER_JSON_FILENAME = "screener_master_projection.json"
SCREENER_MASTER_JS_FILENAME = "screener_master_projection.js"

#: Explicit, deterministic path template per supplementary axis (session -> one path, never a
#: search). Each entry: (directory-slug, filename). ``{session}`` is replaced with the session
#: string with dashes removed (matching this repository's own established
#: ``operations-review/<capability>-v1-<YYYYMMDD>/`` per-session artifact directory
#: convention -- see e.g. ``config/daily_research_session_input_registry.json``'s own dated
#: entries for 2026-09-11).
SUPPLEMENTARY_INPUT_TEMPLATES: dict[str, tuple[str, str]] = {
    "liquidity": ("market-wide-current-liquidity-research-v1-{session}", "market_wide_current_liquidity_research_artifact.json"),
    "leadership": ("current-market-sector-leadership-context-v1-{session}", "current_market_sector_leadership_context_artifact.json"),
    "financial_analysis_product_v2": ("financial-analysis-product-v2-{session}", "financial_analysis_product_artifact.json"),
}


class CanonicalCurrentProductProjectionsError(ValueError):
    """A required input or invariant of this materialization boundary is violated."""


def _session_compact(session: str) -> str:
    return session.replace("-", "")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_supplementary_inputs(root: Path, session: str) -> dict[str, dict[str, Any] | None]:
    """Explicit, deterministic per-session resolution for axes not already covered by
    ``daily_research_session_input_registry.json``. No glob, no latest-mtime search, no
    historical dated fallback. A missing file at its one deterministic path is a legitimately
    unavailable axis (``None``), never an error and never a different session's file."""
    root = Path(root)
    resolved: dict[str, dict[str, Any] | None] = {}
    session_compact = _session_compact(session)
    for name, (dir_template, filename) in SUPPLEMENTARY_INPUT_TEMPLATES.items():
        path = root / "operations-review" / dir_template.format(session=session_compact) / filename
        resolved[name] = _load_json(path) if path.is_file() else None
    return resolved


def _financial_analysis_product_context(supplementary: Mapping[str, Any]) -> dict[str, Any] | None:
    """Unwrap the nested ``financial_analysis_product_integration/v1`` payload from the
    canonical daily Financial V2 materialization wrapper, if present and exact-session."""
    wrapper = supplementary.get("financial_analysis_product_v2")
    if not isinstance(wrapper, Mapping):
        return None
    nested = wrapper.get("financial_analysis_product")
    if isinstance(nested, Mapping) and nested.get("contract_version") == "financial_analysis_product_integration/v1":
        return dict(nested)
    return None


def materialize_current_investment_decision_workspace(
    *,
    session: str,
    registry_inputs: Mapping[str, Any],
    supplementary: Mapping[str, Any],
    requested_at: str,
) -> dict[str, Any]:
    """Build the current-session Investment Decision Workspace from already-resolved inputs.

    ``registry_inputs`` is the same dict ``daily_research_session_operations.resolve_inputs()``
    already produced for the current session (reused here, not re-read): its ``tactical`` entry
    is the exact-session ``watchlist_tactical_entry_classifier`` artifact and its ``valuation``
    entry is the exact-session ``market_wide_current_valuation`` artifact -- both required,
    both already validated against the session registry. Its optional ``event_context`` entry
    (``current_official_event_context/v1``) is preferred over the older, more stale
    ``current_corporate_event_context/v1`` file the original one-off tool used, since it is
    already the authoritative, already-loaded corporate-event input the current cockpit
    pipeline itself accepts for this same conceptual axis.

    Raises ``CanonicalCurrentProductProjectionsError`` if the two required registry inputs are
    absent -- there is no fallback path for these; a Daily run without them has no valid
    Workspace denominator to build from.
    """
    watchlist = registry_inputs.get("tactical")
    valuation = registry_inputs.get("valuation")
    if not isinstance(watchlist, Mapping) or not isinstance(valuation, Mapping):
        raise CanonicalCurrentProductProjectionsError("WORKSPACE_REQUIRED_REGISTRY_INPUT_MISSING")

    opportunity_and_decision = current_valuation_opportunity_integration.build_artifacts(
        as_of_session=session,
        feature_store=None,
        tactical_behavior=None,
        watchlist=watchlist,
        valuation=valuation,
        liquidity=supplementary.get("liquidity"),
        events=registry_inputs.get("event_context"),
        thesis_cases=None,
        leadership=supplementary.get("leadership"),
        portfolio=None,
        financial_analysis_product_context=_financial_analysis_product_context(supplementary),
        financial_analysis_context=None,
        requested_at=requested_at,
    )
    workspace = investment_decision_workspace_projection.build_artifacts(
        opportunity_artifact=opportunity_and_decision["opportunity_context"],
        decision_artifact=opportunity_and_decision["security_decision_context"],
        leadership=supplementary.get("leadership"),
        portfolio_research=None,
        prospective_lifecycle=None,
        requested_at=requested_at,
    )
    return {
        "opportunity_context": opportunity_and_decision["opportunity_context"],
        "security_decision_context": opportunity_and_decision["security_decision_context"],
        "workspace": workspace,
    }


def materialize_current_screener_master_projection(
    *,
    session: str,
    root: Path,
    snapshot_path: Path,
    workspace: Mapping[str, Any],
    registry_inputs: Mapping[str, Any],
    supplementary: Mapping[str, Any],
    requested_at: str,
) -> dict[str, Any]:
    """Build the current-session Screener Master Projection from the canonical exact-session
    screen snapshot plus the current Workspace just materialized. ``as_of_session`` is always
    passed explicitly (never derived from the snapshot's own rows), so a snapshot-derivation
    disagreement fails closed inside ``screener_master_projection.build_projection`` rather
    than silently adopting whichever session the snapshot happens to claim."""
    snapshot_rows = screener_master_projection.load_screen_snapshot_rows(snapshot_path)
    industry_path = root / VCI_INDUSTRY_SNAPSHOT_RELATIVE
    industry_by_ticker = (
        screener_master_projection.load_vci_industry_labels(industry_path) if industry_path.is_file() else {}
    )
    return screener_master_projection.build_projection(
        snapshot_rows=snapshot_rows,
        requested_at=requested_at,
        as_of_session=session,
        snapshot_identity=f"canonical_screen_snapshot:{snapshot_path.name}",
        workspace=workspace,
        financial_v2=_financial_analysis_product_context(supplementary),
        industry_by_ticker=industry_by_ticker,
        official_universe=registry_inputs.get("official_universe"),
    )


def materialize_and_write_current_product_projections(
    *,
    root: Path,
    session: str,
    operation_dir: Path,
    registry_inputs: Mapping[str, Any],
    requested_at: str,
    runtime_root_override: Path | None = None,
) -> dict[str, Any]:
    """Top-level entry point: materialize both current products and write them into
    ``operation_dir`` (the same Daily Research Session Operation directory
    ``dashboard_release_publisher.py`` already reads ``current_decision_cockpit_projection.json``
    from), alongside a small manifest recording what happened.

    Never raises. A missing required input, an inconsistent lineage, or any other failure is
    reported as ``status: SKIPPED`` with a reason code -- core Daily, the decision cockpit, and
    AI handoff must never be blocked by this optional current-product step, exactly like
    ``canonical_daily_operation.py``'s own macro-refresh step.
    """
    root = Path(root)
    operation_dir = Path(operation_dir)
    try:
        supplementary = resolve_supplementary_inputs(root, session)
        workspace_bundle = materialize_current_investment_decision_workspace(
            session=session, registry_inputs=registry_inputs, supplementary=supplementary,
            requested_at=requested_at,
        )
        workspace = workspace_bundle["workspace"]
        snapshot_root = Path(runtime_root_override) if runtime_root_override is not None else runtime_root(root)
        snapshot_path = snapshot_root / "screen_snapshot.csv"
        screener_master = materialize_current_screener_master_projection(
            session=session, root=root, snapshot_path=snapshot_path, workspace=workspace,
            registry_inputs=registry_inputs, supplementary=supplementary, requested_at=requested_at,
        )
    except Exception as exc:  # noqa: BLE001 - this step must never block core Daily
        return {
            "status": "SKIPPED",
            "reason_code": type(exc).__name__,
            "detail": str(exc),
            "contract_version": CONTRACT_VERSION,
        }

    operation_dir.mkdir(parents=True, exist_ok=True)
    workspace_path = operation_dir / WORKSPACE_ARTIFACT_FILENAME
    screener_json_path = operation_dir / SCREENER_MASTER_JSON_FILENAME
    screener_js_path = operation_dir / SCREENER_MASTER_JS_FILENAME
    atomic_write_json(workspace_path, workspace)
    atomic_write_json(screener_json_path, screener_master)
    atomic_write_file(screener_js_path, screener_master_projection.js_fallback(screener_master), encoding="utf-8", newline="\n")

    return {
        "status": "MATERIALIZED",
        "contract_version": CONTRACT_VERSION,
        "session": session,
        "workspace": {
            "path": str(workspace_path),
            "as_of_session": workspace.get("as_of_session"),
            "artifact_identity": workspace.get("artifact_identity"),
            "ticker_denominator": (workspace.get("coverage") or {}).get("ticker_denominator"),
        },
        "screener_master_projection": {
            "json_path": str(screener_json_path),
            "js_path": str(screener_js_path),
            "as_of_session": screener_master.get("as_of_session"),
            "artifact_identity": screener_master.get("artifact_identity"),
            "denominator": screener_master.get("denominator"),
        },
        "supplementary_inputs_available": {name: value is not None for name, value in supplementary.items()},
        "unavailable_optional_axes": ["feature_store", "tactical_behavior", "thesis_cases", "portfolio"],
    }
