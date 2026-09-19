"""No-network cohort and exact-store planning for future foreign-flow enrichment."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from current_foreign_flow_retention import dry_run_plan

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--session", required=True); parser.add_argument("--runtime-root", required=True); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run: parser.error("ONLY_NO_NETWORK_DRY_RUN_SUPPORTED")
    print(json.dumps(dry_run_plan(root=ROOT, runtime_root=args.runtime_root, reference_session=args.session), sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
