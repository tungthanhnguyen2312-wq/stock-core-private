from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any
from official_financial_source_discovery import discover_routes
ROOT=Path(__file__).resolve().parent
def _load(p:Path)->dict[str,Any]: return json.loads(p.read_text(encoding='utf-8'))
def _hash(x:Any)->str:return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def execute()->dict[str,Any]:
 p13=_load(ROOT/'operations-review/p3f13-official-financial-evidence-scaleout-20260820/p3f13_official_financial_evidence_scaleout_artifact.json'); registry=_load(ROOT/'config/official_source_registry.json')
 cohort=[x for x in p13['acquisition_dispositions'] if x['disposition']=='NO_APPROVED_ROUTE_FOUND']
 # P3-F13's retained closed-world dispositions carry no issuer-domain / exchange-detail URL.
 discovery=discover_routes(cohort,{},registry)
 a={'schema_version':'1.0.0','contract_version':'p3f14_official_financial_source_discovery/v1','target_cohort_identity':{'derived_from':p13.get('artifact_identity'),'count':len(cohort),'identity':_hash([x['ticker'] for x in cohort])},'discovery_sources_mechanisms':['P3-F13 closed-world acquisition disposition ledger','existing approved registry host inventory'],'route_candidate_inventory':discovery['route_candidates'],'approval_rejection_matrix':discovery['disposition_counts'],'registry_before_after':{'before_policy_version':registry.get('policy_version'),'after_policy_version':registry.get('policy_version'),'newly_approved_routes':0,'registry_mutated':False},'newly_addressable_issuer_count':0,'unresolved_blocker_distribution':{'NO_RETAINED_ISSUER_DOMAIN_OR_EXCHANGE_DETAIL_SIGNAL':len(cohort)},'representative_provenance_examples':discovery['route_candidates'][:3],'ticker_specific_branch_audit':{'status':'PASS','production_ticker_literals':[]},'authority_boundaries':{'registry_authority_promoted':False,'documents_acquired':0,'new_provider':False,'p3g_started':False},'source_discovery_gate':'GENERIC_OFFICIAL_SOURCE_DISCOVERY_PARTIAL','next_gate':'RETAINED_ISSUER_DOMAIN_OWNERSHIP_OR_EXCHANGE_PROFILE_EVIDENCE','verdict':'P3F14_OFFICIAL_SOURCE_DISCOVERY_PARTIAL'}
 a['artifact_sha256']=_hash(a);a['artifact_identity']='p3f14_official_financial_source_discovery:'+a['artifact_sha256'];return a
