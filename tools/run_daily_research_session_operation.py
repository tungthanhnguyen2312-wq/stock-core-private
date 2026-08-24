"""One explicit foreground entry point for a retained completed-session operation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from daily_research_session_operations import run_session_operation


def _head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize one coherent retained completed-session research operation.")
    parser.add_argument("--session", required=True, help="Completed market session YYYY-MM-DD; resolved only through an explicit input registry.")
    parser.add_argument("--input-registry", type=Path, help="Explicit governed session-input registry; never a latest-file search.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "operations-review" / "daily-research-session-operations-v1")
    parser.add_argument("--generation-context", default="RETAINED_FIXED_TIME_REPLAY")
    parser.add_argument("--portfolio-input", type=Path, help="Explicit portfolio JSON; omitted means no portfolio branch.")
    parser.add_argument("--macro-artifact", type=Path, help="Explicit macro artifact; never inferred from a latest path.")
    args = parser.parse_args()
    consumer_root = ROOT.parent / "ai-core-private"
    portfolio = json.loads(args.portfolio_input.read_text(encoding="utf-8")) if args.portfolio_input else None
    macro = json.loads(args.macro_artifact.read_text(encoding="utf-8")) if args.macro_artifact else None
    operation, output_dir = run_session_operation(ROOT, session=args.session, producer_head=_head(ROOT), consumer_head=_head(consumer_root), output_root=args.output_root, registry_path=args.input_registry, generation_context=args.generation_context, portfolio=portfolio, macro=macro)
    print(operation["manifest"]["operation_identity"])
    print(output_dir)


if __name__ == "__main__":
    main()
