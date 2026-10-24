"""Source-bound Hub discovery remains candidate; qualified point math is non-voting."""
import copy
import json
from pathlib import Path

import pytest

from stocklookup_core.research import shareholder_economics as economics
from tests.test_shareholder_economics import receipt

FIXTURES = Path(__file__).parent / "fixtures"
INDEX = json.loads((FIXTURES / "shareholder_dilution_hub39_v1.json").read_bytes())
NOTE = json.loads((FIXTURES / "hpg_common_share_note_existing_v1.json").read_bytes())
NOW = "2026-10-24T16:00:00+07:00"
SEALED = "2026-10-23T15:00:00+07:00"


def discovery(ticker, cutoff=NOW, index=None, **kwargs):
    index = index or INDEX
    return economics.candidate_discovery_context(ticker=ticker, cutoff=cutoff,
        report_known_at=index["report_known_at"], source_manifest=index["source_manifest"],
        event_rows=index["events"], continuity_rows=index["continuity_points"],
        gap_rows=index["unresolved_gaps"], **kwargs)


def point(value, day, **kwargs):
    return receipt("OUTSTANDING_SHARES", "DATED_OBSERVATION", value=value, effective_date=day,
        share_class="ordinary", denominator_basis="LEGAL_OUTSTANDING", **kwargs)


def project(*rows):
    return economics.project_context(ticker="SYN", cutoff=NOW, observations=rows)


def test_fixture_is_exact_candidate_snapshot_with_no_original_bytes_or_gate_receipts():
    assert INDEX["hub_commit"] == "4ba741960c9859fc370cc667d2cdeb10f70a91ea"
    assert (len(INDEX["source_manifest"]["documents"]),len(INDEX["events"]),len(INDEX["continuity_points"]),len(INDEX["unresolved_gaps"])) == (40,35,32,24)
    assert "NOT_QUALIFIED" in INDEX["fixture_class"]


@pytest.mark.parametrize("ticker", ["HPG","PNJ","SSI","PVD","POW","QNS","PAN","NVL","MWG"])
def test_priority_issuer_discovery_preserves_source_claims_without_qualification(ticker):
    saved = copy.deepcopy(INDEX)
    context = discovery(ticker)
    assert context["coverage_kind"] == "CANDIDATE_DISCOVERY_ONLY"
    assert context["qualified_observation_count"] == 0 and context["claims"] == []
    for key in ("events","continuity_points","unresolved_gaps"):
        assert all(row["classification"] == "CANDIDATE_NOT_PRODUCER_QUALIFIED" for row in context[key])
        assert all(row["candidate_payload"]["issuer"] == ticker for row in context[key])
    assert INDEX == saved
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        economics.at_cutoff(context,ticker=ticker,cutoff=NOW)


@pytest.mark.parametrize("ticker", ["HPG","PNJ","SSI","PVD","POW","QNS"])
def test_october24_report_never_enters_sealed_october23_session(ticker):
    context = discovery(ticker, cutoff=SEALED)
    assert context["status"] == "REPORT_NOT_KNOWN_AT_CUTOFF"
    assert not any(context[k] for k in ("events","continuity_points","sources","unresolved_gaps"))
    assert context["blocker_reason_codes"] == ["REPORT_AVAILABLE_AFTER_CUTOFF"]


def test_known_failure_modes_are_visible_as_candidates_not_repaired_counts():
    hpg, pvd, ssi, pnj, qns = [discovery(t) for t in ("HPG","PVD","SSI","PNJ","QNS")]
    points = {r["candidate_payload"]["chain_id"]:r["candidate_payload"] for d in (hpg,pvd) for r in d["continuity_points"]}
    assert points["C04"]["count"] == "7675465855" and points["C05"]["count"] == "8442964520"
    assert "charter/par" in points["C04"]["share_definition"]
    assert points["C22"]["count"] == "555880006" and points["C23"]["count"] == "927742191"
    assert "EPS" in points["C23"]["share_definition"]
    events = [r["candidate_payload"] for d in (ssi,pnj) for r in d["events"]]
    assert any(r["issuer"] == "SSI" and "issuance end" in r["date_type"] for r in events)
    assert any(r["issuer"] == "PNJ" and r["stage"] == "SHAREHOLDER_APPROVED" and "Buyback" in r["event"] for r in events)
    assert "55,534,605" in json.dumps(qns) and "treasury" in json.dumps(qns)
    assert "ex-date" in json.dumps(ssi["unresolved_gaps"]).lower()
    assert hpg["research_findings"][0]["eps_minus_legal_count"] == 767498665
    assert pvd["research_findings"][0]["eps_minus_legal_count"] == 371862185
    assert all(f["classification"].startswith("CANDIDATE") for f in hpg["research_findings"])


def test_verified_raw_bytes_still_do_not_qualify_csv_facts_or_mirrors():
    verified = {doc["source_id"]:{"status":"RAW_BYTES_AND_MANIFEST_MATCHED","reason_codes":[]}
                for doc in INDEX["source_manifest"]["documents"]}
    hpg = discovery("HPG",original_verifications=verified)
    assert all("CANDIDATE_EXACT_FIELD_NOT_QUALIFIED" in r["blocker_reason_codes"] for r in hpg["sources"])
    assert not any("RETAINED_ORIGINAL_BYTES_NOT_VERIFIED" in r["blocker_reason_codes"] for r in hpg["sources"])
    mwg = discovery("MWG",original_verifications=verified)
    assert any("MIRROR_OR_UNVERIFIED_FIRST_PARTY_PROVENANCE" in r["blocker_reason_codes"] for r in mwg["sources"])
    assert not mwg["claims"]


def test_source_and_row_order_duplicates_and_conflicting_source_ids_are_stable():
    index = copy.deepcopy(INDEX)
    doc = copy.deepcopy(next(d for d in index["source_manifest"]["documents"] if d["issuer"] == "HPG"))
    doc["sha256"] = "f"*64
    index["source_manifest"]["documents"].append(doc)
    forward = discovery("HPG",index=index)
    index["source_manifest"]["documents"].reverse()
    for key in ("events","continuity_points","unresolved_gaps"): index[key].reverse()
    assert discovery("HPG",index=index) == forward
    assert any("CONFLICTING_SOURCE_ID" in r["blocker_reason_codes"] for r in forward["sources"])
    index["events"] += index["events"]
    assert discovery("HPG",index=index) == forward


def test_malformed_candidate_rows_and_unknown_exact_source_ids_remain_explicit():
    index = copy.deepcopy(INDEX)
    index["events"] = [None,42,{"issuer":"HPG"},{"issuer":"HPG","event_id":"BAD","source_id":"LOOKALIKE_HPG"}]
    context = discovery("HPG",index=index)
    assert context["malformed_rows"] == ["MALFORMED_CANDIDATE_ROW","MISSING_CANDIDATE_ROW_ID"]
    assert "UNRESOLVED_EXACT_SOURCE_ID:LOOKALIKE_HPG" in context["events"][0]["blocker_reason_codes"]


def test_existing_hpg_note_is_requalified_only_for_its_original_dated_use():
    saved = copy.deepcopy(NOTE)
    context = economics.project_context(ticker="HPG",cutoff=NOW,retained_common_share_notes=[NOTE])
    assert len(context["claims"]) == 1, context["rejected"]
    claim = context["claims"][0]
    assert (claim["value"],claim["effective_date"],claim["published_at"]) == (7675465855,"2025-12-31",None)
    assert claim["citation_id"] == NOTE["citation_id"] and NOTE == saved
    assert not context["share_capital_research"]["endpoint_changes"]
    assert context["current_outstanding_shares"] is None and not context["historical_pit_eligible"]
    assert economics.at_cutoff(context,ticker="HPG",cutoff=SEALED) is None
    early = economics.project_context(ticker="HPG",cutoff="2026-10-07T15:00:00+07:00",retained_common_share_notes=[NOTE])
    assert not early["claims"]


@pytest.mark.parametrize("mutation", [{"value":7675465856},{"ticker":"PNJ"},{"document_sha256":"0"*64},{"citation_id":"forged"}])
def test_existing_note_receipt_cannot_be_reinterpreted(mutation):
    context = economics.project_context(ticker="HPG",cutoff=NOW,retained_common_share_notes=[NOTE|mutation])
    assert not context["claims"] and context["rejected"]


def test_observed_endpoint_change_is_arithmetic_without_continuity_or_ownership_dilution():
    a,b = point(100,"2026-06-30"),point(120,"2026-09-30",citation_id="second")
    context = project(a,b,a)
    assert context == project(b,a)
    change = context["share_capital_research"]["endpoint_changes"][0]
    assert (change["change"],change["change_ratio"]) == (20,.2)
    assert change["classification"] == "ARITHMETIC_INFERENCE_FROM_QUALIFIED_POINTS"
    assert change["continuity_status"] == "UNKNOWN_BETWEEN_OBSERVATIONS" and change["ownership_dilution"] == "UNKNOWN"
    assert context["current_outstanding_shares"] is None


@pytest.mark.parametrize("kind", ["EPS_WEIGHTED_AVERAGE_SHARES","DILUTED_EPS_SHARES","CHARTER_CAPITAL"])
def test_eps_and_charter_capital_cannot_substitute_for_outstanding(kind):
    other = receipt(kind,"REPORTED" if "EPS" in kind else "DATED_OBSERVATION",value=120,
        unit="shares" if "EPS" in kind else "VND",period_start="2026-01-01",period_end="2026-06-30")
    context = project(point(100,"2026-06-30"),other)
    assert len(context["claims"]) == 2
    assert not context["share_capital_research"]["endpoint_changes"]


def test_qns_different_scopes_are_valid_separate_bases_not_a_conflict():
    a = receipt("TREASURY_SHARES","DATED_OBSERVATION",value=0,scope="parent")
    b = receipt("TREASURY_SHARES","DATED_OBSERVATION",value=55534605,scope="consolidated",citation_id="subsidiary")
    context = project(a,b)
    assert len(context["claims"]) == 2 and not context["rejected"]
    assert not context["share_capital_research"]["endpoint_changes"]


def test_planned_and_executed_variance_requires_exact_event_identity_and_separate_proof():
    def event(state,value,**changes):
        return receipt("ISSUANCE",state,value=value,event_id="same-bonus",share_class="ordinary",
            denominator_basis="BONUS_FROM_EQUITY",execution_evidence_qualified=state=="EXECUTED",**changes)
    planned,executed = event("APPROVED_PROPOSAL",170574553),event("EXECUTED",170572852)
    context = project(planned,executed)
    assert context["share_capital_research"]["planned_executed_variances"][0]["executed_minus_planned"] == -1701
    assert all(c.get("ex_date") is None for c in context["claims"])
    other_event = event("EXECUTED",170572852) | {"event_id":"another"}
    assert not project(planned,other_event)["share_capital_research"]["planned_executed_variances"]
    assert project(executed)["current_outstanding_shares"] is None


@pytest.mark.parametrize("kind", ["SHARE_REPURCHASE","SHARE_CANCELLATION"])
def test_approved_repurchase_or_cancellation_is_not_completed(kind):
    approved = receipt(kind,"APPROVED_PROPOSAL")
    completed_without_proof = receipt(kind,"EXECUTED")
    context = project(approved,completed_without_proof)
    assert len(context["claims"]) == 1 and context["claims"][0]["state"] == "APPROVED_PROPOSAL"
    assert context["current_outstanding_shares"] is None


@pytest.mark.parametrize("field,value", [("ex_date","2026-09-30"),("first_trading_date","2026-10-02"),("share_class","preferred")])
def test_unbound_date_and_share_metadata_cannot_be_added_by_narration(field,value):
    r = receipt()
    assert not project(r|{field:value})["claims"]


@pytest.mark.parametrize("bad", [None,42,[],"candidate",{"kind":[]},receipt(value=10**1000),receipt(share_class=[])])
def test_malformed_typed_observations_fail_locally_without_value_leak(bad):
    context = project(bad)
    assert not context["claims"] and context["rejected"]
    assert all("value" not in r for r in context["rejected"])


def test_offline_inspection_reads_originals_without_admitting_fields_or_mutating_inputs(tmp_path,monkeypatch):
    from tools import replay_corporate_shareholder_economics as tool
    monkeypatch.setattr(tool,"ROOT",tmp_path)
    root = tmp_path/"originals"
    root.mkdir()
    raw = root/"source.pdf"
    raw.write_bytes(b"synthetic raw byte verification only; no financial fact")
    index = copy.deepcopy(INDEX)
    doc = index["source_manifest"]["documents"][0]
    doc["sha256"] = tool.digest(raw)
    manifest = tmp_path/"original_manifest.json"
    manifest.write_text(json.dumps({"records":[dict(ticker=doc["issuer"],canonical_url=doc["url"],
        sha256=doc["sha256"],acquisition_status="retained",relative_path="source.pdf")]}),encoding="utf-8")
    fixture = tmp_path/"index.json"
    fixture.write_text(json.dumps(index),encoding="utf-8")
    before = [p.read_bytes() for p in (raw,fixture,manifest)]
    output = tmp_path/".stocklookup/scratch/inspection"
    kwargs = dict(candidate_index=fixture,output=output,cutoff=NOW,original_root=root,original_manifest=manifest)
    result = tool.inspect_research(**kwargs)
    assert result["verified_raw_documents"] == 1 and result["admitted_observations"] == 0
    assert result["source_hashes_unchanged"] and [p.read_bytes() for p in (raw,fixture,manifest)] == before
    packet = json.loads((output/"research_packet.json").read_bytes())
    assert packet["authority_effect"] == "NONE" and not packet["runtime_activation"]
    assert tool.inspect_research(**kwargs) == result  # exact repeat, no output rewrite
    with pytest.raises(ValueError,match="REFUSING_TO_OVERWRITE"):
        tool.inspect_research(**(kwargs|{"cutoff":"2026-10-25T16:00:00+07:00"}))
    with pytest.raises(ValueError,match="WORKTREE_SCRATCH"):
        tool.inspect_research(**(kwargs|{"output":tmp_path/"not-scratch"}))


def test_candidate_context_cannot_feed_existing_live_forward_driver():
    import current_corporate_intelligence_axis as axis
    row = {"ticker":"HPG","research_session":"2026-10-24","events":[],"shareholder_economics_context":discovery("HPG")}
    with pytest.raises(ValueError,match="IDENTITY_MISMATCH"):
        axis.build_forward_driver_context(row,as_of_session="2026-10-24")


@pytest.mark.parametrize("mutation", [{"unit":"million shares"},{"unit":"VND"},{"value":-1},{"value":1.5}])
def test_share_units_and_nonnegative_integer_basis_are_explicit(mutation):
    row = point(100,"2026-06-30")
    assert not project(row|mutation)["claims"]


def test_conflicts_repetition_and_unknown_class_do_not_create_continuity():
    a,b = point(100,"2026-06-30"),point(101,"2026-06-30",citation_id="conflict")
    assert project(a,b) == project(b,a)
    assert not project(a,b)["claims"] and project(a,b)["rejected"]
    missing_class = receipt("OUTSTANDING_SHARES","DATED_OBSERVATION",value=120,effective_date="2026-09-30")
    assert not project(a,missing_class)["share_capital_research"]["endpoint_changes"]
    def event(event_id,value,consideration="BONUS_FROM_EQUITY"):
        return receipt("ISSUANCE","EXECUTED",event_id=event_id,value=value,consideration=consideration,
            execution_evidence_qualified=True)
    assert len(project(event("first",100),event("second",200),event("first",100))["claims"]) == 2
    assert not project(event("first",100),event("first",100,consideration="NONCASH_CONVERSION"))["claims"]


def test_inspection_child_symlink_cannot_escape_scratch(tmp_path,monkeypatch):
    from tools import replay_corporate_shareholder_economics as tool
    monkeypatch.setattr(tool,"ROOT",tmp_path)
    output = tmp_path/".stocklookup/scratch/inspection"
    output.mkdir(parents=True)
    outside = tmp_path/"outside.json"
    outside.write_text("preserve",encoding="utf-8")
    try:
        (output/"research_packet.json").symlink_to(outside)
    except OSError:
        pytest.skip("host cannot create a test symlink")
    with pytest.raises(ValueError,match="WORKTREE_SCRATCH"):
        tool.inspect_research(candidate_index=FIXTURES/"shareholder_dilution_hub39_v1.json",output=output,cutoff=NOW)
    assert outside.read_text(encoding="utf-8") == "preserve"
