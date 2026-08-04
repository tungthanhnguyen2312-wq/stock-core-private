"""Run the bounded KBS empirical price/volume basis qualification and write its evidence.

Live acquisition only, six requests at most, three tickers, small windows. Nothing here is
imported by the test suite. It reads production databases through SQLite ``mode=ro`` URIs
and writes exclusively under ``operations-review/kbs-empirical-basis-<date>/``.

    python tools/run_kbs_empirical_basis.py            # acquire + analyse
    python tools/run_kbs_empirical_basis.py --offline  # re-analyse retained artifacts only
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import evidence_qualification_tiers as tiers  # noqa: E402
import kbs_capability_matrix as caps  # noqa: E402
import kbs_empirical_basis as kbs  # noqa: E402
import kbs_mutability_protocol as protocol  # noqa: E402
import vci_volume_composition as vci_comp  # noqa: E402

EVIDENCE_DIR = ROOT / "operations-review" / "kbs-empirical-basis-20260804"
RAW_DIR = EVIDENCE_DIR / "raw"

CURRENT_DB = Path("C:/Projects/StockLookup/dashboard-runtime/vn_stock.db")
RETAINED_KBS_SAMPLE = ROOT / "operations-review" / "kbs_ohlcv_sample_hpg.json"
RETAINED_KBS_SAMPLE_RETRIEVED_AT = "2026-08-01T01:11:52Z"

# Browser-shaped headers matching the provider's own web trading application and the
# vnstock KBS adapter's own DEFAULT_HEADERS. No cookie, no authorization, no credential of
# any kind is sent or held.
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Every window is selected from evidence already retained in this repository. No corporate
# document was acquired and no event date was inferred from price behaviour.
WINDOWS = [
    {
        "id": "W1_share_event_HPG",
        "role": "share_related_event",
        "ticker": "HPG",
        "start": "2026-05-18",
        "end": "2026-06-02",
        "events": [
            {
                "kind": kbs.EVENT_KIND_SHARE,
                "ex_date": "2026-05-25",
                "detail": "ISS share issue, stock dividend ratio 10.0%, exercise_ratio 0.1",
                "evidence_identity": (
                    "dashboard-runtime/vn_stock.db:corporate_event_records"
                    "[record_id=31135d0d92c49322d66f26813bf4161505ce100e71d94057be4891b8467d7775,"
                    "provider=VCI,ticker=HPG,event_code=ISS,exright_date=2026-05-25]"
                ),
            }
        ],
    },
    {
        "id": "W2_cash_dividend_VCB",
        "role": "cash_distribution",
        "ticker": "VCB",
        "start": "2026-07-16",
        "end": "2026-07-30",
        "events": [
            {
                "kind": kbs.EVENT_KIND_CASH,
                "ex_date": "2026-07-23",
                "detail": "DIV cash dividend, 450 VND/share",
                "evidence_identity": (
                    "dashboard-runtime/vn_stock.db:corporate_event_records"
                    "[record_id=11ff5ae3e7ebbb8a0aca4d0240a33165b117ddafb1cee6d977d5a9c76cd2e534,"
                    "provider=VCI,ticker=VCB,event_code=DIV,exright_date=2026-07-23]"
                ),
            }
        ],
    },
    {
        "id": "W3_cash_dividend_VNM",
        "role": "cash_distribution",
        "ticker": "VNM",
        "start": "2026-06-19",
        "end": "2026-07-03",
        "events": [
            {
                "kind": kbs.EVENT_KIND_CASH,
                "ex_date": "2026-06-26",
                "detail": "DIV cash dividend, 1,850 VND/share",
                "evidence_identity": (
                    "dashboard-runtime/vn_stock.db:corporate_event_records"
                    "[record_id=618ede7b5a5cf7c3ebbce05828da2c3543ad1ff9b0c02f2c5c67ddda07bf6a3a,"
                    "provider=VCI,ticker=VNM,event_code=DIV,exright_date=2026-06-26]"
                ),
            }
        ],
    },
    {
        "id": "W4_control_HPG_reobservation",
        "role": "no_event_control",
        "ticker": "HPG",
        "start": "2026-07-20",
        "end": "2026-07-30",
        "events": [],
        "note": (
            "Reproduces the exact window of operations-review/kbs_ohlcv_sample_hpg.json so "
            "the same sessions can be compared across two retrieval instants. "
            "corporate_event_records holds no HPG ex-right date inside it."
        ),
    },
    {
        "id": "W5_control_VNM",
        "role": "no_event_control",
        "ticker": "VNM",
        "start": "2026-07-20",
        "end": "2026-07-31",
        "events": [],
        "note": "corporate_event_records holds no VNM ex-right date inside this window.",
    },
    {
        "id": "W6_VCI_rewrite_sessions_VCB",
        "role": "cross_provider_divergence",
        "ticker": "VCB",
        "start": "2026-07-01",
        "end": "2026-07-17",
        "events": [],
        "note": (
            "The exact 13 sessions the VCI pilot demonstrated were retrospectively "
            "rewritten after the 2026-07-23 ex-date. Requested from KBS to see whether the "
            "two providers diverge on dates one of them is known to have restated."
        ),
    },
]

REQUEST_DELAY_SECONDS = 1.2


# ---------------------------------------------------------------------------------
# Acquisition
# ---------------------------------------------------------------------------------


def acquire_all() -> list[dict[str, Any]]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    issued = 0
    observations: list[dict] = []
    failures: dict[str, str] = {}

    for window in WINDOWS:
        if issued >= kbs.REQUEST_BUDGET:
            failures[window["id"]] = "request_budget_exhausted"
            continue
        issued += 1
        try:
            result = kbs.acquire(
                symbol=window["ticker"],
                start=window["start"],
                end=window["end"],
                session=session,
                headers=HEADERS,
            )
        except Exception as exc:  # noqa: BLE001 -- recorded, not swallowed
            failures[window["id"]] = f"{type(exc).__name__}:{exc}"
            continue

        body = result["raw_body"]
        digest = kbs.response_sha256(body)
        name = kbs.artifact_name(
            window["ticker"], retrieved_at=result["retrieved_at"], body_sha256=digest
        )
        (RAW_DIR / name).write_bytes(body)

        try:
            payload = json.loads(body.decode("utf-8"))
            rows = kbs.parse_daily_payload(payload, symbol=window["ticker"])
        except Exception as exc:  # noqa: BLE001
            failures[window["id"]] = kbs.classify_failure(
                exception=exc, status=result["http_status"], body=body
            )
            continue

        normalized = kbs.normalize_daily(rows)
        observations.append(
            {
                **kbs.build_observation(
                    provider=kbs.PROVIDER,
                    source_authority=kbs.SOURCE_AUTHORITY,
                    endpoint=result["url"],
                    method="GET",
                    request_parameters=result["request_parameters"],
                    request_headers_redacted=HEADERS,
                    retrieved_at=result["retrieved_at"],
                    http_status=result["http_status"],
                    redirect_count=result["redirect_count"],
                    retry_count=result["retry_count"],
                    raw_response_sha256=digest,
                    response_schema_fingerprint=kbs.schema_fingerprint(payload),
                    ticker=window["ticker"],
                    interval="1D",
                    requested_date_range=[window["start"], window["end"]],
                    returned_date_range=normalized["returned_date_range"],
                    raw_field_names=sorted(kbs.RAW_FIELD_IDENTITY),
                    normalized_field_names=sorted(normalized["rows"][0]),
                    transformations=normalized["transformations"],
                    transformation_code_identity=normalized["transformation_code_identity"],
                    window_role=window["role"],
                    unresolved_semantic_dimensions=list(kbs.MARKET_SCOPE_DIMENSIONS),
                ),
                "artifact": f"raw/{name}",
                "window_id": window["id"],
            }
        )
        time.sleep(REQUEST_DELAY_SECONDS)

    (EVIDENCE_DIR / "observations.json").write_text(
        json.dumps({"observations": observations, "failures": failures, "requests_issued": issued},
                   indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest = kbs.evidence_manifest(observations)
    (EVIDENCE_DIR / "evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"acquired {len(observations)} windows in {issued} requests; failures={failures}")
    return observations


# ---------------------------------------------------------------------------------
# Offline analysis
# ---------------------------------------------------------------------------------


def load_observations() -> tuple[list[dict], dict]:
    payload = json.loads((EVIDENCE_DIR / "observations.json").read_text(encoding="utf-8"))
    return payload["observations"], payload


def rows_for(observation: dict) -> list[dict]:
    raw = (EVIDENCE_DIR / observation["artifact"]).read_bytes()
    if kbs.response_sha256(raw) != observation["raw_response_sha256"]:
        raise SystemExit(f"artifact hash mismatch: {observation['artifact']}")
    return kbs.parse_daily_payload(json.loads(raw.decode("utf-8")), symbol=observation["ticker"])


def vci_stored(ticker: str, start: str, end: str) -> dict[str, dict]:
    conn = sqlite3.connect(f"file:{CURRENT_DB.as_posix()}?mode=ro", uri=True)
    try:
        return {
            row[0]: {"close": row[1], "volume": row[2]}
            for row in conn.execute(
                "SELECT date, close, volume FROM ohlcv WHERE ticker=? AND source='VCI' "
                "AND date BETWEEN ? AND ? ORDER BY date",
                (ticker, start, end),
            )
        }
    finally:
        conn.close()


def retained_share_bounds(tickers: list[str]) -> dict[str, dict]:
    """Retained issued-share counts, used only as an order-of-magnitude falsifier.

    These figures are *not* qualified for valuation and this milestone does not qualify
    them. They are admissible here because the tie they break is a factor of one thousand:
    the argument is "no session trades six times a company's entire issued capital", and it
    survives the figure being wrong by any factor short of the one it rejects.
    """
    conn = sqlite3.connect(f"file:{CURRENT_DB.as_posix()}?mode=ro", uri=True)
    try:
        bounds = {}
        for ticker in tickers:
            row = conn.execute(
                "SELECT shares_outstanding, updated FROM metadata WHERE ticker=?", (ticker,)
            ).fetchone()
            if row and row[0]:
                bounds[ticker] = {
                    "shares_outstanding": float(row[0]),
                    "as_of": row[1],
                    "evidence_identity": (
                        f"dashboard-runtime/vn_stock.db:metadata[ticker={ticker}]"
                        f".shares_outstanding (updated {row[1]})"
                    ),
                    "qualification": tiers.OBSERVED_ONLY,
                    "admissible_because": "order_of_magnitude_falsifier_not_a_measurement",
                }
        return bounds
    finally:
        conn.close()


def analyse() -> dict:
    observations, envelope = load_observations()
    by_window = {observation["window_id"]: observation for observation in observations}
    windows_by_id = {window["id"]: window for window in WINDOWS}

    per_window: dict[str, dict] = {}
    normalized_by_ticker: dict[str, list[dict]] = {}

    for window_id, observation in by_window.items():
        window = windows_by_id[window_id]
        raw_rows = rows_for(observation)
        normalized = kbs.normalize_daily(raw_rows)
        rows = normalized["rows"]
        normalized_by_ticker.setdefault(window["ticker"], []).extend(rows)

        lattice = kbs.lattice_profile(rows)
        boundary = kbs.lattice_boundary(rows)
        dates = [row["kbs.session_date"] for row in rows]
        contains_event = any(
            dates and dates[0] <= str(event["ex_date"]) <= dates[-1] for event in window["events"]
        )
        verdict = kbs.classify_price_basis(
            lattice=lattice,
            boundary_date=boundary,
            qualified_events=window["events"],
            window_contains_event=contains_event,
        )
        entry = {
            "window_id": window_id,
            "role": window["role"],
            "ticker": window["ticker"],
            "requested_date_range": [window["start"], window["end"]],
            "returned_date_range": normalized["returned_date_range"],
            "sessions": len(rows),
            "events": window["events"],
            "window_contains_qualified_event": contains_event,
            "lattice": lattice,
            "boundary_date": boundary,
            "trading_value_presence": kbs.trading_value_presence_profile(rows),
            "price_verdict": verdict,
            "artifact": observation["artifact"],
            "raw_response_sha256": observation["raw_response_sha256"],
            "retrieved_at": observation["retrieved_at"],
        }
        # Cross-provider comparison: corroboration only, never an authority upgrade.
        stored = vci_stored(window["ticker"], window["start"], window["end"])
        compared = [
            {
                "session_date": row["kbs.session_date"],
                "kbs_close_vnd": row["kbs.observed_close_vnd"],
                "vci_stored_close_vnd": stored[row["kbs.session_date"]]["close"],
                "close_exact_match": float(row["kbs.observed_close_vnd"])
                == float(stored[row["kbs.session_date"]]["close"]),
                "kbs_volume": row["kbs.observed_daily_volume"],
                "vci_stored_volume": stored[row["kbs.session_date"]]["volume"],
                "volume_exact_match": row["kbs.observed_daily_volume"]
                == stored[row["kbs.session_date"]]["volume"],
            }
            for row in rows
            if row["kbs.session_date"] in stored
        ]
        entry["vci_stored_comparison"] = {
            "counterparty": "VCI (locally stored rows, read-only; no VCI request issued)",
            "sessions_compared": len(compared),
            "close_exact_matches": sum(1 for item in compared if item["close_exact_match"]),
            "volume_exact_matches": sum(1 for item in compared if item["volume_exact_match"]),
            "detail": compared,
            "authority_effect": "none; agreement between two undocumented providers is "
            "compatibility, not semantics",
        }
        per_window[window_id] = entry

    # --- historical mutability, from the retained 2026-08-01 KBS artifact ---------
    rewrite = None
    control = by_window.get("W4_control_HPG_reobservation")
    if control is not None and RETAINED_KBS_SAMPLE.exists():
        prior_payload = json.loads(RETAINED_KBS_SAMPLE.read_text(encoding="utf-8"))
        prior_rows = kbs.normalize_daily(
            kbs.parse_daily_payload(prior_payload, symbol="HPG")
        )["rows"]
        current_rows = kbs.normalize_daily(rows_for(control))["rows"]
        # Every qualified HPG ex-right date in 2026 precedes both observations, so this pair
        # is `both_post_event` by construction and the event-time question is not testable
        # from it. Declaring the dates is what makes that explicit instead of implied.
        rewrite = kbs.historical_rewrite_test(
            prior_rows=prior_rows,
            current_rows=current_rows,
            prior_observed_at=RETAINED_KBS_SAMPLE_RETRIEVED_AT,
            current_observed_at=control["retrieved_at"],
            prior_artifact="operations-review/kbs_ohlcv_sample_hpg.json",
            event_ex_dates=["2026-05-11", "2026-05-25"],
        )
        rewrite["spans_qualified_share_event"] = False
        rewrite["note"] = (
            "Both snapshots post-date every qualified HPG ex-right date, so this pair "
            "measures post-event stability only. Re-requesting later cannot change that: "
            "the pre-event observation the question needs no longer exists to be taken."
        )

    # --- price restated, volume not: the two fields move on different schedules ----
    divergence = None
    probe = by_window.get("W6_VCI_rewrite_sessions_VCB")
    if probe is not None:
        probe_rows = kbs.normalize_daily(rows_for(probe))["rows"]
        stored = vci_stored("VCB", "2026-07-01", "2026-07-17")
        divergence = kbs.price_volume_restatement_divergence(
            rows=probe_rows,
            reference_volumes={date: item["volume"] for date, item in stored.items()},
            reference_identity=(
                "dashboard-runtime/vn_stock.db:ohlcv[ticker=VCB,source=VCI,"
                "2026-07-01..2026-07-17] -- rows written by daily runs before the "
                "2026-07-23 ex-date; the pipeline appends and does not rewrite history"
            ),
        )

    # --- unit scaling ------------------------------------------------------------
    share_bounds = retained_share_bounds(sorted(normalized_by_ticker))
    # The primary absolute anchor uses no share count at all: KBS returns integers exactly
    # equal to a locally stored VCI series whose unit was established from VCI's own
    # per-trade tape. Equality is impossible under a thousand-fold unit difference.
    identity = kbs.unit_identity_anchor(
        per_ticker_rows=normalized_by_ticker,
        reference_volumes={
            ticker: {
                date: item["volume"]
                for date, item in vci_stored(ticker, "2026-01-01", "2026-12-31").items()
            }
            for ticker in sorted(normalized_by_ticker)
        },
        reference_identity=(
            "dashboard-runtime/vn_stock.db:ohlcv[source=VCI] volumes; unit established by "
            "vci_volume_composition.active_contract().volume_unit from per-trade "
            "accumulator reconciliation (commit 63ecc48), read-only, no VCI request issued"
        ),
        reference_unit=vci_comp.active_contract()["volume_unit"],
        reference_unit_qualification=tiers.EMPIRICALLY_DEDUCED,
    )
    units = kbs.select_unit_scales(
        normalized_by_ticker, share_count_bounds=share_bounds, identity_anchor=identity
    )
    units["share_count_bounds_used"] = share_bounds
    units["identity_anchor"] = identity
    kbs.assert_unit_does_not_qualify_scope(units)

    merged = kbs.merge_price_verdicts(
        {window_id: entry["price_verdict"] for window_id, entry in per_window.items()}
    )
    mutability = kbs.contract_historical_mutability(rewrite)

    volume_adjustment = kbs.volume_adjustment_verdict(
        rewrite_test=rewrite,
        share_event_window_tested=bool(rewrite and rewrite.get("spans_qualified_share_event")),
        price_basis_verdict=merged["verdict"],
    )
    scope = kbs.market_scope_contract()

    tested_windows = [
        f"{entry['ticker']}:{entry['returned_date_range'][0]}..{entry['returned_date_range'][1]}"
        for entry in per_window.values()
    ]
    empirical_record = {
        "test_method": (
            "HOSE tick-lattice conformance of the provider's own o/h/l/c across qualified "
            "ex-right boundaries, plus an as-of re-observation of an already-retained "
            "window, plus a bounded (v, va) unit-scale elimination."
        ),
        "tested_fields": ["kbs.raw_o", "kbs.raw_h", "kbs.raw_l", "kbs.raw_c", "kbs.raw_v", "kbs.raw_va"],
        "tested_tickers": sorted({entry["ticker"] for entry in per_window.values()}),
        "tested_date_windows": tested_windows,
        "event_evidence": [
            event for window in WINDOWS for event in window["events"]
        ],
        "raw_artifact_hashes": sorted(
            entry["raw_response_sha256"] for entry in per_window.values()
        ),
        "transformation_version": kbs.TRANSFORMATION_CODE_IDENTITY,
        "alternative_explanations_considered": [
            "The provider rounds an as-traded price and lands off the lattice by accident. "
            "Rejected: the off-lattice runs are contiguous and terminate exactly at a "
            "qualified ex-right date, and va is absent over exactly the same runs.",
            "The window's off-lattice prefix is caused by an unqualified event nobody "
            "recorded. Not excluded for any single window; weakened by three windows across "
            "three tickers each matching a separately recorded event of the expected kind.",
            "va is simply not retained for older sessions. Rejected: HPG 2026-07-20..30 "
            "carries va while VCB 2026-07-16..17 does not, so presence tracks the ex-right "
            "boundary and not the calendar.",
            "va includes a trading component the OHLC range does not represent.",
            "v and va have different market scopes, so their ratio is not a session VWAP.",
            "Cross-provider equality reflects a shared upstream vendor rather than "
            "independent agreement. Not excluded; the comparison is therefore recorded as "
            "corroboration with no authority effect.",
        ],
        "falsification_attempts": [
            "A no-event control window was requested for two tickers; a boundary appearing "
            "there would have falsified the event attribution.",
            "Every one of the sixteen candidate (v, va) scale pairs was scored, not just "
            "the expected one.",
            "The winning scale pair was re-scored per ticker independently.",
            "The retained 2026-08-01 HPG window was re-requested to look for a rewrite.",
            "va presence was profiled against lattice conformance across all six windows, "
            "which would have shown a calendar pattern had retention been the cause.",
        ],
        "confidence": "moderate",
        "scope_limitations": [
            "Three tickers, all HOSE, all 2026. Older history and other exchanges untested.",
            "No first-party methodology exists, so which events the provider adjusts for "
            "-- and which it silently does not -- is unknown.",
            "The rewrite comparison spans no qualified share event.",
        ],
        "retrieval_timestamps": sorted({entry["retrieved_at"] for entry in per_window.values()}),
        "historical_mutability": mutability,
    }

    contract = kbs.price_basis_contract(
        merged=merged,
        historical_mutability=mutability,
        tested_windows=tested_windows,
        empirical_record=empirical_record,
    )
    contract = kbs.apply_cross_provider_agreement(
        contract,
        agreement={
            "counterparty": "VCI",
            "basis": "locally stored rows, read-only; no VCI request issued",
            "windows": {
                window_id: entry["vci_stored_comparison"]["close_exact_matches"]
                for window_id, entry in per_window.items()
            },
        },
    )
    kbs.assert_contract_fail_closed(contract)

    summary = {
        "schema_version": kbs.VERSION,
        "provider": kbs.PROVIDER,
        "source_authority": kbs.SOURCE_AUTHORITY,
        "documented_semantics": "absent",
        "starting_contract": kbs.STARTING_CONTRACT,
        "requests_issued": envelope.get("requests_issued"),
        "request_budget": kbs.REQUEST_BUDGET,
        "failures": envelope.get("failures", {}),
        "windows": per_window,
        "merged_price_verdict": merged,
        "historical_rewrite_test": rewrite,
        "mutability_questions": {
            "event_time_rewriting": (rewrite or {}).get("event_time_rewriting", "not_observed"),
            "post_event_snapshot_stability": (rewrite or {}).get(
                "post_event_snapshot_stability", "not_observed"
            ),
            "volume_adjustment_basis": volume_adjustment["verdict"],
            "why_event_time_is_not_testable_here": (
                "Every retained KBS payload post-dates every qualified ex-right date in its "
                "window. A pre/post pair cannot be reconstructed after the fact, and a "
                "further request would be another post-event snapshot."
            ),
        },
        "prospective_protocol": protocol.assert_protocol_inert(),
        "prospective_protocol_fingerprint": protocol.protocol_fingerprint(),
        "price_volume_restatement_divergence": divergence,
        "price_basis_contract": contract,
        "unit_scaling": units,
        "volume_adjustment": volume_adjustment,
        "market_scope": scope,
        "qualification_ladder": list(tiers.TIERS),
    }
    (EVIDENCE_DIR / "basis_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (EVIDENCE_DIR / "capability_matrix.json").write_text(
        json.dumps(caps.assert_matrix_fail_closed(), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(json.dumps({
        "merged_price_verdict": merged,
        "historical_mutability": mutability,
        "event_time_rewriting": (rewrite or {}).get("event_time_rewriting"),
        "post_event_snapshot_stability": (rewrite or {}).get("post_event_snapshot_stability"),
        "snapshot_pair_class": ((rewrite or {}).get("snapshot_pair") or {}).get("pair_class"),
        "volume_unit": units["volume_unit"],
        "trading_value_unit": units["trading_value_unit"],
        "absolute_scale": units.get("absolute_scale"),
        "absolute_scale_anchor": units.get("absolute_scale_anchor"),
        "unit_qualification": units["qualification"],
        "rows_evaluated": units["rows_evaluated"],
        "volume_adjustment": volume_adjustment["verdict"],
        "price_volume_restatement_divergence": (divergence or {}).get("verdict"),
        "raw_as_traded_eligible": contract["raw_as_traded_eligible"],
    }, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="re-analyse retained artifacts only")
    args = parser.parse_args()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    if not args.offline:
        acquire_all()
    analyse()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
