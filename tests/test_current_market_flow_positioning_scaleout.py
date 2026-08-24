import json

import canonical_market_evidence_integration as canonical
from current_market_flow_positioning import build
from current_market_flow_positioning_scaleout import combine_retained_packets
from tools import collect_market_evidence as collector


def test_dnse_foreign_timestamp_attests_exact_requested_session():
    payload = {"foreigners": [{"time": "2026-08-21 15:00:00", "buyVolume": 1, "sellVolume": 2, "buyTradedAmount": 3, "sellTradedAmount": 4}]}
    parsed = collector.parse_raw_observation_data("DNSE", "foreign_trading", payload, "2026-08-21", "HPG")
    assert parsed["provider_session_date"] == "2026-08-21"


def test_dnse_foreign_mixed_dates_remain_session_unresolved():
    payload = {"foreigners": [{"time": "2026-08-21 15:00:00", "buyVolume": 1}, {"time": "2026-08-24 09:00:00", "sellVolume": 1}]}
    parsed = collector.parse_raw_observation_data("DNSE", "foreign_trading", payload, "2026-08-21", "HPG")
    assert parsed.get("provider_session_date") is None
    assert "dnse_foreign_trading_provider_session_mismatch_or_mixed" in parsed["semantic_gaps"]


def test_canonical_provenance_preserves_provider_session_date():
    packet = {"session_date": "2026-08-21", "packet_identity": "packet:test", "packet_sha256": "test", "observations": [{"session": "2026-08-21", "instrument": "HPG", "source": "DNSE", "endpoint_id": "foreign_trading", "status": "ACQUIRED", "usability_state": "RESEARCH_USABLE", "provider_session_date": "2026-08-21", "raw_sha256": "raw", "raw_path": "raw.json", "retrieved_at": "2026-08-21T10:00:00Z", "native_fields": {"FOREIGN_NET_VALUE": {"value": 1, "unit": "vnd"}}, "canonical_fields": {"FOREIGN_NET_VALUE": {"value": 1, "unit": "vnd"}}}]}
    item = canonical.integrate_session_packet(packet)["observations"][0]
    assert item["provenance"]["provider_session_date"] == "2026-08-21"
    assert build(canonical_integration={"session_date": "2026-08-21", "observations": [item]})["records"]["HPG"]["foreign_flow"]["status"] == "MISSING"


def test_combiner_retains_all_versions_and_selects_latest_acquired(tmp_path):
    def packet(raw, retrieved):
        return {"session_date": "2026-08-21", "packet_identity": raw, "packet_sha256": raw, "cli_parameters": {"sources": ["FHSC"], "symbols": ["HPG"]}, "observations": [{"session": "2026-08-21", "instrument": "HPG", "source": "FHSC", "endpoint_id": "trading_history", "status": "ACQUIRED", "raw_sha256": raw, "retrieved_at": retrieved, "native_fields": {}, "canonical_fields": {}}]}
    paths = []
    for raw, retrieved in (("old", "2026-08-21T10:00:00Z"), ("new", "2026-08-21T11:00:00Z")):
        path = tmp_path / (raw + ".json"); path.write_text(json.dumps(packet(raw, retrieved)), encoding="utf-8"); paths.append(path)
    combined, report = combine_retained_packets(paths, "2026-08-21")
    assert combined["observations"][0]["raw_sha256"] == "new"
    assert len(combined["observations"][0]["retained_version_lineage"]) == 2
    assert report["provider_requestable"]["FHSC"] == 1
