import copy
import hashlib
import json

import pytest

from bounded_artifact_stream import canonical_bytes, record_mapping_digest
from bounded_artifact_stream import pretty_record_chunks
import daily_research_session_operations as operations
import stocklookup_core.decision.integrated_investment_decision_product as iid


@pytest.mark.parametrize('value', [
    {}, {'records': {}}, {'records': None},
    {1: 'numeric stdlib key'}, {'records': {1: {'x':True}}},
    {'z': '\u0111ồng\n\"', 'records': {'Z': {'x': -0.0}, 'AAA': [None, True, 1e-30]}, 'a': []},
    {'records': {'A': {'records': {'C': [False, {'u': '\U0001f600'}]}}}, 'coverage': {'total': 1}},
])
def test_record_digest_preserves_exact_stdlib_identity(value):
    assert record_mapping_digest(value) == hashlib.sha256(canonical_bytes(value)).hexdigest()


@pytest.mark.parametrize('records',[{},[],{'ĐỒNG':{'x':[1,-0.0,None,'😀\n"']}},
                                  [{'a':{'b':[]},'c':'Việt'}, True, None]])
def test_record_pretty_writer_preserves_native_stdlib_bytes(records,tmp_path):
    value={'z':{'nested':[True,None]},'records':records,'a':['ĐỒNG 😀',1e-30]}
    path=tmp_path/'oracle.json'
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    assert b''.join(pretty_record_chunks(value)) == path.read_bytes()


def test_iid_identity_exclusions_and_strict_float_semantics():
    artifact = {'records': {'A': {'value': 2.0}}, 'session': '2026-10-06',
                'requested_at': 'ignored', 'artifact_identity': 'ignored', 'artifact_sha256': 'ignored'}
    body = {k:v for k,v in artifact.items() if k not in iid._IDENTITY_EXCLUDED}
    assert iid.content_identity(artifact)['artifact_sha256'] == hashlib.sha256(canonical_bytes(body)).hexdigest()
    artifact['records']['A']['value'] = float('nan')
    with pytest.raises(ValueError):
        iid.content_identity(artifact)


def test_identity_never_encodes_the_whole_artifact_or_records_mapping(monkeypatch):
    import bounded_artifact_stream as stream
    artifact={'records':{str(i):{'ticker':str(i),'text':'ĐỒNG 😀'} for i in range(100)}}
    original=stream.canonical_bytes
    def bounded(value):
        assert value is not artifact and value is not artifact['records']
        return original(value)
    monkeypatch.setattr(stream,'canonical_bytes',bounded)
    assert stream.record_mapping_digest(artifact) == hashlib.sha256(original(artifact)).hexdigest()


def test_binding_copies_only_writable_spine_and_preserves_content():
    session = '2026-10-06'
    registry = {'sessions': {session: {k:{'artifact_identity': k+':1'} for k in operations.REQUIRED}}}
    decision = {'contract_version': iid.CONTRACT_VERSION, 'session': session,
                'artifact_identity': 'iid:1', 'records': {'A': {'ticker': 'A', 'reasons': ['UNCHANGED']}}}
    brief = {'contract_version': 'daily_integrated_decision_brief/v1', 'session': session,
             'artifact_identity': 'brief:1','source_artifact_identities': {'integrated_investment_decision_product':'iid:1'}}
    operation = {'manifest': {'market_session': session, 'outputs': {'daily_product': 'product:1'}},
        'product': {'nested': ['sealed']}, 'integrated_delivery': operations._integrated_delivery_binding(
            session=session,integrated_decision=decision,daily_integrated_brief=None,registry=registry)}
    original = copy.deepcopy(operation)
    result = operations.bind_integrated_decision_brief_before_sealing(operation,
        daily_integrated_decision_brief=brief,registry=registry)
    assert operation == original
    assert result['product'] is operation['product']
    assert result['integrated_delivery']['integrated_investment_decision_product']['records'] is decision['records']
    assert result['manifest'] is not operation['manifest']
    assert result['manifest']['outputs'] is not operation['manifest']['outputs']
    result['manifest']['outputs']['daily_product'] = 'changed'
    assert operation == original
    # Failure must not change the original manifest, binding or analytical graph.
    with pytest.raises(ValueError, match='DAILY_INTEGRATED_BRIEF_SESSION_MISMATCH'):
        operations.bind_integrated_decision_brief_before_sealing(operation,
            daily_integrated_decision_brief={**brief,'session':'2026-10-05'},registry=registry)
    assert operation == original
