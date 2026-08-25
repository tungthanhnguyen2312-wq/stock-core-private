"""Full-market FHSC historical matched-value acquisition, retention, and reconciliation runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_official_market_universe import _identity as official_identity
from dnse_fhsc_volume_basis import parse_fhsc_trading_history
from fhsc_retained_live_reconciliation import FHSC_BASE_URL, TIER1_HEADER_NAME, load_finhay_api_key
from historical_matched_traded_value_authority import (
    reconcile_fhsc_anchor,
    summarize_complete_trade_session,
)
from historical_matched_trading_value_authority import (
    build_historical_matched_trading_value_authority,
    content_identity,
    reconcile_expected_session_grid,
    trailing_expected_sessions,
)
from market_wide_current_valuation_input_scaleout import official_research_universe_tickers

ARTIFACT_DIR = ROOT / "operations-review" / "fhsc-historical-matched-value-coverage-scaleout-v1"
RAW_DIR = ARTIFACT_DIR / "raw"
DEFAULT_OFFICIAL_UNIVERSE = (
    ROOT / "operations-review" / "current-official-market-universe-integration-v1-20260824"
    / "current_official_market_universe_artifact.json"
)
ORIGINAL_RAW_ROOT = WORKSPACE / "operations-review" / "dnse-market-wide-trades-multi-session-v1-20260812"
REPAIR_RAW_ROOT = WORKSPACE / "operations-review" / "dnse-trades-targeted-repair-live-v1-20260815"
FINAL_SESSION_MANIFEST = (
    ORIGINAL_RAW_ROOT / "session=2026-08-11" / "data" / "market_raw_lake" / "manifests"
    / "DNSE__trades_history__market-wide-trades-40sessions-ending-20260811-v1__20260811.json"
)
FROZEN_OUTPUTS = {
    (ROOT / "operations-review" / "market-wide-current-valuation-v1-20260824" / "market_wide_current_valuation_artifact.json").resolve(),
    (ROOT / "operations-review" / "market-wide-current-valuation-v1-20260824-session20260824" / "market_wide_current_valuation_artifact.json").resolve(),
}
FROZEN_IDENTITIES = {
    "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a",
    "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388",
}

START_DATE = "2026-06-17"
END_DATE = "2026-08-25"
STRUCTURALLY_ABSENT_TRADES_PAIRS = (
    ("POM", "2026-07-13"),
    ("VCI", "2026-07-13"),
    ("HPH", "2026-07-14"),
    ("SGR", "2026-07-14"),
    ("OCH", "2026-07-15"),
    ("CT3", "2026-07-16"),
    ("ONE", "2026-08-11"),
)
RETAINED_CONFLICT_TAXONOMY = {
    "conflict_rows": 5447,
    "by_cause": {
        "FHSC_MATCHED_EQUALS_G1_PLUS_G4_RAW_SHARES": 5258,
        "UNEXPLAINED_RESIDUAL": 184,
        "NO_G4_NO_PT_STILL_CONFLICT": 5,
    },
    "by_exchange": {
        "HOSE": 192,
        "HNX_LISTED": 2220,
        "UPCOM": 3035,
    },
    "volume_and_value_both_conflict": 5447,
    "formula_not_rewritten": True,
    "g4_not_coerced_into_matched_value": True,
}


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _trades_universe(manifest: Path) -> list[str]:
    payload = _load_json(manifest)
    suffix = "__20260811__ALL_BOARDS"
    tickers = sorted({
        unit[: -len(suffix)] for unit in payload["requested_units"]
        if isinstance(unit, str) and unit.endswith(suffix)
    })
    if len(tickers) != 1660:
        raise ValueError(f"unexpected_final_trades_universe_size:{len(tickers)}")
    return tickers


def _refuse_frozen(path: Path) -> None:
    if path.resolve() in FROZEN_OUTPUTS:
        raise ValueError("REFUSING_TO_OVERWRITE_FROZEN_VALUATION_ARTIFACT")


def index_dnse_trades_parquet(sessions: list[str]) -> dict[tuple[str, str], list[Path]]:
    """Fast index of DNSE Trades parquet files across sessions."""
    indexed: dict[tuple[str, str], list[Path]] = {}
    for s in sessions:
        rep_dir = REPAIR_RAW_ROOT / f"session={s}" / "data" / "market_raw_lake" / "raw" / "DNSE" / "trades_history"
        orig_dir = ORIGINAL_RAW_ROOT / f"session={s}" / "data" / "market_raw_lake" / "raw" / "DNSE" / "trades_history"
        rep_files: dict[str, list[Path]] = defaultdict(list)
        orig_files: dict[str, list[Path]] = defaultdict(list)

        if rep_dir.exists():
            for td in rep_dir.iterdir():
                if td.is_dir():
                    for pf in td.glob("*.parquet"):
                        ticker = pf.name.split("__")[0]
                        rep_files[ticker].append(pf)
        if orig_dir.exists():
            for td in orig_dir.iterdir():
                if td.is_dir():
                    for pf in td.glob("*.parquet"):
                        ticker = pf.name.split("__")[0]
                        orig_files[ticker].append(pf)

        all_tickers = set(rep_files.keys()) | set(orig_files.keys())
        for ticker in all_tickers:
            if rep_files.get(ticker):
                indexed[(s, ticker)] = sorted(rep_files[ticker])
            elif orig_files.get(ticker):
                indexed[(s, ticker)] = sorted(orig_files[ticker])
    return indexed


def load_fast_pages(paths: list[Path], *, ticker: str, session: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Fast page loader for complete session trade records."""
    pages: list[dict[str, Any]] = []
    hashes: list[str] = []
    for path in paths:
        table = pq.ParquetFile(path).read()
        for record in table.to_pylist():
            if record["provider"] != "DNSE" or record["dataset"] != "trades_history" or record["instrument"] != ticker:
                raise RuntimeError(f"unexpected_raw_page_identity:{path}")
            if record["source_event_time"] != session:
                raise RuntimeError(f"unexpected_raw_page_session:{path}")
            body = json.loads(record["raw_payload_json"])
            request = json.loads(record["request_identity"])
            provenance = json.loads(record["provenance_json"])
            pages.append({
                "page_index": int(request["page_index"]),
                "page_cursor": request.get("cursor"),
                "next_page_token": body.get("nextPageToken"),
                "trades": body.get("trades"),
                "source_page_identity": record["observation_id"],
                "request_identity": record["request_identity"],
                "provenance_page_index": int(provenance["page_index"]),
            })
            hashes.append(record["raw_payload_hash"])
    if not pages:
        raise RuntimeError(f"no_retained_pages:{ticker}:{session}")
    if any(page["page_index"] != page["provenance_page_index"] for page in pages):
        raise RuntimeError(f"page_index_lineage_mismatch:{ticker}:{session}")
    return pages, hashes


def fetch_fhsc_symbol(
    symbol: str,
    api_key: str,
    *,
    start: str = START_DATE,
    end: str = END_DATE,
    raw_dir: Path = RAW_DIR,
) -> dict[str, Any]:
    """Acquire FHSC trading history for one symbol with caching and backoff."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing_files = sorted(raw_dir.glob(f"{symbol}_stock_trading_history_*.json"))
    if existing_files:
        for ef in existing_files:
            try:
                body = ef.read_bytes()
                digest = hashlib.sha256(body).hexdigest()
                payload = json.loads(body.decode("utf-8"))
                if payload.get("data", {}).get("symbol") == symbol:
                    return {
                        "symbol": symbol,
                        "endpoint": f"/market/stocks/{symbol}/trading/history",
                        "request_parameters": {"from": start, "to": end, "resolution": "1D"},
                        "request_url": f"{FHSC_BASE_URL}/market/stocks/{symbol}/trading/history",
                        "retrieval_time": datetime.fromtimestamp(ef.stat().st_mtime, tz=UTC).isoformat(),
                        "http_status": 200,
                        "mime_type": "application/json",
                        "successful": True,
                        "raw_response_retained": True,
                        "raw_path": _rel(ef),
                        "raw_sha256": digest,
                        "source_cache_hit": True,
                    }
            except Exception:
                continue

    params = {"from": start, "to": end, "resolution": "1D"}
    path = f"/market/stocks/{symbol}/trading/history"
    url = f"{FHSC_BASE_URL}{path}?{urlencode(params)}"
    retrieval_time = datetime.now(UTC).isoformat()
    req = Request(url, method="GET", headers={TIER1_HEADER_NAME: api_key})

    max_retries = 3
    body = None
    status = None
    mime = None

    for attempt in range(max_retries):
        try:
            with urlopen(req, timeout=30) as response:
                body = response.read()
                status = int(response.status)
                mime = response.headers.get_content_type()
                break
        except HTTPError as error:
            status = int(error.code)
            if status == 429 and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 1.0
                time.sleep(wait_time)
                continue
            return {
                "symbol": symbol,
                "endpoint": path,
                "request_parameters": params,
                "request_url": url,
                "retrieval_time": retrieval_time,
                "http_status": status,
                "successful": False,
                "failure_disposition": f"HTTP_ERROR_{status}",
                "raw_response_retained": False,
            }
        except OSError as error:
            if attempt < max_retries - 1:
                time.sleep(1.0)
                continue
            return {
                "symbol": symbol,
                "endpoint": path,
                "request_parameters": params,
                "request_url": url,
                "retrieval_time": retrieval_time,
                "successful": False,
                "failure_disposition": f"NETWORK_ERROR_{type(error).__name__}",
                "raw_response_retained": False,
            }

    if body is None:
        return {
            "symbol": symbol,
            "endpoint": path,
            "request_parameters": params,
            "request_url": url,
            "retrieval_time": retrieval_time,
            "successful": False,
            "failure_disposition": "NO_BODY_RETURNED",
            "raw_response_retained": False,
        }

    digest = hashlib.sha256(body).hexdigest()
    raw_path = raw_dir / f"{symbol}_stock_trading_history_{digest[:16]}.json"
    raw_path.write_bytes(body)

    return {
        "symbol": symbol,
        "endpoint": path,
        "request_parameters": params,
        "request_url": url,
        "retrieval_time": retrieval_time,
        "http_status": status,
        "mime_type": mime,
        "successful": status == 200,
        "raw_response_retained": True,
        "raw_path": _rel(raw_path),
        "raw_sha256": digest,
        "source_cache_hit": False,
    }


def run_acquisition_and_reconciliation(
    *,
    out_dir: Path = ARTIFACT_DIR,
    official_universe_path: Path = DEFAULT_OFFICIAL_UNIVERSE,
) -> dict[str, Any]:
    """Execute complete full-market FHSC acquisition, retention, and reconciliation."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    official_doc = _load_json(official_universe_path)
    expected_official_id = official_identity(official_doc)
    if expected_official_id["artifact_sha256"] != official_doc.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:official_universe")

    tickers = official_research_universe_tickers(official_doc)
    if len(tickers) != 1507:
        raise ValueError(f"unexpected_official_universe_size:{len(tickers)}")

    api_key = load_finhay_api_key()
    if not api_key:
        raise RuntimeError("FINHAY_API_KEY_UNAVAILABLE")

    # Step 1: Sequential acquisition across the 1,507 official universe tickers
    manifest_records: list[dict[str, Any]] = []
    t_acq_start = time.time()

    for idx, sym in enumerate(tickers, start=1):
        rec = fetch_fhsc_symbol(sym, api_key, raw_dir=raw_dir)
        manifest_records.append(rec)
        if not rec.get("source_cache_hit"):
            time.sleep(0.06)

    t_acq_end = time.time()

    # Step 2: Parse raw FHSC observations
    fhsc_observations: dict[tuple[str, str], dict[str, Any]] = {}
    raw_parse_summary = Counter()

    for rec in manifest_records:
        if not rec.get("successful") or not rec.get("raw_path"):
            raw_parse_summary["UNSUCCESSFUL_REQUEST"] += 1
            continue
        raw_path = ROOT / rec["raw_path"]
        raw_bytes = raw_path.read_bytes()
        parsed = parse_fhsc_trading_history(raw_bytes, instrument=rec["symbol"])
        parse_status = parsed.get("parse_status")
        raw_parse_summary[parse_status] += 1
        if parse_status == "PARSED":
            for row in parsed.get("rows", []):
                if row.get("parse_status") == "PARSED" and row.get("session"):
                    fhsc_observations[(rec["symbol"], row["session"])] = row

    # Step 3: Index DNSE Trades corpus
    dnse_sessions = sorted([p.name.split("=")[1] for p in ORIGINAL_RAW_ROOT.glob("session=*")])
    indexed_parquet = index_dnse_trades_parquet(dnse_sessions)

    # Step 4: Reconcile against DNSE Trades corpus
    reconciliation_rows: list[dict[str, Any]] = []
    qualified_rows: list[dict[str, Any]] = []
    recon_status_counts = Counter()

    for (session, sym), paths in sorted(indexed_parquet.items()):
        if sym not in tickers:
            continue
        try:
            pages, hashes = load_fast_pages(paths, ticker=sym, session=session)
            candidate = summarize_complete_trade_session(
                ticker=sym, session=session, pages=pages, raw_payload_hashes=hashes,
            )
        except Exception as err:
            recon_status_counts["DNSE_PARSE_FAILURE"] += 1
            continue

        fhsc_row = fhsc_observations.get((sym, session))
        if not fhsc_row:
            recon_status_counts["UNAVAILABLE_NO_FHSC_OBSERVATION"] += 1
            continue

        anchor = {
            "ticker": sym,
            "session": session,
            "fhsc_identity_retained_exact": True,
            "fhsc_matched_volume": fhsc_row["matched_volume"],
            "fhsc_matched_value": fhsc_row["matched_value"],
        }
        recon = reconcile_fhsc_anchor(candidate, anchor)
        candidate["fhsc_reconciliation"] = recon

        if recon["status"] == "EXACT":
            candidate["qualification_status"] = "MATCHED_VALUE_QUALIFIED"
            qualified_rows.append(candidate)
            recon_status_counts["EXACT"] += 1
        elif recon["status"] == "CONFLICT":
            candidate["qualification_status"] = "CONFLICTING"
            recon_status_counts["CONFLICT"] += 1
        else:
            recon_status_counts[recon.get("status", "OTHER")] += 1

        reconciliation_rows.append({
            "ticker": sym,
            "session": session,
            "status": recon["status"],
            "g1_share_quantity": candidate.get("g1_share_quantity"),
            "dnse_matched_value_vnd": candidate.get("matched_value_vnd"),
            "fhsc_matched_volume": fhsc_row["matched_volume"],
            "fhsc_matched_value": fhsc_row["matched_value"],
            "fhsc_put_through_value": fhsc_row.get("put_through_value"),
            "fhsc_total_value": fhsc_row.get("total_value"),
            "g1_to_fhsc_matched_volume": recon.get("g1_to_fhsc_matched_volume"),
            "g1_to_fhsc_matched_value": recon.get("g1_to_fhsc_matched_value"),
        })

    # Step 5: Build authority artifact
    trades_universe = _trades_universe(FINAL_SESSION_MANIFEST)
    authority_artifact = build_historical_matched_trading_value_authority(
        official_universe=official_doc,
        qualified_rows=qualified_rows,
        trades_universe=trades_universe,
        expected_trading_sessions=dnse_sessions,
        reconciliation_rows=reconciliation_rows,
        session_grid=reconcile_expected_session_grid(
            official_ticker_count=len(tickers),
            trading_session_count=len(dnse_sessions),
            evaluated_pairs=sum(recon_status_counts.values()) - recon_status_counts.get("DNSE_PARSE_FAILURE", 0),
            exact=recon_status_counts.get("EXACT", 0),
            conflict=recon_status_counts.get("CONFLICT", 0),
            not_comparable=recon_status_counts.get("NOT_COMPARABLE", 0),
            unavailable=recon_status_counts.get("UNAVAILABLE_NO_FHSC_OBSERVATION", 0),
            structurally_absent=len(STRUCTURALLY_ABSENT_TRADES_PAIRS),
        ),
        source_identities={
            "official_universe": official_doc.get("artifact_identity"),
            "fhsc_openapi_capability": "fhsc:/market/stocks/{symbol}/trading/history",
            "dnse_trades_corpus": "DNSE:trades_history:40sessions",
        },
    )

    # Step 6: Write output artifacts
    manifest_path = out_dir / "fhsc_historical_matched_value_raw_manifest.json"
    manifest_payload = {
        "schema_version": "1.0.0",
        "contract_version": "fhsc_historical_matched_value_acquisition_manifest/v1",
        "universe_size": len(tickers),
        "successful_requests": sum(1 for r in manifest_records if r.get("successful")),
        "failed_requests": sum(1 for r in manifest_records if not r.get("successful")),
        "cached_requests": sum(1 for r in manifest_records if r.get("source_cache_hit")),
        "raw_observations_count": len(fhsc_observations),
        "acquisition_elapsed_seconds": round(t_acq_end - t_acq_start, 2),
        "records": manifest_records,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    recon_path = out_dir / "historical_matched_value_reconciliation_artifact.json"
    recon_payload = {
        "schema_version": "1.0.0",
        "contract_version": "historical_matched_value_reconciliation/v1",
        "summary": dict(sorted(recon_status_counts.items())),
        "total_reconciliation_pairs": len(reconciliation_rows),
        "rows": reconciliation_rows,
    }
    recon_path.write_text(json.dumps(recon_payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    qualified_path = out_dir / "historical_matched_value_qualified_rows.json"
    qualified_path.write_text(json.dumps(qualified_rows, indent=2, sort_keys=True, default=str), encoding="utf-8")

    authority_path = out_dir / "historical_matched_trading_value_authority_artifact.json"
    _refuse_frozen(authority_path)
    authority_path.write_text(json.dumps(authority_artifact, indent=2, sort_keys=True, default=str), encoding="utf-8")

    report_path = out_dir / "historical_matched_trading_value_authority_report.json"
    report_payload = {
        "artifact_identity": authority_artifact["artifact_identity"],
        "verdict": authority_artifact["verdict"],
        "universe_denominator": authority_artifact["coverage"]["universe_denominator"],
        "denominator_reconciles": authority_artifact["coverage"]["denominator_reconciles"],
        "unexplained_count": authority_artifact["coverage"]["unexplained_count"],
        "authority_tier_distribution": authority_artifact["coverage"]["authority_tier_distribution"],
        "reconciliation": authority_artifact["reconciliation"],
        "qualified_rows_count": len(qualified_rows),
        "adtv20_ready_count": authority_artifact["coverage"]["adtv20_ready_count"],
        "adv20_matched_volume_ready_count": authority_artifact["coverage"]["adv20_matched_volume_ready_count"],
        "qualified_observation_tickers": authority_artifact["coverage"]["qualified_observation_tickers"],
        "qualified_observation_sessions": authority_artifact["coverage"]["qualified_observation_sessions"],
        "frozen_identities_unchanged": sorted(FROZEN_IDENTITIES),
        "qualified_liquidity_inputs": authority_artifact["authority_boundary"]["qualified_liquidity_inputs"],
        "position_sizing_is_safe": authority_artifact["authority_boundary"]["position_sizing_is_safe"],
    }
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    return {
        "manifest": manifest_payload,
        "reconciliation_summary": dict(recon_status_counts),
        "authority": authority_artifact["coverage"],
        "verdict": authority_artifact["verdict"],
    }


def replay_retained_authority(
    *,
    out_dir: Path = ARTIFACT_DIR,
    official_universe_path: Path = DEFAULT_OFFICIAL_UNIVERSE,
) -> dict[str, Any]:
    """Rebuild authority from retained files. No network, no 429 retry, no raw rewrite."""
    official_doc = _load_json(official_universe_path)
    expected_official_id = official_identity(official_doc)
    if expected_official_id["artifact_sha256"] != official_doc.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:official_universe")
    tickers = official_research_universe_tickers(official_doc)
    if len(tickers) != 1507:
        raise ValueError(f"unexpected_official_universe_size:{len(tickers)}")
    dnse_sessions = sorted([p.name.split("=")[1] for p in ORIGINAL_RAW_ROOT.glob("session=*")])
    if len(dnse_sessions) != 40:
        raise ValueError(f"unexpected_dnse_session_count:{len(dnse_sessions)}")
    qualified_rows = _load_json(out_dir / "historical_matched_value_qualified_rows.json")
    recon_doc = _load_json(out_dir / "historical_matched_value_reconciliation_artifact.json")
    recon_summary = recon_doc.get("summary") or {}
    session_grid = reconcile_expected_session_grid(
        official_ticker_count=len(tickers),
        trading_session_count=len(dnse_sessions),
        evaluated_pairs=(
            recon_summary.get("EXACT", 0) + recon_summary.get("CONFLICT", 0)
            + recon_summary.get("NOT_COMPARABLE", 0) + recon_summary.get("UNAVAILABLE_NO_FHSC_OBSERVATION", 0)
        ),
        exact=recon_summary.get("EXACT", 0),
        conflict=recon_summary.get("CONFLICT", 0),
        not_comparable=recon_summary.get("NOT_COMPARABLE", 0),
        unavailable=recon_summary.get("UNAVAILABLE_NO_FHSC_OBSERVATION", 0),
        structurally_absent=len(STRUCTURALLY_ABSENT_TRADES_PAIRS),
    )
    authority_artifact = build_historical_matched_trading_value_authority(
        official_universe=official_doc,
        qualified_rows=qualified_rows,
        trades_universe=_trades_universe(FINAL_SESSION_MANIFEST),
        expected_trading_sessions=dnse_sessions,
        reconciliation_rows=recon_doc.get("rows") or [],
        session_grid=session_grid,
        source_identities={
            "official_universe": official_doc.get("artifact_identity"),
            "fhsc_openapi_capability": "fhsc:/market/stocks/{symbol}/trading/history",
            "dnse_trades_corpus": "DNSE:trades_history:40sessions",
        },
        trades_source_contract={
            "replay_retained_only": True,
            "http_429_not_retried": True,
            "expected_trading_sessions": dnse_sessions,
            "trailing_adtv20_window": trailing_expected_sessions(dnse_sessions),
        },
    )
    identity = content_identity(authority_artifact)
    if identity["artifact_sha256"] != authority_artifact["artifact_sha256"]:
        raise ValueError("ARTIFACT_SELF_VERIFICATION_FAILED")
    authority_path = out_dir / "historical_matched_trading_value_authority_artifact.json"
    _refuse_frozen(authority_path)
    authority_path.write_text(json.dumps(authority_artifact, indent=2, sort_keys=True, default=str), encoding="utf-8")
    report_payload = {
        "artifact_identity": authority_artifact["artifact_identity"],
        "verdict": authority_artifact["verdict"],
        "universe_denominator": authority_artifact["coverage"]["universe_denominator"],
        "denominator_reconciles": authority_artifact["coverage"]["denominator_reconciles"],
        "unexplained_count": authority_artifact["coverage"]["unexplained_count"],
        "authority_tier_distribution": authority_artifact["coverage"]["authority_tier_distribution"],
        "reconciliation": authority_artifact["reconciliation"],
        "session_grid": session_grid,
        "conflict_taxonomy": RETAINED_CONFLICT_TAXONOMY,
        "adtv20_contract": authority_artifact["adtv20_contract"],
        "qualified_rows_count": len(qualified_rows),
        "adtv20_ready_count": authority_artifact["coverage"]["adtv20_ready_count"],
        "adtv20_partial_count": authority_artifact["coverage"]["adtv20_partial_count"],
        "adtv20_blocked_count": authority_artifact["coverage"]["adtv20_blocked_count"],
        "adtv20_not_applicable_count": authority_artifact["coverage"]["adtv20_not_applicable_count"],
        "prior_claimed_adtv20_ready_count": 295,
        "adv20_matched_volume_ready_count": authority_artifact["coverage"]["adv20_matched_volume_ready_count"],
        "qualified_observation_tickers": authority_artifact["coverage"]["qualified_observation_tickers"],
        "qualified_observation_sessions": authority_artifact["coverage"]["qualified_observation_sessions"],
        "restricted_scope_tickers": authority_artifact["coverage"]["restricted_scope_tickers"],
        "non_discriminating_exact_tickers": authority_artifact["coverage"]["non_discriminating_exact_tickers"],
        "qualified_observation_tickers_by_exchange": authority_artifact["coverage"]["qualified_observation_tickers_by_exchange"],
        "frozen_identities_unchanged": sorted(FROZEN_IDENTITIES),
        "qualified_liquidity_inputs": authority_artifact["authority_boundary"]["qualified_liquidity_inputs"],
        "position_sizing_is_safe": authority_artifact["authority_boundary"]["position_sizing_is_safe"],
    }
    (out_dir / "historical_matched_trading_value_authority_report.json").write_text(
        json.dumps(report_payload, indent=2, sort_keys=True, default=str), encoding="utf-8",
    )
    (out_dir / "adtv20_window_integrity_report.json").write_text(
        json.dumps({
            "contract_version": "adtv20_window_integrity/v1",
            "session_grid": session_grid,
            "conflict_taxonomy": RETAINED_CONFLICT_TAXONOMY,
            "adtv20": authority_artifact["adtv20_contract"],
            "coverage": authority_artifact["coverage"],
            "authority_boundary": authority_artifact["authority_boundary"],
            "prior_claimed_adtv20_ready_count": 295,
            "true_adtv20_ready_count": authority_artifact["coverage"]["adtv20_ready_count"],
            "structurally_absent_trades_pairs": [
                {"ticker": ticker, "session": session} for ticker, session in STRUCTURALLY_ABSENT_TRADES_PAIRS
            ],
        }, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return {
        "artifact_identity": authority_artifact["artifact_identity"],
        "verdict": authority_artifact["verdict"],
        "coverage": authority_artifact["coverage"],
        "session_grid": session_grid,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--official-universe", type=Path, default=DEFAULT_OFFICIAL_UNIVERSE)
    parser.add_argument(
        "--replay-retained",
        action="store_true",
        help="Rebuild authority from retained files only. No FHSC acquisition or 429 retry.",
    )
    args = parser.parse_args(argv)

    if args.replay_retained:
        summary = replay_retained_authority(
            out_dir=args.out_dir,
            official_universe_path=args.official_universe,
        )
    else:
        summary = run_acquisition_and_reconciliation(
            out_dir=args.out_dir,
            official_universe_path=args.official_universe,
        )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
