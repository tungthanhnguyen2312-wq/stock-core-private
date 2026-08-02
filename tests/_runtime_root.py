"""Shared test helper: resolve the mutable dashboard runtime root.

`stock-core-private` is the authoritative *source* repository. Generated runtime
artifacts (`vn_stock.db`, `financial_snapshot.*`, `screen_snapshot.csv`, `data_bctc/`,
`data/`, `assets/`, the published frontend files, ...) live in the *runtime* root, which
is `dashboard-runtime` in this workspace. Production code resolves that split through
`runtime_paths.runtime_root()`; several older test modules instead read
`Path(__file__).parents[1] / <artifact>` and therefore failed with FileNotFoundError as
soon as the runtime artifacts stopped being kept inside the source tree.

This module centralises the same resolution `tests/test_export_ai_bundle.py` already
performed inline, so a test can say `runtime_path("screen_snapshot.csv")` for a generated
artifact while still using its own `ROOT` for source files it asserts about.

Tests that genuinely require a runtime artifact call `require_runtime_path()`, which
raises `unittest.SkipTest` when the artifact is absent. That keeps a workstation with no
generated runtime honest (explicitly skipped, never silently passed) instead of failing
with a path error that hides whether the code under test is correct.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]

_RUNTIME_ROOT_ENV = "STOCK_LOOKUP_RUNTIME_ROOT"


def _resolve_runtime_root() -> Path:
    configured = os.getenv(_RUNTIME_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = (
        SOURCE_ROOT.parent / "dashboard-runtime",
        SOURCE_ROOT.parent / "VNSTOCK",
        SOURCE_ROOT.parent.parent / "VNSTOCK",
    )
    return next((path.resolve() for path in candidates if path.exists()), candidates[0].resolve())


RUNTIME_ROOT = _resolve_runtime_root()


def runtime_path(*parts: str) -> Path:
    """Absolute path to a generated runtime artifact (may not exist)."""
    return RUNTIME_ROOT.joinpath(*parts)


def require_runtime_path(*parts: str) -> Path:
    """Same as `runtime_path`, but skip the test when the artifact has not been generated."""
    path = runtime_path(*parts)
    if not path.exists():
        raise unittest.SkipTest(
            f"runtime artifact {'/'.join(parts)} is not present in the resolved runtime root; "
            "generate it with the supported producer workflow before running this test"
        )
    return path
