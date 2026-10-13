from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
import ai_handoff_publication as handoff
import pytest
from ai_handoff_publication import HandoffPublicationError, build_package, publish, verify_remote_publication

def git(path,*args): subprocess.run(["git","-C",str(path),*args],check=True,capture_output=True)
def source(path, *, version="one"):
    path.mkdir()
    (path/"ai_research_session_bundle.json").write_text(json.dumps({"artifact_identity":"bundle:"+version}),encoding="utf-8")
    (path/"daily_opportunity_decision_queue_artifact.json").write_text(json.dumps({"artifact_identity":"queue:"+version}),encoding="utf-8")
    (path/"ai_research_bundle_manifest.json").write_text(json.dumps({"artifact_identity":"manifest:"+version,"producer_head":"producer:"+version,"operation_identity":"operation:"+version,"daily_product_identity":"product:"+version}),encoding="utf-8")
def repo(path):
    path.mkdir(); git(path,"init","-q"); git(path,"config","user.email","test@example.com"); git(path,"config","user.name","Test"); (path/"README.md").write_text("x\n"); git(path,"add","README.md"); git(path,"commit","-qm","init")
def legacy(path):
    old=path/"sessions"/"2026-08-28"; old.mkdir(parents=True)
    for name in ("ai_research_session_bundle.json","daily_opportunity_decision_queue_artifact.json","ai_research_bundle_manifest.json"):
        (old/name).write_text(json.dumps({"legacy":name}),encoding="utf-8")
    (old/"HANDOFF.md").write_text("legacy\n",encoding="utf-8")
    git(path,"add","sessions"); git(path,"commit","-qm","legacy session")
    return {p.name:p.read_bytes() for p in old.iterdir()}
def prior(path):
    bundle=path/"2026-08-27"/"prior-build"/"ai_research_session_bundle.json"; bundle.parent.mkdir(parents=True); bundle.write_text(json.dumps({"session":"2026-08-27"}),encoding="utf-8"); return bundle

def test_versioned_build_preserves_legacy_updates_latest_and_is_idempotent(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r); old=legacy(r); previous=prior(tmp_path/"prior")
    first=publish(r,s,"2026-08-28",previous=previous,producer_checkpoint="abc",push=False)
    build=first["package"]["handoff_build_id"]; target=r/first["immutable_session_path"]
    assert target.is_dir() and build in target.as_posix()
    assert {p.name:p.read_bytes() for p in (r/"sessions"/"2026-08-28").iterdir() if p.is_file()} == old
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["handoff_build_id"] == build
    assert latest["immutable_session_path"] == first["immutable_session_path"]
    assert latest["handoff_commit"] == first["immutable_handoff_commit"]
    assert latest["previous_session"] == "2026-08-27"
    assert publish(r,s,"2026-08-28",previous=previous,producer_checkpoint="abc",push=False)["status"] == "NO_OP_ALREADY_PUBLISHED"

def test_same_build_with_mutated_bytes_fails_closed(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    first=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False)
    target=r/first["immutable_session_path"]/"ai_research_session_bundle.json"; target.write_text('{"mutated":true}',encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="HANDOFF_BUILD_CONFLICT"):
        publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False)

def test_second_legitimate_build_for_same_session_is_separate_and_deterministic(tmp_path):
    one,two,r=tmp_path/"one",tmp_path/"two",tmp_path/"repo"; source(one,version="one"); source(two,version="two"); repo(r)
    assert build_package(one,"2026-08-28",producer_checkpoint="abc")[1]["handoff_build_id"] == build_package(one,"2026-08-28",producer_checkpoint="abc")[1]["handoff_build_id"]
    first=publish(r,one,"2026-08-28",producer_checkpoint="abc",push=False)
    first_bytes={p.name:p.read_bytes() for p in (r/first["immutable_session_path"]).iterdir()}
    second=publish(r,two,"2026-08-28",producer_checkpoint="def",push=False)
    assert first["immutable_session_path"] != second["immutable_session_path"]
    assert {p.name:p.read_bytes() for p in (r/first["immutable_session_path"]).iterdir()} == first_bytes
    assert json.loads((r/"LATEST.json").read_text())["handoff_build_id"] == second["package"]["handoff_build_id"]

def test_absolute_paths_are_rejected(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    (s/"ai_research_session_bundle.json").write_text(json.dumps({"path":"D:\\private\\bundle"}),encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="ABSOLUTE_PATH"):
        publish(r,s,"2026-08-28",push=False)

def test_compact_financial_identity_chain_is_validated_without_full_engine_dump(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    identity="financial_analysis_context/v2:abc"
    (s/"ai_research_session_bundle.json").write_text(json.dumps({"financial_analysis":{"source_context_identity":identity,"market_summary":{"source_context_identity":identity},"ticker_index":{"AAA":{"status":"AVAILABLE"}}}}),encoding="utf-8")
    (s/"ai_research_bundle_manifest.json").write_text(json.dumps({"producer_head":"p","operation_identity":"o","daily_product_identity":"d","financial_analysis_source_context_identity":identity}),encoding="utf-8")
    _, payload=build_package(s,"2026-08-28",producer_checkpoint="abc")
    assert payload["lineage"]["financial_analysis_source_context_identity"] == identity
    (s/"ai_research_bundle_manifest.json").write_text(json.dumps({"financial_analysis_source_context_identity":"other"}),encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="FINANCIAL_ANALYSIS_IDENTITY_CHAIN"):
        build_package(s,"2026-08-28",producer_checkpoint="abc")

def test_decision_brief_is_optional_and_additive(tmp_path):
    """A caller that never passes decision_brief sees byte-identical behavior (opt-in only)."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    without=build_package(s,"2026-08-28",producer_checkpoint="abc")
    assert "next_session_decision_brief.json" not in without[0]
    assert "next_session_decision_brief.json" not in without[1]["files"]

def test_decision_brief_included_when_supplied(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    brief=tmp_path/"next_session_decision_brief.json"; brief.write_text(json.dumps({"artifact_identity":"next_session_decision_brief:abc123"}),encoding="utf-8")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False,decision_brief=brief)
    assert (r/result["immutable_session_path"]/"next_session_decision_brief.json").is_file()
    assert result["package"]["lineage"]["next_session_decision_brief_identity"]=="next_session_decision_brief:abc123"
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["decision_brief_sha256"]==result["package"]["files"]["next_session_decision_brief.json"]

def test_comparison_metadata_propagates_into_lineage_and_latest_json(tmp_path):
    """SESSION_REGISTRY_PROMOTION_AND_COMPARISON_SEMANTICS_CORRECTIVE_V1: whatever
    comparison_metadata next_session_decision_brief.json carries must survive, additively,
    into both the handoff package's lineage and the published LATEST.json pointer."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    comparison_metadata={"comparison_session":"2026-08-26","comparison_session_role":"DISTANT_PREVIOUS_GOVERNED_SESSION","session_gap_trading_sessions":5,"is_immediate_previous_completed_session":False,"comparison_fitness":"DEGRADED_MULTI_SESSION_GAP","comparison_reason_codes":["PREVIOUS_SESSION_REGISTRY_GAP"],"skipped_known_sessions":["2026-08-27","2026-08-28","2026-09-03","2026-09-04","2026-09-10"],"notice":"..."}
    brief=tmp_path/"next_session_decision_brief.json"
    brief.write_text(json.dumps({"artifact_identity":"next_session_decision_brief:abc123","comparison_metadata":comparison_metadata}),encoding="utf-8")
    result=publish(r,s,"2026-09-11",producer_checkpoint="abc",push=False,decision_brief=brief)
    assert result["package"]["lineage"]["comparison_metadata"]==comparison_metadata
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["comparison_metadata"]==comparison_metadata

def test_daily_integrated_decision_brief_is_optional_and_additive(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    without=build_package(s,"2026-08-28",producer_checkpoint="abc")
    assert "daily_integrated_decision_brief.json" not in without[0]
    assert "daily_integrated_decision_brief.json" not in without[1]["files"]
    assert "daily_integrated_decision_brief_identity" not in without[1]["lineage"]

def test_daily_integrated_decision_brief_included_when_supplied(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    brief=tmp_path/"daily_integrated_decision_brief.json"
    brief.write_text(json.dumps({"artifact_identity":"daily_integrated_decision_brief/v1:abc123","previous_qualified_session":"2026-08-27"}),encoding="utf-8")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False,daily_integrated_decision_brief=brief)
    assert (r/result["immutable_session_path"]/"daily_integrated_decision_brief.json").is_file()
    assert result["package"]["lineage"]["daily_integrated_decision_brief_identity"]=="daily_integrated_decision_brief/v1:abc123"
    assert result["package"]["lineage"]["daily_integrated_decision_brief_previous_qualified_session"]=="2026-08-27"
    latest=json.loads((r/"LATEST.json").read_text())
    assert latest["daily_integrated_decision_brief_sha256"]==result["package"]["files"]["daily_integrated_decision_brief.json"]

def test_local_only_makes_zero_git_mutation(tmp_path):
    """The exact defect this parameter exists to close: push=False alone still leaves two real
    commits in the handoff repo (see test_versioned_build... below); local_only=True must leave
    the repository's HEAD, working tree, and sessions/ directory completely untouched."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    head_before = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    status_before = subprocess.run(["git","-C",str(r),"status","--porcelain"],capture_output=True,text=True,check=True).stdout
    result = publish(r,s,"2026-08-28",producer_checkpoint="abc",local_only=True)
    assert result["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
    head_after = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    status_after = subprocess.run(["git","-C",str(r),"status","--porcelain"],capture_output=True,text=True,check=True).stdout
    assert head_after == head_before
    assert status_after == status_before
    assert not (r/"sessions").exists()
    assert not (r/"LATEST.json").exists()

def test_local_only_still_computes_the_real_publishable_identity(tmp_path):
    """local_only is genuine validation, not a stub: it must compute the exact same
    handoff_build_id/package hashes a real publish would, proving the package is actually
    publish-ready without ever publishing it."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    _files, direct_payload = build_package(s,"2026-08-28",producer_checkpoint="abc")
    local_result = publish(r,s,"2026-08-28",producer_checkpoint="abc",local_only=True)
    assert local_result["package"] == direct_payload
    real_result = publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False)
    assert local_result["package"]["handoff_build_id"] == real_result["package"]["handoff_build_id"]
    assert local_result["immutable_session_path"] == real_result["immutable_session_path"]

def test_local_only_wins_even_when_push_defaults_true(tmp_path):
    """push defaults to True; a caller must not need to remember push=False on top of
    local_only=True for this to be genuinely zero-Git-mutation -- local_only alone is enough."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    head_before = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    result = publish(r,s,"2026-08-28",producer_checkpoint="abc",local_only=True,push=True)
    assert result["status"] == "LOCAL_VALIDATED_NO_GIT_MUTATION"
    head_after = subprocess.run(["git","-C",str(r),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
    assert head_after == head_before

def test_local_only_still_fails_closed_on_invalid_package(tmp_path):
    """local_only skips Git, never validation -- a genuinely broken source package must still
    raise, not be silently reported as LOCAL_VALIDATED."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    (s/"ai_research_session_bundle.json").write_text(json.dumps({"path":"D:\\private\\bundle"}),encoding="utf-8")
    with pytest.raises(HandoffPublicationError,match="ABSOLUTE_PATH"):
        publish(r,s,"2026-08-28",local_only=True)

def test_daily_integrated_decision_brief_alongside_decision_brief(tmp_path):
    """Both optional artifacts can be published together; each is independently identified."""
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    decision_brief=tmp_path/"next_session_decision_brief.json"; decision_brief.write_text(json.dumps({"artifact_identity":"next_session_decision_brief:abc"}),encoding="utf-8")
    daily_brief=tmp_path/"daily_integrated_decision_brief.json"; daily_brief.write_text(json.dumps({"artifact_identity":"daily_integrated_decision_brief/v1:xyz"}),encoding="utf-8")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=False,decision_brief=decision_brief,daily_integrated_decision_brief=daily_brief)
    assert result["package"]["lineage"]["next_session_decision_brief_identity"]=="next_session_decision_brief:abc"
    assert result["package"]["lineage"]["daily_integrated_decision_brief_identity"]=="daily_integrated_decision_brief/v1:xyz"

def test_remote_verification_binds_latest_pointer_session_hashes_and_lineage(tmp_path):
    s,r=tmp_path/"source",tmp_path/"repo"; source(s); repo(r)
    remote=tmp_path/"remote.git"; subprocess.run(["git","init","--bare","-q",str(remote)],check=True)
    git(r,"branch","-M","main"); git(r,"remote","add","origin",str(remote)); git(r,"push","-u","origin","main")
    result=publish(r,s,"2026-08-28",producer_checkpoint="abc",push=True)
    verified=verify_remote_publication(r,result)
    assert verified["status"]=="READY_FOR_AI"
    assert verified["latest_session"]=="2026-08-28"
    assert verified["remote_sha"]==result["handoff_commit"]


# =====================================================================================
# CANONICAL_DAILY_OWNER_PUBLICATION_RESUME_AND_PRESENTATION_JOIN_V1 section 3 / section 10 item
# E: the AI handoff additively consumes the dedicated post-handoff presentation attestation --
# never mutating the sealed Producer `source` directory -- and exposes its identities/statuses.
# =====================================================================================

def _attestation(*, bound=True):
    projection = (
        {"status": "COLLECTED", "session": "2026-08-28", "lineage_status": "VERIFIED_AGAINST_SEALED_PRODUCER_WORKSPACE",
         "workspace_artifact_identity": "workspace:enriched"}
        if bound else {"status": "UNAVAILABLE", "session": "2026-08-28", "reason": "TEST"}
    )
    return {
        "contract_version": "post_handoff_presentation_attestation/v1", "session": "2026-08-28",
        "presentation_projection": projection,
        "sealed_producer_workspace_artifact_identity": "workspace:sealed",
        "signal_velocity": {"status": "COLLECTED", "artifact_identity": "velocity:1"},
        "current_foreign_flow_enrichment": {
            "status": "COMPLETE", "complete_count": 11, "requested_count": 11, "network_calls_made": 11,
        },
        "flow_price_divergence_shadow": {"status": "COLLECTED", "artifact_identity": "flow_price:1"},
        "post_handoff_prospective_decision_feedback": {"status": "COLLECTED", "artifact_identity": "feedback:1"},
    }


def test_build_package_is_unaffected_when_no_presentation_attestation_supplied(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    files, payload = build_package(s, "2026-08-28", producer_checkpoint="abc")
    assert "post_handoff_presentation_state.json" not in files
    assert "post_handoff_presentation_state" not in payload["lineage"]


def test_build_package_adds_additive_presentation_state_without_touching_sealed_source(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    before = {p.name: p.read_bytes() for p in s.iterdir()}
    files, payload = build_package(s, "2026-08-28", producer_checkpoint="abc", post_handoff_presentation=_attestation())
    assert {p.name: p.read_bytes() for p in s.iterdir()} == before  # sealed source untouched
    assert "post_handoff_presentation_state.json" in files
    assert isinstance(files["post_handoff_presentation_state.json"], (bytes, bytearray))
    lineage = payload["lineage"]["post_handoff_presentation_state"]
    assert lineage["status"] == "COLLECTED"
    assert lineage["workspace_artifact_identity"] == "workspace:enriched"
    assert lineage["sealed_producer_workspace_artifact_identity"] == "workspace:sealed"
    assert lineage["signal_velocity_status"] == "COLLECTED"
    assert lineage["current_foreign_flow_enrichment_status"] == "COMPLETE"
    assert lineage["flow_price_divergence_shadow_status"] == "COLLECTED"
    presentation = json.loads(files["post_handoff_presentation_state.json"].decode("utf-8"))
    assert presentation["current_foreign_flow_enrichment"]["status"] == "COMPLETE"
    assert presentation["current_foreign_flow_enrichment"]["complete_count"] == 11
    assert lineage["post_handoff_prospective_decision_feedback_status"] == "COLLECTED"


def test_build_package_publishes_legitimate_unavailable_presentation_state_not_fabricated(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    _files, payload = build_package(s, "2026-08-28", producer_checkpoint="abc", post_handoff_presentation=_attestation(bound=False))
    assert payload["lineage"]["post_handoff_presentation_state"]["status"] == "UNAVAILABLE"
    assert payload["lineage"]["post_handoff_presentation_state"]["workspace_artifact_identity"] is None


def test_publish_writes_presentation_state_file_and_sealed_source_stays_unchanged(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    before = {p.name: p.read_bytes() for p in s.iterdir()}
    result = publish(r, s, "2026-08-28", producer_checkpoint="abc", push=False, post_handoff_presentation=_attestation())
    target = r / result["immutable_session_path"]
    written = json.loads((target / "post_handoff_presentation_state.json").read_text(encoding="utf-8"))
    assert written["authority_boundary"] == "PRESENTATION_RESEARCH_OBSERVER_STATE_NOT_ANALYTICAL_DECISION_AUTHORITY"
    assert written["sealed_producer_workspace_artifact_identity"] == "workspace:sealed"
    assert written["post_handoff_presentation_workspace_artifact_identity"] == "workspace:enriched"
    assert written["signal_velocity"] == {"status": "COLLECTED", "identity": "velocity:1"}
    assert {p.name: p.read_bytes() for p in s.iterdir()} == before


def test_publish_no_op_replay_still_matches_with_presentation_state_present(tmp_path):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    first = publish(r, s, "2026-08-28", producer_checkpoint="abc", push=False, post_handoff_presentation=_attestation())
    second = publish(r, s, "2026-08-28", producer_checkpoint="abc", push=False, post_handoff_presentation=_attestation())
    assert second["status"] == "NO_OP_ALREADY_PUBLISHED"
    assert second["package"]["handoff_build_id"] == first["package"]["handoff_build_id"]


def _incident_brief(path):
    """Minimal retained-wrapper reproduction of the October 13 PNJ/QNS failure.

    The method identifiers, list indexes, source descriptor and wrapper structure are
    retained from the incident. Fixture identities describe these reduced test bytes.
    """
    descriptor = {
        "provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "/price/ohlc",
        "observed_at": "2026-10-13T21:01:56.488698+07:00", "target_session": "2026-10-13",
        "request_contract": {"from": 1760288400, "resolution": "1D", "to": 1791910799, "type": "STOCK"},
        "no_older_session_substitution": True, "intraday_observations_used": False,
    }
    records = [{"valuation_methods": {}} for _ in range(11)]
    for index, ticker, methods in (
        (5, "PNJ", ("P/E_REPORTED_PERIOD", "P/S_REPORTED_PERIOD")),
        (8, "QNS", ("P/B_OFFICIAL_RESEARCH",)),
    ):
        records[index] = {
            "ticker": ticker,
            "valuation_methods": {
                method: {"status": "RESEARCH_USABLE", "numerator_price_input": {
                    "source": json.loads(json.dumps(descriptor)), "source_snapshot_identity": "retained-snapshot:test",
                }} for method in methods
            },
        }
    payload = {
        "schema_version": "1.0.0", "contract_version": "daily_session_integrated_decision_brief_artifact/v1",
        "session": "2026-10-13", "daily_operation_identity": "retained-operation:test",
        "daily_integrated_decision_brief": {"watchlist": {"records": records}},
        "source_frozen_input_identities": {"valuation_context": "retained-valuation:test"},
    }
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    payload.update({"artifact_identity": "daily_session_integrated_decision_brief_artifact:" + identity,
                    "artifact_sha256": identity})
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


def test_incident_provider_routes_preserve_sealed_wrapper_and_package_identity(tmp_path, monkeypatch):
    s, r = tmp_path / "source", tmp_path / "repo"
    source(s); repo(r)
    brief = s / "daily_integrated_decision_brief_artifact.json"
    original = _incident_brief(brief)
    source_before = {p.name: p.read_bytes() for p in s.iterdir()}
    head_before = handoff._git(r, "rev-parse", "HEAD")
    status_before = handoff._git(r, "status", "--porcelain")
    direct = build_package(s, "2026-10-13", producer_checkpoint="released:test",
                           daily_integrated_decision_brief=brief)[1]
    # local_only must not call Git, including for path/order checks in the destination.
    with monkeypatch.context() as bounded:
        bounded.setattr(handoff, "_git", lambda *a, **k: pytest.fail("local_only called Git"))
        bounded.setattr(handoff, "_git_bytes", lambda *a, **k: pytest.fail("local_only read Git"))
        local = publish(r, s, "2026-10-13", producer_checkpoint="released:test",
                        daily_integrated_decision_brief=brief, local_only=True)
    repeated = build_package(s, "2026-10-13", producer_checkpoint="released:test",
                             daily_integrated_decision_brief=brief)[1]
    assert local["package"] == direct == repeated
    assert direct["files"]["daily_integrated_decision_brief.json"] == hashlib.sha256(source_before[brief.name]).hexdigest()
    assert direct["lineage"]["daily_integrated_decision_brief_identity"] == original["artifact_identity"]
    assert {p.name: p.read_bytes() for p in s.iterdir()} == source_before
    assert handoff._git(r, "rev-parse", "HEAD") == head_before
    assert handoff._git(r, "status", "--porcelain") == status_before
    assert not (r / "sessions").exists()
    assert not (r / "LATEST.json").exists()
    published = publish(r, s, "2026-10-13", producer_checkpoint="released:test",
                        daily_integrated_decision_brief=brief, push=False)
    delivered = r / published["immutable_session_path"] / "daily_integrated_decision_brief.json"
    assert delivered.read_bytes() == source_before[brief.name]
    assert json.loads(delivered.read_text(encoding="utf-8"))["artifact_identity"] == original["artifact_identity"]
    assert published["package"] == direct
    assert {p.name: p.read_bytes() for p in s.iterdir()} == source_before


@pytest.mark.parametrize("descriptor, key", [
    ({"provider": "FHSC", "dataset": "DNSE_OHLC_1D", "endpoint": "/price/ohlc"}, "endpoint"),
    ({"dataset": "DNSE_OHLC_1D", "endpoint": "/price/ohlc"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "other", "endpoint": "/price/ohlc"}, "endpoint"),
    ({"provider": "DNSE", "endpoint": "/price/ohlc"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "path": "/price/ohlc"}, "path"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "/price/ohlc/private"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "/price/ohlc?file=private"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "/price/ohlc/../../private"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "//price/ohlc"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "C:\\private\\secret.json"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "C:/private/secret.json"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "\\\\private-server\\share\\secret.json"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "/private/secret.json"}, "endpoint"),
    ({"provider": "DNSE", "dataset": "DNSE_OHLC_1D", "endpoint": "/price/ohlc", "private_path": "/private/secret.json"}, "private_path"),
])
def test_provider_route_exception_rejects_unsafe_context_and_siblings(tmp_path, descriptor, key):
    s = tmp_path / "source"; source(s)
    brief = s / "daily_integrated_decision_brief_artifact.json"
    fixture = _incident_brief(brief)
    fixture["daily_integrated_decision_brief"]["watchlist"]["records"][5]["valuation_methods"]["P/E_REPORTED_PERIOD"]["numerator_price_input"]["source"] = descriptor
    brief.write_text(json.dumps(fixture), encoding="utf-8")
    before = brief.read_bytes()
    with pytest.raises(HandoffPublicationError, match="HANDOFF_ABSOLUTE_PATH_FORBIDDEN") as raised:
        publish(tmp_path / "untouched", s, "2026-10-13", local_only=True,
                daily_integrated_decision_brief=brief)
    message = str(raised.value)
    assert "/daily_integrated_decision_brief/watchlist/records/5/valuation_methods/P~1E_REPORTED_PERIOD/numerator_price_input/source/" + key in message
    assert descriptor[key] not in message
    assert brief.read_bytes() == before
    assert not (tmp_path / "untouched").exists()


@pytest.mark.parametrize("private_key", ["C:\\private\\key", "\\\\private-server\\share\\key", "/private/key"])
def test_absolute_dictionary_keys_are_rejected_without_disclosing_them(tmp_path, private_key):
    s = tmp_path / "source"; source(s)
    (s / "ai_research_session_bundle.json").write_text(json.dumps({"nested": [{private_key: "otherwise-safe"}]}), encoding="utf-8")
    with pytest.raises(HandoffPublicationError, match="HANDOFF_ABSOLUTE_PATH_FORBIDDEN") as raised:
        publish(tmp_path / "untouched", s, "2026-10-13", local_only=True)
    assert "/nested/0" in str(raised.value)
    assert private_key not in str(raised.value)
    assert not (tmp_path / "untouched").exists()


def _remote_repo(tmp_path):
    r = tmp_path / "repo"; repo(r)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True, capture_output=True)
    git(r, "branch", "-M", "main"); git(r, "remote", "add", "origin", str(remote)); git(r, "push", "-u", "origin", "main")
    return r


def test_real_remote_identical_replay_reports_pointer_head_and_verifies(tmp_path):
    s = tmp_path / "source"; source(s)
    r = _remote_repo(tmp_path)
    first = publish(r, s, "2026-10-13", producer_checkpoint="released:test")
    assert verify_remote_publication(r, first)["remote_sha"] == first["handoff_commit"]
    head_before = handoff._git(r, "rev-parse", "HEAD")
    repeated = publish(r, s, "2026-10-13", producer_checkpoint="released:test")
    assert repeated["status"] == "NO_OP_ALREADY_PUBLISHED"
    assert repeated["handoff_commit"] == first["handoff_commit"] == head_before
    assert repeated["immutable_handoff_commit"] == first["immutable_handoff_commit"]
    assert repeated["immutable_handoff_commit"] != repeated["handoff_commit"]
    assert verify_remote_publication(r, repeated)["remote_sha"] == head_before
    assert handoff._git(r, "rev-parse", "HEAD") == head_before


@pytest.mark.parametrize("older_build_exists", [False, True])
def test_newer_latest_blocks_older_publication_before_any_write(tmp_path, older_build_exists):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    if older_build_exists:
        publish(r, s, "2026-10-13", producer_checkpoint="released:test", push=False)
    publish(r, s, "2026-10-14", producer_checkpoint="released:test", push=False)
    before = {p.relative_to(r).as_posix(): p.read_bytes() for p in r.rglob("*") if p.is_file() and ".git" not in p.relative_to(r).parts}
    head_before = handoff._git(r, "rev-parse", "HEAD")
    with pytest.raises(HandoffPublicationError, match="NEWER|ORDER|REGRESSION"):
        publish(r, s, "2026-10-13", producer_checkpoint="released:test", push=False)
    assert handoff._git(r, "rev-parse", "HEAD") == head_before
    assert handoff._git(r, "status", "--porcelain") == ""
    assert {p.relative_to(r).as_posix(): p.read_bytes() for p in r.rglob("*") if p.is_file() and ".git" not in p.relative_to(r).parts} == before


@pytest.mark.parametrize("crash_boundary", ["pointer_write", "pointer_commit"])
def test_replay_recovers_committed_build_after_pointer_crash_without_rewriting(tmp_path, monkeypatch, crash_boundary):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    actual_git, actual_write = handoff._git, Path.write_text
    with monkeypatch.context() as interrupted:
        if crash_boundary == "pointer_write":
            def fail_pointer_write(path, *args, **kwargs):
                if path == r / "LATEST.json":
                    raise OSError("simulated pointer write interruption")
                return actual_write(path, *args, **kwargs)
            interrupted.setattr(Path, "write_text", fail_pointer_write)
        else:
            def fail_pointer_commit(path, *args):
                if args[0] == "commit" and " latest " in args[-1]:
                    raise HandoffPublicationError("simulated pointer commit interruption")
                return actual_git(path, *args)
            interrupted.setattr(handoff, "_git", fail_pointer_commit)
        with pytest.raises((OSError, HandoffPublicationError), match="simulated pointer"):
            publish(r, s, "2026-10-13", producer_checkpoint="released:test", push=False)
    immutable_commit = actual_git(r, "rev-parse", "HEAD")
    target = next((r / "sessions" / "2026-10-13" / "builds").iterdir())
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in target.iterdir()}
    with monkeypatch.context() as resumed:
        resumed.setattr(handoff.shutil, "copyfile", lambda *a, **k: pytest.fail("replay rewrote sealed build"))
        result = publish(r, s, "2026-10-13", producer_checkpoint="released:test", push=False)
    assert result["immutable_handoff_commit"] == immutable_commit
    assert result["handoff_commit"] == actual_git(r, "rev-parse", "HEAD")
    assert result["handoff_commit"] != immutable_commit
    latest = json.loads((r / "LATEST.json").read_text(encoding="utf-8"))
    assert latest["handoff_commit"] == immutable_commit
    assert latest["immutable_session_path"] == result["immutable_session_path"]
    assert latest["handoff_build_id"] == result["package"]["handoff_build_id"]
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in target.iterdir()} == before
    assert actual_git(r, "status", "--porcelain") == ""


def test_existing_uncommitted_build_is_not_accepted_as_published(tmp_path, monkeypatch):
    s, r = tmp_path / "source", tmp_path / "repo"; source(s); repo(r)
    actual_git = handoff._git
    with monkeypatch.context() as interrupted:
        def fail_build_commit(path, *args):
            if args[0] == "commit" and " build " in args[-1]:
                raise HandoffPublicationError("simulated immutable commit interruption")
            return actual_git(path, *args)
        interrupted.setattr(handoff, "_git", fail_build_commit)
        with pytest.raises(HandoffPublicationError, match="simulated immutable"):
            publish(r, s, "2026-10-13", producer_checkpoint="released:test", push=False)
    head_before = actual_git(r, "rev-parse", "HEAD")
    status_before = actual_git(r, "status", "--porcelain")
    with pytest.raises(HandoffPublicationError):
        publish(r, s, "2026-10-13", producer_checkpoint="released:test", push=False)
    assert actual_git(r, "rev-parse", "HEAD") == head_before
    assert actual_git(r, "status", "--porcelain") == status_before
    assert not (r / "LATEST.json").exists()


def test_push_interruption_retry_publishes_committed_pointer_without_extra_commits(tmp_path, monkeypatch):
    s = tmp_path / "source"; source(s)
    r = _remote_repo(tmp_path)
    actual_git = handoff._git
    with monkeypatch.context() as interrupted:
        def fail_push(path, *args):
            if args[0] == "push":
                raise HandoffPublicationError("simulated remote push interruption")
            return actual_git(path, *args)
        interrupted.setattr(handoff, "_git", fail_push)
        with pytest.raises(HandoffPublicationError, match="simulated remote push"):
            publish(r, s, "2026-10-13", producer_checkpoint="released:test")
    pointer_head = actual_git(r, "rev-parse", "HEAD")
    assert actual_git(r, "rev-parse", "origin/main") != pointer_head
    result = publish(r, s, "2026-10-13", producer_checkpoint="released:test")
    assert result["handoff_commit"] == pointer_head
    assert actual_git(r, "rev-parse", "HEAD") == pointer_head
    assert verify_remote_publication(r, result)["remote_sha"] == pointer_head
    assert actual_git(r, "status", "--porcelain") == ""


@pytest.mark.parametrize("field, artifact_name", [
    ("session_bundle_sha256", "ai_research_session_bundle.json"),
    ("opportunity_artifact_sha256", "daily_opportunity_decision_queue_artifact.json"),
    ("manifest_sha256", "ai_research_bundle_manifest.json"),
    ("decision_brief_sha256", "next_session_decision_brief.json"),
    ("daily_integrated_decision_brief_sha256", "daily_integrated_decision_brief.json"),
])
def test_remote_verifier_rejects_committed_latest_hash_tampering(tmp_path, field, artifact_name):
    s = tmp_path / "source"; source(s)
    r = _remote_repo(tmp_path)
    decision = s / "next_session_decision_brief.json"
    decision.write_text(json.dumps({"artifact_identity": "next_session_decision_brief:fixture"}), encoding="utf-8")
    daily = s / "daily_integrated_decision_brief_artifact.json"; _incident_brief(daily)
    published = publish(r, s, "2026-10-13", producer_checkpoint="released:test",
                        decision_brief=decision, daily_integrated_decision_brief=daily)
    verify_remote_publication(r, published)
    latest_path = r / "LATEST.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest[field] == published["package"]["files"][artifact_name]
    latest[field] = "0" * 64
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    git(r, "add", "LATEST.json"); git(r, "commit", "-qm", "test: corrupt advertised artifact hash"); git(r, "push")
    # Match the remote HEAD deliberately, so rejection must prove semantic integrity.
    tampered_receipt = {**published, "handoff_commit": handoff._git(r, "rev-parse", "HEAD")}
    with pytest.raises(HandoffPublicationError) as raised:
        verify_remote_publication(r, tampered_receipt)
    assert str(raised.value) == "REMOTE_LATEST_HASH_MISMATCH:" + artifact_name


def test_remote_verifier_rejects_committed_immutable_commit_tampering(tmp_path):
    s = tmp_path / "source"; source(s)
    r = _remote_repo(tmp_path)
    published = publish(r, s, "2026-10-13", producer_checkpoint="released:test")
    verify_remote_publication(r, published)
    latest_path = r / "LATEST.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["handoff_commit"] == published["immutable_handoff_commit"]
    # A valid Git object that is the pointer commit still cannot replace the build commit.
    latest["handoff_commit"] = published["handoff_commit"]
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    git(r, "add", "LATEST.json"); git(r, "commit", "-qm", "test: corrupt immutable commit reference"); git(r, "push")
    tampered_receipt = {**published, "handoff_commit": handoff._git(r, "rev-parse", "HEAD")}
    with pytest.raises(HandoffPublicationError) as raised:
        verify_remote_publication(r, tampered_receipt)
    assert str(raised.value) == "REMOTE_IMMUTABLE_COMMIT_MISMATCH"


def test_remote_verifier_rejects_committed_immutable_artifact_tampering(tmp_path):
    s = tmp_path / "source"; source(s)
    r = _remote_repo(tmp_path)
    published = publish(r, s, "2026-10-13", producer_checkpoint="released:test")
    verify_remote_publication(r, published)
    relative = published["immutable_session_path"] + "/ai_research_session_bundle.json"
    (r / relative).write_text(json.dumps({"artifact_identity": "tampered-after-publication"}), encoding="utf-8")
    git(r, "add", relative); git(r, "commit", "-qm", "test: corrupt immutable artifact bytes"); git(r, "push")
    tampered_receipt = {**published, "handoff_commit": handoff._git(r, "rev-parse", "HEAD")}
    with pytest.raises(HandoffPublicationError) as raised:
        verify_remote_publication(r, tampered_receipt)
    assert str(raised.value) == "REMOTE_FILE_HASH_MISMATCH:ai_research_session_bundle.json"


def test_publication_preserves_crlf_sealed_bytes_under_host_and_repository_text_conversion(tmp_path):
    s = tmp_path / "source"; source(s)
    r = _remote_repo(tmp_path)
    git(r, "config", "core.autocrlf", "true")
    (r / ".gitattributes").write_bytes(b"*.json text eol=lf\n")
    git(r, "add", ".gitattributes"); git(r, "commit", "-qm", "test: enforce repository JSON normalization"); git(r, "push")
    brief = s / "daily_integrated_decision_brief_artifact.json"; _incident_brief(brief)
    original = brief.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    brief.write_bytes(original)
    assert original.count(b"\r\n") > 1
    source_before = {p.name: p.read_bytes() for p in s.iterdir()}
    published = publish(r, s, "2026-10-13", producer_checkpoint="released:test",
                        daily_integrated_decision_brief=brief)
    copied = r / published["immutable_session_path"] / "daily_integrated_decision_brief.json"
    assert copied.read_bytes() == original
    assert published["package"]["files"]["daily_integrated_decision_brief.json"] == hashlib.sha256(original).hexdigest()
    assert verify_remote_publication(r, published)["remote_sha"] == published["handoff_commit"]
    remote_name = published["immutable_session_path"] + "/daily_integrated_decision_brief.json"
    fields = handoff._git(r, "ls-tree", "origin/main", "--", remote_name).split("\t", 1)[0].split()
    assert handoff._git_bytes(r, "cat-file", "blob", fields[2]) == original
    assert {p.name: p.read_bytes() for p in s.iterdir()} == source_before
