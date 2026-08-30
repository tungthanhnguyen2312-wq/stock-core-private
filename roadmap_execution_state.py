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


@dataclass(frozen=True)
class RoadmapReport:
    state: Mapping[str, Any]
    findings: tuple[Finding, ...]
    overall: str
    content_identity: str

    def findings_at_or_above(self, severity: str) -> tuple[Finding, ...]:
        rank = _SEVERITY_RANK[severity]
        return tuple(f for f in self.findings if _SEVERITY_RANK[f.severity] <= rank)

    def category_status(self, category: str) -> str:
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
    return run_utf8(["git", "-C", str(repo), *args])


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
    for m in milestones.values():
        mid = m.get("milestone_id")
        if m.get("state") != "COMPLETE":
            continue
        checkpoint = m.get("checkpoint")
        if not checkpoint:
            findings.append(Finding("ROADMAP_CHECKPOINT_MISSING", FAIL, f"{mid} is COMPLETE but has no checkpoint recorded", mid))
            continue
        if repo is None:
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
    if repo is not None:
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

    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.category, f.code, f.message))
    overall = "DRIFT_DETECTED" if any(f.severity == FAIL for f in findings) else "ON_TRACK"
    identity = stable_id({"state": state, "overall": overall})
    return RoadmapReport(state=state, findings=tuple(findings), overall=overall, content_identity=identity)


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
        findings.append(Finding("ROADMAP_MULTIPLE_SOURCE_WRITERS", INFO, f"{len(ahead_worktrees)} worktree(s) ahead of recorded implementation_lineage_head (normal parallel exploration): {', '.join(ahead_worktrees)}"))

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
        return False, ["ALREADY_ACTIVE"]
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
