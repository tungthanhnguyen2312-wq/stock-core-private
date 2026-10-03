"""Parity, reuse, retry, corruption and failure-containment tests for the streaming outcome-feedback builder.

OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1: the streamed artifact must be semantically identical to the
original in-memory ``build_feedback_artifact`` (same ``artifact_identity``), while holding no snapshot graph.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

import bounded_artifact_stream as bas
import prospective_decision_outcome_feedback as feedback
import prospective_decision_retention as retention
import prospective_feedback_streaming as streaming

TICKERS = ("FPT", "HPG", "VNM", "QNS")
POSTURES = ("INITIATE_ON_BREAKOUT", "WAIT_FOR_CONFIRMATION", "ACCUMULATE_ON_RETEST", "EARLY_WATCH")


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _condition(role: str, level: float, operator: str) -> dict:
    return retention.serialize_boundary_condition({
        "status": "READY", "boundary_type": "BREAKOUT", "comparison_operator": operator,
        "source_metric": "resistance" if "GT" in operator else "support", "baseline_value": level,
        "source_rule": "R1", "method": "watchlist_tactical_entry_classifier/v1",
        "evidence_lineage": {"technical": "retained"}, "warnings": [], "reason": "Existing rule.",
    }, role=role, source_strategy_identity="tactical-boundaries:1")


def _axis(state="AVAILABLE"):
    return {"state": state, "fitness": "AVAILABLE", "supporting_reason_codes": ["S"], "contradicting_reason_codes": [],
            "blocker_reason_codes": [], "method": "existing/v1", "lineage": {"source_artifact_identity": "src:1"}}


def _decision(ticker: str, session: str, posture: str, salt: str = "") -> dict:
    return {
        "ticker": ticker, "as_of_session": session, "decision_identity": f"decision:{ticker}:{session}{salt}",
        "research_action_posture": posture, "why_now": "T0 rationale.", "fundamental_state": "IMPROVING",
        "fundamental_decision_policy_version": "fundamental_policy/v1",
        "priority_posture_reconciliation": {"research_priority_tier": "PRIORITY_NOW"},
        "evidence_axis_coherence": {"state": "ALIGNED"},
        "evidence_axes": {name: _axis() for name in retention.REQUIRED_AXES},
        "trigger": {"trigger_state": "APPROACHING", "condition": _condition("trigger", 101.0, "FUTURE_CLOSE_GT_RESISTANCE_LEVEL")},
        "invalidation": {"invalidation_level": 90.0, "condition": _condition("invalidation", 95.0, "FUTURE_CLOSE_LT_SUPPORT_LEVEL")},
        "source_identities": {"technical_structure_identity": "structure:1"},
        "valuation_context_summary": {"status": "AVAILABLE"}, "market_structure_state": "UPTREND",
        "momentum_context": {"status": "AVAILABLE"}, "participation": {"status": "AVAILABLE"},
        "market_sector_context": {"market_regime": "SUPPORTIVE"},
        "qualified_tactical_signal_at_t0": {"status": "CONFIRMED", "source_identity": "tactical:1"},
    }


def _price(session: str, closes: dict[str, float], *, basis: str = "CURRENT_DESCRIPTIVE") -> dict:
    return {
        "resolved_completed_session": session, "snapshot_identity": f"price:{session}",
        "records": {t: {"observations": [
            {"session": "2025-01-01", "close": 1.0, "provider": "DNSE", "price_basis": basis},  # history row: must be ignored
            {"session": session, "close": c, "provider": "DNSE", "dataset": "OHLC", "price_basis": basis,
             "transformation_identity": "normalization/v1", "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY"}]}
            for t, c in closes.items()},
    }


def _integrated(session: str, postures: dict[str, str], salt: str = "") -> dict:
    return {"contract_version": "integrated_investment_decision_product/v1", "session": session,
            "artifact_identity": f"integrated:{session}{salt}", "artifact_sha256": "x" * 64,
            "records": {t: _decision(t, session, p, salt) for t, p in postures.items()}}


def _bind(root: Path, snapshot: dict) -> None:
    session = snapshot["session"]
    _write(root / "operations-review" / "daily-research-session-operations-v1" / session / "run" / "run_manifest.json", {
        "market_session": session, "operation_identity": snapshot["daily_session_operation_identity"],
        "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION"})
    _write(root / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json", {
        "session": session, "daily_session_operation_identity": snapshot["daily_session_operation_identity"],
        "integrated_investment_decision_product_identity": snapshot["source_integrated_decision_artifact"]["artifact_identity"],
        "prospective_decision_snapshot": {"identity": snapshot["snapshot_identity"]},
        "daily_producer": {"status": "COMPLETED"}, "market_session_proof": {"resolved_completed_session": session}})


def _add_modern(root: Path, session: str, step: int, *, salt: str = "", postures=None) -> dict:
    postures = postures or {t: POSTURES[(i + step) % 4] for i, t in enumerate(TICKERS)}
    closes = {t: 100.0 + step * (1 if i % 2 == 0 else -1.5) + i for i, t in enumerate(TICKERS)}
    snapshot = retention.build_snapshot(
        session=session, operation_identity=f"daily-operation:{session}", producer_run_identity=f"run:{session}",
        integrated_artifact=_integrated(session, postures, salt), exact_session_snapshot=_price(session, closes))
    retention.write_immutable_snapshot(root, snapshot)
    _bind(root, snapshot)
    nodash = session.replace("-", "")
    _write(root / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f9b_mva_exact_session_snapshot.json",
           _price(session, closes))
    return snapshot


def _add_legacy(root: Path, session: str, step: int) -> None:
    operation = f"daily-operation:{session}"
    path = root / "operations-review" / "integrated-artifacts" / session / "integrated_investment_decision_product_artifact.json"
    artifact = _integrated(session, {t: POSTURES[(i + step) % 4] for i, t in enumerate(TICKERS)})
    artifact["requested_at"] = session + "T15:00:00+07:00"
    _write(path, artifact)
    _write(root / "operations-review" / "daily-research-session-operations-v1" / session / "run" / "run_manifest.json", {
        "market_session": session, "operation_identity": operation, "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION"})
    _write(root / "operations-review" / "canonical-post-close-v1" / session / "session_handoff_bundle.json", {
        "session": session, "daily_session_operation_identity": operation,
        "integrated_investment_decision_product_identity": artifact["artifact_identity"],
        "deeper_bundles": {"integrated_investment_decision_product": str(path.relative_to(root)).replace("\\", "/")},
        "daily_producer": {"status": "COMPLETED"}, "market_session_proof": {"resolved_completed_session": session}})
    closes = {t: 100.0 + step * (1 if i % 2 == 0 else -1.5) + i for i, t in enumerate(TICKERS)}
    _write(root / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{session.replace('-', '')}" / "p3f9b_mva_exact_session_snapshot.json",
           _price(session, closes))


def _corpus(root: Path, legacy: int = 3, modern: int = 5) -> list[str]:
    sessions = []
    for index in range(legacy):
        session = f"2026-01-{index + 2:02d}"
        _add_legacy(root, session, index)
        sessions.append(session)
    for index in range(modern):
        session = f"2026-01-{legacy + index + 2:02d}"
        _add_modern(root, session, legacy + index)
        sessions.append(session)
    return sessions


def _legacy_artifact(root: Path) -> dict:
    return json.loads(json.dumps(feedback.build_feedback_artifact(root, use_summary_cache=False, use_settled_cache=False)))


def _build(root: Path, output: Path, state: Path, **kwargs) -> dict:
    return streaming.build_streaming_feedback(root, output, state_root=state, **kwargs)


def _artifact_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def corpus(tmp_path):
    root = tmp_path / "evidence"
    sessions = _corpus(root)
    return root, sessions, tmp_path / "state", tmp_path / "out" / "feedback.json"


# -- exact parity -----------------------------------------------------------------------------------------

def test_streamed_artifact_is_identity_and_content_equal_to_the_in_memory_builder(corpus):
    root, _sessions, state, output = corpus
    expected = _legacy_artifact(root)
    result = _build(root, output, state)
    assert result["outcome"] == streaming.OUTCOME_BUILT
    assert result["artifact_identity"] == expected["artifact_identity"]
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    # Non-vacuous: the corpus really exercises matured horizons, mixed postures and the case lists.
    statuses = {row["forward_outcomes"]["horizons"]["forward_close_return_5"]["status"] for row in expected["feedback_records"]}
    assert "MATURE" in statuses and len(expected["feedback_records"]) == 8 * len(TICKERS)
    assert expected["false_negative_cases"] or expected["failed_setup_cases"]
    assert expected["trigger_invalidation_outcomes"] and expected["required_ticker_cases"]["FPT"]


def test_artifact_identity_is_recomputable_from_the_published_bytes(corpus):
    root, _s, state, output = corpus
    result = _build(root, output, state)
    assert streaming.stream_artifact_identity(output) == result["artifact_identity"]
    first_member = output.read_bytes()[:40]
    assert first_member.startswith(b'{"artifact_identity":"')
    assert output.stat().st_size < len(json.dumps(json.loads(output.read_text(encoding="utf-8")), indent=2, sort_keys=True))


def test_two_snapshots_for_one_session_merge_in_original_order(tmp_path):
    root = tmp_path / "evidence"
    _corpus(root, legacy=1, modern=3)
    # A re-sealed (changed) decision for an existing session: same (session, ticker), different decision_identity.
    _add_modern(root, "2026-01-03", 9, salt=":reseal", postures={"FPT": "AVOID", "HPG": "AVOID"})
    expected = _legacy_artifact(root)
    result = _build(root, tmp_path / "o" / "f.json", tmp_path / "state")
    assert result["artifact_identity"] == expected["artifact_identity"]
    keys = [(r["decision_session"], r["ticker"], r["decision_identity"]) for r in expected["feedback_records"]]
    assert keys == sorted(keys)


def test_legacy_file_layout_is_adopted_when_the_content_identity_is_equal(corpus):
    root, _s, state, output = corpus
    from tools.run_prospective_decision_outcome_feedback import run
    run(root=root, output=output)  # original builder: indent=2 layout, no completion manifest
    legacy_identity = streaming._identity_from_header(output)
    result = _build(root, output, state)
    assert result["outcome"] == streaming.OUTCOME_ALREADY_RETAINED_EQUAL
    assert result["artifact_identity"] == legacy_identity
    assert streaming.read_completion(output) is not None
    assert _build(root, output, state)["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE


# -- cold / warm / retry / changed input -------------------------------------------------------------------

def test_warm_run_reuses_the_exact_terminal_output_without_rewriting(corpus):
    root, _s, state, output = corpus
    cold = _build(root, output, state)
    before = (output.stat().st_mtime_ns, _artifact_digest(output))
    warm = _build(root, output, state)
    assert warm["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE
    assert warm["artifact_identity"] == cold["artifact_identity"] and warm["input_digest"] == cold["input_digest"]
    assert (output.stat().st_mtime_ns, _artifact_digest(output)) == before
    assert warm["metrics"].get("rows", 0) == 0  # no record was re-evaluated
    assert list(output.parent.glob(streaming.TEMP_PREFIX + "*")) == []


def test_changed_input_gets_a_distinct_identity_and_relation_incremental(corpus):
    root, _s, state, output = corpus
    first = _build(root, output, state)
    _add_modern(root, "2026-02-20", 11)
    changed_output = output.with_name("feedback_changed.json")
    second = _build(root, changed_output, state, prior_summary=first["inputs_summary"])
    assert second["input_digest"] != first["input_digest"]
    assert second["artifact_identity"] != first["artifact_identity"]
    assert second["relation"]["relation"] == "INCREMENTAL" and second["relation"]["new_sessions"] == ["2026-02-20"]
    assert streaming.relate(first["inputs_summary"], first["inputs_summary"])["relation"] == "IDENTICAL"
    assert streaming.relate(None, first["inputs_summary"])["relation"] == "NO_PRIOR"
    # The old output path keeps its immutable content: a changed input can never overwrite it.
    with pytest.raises(streaming.ImmutableOutputConflict):
        _build(root, output, state)
    assert streaming.read_completion(output)["artifact_identity"] == first["artifact_identity"]


def test_relation_distinct_when_prior_is_not_a_subset():
    prior = {"input_digest": "a", "chain_sessions": ["s1", "s2"], "t0_snapshot_identities": ["x"], "legacy_artifact_paths": [], "artifact_inventory_paths": []}
    current = {"input_digest": "b", "chain_sessions": ["s1", "s3"], "t0_snapshot_identities": ["y"], "legacy_artifact_paths": [], "artifact_inventory_paths": []}
    assert streaming.relate(prior, current)["relation"] == "DISTINCT"


def test_interrupted_build_leaves_only_recognisable_incomplete_data_and_retry_rebuilds(corpus, monkeypatch):
    root, _s, state, output = corpus
    original = streaming._iter_rows
    calls = {"n": 0}

    def exploding(*args, **kwargs):
        for row in original(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 7:
                raise RuntimeError("injected mid-stream failure")
            yield row

    monkeypatch.setattr(streaming, "_iter_rows", exploding)
    with pytest.raises(RuntimeError):
        _build(root, output, state)
    assert not output.exists() and streaming.read_completion(output) is None
    assert [p for p in output.parent.iterdir() if not p.name.startswith(streaming.TEMP_PREFIX)] == []  # only own temporaries, and removed
    monkeypatch.setattr(streaming, "_iter_rows", original)
    result = _build(root, output, state)
    assert result["outcome"] == streaming.OUTCOME_BUILT
    assert json.loads(output.read_text(encoding="utf-8")) == _legacy_artifact(root)


def test_dead_writer_temporaries_are_removed_on_the_next_run_without_manual_cleanup(corpus):
    root, _s, state, output = corpus
    output.parent.mkdir(parents=True, exist_ok=True)
    stale = [output.parent / f"{streaming.TEMP_PREFIX}feedback.json-rows-999999.spool",
             output.parent / f"{streaming.TEMP_PREFIX}feedback.json-999999.incomplete"]
    for path in stale:
        path.write_bytes(b"partial")
    unrelated = output.parent / "keep.txt"
    unrelated.write_text("x")
    _build(root, output, state)
    assert all(not p.exists() for p in stale) and unrelated.exists()


def test_tampered_published_output_is_not_reused_and_is_reported_as_a_conflict(corpus):
    root, _s, state, output = corpus
    _build(root, output, state)
    raw = bytearray(output.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    output.write_bytes(bytes(raw))
    assert streaming.read_completion(output) is None  # raw hash no longer matches the manifest
    with pytest.raises(streaming.ImmutableOutputConflict):
        _build(root, output, state)


def test_corrupt_receipt_manifest_and_price_index_are_ignored_and_rebuilt(corpus):
    root, _s, state, output = corpus
    first = _build(root, output, state)
    for path in list((state / streaming.STATE_DIR).rglob("*.json")):
        path.write_text("{ not json", encoding="utf-8")
    streaming.completion_manifest_path(output).write_text("garbage", encoding="utf-8")
    rebuilt = _build(root, output.with_name("again.json"), state)
    assert rebuilt["artifact_identity"] == first["artifact_identity"]
    adopted = _build(root, output, state)  # same path: bytes equal => adopted, manifest rewritten
    assert adopted["outcome"] == streaming.OUTCOME_ALREADY_RETAINED_EQUAL and streaming.read_completion(output)


# -- source corruption (original semantics preserved: unproven snapshots are excluded, never admitted) -----

def _find_snapshot(root: Path, session: str) -> Path:
    return next((root / "operations-review" / "prospective-decision-retention-v1" / session).glob("*/prospective_decision_snapshot.json"))


def test_tampered_snapshot_is_excluded_exactly_as_the_original_builder_excludes_it(corpus):
    root, sessions, state, output = corpus
    path = _find_snapshot(root, sessions[-1])
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"WAIT_FOR_CONFIRMATION"', '"AVOID"', 1).replace('"EARLY_WATCH"', '"AVOID"', 1), encoding="utf-8")
    expected = _legacy_artifact(root)
    result = _build(root, output, state)
    assert result["artifact_identity"] == expected["artifact_identity"]
    classes = expected["prospective_corpus"]["snapshot_classification_counts"]
    assert classes.get(retention.EXCLUDED, 0) == 1
    reasons = [r for r in expected["temporal_qualification"]["immutable_snapshot_inventory"] if r["classification"] == retention.EXCLUDED]
    assert "SNAPSHOT_CONTENT_IDENTITY_INVALID" in reasons[0]["proof_reason_codes"]


def test_truncated_snapshot_is_skipped_exactly_as_the_original_builder_skips_it(corpus):
    root, sessions, state, output = corpus
    path = _find_snapshot(root, sessions[-2])
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    expected = _legacy_artifact(root)
    assert _build(root, output, state)["artifact_identity"] == expected["artifact_identity"]


def test_snapshot_record_tamper_is_detected_by_the_per_record_identity(corpus):
    root, sessions, state, output = corpus
    path = _find_snapshot(root, sessions[-1])
    value = json.loads(path.read_text(encoding="utf-8"))
    value["records"]["FPT"]["known_at"] = "tampered"  # also breaks the snapshot identity, but never goes unnoticed
    path.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    handle = streaming.load_snapshot_handle(path, state)
    assert handle is not None and handle.valid is False
    assert retention.validate_snapshot(retention._load(path)) is False


def test_receipt_is_keyed_by_exact_bytes_so_a_swapped_file_is_reverified(corpus):
    root, sessions, state, _o = corpus
    path = _find_snapshot(root, sessions[-1])
    good = streaming.load_snapshot_handle(path, state)
    assert good.valid
    original = path.read_bytes()
    path.write_bytes(original.replace(b"FPT", b"FPX", 1))
    swapped = streaming.load_snapshot_handle(path, state)
    assert swapped.raw_sha256 != good.raw_sha256 and swapped.valid is False


def test_source_changed_between_proof_and_use_fails_closed(corpus):
    root, sessions, state, _o = corpus
    path = _find_snapshot(root, sessions[-1])
    handle = streaming.load_snapshot_handle(path, state)
    path.write_bytes(path.read_bytes() + b"\n ")
    with pytest.raises(streaming.SourceIntegrityError):
        list(streaming.iter_snapshot_records(handle))


def test_unsorted_small_snapshot_keeps_the_original_acceptance(tmp_path):
    snapshot = retention.build_snapshot(
        session="2026-03-02", operation_identity="op", producer_run_identity="run", integrated_artifact=_integrated("2026-03-02", {"FPT": "AVOID", "HPG": "AVOID"}),
        exact_session_snapshot=_price("2026-03-02", {"FPT": 100.0, "HPG": 50.0}))
    path = tmp_path / "s.json"
    reordered = {"snapshot_identity": snapshot["snapshot_identity"], **{k: v for k, v in snapshot.items() if k != "snapshot_identity"}}
    path.write_text(json.dumps(reordered, indent=1), encoding="utf-8")  # insertion order: not sorted
    handle = streaming.load_snapshot_handle(path, tmp_path / "state")
    assert handle is not None and handle.valid is True and retention.validate_snapshot(retention._load(path))


# -- aggregation helpers & bounded-stream primitives ------------------------------------------------------

def test_streamed_records_placeholder_refuses_accidental_materialisation(tmp_path):
    placeholder = streaming.StreamedRecords(tmp_path / "x", 3, "t0")
    assert len(placeholder) == 3 and bool(placeholder)
    with pytest.raises(TypeError):
        list(placeholder)
    with pytest.raises(TypeError):
        placeholder.items()


def test_object_stream_large_member_unsorted_mode_and_duplicate_rejection(tmp_path):
    big = {"records": {"A": {"blob": "x" * 700_000}, "B": {"blob": "y" * 700_000}}, "z": 1}
    path = tmp_path / "big.json"
    path.write_text(json.dumps(big, sort_keys=True), encoding="utf-8")
    seen = []
    meta, digest, count = bas.stream_artifact(path, excluded=set(), on_record=lambda t, r: seen.append((t, len(r["blob"]))))
    assert seen == [("A", 700_000), ("B", 700_000)] and count == 2
    assert digest == hashlib.sha256(retention._canon(big).encode()).hexdigest()
    path.write_text('{"b": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(ValueError):
        list(bas.ObjectStream(open(path, encoding="utf-8")).members())
    with open(path, encoding="utf-8") as source:
        parser = bas.ObjectStream(source, sorted_required=False)
        keys = []
        for key in parser.members():
            keys.append(key)
            parser.value()
        assert keys == ["b", "a"]  # unsorted accepted only when explicitly requested
    path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(ValueError):
        with open(path, encoding="utf-8") as source:
            parser = bas.ObjectStream(source, sorted_required=False)
            for _ in parser.members():
                parser.value()


def test_canonical_bytes_equal_the_original_chunked_encoder_and_reject_nan():
    values = [{"b": [1, 2.5, None, True], "a": {"z": "é" + chr(0x2028) + '"\\x', "y": 1e-7, "x": 10 ** 30}, "c": chr(0x65E5)}, [], {}, "s", 3,
              {"k": [{"j": 0.1 + 0.2}]}]
    for value in values:
        assert b"".join(retention._json_bytes(value)) == bas.canonical_bytes(value)
    with pytest.raises(ValueError):
        bas.canonical_bytes({"a": float("nan")})


def test_price_index_keeps_only_same_session_observations_and_matches_the_full_snapshot_semantics(tmp_path):
    path = tmp_path / "p3f9b.json"
    full = _price("2026-04-01", {"FPT": 10.0, "HPG": 20.0})
    full["records"]["HPG"]["observations"].append(copy.deepcopy(full["records"]["HPG"]["observations"][1]))  # duplicate same-session row
    path.write_text(json.dumps(full, sort_keys=True), encoding="utf-8")
    index = streaming.PriceIndex(tmp_path / "state")
    compact = index.load(path, "2026-04-01")
    import integrated_decision_prospective_feedback as bridge
    for ticker in ("FPT", "HPG"):
        assert bridge.retained_session_price_observations({"2026-04-01": compact}, ticker) == bridge.retained_session_price_observations({"2026-04-01": full}, ticker)
    assert index.load(path, "2026-04-02") is None  # session mismatch is rejected like the original loader
    assert index.content_hash("2026-04-01") == retention._hash(full)
    assert streaming.PriceIndex(tmp_path / "state", metrics={}).load(path, "2026-04-01") == compact  # warm path


def test_output_disk_write_failure_leaves_no_published_output(corpus, monkeypatch):
    root, _s, state, output = corpus
    real_replace = os.replace

    def failing_copy(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(streaming, "_copy_hashing", failing_copy)
    with pytest.raises(OSError):
        _build(root, output, state)
    assert not output.exists()
    assert [p.name for p in output.parent.iterdir() if not p.name.startswith(streaming.TEMP_PREFIX)] == []
    assert real_replace is os.replace


# -- the post-marker (future completed-capture chain) evaluation branch -------------------------------------

class _FutureChain(list):
    """Minimal GovernedSessionChain stand-in exposing the exact surface the forward bridge uses."""
    contract_version = "fake_governed_session_chain/v1"

    def realized_prefix_after(self, session, count):
        index = self.index(session)
        return list(self[index + 1:index + 1 + count])

    def next_n_sessions(self, session, count):
        index = self.index(session)
        if index + count < len(self):
            return {"state": "COMPLETE", "target": self[index + count]}
        return {"state": "PROJECTED_ONLY"}


def test_post_marker_sessions_use_the_future_chain_exactly_as_the_original_builder_does(corpus, monkeypatch):
    import prospective_pit_capture_retention as store
    root, sessions, state, output = corpus
    marker_session = sessions[3]
    future = _FutureChain(s for s in sessions if s >= marker_session)
    monkeypatch.setattr(store, "load_marker", lambda r: {"session": marker_session})
    monkeypatch.setattr(store, "load_chain", lambda r, as_of: future)
    expected = _legacy_artifact(root)
    result = _build(root, output, state)
    assert result["artifact_identity"] == expected["artifact_identity"]
    rows = [r for r in expected["feedback_records"] if r["decision_session"] >= marker_session]
    assert rows and all("session_chain_contract" in r["forward_outcomes"]["horizons"]["forward_close_return_5"] or
                        r["forward_outcomes"]["horizons"]["forward_close_return_5"]["status"] for r in rows)
    # With a marker the reuse key also binds the as-of date, so a different day cannot silently reuse the output.
    summary_a = _build(root, output.with_name("b.json"), state)["input_digest"]
    monkeypatch.setattr(streaming, "_future_chain_inputs", lambda repository, marker, as_of: {"marker": marker, "as_of_date": "2099-01-01"})
    assert _build(root, output.with_name("c.json"), state)["input_digest"] != summary_a
