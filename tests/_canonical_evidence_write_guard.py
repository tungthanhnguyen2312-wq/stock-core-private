"""Test-session guard: no test may write into canonical retained evidence.

RETAINED_EVIDENCE_INCIDENT_20260925: tests that rebuilt Level-2 artifacts into the repository's
own ``operations-review`` rewrote the retained 2026-08-25 and 2026-09-04 Integrated Decision
folders -- directly when the suite ran in the Producer checkout, and through a junction when a
worktree's ``operations-review`` was linked to it. Retained-evidence tests must work on scratch
copies (``tests/_retained_scratch.py``); this guard makes any other write fail loudly.

A ``sys.addaudithook`` hook, installed once per test process by ``tests/conftest.py``, refuses
every file-system mutation event (write/append/create/truncate opens, rename/replace, remove,
mkdir/rmdir, utime/chmod/truncate, copy destinations, link targets, rmtree) whose *resolved*
target lies under a protected root. Resolution follows junctions and symlinks, so write-through
from a linked worktree is refused as well. Reads are never affected.

Protected roots: ``operations-review`` and ``data`` of this checkout, of the Producer main
checkout when this checkout is a git worktree, and of ``STOCKLOOKUP_RETAINED_EVIDENCE_ROOT``
when set. A refusal raises ``CanonicalEvidenceWriteRefused`` (a ``PermissionError``) at the
write site and is also recorded, so a caller that swallows the exception (the enrichment
builder deliberately catches broad exceptions per component) still fails the test at teardown.
``tests/conftest.py`` installs the hook at import and re-exports the fixture and session hook
below; the module is also usable directly as a plugin (``-p _canonical_evidence_write_guard``).

Scope: in-process only. A test that spawns a separate Python process is not covered by this
hook; such tests must pass scratch roots explicitly.
"""
from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RETAINED_EVIDENCE_ROOT_ENV = "STOCKLOOKUP_RETAINED_EVIDENCE_ROOT"
PROTECTED_SUBDIRECTORIES = ("operations-review", "data")
REFUSAL_CODE = "CANONICAL_EVIDENCE_WRITE_REFUSED"

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
# event -> indexes of the arguments that are mutation targets
_TARGET_ARGS = {
    "os.rename": (0, 1),
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.mkdir": (0,),
    "os.truncate": (0,),
    "os.utime": (0,),
    "os.chmod": (0,),
    "os.link": (1,),
    "os.symlink": (1,),
    "shutil.copyfile": (1,),
    "shutil.copytree": (1,),
    "shutil.move": (0, 1),
    "shutil.rmtree": (0,),
    "_winapi.CopyFile2": (1,),
    "_winapi.CreateJunction": (1,),
}


class CanonicalEvidenceWriteRefused(PermissionError):
    pass


def producer_main_checkout(repo_root: Path) -> Path | None:
    """The main checkout of the repository when ``repo_root`` is a linked git worktree."""
    dot_git = repo_root / ".git"
    if not dot_git.is_file():
        return None
    text = dot_git.read_text(encoding="utf-8", errors="replace").strip()
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.partition(":")[2].strip())
    if not gitdir.is_absolute():
        gitdir = (repo_root / gitdir).resolve()
    commondir_file = gitdir / "commondir"
    if not commondir_file.is_file():
        return None
    common = Path(commondir_file.read_text(encoding="utf-8").strip())
    if not common.is_absolute():
        common = (gitdir / common).resolve()
    return common.parent


def default_protected_roots(repo_root: Path = REPO_ROOT) -> list[Path]:
    bases = [repo_root]
    main = producer_main_checkout(repo_root)
    if main is not None:
        bases.append(main)
    configured = os.getenv(RETAINED_EVIDENCE_ROOT_ENV, "").strip()
    if configured:
        bases.append(Path(configured))
    return [base / name for base in bases for name in PROTECTED_SUBDIRECTORIES]


def _key(path: object) -> str | None:
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, (str, os.PathLike)):
        return None  # file descriptors, None
    try:
        return os.path.normcase(os.path.realpath(os.fspath(path)))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(os.fspath(path)))


@dataclass
class _GuardState:
    protected: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    installed: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


_STATE = _GuardState()


def _protected_hit(target: object) -> str | None:
    key = _key(target)
    if key is None:
        return None
    for root in _STATE.protected:
        if key == root or key.startswith(root + os.sep):
            return key
    return None


def _refuse(event: str, target_key: str) -> None:
    message = f"{REFUSAL_CODE}:{event}:{target_key}"
    with _STATE.lock:
        _STATE.violations.append(message)
    raise CanonicalEvidenceWriteRefused(message)


def _hook(event: str, args: tuple) -> None:
    if event == "open":
        if len(args) < 3:
            return
        mode, flags = args[1], args[2]
        writes = (isinstance(mode, str) and any(ch in mode for ch in "wax+")) or (
            isinstance(flags, int) and flags & _WRITE_FLAGS
        )
        if not writes:
            return
        hit = _protected_hit(args[0])
        if hit is not None:
            _refuse(event, hit)
        return
    indexes = _TARGET_ARGS.get(event)
    if indexes is None:
        return
    for index in indexes:
        if index < len(args):
            hit = _protected_hit(args[index])
            if hit is not None:
                _refuse(event, hit)


def install(protected_roots: list[Path] | None = None) -> None:
    """Install the process-wide hook once (audit hooks cannot be removed)."""
    roots = protected_roots if protected_roots is not None else default_protected_roots()
    keys = sorted({k for k in (_key(root) for root in roots) if k is not None})
    with _STATE.lock:
        for key in keys:
            if key not in _STATE.protected:
                _STATE.protected.append(key)
        if _STATE.installed:
            return
        _STATE.installed = True
    sys.addaudithook(_hook)


def is_installed() -> bool:
    return _STATE.installed


def protected_roots() -> list[str]:
    return list(_STATE.protected)


def is_protected(path: Path) -> bool:
    return _protected_hit(path) is not None


def protect_temporarily(root: Path):
    """Context manager for the guard's own tests: add a (scratch) protected root."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        key = _key(root)
        with _STATE.lock:
            added = key not in _STATE.protected
            if added:
                _STATE.protected.append(key)
        try:
            yield key
        finally:
            if added:
                with _STATE.lock:
                    _STATE.protected.remove(key)

    return _cm()


def drain_violations() -> list[str]:
    with _STATE.lock:
        drained, _STATE.violations[:] = list(_STATE.violations), []
    return drained


# ---------------------------------------------------------------------------------------------
# pytest wiring
# ---------------------------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    install()


@pytest.fixture(autouse=True)
def canonical_evidence_write_guard():
    drain_violations()
    yield
    violations = drain_violations()
    if violations:
        pytest.fail(
            "Test wrote (or tried to write) into canonical retained evidence; use scratch copies "
            "(tests/_retained_scratch.py):\n" + "\n".join(violations),
            pytrace=False,
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    # A refusal outside any test (collection, module import) is still a failure.
    leftover = drain_violations()
    if leftover:
        print("\n" + "\n".join(leftover))
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
