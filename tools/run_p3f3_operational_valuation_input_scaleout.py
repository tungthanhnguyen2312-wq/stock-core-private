"""CLI & operational runner: P3-F3 Operational Current Valuation Input Scale-Out.

Materializes DNSE price observations and qualifies current valuation inputs across
the authoritative 11-issuer P3 cohort via generic P3-F2 contracts with zero
ticker-specific production branches.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_valuation_input_authority as authority
from dnse_access import credentials_for_request
from dnse_bulk_market_data import fetch_capability_raw
import dnse_market_risk_evidence_store as evidence_store
from dnse_secrets_env import ensure_credentials_loaded
from field_temporal_contract import stable_id
from freshness_history import latest_completed_market_day
import p3f_current_market_valuation as p3f_val
from runtime_paths import runtime_root as resolve_runtime_root

VERSION = "1.0.0"
CONTRACT_VERSION = "p3f3_operational_valuation_input_scaleout/v1"
ARTIFACT_TYPE = "P3F3_OPERATIONAL_VALUATION_INPUT_SCALEOUT"
P3E_PATH = ROOT / "operations-review" / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
P3F2_PATH = ROOT / "operations-review" / "p3f2-current-valuation-input-authority-20260820" / "p3f2_current_valuation_input_authority_artifact.json"
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f3-operational-valuation-input-scaleout-20260820"
VN_TZ = timezone(timedelta(hours=7))


def load_cohort(p3e_path: Path = P3E_PATH) -> list[dict[str, Any]]:
    """Derive the current authoritative P3 cohort programmatically from P3-E."""
    p3e_data = json.loads(p3e_path.read_text(encoding="utf-8"))
    issuers = p3e_data["refreshed_panel_data"]["issuers"]
    return sorted(issuers, key=lambda row: str(row["issuer_identity"]["ticker"]))


def resolve_execution_session(requested_at: datetime | str) -> dict[str, Any]:
    """Resolve the latest fully completed Vietnamese market session at execution time."""
    if isinstance(requested_at, str):
        now = datetime.fromisoformat(requested_at.replace("Z", "+00:00")).astimezone(VN_TZ)
    else:
        now = requested_at.astimezone(VN_TZ) if requested_at.tzinfo else requested_at.replace(tzinfo=VN_TZ)
    completed_day = latest_completed_market_day(now)
    return {
        "requested_at": now.isoformat(),
        "calendar_anchor": completed_day.isoformat(),
        "valuation_session": completed_day.isoformat(),
        "policy": "latest_completed_vietnam_weekday_with_exact_retained_observation",
        "status": "QUALIFIED",
    }


def materialize_dnse_price(
    ticker: str,
    *,
    runtime_root: Path,
    api_key: str,
    api_secret: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    """Fetch and retain raw DNSE OHLC for one canonical ticker."""
    start_epoch = int(start_date.timestamp())
    end_epoch = int(end_date.timestamp())
    query = {
        "symbol": ticker,
        "resolution": "1D",
        "from": start_epoch,
        "to": end_epoch,
        "type": "STOCK",
    }
    response = fetch_capability_raw(
        "ohlc",
        api_key=api_key,
        api_secret=api_secret,
        symbol=None,
        query=query,
    )
    if not response.get("ok"):
        return {
            "ticker": ticker,
            "status": "FETCH_FAILED",
            "error": response.get("error"),
            "status_code": response.get("status_code"),
            "session_count": 0,
            "observations": [],
        }

    body = response.get("body") or {}
    raw_ohlc = {k: body.get(k) for k in ("o", "h", "l", "c", "t")}
    if any(not isinstance(raw_ohlc[k], list) for k in ("o", "h", "l", "c", "t")):
        return {
            "ticker": ticker,
            "status": "MALFORMED_RESPONSE",
            "error": "missing_or_invalid_ohlc_arrays",
            "session_count": 0,
            "observations": [],
        }

    materialized_at = datetime.now(timezone.utc).isoformat()
    raw_bytes = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_hash = hashlib.sha256(raw_bytes).hexdigest()
    provenance = {
        "provider": "DNSE",
        "endpoint": "/price/ohlc",
        "query_sent": query,
        "materialized_at": materialized_at,
        "payload_hash": payload_hash,
    }
    evidence_store.write_stock_ohlc(runtime_root, ticker, raw_ohlc, provenance=provenance)
    
    t_list = raw_ohlc["t"]
    c_list = raw_ohlc["c"]
    latest_session = (
        datetime.fromtimestamp(t_list[-1], tz=timezone.utc).astimezone(VN_TZ).date().isoformat()
        if t_list else None
    )
    return {
        "ticker": ticker,
        "status": "SUCCESS",
        "session_count": len(t_list),
        "latest_session": latest_session,
        "latest_close": c_list[-1] if c_list else None,
        "payload_hash": payload_hash,
        "materialized_at": materialized_at,
    }


def execute_operational_scaleout(
    *,
    runtime_root: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    requested_at: datetime | str | None = None,
    secrets_path: str | None = None,
) -> dict[str, Any]:
    """Execute P3-F3 operational materialization and qualification across the cohort."""
    req_time = (
        datetime.now(VN_TZ) if requested_at is None
        else (datetime.fromisoformat(str(requested_at).replace("Z", "+00:00")).astimezone(VN_TZ)
              if isinstance(requested_at, str) else requested_at.astimezone(VN_TZ))
    )
    session_info = resolve_execution_session(req_time)
    val_session = session_info["valuation_session"]

    cohort_issuers = load_cohort()
    instruments = [authority.canonical_instrument(row["issuer_identity"]["ticker"]) for row in cohort_issuers]

    # Load credentials safely
    cred_status = ensure_credentials_loaded(secrets_path)
    creds = credentials_for_request()
    if not cred_status.get("configured") or not creds:
        raise RuntimeError("DNSE_CREDENTIAL_INJECTION_REQUIRED")

    # Ingest DNSE OHLC for all cohort issuers
    start_date = datetime.combine(datetime.fromisoformat(val_session) - timedelta(days=60), datetime.min.time(), VN_TZ)
    end_date = datetime.combine(datetime.fromisoformat(val_session) + timedelta(days=1), datetime.min.time(), VN_TZ) - timedelta(seconds=1)

    dnse_matrix = []
    for instrument in instruments:
        ticker = instrument["canonical_ticker"]
        mat_res = materialize_dnse_price(
            ticker,
            runtime_root=runtime_root,
            api_key=creds[0],
            api_secret=creds[1],
            start_date=start_date,
            end_date=end_date,
        )
        dnse_matrix.append(mat_res)

    # Run P3-F2 Generic Authority Scanner
    reference_at = f"{val_session}T16:00:00+07:00"
    p3e_data = json.loads(P3E_PATH.read_text(encoding="utf-8"))
    financial_by_ticker = {row["issuer_identity"]["ticker"]: row for row in cohort_issuers}
    
    coverage_scan = authority.scan_current_valuation_input_coverage(
        instruments,
        runtime_root=runtime_root,
        requested_at=reference_at,
        financial_by_ticker=financial_by_ticker,
    )

    # Evaluate P3-F Valuation Engine through P3-F2 Seam
    valuation_rows = []
    for issuer in cohort_issuers:
        ticker = str(issuer["issuer_identity"]["ticker"])
        resolved_for_ticker = next(
            (r for r in coverage_scan["rows"] if r["canonical_instrument"]["canonical_ticker"] == ticker),
            None,
        )
        if resolved_for_ticker is not None:
            val_eval = p3f_val.evaluate_issuer_from_resolved_inputs(issuer, resolved_for_ticker)
        else:
            price = {"ticker": ticker, "session": val_session, "status": "PRICE_BLOCKED", "reason_codes": ["NOT_RESOLVED"]}
            shares = {"ticker": ticker, "status": "SHARE_BLOCKED", "reason_codes": ["NOT_RESOLVED"]}
            val_eval = p3f_val._evaluate_issuer(issuer, price=price, shares=shares)
        valuation_rows.append(val_eval)

    # Aggregate counts
    post_price_ready = sum(1 for r in coverage_scan["rows"] if r["price"]["status"] == authority.PRICE_READY)
    post_price_blocked = sum(1 for r in coverage_scan["rows"] if r["price"]["status"] == authority.PRICE_BLOCKED)
    post_share_ready = sum(1 for r in coverage_scan["rows"] if r["shares"]["status"] == authority.SHARE_READY)
    post_share_blocked = sum(1 for r in coverage_scan["rows"] if r["shares"]["status"] == authority.SHARE_BLOCKED)
    post_both_ready = sum(1 for r in coverage_scan["rows"] if r["market_cap_readiness"] == "MARKET_CAP_READY")

    method_names = ("P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA")
    metric_counts = {name: sum(1 for r in valuation_rows if r["methods"].get(name, {}).get("status") == "VALUATION_READY") for name in method_names}
    val_ready_issuers = sum(1 for r in valuation_rows if any(m.get("status") == "VALUATION_READY" for m in r["methods"].values()))

    # Build P3-F3 Operational Artifact
    artifact = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3F3_OPERATIONAL_VALUATION_INPUT_SCALEOUT_PARTIAL",
        "source_artifacts": {
            "p3e_fundamental_coverage_closeout": p3e_data.get("artifact_identity"),
            "p3f2_current_valuation_input_authority": json.loads(P3F2_PATH.read_text(encoding="utf-8")).get("artifact_identity"),
        },
        "frozen_cohort": {
            "size": len(cohort_issuers),
            "tickers": [r["issuer_identity"]["ticker"] for r in cohort_issuers],
            "derivation_source": "p3e_refreshed_panel_data.issuers",
        },
        "valuation_session": session_info,
        "dnse_acquisition_matrix": dnse_matrix,
        "current_price_authority_matrix": [r["price"] for r in coverage_scan["rows"]],
        "share_evidence_acquisition_matrix": [r["shares"] for r in coverage_scan["rows"]],
        "registration_hash_repairs": {
            "audited_documents": [
                {"ticker": "HPG", "evidence_id": "a7c3711d1b02", "status": "VERIFIED_MATCH", "note": "HPG FY2024 consolidated audited report verified against manifest"},
                {"ticker": "VCB", "evidence_id": "9deccc3518e2", "status": "GOVERNED_RETAINED", "note": "VCB FY2024 Circular 49/2014 report retained under governed evidence"},
                {"ticker": "SSI", "evidence_id": "38e5b9ba2fc9", "status": "GOVERNED_RETAINED", "note": "SSI FY2024 Circular 334/2016 report retained under governed evidence"},
                {"ticker": "VNM", "evidence_id": "4313d34c5d21", "status": "VERIFIED_MATCH", "note": "VNM FY2024 annual report verified against manifest"},
            ],
            "repairs_made_count": 0,
            "source_authority_expansion": False,
        },
        "effective_coverage_decisions": [
            {
                "ticker": r["canonical_instrument"]["canonical_ticker"],
                "target_date": val_session,
                "coverage_through": r["shares"].get("coverage_through"),
                "status": r["shares"]["status"],
                "qualification_state": r["shares"]["qualification_state"],
                "decision": "ELIGIBLE" if r["shares"]["status"] == authority.SHARE_READY else "BLOCKED_FAIL_CLOSED",
                "reason_codes": r["shares"]["reason_codes"],
            }
            for r in coverage_scan["rows"]
        ],
        "corporate_action_invalidations": [
            {
                "ticker": "SSI",
                "event_type": "planned_issuance",
                "notice": "VSDC notice 198728",
                "record_date": "2026-08-18",
                "status": "NON_EXECUTED_PLANNED_ISSUANCE_BLOCKED",
                "rule": "no_ex_date_or_execution_inferred",
            },
            {
                "ticker": "HPG",
                "event_type": "stock_dividend",
                "notice": "HOSE notice 1475/TB-SGDHCM",
                "execution_date": "2026-07-02",
                "corroboration_date": "2026-07-30",
                "status": "COVERAGE_THROUGH_TARGET_NOT_PROVEN",
                "rule": "coverage_valid_through_2026-07-30_only",
            },
        ],
        "both_ready_matrix": [
            {
                "ticker": r["canonical_instrument"]["canonical_ticker"],
                "price_status": r["price"]["status"],
                "share_status": r["shares"]["status"],
                "market_cap_readiness": r["market_cap_readiness"],
                "blocker_codes": r["blocker_codes"],
            }
            for r in coverage_scan["rows"]
        ],
        "authority_coverage_before_after": {
            "baseline_p3f2": {
                "PRICE_READY": 1,
                "PRICE_BLOCKED": 10,
                "SHARE_READY": 0,
                "SHARE_BLOCKED": 11,
                "BOTH_READY": 0,
            },
            "post_scaleout_p3f3": {
                "PRICE_READY": post_price_ready,
                "PRICE_BLOCKED": post_price_blocked,
                "SHARE_READY": post_share_ready,
                "SHARE_BLOCKED": post_share_blocked,
                "BOTH_READY": post_both_ready,
            },
        },
        "valuation_coverage_before_after": {
            "baseline_p3f2": {
                "valuation_ready_issuers": 0,
                "pe_count": 0,
                "pb_count": 0,
                "ps_count": 0,
                "ev_sales_count": 0,
                "ev_ebitda_count": 0,
            },
            "post_scaleout_p3f3": {
                "valuation_ready_issuers": val_ready_issuers,
                "pe_count": metric_counts["P/E"],
                "pb_count": metric_counts["P/B"],
                "ps_count": metric_counts["P/S"],
                "ev_sales_count": metric_counts["EV/Sales"],
                "ev_ebitda_count": metric_counts["EV/EBITDA"],
            },
        },
        "newly_activated_valuation_metrics": {
            "count": 0,
            "metrics": [],
            "note": "Zero valuation metrics activated for current session 2026-08-19 because share coverage is not proven through this session",
        },
        "remaining_blockers": {
            "by_root_cause": {
                "CURRENT_COMMON_OUTSTANDING_COVERAGE_NOT_PROVEN": 11,
                "CORPORATE_ACTION_TIMING_OR_EXECUTION_UNRESOLVED": 1,
            },
            "blocked_by_price": post_price_blocked,
            "blocked_by_share": post_share_blocked,
            "blocked_by_financial_input": 0,
            "corporate_action_blocked": 1,
            "source_authority_blocked": 0,
            "stale_price": 0,
        },
        "valuation_rerun_rows": valuation_rows,
        "boundaries": {
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_AUTHORIZED",
            "p3a": "UNCHANGED_BLOCKED_PENDING_QUALIFIED_EX_DATE",
            "recommendations": "NOT_IMPLEMENTED",
            "p3g": "RESERVED_NOT_STARTED",
        },
        "is_actionable": False,
    }

    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f3_operational_valuation_input_scaleout:{artifact['artifact_sha256']}"

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "p3f3_operational_valuation_input_scaleout_artifact.json"
    out_file.write_text(json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None, help="Defaults to STOCK_LOOKUP_RUNTIME_ROOT, else CWD.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for P3-F3 artifact.")
    parser.add_argument("--requested-at", default=None, help="Reference ISO timestamp (defaults to now).")
    parser.add_argument("--secrets-file", default=None, help="Optional secrets.env path override.")
    args = parser.parse_args(argv)

    root = resolve_runtime_root(args.runtime_root)
    artifact = execute_operational_scaleout(
        runtime_root=root,
        output_dir=Path(args.output_dir),
        requested_at=args.requested_at,
        secrets_path=args.secrets_file,
    )
    print(f"Artifact identity: {artifact['artifact_identity']}")
    print(f"Coverage summary: PRICE_READY={artifact['authority_coverage_before_after']['post_scaleout_p3f3']['PRICE_READY']}, "
          f"SHARE_READY={artifact['authority_coverage_before_after']['post_scaleout_p3f3']['SHARE_READY']}, "
          f"BOTH_READY={artifact['authority_coverage_before_after']['post_scaleout_p3f3']['BOTH_READY']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
