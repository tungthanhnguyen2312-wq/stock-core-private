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
import hashlib
import json
import os
import subprocess
import tempfile
from owner_daily_progress import run_observed_subprocess
import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

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

# CURRENT_FOREIGN_FLOW_DAILY_ACTIVATION_V1: zero-flag Owner Daily enables the already-
# productionized DNSE current-foreign-flow path for the exact qualified session. The shared
# helper default below stays False so the diagnostic CLI remains explicit-opt-in.
NORMAL_DAILY_ENABLE_CURRENT_FOREIGN_FLOW_LIVE = True
# Ordinary Daily binds/plans same-session official HOSE liquidity before Integrated
# Decision. Diagnostic CLI stays opt-in. A failed refresh never fails Core Daily.
NORMAL_DAILY_ENABLE_OFFICIAL_LIQUIDITY_ROLLFORWARD = True

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

# Optional current-source observations advance in a separate knowledge overlay.
# Completed market-session selections, including optional entries, stay frozen.

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


class SupplementalProviderBlockError(CanonicalPostCloseError):
    """PROVIDER_RUNTIME_ISOLATION_V1 governed block surfaced from acquisition: the supplemental
    provider runtime was unavailable, or it ran and the DNSE quality license does not qualify for
    ordinary Daily. DNSE evidence is retained; nothing downstream is materialized or published.
    Carries ``kind``, ``runtime_state``, ``quality_license`` and ``diagnostic_path``."""

    def __init__(self, message: str, *, kind: str, runtime_state: Mapping[str, Any],
                 quality_license: Mapping[str, Any] | None, diagnostic_path: Path | None):
        super().__init__(message)
        self.kind = kind
        self.runtime_state = dict(runtime_state)
        self.quality_license = dict(quality_license) if quality_license else None
        self.diagnostic_path = diagnostic_path


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


@dataclass(frozen=True)
class _IIDWriteReceipt:
    path: Path
    session: str
    contract_version: str
    artifact_identity: str
    artifact_sha256: str
    size: int
    mtime_ns: int
    serialized_sha256: str


class _ReceiptWriter:
    """Hash exactly the UTF-8 chunks already sent to the canonical JSON writer."""
    def __init__(self, handle):
        self.handle = handle
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, text: str) -> int:
        data = text.encode("utf-8")
        if self.handle.write(data) != len(data):
            raise OSError("INTEGRATED_DECISION_CANONICAL_SHORT_WRITE")
        self.digest.update(data)
        self.size += len(data)
        return len(text)


def _write_json(path: Path, value: Mapping[str, Any], *, capture_iid_receipt: bool = False) -> _IIDWriteReceipt | None:
    """Atomic, streaming write, byte-identical to ``json.dumps(..., indent=2, sort_keys=True)``.

    ``write_text(json.dumps(...))`` truncated the destination before encoding a multi-gigabyte
    string, so a failure left a 0-byte retained file (2026-10-02 live Daily). A sibling temp file
    replaced into place keeps any prior complete file intact on failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("wb" if capture_iid_receipt else "w",
                       **({} if capture_iid_receipt else {"encoding": "utf-8", "newline": ""})) as handle:
            writer = _ReceiptWriter(handle) if capture_iid_receipt else handle
            json.dump(value, writer, ensure_ascii=False, indent=2, sort_keys=True)
            writer.write("\n")
            if capture_iid_receipt:
                handle.flush()
                os.fsync(handle.fileno())
        temp.replace(path)
        if capture_iid_receipt:
            stat = path.stat()
            if stat.st_size != writer.size:
                raise CanonicalPostCloseError("INTEGRATED_DECISION_CANONICAL_WRITE_SIZE_MISMATCH")
            return _IIDWriteReceipt(path.resolve(), value.get("session"), value.get("contract_version"),
                                    value.get("artifact_identity"), value.get("artifact_sha256"),
                                    writer.size, stat.st_mtime_ns, writer.digest.hexdigest())
    finally:
        temp.unlink(missing_ok=True)


def _copy_iid_working_view(source: Path, destination: Path, *, session: str,
                           artifact: Mapping[str, Any], receipt: _IIDWriteReceipt | None) -> None:
    """Promote only the exact bytes emitted by this successful current IID build."""
    contract = "integrated_investment_decision_product/v1"
    identity = artifact.get("artifact_identity")
    digest = artifact.get("artifact_sha256")
    if (receipt is None or receipt.path != source.resolve() or receipt.session != session
            or artifact.get("session") != session or receipt.contract_version != contract
            or artifact.get("contract_version") != contract or not isinstance(digest, str) or not digest
            or identity != contract + ":" + digest or receipt.artifact_identity != identity
            or receipt.artifact_sha256 != digest):
        raise CanonicalPostCloseError("INTEGRATED_DECISION_CANONICAL_WRITE_RECEIPT_MISMATCH")
    before = source.stat()
    if receipt.size <= 0 or (before.st_size, before.st_mtime_ns) != (receipt.size, receipt.mtime_ns):
        raise CanonicalPostCloseError("INTEGRATED_DECISION_CANONICAL_SOURCE_CHANGED_OR_EMPTY")
    if source.resolve() == destination.resolve():
        raise CanonicalPostCloseError("INTEGRATED_DECISION_WORKING_VIEW_EQUALS_CANONICAL_SOURCE")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        copied = 0
        serialized_digest = hashlib.sha256()
        with source.open("rb") as incoming, tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=".iid-copy-", suffix=".tmp", delete=False) as outgoing:
            temporary = Path(outgoing.name)
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                if outgoing.write(block) != len(block):
                    raise OSError("INTEGRATED_DECISION_WORKING_VIEW_SHORT_WRITE")
                serialized_digest.update(block)
                copied += len(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        after = source.stat()
        if (copied != receipt.size or serialized_digest.hexdigest() != receipt.serialized_sha256
                or (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns)):
            raise CanonicalPostCloseError("INTEGRATED_DECISION_CANONICAL_SOURCE_BYTES_MISMATCH")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    artifact_root: Path | None = None, historical_compatibility: bool = False,
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
    # 0. a RECOVERY_REPLAY artifact (tools/run_recovery_replay.py) is never ordinary post-close
    # evidence, even if it was copied next to ordinary artifacts.
    if level2.is_recovery_replay_artifact(snapshot):
        raise PreCutoffArtifactError("EXISTING_ARTIFACT_IS_RECOVERY_REPLAY_NOT_ORDINARY_DAILY:" + session)
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
    # 2026-09-26: the same shared policy as the Level-2 reuse gate
    # (level2.core_daily_reuse_refusal) -- Core-Daily proceed predicate re-derived from retained
    # evidence, D2 unchanged, companion evidence mandatory for post-corrective snapshots, and a
    # DNSE-primary snapshot is re-evaluated once the supplemental runtime is launchable.
    if artifact_root is not None:
        evidence_path = level2.session_artifact_paths(artifact_root, session)["multi_source_market_evidence"]
        evidence_present = evidence_path.is_file()
        evidence: Any = None
        if evidence_present:
            try:
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                evidence = None
        recovery = snapshot.get("degraded_provider_recovery")
        marker = recovery.get("mode") if isinstance(recovery, Mapping) else None
        refusal = level2.core_daily_reuse_refusal(
            snapshot, evidence, session, evidence_present=evidence_present, degraded_recovery_mode=marker,
            historical_compatibility=historical_compatibility,
        )
        if refusal == "COMPANION_EVIDENCE_UNREADABLE":
            raise PreCutoffArtifactError(f"EXISTING_ARTIFACT_DNSE_QUALITY_EVIDENCE_UNREADABLE:session={session}")
        if refusal == "COMPANION_EVIDENCE_SESSION_MISMATCH":
            raise PreCutoffArtifactError(f"EXISTING_ARTIFACT_DNSE_QUALITY_EVIDENCE_SESSION_MISMATCH:session={session}")
        if refusal == "COMPANION_EVIDENCE_MISSING":
            raise PreCutoffArtifactError(f"EXISTING_ARTIFACT_DNSE_QUALITY_EVIDENCE_MISSING:session={session}")
        if refusal is not None:
            raise PreCutoffArtifactError(
                f"EXISTING_ARTIFACT_DNSE_PROVIDER_HEALTH_GATE_NOT_SATISFIED:session={session}:{refusal}"
            )
    elif not (historical_compatibility and not level2.requires_companion_evidence(snapshot)):
        # 2026-09-26 PR8 corrective: without an artifact root the companion evidence cannot be
        # checked, which never means "trusted" on the ordinary path.
        raise PreCutoffArtifactError(f"EXISTING_ARTIFACT_DNSE_QUALITY_EVIDENCE_NOT_CHECKED:session={session}")


def resolve_acquisition_root(
    root: Path, session: str, *, now: datetime | None = None, historical_compatibility: bool = False,
) -> tuple[Path, dict[str, Any]]:
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
                    assert_post_close_eligible(
                        candidate, session, now=now, artifact_root=candidate_root,
                        historical_compatibility=historical_compatibility,
                    )
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
        assert_post_close_eligible(
            existing, session, now=now, artifact_root=root, historical_compatibility=historical_compatibility,
        )
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
    retained_evidence_root: Path | None = None, output_root: Path | None = None,
    no_new_provider_acquisition: bool = False, historical_compatibility: bool = False,
    enable_official_liquidity_rollforward: bool = False,
    enable_corporate_currency_rollforward: bool = False,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Stage 1-3: DNSE acquisition, runtime materialization, current-session analytics.

    ``historical_compatibility`` (explicit non-ordinary historical replay only) is the single path
    that may still reuse a genuinely pre-V1 companion-less snapshot; ordinary Daily never sets it.

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
    explicit_retained_evidence_root = retained_evidence_root is not None
    retained_evidence_root = Path(retained_evidence_root or root)
    output_root = Path(output_root or root)
    # This is intentionally before resolve_acquisition_root()/ensure_exact_session_snapshot(),
    # the two boundaries that can create an acquisition attempt or contact a provider.
    from daily_execution_environment import build_resume_plan, missing_retained_inputs
    missing = (
        missing_retained_inputs(
            retained_evidence_root, session, producer_registry_root=root,
        ) if explicit_retained_evidence_root else []
    )
    if missing:
        raise CanonicalPostCloseError(
            "FAILED_PREFLIGHT_RETAINED_EVIDENCE:STATIC_DEPENDENCY_UNAVAILABLE:"
            + ",".join(str(row["contract"]) for row in missing)
        )
    resume_plan = build_resume_plan(output_root, session)
    if no_new_provider_acquisition and resume_plan["provider_required_components"]:
        raise CanonicalPostCloseError(
            "FAILED_PREFLIGHT_RESUME:NO_NEW_PROVIDER_ACQUISITION_COMPONENTS_REQUIRED:"
            + ",".join(resume_plan["provider_required_components"])
        )
    artifact_root, eligibility = resolve_acquisition_root(
        output_root, session, now=now, historical_compatibility=historical_compatibility,
    )
    paths = level2.session_artifact_paths(artifact_root, session)
    if progress_callback is not None:
        try:
            progress_callback({
                "component": "Canonical Daily", "subtask": "exact_session_acquisition",
                "progress_kind": "PIPELINE", "status": "BEGIN",
                # The exact-session directory is a single current-run/session root. Do not
                # register every Level-2 path: that list duplicates directories and includes
                # retained/static evidence unrelated to this run.
                "run_output_paths": [str(paths["exact_session_snapshot"].parent)],
            })
        except Exception:
            pass
    try:
        ensure_kwargs: dict[str, Any] = {}
        if progress_callback is not None:
            ensure_kwargs["progress_callback"] = progress_callback
        level2.ensure_exact_session_snapshot(
            artifact_root, session, runtime_root, workers=workers, now=now, execution_root=root,
            **({"historical_compatibility": True} if historical_compatibility else {}),
            **ensure_kwargs,
        )
    except level2.SupplementalProviderBlocked as exc:
        raise SupplementalProviderBlockError(
            "REFUSE_CANONICAL_POST_CLOSE:" + str(exc)
            + ":DNSE evidence retained; ordinary Daily blocked (DNSE quality license not qualified, or the "
              "supplemental runtime failed mid-operation).",
            kind=exc.kind, runtime_state=exc.runtime_state, quality_license=exc.quality_license,
            diagnostic_path=exc.diagnostic_path,
        ) from exc
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
    # Retain selected listing evidence before complete market companions. The
    # original price retrieved_at remains authoritative, including the raw fallback.
    import prospective_market_evidence_retention as pit_retention
    prospective_evidence = {}
    corporate_rollforward = None
    corporate_frozen_inputs = None
    if enable_corporate_currency_rollforward:
        from corporate_currency_rollforward import rollforward
        corporate_frozen_inputs = capture_corporate_session_inputs(root, retained_evidence_root, session)
        frozen = corporate_frozen_inputs.get("event_context")
        try:
            corporate_rollforward = rollforward(
                retained_evidence_root, target_market_session=session, observed_at=now,
                allow_acquisition=not no_new_provider_acquisition and not historical_compatibility,
                frozen_market_selection=frozen,
            )
        except Exception:
            # Preserve price evidence even when listing acquisition fails. Such
            # a run never gets a complete-capture session or a marker.
            prospective_evidence["market"] = pit_retention.attempt(
                pit_retention.retain_market, snapshot, session=session, root=output_root)
            raise
        # A NEW decision may freeze this exact current selection only when all
        # knowledge was already available at its existing governed cutoff.
        # Completed sessions keep their actual lock, including absent optionals.
        registry = _load(root / "config" / "daily_research_session_input_registry.json") or {}
        completed = (registry.get("completed_sessions") or {}).get(session) or {}
        frozen_selection_failure = None
        if completed.get("status") != "COMPLETED_RETAINED_EVIDENCE":
            from corporate_currency_rollforward import context_known_by
            from official_corporate_event_incremental_acquisition import _retain_context
            current = corporate_rollforward.current_context()
            acquired_at = corporate_rollforward.receipt().get("acquired_at")
            cutoff = datetime.fromisoformat(f"{session}T15:00:00+07:00")
            if current and acquired_at and datetime.fromisoformat(acquired_at) <= cutoff and context_known_by(current, cutoff):
                out = root / "operations-review" / "corporate-daily-frozen-inputs-v1" / session / (current["artifact_sha256"] + ".json")
                try:
                    _retain_context(out, current)
                    corporate_frozen_inputs["event_context"] = {"path": _rel(root, out), "artifact_identity": current["artifact_identity"]}
                except Exception as exc:
                    corporate_frozen_inputs.pop("event_context", None)
                    frozen_selection_failure = f"{type(exc).__name__}:{exc}"
        corporate_rollforward = corporate_rollforward.bind_frozen_market_selection(
            corporate_frozen_inputs.get("event_context"), frozen_selection_failure)
        current_context = corporate_rollforward.current_context()
        if current_context:
            prospective_evidence["corporate"] = pit_retention.attempt(
                pit_retention.retain_corporate, current_context, root=output_root)
        selected_acquisition_session = corporate_rollforward.receipt().get("selected_acquisition_session")
        if selected_acquisition_session:
            prospective_evidence["listing_sources"] = pit_retention.attempt(
                pit_retention.retain_selected_listing_sources, retained_evidence_root,
                acquisition_session=selected_acquisition_session, root=output_root)
    # Explicit selected universe only; no latest directory search or historical active inference.
    universe_selection = (corporate_frozen_inputs or {}).get("official_universe")
    universe_path = root / universe_selection["path"] if universe_selection else level2.session_artifact_paths(retained_evidence_root, session)["official_universe"]
    prospective_evidence["universe"] = pit_retention.attempt(
        pit_retention.retain_universe, universe_path, root=output_root)
    # Same-session listing evidence is retained first. Market receipts keep their
    # exact original bytes; exchange/representation arrive in a separate batch.
    prospective_evidence["market"] = pit_retention.attempt(
        pit_retention.retain_market, snapshot, session=session, root=output_root)
    import prospective_pit_capture_retention as capture_retention
    prospective_evidence["capture"] = pit_retention.attempt(
        capture_retention.retain_capture_bindings, snapshot, session=session,
        evidence=prospective_evidence, root=output_root, created_at=capture_retention.io_known_at())
    prospective_evidence["official_verification"] = pit_retention.attempt(
        capture_retention.retain_registered_verifications, output_root, session=session,
        capture_result=prospective_evidence["capture"], registry_root=retained_evidence_root,
        verification_known_at=capture_retention.io_known_at())
    materialize_kwargs: dict[str, Any] = dict(
        workers=workers, now=now, execution_root=root,
    )
    if progress_callback is not None:
        materialize_kwargs["progress_callback"] = progress_callback
    if explicit_retained_evidence_root:
        materialize_kwargs["retained_evidence_root"] = retained_evidence_root
    level2.materialize_independent_components(
        artifact_root,
        session,
        runtime_root,
        **materialize_kwargs,
    )
    triage_kwargs: dict[str, Any] = {"execution_root": root}
    if explicit_retained_evidence_root:
        triage_kwargs["retained_evidence_root"] = retained_evidence_root
    triage_build_result = level2.maybe_build_triage_dependent(
        artifact_root,
        session,
        **triage_kwargs,
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
    # Official HOSE liquidity is materialized with descriptive DNSE liquidity
    # inside Level-2. Read the component status here; never crawl from this pipeline.
    official_rollforward: dict[str, Any]
    try:
        import daily_official_liquidity_rollforward as official_rollforward_mod
        status_payload, status_error = official_rollforward_mod.load_official_payload(
            official_rollforward_mod.status_path(artifact_root, session)
        )
        official_rollforward = (
            dict(status_payload)
            if isinstance(status_payload, dict)
            else {
                "status": status_error or official_rollforward_mod.UNAVAILABLE_SOURCE,
                "reason_code": status_error or official_rollforward_mod.UNAVAILABLE_SOURCE,
                "target_session": session,
            }
        )
    except Exception as exc:  # noqa: BLE001 -- official refresh must not destroy Daily
        official_rollforward = {
            "status": "UNAVAILABLE_SOURCE",
            "reason_code": f"{type(exc).__name__}:{exc}",
            "target_session": session,
        }
    return {
        "snapshot": snapshot,
        "resolved_completed_session": snapshot.get("resolved_completed_session"),
        "coverage": {"exact_session_retained_count": exact, "total_candidates": total, "ratio": coverage_ratio},
        "provider_contribution_counts": _provider_contribution_counts(snapshot),
        "triage_status": {"status": level2.EXACT_SESSION_CLEAN, "identity": triage_artifact.get("artifact_identity")},
        "triage_build_result": triage_build_result,
        "official_liquidity_rollforward": official_rollforward,
        "corporate_currency_rollforward": corporate_rollforward,
        "prospective_market_evidence": prospective_evidence,
        "corporate_frozen_inputs": corporate_frozen_inputs,
        "paths": paths,
        "artifact_root": artifact_root,
        "eligibility": eligibility,
        "resume_plan": resume_plan,
        "retained_evidence_root": retained_evidence_root,
        "output_root": output_root,
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


def resolve_current_session_priority_queue(
    session: str, *, opportunity: Mapping[str, Any] | None, triage: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Resolve the governed OPPORTUNITY_PRIORITY source for the Integrated Decision seam.

    Reuses the existing ``daily_opportunity_decision_queue.build`` presentation layer over this
    exact session's Level-2 ``current_opportunity_prioritization/v1`` (already the Integrated
    Decision's ``legacy_decision_artifact`` and the Daily brief's priority source) plus the same
    session's entry-candidate triage. No new score, tier, or ranking is computed. Any missing,
    stale, or self-inconsistent input leaves priority explicitly unavailable -- never a stale
    queue resurrected to make coverage nonzero.
    """
    import current_opportunity_prioritization as opportunity_module
    import daily_opportunity_decision_queue as queue_module
    import full_universe_entry_candidate_triage as triage_module

    def unavailable(reason: str) -> tuple[None, dict[str, Any]]:
        return None, {"status": "UNAVAILABLE", "reason": reason}

    if not isinstance(opportunity, Mapping):
        return unavailable("CURRENT_OPPORTUNITY_PRIORITIZATION_NOT_RETAINED")
    if opportunity.get("contract_version") != "current_opportunity_prioritization/v1":
        return unavailable("CURRENT_OPPORTUNITY_PRIORITIZATION_CONTRACT_MISMATCH")
    if opportunity.get("research_session") != session:
        return unavailable("CURRENT_OPPORTUNITY_PRIORITIZATION_SESSION_MISMATCH")
    if opportunity_module.content_identity(opportunity).get("artifact_sha256") != opportunity.get("artifact_sha256"):
        return unavailable("CURRENT_OPPORTUNITY_PRIORITIZATION_CONTENT_IDENTITY_INVALID")
    if not isinstance(triage, Mapping):
        return unavailable("SESSION_ENTRY_CANDIDATE_TRIAGE_NOT_RETAINED")
    if triage.get("source_market_session") != session:
        return unavailable("SESSION_ENTRY_CANDIDATE_TRIAGE_SESSION_MISMATCH")
    if triage_module.content_identity(triage).get("artifact_sha256") != triage.get("artifact_sha256"):
        return unavailable("SESSION_ENTRY_CANDIDATE_TRIAGE_CONTENT_IDENTITY_INVALID")
    try:
        queue = queue_module.build(opportunity=opportunity, triage=triage)
    except Exception as exc:  # noqa: BLE001 -- priority is orthogonal; never blocks the decision
        return unavailable(f"PRIORITY_QUEUE_BUILD_FAILED:{type(exc).__name__}")
    if queue.get("research_session") != session:
        return unavailable("PRIORITY_QUEUE_SESSION_MISMATCH")
    return queue, {
        "status": "RESOLVED_SAME_SESSION",
        "artifact_identity": queue.get("artifact_identity"),
        "source_artifact_identities": dict(queue.get("source_artifact_identities") or {}),
        "record_count": len(queue.get("records") or {}),
    }


def build_enrichment_components(
    root: Path, session: str, *, artifact_root: Path | None = None, runtime_root: Path | None = None,
    priority_queue_artifact: Mapping[str, Any] | None = None,
    retained_evidence_root: Path | None = None, output_root: Path | None = None,
    corporate_currency_rollforward=None,
) -> dict[str, Any]:
    """Best-effort materialize the three current-research components no orchestrator wires today
    (historical context, financial momentum, corporate event context). Each is fully independent;
    a failure in one never blocks the others or the rest of the pipeline -- component-local
    missing evidence stays component-local, per docs/AI_RULES.md invariant 6. A failed fresh build
    degrades to Level-2's shared prior-as-of file (still real retained evidence, just not
    session-pinned) rather than leaving the component wholly absent.

    `artifact_root` (defaulting to `root`) is where this run's session-specific Level-2 outputs
    are looked up. ``retained_evidence_root`` supplies immutable source inputs and ``output_root``
    owns fresh enrichment products; both default to the Producer root for legacy callers.
    """
    artifact_root = artifact_root or root
    retained_evidence_root = retained_evidence_root or root
    output_root = output_root or root
    paths = level2.session_artifact_paths(artifact_root, session)
    retained_paths = level2.session_artifact_paths(retained_evidence_root, session)
    registry_file = root / "config" / "daily_research_session_input_registry.json"
    registry = json.loads(registry_file.read_text(encoding="utf-8")) if registry_file.is_file() else {}
    completed = (registry.get("completed_sessions") or {}).get(session) or {}
    if completed.get("status") == "COMPLETED_RETAINED_EVIDENCE":
        frozen = frozen_optional_session_inputs(root, session)
        for key, level2_key in (("event_context", "official_event_context"), ("official_universe", "official_universe")):
            retained_paths[level2_key] = root / frozen[key]["path"] if key in frozen else root / "operations-review" / "historical-optional-unavailable" / key
    results: dict[str, Any] = {}
    if corporate_currency_rollforward is not None:
        receipt = corporate_currency_rollforward.receipt()
        overlay = {"contract_version": "current_corporate_knowledge_overlay/v1",
                   "receipt": receipt, "official_event_context": corporate_currency_rollforward.current_context(),
                   "non_voting": True, "historical_use_allowed": False}
        try:
            from current_corporate_intelligence_axis import build_artifact, build_forward_driver_context, forward_driver_coverage
            current = overlay["official_event_context"]
            universe = _load(retained_evidence_root / "operations-review" / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json")
            if not current or not universe or universe.get("artifact_identity") != (current.get("source_artifact_identities") or {}).get("official_universe"):
                raise ValueError("SELECTED_CURRENT_CONTEXT_UNIVERSE_LINEAGE_UNAVAILABLE")
            axis = build_artifact(official_universe=universe, official_event_context=current,
                                  root=retained_evidence_root, research_session=current["research_session"],
                                  include_supplemental_events=False)
            drivers = {ticker: build_forward_driver_context(record, as_of_session=receipt["acquisition_civil_date"])
                       for ticker, record in axis["records"].items()}
            overlay.update(corporate_intelligence_axis=axis, forward_driver_contexts=drivers,
                           forward_driver_coverage=forward_driver_coverage(list(drivers.values())))
        except Exception as exc:
            overlay["corporate_intelligence_unavailable_reason"] = f"{type(exc).__name__}:{exc}"
        overlay = __import__("official_corporate_event_incremental_acquisition")._self_verified(
            overlay, "current_corporate_knowledge_overlay")
        out = output_root / "operations-review" / "current-corporate-knowledge-overlay-v1" / receipt["acquisition_civil_date"] / (overlay["artifact_sha256"] + ".json")
        __import__("official_corporate_event_incremental_acquisition")._retain_context(out, overlay)
        results["current_corporate_knowledge_overlay"] = {"status": "AVAILABLE" if overlay["official_event_context"] else "UNAVAILABLE", "artifact": overlay, "path": out}

    iid_write_receipt: _IIDWriteReceipt | None = None

    def _attempt(name: str, level2_key: str, fn) -> None:
        try:
            artifact = fn()
            out = enrichment_output_path(output_root, session, name)
            if name == "integrated_investment_decision_product":
                _copy_iid_working_view(paths["integrated_investment_decision_product"], out,
                                       session=session, artifact=artifact, receipt=iid_write_receipt)
                from prospective_decision_outcome_feedback import retain_iid_classification_summary
                retain_iid_classification_summary(output_root, out, artifact)
            else:
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
        supplemental = (load_supplemental_retained_events(retained_evidence_root, evidence_session)
                        if evidence_session and corporate_currency_rollforward is None else None)
        return build(
            official_universe=official_universe,
            official_event_context=official_event_context,
            supplemental_events=supplemental,
            research_session=evidence_session,
        )

    def _historical_context():
        from market_wide_historical_research_context import build_artifact as build
        from canonical_market_bars import governed_calendar_projection
        universe_resolution = _load(paths["universe_resolution"])
        p3f9b_snapshot = _load(paths["exact_session_snapshot"])
        technical_recovery = _load(paths["technical_recovery"])
        strategy = _load(paths["strategy"])
        event_artifact = _load(retained_paths["official_event_context"]) or {}
        events = [e for record in event_artifact.get("records", {}).values() for e in record.get("events", [])]
        if not universe_resolution or not p3f9b_snapshot:
            raise CanonicalPostCloseError("REQUIRED_INPUT_MISSING")
        return build(universe_resolution_artifact=universe_resolution, p3f9b_snapshot=p3f9b_snapshot,
                     technical_history_recovery_artifact=technical_recovery, strategy_artifact=strategy,
                     market_calendar=governed_calendar_projection(_load(Path(__file__).parent / "config/governed_trading_session_calendar_v1.json")),
                     ca_events=events)

    def _integrated_investment_decision_product():
        nonlocal iid_write_receipt
        from integrated_investment_decision_product import build_artifact as build
        import canonical_current_product_projections as product_projections
        import canonical_daily_financial_v2_materialization as fin_v2_material
        import entity_classification_contract as entity_contract
        import financial_v2_current_input_authority as fin_v2_authority
        import integrated_investment_decision_product as integrated_contract
        import operational_fundamental_context_integration as operational_fundamental
        import market_structure_breakout_product_projection as msb_proj
        import market_wide_relative_volume_research as rvol_research
        import tactical_confirmation_context as confirmation_context
        import tactical_confirmation_invalidation_boundaries as boundary_context
        import tactical_momentum_context as momentum_context
        import tactical_setup_tags as setup_tags_context
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
        mkt = _load(paths["sector_leadership"])
        screening = _load(paths["screening_foundation"])
        opp = _load(paths["opportunity_prioritization"])
        if not desc or not p3f9b:
            raise CanonicalPostCloseError("REQUIRED_INPUT_MISSING")
        # Market receipts are already retained at the validated acquisition seam.
        # Integrated Decision is a consumer, never a second mutable receipt writer.
        # The Level-2 materializer may have preserved an invalid historical recovery artifact at
        # its canonical path while writing its validated same-session replacement into the one
        # explicit ``-revalidated`` namespace.  Never bypass that resolver by loading the
        # hardcoded path here: its exact frozen-Daily lineage contract is the authority for every
        # technical consumer in this Integrated Decision build.
        technical_resolution = level2.resolve_technical_recovery_artifact(
            artifact_root, session,
            p3f9b_snapshot_identity=p3f9b.get("snapshot_identity"),
            authority_root=retained_evidence_root,
        )
        technical_recovery = _load(technical_resolution["selected_path"])
        if not technical_recovery:
            raise CanonicalPostCloseError("RESOLVED_TECHNICAL_RECOVERY_ARTIFACT_UNAVAILABLE")
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
        # tactical_setup_tags/v1 has no canonical Daily materialization path of its own today; it
        # is built here, best-effort, from the exact same already-qualified same-session evidence
        # already in scope for the boundary engine above (plus screening/leadership), so
        # CANONICAL_RECURRING_DECISION_CONTEXT_MATERIALIZATION_V1's tactical_behavior_context
        # join has a genuine current-session source for it rather than none at all. A missing
        # mandatory input (screening/leadership/classifier) or a build failure leaves this
        # retention-only artifact absent; it never alters the already-determined action posture.
        tactical_setup_tags_artifact = None
        if tactical_classifier and screening and mkt:
            try:
                tactical_setup_tags_artifact = setup_tags_context.build_artifact(
                    technical_structure=technical_structure, current_descriptive=desc,
                    current_screening=screening, current_leadership=mkt,
                    tactical=tactical_classifier, requested_at=requested_at,
                )
            except Exception:
                tactical_setup_tags_artifact = None
        # Also retained under its own canonical per-session path (not just consumed here) so
        # downstream consumers -- the daily_integrated_decision_brief CLI-level builder in
        # particular, which needs BOS/CHoCH per watchlist ticker -- can load the same compact V3
        # projection without rebuilding it from raw technical_structure_context.
        _write_json(paths["market_structure_breakout_v3_projection"], tactical_projection)
        _write_json(paths["tactical_momentum_context"], momentum)
        _write_json(paths["tactical_confirmation_context"], confirmation)
        if tactical_boundaries is not None:
            _write_json(paths["tactical_confirmation_invalidation_boundaries"], tactical_boundaries)
        # technical_structure_context itself was never persisted anywhere before this milestone
        # (only its derivatives above were) -- this is pure retention of an already-computed
        # artifact, zero new computation, so canonical_current_product_projections.py can load it
        # per-session instead of rebuilding Tactical V3's own upstream input a second time.
        _write_json(paths["technical_structure_context"], technical_structure)
        if tactical_setup_tags_artifact is not None:
            _write_json(paths["tactical_setup_tags"], tactical_setup_tags_artifact)
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
        fin_authority = fin_v2_authority.resolve(retained_evidence_root)
        semantic_rows: list[dict] = []
        engine_artifact = fin_v2_material.build_engine_artifact(root=retained_evidence_root, requested_at=requested_at, authority=fin_authority,
                                                               semantic_rows_out=semantic_rows)
        financial_session_artifact = fin_v2_material.build_session_artifact(
            root=retained_evidence_root, decision_session=session, product_tickers=daily_denominator,
            requested_at=requested_at, authority=fin_authority, engine_artifact=engine_artifact,
        )
        readiness_context = (
            fin_v2_material.build_calculation_readiness_context(
                runtime_root=runtime_root, decision_session=session, raw_valuation_artifact=raw_val,
                product_tickers=daily_denominator, requested_at=requested_at,
            ) if runtime_root is not None else None
        )
        # CURRENT_RESEARCH_DECISION_CONVERGENCE_V1: one governed current-state entity
        # applicability (layered seed/promoted/legacy-recovery/scale-out authority) for the whole
        # Daily denominator. Valuation method applicability, the operational fundamental bridge and
        # the decision input all read this same resolution instead of the raw valuation lane's
        # narrower issuer panel. It is current-state only, never PIT entity identity.
        entity_applicability = entity_contract.resolve_current_research_entity_applicability(daily_denominator)
        evaluated_valuation = fin_v2_material.build_evaluated_valuation_artifact(
            engine_artifact=engine_artifact, raw_valuation_artifact=raw_val,
            product_tickers=daily_denominator, requested_at=requested_at,
            calculation_readiness_context=readiness_context,
            entity_applicability_artifact=entity_applicability,
            semantic_rows=semantic_rows, decision_session=session,
        )
        _write_json(paths["financial_analysis_product"], financial_session_artifact)
        _write_json(paths["current_valuation_evaluated"], evaluated_valuation)
        _write_json(paths["current_research_entity_applicability"], entity_applicability)
        # Ordinary-Daily binding of the entity-aware operational fundamental bridge. It consumes
        # the SAME feature-store build the Daily Producer retains (same pinned semantics
        # authority, requested_at-independent identity) and is consulted only where Financial V2
        # leaves the direction insufficient. Any failure is component-local: the Integrated
        # Decision then builds without the bridge rather than trusting an unverified source.
        operational_integration = None
        try:
            feature_store_result = product_projections.materialize_current_fundamental_feature_store_context(
                root=retained_evidence_root, requested_at=requested_at,
            )
            if feature_store_result.get("status") != "MATERIALIZED":
                raise CanonicalPostCloseError(
                    "FUNDAMENTAL_FEATURE_STORE_UNAVAILABLE:" + str(feature_store_result.get("reason_code")))
            fa_product = financial_session_artifact["financial_analysis_product"]
            candidates = sorted(
                ticker for ticker, fa_record in (fa_product.get("records") or {}).items()
                if integrated_contract.operational_fundamental_bridge_eligible(fa_record, decision_session=session)
            )
            operational_integration = operational_fundamental.build_daily_artifact(
                session=session, candidate_tickers=candidates,
                feature_store_artifact=feature_store_result["artifact"],
                entity_applicability_artifact=entity_applicability,
                financial_analysis_identity=fa_product.get("artifact_identity"),
            )
            _write_json(paths["operational_fundamental_context_integration"], operational_integration)
            results["operational_fundamental_binding"] = {
                "status": "BOUND", "artifact_identity": operational_integration["artifact_identity"],
                "feature_store_identity": feature_store_result["artifact"].get("artifact_identity"),
                "candidates": operational_integration["coverage"]["candidates"],
                "research_usable": operational_integration["coverage"]["research_usable"],
            }
        except Exception as exc:  # noqa: BLE001 -- component-local: the decision builds without the bridge
            operational_integration = None
            results["operational_fundamental_binding"] = {"status": "UNAVAILABLE", "reason": f"{type(exc).__name__}:{exc}"}
        # Same-session descriptive liquidity research feeds only the decision input's liquidity
        # dimension. A missing or other-session artifact is simply unavailable, never substituted.
        liquidity_research = _load(paths["liquidity_research"]) or _load(retained_paths["liquidity_research"])
        if not (isinstance(liquidity_research, Mapping)
                and liquidity_research.get("contract_version") == integrated_contract.LIQUIDITY_RESEARCH_CONTRACT
                and liquidity_research.get("resolved_completed_session") == session):
            liquidity_research = None
        # Official-exchange liquidity is materialized before this consumer. Same-session
        # only; malformed/other-session/budget/source failures stay component-local and never
        # substitute a prior session or fail the Daily.
        import daily_official_liquidity_rollforward as official_rollforward
        official_resolved = official_rollforward.load_for_daily_consumer(
            session=session,
            candidate_paths=(paths["official_liquidity"], retained_paths["official_liquidity"]),
            component_status_paths=(
                official_rollforward.status_path(paths["official_liquidity"]),
                official_rollforward.status_path(retained_paths["official_liquidity"]),
            ),
            allow_network=False,
        )
        official_liquidity = official_resolved.get("artifact")
        official_component = official_resolved.get("component") or {}
        results["official_liquidity_component"] = {
            "status": official_component.get("status") or official_rollforward.UNAVAILABLE_SOURCE,
            "reason_code": official_component.get("reason_code"),
            "artifact_identity": None if official_liquidity is None else official_liquidity.get("artifact_identity"),
        }
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
            market_wide_ci = (_load(retained_paths["corporate_intelligence"])
                              if corporate_currency_rollforward is None else None)
            if official_universe_ci and official_event_context_ci:
                corporate_intelligence_artifact = build_corporate_intelligence_axis(
                    official_universe=official_universe_ci,
                    official_event_context=official_event_context_ci,
                    root=retained_evidence_root,
                    research_session=official_event_context_ci.get("research_session"),
                    market_wide_current_corporate_intelligence=market_wide_ci,
                    **({"include_supplemental_events": False} if corporate_currency_rollforward is not None else {}),
                )
        except Exception:
            corporate_intelligence_artifact = None
        if corporate_intelligence_artifact is not None:
            _write_json(enrichment_output_path(output_root, session, "corporate_intelligence_axis"), corporate_intelligence_artifact)
        # CURRENT_DECISION_SURFACE_CONVERGENCE_V1: evidence currency is sourced from this exact
        # session's Level-2 same_session_technical_coverage_disposition/v1 (strict session and
        # content-identity checks live in the Integrated Decision boundary itself).
        technical_coverage_disposition = _load(paths["technical_coverage_disposition"]) or _load(retained_paths["technical_coverage_disposition"])
        # OPPORTUNITY_PRIORITY: an explicitly supplied queue wins; otherwise the same-session,
        # lineage-verified governed queue is resolved, or the axis stays explicitly unavailable.
        queue = priority_queue_artifact
        if queue is None:
            queue, priority_resolution = resolve_current_session_priority_queue(
                session, opportunity=opp, triage=_load(paths["session_triage"]) or _load(retained_paths["session_triage"]),
            )
        else:
            priority_resolution = {"status": "SUPPLIED_BY_CALLER", "artifact_identity": queue.get("artifact_identity")}
        results["opportunity_priority_queue"] = priority_resolution
        res = build(
            session=session,
            # The additive bar context needs the actual retained acquisition cutoff.
            # Existing feature builders above keep their standing calculation inputs.
            requested_at=p3f9b.get("requested_at") or requested_at,
            technical_structure_artifact=tactical_projection,
            financial_analysis_artifact=financial_session_artifact["financial_analysis_product"],
            financial_peer_materialization_artifact=financial_session_artifact,
            historical_context_artifact=results.get("historical_context", {}).get("artifact"),
            current_valuation_artifact=evaluated_valuation,
            relative_volume_artifact=relative_volume,
            market_sector_artifact=mkt,
            legacy_decision_artifact=opp,
            priority_queue_artifact=queue,
            technical_coverage_disposition_artifact=technical_coverage_disposition,
            momentum_artifact=momentum,
            tactical_confirmation_artifact=confirmation,
            tactical_boundaries_artifact=tactical_boundaries,
            corporate_intelligence_artifact=corporate_intelligence_artifact,
            operational_fundamental_integration_artifact=operational_integration,
            liquidity_research_artifact=liquidity_research,
            official_liquidity_artifact=official_liquidity,
            entity_applicability_artifact=entity_applicability,
        )
        if res.get("session") != session:
            raise CanonicalPostCloseError(f"INTEGRATED_DECISION_SESSION_MISMATCH:expected={session}:observed={res.get('session')}")
        if (res.get("contract_version") != integrated_contract.CONTRACT_VERSION
                or not isinstance(res.get("artifact_sha256"), str) or not res["artifact_sha256"]
                or res.get("artifact_identity") != integrated_contract.CONTRACT_VERSION + ":" + res["artifact_sha256"]):
            raise CanonicalPostCloseError("INTEGRATED_DECISION_BUILDER_IDENTITY_OR_CONTRACT_MISMATCH")
        iid_write_receipt = _write_json(paths["integrated_investment_decision_product"], res, capture_iid_receipt=True)
        from prospective_decision_outcome_feedback import retain_iid_classification_summary
        retain_iid_classification_summary(output_root, paths["integrated_investment_decision_product"], res)
        return res

    _attempt("financial_momentum", "financial_momentum", _financial_momentum)
    _attempt("corporate_event_context", "corporate_event_context", _corporate_event_context)
    _attempt("historical_context", "historical_context", _historical_context)
    _attempt("integrated_investment_decision_product", "integrated_investment_decision_product", _integrated_investment_decision_product)
    return results


def retain_prospective_decision_snapshot(
    root: Path, session: str, *, producer_result: Mapping[str, Any],
    enrichment: Mapping[str, Any], exact_session_snapshot: Mapping[str, Any] | None = None,
    output_root: Path | None = None,
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
        path = write_immutable_snapshot(output_root or root, snapshot)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": f"PROSPECTIVE_SNAPSHOT_RETENTION_FAILED:{type(exc).__name__}:{exc}"}
    return {"status": "RETAINED", "artifact": snapshot, "path": path}


def run_multi_session_signal_velocity_shadow(root: Path, session: str) -> dict[str, Any]:
    """Optional retained-only transition projection after the canonical handoff exists.

    The current immutable snapshot is intentionally not admitted until
    ``build_tiered_bundle`` has written its same-session handoff binding.  Any
    diagnostic problem is visible but cannot revise a completed Daily result,
    block the AI handoff, or trigger data acquisition.
    """
    from multi_session_signal_velocity import build_from_retained_root, write_immutable

    output = root / "operations-review" / "multi-session-signal-velocity-v1.2" / session / "multi_session_signal_velocity_artifact.json"
    try:
        artifact = build_from_retained_root(root)
        if session not in artifact["validation"]["retained_sessions"]:
            return {"status": "UNAVAILABLE", "session": session, "reason": "CURRENT_SESSION_SNAPSHOT_NOT_QUALIFIED_AFTER_HANDOFF"}
        write_immutable(output, artifact)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "session": session, "reason": f"RETAINED_SIGNAL_VELOCITY_FAILED:{type(exc).__name__}:{exc}"}
    return {
        "status": "COLLECTED", "session": session, "path": _rel(root, output),
        "artifact_identity": artifact["artifact_identity"],
        "latest_session_cohort_counts": artifact["validation"]["latest_session_cohort_counts"],
        "authority_boundary": "RETAINED_ONLY_CATEGORICAL_TRANSITION_RESEARCH_NOT_A_CURRENT_DECISION_INPUT",
    }


def run_flow_price_divergence_shadow(root: Path, runtime_root: Path, session: str,
                                     signal_velocity: Mapping[str, Any]) -> dict[str, Any]:
    """Optional, exact-session retained VALUE-flow observer after Velocity V1.2.

    It is intentionally downstream of the canonical handoff and signal-velocity
    collector.  Any retained-store or artifact issue is visible here but cannot
    alter a completed Daily, decision policy, or AI handoff.
    """
    from flow_price_divergence_shadow import (
        VELOCITY_CONTRACT_VERSION, collect_from_retained_runtime, write_immutable,
    )

    if signal_velocity.get("status") != "COLLECTED":
        return {"status": "UNAVAILABLE", "session": session,
                "reason": "SIGNAL_VELOCITY_V1_2_NOT_COLLECTED"}
    velocity_path = root / str(signal_velocity.get("path") or "")
    velocity = _load(velocity_path)
    if not isinstance(velocity, Mapping) or velocity.get("contract_version") != VELOCITY_CONTRACT_VERSION:
        return {"status": "UNAVAILABLE", "session": session,
                "reason": "EXACT_SIGNAL_VELOCITY_V1_2_ARTIFACT_UNAVAILABLE"}
    if velocity.get("artifact_identity") != signal_velocity.get("artifact_identity"):
        return {"status": "UNAVAILABLE", "session": session,
                "reason": "SIGNAL_VELOCITY_IDENTITY_MISMATCH"}
    velocity_body = {key: value for key, value in velocity.items()
                     if key not in {"artifact_identity", "artifact_sha256"}}
    velocity_digest = hashlib.sha256(
        json.dumps(velocity_body, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    if (velocity.get("artifact_sha256") != velocity_digest or
            velocity.get("artifact_identity") != "multi_session_signal_velocity:" + velocity_digest):
        return {"status": "UNAVAILABLE", "session": session,
                "reason": "SIGNAL_VELOCITY_CONTENT_IDENTITY_INVALID"}
    if (velocity.get("validation") or {}).get("latest_session") != session:
        return {"status": "UNAVAILABLE", "session": session,
                "reason": "SIGNAL_VELOCITY_REFERENCE_SESSION_MISMATCH"}
    output = root / "operations-review" / "flow-price-divergence-shadow-v1" / session / "flow_price_divergence_shadow_artifact.json"
    try:
        artifact = collect_from_retained_runtime(
            root=root, runtime_root=runtime_root, reference_session=session,
            velocity_artifact=velocity,
        )
        write_immutable(output, artifact)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "session": session,
                "reason": f"RETAINED_FLOW_PRICE_DIVERGENCE_FAILED:{type(exc).__name__}:{exc}"}
    return {
        "status": "COLLECTED", "session": session, "contract_version": artifact["contract_version"],
        "path": _rel(root, output), "artifact_identity": artifact["artifact_identity"],
        "relationship_evaluable_count": artifact["validation"]["relationship_evaluable_count"],
        "coverage_status": "PARTIAL_BY_EVIDENCE" if artifact["validation"]["relationship_evaluable_count"] < artifact["validation"]["record_count"] else "COMPLETE_RETAINED_EVIDENCE",
        "authority_boundary": "RETAINED_VALUE_ONLY_NON_CAUSAL_SHADOW_RESEARCH_NOT_A_DECISION_INPUT",
    }


def run_current_foreign_flow_enrichment(root: Path, runtime_root: Path, session: str, *,
                                        allow_network: bool = False) -> dict[str, Any]:
    """Optional, best-effort, resumable current foreign-flow enrichment after the canonical
    handoff exists and after Signal Velocity V1.2 -- deliberately before
    ``run_flow_price_divergence_shadow`` so the exact-session VALUE result is reflected in that
    step's read of the VALUE store. Production Daily
    (``canonical_daily_operation.run_canonical_daily_operation``) passes ``allow_network=True``
    for the qualified session (CURRENT_FOREIGN_FLOW_DAILY_ACTIVATION_V1). This helper still
    defaults closed so a diagnostic caller that omits the flag cannot silently reach DNSE.
    Every failure degrades to a visible, non-blocking status and cannot fail Core Daily or the
    AI handoff.
    """
    from current_foreign_flow_enrichment_operation import acquire_foreign_flow_for_manifest, CONTRACT_VERSION
    from current_foreign_flow_retention import build_manifest_from_root

    output = (root / "operations-review" / "current-foreign-flow-enrichment-v1" / session
             / "current_foreign_flow_enrichment_operation.json")
    try:
        manifest = build_manifest_from_root(root, session)
        operation = acquire_foreign_flow_for_manifest(manifest, runtime_root=runtime_root, allow_network=allow_network)
        _write_json(output, operation)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "session": session,
                "reason": f"CURRENT_FOREIGN_FLOW_ENRICHMENT_FAILED:{type(exc).__name__}:{exc}"}
    return {
        "status": operation["status"], "session": session, "contract_version": CONTRACT_VERSION,
        "path": _rel(root, output), "operation_identity": operation["operation_identity"],
        "manifest_identity": operation["acquisition_manifest_identity"],
        "requested_count": len(operation["requested_tickers"]), "complete_count": operation["complete_count"],
        "pending_count": operation["pending_count"], "failed_count": operation["failed_count"],
        "conflict_count": operation["conflict_count"], "network_calls_made": operation["network"]["network_calls_made"],
        "authority_boundary": "VALUE_ONLY_NON_ACTIONABLE_NO_LIQUIDITY_OR_SIZING_NOT_A_DECISION_INPUT",
    }


def _sealed_workspace_lineage(root: Path, producer_run_dir: Path) -> dict[str, Any] | None:
    """Read-only: locate the SEALED (pre-handoff) Producer Workspace for lineage comparison.

    Mirrors exactly what ``canonical_dashboard_runtime_release._stage_workspace`` already does
    to find the operation directory for a Producer run -- never a second, independent
    resolution. Returns ``None`` (never raises) if anything about the sealed evidence is
    missing or malformed; the caller treats that as "lineage unverifiable", not fatal.
    """
    try:
        run_manifest = _load(producer_run_dir / "run_manifest.json")
        operation_ref = (run_manifest or {}).get("daily_session_operation") or {}
        directory = operation_ref.get("directory")
        if not isinstance(directory, str) or not directory:
            return None
        operation_dir = root / directory
        sealed = _load(operation_dir / "investment_decision_workspace_projection.json")
        if not isinstance(sealed, Mapping):
            return None
        return {
            "operation_dir": operation_dir,
            "artifact_identity": sealed.get("artifact_identity"),
            "source_artifacts": dict(sealed.get("source_artifacts") or {}),
        }
    except Exception:
        return None


def run_post_handoff_presentation_projection(
    root: Path, runtime_root: Path, session: str, *,
    producer_run_dir: Path | None = None, output_root: Path | None = None,
    integrated_investment_decision_product: Mapping[str, Any] | None = None,
    current_corporate_knowledge_overlay: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Additive, presentation-only re-join of the current-product projections (Investment
    Decision Workspace / Screener Master Projection) now that post-handoff observers (Signal
    Velocity, Flow-Price) exist for THIS session -- see
    CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1.

    ``canonical_current_product_projections.materialize_and_write_current_product_projections``
    is the exact same pure, deterministic join Daily Producer itself calls
    (``daily_producer_pipeline.py``); this reuses it verbatim with a fresh ``operation_dir``
    (never the sealed Producer operation directory) so it writes an entirely new, additive
    artifact set and can never overwrite sealed Producer evidence. ``registry_inputs`` is
    re-resolved read-only via ``daily_research_session_operations.resolve_inputs`` against the
    same frozen session registry Producer used -- no new analytical computation, no re-derived
    opportunity/decision context: only the two previously-absent ``signal_velocity``/
    ``flow_price`` axes are newly populated (both were None/unavailable when Producer built the
    sealed Workspace, since post-handoff observers did not exist yet at that point).

    When ``producer_run_dir`` is supplied, the sealed Workspace's own ``source_artifacts.
    opportunity_context``/``security_decision_context`` identities are compared against this
    projection's -- a mismatch means the join drifted from Producer's own inputs and this
    degrades to UNAVAILABLE rather than presenting an inconsistent overlay. Non-blocking: any
    failure here never revises the completed Daily Producer result.

    CURRENT_DECISION_SURFACE_CONVERGENCE_V1: the re-join consumes the exact same Integrated
    Decision the sealed Workspace used (supplied by object, else this session's retained
    enrichment output), and the lineage check also requires that identity to match -- the
    presentation overlay can never carry a different action decision than the sealed product.
    """
    output_root = output_root or root
    lineage = _sealed_workspace_lineage(root, producer_run_dir) if producer_run_dir is not None else None
    integrated = integrated_investment_decision_product
    if integrated is None:
        integrated = _load(enrichment_output_path(output_root, session, "integrated_investment_decision_product"))
    if not isinstance(integrated, Mapping) or integrated.get("session") != session:
        return {"status": "UNAVAILABLE", "session": session,
                "reason": "PRESENTATION_PROJECTION_INTEGRATED_DECISION_UNAVAILABLE"}
    try:
        from daily_research_session_operations import load_registry, resolve_inputs
        from canonical_current_product_projections import materialize_and_write_current_product_projections
        from vn_time import vn_now

        registry = load_registry(root)
        registry_inputs, _metadata = resolve_inputs(root, session, registry)
        presentation_dir = output_root / "operations-review" / "post-handoff-presentation-projection-v1" / session
        if current_corporate_knowledge_overlay is not None:
            presentation_dir = (output_root / "operations-review" / "current-corporate-product-projection-v1"
                                / current_corporate_knowledge_overlay["receipt"]["acquisition_civil_date"]
                                / current_corporate_knowledge_overlay["artifact_sha256"] / session)
        result = materialize_and_write_current_product_projections(
            root=root, session=session, operation_dir=presentation_dir, registry_inputs=registry_inputs,
            requested_at=vn_now().isoformat(timespec="seconds"), runtime_root_override=runtime_root,
            integrated_investment_decision_product=integrated,
            **({"current_corporate_knowledge_overlay": current_corporate_knowledge_overlay}
               if current_corporate_knowledge_overlay is not None else {}),
        )
    except Exception as exc:
        return {"status": "UNAVAILABLE", "session": session, "reason": f"{type(exc).__name__}:{exc}"}
    if result.get("status") != "MATERIALIZED":
        return {"status": "UNAVAILABLE", "session": session,
                "reason": result.get("reason_code") or "PRESENTATION_PROJECTION_NOT_MATERIALIZED"}
    workspace_summary = result.get("workspace") or {}
    workspace_path = presentation_dir / "investment_decision_workspace_projection.json"
    new_workspace = _load(workspace_path) or {}
    new_source_artifacts = dict(new_workspace.get("source_artifacts") or {})
    lineage_status = "UNVERIFIED"
    if lineage is not None:
        matches = all(
            lineage["source_artifacts"].get(key) == new_source_artifacts.get(key)
            for key in ("opportunity_context", "security_decision_context", "integrated_investment_decision_product")
        )
        if not matches:
            return {"status": "UNAVAILABLE", "session": session,
                    "reason": "PRESENTATION_PROJECTION_LINEAGE_DIVERGED_FROM_SEALED_PRODUCER_WORKSPACE"}
        lineage_status = "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE"
    current_brief = None
    if current_corporate_knowledge_overlay is not None and lineage is not None:
        try:
            from corporate_currency_rollforward import current_product_projection
            frozen_brief = _load(lineage["operation_dir"] / "daily_integrated_decision_brief_artifact.json")
            if frozen_brief is not None:
                projected_brief = current_product_projection(frozen_brief, current_corporate_knowledge_overlay)
                brief_path = presentation_dir / "current_knowledge_daily_integrated_decision_brief.json"
                _write_json(brief_path, projected_brief)
                current_brief = {"path": _rel(root, brief_path), "artifact_identity": projected_brief["artifact_identity"],
                                 "frozen_brief_identity": frozen_brief["artifact_identity"]}
        except Exception as exc:
            current_brief = {"status": "UNAVAILABLE", "reason": f"{type(exc).__name__}:{exc}"}
    return {
        "status": "COLLECTED", "session": session,
        "contract_version": "post_handoff_presentation_projection/v1",
        "path": _rel(root, workspace_path),
        "workspace_artifact_identity": workspace_summary.get("artifact_identity"),
        "sealed_producer_workspace_artifact_identity": (lineage or {}).get("artifact_identity"),
        "screener_master_projection_artifact_identity": (result.get("screener_master_projection") or {}).get("artifact_identity"),
        "signal_velocity_source_identity": new_source_artifacts.get("signal_velocity"),
        "flow_price_divergence_shadow_source_identity": new_source_artifacts.get("flow_price_divergence_shadow"),
        "current_knowledge_brief": current_brief,
        "current_corporate_knowledge_overlay_identity": (current_corporate_knowledge_overlay or {}).get("artifact_identity"),
        "lineage_status": lineage_status,
        "authority_boundary": "PRESENTATION_ONLY_JOIN_NOT_A_DECISION_INPUT_NO_ANALYTICAL_RECOMPUTATION_NO_POLICY_MUTATION",
    }


def run_post_handoff_observers(
    root: Path, runtime_root: Path, session: str, tiers: Mapping[str, Any], *,
    enable_current_foreign_flow_live: bool = False,
) -> dict[str, Any]:
    """Retained-only observers admitted only after ``build_tiered_bundle`` has written the
    same-session canonical handoff binding (``session_handoff_bundle.json``).

    Shared by both the production canonical Daily kernel (``canonical_daily_operation.py``)
    and the diagnostic ``run_canonical_post_close`` below so neither can silently diverge on
    this sequencing again (CANONICAL_DAILY_POST_HANDOFF_AND_OWNER_WORKFLOW_RECONCILIATION_V1).
    Every observer here is best-effort and non-blocking: a failure surfaces as UNAVAILABLE and
    never revises or blocks the already-completed Daily Producer result or AI handoff.
    Production Daily passes ``enable_current_foreign_flow_live=True``
    (CURRENT_FOREIGN_FLOW_DAILY_ACTIVATION_V1). This helper still defaults False so a
    diagnostic caller that omits the flag cannot silently reach DNSE.
    """
    signal_velocity = run_multi_session_signal_velocity_shadow(root, session)
    current_foreign_flow_enrichment = run_current_foreign_flow_enrichment(
        root, runtime_root, session, allow_network=enable_current_foreign_flow_live,
    )
    flow_price_divergence = run_flow_price_divergence_shadow(root, runtime_root, session, signal_velocity)
    tier1 = tiers["session_handoff_bundle"]
    volume_flow_context = run_volume_and_flow_context(root, runtime_root, session, signal_velocity,
        tier1.get("prospective_decision_snapshot"))
    tier1["multi_session_signal_velocity"] = signal_velocity
    tier1["current_foreign_flow_enrichment"] = current_foreign_flow_enrichment
    tier1["flow_price_divergence_shadow"] = flow_price_divergence
    tier1["volume_and_flow_context"] = volume_flow_context
    _write_json(tiers["bundle_dir"] / "session_handoff_bundle.json", tier1)
    return {
        "multi_session_signal_velocity": signal_velocity,
        "current_foreign_flow_enrichment": current_foreign_flow_enrichment,
        "flow_price_divergence_shadow": flow_price_divergence,
        "volume_and_flow_context": volume_flow_context,
    }


def run_volume_and_flow_context(root: Path, runtime_root: Path, session: str,
                                signal_velocity: Mapping[str, Any],
                                snapshot_binding: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Separate retained-only observer; no sealed decision or policy mutation."""
    from volume_and_flow_retained import collect
    from flow_price_divergence_shadow import write_immutable
    output = root / "operations-review" / "volume-and-flow-context-v1" / session / "volume_and_flow_context.json"
    try:
        velocity = _load(root / signal_velocity["path"]) if signal_velocity.get("status") == "COLLECTED" else None
        sealed = None
        if snapshot_binding and snapshot_binding.get("status") == "RETAINED":
            sealed = _load(root / snapshot_binding["path"])
            if not sealed or sealed.get("snapshot_identity") != snapshot_binding.get("identity"):
                raise ValueError("VOLUME_FLOW_T0_HANDOFF_BINDING_INVALID")
        artifact, _ = collect(source_root=root,runtime_root=runtime_root,session=session,
                              velocity_artifact=velocity,sealed_snapshot=sealed)
        write_immutable(output,artifact)
        return {"status": "COLLECTED", "session": session, "path": _rel(root,output),
                "contract_version": artifact["contract_version"], "artifact_identity": artifact["artifact_identity"],
                "universe_denominator": artifact["universe_denominator"], "build_stage": "POST_T0_ENRICHED",
                "non_voting": True, "authority_effect": artifact["authority_effect"]}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "session": session,
                "reason": f"RETAINED_VOLUME_FLOW_CONTEXT_FAILED:{type(exc).__name__}:{exc}", "non_voting": True}


def run_post_handoff_prospective_outcome_feedback(
    root: Path, session: str, *, output_root: Path | None = None,
) -> dict[str, Any]:
    """Rerun outcome-feedback maturity evaluation after this session's own canonical handoff
    has bound its T0 snapshot.

    ``prospective_decision_retention.discover_snapshots`` only admits a session's T0 snapshot
    as GENUINE once ``session_handoff_bundle.json`` binds it (see
    CANONICAL_DAILY_POST_HANDOFF_AND_OWNER_WORKFLOW_RECONCILIATION_V1). ``run_prospective_
    collection``'s own feedback call runs before that binding exists for the CURRENT session,
    so a cohort whose maturation horizon lands exactly on today's session is invisible to that
    earlier run and would otherwise only be credited starting tomorrow. This reruns the same
    read-only builder afterwards and writes to a distinct path from the pre-handoff artifact
    ``run_prospective_collection`` already retains -- that earlier artifact remains immutable
    historical evidence of what outcome-feedback could see before this session's own handoff
    existed; no historical artifact is rewritten. Non-blocking: any failure degrades to
    UNAVAILABLE and never revises Daily Producer's completed result.
    """
    output_root = output_root or root
    output = (
        output_root / "operations-review" / "prospective-decision-outcome-feedback-post-handoff-v1"
        / session / "prospective_decision_feedback_artifact.json"
    )
    cmd = [
        sys.executable, "tools/run_prospective_decision_outcome_feedback.py",
        "--root", str(root), "--output", str(output),
    ]
    try:
        result = run_observed_subprocess(cmd, session=session, cwd=str(root), capture_output=True, text=True)
    except OSError as exc:
        return {"status": "UNAVAILABLE", "session": session, "reason": f"{type(exc).__name__}:{exc}"}
    if result.returncode != 0:
        return {"status": "UNAVAILABLE", "session": session, "reason": (result.stderr or result.stdout).strip()[-2000:]}
    artifact = _load(output)
    return {
        "status": "COLLECTED", "session": session, "path": _rel(root, output),
        "artifact_identity": (artifact or {}).get("artifact_identity"),
        "authority_boundary": "RETAINED_ONLY_POST_HANDOFF_MATURITY_REFRESH_NOT_A_CURRENT_DECISION_INPUT",
    }


def frozen_optional_session_inputs(root: Path, session: str, *, registry_path: Path | None = None) -> dict:
    path = registry_path or root / "config" / "daily_research_session_input_registry.json"
    if not path.is_file():
        return {}
    registry = json.loads(path.read_text(encoding="utf-8"))
    completed = (registry.get("completed_sessions") or {}).get(session)
    if not isinstance(completed, Mapping) or completed.get("status") != "COMPLETED_RETAINED_EVIDENCE":
        return {}
    selected = (registry.get("sessions") or {}).get(session) or {}
    lock = completed.get("frozen_input_identities") or {}
    frozen = {}
    for key in OPTIONAL_REGISTRY_KEYS:
        entry = selected.get(key)
        if entry is None:
            if key in lock:
                raise CanonicalPostCloseError("COMPLETED_SESSION_INPUT_MUTATION_REJECTED:" + session)
            continue
        artifact = _load(root / entry["path"])
        if (entry.get("artifact_identity") != lock.get(key)
                or not artifact or artifact.get("artifact_identity") != lock.get(key)):
            raise CanonicalPostCloseError("COMPLETED_SESSION_INPUT_MUTATION_REJECTED:" + session)
        try:
            from current_official_event_context import _verify
            _verify(artifact, "FROZEN_OPTIONAL_INPUT")
        except ValueError as exc:
            raise CanonicalPostCloseError("COMPLETED_SESSION_INPUT_MUTATION_REJECTED:" + session + ":" + str(exc)) from exc
        frozen[key] = dict(entry)
    return frozen


def capture_corporate_session_inputs(root: Path, retained_root: Path, session: str) -> dict:
    """Capture optional market inputs once, before downstream materialization.

    Completed sessions retain their original lock. New sessions use immutable
    content-addressed copies; later discovery cannot change this invocation.
    Event knowledge is bounded by the existing Integrated Decision 15:00 cutoff.
    """
    registry_path = root / "config" / "daily_research_session_input_registry.json"
    registry = _load(registry_path) or {}
    completed = (registry.get("completed_sessions") or {}).get(session) or {}
    if completed.get("status") == "COMPLETED_RETAINED_EVIDENCE":
        return frozen_optional_session_inputs(root, session)
    from corporate_currency_rollforward import context_known_by
    from official_corporate_event_incremental_acquisition import _retain_context
    from current_official_event_context import _verify
    cutoff = datetime.fromisoformat(f"{session}T15:00:00+07:00")
    paths = level2.session_artifact_paths(retained_root, session)
    selected = {}
    for key in OPTIONAL_REGISTRY_KEYS:
        try:
            artifact = _load(paths[REGISTRY_KEY_TO_LEVEL2_KEY[key]])
            if not artifact:
                continue
            _verify(artifact, "CAPTURED_OPTIONAL_INPUT")
            if key == "event_context" and not context_known_by(artifact, cutoff):
                continue
            out = root / "operations-review" / "corporate-daily-frozen-inputs-v1" / session / (artifact["artifact_sha256"] + ".json")
            _retain_context(out, artifact)
        except (ValueError, KeyError, OSError):
            # Optional source outage/integrity failure does not stop other lanes.
            continue
        selected[key] = {"path": _rel(root, out), "artifact_identity": artifact["artifact_identity"]}
    return selected


def register_session_inputs(
    root: Path, session: str, *, registry_path: Path | None = None, artifact_root: Path | None = None,
    retained_evidence_root: Path | None = None,
    corporate_frozen_inputs: Mapping[str, Any] | None = None,
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
    retained_paths = level2.session_artifact_paths(retained_evidence_root or root, session)
    selection: dict[str, dict[str, str]] = {}
    for registry_key, level2_key in REGISTRY_KEY_TO_LEVEL2_KEY.items():
        if corporate_frozen_inputs is not None and registry_key in OPTIONAL_REGISTRY_KEYS:
            entry = corporate_frozen_inputs.get(registry_key)
            if entry is not None:
                artifact = _load(root / entry["path"])
                if not artifact or artifact.get("artifact_identity") != entry["artifact_identity"]:
                    raise CanonicalPostCloseError("CAPTURED_OPTIONAL_INPUT_MUTATION_REJECTED:" + registry_key)
                from current_official_event_context import _verify
                _verify(artifact, "CAPTURED_OPTIONAL_INPUT")
                selection[registry_key] = dict(entry)
            continue
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
        frozen_optional = frozen_optional_session_inputs(root, session, registry_path=path)
        for key in OPTIONAL_REGISTRY_KEYS:
            selection.pop(key, None)
        selection.update(frozen_optional)
        if selection_identities(selection) != lock:
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
    root: Path, session: str, *, artifact_root: Path | None = None, output_root: Path | None = None,
) -> dict[str, Any] | None:
    """Post-hoc, non-blocking: a failure here never revises the completed Daily Producer result.

    `artifact_root` (defaulting to `root`) locates the decision packet build_decision_packet just
    wrote for THIS run. The Producer root remains the registry/code authority, while an explicit
    ``output_root`` receives both fresh prospective artifacts.
    """
    artifact_root = artifact_root or root
    output_root = output_root or root
    paths = level2.session_artifact_paths(artifact_root, session)
    packet_path = paths["decision_packet"]
    output = output_root / "operations-review" / "prospective-research-cohort-collection-v1" / f"prospective_research_cohort_snapshot_{session}.json"
    cmd = [
        sys.executable, "tools/run_prospective_research_cohort_collection.py",
        "--session", session, "--root", str(root), "--output", str(output),
    ]
    if packet_path.is_file():
        cmd += ["--decision-packet-path", str(packet_path)]
    result = run_observed_subprocess(cmd, session=session, cwd=str(root), capture_output=True, text=True)
    if result.returncode != 0:
        return {"status": "UNAVAILABLE", "reason": (result.stderr or result.stdout).strip()[-2000:]}
    snapshot = _load(output)
    # The same bounded post-close hook rolls forward already-retained integrated
    # decisions.  It scans only canonical handoffs from *earlier* sessions (the
    # current handoff has not been written yet), so it cannot feed current or
    # future outcome data back into today's decision.  A diagnostic failure is
    # deliberately localized just like the existing prospective cohort step.
    feedback_output = (
        output_root / "operations-review" / "prospective-decision-outcome-feedback-v1" / session
        / "prospective_decision_feedback_artifact.json"
    )
    feedback_cmd = [
        sys.executable, "tools/run_prospective_decision_outcome_feedback.py",
        "--root", str(root), "--output", str(feedback_output),
    ]
    feedback_result = run_observed_subprocess(feedback_cmd, component="Prospective decision feedback", session=session, cwd=str(root), capture_output=True, text=True)
    feedback = (
        {"status": "COLLECTED", "path": str(feedback_output), "artifact": _load(feedback_output)}
        if feedback_result.returncode == 0
        else {"status": "UNAVAILABLE", "reason": (feedback_result.stderr or feedback_result.stdout).strip()[-2000:]}
    )
    return {"status": "COLLECTED", "stdout": result.stdout, "snapshot": snapshot, "path": str(output), "decision_feedback": feedback}


SHADOW_COLLECTION_COMPLETE = "SHADOW_COLLECTION_COMPLETE"
SHADOW_COLLECTION_SKIPPED_NO_ELIGIBLE_ARTIFACT = "SHADOW_COLLECTION_SKIPPED_NO_ELIGIBLE_ARTIFACT"
SHADOW_COLLECTION_FAILED = "SHADOW_COLLECTION_FAILED"


def run_tactical_reversal_shadow_collection(
    root: Path, session: str, *, artifact_root: Path | None = None, output_root: Path | None = None,
) -> dict[str, Any]:
    """Post-hoc, non-blocking tactical-reversal shadow-probe observation collection.

    Mirrors ``run_prospective_collection``'s isolation contract exactly: a failure here
    never revises the completed Daily Producer result, never re-invokes the production
    classifier, and never acquires market data -- it consumes only the already-produced,
    already-retained ``watchlist_tactical_entry_classifier`` artifact for ``session``. If
    that artifact was never retained for this session (e.g. Daily ran without a tactical
    axis, or this is a non-trading/degraded session), collection is explicitly skipped
    rather than attempted against synthesized input. See
    ``TACTICAL_REVERSAL_SHADOW_COLLECTION_OPERATIONALIZATION_V1``.

    This is a distinct subsystem from ``run_prospective_collection`` above (which admits
    Decision-Workspace research theses into ``durable_prospective_research_case_store``);
    the two are unrelated and intentionally keyed under different result names so neither
    silently shadows the other.
    """
    artifact_root = artifact_root or root
    output_root = output_root or root
    paths = level2.session_artifact_paths(artifact_root, session)
    tactical_path = paths.get("tactical_classifier")
    if not isinstance(tactical_path, Path) or not tactical_path.is_file():
        return {
            "status": SHADOW_COLLECTION_SKIPPED_NO_ELIGIBLE_ARTIFACT,
            "session": session,
            "reason": "TACTICAL_CLASSIFIER_ARTIFACT_NOT_RETAINED_FOR_SESSION",
        }
    store_root = output_root / "operations-review" / "tactical-reversal-prospective-shadow-collection-v1"
    cmd = [
        sys.executable, "tools/run_tactical_reversal_prospective_shadow_collection.py",
        "--retained-evidence-root", str(artifact_root), "--store-root", str(store_root), "--session", session,
    ]
    try:
        result = run_observed_subprocess(cmd, session=session, cwd=str(root), capture_output=True, text=True)
    except OSError as exc:
        return {"status": SHADOW_COLLECTION_FAILED, "session": session, "reason": f"{type(exc).__name__}:{exc}"}
    if result.returncode != 0:
        return {
            "status": SHADOW_COLLECTION_FAILED, "session": session,
            "reason": (result.stderr or result.stdout).strip()[-2000:],
        }
    try:
        summary = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        summary = None
    return {"status": SHADOW_COLLECTION_COMPLETE, "session": session, "store_root": str(store_root), "summary": summary}


def build_tiered_bundle(
    root: Path, session: str, *,
    acquisition: Mapping[str, Any], producer_result: Mapping[str, Any],
    decision_packet: Mapping[str, Any] | None, prospective: Mapping[str, Any] | None,
    enrichment: Mapping[str, Any], producer_head: str | None, consumer_head: str | None,
    prospective_snapshot: Mapping[str, Any] | None = None,
    artifact_root: Path | None = None, runtime_release: Mapping[str, Any] | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    artifact_root = artifact_root or root
    output_root = output_root or root
    level2_paths = level2.session_artifact_paths(artifact_root, session)
    bundle_dir = output_root / "operations-review" / "canonical-post-close-v1" / session
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
    enable_current_foreign_flow_live: bool = False,
    enable_official_liquidity_rollforward: bool = False,
    enable_corporate_currency_rollforward: bool = False,
) -> dict[str, Any]:
    if not isinstance(session, str) or not session.strip():
        raise CanonicalPostCloseError("REFUSE_CANONICAL_POST_CLOSE:EXPLICIT_SESSION_REQUIRED")
    now = now or vn_now()
    acquisition = acquire_and_materialize(
        root, session, runtime_root, workers=workers, now=now,
        enable_official_liquidity_rollforward=enable_official_liquidity_rollforward,
        enable_corporate_currency_rollforward=enable_corporate_currency_rollforward,
    )
    artifact_root = acquisition["artifact_root"]
    register_session_inputs(root, session, artifact_root=artifact_root,
                           corporate_frozen_inputs=acquisition.get("corporate_frozen_inputs"))
    validate_and_freeze_completed_session(root, session)
    # The rich Integrated Decision is an already-governed, exact-session
    # enrichment surface.  Build it before the immutable Daily operation so
    # the operation's AI handoff and cockpit can retain it as an additive
    # overlay.  It is deliberately supplied by object identity below; neither
    # the producer nor the delivery layer performs a "latest" lookup.
    enrichment = build_enrichment_components(
        root, session, artifact_root=artifact_root, runtime_root=runtime_root,
        **({"corporate_currency_rollforward": acquisition["corporate_currency_rollforward"]}
           if acquisition.get("corporate_currency_rollforward") is not None else {}),
    )
    integrated_delivery = (enrichment.get("integrated_investment_decision_product") or {}).get("artifact")
    if not isinstance(integrated_delivery, Mapping) or integrated_delivery.get("session") != session:
        raise CanonicalPostCloseError("REFUSE_CANONICAL_POST_CLOSE:INTEGRATED_DECISION_DELIVERY_INPUT_UNAVAILABLE")
    producer_head, consumer_head = _git_head(root), _git_head(root.parent / "ai-core-private")
    try:
        producer_result = run_daily_producer(
            root, session=session, latest_completed_session=False,
            producer_head=producer_head or "UNKNOWN", consumer_head=consumer_head or "UNKNOWN",
            integrated_investment_decision_product=integrated_delivery,
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
    prospective_snapshot = retain_prospective_decision_snapshot(
        root, session, producer_result=producer_result, enrichment=enrichment,
        exact_session_snapshot=acquisition.get("snapshot"),
    )
    import prospective_pit_capture_retention as capture_retention
    import prospective_market_evidence_retention as pit_retention
    from completed_market_session_gate import evaluate_completed_market_session_gate
    capture_known_at = capture_retention.io_known_at()
    capture_gate = evaluate_completed_market_session_gate(requested_at=capture_known_at,
        requested_session=session, exact_session_evidence=acquisition.get("snapshot"), allow_provider_probe=False)
    prospective_capture_readiness = pit_retention.attempt(capture_retention.daily_boundary, root,
        session=session, gate=capture_gate, evidence=acquisition.get("prospective_market_evidence") or {},
        known_at=capture_known_at, t0_snapshot_identity=((prospective_snapshot or {}).get("artifact") or {}).get("snapshot_identity"))
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
    # The tiered bundle above writes the sole binding that qualifies today's
    # immutable T0 snapshot.  Run the shared post-handoff observers only afterwards
    # (same helper canonical_daily_operation.py's production kernel calls); they are
    # deliberately best-effort and cannot change Producer or handoff success.
    post_handoff = run_post_handoff_observers(
        root, runtime_root, session, tiers, enable_current_foreign_flow_live=enable_current_foreign_flow_live,
    )
    post_handoff_feedback = run_post_handoff_prospective_outcome_feedback(root, session)
    post_handoff_presentation_projection = run_post_handoff_presentation_projection(
        root, runtime_root, session, producer_run_dir=producer_result.get("run_dir"),
        integrated_investment_decision_product=integrated_delivery,
        **({"current_corporate_knowledge_overlay": enrichment["current_corporate_knowledge_overlay"]["artifact"]}
           if enrichment.get("current_corporate_knowledge_overlay") else {}),
    )
    return {
        "session": session, "acquisition": acquisition, "enrichment": enrichment,
        "producer_result": producer_result, "decision_packet": decision_packet,
        "prospective": prospective, "prospective_snapshot": prospective_snapshot,
        "prospective_pit_capture_readiness": prospective_capture_readiness,
        "runtime_release": runtime_release, "tiers": tiers,
        "multi_session_signal_velocity": post_handoff["multi_session_signal_velocity"],
        "current_foreign_flow_enrichment": post_handoff["current_foreign_flow_enrichment"],
        "flow_price_divergence_shadow": post_handoff["flow_price_divergence_shadow"],
        "volume_and_flow_context": post_handoff["volume_and_flow_context"],
        "post_handoff_prospective_decision_feedback": post_handoff_feedback,
        "post_handoff_presentation_projection": post_handoff_presentation_projection,
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
    foreign_flow = tier1.get("current_foreign_flow_enrichment") or {}
    print(f"CURRENT_FOREIGN_FLOW_ENRICHMENT: {foreign_flow.get('status')} "
         f"({foreign_flow.get('complete_count')}/{foreign_flow.get('requested_count')} complete, "
         f"network_calls={foreign_flow.get('network_calls_made')})")
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
    parser.add_argument("--enable-current-foreign-flow-live", action="store_true",
                        help="Explicit authorization for a real DNSE current foreign-flow "
                             "acquisition after this session's canonical handoff is written. "
                             "This diagnostic CLI still defaults network-off; production Daily "
                             "enables the same collector separately.")
    args = parser.parse_args(argv)
    try:
        result = run_canonical_post_close(ROOT, Path(args.runtime_root), args.session, workers=args.workers,
                                          enable_current_foreign_flow_live=args.enable_current_foreign_flow_live)
    except CanonicalPostCloseError as exc:
        print(f"STATUS: {exc}")
        return 2
    print_terminal_handoff(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
