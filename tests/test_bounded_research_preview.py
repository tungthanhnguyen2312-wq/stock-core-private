"""Offline full-verification, selection, parity and adversarial resource boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import time
import tracemalloc

import pytest

import daily_research_session_operations as ops
import personal_investment_decision_action_center as ac
from stocklookup_core.decision import bounded_research_preview as b
from stocklookup_core.decision import integrated_investment_decision_product as iid
from stocklookup_core.evidence import artifact_stream as stream
from stocklookup_core.tactical import watchlist_tactical_entry_classifier as tactical

H = runpy.run_path(str(Path(__file__).with_name("test_research_setup_transition_v1.py")))
CURRENT, PREVIOUS = H["SESSION"], H["PREVIOUS"]
RESOURCE_GATE = b.resource_gate


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    return path


def fixture(root, *, previous=True, mutate=None):
    prev, curr = H["_cases"]()
    # The older fixture deliberately mixes root/record epochs; native verified input cannot.
    prev["records"]["JJJ_EPOCH"]["research_action_policy_version"] = "v2"
    prev["records"]["JJJ_EPOCH"]["decision_identity"] = iid.decision_identity(prev["records"]["JJJ_EPOCH"])
    if mutate:
        mutate(prev, curr)
    registry = {"contract_version": "daily_research_session_input_registry/v1", "sessions": {}, "completed_sessions": {}}
    locations = {}
    artifacts = [prev, curr] if previous else [curr]
    for artifact in artifacts:
        date = artifact["session"]
        artifact["schema_version"] = "integrated_investment_decision_product/1.0.0"
        artifact["coverage"] = {"universe_denominator": len(artifact["records"]), "integrated_context_available": len(artifact["records"])}
        artifact.update(iid.content_identity(artifact))
        iid_path = root / "operations-review" / ("integrated-investment-decision-product-v1-" + date.replace("-", "")) / "integrated_investment_decision_product_artifact.json"
        write(iid_path, artifact)
        tac = {"session": date, "contract_version": tactical.CONTRACT_VERSION,
               "records": {t: {"entry_state": "BREAKOUT_READY" if r["research_action_posture"] == "INITIATE_ON_BREAKOUT" else "SIDEWAYS_NEUTRAL"}
                           for t, r in artifact["records"].items()}}
        tac.update(tactical.content_identity(tac))
        tac_path = write(root / ("tactical-" + date + ".json"), tac)
        selection = {name: {"path": name + ".json", "artifact_identity": "synthetic:" + name + ":" + date} for name in ops.REQUIRED}
        selection["tactical"] = {"path": tac_path.relative_to(root).as_posix(), "artifact_identity": tac["artifact_identity"]}
        lock = {k: v["artifact_identity"] for k, v in selection.items()}
        registry["sessions"][date] = selection
        registry["completed_sessions"][date] = {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True, "frozen_input_identities": lock}
        manifest = {"contract_version": ops.CONTRACT_VERSION, "schema_version": "1.0.0", "market_session": date,
                    "generation_context": "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION",
                    "input_artifacts": {k: {"artifact_identity": v} for k, v in lock.items()},
                    "outputs": {"integrated_investment_decision_product": artifact["artifact_identity"]}}
        manifest["operation_identity"] = ops._identity(manifest)
        operation = root / "operations-review/daily-research-session-operations-v1" / date / manifest["operation_identity"].split(":")[1]
        write(operation / "run_manifest.json", manifest)
        locations[date] = operation
    write(root / "config/daily_research_session_input_registry.json", registry)
    return prev, curr, locations


def evaluate(root, locations, tickers):
    return ac.evaluate_selected_research_preview(repo_root=root, session=CURRENT, tickers=tickers,
        current_operation=locations[CURRENT], previous_operation=locations.get(PREVIOUS))


@pytest.fixture(autouse=True)
def safe_host(monkeypatch):
    # Tests do not depend on the developer machine's transient memory pressure.
    original = b.resource_gate
    monkeypatch.setattr(b, "resource_gate", lambda: original(available_bytes=2 * 1024**3))


@pytest.mark.parametrize("tickers", [["AAA_SAME"], ["AAA_SAME", "DDD_PEND", "EEE_CONF", "GGG_PRIORITY", "HHH_ABSENT", "III_STALE", "MISSING"]])
def test_verified_selected_renderer_and_default_semantics(tmp_path, tickers):
    prev, curr, locations = fixture(tmp_path)
    result = evaluate(tmp_path, locations, tickers)
    assert result == evaluate(tmp_path, locations, list(reversed(tickers)))
    assert result["source_proofs"]["current"]["source_identity"] == curr["artifact_identity"]
    assert result["scope"]["full_source_denominator"] == len(curr["records"])
    assert result["scope"]["selected_record_count"] == len(set(tickers) & set(curr["records"]))
    assert result["scope"]["statistics_scope"] == "SELECTED_TICKERS_ONLY"
    assert result["scope"]["excluded_source_record_count"] + len(result["entries"]) == len(curr["records"])
    for entry in result["entries"]:
        t = entry["ticker"]
        explanation = entry["evidence"]["conditional_research"]["setup_transition"]
        assert explanation["governed_transition_label"] == ac._expected_posture_label(prev["records"].get(t), curr["records"][t], prev, curr)
        assert entry["evidence"]["research_action_posture"] == curr["records"][t]["research_action_posture"]
        assert entry["evidence"]["counter_thesis"] == curr["records"][t]["counter_thesis"]
    rendered = ac.selected_research_preview_markdown(result)
    assert "not a full Action Center" in rendered and "future condition=" in rendered
    assert "not observed events" in rendered
    assert result["private_portfolio"] == "NOT_REQUESTED_OR_READ"
    if "GGG_PRIORITY" in tickers:
        assert result["selected_statistics"]["priority_posture_disagreements"] == 1
    # Existing default golden is tested by its existing independent test suite.


def test_no_previous_qualified_session(tmp_path):
    _, _, locations = fixture(tmp_path, previous=False)
    result = evaluate(tmp_path, locations, ["AAA_SAME"])
    transition = result["entries"][0]["evidence"]["conditional_research"]["setup_transition"]
    assert transition["status"] == "UNAVAILABLE" and transition["governed_transition_label"] is None
    assert not result["selected_statistics"]["transition_counts"]


def test_all_setup_cases_and_tactical_membership(tmp_path):
    prev, curr, locations = fixture(tmp_path)
    result = evaluate(tmp_path, locations, sorted(curr["records"]))
    evidence = {e["ticker"]: e["evidence"] for e in result["entries"]}
    transition = lambda t: evidence[t]["conditional_research"]["setup_transition"]
    assert transition("AAA_SAME")["governed_transition_label"] == "POSTURE_UNCHANGED"
    assert transition("DDD_PEND")["governed_transition_label"] == "WAIT_TO_INITIATE"
    assert transition("DDD_PEND")["tactical_confirmation"]["status"] == "GAINED_CONFIRMATION"
    assert transition("DDD_PEND")["tactical_confirmation"]["source"] == "verified_registered_tactical_selected_projection"
    assert transition("EEE_CONF")["governed_transition_label"] == "BREAKOUT_FAILED"
    assert transition("EEE_CONF")["tactical_confirmation"]["status"] == "LOST_CONFIRMATION"
    assert transition("BBB_NEW")["current_canonical_posture"] == "EARLY_WATCH"
    assert transition("FFF_WEAK")["technical_market_sector_evidence"]["market_regime"]["status"] == "CHANGED"
    assert evidence["HHH_ABSENT"]["conditional_research"]["fundamental_evidence_availability"] == "ABSENT"
    assert evidence["III_STALE"]["conditional_research"]["fundamental_evidence_availability"] == "STALE_ONLY"


@pytest.mark.parametrize("kind", ["research", "fundamental"])
def test_different_policy_epochs_are_not_issuer_evolution(tmp_path, kind):
    def mutate(prev, curr):
        for row in prev["records"].values():
            if kind == "research":
                row["research_action_policy_version"] = "v1"
            else:
                row["fundamental_decision_policy_version"] = "different-native-policy"
            row["decision_identity"] = iid.decision_identity(row)
        if kind == "research":
            prev["research_action_policy_version"] = "v1"
    _, _, locations = fixture(tmp_path, mutate=mutate)
    result = evaluate(tmp_path, locations, ["AAA_SAME", "DDD_PEND"])
    assert result["selected_statistics"]["qualified_comparable_tickers"] == 0
    for entry in result["entries"]:
        transition = entry["evidence"]["conditional_research"]["setup_transition"]
        if kind == "research":
            assert transition["governed_transition_label"] == "NOT_COMPARABLE_POLICY_CHANGE"
            assert transition["tactical_confirmation"]["status"] == "NOT_INTERPRETED"
        else:
            assert transition["setup_context"]["fundamental_state"]["status"] == "NOT_COMPARABLE_POLICY_CHANGE"


@pytest.mark.parametrize("dimension", ["price_unit", "currency", "scale"])
def test_conflicting_price_dimensions_fail_closed(tmp_path, dimension):
    def mutate(prev, curr):
        prev["records"]["AAA_SAME"]["trigger"]["price_basis"][dimension] = "PREVIOUS_VALUE"
        curr["records"]["AAA_SAME"]["trigger"]["price_basis"][dimension] = "CURRENT_VALUE"
    _, _, locations = fixture(tmp_path, mutate=mutate)
    with pytest.raises(ValueError, match="PRICE_DIMENSION_CONFLICT"):
        evaluate(tmp_path, locations, ["AAA_SAME"])


def test_unqualified_basis_and_unit_keep_qualitative_conditions(tmp_path):
    def mutate(prev, curr):
        curr["records"]["AAA_SAME"]["trigger"]["price_basis"].update(price_basis_verified=False, price_unit=None)
    _, _, locations = fixture(tmp_path, mutate=mutate)
    result = evaluate(tmp_path, locations, ["AAA_SAME"])
    boundary = result["entries"][0]["evidence"]["conditional_research"]["trigger"]
    assert boundary["numeric_display_status"] == "WITHHELD_UNQUALIFIED_BOUNDARY"
    assert boundary["trigger_level"] is None and boundary["condition"]["reference_level"] is None
    assert boundary["condition"]["activation_semantics"]


def test_known_optional_manifest_input_is_not_a_frozen_registry_input(tmp_path):
    _, _, locations = fixture(tmp_path)
    path = locations[CURRENT] / "run_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["input_artifacts"]["macro"] = {"artifact_identity": "synthetic:macro-not-consumed"}
    manifest["operation_identity"] = ops._identity(manifest)
    locations[CURRENT] = path.parent.parent / manifest["operation_identity"].split(":")[1]
    write(locations[CURRENT] / "run_manifest.json", manifest)
    assert evaluate(tmp_path, locations, ["AAA_SAME"])["verification"] == "FULL_NATIVE_CONTENT_VERIFIED"


@pytest.mark.parametrize("mutation,reason", [
    (lambda a: a["records"]["AAA_SAME"].update(decision_identity="wrong"), "DECISION_IDENTITY"),
    (lambda a: a["records"]["AAA_SAME"].update(as_of_session=PREVIOUS), "SESSION_OR_TICKER"),
    (lambda a: a.update(session=PREVIOUS), "CONTRACT_SESSION_OR_IDENTITY"),
    (lambda a: a.update(contract_version="wrong/v2"), "CONTRACT_SESSION_OR_IDENTITY"),
    (lambda a: a.update(schema_version="wrong/1.0.0"), "SOURCE_SCHEMA"),
    (lambda a: a.update(research_action_policy_version="v1"), "ROOT_RECORD_POLICY"),
    (lambda a: a["coverage"].update(universe_denominator=1), "DENOMINATOR"),
])
def test_resigned_invalid_source_still_fails(tmp_path, mutation, reason):
    _, curr, _ = fixture(tmp_path)
    mutation(curr)
    curr.update(iid.content_identity(curr))
    p = write(tmp_path / "invalid.json", curr)
    with pytest.raises(ValueError, match=reason):
        b.verified_projection(p, session=CURRENT, expected_identity=curr["artifact_identity"], tickers=["AAA_SAME"], deadline=time.monotonic()+30)


@pytest.mark.parametrize("text", [
    '{"records":{"A":{"nested":{"x":1,"x":2}}}}',
    '{"records":{"A":{},"A":{}}}', '{"records":{},"records":{}}',
    '{"records":{"A":{"n":NaN}}}', '{"records":{"A":{"n":Infinity}}}',
    '{"records":{"A":{"n":1e999}}}', '{"records":{', '{"records":{}} trailing',
    '{"records":{"A": [}', '{"records":{"A":' + '"' + 'x'*6000,
    '\u00a0{"records":{}}', '{"records":{}}\u00a0',
])
def test_invalid_json_never_verified(tmp_path, text):
    p = tmp_path / "bad.json"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        stream.stream_artifact(p, excluded=set(), on_record=lambda *args: None,
                               strict=True, member_limit=4096)


def test_native_hash_equivalence_unicode_floats_exclusions_and_nested_keys(tmp_path):
    _, curr, _ = fixture(tmp_path)
    curr["requested_at"] = "excluded from native identity"
    curr["records"]["AAA_SAME"]["stress"] = {"Việt 😀": [-0.0, 1e-30, True, None, {"z": "quoted\"\n"}]}
    curr.update(iid.content_identity(curr))
    path = write(tmp_path / "oracle.json", curr)
    metadata, digest, count = stream.stream_artifact(path, excluded=iid._IDENTITY_EXCLUDED, on_record=lambda *args: None, strict=True)
    assert digest == iid.content_identity(curr)["artifact_sha256"] == curr["artifact_sha256"]
    assert count == len(curr["records"])
    assert metadata["artifact_identity"] == curr["artifact_identity"]


def test_nonselected_tampering_blocks_the_entire_preview(tmp_path):
    _, _, locations = fixture(tmp_path)
    path = next((tmp_path / "operations-review" / ("integrated-investment-decision-product-v1-" + CURRENT.replace("-", ""))).glob("*.json"))
    value = json.loads(path.read_text(encoding="utf-8"))
    value["records"]["III_STALE"]["why_now"] = "tampered nonselected evidence"
    write(path, value)
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        evaluate(tmp_path, locations, ["AAA_SAME"])


def test_wrong_previous_operation_and_manifest_reference(tmp_path):
    _, _, locations = fixture(tmp_path)
    wrong = dict(locations, **{PREVIOUS: locations[CURRENT]})
    with pytest.raises(ValueError, match="OPERATION_IDENTITY_OR_SESSION"):
        evaluate(tmp_path, wrong, ["AAA_SAME"])
    p = locations[CURRENT] / "run_manifest.json"
    value = json.loads(p.read_text())
    value["outputs"].pop("integrated_investment_decision_product")
    value["operation_identity"] = ops._identity(value)
    new = p.parent.parent / value["operation_identity"].split(":")[1]
    write(new / "run_manifest.json", value)
    locations[CURRENT] = new
    with pytest.raises(ValueError, match="MANIFEST_INTEGRATED_REFERENCE_REQUIRED"):
        evaluate(tmp_path, locations, ["AAA_SAME"])


def test_replay_operation_cannot_claim_original_completed_daily(tmp_path):
    _, _, locations = fixture(tmp_path)
    path = locations[CURRENT] / "run_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["generation_context"] = "RETAINED_FIXED_TIME_REPLAY"
    manifest["operation_identity"] = ops._identity(manifest)
    locations[CURRENT] = path.parent.parent / manifest["operation_identity"].split(":")[1]
    write(locations[CURRENT] / "run_manifest.json", manifest)
    with pytest.raises(ValueError, match="OPERATION_IDENTITY_OR_SESSION"):
        evaluate(tmp_path, locations, ["AAA_SAME"])


@pytest.mark.parametrize("tickers", [[], list(map(str, range(21))), ["AAA_SAME", "AAA_SAME"], ["../escape"]])
def test_selection_refused(tmp_path, tickers):
    with pytest.raises(ValueError, match="SELECTION"):
        b.select_tickers(tickers)


def test_selection_does_not_materialize_unbounded_iterables():
    consumed = []
    def many():
        for i in range(1_000_000):
            consumed.append(i)
            yield str(i)
    with pytest.raises(ValueError, match="SELECTION"):
        b.select_tickers(many())
    assert len(consumed) == b.MAX_SELECTED + 1


def test_resource_deadline_and_limits(tmp_path):
    with pytest.raises(ValueError, match="RESOURCE_BUDGET"):
        RESOURCE_GATE(available_bytes=1)


def test_resource_refusal_precedes_all_source_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "resource_gate", lambda: RESOURCE_GATE(available_bytes=0))
    def forbidden(*args, **kwargs):
        raise AssertionError("unsafe read before admission")
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(ValueError, match="RESOURCE_BUDGET"):
        ac.evaluate_selected_research_preview(repo_root=tmp_path, session=CURRENT,
            tickers=["AAA_SAME"], current_operation=tmp_path)


def test_source_and_selected_payload_budgets(tmp_path, monkeypatch):
    _, curr, _ = fixture(tmp_path)
    p = write(tmp_path / "budget.json", curr)
    kwargs = dict(session=CURRENT, expected_identity=curr["artifact_identity"],
                  tickers=["AAA_SAME"], deadline=time.monotonic()+30)
    monkeypatch.setattr(b, "MAX_SELECTED_BYTES", 10)
    with pytest.raises(ValueError, match="SELECTED_PAYLOAD_LIMIT"):
        b.verified_projection(p, **kwargs)
    monkeypatch.setattr(b, "MAX_SOURCE_BYTES", 1)
    with pytest.raises(ValueError, match="SOURCE_SIZE_REFUSED"):
        b.verified_projection(p, **kwargs)


def test_parser_member_metadata_and_deadline_refusal(tmp_path):
    path = write(tmp_path / "large.json", {"records": {"A": {"x": "x" * 8000}}})
    with pytest.raises(ValueError, match="MEMBER_LIMIT"):
        stream.stream_artifact(path, excluded=set(), on_record=lambda *args: None, member_limit=4096, strict=True)
    with pytest.raises(ValueError, match="DEADLINE"):
        stream.stream_artifact(path, excluded=set(), on_record=lambda *args: None, strict=True, deadline=time.monotonic()-1)
    write(path, {"metadata": "x" * 100, "records": {}})
    with pytest.raises(ValueError, match="METADATA_LIMIT"):
        stream.stream_artifact(path, excluded=set(), on_record=lambda *args: None, strict=True, metadata_limit=50)


def test_stress_record_growth_does_not_retain_source_graph(tmp_path):
    peaks = []
    for count in (10, 1000):
        p = tmp_path / f"stress-{count}.json"
        # Generate the file incrementally, outside the measured consumer interval.
        with p.open("w", encoding="utf-8") as f:
            f.write('{"records":{')
            for i in range(count):
                if i:
                    f.write(',')
                f.write(json.dumps(f"T{i:05d}") + ':' + json.dumps({"payload": "x" * 4096}))
            f.write('}}')
        retained = {}
        tracemalloc.start()
        _, _, seen = stream.stream_artifact(p, excluded=set(), strict=True,
            on_record=lambda t, row: retained.update({t: row}) if t == "T00000" else None)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert seen == count and len(retained) == 1
        peaks.append(peak)
    assert peaks[1] < peaks[0] + 1024**2


def test_no_runtime_or_retained_write_and_private_omission(tmp_path, monkeypatch):
    def private_metadata(prev, curr):
        curr["records"]["AAA_SAME"]["portfolio_context"] = {"portfolio_id": "SYNTHETIC_PRIVATE_SENTINEL", "quantity": 1234}
        curr["records"]["AAA_SAME"]["position_context"] = {"cost": "SYNTHETIC_PRIVATE_SENTINEL"}
    _, _, locations = fixture(tmp_path, mutate=private_metadata)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()}
    def prohibited(*args, **kwargs):
        raise AssertionError("unexpected write or private input")
    monkeypatch.setattr(Path, "write_text", prohibited)
    monkeypatch.setattr(ac, "build_artifact", prohibited)
    original_open = Path.open
    def read_only_evidence(path, mode="r", *args, **kwargs):
        assert path.resolve().is_relative_to(tmp_path.resolve())
        assert not any(flag in mode for flag in ("w", "a", "+", "x"))
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", read_only_evidence)
    result = evaluate(tmp_path, locations, ["AAA_SAME"])
    assert "portfolio_id" not in json.dumps(result)
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in json.dumps(result)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()}
