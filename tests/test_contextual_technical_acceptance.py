"""Bounded retained adapter parsing and exact standing content identity oracles."""
import io
import json

import pytest

from tools.run_contextual_technical_acceptance import ObjectStream, header, stream_artifact
import integrated_investment_decision_product as product
from field_temporal_contract import stable_id


@pytest.mark.parametrize("size", [1,5,13,64,65536])
def test_stream_identity_matches_standing_product_hash_across_chunk_boundaries(tmp_path,size):
    body={"contract_version":product.CONTRACT_VERSION,"requested_at":"2026-10-02T16:00:00Z",
          "session":"2026-10-02","records":{"AAA":{"text":'Unicode \"quoted\"',"nested":[None,1.2,-3]},"VNM":{"text":"x"*70000}}}
    body.update(product.content_identity(body));p=tmp_path/'source.json';p.write_text(json.dumps(body,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    selected={};metadata,digest,count=stream_artifact(p,excluded=product._IDENTITY_EXCLUDED,on_record=lambda t,r:selected.update({t:r}))
    assert digest == body['artifact_sha256'] and selected == body['records'] and count == 2
    # Exercise the parser separately under arbitrarily small reads.
    class SmallReads(io.StringIO):
        def read(self,n=-1):return super().read(min(n,size) if n>=0 else size)
    parser=ObjectStream(SmallReads(json.dumps({'a':12345,'b':-1.234e-12,'c':'string'},sort_keys=True)))
    actual={}
    for key in parser.members():actual[key]=parser.value()
    assert actual == {'a':12345,'b':-1.234e-12,'c':'string'}


def test_price_stream_preserves_stable_id_nan_sanitization(tmp_path):
    body={'records':{'AAA':{'close':float('nan')}},'requested_at':'2026-10-02T16:00:00Z','resolved_completed_session':'2026-10-02'}
    digest=stable_id(body);body.update(snapshot_identity='p3f9_exact_session_snapshot:'+digest,snapshot_sha256=digest)
    p=tmp_path/'price.json';p.write_text(json.dumps(body,sort_keys=True,indent=2),encoding='utf-8')
    metadata,actual,count=stream_artifact(p,excluded={'snapshot_identity','snapshot_sha256'},on_record=lambda *_:None,sanitize=True)
    assert actual == digest and count == 1 and header(p)['snapshot_sha256'] == digest


@pytest.mark.parametrize('text',[ '{"b":2,"a":1}', '{"a":1,"a":2}', '{"a":1} {}', '{"records":{"VNM":{}}' ])
def test_unsafe_noncanonical_or_truncated_stream_fails_closed(tmp_path,text):
    p=tmp_path/'bad.json';p.write_text(text,encoding='utf-8')
    with pytest.raises((ValueError,json.JSONDecodeError)):
        stream_artifact(p,excluded=set(),on_record=lambda *_:None)


def test_member_limit_bounds_a_single_oversized_record():
    parser=ObjectStream(io.StringIO(json.dumps({'a':'x'*70000})),limit=65536)
    with pytest.raises(ValueError,match='MEMBER_LIMIT'):
        for key in parser.members():parser.value()
