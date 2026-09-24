"""Safe, versioned owner workflow for Canonical Daily, AI Git handoff, and Action Center.

The desktop .cmd only calls the paired PowerShell presentation script. This module is
deliberately testable and contains the workflow gates. Its Action Center step may use the
existing optional local portfolio contract, but no private artifact reaches Git publication.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME = ROOT.parent / "dashboard-runtime"
DEFAULT_HANDOFF_REPO = ROOT.parent / "stocklookup-ai-handoffs"
# The external owner result/log root -- the same workspace-level directory the desktop one-click
# launcher (tools/run_owner_daily.ps1, $logDir) writes to. Never inside the Producer checkout:
# validate_result_path() refuses that (RESULT_PATH_INSIDE_PRODUCER_CHECKOUT).
DEFAULT_RESULT_LOG_ROOT = ROOT.parent / "run-logs"
DAILY_STATE_ALLOWLIST = ("config/daily_research_session_input_registry.json",)
SESSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from release_checkout_identity import CANONICAL_WEB_ROOT  # noqa: E402
from canonical_dashboard_runtime_release import (  # noqa: E402
    CanonicalRuntimeReleaseError, materialize_canonical_runtime_release, materialize_release_ready_runtime,
)
from canonical_trusted_subset_release import (  # noqa: E402
    CanonicalTrustedSubsetError, materialize_canonical_trusted_subset,
)
from checkout_cleanliness_contract import (  # noqa: E402
    CONSUMER_APPROVED_UNTRACKED_PREFIXES, classify_checkout_cleanliness,
)
from governed_publication_completion import (  # noqa: E402
    resolve_dashboard_origin_main_sha,
    verify_existing_publication_completion,
)
import owner_daily_journal as journal  # noqa: E402

DEFAULT_WEB_DIR = CANONICAL_WEB_ROOT


class OwnerDailyError(RuntimeError):
    def __init__(self, step: str, reason: str, hint: str = "") -> None:
        super().__init__(reason)
        self.step, self.reason, self.hint = step, reason, hint


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", check=False)
    if result.returncode:
        raise OwnerDailyError("Repository preflight", "GIT_" + args[0].upper() + ":" +
                              (result.stderr.strip() or result.stdout.strip()),
                              "Resolve the Git error and run again.")
    return result.stdout.strip()


def _git_unstripped(root: Path, *args: str) -> str:
    """Like `_git`, but returns raw stdout with no whole-string whitespace trim.

    `_git`'s `.strip()` is safe for every scalar HEAD/branch/remote-url caller, but
    `_tracked_changes` depends on each `git status --porcelain` line's exact fixed 3-character
    ``XY `` status prefix (2 status columns + 1 separating space) to recover the path via a
    fixed-offset slice. When the very first record's status code starts with a space (e.g.
    ``" M path"`` for an unstaged-only modification), a whole-string `.strip()` silently eats
    that leading space before the text is even split into lines, shifting every downstream
    fixed-offset slice one character into the path.
    """
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, encoding="utf-8", check=False)
    if result.returncode:
        raise OwnerDailyError("Repository preflight", "GIT_" + args[0].upper() + ":" +
                              (result.stderr.strip() or result.stdout.strip()),
                              "Resolve the Git error and run again.")
    return result.stdout


def _tracked_changes(root: Path) -> list[str]:
    return [line for line in _git_unstripped(root, "status", "--porcelain", "--untracked-files=no").splitlines() if line]


# Porcelain XY codes a pending, not-yet-committed Daily registry update may legitimately carry:
# an in-place modification that is unstaged, staged, or both. Deletion/rename/add/conflict never.
_PENDING_DAILY_STATE_STATUS_CODES = frozenset({" M", "M ", "MM"})


def _is_sole_pending_daily_state_diff(root: Path) -> bool:
    lines = _tracked_changes(root)
    return bool(lines) and all(
        line[:2] in _PENDING_DAILY_STATE_STATUS_CODES and line[3:].replace("\\", "/") == DAILY_STATE_ALLOWLIST[0]
        for line in lines
    )


def preflight_repository(root: Path, *, expected_name: str, expected_remote_fragment: str,
                         completed_session: str | None = None,
                         runtime_root: Path | None = None,
                         approved_untracked_prefixes: tuple[str, ...] | None = None) -> dict[str, str]:
    """Synchronize a clean main checkout only by safe fast-forward; never discard work.

    ``completed_session`` (explicit replay / verified auto-resume only) is the ONE narrow
    exception to the clean-checkout rule, for a Daily whose analytical kernel completed but was
    interrupted before ``commit_daily_state``: the governed Daily registry may then be the sole
    tracked diff. It is tolerated only when (a) it is exactly that one path as an in-place
    modification, (b) no unsafe untracked path exists, (c) local HEAD already equals the freshly
    fetched ``origin/main`` -- never a pull/fast-forward across a dirty tracked file -- and (d)
    ``verify_daily_completion`` proves ``completed_session`` already passed every canonical
    LOCAL_COMPLETE / retained-evidence gate. The registry itself is then committed and pushed by
    the existing ``commit_daily_state``. A fresh Daily (``completed_session=None``) keeps the
    strict clean-checkout contract unchanged.
    """
    root = root.resolve()
    if root.name != expected_name or not (root / ".git").exists():
        raise OwnerDailyError("Repository preflight", "WRONG_REPOSITORY", f"Expected {expected_name} checkout.")
    remote = _git(root, "remote", "get-url", "origin")
    if expected_remote_fragment not in remote:
        raise OwnerDailyError("Repository preflight", "WRONG_ORIGIN", "Restore the configured private origin.")
    _git(root, "fetch", "origin")
    if _git(root, "branch", "--show-current") != "main":
        raise OwnerDailyError("Repository preflight", "BRANCH_IS_NOT_MAIN", "Switch to main without discarding work.")
    # None keeps the Producer's governed runtime/evidence prefixes; a sibling checkout passes its
    # own explicit contract (e.g. CONSUMER_APPROVED_UNTRACKED_PREFIXES).
    cleanliness = (classify_checkout_cleanliness(root) if approved_untracked_prefixes is None
                   else classify_checkout_cleanliness(root, approved_untracked_prefixes))
    pending_daily_state = bool(
        cleanliness.tracked_dirty_paths and completed_session is not None
        and _is_sole_pending_daily_state_diff(root)
    )
    if cleanliness.tracked_dirty_paths and not pending_daily_state:
        raise OwnerDailyError("Repository preflight",
                              "UNEXPECTED_TRACKED_CHANGES:" + ";".join(cleanliness.tracked_dirty_paths),
                              "Commit, stash, or otherwise resolve the tracked work before Daily.")
    if cleanliness.unsafe_untracked_paths:
        raise OwnerDailyError("Repository preflight",
                              "UNSAFE_UNTRACKED_CHECKOUT:" + ";".join(cleanliness.unsafe_untracked_paths),
                              "Remove or govern the unexpected untracked file(s) before Daily; "
                              "only approved runtime/evidence paths may remain untracked.")
    head, remote_head = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "origin/main")
    if pending_daily_state:
        if head != remote_head:
            raise OwnerDailyError("Repository preflight", "PENDING_DAILY_STATE_HEAD_NOT_ORIGIN_MAIN",
                                  "The pending Daily registry can only be committed on top of origin/main; "
                                  "integrate main safely first. No pull, reset, or rebase was attempted.")
        if runtime_root is None:
            raise OwnerDailyError("Repository preflight", "PENDING_DAILY_STATE_RUNTIME_ROOT_REQUIRED")
        try:
            verify_daily_completion(root, runtime_root, session=completed_session)
        except OwnerDailyError as exc:
            raise OwnerDailyError("Repository preflight",
                                  "PENDING_DAILY_STATE_SESSION_NOT_VERIFIED:" + exc.reason,
                                  "Only a canonically completed exact session may retain its pending registry.") from exc
        return {"head": head, "status": "PENDING_DAILY_STATE_AT_ORIGIN_MAIN"}
    if head == remote_head:
        return {"head": head, "status": "UP_TO_DATE"}
    # --is-ancestor uses its nonzero exit code as a relationship result, not a Git failure.
    is_behind = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", head, remote_head,
                                ], capture_output=True, check=False).returncode == 0
    is_ahead = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", remote_head, head,
                               ], capture_output=True, check=False).returncode == 0
    if not is_behind or is_ahead:
        raise OwnerDailyError("Repository preflight", "UNSAFE_GIT_DIVERGENCE",
                              "Integrate main safely before running Daily; no reset or rebase was attempted.")
    _git(root, "pull", "--ff-only", "origin", "main")
    return {"head": _git(root, "rev-parse", "HEAD"), "status": "FAST_FORWARDED"}


def preflight_dashboard_repository(dashboard_web_dir: Path) -> dict[str, str]:
    """PRE_DAILY_WORKSPACE_READINESS_CORRECTIVE_V1: bring the canonical Dashboard checkout to
    ``origin/main`` BEFORE any analytical Daily work, with the exact same safe-sync semantics as
    the Producer (the one shared ``preflight_repository`` engine -- no second Git sync path):
    ``market-dashboard`` checkout, ``main`` branch, market-dashboard origin, fetch, strictly
    clean (any tracked change or untracked file blocks), UP_TO_DATE / ``pull --ff-only`` only,
    ahead or diverged fails closed. Never resets, rebases, stashes, or cleans.

    The Dashboard source can be promoted independently of Daily (e.g. from an isolated
    worktree), so the canonical checkout may be a clean strict ancestor of ``origin/main`` when
    Daily starts; the publisher deliberately refuses to pull and would otherwise fail only after
    the whole analytical Daily. The publisher's own final ``HEAD == origin/main`` guard
    (release_checkout_identity) is unchanged and still catches a remote advance after this point.
    """
    return preflight_repository(dashboard_web_dir, expected_name="market-dashboard",
                                expected_remote_fragment="market-dashboard")


def consumer_root_for(producer_root: Path) -> Path:
    """The ONE ai-core-private checkout canonical Daily executes: canonical_daily_operation records
    ``_git_head(root.parent / "ai-core-private")`` as ``consumer_head``,
    daily_research_session_operations imports ``builders.build_ticker_context`` from it, and the
    trusted-subset release verifies bundles with it. Never a worktree or another clone."""
    return Path(producer_root).resolve().parent / "ai-core-private"


def preflight_consumer_repository(consumer_root: Path, *, producer_root: Path) -> dict[str, str]:
    """PRE_DAILY_WORKSPACE_READINESS_CORRECTIVE_V1 final hardening: normal Daily (and the
    publication path's trusted-subset verification) EXECUTES code from the sibling ai-core-private
    checkout, so that checkout is governed before any analytical work, with the same single shared
    safe-sync engine as the Producer and Dashboard: exact canonical path (the path Daily imports
    from), ai-core-private origin, ``main``, fetch, clean tracked state, the explicit Consumer
    untracked contract (CONSUMER_APPROVED_UNTRACKED_PREFIXES -- never the Producer's data/...
    prefixes), UP_TO_DATE / ``pull --ff-only`` only, ahead or diverged fails closed. Never resets,
    rebases, stashes, or cleans. The returned ``head`` is the Consumer HEAD Daily then records.
    """
    expected = consumer_root_for(producer_root)
    if os.path.normcase(str(Path(consumer_root).resolve())) != os.path.normcase(str(expected)):
        raise OwnerDailyError("Repository preflight", "WRONG_CONSUMER_PATH:" + str(Path(consumer_root).resolve()),
                              f"Daily executes the Consumer at {expected}; govern that checkout.")
    return preflight_repository(expected, expected_name="ai-core-private",
                                expected_remote_fragment="ai-core-private",
                                approved_untracked_prefixes=CONSUMER_APPROVED_UNTRACKED_PREFIXES)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OwnerDailyError("Daily completion verification", "INVALID_JSON:" + str(path),
                              "Retain a valid canonical completion artifact.") from exc
    if not isinstance(value, dict):
        raise OwnerDailyError("Daily completion verification", "JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _operation_records(root: Path) -> list[tuple[dict[str, Any], Path]]:
    base = root / "operations-review" / "canonical-daily-operation-v1"
    return [(_load(path), path) for path in base.glob("*/*/daily_operation_record.json")]


def verify_daily_completion(root: Path, runtime_root: Path, *, session: str | None = None) -> dict[str, Any]:
    registry = _load(root / DAILY_STATE_ALLOWLIST[0])
    records = [(record, path) for record, path in _operation_records(root)
               if session is None or record.get("session") == session]
    if not records:
        raise OwnerDailyError("Daily completion verification", "CANONICAL_COMPLETION_RECORD_NOT_FOUND")
    record, path = max(records, key=lambda row: row[1].stat().st_mtime)
    resolved = str(record.get("session") or "")
    completed = (registry.get("completed_sessions") or {}).get(resolved) or {}
    required = {
        "daily_operation_state": "LOCAL_COMPLETE", "daily_producer_status": "COMPLETED",
        "runtime_release_status": "READY", "trusted_subset_status": "READY",
    }
    bad = [f"{key}={record.get(key)!r}" for key, expected in required.items() if record.get(key) != expected]
    if (not SESSION_RE.fullmatch(resolved) or completed.get("status") != "COMPLETED_RETAINED_EVIDENCE"
            or completed.get("trading_day_valid") is not True
            or str((record.get("acquisition") or {}).get("resolved_completed_session") or "") != resolved
            or not record.get("daily_producer_run_identity") or not record.get("daily_producer_operation_identity")
            or not record.get("operation_identity") or bad):
        raise OwnerDailyError("Daily completion verification", "CANONICAL_GATE_FAILED:" + ";".join(bad),
                              "Do not publish until canonical Daily records all READY/COMPLETED gates.")
    runtime_manifest = runtime_root / "bundle_manifest.json"
    if not runtime_manifest.is_file():
        raise OwnerDailyError("Daily completion verification", "RUNTIME_RELEASE_MANIFEST_MISSING")
    source_candidates = list((root / "operations-review" / "daily-research-session-operations-v1" / resolved).glob("*/ai_research_bundle_manifest.json"))
    operation_id = record["daily_producer_operation_identity"]
    source_candidates = [p for p in source_candidates if _load(p).get("operation_identity") == operation_id]
    if len(source_candidates) != 1:
        raise OwnerDailyError("Daily completion verification", "AI_HANDOFF_OPERATION_AMBIGUOUS_OR_MISSING")
    return {"session": resolved, "record": record, "record_path": path,
            "source": source_candidates[0].parent, "operation_id": operation_id}


def commit_daily_state(root: Path, session: str) -> dict[str, str]:
    changed = _tracked_changes(root)
    if not changed:
        return {"status": "NO_CHANGE", "sha": _git(root, "rev-parse", "HEAD")}
    paths = {line[3:].replace("\\", "/") for line in changed}
    unexpected = sorted(paths.difference(DAILY_STATE_ALLOWLIST))
    if unexpected:
        raise OwnerDailyError("Producer state publication", "UNEXPECTED_POST_DAILY_DIFF:" + ",".join(unexpected),
                              "Only the governed Daily registry may change before this commit.")
    registry = _load(root / DAILY_STATE_ALLOWLIST[0])
    row = (registry.get("completed_sessions") or {}).get(session) or {}
    if row.get("status") != "COMPLETED_RETAINED_EVIDENCE":
        raise OwnerDailyError("Producer state publication", "REGISTRY_SESSION_NOT_COMPLETED")
    _git(root, "add", "--", *DAILY_STATE_ALLOWLIST)
    _git(root, "commit", "-m", f"daily: retain {session} completed session")
    _git(root, "push", "origin", "main")
    return {"status": "COMMITTED", "sha": _git(root, "rev-parse", "HEAD")}


def verify_dashboard_session(web_dir: Path, session: str) -> dict[str, Any]:
    """Prove the published Dashboard bytes actually carry the exact resolved Daily session.

    Reads only what the governed publisher (`publish_dashboard.py`, via `tools/release_
    orchestrator.py all --live`) itself just wrote to `web_dir` -- never a second,
    independent session resolution. Requires `build_info.market_session`, the additive
    `build_info.investment_workspace.source_session` and (M1_LIVE_ACCEPTANCE_CORRECTIVE_V1)
    `build_info.current_decision_cockpit.source_session` to equal the exact Daily session;
    any mismatch or absence (or the file being unreadable) fails closed.
    """
    build_info_path = web_dir / "data" / "build_info.json"
    try:
        build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAILED", "expected_session": session, "observed_session": None,
                "reason": f"DASHBOARD_BUILD_INFO_UNREADABLE:{type(exc).__name__}:{exc}"}
    market_session = build_info.get("market_session")
    workspace_session = (build_info.get("investment_workspace") or {}).get("source_session")
    cockpit_session = (build_info.get("current_decision_cockpit") or {}).get("source_session")
    if market_session != session or workspace_session != session or cockpit_session != session:
        return {
            "status": "FAILED", "expected_session": session, "observed_session": market_session,
            "reason": ("DASHBOARD_SESSION_MISMATCH:"
                      f"build_info.market_session={market_session!r}:"
                      f"build_info.investment_workspace.source_session={workspace_session!r}:"
                      f"build_info.current_decision_cockpit.source_session={cockpit_session!r}"),
        }
    return {"status": "READY", "expected_session": session, "observed_session": market_session,
           "build_id": build_info.get("build_id")}


def publish_dashboard_release(root: Path, runtime_root: Path, session: str, *, web_dir: Path = DEFAULT_WEB_DIR,
                              complete_publication: bool = True,
                              producer_run_identity: str | None = None) -> dict[str, Any]:
    """Publish the EXACT resolved Daily session to the Dashboard via the existing governed
    `tools/release_orchestrator.py all --live` entry point -- never a second/new Dashboard
    publisher, and never a second "latest session" resolution: `session` is the only session
    this function ever passes downstream.

    Group ``all`` (not ``whole-market`` alone) is required: the Dashboard's own release-smoke
    gate (tests/release-smoke.test.js, "checked-out source session is coherent for public
    verification") fails closed whenever the trusted-ai bundle's own retained session diverges
    from the whole-market session being published -- a whole-market-only publish would leave a
    stale trusted-ai bundle next to a fresh market session. ``--complete-publication`` (default
    on) additionally requires Dashboard CI and Deploy Pages to pass on the exact pushed SHA and
    proves cache-busted public-byte identity before reporting PUBLISHED, per the governed
    vocabulary in governed_publication_completion.py -- the "prefer remote/public bytes over
    local files" verification this milestone asks for.

    Idempotent: `publish_dashboard.py` itself is a no-op commit/push when the whitelist is
    already byte-identical (see its own `Không có thay đổi; exit 0` path), so a replay of an
    already-published session performs no duplicate Dashboard commit.
    """
    # Completed-session replay skips Canonical Daily. Reuse its exact retained run through
    # `materialize_release_ready_runtime` -- the one governed release-ready runtime boundary
    # (sealed baseline + additive presentation-projection overlay, when one was retained; see
    # CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 2) -- then build
    # the exact trusted subset from that runtime, before the governed publisher validates either
    # release. Normal Daily reaches this same boundary after its canonical completion record is
    # verified, so neither route can send an unproven bundle_manifest downstream, and neither can
    # leave same-session Signal Velocity/Flow-Price erased by a second sealed-baseline copy.
    try:
        materialize_release_ready_runtime(
            root, runtime_root, session, producer_run_identity=producer_run_identity,
        )
    except CanonicalRuntimeReleaseError as exc:
        return {"status": "FAILED", "expected_session": session, "observed_session": None,
                "reason": f"CANONICAL_RUNTIME_MATERIALIZATION_FAILED:{exc}"}
    try:
        materialize_canonical_trusted_subset(root, runtime_root, session)
    except CanonicalTrustedSubsetError as exc:
        return {"status": "FAILED", "expected_session": session, "observed_session": None,
                "reason": f"CANONICAL_TRUSTED_SUBSET_MATERIALIZATION_FAILED:{exc}"}
    argv = [sys.executable, "-u", str(root / "tools" / "release_orchestrator.py"), "all",
           "--live", "--expected-session", session, "--backend-dir", str(runtime_root), "--web-dir", str(web_dir)]
    if complete_publication:
        argv.append("--complete-publication")
    result = subprocess.run(
        argv, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "")
        tail = output.strip()[-2000:]
        outcome = {"status": "FAILED", "expected_session": session, "observed_session": None,
                   "reason": f"RELEASE_ORCHESTRATOR_EXIT_{result.returncode}:{tail}"}
        recoverable = re.search(r"RECOVERABLE_RELEASE_SOURCE_SHA=([0-9a-fA-F]{40})", output)
        if recoverable:
            # A source push is recoverable evidence, never a successful publication.  Preserve
            # its exact SHA for an owner replay to resume CI/Pages/public-byte completion.
            outcome["publication_state"] = "GITHUB_SOURCE_UPDATED"
            outcome["recoverable_release_source_sha"] = recoverable.group(1)
        return outcome
    outcome = verify_dashboard_session(web_dir, session)
    outcome.update(_publication_facts_from_orchestrator_output(result.stdout or ""))
    attested = _bind_written_publication_attestation(root, session, outcome.get("release_source_sha"))
    if attested:
        outcome.update(attested)
    if complete_publication and outcome.get("publication_state") != "PUBLISHED":
        observed = outcome.get("publication_state") or "MISSING_PUBLICATION_STATE"
        outcome.update({
            "status": "FAILED",
            "reason": f"GOVERNED_PUBLICATION_COMPLETION_UNATTESTED:{observed}",
        })
    elif not complete_publication:
        outcome.setdefault("publication_state", "GITHUB_SOURCE_UPDATED")
    return outcome


_PUBLICATION_HANDOFF_KEYS = {
    "PUBLICATION_STATE": "publication_state",
    "DASHBOARD_RELEASE_SHA": "release_source_sha",
    "PUBLIC_BYTE_IDENTITY": "public_byte_identity",
    "ATTESTATION_IDENTITY": "attestation_identity",
    "CONTENT_IDENTITY": "content_identity",
}


def _publication_facts_from_orchestrator_output(stdout: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        mapped = _PUBLICATION_HANDOFF_KEYS.get(key.strip())
        if mapped:
            facts[mapped] = value.strip()
    return facts


def _bind_written_publication_attestation(
    producer_root: Path, session: str, release_source_sha: str | None,
) -> dict[str, Any] | None:
    if not release_source_sha:
        return None
    try:
        attested = verify_existing_publication_completion(
            producer_root, session=session, release_source_sha=release_source_sha,
        )
    except Exception:
        return None
    if not attested:
        return None
    bound = {
        "publication_state": attested.get("publication_state"),
        "release_source_sha": attested.get("release_source_sha"),
        "public_byte_identity": attested.get("public_byte_identity"),
    }
    if attested.get("attestation_identity"):
        bound["attestation_identity"] = attested["attestation_identity"]
    if attested.get("content_identity"):
        bound["content_identity"] = attested["content_identity"]
    return bound


def _run_daily(root: Path, runtime_root: Path) -> None:
    result = subprocess.run([sys.executable, "-u", "daily_analysis_pipeline.py", "--runtime-root", str(runtime_root),
                             "--canonical-post-close"], cwd=root, check=False)
    if result.returncode:
        raise OwnerDailyError("Canonical Daily", f"CANONICAL_DAILY_EXIT_{result.returncode}",
                              "Read the log; no state or AI publication was attempted.")


_DAILY_BRIEF_FILENAME = "daily_integrated_decision_brief_artifact.json"
_FULL_UNIVERSE_FILENAME = "ai_research_full_universe.ndjson"


def _handoff_brief_error(reason: str) -> OwnerDailyError:
    return OwnerDailyError("AI handoff build", reason,
                           "The retained Daily Integrated Decision Brief this operation declares is missing or "
                           "invalid; AI handoff was refused before publication. It is never recreated here.")


def _handoff_delivery_error(reason: str) -> OwnerDailyError:
    return OwnerDailyError("AI handoff build", reason,
                           "The retained AI delivery does not carry the exact Integrated Decision surface its "
                           "Brief index declares; AI handoff was refused before publication. It is never "
                           "repaired here.")


def _verify_m1_integrated_projection(label: str, ticker: Any, delivered: Any,
                                     index_rows: Mapping[str, Mapping[str, Any]], identity: Any) -> None:
    """M1_LIVE_ACCEPTANCE_CORRECTIVE_V1: one delivered ``integrated_decision_v1`` must be the
    exact decision-surface index row it projects -- same ticker, posture and evidence currency,
    bound to the same Integrated Decision, with the Integrated Decision's own position context."""
    expected = index_rows.get(ticker) if isinstance(ticker, str) else None
    if expected is None:
        raise _handoff_delivery_error(f"M1_AI_DELIVERY_TICKER_NOT_IN_DECISION_SURFACE_INDEX:{label}:{ticker}")
    if not isinstance(delivered, Mapping):
        raise _handoff_delivery_error(f"M1_AI_DELIVERY_INTEGRATED_DECISION_MISSING:{label}:{ticker}")
    if delivered.get("integrated_investment_decision_product_identity") != identity:
        raise _handoff_delivery_error(f"M1_AI_DELIVERY_INTEGRATED_DECISION_IDENTITY_MISMATCH:{label}:{ticker}")
    for key in ("ticker", "research_action_posture", "evidence_currency"):
        if delivered.get(key) != expected.get(key):
            raise _handoff_delivery_error(f"M1_AI_DELIVERY_DECISION_SURFACE_MISMATCH:{label}:{ticker}:{key}")
    if not isinstance(delivered.get("position_context"), Mapping):
        raise _handoff_delivery_error(f"M1_AI_DELIVERY_POSITION_CONTEXT_MISSING:{label}:{ticker}")


def _verify_m1_ai_delivery(source: Path, bundle: Mapping[str, Any], index_rows: Mapping[str, Mapping[str, Any]],
                           identity: Any) -> dict[str, int]:
    """Every AI-delivered Integrated Decision surface of an M1 operation -- scoped contexts,
    owner-focus contexts, and the full-universe companion (exactly one row per index ticker) --
    must equal the Brief's decision-surface index. Read-only; nothing is rebuilt."""
    cards = bundle.get("ticker_research_contexts")
    if not isinstance(cards, Mapping):
        raise _handoff_delivery_error("M1_AI_DELIVERY_TICKER_CONTEXTS_MISSING")
    for ticker, card in sorted(cards.items()):
        delivered = card.get("integrated_decision_v1") if isinstance(card, Mapping) else None
        _verify_m1_integrated_projection("ticker_research_contexts", ticker, delivered, index_rows, identity)
    owner_focus = bundle.get("owner_focus_research_contexts") or []
    for row in owner_focus:
        row = row if isinstance(row, Mapping) else {}
        _verify_m1_integrated_projection("owner_focus_research_contexts", row.get("ticker"),
                                         row.get("integrated_decision_v1"), index_rows, identity)
    path = source / _FULL_UNIVERSE_FILENAME
    if not path.is_file():
        raise _handoff_delivery_error("M1_AI_FULL_UNIVERSE_COMPANION_MISSING")
    seen: set[str] = set()
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                row = row if isinstance(row, Mapping) else {}
                ticker = row.get("ticker")
                if ticker in seen:
                    raise _handoff_delivery_error(f"M1_AI_FULL_UNIVERSE_DUPLICATE_TICKER:{ticker}")
                _verify_m1_integrated_projection("full_universe", ticker, row.get("integrated_decision_v1"),
                                                 index_rows, identity)
                seen.add(ticker)
    except (OSError, json.JSONDecodeError):
        raise _handoff_delivery_error("M1_AI_FULL_UNIVERSE_COMPANION_UNREADABLE") from None
    if seen != set(index_rows):
        raise _handoff_delivery_error(f"M1_AI_FULL_UNIVERSE_INDEX_SET_MISMATCH:rows={len(seen)}:index={len(index_rows)}")
    return {"ticker_research_contexts": len(cards), "owner_focus_research_contexts": len(owner_focus),
            "full_universe_rows": len(seen)}


def verify_retained_daily_brief_for_handoff(source: Path, session: str) -> dict[str, Any]:
    """PRE_DAILY_WORKSPACE_READINESS_CORRECTIVE_V1 (Phase C): close the M1 Brief/index false-PASS.

    The retained operation's OWN declarations decide what is required -- never the calendar:
    - it declares a Brief when ``run_manifest.json`` ``outputs.daily_integrated_decision_brief``
      or the session bundle's ``integrated_decision_overlay_v1.daily_integrated_decision_brief_identity``
      is set; the retained Brief file is then required, bound to the session and that identity;
    - it is an M1 (CURRENT_DECISION_SURFACE_CONVERGENCE_V1) operation when the overlay's copy of the
      Integrated Decision coverage carries ``evidence_currency_distribution``; the Brief's
      ``decision_surface_index`` is then required: denominator == the Integrated Decision's own
      ``universe_denominator`` == row count, every ticker exactly once, every row carrying ticker /
      research_action_posture / evidence_currency, bound to the same Integrated Decision identity,
      and zero NO_CURRENT_EVIDENCE + WAIT_FOR_CONFIRMATION rows;
    - for the same M1 operation, every AI-delivered ``integrated_decision_v1`` (scoped contexts,
      owner-focus contexts, and the full-universe companion, exactly one row per index ticker)
      must equal its index row and carry the Integrated Decision's position context
      (M1_LIVE_ACCEPTANCE_CORRECTIVE_V1);
    - a genuine pre-M1 operation that declares no Brief keeps the legacy behavior (no Brief file).
    Read-only; never builds or repairs a Brief. research_stance plays no role.
    """
    source = Path(source)
    manifest_path = source / "run_manifest.json"
    manifest = _load(manifest_path) if manifest_path.is_file() else {}
    bundle = _load(source / "ai_research_session_bundle.json")
    overlay = bundle.get("integrated_decision_overlay_v1")
    overlay = overlay if isinstance(overlay, Mapping) else {}
    coverage = overlay.get("coverage") if isinstance(overlay.get("coverage"), Mapping) else {}
    declared = [value for value in (((manifest.get("outputs") or {}).get("daily_integrated_decision_brief")),
                                    overlay.get("daily_integrated_decision_brief_identity")) if value]
    m1 = isinstance(coverage.get("evidence_currency_distribution"), Mapping)
    path = source / _DAILY_BRIEF_FILENAME
    if not declared and not m1:
        return {"status": "LEGACY_NO_BRIEF_DECLARED", "m1": False,
                "brief_path": path if path.is_file() else None}
    if m1 and not declared:
        raise _handoff_brief_error("M1_DAILY_BRIEF_NOT_DECLARED")
    if len(set(declared)) != 1:
        raise _handoff_brief_error("DAILY_BRIEF_DECLARED_IDENTITY_CONFLICT")
    if not path.is_file():
        raise _handoff_brief_error(("M1_" if m1 else "") + "DAILY_BRIEF_RETAINED_FILE_MISSING")
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise _handoff_brief_error("DAILY_BRIEF_UNREADABLE") from None
    brief = wrapper.get("daily_integrated_decision_brief") if isinstance(wrapper, Mapping) else None
    if not isinstance(brief, Mapping):
        brief = wrapper if isinstance(wrapper, Mapping) else None
    if not isinstance(brief, Mapping):
        raise _handoff_brief_error("DAILY_BRIEF_MALFORMED")
    if brief.get("session") != session or (isinstance(wrapper, Mapping) and wrapper.get("session") not in (None, session)):
        raise _handoff_brief_error("DAILY_BRIEF_SESSION_MISMATCH")
    if brief.get("artifact_identity") != declared[0]:
        raise _handoff_brief_error("DAILY_BRIEF_IDENTITY_MISMATCH")
    if not m1:
        return {"status": "DECLARED_BRIEF_VERIFIED", "m1": False, "brief_path": path,
                "brief_identity": declared[0]}

    index = brief.get("decision_surface_index")
    if not isinstance(index, Mapping) or not isinstance(index.get("rows"), list):
        raise _handoff_brief_error("M1_DECISION_SURFACE_INDEX_MISSING")
    rows = index["rows"]
    canonical = coverage.get("universe_denominator")
    if not isinstance(canonical, int) or isinstance(canonical, bool) or canonical <= 0:
        raise _handoff_brief_error("M1_CANONICAL_DENOMINATOR_UNAVAILABLE")
    if index.get("denominator") != canonical or len(rows) != canonical:
        raise _handoff_brief_error(f"M1_DECISION_SURFACE_INDEX_DENOMINATOR_MISMATCH:index={index.get('denominator')}"
                                   f":rows={len(rows)}:canonical={canonical}")
    if index.get("source_integrated_investment_decision_product_identity") != overlay.get("integrated_investment_decision_product_identity"):
        raise _handoff_brief_error("M1_DECISION_SURFACE_INDEX_SOURCE_IDENTITY_MISMATCH")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or not all(isinstance(row.get(key), str) and row.get(key)
                                                   for key in ("ticker", "research_action_posture", "evidence_currency")):
            raise _handoff_brief_error("M1_DECISION_SURFACE_INDEX_ROW_MALFORMED")
        if row["ticker"] in seen:
            raise _handoff_brief_error("M1_DECISION_SURFACE_INDEX_DUPLICATE_TICKER:" + row["ticker"])
        seen.add(row["ticker"])
        if row["evidence_currency"] == "NO_CURRENT_EVIDENCE" and row["research_action_posture"] == "WAIT_FOR_CONFIRMATION":
            raise _handoff_brief_error("M1_NO_CURRENT_EVIDENCE_WAIT_PRESENT:" + row["ticker"])
    ai_delivery = _verify_m1_ai_delivery(source, bundle, {row["ticker"]: row for row in rows},
                                         overlay.get("integrated_investment_decision_product_identity"))
    return {"status": "M1_BRIEF_AND_INDEX_VERIFIED", "m1": True, "brief_path": path,
            "brief_identity": declared[0], "decision_surface_index_denominator": canonical,
            "ai_delivery_parity": ai_delivery}


def publish_ai_handoff(root: Path, handoff_repo: Path, completion: Mapping[str, Any]) -> dict[str, Any]:
    from ai_handoff_publication import publish, verify_remote_publication
    from post_handoff_presentation_attestation import read_attestation
    preflight_repository(handoff_repo, expected_name="stocklookup-ai-handoffs", expected_remote_fragment="stocklookup-ai-handoffs")
    source = Path(completion["source"])
    needed = ("ai_research_session_bundle.json", "daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json")
    if any(not (source / name).is_file() for name in needed):
        raise OwnerDailyError("AI handoff build", "AI_HANDOFF_REQUIRED_FILE_MISSING")
    previous = None
    session = str(completion["session"])
    # A declared (and, for M1, index-bearing) Brief is required and verified before publication;
    # only a genuine pre-M1 operation that never declared one publishes without it.
    brief_check = verify_retained_daily_brief_for_handoff(source, session)
    daily_brief = brief_check["brief_path"]
    # Additive only -- see CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1
    # section 3. The dedicated attestation artifact (never the sealed Producer operation
    # directory `source` itself) is the sole input; a missing attestation (older session,
    # presentation never ran) simply publishes without this extra file, exactly as before.
    presentation_attestation = read_attestation(root, session)
    published = publish(handoff_repo, source, session,
                        producer_checkpoint=_git(root, "rev-parse", "HEAD"), push=True,
                        daily_integrated_decision_brief=daily_brief,
                        previous=previous,
                        post_handoff_presentation=presentation_attestation)
    return {"publication": published, "remote": verify_remote_publication(handoff_repo, published),
            "daily_brief_check": {key: (str(value) if isinstance(value, Path) else value)
                                  for key, value in brief_check.items()}}


def materialize_action_center(root: Path, session: str) -> dict[str, Any]:
    """Use the released local-only Action Center; it never enters either Git publication path."""
    import personal_investment_decision_action_center as action_center
    try:
        artifact = action_center.evaluate_from_retained_artifacts(
            repo_root=root, session=session, requested_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        json_path = action_center.write_private_artifact(artifact)
        markdown_path = action_center.write_markdown(artifact)
    except Exception as exc:  # The core Daily and AI handoff have already passed at this point.
        return {"status": "PARTIAL", "reason": f"ACTION_CENTER_MATERIALIZATION_FAILED:{type(exc).__name__}:{exc}"}
    return {
        "status": "READY", "session": artifact.get("session"),
        "portfolio_status": (artifact.get("portfolio") or {}).get("status"),
        "json_path": str(json_path), "view_path": str(markdown_path),
        "identity": artifact.get("artifact_identity"),
    }


def open_action_center_view(path: str) -> dict[str, str]:
    """Opening the local Markdown is convenience only, never a Daily data gate."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows owner launcher contract.
    except Exception as exc:
        return {"status": "READY_VIEW_OPEN_FAILED", "reason": f"VIEW_OPEN_FAILED:{type(exc).__name__}:{exc}"}
    return {"status": "READY"}


def _journal_start(root: Path, *, intended_session: str | None) -> str:
    """Fail-closed on the production owner path: a durable crash-resume journal MUST be
    initialized before any material work begins (git preflight, acquisition, ...) -- see
    CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 6. Raises
    ``OwnerDailyError`` (never silently returns) if the journal cannot be durably written, so
    the caller never runs an unjournaled owner workflow. Every LATER mid-run stage transition
    remains best-effort via ``_journal_advance`` below -- only this initial write, made before
    any material work, is a hard gate; a hard OS kill still cannot write a final terminal
    marker regardless, which is expected and unrelated to this gate.
    """
    try:
        return journal.start_run(root, intended_session=intended_session)["run_id"]
    except Exception as exc:
        raise OwnerDailyError(
            "Repository preflight", f"OWNER_JOURNAL_INITIALIZATION_FAILED:{type(exc).__name__}:{exc}",
            "A durable crash-resume journal could not be written before material work began. "
            "Resolve the underlying filesystem/permissions issue for "
            "operations-review/owner-daily-journal-v1/ and rerun.",
        ) from exc


def _journal_advance(root: Path, run_id: str | None, stage: str, **kwargs: Any) -> None:
    if run_id is None:
        return
    try:
        journal.advance(root, run_id, stage, **kwargs)
    except Exception:
        pass


def _journal_advance_strict(root: Path, run_id: str, stage: str, **kwargs: Any) -> None:
    """Fail-closed counterpart to `_journal_advance`, for stage transitions that GATE a
    subsequent external side effect (a Git push, a publication, materializing an artifact the
    owner will act on) -- see CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1
    section 3. For this production owner workflow, durable stage transitions are the crash/resume
    authority: if the durable write itself cannot be trusted, blindly continuing to the next side
    effect would leave the owner unable to tell, after a later crash, whether that side effect
    ever ran. Raises `OwnerDailyError` (never silently swallows, unlike `_journal_advance`) so the
    caller stops -- via `run_workflow`'s own outer exception handler, which still records FAILED
    best-effort -- before that next side effect is attempted.
    """
    try:
        journal.advance(root, run_id, stage, **kwargs)
    except Exception as exc:
        raise OwnerDailyError(
            "Owner journal", f"OWNER_JOURNAL_ADVANCE_FAILED:{stage}:{type(exc).__name__}:{exc}",
            "A durable owner-journal stage transition could not be recorded, so the next "
            "external side effect was never attempted. Resolve the underlying issue for "
            "operations-review/owner-daily-journal-v1/ and rerun; already-completed upstream "
            "work is independently reverified and reused, not redone.",
        ) from exc


def _resolve_intended_session(now: datetime | None = None) -> str | None:
    """Best-effort resolution of "what session would an ORDINARY fresh Daily invocation intend
    right now", using the same governed calendar contract already used elsewhere
    (``daily_session_level2_package.resolve_level2_session`` -> ``mva_exact_session_snapshot.
    resolved_completed_session``: pure weekday-calendar arithmetic, no network). This is used
    ONLY to decide whether a durable journal from a PRIOR invocation is safe to auto-resume as
    though it were THIS run -- never to select the session Canonical Daily itself acquires
    (that remains ``canonical_daily_operation``'s own session gate). A resolution failure here
    must never block Daily: ``_auto_resumable_session`` below treats ``None`` as "auto-resume
    cannot safely happen", not as license to fall back to the pre-fix unsafe behavior.
    """
    try:
        from daily_session_level2_package import resolve_level2_session
        return resolve_level2_session(None, now=now)["session"]
    except Exception:
        return None


def _auto_resumable_session(root: Path, runtime_root: Path, *, intended_session: str | None) -> str | None:
    """Read-only: if the durable owner journal shows an interrupted/partial run whose RESOLVED
    session already reached full canonical-Daily completion (LOCAL_COMPLETE/READY/READY -- the
    same gate an explicit ``--replay-completed-session`` already checks) AND that resolved
    session matches ``intended_session`` (today's session, per ``_resolve_intended_session``),
    return that session so the caller can resume publication from it instead of re-running
    acquisition and Daily Producer. Returns None (never raises) when there is nothing safely
    resumable -- the caller then runs a normal fresh Daily, exactly as it always has.

    ``intended_session=None`` (resolution itself failed) unconditionally disables auto-resume --
    it must never fall back to accepting ANY resolved session as resumable. See
    CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 1: a COMPLETE (or
    merely incomplete) journal for an OLDER session must never be silently replayed as today's
    Daily just because nothing else was asked -- ``journal.resumable_state`` already refuses to
    call a session resumable when its resolved session differs from ``intended_session``; this
    function's own pre-fix defect was calling it with ``intended_session=None``, which defeated
    that check entirely. Section 13: a session whose own analytical kernel never finished must
    never be treated as resumable by re-entering Daily Producer -- this only ever resumes from
    PUBLICATION onward, using the exact same completion gate a manual replay already uses.
    """
    if intended_session is None:
        return None
    try:
        state = journal.resumable_state(root, intended_session=intended_session)
    except Exception:
        return None
    if state.get("action") not in ("RESUME", "ALREADY_COMPLETE"):
        return None
    session = state.get("resolved_session")
    if not session:
        return None
    try:
        verify_daily_completion(root, runtime_root, session=session)
    except OwnerDailyError:
        return None
    return session


def _t0_snapshot_attestation(root: Path, completion: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the already-retained T0 snapshot identity. Never recomputes it."""
    record = completion.get("record") if isinstance(completion.get("record"), Mapping) else {}
    snapshot = record.get("prospective_decision_snapshot") if isinstance(record.get("prospective_decision_snapshot"), Mapping) else {}
    identity = snapshot.get("identity")
    status = snapshot.get("status")
    source_id = snapshot.get("source_integrated_decision_identity")
    if not identity:
        lineage = record.get("lineage") if isinstance(record.get("lineage"), Mapping) else {}
        identity = lineage.get("prospective_decision_snapshot")
    if not identity:
        bundle = _load_session_handoff_bundle(root, completion)
        declared = bundle.get("prospective_decision_snapshot") if isinstance(bundle, Mapping) else {}
        if isinstance(declared, Mapping):
            identity = declared.get("identity")
            status = status or declared.get("status")
            source_id = source_id or declared.get("source_integrated_decision_artifact_identity")
    if isinstance(identity, str) and identity:
        attested = {"status": status or "RETAINED", "identity": identity}
        if source_id:
            attested["source_integrated_decision_identity"] = source_id
        return attested
    return {"status": "UNAVAILABLE", "identity": None, "reason": "T0_SNAPSHOT_IDENTITY_NOT_RETAINED"}


def _load_session_handoff_bundle(root: Path, completion: Mapping[str, Any]) -> dict[str, Any] | None:
    candidates: list[Path] = []
    record = completion.get("record") if isinstance(completion.get("record"), Mapping) else {}
    relative = ((record.get("tiers") or {}) if isinstance(record.get("tiers"), Mapping) else {}).get("session_handoff_bundle")
    if relative:
        candidates.append(Path(root) / str(relative))
    source = completion.get("source")
    if source:
        candidates.append(Path(source) / "session_handoff_bundle.json")
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _dashboard_complete_attestation(dashboard: Mapping[str, Any], session: str) -> dict[str, Any]:
    return {
        "session": session,
        "status": dashboard.get("status"),
        "publication_state": dashboard.get("publication_state"),
        "release_source_sha": dashboard.get("release_source_sha"),
        "public_byte_identity": dashboard.get("public_byte_identity"),
        "attestation_identity": dashboard.get("attestation_identity"),
        "content_identity": dashboard.get("content_identity"),
        "build_id": dashboard.get("build_id"),
        "resume_status": dashboard.get("resume_status"),
    }


def _presentation_bound_state(root: Path, session: str) -> str:
    """UNKNOWN on any failure -- the caller must never record ``journal.PRESENTATION_BOUND`` on
    an unknown basis. See CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1
    section 4."""
    try:
        from post_handoff_presentation_attestation import presentation_bound_state, read_attestation
        return presentation_bound_state(read_attestation(root, session))
    except Exception:
        return "UNKNOWN"


# --- CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 4: genuine
# stage-aware resume. Each helper below is a READ-ONLY, independent re-derivation of "did this
# exact session's side effect already durably happen" from the real external system itself --
# never from the journal's own stage text, which is only ever used to decide whether Daily
# Producer acquisition itself may be skipped (see `_auto_resumable_session` above). A caller
# invokes the corresponding publish/materialize step only when the matching helper here returns
# None; this makes "journal stale/incomplete + external state already advanced" (section 5) and
# "verification fails -> resume from the earliest safe stage" (section 4) automatic side effects
# of always reconciling against truth, regardless of what the journal itself claims.
def _verify_dashboard_published(
    web_dir: Path,
    session: str,
    *,
    producer_root: Path | None = None,
    git_runner=None,
) -> dict[str, Any] | None:
    """Skip Dashboard publication only when independent governed publication proof
    already shows this exact session PUBLISHED on the current Dashboard origin/main
    SHA with public-byte identity PASS.

    Local ``build_info.json`` session equality is necessary and never sufficient.
    Journal text is never consulted. This helper never dispatches CI or Pages; a
    None result lets the existing idempotent publisher run again.
    """
    local = verify_dashboard_session(web_dir, session)
    if local.get("status") != "READY" or producer_root is None:
        return None
    try:
        release_sha = resolve_dashboard_origin_main_sha(web_dir, git_runner=git_runner)
        attested = verify_existing_publication_completion(
            producer_root, session=session, release_source_sha=release_sha,
        )
    except Exception:
        return None
    if not attested:
        return None
    return {
        "status": "READY",
        "expected_session": session,
        "observed_session": local.get("observed_session"),
        "build_id": local.get("build_id"),
        "publication_state": attested.get("publication_state"),
        "release_source_sha": attested.get("release_source_sha"),
        "public_byte_identity": attested.get("public_byte_identity"),
        "attestation_identity": attested.get("attestation_identity"),
        "content_identity": attested.get("content_identity"),
        "resume_status": "REUSED_EXISTING_PUBLICATION",
    }


def _verify_ai_handoff_published(handoff_repo: Path, session: str) -> dict[str, Any] | None:
    """Reuses the existing `preflight_repository` sync (the same one `publish_ai_handoff` itself
    calls first) to bring the local handoff checkout to a verified `origin/main`, then reads its
    `LATEST.json` pointer directly -- proof from the remote repository itself, never from journal
    text. Any failure (repo missing/dirty/unreachable, pointer unreadable) is "not verified",
    never an error: the caller simply republishes via the existing idempotent `publish_ai_handoff`
    contract, exactly as it already would with no prior journal at all."""
    try:
        preflight = preflight_repository(handoff_repo, expected_name="stocklookup-ai-handoffs",
                                         expected_remote_fragment="stocklookup-ai-handoffs")
        latest = json.loads((handoff_repo / "LATEST.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(latest, dict) or latest.get("status") != "READY_FOR_AI" or latest.get("latest_session") != session:
        return None
    return {"remote_sha": preflight["head"], "latest_session": session, "handoff_build_id": latest.get("handoff_build_id")}


def _verify_action_center_ready(session: str, *, root: Path | None = None) -> dict[str, Any] | None:
    """Reads the exact-session Action Center artifact the way `materialize_action_center` itself
    writes it (`personal_investment_decision_action_center.write_private_artifact`/
    `write_markdown`) and confirms both files exist and the JSON payload is genuinely addressed
    to `session` with a real identity -- never merely that a file of that name is present."""
    import personal_investment_decision_action_center as action_center
    base = root or action_center.default_action_center_root()
    json_path = base / session / "personal_investment_decision_action_center_v1.json"
    markdown_path = base / session / "personal_investment_decision_action_center.md"
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (not isinstance(payload, dict) or payload.get("session") != session
            or not payload.get("artifact_identity") or not markdown_path.is_file()):
        return None
    return {"status": "READY", "session": session, "portfolio_status": (payload.get("portfolio") or {}).get("status"),
           "json_path": str(json_path), "view_path": str(markdown_path), "identity": payload.get("artifact_identity")}


def run_workflow(*, root: Path = ROOT, runtime_root: Path = DEFAULT_RUNTIME,
                 handoff_repo: Path = DEFAULT_HANDOFF_REPO, dashboard_web_dir: Path = DEFAULT_WEB_DIR,
                 publish_dashboard: bool = True, dashboard_complete_publication: bool = True,
                 replay_completed_session: str | None = None) -> dict[str, Any]:
    root, runtime_root, handoff_repo = root.resolve(), runtime_root.resolve(), handoff_repo.resolve()
    dashboard_web_dir = dashboard_web_dir.resolve()

    # Read the PRE-EXISTING journal (if any) before superseding it below -- this is the only
    # source of "was a session interrupted mid-publication last time" this invocation has.
    auto_resumed = False
    intended_session = replay_completed_session
    if not replay_completed_session:
        intended_session = _resolve_intended_session()
        prior_journal = journal.read_journal(root)
        auto_session = _auto_resumable_session(root, runtime_root, intended_session=intended_session)
        if auto_session:
            replay_completed_session = auto_session
            intended_session = auto_session
            auto_resumed = True
        elif (prior_journal is not None and prior_journal.get("stage") != journal.COMPLETE
              and prior_journal.get("resolved_session") not in (None, intended_session)):
            # An earlier invocation left an INCOMPLETE journal for a DIFFERENT (older) session --
            # this run must never silently replay it as today's Daily (section 1). Superseding it
            # with a fresh run is the existing, already-governed behavior (`start_run` always
            # supersedes); this only makes the abandoned state visible on the console/log instead
            # of silent, per section 1's "surface explicitly" requirement.
            print("STATUS: SUPERSEDING_INCOMPLETE_PRIOR_OWNER_RUN")
            print(f"PRIOR_RUN_SESSION: {prior_journal.get('resolved_session')}")
            print(f"PRIOR_RUN_STAGE: {prior_journal.get('stage')}")
            print(f"PRIOR_RUN_ID: {prior_journal.get('run_id')}")
            print(f"NEW_INTENDED_SESSION: {intended_session}")

    run_id = _journal_start(root, intended_session=intended_session)
    try:
        # SESSION_RESOLVED must be durable BEFORE any material work begins (repository preflight,
        # acquisition, ...) -- see section 2. When the exact session is already definitively known
        # (an explicit replay, or a verified auto-resume) it is recorded immediately, with its
        # resolved_session set. A genuinely fresh acquisition only has a calendar-arithmetic
        # INTENDED value at this point -- never authoritative until Daily Producer's own gate
        # confirms it below -- so the stage is marked reached now, but resolved_session is filled
        # in once that confirmation exists (right after `_run_daily`), so this can never record a
        # resolved_session a later confirmation might contradict.
        if replay_completed_session:
            _journal_advance_strict(root, run_id, journal.SESSION_RESOLVED, resolved_session=replay_completed_session)
        else:
            # `intended_session` (when resolved at all) is only a calendar-arithmetic ESTIMATE of
            # what a fresh acquisition intends -- it may legitimately differ from what Daily
            # Producer's own gate eventually confirms below (see `_resolve_intended_session`'s own
            # docstring). Pre-setting `resolved_session` here to that estimate would make the
            # confirmation call below raise JOURNAL_SESSION_IDENTITY_MISMATCH on any such benign
            # divergence -- so only the STAGE is marked reached now; resolved_session is filled in
            # exactly once, from the one authoritative source, right after `_run_daily` confirms it.
            _journal_advance_strict(root, run_id, journal.SESSION_RESOLVED)

        # A replay/verified auto-resume may carry the governed Daily registry as its sole pending
        # diff (kernel completed, then interrupted before `commit_daily_state`); a fresh Daily
        # passes completed_session=None and keeps the strict clean-checkout contract.
        producer = preflight_repository(root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private",
                                        completed_session=replay_completed_session, runtime_root=runtime_root)
        # The Consumer checkout whose code Daily and the release path execute is governed before
        # any analytical work too (fresh Daily and replay/resume alike).
        consumer_preflight = preflight_consumer_repository(consumer_root_for(root), producer_root=root)
        # The canonical Dashboard checkout must be publishable before analytical work starts:
        # a stale-but-clean checkout is fast-forwarded here, a dirty/ahead/diverged one stops
        # Daily now instead of failing Dashboard publication after the whole Daily.
        dashboard_preflight = (preflight_dashboard_repository(dashboard_web_dir) if publish_dashboard
                               else {"status": "SKIPPED", "reason": "DASHBOARD_PUBLICATION_DISABLED"})

        if replay_completed_session:
            completion = verify_daily_completion(root, runtime_root, session=replay_completed_session)
            daily_status = "ALREADY_COMPLETED / RESUMED" if auto_resumed else "ALREADY_COMPLETED / REUSED"
        else:
            _run_daily(root, runtime_root)
            completion = verify_daily_completion(root, runtime_root)
            daily_status = "COMPLETED"
            _journal_advance_strict(root, run_id, journal.SESSION_RESOLVED, resolved_session=str(completion["session"]))
        _journal_advance_strict(root, run_id, journal.LOCAL_COMPLETE, resolved_session=str(completion["session"]))

        # Section 4.B: `commit_daily_state` is already its own independent verification -- it
        # reads real tracked Git state and only commits/pushes a genuine diff, returning NO_CHANGE
        # (never a duplicate commit) when the registry already reflects this session as retained.
        # Calling it unconditionally on resume both re-verifies and skips redundant Git mutation
        # in one already-governed step; see PRODUCER_STATE_RETAINED's existing tests.
        producer_state = commit_daily_state(root, str(completion["session"]))
        _journal_advance_strict(root, run_id, journal.PRODUCER_STATE_RETAINED)

        # Presentation binding (Signal Velocity / Flow-Price additively joined into the
        # Workspace/Screener presentation) happens inside canonical_daily_operation.py itself,
        # before this workflow ever sees a completed session. This stage may only be recorded
        # when the dedicated attestation artifact proves a real, verifiable outcome (BOUND or a
        # legitimate UNAVAILABLE) -- never merely because the kernel was expected to have
        # attempted it (section 4). An UNKNOWN outcome (older session, attestation never written,
        # or corrupt) must never reach owner COMPLETE (section 1): publication is refused before
        # it starts -- core analytical Daily and the governed registry commit above are already
        # durable (LOCAL_COMPLETE / PRODUCER_STATE_RETAINED), only the owner's own terminal result
        # is withheld.
        session = str(completion["session"])
        presentation_state = _presentation_bound_state(root, session)
        if presentation_state == "UNKNOWN":
            _journal_advance(root, run_id, journal.BLOCKED, detail={
                "reason": "PRESENTATION_UNKNOWN_CANNOT_COMPLETE", "presentation_state": presentation_state,
            })
            return {"status": "BLOCKED", "session": completion["session"], "daily_status": daily_status,
                    "producer_preflight": producer, "dashboard_preflight": dashboard_preflight, "consumer_preflight": consumer_preflight, "producer_state": producer_state,
                    "presentation_state": presentation_state, "reason": "PRESENTATION_UNKNOWN_CANNOT_COMPLETE",
                    "hint": "The dedicated post-handoff presentation attestation for this session is missing or "
                            "does not yet prove BOUND/LEGITIMATE_UNAVAILABLE. Publication was refused before it "
                            "started; rerun once the attestation is written.",
                    "journal_run_id": run_id}
        _journal_advance_strict(root, run_id, journal.PRESENTATION_BOUND, detail={"presentation_state": presentation_state})

        # WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: publish the exact
        # resolved Daily session to the Dashboard via the existing governed release path before
        # AI handoff / Action Center -- a successful Daily must never leave the owner-facing
        # Dashboard on a stale session. A Dashboard failure does not block the independent
        # downstream steps below; it degrades the final status to PARTIAL instead (see main()).
        # Section 4.D: before re-running the (expensive, side-effecting) release pipeline, an
        # independent verification first checks whether governed publication completion already
        # proves this exact session PUBLISHED on the current Dashboard origin/main SHA with
        # public-byte identity PASS. Local build_info session equality is never enough, and
        # journal DASHBOARD_PUBLISHED is never consulted.
        if not publish_dashboard:
            dashboard = {"status": "SKIPPED", "expected_session": session, "observed_session": None,
                        "reason": "DASHBOARD_PUBLICATION_DISABLED"}
        else:
            verified_dashboard = _verify_dashboard_published(
                dashboard_web_dir, session, producer_root=root,
            )
            dashboard = verified_dashboard if verified_dashboard is not None else publish_dashboard_release(
                root, runtime_root, session, web_dir=dashboard_web_dir,
                producer_run_identity=completion["record"]["daily_producer_run_identity"],
                complete_publication=dashboard_complete_publication,
            )
        if dashboard["status"] in {"READY", "SKIPPED"}:
            _journal_advance_strict(root, run_id, journal.DASHBOARD_PUBLISHED, detail={"status": dashboard["status"]})

        # Section 4.E: same pattern -- verify the AI handoff repo's own `origin/main` LATEST.json
        # pointer before republishing; `publish_ai_handoff` is itself already idempotent
        # (NO_OP_ALREADY_PUBLISHED), but this additionally skips its `git fetch`/remote-verify
        # network round trip entirely once independently proven.
        verified_handoff = _verify_ai_handoff_published(handoff_repo, session)
        handoff = ({"publication": {"status": "ALREADY_PUBLISHED_VERIFIED"}, "remote": verified_handoff}
                  if verified_handoff is not None else publish_ai_handoff(root, handoff_repo, completion))
        _journal_advance_strict(root, run_id, journal.AI_HANDOFF_PUBLISHED,
                         detail={"remote_sha": (handoff.get("remote") or {}).get("remote_sha")})

        # Section 4.F: same pattern for the local-only Action Center artifact.
        verified_action_center = _verify_action_center_ready(session)
        action_center = verified_action_center if verified_action_center is not None else materialize_action_center(root, session)
        if action_center["status"] != "PARTIAL":
            _journal_advance_strict(root, run_id, journal.ACTION_CENTER_READY, detail={"status": action_center["status"]})

        dashboard_failed = dashboard["status"] not in {"READY", "SKIPPED"}
        if action_center["status"] == "PARTIAL" or dashboard_failed:
            _journal_advance(root, run_id, journal.BLOCKED, detail={
                "dashboard_failed": dashboard_failed, "action_center_status": action_center["status"],
            })
            return {"status": "PARTIAL", "session": completion["session"], "daily_status": daily_status,
                    "producer_preflight": producer, "dashboard_preflight": dashboard_preflight, "consumer_preflight": consumer_preflight, "producer_state": producer_state,
                    "dashboard": dashboard, "ai_handoff": handoff, "action_center": action_center,
                    "journal_run_id": run_id}
        action_center["view_open"] = open_action_center_view(str(action_center["view_path"]))
        # OWNER_COMPLETE_ATTESTATION: the durable, single terminal record of every identity a
        # PASS is supposed to attest -- see CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_
        # PRESENTATION_JOIN_V1 section 11. Observer/presentation availability itself never needs
        # to be COLLECTED to PASS (a legitimate UNAVAILABLE is fine); this only records whatever
        # each step actually reported. Presentation identities are read from the dedicated
        # attestation artifact (never `record` -- the immutable `daily_operation_record.json`
        # deliberately excludes these volatile post-handoff fields; reading them from there was
        # exactly the pre-fix section-4 defect, which silently made this key always None/absent).
        record = completion.get("record") or {}
        presentation_attestation = None
        try:
            from post_handoff_presentation_attestation import read_attestation as _read_attestation
            presentation_attestation = _read_attestation(root, str(completion["session"]))
        except Exception:
            presentation_attestation = None
        presentation_projection = (presentation_attestation or {}).get("presentation_projection") or {}
        signal_velocity = (presentation_attestation or {}).get("signal_velocity") or {}
        flow_price = (presentation_attestation or {}).get("flow_price_divergence_shadow") or {}
        post_handoff_feedback = (presentation_attestation or {}).get("post_handoff_prospective_decision_feedback") or {}
        runtime_restage = (presentation_attestation or {}).get("runtime_restage") or {}
        _journal_advance_strict(root, run_id, journal.COMPLETE, detail={
            "session": str(completion["session"]),
            "canonical_daily_operation_identity": record.get("operation_identity"),
            "daily_producer_run_identity": record.get("daily_producer_run_identity"),
            "daily_producer_operation_identity": record.get("daily_producer_operation_identity"),
            "t0_snapshot": _t0_snapshot_attestation(root, completion),
            "producer_state_retained": producer_state.get("status"),
            "consumer_preflight": {"head": consumer_preflight.get("head"), "status": consumer_preflight.get("status")},
            "presentation_bound_state": presentation_state,
            "post_handoff_presentation_projection": {
                "status": presentation_projection.get("status"),
                "lineage_status": presentation_projection.get("lineage_status"),
                "workspace_artifact_identity": presentation_projection.get("workspace_artifact_identity"),
                "sealed_producer_workspace_artifact_identity": (presentation_attestation or {}).get("sealed_producer_workspace_artifact_identity"),
            },
            "signal_velocity": {"status": signal_velocity.get("status"), "identity": signal_velocity.get("artifact_identity")},
            "flow_price_divergence_shadow": {"status": flow_price.get("status"), "identity": flow_price.get("artifact_identity")},
            "post_handoff_prospective_decision_feedback": {"status": post_handoff_feedback.get("status"), "identity": post_handoff_feedback.get("artifact_identity")},
            "final_runtime_presentation": {"status": runtime_restage.get("status"), "identity": runtime_restage.get("artifact_identity")},
            "dashboard": _dashboard_complete_attestation(dashboard, session),
            "ai_handoff": {"session": session, "remote_sha": (handoff.get("remote") or {}).get("remote_sha"),
                           "handoff_build_id": (handoff.get("remote") or {}).get("handoff_build_id")},
            "action_center": {"session": session, "status": action_center.get("status"), "identity": action_center.get("identity")},
        })
        return {"status": "PASS", "session": completion["session"], "daily_status": daily_status,
                "producer_preflight": producer, "dashboard_preflight": dashboard_preflight, "consumer_preflight": consumer_preflight, "producer_state": producer_state,
                "dashboard": dashboard, "ai_handoff": handoff, "action_center": action_center,
                "journal_run_id": run_id}
    except BaseException as exc:
        _journal_advance(root, run_id, journal.INTERRUPTED if isinstance(exc, KeyboardInterrupt) else journal.FAILED,
                         detail={"reason": f"{type(exc).__name__}:{exc}"})
        raise


def validate_result_path(result_path: Path, *, root: Path) -> Path:
    """Refuse a ``--result-path`` inside the Producer checkout before any workflow work runs.

    A result file written inside the checkout is an untracked, non-governed path, so the NEXT
    Daily/replay's own repository preflight refuses it as UNSAFE_UNTRACKED_CHECKOUT -- the CLI
    would poison its own next run. Normalizes ``..``/symlinks and compares case-insensitively on
    Windows. Pure check: never creates the file or any parent directory.
    """
    resolved = Path(os.path.abspath(Path(result_path).expanduser())).resolve(strict=False)
    checkout = Path(root).resolve(strict=False)
    candidate, base = os.path.normcase(str(resolved)), os.path.normcase(str(checkout))
    if candidate == base or candidate.startswith(base.rstrip(os.sep) + os.sep):
        raise OwnerDailyError("Result path preflight", "RESULT_PATH_INSIDE_PRODUCER_CHECKOUT:" + str(resolved),
                              "Write the owner result outside the Producer checkout, e.g. "
                              r"C:\Projects\StockLookup\owner-daily-run-logs\<run>.result.json.")
    return resolved


def default_result_path(*, root: Path = ROOT, log_root: Path | None = None, now: datetime | None = None) -> Path:
    """The one Python-owned owner result-path resolver (PRE_DAILY_WORKSPACE_READINESS_CORRECTIVE_V1).

    Every Python entrypoint that starts the production Owner Daily (``stocklookup.py daily``)
    takes its ``--result-path`` from here, so it can never drift from ``validate_result_path``
    again. Defaults to the external workspace-level ``run-logs`` directory the desktop launcher
    (tools/run_owner_daily.ps1) already uses, with the same file name pattern. The returned path
    is validated against ``root`` before it is handed out; nothing is created on disk.
    """
    base = Path(log_root) if log_root is not None else Path(root).resolve().parent / "run-logs"
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return validate_result_path(base / f"stock_lookup_daily_{stamp}.result.json", root=root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--handoff-repo", type=Path, default=DEFAULT_HANDOFF_REPO)
    parser.add_argument("--dashboard-web-dir", type=Path, default=DEFAULT_WEB_DIR,
                        help="Dashboard checkout to publish the exact resolved Daily session into.")
    parser.add_argument("--no-publish-dashboard", action="store_true",
                        help="Skip the Dashboard publication step entirely (diagnostic/offline use only).")
    parser.add_argument("--no-complete-publication", action="store_true",
                        help="Skip Dashboard CI/Deploy Pages/public-byte-identity verification after push "
                             "(faster, but only proves the source push, not PUBLISHED).")
    parser.add_argument("--replay-completed-session", default=None, help="Validate/publish an already completed session without acquisition.")
    parser.add_argument("--result-path", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_result_path(args.result_path, root=ROOT)
    except OwnerDailyError as exc:
        # No result file is written: the only requested location is the one being refused.
        print(f"OWNER_DAILY_RESULT_PATH_REJECTED={exc.reason}", file=sys.stderr)
        print(f"HINT: {exc.hint}", file=sys.stderr)
        return 1
    result: dict[str, Any]
    code = 0
    reraise: BaseException | None = None
    try:
        result = run_workflow(runtime_root=args.runtime_root, handoff_repo=args.handoff_repo,
                              dashboard_web_dir=args.dashboard_web_dir,
                              publish_dashboard=not args.no_publish_dashboard,
                              dashboard_complete_publication=not args.no_complete_publication,
                              replay_completed_session=args.replay_completed_session)
        if result["status"] in ("PARTIAL", "BLOCKED"):
            code = 3
    except OwnerDailyError as exc:
        code = 1
        result = {"status": "FAILED", "failed_step": exc.step, "reason": exc.reason, "hint": exc.hint}
    except KeyboardInterrupt as exc:
        # The owner (or the console itself) cut the run short. Record what we can before the
        # interrupt propagates, so this is never a bare log with no matching result.json.
        code = 130
        result = {"status": "INTERRUPTED", "failed_step": "UNKNOWN", "reason": "KEYBOARD_INTERRUPT",
                  "hint": "The run was stopped (Ctrl+C or console close) before reaching a known gate. "
                          "Read the log for the last completed step, then rerun; already-completed "
                          "work upstream of the interrupted step is reused, not redone."}
        reraise = exc
    except Exception as exc:  # noqa: BLE001 -- last resort so a bug here still leaves a result.
        # Keep the traceback visible in the tee'd log exactly as an uncaught exception normally
        # would, but no longer let it also swallow the result file the owner depends on.
        traceback.print_exc()
        code = 2
        result = {"status": "INTERRUPTED", "failed_step": "UNKNOWN",
                  "reason": f"UNCAUGHT_EXCEPTION:{type(exc).__name__}:{exc}",
                  "hint": "An unexpected error interrupted Daily outside any known gate. Read the "
                          "log for the traceback; already-completed work upstream of the "
                          "interrupted step is reused, not redone, on rerun."}
    args.result_path.parent.mkdir(parents=True, exist_ok=True)
    args.result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("OWNER_DAILY_RESULT=" + str(args.result_path))
    if reraise is not None:
        raise reraise
    return code


if __name__ == "__main__":
    raise SystemExit(main())
