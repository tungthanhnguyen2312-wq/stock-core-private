"""Governed Dashboard CI → Pages → public-byte completion for release_orchestrator.

This is not a second release orchestrator. ``release_orchestrator.py all --live
--complete-publication`` remains the only live-publish entry point; this module owns
the remote completion gates that used to be manual ``gh`` steps.

Automatic GitHub triggers stay defense in depth. This path succeeds even when
push→CI or CI→Pages events are missed, by reusing exact-SHA proof or dispatching
the existing manual fallbacks at most once per invocation.

``gh`` is invoked only through argument arrays (``shell=False``). Credentials are
never printed. GitHub run IDs belong to an external attestation identity, not a
deterministic research content identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from atomic_io import atomic_write_json, validate_json_file
from field_temporal_contract import stable_id
from release_checkout_identity import (
    CANONICAL_BRANCH,
    CANONICAL_ORIGIN_REPO,
    PUBLISHED,
    is_test_fixture,
    origin_is_canonical,
)

CONTRACT_VERSION = "governed_publication_completion/v1"
CI_WORKFLOW = "dashboard-ci.yml"
CI_NAME = "Dashboard CI"
PAGES_WORKFLOW = "deploy-pages.yml"
PAGES_NAME = "Deploy Pages"
DEFAULT_WATCH_TIMEOUT_SECONDS = 3600
PUBLIC_BYTE_PASS_RE = re.compile(
    r"PUBLIC_BYTE_IDENTITY_PASS(?:\s+attempt=(?P<attempt>\d+))?"
    r"\s+session=(?P<session>\d{4}-\d{2}-\d{2})"
    r"\s+sha=(?P<sha>[0-9a-fA-F]{40})"
)
MANUAL_PAGES_GATE_RE = re.compile(
    r"MANUAL_DISPATCH_CI_GATE_PASS\s+run_id=(?P<run_id>\d+)\s+sha=(?P<sha>[0-9a-fA-F]{40})"
)
IN_PROGRESS_STATUSES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})
AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
}

GhRunner = Callable[..., subprocess.CompletedProcess]


class PublicationCompletionError(RuntimeError):
    """Fail-closed remote publication completion refusal."""

    def __init__(self, code: str, message: str | None = None, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(message or code)


def _watch_timeout() -> float:
    raw = os.environ.get("STOCK_LOOKUP_PUBLICATION_WATCH_TIMEOUT", "").strip()
    if raw:
        return float(raw)
    return float(DEFAULT_WATCH_TIMEOUT_SECONDS)


def which_gh() -> str | None:
    return shutil.which("gh")


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _gh_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GH_PAGER"] = "cat"
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    env["NO_COLOR"] = "1"
    env["CLICOLOR"] = "0"
    return env


def run_gh(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float | None = None,
    runner: GhRunner | None = None,
) -> subprocess.CompletedProcess:
    argv = ["gh", *[str(item) for item in args]]
    if runner is not None:
        return runner(argv, cwd=cwd, timeout=timeout)
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=timeout,
        check=False,
        env=_gh_env(),
    )


def _decode_json(payload: str, code: str) -> Any:
    text = _ANSI_RE.sub("", payload or "").strip()
    try:
        return json.loads(text or "null")
    except json.JSONDecodeError as exc:
        preview = text[:200].replace("\n", " ")
        raise PublicationCompletionError(code, f"{code}: malformed gh JSON: {preview!r}") from exc


def gh_preflight(
    web_dir: Path,
    *,
    runner: GhRunner | None = None,
    git_runner: Callable[..., tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Verify gh, auth, Dashboard remote, and main before any remote follow-up."""
    executable = which_gh()
    if not executable:
        raise PublicationCompletionError(
            "BLOCKED_GH_UNAVAILABLE",
            "BLOCKED_GH_UNAVAILABLE: install and authenticate GitHub CLI `gh`, then retry.",
        )
    auth = run_gh(["auth", "status"], cwd=web_dir, runner=runner)
    if auth.returncode != 0:
        raise PublicationCompletionError(
            "BLOCKED_GH_AUTH",
            "BLOCKED_GH_AUTH: `gh auth status` failed. Authenticate gh locally; no token is accepted here.",
        )
    git = git_runner or _git
    rc_origin, origin_url = git(web_dir, ["remote", "get-url", "origin"])
    if rc_origin != 0 or not origin_is_canonical(origin_url):
        raise PublicationCompletionError(
            "BLOCKED_DASHBOARD_REMOTE_MISMATCH",
            f"BLOCKED_DASHBOARD_REMOTE_MISMATCH: origin must be {CANONICAL_ORIGIN_REPO}.",
            origin_url=origin_url,
        )
    rc_branch, branch = git(web_dir, ["branch", "--show-current"])
    if rc_branch != 0 or branch != CANONICAL_BRANCH:
        raise PublicationCompletionError(
            "BLOCKED_DASHBOARD_REMOTE_MISMATCH",
            f"BLOCKED_DASHBOARD_REMOTE_MISMATCH: branch must be {CANONICAL_BRANCH}.",
            branch=branch,
        )
    return {
        "gh": executable,
        "origin_url": origin_url,
        "branch": branch,
        "repository": CANONICAL_ORIGIN_REPO,
    }


def _git(web_dir: Path, args: Sequence[str]) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *[str(item) for item in args]],
        cwd=web_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    return result.returncode, (result.stdout or "").strip()


def _fetch_origin_main(web_dir: Path, git: Callable[..., tuple[int, str]]) -> None:
    if is_test_fixture(web_dir):
        return
    rc, output = git(web_dir, ["fetch", "origin", CANONICAL_BRANCH])
    if rc != 0:
        raise PublicationCompletionError(
            "BLOCKED_DASHBOARD_REMOTE_MISMATCH",
            "BLOCKED_DASHBOARD_REMOTE_MISMATCH: git fetch origin main failed.",
            detail=output,
        )


def resolve_release_source_sha(
    web_dir: Path,
    *,
    explicit_sha: str | None = None,
    git_runner: Callable[..., tuple[int, str]] | None = None,
    require_identical_main: bool = True,
) -> str:
    git = git_runner or _git
    _fetch_origin_main(web_dir, git)
    rc_head, head = git(web_dir, ["rev-parse", "HEAD"])
    rc_main, origin_main = git(web_dir, ["rev-parse", f"origin/{CANONICAL_BRANCH}"])
    if rc_head != 0 or rc_main != 0 or not head or not origin_main:
        raise PublicationCompletionError("BLOCKED_DASHBOARD_REMOTE_MISMATCH", "cannot resolve Dashboard HEAD/origin/main")
    sha = (explicit_sha or head).strip()
    if len(sha) != 40:
        raise PublicationCompletionError("BLOCKED_DASHBOARD_REMOTE_MISMATCH", "release source SHA must be 40 hex characters")
    if require_identical_main:
        if head != sha or origin_main != sha:
            raise PublicationCompletionError(
                "BLOCKED_DASHBOARD_MAIN_ADVANCED",
                "BLOCKED_DASHBOARD_MAIN_ADVANCED: new publication requires HEAD == origin/main == RELEASE_SOURCE_SHA.",
                head=head,
                origin_main=origin_main,
                release_source_sha=sha,
            )
    else:
        relationship = classify_main_lineage(web_dir, sha, git_runner=git)
        if relationship not in {"IDENTICAL", "AHEAD"}:
            raise PublicationCompletionError(
                "BLOCKED_DASHBOARD_MAIN_ADVANCED",
                "BLOCKED_DASHBOARD_MAIN_ADVANCED: source SHA is not on current main lineage.",
                head=head,
                origin_main=origin_main,
                release_source_sha=sha,
                relationship=relationship,
            )
    return sha


def classify_main_lineage(
    web_dir: Path,
    source_sha: str,
    *,
    git_runner: Callable[..., tuple[int, str]] | None = None,
) -> str:
    git = git_runner or _git
    _fetch_origin_main(web_dir, git)
    rc_main, origin_main = git(web_dir, ["rev-parse", f"origin/{CANONICAL_BRANCH}"])
    if rc_main != 0 or not origin_main:
        return "UNKNOWN"
    if origin_main == source_sha:
        return "IDENTICAL"
    rc, _ = git(web_dir, ["merge-base", "--is-ancestor", source_sha, origin_main])
    if rc == 0:
        return "AHEAD"
    return "NOT_ON_MAIN_LINEAGE"


def parse_public_byte_proof(log_text: str) -> dict[str, Any] | None:
    match = PUBLIC_BYTE_PASS_RE.search(log_text or "")
    if not match:
        return None
    return {
        "status": "PASS",
        "attempt": match.group("attempt"),
        "session": match.group("session"),
        "sha": match.group("sha").lower(),
        "line": match.group(0),
    }


def _run_name(row: Mapping[str, Any]) -> str:
    return str(row.get("name") or row.get("workflowName") or "")


def _is_ci_row(row: Mapping[str, Any], source_sha: str) -> bool:
    return (
        _run_name(row) == CI_NAME
        and str(row.get("headBranch") or "") == CANONICAL_BRANCH
        and str(row.get("headSha") or "").lower() == source_sha.lower()
    )


def _is_pages_row(row: Mapping[str, Any]) -> bool:
    return _run_name(row) == PAGES_NAME


def list_workflow_runs(
    workflow: str,
    *,
    cwd: Path,
    commit: str | None = None,
    runner: GhRunner | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    args: list[str] = [
        "run", "list",
        "--workflow", workflow,
        "--limit", str(limit),
        "--json", "databaseId,headSha,status,conclusion,name,event,headBranch,url,displayTitle,workflowName,createdAt,number",
    ]
    if commit:
        args.extend(["--commit", commit])
        args.extend(["--branch", CANONICAL_BRANCH])
    result = run_gh(args, cwd=cwd, runner=runner)
    if result.returncode != 0:
        raise PublicationCompletionError(
            "BLOCKED_GH_UNAVAILABLE",
            f"gh run list failed for {workflow}",
            stderr=(result.stderr or "")[:500],
        )
    payload = _decode_json(result.stdout, "BLOCKED_GH_UNAVAILABLE")
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise PublicationCompletionError("BLOCKED_GH_UNAVAILABLE", "gh run list did not return a JSON array")
    return [row for row in payload if isinstance(row, dict)]


def run_logs(run_id: int | str, *, cwd: Path, runner: GhRunner | None = None) -> str:
    result = run_gh(["run", "view", str(run_id), "--log"], cwd=cwd, runner=runner)
    if result.returncode != 0:
        return (result.stdout or "") + (result.stderr or "")
    return result.stdout or ""


def watch_run(
    run_id: int | str,
    *,
    cwd: Path,
    runner: GhRunner | None = None,
    timeout: float | None = None,
    stage: str,
) -> None:
    try:
        result = run_gh(
            ["run", "watch", str(run_id), "--exit-status"],
            cwd=cwd,
            runner=runner,
            timeout=_watch_timeout() if timeout is None else timeout,
        )
    except subprocess.TimeoutExpired as exc:
        code = "BLOCKED_CI_TIMEOUT" if stage == "ci" else "BLOCKED_PAGES_TIMEOUT" if stage == "pages" else "BLOCKED_REMOTE_TIMEOUT"
        raise PublicationCompletionError(
            code,
            f"{code}: gh run watch timed out for {stage} run {run_id}",
            run_id=str(run_id),
            stage=stage,
        ) from exc
    if result.returncode != 0:
        code = "BLOCKED_CI_FAILED" if stage == "ci" else "BLOCKED_PAGES_FAILED"
        raise PublicationCompletionError(
            code,
            f"{code}: {stage} run {run_id} did not succeed",
            run_id=str(run_id),
            stage=stage,
            stderr=(result.stderr or "")[:500],
        )


def _successful_ci(rows: Sequence[Mapping[str, Any]], source_sha: str) -> dict[str, Any] | None:
    matches = [
        row for row in rows
        if _is_ci_row(row, source_sha)
        and str(row.get("status") or "") == "completed"
        and str(row.get("conclusion") or "") == "success"
    ]
    return matches[0] if len(matches) == 1 else matches[0] if matches else None


def _in_progress_ci(rows: Sequence[Mapping[str, Any]], source_sha: str) -> dict[str, Any] | None:
    matches = [
        row for row in rows
        if _is_ci_row(row, source_sha) and str(row.get("status") or "") in IN_PROGRESS_STATUSES
    ]
    if len(matches) > 1:
        raise PublicationCompletionError(
            "BLOCKED_CI_DISPATCH",
            "BLOCKED_CI_DISPATCH: multiple in-progress Dashboard CI runs for the exact SHA.",
        )
    return matches[0] if matches else None


def resolve_dashboard_ci(
    source_sha: str,
    *,
    web_dir: Path,
    runner: GhRunner | None = None,
    git_runner: Callable[..., tuple[int, str]] | None = None,
    allow_dispatch: bool = True,
    watch_timeout: float | None = None,
) -> dict[str, Any]:
    rows = list_workflow_runs(CI_WORKFLOW, cwd=web_dir, commit=source_sha, runner=runner)
    successful = _successful_ci(rows, source_sha)
    if successful:
        if str(successful.get("headSha") or "").lower() != source_sha.lower():
            raise PublicationCompletionError("BLOCKED_CI_FAILED", "wrong-SHA CI cannot be reused")
        return {"run": successful, "reused": True, "dispatched": False}
    in_progress = _in_progress_ci(rows, source_sha)
    if in_progress:
        watch_run(in_progress["databaseId"], cwd=web_dir, runner=runner, timeout=watch_timeout, stage="ci")
        refreshed = list_workflow_runs(CI_WORKFLOW, cwd=web_dir, commit=source_sha, runner=runner)
        successful = _successful_ci(refreshed, source_sha)
        if not successful:
            raise PublicationCompletionError("BLOCKED_CI_FAILED", "watched Dashboard CI did not complete successfully")
        return {"run": successful, "reused": True, "dispatched": False, "watched": True}
    if not allow_dispatch:
        raise PublicationCompletionError(
            "BLOCKED_CI_DISPATCH",
            "BLOCKED_CI_DISPATCH: no exact-SHA Dashboard CI proof and dispatch is disabled.",
        )
    lineage = classify_main_lineage(web_dir, source_sha, git_runner=git_runner)
    if lineage != "IDENTICAL":
        raise PublicationCompletionError(
            "BLOCKED_DASHBOARD_MAIN_ADVANCED",
            "BLOCKED_DASHBOARD_MAIN_ADVANCED: CI dispatch for a new publication requires origin/main == RELEASE_SOURCE_SHA.",
            relationship=lineage,
        )
    dispatched = run_gh(["workflow", "run", CI_WORKFLOW, "--ref", CANONICAL_BRANCH], cwd=web_dir, runner=runner)
    if dispatched.returncode != 0:
        raise PublicationCompletionError(
            "BLOCKED_CI_DISPATCH",
            "BLOCKED_CI_DISPATCH: gh workflow run dashboard-ci.yml failed.",
            stderr=(dispatched.stderr or "")[:500],
        )
    created = list_workflow_runs(CI_WORKFLOW, cwd=web_dir, commit=source_sha, runner=runner)
    created_exact = [row for row in created if _is_ci_row(row, source_sha)]
    if not created_exact:
        raise PublicationCompletionError(
            "BLOCKED_CI_DISPATCH",
            "BLOCKED_CI_DISPATCH: dispatched Dashboard CI run could not be resolved to the exact release SHA.",
        )
    target = created_exact[0]
    if str(target.get("headSha") or "").lower() != source_sha.lower():
        raise PublicationCompletionError(
            "BLOCKED_CI_DISPATCH",
            "BLOCKED_CI_DISPATCH: dispatched CI head_sha does not match RELEASE_SOURCE_SHA.",
        )
    if str(target.get("status") or "") != "completed" or str(target.get("conclusion") or "") != "success":
        watch_run(target["databaseId"], cwd=web_dir, runner=runner, timeout=watch_timeout, stage="ci")
        created = list_workflow_runs(CI_WORKFLOW, cwd=web_dir, commit=source_sha, runner=runner)
        successful = _successful_ci(created, source_sha)
        if not successful:
            raise PublicationCompletionError("BLOCKED_CI_FAILED", "dispatched Dashboard CI did not succeed")
        target = successful
    return {"run": target, "reused": False, "dispatched": True}


def _pages_log_proves(
    run: Mapping[str, Any],
    *,
    source_sha: str,
    expected_session: str,
    web_dir: Path,
    runner: GhRunner | None = None,
    log_text: str | None = None,
) -> dict[str, Any] | None:
    logs = log_text if log_text is not None else run_logs(run["databaseId"], cwd=web_dir, runner=runner)
    proof = parse_public_byte_proof(logs)
    if not proof:
        return None
    if proof["session"] != expected_session or proof["sha"] != source_sha.lower():
        return None
    manual = MANUAL_PAGES_GATE_RE.search(logs)
    return {
        "run": dict(run),
        "proof": proof,
        "logs_excerpt": proof["line"],
        "manual_ci_run_id": None if not manual else manual.group("run_id"),
        "event": run.get("event"),
    }


def find_pages_proof(
    source_sha: str,
    expected_session: str,
    *,
    web_dir: Path,
    runner: GhRunner | None = None,
    log_loader: Callable[[Mapping[str, Any]], str] | None = None,
) -> dict[str, Any] | None:
    rows = list_workflow_runs(PAGES_WORKFLOW, cwd=web_dir, commit=None, runner=runner)
    successful = [
        row for row in rows
        if _is_pages_row(row)
        and str(row.get("status") or "") == "completed"
        and str(row.get("conclusion") or "") == "success"
    ]
    for row in successful:
        logs = log_loader(row) if log_loader else None
        proved = _pages_log_proves(
            row,
            source_sha=source_sha,
            expected_session=expected_session,
            web_dir=web_dir,
            runner=runner,
            log_text=logs,
        )
        if proved:
            # Automatic path is strongly identifiable when the run head SHA is the
            # release source (normal new publication). Manual fallback is identifiable
            # from PUBLIC_BYTE_IDENTITY_PASS + source sha in the log.
            event = str(row.get("event") or "")
            head = str(row.get("headSha") or "").lower()
            if event == "workflow_run" and head and head != source_sha.lower():
                # Do not treat a later workflow-head Pages run as proof unless logs
                # explicitly name the release source SHA.
                if proved["proof"]["sha"] != source_sha.lower():
                    continue
            return proved
    in_progress = [
        row for row in rows
        if _is_pages_row(row) and str(row.get("status") or "") in IN_PROGRESS_STATUSES
        and str(row.get("headSha") or "").lower() == source_sha.lower()
    ]
    if len(in_progress) == 1:
        return {"run": in_progress[0], "proof": None, "in_progress": True}
    return None


def resolve_deploy_pages(
    source_sha: str,
    expected_session: str,
    ci_run_id: int | str,
    *,
    web_dir: Path,
    runner: GhRunner | None = None,
    git_runner: Callable[..., tuple[int, str]] | None = None,
    allow_dispatch: bool = True,
    watch_timeout: float | None = None,
    log_loader: Callable[[Mapping[str, Any]], str] | None = None,
) -> dict[str, Any]:
    existing = find_pages_proof(
        source_sha,
        expected_session,
        web_dir=web_dir,
        runner=runner,
        log_loader=log_loader,
    )
    if existing and existing.get("proof"):
        return {**existing, "reused": True, "dispatched": False}
    if existing and existing.get("in_progress"):
        watch_run(existing["run"]["databaseId"], cwd=web_dir, runner=runner, timeout=watch_timeout, stage="pages")
        proved = find_pages_proof(source_sha, expected_session, web_dir=web_dir, runner=runner, log_loader=log_loader)
        if not proved or not proved.get("proof"):
            raise PublicationCompletionError("BLOCKED_PUBLIC_BYTE_PROOF", "watched Deploy Pages run lacked public-byte proof")
        return {**proved, "reused": True, "dispatched": False, "watched": True}
    if not allow_dispatch:
        raise PublicationCompletionError(
            "BLOCKED_PAGES_DISPATCH",
            "BLOCKED_PAGES_DISPATCH: no exact-source Pages/public-byte proof and dispatch is disabled.",
        )
    lineage = classify_main_lineage(web_dir, source_sha, git_runner=git_runner)
    if lineage not in {"IDENTICAL", "AHEAD"}:
        raise PublicationCompletionError(
            "BLOCKED_DASHBOARD_MAIN_ADVANCED",
            "BLOCKED_DASHBOARD_MAIN_ADVANCED: Pages source is not on current main lineage.",
            relationship=lineage,
        )
    dispatched = run_gh(
        [
            "workflow", "run", PAGES_WORKFLOW,
            "--ref", CANONICAL_BRANCH,
            "-f", f"source_sha={source_sha}",
            "-f", f"validated_ci_run_id={ci_run_id}",
        ],
        cwd=web_dir,
        runner=runner,
    )
    if dispatched.returncode != 0:
        raise PublicationCompletionError(
            "BLOCKED_PAGES_DISPATCH",
            "BLOCKED_PAGES_DISPATCH: gh workflow run deploy-pages.yml failed.",
            stderr=(dispatched.stderr or "")[:500],
        )
    created_rows = list_workflow_runs(PAGES_WORKFLOW, cwd=web_dir, commit=None, runner=runner)
    candidates = [
        row for row in created_rows
        if _is_pages_row(row) and str(row.get("event") or "") == "workflow_dispatch"
    ]
    if not candidates:
        raise PublicationCompletionError(
            "BLOCKED_PAGES_DISPATCH",
            "BLOCKED_PAGES_DISPATCH: dispatched Deploy Pages run could not be resolved.",
        )
    target = candidates[0]
    if str(target.get("status") or "") != "completed" or str(target.get("conclusion") or "") != "success":
        watch_run(target["databaseId"], cwd=web_dir, runner=runner, timeout=watch_timeout, stage="pages")
    proved = find_pages_proof(source_sha, expected_session, web_dir=web_dir, runner=runner, log_loader=log_loader)
    if not proved or not proved.get("proof"):
        logs = log_loader(target) if log_loader else run_logs(target["databaseId"], cwd=web_dir, runner=runner)
        if str(target.get("conclusion") or "") == "success" and not parse_public_byte_proof(logs):
            raise PublicationCompletionError(
                "BLOCKED_PUBLIC_BYTE_PROOF",
                "BLOCKED_PUBLIC_BYTE_PROOF: Deploy Pages succeeded without PUBLIC_BYTE_IDENTITY_PASS for the expected session/SHA.",
            )
        raise PublicationCompletionError("BLOCKED_PAGES_FAILED", "dispatched Deploy Pages did not prove public-byte identity")
    if proved["proof"]["sha"] != source_sha.lower() or proved["proof"]["session"] != expected_session:
        raise PublicationCompletionError(
            "BLOCKED_PUBLIC_BYTE_PROOF",
            "BLOCKED_PUBLIC_BYTE_PROOF: public-byte proof session/SHA mismatch.",
            proof=proved["proof"],
        )
    return {**proved, "reused": False, "dispatched": True}


def _artifact_dir(producer_root: Path, session: str, digest: str) -> Path:
    return producer_root / "operations-review" / "governed-publication-completion-v1" / session / f"attestation-{digest}"


def write_completion_artifact(producer_root: Path, record: Mapping[str, Any]) -> Path:
    session = str(record["session"])
    digest = str(record["attestation_digest"])
    directory = _artifact_dir(producer_root, session, digest)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "publication_completion.json"
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        prior = json.loads(path.read_text(encoding="utf-8"))
        if prior.get("release_source_sha") == record.get("release_source_sha") and prior.get("publication_state") == "PUBLISHED":
            return path
        raise PublicationCompletionError("IMMUTABLE_PUBLICATION_ATTESTATION_CONFLICT", path=str(path))
    if not path.exists():
        atomic_write_json(path, dict(record), validator=validate_json_file)
    return path


def format_handoff(record: Mapping[str, Any]) -> str:
    return "\n".join([
        f"PUBLICATION_STATE={record.get('publication_state')}",
        f"SESSION={record.get('session')}",
        f"DASHBOARD_RELEASE_SHA={record.get('release_source_sha')}",
        f"DASHBOARD_CI_RUN_ID={record.get('dashboard_ci_run_id')}",
        f"DASHBOARD_CI_STATUS={record.get('dashboard_ci_status')}",
        f"DEPLOY_PAGES_RUN_ID={record.get('deploy_pages_run_id')}",
        f"DEPLOY_PAGES_STATUS={record.get('deploy_pages_status')}",
        f"PUBLIC_BYTE_IDENTITY={record.get('public_byte_identity')}",
        f"CI_REUSED={record.get('ci_reused')}",
        f"PAGES_REUSED={record.get('pages_reused')}",
        f"AUTHORITY_EFFECT={record.get('authority_effect')}",
        f"ATTESTATION_IDENTITY={record.get('attestation_identity')}",
        f"CONTENT_IDENTITY={record.get('content_identity')}",
        f"REASON_CODES={','.join(record.get('reason_codes') or [])}",
    ])


def complete_publication(
    *,
    web_dir: Path,
    expected_session: str,
    producer_root: Path,
    release_source_sha: str | None = None,
    require_identical_main: bool = True,
    allow_dispatch: bool = True,
    runner: GhRunner | None = None,
    git_runner: Callable[..., tuple[int, str]] | None = None,
    watch_timeout: float | None = None,
    log_loader: Callable[[Mapping[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """Resolve or dispatch exact-SHA Dashboard CI and Deploy Pages, then attest PUBLISHED."""
    preflight = gh_preflight(web_dir, runner=runner, git_runner=git_runner)
    source_sha = resolve_release_source_sha(
        web_dir,
        explicit_sha=release_source_sha,
        git_runner=git_runner,
        require_identical_main=require_identical_main,
    )
    ci = resolve_dashboard_ci(
        source_sha,
        web_dir=web_dir,
        runner=runner,
        git_runner=git_runner,
        allow_dispatch=allow_dispatch,
        watch_timeout=watch_timeout,
    )
    ci_run = ci["run"]
    pages = resolve_deploy_pages(
        source_sha,
        expected_session,
        ci_run["databaseId"],
        web_dir=web_dir,
        runner=runner,
        git_runner=git_runner,
        allow_dispatch=allow_dispatch,
        watch_timeout=watch_timeout,
        log_loader=log_loader,
    )
    proof = pages["proof"]
    content_payload = {
        "contract_version": CONTRACT_VERSION,
        "session": expected_session,
        "release_source_sha": source_sha.lower(),
        "publication_state": PUBLISHED,
        "public_byte_identity": "PASS",
        "authority_effect": "NONE",
    }
    content_identity = stable_id(content_payload)
    attestation_payload = {
        **content_payload,
        "dashboard_ci_run_id": str(ci_run["databaseId"]),
        "deploy_pages_run_id": str(pages["run"]["databaseId"]),
        "public_byte_line": proof.get("line"),
        "ci_event": ci_run.get("event"),
        "pages_event": pages["run"].get("event"),
    }
    attestation_digest = stable_id(attestation_payload)
    record = {
        "schema_version": CONTRACT_VERSION,
        "session": expected_session,
        "release_source_sha": source_sha.lower(),
        "publication_state": PUBLISHED,
        "dashboard_ci_run_id": str(ci_run["databaseId"]),
        "dashboard_ci_status": "SUCCESS",
        "deploy_pages_run_id": str(pages["run"]["databaseId"]),
        "deploy_pages_status": "SUCCESS",
        "public_byte_identity": "PASS",
        "public_byte_proof": proof,
        "ci_reused": bool(ci.get("reused")),
        "pages_reused": bool(pages.get("reused")),
        "ci_dispatched": bool(ci.get("dispatched")),
        "pages_dispatched": bool(pages.get("dispatched")),
        "gh_preflight": {"repository": preflight["repository"], "branch": preflight["branch"]},
        "reason_codes": ["PUBLICATION_COMPLETED"],
        "authority_effect": "NONE",
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
        "content_identity": f"governed_publication_content:{content_identity}",
        "attestation_digest": attestation_digest,
        "attestation_identity": f"governed_publication_attestation:{attestation_digest}",
        "disposition": "PUBLISHED",
    }
    path = write_completion_artifact(producer_root, record)
    record["artifact_path"] = str(path.as_posix())
    record["is_idempotent_replay"] = bool(ci.get("reused") and pages.get("reused"))
    return record
