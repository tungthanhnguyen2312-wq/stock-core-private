"""Adversarial two-operation proof; all writes are isolated synthetic fixtures."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

import prospective_decision_retention as retention
import prospective_feedback_streaming as streaming
import prospective_t0_seal_index as seals
from stocklookup_core.evidence.field_identity import stable_id
from test_prospective_decision_retention import _integrated, _price_snapshot, _snapshot, _bind


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def operation(root, session, decision, *, epoch="original"):
    value = {"contract_version": "daily_research_session_operation/v1", "market_session": session,
             "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION", "producer_head": epoch,
             "outputs": {"integrated_investment_decision_product": decision}}
    value["operation_identity"] = "daily_research_session_operation:" + stable_id(value)
    path = root / "operations-review/daily-research-session-operations-v1" / session / value["operation_identity"].split(":")[1] / "run_manifest.json"
    write(path, value)
    return value, path


@pytest.fixture
def reuse(tmp_path):
    session = "2026-10-05"
    iid = "integrated_investment_decision_product/v1:" + "a" * 64
    later_iid = "integrated_investment_decision_product/v1:" + "b" * 64
    orig, opath = operation(tmp_path, session, iid)
    later, lpath = operation(tmp_path, session, later_iid, epoch="recovery")
    integrated = _integrated(session)
    integrated.update(artifact_identity=iid, artifact_sha256="a" * 64)
    snapshot = retention.build_snapshot(session=session, operation_identity=orig["operation_identity"],
        producer_run_identity="original-run", integrated_artifact=integrated, exact_session_snapshot=_price_snapshot(session, 100))
    path = retention.write_immutable_snapshot(tmp_path, snapshot)
    ref = seals.from_snapshot(snapshot, path, created_at="2026-10-05T11:28:14+00:00",
                              file_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    handoff = {"session": session, "daily_session_operation_identity": later["operation_identity"],
        "integrated_investment_decision_product_identity": later_iid,
        "prospective_decision_snapshot": {"identity": snapshot["snapshot_identity"], "status": "RETAINED",
            "retention": "ORIGINAL_SESSION_T0_REUSED", "path": str(path.relative_to(tmp_path)),
            "source_integrated_decision_artifact_identity": iid, "seal_index": {"status": "RETAINED", **ref}}}
    hpath = tmp_path / "operations-review/canonical-post-close-v1" / session / "session_handoff_bundle.json"
    write(hpath, handoff)
    return dict(root=tmp_path, path=path, snapshot=snapshot, handoff=handoff, hpath=hpath,
                original_path=opath, later_path=lpath, original=orig, later=later)


def inventory(case, *, streamed=False):
    kwargs = {}
    if streamed:
        kwargs = {"snapshot_loader": lambda p: streaming.load_snapshot_handle(p, case["root"] / "test-cache"),
                  "snapshot_validator": lambda h: h.valid}
    return retention.discover_snapshots(case["root"], **kwargs)


def test_valid_reuse_joins_origination_not_current_view_and_preserves_prices(reuse):
    before = reuse["path"].read_bytes()
    result = inventory(reuse)
    assert result["inventory"][0]["classification"] == retention.GENUINE
    assert len(result["genuine_snapshots"]) == 1
    assert reuse["path"].read_bytes() == before
    assert result["genuine_snapshots"][0]["snapshot"] == reuse["snapshot"]
    assert reuse["snapshot"]["records"]["FPT"]["t0_close_observation"]["close"] == 100


def test_ordinary_original_binding_remains_accepted(tmp_path):
    snapshot = _snapshot("2026-01-02", 100)
    retention.write_immutable_snapshot(tmp_path, snapshot)
    _bind(tmp_path, snapshot)
    assert retention.discover_snapshots(tmp_path)["inventory"][0]["classification"] == retention.GENUINE


@pytest.mark.parametrize("fault", ["snapshot_hash", "missing_original", "original_hash", "original_source",
    "original_replay", "seal", "receipt", "missing_seal", "different_snapshot", "another_session",
    "later_hash", "later_source", "missing_later", "no_reuse_claim", "original_reference",
    "snapshot_path", "replay_index", "record_origination", "missing_snapshot", "orphan", "duplicate_handoff"])
def test_incomplete_or_forged_relation_is_rejected(reuse, fault):
    c = reuse
    if fault == "snapshot_hash":
        v = copy.deepcopy(c["snapshot"]); v["records"]["FPT"]["t0_close_observation"]["close"] = 101; write(c["path"], v)
    elif fault in {"missing_original", "missing_later", "missing_snapshot"}:
        c[{"missing_original": "original_path", "missing_later": "later_path", "missing_snapshot": "path"}[fault]].unlink()
    elif fault in {"original_hash", "original_source", "original_replay", "later_hash", "later_source"}:
        key = "original_path" if fault.startswith("original") else "later_path"
        v = json.loads(c[key].read_bytes())
        if fault.endswith("source"): v["outputs"]["integrated_investment_decision_product"] = "different"
        elif fault.endswith("replay"): v["generation_context"] = "REPLAY_DIAGNOSTIC"
        else: v["producer_head"] = "tampered"
        write(c[key], v)
    elif fault in {"seal", "receipt", "replay_index", "record_origination", "missing_seal"}:
        p = c["path"].parent / ("prospective_t0_snapshot_write_receipt.json" if fault == "receipt" else "prospective_t0_seal_index.json")
        if fault == "missing_seal": p.unlink()
        else:
            v = json.loads(p.read_bytes())
            if fault == "replay_index": v["evaluation_scope"] = "REPLAY_DIAGNOSTIC"
            elif fault == "record_origination": v["records"]["FPT"]["source_decision_artifact_identity"] = "different"
            else: v["artifact_identity"] = "forged"
            write(p, v)
    elif fault == "orphan": c["hpath"].unlink()
    elif fault == "duplicate_handoff":
        write(c["root"] / "operations-review/canonical-post-close-v1/other/session_handoff_bundle.json", c["handoff"])
    else:
        b = c["handoff"]["prospective_decision_snapshot"]
        if fault == "different_snapshot": b["identity"] = "prospective_decision_snapshot:" + "c" * 64
        elif fault == "another_session": c["handoff"]["session"] = "2026-10-06"
        elif fault == "no_reuse_claim": b.pop("retention")
        elif fault == "original_reference": b["source_integrated_decision_artifact_identity"] = "forged"
        elif fault == "snapshot_path": b["path"] = "other/snapshot.json"
        write(c["hpath"], c["handoff"])
    result = inventory(c)
    assert not result["genuine_snapshots"], fault


def test_valid_and_invalid_streaming_equivalence(reuse):
    before = inventory(reuse)["inventory"]
    assert inventory(reuse, streamed=True)["inventory"] == before
    reuse["handoff"]["prospective_decision_snapshot"].pop("retention")
    write(reuse["hpath"], reuse["handoff"])
    assert inventory(reuse, streamed=True)["inventory"] == inventory(reuse)["inventory"]


def test_rehashing_a_wrong_original_manifest_is_still_unbound(reuse):
    bad, path = operation(reuse["root"], "2026-10-05", "wrong-original-source", epoch="forged")
    # Even a self-consistent different manifest cannot replace the sealed operation.
    reuse["original_path"].unlink()
    assert not inventory(reuse)["genuine_snapshots"]


def test_reuse_does_not_admit_unsealed_current_view(tmp_path):
    write(tmp_path / "operations-review/canonical-post-close-v1/2026-10-05/session_handoff_bundle.json",
          {"session": "2026-10-05", "prospective_decision_snapshot": {"identity": "missing", "retention": "ORIGINAL_SESSION_T0_REUSED"}})
    assert not retention.discover_snapshots(tmp_path)["genuine_snapshots"]


def resign_seal(case, changes, receipt_changes=None):
    """Make cryptographically valid but semantically false companion evidence."""
    p = case["path"].parent / "prospective_t0_seal_index.json"
    value = json.loads(p.read_bytes()); value.update(changes)
    value = seals.identified(value, "prospective_t0_seal_index"); write(p, value)
    rp = p.parent / "prospective_t0_snapshot_write_receipt.json"
    receipt = json.loads(rp.read_bytes())
    receipt.update(index_identity=value["artifact_identity"], index_sha256=value["artifact_sha256"])
    receipt.update(receipt_changes or {})
    receipt = seals.identified(receipt, "prospective_t0_snapshot_write_receipt"); write(rp, receipt)
    case["handoff"]["prospective_decision_snapshot"]["seal_index"].update(
        artifact_identity=value["artifact_identity"], write_receipt_identity=receipt["artifact_identity"])
    write(case["hpath"], case["handoff"])


@pytest.mark.parametrize("fault", ["replay", "non_authoritative", "operation", "source", "raw_write_hash", "created_at"])
def test_valid_crypto_does_not_replace_origination_semantics(reuse, fault):
    changes, receipt_changes = {}, {}
    if fault == "replay": changes["evaluation_scope"] = "REPLAY_DIAGNOSTIC"
    elif fault == "non_authoritative": changes["authority_status"] = "NON_AUTHORITATIVE"
    elif fault == "operation": changes["operation_identity"] = reuse["later"]["operation_identity"]
    elif fault == "source": changes["source_integrated_decision_artifact"] = {"artifact_identity": "different"}
    elif fault == "raw_write_hash":
        changes["snapshot_file_sha256"] = "0" * 64; receipt_changes["snapshot_file_sha256"] = "0" * 64
    elif fault == "created_at": receipt_changes["index_created_at"] = "2026-10-16T11:00:00+00:00"
    resign_seal(reuse, changes, receipt_changes)
    assert not inventory(reuse)["genuine_snapshots"]


def test_capture_bound_original_cannot_be_replaced_by_another_sealed_t0(reuse):
    value = seals.identified({"contract_version": "prospective_capture_complete_session/v1", "session": "2026-10-05",
        "t0_decision_snapshot_identity": "prospective_decision_snapshot:" + "f" * 64}, "prospective_capture_complete_session")
    write(reuse["root"] / "operations-review/prospective-pit-capture-v1/sessions/2026-10-05.json", value)
    assert not inventory(reuse)["genuine_snapshots"]


def test_ambiguous_sealed_origins_are_not_resolved_by_newest(reuse):
    write(reuse["path"].parent.parent / "other/prospective_t0_snapshot_write_receipt.json", {})
    assert not inventory(reuse)["genuine_snapshots"]


def test_rehashed_later_operation_cannot_claim_a_different_decision(reuse):
    manifest, path = operation(reuse["root"], "2026-10-05",
        "integrated_investment_decision_product/v1:" + "c" * 64, epoch="different-valid-manifest")
    reuse["handoff"]["daily_session_operation_identity"] = manifest["operation_identity"]
    write(reuse["hpath"], reuse["handoff"])
    assert not inventory(reuse)["genuine_snapshots"]


def test_valid_native_hash_does_not_qualify_replay_context(reuse):
    value = dict(reuse["original"]); value.pop("operation_identity")
    value["generation_context"] = "REPLAY_DIAGNOSTIC"
    value["operation_identity"] = "daily_research_session_operation:" + stable_id(value)
    p = reuse["root"] / "operations-review/daily-research-session-operations-v1/2026-10-05" / value["operation_identity"].split(":")[1] / "run_manifest.json"
    write(p, value)
    assert not retention._verified_origination_operation(reuse["root"],
        {"path": str(p.relative_to(reuse["root"])), "manifest": value}, identity=value["operation_identity"],
        session="2026-10-05", decision=value["outputs"]["integrated_investment_decision_product"])
