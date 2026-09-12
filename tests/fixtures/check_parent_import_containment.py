"""Run in a FRESH, isolated subprocess (see tests/test_vnstock_worker_import_containment.py) --
never inside the main pytest process, where other test files in the same session may
legitimately import vn_stock_pipeline/vnstock directly and would make an in-process sys.modules
check meaningless.

Imports the same modules the canonical exact-session parent-side path imports, exercises a real
worker round-trip against the deterministic fake worker (tests/fixtures/fake_vnstock_worker.py --
no real vnstock/vnai/network involved), then asserts this PROCESS's own sys.modules never
acquired vnstock or vnai. Prints ``IMPORT_CONTAINMENT_OK`` and exits 0 on success; prints a
``IMPORT_CONTAINMENT_FAILED:<detail>`` line and exits 1 otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

FAKE_WORKER = Path(__file__).with_name("fake_vnstock_worker.py")


def main() -> int:
    import multi_source_exact_session_resolver  # noqa: F401
    import vnstock_worker_client
    import vnstock_worker_protocol  # noqa: F401

    worker = vnstock_worker_client.VnstockWorkerFetcher(
        worker_script=FAKE_WORKER, request_timeout=10.0, startup_timeout=10.0,
    )
    try:
        outcome = worker.fetch("EXACT_A", "KBS", "2026-09-01", "2026-09-10")
        assert outcome.status == "success"
        worker.diagnostic()
        worker.estimated_minimum_seconds_for(5)
    finally:
        worker.shutdown()

    offenders = sorted(m for m in ("vnstock", "vnai") if m in sys.modules)
    if offenders:
        print(f"IMPORT_CONTAINMENT_FAILED:{','.join(offenders)}")
        return 1
    print("IMPORT_CONTAINMENT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
