"""Portable accounting and bounded retained artifact verification for offline Stage 1."""
import json
from pathlib import Path
import pytest
import stocklookup_core.research.thesis_evidence_contract as c
import stocklookup_core.research.thesis_evidence_matrix as m

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"docs/internal/THESIS_EVIDENCE_MATRIX_STAGE_1_ACCEPTANCE.json"


def test_portable_october_2_acceptance_identity_and_accounting():
    from tools.run_thesis_evidence_matrix_acceptance import ACCEPTANCE,NEXT
    import stocklookup_core.research.thesis_evidence_adapters as adapters
    report=json.loads(REPORT.read_text(encoding="utf-8"))
    c.verify_identity(report,ACCEPTANCE)
    assert report["all_assertions_passed"]
    assert report["universe_denominator"]==1683 and report["technical_scope"]==1503
    assert report["authority_effect"]==c.AUTHORITY and report["evaluation_scope"]=="REPLAY_DIAGNOSTIC"
    assert report["authority_status"]=="NON_AUTHORITATIVE"
    assert report["adapter_registry"]==json.loads(c.canonical(adapters.REGISTRY))
    assert report["final_public_verification"]["records"]==1683 and report["final_public_verification"]["status"]=="PASS"
    d=report["distributions"]
    for view in c.VIEWS:
        for lens in c.LENSES:
            assert sum(d[view+"/"+lens+"/lens"].values())==1683
            for axis in c.AXES: assert sum(d[view+"/"+lens+"/axis/"+axis].values())==1683
    assert d["T0_THESIS_VIEW/availability"]=={"UNAVAILABLE":1683}
    assert d["CURRENT_RESEARCH_VIEW/LONG_TERM_INVESTOR/axis/TECHNICAL"]=={"UNKNOWN":1683}
    assert report["network_provider_calls"]=={"network":0,"provider":0,"vnstock_import":0}
    assert report["daily_runs"]==report["production_publication_writes"]==report["historical_t0_writes"]==0
    assert report["non_regression"]["all_decision_field_deltas"]==0
    assert not any(report["pathology_guards"].values())
    assert set(report["knowledge_stage_counts"])=={"POST_T0_ENRICHED"}
    assert sum(report["knowledge_stage_counts"].values())==sum(report["role_counts"].values())
    assert report["foreign_cohort"]["in_cohort/1D/1"]==11
    assert report["foreign_cohort"]["qualified/1D/10"]==report["foreign_cohort"]["qualified/1D/20"]==0
    for lens,counts in report["correlation_dedup"].items():
        assert counts["input_members"]==counts["semantic_groups"]+counts["folded_members"]
    readiness=report["t0_current_separation"]["readiness"]
    assert readiness["first_complete_capture_session"] is None and readiness["complete_session_count"]==0
    assert report["next_gate"]==NEXT and report["next_gate_started"] is False
    assert report["performance"]["source_parse_passes"]=={"decision":1,"technical":1,"flow":1}
    for case in report["representative_cases"].values():
        assert case["card"]["ACTION SUPPORT REFERENCE"]["second_posture"] is False
        assert case["card"]["HEADER"]["evaluation_scope"]=="REPLAY_DIAGNOSTIC"
        assert case["card"]["HEADER"]["authority_status"]=="NON_AUTHORITATIVE"
        c.verify_identity(case["card"],m.CARD_VERSION)
        c.scan_forbidden(case["card"])


@pytest.mark.retained_evidence(".stocklookup/scratch/thesis-evidence-matrix-20261002.ndjson")
def test_exact_local_matrix_retained_samples_and_file_binding():
    from bounded_artifact_stream import source_hash
    path=ROOT/".stocklookup/scratch/thesis-evidence-matrix-20261002.ndjson"
    if not path.exists():pytest.skip("Offline Stage 1 session matrix is private retained evidence, absent in clean clone")
    report=json.loads(REPORT.read_text(encoding="utf-8"))
    assert source_hash(path)==report["matrix_artifact"]["sha256"]
    representatives={v["ticker"]:v["matrix_identity"] for v in report["representative_cases"].values()}
    verified=0;records=0
    with path.open(encoding="utf-8") as source:
        header=json.loads(next(source));assert header["session"]=="2026-10-02"
        for line in source:
            record=json.loads(line);records+=1
            if record["ticker"] in representatives:
                m.verify_matrix(record);verified+=1
                assert record["artifact_identity"]==representatives[record["ticker"]]
    assert records==1683 and verified==len(representatives)
