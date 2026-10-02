from pathlib import Path
import json
import pytest

import tactical_reversal_prospective_shadow_collection as collection
import tactical_prospective_outcome_store as storage
from tools import run_tactical_reversal_prospective_shadow_collection as runner
from test_tactical_reversal_shadow_collection_operationalization import _corpus, _populate, _legacy_mature_all, _tree_bytes, _SESSIONS


def test_legacy_v2_mixed_exact_history_status_and_summary(tmp_path):
    _corpus(tmp_path / "ev")
    for name in ("legacy", "v2"):
        _populate(tmp_path / "ev", tmp_path / name)
    old = _legacy_mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "legacy")
    originals = _tree_bytes(tmp_path / "legacy")
    new = runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "v2")
    assert old == new
    old_store = collection.ProspectiveShadowObservationStore(tmp_path / "legacy")
    new_store = collection.ProspectiveShadowObservationStore(tmp_path / "v2")
    old_index = old_store.build_outcome_store_index()
    new_index = new_store.build_outcome_store_index()
    assert old_index.latest == new_index.latest
    # Mixed duplicates are resolved by the unchanged analytical outcome identity.
    runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "legacy")
    mixed = old_store.build_outcome_store_index()
    assert mixed.latest == new_index.latest
    for oid in mixed.latest:
        assert mixed.history(oid) == old_index.history(oid) == new_index.history(oid)
        assert old_store.latest_outcome_update(oid, index=mixed) == new_index.latest[oid]
    observations = [o for _, o in old_store.iter_validated_observations()]
    assert collection.build_collection_status(observations, mixed.latest) == collection.build_collection_status(observations, new_index.latest)
    assert collection.historical_descriptive_summary(observations, mixed.latest) == collection.historical_descriptive_summary(observations, new_index.latest)
    for path, data in originals.items():
        assert (tmp_path / "legacy" / path).read_bytes() == data


def test_shard_determinism_idempotency_and_conflict(tmp_path):
    _corpus(tmp_path / "ev")
    for name in ("one", "two"):
        _populate(tmp_path / "ev", tmp_path / name)
        runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / name)
    assert _tree_bytes(tmp_path / "one") == _tree_bytes(tmp_path / "two")
    before = _tree_bytes(tmp_path / "one")
    runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "one")
    assert before == _tree_bytes(tmp_path / "one")
    # Changing inputs under an already published session cannot overwrite evidence.
    path = next((tmp_path / "ev" / "operations-review").glob("watchlist-tactical-entry-decision-v1-*/*.json"))
    body = json.loads(path.read_text(encoding="utf-8"))
    body["diagnostic_extra"] = True
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(collection.ProspectiveShadowCollectionError, match="IMMUTABLE_OUTCOME_SESSION_CONFLICT"):
        runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "one")
    assert before == _tree_bytes(tmp_path / "one")


def test_late_tamper_prevents_any_promotion_preserves_old_store(tmp_path):
    _corpus(tmp_path / "ev")
    _populate(tmp_path / "ev", tmp_path / "store")
    files = sorted((tmp_path / "store" / "observations").glob("*.json"))
    body = json.loads(files[-1].read_text(encoding="utf-8"))
    body["ticker"] = "TAMPER"
    files[-1].write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(collection.ProspectiveShadowCollectionError, match="OBSERVATION_CONTENT_IDENTITY_INVALID"):
        runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "store")
    assert not list((tmp_path / "store" / "outcome_sessions").glob("*/manifest.json"))
    assert not list((tmp_path / "store" / "outcome_sessions").glob("*/outcomes.ndjson"))
    assert not list((tmp_path / "store" / "outcome_sessions").glob("*/*.tmp"))
    assert not list((tmp_path / "store" / "outcome_updates").glob("*.json"))


def test_legacy_compaction_warm_corrupt_new_and_same_stat_mutation(tmp_path):
    _corpus(tmp_path / "ev")
    _populate(tmp_path / "ev", tmp_path / "store")
    _legacy_mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "store")
    store = collection.ProspectiveShadowObservationStore(tmp_path / "store")
    cold_metrics, warm_metrics = {}, {}
    cold = store.build_outcome_store_index(metrics=cold_metrics)
    warm = store.build_outcome_store_index(metrics=warm_metrics)
    assert cold.latest == warm.latest
    assert cold_metrics["legacy_json_parses"] > 0
    assert warm_metrics["legacy_json_parses"] == 0
    assert warm_metrics["legacy_compaction_hits"] == 1
    assert warm_metrics["shard_files_opened"] == 1
    (store.root / "_derived_outcome_index" / "legacy.ndjson").write_bytes(b"corrupt")
    assert store.build_outcome_store_index().latest == cold.latest
    oid, observation = next(store.iter_validated_observations())
    new = collection.mature_outcome(observation, [], evaluation_as_of_session="2026-10-01")
    store.persist_outcome_update(oid, new, validated_observation=observation)
    metrics = {}
    changed = store.build_outcome_store_index(metrics=metrics)
    assert changed.latest[oid] == new
    assert metrics["legacy_json_parses"] == cold_metrics["legacy_json_parses"] + 1
    path = store._path_for(new["outcome_update_id"], store.outcomes_dir)
    import os
    before = path.stat()
    data = path.read_bytes().replace(b"2026-10-01", b"2026-10-02")
    path.write_bytes(data)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(collection.ProspectiveShadowCollectionError, match="LEGACY_OUTCOME_CONTENT_IDENTITY_INVALID"):
        store.build_outcome_store_index()


def test_index_reused_and_bound_enforced(tmp_path, monkeypatch):
    _corpus(tmp_path / "ev")
    _populate(tmp_path / "ev", tmp_path / "store")
    runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "store")
    store = collection.ProspectiveShadowObservationStore(tmp_path / "store")
    index = store.build_outcome_store_index()
    monkeypatch.setattr(store, "build_outcome_store_index", lambda **kw: pytest.fail("rediscovered"))
    for oid in index.latest:
        assert store.load_outcome_updates(oid, index=index) == [index.latest[oid]]
    assert store.latest_outcome_updates_by_observation(index=index) == index.latest
    monkeypatch.setattr(storage, "MAX_ROWS", 1)
    with pytest.raises(collection.ProspectiveShadowCollectionError, match="OUTCOME_STORE_INDEX_LIMIT"):
        storage.OutcomeStoreIndex(store.root)


def test_manifest_failure_no_promotion(tmp_path, monkeypatch):
    _corpus(tmp_path / "ev")
    _populate(tmp_path / "ev", tmp_path / "store")
    def fail(*args):
        raise OSError("fsync/publish failed")
    monkeypatch.setattr(storage, "_atomic_json", fail)
    with pytest.raises(OSError):
        runner.mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "store")
    assert not list((tmp_path / "store" / "outcome_sessions").glob("*/*.json"))
    assert not list((tmp_path / "store" / "outcome_sessions").glob("*/*.ndjson"))


def test_legacy_compaction_write_failure_falls_back_to_originals(tmp_path, monkeypatch):
    _corpus(tmp_path / "ev")
    _populate(tmp_path / "ev", tmp_path / "store")
    _legacy_mature_all(retained_evidence_root=tmp_path / "ev", store_root=tmp_path / "store")
    store = collection.ProspectiveShadowObservationStore(tmp_path / "store")
    def fail(*args, **kwargs):
        raise OSError("derived cache unwritable")
    monkeypatch.setattr(storage, "_atomic_json", fail)
    index = store.build_outcome_store_index()
    assert len(index.latest) == (len(_SESSIONS) - 1) * 6
