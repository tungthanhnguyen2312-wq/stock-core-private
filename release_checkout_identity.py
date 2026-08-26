"""Canonical Dashboard checkout identity for live publication.

One web checkout is allowed to receive a live release:

    C:\\Projects\\StockLookup\\market-dashboard

on branch ``main``, origin ``tungthanhnguyen2312-wq/market-dashboard``.
A successful ``git push`` is ``GITHUB_SOURCE_UPDATED``. ``PUBLISHED`` is a later
state and is never implied by push alone.

Tests may set ``STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE`` to the exact
resolved fixture web path. That bypasses the canonical-path/origin/branch pin
for that path only. Legacy workspace paths are still refused.
"""
from __future__ import annotations

import os
from pathlib import Path

CANONICAL_WEB_ROOT = Path(r"C:\Projects\StockLookup\market-dashboard")
CANONICAL_BACKEND_ROOT = Path(r"C:\Projects\StockLookup\dashboard-runtime")
CANONICAL_PRODUCER_ROOT = Path(r"C:\Projects\StockLookup\stock-core-private")
CANONICAL_PRODUCER_PUBLISH_DASHBOARD = CANONICAL_PRODUCER_ROOT / "publish_dashboard.py"
CANONICAL_PRODUCER_PUBLISH_RELEASE = CANONICAL_PRODUCER_ROOT / "tools" / "publish_release.py"
CANONICAL_PRODUCER_ORCHESTRATOR = CANONICAL_PRODUCER_ROOT / "tools" / "release_orchestrator.py"
CANONICAL_BRANCH = "main"
CANONICAL_ORIGIN_REPO = "tungthanhnguyen2312-wq/market-dashboard"
CANONICAL_ORIGIN_MARKERS = (
    "github.com/tungthanhnguyen2312-wq/market-dashboard",
    "github.com:tungthanhnguyen2312-wq/market-dashboard",
)
TEST_FIXTURE_ENV = "STOCK_LOOKUP_RELEASE_IDENTITY_TEST_FIXTURE"

GITHUB_SOURCE_UPDATED = "GITHUB_SOURCE_UPDATED"
PUBLISHED = "PUBLISHED"

LEGACY_WEB_PATH_MARKERS = (
    "worktrees\\market-dashboard-main",
    "worktrees/market-dashboard-main",
    "publish\\market-dashboard-main",
    "publish/market-dashboard-main",
    "worktrees\\market-dashboard-phase5",
    "worktrees/market-dashboard-phase5",
    "worktrees\\market-dashboard-repair",
    "worktrees/market-dashboard-repair",
    "worktrees\\market-dashboard-atomic-review",
    "worktrees/market-dashboard-atomic-review",
    "worktrees\\market-dashboard-v2-integration",
    "worktrees/market-dashboard-v2-integration",
    "worktrees\\current-decision-cockpit-dashboard-v2",
    "worktrees/current-decision-cockpit-dashboard-v2",
    "worktrees\\market-dashboard-ci",
    "worktrees/market-dashboard-ci",
    "worktrees\\dashboard-phase2c",
    "worktrees/dashboard-phase2c",
    "tmp\\pow-standard-runtime",
    "tmp/pow-standard-runtime",
)


class ReleaseIdentityError(ValueError):
    """A live-release checkout identity gate refused to pass."""


def _norm(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def is_test_fixture(web_dir: Path) -> bool:
    raw = os.environ.get(TEST_FIXTURE_ENV, "").strip()
    if not raw:
        return False
    return _norm(Path(raw)) == _norm(web_dir)


def origin_is_canonical(origin_url: str) -> bool:
    normalized = origin_url.strip().lower().replace("\\", "/")
    return any(marker in normalized for marker in CANONICAL_ORIGIN_MARKERS)


def legacy_web_marker(web_dir: Path) -> str | None:
    text = str(web_dir.resolve())
    lowered = text.replace("/", "\\").lower()
    for marker in LEGACY_WEB_PATH_MARKERS:
        if marker.lower() in lowered:
            return marker
    runtime = _norm(CANONICAL_BACKEND_ROOT)
    if _norm(web_dir) == runtime:
        return str(CANONICAL_BACKEND_ROOT)
    return None


def assert_producer_publisher_file(path: Path, *, role: str) -> None:
    expected = {
        "publish_dashboard": CANONICAL_PRODUCER_PUBLISH_DASHBOARD,
        "publish_release": CANONICAL_PRODUCER_PUBLISH_RELEASE,
        "release_orchestrator": CANONICAL_PRODUCER_ORCHESTRATOR,
    }[role]
    if _norm(path) != _norm(expected):
        raise ReleaseIdentityError(
            f"REFUSED: {role} authority is {expected}; got {path}. "
            "Dashboard checkouts are TARGETS, not publisher authority."
        )


def assert_web_checkout_identity(
    web_dir: Path,
    *,
    backend_dir: Path | None = None,
    origin_url: str | None = None,
    branch: str | None = None,
    head: str | None = None,
    origin_main: str | None = None,
    live: bool = False,
    git_toplevel: Path | None = None,
) -> None:
    """Refuse non-canonical Dashboard checkouts.

    Canonical path/origin/branch are required unless this exact web_dir is a
    declared test fixture. Legacy workspace paths are always refused.
    """
    web = web_dir.resolve()
    marker = legacy_web_marker(web)
    if marker:
        raise ReleaseIdentityError(
            f"REFUSED: legacy Dashboard checkout {web} (matched {marker}). "
            f"Live web Git toplevel must be {CANONICAL_WEB_ROOT}."
        )

    if backend_dir is not None and backend_dir.resolve() == web:
        raise ReleaseIdentityError(
            f"REFUSED: backend == web ({web}). dashboard-runtime is DATA/RUNTIME only."
        )

    fixture = is_test_fixture(web)
    if not fixture and _norm(web) != _norm(CANONICAL_WEB_ROOT):
        raise ReleaseIdentityError(
            f"REFUSED: web Git toplevel must be {CANONICAL_WEB_ROOT}; got {web}."
        )

    if git_toplevel is not None and _norm(git_toplevel) != _norm(web):
        raise ReleaseIdentityError(
            f"REFUSED: git toplevel {git_toplevel} is not the web checkout {web}. "
            "validation, git add, commit, and push must use the same checkout."
        )

    if fixture:
        return

    if branch is not None and branch != CANONICAL_BRANCH:
        raise ReleaseIdentityError(
            f"REFUSED: web branch must be {CANONICAL_BRANCH}; got {branch!r}."
        )
    if origin_url is not None and not origin_is_canonical(origin_url):
        raise ReleaseIdentityError(
            f"REFUSED: origin must be {CANONICAL_ORIGIN_REPO}; got {origin_url!r}."
        )
    if live and head and origin_main and head != origin_main:
        raise ReleaseIdentityError(
            f"REFUSED: HEAD ({head}) != origin/main ({origin_main}) before release mutation."
        )


def publication_state_after_push(*, ci_pass: bool = False, pages_pass: bool = False,
                                 public_verify_pass: bool = False,
                                 local_validation_pass: bool = False) -> str:
    """A git push is never PUBLISHED by itself."""
    if local_validation_pass and ci_pass and pages_pass and public_verify_pass:
        return PUBLISHED
    return GITHUB_SOURCE_UPDATED
