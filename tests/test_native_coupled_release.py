"""Exact coupled acceptance; ordinary dependency gates and source leases remain."""
import json

import pytest
import roadmap_execution_state as res
from tests.test_parallel_domain_control_plane import world, candidate, transition, load, receipt, git, commit


@pytest.fixture
def pair(world):
    a, ah = candidate(world, 'home', 'home.py', provides={'cards': 'v1'})
    assert transition(world, 'home', 'COMPLETE_LOCAL', ah) == 0
    b, bh = candidate(world, 'restage', 'restage.py', dependencies=['home'], consumes={'cards': 'v1'})
    root, base, state_path, run = world
    wt = root.parent / 'joint'
    git(root, 'worktree', 'add', '-qb', 'fixture/joint', str(wt), base)
    git(wt, 'merge', '--no-ff', '-qm', 'exact Home source', ah)
    git(wt, 'merge', '--no-ff', '-qm', 'exact restage source', bh)
    spec = {'schema': 'stocklookup_coupled_source_release/1',
            'checkpoints': {'home': ah, 'restage': bh}, 'fixture_sha': git(wt, 'rev-parse', 'HEAD'),
            'standalone_failures': {'home': {'hermetic-integration': {'status': 'FAIL', 'evidence': 'retained Home-alone restage drops cards'}}}}
    return world, wt, spec


def plan(pair, **kw):
    world, _, spec = pair
    return res.integration_plan(load(world), repo=world[0], main_sha=kw.pop('main', world[1]), coupled_spec=spec, **kw)


def release(pair, review, main):
    world, _, spec = pair
    root, _, _, run = world
    sf, rf = root.parent / 'coupled.json', root.parent / 'receipt.json'
    sf.write_text(json.dumps(spec), encoding='utf-8')
    rf.write_text(json.dumps(review), encoding='utf-8')
    return run('--release-coupled-lanes', '--coupled-spec', str(sf), '--main-sha', main,
               '--review-receipt', str(rf), '--owner-override', '--scope-note', 'explicit Owner pair release', '--agent', 'OwnerIntegrator')


def test_joint_plan_preserves_failed_standalone_and_does_not_release(pair):
    world, _, spec = pair
    before = load(world)
    ordinary = res.integration_plan(before, repo=world[0], main_sha=world[1], candidate_id='restage')
    assert 'LANE_DEPENDENCY_NOT_RELEASED:restage:home' in ordinary['errors']
    p = plan(pair)
    checked = plan(pair, receipts=receipt(p))
    assert checked['errors'] == []
    assert checked['order'] == ['home', 'restage']
    assert checked['coupled_acceptance']['standalone_failures'] == spec['standalone_failures']
    assert checked['coupled_acceptance']['dependency_disposition'] == 'PENDING_ATOMIC_RELEASE_NOT_PROMOTED'
    assert load(world) == before
    assert not checked['merge_authorized'] and not checked['runtime_authorized']


def test_atomic_true_release_after_main_ci_preserves_history_and_leases(pair):
    world, wt, spec = pair
    root = world[0]
    git(root, 'merge', '--no-ff', '-qm', 'approved pair', spec['fixture_sha'])
    main = git(root, 'rev-parse', 'HEAD')
    git(root, 'push', '-q', 'origin', 'main')
    before = load(world)
    r = receipt(plan(pair, main=main))
    r.update(owner_merge_directive='Owner approved exact pair', post_merge_ci_evidence='exact-main CI PASS')
    assert release(pair, r, main) == 0
    after = load(world)
    assert after['development_control']['revision'] == before['development_control']['revision'] + 1
    for old in before['development_control']['lanes']:
        new = res.lane_by_id(after, old['milestone_id'])
        assert new['state'] == 'MERGED_RELEASED' and new['release_sha'] == main
        assert new['history'][:-1] == old['history']
        assert {k:v for k,v in new.items() if k not in ('state','release_sha','history')} == {k:v for k,v in old.items() if k not in ('state','release_sha','history')}
    assert after['development_control']['history'][:-1] == before['development_control']['history']
    assert {k:v for k,v in after.items() if k != 'development_control'} == {k:v for k,v in before.items() if k != 'development_control'}
    assert release(pair, r, main) == 2  # no duplicate/replayed completion


def test_no_release_before_code_on_actual_main(pair):
    before = pair[0][2].read_bytes()
    r = receipt(plan(pair))
    r.update(owner_merge_directive='Owner', post_merge_ci_evidence='claimed CI')
    assert release(pair, r, pair[0][1]) == 2
    assert pair[0][2].read_bytes() == before


def test_source_changed_after_fixture_cannot_release(pair):
    world, _, spec = pair
    git(world[0], 'merge', '--no-ff', '-qm', 'pair', spec['fixture_sha'])
    main = commit(world[0], 'home.py', 'subsequent incompatible source\n')
    git(world[0], 'push', '-q', 'origin', 'main')
    assert any('LANE_COUPLED_RELEASED_SOURCE_CHANGED' in e for e in plan(pair, main=main)['errors'])


def test_wrong_bound_owner_cannot_write_even_after_merge(pair):
    world, _, spec = pair
    sf = world[0].parent / 'spec-owner.json'
    sf.write_text(json.dumps(spec), encoding='utf-8')
    before = world[2].read_bytes()
    assert world[3]('--release-coupled-lanes', '--coupled-spec', str(sf), '--main-sha', world[1],
                    '--agent', 'Other', '--owner-override', '--scope-note', 'Owner') == 2
    assert world[2].read_bytes() == before


@pytest.mark.parametrize('field', ['owner_merge_directive', 'post_merge_ci_evidence'])
def test_release_requires_owner_and_postmerge_ci(pair, field):
    world, _, spec = pair
    git(world[0], 'merge', '--no-ff', '-qm', 'pair', spec['fixture_sha'])
    main = git(world[0], 'rev-parse', 'HEAD')
    git(world[0], 'push', '-q', 'origin', 'main')
    r = receipt(plan(pair, main=main))
    r.update(owner_merge_directive='Owner', post_merge_ci_evidence='CI PASS')
    del r[field]
    before = world[2].read_bytes()
    assert release(pair, r, main) == 2 and world[2].read_bytes() == before


@pytest.mark.parametrize('kind', ['extra-key','one-lane','three-lanes','missing-failure','passing-standalone','unknown-check','unknown-lane','stale-head','extra-source','altered-source','dirty-candidate','missing-review','failed-joint-check','external-dependency','wrong-owner'])
def test_adversarial_coupled_refusals(pair, kind):
    world, wt, spec = pair
    before = world[2].read_bytes()
    review = None
    if kind == 'extra-key': spec['authority_effect'] = 'PROMOTED'
    elif kind == 'one-lane': del spec['checkpoints']['restage']
    elif kind == 'three-lanes': spec['checkpoints']['extra'] = world[1]
    elif kind == 'missing-failure': spec['standalone_failures'] = {}
    elif kind == 'passing-standalone': spec['standalone_failures']['home']['hermetic-integration']['status'] = 'PASS'
    elif kind == 'unknown-check': spec['standalone_failures']['home'] = {'unknown': {'status':'FAIL','evidence':'actual failure'}}
    elif kind == 'unknown-lane': spec['checkpoints'] = {'home':spec['checkpoints']['home'], 'unknown':world[1]}
    elif kind == 'stale-head': spec['checkpoints']['home'] = world[1]
    elif kind == 'extra-source': spec['fixture_sha'] = commit(wt, 'extra.py', 'unreviewed\n')
    elif kind == 'altered-source': spec['fixture_sha'] = commit(wt, 'home.py', 'changed\n')
    elif kind == 'dirty-candidate': (world[0].parent / 'home/home.py').write_text('dirty\n')
    elif kind in ('missing-review','failed-joint-check','wrong-owner'):
        review = receipt(plan(pair))
        if kind == 'missing-review': del review['cross_repo_review']
        if kind == 'failed-joint-check': review['checks']['home']['hermetic-integration']['status'] = 'FAIL'
        if kind == 'wrong-owner': review['reviewed_by'] = 'Other'
    elif kind == 'external-dependency':
        candidate(world, 'external', 'external.py')
        s = load(world)
        res.lane_by_id(s,'restage')['dependencies'].append('external')
        # Deliberately malformed admission fixture only: production never edits state.
        world[2].write_text(json.dumps(s), encoding='utf-8')
        before = world[2].read_bytes()
    try:
        assert plan(pair, receipts=review)['errors']
    except res.RoadmapStateError:
        pass
    assert world[2].read_bytes() == before
