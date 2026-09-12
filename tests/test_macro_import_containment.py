"""After MACRO_NETWORK_GOVERNANCE_AND_VNSTOCK_DECOUPLING_V1, the macro subprocess/module path
(``macro_sync.py`` and its VCB/SJC adapters) must never import ``vnstock``/``vnai`` -- that
dependency is fully removed for macro acquisition (VCB/SJC now use first-party adapters
directly). This is distinct from -- and must not affect -- W3's own parent-process containment
guarantee for exact-session KBS/VCI resolution (tests/test_vnstock_worker_import_containment.py),
which is untouched by this milestone.

This check MUST run in a freshly spawned, isolated Python subprocess
(tests/fixtures/check_macro_import_containment.py), not in-process in the main pytest run: other
test files collected in the same pytest session (e.g. test_vn_stock_pipeline.py) legitimately
import vnstock directly, which would permanently pollute sys.modules for the rest of that
process and make an in-process assertion order-dependent rather than a real guarantee.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CHECK_SCRIPT = Path(__file__).with_name("fixtures") / "check_macro_import_containment.py"


def test_macro_subprocess_path_never_imports_vnstock_or_vnai():
    result = subprocess.run(
        [sys.executable, "-u", str(_CHECK_SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "MACRO_IMPORT_CONTAINMENT_OK" in result.stdout, result.stdout
