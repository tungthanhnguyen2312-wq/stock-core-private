"""Run in a FRESH, isolated subprocess (see tests/test_macro_import_containment.py) -- never
inside the main pytest process, where other test files in the same session may legitimately
import vnstock/vnai directly and would make an in-process sys.modules check meaningless (see
tests/fixtures/check_parent_import_containment.py for the identical W3 rationale).

Imports macro_sync.py (the canonical macro subprocess entry point) and the two new first-party
VCB/SJC adapter modules, exercises their pure parsing/module-level surface without any real
network call, then asserts this PROCESS's own sys.modules never acquired vnstock or vnai.
Prints ``MACRO_IMPORT_CONTAINMENT_OK`` and exits 0 on success; prints a
``MACRO_IMPORT_CONTAINMENT_FAILED:<detail>`` line and exits 1 otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    import macro_sync  # noqa: F401
    import macro_sjc_adapter
    import macro_vcb_adapter

    # Exercise the fetchers' full round-trip (network layer mocked) so any lazy/deferred
    # import inside fetch_vcb_today()/fetch_sjc_today() actually executes in this process,
    # not merely a static top-of-file import.
    from unittest import mock

    ok_vcb = macro_vcb_adapter.MacroFetchResult([("2026-09-10", 26690.0)], "OK", None)
    with mock.patch.object(macro_vcb_adapter, "fetch_vcb_usd_sell_rate", return_value=ok_vcb):
        assert macro_sync.fetch_vcb_today() == [("2026-09-10", 26690.0)]

    ok_sjc = macro_sjc_adapter.MacroFetchResult([("2026-09-10", 82000000.0)], "OK", None)
    with mock.patch.object(macro_sjc_adapter, "fetch_sjc_gold_sell_price", return_value=ok_sjc):
        assert macro_sync.fetch_sjc_today() == [("2026-09-10", 82000000.0)]

    offenders = sorted(m for m in ("vnstock", "vnai") if m in sys.modules)
    if offenders:
        print(f"MACRO_IMPORT_CONTAINMENT_FAILED:{','.join(offenders)}")
        return 1
    print("MACRO_IMPORT_CONTAINMENT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
