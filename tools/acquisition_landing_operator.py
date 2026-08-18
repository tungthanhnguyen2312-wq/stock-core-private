#!/usr/bin/env python
"""Thin foreground CLI entrypoint for the isolated bulk acquisition framework.

Runs exactly one bounded, resumable acquisition batch and exits - no
daemon, scheduler, timer, or background loop. The operator is responsible
for starting each run. Currently wires up the one supported domain:
official financial filings, replayed from Stock Lookup's existing governed
evidence corpus (see financial_filings_replay_adapter.py).

Example:
    python tools/acquisition_landing_operator.py replay-financial-filings \
        --run-id demo-run-1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import acquisition_landing_checkpoint as checkpoint  # noqa: E402
import acquisition_landing_isolation as isolation  # noqa: E402
import financial_filings_replay_adapter as replay_adapter  # noqa: E402
from acquisition_landing_contract import new_run_id  # noqa: E402

DEFAULT_WORKSPACE_ROOT = r"C:\Projects\StockLookup"


def _default_landing_root(workspace_root: str) -> Path:
    return Path(workspace_root) / "data-landing" / replay_adapter.DOMAIN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    replay = subparsers.add_parser(
        "replay-financial-filings",
        help="Replay the existing governed HPG/VNM/VCB (or other) financial-filing corpus into the landing contract.",
    )
    replay.add_argument("--workspace-root", default=DEFAULT_WORKSPACE_ROOT, help="Workspace root (default: %(default)s)")
    replay.add_argument("--landing-root", default=None, help="Landing root (default: <workspace-root>/data-landing/official-financial-filings-v1)")
    replay.add_argument(
        "--governed-evidence-root",
        default=None,
        help="Source governed-evidence root to replay from (default: <workspace-root>/stock-core-private/operations-review/governed-official-evidence-v1)",
    )
    replay.add_argument("--tickers", default=",".join(replay_adapter.DEFAULT_TICKERS), help="Comma-separated ticker allowlist (default: %(default)s)")
    replay.add_argument("--run-id", default=None, help="Run id; auto-generated when omitted. Reuse an existing run-id to resume it.")
    replay.add_argument("--no-resume", action="store_true", help="Ignore any existing checkpoint for this run-id and start fresh.")

    return parser


def run_replay_financial_filings(args: argparse.Namespace) -> checkpoint.RunReport:
    workspace_root = Path(args.workspace_root)
    landing_root = Path(args.landing_root) if args.landing_root else _default_landing_root(str(workspace_root))
    governed_evidence_root = (
        Path(args.governed_evidence_root)
        if args.governed_evidence_root
        else replay_adapter.default_governed_evidence_root(workspace_root)
    )
    tickers = tuple(t.strip().upper() for t in args.tickers.split(",") if t.strip())
    run_id = args.run_id or new_run_id("official-financial-filings-v1")

    protected_roots = isolation.default_protected_roots(workspace_root)
    items = replay_adapter.iter_replay_items(governed_evidence_root, tickers)

    report = checkpoint.process_batch(
        landing_root,
        items,
        run_id=run_id,
        domain=replay_adapter.DOMAIN,
        allowed_root=landing_root,
        protected_roots=protected_roots,
        extra_protected_paths=(governed_evidence_root,),
        observed_at_fn=replay_adapter.utc_now_iso,
        resume=not args.no_resume,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "replay-financial-filings":
        report = run_replay_financial_filings(args)
    else:  # pragma: no cover - argparse `required=True` already prevents this
        parser.error(f"unknown mode {args.mode!r}")
        return 2

    print(f"run_id={report.run_id} domain={report.domain} status={report.status}")
    print(
        f"attempted={report.attempted} succeeded={report.succeeded} skipped={report.skipped} "
        f"quarantined={report.quarantined} failed_retryable={report.failed_retryable} "
        f"failed_permanent={report.failed_permanent}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
