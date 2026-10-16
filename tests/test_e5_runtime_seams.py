"""Accepted E4 execution parity, shared contracts and adversarial dependency proofs."""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

import corporate_currency_rollforward as rollforward
import field_temporal_contract as legacy_field
import official_financial_ocr_table_evidence as ocr
from stocklookup_core.evidence import corporate_event_temporality as event_time
from stocklookup_core.evidence import field_identity, financial_document_text, research_output_fields
from e5_seam_fixtures import consumer_outputs

ROOT = Path(__file__).resolve().parents[1]
BASE = 'e9ee2fe135e9e529b60f11ab97f30fc6441e6e24'
FIXTURE = json.loads((ROOT/'tests/fixtures/e5_runtime_seams_baseline.json').read_text(encoding='utf-8'))
ALLOWED_LIBRARIES = {'corporate_currency_rollforward.py','field_temporal_contract.py','official_financial_ocr_table_evidence.py',
                    'official_financial_period_identity.py','stocklookup_core/decision/human_ai_decision_evidence_packet.py'}


def baseline(relative):
    assert relative in ALLOWED_LIBRARIES  # reviewed library modules only, never CLI runners
    name = '_e5_baseline_' + relative.replace('/', '_').replace('.', '_')
    if name not in sys.modules:
        source = subprocess.check_output(['git','show',BASE+':'+relative],cwd=ROOT)
        module = types.ModuleType(name)
        sys.modules[name] = module  # dataclasses preserve ordinary module lookup
        exec(compile(source,relative,'exec'),module.__dict__)
    return sys.modules[name]


def outcome(call):
    try:
        return ('ok',call())
    except Exception as error:
        return ('error',type(error),str(error))


CUTOFF = datetime.fromisoformat('2026-10-08T15:00:00+07:00')
CONTEXTS = [
    {}, {'all_current_universe_event_records':[]}, {'all_current_universe_event_records':None},
    {'all_current_universe_event_records':{},'excluded_noncurrent_or_official_only_event_records':[]},
    {'all_current_universe_event_records':[],'excluded_noncurrent_or_official_only_event_records':None},
] + [{'all_current_universe_event_records':[row]} for row in [
    None, {}, {'official_observed_at':None}, {'official_observed_at':False},
    {'official_observed_at':'malformed'}, {'official_observed_at':'2026-10-08T15:00:00'},
    {'official_observed_at':'2026-10-08T08:00:00Z'}, {'official_observed_at':'2026-10-08T15:00:00+07:00'},
    {'official_observed_at':'2026-10-08T08:00:00.000001Z'},
    {'official_observed_at':'2026-10-07T08:00:00Z','published_at':None},
    {'official_observed_at':'2026-10-07T08:00:00Z','published_at':'2026-10-09T00:00:00Z'},
    {'official_observed_at':'2026-10-07T08:00:00Z','published_at':'bad'},
]] + [{'all_current_universe_event_records':[], 'excluded_noncurrent_or_official_only_event_records':[{'official_observed_at':'bad'}]}]


@pytest.mark.parametrize('context',CONTEXTS)
@pytest.mark.parametrize('cutoff',[CUTOFF,CUTOFF.astimezone(timezone.utc),datetime(2026,10,8),None])
def test_event_cutoff_exact_original_results_errors_and_no_mutation(context,cutoff):
    before = copy.deepcopy(context)
    original = baseline('corporate_currency_rollforward.py').context_known_by
    assert outcome(lambda:event_time.context_known_by(context,cutoff)) == outcome(lambda:original(context,cutoff))
    assert context == before


TEXTS = ['', 'Tiếng Việt', "LU'U CHUYỆN TIỀN TỆ", 'BÁO CÁO SOÁT XÉT', 'Provisi²ns', 'Provisions',
         'chưa được kiểm toán', 'Không được soát xét', 'not yet independently audited',
         'independent auditors’ report', 'đ Đ ĐIỀU KIỆN', '０１２３', '²0²6', 'a\t\nb’,c',None,42,b'bytes']


@pytest.mark.parametrize('text',TEXTS)
def test_normalizer_exact_original_strings_and_errors(text):
    old = baseline('official_financial_ocr_table_evidence.py')._normalize
    assert outcome(lambda:financial_document_text._normalize(text)) == outcome(lambda:old(text))


@pytest.mark.parametrize('text',[t for t in TEXTS if isinstance(t,str)])
def test_assurance_negation_consumer_parity(text):
    import official_financial_period_identity as current
    old = baseline('official_financial_period_identity.py')
    assert current.recognize_audit_or_review(text) == old.recognize_audit_or_review(text)
    assert current.assurance_language_is_negative(text) == old.assurance_language_is_negative(text)


FIELD_VALUES = [None,{},[],{'name':'Tiếng Việt','zero':-0.0},{'record':[float('nan'),1,('nested',)]},
                datetime(2026,10,8,8,tzinfo=timezone.utc),{'value':b'bytes'},{'value':complex(1,2)},
                {'z':1,'a':2},{1:1},{'a':1,2:2},float('inf'),float('-inf'),{'surrogate':'\ud800'},
                {'records':{str(i):{'text':'ấ'*65537,'zero':-0.0} for i in range(3)}}]


@pytest.mark.parametrize('value',FIELD_VALUES)
@pytest.mark.parametrize('name',['canonical_json','stable_id'])
def test_field_identity_exact_original_bytes_hash_and_error_contract(value,name):
    old = getattr(baseline('field_temporal_contract.py'),name)
    candidate = getattr(field_identity,name)
    assert outcome(lambda:candidate(value)) == outcome(lambda:old(value))
    assert outcome(lambda:candidate(value)) == outcome(lambda:candidate(value))


def test_field_encoding_is_distinct_from_strict_artifact_encoding():
    from stocklookup_core.evidence import bounded_json
    assert field_identity.canonical_json({'nan':float('nan')}) == '{"nan":null}'
    assert field_identity.canonical_json({'bytes':b'a'}) == '{"bytes":"b\'a\'"}'
    with pytest.raises(ValueError):
        bounded_json.canonical_bytes({'nan':float('nan')})
    with pytest.raises(TypeError):
        bounded_json.canonical_bytes({'bytes':b'a'})


def test_original_compatibility_functions_and_consumer_bindings_are_shared_objects():
    assert rollforward.context_known_by is event_time.context_known_by
    assert ocr._normalize is financial_document_text._normalize
    for name in ('_sanitize_for_json','canonical_json','stable_id'):
        assert getattr(legacy_field,name) is getattr(field_identity,name)
    from stocklookup_core.decision import human_ai_decision_evidence_packet as packet
    assert packet.FORBIDDEN is research_output_fields.FORBIDDEN
    assert packet.FORBIDDEN == baseline('stocklookup_core/decision/human_ai_decision_evidence_packet.py').FORBIDDEN
    for module in ('stocklookup_core.evidence.official_document_qualification',
                   'stocklookup_core.valuation.market_wide_current_valuation_input_scaleout',
                   'stocklookup_core.valuation.p3f_current_market_valuation',
                   'stocklookup_core.financial.fundamental_research_cohort_scaleout',
                   'stocklookup_core.portfolio.current_portfolio_risk_envelope',
                   'stocklookup_core.research.prospective_research_learning',
                   'stocklookup_core.decision.current_daily_decision_research_product'):
        assert importlib.import_module(module).stable_id is field_identity.stable_id


def test_actual_consumers_match_separately_executed_accepted_e4_fixture():
    assert FIXTURE['source_ref'] == BASE
    current = consumer_outputs()
    assert current == FIXTURE['outputs']
    raw = json.dumps(current,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    assert hashlib.sha256(raw).hexdigest() == FIXTURE['canonical_sha256']


@pytest.mark.parametrize('field',research_output_fields.FORBIDDEN+('freshness_score','capital_verdict'))
def test_financial_packet_nested_forbidden_fields_still_fail_closed(field):
    from stocklookup_core.financial import financial_reporting_currency as currency
    value = copy.deepcopy(FIXTURE['outputs']['currency'])
    value['records']['FPT']['frozen_provider_baseline'][field] = 1
    value.update(currency.identity(value))
    with pytest.raises(ValueError,match='FINANCIAL_CURRENCY_FORBIDDEN_VERDICT'):
        currency.packet_context(value,ticker='FPT')


def test_lazy_consumer_monkeypatches_and_existing_mutable_contract_are_live(monkeypatch):
    import current_official_event_context as event
    import official_financial_assurance_evidence as assurance
    import official_financial_period_identity as period
    value = copy.deepcopy(FIXTURE['outputs']['event_projection'])
    monkeypatch.setattr(event_time,'context_known_by',lambda *args:False)
    with pytest.raises(ValueError,match='NOT_KNOWN_BY_SESSION_CUTOFF'):
        event.project_session_context(value,session='2026-10-08',cutoff='2026-10-08T15:00:00+07:00')
    monkeypatch.setattr(financial_document_text,'_normalize',lambda *args:'unaudited')
    assert assurance._normalize('any') == 'unaudited'
    assert period.assurance_language_is_negative('any') is True
    # Existing OCR binding stays independently patchable, and its mutable row
    # policy remains the exact same object rather than a copied configuration.
    policy = ocr.ROW_LABEL_CONTRACT
    monkeypatch.setitem(policy,'synthetic_metric',{'any_of':('synthetic',),'forbidden':()})
    assert ocr.ROW_LABEL_CONTRACT is policy
    monkeypatch.setattr(ocr,'_normalize',lambda text:'synthetic')
    assert ocr.row_label_supports_metric('synthetic_metric','anything') is True
    monkeypatch.setattr(legacy_field,'stable_id',lambda value:'patched-existing-field-slot')
    field = legacy_field.TemporalField('close',25.5,None,None,'missing',False,'TIMESTAMP_MISSING_OR_INVALID')
    assert field.field_id == 'patched-existing-field-slot'
    # The shared implementation follows its new owner's helper globals.
    monkeypatch.setattr(field_identity,'canonical_json',lambda value:'"patched-owner"')
    assert field_identity.stable_id({}) == hashlib.sha256(b'"patched-owner"').hexdigest()


@pytest.mark.parametrize('first',['legacy','foundation'])
def test_import_orders_shared_exceptions_and_no_freshness_relocation(first):
    script = '''import sys
from datetime import datetime
if FIRST == 'legacy':
 import field_temporal_contract as old
 import corporate_currency_rollforward as roll
 import official_financial_ocr_table_evidence as ocr
from stocklookup_core.evidence import field_identity as new, corporate_event_temporality as time, financial_document_text as text
import field_temporal_contract as old, corporate_currency_rollforward as roll, official_financial_ocr_table_evidence as ocr
from freshness_history import RULES
assert old.stable_id is new.stable_id and old.canonical_json is new.canonical_json
assert roll.context_known_by is time.context_known_by and ocr._normalize is text._normalize
assert old.RULES is RULES
for function in (roll.context_known_by,time.context_known_by):
 try: function({},datetime(2026,10,8))
 except ValueError as error: assert type(error) is ValueError and str(error)=='KNOWLEDGE_TIME_MUST_BE_TIMEZONE_AWARE'
 else: raise AssertionError('naive cutoff accepted')
'''
    subprocess.run([sys.executable,'-c',"FIRST="+repr(first)+'\n'+script],cwd=ROOT,check=True,capture_output=True)


def test_foundations_load_without_orchestration_or_freshness_side_effects():
    script = '''import sys
from stocklookup_core.evidence import field_identity,corporate_event_temporality,financial_document_text,research_output_fields
assert not {'corporate_currency_rollforward','current_official_event_context','field_temporal_contract','freshness_history','official_financial_ocr_table_evidence','official_financial_assurance_evidence','stocklookup_core.decision.human_ai_decision_evidence_packet'} & set(sys.modules)
'''
    subprocess.run([sys.executable,'-c',script],cwd=ROOT,check=True,capture_output=True)
    for filename in ('field_identity.py','corporate_event_temporality.py','financial_document_text.py','research_output_fields.py'):
        tree = ast.parse((ROOT/'stocklookup_core/evidence'/filename).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                assert all(name.name.split('.')[0] in sys.stdlib_module_names for name in node.names)
            if isinstance(node,ast.ImportFrom):
                assert node.module.split('.')[0] in sys.stdlib_module_names and node.level==0


def test_cycle_cuts_remain_real_and_restoring_them_restores_coupling():
    from tools import check_architecture as guard
    sources = {p.relative_to(ROOT).as_posix():p.read_text(encoding='utf-8-sig') for p in guard.source_paths(ROOT)}
    graph = guard.scan_sources(sources)
    groups = guard.cyclic_components(graph['edges'],eager=False)[1]
    assert max(map(len,groups)) <= 10
    assert sum(map(len,groups)) <= 47
    cuts = [('current_official_event_context','corporate_currency_rollforward'),
            ('official_financial_assurance_evidence','official_financial_ocr_table_evidence'),
            ('official_financial_period_identity','official_financial_ocr_table_evidence'),
            ('stocklookup_core.financial.financial_reporting_currency','stocklookup_core.decision.human_ai_decision_evidence_packet')]
    assert not any(tuple(edge[:2]) in cuts for edge in graph['edges'])
    restored = list(graph['edges'])+[(left,right,'lazy','static','from') for left,right in cuts]
    assert max(map(len,guard.cyclic_components(restored,eager=False)[1]))==26
    assert sum(map(len,guard.cyclic_components(restored,eager=False)[1])) > sum(map(len,groups))
    # E6 legitimately reduces the separate financial component. Preserve the
    # exact E5 negative control against immutable E5 source, rather than require
    # later improvements to recreate unrelated historical financial cycles.
    from tests.architecture_checkpoint_fixture import checkpoint_graph
    accepted = checkpoint_graph(ROOT,'ad66c6e964845b0b972a29383ae844213107bd98',guard)
    assert sum(map(len,guard.cyclic_components(accepted['edges'],eager=False)[1]))==47
    historical_restored = list(accepted['edges'])+[(left,right,'lazy','static','from') for left,right in cuts]
    assert max(map(len,guard.cyclic_components(historical_restored,eager=False)[1]))==26
    assert sum(map(len,guard.cyclic_components(historical_restored,eager=False)[1]))==65


def test_v1_v2_inputs_provider_bundle_and_tactical_frozen_sources_are_untouched():
    from tools import qualify_e4_infrastructure as identity
    protected = {path for _,path in identity.V1_SOURCES}|set(identity.V2_SOURCES)
    manifest = json.loads((ROOT/'tests/fixtures/e2e3_frozen_sources.json').read_text(encoding='utf-8'))
    protected |= set(manifest['source_sha256_lf'])
    source = (ROOT/'provider_build_manifest.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    bundle = next(node for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='WORKER_SOURCE_FILES' for t in node.targets))
    protected |= set(ast.literal_eval(bundle.value))
    protected |= {'contextual_technical_features.py','volume_and_flow_context.py','technical_structure_context.py'}
    # Owner-reviewed exceptions keep an exact pin, re-anchored from the historical base bytes.
    amended = json.loads((ROOT/'tests/fixtures/frozen_source_reviewed_amendments.json').read_text(encoding='utf-8'))['amendments']
    assert not set(amended) & ({path for _,path in identity.V1_SOURCES}|set(identity.V2_SOURCES))
    for path in sorted(protected):
        original = subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT).replace(b'\r\n',b'\n')
        from tools.verify_retention_reader_transition import historical_bytes
        current = historical_bytes(ROOT, path)
        if path in amended:
            assert hashlib.sha256(original).hexdigest()==amended[path]['base_sha256_lf'],path
            assert hashlib.sha256(current).hexdigest()==amended[path]['sha256_lf']==manifest['source_sha256_lf'][path],path
            continue
        assert current==original,path
    from tools.verify_retention_reader_transition import legacy_source_identity
    assert legacy_source_identity(ROOT,version='v1')['code_digest']=='fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46'
    assert legacy_source_identity(ROOT,version='v2')['code_digest']=='07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567'
