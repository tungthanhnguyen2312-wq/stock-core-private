"""Build the generated statement-taxonomy sidecar for a runtime root.

Read-only over the retained statement payloads; the only thing it writes is
`<runtime-root>/statement_taxonomy_sidecar.json` (atomically). It never touches
`config/ticker_entity_profiles.csv`, any database, any evidence store, or any bundle
artifact -- see `statement_taxonomy_sidecar.py` for the authority contract.

Usage:
  python tools/build_statement_taxonomy_sidecar.py --runtime-root <path> \
      --session-identity 2026-07-28 --generated-at 2026-08-03T00:00:00+00:00
  python tools/build_statement_taxonomy_sidecar.py --runtime-root <path> --check

`--check` rebuilds in memory and compares `records_fingerprint` against the sidecar
already on disk, exiting non-zero on any drift. It never writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json  # noqa: E402
from statement_taxonomy_sidecar import (  # noqa: E402
    SIDECAR_FILENAME,
    build_sidecar,
    load_sidecar,
    sidecar_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--session-identity", default=None,
                        help="Export session identity to bind this sidecar to (reference session date).")
    parser.add_argument("--generated-at", default=None,
                        help="Explicit ISO timestamp; defaults to now (UTC, seconds).")
    parser.add_argument("--producer-contract-version", default=None)
    parser.add_argument("--check", action="store_true",
                        help="Do not write; verify the on-disk sidecar reproduces byte-identical records.")
    args = parser.parse_args()
    # Vietnamese diagnostics must survive a legacy console codepage.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    root = args.runtime_root.expanduser().resolve()
    if not (root / "data_bctc").is_dir():
        print(f"[statement_taxonomy_sidecar] LỖI: không thấy {root / 'data_bctc'}", file=sys.stderr)
        return 2

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = build_sidecar(root, generated_at=generated_at,
                            session_identity=args.session_identity or "",
                            producer_contract_version=args.producer_contract_version)

    reconciliation = payload["reconciliation"]
    if not reconciliation["inputs_fully_accounted"]:
        print("[statement_taxonomy_sidecar] LỖI: input payloads không đối soát hết"
              f" ({reconciliation})", file=sys.stderr)
        return 1

    if args.check:
        existing = load_sidecar(root)
        if existing is None:
            print(f"[statement_taxonomy_sidecar] --check LỖI: không đọc được {SIDECAR_FILENAME}",
                  file=sys.stderr)
            return 1
        if existing.get("records_fingerprint") != payload["records_fingerprint"]:
            print("[statement_taxonomy_sidecar] --check LỆCH: records_fingerprint khác"
                  f" (on-disk={existing.get('records_fingerprint')},"
                  f" rebuilt={payload['records_fingerprint']})", file=sys.stderr)
            return 1
        print(f"[statement_taxonomy_sidecar] --check OK: {SIDECAR_FILENAME} tái tạo byte-ổn định"
              f" ({reconciliation['classified_records']} records).")
        return 0

    atomic_write_json(sidecar_path(root), payload)
    print(f"[statement_taxonomy_sidecar] OK -> {sidecar_path(root)}")
    print(f"   inputs={reconciliation['input_payloads']}"
          f" classified={reconciliation['classified_records']}"
          f" omitted={reconciliation['omitted_records']}")
    print(f"   taxonomy_counts={json.dumps(payload['taxonomy_counts'], ensure_ascii=False)}")
    for row in payload["omitted"]:
        print(f"   [omitted] {row['ticker']}: {row['omission_reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
