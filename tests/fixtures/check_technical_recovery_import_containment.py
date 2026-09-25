"""Run in a FRESH subprocess (tests/test_provider_runtime_isolation.py): the technical-history
recovery runner -- a process that holds DNSE credentials -- must never import the provider
adapter or the provider packages, even while it routes a KBS request through the isolated worker.

Uses only the deterministic fake worker (tests/fixtures/fake_vnstock_worker.py) under an explicit
test-only ALLOW policy; no vnstock/vnai/network anywhere. Prints
``TECHNICAL_RECOVERY_IMPORT_CONTAINMENT_OK`` and exits 0 on success.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (_REPO_ROOT, _REPO_ROOT / "tools", _REPO_ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))


def main() -> int:
    import run_market_wide_current_technical_coverage_scaleout as runner
    import vnstock_worker_client
    from _provider_runtime_fixtures import FAKE_WORKER, TEST_ALLOW_POLICY

    real_open = vnstock_worker_client.open_provider_runtime

    def fake_open(**kwargs):
        return real_open(
            policy=TEST_ALLOW_POLICY, environ={"STOCKLOOKUP_PROVIDER_PYTHON": sys.executable},
            core_executable="/nonexistent/core/python", worker_script=FAKE_WORKER, **kwargs,
        )

    runner.worker_client.open_provider_runtime = fake_open
    fetch = runner._ProviderHistoryFetch(session="2026-09-10")
    try:
        outcome = fetch("EXACT_HPG", "KBS", "2026-07-01", "2026-09-10")
        assert outcome.status == "success", outcome.status
    finally:
        fetch.close()

    offenders = sorted(m for m in ("vnstock", "vnai", "vn_stock_pipeline") if m in sys.modules)
    if offenders:
        print(f"TECHNICAL_RECOVERY_IMPORT_CONTAINMENT_FAILED:{','.join(offenders)}")
        return 1
    print("TECHNICAL_RECOVERY_IMPORT_CONTAINMENT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
