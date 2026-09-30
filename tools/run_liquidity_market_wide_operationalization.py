"""OFFICIAL_EXCHANGE_LIQUIDITY_MARKET_WIDE_OPERATIONALIZATION_V1 runner: plan -> bounded probe -> offline build.

``plan``   Frames the governed universe from retained evidence, applies the acquisition-rights gate and
           freezes the exact request list and budget (no network).
``probe``  Executes exactly the frozen plan: foreground, one attempt per request, at most one retry for an
           explicit transient class, fixed spacing, hard budget, consecutive-failure breaker. Exact response
           bytes are content-addressed under the (gitignored) evidence directory and never staged for Git.
           Already-retained series are copied, never re-requested. No DNSE, Vnstock, KBS, VCI or FHSC call.
``build``  Offline, deterministic artifact from retained bytes and retained DNSE batches
           (``--verify-determinism`` builds twice and compares hashes).

No Daily, Dashboard, AI-core publication, production DB or runtime-registry write occurs here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import liquidity_authority_contract as contract  # noqa: E402
import official_exchange_trading_statistics as official  # noqa: E402
import official_liquidity_market_wide as wide  # noqa: E402
from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402
from governed_trading_session_calendar import load_governed_trading_session_calendar  # noqa: E402
from tools import run_liquidity_authority_closure as closure  # noqa: E402

TARGET_SESSION = "2026-09-28"
HARD_REQUEST_BUDGET = 400
REQUEST_SPACING_SECONDS = 1.5
CONSECUTIVE_FAILURE_BREAKER = 3
TRANSIENT_OUTCOMES = frozenset({"HTTP_429", "HTTP_502", "HTTP_503", "HTTP_504", "URLError", "TimeoutError"})
OPS = ROOT / "operations-review"
DEFAULT_OUTPUT = OPS / f"official-exchange-liquidity-research-v1-{TARGET_SESSION.replace('-', '')}"
GITATTRIBUTES = "# Retained evidence: keep exact bytes (hashes are recorded in the ledgers and artifact).\n*.bin binary\n*.jsonl -text\n"


def _frame_inputs(args: argparse.Namespace) -> dict[str, Any]:
    retained = Path(args.retained_root)
    universe_path = retained / "current-official-market-universe-refresh-v1-20260913" / "current_official_market_universe_artifact.json"
    universe = closure._load(universe_path)
    batches = retained / "market-wide-current-liquidity-research-v1-20260928" / "batches"
    trades, ohlc, batch_identities = closure.load_dnse_batches(batches)
    resolved = closure._resolved(trades)
    frame = wide.frame_universe(universe["records"], resolved)
    return {"universe": universe, "universe_sha256": closure._sha256_file(universe_path), "trades": trades, "ohlc": ohlc,
            "batch_identities": batch_identities, "resolved": resolved, "frame": frame}


def _prior_series(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    series, _ = closure._official_series(Path(args.prior_closure_dir))
    return series


def plan_command(args: argparse.Namespace) -> dict[str, Any]:
    inputs = _frame_inputs(args)
    retained = _prior_series(args)
    session = getattr(args, "session", TARGET_SESSION)
    plan = wide.plan_acquisition(inputs["frame"], retained, target_session=session, hard_request_budget=HARD_REQUEST_BUDGET)
    plan = {**plan, "inputs": {"official_universe_identity": inputs["universe"].get("artifact_identity"), "official_universe_file_sha256": inputs["universe_sha256"],
                               "dnse_batch_files": inputs["batch_identities"]},
            "denominators": wide.universe_denominators(inputs["frame"], retained_tickers=retained)}
    plan = {**{k: v for k, v in plan.items() if k not in ("artifact_sha256", "artifact_identity")}}
    plan.update(contract.content_identity(plan, kind="official_exchange_liquidity_acquisition_plan"))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_file(output / ".gitattributes", GITATTRIBUTES)
    atomic_write_json(output / "probe" / "acquisition_plan.json", plan)
    return {"plan": plan["artifact_identity"], "planned_requests": plan["planned_requests"], "planned_by_exchange": plan["planned_by_exchange"],
            "reused_retained_by_exchange": plan["reused_retained_by_exchange"], "not_authorized_not_planned": plan["not_authorized_not_planned"],
            "denominators": plan["denominators"]}


def _copy_prior_entries(prior_dir: Path, output: Path) -> list[dict[str, Any]]:
    """Carry the prior bounded probe's retained responses into this evidence set, bytes verified."""
    ledger = [json.loads(line) for line in (prior_dir / "probe" / "request_ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    raw_out = output / "probe" / "raw"
    raw_out.mkdir(parents=True, exist_ok=True)
    carried = []
    for entry in ledger:
        if entry.get("outcome") == "OK":
            source = prior_dir / "probe" / "raw" / f"{entry['sha256']}.bin"
            if closure._sha256_bytes(source.read_bytes()) != entry["sha256"]:
                raise SystemExit(f"prior retained bytes hash mismatch: {entry['sha256']}")
            target = raw_out / f"{entry['sha256']}.bin"
            if not target.exists():
                shutil.copyfile(source, target)
        carried.append({**entry, "carried_from": "AUTHORITY_CLOSURE_LIQUIDITY_FOUNDATION_V1_BOUNDED_PROBE"})
    return carried


def _attempt(request: Mapping[str, Any], raw_dir: Path) -> dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    status, content_type, body, error = closure._execute(request)
    digest = closure._sha256_bytes(body)
    if body:
        target = raw_dir / f"{digest}.bin"
        if not target.exists():
            atomic_write_file(target, body)
    ok = status == 200 and error is None and bool(body)
    return {"retrieved_at": started, "http_status": status, "content_type": content_type, "bytes": len(body),
            "sha256": digest if body else None, "outcome": "OK" if ok else (error or "EMPTY_BODY")}


def probe_command(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    plan = closure._load(output / "probe" / "acquisition_plan.json")
    if plan["planned_requests"] + plan["retry_allowance"] > HARD_REQUEST_BUDGET:
        raise SystemExit("plan exceeds hard request budget")
    final_path = output / "probe" / "request_ledger.jsonl"
    partial_path = output / "probe" / "request_ledger.partial.jsonl"
    if final_path.exists():
        raise SystemExit(f"refusing to overwrite an existing probe ledger: {final_path}")
    raw_dir = output / "probe" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    done: dict[int, dict[str, Any]] = {}
    if partial_path.exists():
        for line in partial_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                done[item["plan_index"]] = item
    else:
        for index, entry in enumerate(_copy_prior_entries(Path(args.prior_closure_dir), output)):
            done[-1 - index] = {**entry, "plan_index": -1 - index}
        atomic_write_file(partial_path, "".join(json.dumps(done[k], ensure_ascii=False, sort_keys=True) + "\n" for k in sorted(done)))
    requests_made, consecutive = sum(1 for item in done.values() if item.get("http_status") is not None and item["plan_index"] >= 0), 0
    with partial_path.open("a", encoding="utf-8", newline="\n") as handle:
        for index, request in enumerate(plan["requests"]):
            if index in done:
                continue
            if consecutive >= CONSECUTIVE_FAILURE_BREAKER:
                entry = {"plan_index": index, "index": index, "request": request, "outcome": "NOT_ATTEMPTED_BREAKER_OPEN", "attempts": []}
            else:
                attempts = []
                result = _attempt(request, raw_dir)
                requests_made += 1
                time.sleep(REQUEST_SPACING_SECONDS)
                if result["outcome"] in TRANSIENT_OUTCOMES and requests_made < HARD_REQUEST_BUDGET:
                    attempts.append(result)
                    result = _attempt(request, raw_dir)
                    requests_made += 1
                    time.sleep(REQUEST_SPACING_SECONDS)
                consecutive = 0 if result["outcome"] == "OK" else consecutive + 1
                entry = {"plan_index": index, "index": index, "request": request, **result, "attempts": attempts}
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            done[index] = entry
    ordered = [done[k] for k in sorted(done, key=lambda k: (k < 0, abs(k) if k < 0 else k))]
    for position, entry in enumerate(ordered):
        entry["index"] = position
    atomic_write_file(final_path, "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in ordered))
    partial_path.unlink()
    executed = [e for e in ordered if e["plan_index"] >= 0]
    summary = {"plan_identity": plan["artifact_identity"], "planned_requests": plan["planned_requests"],
               "http_requests_made": requests_made, "hard_request_budget": HARD_REQUEST_BUDGET,
               "final_outcomes": dict(sorted(Counter(e["outcome"] for e in executed).items())),
               "retries_used": sum(len(e.get("attempts") or []) for e in executed),
               "carried_prior_entries": sum(1 for e in ordered if e["plan_index"] < 0), "ledger_sha256": closure._sha256_file(final_path)}
    atomic_write_json(output / "probe" / "probe_summary.json", summary)
    return summary


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    inputs = _frame_inputs(args)
    frame, resolved = inputs["frame"], inputs["resolved"]
    series, ledger = closure._official_series(output)
    session = getattr(args, "session", TARGET_SESSION)
    hose_dates = {s for slot in series.values() if slot["exchange"] == official.HOSE for s in slot["rows"]}
    hnx_dates = {s for slot in series.values() if slot["exchange"] != official.HOSE for s in slot["rows"]}
    base = load_governed_trading_session_calendar(closure.GOVERNED_CALENDAR)
    ledger_identity = "probe_request_ledger:" + closure._sha256_file(output / "probe" / "request_ledger.jsonl")
    extension = contract.extend_governed_calendar(base, hose_sessions=hose_dates, hnx_sessions=hnx_dates, evidence_identity=ledger_identity)
    calendar = extension["calendar"]
    qualified = wide.reconcile_and_qualify(series, resolved, inputs["ohlc"], target_session=session)
    units, recon = qualified["units"], qualified["reconciliations"]
    records = {ticker: wide.build_record(row=row, slot=series.get(ticker), dnse_item=resolved.get(ticker), recon=recon.get(ticker), units=units,
                                         calendar=calendar, target_session=session) for ticker, row in sorted(frame.items())}
    tables = wide.coverage_tables(records)
    plan = closure._load(output / "probe" / "acquisition_plan.json")
    summary = closure._load(output / "probe" / "probe_summary.json")
    readiness = wide.readiness_summary(records)
    ohlc_equal = Counter(f"{r['exchange']}:{r.get('dnse_ohlc_v_equals_g1_shares')}:g1_active={'G1' in (r.get('active_boards') or [])}"
                         for r in recon.values() if r.get("verdict") != "EXCHANGE_BINDING_MISMATCH")
    current_basis = Counter()
    for record in records.values():
        basis = record["research_view"]["current_session"]["measurement_basis"]
        if basis:
            current_basis[f"{record['route_exchange']}:{basis}"] += 1
    retained_tickers = {t for t, s in series.items() if s["rows"] and not s["parse_failures"]}
    artifact = {
        "schema_version": "1.0.0", "contract_version": wide.CONTRACT_VERSION, "milestone": wide.MILESTONE,
        "resolved_completed_session": session,
        "inputs": {"acquisition_plan_identity": plan["artifact_identity"], "probe_request_ledger": ledger_identity, "probe_summary": summary,
                   "official_universe_identity": inputs["universe"].get("artifact_identity"), "official_universe_file_sha256": inputs["universe_sha256"],
                   "dnse_batch_files": inputs["batch_identities"], "base_governed_calendar": base.identity},
        "acquisition_rights": {ex: {k: v for k, v in r.items()} for ex, r in wide.ACQUISITION_RIGHTS.items()},
        "rights_reviewed_on": wide.RIGHTS_REVIEWED_ON,
        "denominators": wide.universe_denominators(frame, retained_tickers=retained_tickers),
        "governed_calendar_extension": {k: (v.to_dict() if k == "calendar" and v is not None else v) for k, v in extension.items()},
        "board_unit_qualification": {ex: {b: {k: cell[k] for k in ("state", "volume_state", "value_state", "component", "conflict_count", "volume_truncation_observations")}
                                          | {"exact_volume_ticker_count": len(cell["exact_volume_tickers"]), "exact_value_ticker_count": len(cell["exact_value_tickers"])}
                                          for b, cell in per.items()} for ex, per in units.items()},
        "current_session_basis_counts": dict(sorted(current_basis.items())),
        "dnse_ohlc_v_equals_g1_shares_on_reconciled": dict(sorted(ohlc_equal.items())),
        "coverage": tables, "execution_capacity_readiness": readiness,
        "records": records,
        "authority_boundary": {
            **wide.artifact_authority_summary(records),
            "market_wide_promotion": False,
            "hnx_evidence_generalized_to_hose": False,
            "vnstock_kbs_vci_used": False,
            "raw_exchange_bodies_published": False,
            "knowledge_time_basis": contract.KNOWLEDGE_TIME_BASIS,
        },
    }
    return {**artifact, **contract.content_identity(artifact, kind="official_exchange_liquidity_research")}


def build_command(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    artifact = build_artifact(args)
    if args.verify_determinism and build_artifact(args)["artifact_sha256"] != artifact["artifact_sha256"]:
        raise SystemExit("BUILD_NOT_DETERMINISTIC")
    atomic_write_json(output / "official_exchange_liquidity_research_artifact.json", artifact)
    session = getattr(args, "session", TARGET_SESSION)
    readiness = {"contract_version": "execution_capacity_readiness/v1", "milestone": wide.MILESTONE, "resolved_completed_session": session,
                 "source_artifact_identity": artifact["artifact_identity"], "summary": artifact["execution_capacity_readiness"],
                 "records": {t: wide.execution_capacity_readiness(r) for t, r in artifact["records"].items()},
                 "position_sizing": "BLOCKED", "execution_capacity": "BLOCKED"}
    readiness.update(contract.content_identity(readiness, kind="execution_capacity_readiness"))
    atomic_write_json(output / "execution_capacity_readiness_artifact.json", readiness)
    return {"artifact": artifact["artifact_identity"], "readiness": readiness["artifact_identity"], "denominators": artifact["denominators"],
            "coverage": artifact["coverage"]["by_exchange_and_class"], "unrouted": artifact["coverage"]["unrouted_by_class"],
            "adtv20_exact": artifact["coverage"]["adtv20_exact_by_exchange"], "adv20_exact": artifact["coverage"]["adv20_exact_by_exchange"],
            "current_basis": artifact["current_session_basis_counts"], "units": artifact["board_unit_qualification"],
            "deterministic_dual_build": bool(args.verify_determinism)}


CANONICAL_BASE = "170b2cfbcf77d7ec4f5ca823f5f78e4787795339"


def publication_manifest(artifact: Mapping[str, Any], output: Path) -> dict[str, Any]:
    """Counts, identities and hashes only: nothing here can reconstruct an official response body."""
    ledger = [json.loads(line) for line in (output / "probe" / "request_ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    plan = closure._load(output / "probe" / "acquisition_plan.json")
    summary = closure._load(output / "probe" / "probe_summary.json")
    fresh = [e for e in ledger if e.get("plan_index", -1) >= 0]
    carried = [e for e in ledger if e.get("plan_index", -1) < 0]
    units = {ex: {board: cell["state"] for board, cell in per.items()} for ex, per in artifact["board_unit_qualification"].items()}
    return {
        "schema_version": "official_exchange_liquidity_market_wide_publication_manifest/v1", "milestone": wide.MILESTONE,
        "canonical_base": CANONICAL_BASE, "session": artifact["resolved_completed_session"],
        "publication_disposition": "CODE_CONTRACTS_SYNTHETIC_TESTS_HASHES_AND_DERIVED_COUNTS_ONLY",
        "raw_exchange_response_bodies_published": False, "per_ticker_official_values_published": False,
        "acquisition_rights": {ex: {"decision": r["decision"], "internal_retention": r["internal_retention"], "redistribution": r["redistribution"],
                                    "external_approval_needed": r["external_approval_needed"]} for ex, r in artifact["acquisition_rights"].items()},
        "rights_reviewed_on": artifact["rights_reviewed_on"],
        "acquisition": {"plan_identity": plan["artifact_identity"], "planned_requests": plan["planned_requests"], "hard_request_budget": HARD_REQUEST_BUDGET,
                        "retry_allowance": plan["retry_allowance"], "http_requests_made": summary["http_requests_made"], "retries_used": summary["retries_used"],
                        "final_outcomes": summary["final_outcomes"], "fresh_responses": len(fresh), "carried_prior_responses": len(carried),
                        "response_bytes_total": sum(e.get("bytes") or 0 for e in ledger), "request_ledger_sha256": summary["ledger_sha256"],
                        "planned_by_exchange": plan["planned_by_exchange"], "not_authorized_not_planned": plan["not_authorized_not_planned"],
                        "limits": plan["limits"]},
        "artifact_identity": artifact["artifact_identity"], "denominators": artifact["denominators"],
        "coverage_by_exchange_and_class": artifact["coverage"]["by_exchange_and_class"], "unrouted_by_class": artifact["coverage"]["unrouted_by_class"],
        "coverage_labels": artifact["coverage"]["labels"],
        "adtv20_exact_by_exchange": artifact["coverage"]["adtv20_exact_by_exchange"], "adv20_exact_by_exchange": artifact["coverage"]["adv20_exact_by_exchange"],
        "current_session_basis_counts": artifact["current_session_basis_counts"], "dimension_counts": artifact["coverage"]["dimension_counts"],
        "board_unit_states": units, "dnse_ohlc_v_equals_g1_shares_on_reconciled": artifact["dnse_ohlc_v_equals_g1_shares_on_reconciled"],
        "execution_capacity_readiness": artifact["execution_capacity_readiness"]["dimensions"],
        "authority_boundary": artifact["authority_boundary"],
    }


def manifest_command(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    artifact = closure._load(output / "official_exchange_liquidity_research_artifact.json")
    manifest = publication_manifest(artifact, output)
    target = Path(args.manifest_path)
    atomic_write_file(target, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + chr(10))
    return {"manifest": str(target), "artifact": artifact["artifact_identity"]}


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "probe", "build", "manifest"))
    parser.add_argument("--session", default=TARGET_SESSION, help="target completed session YYYY-MM-DD")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retained-root", type=Path, required=True, help="operations-review root holding the retained official universe and DNSE batches")
    parser.add_argument("--prior-closure-dir", type=Path, required=True, help="retained AUTHORITY_CLOSURE_LIQUIDITY_FOUNDATION_V1 evidence directory")
    parser.add_argument("--verify-determinism", action="store_true")
    parser.add_argument("--manifest-path", type=Path, default=ROOT / "docs" / "liquidity_market_wide_publication_manifest.json")
    args = parser.parse_args(argv)
    if args.output_dir == DEFAULT_OUTPUT and args.session != TARGET_SESSION:
        args.output_dir = OPS / f"official-exchange-liquidity-research-v1-{args.session.replace('-', '')}"
    return args


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    result = {"plan": plan_command, "probe": probe_command, "build": build_command, "manifest": manifest_command}[args.command](args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
