import json
from pathlib import Path
from polymorphic_current_strategy_classification import build, content_identity, prospective_context

ROOT=Path(__file__).resolve().parents[1]; OPS=ROOT/'operations-review'
PATHS={"descriptive":"market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json","tactical":"watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json","peer_relative":"sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json","fundamental":"market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json","valuation":"market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json","scenario":"current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json","corporate_intelligence":"market-wide-current-corporate-intelligence-v1-20260824/market_wide_current_corporate_intelligence_artifact.json"}
def _artifact(): return build(**{k:json.loads((OPS/v).read_text(encoding='utf-8')) for k,v in PATHS.items()})
def test_full_universe_deterministic_and_value_fails_closed():
 a,b=_artifact(),_artifact(); assert content_identity(a)['artifact_sha256']==a['artifact_sha256']; assert a['artifact_identity']==b['artifact_identity']; assert a['coverage']['universe_count']==1683
 assert all(r['strategies']['VALUE']['status']=='BLOCKED' for r in a['records'].values())
def test_strategy_is_independent_from_tactical_and_scenario_with_stable_freeze():
 a=_artifact(); hpg=a['records']['HPG']; assert hpg['tactical_context']['entry_action']=='WAIT'; assert hpg['strategies']['EVENT_DRIVEN']['status']=='ELIGIBLE'; assert hpg['strategies']['EVENT_DRIVEN']['scenario_relationship']['probability_status']=='UNKNOWN_UNCALIBRATED'
 assert a['records']['ABB']['strategies']['EARLY_REVERSAL']['status']=='ELIGIBLE'; assert prospective_context(a)['cohort_count']==1683
def test_missing_event_only_limits_event_strategy():
 a=_artifact(); aaa=a['records']['AAA']; assert aaa['strategies']['EVENT_DRIVEN']['status']=='INSUFFICIENT_DATA'; assert aaa['strategies']['VALUE']['status']=='BLOCKED'; assert aaa['strategies']['EARLY_REVERSAL']['status'] in {'ELIGIBLE','NOT_APPLICABLE','INSUFFICIENT_DATA'}
