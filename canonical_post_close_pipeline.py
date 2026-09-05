"""Canonical post-close one-command operator pipeline (PROSPECTIVE_RESEARCH scope: operational
composition only -- no new analytical methodology, no authority promotion).

This module is pure orchestration glue over already-existing, already-tested capabilities:

    GOVERNED EXACT-SESSION MARKET EVIDENCE (DNSE P3F9B, existing)
        -> CANONICAL RUNTIME MATERIALIZATION (existing per-session artifact chain, reused via
           daily_session_level2_package.materialize_independent_components/maybe_build_triage_dependent)
        -> DETERMINISTIC CURRENT-SESSION ANALYTICS / CURRENT RESEARCH CONTEXT (same reused chain,
           plus best-effort enrichment builders for the three components no orchestrator wires today)
        -> EXACT INPUT REGISTRATION (new: config/daily_research_session_input_registry.json writer;
           no such writer existed anywhere in the repository before this module)
        -> CANONICAL DAILY PRODUCER (existing daily_producer_pipeline.run_daily_producer, unmodified)
        -> PROSPECTIVE COLLECTION (existing cohort collector plus retained-only outcome-feedback roll-forward)
        -> BUNDLE INDEX / AI HANDOFF (new: tiered index over already-materialized artifacts; no
           payload is duplicated, only paths + identities + hashes)

No new provider is added. DNSE/Livespeed remains the primary, preferred full-universe acquisition
route this pipeline calls (via daily_session_level2_package.ensure_exact_session_snapshot's own
Pass 1). Since 2026-09-03 (MULTI_SOURCE_EXACT_SESSION_MARKET_EVIDENCE_AND_DAILY_RESILIENCE_V1),
that same acquisition boundary also recovers DNSE's own exact-session gaps through this project's
existing VCI/KBS capability (vn_stock_pipeline.py's fetch primitives, reused unmodified) for
Current Research / Daily Product Mode only -- never Audit/PIT/Execution Mode, never a second
full-universe acquisition owner, never concurrent. See PROVIDER_ROLE_MATRIX below and
multi_source_exact_session_resolver.py's own module docstring for the four-pass strategy.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import daily_session_level2_package as level2
import release_session_contract
from canonical_dashboard_runtime_release import (
    CanonicalRuntimeReleaseError,
    materialize_canonical_runtime_release,
)
from completed_market_session_gate import DEFAULT_POST_CLOSE_ATTEMPT_FLOOR
from daily_producer_pipeline import DailyProducerError, run_daily_producer
from daily_research_session_operations import (
    load_registry,
    resolve_inputs,
    selection_identities,
    validate_coherence,
)
from multi_source_exact_session_resolver import DEGRADED_RECOVERY_COMPLETED
from multi_source_market_evidence_contract import DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD
from vn_time import VN_TZ, vn_now

ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "canonical_post_close_pipeline/v1"

# Registry input class -> daily_session_level2_package.session_artifact_paths() key. Every
# REQUIRED registry key must resolve; market_flow_positioning is intentionally omitted -- Level-2
# does not build it and the real 2026-08-24/25 governed sessions register it (see
# config/daily_research_session_input_registry.json). Its absence is an accepted, already-precedented
# optional gap, not a new one.
REGISTRY_KEY_TO_LEVEL2_KEY = {
    "descriptive": "descriptive_research",
    "screening": "screening_foundation",
    "tactical": "tactical_classifier",
    "triage": "session_triage",
    "fundamental": "fundamental",
    "valuation": "valuation",
    "catalyst": "catalyst",
    "corporate_intelligence": "corporate_intelligence",
    "official_universe": "official_universe",
    "event_context": "official_event_context",
}
REQUIRED_REGISTRY_KEYS = (
    "descriptive", "screening", "tactical", "triage",
    "fundamental", "valuation", "catalyst", "corporate_intelligence",
)
OPTIONAL_REGISTRY_KEYS = ("official_universe", "event_context")

# These Level-2 keys are governed retained inputs, not outputs of a redirected
# canonical attempt. They must continue to resolve under the Producer root.
RETAINED_LEVEL2_INPUT_KEYS = frozenset({
    "fundamental", "official_universe", "official_event_context", "catalyst",
    "historical_context", "financial_momentum", "corporate_event_context",
    "corporate_intelligence_axis",
})

# A completed-session snapshot with fewer than this fraction of the attempted DNSE candidate
# universe returning an exact-dated bar is treated as evidence of a partial/failed acquisition
# (pre-close attempt, connectivity failure, etc.), never as a genuine thin trading day. Observed
# real full-universe runs to date: 2026-08-20 50.09%, 2026-08-25 53.06% -- this floor is set well
# below that range so it never rejects a normal session while still catching a degenerate fetch.
MIN_EXACT_SESSION_COVERAGE_RATIO = 0.20

# These are the publisher's session-sensitive runtime inputs.  Their session semantics are
# owned by release_session_contract.py; this pipeline deliberately calls that contract rather
# than re-implementing its manifest/CSV/JSON validation rules.
DASHBOARD_RUNTIME_REQUIRED_ARTIFACTS = (
    "screen_snapshot.csv", "market_breadth.csv", "analysis_latest.json",
)
DASHBOARD_RUNTIME_OPTIONAL_ARTIFACTS = ("screen_snapshot_live.csv",)

# Owner operational collection cutoff: same-day session evidence is not treated as eligible for
# canonical post-close use before this local time, regardless of DNSE credential/API availability
# or of the exchange's own ~15:00 close. This is an operational collection policy, not a claim
# that providers can never revise data after this point. Single-sourced from
# completed_market_session_gate.DEFAULT_POST_CLOSE_ATTEMPT_FLOOR (2026-09-03 rebaseline, was
# 18:00) so this pipeline's own same-day gate and the Phase A/B gate never drift into two
# competing floors.
POST_CLOSE_COLLECTION_CUTOFF_LOCAL_TIME = DEFAULT_POST_CLOSE_ATTEMPT_FLOOR


class CanonicalPostCloseError(ValueError):
    """A deliberately concise operational refusal, mirroring DailyProducerError's style."""


class PreCutoffArtifactError(CanonicalPostCloseError):
    """An existing same-session artifact fails the post-close eligibility contract (see
    assert_post_close_eligible). Distinct from CanonicalPostCloseError so callers can catch this
    specifically and redirect to a fresh acquisition attempt, rather than treating it as a hard
    pipeline failure the way an unrelated CanonicalPostCloseError should be treated."""


PROVIDER_ROLE_MATRIX = {
    "DNSE_LIVESPEED": {
        "role": "CANONICAL_PRIMARY",
        "scope": "Full-universe exact-session OHLC acquisition (Pass 1) and every current-research "
                 "artifact this pipeline builds or reuses (descriptive, screening, tactical, "
                 "triage, corporate intelligence, valuation price leg, liquidity, technical "
                 "recovery). Preferred current-market source wherever it has exact-session "
                 "evidence -- never re-queried or second-guessed once resolved.",
        "used_by_this_pipeline_for": ["session_acquisition", "runtime_evidence_input", "current_research"],
    },
    "FHSC": {
        "role": "SUPPLEMENTAL_BOUNDED",
        "scope": "Shadow/reference cross-validation of DNSE volume semantics only (HOSE-only, "
                 "credential-blocked in production). Never a price/OHLC acquisition route.",
        "used_by_this_pipeline_for": [],
        "constraint": "This pipeline never calls FHSC and never promotes it toward liquidity, "
                       "ADTV20, or RAW_AS_TRADED authority as an operational side effect.",
    },
    "VNSTOCK_VCI_KBS": {
        "role": "CURRENT_RESEARCH_RECOVERY",
        "scope": "2026-09-03 MULTI_SOURCE_EXACT_SESSION_MARKET_EVIDENCE_AND_DAILY_RESILIENCE_V1: "
                 "vn_stock_pipeline.py's existing VCI/KBS fetch primitives (fetch_single_source, "
                 "reused unmodified) now recover exactly the exact-session candidates DNSE did not "
                 "resolve (multi_source_exact_session_resolver.py, invoked in-process from "
                 "daily_session_level2_package.ensure_exact_session_snapshot -- never a second "
                 "market-wide acquisition owner: DNSE Pass 1 always runs first and full-universe; "
                 "VCI/KBS only ever touch DNSE's own gaps). vn_stock_pipeline.py's DB-writing "
                 "update/backfill commands and vn_stock.db remain a wholly separate legacy path, "
                 "never read or written by this recovery. Never promoted toward RAW_AS_TRADED, "
                 "PIT, liquidity/ADTV20, or execution authority -- Current Research / Daily "
                 "Product Mode only.",
        "used_by_this_pipeline_for": ["exact_session_gap_recovery", "current_research"],
        "constraint": "Recovery is per-ticker and bounded to DNSE's own gaps -- never a broad "
                       "second full-universe pull, never concurrent (no evidence VCI/KBS tolerate "
                       "concurrent access; see docs/DECISIONS.md "
                       "MARKET_WIDE_ENRICHMENT_AND_CANONICALIZATION_V1 = PAUSED_RATE_LIMIT_CONSTRAINED), "
                       "and volume is never synthesized across the DNSE/VCI-KBS provider families "
                       "(see multi_source_market_evidence_contract.py).",
    },
}


def _git_head(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evaluate_dashboard_runtime_readiness(runtime_root: Path, session: str) -> dict[str, Any]:
    """Return the existing release-session contract's verdict for one canonical session.

    ``runtime_root`` is the exact input root that publish_dashboard.py will consume.  A
    successful research/Producer run is not a substitute for this check: only a complete,
    same-session runtime release may be advertised as ready for governed publication.
    """
    runtime_root = Path(runtime_root)
    required = list(DASHBOARD_RUNTIME_REQUIRED_ARTIFACTS)
    required += [name for name in DASHBOARD_RUNTIME_OPTIONAL_ARTIFACTS
                 if (runtime_root / name).is_file()]
    report = release_session_contract.resolve_release_session(runtime_root, required)
    exact_session = report.session == session
    ready = bool(report.ready and exact_session)
    reason = None
    if not report.ready:
        reason = "RUNTIME_RELEASE_SESSION_CONTRACT_FAILED"
    elif not exact_session:
        reason = f"RUNTIME_RELEASE_SESSION_MISMATCH:expected={session}:observed={report.session or 'UNRESOLVED'}"
    return {
        "runtime_root": str(runtime_root),
        "expected_session": session,
        "resolved_session": report.session,
        "ready": ready,
        "reason": reason,
        "release_session_report": {
            "authority": report.authority,
            "required_artifacts": [row.name for row in report.results],
            "problems": list(report.problems),
            "results": [
                {"name": row.name, "status": row.status, "observed": row.observed,
                 "detail": row.detail}
                for row in report.results
            ],
        },
    }


def assert_same_day_post_close_eligible(session: str, *, now: datetime | None = None) -> None:
    """Fail closed before any acquisition/reuse attempt when the requested session is today's
    Vietnam calendar date and it is not yet past the owner's collection cutoff. Deliberately
    accepts an injectable `now` rather than calling the wall clock internally, so tests never
    depend on real time and business logic elsewhere never has to hardwire it either. A session
    strictly before today is never gated here -- only same-day requests are collection-cutoff
    sensitive; a past completed session is governed by its own retained acquisition evidence.
    """
    now = now or vn_now()
    local = now.astimezone(VN_TZ)
    if session == local.date().isoformat() and local.time() < POST_CLOSE_COLLECTION_CUTOFF_LOCAL_TIME:
        raise CanonicalPostCloseError(
            "REFUSE_CANONICAL_POST_CLOSE:COMPLETED_SESSION_EVIDENCE_NOT_YET_ELIGIBLE:"
            f"session={session}:local_time={local.isoformat(timespec='seconds')}:"
            f"cutoff={POST_CLOSE_COLLECTION_CUTOFF_LOCAL_TIME.isoformat()}"
        )


def _exact_session_coverage(snapshot: Mapping[str, Any]) -> tuple[int, int, float]:
    total = int(snapshot.get("attempted_candidate_count") or 0)
    exact = int(snapshot.get("exact_session_observed_count") or 0)
    ratio = (exact / total) if total else 0.0
    return exact, total, ratio


def _current_research_coverage(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reporting-only companion to ``_exact_session_coverage`` (DAILY_ACTIVITY_AWARE_ADAPTIVE_
    GAP_RECOVERY_V1, 2026-09-04): the same exact-session numerator against the semantically
    narrower current-equity/recovery-eligible denominator (daily_recovery_eligibility_projection,
    stamped onto the snapshot by daily_session_level2_package.ensure_exact_session_snapshot),
    instead of the raw attempted-candidate count.

    Deliberately never consulted by ``assert_post_close_eligible``'s own MIN_EXACT_SESSION_
    COVERAGE_RATIO gate -- that gate's raw-candidate denominator is an intentional, pre-existing
    design choice (a narrower denominator computed from a downstream/resolved artifact would be
    circular; see current_universe_status_and_session_coverage_resolution.py's own module note).
    This function only surfaces the more honest Current-Research figure for callers/consumers
    that display or reason about partial coverage -- it asserts nothing and blocks nothing.
    Returns ``None`` when the snapshot predates this milestone or the projection was unavailable
    (degraded to "no filter") for this session.
    """
    coverage = snapshot.get("recovery_eligibility")
    if not isinstance(coverage, Mapping) or not coverage.get("available"):
        return None
    return {
        "current_equity_denominator": coverage.get("current_equity_denominator"),
        "current_equity_exact": coverage.get("current_equity_exact"),
        "current_equity_coverage_ratio": coverage.get("current_equity_coverage_ratio"),
        "not_authoritative": True,
        "scope": "CURRENT_RESEARCH_REPORTING_ONLY_NEVER_A_GATE",
    }


def _provider_contribution_counts(snapshot: Mapping[str, Any]) -> dict[str, int]:
    """Per-source count of EXACT_SESSION_RETAINED tickers in a (possibly multi-source-
    resolved) exact-session snapshot. DNSE-only snapshots (contract unchanged) report
    entirely under "DNSE"; a resolved snapshot's recovered records carry their own
    honest observation-row provider (VCI/KBS) -- see multi_source_exact_session_resolver.py.
    """
    counts: dict[str, int] = {}
    for record in (snapshot.get("records") or {}).values():
        if record.get("disposition") != "EXACT_SESSION_RETAINED":
            continue
        observations = record.get("observations") or []
        provider = observations[0].get("provider") if observations else "UNKNOWN"
        counts[provider] = counts.get(provider, 0) + 1
    return counts


def assert_post_close_eligible(
    snapshot: Mapping[str, Any], session: str, *, now: datetime | None = None,
    artifact_root: Path | None = None,
) -> None:
    """The 6-point contract an *existing* same-session P3F9B snapshot must satisfy before this
    pipeline may reuse it as canonical post-close evidence, rather than treating mere same-session
    file presence as sufficient (that was the original defect: an artifact genuinely acquired
    before the owner's collection cutoff can still have resolved_completed_session == session and
    look self-consistent). Raises PreCutoffArtifactError -- distinct from a hard pipeline failure --
    naming exactly which condition failed; callers should catch it and redirect to a fresh
    acquisition rather than propagate it.

    2026-09-04 MULTI_SOURCE_DAILY_DEGRADED_PROVIDER_AUTORECOVERY_AND_IDEMPOTENCY_CORRECTIVE_V1:
    point 6 (provider-health gate) closes a second idempotency escape -- an existing snapshot can
    have session identity, lineage, contract version, scope, and coverage ratio all genuinely
    correct while still reflecting DNSE_BROAD_STALE_OR_INCOMPLETE_EOD that was never resolved
    (e.g. a pre-corrective artifact written before this milestone existed). ``artifact_root``,
    when given, loads the sibling multi-source evidence artifact
    (daily_session_level2_package.session_artifact_paths' own multi_source_market_evidence key,
    same directory as this snapshot) and cross-checks its retained DNSE quality sentinel verdict
    against ``snapshot``'s own self-declared ``degraded_provider_recovery`` marker -- identical
    policy to daily_session_level2_package._canonical_snapshot_gate_satisfied, applied here so
    resolve_acquisition_root's EXISTING fresh-attempt-directory redirect (today used only for a
    pre-cutoff artifact) also covers this case, with no new mechanism. ``artifact_root`` omitted
    (the default) or a missing/unreadable companion evidence file skips this point entirely --
    "nothing to disprove trust with", never "untrustworthy" -- so this stays backward compatible
    with every caller/test that predates this point and never wrote a companion evidence file.
    """
    now = now or vn_now()
    # 1. session identity
    if snapshot.get("resolved_completed_session") != session or snapshot.get("retained_snapshot_session") != session:
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_SESSION_IDENTITY_MISMATCH:" + session)
    # 4. required lineage/hash metadata present
    identity, sha = snapshot.get("snapshot_identity"), snapshot.get("snapshot_sha256")
    if not isinstance(identity, str) or not isinstance(sha, str) or not identity.endswith(sha):
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_LINEAGE_HASH_METADATA_MISSING:" + session)
    # 3. upstream acquisition has a terminal/complete status for its own contract
    if snapshot.get("contract_version") != "p3f9_exact_session_mva_snapshot/v2":
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_UPSTREAM_CONTRACT_UNRECOGNIZED:" + session)
    if snapshot.get("materialization_scope") != "FULL_CANONICAL_CANDIDATE_SET":
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_NOT_FULL_UNIVERSE_SCOPE:" + session)
    if snapshot.get("unattempted_without_explicit_disposition") not in (0, None):
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_HAS_UNATTEMPTED_CANDIDATES:" + session)
    # 5. not merely a partial artifact from an interrupted acquisition
    exact, total, ratio = _exact_session_coverage(snapshot)
    if total <= 0 or ratio < MIN_EXACT_SESSION_COVERAGE_RATIO:
        raise PreCutoffArtifactError(
            f"EXISTING_ARTIFACT_PARTIAL_OR_INTRADAY_EVIDENCE:session={session}:exact={exact}:total={total}:ratio={ratio:.4f}"
        )
    # 2. acquisition/request timestamp satisfies the canonical post-close eligibility contract
    requested_at_raw = snapshot.get("requested_at")
    if not isinstance(requested_at_raw, str) or not requested_at_raw:
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_ACQUISITION_TIMESTAMP_MISSING:" + session)
    try:
        acquired_at = datetime.fromisoformat(requested_at_raw)
    except ValueError as exc:
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_ACQUISITION_TIMESTAMP_UNPARSEABLE:" + session) from exc
    acquired_local = (acquired_at if acquired_at.tzinfo else acquired_at.replace(tzinfo=VN_TZ)).astimezone(VN_TZ)
    if acquired_local.date().isoformat() == session and acquired_local.time() < POST_CLOSE_COLLECTION_CUTOFF_LOCAL_TIME:
        raise PreCutoffArtifactError(
            f"PRE_CUTOFF_RETAINED_NOT_POST_CLOSE_ELIGIBLE:session={session}:"
            f"acquired_at_local={acquired_local.isoformat(timespec='seconds')}:"
            f"cutoff={POST_CLOSE_COLLECTION_CUTOFF_LOCAL_TIME.isoformat()}"
        )
    # 6. provider-health gate: an existing snapshot that reflects an unresolved DNSE broad
    # degradation is never eligible for reuse, even though points 1-5 above all pass.
    if artifact_root is not None:
        evidence_path = level2.session_artifact_paths(artifact_root, session)["multi_source_market_evidence"]
        if evidence_path.is_file():
            try:
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                evidence = None
            sentinel = evidence.get("dnse_quality_sentinel") if isinstance(evidence, Mapping) else None
            health = sentinel.get("health") if isinstance(sentinel, Mapping) else None
            if isinstance(health, Mapping) and health.get("state") == DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD:
                recovery = snapshot.get("degraded_provider_recovery")
                if not (isinstance(recovery, Mapping) and recovery.get("mode") == DEGRADED_RECOVERY_COMPLETED):
                    raise PreCutoffArtifactError(
                        f"EXISTING_ARTIFACT_DNSE_PROVIDER_HEALTH_GATE_NOT_SATISFIED:session={session}"
                    )


def resolve_acquisition_root(root: Path, session: str, *, now: datetime | None = None) -> tuple[Path, dict[str, Any]]:
    """Decide where THIS run's DNSE acquisition/materialization chain should read and write.

    Defaults to `root` (Level-2's own static per-session paths), exactly as before this fix, when
    no same-session P3F9B snapshot exists yet or the existing one is genuinely post-close eligible
    (real idempotent reuse -- no unnecessary network acquisition on an identical rerun). Only when
    an existing snapshot is found and fails assert_post_close_eligible does this redirect to a
    fresh, distinctly-named attempt directory nested under the same session's operations-review
    namespace, so the ineligible artifact is never overwritten, relabeled, or silently resumed
    from -- the smallest available run/attempt/output-directory mechanism, not a second data lake.
    """
    now = now or vn_now()
    assert_same_day_post_close_eligible(session, now=now)
    default_paths = level2.session_artifact_paths(root, session)
    existing = _load(default_paths["exact_session_snapshot"])

    def retained_attempt_root() -> tuple[Path, Mapping[str, Any]] | None:
        # A completed historical P3F9B attempt is retained beneath the canonical
        # attempt namespace. Reuse its exact artifact root rather than using the
        # current wall clock to acquire whichever session is latest today.
        attempts_root = root / "operations-review" / "canonical-post-close-v1" / session
        if attempts_root.is_dir():
            for candidate_root in sorted(attempts_root.glob("post-close-attempt-*"), reverse=True):
                candidate = _load(level2.session_artifact_paths(candidate_root, session)["exact_session_snapshot"])
                if not isinstance(candidate, Mapping):
                    continue
                try:
                    assert_post_close_eligible(candidate, session, now=now, artifact_root=candidate_root)
                except PreCutoffArtifactError:
                    continue
                return candidate_root, candidate

        return None

    if existing is None:
        retained = retained_attempt_root()
        if retained is not None:
            candidate_root, candidate = retained
            return candidate_root, {
                "redirected": False,
                "reused_existing_eligible_artifact": True,
                "historical_retained_reuse": True,
                "artifact_identity": candidate.get("snapshot_identity"),
                "artifact_root": _rel(root, candidate_root),
            }
        return root, {"redirected": False, "reason": "NO_EXISTING_ARTIFACT_FOR_SESSION"}
    try:
        assert_post_close_eligible(existing, session, now=now, artifact_root=root)
    except PreCutoffArtifactError as exc:
        retained = retained_attempt_root()
        if retained is not None:
            candidate_root, candidate = retained
            return candidate_root, {
                "redirected": False,
                "reused_existing_eligible_artifact": True,
                "historical_retained_reuse": True,
                "artifact_identity": candidate.get("snapshot_identity"),
                "artifact_root": _rel(root, candidate_root),
            }
        attempt_root = (
            root / "operations-review" / "canonical-post-close-v1" / session
            / f"post-close-attempt-{now.astimezone(VN_TZ).strftime('%H%M%S')}"
        )
        return attempt_root, {
            "redirected": True,
            "reason": str(exc),
            "pre_cutoff_artifact_classification": "PRE_CUTOFF_RETAINED_NOT_POST_CLOSE_ELIGIBLE",
            "pre_cutoff_artifact_path": _rel(root, default_paths["exact_session_snapshot"]),
            "pre_cutoff_artifact_identity": existing.get("snapshot_identity"),
            "fresh_attempt_root": _rel(root, attempt_root),
        }
    return root, {
        "redirected": False,
        "reused_existing_eligible_artifact": True,
        "artifact_identity": existing.get("snapshot_identity"),
    }


def acquire_and_materialize(
    root: Path, session: str, runtime_root: Path, *, workers: int = 12, now: datetime | None = None,
) -> dict[str, Any]:
    """Stage 1-3: DNSE acquisition, runtime materialization, current-session analytics.

    Wholly delegates to daily_session_level2_package -- this pipeline adds no second research
    engine. The exact-session P3F9B snapshot is acquired and its coverage validated FIRST, before
    any liquidity or technical-recovery work runs: a session whose coverage is already below
    MIN_EXACT_SESSION_COVERAGE_RATIO stops immediately, so a thin/partial acquisition never spends
    liquidity batches, technical-history recovery, or any other downstream current-session
    analytics on evidence this function is about to reject anyway (2026-09-03 corrective fix --
    the live defect this closes ran 17 liquidity batches and technical-history recovery to
    completion on a 17/1683 exact-session snapshot before the coverage gate below ever ran).
    Raises CanonicalPostCloseError if the acquired snapshot's own resolved session does not
    exactly equal the requested session (no silent prior-session substitution), if an existing
    same-session snapshot exists but is not post-close eligible and today's collection cutoff has
    not yet passed (resolve_acquisition_root's same-day gate), or if coverage is insufficient.
    """
    now = now or vn_now()
    artifact_root, eligibility = resolve_acquisition_root(root, session, now=now)
    paths = level2.session_artifact_paths(artifact_root, session)
    try:
        level2.ensure_exact_session_snapshot(
            artifact_root, session, runtime_root, workers=workers, now=now, execution_root=root,
        )
    except ValueError as exc:
        if str(exc).startswith("P3F9B_ACQUIRED_SESSION_MISMATCH"):
            raise CanonicalPostCloseError(
                "REFUSE_CANONICAL_POST_CLOSE:" + str(exc)
                + ":requested session is not the DNSE wall-clock-resolved latest completed session; "
                  "never silently substituting."
            ) from exc
        raise
    snapshot = _load(paths["exact_session_snapshot"])
    if not snapshot:
        raise CanonicalPostCloseError("REFUSE_CANONICAL_POST_CLOSE:EXACT_SESSION_SNAPSHOT_MISSING_AFTER_ACQUISITION")
    exact, total, coverage_ratio = _exact_session_coverage(snapshot)
    if coverage_ratio < MIN_EXACT_SESSION_COVERAGE_RATIO:
        health_state = snapshot.get("dnse_provider_health_state")
        recovery = snapshot.get("degraded_provider_recovery") if isinstance(snapshot.get("degraded_provider_recovery"), Mapping) else {}
        degraded_note = (
            f":DNSE_PROVIDER_HEALTH=DEGRADED:DEGRADED_PROVIDER_RECOVERY_MODE={recovery.get('mode')}"
            if health_state == DNSE_HEALTH_BROAD_STALE_OR_INCOMPLETE_EOD else ""
        )
        raise CanonicalPostCloseError(
            f"REFUSE_CANONICAL_POST_CLOSE:PARTIAL_OR_INTRADAY_SESSION_EVIDENCE:"
            f"exact={exact}:total={total}:ratio={coverage_ratio:.4f}:floor={MIN_EXACT_SESSION_COVERAGE_RATIO}"
            f"{degraded_note}"
        )
    level2.materialize_independent_components(
        artifact_root,
        session,
        runtime_root,
        workers=workers,
        now=now,
        execution_root=root,
    )
    triage_build_result = level2.maybe_build_triage_dependent(
        artifact_root,
        session,
        execution_root=root,
    )
    # Ground-truth check on the triage file itself, matching maybe_build_triage_dependent's own
    # fallback (registry-based session_triage_status would require this session to already be
    # registered, which it deliberately is not yet at this point in the pipeline -- registration
    # happens after acquisition, consuming this very artifact).
    triage_artifact = _load(paths["session_triage"])
    if not triage_artifact or triage_artifact.get("source_market_session") != session:
        raise CanonicalPostCloseError(
            "REFUSE_CANONICAL_POST_CLOSE:TRIAGE_NOT_EXACT_SESSION_CLEAN:session=" + session
        )
    return {
        "snapshot": snapshot,
        "resolved_completed_session": snapshot.get("resolved_completed_session"),
        "coverage": {"exact_session_retained_count": exact, "total_candidates": total, "ratio": coverage_ratio},
        "provider_contribution_counts": _provider_contribution_counts(snapshot),
        "triage_status": {"status": level2.EXACT_SESSION_CLEAN, "identity": triage_artifact.get("artifact_identity")},
        "triage_build_result": triage_build_result,
        "paths": paths,
        "artifact_root": artifact_root,
        "eligibility": eligibility,
    }


def enrichment_output_path(root: Path, session: str, name: str) -> Path:
    """Session-scoped output for the three components Level-2 only ever reuses at a shared,
    non-session-templated path (session_artifact_paths()'s financial_momentum/
    corporate_event_context/historical_context keys). Writing a freshly-built, session-specific
    artifact over one of those shared paths would silently relabel retained prior-as-of evidence
    under its old filename -- exactly what docs/DATA_FIRST_DOCTRINE.md's immutability/provenance
    rules forbid. A fresh build therefore gets its own session-scoped identity here instead.
    """
    return root / "operations-review" / "canonical-post-close-v1" / session / "enrichment" / f"{name}.json"


def build_enrichment_components(
    root: Path, session: str, *, artifact_root: Path | None = None, runtime_root: Path | None = None,
    priority_queue_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Best-effort materialize the three current-research components no orchestrator wires today
    (historical context, financial momentum, corporate event context). Each is fully independent;
    a failure in one never blocks the others or the rest of the pipeline -- component-local
    missing evidence stays component-local, per docs/AI_RULES.md invariant 6. A failed fresh build
    degrades to Level-2's shared prior-as-of file (still real retained evidence, just not
    session-pinned) rather than leaving the component wholly absent.

    `artifact_root` (defaulting to `root`) is where this run's session-specific Level-2 outputs
    are looked up. Immutable retained inputs stay under the Producer `root`, even when the run
    selected a fresh-attempt directory. Output always stays under `root`
    (this pipeline's own enrichment namespace never collides with a pre-cutoff artifact, since
    that namespace does not exist until this function runs).
    """
    artifact_root = artifact_root or root
    paths = level2.session_artifact_paths(artifact_root, session)
    retained_paths = level2.session_artifact_paths(root, session)
    results: dict[str, Any] = {}

    def _attempt(name: str, level2_key: str, fn) -> None:
        try:
            artifact = fn()
            out = enrichment_output_path(root, session, name)
            _write_json(out, artifact)
            results[name] = {"status": "BUILT", "artifact": artifact, "path": out}
            return
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: component-local isolation
            reason = f"{type(exc).__name__}:{exc}"
        prior = _load(retained_paths[level2_key])
        if prior:
            results[name] = {
                "status": "PRIOR_AS_OF_CONTEXT",
                "artifact": prior,
                "path": retained_paths[level2_key],
                "reason": reason,
            }
        else:
            results[name] = {"status": "UNAVAILABLE", "artifact": None, "reason": reason}

    def _financial_momentum():
        from current_financial_momentum_context import build_artifact as build
        official_universe = _load(retained_paths["official_universe"])
        fundamental = _load(retained_paths["fundamental"])
        descriptive = _load(paths["descriptive_research"])
        if not official_universe or not fundamental:
            raise CanonicalPostCloseError("REQUIRED_INPUT_MISSING")
        return build(current_official_universe=official_universe, current_fundamental=fundamental, current_descriptive=descriptive)

    def _corporate_event_context():
        from current_corporate_event_context import build_artifact as build, load_supplemental_retained_events
        official_universe = _load(retained_paths["official_universe"])
        official_event_context = _load(retained_paths["official_event_context"])
        if not official_universe or not official_event_context:
            raise CanonicalPostCloseError("REQUIRED_INPUT_MISSING")
        # official_event_context has been frozen at research_session=2026-08-21 since before
        # CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1 (no fresher retained
        # official ex-date evidence exists yet). Bind to that evidence's own session -- never
        # today's `session` -- exactly like current_corporate_intelligence_axis's build below, so
        # this component actually builds instead of always failing closed on
        # EVENT_CONTEXT_SESSION_MISMATCH and silently degrading to a frozen PRIOR_AS_OF copy every
        # day. Also activate supplemental_events (the HPG/VNM/VCB retained issuer/VSDC chains),
        # closing the gap the prior milestone explicitly left open for this shared component so
        # current_research_risk_register.py/current_research_decision_packet.py see the same
        # evidence current_corporate_intelligence_axis.py already does.
        evidence_session = official_event_context.get("research_session")
        supplemental = load_supplemental_retained_events(root, evidence_session) if evidence_session else None
        return build(
            official_universe=official_universe,
            official_event_context=official_event_context,
            supplemental_events=supplemental,
            research_session=evidence_session,
        )

    def _historical_context():
        from market_wide_historical_research_context import build_artifact as build
        universe_resolution = _load(paths["universe_resolution"])
        p3f9b_snapshot = _load(paths["exact_session_snapshot"])
        technical_recovery = _load(paths["technical_recovery"])
        strategy = _load(paths["strategy"])
        if not universe_resolution or not p3f9b_snapshot:
            raise CanonicalPostCloseError("REQUIRED_INPUT_MISSING")
        return build(universe_resolution_artifact=universe_resolution, p3f9b_snapshot=p3f9b_snapshot,
                     technical_history_recovery_artifact=technical_recovery, strategy_artifact=strategy)

    def _integrated_investment_decision_product():
        from integrated_investment_decision_product import build_artifact as build
        import canonical_daily_financial_v2_materialization as fin_v2_material
        import financial_v2_current_input_authority as fin_v2_authority
        import market_structure_breakout_product_projection as msb_proj
        import market_wide_relative_volume_research as rvol_research
        import tactical_confirmation_context as confirmation_context
        import tactical_confirmation_invalidation_boundaries as boundary_context
        import tactical_momentum_context as momentum_context
        import technical_structure_context as tsc
        # integrated_investment_decision_product.evaluate_tactical_phase/evaluate_participation read
        # a FLAT compact shape (eligible, market_structure_state, breakout_state_v3, bos_state,
        # choch_state, relative_volume_percentile, volume_acceleration_ratio, ...) -- the
        # market_structure_breakout_product_projection/v1 (Tactical V3) and market_wide_relative_
        # volume_research/v1 contracts, not watchlist_tactical_entry_classifier's own deeply nested
        # nine-state entry_state shape (no eligible/market_structure_state/bos_state keys at all) or
        # market_wide_current_descriptive_research's market-wide breadth shape (no per-ticker
        # relative_volume_percentile at all). Neither V3 projection nor relative-volume research has
        # its own canonical per-session materialization path yet, so both are built fresh here from
        # already-registered raw inputs -- exactly this function's existing pattern for financial_
        # momentum/corporate_event_context/historical_context above -- rather than loaded from a
        # path that does not exist. Verified against real 2026-08-28/2026-08-25 retained evidence:
        # the previous wiring produced research_action_posture=INSUFFICIENT_CURRENT_RESEARCH for
        # every ticker (eligible/market_structure_state always absent -> always None -> always
        # falsy), a silent, universe-wide defect this fix corrects.
        raw_val = _load(paths["valuation"]) or _load(retained_paths["valuation"])
        desc = _load(paths["descriptive_research"])
        p3f9b = _load(paths["exact_session_snapshot"])
        technical_recovery = _load(paths["technical_recovery"])
        mkt = _load(paths["sector_leadership"])
        opp = _load(paths["opportunity_prioritization"])
        if not desc or not p3f9b:
            raise CanonicalPostCloseError("REQUIRED_INPUT_MISSING")
        requested_at = f"{session}T15:00:00+07:00"
        technical_structure = tsc.build_artifact(
            current_descriptive=desc, p3f9b_snapshot=p3f9b, requested_at=requested_at,
            technical_history_recovery_artifact=technical_recovery,
        )
        tactical_projection = msb_proj.build_artifact(technical_structure=technical_structure, requested_at=requested_at)
        daily_denominator = sorted((p3f9b.get("records") or {}).keys())
        relative_volume = rvol_research.build_artifact(candidates=daily_denominator, records=p3f9b.get("records") or {}, session=session, requested_at=requested_at)
        # Both contexts consume the same already-qualified descriptive/snapshot/recovery evidence
        # as Tactical V3.  They add no provider acquisition and preserve each ticker's local
        # insufficient-history or participation limitation instead of dropping that ticker.
        momentum = momentum_context.build_artifact(
            current_descriptive=desc, p3f9b_snapshot=p3f9b, requested_at=requested_at,
            technical_history_recovery_artifact=technical_recovery,
        )
        confirmation = confirmation_context.build_artifact(
            structure_projection=tactical_projection, momentum=momentum,
            participation=relative_volume, requested_at=requested_at,
        )
        tactical_boundaries = None
        tactical_classifier = _load(paths["tactical_classifier"])
        if tactical_classifier:
            try:
                # Reuse the standing boundary engine's own semantics.  This is
                # retention instrumentation only; a missing boundary input may
                # not alter the already-determined action posture.
                tactical_boundaries = boundary_context.build_artifact(
                    tactical=tactical_classifier, current_descriptive=desc,
                    technical_structure=technical_structure, requested_at=requested_at,
                )
            except Exception:
                tactical_boundaries = None
        # Also retained under its own canonical per-session path (not just consumed here) so
        # downstream consumers -- the daily_integrated_decision_brief CLI-level builder in
        # particular, which needs BOS/CHoCH per watchlist ticker -- can load the same compact V3
        # projection without rebuilding it from raw technical_structure_context.
        _write_json(paths["market_structure_breakout_v3_projection"], tactical_projection)
        _write_json(paths["tactical_momentum_context"], momentum)
        _write_json(paths["tactical_confirmation_context"], confirmation)
        if tactical_boundaries is not None:
            _write_json(paths["tactical_confirmation_invalidation_boundaries"], tactical_boundaries)
        # Financial V2 previously had NO canonical daily-materialization path anywhere in this
        # pipeline: the prior wiring here loaded the legacy, structurally incompatible
        # market_wide_current_fundamental_research/v1 artifact (523-record shape;
        # evaluate_fundamental_direction() needs the flat financial_analysis_product_integration/v1
        # compact shape instead), which made fundamental_state INSUFFICIENT for every ticker every
        # session. Build the current Financial V2 engine + compact product fresh from the pinned
        # financial_v2_current_input_authority evidence chain, over the SAME daily denominator as
        # relative volume above -- every ticker gets an explicit AVAILABLE or ABSENT compact record,
        # never a silent drop. The raw per-session valuation artifact is likewise not itself the
        # shape evaluate_valuation_context() needs (methods/peer_relative_context); it must first
        # pass through current_research_valuation_context.evaluate_ticker_valuation()/attach_peer_
        # relative(), joined against this same engine artifact's TTM features -- mirroring
        # tools/run_integrated_investment_decision_replay.py's own proven wiring, the one place both
        # correct shapes are established end to end.
        fin_authority = fin_v2_authority.resolve(root)
        engine_artifact = fin_v2_material.build_engine_artifact(root=root, requested_at=requested_at, authority=fin_authority)
        financial_session_artifact = fin_v2_material.build_session_artifact(
            root=root, decision_session=session, product_tickers=daily_denominator,
            requested_at=requested_at, authority=fin_authority, engine_artifact=engine_artifact,
        )
        readiness_context = (
            fin_v2_material.build_calculation_readiness_context(
                runtime_root=runtime_root, decision_session=session, raw_valuation_artifact=raw_val,
                product_tickers=daily_denominator, requested_at=requested_at,
            ) if runtime_root is not None else None
        )
        evaluated_valuation = fin_v2_material.build_evaluated_valuation_artifact(
            engine_artifact=engine_artifact, raw_valuation_artifact=raw_val,
            product_tickers=daily_denominator, requested_at=requested_at,
            calculation_readiness_context=readiness_context,
        )
        _write_json(paths["financial_analysis_product"], financial_session_artifact)
        _write_json(paths["current_valuation_evaluated"], evaluated_valuation)
        # Corporate Intelligence axis (CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_
        # INTEGRATION_V1). Built independently, with its own local try/except -- exactly the
        # tactical_boundaries pattern above -- so a corporate-evidence failure never cascades
        # into failing the whole Integrated Decision build. official_event_context has been
        # frozen at research_session=2026-08-21 since before this milestone (verified: no
        # fresher retained official ex-date evidence exists), so this is built AS OF THAT
        # evidence's own session, not today's `session` -- current_corporate_event_context.
        # build_artifact() fails closed on a session mismatch, and staleness is surfaced
        # explicitly by evaluate_corporate_intelligence_context() below rather than papered
        # over by silently re-labelling old evidence as current.
        corporate_intelligence_artifact = None
        try:
            from current_corporate_intelligence_axis import build_artifact as build_corporate_intelligence_axis
            official_universe_ci = _load(retained_paths["official_universe"])
            official_event_context_ci = _load(retained_paths["official_event_context"])
            market_wide_ci = _load(retained_paths["corporate_intelligence"])
            if official_universe_ci and official_event_context_ci:
                corporate_intelligence_artifact = build_corporate_intelligence_axis(
                    official_universe=official_universe_ci,
                    official_event_context=official_event_context_ci,
                    root=root,
                    research_session=official_event_context_ci.get("research_session"),
                    market_wide_current_corporate_intelligence=market_wide_ci,
                )
        except Exception:
            corporate_intelligence_artifact = None
        if corporate_intelligence_artifact is not None:
            _write_json(paths["corporate_intelligence_axis"], corporate_intelligence_artifact)
        res = build(
            session=session,
            requested_at=requested_at,
            technical_structure_artifact=tactical_projection,
            financial_analysis_artifact=financial_session_artifact["financial_analysis_product"],
            current_valuation_artifact=evaluated_valuation,
            relative_volume_artifact=relative_volume,
            market_sector_artifact=mkt,
            legacy_decision_artifact=opp,
            priority_queue_artifact=priority_queue_artifact,
            momentum_artifact=momentum,
            tactical_confirmation_artifact=confirmation,
            tactical_boundaries_artifact=tactical_boundaries,
            corporate_intelligence_artifact=corporate_intelligence_artifact,
        )
        if res.get("session") != session:
            raise CanonicalPostCloseError(f"INTEGRATED_DECISION_SESSION_MISMATCH:expected={session}:observed={res.get('session')}")
        _write_json(paths["integrated_investment_decision_product"], res)
        return res

    _attempt("financial_momentum", "financial_momentum", _financial_momentum)
    _attempt("corporate_event_context", "corporate_event_context", _corporate_event_context)
    _attempt("historical_context", "historical_context", _historical_context)
    _attempt("integrated_investment_decision_product", "integrated_investment_decision_product", _integrated_investment_decision_product)
    return results


def retain_prospective_decision_snapshot(
    root: Path, session: str, *, producer_result: Mapping[str, Any],
    enrichment: Mapping[str, Any], exact_session_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Seal the current Integrated Decision at T0 before its handoff is written.

    A content-addressed path makes an identical warm rerun idempotent and a
    genuinely changed decision a distinct snapshot; no session-shaped working
    artifact can silently rewrite the original T0 decision.
    """
    from prospective_decision_retention import build_snapshot, write_immutable_snapshot

    integrated = (enrichment.get("integrated_investment_decision_product") or {}).get("artifact")
    operation = producer_result.get("operation") or {}
    operation_identity = (operation.get("manifest") or {}).get("operation_identity")
    if not isinstance(integrated, Mapping):
        # Daily Producer is already complete.  Like downstream outcome
        # feedback, retention instrumentation must surface its own failure
        # without revising or blocking today's governed decision.
        return {"status": "UNAVAILABLE", "reason": "INTEGRATED_DECISION_ARTIFACT_UNAVAILABLE"}
    try:
        snapshot = build_snapshot(
            session=session, operation_identity=operation_identity,
            producer_run_identity=producer_result.get("run_identity"), integrated_artifact=integrated,
            exact_session_snapshot=exact_session_snapshot,
        )
        path = write_immutable_snapshot(root, snapshot)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": f"PROSPECTIVE_SNAPSHOT_RETENTION_FAILED:{type(exc).__name__}:{exc}"}
    return {"status": "RETAINED", "artifact": snapshot, "path": path}


def register_session_inputs(
    root: Path, session: str, *, registry_path: Path | None = None, artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Write config/daily_research_session_input_registry.json's sessions[session] entry.

    No such writer existed in the repository before this pipeline (confirmed by exhaustive
    search); registration was previously always a manual JSON edit. This function reproduces
    the exact shape of the three existing hand-written entries and refuses (never overwrites) a
    conflicting already-frozen completed_sessions[session] lock, matching
    daily_research_session_operations.assert_completed_session_inputs_locked semantics.

    `artifact_root` (defaulting to `root`) supplies session-specific outputs while immutable
    retained inputs stay under `root` (see build_enrichment_components). Recorded registry paths
    are always computed relative to the real `root`, so
    daily_research_session_operations.resolve_inputs() resolves them correctly regardless of how
    deep the selected attempt directory is nested.
    """
    artifact_root = artifact_root or root
    path = registry_path or root / "config" / "daily_research_session_input_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    paths = level2.session_artifact_paths(artifact_root, session)
    retained_paths = level2.session_artifact_paths(root, session)
    selection: dict[str, dict[str, str]] = {}
    for registry_key, level2_key in REGISTRY_KEY_TO_LEVEL2_KEY.items():
        artifact_path = retained_paths[level2_key] if level2_key in RETAINED_LEVEL2_INPUT_KEYS else paths[level2_key]
        artifact = _load(artifact_path)
        if artifact is None or not isinstance(artifact.get("artifact_identity"), str):
            if registry_key in REQUIRED_REGISTRY_KEYS:
                raise CanonicalPostCloseError(
                    f"REFUSE_CANONICAL_POST_CLOSE:REQUIRED_REGISTRY_INPUT_UNAVAILABLE:{registry_key}"
                )
            continue
        selection[registry_key] = {
            "path": _rel(root, artifact_path),
            "artifact_identity": artifact["artifact_identity"],
        }
    completed = (registry.get("completed_sessions") or {}).get(session)
    if isinstance(completed, Mapping) and completed.get("status") == "COMPLETED_RETAINED_EVIDENCE":
        lock = completed.get("frozen_input_identities") or {}
        if selection_identities(selection) != {k: v for k, v in lock.items()}:
            raise CanonicalPostCloseError("COMPLETED_SESSION_INPUT_MUTATION_REJECTED:" + session)
        return {"status": "ALREADY_FROZEN_IDENTICAL", "session": session, "selection": selection}
    existing = (registry.get("sessions") or {}).get(session)
    if existing == selection:
        return {"status": "ALREADY_REGISTERED_IDENTICAL", "session": session, "selection": selection}
    registry.setdefault("sessions", {})[session] = selection
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return {"status": "REGISTERED", "session": session, "selection": selection}


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def validate_and_freeze_completed_session(
    root: Path, session: str, *, registry_path: Path | None = None,
) -> dict[str, Any]:
    """Prove real input coherence (descriptive/screening/tactical/triage session agreement,
    lineage chaining, technical coverage parity -- the same checks Daily Producer itself runs)
    and only then freeze completed_sessions[session]. This is the evidence basis for
    COMPLETED_RETAINED_EVIDENCE; it is never inferred from wall-clock time alone -- the acquisition
    stage's own coverage-ratio and resolved-session checks already ran before this is reached.
    """
    path = registry_path or root / "config" / "daily_research_session_input_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    already = (registry.get("completed_sessions") or {}).get(session)
    if isinstance(already, Mapping) and already.get("status") == "COMPLETED_RETAINED_EVIDENCE":
        return {"status": "ALREADY_COMPLETED", "session": session}
    inputs, entries = resolve_inputs(root, session, registry)
    coherence = validate_coherence(inputs, session)
    required_inputs = sorted(name for name in entries if name in REQUIRED_REGISTRY_KEYS)
    frozen_identities = {name: entries[name]["artifact_identity"] for name in entries}
    registry.setdefault("completed_sessions", {})[session] = {
        "status": "COMPLETED_RETAINED_EVIDENCE",
        "trading_day_valid": True,
        "completion_evidence": {
            "basis": "EXACT_SESSION_UPSTREAM_ARTIFACT_REGISTRY",
            "required_current_session_inputs": required_inputs,
            "policy": "The registry is a governed completed-session ledger. It does not infer completion from civil time, weekday, or a latest file.",
            "canonical_post_close_pipeline_evidence": {
                "contract_version": CONTRACT_VERSION,
                "session_coherence": coherence,
            },
        },
        "frozen_input_identities": frozen_identities,
    }
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return {"status": "FROZEN", "session": session, "coherence": coherence, "frozen_input_identities": frozen_identities}


def build_decision_packet(
    root: Path, session: str, *,
    opportunity: Mapping[str, Any] | None = None, enrichment: Mapping[str, Any] | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any] | None:
    """Build current_research_decision_packet/v1 for this session, degrading gracefully.

    opportunity comes from the just-completed Daily Producer operation in-memory when available
    (daily_producer_pipeline.run_daily_producer()'s returned operation["opportunity"]); falling
    back to the materialized artifact on disk keeps this function independently callable/testable.
    financial_momentum/corporate_event/historical are read from the in-memory enrichment result
    (build_enrichment_components' return value) so a freshly session-scoped build is preferred
    over Level-2's shared prior-as-of file without this function needing to know the difference.

    `artifact_root` (defaulting to `root`) governs both where the Level-2 inputs are read from
    and where the packet itself is written, so a fresh-attempt run never writes its packet over
    Level-2's shared static per-session decision-packet path if a different attempt already has.
    """
    from current_research_decision_packet import build_artifact

    artifact_root = artifact_root or root
    paths = level2.session_artifact_paths(artifact_root, session)
    opportunity = opportunity if opportunity is not None else _load(paths["opportunity_prioritization"])
    if not opportunity:
        return None
    enrichment = enrichment or {}

    def _enriched(name: str, level2_key: str) -> Any:
        row = enrichment.get(name)
        if isinstance(row, Mapping) and row.get("artifact") is not None:
            return row["artifact"]
        return _load(paths[level2_key])

    packet = build_artifact(
        opportunity=opportunity,
        scenario=_load(paths["scenario"]),
        risk_register=_load(paths["risk_register"]),
        market_sector=_load(paths["sector_leadership"]),
        financial_momentum=_enriched("financial_momentum", "financial_momentum"),
        corporate_event=_enriched("corporate_event_context", "corporate_event_context"),
        valuation=_load(paths["valuation"]),
        historical=_enriched("historical_context", "historical_context"),
    )
    _write_json(paths["decision_packet"], packet)
    return packet


def run_prospective_collection(
    root: Path, session: str, *, artifact_root: Path | None = None,
) -> dict[str, Any] | None:
    """Post-hoc, non-blocking: a failure here never revises the completed Daily Producer result.

    `artifact_root` (defaulting to `root`) locates the decision packet build_decision_packet just
    wrote for THIS run; prospective collection's own output always stays under `root`
    (unaffected by any fresh-attempt redirect -- that namespace is not session-templated per
    attempt and was never touched by an earlier pre-cutoff run).
    """
    artifact_root = artifact_root or root
    paths = level2.session_artifact_paths(artifact_root, session)
    packet_path = paths["decision_packet"]
    cmd = [sys.executable, "tools/run_prospective_research_cohort_collection.py", "--session", session]
    if packet_path.is_file():
        cmd += ["--decision-packet-path", str(packet_path)]
    result = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    if result.returncode != 0:
        return {"status": "UNAVAILABLE", "reason": (result.stderr or result.stdout).strip()[-2000:]}
    output = root / "operations-review" / "prospective-research-cohort-collection-v1" / f"prospective_research_cohort_snapshot_{session}.json"
    snapshot = _load(output)
    # The same bounded post-close hook rolls forward already-retained integrated
    # decisions.  It scans only canonical handoffs from *earlier* sessions (the
    # current handoff has not been written yet), so it cannot feed current or
    # future outcome data back into today's decision.  A diagnostic failure is
    # deliberately localized just like the existing prospective cohort step.
    feedback_output = (
        root / "operations-review" / "prospective-decision-outcome-feedback-v1" / session
        / "prospective_decision_feedback_artifact.json"
    )
    feedback_cmd = [
        sys.executable, "tools/run_prospective_decision_outcome_feedback.py",
        "--root", str(root), "--output", str(feedback_output),
    ]
    feedback_result = subprocess.run(feedback_cmd, cwd=str(root), capture_output=True, text=True)
    feedback = (
        {"status": "COLLECTED", "path": str(feedback_output), "artifact": _load(feedback_output)}
        if feedback_result.returncode == 0
        else {"status": "UNAVAILABLE", "reason": (feedback_result.stderr or feedback_result.stdout).strip()[-2000:]}
    )
    return {"status": "COLLECTED", "stdout": result.stdout, "snapshot": snapshot, "path": str(output), "decision_feedback": feedback}


def build_tiered_bundle(
    root: Path, session: str, *,
    acquisition: Mapping[str, Any], producer_result: Mapping[str, Any],
    decision_packet: Mapping[str, Any] | None, prospective: Mapping[str, Any] | None,
    enrichment: Mapping[str, Any], producer_head: str | None, consumer_head: str | None,
    prospective_snapshot: Mapping[str, Any] | None = None,
    artifact_root: Path | None = None, runtime_release: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_root = artifact_root or root
    level2_paths = level2.session_artifact_paths(artifact_root, session)
    bundle_dir = root / "operations-review" / "canonical-post-close-v1" / session
    manifest = producer_result["manifest"]
    operation = producer_result["operation"]
    product = operation["product"]
    triage = _load(level2_paths["session_triage"])
    tactical = _load(level2_paths["tactical_classifier"])
    breadth = (product.get("market_brief") or {}).get("coverage") or {}
    descriptive = _load(level2_paths["descriptive_research"]) or {}
    market_breadth = descriptive.get("market_breadth") or {}
    tactical_counts = (tactical or {}).get("coverage", {}).get("entry_state_counts") or {}

    shared_lineage = {
        "session": session,
        "producer_head": producer_head,
        "consumer_head": consumer_head,
        "schema_version": "1.0.0",
        "canonical_post_close_contract_version": CONTRACT_VERSION,
        "daily_producer_run_identity": producer_result["run_identity"],
        "daily_session_operation_identity": operation["manifest"]["operation_identity"],
        "upstream_evidence_identities": manifest["upstream_artifact_identities"],
    }

    tier1 = {
        **shared_lineage,
        "tier": "SESSION_AI_HANDOFF_BUNDLE",
        "market_session_proof": {
            "resolved_completed_session": acquisition["resolved_completed_session"],
            "exact_session_coverage": acquisition["coverage"],
            "provider": "MULTI_SOURCE",
            "provider_contribution_counts": _provider_contribution_counts(acquisition.get("snapshot") or {}),
            "dnse_provider_health_state": (acquisition.get("snapshot") or {}).get("dnse_provider_health_state"),
            "degraded_provider_recovery": (acquisition.get("snapshot") or {}).get("degraded_provider_recovery"),
        },
        "market_coverage": breadth,
        "breadth": {
            "advancing": market_breadth.get("advancing"),
            "declining": market_breadth.get("declining"),
            "unchanged": market_breadth.get("unchanged"),
            "breadth_descriptor": (market_breadth.get("breadth_descriptor") or {}).get("descriptor"),
            "momentum_descriptor": (market_breadth.get("momentum_descriptor") or {}).get("descriptor"),
        },
        "tactical_counts": {state: tactical_counts.get(state) for state in
                             ("BASE_BUILDING", "BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE", "UPTREND_CONFIRMED")},
        "entry_relevant_count": (triage or {}).get("entry_relevant_count"),
        "high_priority_review_count": product.get("high_priority_full_universe_review_set", {}).get("count"),
        "blocked_dimensions": manifest["blocked_dimensions"],
        "warnings": manifest["warnings"],
        "daily_producer": {
            "operation_identity": operation["manifest"]["operation_identity"],
            "run_identity": producer_result["run_identity"],
            "status": producer_result["status"],
        },
        "current_research_packet_identity": (decision_packet or {}).get("artifact_identity"),
        "integrated_investment_decision_product_identity": (
            (enrichment.get("integrated_investment_decision_product") or {}).get("artifact") or {}
        ).get("artifact_identity"),
        "prospective_decision_snapshot": {
            "status": (prospective_snapshot or {}).get("status", "UNAVAILABLE"),
            "reason": (prospective_snapshot or {}).get("reason"),
            "identity": ((prospective_snapshot or {}).get("artifact") or {}).get("snapshot_identity"),
            "path": _rel(root, (prospective_snapshot or {}).get("path")) if (prospective_snapshot or {}).get("path") else None,
            "source_integrated_decision_artifact_identity": (((prospective_snapshot or {}).get("artifact") or {}).get("source_integrated_decision_artifact") or {}).get("artifact_identity"),
            "authority_boundary": "IMMUTABLE_T0_SNAPSHOT_NOT_A_CURRENT_DECISION_INPUT",
        },
        "prospective_cohort_snapshot_identity": ((prospective or {}).get("snapshot") or {}).get("snapshot_id"),
        "prospective_decision_feedback_identity": (((prospective or {}).get("decision_feedback") or {}).get("artifact") or {}).get("artifact_identity"),
        "enrichment_component_status": {name: row["status"] for name, row in enrichment.items()},
        "deeper_bundles": {
            "opportunity_research_bundle": _rel(root, bundle_dir / "opportunity_research_bundle.json"),
            "full_universe_bundle_index": _rel(root, bundle_dir / "full_universe_bundle_index.json"),
            "dashboard_release_set_index": _rel(root, bundle_dir / "dashboard_release_set_index.json"),
            "integrated_investment_decision_product": _rel(root, level2_paths["integrated_investment_decision_product"]),
            "prospective_decision_feedback": ((prospective or {}).get("decision_feedback") or {}).get("path"),
            "prospective_decision_snapshot": _rel(root, (prospective_snapshot or {}).get("path")) if (prospective_snapshot or {}).get("path") else None,
        },
        "primary_ai_input": _rel(root, producer_result["run_dir"] / "ai_research_session_bundle.json"),
        "recommended_ai_inputs": {
            "normal_human_review": _rel(root, producer_result["run_dir"] / "ai_research_session_bundle.json"),
            "arbitrary_ticker_lookup": _rel(root, producer_result["run_dir"] / "ai_research_full_universe.ndjson"),
        },
        "authority_boundary": manifest["authority_boundary"],
    }

    decision_queue = _load(level2_paths["opportunity_prioritization"])
    tier2 = {
        **shared_lineage,
        "tier": "OPPORTUNITY_RESEARCH_BUNDLE",
        "current_research_decision_packet_identity": (decision_packet or {}).get("artifact_identity"),
        "current_research_decision_packet_path": _rel(root, level2_paths["decision_packet"]) if decision_packet else None,
        "opportunity_prioritization_identity": (decision_queue or {}).get("artifact_identity"),
        "entry_relevant_states": ("BASE_BUILDING", "BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE"),
        "cohort_tickers_by_state": {
            state: sorted(t for t, row in ((tactical or {}).get("records") or {}).items() if row.get("entry_state") == state)
            for state in ("BASE_BUILDING", "BREAKOUT_READY", "EARLY_REVERSAL_CANDIDATE")
        },
        "prospective_cohort_snapshot": {
            "identity": ((prospective or {}).get("snapshot") or {}).get("snapshot_id"),
            "path": (prospective or {}).get("path"),
        },
        "prospective_decision_feedback": {
            "identity": (((prospective or {}).get("decision_feedback") or {}).get("artifact") or {}).get("artifact_identity"),
            "path": ((prospective or {}).get("decision_feedback") or {}).get("path"),
            "authority_boundary": "DOWNSTREAM_OBSERVATION_ONLY_NOT_A_CURRENT_DECISION_INPUT",
        },
        "prospective_decision_snapshot": tier1["prospective_decision_snapshot"],
        "authority_boundary": {"no_probability_target_expected_return_or_sizing": True, "is_actionable": False},
    }

    tier3 = {
        **shared_lineage,
        "tier": "FULL_UNIVERSE_BUNDLE_INDEX",
        "format": "NDJSON",
        "role": "FULL_UNIVERSE_LOOKUP_ONLY",
        "not_primary_human_review_input": True,
        "full_universe_path": _rel(root, producer_result["run_dir"] / "ai_research_full_universe.ndjson"),
        "manifest_path": _rel(root, producer_result["run_dir"] / "ai_research_bundle_manifest.json"),
        "queryable_by": ["ticker", "exact session"],
        "ordering": "TICKER_ASCENDING_DETERMINISTIC_LOOKUP_NOT_SAMPLING",
        "note": "FULL_UNIVERSE_LOOKUP_ONLY / NOT_PRIMARY_HUMAN_REVIEW_INPUT. Do not upload as the normal human-review AI input. Use ai_research_session_bundle.json for normal review, or the deterministic ticker extractor for bounded lookup.",
    }

    tier4 = {
        **shared_lineage,
        "tier": "DASHBOARD_RELEASE_SET_INDEX",
        "dashboard_projection_path": _rel(root, producer_result["run_dir"] / "dashboard" / "current_decision_cockpit_projection.json"),
        "dashboard_projection_identity": manifest["dashboard_projection"]["identity"],
        "run_manifest_path": _rel(root, producer_result["run_dir"] / "run_manifest.json"),
        "runtime_release": dict(runtime_release or {}),
        "ready_for_governed_publication": bool((runtime_release or {}).get("ready")),
        "publication_authority": "release_orchestrator.py (existing; not invoked by this pipeline)",
        "note": "This is an index over already-materialized Daily Producer output. Governed publication is ready only when the publisher input runtime root independently validates for this exact session.",
    }

    _write_json(bundle_dir / "session_handoff_bundle.json", tier1)
    _write_json(bundle_dir / "opportunity_research_bundle.json", tier2)
    _write_json(bundle_dir / "full_universe_bundle_index.json", tier3)
    _write_json(bundle_dir / "dashboard_release_set_index.json", tier4)
    return {"session_handoff_bundle": tier1, "opportunity_research_bundle": tier2,
            "full_universe_bundle_index": tier3, "dashboard_release_set_index": tier4, "bundle_dir": bundle_dir}


def run_canonical_post_close(
    root: Path, runtime_root: Path, session: str, *, workers: int = 12, now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(session, str) or not session.strip():
        raise CanonicalPostCloseError("REFUSE_CANONICAL_POST_CLOSE:EXPLICIT_SESSION_REQUIRED")
    now = now or vn_now()
    acquisition = acquire_and_materialize(root, session, runtime_root, workers=workers, now=now)
    artifact_root = acquisition["artifact_root"]
    register_session_inputs(root, session, artifact_root=artifact_root)
    validate_and_freeze_completed_session(root, session)
    producer_head, consumer_head = _git_head(root), _git_head(root.parent / "ai-core-private")
    try:
        producer_result = run_daily_producer(
            root, session=session, latest_completed_session=False,
            producer_head=producer_head or "UNKNOWN", consumer_head=consumer_head or "UNKNOWN",
            now=now,
        )
    except DailyProducerError as exc:
        raise CanonicalPostCloseError("REFUSE_CANONICAL_POST_CLOSE:DAILY_PRODUCER_INTEGRITY_FAILURE:" + str(exc)) from exc
    try:
        materialize_canonical_runtime_release(root, runtime_root, session)
    except CanonicalRuntimeReleaseError as exc:
        raise CanonicalPostCloseError(
            "REFUSE_CANONICAL_POST_CLOSE:CANONICAL_RUNTIME_RELEASE_INTEGRITY_FAILURE:" + str(exc)
        ) from exc
    enrichment = build_enrichment_components(
        root, session, artifact_root=artifact_root, runtime_root=runtime_root,
        priority_queue_artifact=producer_result["operation"].get("decision_queue"),
    )
    prospective_snapshot = retain_prospective_decision_snapshot(
        root, session, producer_result=producer_result, enrichment=enrichment,
        exact_session_snapshot=acquisition.get("snapshot"),
    )
    decision_packet = build_decision_packet(
        root, session, opportunity=producer_result["operation"].get("opportunity"), enrichment=enrichment,
        artifact_root=artifact_root,
    )
    prospective = run_prospective_collection(root, session, artifact_root=artifact_root)
    runtime_release = evaluate_dashboard_runtime_readiness(runtime_root, session)
    tiers = build_tiered_bundle(
        root, session, acquisition=acquisition, producer_result=producer_result,
        decision_packet=decision_packet, prospective=prospective, enrichment=enrichment,
        producer_head=producer_head, consumer_head=consumer_head, prospective_snapshot=prospective_snapshot,
        artifact_root=artifact_root,
        runtime_release=runtime_release,
    )
    return {
        "session": session, "acquisition": acquisition, "enrichment": enrichment,
        "producer_result": producer_result, "decision_packet": decision_packet,
        "prospective": prospective, "prospective_snapshot": prospective_snapshot,
        "runtime_release": runtime_release, "tiers": tiers,
        "producer_head": producer_head, "consumer_head": consumer_head,
    }


def print_terminal_handoff(result: Mapping[str, Any]) -> None:
    tier1 = result["tiers"]["session_handoff_bundle"]
    producer_result = result["producer_result"]
    print(f"SESSION: {result['session']}")
    print(f"STATUS: {producer_result['status']}")
    print(f"MARKET_SESSION_PROOF: {json.dumps(tier1['market_session_proof'], sort_keys=True)}")
    print(f"MARKET_COVERAGE: {json.dumps(tier1['market_coverage'], sort_keys=True)}")
    print(f"BREADTH: {json.dumps(tier1['breadth'], sort_keys=True)}")
    print(f"TACTICAL_COUNTS: {json.dumps(tier1['tactical_counts'], sort_keys=True)}")
    print(f"HIGH_PRIORITY_REVIEW_COUNT: {tier1['high_priority_review_count']}")
    print(f"AI_PRIMARY_BUNDLE: {tier1.get('primary_ai_input') or (tier1.get('recommended_ai_inputs') or {}).get('normal_human_review')}")
    print(f"AI_FULL_UNIVERSE_LOOKUP_ONLY: {(tier1.get('recommended_ai_inputs') or {}).get('arbitrary_ticker_lookup') or result['tiers']['full_universe_bundle_index'].get('full_universe_path')}")
    print("DO_NOT_USE_AS_PRIMARY: ai_research_full_universe.ndjson")
    print(f"SESSION_HANDOFF_BUNDLE: {_rel(ROOT, result['tiers']['bundle_dir'] / 'session_handoff_bundle.json')}")
    print(f"DAILY_PRODUCER_OPERATION_ID: {tier1['daily_producer']['operation_identity']}")
    print(f"DAILY_PRODUCER_RUN_ID: {tier1['daily_producer']['run_identity']}")
    print(f"CURRENT_RESEARCH_PACKET_ID: {tier1['current_research_packet_identity']}")
    print(f"PROSPECTIVE_COHORT_SNAPSHOT_ID: {tier1['prospective_cohort_snapshot_identity']}")
    print(f"BLOCKED_DIMENSIONS: {tier1['blocked_dimensions']}")
    print(f"WARNINGS: {tier1['warnings']}")
    runtime_release = result.get("runtime_release") or result["tiers"]["dashboard_release_set_index"].get("runtime_release") or {}
    print(f"DASHBOARD_RUNTIME_READY: {'YES' if runtime_release.get('ready') else 'NO'}")
    print(f"DASHBOARD_RUNTIME_SESSION: {runtime_release.get('resolved_session') or 'UNRESOLVED'}")
    if runtime_release.get("reason"):
        print(f"DASHBOARD_RUNTIME_REASON: {runtime_release['reason']}")
    print("PUBLICATION_REQUIRED_SEPARATELY: YES")
    print(f"READY_FOR_GOVERNED_PUBLICATION: {'YES' if result['tiers']['dashboard_release_set_index']['ready_for_governed_publication'] else 'NO'}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Canonical one-command post-close pipeline.")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--session", required=True, help="Explicit completed market session YYYY-MM-DD.")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args(argv)
    try:
        result = run_canonical_post_close(ROOT, Path(args.runtime_root), args.session, workers=args.workers)
    except CanonicalPostCloseError as exc:
        print(f"STATUS: {exc}")
        return 2
    print_terminal_handoff(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
