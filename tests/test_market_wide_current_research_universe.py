from market_wide_current_research_universe import build_artifact


def test_full_ledger_keeps_unknown_and_non_equity_distinct():
    snapshot = {
        'snapshot_identity': 'x',
        'records': {
            'AAA': {'status': 'OBSERVED', 'disposition': 'EXACT_SESSION_RETAINED'},
            'BBB': {'status': 'SESSION_MISSING', 'disposition': 'SESSION_MISSING'},
            'CCC': {'status': 'OBSERVED', 'disposition': 'EXACT_SESSION_RETAINED'},
        },
    }
    rows = [
        {'symbol': 'AAA', 'securityGroupId': 'ST', 'exchange': 'HOSE'},
        {'symbol': 'BBB', 'securityGroupId': 'EF', 'exchange': 'HOSE'},
    ]
    artifact = build_artifact(canonical_snapshot=snapshot, instrument_rows=rows)

    assert artifact['disposition_counts'] == {'EXCLUDED': 1, 'INCLUDED': 1, 'UNKNOWN': 1}
    assert artifact['records']['CCC']['reason_code'] == 'SECURITY_MASTER_SYMBOL_NOT_RETAINED'

def test_duplicate_current_reference_symbol_is_ambiguous_not_selected():
    s={'records':{'AAA':{'status':'OBSERVED','disposition':'EXACT_SESSION_RETAINED'}}}
    a=build_artifact(canonical_snapshot=s,instrument_rows=[{'symbol':'AAA','securityGroupId':'ST'},{'symbol':'AAA','securityGroupId':'ST'}])
    assert a['records']['AAA']['reason_code']=='AMBIGUOUS_SECURITY_MASTER_SYMBOL'
