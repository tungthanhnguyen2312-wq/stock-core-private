"""One shared checkout-cleanliness contract for Canonical Daily and Owner Daily.

Before this module existed, the owner-facing repository preflight
(``tools/run_owner_daily.py::preflight_repository``) and the Canonical producer
release qualification (``daily_execution_environment.py::producer_release_
qualification``) ran two different ``git status`` invocations and could reach
opposite conclusions about the very same checkout:

    owner preflight:  git status --porcelain --untracked-files=no  (ignores ALL untracked)
    Canonical:         git status --porcelain                       (any untracked = dirty)

A checkout carrying only governed runtime/evidence files -- e.g. ``data/dnse-
foreign-flow/``, written directly inside the producer checkout by
``dnse_foreign_flow_store.py`` whenever no separate runtime root is configured --
therefore passed step 1 and then failed step 2 with ``RELEASE_CHECKOUT_DIRTY``,
even though no source, config, or tracked file had changed.

This module is the one place that decides what "clean" means. Both call sites
use it instead of running their own ``git status``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

# The bounded set of governed runtime/evidence store roots that may exist
# untracked inside a producer checkout without blocking release qualification.
# Each entry mirrors the `STORE_RELATIVE` constant a store module documents as
# "generated runtime data, never the source repo" (dnse_foreign_flow_store.py,
# market_raw_lake.py, raw_financial_store.py, canonical_fact_store.py,
# dnse_market_risk_evidence_store.py). tests/test_checkout_cleanliness_contract.py
# asserts this list stays in sync with those constants so it cannot drift silently.
APPROVED_RUNTIME_EVIDENCE_PREFIXES: tuple[str, ...] = (
    "data/canonical-financial-facts/",
    "data/dnse-foreign-flow/",
    "data/dnse-market-risk-evidence/",
    "data/market-wide-financials/",
    "data/market_raw_lake/",
)

TRACKED_DIRTY = "TRACKED_DIRTY"
UNSAFE_UNTRACKED = "UNSAFE_UNTRACKED"
CLEAN = "PASS"
GIT_UNAVAILABLE = "GIT_STATUS_UNAVAILABLE"


@dataclass(frozen=True)
class CheckoutCleanliness:
    """Structured, deterministic classification of one checkout's working tree.

    ``qualified`` is the single fail-closed verdict both call sites act on. The
    path lists exist so an owner-visible refusal can say WHAT is wrong instead
    of only that something is.
    """
    tracked_dirty_paths: tuple[str, ...]
    approved_untracked_paths: tuple[str, ...]
    unsafe_untracked_paths: tuple[str, ...]
    qualified: bool
    reason_code: str


def _git(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", check=False,
    )
    return result.returncode, result.stdout


def classify_checkout_cleanliness(root: Path) -> CheckoutCleanliness:
    """Classify ``root``'s working tree. Never mutates, deletes, or moves anything.

    - Any tracked change (modified/added/deleted/renamed/staged) blocks.
    - Any untracked file outside ``APPROVED_RUNTIME_EVIDENCE_PREFIXES`` blocks --
      an unreviewed ``foo.py`` or config override sitting in the checkout must
      never silently pass just because it happens to be untracked.
    - Untracked files inside an approved prefix never block: they are evidence
      the checkout is expected to carry, not drift.
    """
    root = Path(root)

    tracked_code, tracked_out = _git(root, "status", "--porcelain", "--untracked-files=no")
    if tracked_code:
        return CheckoutCleanliness((), (), (), False, GIT_UNAVAILABLE)
    tracked_dirty_paths = tuple(sorted(
        line[3:].strip() for line in tracked_out.splitlines() if line.strip()
    ))

    untracked_code, untracked_out = _git(root, "ls-files", "--others", "--exclude-standard")
    if untracked_code:
        return CheckoutCleanliness(tracked_dirty_paths, (), (), False, GIT_UNAVAILABLE)
    untracked_paths = [line.strip() for line in untracked_out.splitlines() if line.strip()]

    approved_untracked_paths = tuple(sorted(
        p for p in untracked_paths if p.startswith(APPROVED_RUNTIME_EVIDENCE_PREFIXES)
    ))
    unsafe_untracked_paths = tuple(sorted(
        p for p in untracked_paths if not p.startswith(APPROVED_RUNTIME_EVIDENCE_PREFIXES)
    ))

    if tracked_dirty_paths:
        reason_code = TRACKED_DIRTY
    elif unsafe_untracked_paths:
        reason_code = UNSAFE_UNTRACKED
    else:
        reason_code = CLEAN

    qualified = not tracked_dirty_paths and not unsafe_untracked_paths
    return CheckoutCleanliness(
        tracked_dirty_paths, approved_untracked_paths, unsafe_untracked_paths, qualified, reason_code,
    )
