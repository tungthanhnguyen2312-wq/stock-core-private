"""Fail-closed production-isolation guard.

Every write this framework performs must pass through assert_write_allowed
first. The check is deliberately redundant (both an allow-list check
against the landing root and a deny-list check against protected roots)
so a bug in either half does not by itself open a hole - see
docs/acquisition_landing_framework.md, "Protected roots".
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from acquisition_landing_contract import ProtectedRootWriteError

# Sibling directories of the workspace root that this framework must never
# write into, at minimum per the milestone's own requirement: dashboard
# runtime, AI runtime, the Consumer source repo, deployment/publish output,
# and the primary (non-worktree) Producer checkout, whose untracked
# governed-evidence directory this framework only ever reads.
DEFAULT_PROTECTED_ROOT_NAMES = (
    "dashboard-runtime",
    "ai-runtime",
    "ai-core-private",
    "publish",
    "stock-core-private",
)

# Matched case-insensitively against a target's filename, regardless of
# directory, as defense in depth for the production database specifically.
PROTECTED_FILENAME_PREFIXES = ("vn_stock.db",)


def resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def default_protected_roots(workspace_root: str | Path) -> tuple[Path, ...]:
    root = resolve(workspace_root)
    return tuple(root / name for name in DEFAULT_PROTECTED_ROOT_NAMES)


def _is_under_or_equal(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def assert_write_allowed(
    target_path: str | Path,
    *,
    allowed_root: str | Path,
    protected_roots: Iterable[str | Path] = (),
    extra_protected_paths: Iterable[str | Path] = (),
) -> Path:
    """Raise ProtectedRootWriteError unless target_path resolves strictly
    under allowed_root and outside every protected root/path. Returns the
    resolved path on success. Performs no filesystem I/O of its own - pure
    path-containment logic, so it is safe to call before the target exists."""
    resolved_target = resolve(target_path)
    resolved_allowed = resolve(allowed_root)

    for protected in (*tuple(protected_roots), *tuple(extra_protected_paths)):
        resolved_protected = resolve(protected)
        if _is_under_or_equal(resolved_target, resolved_protected):
            raise ProtectedRootWriteError(
                f"refusing to write under protected root {resolved_protected}: target={resolved_target}"
            )

    lowered_name = resolved_target.name.lower()
    for prefix in PROTECTED_FILENAME_PREFIXES:
        if lowered_name.startswith(prefix):
            raise ProtectedRootWriteError(
                f"refusing to write a file matching protected production-database name "
                f"({prefix!r}): {resolved_target}"
            )

    if not _is_under_or_equal(resolved_target, resolved_allowed):
        raise ProtectedRootWriteError(
            f"refusing to write outside the allowed landing root {resolved_allowed}: {resolved_target}"
        )

    return resolved_target
