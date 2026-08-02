"""Test-session bootstrap for the source/runtime split.

`stock-core-private` holds source only; the generated runtime state it operates on
(`vn_stock.db`, `data_bctc/`, `financial_snapshot.*`, the published frontend files)
lives in the runtime root -- `dashboard-runtime` in this workspace. Production code
resolves that split through `STOCK_LOOKUP_RUNTIME_ROOT` (see `runtime_paths.py`).

Without the variable set, every module-level path constant falls back to its legacy
default (the source directory), so an unconfigured `pytest` run read empty inputs and
reported failures that say nothing about the code under test. `tests/test_export_ai_bundle.py`
already discovered and exported the variable at import time; doing it once here makes
every module see the same root regardless of collection order, while still honouring an
explicitly configured value.
"""

from __future__ import annotations

import os

from _runtime_root import RUNTIME_ROOT, _RUNTIME_ROOT_ENV

if not os.getenv(_RUNTIME_ROOT_ENV, "").strip():
    os.environ[_RUNTIME_ROOT_ENV] = str(RUNTIME_ROOT)
