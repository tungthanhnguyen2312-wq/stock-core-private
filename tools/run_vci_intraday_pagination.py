"""Exhaust the VCI intraday tape for one ticker and one session segment.

One symbol, one date, one direction. The request cap is computed before the first request
and never raised during the run. There is no retry of the pilot, no background execution,
no timer and no polling loop: it runs once, stops on the first stop condition, and every
later analysis reads the retained page artifacts offline.

    python tools/run_vci_intraday_pagination.py --execute
    python tools/run_vci_intraday_pagination.py --offline
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vci_direct_basis_pilot as pilot  # noqa: E402
import vci_intraday_pagination as pager  # noqa: E402

EVIDENCE_ROOT = ROOT / "operations-review" / "vci-intraday-pagination-20260804"
# Run 01 used an off-by-one cursor and is retained as the evidence that established the
# exclusive page boundary. Run 02 is the corrected scan. Neither overwrites the other.
# Run 03 is the reported pilot: HPG's tape carries seconds at the 100-row cap, which a
# one-second cursor provably cannot resolve, so the scan moved to the sparsest ticker
# already inside the approved pilot scope. Still one symbol and one date per run.
RUNS = {
    "HPG": ("run-02-corrected-cursor", 11_145_500, 1_469.0),
    "VCB": ("run-03-vcb-complete-segment", 1_877_000, 359.0),
}
TICKER = "VCB"
RUN_ID, EXPECTED_SESSION_QUANTITY, MEAN_TRADE_QUANTITY = RUNS[TICKER]
EVIDENCE_DIR = EVIDENCE_ROOT / RUN_ID
PAGES_DIR = EVIDENCE_DIR / "pages"

SESSION_DATE = "2026-08-04"

# 2026-08-04T04:30:00Z == 11:30:00 ICT, the HOSE morning-session close. The tape is frozen
# through the lunch halt, so the segment has a fixed end as well as a provable start.
START_CURSOR = 1785817800
SEGMENT = "morning_session_open_to_1130_ict_lunch_halt"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
}

REQUEST_DELAY_SECONDS = 0.6


def ict(epoch: int) -> str:
    return (datetime.fromtimestamp(int(epoch), tz=timezone.utc) + timedelta(hours=7)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(pager.canonical_json(payload), encoding="utf-8")


def paginate(session) -> dict:
    budget = pager.compute_request_cap(
        expected_session_quantity=EXPECTED_SESSION_QUANTITY,
        mean_trade_quantity=MEAN_TRADE_QUANTITY,
    )
    cap = budget["cap"]
    print(f"[cap] {cap} requests ({budget['basis']}, ~{budget['estimated_pages']} pages estimated)")

    cursor = START_CURSOR
    previous_cursor: int | None = None
    seen_cursors: list[int] = []
    transitions: list[dict] = []
    dense_seconds: list[dict] = []
    all_rows: list[dict] = []
    requests_made = 0
    stop_reason = "request_cap_reached"
    session_start_confirmed = False

    while True:
        if requests_made >= cap:
            stop_reason = "request_cap_reached"
            break

        payload = pilot.intraday_payload(TICKER, limit=pager.OBSERVED_SERVER_ROW_CAP, trunc_time=cursor)
        transport = pilot.acquire(
            endpoint=pilot.INTRADAY_ENDPOINT, payload=payload, session=session, headers=HEADERS
        )
        requests_made += 1
        body = transport["raw_body"]
        digest = pager.page_hash(body)
        page_index = requests_made
        _write(PAGES_DIR / f"page_{page_index:04d}_{cursor}_{digest[:16]}.raw.json", body)

        parsed = json.loads(body.decode("utf-8"))
        if not parsed:
            transitions.append(
                {"page": page_index, "request_cursor": cursor, "rows": 0, "page_sha256": digest}
            )
            stop_reason = "empty_page"
            break

        rows = pilot.parse_intraday_payload(parsed, symbol=TICKER)
        all_rows.extend(rows)
        oldest = pager.oldest_trunc_time(rows)
        candidate = pager.next_cursor(rows)
        transitions.append(
            {
                "page": page_index,
                "request_cursor": cursor,
                "request_cursor_ict": ict(cursor),
                "rows": len(rows),
                "page_sha256": digest,
                "newest_trunc_time": max(int(r["vci.raw_trunc_time"]) for r in rows),
                "oldest_trunc_time": oldest,
                "oldest_trunc_time_ict": ict(oldest),
                "next_cursor": candidate,
                "boundary": pager.CURSOR_BOUNDARY,
            }
        )

        if pager.session_start_reached(rows):
            session_start_confirmed = True
            stop_reason = "session_start_boundary_reached"
            break

        try:
            pager.assert_cursor_advances(previous_cursor, candidate, seen=seen_cursors)
        except pager.PaginationError as exc:
            # A whole page inside one second: the cursor has one-second resolution, so the
            # rest of that second is unreachable. Step past it and let the accumulator
            # measure what was skipped, rather than stopping blind or looping.
            if pager.page_is_single_second(rows) and "did_not_advance" in str(exc):
                escape = pager.dense_second_escape(rows)
                dense_seconds.append(
                    {"page": page_index, "second": escape, "second_ict": ict(escape), "rows_at_second": len(rows)}
                )
                transitions[-1]["dense_second_escape"] = escape
                if escape in seen_cursors or (previous_cursor is not None and escape >= previous_cursor):
                    stop_reason = "cursor_repeated"
                    transitions[-1]["cursor_failure"] = str(exc)
                    break
                seen_cursors.append(escape)
                previous_cursor, cursor = escape, escape
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
            stop_reason = "cursor_repeated" if "repeated" in str(exc) else "cursor_did_not_advance"
            transitions[-1]["cursor_failure"] = str(exc)
            break

        seen_cursors.append(candidate)
        previous_cursor, cursor = candidate, candidate
        if requests_made % 10 == 0:
            print(f"  [page {page_index}] cursor {ict(candidate)} rows so far {len(all_rows)}")
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"[stop] {stop_reason} after {requests_made} requests, {len(all_rows)} raw rows")
    return {
        "budget": budget,
        "requests_made": requests_made,
        "stop_reason": stop_reason,
        "session_start_confirmed": session_start_confirmed,
        "dense_seconds_escaped": dense_seconds,
        "transitions": transitions,
        "rows": all_rows,
    }


def load_pages_offline() -> dict:
    """Rebuild the run from retained page artifacts. No network."""
    manifest_path = EVIDENCE_DIR / "pagination_run.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for transition in manifest["transitions"]:
        matches = sorted(PAGES_DIR.glob(f"page_{transition['page']:04d}_*.raw.json"))
        if not matches:
            raise pager.PaginationError(f"page_artifact_missing:{transition['page']}")
        body = matches[0].read_bytes()
        if pager.page_hash(body) != transition["page_sha256"]:
            raise pager.PaginationError(f"page_artifact_hash_drift:{transition['page']}")
        parsed = json.loads(body.decode("utf-8"))
        if parsed:
            rows.extend(pilot.parse_intraday_payload(parsed, symbol=TICKER))
    manifest["rows"] = rows
    return manifest


def fetch_daily_volume(session) -> dict:
    """One daily bar for the same in-progress session, for the reconciliation target."""
    payload = pilot.daily_payload(TICKER, to_epoch=1785888000, count_back=2)
    transport = pilot.acquire(
        endpoint=pilot.DAILY_ENDPOINT, payload=payload, session=session, headers=HEADERS
    )
    body = transport["raw_body"]
    digest = pilot.response_sha256(body)
    _write(EVIDENCE_DIR / f"daily_bar_{transport['retrieved_at'].replace(':','').replace('-','')}_{digest[:16]}.raw.json", body)
    parsed = json.loads(body.decode("utf-8"))
    normalized = pilot.normalize_daily(pilot.parse_daily_payload(parsed, symbol=TICKER))
    latest = normalized["rows"][-1]
    return {
        "session_date": latest["vci.session_date"],
        "daily_volume": latest["vci.observed_daily_volume"],
        "raw_response_sha256": digest,
        "retrieved_at": transport["retrieved_at"],
        "http_status": transport["http_status"],
        "redirect_count": transport["redirect_count"],
        "retry_count": transport["retry_count"],
    }


def analyse(run: dict, daily: dict) -> dict:
    deduped = pager.dedupe(run["rows"])
    reconciliation = pager.reconcile_session(
        rows=deduped["rows"],
        daily_volume=daily.get("daily_volume"),
        stop_reason=run["stop_reason"],
        session_start_confirmed=run["session_start_confirmed"],
        # Stated by the operator, never inferred: this segment ends at the lunch halt, so
        # the afternoon session is not in it.
        covers_full_trading_day=False,
    )
    contract = pager.assert_market_scope_not_upgraded(
        pager.volume_contract(
            reconciliation=reconciliation,
            unit_qualified=reconciliation.get("value_identity_pairs_checked", 0) > 0
            and reconciliation["value_identity_pairs_matching"] == reconciliation["value_identity_pairs_checked"],
            field_identity_qualified=True,
        )
    )
    return {
        "schema_version": pager.VERSION,
        "provider": pilot.PROVIDER,
        "source_authority": pilot.SOURCE_AUTHORITY,
        "ticker": TICKER,
        "session_date": SESSION_DATE,
        "segment": SEGMENT,
        "start_cursor": START_CURSOR,
        "start_cursor_ict": ict(START_CURSOR),
        "request_budget": run["budget"],
        "requests_made": run["requests_made"],
        "stop_reason": run["stop_reason"],
        "pages": len(run["transitions"]),
        "cursor_transitions": run["transitions"],
        "deduplication": {k: v for k, v in deduped.items() if k != "rows"},
        "dense_seconds_escaped": run.get("dense_seconds_escaped", []),
        "daily_bar": daily,
        "reconciliation": reconciliation,
        "volume_contract": contract,
        "endpoint_history_reach": {
            "prior_session_cursor_probe": 1785743100,
            "prior_session_cursor_probe_ict": ict(1785743100),
            "rows_returned": 0,
            "conclusion": (
                "The tape serves only the current session. A completed prior session is "
                "not reachable through this endpoint, which is why this pilot bounds a "
                "segment of the current session instead of a whole prior trading day."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--execute", action="store_true", help="run the live pagination once")
    group.add_argument("--offline", action="store_true", help="re-analyse retained pages only")
    args = parser.parse_args()

    if args.execute:
        session = requests.Session()
        run = paginate(session)
        _write(EVIDENCE_DIR / "pagination_run.json", {k: v for k, v in run.items() if k != "rows"})
        daily = fetch_daily_volume(session)
        _write(EVIDENCE_DIR / "daily_bar.json", daily)
    else:
        run = load_pages_offline()
        if not run:
            print("[offline] no retained run")
            return 1
        daily = json.loads((EVIDENCE_DIR / "daily_bar.json").read_text(encoding="utf-8"))

    summary = analyse(run, daily)
    _write(EVIDENCE_DIR / "pagination_summary.json", summary)
    print(pager.canonical_json({k: summary[k] for k in ("requests_made", "pages", "stop_reason", "deduplication", "reconciliation", "volume_contract")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
