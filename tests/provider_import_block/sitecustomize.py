"""Hermetic-CI provider-import block (opt-in by putting this directory on ``PYTHONPATH``).

Python imports ``sitecustomize`` at interpreter start-up, so prepending this directory to
``PYTHONPATH`` makes every interpreter in the job -- the pytest process *and* every Python
subprocess a test spawns (import-containment checks, worker fixtures) -- refuse the optional
provider packages from ``requirements-providers.txt``. CI does not install them anyway; the block
proves the hermetic tier needs them even on a machine where they happen to be installed.

A blocked import raises ``ModuleNotFoundError`` (an ``ImportError``), exactly what an absent
package raises, so code that already degrades on a missing provider behaves identically. The
message carries ``PROVIDER_RUNTIME_BLOCKED:<name>`` so a hidden provider import is attributable.

Keep ``BLOCKED_PROVIDER_MODULES`` equal to ``tests/_test_tiers.PROVIDER_RUNTIME_MODULES``
(enforced by ``tests/test_ci_dependency_tiers.py``).
"""

from __future__ import annotations

import os
import sys

BLOCKED_PROVIDER_MODULES = ("vnstock", "vnai")
ACTIVE_ENV = "STOCKLOOKUP_PROVIDER_IMPORT_BLOCK"


class ProviderImportBlocker:
    """``sys.meta_path`` finder that refuses the provider packages and all their submodules."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] in BLOCKED_PROVIDER_MODULES:
            raise ModuleNotFoundError(
                f"PROVIDER_RUNTIME_BLOCKED:{fullname} (hermetic CI tier; optional provider "
                "packages live in requirements-providers.txt)",
                name=fullname,
            )
        return None


if not any(isinstance(finder, ProviderImportBlocker) for finder in sys.meta_path):
    sys.meta_path.insert(0, ProviderImportBlocker())
# Visible to the process and inherited by children, so a test can assert the block is active.
os.environ[ACTIVE_ENV] = "ACTIVE"
