"""Safe one-way source deploy tool — Phase 4A.

Deploys Git-tracked source files from THIS private repository to a runtime
workspace (private repo -> runtime, one direction only). Never writes back
to the private repo. Dry-run by default; real writes require --apply AND
--confirm DEPLOY_AUTHENTIC_SOURCE.

This file is intentionally duplicated byte-for-byte between
vnstock-core-private/tools/safe_deploy.py and
ai-analyze-core-private/tools/safe_deploy.py so neither private repo has a
runtime dependency on the other (matches the "no monorepo, no submodule"
decision in AUTHORITATIVE_SOURCE_AND_RUNTIME_PLAN.md section 8.3).
Project-specific behavior (allowlist, denylist, destination, size limit)
lives entirely in deploy_config.json. If you fix a bug here, apply the same
fix to the twin copy in the other repo.

Stdlib only, no third-party dependencies.
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

TOOL_VERSION = "1.0.0"
CONFIRM_TOKEN = "DEPLOY_AUTHENTIC_SOURCE"
DEFAULT_SIZE_LIMIT_BYTES = 5 * 1024 * 1024  # 5 MiB
DEFAULT_BACKUP_ROOT = Path(
    r"C:\Users\tungt\OneDrive\Documents\ProjectBackups\SourceDeployments"
)

_SECRET_PATTERNS = [
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk-[a-zA-Z0-9]{20,}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
]

REPO_ROOT = Path(__file__).resolve().parent.parent


class DeployError(Exception):
    """Fatal error — abort before touching anything."""


# --------------------------------------------------------------------------
# git helpers — all read-only against the SOURCE repo; never mutate it.
# --------------------------------------------------------------------------

def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise DeployError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def git_status_dirty_tracked(repo: Path) -> list[str]:
    """Return non-empty list if any TRACKED file has uncommitted changes.

    Untracked files ('??' lines) are deliberately ignored here.
    SOURCE_BASELINE_ADDITIONS.sanitized.json is intentionally kept
    untracked forever in both private repos (see
    SOURCE_CONTROL_BASELINE_COMPLETION_REPORT.md section 8) — treating '??'
    as "dirty" would make this tool permanently refuse to run. What
    actually matters for deploy correctness is that no TRACKED file's
    working-tree content differs from what HEAD (and therefore `git show
    HEAD:<path>`) will hand back as the deploy source.
    """
    out = _run_git(repo, "status", "--porcelain")
    return [line for line in out.splitlines() if line.strip() and not line.startswith("??")]


def git_current_branch(repo: Path) -> str:
    return _run_git(repo, "branch", "--show-current").strip()


def git_head_commit(repo: Path) -> str:
    return _run_git(repo, "rev-parse", "HEAD").strip()


def git_tags_at_head(repo: Path) -> list[str]:
    out = _run_git(repo, "tag", "--points-at", "HEAD")
    return sorted(t for t in out.splitlines() if t.strip())


def git_ls_files(repo: Path) -> list[str]:
    out = _run_git(repo, "ls-files")
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def git_show_bytes(repo: Path, commit: str, rel_path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{rel_path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeployError(
            f"git show {commit}:{rel_path} failed: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return result.stdout


# --------------------------------------------------------------------------
# pattern matching for allowlist / denylist / runtime scan globs
# --------------------------------------------------------------------------

def match_pattern(rel_path: str, pattern: str) -> bool:
    """Minimal glob matcher, deliberately simple (no external deps).

    - 'dir/**'  -> matches 'dir' itself and everything under 'dir/'.
    - 'name'    -> exact match on a root-level path (no '/').
    - '*.ext'   -> fnmatch against root-level files only (no '/' allowed in
                   the candidate path) — this is what keeps '*.py' scoped
                   to the repo root instead of recursing into tests/.
    - anything else -> fnmatchcase against the full relative path.
    """
    rel_path = rel_path.replace("\\", "/")
    pattern = pattern.replace("\\", "/")
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel_path == prefix or rel_path.startswith(prefix + "/")
    if "/" not in pattern:
        if "/" in rel_path:
            return False
        return fnmatch.fnmatchcase(rel_path, pattern)
    return fnmatch.fnmatchcase(rel_path, pattern)


def matches_any(rel_path: str, patterns: list[str]) -> bool:
    return any(match_pattern(rel_path, p) for p in patterns)


# --------------------------------------------------------------------------
# symlink / junction / path-traversal guards
# --------------------------------------------------------------------------

def is_symlink_or_junction(path: Path) -> bool:
    """True if path is a symlink OR a Windows reparse point (junction).

    Path.is_symlink() alone is not reliable for Windows junctions across
    all Python versions, so this also checks FILE_ATTRIBUTE_REPARSE_POINT
    directly via ctypes (stdlib-only, no extra dependency).
    """
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    if os.name == "nt" and path.exists():
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            if attrs != -1 and (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
                return True
        except OSError:
            pass
    return False


class BlockedPathError(Exception):
    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(message)


def resolve_dest_path(dest_root: Path, rel_path: str) -> Path:
    """Resolve rel_path under dest_root, refusing to follow any symlink or
    junction found along the way.

    'Never follow' is unconditional here: every existing path component is
    checked for being a reparse point BEFORE we ever call .resolve() on the
    full path, so a junction that happens to stay inside dest_root is
    still rejected, not just one that would escape it. The escape check
    below is a second, independent guard against path traversal (e.g. a
    '..'-free but symlink-mediated redirect, or any other way .resolve()
    could land outside dest_root).
    """
    parts = Path(rel_path).parts
    if ".." in parts or Path(rel_path).is_absolute():
        raise BlockedPathError("path_traversal", f"suspicious relative path: {rel_path}")
    dest_root_resolved = dest_root.resolve()
    current = dest_root_resolved
    for part in parts:
        current = current / part
        if current.exists() and is_symlink_or_junction(current):
            raise BlockedPathError(
                "symlink_or_junction_in_path", f"symlink or junction in path: {current}"
            )
    candidate = (dest_root_resolved / rel_path).resolve()
    if candidate != dest_root_resolved and dest_root_resolved not in candidate.parents:
        raise BlockedPathError("path_traversal", f"destination escapes runtime root: {rel_path}")
    return candidate


# --------------------------------------------------------------------------
# secret / size scanning
# --------------------------------------------------------------------------

def scan_for_secrets(data: bytes) -> list[str]:
    hits = []
    for pattern in _SECRET_PATTERNS:
        if pattern.search(data):
            hits.append(pattern.pattern.decode("utf-8", errors="replace"))
    return hits


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

@dataclasses.dataclass
class DeployConfig:
    project: str
    runtime_destination: Path
    allowed_branches: list[str]
    size_limit_bytes: int
    allowlist: list[str]
    denylist: list[str]
    runtime_scan_globs: list[str]

    @staticmethod
    def load(path: Path) -> "DeployConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        return DeployConfig(
            project=data["project"],
            runtime_destination=Path(data["runtime_destination"]),
            allowed_branches=data.get("allowed_branches", ["main"]),
            size_limit_bytes=data.get("size_limit_bytes", DEFAULT_SIZE_LIMIT_BYTES),
            allowlist=data["allowlist"],
            denylist=data.get("denylist", []),
            runtime_scan_globs=data.get("runtime_scan_globs", data["allowlist"]),
        )


# --------------------------------------------------------------------------
# deploy state (outside git, .deploy/state/<project>.json)
# --------------------------------------------------------------------------

def load_deploy_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_deploy_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(state_path, json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8"))


def load_approved_paths(approve_baseline: Optional[Path], approve_files: list[str]) -> set[str]:
    approved: set[str] = set(approve_files)
    if approve_baseline is not None:
        data = json.loads(approve_baseline.read_text(encoding="utf-8"))
        approved.update(data.get("approved_paths", []))
    return approved


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------

@dataclasses.dataclass
class FileRecord:
    rel_path: str
    classification: str  # unchanged | create | update | blocked | excluded_not_allowlisted
    block_reason: Optional[str] = None
    source_sha256: Optional[str] = None
    runtime_sha256: Optional[str] = None
    last_deploy_sha256: Optional[str] = None
    size_bytes: Optional[int] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def classify_file(
    runtime_exists: bool,
    source_hash: str,
    runtime_hash: Optional[str],
    last_deploy_hash: Optional[str],
    rel_path: str,
    approved_paths: set[str],
) -> tuple[str, Optional[str]]:
    if not runtime_exists:
        return "create", None
    if runtime_hash == source_hash:
        return "unchanged", None
    # runtime differs from source
    if last_deploy_hash is None:
        if rel_path in approved_paths:
            return "update", None
        return "blocked", "initial_difference_unapproved"
    if runtime_hash == last_deploy_hash:
        return "update", None  # safe update: runtime untouched since last deploy
    return "blocked", "runtime_drift"


# --------------------------------------------------------------------------
# runtime-only scan (files present at destination, absent from source)
# --------------------------------------------------------------------------

_RUNTIME_SCAN_IGNORE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_RUNTIME_SCAN_IGNORE_SUFFIXES = {".pyc", ".pyo"}


def _is_runtime_scan_noise(path: Path) -> bool:
    """Bytecode caches etc. are never source and never meaningfully
    'runtime-only' in the sense this report cares about -- every real
    Python invocation regenerates them, so including them just buries the
    signal (files a human should actually look at) under noise."""
    if path.suffix in _RUNTIME_SCAN_IGNORE_SUFFIXES:
        return True
    return any(part in _RUNTIME_SCAN_IGNORE_DIR_NAMES for part in path.parts)


def iter_runtime_files_for_pattern(dest_root: Path, pattern: str):
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        base = dest_root / prefix
        if not base.exists() or is_symlink_or_junction(base):
            return
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirpath_p = Path(dirpath)
            dirnames[:] = [
                d for d in dirnames
                if not is_symlink_or_junction(dirpath_p / d) and d not in _RUNTIME_SCAN_IGNORE_DIR_NAMES
            ]
            for fname in filenames:
                fpath = dirpath_p / fname
                if not is_symlink_or_junction(fpath) and not _is_runtime_scan_noise(fpath):
                    yield fpath
    elif "/" not in pattern:
        if not dest_root.exists():
            return
        for p in dest_root.glob(pattern):
            if p.is_file() and not is_symlink_or_junction(p) and not _is_runtime_scan_noise(p):
                yield p


def scan_runtime_only(dest_root: Path, runtime_scan_globs: list[str], known_rel_paths: set[str]) -> list[str]:
    found: set[str] = set()
    dest_root_resolved = dest_root.resolve()
    for pattern in runtime_scan_globs:
        for path in iter_runtime_files_for_pattern(dest_root_resolved, pattern):
            rel = path.resolve().relative_to(dest_root_resolved).as_posix()
            if rel not in known_rel_paths:
                found.add(rel)
    return sorted(found)


# --------------------------------------------------------------------------
# atomic write / backup
# --------------------------------------------------------------------------

def atomic_write(dest_path: Path, data: bytes) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest_path.parent), prefix=".safe_deploy_tmp_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, str(dest_path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def backup_file(dest_path: Path, backup_dir: Path, rel_path: str) -> Path:
    backup_path = backup_dir / rel_path
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dest_path, backup_path)
    return backup_path


# --------------------------------------------------------------------------
# plan building — shared by dry-run and apply
# --------------------------------------------------------------------------

@dataclasses.dataclass
class DeployPlan:
    project: str
    mode: str
    timestamp: str
    source_repo: str
    source_branch: str
    source_head: str
    source_tags: list[str]
    runtime_destination: str
    files: list[FileRecord]
    runtime_only_files: list[str]
    estimated_backup_bytes: int
    backup_root: str

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for f in self.files:
            counts[f.classification] = counts.get(f.classification, 0) + 1
        return counts

    def blocked(self) -> list[FileRecord]:
        return [f for f in self.files if f.classification == "blocked"]

    def backup_preview(self) -> list[dict]:
        """Simulated backup + rollback manifest for the files an apply
        would update. Never executed in dry-run — this is what WOULD
        happen, per Phase 4A section 8 ('Dry-run phải mô phỏng: file nào
        sẽ được backup, backup path dự kiến, rollback manifest dự kiến')."""
        backup_dir = Path(self.backup_root) / self.project / self.timestamp
        preview = []
        for f in self.files:
            if f.classification != "update":
                continue
            backup_path = backup_dir / f.rel_path
            preview.append({
                "rel_path": f.rel_path,
                "size_bytes": f.size_bytes,
                "would_backup_to": str(backup_path),
                "rollback_restore_from": str(backup_path),
                "rollback_restore_to": str(Path(self.runtime_destination) / f.rel_path),
                "rollback_verifies_sha256": f.runtime_sha256,
            })
        return preview

    def to_manifest_dict(self) -> dict:
        return {
            "tool_version": TOOL_VERSION,
            "project": self.project,
            "mode": self.mode,
            "timestamp": self.timestamp,
            "source_repo": self.source_repo,
            "source_branch": self.source_branch,
            "source_head": self.source_head,
            "source_tags": self.source_tags,
            "runtime_destination": self.runtime_destination,
            "candidate_file_count": len(self.files),
            "summary": self.summary(),
            "files": [f.to_dict() for f in self.files],
            "runtime_only_files": self.runtime_only_files,
            "estimated_backup_bytes": self.estimated_backup_bytes,
            "backup_root": self.backup_root,
            "backup_and_rollback_preview": self.backup_preview(),
        }


def build_plan(
    repo: Path,
    config: DeployConfig,
    dest_root: Path,
    state: dict,
    approved_paths: set[str],
    mode: str,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
) -> DeployPlan:
    tracked = git_ls_files(repo)
    head = git_head_commit(repo)
    branch = git_current_branch(repo)
    tags = git_tags_at_head(repo)
    last_deploy_hashes: dict[str, str] = state.get("files", {})

    records: list[FileRecord] = []
    known_rel_paths: set[str] = set()

    for rel_path in tracked:
        if not matches_any(rel_path, config.allowlist):
            records.append(FileRecord(rel_path=rel_path, classification="excluded_not_allowlisted"))
            continue
        known_rel_paths.add(rel_path)

        if matches_any(rel_path, config.denylist):
            records.append(FileRecord(rel_path=rel_path, classification="blocked", block_reason="denylist_match"))
            continue

        try:
            dest_path = resolve_dest_path(dest_root, rel_path)
        except BlockedPathError as exc:
            records.append(FileRecord(rel_path=rel_path, classification="blocked", block_reason=exc.reason))
            continue

        source_bytes = git_show_bytes(repo, head, rel_path)
        size_bytes = len(source_bytes)

        if size_bytes > config.size_limit_bytes:
            records.append(FileRecord(
                rel_path=rel_path, classification="blocked", block_reason="oversized",
                size_bytes=size_bytes,
            ))
            continue

        secret_hits = scan_for_secrets(source_bytes)
        if secret_hits:
            records.append(FileRecord(
                rel_path=rel_path, classification="blocked",
                block_reason=f"possible_secret:{','.join(secret_hits)}", size_bytes=size_bytes,
            ))
            continue

        source_hash = sha256_bytes(source_bytes)
        runtime_exists = dest_path.exists()
        runtime_hash = sha256_file(dest_path) if runtime_exists else None
        last_deploy_hash = last_deploy_hashes.get(rel_path)

        classification, block_reason = classify_file(
            runtime_exists, source_hash, runtime_hash, last_deploy_hash, rel_path, approved_paths,
        )
        records.append(FileRecord(
            rel_path=rel_path,
            classification=classification,
            block_reason=block_reason,
            source_sha256=source_hash,
            runtime_sha256=runtime_hash,
            last_deploy_sha256=last_deploy_hash,
            size_bytes=size_bytes,
        ))

    runtime_only = scan_runtime_only(dest_root, config.runtime_scan_globs, known_rel_paths)

    estimated_backup_bytes = sum(
        (r.size_bytes or 0) for r in records if r.classification == "update"
    )

    return DeployPlan(
        project=config.project,
        mode=mode,
        timestamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        source_repo=str(repo),
        source_branch=branch,
        source_head=head,
        source_tags=tags,
        runtime_destination=str(dest_root),
        backup_root=str(backup_root),
        files=records,
        runtime_only_files=runtime_only,
        estimated_backup_bytes=estimated_backup_bytes,
    )


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------

def apply_plan(repo: Path, plan: DeployPlan, dest_root: Path, backup_root: Path) -> dict:
    """Write create/update files atomically. Caller MUST have already
    verified plan.blocked() is empty — this function refuses to run
    otherwise, as a second independent gate (defense in depth)."""
    if plan.blocked():
        raise DeployError(
            f"refusing to apply: {len(plan.blocked())} blocked file(s) present"
        )

    backup_dir = backup_root / plan.project / plan.timestamp
    backed_up: list[dict] = []
    written: list[str] = []

    for record in plan.files:
        if record.classification not in ("create", "update"):
            continue
        dest_path = resolve_dest_path(dest_root, record.rel_path)
        if record.classification == "update" and dest_path.exists():
            backup_path = backup_file(dest_path, backup_dir, record.rel_path)
            backed_up.append({"rel_path": record.rel_path, "backup_path": str(backup_path)})
        data = git_show_bytes(repo, plan.source_head, record.rel_path)
        atomic_write(dest_path, data)
        written.append(record.rel_path)

    new_state = {
        "project": plan.project,
        "last_deployed_source_commit": plan.source_head,
        "last_deploy_timestamp": plan.timestamp,
        "runtime_destination": str(dest_root),
        "deploy_result": "success",
        "files": {
            r.rel_path: r.source_sha256
            for r in plan.files
            if r.classification in ("create", "update", "unchanged")
        },
    }
    return {"written": written, "backed_up": backed_up, "backup_dir": str(backup_dir), "new_state": new_state}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "tools" / "deploy_config.json")
    parser.add_argument("--target", type=Path, default=None, help="Override runtime destination from config (used for testing).")
    parser.add_argument("--apply", action="store_true", help="Actually write. Requires --confirm too.")
    parser.add_argument("--confirm", type=str, default=None, help=f"Must equal {CONFIRM_TOKEN} to allow --apply.")
    parser.add_argument("--branch", type=str, default=None, help="Override the single allowed branch check.")
    parser.add_argument("--state-file", type=Path, default=None, help="Override .deploy/state/<project>.json path (testing).")
    parser.add_argument("--preview-dir", type=Path, default=None, help="Override .deploy/previews/ path (testing).")
    parser.add_argument("--backup-root", type=Path, default=None, help="Override backup root (testing).")
    parser.add_argument("--approve-initial-baseline", type=Path, default=None, help="JSON file with an 'approved_paths' list.")
    parser.add_argument("--approve-file", action="append", default=[], help="Repeatable: pre-approve one relative path for INITIAL_DIFFERENCE.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.apply and args.confirm != CONFIRM_TOKEN:
        print(f"REFUSED: --apply requires --confirm {CONFIRM_TOKEN}", file=sys.stderr)
        return 2

    mode = "apply" if (args.apply and args.confirm == CONFIRM_TOKEN) else "dry-run"

    config = DeployConfig.load(args.config)
    repo = REPO_ROOT
    dest_root = args.target if args.target is not None else config.runtime_destination
    allowed_branches = [args.branch] if args.branch else config.allowed_branches
    state_path = args.state_file if args.state_file is not None else repo / ".deploy" / "state" / f"{config.project}.json"
    preview_dir = args.preview_dir if args.preview_dir is not None else repo / ".deploy" / "previews"
    backup_root = args.backup_root if args.backup_root is not None else DEFAULT_BACKUP_ROOT

    dirty = git_status_dirty_tracked(repo)
    if dirty:
        print("REFUSED: source repo has uncommitted changes to tracked files:", file=sys.stderr)
        for line in dirty:
            print(f"  {line}", file=sys.stderr)
        return 2

    branch = git_current_branch(repo)
    if branch not in allowed_branches:
        print(f"REFUSED: branch '{branch}' not in allowed branches {allowed_branches}", file=sys.stderr)
        return 2

    state = load_deploy_state(state_path)
    approved_paths = load_approved_paths(args.approve_initial_baseline, args.approve_file)

    plan = build_plan(repo, config, dest_root, state, approved_paths, mode, backup_root)

    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"deploy-preview-{config.project}-{plan.timestamp}.json"
    preview_path.write_text(json.dumps(plan.to_manifest_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    summary = plan.summary()
    print(f"mode={mode} project={config.project} head={plan.source_head[:12]} branch={plan.source_branch}")
    print(f"summary: {summary}")
    print(f"runtime_only_files: {len(plan.runtime_only_files)}")
    print(f"files that would be backed up: {len(plan.backup_preview())} "
          f"({plan.estimated_backup_bytes} bytes) -> {backup_root / config.project / plan.timestamp}")
    print(f"preview manifest: {preview_path}")

    if plan.blocked():
        print(f"BLOCKED files: {len(plan.blocked())}", file=sys.stderr)
        for record in plan.blocked():
            print(f"  {record.rel_path}: {record.block_reason}", file=sys.stderr)

    if mode == "dry-run":
        print("DRY-RUN complete. No changes written. Re-run with --apply --confirm "
              f"{CONFIRM_TOKEN} to write for real (will still refuse if any file is blocked).")
        return 0 if not plan.blocked() else 3

    # mode == "apply"
    if plan.blocked():
        print("REFUSED: apply aborted, blocked files present (see above). Nothing written.", file=sys.stderr)
        return 2

    result = apply_plan(repo, plan, dest_root, backup_root)
    save_deploy_state(state_path, result["new_state"])
    print(f"APPLY complete: {len(result['written'])} file(s) written, "
          f"{len(result['backed_up'])} backed up to {result['backup_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
