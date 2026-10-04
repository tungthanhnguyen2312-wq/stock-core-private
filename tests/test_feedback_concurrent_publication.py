"""Real-process single-winner, pointer, crash and lease-death qualification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import feedback_resource_guard as guard
from feedback_publication_lock import publication_locks
import prospective_feedback_streaming as streaming
from tests.test_prospective_feedback_streaming import _corpus, _add_modern

REPO = Path(__file__).resolve().parents[1]
WORKER = r'''
import json, os, sys, threading
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import prospective_feedback_streaming as s
from feedback_publication_lock import publication_locks
from tools.run_prospective_decision_outcome_feedback import run_streaming
root, out, state, result, status, mode = sys.argv[2:]
if mode == 'start':
    print('READY', flush=True)
    sys.stdin.readline()
with publication_locks(out, status):
    if mode in ('claim', 'death'):
        print('CLAIM', flush=True)
        if mode == 'death':
            threading.Event().wait(300)
        sys.stdin.readline()
        os._exit(91)
    if mode in ('temp', 'artifact'):
        original = s._assemble if mode == 'temp' else s._write_completion
        def crash(*args, **kwargs):
            if mode == 'temp':
                original(*args, **kwargs)
            print(mode.upper(), flush=True)
            sys.stdin.readline()
            os._exit(92)
        if mode == 'temp': s._assemble = crash
        else: s._write_completion = crash
    outcome = run_streaming(root=root, output=out, state_root=state, result=result, status=status)
    print(json.dumps(outcome), flush=True)
    sys.exit(outcome['exit'])
'''


@pytest.fixture
def world(tmp_path):
    root = tmp_path / 'evidence'
    _corpus(root, legacy=1, modern=3)
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    worker = tmp_path / 'worker.py'
    worker.write_text(WORKER, encoding='utf-8')
    yield root, tmp_path, worker
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def command(world, name, mode='normal', *, root=None, output=None, status=None):
    evidence, base, worker = world
    return [sys.executable, str(worker), str(REPO), str(root or evidence), str(output or base / 'out' / 'feedback.json'),
            str(base / ('state-' + name)), str(base / (name + '.result.json')),
            str(status or base / 'shared.status.json'), mode]


def start(world, name, mode='normal', *, env=None, **kwargs):
    return subprocess.Popen(command(world, name, mode, **kwargs), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)


def finish(process, *, send=None, code=0):
    stdout, stderr = process.communicate(send, timeout=90)
    assert process.returncode == code, (stdout, stderr)
    return json.loads(stdout.strip().splitlines()[-1]) if code in (0, 32) else None


def test_same_input_simultaneous_writers_one_built_and_one_reuse(world):
    a, b = start(world, 'a', 'start'), start(world, 'b', 'start')
    assert a.stdout.readline().strip() == b.stdout.readline().strip() == 'READY'
    a.stdin.write('\n'); a.stdin.flush()
    b.stdin.write('\n'); b.stdin.flush()
    results = [finish(p)['payload'] for p in (a, b)]
    assert sorted(r['outcome'] for r in results) == ['ALREADY_COMPLETE', 'BUILT']
    assert len({r['artifact_identity'] for r in results}) == 1
    pointer = json.loads((world[1] / 'shared.status.json').read_text())
    assert pointer['artifact_identity'] == streaming.read_completion(Path(pointer['path']))['artifact_identity']


def test_winner_completes_before_loser_and_existing_complete_retry(world):
    first = finish(start(world, 'a'))['payload']
    output = world[1] / 'out' / 'feedback.json'
    before = output.read_bytes(), output.stat().st_mtime_ns
    for name in ('b', 'retry'):
        result = finish(start(world, name))['payload']
        assert result['outcome'] == 'ALREADY_COMPLETE' and result['artifact_identity'] == first['artifact_identity']
    assert (output.read_bytes(), output.stat().st_mtime_ns) == before


def test_lease_identity_survives_different_contender_temp_environments(world):
    a, b = [], []
    for name, bucket in (('a', a), ('b', b)):
        directory = world[1] / ('temp-' + name)
        directory.mkdir()
        env = {**os.environ, 'TEMP': str(directory), 'TMP': str(directory), 'TMPDIR': str(directory)}
        bucket.append(start(world, name, 'start', env=env))
    processes = a + b
    assert all(p.stdout.readline().strip() == 'READY' for p in processes)
    for p in processes: p.stdin.write('\n'); p.stdin.flush()
    outcomes = [finish(p)['payload']['outcome'] for p in processes]
    assert sorted(outcomes) == ['ALREADY_COMPLETE', 'BUILT']


@pytest.mark.parametrize('mode,signal,exit_code', [('claim', 'CLAIM', 91), ('temp', 'TEMP', 92), ('artifact', 'ARTIFACT', 92)])
def test_crash_at_claim_temp_and_artifact_before_manifest_is_recoverable(world, mode, signal, exit_code):
    p = start(world, 'crash', mode)
    assert p.stdout.readline().strip() == signal
    output = world[1] / 'out' / 'feedback.json'
    assert streaming.read_completion(output) is None
    finish(p, send='\n', code=exit_code)
    result = finish(start(world, 'retry'))['payload']
    assert result['artifact_identity'] == streaming.stream_artifact_identity(output)
    assert result['outcome'] in ('BUILT', 'ALREADY_RETAINED_EQUAL_IDENTITY')
    assert streaming.read_completion(output)
    assert not list(output.parent.glob('.feedback-*'))


def test_changed_input_cannot_replace_complete_or_shared_status(world):
    first = finish(start(world, 'a'))['payload']
    root, base, _ = world
    changed = base / 'changed'
    import shutil
    shutil.copytree(root, changed)
    _add_modern(changed, '2026-02-20', 11)
    output = base / 'out' / 'feedback.json'
    protected = output.read_bytes(), (base / 'shared.status.json').read_bytes()
    conflict = finish(start(world, 'different', root=changed), code=32)['payload']
    assert conflict['reason_code'] == guard.IMMUTABLE_CONFLICT
    assert protected == (output.read_bytes(), (base / 'shared.status.json').read_bytes())
    adjacent = finish(start(world, 'adjacent', root=changed, output=base / 'adjacent' / 'feedback.json'))['payload']
    pointer = json.loads((base / 'shared.status.json').read_text())
    assert pointer['path'] == adjacent['path'] and pointer['input_digest'] == adjacent['input_digest']
    assert first['artifact_identity'] == streaming.read_completion(output)['artifact_identity']


def test_two_processes_publish_adjacent_outputs_to_shared_pointer(world):
    root, base, _ = world
    import shutil
    changed = base / 'changed'
    shutil.copytree(root, changed)
    _add_modern(changed, '2026-02-20', 11)
    a = start(world, 'a', 'start')
    b = start(world, 'b', 'start', root=changed, output=base / 'second' / 'feedback.json')
    assert a.stdout.readline().strip() == b.stdout.readline().strip() == 'READY'
    for p in (a, b): p.stdin.write('\n'); p.stdin.flush()
    results = [finish(p)['payload'] for p in (a, b)]
    pointer = json.loads((base / 'shared.status.json').read_text())
    winner = next(r for r in results if r['path'] == pointer['path'])
    assert pointer == winner
    manifest = streaming.read_completion(Path(pointer['path']))
    assert manifest['input_digest'] == pointer['input_digest']
    assert manifest['artifact_identity'] == pointer['artifact_identity']


def test_corrupted_output_cannot_become_complete(world):
    finish(start(world, 'a'))
    output = world[1] / 'out' / 'feedback.json'
    output.write_bytes(b'partial/corrupted')
    assert streaming.read_completion(output) is None
    result = finish(start(world, 'b'), code=32)['payload']
    assert result['reason_code'] == guard.IMMUTABLE_CONFLICT
    assert output.read_bytes() == b'partial/corrupted'


def test_process_death_releases_lease_and_waiting_contender_recovers(world):
    owner = start(world, 'owner', 'death')
    assert owner.stdout.readline().strip() == 'CLAIM'
    output, status = world[1] / 'out' / 'feedback.json', world[1] / 'shared.status.json'
    with pytest.raises(BlockingIOError):
        with publication_locks(output, status, blocking=False): pass
    contender = start(world, 'contender')
    owner.kill(); owner.communicate(timeout=10)
    assert finish(contender)['payload']['outcome'] == 'BUILT'


def test_timeout_while_lease_held_releases_claim(world):
    policy = guard.ResourcePolicy(3, 1 << 30, 0, 0, 0)
    run = guard.run_bounded(command(world, 'timeout', 'death'), cwd=REPO, policy=policy,
                            result_path=world[1] / 'timeout.result.json')
    assert run['outcome'] == 'TIMEOUT' and run['reaped'] and run['tree_termination_confirmed']
    assert finish(start(world, 'retry'))['payload']['outcome'] == 'BUILT'


def test_cancellation_while_lease_held_reaps_and_releases(world, monkeypatch):
    owner = start(world, 'cancel', 'death')
    assert owner.stdout.readline().strip() == 'CLAIM'
    monkeypatch.setattr(guard.subprocess, 'Popen', lambda *a, **k: owner)
    original = owner.wait
    calls = []
    def cancel(timeout=None):
        if not calls:
            calls.append(True)
            raise KeyboardInterrupt
        return original(timeout=timeout)
    monkeypatch.setattr(owner, 'wait', cancel)
    with pytest.raises(KeyboardInterrupt):
        guard.run_bounded(['already-launched'], cwd=REPO, policy=guard.ResourcePolicy(30, 1 << 30, 0, 0, 0),
                          result_path=world[1] / 'cancel.result.json')
    assert owner.poll() is not None
    monkeypatch.undo()
    assert finish(start(world, 'retry'))['payload']['outcome'] == 'BUILT'
