"""OWNER_DAILY_20261005_CANONICAL_BUNDLE_FAILURE_RECOVERY_V1.

The 2026-10-05 Daily was the first trading session at/after PRODUCTION_V2_START_SESSION, i.e. the
first production run whose T0 seal index was RETAINED. ``prospective_t0_seal_index.publish``
returns a serialized reference (``{"path": str, ...}``) and ``build_tiered_bundle`` passed that
string to ``_rel``, which assumed ``Path``: AttributeError after T0, capture and first marker had
already been sealed. These tests drive the real retain -> seal -> tiered-bundle path (no mocks of
``build_tiered_bundle``) and pin the session-level original-T0 reuse a recovery rerun relies on.
"""
import copy
import json
import os
from pathlib import Path

import pytest

import canonical_post_close_pipeline as cpc
import daily_session_level2_package as level2
import stocklookup_core.decision.integrated_investment_decision_product as product
import prospective_decision_retention as retention
import prospective_t0_seal_index as seals
from contextual_technical_dispatch import PRODUCTION_V2_START_SESSION
from test_thesis_evidence_matrix import integrated_row

SESSION = "2026-10-05"
assert SESSION >= PRODUCTION_V2_START_SESSION


def _iid(session=SESSION, tickers=("VNM", "AAA")):
    records = {}
    for ticker in tickers:
        row = copy.deepcopy(integrated_row())
        row.update(ticker=ticker, as_of_session=session)
        row.pop("contextual_technical_context", None)
        row["decision_identity"] = product.decision_identity(row)
        records[ticker] = row
    iid = {"contract_version": product.CONTRACT_VERSION, "session": session, "records": records,
           "requested_at": session + "T15:00:00+07:00"}
    iid.update(product.content_identity(iid))
    return iid


def _producer_result(run_dir, operation_identity="daily_research_session_operation:first"):
    return {
        "run_identity": "daily_producer_run:" + operation_identity.rsplit(":", 1)[-1], "run_dir": run_dir, "status": "COMPLETED",
        "manifest": {"upstream_artifact_identities": {}, "blocked_dimensions": [], "warnings": [],
                     "authority_boundary": {"is_actionable": False},
                     "dashboard_projection": {"identity": "current_decision_cockpit_projection:fake"}},
        "operation": {"manifest": {"operation_identity": operation_identity},
                      "product": {"market_brief": {"coverage": {}}, "high_priority_full_universe_review_set": {"count": 0}}},
    }


def _retain(root, operation_identity="daily_research_session_operation:first", iid=None):
    return cpc.retain_prospective_decision_snapshot(
        root, SESSION, producer_result=_producer_result(root / "run", operation_identity),
        enrichment={"integrated_investment_decision_product": {"artifact": iid or _iid()}},
    )


def _bundle_inputs(root):
    paths = level2.session_artifact_paths(root, SESSION)
    for key in ("session_triage", "tactical_classifier", "descriptive_research", "opportunity_prioritization", "decision_packet"):
        paths[key].parent.mkdir(parents=True, exist_ok=True)
        paths[key].write_text(json.dumps({"records": {}}), encoding="utf-8")
    run_dir = root / "run"
    (run_dir / "dashboard").mkdir(parents=True, exist_ok=True)
    for name in ("ai_research_full_universe.ndjson", "ai_research_bundle_manifest.json", "run_manifest.json"):
        (run_dir / name).write_text("{}" if name.endswith(".json") else "", encoding="utf-8")
    (run_dir / "dashboard" / "current_decision_cockpit_projection.json").write_text("{}", encoding="utf-8")
    return run_dir


def _session_dirs(root):
    base = root / "operations-review" / "prospective-decision-retention-v1" / SESSION
    return sorted(p.name for p in base.iterdir()) if base.exists() else []


# --- 1. exact production failure shape, real build_tiered_bundle ---

def test_real_retained_seal_index_reference_serializes_root_relative_in_tiered_bundle(tmp_path):
    run_dir = _bundle_inputs(tmp_path)
    snapshot = _retain(tmp_path)
    # The failing run's shape: snapshot path is a Path, the seal-index reference path a str.
    assert snapshot["status"] == "RETAINED" and snapshot["seal_index"]["status"] == "RETAINED"
    assert isinstance(snapshot["path"], Path) and isinstance(snapshot["seal_index"]["path"], str)

    tiers = cpc.build_tiered_bundle(
        tmp_path, SESSION, acquisition={"resolved_completed_session": SESSION, "coverage": {}},
        producer_result=_producer_result(run_dir), decision_packet=None, prospective=None, enrichment={},
        producer_head="deadbeef", consumer_head="deadbeef", prospective_snapshot=snapshot, artifact_root=tmp_path,
    )

    block = tiers["session_handoff_bundle"]["prospective_decision_snapshot"]
    digest = snapshot["artifact"]["snapshot_identity"].removeprefix(retention.SNAPSHOT_PREFIX)
    expected_dir = f"operations-review/prospective-decision-retention-v1/{SESSION}/{digest}"
    assert block["identity"] == snapshot["artifact"]["snapshot_identity"]
    assert block["path"] == expected_dir + "/prospective_decision_snapshot.json"
    assert block["seal_index"]["path"] == expected_dir + "/prospective_t0_seal_index.json"
    # Seal identities pass through byte-identical; only the path is normalized.
    for key in ("status", "artifact_identity", "write_receipt_identity"):
        assert block["seal_index"][key] == snapshot["seal_index"][key]
    assert "retention" not in block
    # The serialized handoff is plain JSON and is consumable exactly as Volume/Flow V2 consumes it.
    on_disk = json.loads((tiers["bundle_dir"] / "session_handoff_bundle.json").read_text(encoding="utf-8"))
    ref = on_disk["prospective_decision_snapshot"]["seal_index"]
    bound = seals.load_verified({**ref, "path": str(tmp_path / ref["path"])},
                                expected_snapshot_identity=block["identity"], session=SESSION)
    assert bound is not None and bound.snapshot_identity == block["identity"]


# --- 2. _rel contract: Path | str, root-relative, containment policy unchanged ---

@pytest.mark.parametrize("make", [
    lambda root: root / "operations-review" / "x" / "a.json",
    lambda root: str(root / "operations-review" / "x" / "a.json"),
    lambda root: "operations-review/x/a.json",
    pytest.param(lambda root: "operations-review\\x\\a.json",
                 marks=pytest.mark.skipif(os.name != "nt", reason="backslash is a path separator only on Windows")),
    lambda root: Path("operations-review/x/a.json"),
], ids=["abs-Path", "abs-str", "rel-str", "rel-str-backslash", "rel-Path"])
def test_rel_normalizes_path_and_serialized_string_to_root_relative(tmp_path, monkeypatch, make):
    root = tmp_path / "repo"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # relative inputs resolve against root, never the CWD
    # Nonexistent target: serialization may precede the write.
    assert cpc._rel(root, make(root)) == "operations-review/x/a.json"


def test_rel_keeps_out_of_root_paths_absolute_as_before(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "operation-output" / "a.json"
    assert cpc._rel(root, outside) == outside.as_posix()
    assert cpc._rel(root, str(outside)) == outside.as_posix()
    assert cpc._rel(root, "../operation-output/a.json").endswith("operation-output/a.json")
    assert not cpc._rel(root, "../operation-output/a.json").startswith("operation-output")


@pytest.mark.parametrize("value", [None, 7, {"path": "x"}])
def test_rel_rejects_non_path_values_explicitly(tmp_path, value):
    with pytest.raises(TypeError, match="PATH_LIKE_REQUIRED"):
        cpc._rel(tmp_path, value)


# --- 3. session-level original T0 reuse (recovery / rerun after a code change) ---

def test_rerun_with_new_operation_identity_reuses_original_sealed_t0(tmp_path):
    first = _retain(tmp_path)
    original_dir = _session_dirs(tmp_path)
    snapshot_path = first["path"]
    before = (snapshot_path.read_bytes(), snapshot_path.stat().st_mtime_ns)

    # A merged fix changes producer HEAD -> operation identity -> would-be snapshot identity.
    again = _retain(tmp_path, operation_identity="daily_research_session_operation:after-merge")

    assert again["status"] == "RETAINED" and again["retention"] == "ORIGINAL_SESSION_T0_REUSED"
    assert again["artifact"]["snapshot_identity"] == first["artifact"]["snapshot_identity"]
    assert again["artifact"]["source_integrated_decision_artifact"] == first["artifact"]["source_integrated_decision_artifact"]
    assert again["artifact"]["daily_session_operation_identity"] == "daily_research_session_operation:first"
    assert {k: again["seal_index"][k] for k in ("artifact_identity", "write_receipt_identity")} == \
           {k: first["seal_index"][k] for k in ("artifact_identity", "write_receipt_identity")}
    assert _session_dirs(tmp_path) == original_dir  # no second T0
    assert (snapshot_path.read_bytes(), snapshot_path.stat().st_mtime_ns) == before


def test_reused_t0_flows_through_tiered_bundle_with_retention_marker(tmp_path):
    run_dir = _bundle_inputs(tmp_path)
    first = _retain(tmp_path)
    again = _retain(tmp_path, operation_identity="daily_research_session_operation:after-merge")
    tiers = cpc.build_tiered_bundle(
        tmp_path, SESSION, acquisition={"resolved_completed_session": SESSION, "coverage": {}},
        producer_result=_producer_result(run_dir, "daily_research_session_operation:after-merge"),
        decision_packet=None, prospective=None, enrichment={}, producer_head="cafe", consumer_head="cafe",
        prospective_snapshot=again, artifact_root=tmp_path,
    )
    block = tiers["session_handoff_bundle"]["prospective_decision_snapshot"]
    assert block["identity"] == first["artifact"]["snapshot_identity"]
    assert block["retention"] == "ORIGINAL_SESSION_T0_REUSED"
    assert block["seal_index"]["path"].endswith("/prospective_t0_seal_index.json")
    assert not Path(block["seal_index"]["path"]).is_absolute()


def test_capture_session_binding_is_authoritative_and_unverifiable_t0_is_never_replaced(tmp_path):
    first = _retain(tmp_path)
    capture = tmp_path / "operations-review" / "prospective-pit-capture-v1" / "sessions" / f"{SESSION}.json"
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(json.dumps({"t0_decision_snapshot_identity": first["artifact"]["snapshot_identity"]}), encoding="utf-8")
    assert _retain(tmp_path, "daily_research_session_operation:x")["retention"] == "ORIGINAL_SESSION_T0_REUSED"

    index_path = Path(first["seal_index"]["path"])
    index_path.write_bytes(index_path.read_bytes().replace(b'"records"', b'"recordz"'))
    refused = _retain(tmp_path, "daily_research_session_operation:y")
    assert refused["status"] == "UNAVAILABLE" and refused["reason"].startswith("ORIGINAL_SESSION_T0_UNVERIFIED:")
    assert len(_session_dirs(tmp_path)) == 1


def test_capture_binding_to_missing_t0_fails_soft_without_minting(tmp_path):
    capture = tmp_path / "operations-review" / "prospective-pit-capture-v1" / "sessions" / f"{SESSION}.json"
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(json.dumps({"t0_decision_snapshot_identity": retention.SNAPSHOT_PREFIX + "0" * 64}), encoding="utf-8")
    refused = _retain(tmp_path)
    assert refused["status"] == "UNAVAILABLE" and refused["reason"].startswith("ORIGINAL_SESSION_T0_UNVERIFIED:")
    assert _session_dirs(tmp_path) == []


def test_multiple_sealed_t0_without_capture_binding_is_ambiguous_not_chosen(tmp_path, monkeypatch):
    _retain(tmp_path)
    monkeypatch.setattr(cpc, "_original_session_t0", lambda base, session: None)
    _retain(tmp_path, operation_identity="daily_research_session_operation:legacy-second")
    monkeypatch.undo()
    assert len(_session_dirs(tmp_path)) == 2
    refused = _retain(tmp_path, operation_identity="daily_research_session_operation:third")
    assert refused == {"status": "UNAVAILABLE", "reason": "ORIGINAL_SESSION_T0_AMBIGUOUS:2"}
    assert len(_session_dirs(tmp_path)) == 2


def test_capture_record_without_t0_binding_and_no_sealed_t0_keeps_first_run_behavior(tmp_path):
    capture = tmp_path / "operations-review" / "prospective-pit-capture-v1" / "sessions" / f"{SESSION}.json"
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(json.dumps({"t0_decision_snapshot_identity": None}), encoding="utf-8")
    result = _retain(tmp_path)
    assert result["status"] == "RETAINED" and "retention" not in result
    assert len(_session_dirs(tmp_path)) == 1


def test_pre_v2_sessions_never_consult_original_t0_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(cpc, "_original_session_t0", lambda *a, **k: pytest.fail("consulted"))
    result = cpc.retain_prospective_decision_snapshot(
        tmp_path, "2026-10-02", producer_result=_producer_result(tmp_path / "run"), enrichment={},
    )
    assert result == {"status": "UNAVAILABLE", "reason": "INTEGRATED_DECISION_ARTIFACT_UNAVAILABLE"}


def test_original_t0_reuse_respects_operation_output_root(tmp_path):
    output_root = tmp_path / "operation-output"
    first = cpc.retain_prospective_decision_snapshot(
        tmp_path, SESSION, producer_result=_producer_result(tmp_path / "run"),
        enrichment={"integrated_investment_decision_product": {"artifact": _iid()}}, output_root=output_root,
    )
    again = cpc.retain_prospective_decision_snapshot(
        tmp_path, SESSION, producer_result=_producer_result(tmp_path / "run", "daily_research_session_operation:z"),
        enrichment={"integrated_investment_decision_product": {"artifact": _iid()}}, output_root=output_root,
    )
    assert again["retention"] == "ORIGINAL_SESSION_T0_REUSED"
    assert again["artifact"]["snapshot_identity"] == first["artifact"]["snapshot_identity"]
    assert _session_dirs(tmp_path) == []


# --- 4. capture / first-marker idempotency with the reused original T0 ---

def test_reused_original_t0_keeps_capture_record_and_first_marker_idempotent(tmp_path):
    import prospective_pit_capture_retention as store
    from test_prospective_pit_capture import DAY, capture_session
    assert DAY == SESSION
    first = _retain(tmp_path)
    original_identity = first["artifact"]["snapshot_identity"]
    _, evidence, gate, result = capture_session(tmp_path, t0_snapshot_identity=original_identity)
    assert result["session_capture"]["status"] == "RETAINED"
    assert result["session_capture"]["marker_status"] == "PUBLISHED"
    marker_path = tmp_path / store.STORE / "first_complete_capture_session.json"
    record_path = tmp_path / store.STORE / "sessions" / f"{SESSION}.json"
    frozen = (marker_path.read_bytes(), record_path.read_bytes())

    # Recovery rerun after a code change: the T0 is reused, so the capture boundary binds cleanly.
    again = _retain(tmp_path, operation_identity="daily_research_session_operation:after-merge")
    assert again["artifact"]["snapshot_identity"] == original_identity
    repeat = store.daily_boundary(tmp_path, session=SESSION, gate=gate, evidence=evidence,
                                  known_at="2026-10-05T13:00:00Z", t0_snapshot_identity=again["artifact"]["snapshot_identity"])
    assert repeat["session_capture"]["status"] == "ALREADY_CAPTURED"
    assert repeat["session_capture"]["marker_status"] == "ALREADY_PUBLISHED"
    assert (marker_path.read_bytes(), record_path.read_bytes()) == frozen

    # Without reuse (pre-corrective main) the re-minted T0 cannot bind: the boundary refuses.
    with pytest.raises(ValueError, match="RECOVERY_T0_BINDING_MISMATCH"):
        store.complete_capture_session(tmp_path, session=SESSION, gate=gate, evidence=evidence,
                                       completion_known_at="2026-10-05T13:00:00Z",
                                       t0_snapshot_identity=retention.SNAPSHOT_PREFIX + "f" * 64)
    assert (marker_path.read_bytes(), record_path.read_bytes()) == frozen
