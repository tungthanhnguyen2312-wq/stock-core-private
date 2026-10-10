"""Offline evidence intake and read-only product dispatch contracts."""
import argparse
import hashlib
import json
from pathlib import Path

import pytest

import decision_outcome_calibration_review as review
import decision_intelligence_coverage_calibration as spine
import historical_temporal_research_panel as panel
import stocklookup
from tools import inspect_decision_research as cli


def write(path, body):
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("payload", [
    '{"feedback_records": [{"ticker":"AAA"}]',
    '{"feedback_records": [',
    '{"feedback_records": [{"ticker":"AAA"}',
    '{"feedback_records": [{} {}]}',
    '{"feedback_records": [{},]}',
    '{"feedback_records": [,{}]}',
    '{"feedback_records": [null]}',
    '{"feedback_records": [], "feedback_records": []}',
    '{"feedback_records": [{"x":1,"x":2}]}',
    '{"feedback_records": [{"x":NaN}]}',
    '{"feedback_records": [{"x":1e999}]}',
    '{"feedback_records": []} garbage',
    '{"feedback_records": [], "later": [}',
    '{"nested": {"feedback_records": []}}',
    '{"feedback_records": [], "later": {"x":1,"x":2}}',
])
def test_partial_or_malformed_feedback_never_completes(tmp_path, payload):
    path = tmp_path / "feedback.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        list(review.iter_feedback_records(path))


def test_valid_stream_unicode_and_large_prefix(tmp_path):
    records = [{"ticker": "AAA", "note": "đ" * 150000}, {"ticker": "BBB"}]
    path = write(tmp_path / "phiên.json", {"large_header": "x" * 410000, "feedback_records": records, "suffix": {"ok": True}})
    assert list(review.iter_feedback_records(path)) == records


def test_empty_stream_and_key_in_string_do_not_confuse_reader(tmp_path):
    path = write(tmp_path / "empty.json", {"note": '"feedback_records": [', "feedback_records": []})
    assert list(review.iter_feedback_records(path)) == []


def test_large_metadata_container_is_validated_without_member_overread(tmp_path):
    path = tmp_path / "large.json"
    with path.open("w", encoding="utf-8") as handle:
        handle.write('{"inventory": [')
        member = json.dumps({"note": "x" * 1024})
        for i in range(17000):
            handle.write(("," if i else "") + member)
        handle.write('], "feedback_records": [{"ticker":"AAA"}]}')
    assert path.stat().st_size > 16 * 1024 * 1024
    assert list(review.iter_feedback_records(path)) == [{"ticker": "AAA"}]


def coverage_args(tmp_path):
    session = "2026-10-06"
    args = argparse.Namespace(research_action="coverage", session=session, ticker=["aaa"], panel=None)
    for name, (contract, key) in cli.SOURCES.items():
        body = {"contract_version": contract, key: {"resolved_completed_session": session} if name == "universe" else session}
        if name == "events":
            body["all_current_universe_event_records"] = []
        else:
            body["records"] = {"AAA": {}}
        if name == "universe":
            body["records"] = {"AAA": {}, **{f"T{i:04}": {} for i in range(1682)}}
        setattr(args, name, write(tmp_path / (name + ".json"), body))
    return args


def test_focus_preserves_full_denominator_missingness_and_readonly(tmp_path):
    args = coverage_args(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = cli.inspect(args)
    assert result["coverage_summary"]["denominator"] == 1683
    assert result["coverage_summary"]["counts"]["missing"] == 1683
    assert list(result["focus"]) == ["AAA"]
    assert result["focus"]["AAA"]["coverage"]["fundamental_evidence_status"] == "UNKNOWN"
    assert result["persisted"] is False and result["authority_effect"] == "NONE"
    assert result["source_references"]["universe"]["sha256"] == hashlib.sha256(args.universe.read_bytes()).hexdigest()
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    args.ticker = ["MISSING"]
    missing = cli.inspect(args)["focus"]["MISSING"]
    assert not missing["coverage_present"] and missing["retention_limitation"] == "HISTORICAL_PANEL_NOT_SUPPLIED"


@pytest.mark.parametrize("name", list(cli.SOURCES))
def test_each_source_session_must_match(tmp_path, name):
    args = coverage_args(tmp_path)
    path = getattr(args, name)
    body = json.loads(path.read_text(encoding="utf-8"))
    key = cli.SOURCES[name][1]
    body[key] = {"resolved_completed_session": "2026-10-07"} if name == "universe" else "2026-10-07"
    write(path, body)
    with pytest.raises(ValueError, match="SOURCE_SESSION_MISMATCH"):
        cli.inspect(args)


def test_contract_and_denominator_are_strict(tmp_path):
    args = coverage_args(tmp_path)
    body = json.loads(args.universe.read_text(encoding="utf-8"))
    body["records"].pop("AAA")
    write(args.universe, body)
    with pytest.raises(ValueError, match="DENOMINATOR_SWITCH"):
        cli.inspect(args)
    body["contract_version"] = "wrong"
    write(args.universe, body)
    with pytest.raises(ValueError, match="SOURCE_CONTRACT_MISMATCH"):
        cli.inspect(args)


def test_panel_future_rows_refused_and_parent_tier_preserved(tmp_path):
    args = coverage_args(tmp_path)
    observation = {"session": "2026-10-05", "ticker": "AAA", "semantic_tier": panel.RECONSTRUCTED_RESEARCH, "tactical_state": "UPTREND"}
    built = panel.build_panel([observation])
    args.panel = write(tmp_path / "panel.json", built)
    result = cli.inspect(args)
    assert result["focus"]["AAA"]["historical_rows"] == 1
    assert "UPTREND_NOT_RELABELED_BOTTOM_FISHING" in result["focus"]["AAA"]["distinctions"]
    assert json.loads(args.panel.read_text())["tier_counts"] == built["tier_counts"]
    built["rows"][0]["session"] = "2026-10-07"
    write(args.panel, built)
    with pytest.raises(ValueError, match="PANEL_FUTURE_SESSION"):
        cli.inspect(args)


def test_source_mutation_refused(tmp_path, monkeypatch):
    args = coverage_args(tmp_path)
    old = spine.join_coverage_artifacts
    def change(**kwargs):
        result = old(**kwargs)
        args.events.write_text('{}', encoding="utf-8")
        return result
    monkeypatch.setattr(spine, "join_coverage_artifacts", change)
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        cli.inspect(args)


def test_calibration_matches_existing_reducer_and_stdout_dispatch(tmp_path, capsys):
    record = {"source_type": "QUALIFIED_LEGACY_INTEGRATED_T0", "decision_session": "2026-09-03",
              "ticker": "AAA", "research_action_posture": "EARLY_REVERSAL",
              "tactical_structure_state": "BREAKOUT_READY", "market_sector_state": "MIXED_BREADTH",
              "forward_outcomes": {"horizons": {"forward_close_return_20": {"status": "MATURE", "return": 0.01}}}}
    path = write(tmp_path / "feedback.json", {"contract_version": "prospective_decision_outcome_feedback/v3", "feedback_records": [record]})
    args = argparse.Namespace(research_action="calibration", feedback=path)
    result = cli.inspect(args)
    expected = review.review_feedback_artifact(path)
    assert result["mature_counts"]["T20"]["rows"] == 1
    assert result["qualified_control_edges"] == 0
    for key in ("review_identity", "mature_counts", "cohorts", "qualified_control_edges", "probability", "automatic_threshold_change"):
        assert result[key] == expected[key]
    assert stocklookup.main(["research", "calibration", "--feedback", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "AVAILABLE"
    path.write_text('{"feedback_records": []', encoding="utf-8")
    assert stocklookup.main(["research", "calibration", "--feedback", str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "UNAVAILABLE"


def test_missing_file_does_not_leak_host_path(tmp_path, capsys):
    secret = tmp_path / "private-owner-name" / "missing.json"
    assert cli.run(argparse.Namespace(research_action="calibration", feedback=secret)) == 2
    output = capsys.readouterr().out
    assert "private-owner-name" not in output and str(tmp_path) not in output


def test_nonserializable_result_never_emits_partial_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "inspect", lambda args: {"status": "AVAILABLE", "metric": float("inf")})
    assert cli.run(None) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "UNAVAILABLE"
