"""Run the bounded direct-VCI basis pilot and write immutable evidence artifacts.

Live acquisition only. Nothing here is imported by the test suite. It reads production
databases through SQLite `mode=ro` URIs and writes exclusively under
`operations-review/vci-direct-basis-pilot-<date>/`.

    python tools/run_vci_basis_pilot.py            # acquire + analyse
    python tools/run_vci_basis_pilot.py --offline  # re-analyse retained artifacts only
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vci_direct_basis_pilot as pilot  # noqa: E402

EVIDENCE_DIR = ROOT / "operations-review" / "vci-direct-basis-pilot-20260804"

CURRENT_DB = Path("C:/Projects/StockLookup/dashboard-runtime/vn_stock.db")
PRE_EVENT_SNAPSHOT_DB = Path(
    "C:/Projects/StockLookup/archive/runtime-backups/VNSTOCK_DATA_BACKUPS/20260719_223620/vn_stock.db"
)
RETAINED_RAW_SAMPLE = ROOT / "operations-review" / "vci_ohlcv_sample_hpg.json"
RETAINED_KBS_SAMPLE = ROOT / "operations-review" / "kbs_ohlcv_sample_hpg.json"

# Browser-shaped headers matching the provider's own web application. No cookie, no
# authorization, no credential of any kind is sent or held.
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
}

# Every window is selected from evidence already retained in this repository. No corporate
# document was acquired and no event date was inferred from price behaviour.
DAILY_WINDOWS = [
    {
        "id": "W1_control_no_event",
        "ticker": "HPG",
        "to_epoch": 1769817600,  # 2026-01-31T00:00:00Z
        "count_back": 5,
        "requested_date_range": ["2026-01-26", "2026-01-30"],
        "selection_evidence": (
            "operations-review/vci_ohlcv_sample_hpg.json (retained raw VCI payload, "
            "sha256 1f57e4fe..., retrieved 2026-08-01T01:08:57Z) reproduces this exact "
            "request; dashboard-runtime/vn_stock.db:corporate_event_records holds no HPG "
            "event with an ex-right date in 2026-01"
        ),
    },
    {
        "id": "W2_cash_dividend_event",
        "ticker": "VCB",
        "to_epoch": 1785542400,  # 2026-08-01T00:00:00Z
        "count_back": 25,
        "requested_date_range": ["2026-07-01", "2026-07-31"],
        "selection_evidence": (
            "dashboard-runtime/vn_stock.db:corporate_event_records VCB/DIV/Cash Dividend "
            "exright_date=2026-07-23 record_date=2026-07-24 value_per_share=450.0 "
            "provider=VCI coverage=partial_unqualified_50_row_cap"
        ),
    },
    {
        "id": "W3_capital_event",
        "ticker": "HPG",
        "to_epoch": 1780358400,  # 2026-06-02T00:00:00Z
        "count_back": 12,
        "requested_date_range": ["2026-05-18", "2026-06-01"],
        "selection_evidence": (
            "dashboard-runtime/vn_stock.db:corporate_event_records HPG/ISS/Share Issue "
            "exright_date=2026-05-25 record_date=2026-05-26 exercise_ratio=0.1 "
            "provider=VCI coverage=partial_unqualified_50_row_cap"
        ),
    },
    {
        "id": "W4_intraday_alignment_daily",
        "ticker": "HPG",
        "to_epoch": 1785888000,  # 2026-08-05T00:00:00Z
        "count_back": 3,
        "requested_date_range": ["2026-08-03", "2026-08-04"],
        "selection_evidence": "current sessions, aligned with the intraday sample below",
    },
]

INTRADAY_REQUEST = {"id": "W5_intraday", "ticker": "HPG", "limit": 30000}

QUALIFIED_EVENTS = {
    "HPG": [
        {
            "ex_date": "2026-05-25",
            "kind": "capital",
            "detail": "ISS share issue, exercise_ratio 0.1",
            "evidence_identity": "vn_stock.db:corporate_event_records[provider=VCI,ticker=HPG,event_code=ISS,exright_date=2026-05-25]",
        },
        {
            "ex_date": "2026-05-11",
            "kind": "cash",
            "detail": "DIV cash dividend, 500 VND/share",
            "evidence_identity": "vn_stock.db:corporate_event_records[provider=VCI,ticker=HPG,event_code=DIV,exright_date=2026-05-11]",
        },
    ],
    "VCB": [
        {
            "ex_date": "2026-07-23",
            "kind": "cash",
            "detail": "DIV cash dividend, 450 VND/share",
            "evidence_identity": "vn_stock.db:corporate_event_records[provider=VCI,ticker=VCB,event_code=DIV,exright_date=2026-07-23]",
        }
    ],
    "VNM": [
        {
            "ex_date": "2026-06-26",
            "kind": "cash",
            "detail": "DIV cash dividend, 1850 VND/share",
            "evidence_identity": "vn_stock.db:corporate_event_records[provider=VCI,ticker=VNM,event_code=DIV,exright_date=2026-06-26]",
        }
    ],
}


def _write(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path.name


def acquire_daily(session, window, budget):
    if budget["spent"] >= pilot.REQUEST_BUDGET:
        raise pilot.VCIPilotError("request_budget_exhausted")
    payload = pilot.daily_payload(window["ticker"], to_epoch=window["to_epoch"], count_back=window["count_back"])
    budget["spent"] += 1
    transport = pilot.acquire(
        endpoint=pilot.DAILY_ENDPOINT, payload=payload, session=session, headers=HEADERS
    )
    body = transport["raw_body"]
    body_sha = pilot.response_sha256(body)
    name = pilot.artifact_name("daily", window["ticker"], retrieved_at=transport["retrieved_at"], body_sha256=body_sha)
    _write(EVIDENCE_DIR / "raw" / name, body)

    parsed = json.loads(body.decode("utf-8"))
    raw_rows = pilot.parse_daily_payload(parsed, symbol=window["ticker"])
    normalized = pilot.normalize_daily(raw_rows)
    observation = pilot.build_observation(
        provider=pilot.PROVIDER,
        source_authority=pilot.SOURCE_AUTHORITY,
        endpoint=pilot.DAILY_ENDPOINT,
        method="POST",
        request_parameters=payload,
        request_headers_redacted=HEADERS,
        retrieved_at=transport["retrieved_at"],
        http_status=transport["http_status"],
        redirect_count=transport["redirect_count"],
        retry_count=transport["retry_count"],
        raw_response_sha256=body_sha,
        response_schema_fingerprint=pilot.schema_fingerprint(parsed),
        ticker=window["ticker"],
        interval="1D",
        requested_date_range=window["requested_date_range"],
        returned_date_range=normalized["returned_date_range"],
        raw_field_names=sorted(parsed[0].keys()),
        normalized_field_names=sorted(normalized["rows"][0].keys()),
        transformations=normalized["transformations"],
        transformation_code_identity=normalized["transformation_code_identity"],
        qualification_verdict="pending_analysis",
        unresolved_semantic_dimensions=["price_adjustment_declaration", "volume_market_scope"],
    )
    observation["window_id"] = window["id"]
    observation["window_selection_evidence"] = window["selection_evidence"]
    observation["raw_artifact"] = name
    _write(EVIDENCE_DIR / f"observation_{window['id']}.json", observation)
    return {"window": window, "raw_rows": raw_rows, "normalized": normalized, "observation": observation}


def acquire_intraday(session, budget):
    if budget["spent"] >= pilot.REQUEST_BUDGET:
        raise pilot.VCIPilotError("request_budget_exhausted")
    payload = pilot.intraday_payload(INTRADAY_REQUEST["ticker"], limit=INTRADAY_REQUEST["limit"])
    budget["spent"] += 1
    transport = pilot.acquire(
        endpoint=pilot.INTRADAY_ENDPOINT, payload=payload, session=session, headers=HEADERS
    )
    body = transport["raw_body"]
    body_sha = pilot.response_sha256(body)
    name = pilot.artifact_name(
        "intraday", INTRADAY_REQUEST["ticker"], retrieved_at=transport["retrieved_at"], body_sha256=body_sha
    )
    _write(EVIDENCE_DIR / "raw" / name, body)
    parsed = json.loads(body.decode("utf-8"))
    rows = pilot.parse_intraday_payload(parsed, symbol=INTRADAY_REQUEST["ticker"])
    return {
        "rows": rows,
        "raw_artifact": name,
        "transport": {k: v for k, v in transport.items() if k != "raw_body"},
        "request_parameters": payload,
        "schema_fingerprint": pilot.schema_fingerprint(parsed),
        "raw_response_sha256": body_sha,
        "rows_returned": len(rows),
    }


def replay_daily(window):
    """Rebuild a window's result from its retained raw artifact -- no network.

    Replaying frozen bytes must reproduce the same normalised rows and the same artifact
    identity; that is what makes the evidence reusable without re-requesting it.
    """
    observation_path = EVIDENCE_DIR / f"observation_{window['id']}.json"
    if not observation_path.exists():
        return None
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    path = EVIDENCE_DIR / "raw" / observation["raw_artifact"]
    body = path.read_bytes()
    body_sha = pilot.response_sha256(body)
    if body_sha != observation["raw_response_sha256"]:
        raise pilot.VCIPilotError(f"retained_artifact_hash_drift:{path.name}")
    expected_name = pilot.artifact_name(
        "daily", window["ticker"], retrieved_at=observation["retrieved_at"], body_sha256=body_sha
    )
    if expected_name != path.name:
        raise pilot.VCIPilotError(f"artifact_identity_not_reproducible:{path.name}")
    parsed = json.loads(body.decode("utf-8"))
    raw_rows = pilot.parse_daily_payload(parsed, symbol=window["ticker"])
    normalized = pilot.normalize_daily(raw_rows)
    if normalized["returned_date_range"] != observation["returned_date_range"]:
        raise pilot.VCIPilotError(f"replay_returned_date_range_drift:{window['id']}")
    # Transport facts come from the original acquisition; everything derived from the
    # bytes is recomputed, so the record always matches the code that produced it. The
    # raw payload itself is never rewritten.
    observation["response_schema_fingerprint"] = pilot.schema_fingerprint(parsed)
    observation["transformations"] = normalized["transformations"]
    observation["transformation_code_identity"] = normalized["transformation_code_identity"]
    _write(EVIDENCE_DIR / f"observation_{window['id']}.json", observation)
    return {"window": window, "raw_rows": raw_rows, "normalized": normalized, "observation": observation}


def replay_intraday():
    """Rebuild the intraday sample from its retained raw artifact -- no network."""
    matches = sorted((EVIDENCE_DIR / "raw").glob(f"vci_intraday_{INTRADAY_REQUEST['ticker']}_*.raw.json"))
    if not matches:
        return None
    path = matches[-1]
    body = path.read_bytes()
    parsed = json.loads(body.decode("utf-8"))
    rows = pilot.parse_intraday_payload(parsed, symbol=INTRADAY_REQUEST["ticker"])
    return {
        "rows": rows,
        "raw_artifact": path.name,
        "raw_response_sha256": pilot.response_sha256(body),
        "schema_fingerprint": pilot.schema_fingerprint(parsed),
        "rows_returned": len(rows),
        "raw_field_names": sorted(parsed[0].keys()) if isinstance(parsed, list) and parsed else [],
    }


def db_rows(db_path: Path, ticker: str, start: str, end: str):
    if not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        return {
            row[0]: {"open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]}
            for row in conn.execute(
                "SELECT date,open,high,low,close,volume FROM ohlcv WHERE ticker=? AND date BETWEEN ? AND ? ORDER BY date",
                (ticker, start, end),
            )
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="skip acquisition, analyse retained artifacts")
    args = parser.parse_args()

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    budget = {"spent": 0}
    results, failures = {}, {}

    if not args.offline:
        session = requests.Session()
        for window in DAILY_WINDOWS:
            try:
                results[window["id"]] = acquire_daily(session, window, budget)
                print(f"[ok] {window['id']} {window['ticker']} -> {results[window['id']]['normalized']['returned_date_range']}")
            except Exception as exc:  # noqa: BLE001
                failures[window["id"]] = {
                    "classification": pilot.classify_failure(exception=exc, status=None, body=None),
                    "detail": f"{type(exc).__name__}: {exc}",
                }
                print(f"[fail] {window['id']}: {failures[window['id']]}")
            time.sleep(1.5)
        try:
            results["W5_intraday"] = acquire_intraday(session, budget)
            print(f"[ok] W5_intraday rows={results['W5_intraday']['rows_returned']}")
        except Exception as exc:  # noqa: BLE001
            failures["W5_intraday"] = {
                "classification": pilot.classify_failure(exception=exc, status=None, body=None),
                "detail": f"{type(exc).__name__}: {exc}",
            }
            print(f"[fail] W5_intraday: {failures['W5_intraday']}")

    # Any window not acquired this run is replayed from its retained raw artifact, so
    # analysis never depends on repeating a request that already succeeded.
    for window in DAILY_WINDOWS:
        if window["id"] not in results:
            replayed = replay_daily(window)
            if replayed:
                results[window["id"]] = replayed
                failures.pop(window["id"], None)
                print(f"[replay] {window['id']} from {replayed['observation']['raw_artifact']}")
    if "W5_intraday" not in results:
        replayed = replay_intraday()
        if replayed:
            results["W5_intraday"] = replayed
            failures.pop("W5_intraday", None)
            print(f"[replay] W5_intraday rows={replayed['rows_returned']} from {replayed['raw_artifact']}")

    summary = {
        "schema_version": pilot.VERSION,
        "provider": pilot.PROVIDER,
        "source_authority": pilot.SOURCE_AUTHORITY,
        "network_requests_issued": budget["spent"],
        "request_budget": pilot.REQUEST_BUDGET,
        "failures": failures,
        "windows": {},
    }

    # --- W1: two observations of the same request at different retrieval times -------
    if "W1_control_no_event" in results:
        live = {r["vci.raw_t"]: r for r in results["W1_control_no_event"]["raw_rows"]}
        retained = json.loads(RETAINED_RAW_SAMPLE.read_text(encoding="utf-8"))
        prior = pilot.parse_daily_payload(retained, symbol="HPG")
        prior_map = {r["vci.raw_t"]: r for r in prior}
        shared = sorted(set(live) & set(prior_map))
        changed = [t for t in shared if live[t] != prior_map[t]]
        summary["windows"]["W1_control_no_event"] = {
            "prior_observation": "operations-review/vci_ohlcv_sample_hpg.json @ 2026-08-01T01:08:57Z",
            "sessions_compared": len(shared),
            "sessions_changed": len(changed),
            "changed_detail": [{"t": t, "prior": prior_map[t], "live": live[t]} for t in changed],
            "lattice": pilot.lattice_profile(results["W1_control_no_event"]["normalized"]["rows"]),
        }

    # --- W2/W3: lattice + boundary, and the pre-event DB snapshot comparison ---------
    for window_id, ticker, snapshot_range in (
        ("W2_cash_dividend_event", "VCB", ("2026-07-01", "2026-07-17")),
        ("W3_capital_event", "HPG", None),
    ):
        if window_id not in results:
            continue
        rows = results[window_id]["normalized"]["rows"]
        lattice = pilot.lattice_profile(rows)
        boundary = pilot.lattice_boundary(rows)
        verdict = pilot.classify_price_basis(
            lattice=lattice, boundary_date=boundary, qualified_events=QUALIFIED_EVENTS[ticker]
        )
        entry = {"lattice": lattice, "boundary_date": boundary, "price_verdict": verdict}

        if snapshot_range:
            pre = db_rows(PRE_EVENT_SNAPSHOT_DB, ticker, *snapshot_range)
            live_by_date = {r["vci.session_date"]: r for r in rows}
            comparison = []
            for date in sorted(pre or {}):
                if date not in live_by_date:
                    continue
                stored, now = pre[date], live_by_date[date]
                comparison.append(
                    {
                        "session_date": date,
                        "pre_event_snapshot_close_vnd": stored["close"],
                        "post_event_live_close_vnd": now["vci.observed_close_vnd"],
                        "close_changed": abs(stored["close"] - now["vci.observed_close_vnd"]) > 0.5,
                        "pre_event_snapshot_volume": stored["volume"],
                        "post_event_live_volume": now["vci.observed_daily_volume"],
                        "volume_changed": stored["volume"] != now["vci.observed_daily_volume"],
                    }
                )
            entry["retroactive_revision_test"] = {
                "prior_observation": f"{PRE_EVENT_SNAPSHOT_DB} (snapshot taken 2026-07-19, before the 2026-07-23 ex-date)",
                "note": (
                    "The snapshot rows were written by daily runs before the ex-date and the "
                    "pipeline never rewrites historical rows, so they are a genuine "
                    "pre-event observation of the same sessions."
                ),
                "sessions_compared": len(comparison),
                "sessions_with_changed_close": sum(1 for c in comparison if c["close_changed"]),
                "sessions_with_changed_volume": sum(1 for c in comparison if c["volume_changed"]),
                "detail": comparison,
            }
        summary["windows"][window_id] = entry

    # --- W4/W5: volume field identity, unit, and reconciliation -----------------------
    if "W5_intraday" in results and "W4_intraday_alignment_daily" in results:
        intraday = results["W5_intraday"]
        quantities = [r["vci.observed_intraday_trade_quantity"] for r in intraday["rows"]]
        daily_rows = results["W4_intraday_alignment_daily"]["normalized"]["rows"]
        latest = daily_rows[-1]
        reconciliation = pilot.reconcile_volume(
            daily_volume=latest["vci.observed_daily_volume"],
            intraday_quantities=quantities,
            intraday_page_size=INTRADAY_REQUEST["limit"],
            intraday_rows_returned=intraday["rows_returned"],
            intraday_covers_full_session=False,
        )
        consistency = pilot.intraday_accumulator_consistency(intraday["rows"])

        # The daily bar for the in-progress session and the newest intraday trade were
        # retrieved one second apart. If the daily `v` equals the running accumulator the
        # matched-trade feed reports at that same instant, the two fields are the same
        # counter -- which qualifies the field's identity without touching its scope.
        newest = max(intraday["rows"], key=lambda row: (row["vci.raw_trunc_time"], str(row["vci.raw_trade_id"])))
        accumulator = newest.get("vci.raw_accumulated_volume")
        identity = {
            "compared_session": latest["vci.session_date"],
            "daily_v": latest["vci.observed_daily_volume"],
            "intraday_newest_accumulated_volume": accumulator,
            "exact_match": accumulator is not None
            and latest["vci.observed_daily_volume"] is not None
            and abs(float(accumulator) - float(latest["vci.observed_daily_volume"])) < 0.5,
            "note": (
                "Both observations are of an in-progress session taken ~1s apart, so this "
                "identifies the field, not the session total."
            ),
        }
        summary["windows"]["volume_reconciliation"] = {
            "compared_session": latest["vci.session_date"],
            "intraday_rows_returned": intraday["rows_returned"],
            "intraday_page_size_requested": INTRADAY_REQUEST["limit"],
            "intraday_raw_artifact": intraday["raw_artifact"],
            "server_side_row_cap_observed": intraday["rows_returned"] < INTRADAY_REQUEST["limit"],
            "reconciliation": reconciliation,
            "intraday_accumulator_consistency": consistency,
            "daily_field_identity": identity,
        }
        summary["volume_declaration"] = pilot.volume_basis_declaration(
            field_identity_qualified=bool(identity["exact_match"]),
            unit_verdict=(
                "qualified"
                if consistency.get("verdict") == "accumulators_internally_consistent"
                else "unknown"
            ),
            adjustment_verdict="unknown",
            reconciliation=reconciliation,
        )

    # --- Volume revision behaviour across the two VCB observations --------------------
    revision = summary["windows"].get("W2_cash_dividend_event", {}).get("retroactive_revision_test")
    if revision:
        deltas = [
            {
                "session_date": row["session_date"],
                "pre": row["pre_event_snapshot_volume"],
                "post": row["post_event_live_volume"],
                "ratio": round(row["post_event_live_volume"] / row["pre_event_snapshot_volume"], 8),
                "pre_is_multiple_of_100": row["pre_event_snapshot_volume"] % 100 == 0,
                "post_is_multiple_of_100": row["post_event_live_volume"] % 100 == 0,
            }
            for row in revision["detail"]
            if row["pre_event_snapshot_volume"]
        ]
        ratios = sorted({item["ratio"] for item in deltas})
        summary["volume_revision_behaviour"] = {
            "sessions": len(deltas),
            "distinct_ratios": len(ratios),
            "ratio_range": [ratios[0], ratios[-1]] if ratios else [],
            "pre_all_multiples_of_100": all(item["pre_is_multiple_of_100"] for item in deltas),
            "post_any_multiple_of_100": any(item["post_is_multiple_of_100"] for item in deltas),
            "conclusion": (
                "Daily volume is revised after first observation. The ratios are not "
                "constant, so this is not a single corporate-action volume factor. The "
                "earlier values being exact multiples of 100 (the HOSE round lot) and the "
                "later ones not is equally consistent with the first observation having "
                "captured a mid-session accumulator. The two causes cannot be separated "
                "from this evidence, so volume_adjustment_basis stays unknown."
            ),
            "detail": deltas,
        }

    # --- KBS read-only comparison (already-local artifact, no new lane) ---------------
    if RETAINED_KBS_SAMPLE.exists():
        kbs = json.loads(RETAINED_KBS_SAMPLE.read_text(encoding="utf-8"))
        kbs_by_date = {str(row["t"])[:10]: row for row in kbs}
        vci_db = db_rows(CURRENT_DB, "HPG", "2026-07-20", "2026-07-30") or {}
        rows = []
        for date in sorted(set(kbs_by_date) & set(vci_db)):
            k, v = kbs_by_date[date], vci_db[date]
            rows.append(
                {
                    "session_date": date,
                    "kbs_close": k["c"],
                    "vci_stored_close": v["close"],
                    "close_exact_match": abs(float(k["c"]) - float(v["close"])) < 1e-6,
                    "kbs_volume": k["v"],
                    "vci_stored_volume": v["volume"],
                    "volume_exact_match": int(k["v"]) == int(v["volume"]),
                }
            )
        summary["kbs_read_only_comparison"] = {
            "kbs_artifact": "operations-review/kbs_ohlcv_sample_hpg.json (retrieved 2026-08-01T01:11:52Z)",
            "sessions_compared": len(rows),
            "close_exact_matches": sum(1 for r in rows if r["close_exact_match"]),
            "volume_exact_matches": sum(1 for r in rows if r["volume_exact_match"]),
            "detail": rows,
            "authority_effect": "none; agreement between two undocumented providers is compatibility, not semantics",
        }

    # --- W1 control verdict ------------------------------------------------------------
    if "W1_control_no_event" in results:
        rows = results["W1_control_no_event"]["normalized"]["rows"]
        lattice = pilot.lattice_profile(rows)
        summary["windows"]["W1_control_no_event"]["price_verdict"] = pilot.classify_price_basis(
            lattice=lattice,
            boundary_date=pilot.lattice_boundary(rows),
            qualified_events=QUALIFIED_EVENTS["HPG"],
        )

    # --- Provider-level price verdict ---------------------------------------------------
    per_ticker = {
        window_id: entry["price_verdict"]
        for window_id, entry in summary["windows"].items()
        if isinstance(entry, dict) and "price_verdict" in entry
    }
    if per_ticker:
        merged = pilot.merge_price_verdicts(per_ticker)
        verdict = {"verdict": merged, "per_window": {k: v["verdict"] for k, v in per_ticker.items()}}

        # Corroboration only. Neither of the next two calls may move the verdict.
        revision_detail = (summary["windows"].get("W2_cash_dividend_event", {}) or {}).get(
            "retroactive_revision_test", {}
        ).get("detail", [])
        fit = {}
        if revision_detail:
            ratios = sorted(
                {
                    round(row["post_event_live_close_vnd"] / row["pre_event_snapshot_close_vnd"], 6)
                    for row in revision_detail
                    if row["pre_event_snapshot_close_vnd"]
                }
            )
            fit = {
                "window": "VCB 2026-07-01..2026-07-17, pre-ex-date observation vs post-ex-date observation",
                "distinct_close_ratios": ratios,
                "single_constant_factor": len(ratios) == 1,
                "declared_cash_dividend_vnd_per_share": 450.0,
                "note": (
                    "A single constant multiplicative factor across independent sessions is "
                    "consistent with a standard cash-dividend back-adjustment, but a fitted "
                    "factor is not a source declaration."
                ),
            }
            verdict = pilot.apply_event_window_fit(verdict, fit=fit)
        if summary.get("kbs_read_only_comparison"):
            verdict = pilot.apply_cross_provider_agreement(
                verdict,
                agreement={
                    "counterparty": "KBS",
                    "basis": "already-local retained artifact, read-only, no new lane",
                    "sessions_compared": summary["kbs_read_only_comparison"]["sessions_compared"],
                    "close_exact_matches": summary["kbs_read_only_comparison"]["close_exact_matches"],
                },
            )
        verdict.update(
            {
                "provider": pilot.PROVIDER,
                "source_authority": pilot.SOURCE_AUTHORITY,
                "source_documentation": "absent",
                "fields": [
                    "vci.raw_open",
                    "vci.raw_high",
                    "vci.raw_low",
                    "vci.raw_close",
                ],
            }
        )
        summary["price_verdict"] = pilot.assert_verdict_scope(verdict)
        summary["downstream_eligibility"] = pilot.downstream_eligibility(
            price_verdict=merged,
            volume_declaration=summary.get(
                "volume_declaration",
                pilot.volume_basis_declaration(
                    field_identity_qualified=False,
                    unit_verdict="unknown",
                    adjustment_verdict="unknown",
                    reconciliation=None,
                ),
            ),
        )

    _write(EVIDENCE_DIR / "pilot_summary.json", summary)
    print(json.dumps({"requests": budget["spent"], "failures": list(failures)}, indent=1))
    print(f"[evidence] {EVIDENCE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
