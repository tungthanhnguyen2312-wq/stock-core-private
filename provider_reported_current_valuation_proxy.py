"""Non-authoritative adapter over retained provider-issued-share proxy valuation evidence."""
from __future__ import annotations
from typing import Any, Mapping
from field_temporal_contract import stable_id

CONTRACT_VERSION="provider_reported_current_valuation_proxy/v1"
METHOD="PROVIDER_ISSUED_SHARES_PROXY"
AUTHORITY="NON_AUTHORITATIVE_RESEARCH_PROXY"
METRICS={"P/E":"pe_provider_issued_share_proxy","P/B":"pb_provider_issued_share_proxy","P/S":"ps_provider_issued_share_proxy","EV/Sales":"ev_sales_provider_issued_share_proxy","EV/EBITDA":"ev_ebitda_provider_issued_share_proxy"}

def build_proxy(p3f6:Mapping[str,Any],p3f3:Mapping[str,Any])->dict[str,Any]:
    rows=[]
    for source in sorted(p3f6["proxy_valuation_rows"],key=lambda row:row["ticker"]):
        share,cap=source["provider_share_proxy"],source["market_cap_provider_issued_share_proxy"]
        metrics={}
        for name,identity in METRICS.items():
            value=source["methods"][name]
            metrics[identity]={"method":METHOD,"authority":AUTHORITY,"status":value["status"],"value":value.get("value") if value["status"]=="MVA_PROXY_READY" else None,"financial_input_lineage":value.get("financial_inputs",[]),"blocked_reasons":value.get("blockers",[]),"sector_applicable":value["status"]!="NOT_APPLICABLE"}
        row={"ticker":source["ticker"],"valuation_session":source["valuation_date"],"method":METHOD,"authority":AUTHORITY,
             "price":{"value_vnd_per_share":source["price_input"].get("value"),"unit":"VND/share","source":source["price_input"].get("provider"),"basis":source["price_input"].get("price_basis"),"lineage":source["price_input"].get("payload_identity"),"status":source["price_input"].get("status")},
             "provider_issued_shares":{"value":share.get("value"),"semantic_identity":str(share.get("semantic_identity") or "").lower(),"source":share.get("provider_source"),"observation_date":share.get("provider_observation_date"),"freshness_state":share.get("freshness_state"),"corporate_action_state":share.get("corporate_action_state"),"common_outstanding_equivalence":False},
             "provider_issued_share_market_cap_proxy":{"method":METHOD,"authority":AUTHORITY,"status":cap.get("status"),"value":cap.get("value") if cap.get("status")=="PROXY_MARKET_CAP_READY" else None,"blocked_reasons":cap.get("blockers",[])},"metrics":metrics}
        row["content_identity"]=stable_id(row);rows.append(row)
    counts={"candidate_universe":p3f6["provider_proxy_coverage"]["available_metadata_universe"],"valid_provider_issued_share_observations":p3f6["provider_proxy_coverage"]["proxy_share_eligible"],"current_price_eligible":len(rows),"financial_input_eligible":len(rows),"corporate_action_blocked":sum(row["provider_issued_shares"]["corporate_action_state"]=="provider_reported_unverifiable_freshness" for row in rows),"proxy_market_cap_produced":sum(row["provider_issued_share_market_cap_proxy"]["value"] is not None for row in rows),"pe_proxy_produced":sum(row["metrics"][METRICS["P/E"]]["value"] is not None for row in rows),"pb_proxy_produced":sum(row["metrics"][METRICS["P/B"]]["value"] is not None for row in rows),"ps_proxy_produced":sum(row["metrics"][METRICS["P/S"]]["value"] is not None for row in rows),"ev_family_proxy_produced":sum(row["metrics"][METRICS["EV/Sales"]]["value"] is not None for row in rows),"fully_blocked":sum(row["provider_issued_share_market_cap_proxy"]["value"] is None for row in rows)}
    artifact={"contract_version":CONTRACT_VERSION,"method":METHOD,"authority":AUTHORITY,"valuation_session":p3f6["provider_proxy_coverage"]["valuation_date"],"source_artifacts":{"p3f6":p3f6["artifact_identity"],"p3f3":p3f3["artifact_identity"]},"corpus_results":rows,"broader_retained_universe_denominators":counts,"boundaries":{"common_shares_outstanding_authority":False,"authoritative_valuation":False,"historical_pit":False,"raw_as_traded":False,"recommendation_ranking_sizing_portfolio":False},"verdict":"PROVIDER_REPORTED_CURRENT_VALUATION_PROXY_COMPLETE"}
    artifact["artifact_sha256"]=stable_id(artifact);artifact["artifact_identity"]="provider_reported_current_valuation_proxy:"+artifact["artifact_sha256"];return artifact
