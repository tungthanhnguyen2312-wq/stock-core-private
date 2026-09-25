"""Run in a FRESH subprocess (tests/test_provider_runtime_isolation.py): the canonical Daily parent
-- a process that holds DNSE credentials -- must never import the provider adapter or the provider
packages on the AVAILABLE-runtime path either, i.e. while the real ensure_exact_session_snapshot
runs the real resolver through a live (fake) provider worker to a qualified snapshot.

An import trap refuses and records any attempt, so even an import that would have succeeded (the
adapter ``vn_stock_pipeline`` imports vnstock only lazily) is caught. Uses only the deterministic
fake worker under the explicit test-only ALLOW policy; no vnstock/vnai/network, synthetic
credentials only. Prints ``AVAILABLE_DAILY_PARENT_IMPORT_CONTAINMENT_OK`` and exits 0 on success.
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (_REPO_ROOT, _REPO_ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

FORBIDDEN = ("vn_stock_pipeline", "vnstock", "vnai")
ATTEMPTS: list[str] = []


class _ParentImportTrap:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] in FORBIDDEN:
            ATTEMPTS.append(f"{fullname}\n{''.join(traceback.format_stack(limit=8))}")
            raise ModuleNotFoundError(f"AVAILABLE_PARENT_IMPORT_TRAP:{fullname}", name=fullname)
        return None


def main() -> int:
    sys.meta_path.insert(0, _ParentImportTrap())

    import daily_session_level2_package as level2
    import dnse_access
    import dnse_secrets_env
    import mva_exact_session_snapshot as snapshotter
    import provider_runtime_state as runtime_contract
    import vnstock_worker_client
    from _provider_runtime_fixtures import available_handle, fake_fetcher
    from test_provider_runtime_isolation import TARGET, _dnse_obs, _dnse_snapshot

    dnse_records = {"EXACT_A": ("EXACT_SESSION_RETAINED", [_dnse_obs(TARGET)])}
    snapshot = _dnse_snapshot(dnse_records)
    snapshotter.canonical_candidates = lambda _root: list(dnse_records)
    snapshotter.materialize_snapshot = lambda **_kw: json.loads(json.dumps(snapshot))
    dnse_secrets_env.ensure_credentials_loaded = lambda *a, **k: {"configured": True}
    dnse_access.credentials_for_request = lambda *a, **k: ("synthetic", "synthetic")

    fetcher = fake_fetcher()
    fetcher.start()
    handle = available_handle(fetcher)
    vnstock_worker_client.open_provider_runtime = lambda **_kw: handle

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        path = level2.ensure_exact_session_snapshot(root, TARGET, root / "runtime")
        written = json.loads(path.read_text(encoding="utf-8"))

    if written.get("provider_runtime_state") != runtime_contract.AVAILABLE:
        print(f"AVAILABLE_DAILY_PARENT_IMPORT_CONTAINMENT_FAILED:runtime={written.get('provider_runtime_state')}")
        return 1
    if (written.get("dnse_quality_license") or {}).get("qualifies_for_ordinary_daily") is not True:
        print(f"AVAILABLE_DAILY_PARENT_IMPORT_CONTAINMENT_FAILED:license={written.get('dnse_quality_license')}")
        return 1
    loaded = sorted(m for m in sys.modules if m.partition(".")[0] in FORBIDDEN)
    if ATTEMPTS or loaded:
        print(f"AVAILABLE_DAILY_PARENT_IMPORT_CONTAINMENT_FAILED:loaded={loaded}")
        for attempt in ATTEMPTS:
            print(attempt)
        return 1
    print("AVAILABLE_DAILY_PARENT_IMPORT_CONTAINMENT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
