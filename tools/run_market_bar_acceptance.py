"""Bounded offline D/W/M acceptance; exact inputs parsed once and never written."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import canonical_market_bars as bars
import integrated_investment_decision_product as product
import market_wide_historical_research_context as history
from test_production_call_shape_smoke import _offline_smoke_guard


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("price-snapshot","prospective","current-product","events","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--cutoff",required=True)
    args=p.parse_args()
    paths={k:getattr(args,k) for k in ("price_snapshot","prospective","current_product","events")}
    paths["calendar"]=ROOT / "config/governed_trading_session_calendar_v1.json"
    if args.output.resolve() in {v.resolve() for v in paths.values()}:
        raise ValueError("OUTPUT_MUST_NOT_REPLACE_EVIDENCE")
    before={k:sha(v) for k,v in paths.items()}
    with _offline_smoke_guard() as counters:
        snapshot=json.loads(paths["price_snapshot"].read_text(encoding="utf-8"))
        current=json.loads(paths["current_product"].read_text(encoding="utf-8"))
        event_artifact=json.loads(paths["events"].read_text(encoding="utf-8"))
        history._verify_p3f9b_identity(snapshot)
        assert product.content_identity(current)["artifact_identity"] == current["artifact_identity"]
        events=[e for r in event_artifact["records"].values() for e in r.get("events",[])]
        calendar=bars.governed_calendar_projection(json.loads(paths["calendar"].read_text(encoding="utf-8")))
        prospective=[]; prospective_total=0
        with paths["prospective"].open(encoding="utf-8") as stream:
            for line in stream:
                row=json.loads(line);prospective_total+=1
                if row.get("instrument",{}).get("ticker") == "VNM":prospective.append(row)
        session=snapshot["resolved_completed_session"]
        projections={};cohort_counts={}
        for ticker in ("VNM","HPG","ALT"):
            rows=snapshot["records"][ticker].get("observations",[])
            projections[ticker]=bars.research_projection(rows,ticker=ticker,target_session=session,
                knowledge_cutoff=args.cutoff,source_identity=snapshot["snapshot_identity"],calendar_evidence=calendar,ca_events=events)
            cohort_counts[ticker]=len(rows)
        prospective_projection=bars.research_projection(prospective,ticker="VNM",target_session=session,
            knowledge_cutoff=args.cutoff,source_identity="jsonl:sha256:"+before["prospective"],calendar_evidence=calendar,ca_events=events)
        h={"contract_version":history.CONTRACT_VERSION,"session":session,
           "records":{t:{"multi_timeframe":v} for t,v in projections.items()}}
        h.update(history.content_identity(h))
        attached=product.market_bar_context_records(h,session=session,requested_at=args.cutoff)
        deltas=0
        for ticker,context in attached.items():
            assert context["status"] == "AVAILABLE"
            record=copy.deepcopy(current["records"][ticker])
            record["market_sector_context"]["multi_timeframe"]=context
            record["market_sector_context"].pop("multi_timeframe")
            deltas += record != current["records"][ticker]
        assert deltas == 0
        ca_period=bars.derive(snapshot["records"]["ALT"]["observations"],ticker="ALT",timeframe="1M",period_session="2026-09-01",
            knowledge_cutoff=args.cutoff,source_identity=snapshot["snapshot_identity"],calendar_evidence=calendar,ca_events=events)
        assert ca_period["corporate_action_crossing"]["state"] == "EVENTS_OBSERVED"
        assert ca_period["period_completeness"] == "CALENDAR_SCOPE_UNKNOWN"
        assert ca_period["corporate_action_crossing"]["factor_chain_state"] == "NOT_ESTABLISHED"
        assert all(p["PIT_CA_ADJUSTED"]["status"] == "UNAVAILABLE" for p in projections.values())
        summaries={}
        for name,projection in {**projections,"VNM_PROSPECTIVE":prospective_projection}.items():
            summaries[name]={tf:{k:v for k,v in projection[tf].items() if k not in ("latest_observed","latest_completed")} for tf in ("1D","1W","1M")}
            for tf in summaries[name]:
                for field in ("latest_observed","latest_completed"):
                    b=projection[tf][field]
                    summaries[name][tf][field]=None if b is None else {k:b[k] for k in ("artifact_identity","period_start","period_end","price_basis","volume_unit","period_completeness","constituent_count","knowledge_available_at")}
        after={k:sha(v) for k,v in paths.items()}
        assert before == after
        report={"contract_version":"market_bar_retained_acceptance/v1","session":session,"knowledge_cutoff":args.cutoff,
            "inputs_sha256":before,"inputs_unchanged":True,"historical_cohort_count":len(projections),"historical_daily_rows":cohort_counts,
            "prospective_corpus_rows_parsed_once":prospective_total,"prospective_vnm_versions":len(prospective),
            "source_candidate_count":len(snapshot["records"]),"attached_current_research_count":len(attached),
            "posture_or_decision_field_deltas":deltas,"historical_t0_writes":0,"network_provider_calls":counters,
            "projections":summaries,"ca_crossing_period":ca_period,"qualified_factor_series_count":0,
            "authority_effect":"NONE","all_assertions_passed":True}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("historical_daily_rows","prospective_corpus_rows_parsed_once","prospective_vnm_versions","attached_current_research_count","posture_or_decision_field_deltas","inputs_unchanged","network_provider_calls")}))


if __name__ == "__main__":
    main()
