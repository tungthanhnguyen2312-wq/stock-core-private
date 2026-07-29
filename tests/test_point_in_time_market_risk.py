import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import point_in_time_market_risk as pit_risk
import semantic_evidence_bridge as bridge


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _evidence_id(sha256, ticker="VNM"):
    return _hash({"authority_domain": "vinamilk.com.vn", "source_url": "u", "sha256": sha256, "ticker": ticker,
        "reporting_period": "2024", "evidence_type": "audited_consolidated_financial_statements"})


def _evidence_record(evidence_id, filename, sha256, ticker="VNM"):
    return {"evidence_id": evidence_id, "authority": "KPMG Vietnam", "authority_domain": "vinamilk.com.vn", "ticker": ticker,
        "issuer": "Vietnam Dairy Products Joint Stock Company", "evidence_type": "audited_consolidated_financial_statements",
        "source_url": "https://vinamilk.com.vn/" + filename, "document_title": "Vinamilk 2024 Annual Report",
        "reporting_period": "2024", "publication_date": "2025-02-28", "retrieved_at": "2026-07-28T13:42:50Z",
        "content_type": "application/pdf", "language": "en", "filename": filename, "sha256": sha256, "byte_size": 100,
        "source_location_capability": "official_ir_portal", "qualification_state": "qualified", "warnings": [], "is_actionable": False}


def _write_risk_runtime(root, vnm_prices, bmk_prices, pdf_bytes=b"%PDF-1.4 test risk"):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    evidence_id = _evidence_id(sha256, ticker="VNM")
    (evidence_dir / "vnm.pdf").write_bytes(pdf_bytes)
    (evidence_dir / "manifest.json").write_text(json.dumps({"schema_version": "1.0.0", "records": [_evidence_record(evidence_id, "vnm.pdf", sha256)]}), encoding="utf-8")

    with (evidence_dir / "cash_dividend_citations.jsonl").open("w", encoding="utf-8") as fh: pass
    with (evidence_dir / "non_cash_event_citations.jsonl").open("w", encoding="utf-8") as fh: pass

    vnm_cits = []
    db_path = root / "vn_stock.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")

    for pdate, pval in vnm_prices:
        cit_id = _hash({"ticker": "VNM", "trading_date": pdate, "price_field": "close", "value": float(pval), "provider": "SSI"})
        vnm_cits.append({
            "citation_id": cit_id, "ticker": "VNM", "trading_date": pdate,
            "price_field": "close", "value": float(pval), "currency": "VND",
            "adjustment_status": "raw_as_quoted_no_adjustment_applied", "provider": "SSI", "schema_version": "1.0.0"
        })
        conn.execute("INSERT INTO ohlcv VALUES ('VNM', ?, ?, ?, ?, ?, 1000000.0, 'SSI')", (pdate, float(pval), float(pval)+500, float(pval)-500, float(pval)))

    for pdate, pval in bmk_prices:
        conn.execute("INSERT INTO ohlcv VALUES ('VNINDEX', ?, ?, ?, ?, ?, 1000000.0, 'SSI')", (pdate, float(pval), float(pval)+500, float(pval)-500, float(pval)))

    conn.commit()
    conn.close()

    with (evidence_dir / "market_price_citations.jsonl").open("w", encoding="utf-8") as fh:
        for pc in vnm_cits: fh.write(json.dumps(pc, ensure_ascii=False) + "\n")

    return evidence_id


class PointInTimeMarketRiskTests(unittest.TestCase):
    def test_59_to_60_observation_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test gate"

            # Create 61 synthetic price dates to yield 60 valid return pairs
            # (First price date produces null return, subsequent 60 dates produce 60 valid returns)
            dates = [f"2024-01-{(i+1):02d}" if i < 30 else f"2024-02-{(i-29):02d}" for i in range(61)]
            
            # VNM prices: linearly increasing 100000 + i*100
            # BMK prices: linearly increasing 1200 + i*2
            vnm_prices = [(d, 100000.0 + i * 100.0) for i, d in enumerate(dates)]
            bmk_prices = [(d, 1200.0 + i * 2.0) for i, d in enumerate(dates)]

            _write_risk_runtime(root, vnm_prices, bmk_prices, pdf_bytes=pdf_bytes)

            res = pit_risk.calculate_point_in_time_beta_and_correlation(root, ticker="VNM", benchmark_symbol="VNINDEX", window_length=60)
            self.assertEqual(res["status"], "available")
            
            series = res["metric_series"]
            self.assertEqual(len(series), 61)

            # At index 59 (59th valid return observation): gate fails closed
            row59 = series[59]
            self.assertEqual(row59["eligible_observation_count"], 59)
            self.assertIsNone(row59["beta_value"])
            self.assertIsNone(row59["correlation_value"])
            self.assertEqual(row59["unavailable_reason"], "insufficient_aligned_observations")

            # At index 60 (60th valid return observation): exactly 60 available -> beta & correlation computed
            row60 = series[60]
            self.assertEqual(row60["eligible_observation_count"], 60)
            self.assertIsNotNone(row60["beta_value"])
            self.assertIsNotNone(row60["correlation_value"])
            self.assertIsNone(row60["unavailable_reason"])

    def test_zero_variance_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test zero var"
            dates = [f"2024-01-{(i+1):02d}" if i < 30 else f"2024-02-{(i-29):02d}" for i in range(61)]

            vnm_prices = [(d, 100000.0 + i * 100.0) for i, d in enumerate(dates)]
            # Constant benchmark price (zero return variance)
            bmk_prices = [(d, 1200.0) for _, d in enumerate(dates)]

            _write_risk_runtime(root, vnm_prices, bmk_prices, pdf_bytes=pdf_bytes)

            res = pit_risk.calculate_point_in_time_beta_and_correlation(root, ticker="VNM", benchmark_symbol="VNINDEX", window_length=60)
            row60 = res["metric_series"][60]
            self.assertIsNone(row60["beta_value"])
            self.assertEqual(row60["unavailable_reason"], "zero_or_near_zero_benchmark_variance")

    def test_byte_identical_repeated_risk_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test risk determinism"
            dates = [f"2024-01-{(i+1):02d}" if i < 30 else f"2024-02-{(i-29):02d}" for i in range(61)]
            vnm_prices = [(d, 100000.0 + i * 100.0) for i, d in enumerate(dates)]
            bmk_prices = [(d, 1200.0 + i * 2.0) for i, d in enumerate(dates)]
            _write_risk_runtime(root, vnm_prices, bmk_prices, pdf_bytes=pdf_bytes)

            run1 = pit_risk.calculate_point_in_time_beta_and_correlation(root, ticker="VNM", benchmark_symbol="VNINDEX")
            run2 = pit_risk.calculate_point_in_time_beta_and_correlation(root, ticker="VNM", benchmark_symbol="VNINDEX")
            self.assertEqual(run1, run2)

    def test_zero_alpha_portfolio_backtest_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = b"%PDF-1.4 test risk safety"
            dates = [f"2024-01-{(i+1):02d}" if i < 30 else f"2024-02-{(i-29):02d}" for i in range(61)]
            vnm_prices = [(d, 100000.0 + i * 100.0) for i, d in enumerate(dates)]
            bmk_prices = [(d, 1200.0 + i * 2.0) for i, d in enumerate(dates)]
            _write_risk_runtime(root, vnm_prices, bmk_prices, pdf_bytes=pdf_bytes)

            res = pit_risk.calculate_point_in_time_beta_and_correlation(root, ticker="VNM", benchmark_symbol="VNINDEX")
            self.assertNotIn("alpha", res)
            self.assertNotIn("portfolio", res)
            self.assertNotIn("backtest", res)
            for m in res["metric_series"]:
                self.assertNotIn("alpha", m)
                self.assertNotIn("portfolio", m)
                self.assertNotIn("backtest", m)


if __name__ == "__main__":
    unittest.main()
