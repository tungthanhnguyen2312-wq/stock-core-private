"""Independent financial semantics, shared contracts and removed-cycle regressions."""
import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

from tests.e6_financial_fixtures import LABEL_CASES, capture, consumer_outputs, metadata_cases, proved_fixture
from stocklookup_core.evidence import financial_metadata_envelope as envelope, financial_row_identity as rows
from stocklookup_core.financial import qualification_states as states
import official_financial_filing_evidence as filing
import official_financial_ocr_table_evidence as ocr

ROOT = Path(__file__).resolve().parents[1]
BASE = '70fbba96d02369e0f02a5a15dd264bad780fe6ce'
FIXTURE = json.loads((ROOT/'tests/fixtures/e6_financial_boundary_baseline.json').read_text(encoding='utf-8'))
LIBRARIES = {'official_financial_filing_evidence.py', 'official_financial_ocr_table_evidence.py',
             'canonical_financial_qualification_policy.py', 'stocklookup_core/evidence/official_document_qualification.py'}


def baseline(relative):
    assert relative in LIBRARIES  # reviewed libraries only; no historical CLI execution
    name = '_e6_original_'+relative.replace('/', '_').replace('.', '_')
    if name not in sys.modules:
        module = types.ModuleType(name); module.__file__ = str(ROOT/relative)
        sys.modules[name] = module
        source = subprocess.check_output(['git', 'show', BASE+':'+relative], cwd=ROOT)
        exec(compile(source, relative, 'exec'), module.__dict__)
    return sys.modules[name]


@pytest.mark.parametrize('candidate', metadata_cases())
def test_metadata_exact_original_results_errors_and_no_mutation(candidate):
    before = copy.deepcopy(candidate)
    expected = capture(lambda: baseline('official_financial_filing_evidence.py').qualify_document_metadata(candidate))
    assert capture(lambda: envelope.qualify_document_metadata(candidate)) == expected
    assert candidate == before


@pytest.mark.parametrize('metric,label', LABEL_CASES)
def test_literal_rows_exact_original_results_and_errors(metric, label):
    expected = capture(lambda: baseline('official_financial_ocr_table_evidence.py').row_label_supports_metric(metric, label))
    assert capture(lambda: rows.row_label_supports_metric(metric, label)) == expected
    assert capture(lambda: ocr.row_label_supports_metric(metric, label)) == expected


@pytest.mark.parametrize('value', [None, {}, {'x': -0.0, 'text': 'Tiếng Việt'}, [1,2], float('nan'), float('inf'), {'x': object()}])
def test_filing_encoder_stays_distinct_and_exact(value):
    old = baseline('official_financial_filing_evidence.py')
    for name in ('canonical_json', 'stable_id'):
        assert capture(lambda: getattr(envelope,name)(value)) == capture(lambda: getattr(old,name)(value))


def test_shared_envelope_classes_functions_constants_and_mutable_row_policy():
    import reviewed_interim_canonical_ingress as ingress
    import canonical_financial_qualification_policy as policy
    import official_legacy_precedence as precedence
    import financial_evidence_currency_refresh as refresh
    for name in ('EvidenceSpan','_span','qualify_document_metadata','canonical_json','stable_id',
                 'REQUIRED_METADATA','METADATA_QUALIFIED','METADATA_BLOCKED'):
        assert getattr(filing,name) is getattr(envelope,name)
    assert refresh.qualify_document_metadata is envelope.qualify_document_metadata
    assert ocr.ROW_LABEL_CONTRACT is rows.ROW_LABEL_CONTRACT
    assert ocr._identity_fold is rows._identity_fold
    assert ocr._identity_fold.__annotations__ == baseline('official_financial_ocr_table_evidence.py')._identity_fold.__annotations__
    assert ingress.LINE_CODE_IDENTITY_CONFLICTS is rows.LINE_CODE_IDENTITY_CONFLICTS
    assert precedence.POLICY_QUALIFIED is policy.QUALIFIED is states.QUALIFIED
    assert precedence.METADATA_QUALIFIED is envelope.METADATA_QUALIFIED
    assert inspect.signature(ocr.row_label_supports_metric) == inspect.signature(baseline('official_financial_ocr_table_evidence.py').row_label_supports_metric)
    span = envelope._span({'citation_id':'owned','text':'explicit','source_page':1,'document_sha256':'a'*64},'a'*64)
    assert isinstance(span,filing.EvidenceSpan) and span.to_dict()['citation_id']=='owned'
    with pytest.raises(Exception) as error:
        span.text = 'changed'
    from dataclasses import FrozenInstanceError
    assert type(error.value) is FrozenInstanceError


def test_known_legacy_and_lower_owner_monkeypatch_slots(monkeypatch):
    monkeypatch.setitem(rows.ROW_LABEL_CONTRACT,'owned-test',{'any_of':('synthetic',),'forbidden':()})
    assert ocr.ROW_LABEL_CONTRACT is rows.ROW_LABEL_CONTRACT
    monkeypatch.setattr(ocr,'_normalize',lambda value:'synthetic')
    assert ocr.row_label_supports_metric('owned-test','other') is True
    assert rows.row_label_supports_metric('owned-test','other') is False
    assert rows.row_label_supports_metric('owned-test','other',normalizer=ocr._normalize) is True
    candidate = metadata_cases()[0]
    monkeypatch.setattr(envelope,'stable_id',lambda value:'owned-identity-slot')
    assert filing.qualify_document_metadata(candidate)['evidence_envelope_id']=='owned-identity-slot'


def test_lazy_admission_and_ingress_use_lower_row_rule(monkeypatch):
    import reviewed_interim_canonical_ingress as ingress
    row, context = proved_fixture()
    monkeypatch.setattr(rows,'row_label_supports_metric',lambda *args,**kwargs:False)
    result = filing.admit_official_financial_fact(row,**context)
    assert result['state']=='BLOCKED' and 'METRIC_LITERAL_LABEL_NOT_SUPPORTED' in result['reason_codes']
    component={'canonical_metric':'investment_property_disposal_result','period_type':'interim',
        'context_kind':'EARNINGS_QUALITY_COMPONENT','component_contract':ingress.EARNINGS_COMPONENT_CONTRACT,
        'ingress_contract':ingress.CONTRACT_VERSION,'projection_currency_policy':'VND_EXISTING_CONTRACT',
        'currency':'VND','statement_family':'income_statement','line_code':'21','citation_id':'owned',
        'reported_component_evidence':{'citation_id':'owned','literal_label':'thanh ly bat dong san dau tu'}}
    assert ingress.earnings_component_is_admitted(component) is False


def test_independent_e5_consumer_artifacts_exact_bytes_hashes_and_semantics():
    output=consumer_outputs()
    payload=json.dumps(output,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    assert json.loads(payload) == FIXTURE['outputs']
    assert len(payload)==141591
    assert hashlib.sha256(payload).hexdigest()==FIXTURE['compact_sha256']=='62862f936b6e6659303536b95d6c18b739bf41d03eecdf672860b00cf0a5826b'
    assert any(item['state']=='ADMITTED' for item in output['admission'])
    assert any(item['state']=='UNKNOWN' for item in output['admission'])
    assert any(item['state']=='BLOCKED' for item in output['admission'])
    assert all(item['qualification_state']=='QUALIFIED' for item in output['extraction'])


@pytest.mark.parametrize('period',['2025','2026-H1','2026-Q2'])
@pytest.mark.parametrize('physical',['intact','tampered','missing'])
def test_retained_registration_parser_absence_and_source_failures_match_original(tmp_path,monkeypatch,period,physical):
    from stocklookup_core.evidence import official_document_qualification as registration
    row, context=proved_fixture(period,native_pdf=True)
    if physical!='missing':
        (tmp_path/'fixture.pdf').write_bytes(context['retained_bytes'] if physical=='intact' else b'owned invalid PDF')
    monkeypatch.setitem(sys.modules,'pypdf',None)
    kwargs={'evidence_root':tmp_path,'registry':context['registry'],'verified_at':'2026-10-08T00:00:00Z'}
    current=registration.qualify_retained_document(context['source_record'],**kwargs)
    old=baseline('stocklookup_core/evidence/official_document_qualification.py').qualify_retained_document(context['source_record'],**kwargs)
    assert current.to_dict()==old.to_dict()
    assert current.qualification_status==registration.QUALIFICATION_FAILURE_STATUS
    assert 'DOCUMENT_METADATA_OR_ASSURANCE_PROOF_UNAVAILABLE' in current.qualification_reasons


@pytest.mark.parametrize('period',['2025','2026-H1','2026-Q2'])
def test_optional_native_parser_registration_exact_original(tmp_path,period):
    pytest.importorskip('pypdf')
    from stocklookup_core.evidence import official_document_qualification as registration
    row,context=proved_fixture(period,native_pdf=True)
    (tmp_path/'fixture.pdf').write_bytes(context['retained_bytes'])
    kwargs={'evidence_root':tmp_path,'registry':context['registry'],'verified_at':'2026-10-08T00:00:00Z'}
    current=registration.qualify_retained_document(context['source_record'],**kwargs)
    old=baseline('stocklookup_core/evidence/official_document_qualification.py').qualify_retained_document(context['source_record'],**kwargs)
    assert current.to_dict()==old.to_dict()
    assert current.qualification_status==registration.QUALIFICATION_SUCCESS_STATUS


@pytest.mark.parametrize('order',['legacy','lower'])
def test_import_order_and_legacy_class_lookup(order):
    script='''import sys
if ORDER=='legacy':
 import official_financial_filing_evidence as old
 import official_financial_ocr_table_evidence as ocr
from stocklookup_core.evidence import financial_metadata_envelope as new,financial_row_identity as rows
import official_financial_filing_evidence as old,official_financial_ocr_table_evidence as ocr
assert old.EvidenceSpan is new.EvidenceSpan and old.qualify_document_metadata is new.qualify_document_metadata
assert ocr.ROW_LABEL_CONTRACT is rows.ROW_LABEL_CONTRACT and ocr._identity_fold is rows._identity_fold
import pickle
value=new.EvidenceSpan('owned','a'*64,1,'literal','owned')
assert pickle.loads(pickle.dumps(value))==value
# Historical pickle lookup still finds the same class through the legacy alias.
assert pickle.loads(b'cofficial_financial_filing_evidence\\nEvidenceSpan\\n.') is new.EvidenceSpan
'''
    subprocess.run([sys.executable,'-c','ORDER='+repr(order)+'\n'+script],cwd=ROOT,capture_output=True,check=True)


def test_lower_contracts_load_without_admission_extraction_or_policy():
    script='''import sys
from stocklookup_core.evidence import financial_metadata_envelope,financial_row_identity
from stocklookup_core.financial import qualification_states
assert not {'official_financial_ocr_table_evidence','financial_evidence_currency_refresh','official_financial_filing_evidence','reviewed_interim_canonical_ingress','official_legacy_precedence','canonical_financial_qualification_policy','semantic_evidence_bridge'} & set(sys.modules)
'''
    subprocess.run([sys.executable,'-c',script],cwd=ROOT,capture_output=True,check=True)
    for name in ('stocklookup_core/evidence/financial_metadata_envelope.py','stocklookup_core/evidence/financial_row_identity.py','stocklookup_core/financial/qualification_states.py'):
        for node in ast.walk(ast.parse((ROOT/name).read_text())):
            if isinstance(node,ast.ImportFrom):
                assert node.module.startswith('stocklookup_core.evidence.financial_document_text') or node.module.split('.')[0] in sys.stdlib_module_names
            if isinstance(node,ast.Import):
                assert all(item.name.split('.')[0] in sys.stdlib_module_names for item in node.names)


def test_financial_cycle_cuts_and_restoration_are_real_daily_component_unchanged():
    from tools import check_architecture as guard
    from tests.architecture_checkpoint_fixture import checkpoint_graph
    old=checkpoint_graph(ROOT,BASE,guard)
    graph=guard.scan(ROOT)
    old_groups=guard.cyclic_components(old['edges'],eager=False)[1]
    groups=guard.cyclic_components(graph['edges'],eager=False)[1]
    financial=next(s for s in old_groups if 'official_financial_ocr_table_evidence' in s)
    assert len(financial)==10
    assert max(len(s) for s in groups if set(s)&set(financial))<=4
    assert sum(map(len,groups))<=41
    daily=next(s for s in old_groups if 'canonical_daily_operation' in s)
    assert daily in groups and len(daily)==10
    assert guard.cyclic_components(old['edges'],eager=True)[1]==guard.cyclic_components(graph['edges'],eager=True)[1]
    cuts=[('official_financial_filing_evidence','official_financial_ocr_table_evidence'),
        ('official_financial_filing_evidence','reviewed_interim_canonical_ingress'),
        ('reviewed_interim_canonical_ingress','official_financial_ocr_table_evidence'),
        ('historical_net_income_semantic_correction','official_financial_ocr_table_evidence'),
        ('official_legacy_precedence','canonical_financial_qualification_policy'),
        ('official_legacy_precedence','official_financial_filing_evidence')]
    assert not any(tuple(e[:2]) in cuts for e in graph['edges'])
    restored=list(graph['edges'])+[e for e in old['edges'] if tuple(e[:2]) in cuts]
    restored_groups=guard.cyclic_components(restored,eager=False)[1]
    assert financial in restored_groups and sum(map(len,restored_groups))==47


def test_frozen_sources_e5_foundations_and_financial_authority_pins_are_unchanged():
    from tools import qualify_e4_infrastructure as identity
    protected={path for _,path in identity.V1_SOURCES}|set(identity.V2_SOURCES)
    frozen=json.loads((ROOT/'tests/fixtures/e2e3_frozen_sources.json').read_text())['source_sha256_lf']
    protected |= set(frozen)
    protected |= {'stocklookup_core/evidence/field_identity.py','stocklookup_core/evidence/financial_document_text.py',
        'stocklookup_core/evidence/corporate_event_temporality.py','stocklookup_core/evidence/research_output_fields.py',
        'config/official_financial_legacy_row_admission_v1.json','config/official_source_registry.json',
        'official_financial_period_identity.py','official_financial_assurance_evidence.py','financial_statement_unit_resolution.py',
        'financial_evidence_currency_contract.py','official_financial_pdf_page_evidence.py'}
    # Owner-reviewed exceptions keep an exact pin, re-anchored from the historical base bytes.
    amended=json.loads((ROOT/'tests/fixtures/frozen_source_reviewed_amendments.json').read_text(encoding='utf-8'))['amendments']
    assert not set(amended)&({path for _,path in identity.V1_SOURCES}|set(identity.V2_SOURCES))
    for path in sorted(protected):
        original=subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT).replace(b'\r\n',b'\n')
        from tools.verify_retention_reader_transition import historical_bytes
        current=historical_bytes(ROOT, path)
        if path in amended:
            assert hashlib.sha256(original).hexdigest()==amended[path]['base_sha256_lf'],path
            assert hashlib.sha256(current).hexdigest()==amended[path]['sha256_lf']==frozen[path],path
            continue
        assert current==original,path
    from tools.verify_retention_reader_transition import legacy_source_identity
    assert legacy_source_identity(ROOT,version='v1')['code_digest']=='fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46'
    assert legacy_source_identity(ROOT,version='v2')['code_digest']=='07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567'
