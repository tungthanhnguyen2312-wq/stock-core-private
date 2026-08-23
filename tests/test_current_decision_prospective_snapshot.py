from prospective_research_learning import freeze_current_decision_surface

def test_additive_current_decision_snapshot_is_deterministic_and_labels_shadow():
 tactical={'session':'2026-08-21','artifact_identity':'t','records':{'AAA':{'ticker':'AAA','entry_state':'BASE_BUILDING','entry_action':'ACCUMULATE_IN_BASE','ticker_structure_state':'NEUTRAL','confirmation_trigger':'c','invalidation':'i','data_quality':'OK'}}}
 triage={'source_market_session':'2026-08-21','artifact_identity':'r','all_entry_relevant_records':{'BASE':[{'ticker':'AAA'}]}}
 fund={'artifact_identity':'f','records':{'AAA':{'ticker':'AAA','entity_class':'corporate','authority_tier':'PROVIDER_RESEARCH','fundamental_trajectory_context':{'revenue_direction':'INCREASED','revenue_vs_earnings_alignment':'BOTH_EXPANDING'}}}}
 val={'valuation_session':'2026-08-21','artifact_identity':'v','records':{'AAA':{'content_identity':'x','metrics':{'P/E':{'status':'BLOCKED'}},'shadow_proxy_valuation':{'source_observation':{'status':'PROXY_STALE','freshness_state':'STALE_DEGRADED'},'metrics':{'proxy_P/E':{'status':'SHADOW_PROXY_READY'}}}}}}
 first=freeze_current_decision_surface(tactical,triage,fund,val);second=freeze_current_decision_surface(tactical,triage,fund,val)
 assert first['snapshot_id']==second['snapshot_id']
 d=first['frozen_records'][0]['decision_surface'];assert d['valuation']['authoritative_current_valuation_available'] is False
 assert d['valuation']['shadow_proxy_valuation_available'] is True and d['valuation']['available_proxy_metric_ids']==['proxy_P/E']
