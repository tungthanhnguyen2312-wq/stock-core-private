"""Machine-readable roadmap execution-state authority: load, validate, query.

``docs/ROADMAP_STATE.json`` is the EXECUTION-STATE authority: which milestone is
current/active/next/blocked, what checkpoint proves each completed milestone,
and whether recorded state contradicts Git/worktree reality. It intentionally
does not restate ``docs/ROADMAP.md`` (strategic/narrative roadmap),
``docs/STATE.md`` (operational narrative), or ``docs/DECISIONS.md`` (decision
record) -- see the state file's own ``narrative_authority`` block and
``docs/AI_RULES.md``. This module never parses those Markdown files; where a
contradiction between this file and a narrative doc is structurally
detectable, callers should surface it rather than silently trusting either
side (AGENTS.md "Default lightweight bootstrap" conflict rule).

Read-only by design: nothing here mutates Git, a worktree, or the roadmap
state file. Updating recorded state is a manual, reviewed edit to the JSON.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from subprocess_capture import run_utf8

try:
    from field_temporal_contract import stable_id
except ImportError:  # pragma: no cover - field_temporal_contract has no third-party deps
    import hashlib

    def stable_id(value: Any) -> str:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = REPO_ROOT / "docs" / "ROADMAP_STATE.json"
SCHEMA_VERSION = "stocklookup_roadmap_execution_state/1.0.0"

VALID_STATES = {"COMPLETE", "ACTIVE", "NEXT", "BLOCKED", "DEFERRED", "SUPERSEDED"}
CLOSED_STATES = {"COMPLETE", "SUPERSEDED"}
SATISFIES_DEPENDENCY = {"COMPLETE", "SUPERSEDED"}
HEAD_SENTINEL = "HEAD"

INFO = "INFO"
WARNING = "WARNING"
FAIL = "FAIL"
_SEVERITY_RANK = {FAIL: 0, WARNING: 1, INFO: 2}

CHECK_CATEGORIES = (
    "multiple active writers",
    "dependency consistency",
    "checkpoint existence",
    "stale next pointers",
    "git/worktree consistency",
)
_CATEGORY_BY_CODE = {
    "ROADMAP_MULTIPLE_ACTIVE_MILESTONES": "multiple active writers",
    "ROADMAP_MULTIPLE_SOURCE_WRITERS": "multiple active writers",
    "ROADMAP_ACTIVE_NOT_ALLOWED_BY_DEPENDENCIES": "dependency consistency",
    "ROADMAP_NEXT_DEPENDENCY_UNSATISFIED": "dependency consistency",
    "ROADMAP_CLOSED_MILESTONE_REOPENED": "dependency consistency",
    "ROADMAP_UNKNOWN_MILESTONE": "dependency consistency",
    "ROADMAP_CHECKPOINT_MISSING": "checkpoint existence",
    "ROADMAP_CHECKPOINT_NOT_IN_GIT": "checkpoint existence",
    "ROADMAP_STALE_NEXT_POINTER": "stale next pointers",
    "ROADMAP_RECORDED_HEAD_DIVERGENCE": "git/worktree consistency",
    "ROADMAP_DIRTY_WORKTREE": "git/worktree consistency",
    "ROADMAP_UNRESOLVED_HEAD_SENTINEL_STALE": "git/worktree consistency",
    "ROADMAP_LANE_WORKTREE_UNAVAILABLE": "git/worktree consistency",
}


class RoadmapStateError(ValueError):
    """The roadmap state file is absent, corrupt, or structurally invalid."""


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    milestone_id: str | None = None

    @property
    def category(self) -> str:
        return _CATEGORY_BY_CODE.get(self.code, "other")


GIT_VERIFICATION_VERIFIED = "VERIFIED"
GIT_VERIFICATION_SKIPPED = "SKIPPED"
GIT_VERIFICATION_UNAVAILABLE = "UNAVAILABLE"
GIT_VERIFICATION_MISMATCH = "MISMATCH"
OVERALL_GIT_NOT_CHECKED = "GIT_NOT_CHECKED"
_GIT_MISMATCH_CODES = {"ROADMAP_RECORDED_HEAD_DIVERGENCE", "ROADMAP_CHECKPOINT_NOT_IN_GIT"}

DO_NOT_OPEN = (
    "docs/STATE.md",
    "docs/DECISIONS.md",
    "docs/ROADMAP.md",
    "docs/ROADMAP_STATE.json",
    "tools/handoff.py historical mode",
)
LOCAL_FAST = (
    "tests/test_repository_layout.py",
    "tests/test_roadmap_execution_state.py",
    "tests/test_production_call_shape_smoke.py::test_offline_guard_blocks_requests_urllib_and_vnstock_import",
    "tests/test_production_call_shape_smoke.py::test_owner_daily_entry_route_remains_canonical",
    "python tools/stocklookup_roadmap.py --check",
)


@dataclass(frozen=True)
class RoadmapReport:
    state: Mapping[str, Any]
    findings: tuple[Finding, ...]
    overall: str
    content_identity: str
    git_verification: str = GIT_VERIFICATION_SKIPPED

    def findings_at_or_above(self, severity: str) -> tuple[Finding, ...]:
        rank = _SEVERITY_RANK[severity]
        return tuple(f for f in self.findings if _SEVERITY_RANK[f.severity] <= rank)

    def category_status(self, category: str) -> str:
        if category == "git/worktree consistency" and self.git_verification == GIT_VERIFICATION_SKIPPED:
            return "SKIPPED"
        if category == "git/worktree consistency" and self.git_verification == GIT_VERIFICATION_UNAVAILABLE:
            return "UNAVAILABLE"
        codes = [f for f in self.findings if f.category == category]
        if any(f.severity == FAIL for f in codes):
            return FAIL
        if any(f.severity == WARNING for f in codes):
            return WARNING
        return "PASS"

    def has_fail(self) -> bool:
        return any(f.severity == FAIL for f in self.findings)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_state(path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RoadmapStateError(f"ROADMAP_STATE_FILE_MISSING:{path}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RoadmapStateError(f"ROADMAP_STATE_FILE_CORRUPT:{path}") from exc
    if not isinstance(value, dict):
        raise RoadmapStateError(f"ROADMAP_STATE_FILE_INVALID:{path}")
    return value


def _milestones_by_id(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for entry in state.get("milestones") or []:
        if isinstance(entry, Mapping) and isinstance(entry.get("milestone_id"), str):
            result[entry["milestone_id"]] = entry
    return result


# --------------------------------------------------------------------------
# Git introspection (read-only; never mutates the repo/worktree)
# --------------------------------------------------------------------------

def git_run(repo: Path, *args: str) -> tuple[int, str, str]:
    from subprocess import TimeoutExpired
    try:
        return run_utf8(["git", "--no-optional-locks", "-c", "maintenance.auto=false",
                         "-c", "gc.auto=0", "-C", str(repo), *args], timeout=30)
    except TimeoutExpired:
        return 124, "", "GIT_QUERY_TIMEOUT"


def git_head(repo: Path) -> str | None:
    code, out, _ = git_run(repo, "rev-parse", "HEAD")
    return out.strip() if code == 0 else None


def git_branch(repo: Path) -> str | None:
    code, out, _ = git_run(repo, "branch", "--show-current")
    return out.strip() if code == 0 else None


def git_object_type(repo: Path, ref: str) -> str | None:
    code, out, _ = git_run(repo, "cat-file", "-t", ref)
    return out.strip() if code == 0 else None


def git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    code, _, _ = git_run(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    return code == 0


def git_dirty_tracked(repo: Path) -> list[str]:
    code, out, _ = git_run(repo, "status", "--porcelain")
    if code != 0:
        return []
    return [line for line in out.splitlines() if line.strip() and not line.startswith("??")]


def git_staged(repo: Path) -> list[str]:
    code, out, _ = git_run(repo, "diff", "--cached", "--name-only")
    if code != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def git_ahead_behind(repo: Path, local_ref: str, upstream_ref: str) -> tuple[int, int] | None:
    code, out, _ = git_run(repo, "rev-list", "--left-right", "--count", f"{local_ref}...{upstream_ref}")
    if code != 0 or not out.strip():
        return None
    parts = out.split()
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def git_last_commit_touching(repo: Path, relative_path: str) -> str | None:
    code, out, _ = git_run(repo, "log", "-1", "--format=%H", "--", relative_path)
    text = out.strip()
    return text if code == 0 and text else None


def git_worktrees(repo: Path) -> list[dict[str, str]]:
    code, out, _ = git_run(repo, "worktree", "list", "--porcelain")
    if code != 0:
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            if current:
                entries.append(current)
            current = {"worktree": line[len("worktree "):].strip()}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].strip()
        elif line == "bare":
            current["bare"] = "true"
        elif line == "detached":
            current["detached"] = "true"
        elif line.startswith("locked"):
            current["locked"] = "true"
        elif line.startswith("prunable"):
            current["prunable"] = "true"
    if current:
        entries.append(current)
    return entries


def resolve_checkpoint(repo: Path | None, checkpoint: str | None) -> tuple[bool, str]:
    """Return ``(exists_as_commit, resolved_sha_or_reason)`` for one checkpoint value.

    ``"HEAD"`` is a documented sentinel meaning "the commit that introduces this
    exact roadmap-state record" -- used because a commit cannot embed its own
    hash. It always resolves against live ``git rev-parse HEAD``. Whoever next
    edits ``docs/ROADMAP_STATE.json`` should freeze it to the literal SHA first
    (``git rev-parse HEAD`` at the start of their own change) -- see
    ``ROADMAP_UNRESOLVED_HEAD_SENTINEL_STALE``.
    """
    if not checkpoint:
        return False, "MISSING"
    if repo is None:
        return (checkpoint == HEAD_SENTINEL), ("UNRESOLVED_NO_REPO" if checkpoint != HEAD_SENTINEL else "HEAD_NO_REPO")
    if checkpoint == HEAD_SENTINEL:
        head = git_head(repo)
        if head is None:
            return False, "HEAD_UNRESOLVABLE"
        return True, head
    obj_type = git_object_type(repo, checkpoint)
    if obj_type != "commit":
        return False, "NOT_IN_GIT"
    return True, checkpoint


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _dependency_ok_for_active(milestones: Mapping[str, Mapping[str, Any]], dep_id: str) -> bool:
    dep = milestones.get(dep_id)
    return bool(dep) and dep.get("state") in SATISFIES_DEPENDENCY


def _dependency_ok_for_next(milestones: Mapping[str, Mapping[str, Any]], dep_id: str) -> bool:
    dep = milestones.get(dep_id)
    return bool(dep) and dep.get("state") in (SATISFIES_DEPENDENCY | {"ACTIVE"})


def evaluate(state: Mapping[str, Any], *, repo: Path | None = None) -> RoadmapReport:
    findings: list[Finding] = []
    milestones = _milestones_by_id(state)
    allowlist = set(state.get("known_operational_diff_allowlist") or [])
    if len(milestones) != len(state.get("milestones") or []):
        findings.append(Finding("ROADMAP_UNKNOWN_MILESTONE", FAIL, "duplicate or malformed milestone IDs"))
    for message in validate_development_control(state):
        findings.append(Finding("ROADMAP_LANE_INVALID", FAIL, message))

    # -- referential integrity -------------------------------------------------
    known_ids = set(milestones)
    referenced: list[tuple[str, str]] = []
    current = state.get("current") or {}
    if isinstance(current.get("milestone"), str):
        referenced.append((current["milestone"], "current.milestone"))
    for mid in state.get("queued_next") or []:
        referenced.append((mid, "queued_next"))
    for m in milestones.values():
        for dep in m.get("dependencies") or []:
            referenced.append((dep, f"{m.get('milestone_id')}.dependencies"))
        for unl in m.get("unlocks") or []:
            referenced.append((unl, f"{m.get('milestone_id')}.unlocks"))
    for mid, where in referenced:
        if mid not in known_ids:
            findings.append(Finding("ROADMAP_UNKNOWN_MILESTONE", FAIL, f"{where} references unknown milestone_id {mid!r}", mid))

    # -- single-active invariant ------------------------------------------------
    active = [m for m in milestones.values() if m.get("state") == "ACTIVE"]
    if len(active) > 1:
        ids = ", ".join(sorted(m["milestone_id"] for m in active))
        findings.append(Finding("ROADMAP_MULTIPLE_ACTIVE_MILESTONES", FAIL, f"more than one milestone recorded ACTIVE: {ids}"))

    # -- dependency consistency --------------------------------------------------
    for m in active:
        unmet = [d for d in (m.get("dependencies") or []) if d in known_ids and not _dependency_ok_for_active(milestones, d)]
        if unmet:
            findings.append(Finding(
                "ROADMAP_ACTIVE_NOT_ALLOWED_BY_DEPENDENCIES", FAIL,
                f"{m['milestone_id']} is ACTIVE but dependency(ies) not satisfied: {', '.join(unmet)}",
                m["milestone_id"],
            ))

    next_milestones = [m for m in milestones.values() if m.get("state") == "NEXT"]
    for m in next_milestones:
        blocked = [d for d in (m.get("dependencies") or []) if d in known_ids and milestones[d].get("state") in ("BLOCKED", "DEFERRED")]
        if blocked:
            findings.append(Finding(
                "ROADMAP_NEXT_DEPENDENCY_UNSATISFIED", FAIL,
                f"{m['milestone_id']} is NEXT but depends on BLOCKED/DEFERRED milestone(s): {', '.join(blocked)}",
                m["milestone_id"],
            ))

    for m in milestones.values():
        mid = m.get("milestone_id")
        st = m.get("state")
        history = list(m.get("state_history") or [])
        override = m.get("owner_override") or None
        allows_reopen = isinstance(override, Mapping) and override.get("allows_reopen") is True
        if st in ("ACTIVE", "NEXT") and any(h in CLOSED_STATES for h in history) and not allows_reopen:
            findings.append(Finding(
                "ROADMAP_CLOSED_MILESTONE_REOPENED", FAIL,
                f"{mid} was previously {history} and is now {st} without an owner_override.allows_reopen=true",
                mid,
            ))

    # -- stale NEXT pointer -------------------------------------------------------
    queued_next = list(state.get("queued_next") or [])
    if len(next_milestones) > 1:
        ids = ", ".join(sorted(m["milestone_id"] for m in next_milestones))
        findings.append(Finding("ROADMAP_STALE_NEXT_POINTER", FAIL, f"more than one milestone recorded NEXT (ambiguous queue): {ids}"))
    elif next_milestones and not queued_next:
        findings.append(Finding("ROADMAP_STALE_NEXT_POINTER", FAIL, f"{next_milestones[0]['milestone_id']} is NEXT but queued_next is empty"))
    elif next_milestones and queued_next and next_milestones[0]["milestone_id"] != queued_next[0]:
        findings.append(Finding(
            "ROADMAP_STALE_NEXT_POINTER", FAIL,
            f"NEXT milestone {next_milestones[0]['milestone_id']!r} does not match queued_next head {queued_next[0]!r}",
        ))
    elif queued_next and not next_milestones:
        findings.append(Finding("ROADMAP_STALE_NEXT_POINTER", WARNING, f"queued_next names {queued_next[0]!r} but no milestone is recorded NEXT"))
    for mid in queued_next:
        if mid in known_ids and milestones[mid].get("state") in ("SUPERSEDED", "DEFERRED"):
            findings.append(Finding("ROADMAP_STALE_NEXT_POINTER", WARNING, f"queued_next references {mid!r} whose state is already {milestones[mid].get('state')}", mid))

    # -- checkpoint existence -----------------------------------------------------
    git_live = repo is not None and git_head(repo) is not None
    for m in milestones.values():
        mid = m.get("milestone_id")
        if m.get("state") != "COMPLETE":
            continue
        checkpoint = m.get("checkpoint")
        if not checkpoint:
            findings.append(Finding("ROADMAP_CHECKPOINT_MISSING", FAIL, f"{mid} is COMPLETE but has no checkpoint recorded", mid))
            continue
        if not git_live:
            continue
        ok, resolved = resolve_checkpoint(repo, checkpoint)
        if not ok:
            findings.append(Finding("ROADMAP_CHECKPOINT_NOT_IN_GIT", FAIL, f"{mid} checkpoint {checkpoint!r} does not resolve to a Git commit ({resolved})", mid))
        elif checkpoint == HEAD_SENTINEL:
            last_touch = git_last_commit_touching(repo, "docs/ROADMAP_STATE.json")
            live_head = git_head(repo)
            if last_touch and live_head and last_touch != live_head:
                findings.append(Finding(
                    "ROADMAP_UNRESOLVED_HEAD_SENTINEL_STALE", WARNING,
                    f"{mid} checkpoint is still the literal 'HEAD' sentinel but HEAD has moved since docs/ROADMAP_STATE.json was last touched -- resolve it to {last_touch}",
                    mid,
                ))

    # -- git/worktree consistency --------------------------------------------------
    if git_live:
        recorded_head = state.get("implementation_lineage_head")
        ok, resolved = resolve_checkpoint(repo, recorded_head)
        live_head = git_head(repo)
        if recorded_head and live_head:
            reference = resolved if ok and recorded_head == HEAD_SENTINEL else recorded_head
            if reference and git_object_type(repo, reference) == "commit":
                if reference == live_head:
                    findings.append(Finding("ROADMAP_RECORDED_HEAD_DIVERGENCE", INFO, "recorded implementation_lineage_head matches live HEAD"))
                elif git_is_ancestor(repo, reference, live_head):
                    findings.append(Finding("ROADMAP_RECORDED_HEAD_DIVERGENCE", INFO, "live HEAD is a normal forward descendant of recorded implementation_lineage_head"))
                elif git_is_ancestor(repo, live_head, reference):
                    findings.append(Finding("ROADMAP_RECORDED_HEAD_DIVERGENCE", FAIL, "live HEAD is BEHIND recorded implementation_lineage_head -- possible reset"))
                else:
                    findings.append(Finding("ROADMAP_RECORDED_HEAD_DIVERGENCE", FAIL, "live HEAD and recorded implementation_lineage_head have diverged (unrelated history) -- possible rebase/force-push/reset"))
            else:
                findings.append(Finding("ROADMAP_RECORDED_HEAD_DIVERGENCE", FAIL, f"recorded implementation_lineage_head {recorded_head!r} does not resolve to a Git commit"))

        for line in git_dirty_tracked(repo):
            path = line[3:].strip() if len(line) > 3 else line.strip()
            if path in allowlist:
                findings.append(Finding("ROADMAP_DIRTY_WORKTREE", INFO, f"known pre-existing operational diff (allowlisted): {path}"))
            else:
                findings.append(Finding("ROADMAP_DIRTY_WORKTREE", WARNING, f"unallowlisted tracked-file change in {repo}: {line.strip()}"))
        staged = git_staged(repo)
        if staged:
            findings.append(Finding("ROADMAP_DIRTY_WORKTREE", WARNING, f"{len(staged)} file(s) staged but not committed in {repo}: {', '.join(staged[:5])}"))

        writer_findings = _check_multiple_source_writers(state, milestones, repo)
        findings.extend(writer_findings)
        control = state.get("development_control") if isinstance(state.get("development_control"), dict) else {}
        if control and not coordinator_host_available(state, repo):
            findings.append(Finding("ROADMAP_LANE_WORKTREE_UNAVAILABLE", WARNING,
                                    "lane host observations SKIPPED_NON_COORDINATOR_CLONE; structural state only, no lane start/integration authority"))
        elif not validate_development_control(state):
            for lane in (state.get("development_control") or {}).get("lanes", []):
                if lane.get("state") not in LANE_TERMINAL:
                    for error in check_lane(state, lane["milestone_id"], repo=repo)["errors"]:
                        findings.append(Finding("ROADMAP_LANE_INVALID", FAIL, error, lane["milestone_id"]))

    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.category, f.code, f.message))
    git_verification = _git_verification(repo, findings)
    if any(f.severity == FAIL for f in findings):
        overall = "DRIFT_DETECTED"
    elif git_verification in {GIT_VERIFICATION_SKIPPED, GIT_VERIFICATION_UNAVAILABLE}:
        overall = OVERALL_GIT_NOT_CHECKED
    else:
        overall = "ON_TRACK"
    identity = stable_id({"state": state, "overall": overall, "git_verification": git_verification})
    return RoadmapReport(
        state=state, findings=tuple(findings), overall=overall,
        content_identity=identity, git_verification=git_verification,
    )


def _git_verification(repo: Path | None, findings: Sequence[Finding]) -> str:
    """Separate native-state validation from a live Git checkpoint check."""
    if repo is None:
        return GIT_VERIFICATION_SKIPPED
    if git_head(repo) is None:
        return GIT_VERIFICATION_UNAVAILABLE
    if any(f.code in _GIT_MISMATCH_CODES and f.severity == FAIL for f in findings):
        return GIT_VERIFICATION_MISMATCH
    return GIT_VERIFICATION_VERIFIED


def focused_selection_count(repo: Path) -> int | str:
    """Count FOCUSED_SELECTION test tokens. UNKNOWN when the workflow cannot be parsed."""
    path = repo / ".github" / "workflows" / "producer-ci.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "UNKNOWN"
    marker = "FOCUSED_SELECTION:"
    start = text.find(marker)
    if start < 0:
        return "UNKNOWN"
    tokens: list[str] = []
    for line in text[start:].splitlines()[1:]:
        if line and not line[0].isspace():
            break
        tokens.extend(line.split())
    paths = [token for token in tokens if token.startswith("tests/") or token.endswith(".py")]
    return len(paths) if paths else "UNKNOWN"


def classify_worktrees(repo: Path) -> dict[str, Any]:
    """Count worktrees. Rows are for ``--worktrees`` only and are not the default JSON payload.

    Untracked inspection is limited to ``data/`` and ``operations-review/`` on ancestor
    candidates. It does not hash file contents and does not remove anything.
    """
    counts = {
        "registered": 0,
        "ancestor_of_head": 0,
        "tracked_clean": 0,
        "tracked_dirty": 0,
        "unmerged": 0,
        "status_unknown": 0,
    }
    rows: list[dict[str, Any]] = []
    head = git_head(repo)
    entries = [wt for wt in git_worktrees(repo) if wt.get("bare") != "true" and wt.get("worktree")]
    counts["registered"] = len(entries)
    if head is None:
        counts["status_unknown"] = len(entries)
        return {"counts": counts, "rows": rows}
    for wt in entries:
        wt_head = wt.get("head") or ""
        ancestor = bool(wt_head) and git_is_ancestor(repo, wt_head, head)
        code, out, _ = git_run(Path(wt["worktree"]), "status", "--porcelain")
        if code != 0:
            counts["status_unknown"] += 1
            klass = "STATUS_UNKNOWN"
            dirty_count: int | str = "UNKNOWN"
        else:
            tracked = [line for line in out.splitlines() if line.strip() and not line.startswith("??")]
            dirty_count = len(tracked)
            if not ancestor:
                counts["unmerged"] += 1
                klass = "UNMERGED"
            else:
                counts["ancestor_of_head"] += 1
                if tracked:
                    counts["tracked_dirty"] += 1
                    klass = "ANCESTOR_TRACKED_DIRTY"
                else:
                    counts["tracked_clean"] += 1
                    klass = "ANCESTOR_TRACKED_CLEAN"
                    unresolved = _ancestor_untracked_unresolved(Path(wt["worktree"]))
                    if unresolved is None:
                        counts["status_unknown"] += 1
                        klass = "STATUS_UNKNOWN"
                    elif unresolved:
                        klass = "UNTRACKED_UNRESOLVED"
        branch = wt.get("branch") or ("DETACHED" if wt.get("detached") == "true" else "UNKNOWN")
        rows.append({
            "class": klass,
            "head": wt_head or "UNKNOWN",
            "branch": branch,
            "tracked_dirty_count": dirty_count,
            "path": wt["worktree"],
        })
    rows.sort(key=lambda row: (row["class"], row["branch"], row["head"], row["path"]))
    return {"counts": counts, "rows": rows}


def _ancestor_untracked_unresolved(worktree: Path) -> bool | None:
    code, out, _ = git_run(
        worktree, "status", "--porcelain", "-u", "--untracked-files=normal", "--", "data", "operations-review",
    )
    if code != 0:
        return None
    for line in out.splitlines():
        if not line.startswith("??"):
            continue
        path = line[3:].strip().replace("\\", "/")
        if path == "data" or path.startswith("data/") or path == "operations-review" or path.startswith("operations-review/"):
            return True
    return False


def build_bootstrap(repo: Path) -> dict[str, Any]:
    """Navigation fields for an ordinary agent. Counts only; no worktree path list."""
    classified = classify_worktrees(repo)
    return {
        "do_not_open": list(DO_NOT_OPEN),
        "local_fast": list(LOCAL_FAST),
        "focused_selection_count": focused_selection_count(repo),
        "worktrees": classified["counts"],
    }


def _check_multiple_source_writers(
    state: Mapping[str, Any], milestones: Mapping[str, Mapping[str, Any]], repo: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    worktrees = git_worktrees(repo)
    active_ids = [m["milestone_id"] for m in milestones.values() if m.get("state") == "ACTIVE"]

    def _normalize(text: str) -> str:
        return text.lower().replace("-", "_").replace("/", "_")

    ahead_worktrees: list[str] = []
    lineage_head_ok, lineage_head_resolved = resolve_checkpoint(repo, state.get("implementation_lineage_head"))
    for wt in worktrees:
        path = wt.get("worktree")
        head = wt.get("head")
        if not path or not head or wt.get("bare") == "true":
            continue
        if lineage_head_ok and git_is_ancestor(repo, lineage_head_resolved, head) and head != lineage_head_resolved:
            ahead_worktrees.append(path)

    if ahead_worktrees:
        findings.append(Finding(
            "ROADMAP_MULTIPLE_SOURCE_WRITERS", INFO,
            f"{len(ahead_worktrees)} worktree(s) ahead of recorded implementation_lineage_head "
            "(normal parallel exploration). Pass --worktrees for paths.",
        ))

    matches_by_milestone: dict[str, list[str]] = {}
    for wt in worktrees:
        branch = wt.get("branch") or ""
        norm_branch = _normalize(branch)
        for mid in active_ids:
            if _normalize(mid) in norm_branch or _normalize(mid).replace("_v1", "") in norm_branch:
                matches_by_milestone.setdefault(mid, []).append(wt.get("worktree", "?"))
    for mid, paths in matches_by_milestone.items():
        if len(paths) > 1:
            findings.append(Finding(
                "ROADMAP_MULTIPLE_SOURCE_WRITERS", FAIL,
                f"milestone {mid} is ACTIVE and matched by {len(paths)} distinct worktree branches: {', '.join(paths)}",
                mid,
            ))
    return findings


# --------------------------------------------------------------------------
# Human-facing queries
# --------------------------------------------------------------------------

def find_primary_checkout(repo: Path) -> dict[str, str] | None:
    worktrees = git_worktrees(repo)
    return worktrees[0] if worktrees else None


def can_start(state: Mapping[str, Any], milestone_id: str, *, owner_override: bool = False) -> tuple[bool, list[str]]:
    milestones = _milestones_by_id(state)
    target = milestones.get(milestone_id)
    reasons: list[str] = []
    if target is None:
        return False, [f"ROADMAP_UNKNOWN_MILESTONE:{milestone_id}"]
    st = target.get("state")
    if st == "ACTIVE":
        current = state.get("current") or {}
        return (current.get("milestone") == milestone_id), ([] if current.get("milestone") == milestone_id else ["ACTIVE_NOT_CURRENT"])
    if st in CLOSED_STATES and not owner_override:
        reasons.append(f"ROADMAP_CLOSED_MILESTONE_REOPENED_WOULD_RESULT:current_state={st}")
    if st != "NEXT" and not owner_override and st not in CLOSED_STATES:
        reasons.append(f"NOT_RECORDED_NEXT:current_state={st}")
    unsatisfied = [d for d in (target.get("dependencies") or []) if not _dependency_ok_for_active(milestones, d)]
    if unsatisfied:
        reasons.append("UNSATISFIED_DEPENDENCIES:" + ",".join(unsatisfied))
    conflicting = [m["milestone_id"] for m in milestones.values() if m.get("state") == "ACTIVE" and m.get("milestone_id") != milestone_id]
    if conflicting:
        reasons.append("CONFLICTING_ACTIVE_WRITER:" + ",".join(conflicting))
    return (len(reasons) == 0), reasons


def summary_counts(state: Mapping[str, Any]) -> dict[str, int]:
    milestones = list((state.get("milestones") or []))
    counts = {key: 0 for key in VALID_STATES}
    for m in milestones:
        st = m.get("state")
        if st in counts:
            counts[st] += 1
    return counts


# Optional coordinated development extension. Legacy current/milestones are unchanged.
# These records grant source-development scope only, never runtime or release authority.
LANE_SCHEMA = "stocklookup_development_lanes/1"
LANE_MODES = {"IMPLEMENTATION", "SHADOW", "READ_ONLY", "EXTERNAL_RESEARCH"}
LANE_STATES = {"ADMITTED", "ACTIVE", "PAUSED", "REVIEW_READY", "COMPLETE_LOCAL", "MERGED_RELEASED", "ABANDONED"}
LANE_TERMINAL = {"MERGED_RELEASED", "ABANDONED"}
SHARED_PATHS = (
    "docs/ROADMAP_STATE.json", "roadmap_execution_state.py", "tools/stocklookup_roadmap.py",
    ".github/", "config/", "AGENTS.md", "docs/AI_RULES.md", "docs/ACTIVE_STATE.md",
    "docs/AUTHORITY.md", "docs/ROADMAP_CURRENT.md", "docs/CAPABILITIES.md",
    "docs/DAILY_PIPELINE.md", "docs/NORTH_STAR.md", "requirements", "constraints.txt",
    "stocklookup.ps1", "stocklookup.py", "release_orchestrator.py",
    "tests/fixtures/e2e3_frozen_sources.json",
    ".gitignore", ".gitattributes", ".gitmodules", ".rgignore",
)
PROTECTED_PATHS = (".git/", "data/", "operations-review/", "dashboard-runtime/", "backups/", ".stocklookup/")


def _path_key(path: str) -> str:
    return str(Path(path).resolve()).replace("\\", "/").casefold()


def _scope_path(path: Any) -> bool:
    """Only exact relative paths or directory prefixes; no glob ambiguity/traversal."""
    return (isinstance(path, str) and bool(path) and path == path.strip()
            and not path.startswith("/") and "\\" not in path and ":" not in path
            and not any(c in path for c in "*?[]\x00\n\r")
            and all(p not in {"", ".", ".."} for p in path.rstrip("/").split("/")))


def path_owned(path: str, scope: str) -> bool:
    # Windows and case-sensitive hosts enforce the same conservative overlap contract.
    path, scope = path.casefold(), scope.casefold()
    return path.startswith(scope) if scope.endswith("/") else path == scope


def scope_overlap(a: str, b: str) -> bool:
    return path_owned(a.rstrip("/"), b) or path_owned(b.rstrip("/"), a) or a.casefold() == b.casefold()


def shared_path(path: str) -> bool:
    return (any(path_owned(path, p) for p in SHARED_PATHS)
            or "registry" in Path(path).name.casefold()
            or Path(path).name.casefold().startswith("requirements"))


def validate_development_control(state: Mapping[str, Any]) -> list[str]:
    control = state.get("development_control")
    if control is None:
        return []
    errors: list[str] = []
    if not isinstance(control, dict) or control.get("schema") != LANE_SCHEMA:
        return ["LANE_SCHEMA_INVALID"]
    if (not isinstance(control.get("revision"), int) or isinstance(control.get("revision"), bool)
            or control["revision"] < 1 or not isinstance(control.get("history"), list)
            or len(control["history"]) != control["revision"]
            or not all(control.get(k) for k in ("integration_agent", "integration_branch", "integration_worktree"))):
        return ["LANE_COORDINATOR_INVALID"]
    lanes = control.get("lanes")
    if not isinstance(lanes, list) or not all(isinstance(l, dict) for l in lanes):
        return errors + ["LANE_RECORDS_INVALID"]
    ids = [l.get("milestone_id") for l in lanes]
    if any(not isinstance(mid, str) or not mid for mid in ids) or len(set(map(str, ids))) != len(ids):
        return errors + ["LANE_DUPLICATE_OR_INVALID_ID"]
    legacy_ids = set(_milestones_by_id(state))
    for lane in lanes:
        mid = lane["milestone_id"]
        if mid in legacy_ids:
            errors.append(f"LANE_DUPLICATE_LEGACY_ID:{mid}")
        if (lane.get("mode") not in LANE_MODES or lane.get("state") not in LANE_STATES
                or lane.get("authority_effect") != "NONE"
                or not all(isinstance(lane.get(k), str) and lane[k].strip() for k in
                           ("responsible_agent", "branch", "worktree", "base_sha", "domain"))
                or not isinstance(lane.get("admission_authority"), dict)
                or lane.get("admission_authority", {}).get("kind") != "EXPLICIT_OWNER_DIRECTIVE"
                or not lane.get("admission_authority", {}).get("note")):
            errors.append(f"LANE_METADATA_INVALID:{mid}")
            continue
        if not Path(lane["worktree"]).is_absolute():
            errors.append(f"LANE_ABSOLUTE_WORKTREE_REQUIRED:{mid}")
        import re
        if not re.fullmatch(r"[0-9a-f]{40}", lane["base_sha"]):
            errors.append(f"LANE_EXACT_BASE_SHA_REQUIRED:{mid}")
        if lane.get("checkpoint") and (not isinstance(lane["checkpoint"], str) or not re.fullmatch(r"[0-9a-f]{40}", lane["checkpoint"])):
            errors.append(f"LANE_EXACT_CHECKPOINT_REQUIRED:{mid}")
        if lane.get("branch") in {"main", "master", control["integration_branch"]}:
            errors.append(f"LANE_MAIN_OR_COORDINATOR_BRANCH:{mid}")
        scopes = lane.get("allowed_paths")
        if not isinstance(scopes, list) or not scopes or not all(_scope_path(p) for p in scopes):
            errors.append(f"LANE_SCOPE_INVALID:{mid}")
            continue
        leases = lane.get("shared_paths")
        if not isinstance(leases, list) or not all(_scope_path(p) and not p.endswith("/") for p in leases):
            errors.append(f"LANE_SHARED_LEASE_INVALID:{mid}")
            continue
        for path in scopes:
            if any(scope_overlap(path, p) for p in PROTECTED_PATHS):
                errors.append(f"LANE_PROTECTED_SCOPE:{mid}:{path}")
            if (lane["mode"] in {"IMPLEMENTATION", "SHADOW"}
                    and (any(scope_overlap(path, p) for p in SHARED_PATHS) or shared_path(path)) and path not in leases):
                errors.append(f"LANE_SHARED_SCOPE_REQUIRES_EXACT_LEASE:{mid}:{path}")
        if leases and (lane.get("responsible_agent") != control["integration_agent"]
                       or not lane.get("lease_note") or not all(p in scopes for p in leases)):
            errors.append(f"LANE_SHARED_LEASE_NOT_INTEGRATION_OWNER:{mid}")
        deps = lane.get("dependencies")
        if not isinstance(deps, list) or any(d not in ids + list(legacy_ids) or d == mid for d in deps):
            errors.append(f"LANE_DEPENDENCY_INVALID:{mid}")
        for key in ("provides", "consumes"):
            if not isinstance(lane.get(key), dict) or not all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in lane[key].items()):
                errors.append(f"LANE_INTERFACE_INVALID:{mid}:{key}")
        if (not isinstance(lane.get("required_checks"), list) or not lane["required_checks"]
                or not all(isinstance(c, str) and c.strip() for c in lane["required_checks"])
                or len(set(lane["required_checks"])) != len(lane["required_checks"])):
            errors.append(f"LANE_CHECKS_REQUIRED:{mid}")
        if not isinstance(lane.get("history"), list):
            errors.append(f"LANE_HISTORY_REQUIRED:{mid}")
        if lane.get("mode") != "IMPLEMENTATION" and lane.get("state") in {"REVIEW_READY", "COMPLETE_LOCAL", "MERGED_RELEASED"}:
            errors.append(f"LANE_SHADOW_PROMOTION_FORBIDDEN:{mid}")
        if lane.get("state") in {"REVIEW_READY", "COMPLETE_LOCAL", "MERGED_RELEASED"} and not lane.get("checkpoint"):
            errors.append(f"LANE_CHECKPOINT_REQUIRED:{mid}")
    active = [l for l in lanes if l.get("state") not in LANE_TERMINAL]
    if errors:
        return sorted(set(errors))
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.get("branch") == b.get("branch") or _path_key(a.get("worktree", ".")) == _path_key(b.get("worktree", ".")):
                errors.append(f"LANE_WRITER_IDENTITY_OVERLAP:{a['milestone_id']}:{b['milestone_id']}")
            writers = a.get("mode") in {"IMPLEMENTATION", "SHADOW"} and b.get("mode") in {"IMPLEMENTATION", "SHADOW"}
            if writers and (a["domain"].casefold() == b["domain"].casefold() or any(scope_overlap(p, q) for p in a.get("allowed_paths", []) for q in b.get("allowed_paths", []))):
                errors.append(f"LANE_OWNERSHIP_OVERLAP:{a['milestone_id']}:{b['milestone_id']}")
    visiting, visited = set(), set()
    by_id = {l["milestone_id"]: l for l in lanes}
    def visit(mid: str) -> None:
        if mid in visiting:
            errors.append(f"LANE_DEPENDENCY_CYCLE:{mid}")
            return
        if mid in visited:
            return
        visiting.add(mid)
        for dep in by_id[mid].get("dependencies", []):
            if dep in by_id:
                visit(dep)
        visiting.remove(mid)
        visited.add(mid)
    for mid in by_id:
        visit(mid)
    return sorted(set(errors))


def lane_by_id(state: Mapping[str, Any], mid: str) -> dict[str, Any]:
    errors = validate_development_control(state)
    if errors:
        raise RoadmapStateError(";".join(errors))
    for lane in (state.get("development_control") or {}).get("lanes", []):
        if lane["milestone_id"] == mid:
            return lane
    raise RoadmapStateError(f"LANE_UNKNOWN:{mid}")


def prepare_declaration_amendment(state: Mapping[str, Any], spec: Any, *, repo: Path) -> tuple[dict, list[dict]]:
    """Prepare one atomic metadata-only correction; never write state or grant release.

    Caller must enforce the existing bound-owner directive/identity checks and use
    the native CAS writer. Existing state/checkpoint/ownership and history remain
    untouched. Dependencies may be added, never dropped by this narrow operation.
    """
    import copy
    fields = {"provides", "consumes", "dependencies"}
    if (not isinstance(spec, dict) or set(spec) != {"schema", "expected_revision", "amendments"}
            or spec.get("schema") != "stocklookup_lane_declaration_amendment/1"
            or not isinstance(spec.get("expected_revision"), int)
            or isinstance(spec["expected_revision"], bool)
            or not isinstance(spec.get("amendments"), list) or not spec["amendments"]):
        raise RoadmapStateError("LANE_DECLARATION_EXACT_SPEC_REQUIRED")
    control = state.get("development_control") or {}
    if spec["expected_revision"] != control.get("revision"):
        raise RoadmapStateError("LANE_DECLARATION_REVISION_CHANGED_RELOAD_REQUIRED")
    updated = copy.deepcopy(state)
    changes, selected = [], set()
    for item in spec["amendments"]:
        if (not isinstance(item, dict)
                or set(item) != {"milestone_id", "checkpoint", "before", "after", "review_note"}
                or not isinstance(item["milestone_id"], str)
                or not isinstance(item["review_note"], str) or not item["review_note"].strip()
                or any(not isinstance(item[k], dict) or set(item[k]) != fields for k in ("before", "after"))):
            raise RoadmapStateError("LANE_DECLARATION_RESERVED_OR_MISSING_FIELDS")
        mid = item["milestone_id"]
        if mid in selected:
            raise RoadmapStateError("LANE_DECLARATION_DUPLICATE_TARGET")
        selected.add(mid)
        lane = lane_by_id(updated, mid)
        if lane["mode"] != "IMPLEMENTATION" or lane["state"] not in {"REVIEW_READY", "COMPLETE_LOCAL"}:
            raise RoadmapStateError("LANE_DECLARATION_DURABLE_UNRELEASED_CANDIDATE_REQUIRED")
        if item["checkpoint"] != lane.get("checkpoint"):
            raise RoadmapStateError("LANE_DECLARATION_CHECKPOINT_MISMATCH")
        checked = check_lane(state, mid, repo=repo)
        if checked["errors"] or not checked["clean"] or checked["head"] != lane["checkpoint"]:
            raise RoadmapStateError("LANE_DECLARATION_EXACT_CLEAN_CHECKPOINT_REQUIRED:" + ";".join(checked["errors"]))
        before = {k: lane[k] for k in fields}
        if item["before"] != before:
            raise RoadmapStateError("LANE_DECLARATION_BEFORE_CHANGED_RELOAD_REQUIRED")
        if item["after"] == before:
            raise RoadmapStateError("LANE_DECLARATION_NO_CHANGE")
        deps = item["after"]["dependencies"]
        if (not isinstance(deps, list) or not all(isinstance(d, str) for d in deps)
                or len(deps) != len(set(deps)) or not set(before["dependencies"]).issubset(deps)):
            raise RoadmapStateError("LANE_DECLARATION_DEPENDENCY_REMOVAL_OR_INVALID")
        lane.update(copy.deepcopy(item["after"]))
        changes.append(copy.deepcopy(item))
    errors = validate_development_control(updated)
    if errors:
        raise RoadmapStateError(";".join(errors))
    peers = [l for l in updated["development_control"]["lanes"]
             if l["mode"] == "IMPLEMENTATION" and l["state"] != "ABANDONED"]
    for i, a in enumerate(peers):
        for b in peers[i + 1:]:
            if not {a["milestone_id"], b["milestone_id"]} & selected:
                continue
            for producer, consumer in ((a, b), (b, a)):
                for key, version in producer["provides"].items():
                    if key in consumer["provides"]:
                        errors.append(f"LANE_DUPLICATE_INTERFACE_OWNER:{key}")
                    if key in consumer["consumes"]:
                        if version != consumer["consumes"][key]:
                            errors.append(f"LANE_INTERFACE_VERSION_CONFLICT:{key}")
                        if producer["milestone_id"] not in consumer["dependencies"]:
                            errors.append(f"LANE_INTERFACE_DEPENDENCY_UNDECLARED:{key}")
    old_lanes = {l["milestone_id"]: l for l in control["lanes"]}
    previously_provided = {k for l in old_lanes.values() if l["mode"] == "IMPLEMENTATION"
                           and l["state"] != "ABANDONED" for k in l["provides"]}
    provided = {k for l in peers for k in l["provides"]}
    for lane in peers:
        for key in lane["consumes"]:
            newly_consumed = lane["milestone_id"] in selected and key not in old_lanes[lane["milestone_id"]]["consumes"]
            if key not in provided and (key in previously_provided or newly_consumed):
                errors.append(f"LANE_DECLARATION_INTERFACE_OWNER_MISSING:{key}")
    if errors:
        raise RoadmapStateError(";".join(sorted(set(errors))))
    return updated, sorted(changes, key=lambda item: item["milestone_id"])


def coordinator_host_available(state: Mapping[str, Any], repo: Path) -> bool:
    """Clone/CI metadata validation cannot certify another host's live worktrees."""
    control = state.get("development_control") if isinstance(state.get("development_control"), dict) else {}
    path = control.get("integration_worktree")
    if not isinstance(path, str) or not Path(path).is_dir():
        return False
    first = git_run(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    second = git_run(Path(path), "rev-parse", "--path-format=absolute", "--git-common-dir")
    return first[0] == second[0] == 0 and _path_key(first[1].strip()) == _path_key(second[1].strip())


def _full_sha(repo: Path, sha: Any) -> bool:
    import re
    return isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) is not None and git_object_type(repo, sha) == "commit"


def _changed_paths(repo: Path, base: str) -> tuple[list[str], list[str]]:
    """Include committed, staged, unstaged, untracked and both sides of renames."""
    errors, paths = [], set()
    for args in (("diff", "--no-renames", "--name-only", "-z", base, "HEAD"),
                 ("diff", "--no-renames", "--name-only", "-z", "HEAD"),
                 ("ls-files", "--others", "--exclude-standard", "-z")):
        code, out, _ = git_run(repo, *args)
        if code:
            errors.append("LANE_GIT_DIFF_UNAVAILABLE")
        else:
            paths.update(p for p in out.split("\x00") if p)
    return sorted(paths), errors


def identity_sensitive_paths(repo: Path, base: str) -> set[str]:
    """Read only the small, existing reviewed source/launcher manifests at base.

    This is a navigation guard, not an exhaustive model of dynamic code identities;
    explicit frozen/source-contract review remains mandatory for every integration.
    """
    sensitive = set(SHARED_PATHS)
    for path in ("tests/fixtures/e2e3_frozen_sources.json", "config/daily_path_launchers.json"):
        code, out, _ = git_run(repo, "show", base + ":" + path)
        if code:
            continue  # Hermetic/minimal repositories may have no Producer manifests.
        try:
            manifest = json.loads(out)
            sensitive.update(manifest.get("source_sha256_lf", {}))
            sensitive.update(manifest.get("python_callers", {}))
            sensitive.update(manifest.get("non_python_callers", {}))
        except (ValueError, TypeError, AttributeError) as exc:
            raise RoadmapStateError("LANE_FROZEN_MANIFEST_INVALID:" + path) from exc
    return sensitive


def check_lane(state: Mapping[str, Any], mid: str, *, repo: Path) -> dict[str, Any]:
    lane = lane_by_id(state, mid)
    errors = validate_development_control(state)
    if errors:
        return {"milestone_id": mid, "head": None, "paths": [], "clean": False,
                "errors": errors, "unmet_dependencies": [], "authority_effect": "NONE", "runtime_authorized": False}
    wt = Path(lane["worktree"])
    registered = git_worktrees(repo)
    match = next((w for w in registered if _path_key(w["worktree"]) == _path_key(str(wt))), None)
    if not match or not wt.is_dir() or match.get("branch") != "refs/heads/" + lane["branch"]:
        errors.append("LANE_WORKTREE_BRANCH_MISMATCH")
    if match and (match.get("locked") or match.get("prunable")):
        errors.append("LANE_WORKTREE_LOCKED_OR_MISSING")
    # Ensure it is really this Git repository, not a replaced directory with another .git.
    def common(root: Path) -> str:
        code, value, _ = git_run(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        return _path_key(value.strip()) if code == 0 else ""
    if not common(wt) or common(wt) != common(repo):
        errors.append("LANE_REPOSITORY_MISMATCH")
    head = git_head(wt)
    if git_branch(wt) != lane["branch"] or head != (match or {}).get("head"):
        errors.append("LANE_LIVE_HEAD_MISMATCH")
    code, branch_head, _ = git_run(repo, "rev-parse", "refs/heads/" + lane["branch"])
    if code or branch_head.strip() != head:
        errors.append("LANE_BRANCH_HEAD_MISMATCH")
    if not _full_sha(repo, lane["base_sha"]) or not head or not git_is_ancestor(repo, lane["base_sha"], head):
        errors.append("LANE_BASE_NOT_ANCESTOR")
        return {"milestone_id": mid, "head": head, "paths": [], "clean": False,
                "errors": sorted(set(errors)), "unmet_dependencies": [], "authority_effect": "NONE", "runtime_authorized": False}
    checkpoint = lane.get("checkpoint")
    if checkpoint and (not _full_sha(repo, checkpoint) or not head or not git_is_ancestor(repo, checkpoint, head)):
        errors.append("LANE_CHECKPOINT_NOT_ANCESTOR")
    paths, diff_errors = _changed_paths(wt, lane["base_sha"])
    errors += diff_errors
    sensitive = identity_sensitive_paths(repo, lane["base_sha"])
    for path in paths:
        if (not _scope_path(path) or any(path_owned(path, p) for p in PROTECTED_PATHS)
                or not any(path_owned(path, p) for p in lane["allowed_paths"])
                or (shared_path(path) or path in sensitive) and path not in lane["shared_paths"]):
            errors.append("LANE_PROHIBITED_CHANGE:" + path)
    if lane["mode"] in {"READ_ONLY", "EXTERNAL_RESEARCH"} and paths:
        errors.append("LANE_READ_ONLY_CHANGE")
    code, status, _ = git_run(wt, "status", "--porcelain", "--untracked-files=all")
    if code:
        errors.append("LANE_STATUS_UNAVAILABLE")
    for scope in lane["allowed_paths"]:
        if lane["mode"] in {"IMPLEMENTATION", "SHADOW"} and any(path_owned(path, scope) for path in sensitive) and scope not in lane["shared_paths"]:
            errors.append("LANE_FROZEN_SCOPE_REQUIRES_EXACT_LEASE:" + scope)
    control = state["development_control"]
    all_deps = {m["milestone_id"]: m for m in state.get("milestones", [])}
    all_deps.update({l["milestone_id"]: l for l in control["lanes"]})
    unmet = [d for d in lane["dependencies"] if all_deps.get(d, {}).get("state") not in {"COMPLETE", "SUPERSEDED", "COMPLETE_LOCAL", "MERGED_RELEASED"}]
    if lane["state"] == "ACTIVE" and unmet:
        errors.append("LANE_DEVELOPMENT_DEPENDENCIES_UNSATISFIED:" + ",".join(unmet))
    return {"milestone_id": mid, "head": head, "branch": lane["branch"], "worktree": str(wt),
            "paths": paths, "clean": code == 0 and not status.strip(),
            "state": lane["state"], "mode": lane["mode"], "unmet_dependencies": unmet,
            "errors": sorted(set(errors)), "authority_effect": "NONE", "runtime_authorized": False}


def integration_plan(state: Mapping[str, Any], *, repo: Path, main_sha: str,
                     receipts: Mapping[str, Any] | None = None, candidate_id: str | None = None) -> dict[str, Any]:
    """Bounded metadata-only plan. Never fetch, merge, rebase, run checks or promote."""
    errors = validate_development_control(state)
    if errors:
        raise RoadmapStateError(";".join(errors))
    control = state.get("development_control") or {}
    if not control:
        raise RoadmapStateError("LANE_COORDINATOR_NOT_INITIALIZED")
    if not _full_sha(repo, main_sha):
        raise RoadmapStateError("LANE_EXACT_MAIN_SHA_REQUIRED")
    # Remote-tracking metadata alone is explicitly insufficient. No ref writes.
    code, remote, _ = git_run(repo, "ls-remote", "origin", "refs/heads/main")
    code2, tracking, _ = git_run(repo, "rev-parse", "refs/remotes/origin/main")
    if code or not remote.strip() or remote.split()[0] != main_sha or code2 or tracking.strip() != main_sha:
        errors.append("LANE_REMOTE_MAIN_STALE_OR_UNVERIFIED")
    coordinator = Path(control["integration_worktree"])
    coordinator_head = git_head(coordinator) if coordinator_host_available(state, repo) else None
    coordinator_paths, coordinator_errors = _changed_paths(coordinator, coordinator_head) if coordinator_head else ([], ["LANE_COORDINATOR_HOST_UNAVAILABLE"])
    errors += coordinator_errors
    source_dirty = [p for p in coordinator_paths if p != "docs/ROADMAP_STATE.json"]
    if source_dirty:
        errors.append("LANE_COORDINATOR_SOURCE_DIRTY:" + ",".join(source_dirty))
    lanes = [l for l in control["lanes"] if l["mode"] == "IMPLEMENTATION" and l["state"] not in LANE_TERMINAL]
    if candidate_id:
        lanes = [l for l in lanes if l["milestone_id"] == candidate_id]
        if not lanes:
            raise RoadmapStateError("LANE_INTEGRATION_CANDIDATE_UNKNOWN")
    rows = {l["milestone_id"]: check_lane(state, l["milestone_id"], repo=repo) for l in lanes}
    main_paths = {}
    for lane in lanes:
        mid, row = lane["milestone_id"], rows[lane["milestone_id"]]
        errors += [mid + ":" + e for e in row["errors"]]
        if not row["clean"]:
            errors.append(f"LANE_DIRTY_CANDIDATE:{mid}")
        if lane["state"] not in {"REVIEW_READY", "COMPLETE_LOCAL"} or lane.get("checkpoint") != row["head"]:
            errors.append(f"LANE_NOT_EXACT_REVIEW_CANDIDATE:{mid}")
        if not git_is_ancestor(repo, lane["base_sha"], main_sha):
            errors.append(f"LANE_MAIN_BASE_DIVERGED:{mid}")
        code, out, _ = git_run(repo, "diff", "--no-renames", "--name-only", "-z", lane["base_sha"], main_sha)
        main_paths[mid] = sorted(p for p in out.split("\x00") if p) if code == 0 else []
        if code:
            errors.append(f"LANE_MAIN_DIFF_UNAVAILABLE:{mid}")
        overlap = sorted(set(main_paths[mid]) & set(row["paths"]))
        if overlap and not (git_is_ancestor(repo, main_sha, row["head"]) or git_is_ancestor(repo, row["head"], main_sha)):
            errors.append(f"LANE_MAIN_CHANGED_FILE_OVERLAP:{mid}:" + ",".join(overlap))
        for dep in lane["dependencies"]:
            other = next((l for l in control["lanes"] if l["milestone_id"] == dep), None)
            legacy = _milestones_by_id(state).get(dep)
            if other and (other["state"] != "MERGED_RELEASED" or not other.get("release_sha") or not git_is_ancestor(repo, other["release_sha"], main_sha)):
                errors.append(f"LANE_DEPENDENCY_NOT_RELEASED:{mid}:{dep}")
            if legacy and (legacy.get("state") not in CLOSED_STATES or not legacy.get("checkpoint") or not git_is_ancestor(repo, legacy["checkpoint"], main_sha)):
                errors.append(f"LANE_LEGACY_DEPENDENCY_NOT_ON_MAIN:{mid}:{dep}")
    semantic_risks = []
    selected = {l["milestone_id"] for l in lanes}
    peers = [l for l in control["lanes"] if l["mode"] == "IMPLEMENTATION" and l["state"] != "ABANDONED"]
    for i, a in enumerate(peers):
        for b in peers[i + 1:]:
            if not {a["milestone_id"], b["milestone_id"]} & selected:
                continue
            overlap = sorted(set(rows.get(a["milestone_id"], {}).get("paths", [])) & set(rows.get(b["milestone_id"], {}).get("paths", [])))
            if overlap:
                errors.append(f"LANE_CHANGED_FILE_OVERLAP:{a['milestone_id']}:{b['milestone_id']}:" + ",".join(overlap))
            for producer, consumer in ((a, b), (b, a)):
                for key, version in producer["provides"].items():
                    if key in consumer["provides"]:
                        errors.append(f"LANE_DUPLICATE_INTERFACE_OWNER:{key}")
                    if key in consumer["consumes"]:
                        semantic_risks.append({"interface": key, "producer": producer["milestone_id"], "consumer": consumer["milestone_id"]})
                        if version != consumer["consumes"][key]:
                            errors.append(f"LANE_INTERFACE_VERSION_CONFLICT:{key}")
                        if consumer["milestone_id"] in selected and producer["milestone_id"] not in consumer["dependencies"]:
                            errors.append(f"LANE_INTERFACE_DEPENDENCY_UNDECLARED:{key}")
    order, todo = [], {l["milestone_id"]: l for l in lanes}
    while todo:
        ready = sorted(mid for mid, l in todo.items() if not set(l["dependencies"]) & set(todo))
        if not ready:
            errors.append("LANE_INTEGRATION_CYCLE")
            break
        for mid in ready:
            order.append(mid)
            del todo[mid]
    sensitive = identity_sensitive_paths(repo, main_sha)
    plan = {"schema": "stocklookup_integration_plan/1", "main_sha": main_sha,
            "coordinator_head": coordinator_head, "coordinator_source_changes": source_dirty,
            "coordinator_native_state_dirty": "docs/ROADMAP_STATE.json" in coordinator_paths,
            "heads": {mid: rows[mid]["head"] for mid in sorted(rows)}, "order": order,
            "changed_paths": {mid: rows[mid]["paths"] for mid in sorted(rows)},
            "main_changes_since_base": main_paths, "semantic_dependencies": semantic_risks,
            "declared_interfaces": {l["milestone_id"]: {k: l[k] for k in ("provides", "consumes")} for l in lanes},
            "dependencies": {l["milestone_id"]: l["dependencies"] for l in lanes},
            "lane_context": {l["milestone_id"]: {k: l[k] for k in
                             ("responsible_agent", "branch", "worktree", "base_sha", "domain",
                              "allowed_paths", "shared_paths", "admission_authority")} for l in lanes},
            "peer_interfaces": {l["milestone_id"]: {k: l[k] for k in ("provides", "consumes", "state", "checkpoint")} for l in peers},
            "required_checks": {l["milestone_id"]: l["required_checks"] for l in lanes},
            "shared_and_frozen_review": sorted({p for row in rows.values() for p in row["paths"] if shared_path(p) or p in sensitive}),
            "authority_effect": "NONE", "runtime_authorized": False, "merge_authorized": False}
    plan["plan_identity"] = stable_id(plan)
    # Human semantic/cross-repo/frozen review and actual test receipts are mandatory:
    # a static disjoint-file calculation alone cannot establish integration safety.
    receipt = receipts or {}
    if (receipt.get("plan_identity") != plan["plan_identity"] or receipt.get("reviewed_by") != control["integration_agent"]
            or not receipt.get("review_note") or not receipt.get("cross_repo_review")
            or not receipt.get("frozen_identity_review")):
        errors.append("LANE_EXACT_INTEGRATION_REVIEW_REQUIRED")
    for mid, checks in plan["required_checks"].items():
        for check in checks:
            result = (receipt.get("checks") or {}).get(mid, {}).get(check, {})
            if result.get("status") != "PASS" or not result.get("evidence"):
                errors.append(f"LANE_INTEGRATION_CHECK_REQUIRED:{mid}:{check}")
    plan["errors"] = sorted(set(errors))
    plan["disposition"] = "BLOCKED" if errors else "READY_FOR_OWNER_REVIEW"
    return plan
