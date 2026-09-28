"""AUTHORITY_CLOSURE_LIQUIDITY_FOUNDATION_V1 runner: plan -> bounded official probe -> offline build.

``plan``   Deterministic qualification cohort from retained evidence only (no network).
``probe``  Executes exactly the planned official-exchange requests: public HOSE/HNX routes, a hard
           request budget, one attempt per request, fixed spacing, a consecutive-failure breaker.
           It keeps the exact response bytes content-addressed, plus a request ledger. No DNSE,
           Vnstock, KBS, VCI or FHSC call, no credential and no polling.
``build``  Offline, deterministic evidence artifact built from the retained probe bytes, the
           retained DNSE 2026-09-28 trades_latest/OHLC batches, and prior liquidity evidence
           (reproduced, not trusted). ``--verify-determinism`` builds twice and compares hashes.

No Daily, Dashboard, AI-core publication, production DB or runtime-registry write occurs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnse_trades_liquidity_basis as descriptive_basis  # noqa: E402
import liquidity_authority_contract as contract  # noqa: E402
import official_exchange_trading_statistics as official  # noqa: E402
from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402
from governed_trading_session_calendar import load_governed_trading_session_calendar  # noqa: E402

TARGET_SESSION = "2026-09-28"
OPS = ROOT / "operations-review"
DEFAULT_OUTPUT = OPS / "liquidity-authority-closure-v1-20260928"
DEFAULT_DNSE_BATCHES = OPS / "market-wide-current-liquidity-research-v1-20260928" / "batches"
DEFAULT_DNSE_ARTIFACT = OPS / "market-wide-current-liquidity-research-v1-20260928" / "market_wide_current_liquidity_research_artifact.json"
DEFAULT_TAIL = OPS / "fhsc-matched-value-tail-window-acquisition-and-g1-reconciliation-v1-20260907" / "g1_tail_reconciliation.json"
DEFAULT_PRIOR_ADTV20 = OPS / "composite-g1-reconciliation-and-adtv20-state-correction-v1-20260908" / "adtv20_corrected.json"
DEFAULT_FHSC_RAW = OPS / "fhsc-historical-matched-value-coverage-scaleout-v1" / "raw"
DEFAULT_FHSC_CANARY = OPS / "fhsc-20260806-anchor-backfill-and-adtv20-unlock-v1-20260908" / "canary_result.json"
GOVERNED_CALENDAR = ROOT / "config" / "governed_trading_session_calendar_v1.json"
WATCHLIST_CONFIG = ROOT / "config" / "owner_research_focus.json"
#: The ceiling is reproduced as it stood at the starting canonical main, never from the edited working copy.
STARTING_MAIN = "36b89f32a82a786d043237c4159c8b469d8985c5"

REQUEST_BUDGET = 160
REQUEST_SPACING_SECONDS = 1.2
CONSECUTIVE_FAILURE_BREAKER = 3
QUANTILES = tuple(i / 10 for i in range(11))
USER_AGENT = "StockLookup-research/1.0 (bounded official-exchange qualification probe; no automation loop)"


def _load(path: Path, *, decimal: bool = False) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_float=Decimal) if decimal else json.loads(text)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def load_dnse_batches(directory: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    trades: dict[str, Any] = {}
    ohlc: dict[str, Any] = {}
    identities = []
    for path in sorted(glob.glob(str(Path(directory) / "batch-*.json"))):
        payload = _load(Path(path), decimal=True)
        if payload.get("session") != TARGET_SESSION:
            raise SystemExit(f"DNSE batch session mismatch: {path}")
        trades.update(payload["trades"])
        ohlc.update(payload["ohlc"])
        identities.append({"file": Path(path).name, "sha256": _sha256_file(Path(path))})
    if not trades:
        raise SystemExit(f"no DNSE batches under {directory}")
    return trades, ohlc, identities


def _resolved(trades: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for ticker, response in sorted(trades.items()):
        if not response.get("ok") or not isinstance(response.get("body"), Mapping):
            out[ticker] = {"state": "DNSE_RESPONSE_NOT_OK", "boards": {}, "exchange": None, "market_id": None}
            continue
        out[ticker] = contract.dnse_board_contributions(response["body"], symbol=ticker)
    return out


# ---------------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------------

def plan_cohort(*, trades: Mapping[str, Any], tail_rows: list[Mapping[str, Any]], watchlist: list[str]) -> dict[str, Any]:
    resolved = _resolved(trades)
    frame = {}
    for ticker, item in resolved.items():
        exchange = item.get("exchange")
        if exchange is None:
            continue
        today = {b: v for b, v in item["boards"].items() if v.get("session") == TARGET_SESSION}
        frame[ticker] = {"exchange": exchange, "today": set(today),
                         "g1_value": today["G1"]["gross_trade_amount_raw"] if "G1" in today else None}
    reasons: dict[str, set[str]] = defaultdict(set)
    conflicts: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in tail_rows:
        if row.get("status") == "CONFLICT" and row.get("ticker") in frame:
            conflicts[frame[row["ticker"]]["exchange"]][str(row.get("conflict_cause"))].append(row["ticker"])
    for exchange in official.EXCHANGES:
        members = sorted(t for t, f in frame.items() if f["exchange"] == exchange)
        for ticker in watchlist:
            if ticker in members:
                reasons[ticker].add("OWNER_WATCHLIST")
        active = sorted((t for t in members if frame[t]["g1_value"] is not None), key=lambda t: (-frame[t]["g1_value"], t))
        for q in QUANTILES:
            if active:
                reasons[active[round(q * (len(active) - 1))]].add(f"G1_VALUE_QUANTILE_{q:.1f}")
        special = {
            "T1_ACTIVE_TODAY": lambda f: "T1" in f["today"],
            "T3_ACTIVE_TODAY": lambda f: "T3" in f["today"],
            "ODD_LOT_PUT_THROUGH_ACTIVE_TODAY": lambda f: bool({"T4", "T6"} & f["today"]),
            "G3_POST_CLOSE_ACTIVE_TODAY": lambda f: "G3" in f["today"],
            "ODD_LOT_ONLY_TODAY": lambda f: f["today"] == {"G4"},
            "NO_BOARD_ACTIVE_TODAY": lambda f: not f["today"],
        }
        limits = {"ODD_LOT_ONLY_TODAY": 2, "NO_BOARD_ACTIVE_TODAY": 2}
        for label, predicate in special.items():
            for ticker in [t for t in members if predicate(frame[t])][: limits.get(label, 3)]:
                reasons[ticker].add(label)
        for cause, count in (("UNEXPLAINED_RESIDUAL", 4), ("NO_G4_NO_PT_STILL_CONFLICT", 2), ("FHSC_MATCHED_EQUALS_G1_PLUS_G4_RAW_SHARES", 2)):
            for ticker in sorted(set(conflicts[exchange].get(cause, [])))[:count]:
                reasons[ticker].add(f"TAIL_CONFLICT_{cause}")
    requests = []
    for ticker in sorted(reasons):
        exchange = frame[ticker]["exchange"]
        requests.append(official.request_for(ticker, exchange, hose_page=1, hnx_rows=60))
        if exchange == official.HOSE and "OWNER_WATCHLIST" in reasons[ticker]:
            requests.extend([official.hose_request(ticker, page=2), official.hose_request(ticker, page=3)])
    cohort = [{"ticker": t, "exchange": frame[t]["exchange"], "selection_reasons": sorted(reasons[t])} for t in sorted(reasons)]
    plan = {"schema_version": "1.0.0", "contract_version": "liquidity_authority_closure_probe_plan/v1",
            "target_session": TARGET_SESSION, "selection_rule": {
                "frame": "retained DNSE 2026-09-28 trades_latest bodies; exchange from marketId",
                "per_exchange": ["owner broader_watchlist members", "G1 grossTradeAmount rank at quantiles 0.0..1.0",
                                 "first 3 alphabetical T1/T3/T4-T6/G3-active-today", "first 2 odd-lot-only and 2 no-activity",
                                 "first alphabetical tail-conflict tickers by cause (4/2/2)"],
                "depth": "HOSE page 1 (20 sessions); HOSE watchlist pages 2-3 (60); HNX/UPCoM 60 rows"},
            "cohort_counts": dict(sorted(Counter(item["exchange"] for item in cohort).items())),
            "cohort": cohort, "requests": requests, "request_count": len(requests), "request_budget": REQUEST_BUDGET}
    if len(requests) > REQUEST_BUDGET:
        raise SystemExit(f"plan exceeds request budget {len(requests)} > {REQUEST_BUDGET}")
    return {**plan, **contract.content_identity(plan, kind="liquidity_authority_closure_probe_plan")}


# ---------------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------------

def _execute(request: Mapping[str, Any]) -> tuple[int | None, str | None, bytes, str | None]:
    data = urllib.parse.urlencode(request["form"]).encode("utf-8") if request["form"] else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.1"}
    if data is not None:
        headers.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"})
    http_request = urllib.request.Request(request["url"], data=data, method=request["method"], headers=headers)
    try:
        with urllib.request.urlopen(http_request, timeout=30) as response:
            return response.status, response.headers.get("Content-Type"), response.read(), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type") if exc.headers else None, exc.read() or b"", f"HTTP_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, None, b"", type(exc).__name__


def run_probe(plan_path: Path, output: Path) -> dict[str, Any]:
    plan = _load(plan_path)
    raw_dir = output / "probe" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output / "probe" / "request_ledger.jsonl"
    if ledger_path.exists():
        raise SystemExit(f"refusing to overwrite an existing probe ledger: {ledger_path}")
    entries, consecutive_failures = [], 0
    for index, request in enumerate(plan["requests"]):
        if index >= REQUEST_BUDGET:
            break
        if consecutive_failures >= CONSECUTIVE_FAILURE_BREAKER:
            entries.append({"index": index, "request": request, "outcome": "NOT_ATTEMPTED_BREAKER_OPEN"})
            continue
        started = dt.datetime.now(dt.timezone.utc).isoformat()
        status, content_type, body, error = _execute(request)
        digest = _sha256_bytes(body)
        if body:
            target = raw_dir / f"{digest}.bin"
            if not target.exists():
                atomic_write_file(target, body)
        ok = status == 200 and error is None and bool(body)
        consecutive_failures = 0 if ok else consecutive_failures + 1
        entries.append({"index": index, "request": request, "retrieved_at": started, "http_status": status,
                        "content_type": content_type, "bytes": len(body), "sha256": digest if body else None,
                        "outcome": "OK" if ok else (error or "EMPTY_BODY")})
        time.sleep(REQUEST_SPACING_SECONDS)
    atomic_write_file(ledger_path, "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in entries))
    summary = {"plan_identity": plan["artifact_identity"], "attempted": sum(1 for e in entries if "http_status" in e),
               "ok": sum(1 for e in entries if e["outcome"] == "OK"),
               "outcomes": dict(sorted(Counter(e["outcome"] for e in entries).items())),
               "ledger_sha256": _sha256_file(ledger_path)}
    atomic_write_json(output / "probe" / "probe_summary.json", summary)
    return summary


# ---------------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------------

def _official_series(output: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Merge every retained OK response into one per-ticker series (pages combined)."""
    ledger = [json.loads(line) for line in (output / "probe" / "request_ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    series: dict[str, dict[str, Any]] = {}
    for entry in ledger:
        request = entry["request"]
        ticker = request["symbol"]
        slot = series.setdefault(ticker, {"ticker": ticker, "exchange": request["exchange"], "source": request["source"],
                                          "rows": {}, "responses": [], "parse_failures": [], "rejected_rows": 0,
                                          "exhausted": False, "oldest": None})
        if entry["outcome"] != "OK":
            slot["parse_failures"].append({"index": entry["index"], "outcome": entry["outcome"]})
            continue
        body = (output / "probe" / "raw" / f"{entry['sha256']}.bin").read_bytes()
        if _sha256_bytes(body) != entry["sha256"]:
            raise SystemExit(f"retained raw bytes hash mismatch for ledger index {entry['index']}")
        parsed = official.parse_response(request, body)
        slot["responses"].append({"index": entry["index"], "sha256": entry["sha256"], "retrieved_at": entry["retrieved_at"],
                                  "url": request["url"], "form": request["form"], "parse_status": parsed["parse_status"],
                                  "rows": len(parsed["rows"])})
        if parsed["parse_status"] != official.PARSED:
            slot["parse_failures"].append({"index": entry["index"], "outcome": parsed["parse_status"]})
            continue
        slot["rejected_rows"] += len(parsed.get("rejected") or [])
        for row in parsed["rows"]:
            existing = slot["rows"].get(row["session"])
            if existing is not None and existing["components"] != row["components"]:
                raise SystemExit(f"official rows disagree across pages: {ticker} {row['session']}")
            slot["rows"][row["session"]] = {key: row[key] for key in ("session", "components", "row_integrity", "symbol_binding")}
        if len(parsed["rows"]) < request["rows_requested"]:
            slot["exhausted"] = True
    for slot in series.values():
        slot["oldest"] = min(slot["rows"]) if slot["rows"] else None
        slot["newest"] = max(slot["rows"]) if slot["rows"] else None
    return series, ledger


def reproduce_prior_ceiling(args: argparse.Namespace, dnse_artifact: Mapping[str, Any], trades: Mapping[str, Any]) -> dict[str, Any]:
    tail = _load(args.tail_reconciliation)
    tail_conflicts = [row for row in tail["rows"] if row.get("status") == "CONFLICT"]
    prior = _load(args.prior_adtv20)["run_1"]
    fhsc_files = sorted(glob.glob(str(Path(args.fhsc_raw_dir) / "*.json")))
    fhsc_0806 = 0
    for path in fhsc_files:
        payload = _load(Path(path))
        rows = ((payload.get("data") or {}).get("data") or []) if isinstance(payload, Mapping) else []
        fhsc_0806 += sum(1 for row in rows if isinstance(row, Mapping) and row.get("date") == "2026-08-06")
    canary = _load(args.fhsc_canary) if Path(args.fhsc_canary).exists() else {}
    g3_rejected = 0
    for ticker, response in trades.items():
        for tick in ((response.get("body") or {}).get("trades") or []) if response.get("ok") else []:
            if tick.get("boardId") == "G3":
                parsed = descriptive_basis.canonicalize_trade_tick(json.loads(json.dumps(tick, default=float)), symbol=ticker, endpoint="trades_latest")
                g3_rejected += parsed["parse_status"] == "UNRECOGNIZED_BOARD_ID"
    code_contract = descriptive_basis.session_liquidity_research_contract(current_session_boards_active=True, historical_scan_state=None)
    shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{STARTING_MAIN}:docs/ROADMAP_STATE.json"], capture_output=True, check=False)
    if shown.returncode != 0:
        raise SystemExit(f"cannot read ROADMAP_STATE.json at starting main {STARTING_MAIN}")
    roadmap = json.loads(shown.stdout.decode("utf-8"))
    blocked = next(item for item in roadmap["blocked_capabilities"] if item["capability"] == "LIQUIDITY_AND_POSITION_SIZING_AUTHORITY")
    return {
        "roadmap_blocked_capability": {"capability": blocked["capability"], "state": blocked["state"], "reference_checkpoint": blocked["reference_checkpoint"],
                                       "read_at": STARTING_MAIN},
        "descriptive_code_contract_states": {dim: cell["state"] for dim, cell in code_contract.items()},
        "current_session_artifact_2026_09_28": {"identity": dnse_artifact["artifact_identity"], "authority_boundary": dnse_artifact["authority_boundary"],
                                                "disposition_counts": dnse_artifact["coverage"]["disposition_counts"]},
        "g3_post_close_ticks_rejected_by_descriptive_parser_2026_09_28": g3_rejected,
        "prior_adtv20_target_2026_09_04": {key: prior[key] for key in ("exact", "coverage_restricted", "semantics_unqualified", "insufficient_window")},
        "tail_conflicts_recounted": {"total": len(tail_conflicts), "by_session": dict(sorted(Counter(r["session"] for r in tail_conflicts).items())),
                                     "by_cause": dict(sorted(Counter(str(r.get("conflict_cause")) for r in tail_conflicts).items()))},
        "fhsc_2026_08_06_rows_in_retained_raw": {"files_scanned": len(fhsc_files), "rows_dated_2026_08_06": fhsc_0806},
        "fhsc_2026_08_06_canary": {key: canary.get(key) for key in ("classification", "attempted", "http_200", "empty_for_2026_08_06") if key in canary},
        "reproduced_verdict": ("CONFIRMED" if len(tail_conflicts) == 752 and prior["exact"] == 0 and prior["coverage_restricted"] == 42
                               and prior["semantics_unqualified"] == 1641 and fhsc_0806 == 0 else "DIFFERS_FROM_PROSE"),
    }


def _adjudicate_tail(tail_rows: list[Mapping[str, Any]], series: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    cells, counts, absent = [], Counter(), 0
    for row in tail_rows:
        slot = series.get(row.get("ticker"))
        if slot is None or row.get("status") not in ("EXACT", "CONFLICT"):
            continue
        official_row = slot["rows"].get(row["session"])
        if official_row is None or official_row["row_integrity"] != "COMPONENTS_SUM_TO_TOTAL":
            absent += 1
            continue
        dnse_pair = (int(row["g1_share_quantity"]), int(row["matched_value_vnd"]))
        fhsc_pair = (int(row["fhsc_matched_volume"]), int(row["fhsc_matched_value"]))
        judged = contract.adjudicate_prior_matched_cell(exchange=slot["exchange"], official_components=official_row["components"],
                                                        dnse_g1=dnse_pair, fhsc_matched=fhsc_pair)
        counts[(slot["exchange"], row["status"], judged["verdict"])] += 1
        cells.append({"ticker": row["ticker"], "exchange": slot["exchange"], "session": row["session"], "prior_status": row["status"],
                      "prior_cause": row.get("conflict_cause"), **judged,
                      "official_matched_all": dict(official_row["components"][contract.MATCHED_ALL]),
                      "dnse_g1_phase_a": {"volume_shares": dnse_pair[0], "value_vnd": dnse_pair[1]},
                      "fhsc_matched": {"volume_shares": fhsc_pair[0], "value_vnd": fhsc_pair[1]}})
    return {"cells": sorted(cells, key=lambda c: (c["ticker"], c["session"])),
            "counts": {f"{exchange}:{status}:{verdict}": n for (exchange, status, verdict), n in sorted(counts.items())},
            "official_row_absent": absent}


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    plan = _load(output / "probe" / "cohort_plan.json")
    trades, ohlc, batch_identities = load_dnse_batches(args.dnse_batches)
    dnse_artifact = _load(args.dnse_artifact)
    series, ledger = _official_series(output)
    resolved = _resolved(trades)
    tail_rows = _load(args.tail_reconciliation)["rows"]

    # Current-session reconciliation + stale-board points for every probed ticker.
    reconciliations, evidence = {}, []
    for ticker, slot in sorted(series.items()):
        item = resolved.get(ticker) or {}
        if item.get("exchange") != slot["exchange"]:
            reconciliations[ticker] = {"verdict": "EXCHANGE_BINDING_MISMATCH", "dnse_exchange": item.get("exchange")}
            continue
        measures = contract.dnse_session_measures(item, session=TARGET_SESSION)
        recon = contract.reconcile_session(measures, slot["rows"].get(TARGET_SESSION), exchange=slot["exchange"])
        points = contract.stale_board_points(item, slot["rows"], exchange=slot["exchange"], target_session=TARGET_SESSION)
        ohlc_v = ((ohlc.get(ticker) or {}).get("body") or {}).get("v") or []
        g1 = next((m for m in measures["_active_measures"] if m["board"] == "G1"), None)
        reconciliations[ticker] = {**recon, "active_boards": measures["active_boards"], "unknown_boards": measures["unknown_boards"],
                                   "dnse_components": measures["components"], "stale_board_points": points,
                                   "dnse_ohlc_v_equals_g1_shares": (bool(ohlc_v) and g1 is not None and Decimal(str(ohlc_v[-1])) == g1["volume_shares"])}
        if recon["verdict"] in (contract.EXACT, contract.VOLUME_TRUNCATED_VALUE_EXACT, contract.CONFLICT):
            evidence.append({"ticker": ticker, "exchange": slot["exchange"], "kind": "CURRENT_SESSION", "reconciliation": recon})
        evidence.extend({"ticker": ticker, "exchange": slot["exchange"], "kind": "STALE_BOARD_POINT", "point": p} for p in points)
    units = contract.qualify_board_units(evidence)

    # Calendar extension from two official publishers.
    base = load_governed_trading_session_calendar(GOVERNED_CALENDAR)
    hose_dates = {s for slot in series.values() if slot["exchange"] == official.HOSE for s in slot["rows"]}
    hnx_dates = {s for slot in series.values() if slot["exchange"] != official.HOSE for s in slot["rows"]}
    ledger_identity = "probe_request_ledger:" + _sha256_file(output / "probe" / "request_ledger.jsonl")
    extension = contract.extend_governed_calendar(base, hose_sessions=hose_dates, hnx_sessions=hnx_dates, evidence_identity=ledger_identity)
    calendar = extension["calendar"]

    # Per-ticker official trailing features + seven-dimension fitness (cohort).
    cohort_records = {}
    for ticker, slot in sorted(series.items()):
        acquired = bool(slot["rows"]) and not slot["parse_failures"]
        features = {}
        if calendar is not None and acquired:
            for feature_id, component, metric, size in contract.TRAILING_FEATURES:
                features[feature_id] = contract.official_trailing_feature(
                    ticker=ticker, exchange=slot["exchange"], feature_id=feature_id, component=component, metric=metric,
                    size=size, target_session=TARGET_SESSION, calendar=calendar, rows_by_session=slot["rows"],
                    series_exhausted=slot["exhausted"], oldest_retained_session=slot["oldest"])
        recon = reconciliations.get(ticker) or {}
        active = bool(recon.get("active_boards"))
        basis = contract.matched_measurement_basis(recon.get("active_boards") or [], units[slot["exchange"]], recon)
        put_through = contract.put_through_precision(recon.get("active_boards") or [], units[slot["exchange"]], recon)
        fitness = contract.dimension_fitness(current_basis=basis, current_active=active, official_series_acquired=acquired, features=features)
        cohort_records[ticker] = {
            "ticker": ticker, "exchange": slot["exchange"], "source": slot["source"],
            "official_series": {"sessions_retained": len(slot["rows"]), "oldest": slot["oldest"], "newest": slot["newest"],
                                "exhausted": slot["exhausted"], "rejected_rows": slot["rejected_rows"],
                                "row_integrity_failures": sum(1 for r in slot["rows"].values() if r["row_integrity"] != "COMPONENTS_SUM_TO_TOTAL"),
                                "responses": slot["responses"], "parse_failures": slot["parse_failures"]},
            "current_session_reconciliation": reconciliations.get(ticker),
            "current_session_measurement_basis": basis if active else None,
            "current_session_put_through_precision": put_through if active else None,
            "features": features, "fitness": fitness,
        }

    # Market-wide current-session projection under the per-exchange unit contract (explicitly labelled).
    market_wide, basis_counts, put_through_counts, g3_active = {}, Counter(), Counter(), 0
    for ticker, item in sorted(resolved.items()):
        exchange = item.get("exchange")
        if exchange is None:
            basis_counts["NO_DNSE_EXCHANGE_BINDING"] += 1
            continue
        measures = contract.dnse_session_measures(item, session=TARGET_SESSION)
        if not measures["active_boards"]:
            basis_counts["NO_BOARD_ACTIVE_TARGET_SESSION"] += 1
            continue
        g3_active += "G3" in measures["active_boards"]
        recon = (cohort_records.get(ticker) or {}).get("current_session_reconciliation")
        recon = recon if (recon or {}).get("exchange") == exchange else None
        basis = contract.matched_measurement_basis(measures["active_boards"], units[exchange], recon)
        put_through = contract.put_through_precision(measures["active_boards"], units[exchange], recon)
        basis_counts[f"{exchange}:{basis}"] += 1
        put_through_counts[f"{exchange}:{put_through}"] += 1
        matched = {name: measures["components"][name] for name in (contract.MATCHED_ROUND_LOT, contract.MATCHED_ODD_LOT, contract.MATCHED_ALL)}
        market_wide[ticker] = {"exchange": exchange, "active_boards": measures["active_boards"], "matched_measurement_basis": basis,
                               "matched_components": matched if basis != contract.BASIS_RAW_COUNTERS_ONLY else None,
                               "put_through_precision": put_through,
                               "put_through_components": ({name: measures["components"][name] for name in (contract.PUT_THROUGH_ROUND_LOT, contract.PUT_THROUGH_ODD_LOT, contract.PUT_THROUGH_ALL)}
                                                          if put_through not in ("UNQUALIFIED", "NO_PUT_THROUGH_ACTIVE") else None),
                               "unqualified_active_boards": sorted(b for b in measures["active_boards"] if units[exchange][b]["state"] != contract.UNIT_QUALIFIED)}

    # Scoped dimension summary and before/after matrix.
    dim_counts = {dim: dict(sorted(Counter(f"{rec['exchange']}:{rec['fitness'][dim]['state']}" for rec in cohort_records.values()).items()))
                  for dim in contract.LIQUIDITY_DIMENSIONS}
    adtv_eligible = sorted(t for t, rec in cohort_records.items() if rec["fitness"][contract.ADTV_RESEARCH]["state"] == contract.ELIGIBLE)
    prior = reproduce_prior_ceiling(args, dnse_artifact, trades)
    adjudication = _adjudicate_tail(tail_rows, series)
    qualified_units = {ex: {"volume_and_value": sorted(b for b, cell in per.items() if cell["state"] == contract.UNIT_QUALIFIED),
                            "value_only": sorted(b for b, cell in per.items() if cell["value_state"] == contract.UNIT_QUALIFIED and cell["state"] != contract.UNIT_QUALIFIED)}
                       for ex, per in units.items()}
    universe = dnse_artifact["universe"]["canonical_candidate_count"]
    matrix = {
        contract.CURRENT_SESSION_LIQUIDITY_RESEARCH: {
            "before": "ELIGIBLE (descriptive raw counters; units UNKNOWN; grossTradeAmount NON_AUTHORITATIVE; HNX G3 post-close ticks rejected)",
            "after": f"ELIGIBLE with absolute shares/VND per component: {sum(v for k, v in basis_counts.items() if k.endswith(contract.BASIS_OFFICIAL_RECONCILED))} "
                     f"officially reconciled, {sum(v for k, v in basis_counts.items() if k.endswith(contract.BASIS_UNIT_CONTRACT_APPLIED))} under the "
                     f"qualified per-exchange board-unit contract, {sum(v for k, v in basis_counts.items() if k.endswith(contract.BASIS_RAW_COUNTERS_ONLY))} raw-counter only"},
        contract.HISTORICAL_LIQUIDITY_RESEARCH: {"before": "BLOCKED (canonical Trades/FHSC evidence ceiling)",
                                                 "after": f"ELIGIBLE for {sum(1 for r in cohort_records.values() if r['fitness'][contract.HISTORICAL_LIQUIDITY_RESEARCH]['state'] == contract.ELIGIBLE)} "
                                                          f"official-series cohort tickers; BLOCKED for the {universe - len(cohort_records)} not acquired"},
        contract.ADV_VOLUME_RESEARCH: {"before": "BLOCKED (no ADV emitted)",
                                       "after": f"PARTIAL for {sum(1 for r in cohort_records.values() if r['fitness'][contract.ADV_VOLUME_RESEARCH]['state'] == contract.PARTIAL)} cohort tickers "
                                                "(official as-traded shares, not corporate-action normalized); BLOCKED otherwise"},
        contract.ADTV_RESEARCH: {"before": f"BLOCKED (exact ADTV20 {prior['prior_adtv20_target_2026_09_04']['exact']}/1683)",
                                 "after": f"ELIGIBLE for {len(adtv_eligible)} cohort tickers (ADTV20_MATCHED_ALL_VND, official); BLOCKED otherwise"},
        contract.EXECUTION_CAPACITY: {"before": "BLOCKED", "after": "BLOCKED"},
        contract.POSITION_SIZING: {"before": "BLOCKED", "after": "BLOCKED"},
        contract.PIT_BACKTEST: {"before": "BLOCKED", "after": "BLOCKED"},
    }
    promoted = bool(adtv_eligible) or any(v["volume_and_value"] for v in qualified_units.values())
    artifact = {
        "schema_version": "1.0.0", "contract_version": contract.CONTRACT_VERSION, "milestone": contract.MILESTONE,
        "target_session": TARGET_SESSION,
        "inputs": {"probe_plan_identity": plan["artifact_identity"], "probe_request_ledger": ledger_identity,
                   "probe_requests": len(ledger), "probe_ok": sum(1 for e in ledger if e["outcome"] == "OK"),
                   "dnse_current_artifact_identity": dnse_artifact["artifact_identity"], "dnse_batch_files": batch_identities,
                   "base_governed_calendar": base.identity},
        "prior_ceiling_reproduced": prior,
        "board_unit_qualification": units, "qualified_board_units": qualified_units,
        "governed_calendar_extension": {key: (value.to_dict() if key == "calendar" and value is not None else value) for key, value in extension.items()},
        "cohort_records": cohort_records,
        "cohort_reconciliation_summary": dict(sorted(Counter(f"{r['exchange']}:{(r['current_session_reconciliation'] or {}).get('verdict')}" for r in cohort_records.values()).items())),
        "dnse_ohlc_v_equals_g1_shares": dict(sorted(Counter(str((r["current_session_reconciliation"] or {}).get("dnse_ohlc_v_equals_g1_shares")) for r in cohort_records.values()).items())),
        "tail_conflict_adjudication": adjudication,
        "fhsc_gap_session_2026_08_06_official_rows": {
            "tickers_with_official_row": sorted(t for t, slot in series.items() if (slot["rows"].get("2026-08-06") or {}).get("row_integrity") == "COMPONENTS_SUM_TO_TOTAL"),
            "note": "the permanent FHSC 2026-08-06 hole does not exist in the official exchange series"},
        "market_wide_current_session_projection": {"matched_basis_counts": dict(sorted(basis_counts.items())), "put_through_precision_counts": dict(sorted(put_through_counts.items())), "g3_active_tickers": g3_active, "records": market_wide},
        "scoped_dimension_counts": dim_counts, "adtv20_eligible_tickers": adtv_eligible,
        "capability_matrix": matrix,
        "sizing_readiness_envelope": contract.sizing_readiness_envelope(qualified_liquidity_tickers=len(adtv_eligible)),
        "pit_dependency": {
            "does_not_require_pit": ["CURRENT_SESSION_LIQUIDITY_RESEARCH", "HISTORICAL_LIQUIDITY_RESEARCH (as-of-today research)", "ADTV_RESEARCH (as-of-today research)"],
            "requires_pit": ["PIT_BACKTEST", "any historical as-known-at liquidity claim", "EXECUTION_CAPACITY / POSITION_SIZING at a past decision time"],
        },
        "authority_boundary": {"QUALIFIED_LIQUIDITY_INPUTS": "PARTIAL_RESEARCH_SCOPED_OFFICIAL_COHORT_ONLY", "POSITION_SIZING_IS_SAFE": False,
                               "execution_input_eligible": False, "position_sizing_eligible": False, "RAW_AS_TRADED": "NOT_PROMOTED",
                               "PIT": "NOT_PROMOTED", "market_wide_promotion": False, "hnx_evidence_generalized_to_hose": False,
                               "vnstock_kbs_vci_used": False, "fhsc_used_as_authority": False},
        "terminal_disposition": "LIQUIDITY_AUTHORITY_PARTIALLY_PROMOTABLE" if promoted else "LIQUIDITY_AUTHORITY_BLOCKED_ON_EXACT_EXTERNAL_EVIDENCE",
    }
    return {**artifact, **contract.content_identity(artifact)}


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "probe", "build"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dnse-batches", type=Path, default=DEFAULT_DNSE_BATCHES)
    parser.add_argument("--dnse-artifact", type=Path, default=DEFAULT_DNSE_ARTIFACT)
    parser.add_argument("--tail-reconciliation", type=Path, default=DEFAULT_TAIL)
    parser.add_argument("--prior-adtv20", type=Path, default=DEFAULT_PRIOR_ADTV20)
    parser.add_argument("--fhsc-raw-dir", type=Path, default=DEFAULT_FHSC_RAW)
    parser.add_argument("--fhsc-canary", type=Path, default=DEFAULT_FHSC_CANARY)
    parser.add_argument("--verify-determinism", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    output = Path(args.output_dir)
    if args.command == "plan":
        trades, _, _ = load_dnse_batches(args.dnse_batches)
        watchlist = list(_load(WATCHLIST_CONFIG).get("broader_watchlist") or [])
        plan = plan_cohort(trades=trades, tail_rows=_load(args.tail_reconciliation)["rows"], watchlist=watchlist)
        atomic_write_json(output / "probe" / "cohort_plan.json", plan)
        print(json.dumps({"plan": plan["artifact_identity"], "cohort": plan["cohort_counts"], "requests": plan["request_count"]}))
    elif args.command == "probe":
        print(json.dumps(run_probe(output / "probe" / "cohort_plan.json", output)))
    else:
        artifact = build_artifact(args)
        if args.verify_determinism:
            again = build_artifact(args)
            if again["artifact_sha256"] != artifact["artifact_sha256"]:
                raise SystemExit("BUILD_NOT_DETERMINISTIC")
        atomic_write_json(output / "liquidity_authority_closure_artifact.json", artifact)
        print(json.dumps({"artifact": artifact["artifact_identity"], "disposition": artifact["terminal_disposition"],
                          "qualified_board_units": artifact["qualified_board_units"], "adtv20_eligible": len(artifact["adtv20_eligible_tickers"]),
                          "deterministic_dual_build": bool(args.verify_determinism)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
