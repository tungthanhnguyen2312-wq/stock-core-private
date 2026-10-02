"""Offline Release C inventory over exact R7 inputs. No manufactured T0 signals."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.run_portfolio_pit_execution_acceptance import Inputs
import market_only_pit_eligibility as eligibility
import prospective_market_snapshot_contract as market
from completed_market_session_gate import pit_calendar_at_cutoff, build_working_dates_calendar_receipt

INPUT_IDS = {"dnse_snapshots", "hose_snapshots", "raw_pit_authority", "current_universe", "real_ca_outcome",
             "prospective_20260929", "prospective_20260930", "prospective_20261001"}


def listing_continuity_acceptance(*, source_root: Path, acquisition_session: str, expected_attempt_identity: str, output_root: Path) -> dict:
    from official_corporate_event_incremental_acquisition import verify_successful_acquisition, RAW_STORE_RELATIVE
    from prospective_market_evidence_retention import retain_selected_listing_sources
    verified = verify_successful_acquisition(source_root,acquisition_session)
    if verified["attempt_identity"] != expected_attempt_identity:
        raise ValueError("SELECTED_LISTING_ATTEMPT_IDENTITY_MISMATCH")
    paths = [(source_root / RAW_STORE_RELATIVE / c["relative_path"]).resolve() for family in ("hnx","hose") for c in verified[family]["captures"]]
    before = {path:path.read_bytes() for path in paths}
    first = retain_selected_listing_sources(source_root,acquisition_session=acquisition_session,root=output_root)
    retained = Path(first["path"]).read_bytes()
    repeat = retain_selected_listing_sources(source_root,acquisition_session=acquisition_session,root=output_root)
    if (first["artifact_identity"] != repeat["artifact_identity"] or Path(first["path"]).read_bytes() != retained or
        any(path.read_bytes() != body for path,body in before.items())):
        raise ValueError("LISTING_CONTINUITY_SOURCE_OR_RECEIPT_MUTATED")
    return {**{k:v for k,v in first.items() if k != "path"},"selected_acquisition_session":acquisition_session,
            "acquisition_attempt_identity":expected_attempt_identity,"capture_count":len(before),
            "source_bytes":sum(len(body) for body in before.values()),"source_bytes_unchanged":True,
            "idempotence":"PASS","scope":"NEW_SOURCE_OBSERVATIONS_AT_ACTUAL_RECEIPT_TIME_NO_HISTORICAL_BACKFILL"}


def run(*, manifest: dict, roots: dict[str, Path], calendar_path: Path, calendar_receipts: tuple = ()) -> dict:
    subset = {"inputs":[e for e in manifest["inputs"] if e["id"] in INPUT_IDS]}
    if {e["id"] for e in subset["inputs"]} != INPUT_IDS:
        raise ValueError("EXACT_RETAINED_INPUT_SET_INCOMPLETE")
    inputs = Inputs(subset, roots)
    calendar_bytes = calendar_path.read_bytes()
    calendar = json.loads(calendar_bytes)
    if calendar.get("contract_version") != "governed_trading_session_calendar/v1" or calendar.get("source",{}).get("kind") != "EXPLICIT_GOVERNED_SESSION_EVIDENCE":
        raise ValueError("EXPLICIT_GOVERNED_CALENDAR_REQUIRED")
    sessions = calendar["sessions"]
    dnse = [json.loads(line) for line in inputs.paths["dnse_snapshots"].read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    hose = [json.loads(line) for line in inputs.paths["hose_snapshots"].read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    later = [row for key in sorted(INPUT_IDS) if key.startswith("prospective_") for row in inputs.load(key)["records"]]
    versions = {r["snapshot_identity"]:r for r in dnse+later}
    grouped = defaultdict(list)
    for row in versions.values():
        grouped[row["instrument"]["ticker"]].append(row)
    universe = inputs.load("current_universe")
    # Existing current rows contain no qualified temporal membership. Preserve their fields.
    memberships = [{"ticker":ticker,"exchange":r.get("exchange_or_market"),"source_identity":r.get("official_source_row_identity"),
                    "knowledge_available_at":r.get("official_observed_at"),"source_observation":r}
                   for ticker,r in universe.get("records",{}).items()]
    membership_by_ticker = defaultdict(list)
    for row in memberships: membership_by_ticker[row["ticker"]].append(row)
    evaluated = []
    replay_evaluated = []
    for ticker, rows in sorted(grouped.items()):
        # The receipt's actual instant is a candidate data-availability cutoff,
        # not an assertion that a real T0 signal was emitted then.
        earliest = {}
        for row in rows:
            day = row["trading_session"]
            known = row["acquisition"]["knowledge_available_at_utc"]
            if day not in earliest or market._utc(known,"known") < market._utc(earliest[day],"known"):
                earliest[day] = known
        for day, cutoff in sorted(earliest.items()):
            cutoff_sessions = pit_calendar_at_cutoff(sessions, calendar_receipts, session=day, knowledge_cutoff=cutoff)
            args = dict(ticker=ticker,session=day,knowledge_cutoff=cutoff,market_versions=rows,
                        calendar_sessions=cutoff_sessions,universe_versions=membership_by_ticker[ticker])
            evaluated.append(eligibility.evaluate(requirements=eligibility.existing_vnm_requirements(),**args))
            replay_evaluated.append(eligibility.evaluate(requirements=eligibility.existing_vnm_requirements(replay_inputs=True),**args))
    windows = [sessions] + [r["sessions"] for r in calendar_receipts]
    signal_coverage = eligibility.contiguous_coverage(evaluated,calendar_sessions=sessions,calendar_windows=windows)
    gross_coverage = eligibility.contiguous_coverage(replay_evaluated,calendar_sessions=sessions,calendar_windows=windows)
    raw_counts = Counter(r["instrument"].get("exchange") or "UNKNOWN_LEGACY_INSTRUMENT_FIELD" for r in dnse if market.USE_PROSPECTIVE_RAW_AS_TRADED_PRICE in r["qualification"]["allowed_uses"])
    by_exchange = Counter(r["instrument"].get("exchange") or "UNKNOWN" for r in versions.values())
    eligible = sum(r["state"] == "ELIGIBLE" for r in replay_evaluated)
    # This retained cohort has no qualified region. Do not create feature snapshots
    # from current Integrated Decision to manufacture a historical representative.
    replay = {"state":"NOT_RUN_NO_ELIGIBLE_MARKET_WINDOW", "genuine_research_pairs":0,"gross_return":None,"net_return":None,"execution":"UNAVAILABLE"}
    if eligible:
        replay["state"] = "QUALIFIED_INPUTS_REQUIRE_GENUINE_T0_SIGNAL_LINEAGE"
    inputs.unchanged()
    if calendar_path.read_bytes() != calendar_bytes:
        raise ValueError("CALENDAR_SOURCE_MUTATED")
    body = {"contract_version":"market_only_pit_retained_acceptance/v1", "input_sha256":inputs.hashes,
            "calendar_sha256":market.sha256_hex(calendar_bytes),"calendar_scope":calendar["source"],
            "additional_calendar_receipt_identities":[r["artifact_identity"] for r in calendar_receipts],
            "cutoff_semantics":"ACTUAL_RECEIPT_TIME_DATA_FEASIBILITY_NOT_EMITTED_T0_SIGNAL",
            "inventory":{"prospective_dnse_receipts":len(dnse),"official_hose_receipts":len(hose),"later_daily_receipts":len(later),
                         "unique_market_receipt_versions":len(versions),"tickers":len(grouped),
                         "qualified_as_known_price_receipts":sum(market.USE_PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE in r["qualification"]["allowed_uses"] for r in versions.values()),
                         "observed_sessions":len({r["trading_session"] for r in versions.values()}),
                         "observed_earliest":min(r["trading_session"] for r in versions.values()),"observed_latest":max(r["trading_session"] for r in versions.values()),
                         "by_exchange":dict(sorted(by_exchange.items())),"legacy_scoped_raw_receipts":sum(raw_counts.values()),
                         "legacy_raw_instrument_fields":dict(sorted(raw_counts.items())),
                         "volume_values_retained":sum(market._finite_number(r["normalized"]["volume_value"].get("volume")) for r in versions.values()),
                         "qualified_volume_receipts":sum(eligibility._volume_ready(r) for r in versions.values())},
            "signal_input_coverage":signal_coverage,"gross_replay_input_coverage":gross_coverage,"representative_replay":replay,
            "authority_effect":"NONE","source_bytes_unchanged":True,"acquisition_requests":0,"production_writes":0}
    body.update(market.content_identity(body,kind="market_only_pit_retained_acceptance"))
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,default=Path("docs/internal/R7_RETAINED_INPUT_MANIFEST.json"))
    parser.add_argument("--primary-root",type=Path,required=True)
    parser.add_argument("--raw-pit-root",type=Path,required=True)
    parser.add_argument("--calendar",type=Path,default=Path("config/governed_trading_session_calendar_v1.json"))
    parser.add_argument("--calendar-receipt",type=Path,action="append",default=[])
    parser.add_argument("--report",type=Path,required=True)
    parser.add_argument("--listing-source-root",type=Path)
    parser.add_argument("--listing-acquisition-session")
    parser.add_argument("--listing-attempt-identity")
    parser.add_argument("--output-root",type=Path)
    args = parser.parse_args()
    calendar_bytes = {p:p.read_bytes() for p in args.calendar_receipt}
    calendar_receipts = []
    for path, body in calendar_bytes.items():
        receipt = json.loads(body)
        raw_path = path.parent.parent / "raw" / receipt["payload_sha256"]
        raw = raw_path.read_bytes()
        rebuilt = build_working_dates_calendar_receipt(raw, retrieved_at=receipt["retrieved_at"],
            documentation_sha256=receipt["documentation_sha256"],
            documentation_retrieved_at=receipt["documentation_retrieved_at"])
        if receipt != rebuilt:
            raise ValueError("CALENDAR_RAW_SOURCE_BINDING_INVALID")
        calendar_receipts.append(receipt)
    report = run(manifest=json.loads(args.manifest.read_text(encoding="utf-8")),roots={"primary":args.primary_root,"raw_pit":args.raw_pit_root},calendar_path=args.calendar,
                 calendar_receipts=tuple(calendar_receipts))
    if any(p.read_bytes() != b for p,b in calendar_bytes.items()):
        raise ValueError("CALENDAR_RECEIPT_MUTATED")
    if args.listing_source_root:
        if not all((args.listing_acquisition_session,args.listing_attempt_identity,args.output_root)):
            raise ValueError("EXACT_LISTING_SELECTION_AND_OUTPUT_ROOT_REQUIRED")
        report["new_listing_source_continuity"] = listing_continuity_acceptance(source_root=args.listing_source_root,
            acquisition_session=args.listing_acquisition_session,expected_attempt_identity=args.listing_attempt_identity,output_root=args.output_root)
        report.update(market.content_identity(report,kind="market_only_pit_retained_acceptance"))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,sort_keys=True))


if __name__ == "__main__": main()
