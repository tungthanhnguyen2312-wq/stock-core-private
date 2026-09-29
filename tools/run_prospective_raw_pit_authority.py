"""PROSPECTIVE_RAW_PIT_AUTHORITY_V1 runner: offline build over retained evidence (no provider call).

``build``     Reads the retained Daily exact-session snapshots (each dated, with per-observation
              ``retrieved_at``), the retained official HOSE trading-result responses (prior liquidity
              probe + this milestone's bounded probe) and the retained official event index. Writes the
              local/private prospective snapshot store (JSONL) and a local authority artifact.
``manifest``  Writes the publication-safe manifest (counts, identities and hashes only).

Raw exchange bodies and per-ticker official prices are never written to a tracked path.
``--verify-determinism`` builds the analysis twice from the loaded inputs and compares hashes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import prospective_market_snapshot_contract as contract  # noqa: E402
import prospective_pit_evidence_analysis as analysis  # noqa: E402
import raw_pit_authority_matrix as matrix  # noqa: E402
from atomic_io import atomic_write_file, atomic_write_json  # noqa: E402

MILESTONE = "PROSPECTIVE_RAW_PIT_AUTHORITY_V1"
FIRST_UNIT_RESOLVED_DAY = "2026-08-24"  # earlier snapshots carry no price_unit and are VND-scaled: excluded, not rescaled
OPS = ROOT / "operations-review"
DEFAULT_OUTPUT = OPS / "prospective-raw-pit-authority-v1-20260929"
VN = dt.timezone(dt.timedelta(hours=7))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dnse_daily(ops_root: Path) -> dict[str, dict[str, Any]]:
    """Retained Daily exact-session snapshots keyed by day. Only the target bar (and the last day's full series) is kept."""
    days: dict[str, dict[str, Any]] = {}
    for directory in sorted(glob.glob(str(ops_root / "p3f9b-market-wide-exact-session-scaleout-*"))):
        name = Path(directory).name[-8:]
        day = f"{name[:4]}-{name[4:6]}-{name[6:]}"
        path = Path(directory) / "p3f9b_mva_exact_session_snapshot.json"
        if not path.is_file() or day < FIRST_UNIT_RESOLVED_DAY:
            continue
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        target = snapshot.get("resolved_completed_session") or snapshot.get("target_session")
        series = {}
        for ticker, record in snapshot["records"].items():
            observations = record.get("observations") or []
            if observations:
                series[ticker] = {o["session"]: (o["open"], o["high"], o["low"], o["close"], o.get("volume"), o.get("retrieved_at"))
                                  for o in observations if o.get("session")}
        days[day] = {"target": target, "file_sha256": _sha256_file(path), "series": series}
    return days


def load_hose(ledgers: list[Path]) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, Any]]:
    """Every retained official HOSE row with its response receipt (T0, later probes...)."""
    rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    responses = 0
    for ledger in ledgers:
        raw_dir = ledger.parent / "raw"
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            url = (entry.get("request") or {}).get("url", "")
            if entry.get("outcome") != "OK" or "api.hsx.vn" not in url or not entry.get("sha256"):
                continue
            body = (raw_dir / f"{entry['sha256']}.bin").read_bytes()
            if hashlib.sha256(body).hexdigest() != entry["sha256"]:
                raise SystemExit(f"retained HOSE body hash mismatch: {entry['sha256']}")
            responses += 1
            for row in json.loads(body)["data"]["list"]:
                session = dt.datetime.fromtimestamp(row["reportDate"], dt.timezone.utc).date().isoformat()
                ticker = row["symbol"].strip()
                rows.setdefault((ticker, session), []).append({
                    "receipt_at": entry["retrieved_at"], "body_sha256": entry["sha256"], "body_bytes": len(body),
                    "ohlc": tuple(row[k] / 1000.0 for k in ("openPrice", "highPrice", "lowPrice", "closePrice")),
                    "average": row["averagePrice"] / 1000.0, "volume": row["totalShare"], "value": row["totalValue"],
                    "main_volume": row["mainVolume"], "url": url})
    return rows, {"responses": responses, "ledgers": [str(p) for p in ledgers]}


def _next_session(sessions: list[str], session: str) -> str | None:
    later = [s for s in sessions if s > session]
    return later[0] if later else None


def analyse(dnse: Mapping[str, Mapping[str, Any]], hose: Mapping[tuple[str, str], list[dict[str, Any]]],
            *, calendar_sessions: list[str], events: list[Mapping[str, Any]], event_windows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic analysis; every count is derived from the retained inputs passed in."""
    days = sorted(dnse)
    last = days[-1]
    t1_series = dnse[last]["series"]
    per_day: dict[str, Any] = {}
    pair_kind: Counter = Counter()
    three: Counter = Counter()
    three_by_kind: Counter = Counter()
    verified_rebasing_tickers: set[str] = set()
    inconsistent_by_day: Counter = Counter()
    for day in days[:-1]:
        target = dnse[day]["target"]
        counts: Counter = Counter()
        for ticker, series in dnse[day]["series"].items():
            t0, t1 = series.get(target), t1_series.get(ticker, {}).get(target)
            if not t0 or not t1:
                continue
            kind = analysis.classify_bar_pair(t0[:4], t1[:4])
            counts[kind] += 1
            pair_kind[kind] += 1
            if kind == analysis.INCONSISTENT:
                inconsistent_by_day[day] += 1
            official = hose.get((ticker, target))
            if official:
                verdict = analysis.three_way_basis(official[0]["ohlc"], t0[:4], t1[:4])
                if kind != analysis.IDENTICAL:
                    three[verdict] += 1
                    three_by_kind[f"{kind}|{verdict}"] += 1
                    if verdict == analysis.HOSE_EQ_T0_ONLY:
                        # official series equals the value known at T0 while the re-fetched DNSE series differs:
                        # the re-fetched series was re-based after the fact, the official series was not.
                        verified_rebasing_tickers.add(ticker)
        per_day[day] = dict(sorted(counts.items()))
    windows = []
    for window in event_windows:
        ticker, ex = window["ticker"], window["ex_date"]
        sessions = sorted(s for (t, s) in hose if t == ticker)
        pre = [s for s in sessions if s < ex]
        post = [s for s in sessions if s >= ex]
        if not pre or not post or ticker not in t1_series:
            windows.append({**window, "verdict": "NO_COMPARABLE_WINDOW"})
            continue
        pre_s, post_s = pre[-1], post[0]
        o_pre, o_post = hose[(ticker, pre_s)][-1]["ohlc"][3], hose[(ticker, post_s)][-1]["ohlc"][3]
        d_pre, d_post = t1_series[ticker].get(pre_s), t1_series[ticker].get(post_s)
        if not d_pre or not d_post:
            windows.append({**window, "verdict": "NO_COMPARABLE_DNSE_BAR"})
            continue
        ratio_pre = analysis.event_window_ratio(o_pre, d_pre[3])
        post_equal = abs(o_post - d_post[3]) < analysis.PRICE_EPSILON
        verdict = ("HOSE_UNADJUSTED_DNSE_REBASED_ACROSS_EVENT" if abs(ratio_pre - 1) > 0.001 and post_equal else
                   "NO_REBASING_OBSERVED" if abs(ratio_pre - 1) <= 0.001 else "INCONCLUSIVE")
        windows.append({**window, "pre_ex_session": pre_s, "post_ex_session": post_s, "official_pre_ex_close_over_1000": o_pre,
                        "dnse_refetched_pre_ex_close": d_pre[3], "observed_rebasing_ratio": round(ratio_pre, 5),
                        "post_ex_close_equal": post_equal, "official_sessions_retained": len(sessions), "verdict": verdict})
    return {"pairs_by_kind": dict(sorted(pair_kind.items())), "per_day": per_day,
            "inconsistent_pairs_by_day": dict(sorted(inconsistent_by_day.items())),
            "three_way_on_revised_pairs": dict(sorted(three.items())),
            "three_way_by_pair_kind": dict(sorted(three_by_kind.items())),
            "official_verified_rebasing_pairs": three.get(analysis.HOSE_EQ_T0_ONLY, 0),
            "official_verified_rebasing_tickers": len(verified_rebasing_tickers),
            "t0_bar_not_final_pairs": three.get(analysis.HOSE_EQ_T1_ONLY, 0),
            "unresolved_pairs": three.get(analysis.OFFICIAL_EQ_NEITHER, 0),
            "_verified_rebasing_tickers": sorted(verified_rebasing_tickers),
            "event_windows": windows, "event_authority": analysis.event_authority_table(events)}


def build_snapshots(dnse, hose, *, calendar_sessions, unadjusted_tickers):
    """Yield (store, record) for every prospectively-targeted DNSE bar and every retained official HOSE row."""
    for day in sorted(dnse):
        target = dnse[day]["target"]
        nxt = _next_session(calendar_sessions, target)
        for ticker, series in sorted(dnse[day]["series"].items()):
            bar = series.get(target)
            if not bar or not bar[5]:
                continue
            official = hose.get((ticker, target))
            agreement = None if not official else analysis.bars_equal(official[0]["ohlc"], bar[:4])
            payload = contract.canonical({"ticker": ticker, "session": target, "bar": list(bar[:5]), "retrieved_at": bar[5]})
            yield "dnse", contract.build_snapshot(
                provider="DNSE", source_id="DNSE_OHLC_1D_DAILY_EXACT_SESSION_SNAPSHOT", route="/price/ohlc", ticker=ticker, exchange=None,
                session=target, receipt_at=bar[5], payload_sha256=contract.sha256_hex(payload), payload_bytes=len(payload),
                payload_hash_kind="canonical_json_of_retained_observation", next_session=nxt,
                ohlc={"open": bar[0], "high": bar[1], "low": bar[2], "close": bar[3]}, volume_value={"volume": bar[4]},
                board_basis={"unit": "SOURCE_PRICE_UNIT_UNDOCUMENTED", "board": "DNSE_OHLC_1D_AGGREGATE"},
                source_claim=contract.SOURCE_BASIS_UNDOCUMENTED,
                # The T0 receipt is the value as known then; later re-basing of a re-fetched series does not relabel it.
                empirical=contract.EMPIRICAL_NOT_TESTED, cross_source_agreement=agreement, payload_observed_at=None)
    for (ticker, session), receipts in sorted(hose.items()):
        nxt = _next_session(calendar_sessions, session)
        for item in receipts:
            open_, high, low, close = item["ohlc"]
            yield "hose", contract.build_snapshot(
                provider="HOSE", source_id="HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT",
                route="/mk/api/v1/market/securities/tradingresult", ticker=ticker, exchange="HOSE", session=session,
                receipt_at=item["receipt_at"], payload_sha256=item["body_sha256"], payload_bytes=item["body_bytes"],
                payload_hash_kind="exact_http_response_body_sha256", next_session=nxt,
                ohlc={"open": open_, "high": high, "low": low, "close": close, "average": item["average"]},
                volume_value={"volume": item["volume"], "value": item["value"], "matched_round_lot_volume": item["main_volume"]},
                board_basis={"unit": "VND_DIVIDED_BY_1000_FOR_COMPARISON", "scope": "all boards, exchange-published daily result"},
                source_claim=contract.SOURCE_BASIS_UNDOCUMENTED,
                empirical=(contract.EMPIRICAL_UNADJUSTED_ACROSS_EVENT if ticker in unadjusted_tickers else contract.EMPIRICAL_NOT_TESTED),
                cross_source_agreement=None, payload_observed_at=None)


def _probe_revision(hose: Mapping[tuple[str, str], list[dict[str, Any]]], calendar_sessions: list[str], t1_marker: str) -> dict[str, Any]:
    """T0 (first receipt) vs T1 (probe receipt) for every ticker/session present in both."""
    results: Counter = Counter()
    tickers: set[str] = set()
    for (ticker, session), receipts in sorted(hose.items()):
        if len(receipts) < 2:
            continue
        t0, t1 = receipts[0], receipts[-1]
        if t1["receipt_at"] == t0["receipt_at"]:
            continue
        def snap(item):
            return contract.build_snapshot(
                provider="HOSE", source_id="HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT",
                route="/mk/api/v1/market/securities/tradingresult", ticker=ticker, exchange="HOSE", session=session,
                receipt_at=item["receipt_at"], payload_sha256=item["body_sha256"], payload_bytes=item["body_bytes"],
                payload_hash_kind="exact_http_response_body_sha256", next_session=_next_session(calendar_sessions, session),
                ohlc=dict(zip(("open", "high", "low", "close"), item["ohlc"])))
        outcome = contract.revision_classification(snap(t0), snap(t1))
        results[outcome["classification"]] += 1
        tickers.add(ticker)
    return {"tested_ticker_sessions": sum(results.values()), "tested_tickers": len(tickers), "by_classification": dict(sorted(results.items())),
            "scope": "HOSE tradingresult O/H/L/C, retained T0 (2026-09-28) vs T1 (2026-09-29 probe); an interval of hours, not a long-run claim"}


def trades_verdict(ops_root: Path, hose: Mapping[tuple[str, str], list[dict[str, Any]]], session: str) -> dict[str, Any]:
    """DNSE trades_latest per-board session aggregates vs the official HOSE row, plus the fail-closed reconstruction demo."""
    counts: Counter = Counter()
    for path in sorted(glob.glob(str(ops_root / "market-wide-current-liquidity-research-v1-20260928" / "batches" / "batch-*.json"))):
        batch = json.loads(Path(path).read_text(encoding="utf-8"))
        for ticker, item in batch["trades"].items():
            official = hose.get((ticker, session))
            if not official or not item.get("ok"):
                continue
            row = official[0]
            if not row["main_volume"]:
                counts["official_no_matched_trading"] += 1
                continue
            g1 = [t for t in item["body"]["trades"] if t["boardId"] == "G1"]
            if not g1:
                counts["no_g1_record"] += 1
                continue
            x = g1[0]
            counts["compared"] += 1
            counts["open_equal"] += round(x["openPrice"], 6) == round(row["ohlc"][0], 6)
            counts["high_equal"] += round(x["highestPrice"], 6) == round(row["ohlc"][1], 6)
            counts["low_equal"] += round(x["lowestPrice"], 6) == round(row["ohlc"][2], 6)
            counts["last_match_equals_close"] += round(x["matchPrice"], 6) == round(row["ohlc"][3], 6)
    demo_none = analysis.reconstruct_daily_ohlc_from_trades([], session=session, completeness_proof=None)
    demo_cap = analysis.reconstruct_daily_ohlc_from_trades(
        [{"boardId": "G1", "time": f"{session} 10:00:00.000", "matchPrice": 1.0}], session=session,
        completeness_proof={"pages_complete": True, "http_failures": 0, "page_sizes": [analysis.DNSE_TRADES_PAGE_CAP]})
    return {"same_session_trades_latest_vs_official": dict(sorted(counts.items())),
            "historical_tick_corpus_locally_available": False,
            "local_trade_page_sample": "one page-capped canonical smoke parquet (SSI 2026-06-17: 100 rows at the DNSE page cap)",
            "fail_closed_without_completeness_proof": demo_none["reason_codes"],
            "fail_closed_at_page_cap": demo_cap["reason_codes"],
            "verdict": "HISTORICAL_TRADES_DERIVED_OHLC_NOT_AVAILABLE_LOCALLY_FAIL_CLOSED"}


def build(args: argparse.Namespace) -> dict[str, Any]:
    ops_root = Path(args.ops_root)
    output = Path(args.output_dir)
    ledgers = [Path(p) for p in args.hose_ledger]
    dnse = load_dnse_daily(ops_root)
    hose, hose_meta = load_hose(ledgers)
    calendar = json.loads((ROOT / "config" / "governed_trading_session_calendar_v1.json").read_text(encoding="utf-8"))
    calendar_sessions = sorted(set(calendar["sessions"]) | {v["target"] for v in dnse.values()})
    event_artifact = json.loads((ops_root / "current-official-event-context-integration-v1-20260905" / "current_official_event_context_artifact.json").read_text(encoding="utf-8"))
    events = [{**e, "ticker": t} for t, r in event_artifact["records"].items() for e in r["events"]]
    windows = [{"ticker": "HPG", "ex_date": "2026-05-25", "event_type": "STOCK_BONUS_ISSUE", "ex_date_source": "DNSE bounded authority (provider evidence, not official)"},
               {"ticker": "VCB", "ex_date": "2026-07-23", "event_type": "CASH_DIVIDEND", "ex_date_source": "DNSE bounded authority (provider evidence, not official)"}]
    result = analyse(dnse, hose, calendar_sessions=calendar_sessions, events=events, event_windows=windows)
    if args.verify_determinism:
        again = analyse(dnse, hose, calendar_sessions=calendar_sessions, events=events, event_windows=windows)
        if contract.sha256_hex(contract.canonical(again)) != contract.sha256_hex(contract.canonical(result)):
            raise SystemExit("ANALYSIS_NOT_DETERMINISTIC")
    output.mkdir(parents=True, exist_ok=True)
    stores = {"dnse": output / "dnse_prospective_snapshots.jsonl", "hose": output / "hose_official_snapshots.jsonl"}
    handles = {k: p.open("w", encoding="utf-8", newline="\n") for k, p in stores.items()}
    summary_rows: dict[str, list] = {"dnse": [], "hose": []}
    counts: Counter = Counter()
    identity_digest = {"dnse": hashlib.sha256(), "hose": hashlib.sha256()}
    try:
        for store, record in build_snapshots(dnse, hose, calendar_sessions=calendar_sessions, unadjusted_tickers=set(result["_verified_rebasing_tickers"])):
            handles[store].write(contract.canonical(record).decode("utf-8") + "\n")
            identity_digest[store].update(record["snapshot_identity"].encode())
            summary_rows[store].append(record)
            counts[store] += 1
    finally:
        for h in handles.values():
            h.close()
    store_summary = {k: {**contract.summarize(v), "file_sha256": _sha256_file(stores[k]), "identity_chain_sha256": identity_digest[k].hexdigest()}
                     for k, v in summary_rows.items()}
    dnse_records = summary_rows["dnse"]
    prospective = [r for r in dnse_records if r["acquisition"]["capture_timing"] == contract.PROSPECTIVE_SAME_SESSION_CAPTURE]
    raw_qualified = [r for r in dnse_records if contract.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE in r["qualification"]["allowed_uses"]]
    last_day = sorted(dnse)[-1]
    same_session_agree = sum(1 for r in dnse_records if r["trading_session"] == dnse[last_day]["target"]
                             and r["observation"]["cross_source_agreement"] is True)
    revision = _probe_revision(hose, calendar_sessions, "T1")
    trades = trades_verdict(ops_root, hose, dnse[last_day]["target"])
    ea = result["event_authority"]
    evidence = {
        "prospective_sessions": len({r["trading_session"] for r in prospective}), "prospective_dnse_bars": len(prospective),
        "prospective_raw_qualified_bars": len(raw_qualified), "same_session_cross_source_agreement_09_28": same_session_agree,
        "hose_tickers": len({t for (t, _s) in hose}), "hose_event_tests_unadjusted": len(set(result["_verified_rebasing_tickers"]) | {
            w["ticker"] for w in result["event_windows"] if w.get("verdict") == "HOSE_UNADJUSTED_DNSE_REBASED_ACROSS_EVENT"}),
        "explicit_ex_date_events": ea["explicit_ex_date"], "ratio_or_cash_terms_events": ea["ratio_or_cash_terms"],
        "publication_time_events": ea["publication_time_retained"], "qualified_factor_chain_events": 0,
        "official_verified_rebasing_pairs": result["official_verified_rebasing_pairs"],
        "t0_bar_not_final_pairs": result["t0_bar_not_final_pairs"],
    }
    authority = matrix.evaluate(evidence)
    body = {
        "schema_version": "1.0.0", "milestone": MILESTONE, "contract_version": contract.CONTRACT_VERSION,
        "canonical_base": "ac9b8cf5473191fb054782e441e1f5145897c0c3",
        "inputs": {"dnse_daily_snapshots": {d: {"target": v["target"], "file_sha256": v["file_sha256"]} for d, v in sorted(dnse.items())},
                   "hose_retained_responses": hose_meta["responses"], "calendar_sessions": len(calendar_sessions)},
        "snapshot_store": store_summary,
        "prospective_bars": {"post_close_same_session": len(prospective), "raw_as_traded_qualified_cross_source": len(raw_qualified),
                             "as_known_only": len(prospective) - len(raw_qualified)},
        "revision_history": {k: v for k, v in result.items() if not k.startswith("_") and k != "event_authority"},
        "probe_revision_t0_vs_t1": revision, "trades_derived_ohlc": trades, "corporate_action_events": ea,
        "evidence_counts": evidence, "authority_matrix": authority,
        "terminal_disposition": "PROSPECTIVE_PIT_OPERATIONAL / HISTORICAL_PIT_PARTIAL",
        "authority_boundary": {"raw_exchange_bodies_published": False, "per_ticker_official_prices_published": False,
                               "provider_calls_by_build": 0, "production_db_written": False, "execution_authority": False,
                               "pit_backtest_authority": False, "active_universe_promoted": False},
    }
    body.update(contract.content_identity(body, kind="prospective_raw_pit_authority"))
    if args.verify_determinism:
        body["deterministic_dual_build"] = True
    atomic_write_json(output / "prospective_raw_pit_authority_artifact.json", body)
    return {"artifact": body["artifact_identity"], "snapshots": dict(counts), "prospective": body["prospective_bars"],
            "pairs": result["pairs_by_kind"], "three_way": result["three_way_on_revised_pairs"],
            "windows": [{k: w.get(k) for k in ("ticker", "ex_date", "observed_rebasing_ratio", "verdict")} for w in result["event_windows"]],
            "probe_revision": revision, "matrix_changed": authority["changed"]}


def manifest(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir)
    artifact = json.loads((output / "prospective_raw_pit_authority_artifact.json").read_text(encoding="utf-8"))
    probe = json.loads((output / "probe" / "probe_summary.json").read_text(encoding="utf-8"))
    public = {
        "schema_version": "prospective_raw_pit_publication_manifest/v1", "milestone": MILESTONE, "canonical_base": artifact["canonical_base"],
        "publication_disposition": "CODE_CONTRACTS_SYNTHETIC_TESTS_HASHES_AND_DERIVED_COUNTS_ONLY",
        "raw_exchange_response_bodies_published": False, "per_ticker_official_prices_published": False,
        "artifact_identity": artifact["artifact_identity"], "terminal_disposition": artifact["terminal_disposition"],
        "snapshot_store": {k: {kk: vv for kk, vv in v.items()} for k, v in artifact["snapshot_store"].items()},
        "prospective_bars": artifact["prospective_bars"], "revision_history": {k: artifact["revision_history"][k] for k in (
            "pairs_by_kind", "three_way_on_revised_pairs", "three_way_by_pair_kind", "official_verified_rebasing_pairs",
            "official_verified_rebasing_tickers", "t0_bar_not_final_pairs", "unresolved_pairs", "inconsistent_pairs_by_day")},
        "event_window_tests": [{k: w.get(k) for k in ("ticker", "ex_date", "event_type", "ex_date_source", "observed_rebasing_ratio", "post_ex_close_equal",
                                                       "official_sessions_retained", "verdict")} for w in artifact["revision_history"]["event_windows"]],
        "probe": {"requests": probe["http_requests_made"], "hard_budget": probe["hard_request_budget"], "final_outcomes": probe["final_outcomes"],
                  "retries_used": probe["retries_used"], "plan_sha256": probe["plan_sha256"], "ledger_sha256": probe["ledger_sha256"]},
        "probe_revision_t0_vs_t1": artifact["probe_revision_t0_vs_t1"], "trades_derived_ohlc": artifact["trades_derived_ohlc"],
        "corporate_action_events": artifact["corporate_action_events"], "authority_matrix": artifact["authority_matrix"],
        "authority_boundary": artifact["authority_boundary"],
    }
    target = Path(args.manifest_path)
    atomic_write_file(target, json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {"manifest": str(target), "artifact": artifact["artifact_identity"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "manifest"))
    parser.add_argument("--ops-root", type=Path, required=True, help="operations-review root holding the retained Daily snapshots and event context")
    parser.add_argument("--hose-ledger", type=Path, action="append", default=[], help="retained HOSE request_ledger.jsonl (repeatable, oldest first)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-determinism", action="store_true")
    parser.add_argument("--manifest-path", type=Path, default=ROOT / "docs" / "prospective_raw_pit_publication_manifest.json")
    args = parser.parse_args(argv)
    print(json.dumps({"build": build, "manifest": manifest}[args.command](args), ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
