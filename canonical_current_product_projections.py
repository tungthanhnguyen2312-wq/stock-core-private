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

``feature_store`` (``market_wide_fundamental_feature_store/v1``) and ``tactical_behavior``
(``tactical_behavior_context/v1``) are, as of
CANONICAL_RECURRING_DECISION_CONTEXT_MATERIALIZATION_V1, materialized fresh here every run --
never read from either module's own dated default or the detached 2026-08-31 feature worktrees
that produced the original one-off snapshots (see ``materialize_current_fundamental_feature_
store_context`` / ``materialize_current_tactical_behavior_context`` below). Financial evidence is
periodic, not daily: the fundamental feature context is rebuilt from
``financial_v2_current_input_authority``'s pinned, versioned structured-period-semantics chain
(the same evidence Financial V2 itself already consumes every session) and is NOT session-bound
-- its identity changes only when that authority itself advances. Tactical behavior IS exact
same-session -- it is rebuilt from the registry's own ``watchlist_tactical_entry_classifier``
plus ``technical_structure_context``/``tactical_setup_tags``, both now retained per-session by
``canonical_post_close_pipeline.py`` (the first genuinely current-session, non-historical source
either axis has ever had). Either axis missing its mandatory current-session input is an explicit
unavailable status, never a historical fallback.

``thesis_cases`` (catalyst/downside-invalidation cases) and ``portfolio`` (explicit
portfolio-risk research) still have no recurring, canonical-runtime source and remain passed as
``None`` here; both are already optional, gracefully-degrading keyword arguments in the builders
this module calls, so the Workspace/Screener product is not blocked, only that individual axis's
field.

Never raises out of the top-level entry point (``materialize_and_write_current_product_projections``):
a failure here must never block core Daily / the decision cockpit / AI handoff, exactly like
``canonical_daily_operation.py``'s own macro-refresh step. It returns an explicit
status dict instead.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from atomic_io import atomic_write_file, atomic_write_json
import canonical_daily_financial_v2_materialization
import current_valuation_opportunity_integration
import financial_v2_current_input_authority
import investment_decision_workspace_projection
import market_wide_fundamental_feature_store
import screener_master_projection
import tactical_behavior_context
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
FEATURE_STORE_ARTIFACT_FILENAME = "market_wide_fundamental_feature_store_artifact.json"
FEATURE_STORE_RECORDS_FILENAME = "market_wide_fundamental_feature_store_records.jsonl.gz"
TACTICAL_BEHAVIOR_ARTIFACT_FILENAME = "tactical_behavior_context_artifact.json"

#: Explicit, deterministic path template per supplementary axis (session -> one path, never a
#: search). Each entry: (directory-slug, filename). ``{session}`` is replaced with the session
#: string with dashes removed (matching this repository's own established
#: ``operations-review/<capability>-v1-<YYYYMMDD>/`` per-session artifact directory
#: convention -- see e.g. ``config/daily_research_session_input_registry.json``'s own dated
#: entries for 2026-09-11). ``technical_structure``/``tactical_setup_tags``/``tactical_boundaries``
#: reuse ``daily_session_level2_package.session_artifact_paths()``'s own
#: ``integrated-investment-decision-product-v1-{session}`` directory -- the same one
#: ``canonical_post_close_pipeline.py`` already retains ``tactical_confirmation_invalidation_
#: boundaries_artifact.json`` under, and now also retains ``technical_structure_context``/
#: ``tactical_setup_tags`` under, for exactly this axis.
SUPPLEMENTARY_INPUT_TEMPLATES: dict[str, tuple[str, str]] = {
    "liquidity": ("market-wide-current-liquidity-research-v1-{session}", "market_wide_current_liquidity_research_artifact.json"),
    "leadership": ("current-market-sector-leadership-context-v1-{session}", "current_market_sector_leadership_context_artifact.json"),
    "financial_analysis_product_v2": ("financial-analysis-product-v2-{session}", "financial_analysis_product_artifact.json"),
    "technical_structure": ("integrated-investment-decision-product-v1-{session}", "technical_structure_context_artifact.json"),
    "tactical_setup_tags": ("integrated-investment-decision-product-v1-{session}", "tactical_setup_tags_artifact.json"),
    "tactical_boundaries": ("integrated-investment-decision-product-v1-{session}", "tactical_confirmation_invalidation_boundaries_artifact.json"),
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


def _project_to_daily_tickers(artifact: Mapping[str, Any] | None, daily_tickers: set[str]) -> dict[str, Any] | None:
    """Restrict ``artifact["records"]`` to ``daily_tickers`` for a transient join-time view --
    never fabricates a record for a Daily ticker the axis doesn't cover, never mutates the
    artifact's own identity (the identity describes the ORIGINAL, unprojected content; this is
    a view, not a new artifact). ``None`` in, ``None`` out."""
    if artifact is None:
        return None
    records = artifact.get("records") or {}
    projected = dict(artifact)
    projected["records"] = {ticker: records[ticker] for ticker in daily_tickers if ticker in records}
    return projected


def materialize_current_fundamental_feature_store_context(*, root: Path, requested_at: str) -> dict[str, Any]:
    """Build the current ``market_wide_fundamental_feature_store/v1`` research context fresh
    from ``financial_v2_current_input_authority``'s pinned, versioned structured-period-semantics
    chain -- the same evidence Financial V2 itself already reads and identity-verifies every
    session. Never uses ``market_wide_fundamental_feature_store.DEFAULT_SEMANTICS`` (the module's
    own frozen 2026-08-31 constant) and never reads the frozen 2026-08-31
    ``market_wide_fundamental_feature_store_artifact.json`` snapshot the authority separately
    pins for Financial V2's OWN internal entity-type join -- this axis independently rebuilds a
    fresh feature-store artifact from the current semantics rows instead.

    Financial evidence is periodic, not daily: this axis is deliberately NOT checked against the
    Daily ``session`` the way ``tactical_behavior`` is -- its content identity is expected to
    repeat unchanged across many consecutive sessions and only changes when the pinned authority
    itself is deliberately advanced to a newer retained semantics snapshot.

    Never raises: a missing/drifted authority input is an explicit ``UNAVAILABLE`` status.
    """
    try:
        authority = financial_v2_current_input_authority.resolve(Path(root))
        semantic_rows, semantics_artifact = canonical_daily_financial_v2_materialization.load_semantic_rows(authority)
    except financial_v2_current_input_authority.FinancialV2InputAuthorityError as exc:
        return {"status": "UNAVAILABLE", "reason_code": "FUNDAMENTAL_FEATURE_SEMANTICS_SOURCE_UNAVAILABLE", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - axis-local failure must stay non-blocking
        return {"status": "UNAVAILABLE", "reason_code": type(exc).__name__, "detail": str(exc)}
    artifact = market_wide_fundamental_feature_store.build_artifact(
        semantic_rows=semantic_rows, period_semantics_identity=semantics_artifact["artifact_identity"],
        requested_at=requested_at,
    )
    return {
        "status": "MATERIALIZED",
        "artifact": artifact,
        "source_semantics_identity": semantics_artifact["artifact_identity"],
        "financial_input_authority": authority.to_manifest(),
    }


def materialize_current_tactical_behavior_context(
    *,
    session: str,
    registry_inputs: Mapping[str, Any],
    supplementary: Mapping[str, Any],
    requested_at: str,
) -> dict[str, Any]:
    """Build the current-session ``tactical_behavior_context/v1`` from already-governed,
    exact-session inputs only: the registry's own ``watchlist_tactical_entry_classifier``
    (``registry_inputs["tactical"]``) plus ``technical_structure_context``/``tactical_setup_tags``,
    both now retained per-session by ``canonical_post_close_pipeline.py`` (rebuilt there, once,
    from the same session's already-qualified descriptive/snapshot/recovery evidence -- no
    duplicate computation happens in this module). Boundaries and leadership are optional,
    exactly as ``tactical_behavior_context.build_artifact`` already degrades them.

    A mandatory-input gap or a session mismatch against the requested Daily ``session`` is an
    explicit ``UNAVAILABLE`` status -- never a historical fallback, never raised out to the
    caller.
    """
    tactical = registry_inputs.get("tactical")
    technical_structure = supplementary.get("technical_structure")
    setup_tags = supplementary.get("tactical_setup_tags")
    if not isinstance(tactical, Mapping) or not isinstance(technical_structure, Mapping) or not isinstance(setup_tags, Mapping):
        return {
            "status": "UNAVAILABLE",
            "reason_code": "TACTICAL_BEHAVIOR_MANDATORY_INPUT_MISSING",
            "detail": {
                "tactical_available": isinstance(tactical, Mapping),
                "technical_structure_available": isinstance(technical_structure, Mapping),
                "tactical_setup_tags_available": isinstance(setup_tags, Mapping),
            },
        }
    if tactical.get("session") != session:
        return {
            "status": "UNAVAILABLE", "reason_code": "TACTICAL_SESSION_MISMATCH",
            "detail": {"expected": session, "observed": tactical.get("session")},
        }
    try:
        artifact = tactical_behavior_context.build_artifact(
            tactical=tactical, technical_structure=technical_structure, tactical_setup_tags=setup_tags,
            confirmation_invalidation_boundaries=supplementary.get("tactical_boundaries"),
            current_leadership=supplementary.get("leadership"),
            requested_at=requested_at,
        )
    except tactical_behavior_context.TacticalBehaviorContextError as exc:
        return {"status": "UNAVAILABLE", "reason_code": str(exc), "detail": None}
    except Exception as exc:  # noqa: BLE001 - axis-local failure must stay non-blocking
        return {"status": "UNAVAILABLE", "reason_code": type(exc).__name__, "detail": str(exc)}
    return {"status": "MATERIALIZED", "artifact": artifact}


def materialize_current_investment_decision_workspace(
    *,
    session: str,
    registry_inputs: Mapping[str, Any],
    supplementary: Mapping[str, Any],
    requested_at: str,
    feature_store: Mapping[str, Any] | None = None,
    tactical_behavior: Mapping[str, Any] | None = None,
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

    ``feature_store``/``tactical_behavior``, when supplied, are the already-materialized
    ``market_wide_fundamental_feature_store/v1``/``tactical_behavior_context/v1`` artifacts
    (see ``materialize_current_fundamental_feature_store_context``/``materialize_current_
    tactical_behavior_context``); ``None`` means that axis is genuinely unavailable this run,
    exactly the same optional, gracefully-degrading semantics every other axis here already has.

    Raises ``CanonicalCurrentProductProjectionsError`` if the two required registry inputs are
    absent -- there is no fallback path for these; a Daily run without them has no valid
    Workspace denominator to build from.
    """
    watchlist = registry_inputs.get("tactical")
    valuation = registry_inputs.get("valuation")
    if not isinstance(watchlist, Mapping) or not isinstance(valuation, Mapping):
        raise CanonicalCurrentProductProjectionsError("WORKSPACE_REQUIRED_REGISTRY_INPUT_MISSING")

    # market_wide_fundamental_feature_store/v1's own ticker universe (drawn from the structured
    # financial-semantics corpus) need not equal -- and today does not equal -- the Daily
    # Product's own denominator (watchlist/valuation). Left unprojected, an extra feature-store
    # ticker would widen current_valuation_opportunity_integration's ticker union past what
    # financial_analysis_product_context (itself already Daily-denominator-complete) covers,
    # tripping its own zero-silent-drop invariant. Mirrors canonical_daily_financial_v2_
    # materialization.build_compact_product's established pattern: project the axis's own
    # narrower/wider engine cohort onto the Daily Product's OWN ticker denominator, never the
    # other way around. The retained on-disk Feature Store artifact keeps its full, unprojected
    # records and its own real identity -- only this transient join-time view is restricted.
    daily_tickers = set((watchlist.get("records") or {})) | set((valuation.get("records") or {}))
    projected_feature_store = _project_to_daily_tickers(feature_store, daily_tickers)

    opportunity_and_decision = current_valuation_opportunity_integration.build_artifacts(
        as_of_session=session,
        feature_store=projected_feature_store,
        tactical_behavior=tactical_behavior,
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
        feature_store_result = materialize_current_fundamental_feature_store_context(
            root=root, requested_at=requested_at,
        )
        tactical_behavior_result = materialize_current_tactical_behavior_context(
            session=session, registry_inputs=registry_inputs, supplementary=supplementary,
            requested_at=requested_at,
        )
        feature_store_artifact = (
            feature_store_result.get("artifact") if feature_store_result.get("status") == "MATERIALIZED" else None
        )
        tactical_behavior_artifact = (
            tactical_behavior_result.get("artifact") if tactical_behavior_result.get("status") == "MATERIALIZED" else None
        )
        workspace_bundle = materialize_current_investment_decision_workspace(
            session=session, registry_inputs=registry_inputs, supplementary=supplementary,
            requested_at=requested_at, feature_store=feature_store_artifact,
            tactical_behavior=tactical_behavior_artifact,
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

    fundamental_feature_store_status: dict[str, Any] = {"status": feature_store_result.get("status")}
    if feature_store_artifact is not None:
        # Preserve the Feature Store's own scalable summary/records-payload representation
        # (mirrors tools/run_market_wide_fundamental_feature_store_v1.py) rather than writing one
        # enormous inline JSON file -- the in-memory ``feature_store_artifact`` used above for the
        # opportunity/decision join keeps its own full ``records``-inclusive identity untouched.
        summary = dict(feature_store_artifact)
        records = summary.pop("records")
        records_path = operation_dir / FEATURE_STORE_RECORDS_FILENAME
        digest = hashlib.sha256()
        with gzip.open(records_path, "wt", encoding="utf-8", newline="\n") as handle:
            for ticker in sorted(records):
                line = json.dumps(records[ticker], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                digest.update(line.encode("utf-8"))
                handle.write(line)
        summary["records_payload"] = {
            "path": FEATURE_STORE_RECORDS_FILENAME, "record_count": len(records),
            "canonical_jsonl_sha256": digest.hexdigest(),
        }
        summary.update(market_wide_fundamental_feature_store.content_identity(summary))
        atomic_write_json(operation_dir / FEATURE_STORE_ARTIFACT_FILENAME, summary)
        fundamental_feature_store_status.update({
            "artifact_identity": feature_store_artifact.get("artifact_identity"),
            "retained_summary_identity": summary.get("artifact_identity"),
            "input_period_semantics_identity": feature_store_artifact.get("input_period_semantics_identity"),
            "ticker_denominator": (feature_store_artifact.get("coverage") or {}).get("ticker_denominator"),
        })
    else:
        fundamental_feature_store_status["reason_code"] = feature_store_result.get("reason_code")

    tactical_behavior_status: dict[str, Any] = {"status": tactical_behavior_result.get("status")}
    if tactical_behavior_artifact is not None:
        atomic_write_json(operation_dir / TACTICAL_BEHAVIOR_ARTIFACT_FILENAME, tactical_behavior_artifact)
        tactical_behavior_status.update({
            "artifact_identity": tactical_behavior_artifact.get("artifact_identity"),
            "session": tactical_behavior_artifact.get("session"),
            "candidate_count": (tactical_behavior_artifact.get("coverage") or {}).get("candidate_count"),
        })
    else:
        tactical_behavior_status["reason_code"] = tactical_behavior_result.get("reason_code")

    unavailable_optional_axes = ["thesis_cases", "portfolio"]
    if feature_store_artifact is None:
        unavailable_optional_axes.append("feature_store")
    if tactical_behavior_artifact is None:
        unavailable_optional_axes.append("tactical_behavior")

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
        "fundamental_feature_store": fundamental_feature_store_status,
        "tactical_behavior_context": tactical_behavior_status,
        "supplementary_inputs_available": {name: value is not None for name, value in supplementary.items()},
        "unavailable_optional_axes": sorted(unavailable_optional_axes),
    }
