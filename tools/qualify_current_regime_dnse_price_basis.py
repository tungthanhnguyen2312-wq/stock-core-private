"""Run the bounded current-regime DNSE price-basis qualification cohort.

Only selected missing daily-OHLC event windows are requested.  Response bodies are retained as
runtime evidence, never printed; credentials are loaded through the repository's secret-safe
loader and are never serialized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dnse_access import credentials_for_request
from dnse_bulk_market_data import fetch_capability_raw
from dnse_current_regime_price_basis import (
    DATASET, promotion_analysis, qualify_event, query_for_window, reconcile, select_cohort,
    snapshot_coverage,
)
from dnse_secrets_env import ensure_credentials_loaded


def _event_rows(path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    try:
        columns = ["record_id", "provider", "ticker", "event_code", "exright_date", "exercise_ratio", "value_per_share", "public_date", "revision_status", "coverage_status"]
        query = "SELECT " + ", ".join(columns) + " FROM corporate_event_records WHERE exright_date IS NOT NULL"
        return [dict(zip(columns, row)) for row in connection.execute(query)]
    finally:
        connection.close()


def _universe(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["symbol"]): row for row in pq.read_table(path).to_pylist()}


def _identity(case: dict[str, Any], query: dict[str, Any]) -> str:
    material = json.dumps({"provider": "DNSE", "dataset": DATASET, "record_id": case["record_id"], "symbol": case["ticker"], "query": query}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _render_report(summary: dict[str, Any], selection: dict[str, Any], results: list[dict[str, Any]], probes: list[dict[str, Any]]) -> str:
    cohort = summary["cohort"]
    promotion = summary["promotion_analysis"]
    snapshot = summary["current_snapshot"]
    hypothetical = summary["hypothetical_if_promoted"]
    lines = [
        "# Current-regime DNSE daily-OHLC price-basis qualification",
        "",
        "This is bounded qualification evidence only. It does not create provider-wide or regime-wide authority.",
        "",
        "## Cohort reconciliation",
        "",
        f"- Eligible retained cases: {cohort['eligible_official_cases']}",
        f"- Qualified adjusted: {cohort['qualified_adjusted']}",
        f"- Qualified raw: {cohort['qualified_raw']}",
        f"- Insufficient evidence: {cohort['insufficient_evidence']}",
        f"- Provider/request failures: {cohort['provider_request_failures']}",
        f"- Other explicit blocked: {cohort['other']}",
        f"- Exact reconciliation: {cohort['exact_reconciliation']}",
        "",
        "## Per-event outcomes",
        "",
        "| Ticker | Ex-right date | Type | Exchange | Verdict | Status | Sessions | Blocker |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in results:
        sessions = row.get("sessions_observed")
        if isinstance(sessions, dict):
            sessions_text = f"{sessions.get('pre_event', 0)} pre / {sessions.get('post_event', 0)} post"
        else:
            sessions_text = "retained regression" if row.get("already_active_regression") else "0"
        lines.append(
            "| {ticker} | {date} | {event_type} | {exchange} | {verdict} | {status} | {sessions} | {blocker} |".format(
                ticker=row.get("ticker"), date=row.get("official_exright_date"), event_type=row.get("event_type"),
                exchange=row.get("exchange_raw"), verdict=row.get("verdict"), status=row.get("qualification_status"),
                sessions=sessions_text, blocker=row.get("blocker") or "—",
            )
        )
    lines.extend(["", "## Excluded retained cases", ""])
    if selection["excluded"]:
        for row in selection["excluded"]:
            lines.append(f"- {row.get('ticker')} {row.get('exright_date')}: `{row.get('reason')}`")
    else:
        lines.append("- None.")
    lines.extend([
        "", "## Probe lineage", "",
        "Successful raw provider payloads are retained separately and are not embedded in this report.",
    ])
    for probe in probes:
        source = probe.get("source", "live")
        lines.append(f"- `{probe.get('record_id')}`: {source}; request `{probe.get('request_identity', 'not-applicable')}`; payload `{probe.get('raw_payload_hash', 'not-applicable')}`")
    lines.extend([
        "", "## Promotion analysis", "",
        f"- Lifecycle: `{promotion['lifecycle']}`",
        f"- Result: `{promotion['result']}`",
        f"- Proposed scope: `{promotion['proposed_scope']}`",
        f"- Evidence count: {promotion['evidence_count']}",
        f"- Instruments: {', '.join(promotion['instruments']) or 'none'}",
        f"- Exchanges: {', '.join(promotion['exchanges']) or 'none'}",
        f"- Event types: {', '.join(promotion['event_types']) or 'none'}",
        f"- Date range: {promotion['date_range'] or 'none'}",
        f"- Contradictions: {', '.join(promotion['contradictions']) or 'none'}",
        f"- Blockers: {', '.join(promotion['blockers']) or 'none'}",
        "", "## Snapshot implication", "",
        f"- Candidates: {snapshot['candidates']}",
        f"- Known basis under active authority: {snapshot['known_basis_under_active_authority']}",
        f"- Unknown basis: {snapshot['unknown_basis']}",
        f"- Hypothetical is non-authoritative: {hypothetical['clearly_non_authoritative']}",
        f"- Hypothetical known / unknown: {hypothetical['known_basis']} / {hypothetical['unknown_basis']}",
        "", "Already-active HPG and VCB bounded authority was used only as regression evidence and remains unchanged.", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-db", required=True, type=Path)
    parser.add_argument("--universe-parquet", required=True, type=Path)
    parser.add_argument("--phase3-snapshot", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--secrets-file", type=Path, default=None)
    parser.add_argument("--replay-probe-root", type=Path,
                        help="Reuse retained successful probe bodies without any network request.")
    parser.add_argument("--render-existing", action="store_true",
                        help="Re-render REPORT.md from an existing output root without database, parquet, or network access.")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.render_existing:
        required = ["summary.json", "cohort_manifest.json", "event_qualification_results.json", "evidence_probe_manifest.json"]
        missing = [name for name in required if not (args.output_root / name).is_file()]
        if missing:
            parser.error("--render-existing requires existing output files: " + ", ".join(missing))
        summary = json.loads((args.output_root / "summary.json").read_text(encoding="utf-8"))
        selection = json.loads((args.output_root / "cohort_manifest.json").read_text(encoding="utf-8"))
        results = json.loads((args.output_root / "event_qualification_results.json").read_text(encoding="utf-8"))
        probes = json.loads((args.output_root / "evidence_probe_manifest.json").read_text(encoding="utf-8"))
        (args.output_root / "REPORT.md").write_text(_render_report(summary, selection, results, probes), encoding="utf-8")
        return 0
    if args.output_root.exists():
        parser.error("--output-root must not already exist")
    selection = select_cohort(_event_rows(args.event_db), _universe(args.universe_parquet))
    args.output_root.mkdir(parents=True)
    raw_root = args.output_root / "raw"
    raw_root.mkdir()
    probes: dict[str, dict[str, Any]] = {}
    probe_manifest: list[dict[str, Any]] = []
    if args.live and args.replay_probe_root:
        parser.error("--live and --replay-probe-root are mutually exclusive")
    credentials = None
    if args.live:
        status = ensure_credentials_loaded(args.secrets_file)
        if not status["configured"]:
            raise SystemExit("DNSE_CREDENTIAL_INJECTION_REQUIRED")
        credentials = credentials_for_request()
        if credentials is None:
            raise SystemExit("DNSE_CREDENTIAL_INJECTION_REQUIRED")
    retained_probes: dict[str, dict[str, Any]] = {}
    if args.replay_probe_root:
        manifest = json.loads((args.replay_probe_root / "evidence_probe_manifest.json").read_text(encoding="utf-8"))
        for item in manifest:
            query = item.get("query_sent", {})
            raw_file = item.get("raw_payload_file")
            if item.get("ok") and query.get("symbol") and raw_file:
                retained_probes[str(query["symbol"]).upper()] = {**item, "body": json.loads(Path(raw_file).read_text(encoding="utf-8"))}
    for case in selection["eligible"]:
        if case["already_active_regression"]:
            probe_manifest.append({"record_id": case["record_id"], "source": "retained_existing_qualification", "live_request": False})
            continue
        query = query_for_window(case["comparison_window"], symbol=case["ticker"])
        request_identity = _identity(case, query)
        if args.replay_probe_root:
            retained = retained_probes.get(case["ticker"])
            if retained is None:
                probe_manifest.append({"record_id": case["record_id"], "source": "retained_probe_missing", "live_request": False})
            else:
                probes[case["record_id"]] = retained
                probe_manifest.append({"record_id": case["record_id"], "source": "retained_live_probe", "raw_payload_hash": retained.get("raw_payload_hash"), "request_identity": retained.get("request_identity"), "live_request": False})
            continue
        if not args.live:
            probe_manifest.append({"record_id": case["record_id"], "request_identity": request_identity, "query": query, "live_request": False, "status": "PLANNED_NOT_EXECUTED"})
            continue
        response = fetch_capability_raw("ohlc", api_key=credentials[0], api_secret=credentials[1], symbol=case["ticker"], query=query)
        response["request_identity"] = request_identity
        response["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        if "body" in response:
            payload = response["body"]
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            response["raw_payload_hash"] = hashlib.sha256(raw).hexdigest()
            raw_path = raw_root / f"DNSE__{DATASET}__{case['ticker']}__{case['record_id'][:12]}.json"
            _write_json(raw_path, payload)
            response["raw_payload_file"] = str(raw_path)
        probes[case["record_id"]] = response
        probe_manifest.append({key: value for key, value in response.items() if key not in {"body", "body_text_preview"}})
    results = [qualify_event(case, probes.get(case["record_id"])) for case in selection["eligible"]]
    snapshot = pq.read_table(args.phase3_snapshot, columns=["price_basis_status"]).to_pylist()
    promotion = promotion_analysis(results)
    summary = {
        "schema_version": "1.0.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohort": reconcile(results), "excluded_cases": selection["excluded"],
        "promotion_analysis": promotion, "current_snapshot": snapshot_coverage(snapshot),
        "hypothetical_if_promoted": {"clearly_non_authoritative": True, "known_basis": snapshot_coverage(snapshot)["known_basis_under_active_authority"], "unknown_basis": snapshot_coverage(snapshot)["unknown_basis"], "reason": "no_promotion_candidate_approved_or_active"},
        "network_requests": len(probes) if args.live else 0,
        "retained_probe_replay_count": len(probes) if args.replay_probe_root else 0,
    }
    _write_json(args.output_root / "cohort_manifest.json", selection)
    _write_json(args.output_root / "event_qualification_results.json", results)
    _write_json(args.output_root / "evidence_probe_manifest.json", probe_manifest)
    _write_json(args.output_root / "reconciliation_summary.json", summary["cohort"])
    _write_json(args.output_root / "promotion_analysis.json", promotion)
    _write_json(args.output_root / "summary.json", summary)
    (args.output_root / "REPORT.md").write_text(_render_report(summary, selection, results, probe_manifest), encoding="utf-8")
    print(json.dumps({"cohort": summary["cohort"], "promotion_analysis": promotion, "current_snapshot": summary["current_snapshot"], "network_requests": summary["network_requests"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
