"""Read-only retained-cohort acceptance; writes only to an explicit separate output directory."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stocklookup_core.evidence.artifact_stream import source_hash, stream_artifact
from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.valuation import current_research_valuation_context as valuation
from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import content_identity as raw_identity


def retained_cohort(path: Path, session: str) -> dict:
    artifact = json.loads(path.read_text(encoding='utf-8'))
    body = {k:v for k,v in artifact.items() if k not in ('artifact_identity','artifact_sha256')}
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest != artifact.get('artifact_sha256'):
        raise ValueError('VN30_MEMBERSHIP_ARTIFACT_IDENTITY_MISMATCH')
    captures = {c['surface']: c for c in artifact['captures']}
    for surface in ('index_catalog', 'vn30_constituents'):
        capture = captures[surface]
        source = (path.parent / capture['relative_path']).resolve()
        if path.parent.resolve() not in source.parents or source_hash(source) != capture['sha256']:
            raise ValueError('VN30_MEMBERSHIP_RAW_HASH_OR_PATH_MISMATCH')
        if capture['retrieved_at'][:10] > session:
            raise ValueError('VN30_MEMBERSHIP_AFTER_TARGET_SESSION')
    members = artifact['datasets']['hose_public_vn30_membership/v1']
    tickers = sorted(r['ticker'] for r in members)
    if len(tickers) != len(set(tickers)) or len(tickers) != artifact['coverage']['index_tickers']:
        raise ValueError('VN30_MEMBERSHIP_ACCOUNTING_MISMATCH')
    if any(r['source_identity'] != captures['vn30_constituents']['sha256'] for r in members):
        raise ValueError('VN30_MEMBERSHIP_ROW_LINEAGE_MISMATCH')
    return {'tickers': tickers, 'cohort_label': 'RETAINED_HOSE_VN30_OBSERVATION_NOT_EXACT_TARGET_MEMBERSHIP',
            'membership_observation_time': captures['vn30_constituents']['retrieved_at'],
            'membership_as_of_date': artifact['as_of_date'], 'target_session': session,
            'membership_artifact_identity': artifact['artifact_identity'],
            'membership_raw_sha256': captures['vn30_constituents']['sha256'],
            'exact_target_membership_qualified': False, 'membership_effective_intervals': 'UNKNOWN'}


def matrix(context: dict) -> list[dict]:
    return [{'ticker': ticker, 'metric': mid, 'method': m.get('method'), 'input_source':
             m['source_lineage'].get('source') or m['source_lineage'].get('method') or 'NOT_RETAINED',
             'fitness': m['fitness'], 'producer_fitness': m['producer_fitness'], 'value': m.get('value'),
             'period': json.dumps(m['period_identity']), 'scope': json.dumps(m['statement_scope']),
             'currency': m['currency'], 'scale': m['scale'], 'share_basis': m['share_basis'],
             'freshness': m['freshness']['freshness_status'], 'blockers': json.dumps(m['reason_codes']),
             'freshness_reasons': json.dumps(m['freshness'].get('reason_codes', [])),
             'peer_universe': m['peer_universe'],
             'peer_status': m['peer_context']['status'], 'peer_count': m['peer_context'].get('peer_count', 0)}
            for ticker, r in context['records'].items() for mid, m in r['metrics'].items()]


def counts(rows: list[dict]) -> dict:
    return {mid: {'available': sum(r['value'] is not None and r['fitness'] in
             ('READY','RESEARCH_PROXY','STALE_BUT_RESEARCH_USABLE') for r in rows if r['metric'] == mid),
             'fitness': dict(sorted(Counter(r['fitness'] for r in rows if r['metric'] == mid).items())),
             'qualified_peer_values': sum(r['peer_status'] == 'READY_RESEARCH_ONLY' for r in rows if r['metric'] == mid)}
            for mid in sorted({r['metric'] for r in rows})}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--membership-artifact', required=True, type=Path)
    parser.add_argument('--engine-artifact', required=True, type=Path)
    parser.add_argument('--evaluated-valuation-artifact', required=True, type=Path)
    parser.add_argument('--raw-valuation-artifact', required=True, type=Path)
    parser.add_argument('--session', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    inputs = [args.membership_artifact, args.engine_artifact, args.evaluated_valuation_artifact, args.raw_valuation_artifact]
    output = args.output.resolve()
    if any(p.resolve() == output or output in p.resolve().parents or p.resolve().parent == output for p in inputs):
        raise ValueError('OUTPUT_MUST_BE_SEPARATE_FROM_INPUTS')
    hashes = {str(p.resolve()): source_hash(p) for p in inputs}
    cohort = retained_cohort(args.membership_artifact, args.session)
    names = set(cohort['tickers'])
    financial = json.loads(args.engine_artifact.read_text(encoding='utf-8'))
    if engine.content_identity(financial)['artifact_identity'] != financial.get('artifact_identity'):
        raise ValueError('FINANCIAL_ENGINE_IDENTITY_MISMATCH')
    rows = {}
    meta, digest, count = stream_artifact(args.evaluated_valuation_artifact,
        excluded={'artifact_sha256','artifact_identity','requested_at'}, on_record=lambda t,r: rows.update({t:r}) if t in names else None)
    if meta.get('artifact_sha256') != digest or set(rows) != names:
        raise ValueError('VALUATION_IDENTITY_OR_COHORT_COVERAGE_MISMATCH')
    raw = json.loads(args.raw_valuation_artifact.read_text(encoding='utf-8'))
    if raw_identity(raw)['artifact_identity'] != raw.get('artifact_identity'):
        raise ValueError('RAW_VALUATION_IDENTITY_MISMATCH')
    validate_source_binding(meta, raw, args.session)
    before_inputs = copy.deepcopy(rows)
    after = valuation.build_metric_research_context(rows=rows, engine_artifact=financial,
        decision_session=args.session, raw_valuation_records=raw['records'],
        source_valuation_identity=meta['artifact_identity'])
    assert rows == before_inputs
    for ticker in names:
        for mid in valuation.METRIC_RESEARCH_METHODS:
            if mid in rows[ticker]['methods']:
                assert after['records'][ticker]['metrics'][mid]['source_lineage'] == rows[ticker]['methods'][mid]
        for mid, fid in valuation.RETURN_FEATURES.items():
            feature = (financial['records'].get(ticker, {}).get('features') or {}).get(fid)
            if rows[ticker].get('entity_class') == 'corporate' and feature:
                assert after['records'][ticker]['metrics'][mid]['source_lineage'] == feature
    # Baseline method inventory, not a fictitious historical publication: every existing
    # value comes from the verified original owner. Only the new formula is absent before.
    before = copy.deepcopy(after)
    for r in before['records'].values():
        m = r['metrics'][valuation.ROE_REPORTED_PERIOD]
        if m['fitness'] != 'NOT_APPLICABLE':
            m.update(fitness='BLOCKED_BY_EVIDENCE', producer_fitness='BLOCKED_BY_EVIDENCE', value=None,
                     reason_codes=['REPORTED_PERIOD_RETURN_PROJECTION_NOT_IMPLEMENTED_BEFORE_MILESTONE'],
                     peer_context={'status': 'NOT_COMPARABLE', 'reason': 'METHOD_NOT_IMPLEMENTED'})
    before_matrix, after_matrix = matrix(before), matrix(after)
    gains = [{'ticker': a['ticker'], 'metric': a['metric'], 'fitness': a['fitness'], 'value': a['value']}
             for b,a in zip(before_matrix,after_matrix) if b['value'] is None and a['value'] is not None]
    for p in inputs:
        assert source_hash(p) == hashes[str(p.resolve())]
    summary = {'cohort': cohort, 'before': counts(before_matrix), 'after': counts(after_matrix), 'gains': gains,
               'retained_input_hashes_unchanged': hashes, 'verified_valuation_source_identity': meta['artifact_identity'],
               'verified_full_valuation_denominator': count, 'after_identity': after['artifact_identity'],
               'existing_numerical_and_provenance_parity': True, 'newly_qualified_source_evidence': 0,
               'production_daily_or_runtime_write': False, 'authority_promoted': False,
               'baseline_semantics': 'SAME_INPUT_OWNER_METHOD_INVENTORY_NOT_REWRITTEN_HISTORICAL_SESSION'}
    output.mkdir(parents=True, exist_ok=True)
    for label, data in [('before',before_matrix),('after',after_matrix)]:
        with (output/(label+'-matrix.csv')).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    (output/'metric-research-context.json').write_text(json.dumps(after,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (output/'acceptance.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'gains': gains, 'cohort_count': len(names), 'identity': after['artifact_identity']}))
    return 0


def validate_source_binding(evaluated: dict, raw: dict, session: str) -> None:
    if raw.get('valuation_session') != session:
        raise ValueError('VALUATION_SESSION_MISMATCH')
    if evaluated.get('source_valuation_identity') != raw.get('artifact_identity'):
        raise ValueError('VALUATION_SOURCE_IDENTITY_MISMATCH')


if __name__ == '__main__':
    raise SystemExit(main())
