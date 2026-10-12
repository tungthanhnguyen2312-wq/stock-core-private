"""Fixed synthetic consumer call shapes; also executed against accepted E4 Git source."""
from datetime import datetime, timezone
import hashlib
import json


def consumer_outputs():
    import field_temporal_contract as field
    import current_official_event_context as event
    import official_financial_assurance_evidence as assurance
    from stocklookup_core.decision import human_ai_decision_evidence_packet as packet
    from stocklookup_core.decision import current_daily_decision_research_product as daily
    from stocklookup_core.portfolio import current_portfolio_risk_envelope as risk
    from stocklookup_core.financial import financial_reporting_currency as currency
    from stocklookup_core.financial import financial_analysis_product_projection as projection

    def seal(value):
        digest = hashlib.sha256(event._canonical(value)).hexdigest()
        return {**value, 'artifact_sha256': digest, 'artifact_identity': 'synthetic:'+digest}
    universe = seal({'records': {'FPT': {'stocklookup_candidate': True, 'current_universe_status': 'OFFICIAL_CURRENT_EXCHANGE_SECURITY'}},
                     'reconciliation': {'official_total_match': 1}})
    hnx = seal({'captures': [{'sha256':'synthetic:hnx','retrieved_at':'2026-10-07T08:00:00Z'}],
                'datasets': {'hnx_official_rights_event_index/v1': [{'ticker':'FPT','event_type':'CASH_DIVIDEND','ex_date':'2026-10-08',
                    'record_date':'2026-10-09','source_identity':'synthetic:hnx','qualification':'EX_DATE_OFFICIAL_QUALIFIED'}]}})
    hose = seal({'datasets': {}})
    parent = event.build_artifact(official_universe=universe, hnx=hnx, hose=hose, research_session='2026-10-07')
    projected = event.project_session_context(parent, session='2026-10-08', cutoff='2026-10-08T15:00:00+07:00')

    product = {'contract_version':projection.INTEGRATION_CONTRACT,'records':{},'source_context_identity':'synthetic:provider'}
    product.update(projection._identity(product))
    financial = currency.build(financial_product=product, official_rows=[], tickers=['FPT'],
        decision_session='2026-10-08', knowledge_cutoff='2026-10-08T15:00:00+07:00')
    accepted = currency.packet_context(financial, ticker='FPT', decision_session='2026-10-08')
    human = packet.build_packet(ticker='FPT', feature_measurements={'rsi':28,'context':'Tiếng Việt'},
                               canonical_packet_identity='synthetic:packet')
    text = 'BÁO CÁO SOÁT XÉT hợp nhất giữa niên độ hợp đồng dịch vụ soát xét số 2410 không đưa ra ý kiến kiểm toán'
    materialization = {'document_sha256':'a'*64,'pages':[{'page_number':1,'rendered_image_sha256':'b'*64,
        'ocr_derived_text_evidence':{'tokens':[{'text':word,'raw_token_order':i,'top':1,'x0':i,'x1':i+1} for i,word in enumerate(text.split())]}}]}
    proof = assurance.resolve_document_assurance_evidence(materialization)
    record = field.TemporalField('close', 25.5, '2026-10-08T08:00:00Z', '2026-10-08', 'current', False, 'UNQUALIFIED_PRICE_BASIS',
                                 quality_status='research', lineage={'fixture':'synthetic'})
    value = {'session':'2026-10-08','records':{'FPT':{'name':'Tiếng Việt','value':float('nan'),'zero':-0.0}},
             'at':datetime(2026,10,8,8,tzinfo=timezone.utc)}
    return {'event_projection':projected,'currency':financial,'currency_packet_context':accepted,'human_packet':human,
            'assurance':proof,'field_record_json':record.canonical_json(),'field_json':field.canonical_json(value),
            'field_id':field.stable_id(value),'daily_identity':daily.content_identity(value),'risk_identity':risk.identity(value)}
