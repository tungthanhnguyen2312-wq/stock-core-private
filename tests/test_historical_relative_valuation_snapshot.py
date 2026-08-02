import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import semantic_evidence_bridge as bridge
from relative_valuation import evaluate_relative_valuation


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _make_ohlcv_db(root: Path, rows):
    """A temp, standalone vn_stock.db with the same ohlcv schema as production.
    Never touches the real database; each test gets its own file."""
    db_path = root / "vn_stock.db"
    connection = sqlite3.connect(str(db_path))
    connection.execute("CREATE TABLE ohlcv(ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
                        "volume INTEGER, source TEXT, PRIMARY KEY(ticker, date))")
    connection.executemany("INSERT INTO ohlcv(ticker, date, open, high, low, close, volume, source) VALUES (?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()
    return db_path


def _price_citation(ticker, trading_date, value, provider="VCI", adjustment_status="raw_as_quoted_no_adjustment_applied",
                     price_field="close", financial_period="2024"):
    citation_id = _hash({"ticker": ticker, "trading_date": trading_date, "price_field": price_field,
                          "value": value, "provider": provider})
    return {"citation_id": citation_id, "ticker": ticker, "trading_date": trading_date, "price_field": price_field,
            "value": value, "currency": "VND", "adjustment_status": adjustment_status, "adjustment_note": "test",
            "provider": provider, "source_table": "ohlcv", "reporting_frequency": "annual",
            "financial_period": financial_period, "retrieved_at": "2026-07-27T00:00:00+07:00", "schema_version": "1.0.0"}


def _write_price_citations(root: Path, citations):
    evidence_dir = root / "data" / "official-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with (evidence_dir / "market_price_citations.jsonl").open("w", encoding="utf-8") as fh:
        for c in citations:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")


def _financial(period="2024"):
    def r(m, v):
        return {"canonical_metric": m, "value": v, "quality_state": "available", "statement_scope": "consolidated",
                "period_identity": {"period": period, "period_type": "annual"}}
    return {m: r(m, v) for m, v in {"net_income": 12021443836074, "shareholders_equity": 114356467351331,
            "revenue": 138855112131387, "total_debt": 82963129469555, "cash_and_equivalents": 6887646139852}.items()}


def _share(value, semantics, period="2024"):
    return {"value": value, "semantics": semantics, "period_identity": {"period": period, "period_type": "annual"}}


def _price(value=19830.0, as_of_date="2024-12-31", financial_period="2024", is_actionable=True):
    return {"value": value, "as_of_date": as_of_date, "financial_period": financial_period,
            "source": "VCI:ohlcv", "is_actionable": is_actionable}


class HistoricalRelativeValuationSnapshotTests(unittest.TestCase):
    def test_pe_and_pb_share_identities_never_aliased(self):
        # Only a weighted-average count supplied: P/E gets it, P/B does not fall back to it.
        only_wa = evaluate_relative_valuation({"entity_type": "corporate", "current_price": _price(),
            "share_count_weighted_average_basic": _share(6396250200, "weighted_average_basic"), "financial": _financial()})
        self.assertEqual(only_wa["methods"]["pe"]["state"], "available")
        self.assertEqual(only_wa["methods"]["pb"]["state"], "unavailable")
        self.assertIn("qualified_period_end_share_count", only_wa["methods"]["pb"]["missing_inputs"])

        # Only a period-end count supplied: P/B gets it, P/E does not fall back to it.
        only_pe = evaluate_relative_valuation({"entity_type": "corporate", "current_price": _price(),
            "share_count_period_end": _share(6396250200, "period_end"), "financial": _financial()})
        self.assertEqual(only_pe["methods"]["pb"]["state"], "available")
        self.assertEqual(only_pe["methods"]["pe"]["state"], "unavailable")
        self.assertIn("qualified_weighted_average_share_count", only_pe["methods"]["pe"]["missing_inputs"])

        # A period-end count mislabeled with the wrong semantics is not accepted for P/E,
        # even though its numeric value is the one P/E would otherwise expect.
        mislabeled = evaluate_relative_valuation({"entity_type": "corporate", "current_price": _price(),
            "share_count_weighted_average_basic": _share(6396250200, "period_end"), "financial": _financial()})
        self.assertEqual(mislabeled["methods"]["pe"]["state"], "unavailable")

    def test_last_trading_day_date_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_ohlcv_db(root, [("HPG", "2024-12-30", 19940, 19970, 19830, 19900, 12176491, "VCI"),
                                   ("HPG", "2024-12-31", 19900, 19900, 19790, 19830, 10258083, "VCI")])
            _write_price_citations(root, [_price_citation("HPG", "2024-12-31", 19830.0)])
            verified = bridge.load_verified_market_price(root)
            self.assertEqual(verified["status"], "available")
            self.assertEqual(verified["rejected"], [])
            entry = verified["by_ticker_date"][("HPG", "2024-12-31")]
            self.assertEqual(entry["value"], 19830.0)
            # The reader never searches for a nearby date on its own -- only the exact
            # cited trading_date. A citation for a date with no ohlcv row fails closed.
            _write_price_citations(root, [_price_citation("HPG", "2025-01-01", 20000.0)])
            missing_date = bridge.load_verified_market_price(root)
            self.assertEqual(missing_date["by_ticker_date"], {})
            self.assertEqual(missing_date["rejected"][0]["reason"], "ohlcv_row_missing")

    def test_price_share_financial_period_alignment(self):
        # price.financial_period disagrees with the financial metrics' period -> fail closed.
        misaligned_metric = evaluate_relative_valuation({"entity_type": "corporate",
            "current_price": _price(financial_period="2023"),
            "share_count_weighted_average_basic": _share(6396250200, "weighted_average_basic"),
            "share_count_period_end": _share(6396250200, "period_end"), "financial": _financial("2024")})
        self.assertEqual(misaligned_metric["methods"]["pe"]["state"], "unavailable")
        self.assertEqual(misaligned_metric["methods"]["pb"]["state"], "unavailable")
        # price.financial_period disagrees with the period-end share count's own period ->
        # market-cap reconstruction (and therefore pb/ps/ev_sales) fails closed too.
        misaligned_shares = evaluate_relative_valuation({"entity_type": "corporate",
            "current_price": _price(financial_period="2024"),
            "share_count_period_end": _share(6396250200, "period_end", period="2023"),
            "financial": _financial("2024")})
        self.assertEqual(misaligned_shares["methods"]["pb"]["state"], "unavailable")
        self.assertIn("price_share_period_alignment", misaligned_shares["methods"]["pb"]["missing_inputs"])

    def test_market_cap_reconstruction(self):
        price_value, shares = 19830.0, 6396250200
        result = evaluate_relative_valuation({"entity_type": "corporate", "current_price": _price(price_value),
            "share_count_period_end": _share(shares, "period_end"), "financial": _financial()})
        expected_market_cap = price_value * shares
        self.assertAlmostEqual(result["methods"]["pb"]["observed_multiple"], expected_market_cap / 114356467351331)
        self.assertAlmostEqual(result["methods"]["ps"]["observed_multiple"], expected_market_cap / 138855112131387)
        expected_ev = expected_market_cap + 82963129469555 - 6887646139852
        self.assertAlmostEqual(result["methods"]["ev_sales"]["observed_multiple"], expected_ev / 138855112131387)
        # Never built from the weighted-average count, even if it is the only one supplied
        # and happens to carry the identical numeric value.
        wa_only = evaluate_relative_valuation({"entity_type": "corporate", "current_price": _price(price_value),
            "share_count_weighted_average_basic": _share(shares, "weighted_average_basic"), "financial": _financial()})
        self.assertEqual(wa_only["methods"]["pb"]["state"], "unavailable")
        self.assertEqual(wa_only["methods"]["ev_sales"]["state"], "unavailable")

    def test_fail_closed_for_unsupported_adjustment_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_ohlcv_db(root, [("HPG", "2024-12-31", 19900, 19900, 19790, 19830, 10258083, "VCI")])
            _write_price_citations(root, [_price_citation("HPG", "2024-12-31", 19830.0,
                adjustment_status="requires_split_adjustment_not_yet_applied")])
            unadjusted = bridge.load_verified_market_price(root)
            self.assertEqual(unadjusted["by_ticker_date"], {})
            self.assertEqual(unadjusted["rejected"][0]["reason"], "unsupported_adjustment_status")

    def test_fail_closed_without_any_citation_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No citation file at all -> unavailable, not an error, and relative_valuation
            # correctly stays fail-closed rather than falling back to any other price.
            legacy = bridge.load_verified_market_price(Path(tmp))
            self.assertEqual(legacy, {"status": "unavailable", "version": bridge.VERSION, "by_ticker_date": {}, "rejected": []})

    def test_fail_closed_on_drifted_ohlcv_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Citation says 19830 but the live ohlcv row has since drifted to a different
            # close -> fails closed rather than trusting the stale cited value.
            _make_ohlcv_db(root, [("HPG", "2024-12-31", 19900, 19900, 19790, 20500, 10258083, "VCI")])
            _write_price_citations(root, [_price_citation("HPG", "2024-12-31", 19830.0)])
            drifted = bridge.load_verified_market_price(root)
            self.assertEqual(drifted["by_ticker_date"], {})
            self.assertEqual(drifted["rejected"][0]["reason"], "ohlcv_value_drifted_from_citation")

    def test_ev_ebitda_stays_unavailable(self):
        result = evaluate_relative_valuation({"entity_type": "corporate", "current_price": _price(),
            "share_count_period_end": _share(6396250200, "period_end"), "financial": _financial()})
        self.assertEqual(result["methods"]["ev_ebitda"]["state"], "unavailable")
        self.assertIn("required_input_missing", result["methods"]["ev_ebitda"]["missing_inputs"])


if __name__ == "__main__":
    unittest.main()


class TemporalScopeLabellingTests(unittest.TestCase):
    """Regression guard (2026-08-02): an available multiple is built from a cited
    *historical* close (HPG FY2024 -> 2024-12-31) while the envelope's reference_at is
    the current build time. Without an explicit marker, a downstream reader (Consumer,
    AI prompt, Dashboard) cannot tell an FY2024 point-in-time P/E from a claim that the
    ticker currently trades at that multiple."""

    def _available_pe(self):
        result = evaluate_relative_valuation({"entity_type": "corporate", "current_price": _price(),
            "share_count_weighted_average_basic": _share(6396250200, "weighted_average_basic"),
            "share_count_period_end": _share(6396250200, "period_end"), "financial": _financial()},
            reference_at="2026-07-30T00:00:00+00:00")
        return result["methods"]["pe"]

    def test_available_multiple_is_marked_historical_only_and_not_market_dependent(self):
        pe = self._available_pe()
        self.assertEqual(pe["state"], "available")
        self.assertTrue(pe["historical_only"])
        self.assertFalse(pe["market_dependent"])
        self.assertEqual(pe["as_of_semantics"], "point_in_time_valuation_date_not_current_session")

    def test_available_multiple_carries_a_dated_not_current_warning(self):
        pe = self._available_pe()
        self.assertTrue(pe["warnings"], "an available historical multiple must never ship with zero warnings")
        self.assertTrue(any(pe["price_as_of_date"] in w for w in pe["warnings"]),
                        "the warning must name the actual valuation date")
        self.assertTrue(any("not a current-market valuation" in w for w in pe["warnings"]))

    def test_unavailable_method_is_not_labelled(self):
        result = evaluate_relative_valuation({}, reference_at="2026-07-30T00:00:00+00:00")
        pe = result["methods"]["pe"]
        self.assertNotEqual(pe["state"], "available")
        self.assertNotIn("historical_only", pe)
