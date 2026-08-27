"""Retained inventory + optional bounded FHSC recovery for the ADTV20 trailing-20 window."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adtv20_exact_reconciled_trailing_window_recovery import (
    DEFAULT_OUT_DIR,
    DEFAULT_REQUEST_BUDGET,
    acquisition_plan,
    build_recovery_artifact,
    evaluation_rows_from_qualified,
    json_dumps,
    load_retained_inputs,
    inventory_trailing20,
    merge_new_exact_row,
    recompute_adtv20,
    reconcile_acquired_session,
    run_bounded_acquisition,
)
from fhsc_retained_live_reconciliation import load_finhay_api_key
from historical_matched_trading_value_authority import EXACT_RECONCILED


def _load_dnse_pages(ticker: str, session: str) -> tuple[list[dict[str, Any]], list[str]] | tuple[None, None]:
    from tools.run_fhsc_historical_matched_value_coverage_scaleout import (
        index_dnse_trades_parquet,
        load_fast_pages,
    )
    indexed = index_dnse_trades_parquet([session])
    paths = indexed.get((session, ticker))
    if not paths:
        return None, None
    return load_fast_pages(paths, ticker=ticker, session=session)


def run(
    *,
    acquire: bool,
    budget: int,
    out_dir: Path,
    api_key: str | None = None,
    fetcher=None,
    dnse_loader=None,
) -> dict[str, Any]:
    inputs = load_retained_inputs()
    inventory = inventory_trailing20(
        tickers=inputs["tickers"],
        exchanges=inputs["exchanges"],
        window=inputs["window"],
        qualified_rows=inputs["qualified_rows"],
        recon_rows=inputs["recon_rows"],
    )
    plan = acquisition_plan(inventory, budget=budget)
    eval_rows = evaluation_rows_from_qualified(inputs["qualified_rows"], inputs["exchanges"])
    before = recompute_adtv20(
        eval_rows, tickers=inputs["tickers"], exchanges=inputs["exchanges"], window=inputs["window"],
    )
    acquisition = None
    new_qualified: list[dict[str, Any]] = []
    after_rows = list(eval_rows)
    if acquire:
        key = api_key if api_key is not None else load_finhay_api_key()
        acquisition = run_bounded_acquisition(
            plan,
            api_key=key,
            raw_dir=out_dir / "raw",
            budget=budget,
            fetcher=fetcher,
        )
        loader = dnse_loader or _load_dnse_pages
        for rec in acquisition.get("records") or []:
            ticker = rec.get("symbol")
            parsed_rows = rec.get("parsed_rows_by_session") or {}
            plan_item = next((item for item in plan.get("selected") or [] if item["ticker"] == ticker), None)
            if not plan_item:
                continue
            exchange = inputs["exchanges"].get(ticker)
            for session in plan_item.get("fhsc_missing_sessions") or []:
                fhsc_row = parsed_rows.get(session)
                if not fhsc_row:
                    continue
                pages, hashes = loader(ticker, session)
                upgraded = reconcile_acquired_session(
                    ticker=ticker,
                    session=session,
                    fhsc_row=fhsc_row,
                    dnse_pages=pages,
                    raw_payload_hashes=hashes,
                    exchange=exchange,
                )
                if upgraded and upgraded.get("value_reconciliation") == EXACT_RECONCILED:
                    after_rows = merge_new_exact_row(after_rows, upgraded)
                    new_qualified.append(upgraded)
    after = recompute_adtv20(
        after_rows, tickers=inputs["tickers"], exchanges=inputs["exchanges"], window=inputs["window"],
    )
    artifact = build_recovery_artifact(
        inventory=inventory,
        plan=plan,
        before=before,
        after=after,
        acquisition=acquisition,
        source_identities=inputs["source_identities"],
        new_qualified_rows=new_qualified,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "adtv20_exact_reconciled_trailing_window_recovery_artifact.json").write_text(
        json_dumps(artifact), encoding="utf-8",
    )
    report = {
        "outcome": artifact["outcome"],
        "artifact_identity": artifact["artifact_identity"],
        "inventory": artifact["inventory"],
        "acquisition_plan": {
            "request_budget": plan["request_budget"],
            "selected_tickers": [item["ticker"] for item in plan["selected"]],
            "session_wide_fhsc_holes": plan["session_wide_fhsc_holes"],
        },
        "acquisition": artifact.get("acquisition"),
        "before": artifact["before"],
        "after": artifact["after"],
        "new_qualified_observations": artifact["new_qualified_observations"],
        "reopening_gate": artifact["reopening_gate"],
        "authority_effect": artifact["authority_effect"],
    }
    (out_dir / "adtv20_exact_reconciled_trailing_window_recovery_report.json").write_text(
        json_dumps(report), encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true", help="Run the bounded FHSC batch. Default is retained inventory only.")
    parser.add_argument("--budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    report = run(acquire=args.acquire, budget=args.budget, out_dir=args.out_dir)
    print(f"OUTCOME={report['outcome']}")
    print(f"READY_BEFORE={report['before']['ready_count']} READY_AFTER={report['after']['ready_count']}")
    print(f"PARTIAL_BEFORE={report['before']['partial_count']} PARTIAL_AFTER={report['after']['partial_count']}")
    holes = report["acquisition_plan"]["session_wide_fhsc_holes"]
    print(f"SESSION_WIDE_FHSC_HOLES={','.join(holes) if holes else 'NONE'}")
    print(f"SELECTED={','.join(report['acquisition_plan']['selected_tickers'])}")
    if report.get("acquisition"):
        print(f"REQUESTS_SENT={report['acquisition']['requests_sent']}")
        print(f"HTTP={report['acquisition']['http_disposition']}")
        print(f"TERMINATED={report['acquisition']['terminated_reason']}")
    print(f"NEW_QUALIFIED={len(report['new_qualified_observations'])}")
    print(f"AUTHORITY_EFFECT={report['authority_effect']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
