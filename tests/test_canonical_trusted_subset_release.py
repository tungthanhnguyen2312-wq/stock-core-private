"""Canonical trusted-subset adapter: retained session + statement evidence, no network."""
from __future__ import annotations

import csv
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import canonical_dashboard_runtime_release as runtime_release
import canonical_trusted_subset_release as trusted
from export_ai_bundle import DEFAULT_TICKERS, PRODUCER_BUNDLE_CONTRACT_VERSION
from statement_taxonomy_sidecar import build_sidecar
from trusted_subset_contract import verify_trusted_subset

SESSION = "2026-08-26"
GENERATED_AT = trusted._session_generated_at(SESSION)
CONSUMER = ROOT.parent / "ai-core-private"
CORPORATE_ITEMS = ["current_assets", "current_liabilities", "short_term_borrowings", "inventories"]
BANK_ITEMS = [
    "deposits_from_customers",
    "balances_with_the_sbv",
    "placements_with_and_loans_to_other_credit_institutions",
]


def _write_parquet(root: Path, ticker: str, items: list[str], periods: tuple[str, ...] = ("2025-Q4", "2026-Q1")) -> Path:
    directory = root / "data_bctc"
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"item_id": items, "source": ["VCI"] * len(items)})
    for period in periods:
        frame[period] = 1.0
    path = directory / f"{ticker}_balance_sheet_quarter.parquet"
    frame.to_parquet(path)
    return path


def _write_live(root: Path, session: str, tickers: list[str]) -> None:
    fields = [
        "ticker", "date", "close", "exchange", "industry", "is_live",
        "live_universe_status", "canonical_observation_status",
        "canonical_price_basis", "canonical_field_availability",
    ]
    path = root / "screen_snapshot_live.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for ticker in tickers:
            writer.writerow({
                "ticker": ticker,
                "date": session,
                "close": "10",
                "exchange": "HSX",
                "industry": "Steel",
                "is_live": "true",
                "live_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
                "canonical_observation_status": "EXACT_SESSION_RETAINED",
                "canonical_price_basis": "ADJUSTED_RETROSPECTIVE",
                "canonical_field_availability": "DIRECT_CANONICAL_MAPPING",
            })


def _canonical_manifest(root: Path, session: str) -> None:
    (root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": session}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "bundle_manifest.json").write_text(
        json.dumps({
            "schema_version": "canonical_dashboard_runtime_release/v1",
            "freshness": {"reference_session": session, "status": "fresh", "blocked": False},
            "release_contract": {"source": "retained_canonical_daily_producer", "session": session},
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "screen_snapshot.csv").write_text(
        "ticker,exchange,date\nHPG,HSX," + session + "\n",
        encoding="utf-8",
    )
    (root / "market_breadth.csv").write_text(
        f"group,date,n_up,n_down,n_flat\nALL,{session},1,1,1\n",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path, *, session: str = SESSION, tickers: list[str] | None = None,
             periods: tuple[str, ...] = ("2025-Q4", "2026-Q1")) -> Path:
    names = tickers or ["HPG", "SSI"]
    _canonical_manifest(tmp_path, session)
    _write_live(tmp_path, session, names)
    items = {"SSI": BANK_ITEMS}
    for ticker in names:
        _write_parquet(tmp_path, ticker, items.get(ticker, CORPORATE_ITEMS), periods)
    return tmp_path


@pytest.fixture
def monkey_sources(monkeypatch):
    monkeypatch.setattr(trusted, "_source_paths", lambda *args, **kwargs: {})
    return monkeypatch


def test_valid_retained_statement_evidence_known_as_of_session(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path)
    result = trusted.materialize_canonical_trusted_subset(
        ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
    )
    sidecar = json.loads((runtime / "statement_taxonomy_sidecar.json").read_text(encoding="utf-8"))
    assert result["session"] == SESSION
    assert sidecar["session_identity"] == SESSION
    assert sidecar["generated_at"] == GENERATED_AT
    assert sidecar["records"][0]["source"] == "VCI"
    report = verify_trusted_subset(runtime)
    assert report.ready
    bundle = json.loads((runtime / "analysis_bundle.json").read_text(encoding="utf-8"))
    assert bundle["tickers"]["HPG"]["snapshot"]["date"] == SESSION
    assert bundle["tickers"]["SSI"]["financial_distress_evidence"]["status"] == "not_applicable"


def test_lookahead_reporting_period_fails_closed(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path, periods=("2026-Q3",))
    with pytest.raises(trusted.CanonicalTrustedSubsetError, match="LOOKAHEAD_FINANCIAL_EVIDENCE"):
        trusted.materialize_canonical_trusted_subset(
            ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
        )


def test_vci_sidecar_relabel_is_rejected(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path)
    old = build_sidecar(runtime, generated_at="2026-08-26T06:28:43+00:00", session_identity="2026-08-25")
    old["session_identity"] = SESSION
    (runtime / "statement_taxonomy_sidecar.json").write_text(
        json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    with pytest.raises(trusted.CanonicalTrustedSubsetError, match="SIDECAR_RELABEL_REJECTED"):
        trusted.materialize_canonical_trusted_subset(
            ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
        )


def test_missing_required_taxonomy_fails_closed(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path, tickers=["HPG"])
    _write_live(runtime, SESSION, ["HPG", "SSI"])
    with pytest.raises(trusted.CanonicalTrustedSubsetError, match="MISSING_REQUIRED_TAXONOMY_EVIDENCE:SSI"):
        trusted.materialize_canonical_trusted_subset(
            ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
        )


def test_tampered_statement_payload_hash_fails_closed(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path)
    trusted.materialize_canonical_trusted_subset(
        ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
    )
    sidecar_path = runtime / "statement_taxonomy_sidecar.json"
    sidecar_path.write_text(sidecar_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    report = verify_trusted_subset(runtime)
    assert not report.ready
    assert any("statement_taxonomy_sidecar.json" in problem for problem in report.problems)


def test_market_session_mismatch_fails_closed(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path, session="2026-08-25")
    with pytest.raises(trusted.CanonicalTrustedSubsetError, match="MARKET_SESSION_MISMATCH"):
        trusted.materialize_canonical_trusted_subset(
            ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
        )


def test_trusted_artifact_hash_mismatch_fails_closed(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path)
    trusted.materialize_canonical_trusted_subset(
        ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
    )
    bundle = runtime / "analysis_bundle.json"
    bundle.write_text(bundle.read_text(encoding="utf-8").replace(SESSION, "2026-08-24"), encoding="utf-8")
    report = verify_trusted_subset(runtime)
    assert not report.ready


def test_consumer_exact_session_validator_accepts_temp_release(tmp_path, monkey_sources):
    runtime = _fixture(tmp_path)
    trusted.materialize_canonical_trusted_subset(
        ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=["HPG", "SSI"],
    )
    sys.path.insert(0, str(CONSUMER))
    from builders.build_ticker_context import verify_exact_session_bundle
    bundle_path = runtime / "analysis_bundle.json"
    ok, reason = verify_exact_session_bundle(
        bundle_path,
        json.loads(bundle_path.read_text(encoding="utf-8")),
        json.loads((runtime / "bundle_manifest.json").read_text(encoding="utf-8")),
    )
    assert ok, reason


def test_adapter_source_has_no_network_acquisition():
    source = (ROOT / "canonical_trusted_subset_release.py").read_text(encoding="utf-8")
    for banned in ("import urllib", "import requests", "import httpx", "import aiohttp"):
        assert banned not in source


def test_period_end_helper_is_calendar_not_clock():
    assert trusted.reporting_period_end("2026-Q1") == date(2026, 3, 31)
    assert trusted.reporting_period_end("2026-Q3") == date(2026, 9, 30)
    assert trusted.reporting_period_end("2026") == date(2026, 12, 31)


def test_temp_end_to_end_retained_2026_08_26(tmp_path):
    from _runtime_root import RUNTIME_ROOT
    runtime = tmp_path / "runtime"
    runtime_release.materialize_canonical_runtime_release(ROOT, runtime, SESSION)
    src = RUNTIME_ROOT / "data_bctc"
    dest = runtime / "data_bctc"
    dest.mkdir()
    for ticker in DEFAULT_TICKERS:
        shutil.copy2(src / f"{ticker}_balance_sheet_quarter.parquet", dest / f"{ticker}_balance_sheet_quarter.parquet")
    result = trusted.materialize_canonical_trusted_subset(
        ROOT, runtime, SESSION, consumer_root=CONSUMER, tickers=list(DEFAULT_TICKERS),
    )
    sidecar = json.loads((runtime / "statement_taxonomy_sidecar.json").read_text(encoding="utf-8"))
    assert sidecar["session_identity"] == SESSION
    assert sidecar["generated_at"] == GENERATED_AT
    assert sidecar["producer_contract_version"] == PRODUCER_BUNDLE_CONTRACT_VERSION
    assert result["sidecar_records"] == len(DEFAULT_TICKERS)
    report = verify_trusted_subset(runtime)
    assert report.ready

    sys.path.insert(0, str(ROOT / "tools"))
    import publish_release as release
    dest_web = tmp_path / "web"
    dest_web.mkdir()
    publisher = release.ReleasePublisher(runtime, dest_web, live=False, use_git=False, consumer_root=CONSUMER)
    code, payload = release.run_publication(publisher)
    assert code == 0
    assert payload["outcome"] == "dry_run_ok"
