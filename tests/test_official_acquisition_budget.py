from dataclasses import replace
from io import BytesIO
import json

import pytest

from official_acquisition_budget import AcquisitionBudget, AcquisitionLimits, AcquisitionBudgetExceeded
import official_corporate_event_incremental_acquisition as incremental
import hnx_enumerable_universe_kllh_event_disclosure_scaleout as hnx
from test_official_corporate_event_incremental_acquisition import _stocklookup_universe, _make_hnx_fetch, _hose_response


def response(data=b'x'):
    return {'data': data, 'http_status': 200}


def budget(**limits):
    return AcquisitionBudget(replace(AcquisitionLimits(), **limits), clock=lambda: 0)


def call(b, data=b'x', **kw):
    return b.request(lambda url: response(data), 'https://example.invalid/public', surface='test', **kw)


def test_request_exact_then_one_over_never_dispatches():
    b = budget(max_requests=2)
    call(b); call(b)
    with pytest.raises(AcquisitionBudgetExceeded, match='REQUEST_BUDGET_EXHAUSTED'):
        call(b)
    assert b.report()['request_count'] == 2


def test_total_bytes_exact_and_over():
    b = budget(max_total_bytes=4)
    call(b, b'ab'); call(b, b'cd')
    assert b.downloaded_bytes == 4
    with pytest.raises(AcquisitionBudgetExceeded, match='TOTAL_BYTE_BUDGET_EXHAUSTED'):
        call(b)
    over = budget(max_total_bytes=3)
    with pytest.raises(AcquisitionBudgetExceeded, match='TOTAL_BYTE_BUDGET_EXHAUSTED'):
        call(over, b'abcd')
    assert over.downloaded_bytes == 4


def test_per_response_limit():
    b = budget(max_response_bytes=3)
    call(b, b'abc')
    with pytest.raises(AcquisitionBudgetExceeded, match='RESPONSE_BYTE_LIMIT_EXCEEDED'):
        call(b, b'abcd')


def test_page_boundary_never_dispatches_next_page():
    b = budget(max_pages_per_surface=2)
    call(b, page=2)
    with pytest.raises(AcquisitionBudgetExceeded, match='PAGE_BUDGET_EXHAUSTED'):
        call(b, page=3)
    assert len(b.requests) == 1


def test_clock_expires_before_dispatch_and_after_response():
    now = [0]
    b = AcquisitionBudget(replace(AcquisitionLimits(), max_seconds=2), clock=lambda: now[0])
    def fetch(url):
        now[0] = 2
        return response()
    with pytest.raises(AcquisitionBudgetExceeded, match='WALL_CLOCK_BUDGET_EXHAUSTED'):
        b.request(fetch, 'public', surface='test')
    assert b.requests[0]['status'] == 'BUDGET_TERMINATED'
    with pytest.raises(AcquisitionBudgetExceeded):
        call(b)
    assert len(b.requests) == 1


@pytest.mark.parametrize('cap,data,accepted,count', [(4,b'abcd',True,4),(4,b'abcde' * 100,False,5)])
def test_transport_read_is_bounded_and_exact(cap, data, accepted, count):
    b = budget(max_response_bytes=cap)
    stream = BytesIO(data)
    def transport(url, *, _budget):
        return response(_budget.read(stream))
    transport.bounded_transport = True
    if accepted:
        assert b.request(transport, 'public', surface='test')['data'] == data
    else:
        with pytest.raises(AcquisitionBudgetExceeded, match='RESPONSE_BYTE_LIMIT_EXCEEDED'):
            b.request(transport, 'public', surface='test')
    assert b.downloaded_bytes == count
    assert stream.tell() == count


def test_shared_hnx_hose_limit_retained_failure_prior_still_usable(tmp_path, monkeypatch):
    _stocklookup_universe(tmp_path)
    monkeypatch.setattr(hnx, 'fetch', _make_hnx_fetch())
    first = incremental.acquire(tmp_path, session='2026-09-05', hose_fetcher=_hose_response, budget=budget())
    assert first['disposition'] == 'SUCCESS'
    raw = tmp_path / incremental.RAW_STORE_RELATIVE
    original = {p: p.read_bytes() for p in raw.rglob('*') if p.is_file()}
    hose_calls = []
    def hose(url):
        hose_calls.append(url)
        return _hose_response(url)
    failed = incremental.acquire(tmp_path, session='2026-09-06', hose_fetcher=hose, budget=budget(max_requests=8))
    assert failed['disposition'] == 'FAILURE'
    assert failed['failure_kind'] == 'BUDGET_TERMINATED'
    assert failed['budget_usage']['reason'] == 'REQUEST_BUDGET_EXHAUSTED'
    assert failed['budget_usage']['request_count'] == 8
    assert not hose_calls
    assert incremental.latest_successful_session(tmp_path)['acquisition_session'] == '2026-09-05'
    saved = json.loads((tmp_path / incremental.SESSIONS_RELATIVE / '2026-09-06' / incremental.ATTEMPT_FILENAME).read_text(encoding="utf-8"))
    assert saved == failed
    assert all(p.read_bytes() == data for p, data in original.items())
    with pytest.raises(incremental.IncrementalAcquisitionError, match='ALREADY_RETAINED'):
        incremental.acquire(tmp_path, session='2026-09-05', budget=budget())


def test_default_disclosures_absent_and_reports_deterministic(tmp_path, monkeypatch):
    _stocklookup_universe(tmp_path)
    urls = []
    fetch = _make_hnx_fetch()
    def hnx_fetch(url, **kwargs):
        urls.append(url)
        return fetch(url, **kwargs)
    monkeypatch.setattr(hnx, 'fetch', hnx_fetch)
    a = incremental.acquire(tmp_path, session='2026-09-05', hose_fetcher=_hose_response, budget=budget())
    b = incremental.acquire(tmp_path, session='2026-09-06', hose_fetcher=_hose_response, budget=budget())
    for receipt in b['budget_usage']['requests']:
        receipt['requested_url'] = receipt['requested_url'].replace('2026-09-06', '2026-09-05')
    assert a['budget_usage'] == b['budget_usage']
    assert a['budget_usage']['request_count'] == 19
    assert not any(url.endswith(('NextPageTinCPNY','NextPageTinUpCoM')) for url in urls)


def test_declared_hnx_huge_page_count_stops_after_first_response(tmp_path):
    calls = []
    def fetch(url, **kw):
        calls.append(url)
        return {'http_status':200,'data':b'<html>Tong</html>'}
    # Explicit known terminal pagination marker with one row and total 441.
    document = 'Tổng số 441 bản ghi<table><tbody><tr><td>1</td></tr></tbody></table><a onclick="pageNext(441)">x</a>'
    def paged(url, **kw):
        calls.append(url)
        return dict(http_status=200,data=document.encode(),requested_url=url,official_url=url,retrieved_at='2026-10-02T00:00:00Z',content_type='text/html')
    with pytest.raises(AcquisitionBudgetExceeded, match='PAGE_BUDGET_EXHAUSTED'):
        hnx._post_pages(endpoint='/public', surface='disclosures', destination=tmp_path,
                        base_body={}, budget=budget(), fetcher=paged)
    assert len(calls) == 1
    assert len([p for p in tmp_path.rglob('*') if p.is_file()]) == 1  # complete first response retained, dataset still fails


@pytest.mark.parametrize('value', [0,-1,float('inf'),float('nan'),True])
def test_invalid_limits_cannot_disable_bounds(value):
    with pytest.raises(ValueError):
        AcquisitionLimits(max_seconds=value)


def test_redirects_are_not_hidden_requests():
    from official_acquisition_budget import _NoAutomaticRedirect
    with pytest.raises(ValueError, match='REDIRECT_NOT_ADMITTED'):
        _NoAutomaticRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.invalid/')


def test_budget_transport_exception_preserved_not_swallowed(monkeypatch):
    b = budget(max_total_bytes=3)
    monkeypatch.setattr(b, 'open', lambda request: BytesIO(b'1234'))
    with pytest.raises(AcquisitionBudgetExceeded, match='TOTAL_BYTE_BUDGET_EXHAUSTED'):
        b.request(hnx.fetch, 'https://hnx.vn/public', surface='hnx_test')
    assert b.report()['requests'][0]['status'] == 'BUDGET_TERMINATED'


def test_wall_termination_manifest_keeps_prior_success(tmp_path, monkeypatch):
    _stocklookup_universe(tmp_path)
    monkeypatch.setattr(hnx, 'fetch', _make_hnx_fetch())
    incremental.acquire(tmp_path, session='2026-09-05', hose_fetcher=_hose_response, budget=budget())
    now = [0]
    b = AcquisitionBudget(replace(AcquisitionLimits(), max_seconds=1), clock=lambda: now[0])
    now[0] = 1
    a = incremental.acquire(tmp_path, session='2026-09-06', hose_fetcher=_hose_response, budget=b)
    assert a['disposition'] == 'FAILURE'
    assert a['budget_usage']['reason'] == 'WALL_CLOCK_BUDGET_EXHAUSTED'
    assert a['budget_usage']['request_count'] == 0
    assert incremental.latest_successful_session(tmp_path)['acquisition_session'] == '2026-09-05'


def test_explicit_retry_archives_failure_without_automatic_retry(tmp_path, monkeypatch):
    _stocklookup_universe(tmp_path)
    monkeypatch.setattr(hnx, 'fetch', _make_hnx_fetch())
    failed = incremental.acquire(tmp_path, session='2026-09-05', hose_fetcher=_hose_response, budget=budget(max_requests=1))
    success = incremental.acquire(tmp_path, session='2026-09-05', hose_fetcher=_hose_response, budget=budget())
    assert success['disposition'] == 'SUCCESS'
    history = list((tmp_path / incremental.SESSIONS_RELATIVE / '2026-09-05/attempt_history').glob('*.json'))
    assert len(history) == 1
    assert json.loads(history[0].read_text(encoding="utf-8")) == failed


@pytest.mark.parametrize('error,kind', [(ValueError('SOURCE_FETCH_FAILED:test'),'SOURCE_FAILURE'),
    (json.JSONDecodeError('bad','x',0),'PARSE_FAILURE'),
    (ValueError('ROW_COUNT_MISMATCH'),'SEMANTIC_VALIDATION_FAILURE'),
    (ValueError('IMMUTABLE_CONTENT_CONFLICT'),'IMMUTABLE_RETENTION_CONFLICT')])
def test_failure_kinds_are_distinct_and_retained(tmp_path, monkeypatch, error, kind):
    _stocklookup_universe(tmp_path)
    def fail(**kwargs):
        raise error
    monkeypatch.setattr(hnx, 'build', fail)
    a = incremental.acquire(tmp_path, session='2026-09-05', budget=budget())
    assert a['disposition'] == 'FAILURE'
    assert a['failure_kind'] == kind
    assert a['budget_usage']['terminal_state'] == 'WITHIN_LIMITS'


def test_explicit_window_passed_to_existing_route_and_bound_to_manifest(tmp_path, monkeypatch):
    _stocklookup_universe(tmp_path)
    fetch = _make_hnx_fetch()
    bodies = []
    def hnx_fetch(url, **kwargs):
        if 'LTHQ' in url or 'THQUpCoM' in url:
            bodies.append(kwargs['body'])
        return fetch(url, **kwargs)
    monkeypatch.setattr(hnx, 'fetch', hnx_fetch)
    a = incremental.acquire(tmp_path, session='2026-09-05', hose_fetcher=_hose_response,
                            budget=budget(), hnx_rights_window=('2026-09-01','2026-09-10'))
    assert a['disposition'] == 'SUCCESS'
    assert a['hnx_rights_window'] == ['2026-09-01','2026-09-10']
    assert all(body['pFromDate'] == '01/09/2026' and body['pToDate'] == '10/09/2026' for body in bodies)
    hnx_artifact = json.loads((tmp_path / incremental.SESSIONS_RELATIVE / '2026-09-05/hnx_artifact.json').read_text(encoding="utf-8"))
    assert hnx_artifact['rights_event_index']['scope'] == 'EX_DATE_WINDOW'


def test_ignored_window_never_claims_success(tmp_path, monkeypatch):
    _stocklookup_universe(tmp_path)
    monkeypatch.setattr(hnx, 'fetch', _make_hnx_fetch())
    a = incremental.acquire(tmp_path, session='2026-09-05', hose_fetcher=_hose_response,
                            budget=budget(), hnx_rights_window=('2026-09-06','2026-09-10'))
    assert a['disposition'] == 'FAILURE'
    assert a['error_message'] == 'RIGHTS_WINDOW_DATE_BINDING_FAILED'


def test_reversed_window_fails_before_dispatch(tmp_path, monkeypatch):
    _stocklookup_universe(tmp_path)
    monkeypatch.setattr(hnx, 'fetch', lambda *a, **k: pytest.fail('Unexpected dispatch'))
    a = incremental.acquire(tmp_path, session='2026-09-05',budget=budget(),hnx_rights_window=('2026-09-10','2026-09-01'))
    assert a['disposition'] == 'FAILURE'
    assert a['budget_usage']['request_count'] == 0
