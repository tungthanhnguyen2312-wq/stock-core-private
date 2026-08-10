"""Offline ingestion: sanitized DNSE probe evidence -> the retained foreign-flow store.

No network I/O, no secrets.env, no credential material anywhere in this tool -- it
only reads a JSON evidence file already produced by
`tools/dnse_market_data_probe.py --probe foreign-value --live` (via the secret-blind
launcher) and writes normalized, value-only observations into
`dnse_foreign_flow_store.py`'s retained store under the runtime root.

For each ticker/session in the evidence, the *first* record of that call's
`foreigners` list is used -- the probe queries with order=DESC, so the first record
is the most recent (closest to session close) cumulative snapshot for that day, not
an arbitrary one. See build_foreign_value_call_plan()'s docstring in the probe for
why DESC (not ASC, which was tried first and returned zero rows for this endpoint).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_foreign_flow_capability import DnseForeignFlowError, normalize_record  # noqa: E402
from dnse_foreign_flow_store import write_observations  # noqa: E402
from runtime_paths import runtime_root as resolve_runtime_root  # noqa: E402

DEFAULT_EVIDENCE = (
    ROOT.parent / "operations-review" / "dnse-foreign-value-integration-20260810" / "probe_results.json"
)


def extract_normalized_observations(evidence: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Every ok, non-empty `foreign_trading` result in the evidence -> normalized
    records, grouped by ticker. Skips (does not raise on) a failed or empty call --
    a session that DNSE genuinely returned nothing for is absent, not fabricated."""
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for result in evidence.get("results", []):
        if result.get("capability") != "foreign_trading" or not result.get("ok"):
            continue
        body = result.get("body_redacted") or {}
        records = body.get("foreigners")
        if not records or not isinstance(records, list):
            continue
        raw = records[0]  # DESC order -> most recent (session-close) cumulative snapshot
        try:
            normalized = normalize_record(raw, source_endpoint=result.get("endpoint", ""),
                                           query_window=result.get("query_sent"))
        except DnseForeignFlowError:
            continue  # malformed source record -- skip it, never fabricate a substitute
        by_ticker.setdefault(normalized["ticker"], []).append(normalized)
    return by_ticker


def ingest(evidence_path: Path, runtime_root: Path, *, dry_run: bool) -> dict[str, Any]:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    by_ticker = extract_normalized_observations(evidence)
    report: dict[str, Any] = {"evidence_path": str(evidence_path), "runtime_root": str(runtime_root),
                               "dry_run": dry_run, "tickers": {}}
    for ticker, observations in sorted(by_ticker.items()):
        sessions = sorted(o["session_date"] for o in observations)
        report["tickers"][ticker] = {"session_count": len(observations), "sessions": sessions}
        if not dry_run:
            write_observations(runtime_root, ticker, observations)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE),
                         help="Path to a probe_results.json produced by --probe foreign-value.")
    parser.add_argument("--runtime-root", default=None,
                         help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Report what would be ingested without writing the store.")
    args = parser.parse_args(argv)

    evidence_path = Path(args.evidence)
    if not evidence_path.exists():
        print(json.dumps({"status": "evidence_not_found", "path": str(evidence_path)}))
        return 2

    root = resolve_runtime_root(args.runtime_root)
    report = ingest(evidence_path, root, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
