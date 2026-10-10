"""Offline retained-source consumer acceptance and adversarial authority boundaries."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import long_term_company_economics_evidence as economics
from stocklookup_core.decision.human_ai_decision_evidence_packet import build_packet
from tools import inspect_decision_research as cli

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "derived/financial-evidence-currency-refresh-v1/qualified_official_facts.jsonl"
CUTOFF = "2026-10-08T15:00:00+07:00"
BEFORE = "2026-10-07T15:00:00+07:00"


@pytest.fixture
def matrices():
    rows = [json.loads(line) for line in FACTS.read_text(encoding="utf8").splitlines()]
    return {t: economics.build(ticker=t, knowledge_cutoff=CUTOFF, official_rows=rows) for t in ("PNJ", "PVD", "FPT")}


def observations(matrix):
    return [o for d in matrix["dimensions"].values() for o in d["observations"]]


def reseal(matrix):
    return economics._seal(matrix, economics.CONTRACT_VERSION)


def arguments(*extra):
    parser = argparse.ArgumentParser()
    cli.configure_parser(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(["research", "economics", "--facts", str(FACTS), "--cutoff", CUTOFF, "--ticker", "PNJ", *extra])


@pytest.mark.parametrize("ticker,count", [("PNJ", 6), ("PVD", 7), ("FPT", 3)])
def test_packet_preserves_all_exact_facts_and_separate_states(matrices, ticker, count):
    matrix = matrices[ticker]
    original = deepcopy(matrix)
    packet = build_packet(ticker=ticker, company_economics=matrix, ai_narration="Observation only", capital_decision="BUY")
    field = packet["sections"]["stock"]["fields"]["company_economics_evidence"]
    assert field["claim"] == "DATA_WARNING"
    context = field["value"]
    view = context["matrix"]
    assert len(observations(view)) == count
    for key, value in matrix.items():
        assert view[key] == value
    assert matrix == original and packet["capital_decision"]["value"] is None
    assert not packet["is_actionable"] and view["authority_effect"] == "NONE"
    assert context["temporal_use"] == "CONSULTATION_KNOWLEDGE_CUTOFF_NOT_SEALED_DECISION_TIME"
    economics._verify_identity(view, economics.CONTRACT_VERSION)
    assert packet["sections"]["counter_thesis"]["fields"]["company_economics_unknowns"]["value"]["cyclicality"]["interpretation_status"] == "UNKNOWN"
    if ticker == "FPT":
        assert view["dimensions"]["revenue_profit_economics"]["current_observation_status"] == "UNKNOWN"


def test_opt_in_absence_keeps_released_packet_identity():
    packet = build_packet(ticker="PNJ", sections={"stock": {"revenue": 123}, "uncertainty": {"gap": None}},
                          feature_measurements={"price": 5}, ai_narration="bounded research", capital_decision="BUY")
    assert packet["packet_identity"] == "human_ai_decision_evidence_packet:bca218936fbe45cd37c9d8a9131a6e7a21e66b0860d930627e9418a266a810b3"
    assert "company_economics_evidence" not in packet["sections"]["stock"]["fields"]


@pytest.mark.parametrize("section,field", [("stock", "company_economics_evidence"), ("uncertainty", "company_economics_limits"), ("counter_thesis", "company_economics_unknowns")])
def test_reserved_economics_fields_cannot_silently_replace_caller(matrices, section, field):
    with pytest.raises(ValueError, match="COLLISION"):
        build_packet(ticker="PNJ", company_economics=matrices["PNJ"], sections={section: {field: None}})


@pytest.mark.parametrize("change", [
    lambda m: m.update(ticker="OTHER"),
    lambda m: m.update(non_voting=False),
    lambda m: m.update(is_actionable=True),
    lambda m: m.update(authority_effect="PROMOTED"),
    lambda m: m.update(production="DAILY"),
    lambda m: m.update(strict_share_qualification="QUALIFIED"),
    lambda m: m["normalization"].update(status="NORMALIZED"),
    lambda m: m["flags"]["STRUCTURAL_THESIS_SUPPORTED"].update(status="KNOWN"),
    lambda m: m["dimensions"]["business_durability"].update(interpretation_status="KNOWN"),
    lambda m: m["dimensions"].pop("cyclicality"),
    lambda m: m["research_boundaries"].clear(),
    lambda m: observations(m)[0]["source"].update(knowledge_available_at="2026-10-09T00:00:00Z"),
    lambda m: observations(m)[0]["source"].update(observed_at="2026-10-09"),
    lambda m: observations(m)[0]["source"].update(publication_date="2026-10-09"),
    lambda m: observations(m)[0].update(annualization="PERMITTED"),
    lambda m: observations(m)[0].update(normalized_value=True),
    lambda m: observations(m)[0].update(structural_verdict="SUPPORTS"),
    lambda m: m.update(company_score=1),
])
def test_resealed_invalid_matrix_fails_closed(matrices, change):
    matrix = deepcopy(matrices["PNJ"])
    change(matrix)
    with pytest.raises(ValueError):
        build_packet(ticker="PNJ", company_economics=reseal(matrix))


def test_changed_hash_and_nan_fail_closed(matrices):
    matrix = deepcopy(matrices["PNJ"])
    observations(matrix)[0]["normalized_value"] += 1
    with pytest.raises(ValueError, match="IDENTITY"):
        build_packet(ticker="PNJ", company_economics=matrix)
    observations(matrix)[0]["normalized_value"] = float("nan")
    with pytest.raises(ValueError):
        build_packet(ticker="PNJ", company_economics=matrix)


def test_comparison_keeps_currency_period_assurance_and_all_values(matrices):
    selected = list(matrices.values())
    original = deepcopy(selected)
    comparison = economics.compare_selected(selected)
    assert comparison == economics.compare_selected(list(reversed(selected)))
    rows = [r for g in comparison["groups"] for r in g["observations"]] + comparison["unpaired_observations"]
    assert len(rows) == 16 and selected == original
    for ticker, matrix in matrices.items():
        assert [r["observation"] for r in rows if r["ticker"] == ticker] == sorted(
            observations(matrix), key=lambda o: json.dumps({k: o.get(k) for k in (
                "canonical_metric", "period_start", "period_end", "period_type", "statement_scope", "currency", "statement_family", "temporal_nature", "context_kind", "component_semantic_type", "component_direction")}, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    for group in comparison["groups"]:
        assert len({r["observation"]["currency"] for r in group["observations"]}) == 1
        assert len({(r["observation"]["period_start"], r["observation"]["period_end"]) for r in group["observations"]}) == 1
    assert comparison["issuer_states"]["PNJ"]["normalization"]["status"] == "NORMALIZED_ECONOMICS_NOT_QUALIFIED"
    assert "EXACT_REPORTED_BASIS_MATCH_NOT_ECONOMIC_EQUIVALENCE" in {g["basis_status"] for g in comparison["groups"]}


@pytest.mark.parametrize("key,value", [("period_start", None), ("period_end", "not-a-date"), ("currency", "USD"), ("statement_scope", "standalone"), ("statement_family", "other"), ("component_direction", "different")])
def test_label_alone_cannot_make_comparable_group(matrices, key, value):
    # Synthetic alternate issuer is an adversarial basis fixture, not source qualification.
    other = deepcopy(matrices["PNJ"])
    other["ticker"] = "AAA"
    for observation in observations(other):
        observation[key] = value
    comparison = economics.compare_selected([matrices["PNJ"], reseal(other)])
    assert not any(g["basis_status"] == "EXACT_REPORTED_BASIS_MATCH_NOT_ECONOMIC_EQUIVALENCE" for g in comparison["groups"])
    if value is None or value == "not-a-date":
        assert len(comparison["unpaired_observations"]) == 6


def test_comparison_requires_distinct_subjects_and_one_cutoff(matrices):
    with pytest.raises(ValueError, match="SELECTION"):
        economics.compare_selected([])
    with pytest.raises(ValueError, match="DUPLICATE"):
        economics.compare_selected([matrices["PNJ"], matrices["PNJ"]])
    other = deepcopy(matrices["PVD"])
    other["knowledge_cutoff"] = "2026-10-08T16:00:00+07:00"
    with pytest.raises(ValueError, match="CUTOFF_MISMATCH"):
        economics.compare_selected([matrices["PNJ"], reseal(other)])


def test_cli_real_overlay_read_only_and_earlier_cutoff():
    before = hashlib.sha256(FACTS.read_bytes()).hexdigest()
    args = arguments("--ticker", "PVD", "--ticker", "FPT")
    result = cli.inspect(args)
    assert result["status"] == "AVAILABLE" and result["persisted"] is False
    assert result["canonical_reference"] is None
    assert result["source_references"]["facts"]["sha256"] == before
    args.cutoff = BEFORE
    early = cli.inspect(args)
    counts = {t: len(observations(p["sections"]["stock"]["fields"]["company_economics_evidence"]["value"]["matrix"])) for t, p in early["packets"].items()}
    assert counts == {"FPT": 0, "PNJ": 3, "PVD": 3}
    assert hashlib.sha256(FACTS.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("text", ['{"ticker":"PNJ","ticker":"FPT"}', '{"ticker":"PNJ","value":NaN}', '{"ticker":"PNJ","value":1e999}', '{"ticker":"PNJ"} trailing', '[]', '{}'])
def test_cli_malformed_jsonl_fails_without_partial_packet(tmp_path, capsys, text):
    args = arguments()
    args.facts = tmp_path / "facts.jsonl"
    args.facts.write_text(FACTS.read_text(encoding="utf8") + "\n" + text, encoding="utf8")
    assert cli.run(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "UNAVAILABLE" and "packets" not in result
    assert str(tmp_path) not in json.dumps(result)


def test_changed_source_never_publishes_success(monkeypatch, capsys):
    digest = cli._digest
    calls = 0
    def changing(path):
        nonlocal calls
        calls += 1
        return digest(path) if calls == 1 else "different"
    monkeypatch.setattr(cli, "_digest", changing)
    assert cli.run(arguments()) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "SOURCE_CHANGED_DURING_INSPECTION"


def test_optional_canonical_reference_is_verified_and_not_enriched(tmp_path):
    from stocklookup_core.decision import current_research_decision_packet as canonical
    from stocklookup_core.decision.current_opportunity_prioritization import content_identity
    opportunity = {"contract_version": "current_opportunity_prioritization/v1", "research_session": "2026-10-06",
                   "records": {"PNJ": {"ticker": "PNJ"}}}
    opportunity.update(content_identity(opportunity))
    artifact = canonical.build_artifact(opportunity=opportunity)
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(artifact), encoding="utf8")
    before = path.read_bytes()
    args = arguments("--canonical-packet", str(path))
    result = cli.inspect(args)
    assert result["canonical_reference"]["research_session"] == "2026-10-06"
    assert result["knowledge_cutoff"] == CUTOFF
    assert result["packets"]["PNJ"]["canonical_packet_identity"] == artifact["artifact_identity"]
    assert path.read_bytes() == before and "company_economics_evidence" not in artifact
    args.ticker = ["PVD"]
    with pytest.raises(ValueError, match="SUBJECT"):
        cli.inspect(args)
    args.ticker = ["PNJ"]
    artifact["research_session"] = "2026-10-07"
    path.write_text(json.dumps(artifact), encoding="utf8")
    with pytest.raises(ValueError, match="IDENTITY"):
        cli.inspect(args)
    artifact["research_session"] = "2026-10-09"
    artifact.update(canonical.content_identity(artifact))
    path.write_text(json.dumps(artifact), encoding="utf8")
    with pytest.raises(ValueError, match="AFTER_CONSULTATION"):
        cli.inspect(args)


@pytest.mark.parametrize("status,percentile,qualified", [("READY_RESEARCH_ONLY", 0.9, True), ("BLOCKED", 0.9, False), ("READY_RESEARCH_ONLY", 0.1, False)])
def test_existing_method_scoped_valuation_context_survives(status, percentile, qualified):
    rows = [json.loads(line) for line in FACTS.read_text(encoding="utf8").splitlines()]
    envelope = {"observed_at": "2026-10-08T01:00:00Z", "knowledge_available_at": "2026-10-08T01:00:00Z",
                "payload": {"source_identity": "synthetic:valuation-contract-fixture", "session": "2026-10-08",
                            "relative_research_state": "EXPENSIVE_RELATIVE_RESEARCH",
                            "peer_methods": {"P/B": {"status": status, "percentile": percentile, "peer_count": 12, "basis": {"method_id": "P/B"}}}}}
    matrix = economics.build(ticker="PNJ", knowledge_cutoff=CUTOFF, official_rows=rows, valuation_context=envelope)
    view = economics.packet_context(matrix, ticker="PNJ")["matrix"]
    assert view == matrix
    assert view["dimensions"]["valuation_fitness"]["interpretation_status"] == ("PARTIALLY_KNOWN" if qualified else "UNKNOWN")
    assert view["strict_valuation_qualification"] == "NOT_PROVIDED"
    if qualified:
        view["dimensions"]["valuation_fitness"]["research_context"][0]["qualified_methods"][0]["percentile"] = 0.1
        with pytest.raises(ValueError, match="METHOD_FITNESS"):
            economics.packet_context(reseal(view), ticker="PNJ")


def test_production_entrypoint_routes_only_explicit_offline_research():
    process = subprocess.run([sys.executable, str(ROOT / "stocklookup.py"), "research", "economics",
                              "--facts", str(FACTS), "--cutoff", CUTOFF, "--ticker", "PNJ"],
                             cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert process.returncode == 0, process.stderr
    output = json.loads(process.stdout)
    assert output["status"] == "AVAILABLE" and output["persisted"] is False
    assert len(observations(output["packets"]["PNJ"]["sections"]["stock"]["fields"]["company_economics_evidence"]["value"]["matrix"])) == 6
