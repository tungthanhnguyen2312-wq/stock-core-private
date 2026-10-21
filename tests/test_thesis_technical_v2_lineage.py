"""Current Thesis adopts a verified Technical V2 batch; T0 does not receive it."""
import copy

import stocklookup_core.research.thesis_evidence_contract as c
import stocklookup_core.research.thesis_evidence_production as engine
from test_thesis_evidence_stage2 import DAY, fixture, records


def _write_batch(root, contexts, *, session=DAY):
    folder = root / "operations-review" / "canonical-post-close-v1" / session / "enrichment"
    folder.mkdir(parents=True)
    artifact = c.seal({
        "contract_version": "market_wide_historical_research_context/v1",
        "session": session,
        "records": {ticker: {"contextual_technical": context} for ticker, context in contexts.items()},
    }, "market_wide_historical_research_context")
    path = folder / "historical_context.json"
    path.write_text(c.canonical(artifact), encoding="utf-8")
    return path


def test_current_records_verified_v2_identity_and_t0_does_not_adopt_the_batch(tmp_path):
    args, _row, context, _bound, _path, _flow = fixture(tmp_path)
    _write_batch(tmp_path, {"VNM": context})
    current = engine.build(**args, stage="current")
    view = records(current, tmp_path)["VNM"]
    technical = view["source_pointers"]["technical"]
    assert technical["contract_version"] == "contextual_technical_feature_set/v2"
    assert technical["session"] == DAY
    assert technical["accepted_count"] == 1
    assert technical["knowledge_cutoff_bound"] == "ASIA_HO_CHI_MINH_CALENDAR_DATE"
    assert technical["post_t0_not_admitted_to_t0"] is True
    assert technical["identity"].startswith("market_wide_historical_research_context:")
    coverage = view["stage_coverage_by_axis"]
    assert coverage.get("TECHNICAL/POST_T0_ENRICHED", 0) + coverage.get("TECHNICAL/T0_SEALED", 0) > 0
    t0 = engine.build(**args, stage="t0", origin="SEAL_TIME")
    t0_view = records(t0, tmp_path)["VNM"]
    assert "technical" not in t0_view["source_pointers"]
    assert t0_view["post_items_in_t0"] == 0


def test_future_or_unverified_v2_batch_is_not_adopted(tmp_path):
    args, _row, context, _bound, _path, _flow = fixture(tmp_path)
    mutated = copy.deepcopy(context)
    mutated["knowledge_cutoff"] = "2026-10-06T00:30:00+07:00"
    _write_batch(tmp_path, {"VNM": mutated})
    current = engine.build(**args, stage="current")
    view = records(current, tmp_path)["VNM"]
    assert "technical" not in view["source_pointers"]


def test_knowledge_cutoff_uses_the_ho_chi_minh_calendar_date():
    assert engine._knowledge_cutoff_session_date("2026-10-20T16:01:37+07:00") == "2026-10-20"
    assert engine._knowledge_cutoff_session_date("2026-10-20T12:00:00Z") == "2026-10-20"
    assert engine._knowledge_cutoff_session_date("2026-10-20T23:00:00Z") == "2026-10-21"
    assert engine._knowledge_cutoff_session_date("2026-10-20T15:00:00") is None
    assert engine._knowledge_cutoff_session_date(None) is None
