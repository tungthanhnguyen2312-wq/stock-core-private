"""Acceptance case O: after this milestone, the canonical parent-side exact-session path must
never import ``vnstock``/``vnai`` into ITS OWN process -- those imports must occur only inside
the bounded worker subprocess.

This check MUST run in a freshly spawned, isolated Python subprocess
(tests/fixtures/check_parent_import_containment.py), not in-process in the main pytest run: other
test files collected in the same pytest session (e.g. test_vn_stock_pipeline.py) legitimately
import ``vn_stock_pipeline``/``vnstock`` directly, which would permanently pollute
``sys.modules`` for the rest of that process and make an in-process assertion pass or fail
depending on unrelated test collection/order rather than on this milestone's actual guarantee.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CHECK_SCRIPT = Path(__file__).with_name("fixtures") / "check_parent_import_containment.py"


def test_parent_process_never_imports_vnstock_or_vnai_for_exact_session_resolution():
    result = subprocess.run(
        [sys.executable, "-u", str(_CHECK_SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "IMPORT_CONTAINMENT_OK" in result.stdout, result.stdout
