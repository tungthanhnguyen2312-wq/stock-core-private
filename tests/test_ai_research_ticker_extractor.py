import hashlib
import json
from pathlib import Path

import pytest

from ai_research_session_delivery import build_delivery
from ai_research_ticker_extractor import (
    ABSENT_STATUS,
    TickerExtractorError,
    extract_ai_research_tickers,
    parse_tickers,
    resolve_daily_producer_run,
    write_packet,
)
from current_daily_decision_research_product import OWNER_FOCUS_TICKERS, WATCHLIST
from owner_research_focus import owner_focus_tickers


ROOT = Path(__file__).resolve().parents[1]
RETAINED_26 = ROOT / "operations-review" / "daily-producer-runs-v1" / "2026-08-26" / "9f8dcbb36d9428ff772d94a3dec85d96d0a573e39d5905b433c7ba28ffb856b0"


def _card(ticker, action="WAIT"):
    return {
        "ticker": ticker,
        "status": "AVAILABLE",
        "current_decision_state": {
            "entry_action": action,
            "is_actionable": False,
            "entry_action_is_research_label_not_execution_instruction": True,
        },
        "market_flow_positioning": {"status": "UNAVAILABLE", "traded_value": 0.0},
        "valuation_context": {"strict_valuation_status": "UNAVAILABLE"},
    }


def _scoped_operation():
    cards = {ticker: _card(ticker, "BUY_ON_CONFIRMATION") for ticker in OWNER_FOCUS_TICKERS}
    cards["QNS"] = _card("QNS", "ACCUMULATE_IN_BASE")
    cards["AAA"] = _card("AAA", "EARLY_ENTRY")
    product = {
        "artifact_identity": "product:1",
        "authority_boundary": {"is_actionable": False, "probability": "UNKNOWN_UNCALIBRATED", "recommendation": "NOT_EMITTED"},
        "market_brief": {"coverage": {"technical": 0}},
        "macro_context": {"status": "UNAVAILABLE"},
        "research_cohorts": {"EARLY_REVERSAL": {"count": 1, "tickers": ["AAA"]}},
        "high_priority_full_universe_review_set": {"count": 1, "tickers": ["AAA"]},
        "watchlist": {"cards_available": 11, "tickers": list(WATCHLIST), "is_portfolio_holdings": False},
        "owner_focus": {"tickers": list(OWNER_FOCUS_TICKERS), "cards_available": 10, "missing": [], "is_portfolio_holdings": False, "is_actionable": False},
        "aggregate_validation": {"entry_relevant_90_count": 1},
        "detailed_research_cards": cards,
        "risk_data_gap_panel": {"technical_unavailable": 0},
        "what_to_verify_next": ["verify"],
        "source_artifact_identities": {"descriptive": "descriptive:1"},
    }
    manifest = {
        "market_session": "2026-08-26",
        "operation_identity": "operation:1",
        "producer_head": "producer",
        "consumer_head": "consumer",
        "input_artifacts": {"descriptive": {"artifact_identity": "descriptive:1", "session": "2026-08-26"}},
        "outputs": {"daily_product": "product:1"},
        "warnings": ["warning"],
        "session_coherence": {"session": "2026-08-26"},
        "coverage_summary": {},
    }
    return {"product": product, "manifest": manifest, "peer": {"records": {}}, "scenario": {"records": {}}, "strategy": {"records": {}}, "portfolio_risk": None}


def _write_run(tmp_path: Path, session: str, run_hash: str, tickers=("AAA", "AAM", "HPG", "PAN", "SSI")):
    operation = _scoped_operation()
    operation["manifest"]["market_session"] = session
    inputs = {
        "descriptive": {"records": {ticker: {} for ticker in tickers}},
        "tactical": {"records": {}},
        "fundamental": {"records": {}},
        "valuation": {"records": {}},
        "market_flow_positioning": {"records": {}},
        "corporate_intelligence": {"records": {}},
    }
    delivery = build_delivery(operation, inputs)
    run_dir = tmp_path / "operations-review" / "daily-producer-runs-v1" / session / run_hash
    run_dir.mkdir(parents=True)
    (run_dir / "ai_research_session_bundle.json").write_bytes(delivery["primary"])
    (run_dir / "ai_research_full_universe.ndjson").write_bytes(delivery["full_universe"])
    (run_dir / "ai_research_bundle_manifest.json").write_bytes(delivery["manifest"])
    run_manifest = {
        "target_market_session": session,
        "run_identity": "daily_producer_run:" + run_hash,
        "daily_session_operation": {"identity": "operation:1"},
        "daily_product_identity": "product:1",
        "producer_head": "producer",
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
    return run_dir


def test_parse_tickers_preserves_request_order_not_alphabet():
    assert parse_tickers("HPG,PAN,SSI") == ["HPG", "PAN", "SSI"]
    assert parse_tickers("ssi, hpg, pan") == ["SSI", "HPG", "PAN"]


def test_resolver_requires_unique_run_or_explicit_identity(tmp_path: Path):
    _write_run(tmp_path, "2026-08-26", "aaa111")
    _write_run(tmp_path, "2026-08-21", "run1")
    _write_run(tmp_path, "2026-08-21", "run2")
    unique = resolve_daily_producer_run(tmp_path, "2026-08-26")
    assert unique.name == "aaa111"
    with pytest.raises(TickerExtractorError, match="AMBIGUOUS_SESSION_RUN"):
        resolve_daily_producer_run(tmp_path, "2026-08-21")
    chosen = resolve_daily_producer_run(tmp_path, "2026-08-21", run_identity="daily_producer_run:run2")
    assert chosen.name == "run2"
    latest = tmp_path / "operations-review" / "daily-producer-runs-v1" / "LATEST_COMPLETED_RUN.json"
    latest.write_text(json.dumps({"session": "2026-08-21", "relative_directory": "2026-08-21/run1", "navigation_only": True}), encoding="utf-8")
    with pytest.raises(TickerExtractorError, match="AMBIGUOUS_SESSION_RUN"):
        resolve_daily_producer_run(tmp_path, "2026-08-21")


def test_extractor_returns_requested_non_a_tickers_and_explicit_missing(tmp_path: Path):
    _write_run(tmp_path, "2026-08-26", "runhash")
    packet = extract_ai_research_tickers(tmp_path, session="2026-08-26", tickers="HPG,PAN,SSI,UNKNOWNX")
    assert packet["session"] == "2026-08-26"
    assert packet["run_identity"] == "daily_producer_run:runhash"
    assert packet["requested_tickers"] == ["HPG", "PAN", "SSI", "UNKNOWNX"]
    assert packet["coverage"]["present"] == ["HPG", "PAN", "SSI"]
    assert packet["coverage"]["missing"] == ["UNKNOWNX"]
    assert packet["records"]["HPG"]["status"] == "PRESENT"
    assert packet["records"]["PAN"]["card"]["ticker"] == "PAN"
    assert packet["records"]["SSI"]["source"] == "PRIMARY_SESSION_BUNDLE"
    assert packet["records"]["UNKNOWNX"]["status"] == ABSENT_STATUS
    assert "AAA" not in packet["records"]
    assert "AAM" not in packet["records"]
    assert packet["no_alphabetical_sampling"] is True
    assert packet["is_actionable"] is False
    assert packet["entry_action_is_research_label_not_execution_instruction"] is True
    assert packet["no_network"] is True
    assert packet["resolved_from"]["latest_file_navigation_used"] is False
    blob = json.dumps(packet)
    assert "target_price" not in blob
    assert packet["authority_boundary"]["recommendation"] == "NOT_EMITTED"


def test_extractor_can_lookup_non_card_ticker_from_ndjson_without_sampling(tmp_path: Path):
    _write_run(tmp_path, "2026-08-26", "runhash", tickers=("AAA", "AAM", "ZZZ"))
    packet = extract_ai_research_tickers(tmp_path, session="2026-08-26", tickers="ZZZ")
    assert list(packet["records"]) == ["ZZZ"]
    assert packet["records"]["ZZZ"]["status"] == "PRESENT_FULL_UNIVERSE_LOOKUP"
    assert packet["records"]["ZZZ"]["source"] == "FULL_UNIVERSE_LOOKUP_ONLY"
    assert "AAA" not in packet["records"]


def test_write_packet_is_deterministic(tmp_path: Path):
    _write_run(tmp_path, "2026-08-26", "runhash")
    packet = extract_ai_research_tickers(tmp_path, session="2026-08-26", tickers=["HPG", "PAN", "SSI"])
    path = write_packet(tmp_path / "ai_ticker_research_packet.json", packet)
    again = write_packet(tmp_path / "ai_ticker_research_packet.json", packet)
    assert path.read_bytes() == again.read_bytes()


def test_extractor_module_has_no_network_or_latest_file_authority():
    source = (ROOT / "ai_research_ticker_extractor.py").read_text(encoding="utf-8")
    assert "urllib" not in source
    assert "requests" not in source
    assert "http.client" not in source
    assert "LATEST_COMPLETED_RUN" not in source
    assert "glob(" not in source


def test_retained_2026_08_26_handoff_contains_owner_focus_and_extracts_hpg_pan_ssi():
    bundle = json.loads((RETAINED_26 / "ai_research_session_bundle.json").read_text(encoding="utf-8"))
    manifest = json.loads((RETAINED_26 / "ai_research_bundle_manifest.json").read_text(encoding="utf-8"))
    ndjson_path = RETAINED_26 / "ai_research_full_universe.ndjson"
    ndjson_bytes = ndjson_path.read_bytes()
    assert hashlib.sha256(ndjson_bytes).hexdigest() == manifest["files"]["ai_research_full_universe.ndjson"]["sha256"]
    first_ndjson = [json.loads(line)["ticker"] for line in ndjson_bytes.decode("utf-8").splitlines()[:6]]
    assert first_ndjson[0] < "HPG"
    watchlist = bundle["research_cohorts"]["watchlist"]["tickers"]
    cards = bundle["ticker_research_contexts"]
    for ticker in owner_focus_tickers():
        assert ticker in watchlist
        assert ticker in cards
    assert "QNS" in watchlist
    packet = extract_ai_research_tickers(ROOT, session="2026-08-26", tickers="HPG,PAN,SSI")
    assert packet["session"] == "2026-08-26"
    assert packet["run_identity"] == "daily_producer_run:9f8dcbb36d9428ff772d94a3dec85d96d0a573e39d5905b433c7ba28ffb856b0"
    assert packet["requested_tickers"] == ["HPG", "PAN", "SSI"]
    assert packet["coverage"]["missing"] == []
    assert all(packet["records"][ticker]["status"] == "PRESENT" for ticker in ("HPG", "PAN", "SSI"))
    assert "AAA" not in packet["records"]
    assert "AAM" not in packet["records"]
    assert packet["records"]["HPG"]["card"]["ticker"] == "HPG"
    assert packet["is_actionable"] is False
    assert packet["authority_boundary"]["is_actionable"] is False
