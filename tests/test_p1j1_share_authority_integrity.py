"""P1J.1 — integrity of the current-share authority chain.

One test per defect the P1J.1 repair closed. Each is written against a synthetic runtime root
wherever the point is a rule rather than a fact about today's data, so the suite states what
the code must do rather than what the database happens to contain this week.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import market_wide_calculation_readiness as readiness  # noqa: E402
import market_wide_current_shares_resolver as shares  # noqa: E402

RUNTIME = ROOT.parent / "dashboard-runtime"


def build_runtime(root: Path, *, metadata: list[tuple], events: list[tuple] = (),
                  anchors: list[dict] = ()) -> Path:
    """A minimal runtime root: the two tables and the citation file the resolver reads."""
    evidence = root / "data" / "official-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    with (evidence / "share_basis_citations.jsonl").open("w", encoding="utf-8") as handle:
        for anchor in anchors:
            handle.write(json.dumps(anchor) + "\n")

    connection = sqlite3.connect(root / "vn_stock.db")
    connection.execute("CREATE TABLE metadata (ticker TEXT, shares_outstanding REAL, updated TEXT)")
    connection.execute("CREATE TABLE corporate_event_records "
                       "(ticker TEXT, event_code TEXT, exright_date TEXT, coverage_status TEXT)")
    connection.executemany("INSERT INTO metadata VALUES (?, ?, ?)", metadata)
    connection.executemany("INSERT INTO corporate_event_records VALUES (?, ?, ?, ?)", events)
    connection.commit()
    connection.close()
    return root


def anchor(ticker: str, value: int, period: str = "2024") -> dict:
    return {"ticker": ticker, "value": value, "identity_type": "period_end_shares_outstanding",
            "reporting_period": period, "reporting_frequency": "annual",
            "share_class": "common_outstanding", "unit": "shares",
            "citation_id": f"cite_{ticker.lower()}"}


class SessionPinningTests(unittest.TestCase):
    """The session must be supplied. It used to default to a literal `"2026-07-30"`."""

    def test_session_date_has_no_default(self) -> None:
        with self.assertRaises(TypeError):
            shares.resolve_effective_shares("HPG", RUNTIME)  # type: ignore[call-arg]

    def test_session_date_must_be_a_date(self) -> None:
        with self.assertRaises(ValueError):
            shares.resolve_effective_shares("HPG", RUNTIME, "not-a-date")
        with self.assertRaises(ValueError):
            shares.resolve_market_wide_shares(RUNTIME, "")

    def test_the_resolved_session_is_the_session_reported(self) -> None:
        for session in ("2026-08-03", "2026-07-30"):
            result = shares.resolve_effective_shares("HPG", RUNTIME, session)
            self.assertEqual(result["session_date"], session)

    def test_lag_is_measured_against_the_requested_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(Path(tmp), metadata=[("AAA", 1000.0, "2026-07-30 17:00")])
            same = shares.resolve_effective_shares("AAA", root, "2026-07-30")
            later = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertEqual(same["authority"], "provider_reported_current")
        self.assertEqual(same["observation_lag_days"], 0)
        self.assertEqual(later["authority"], "provider_reported_lagged")
        self.assertEqual(later["observation_lag_days"], 4)


class OfficialAnchorTests(unittest.TestCase):
    """Anchors are read from the citation store. Two of the three literals were wrong."""

    def test_anchors_come_from_the_citation_file(self) -> None:
        loaded = shares.load_official_anchors(RUNTIME)
        self.assertEqual(loaded["VCB"]["value"], 5589091262)
        self.assertEqual(loaded["HPG"]["value"], 6396250200)
        self.assertEqual(loaded["VNM"]["value"], 2089955445)

    def test_the_retired_literals_are_produced_by_no_code_path(self) -> None:
        source = (ROOT / "market_wide_current_shares_resolver.py").read_text(encoding="utf-8")
        for wrong in ("7163748865", "5589091222"):
            self.assertNotIn(wrong, source)

    def test_a_period_end_anchor_is_not_a_current_share_count(self) -> None:
        """The promotion gate stays shut while the ledger cannot prove the interval."""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(
                Path(tmp),
                metadata=[("AAA", 2000.0, "2026-08-03 17:00")],
                events=[("AAA", "ISS", "2026-05-01", "partial_unqualified_50_row_cap")],
                anchors=[anchor("AAA", 1000)])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertNotEqual(result["authority"], "qualified_official")
        self.assertEqual(result["official_anchor_value"], 1000)
        self.assertEqual(result["official_anchor_not_promoted_because"],
                         "corporate_action_ledger_coverage_not_qualified")
        self.assertEqual(result["value"], 2000)

    def test_a_qualified_ledger_opens_the_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(
                Path(tmp),
                metadata=[("AAA", 2000.0, "2026-08-03 17:00")],
                events=[("AAA", "AGME", "2026-05-01", "qualified")],
                anchors=[anchor("AAA", 1000)])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertEqual(result["authority"], "qualified_official")
        self.assertEqual(result["value"], 1000)
        self.assertEqual(result["share_concept"], "current_common_shares_outstanding")

    def test_no_ticker_is_qualified_official_against_the_live_runtime(self) -> None:
        """Today's retained ledger is row-capped, so the honest count is zero, not three."""
        summary = shares.resolve_market_wide_shares(RUNTIME, "2026-08-03")
        self.assertEqual(summary["counts"].get("qualified_official", 0), 0)


class EventClassificationTests(unittest.TestCase):
    def test_a_benign_event_does_not_invalidate_the_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(
                Path(tmp),
                metadata=[("AAA", 1000.0, "2026-08-03 17:00")],
                events=[("AAA", "DDINS", "2026-09-01", "partial_unqualified_50_row_cap"),
                        ("AAA", "AGME", "2026-09-02", "partial_unqualified_50_row_cap")])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertEqual(result["authority"], "provider_reported_current")
        self.assertEqual(result["share_changing_after_observation"], [])

    def test_a_share_changing_event_after_the_observation_invalidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(
                Path(tmp),
                metadata=[("AAA", 1000.0, "2026-08-01 17:00")],
                events=[("AAA", "ISS", "2026-08-02", "partial_unqualified_50_row_cap")])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertEqual(result["authority"], "provider_reported_stale")
        self.assertIsNone(result["value"])
        self.assertEqual(result["share_changing_after_observation"], ["ISS"])

    def test_a_share_changing_event_before_the_observation_does_not(self) -> None:
        """The old rule compared against a fixed 2024-12-31 and invalidated on events the
        provider observation already reflects. HPG is the live case."""
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(
                Path(tmp),
                metadata=[("AAA", 1100.0, "2026-08-01 17:00")],
                events=[("AAA", "ISS", "2026-06-04", "partial_unqualified_50_row_cap")])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-01")
        self.assertEqual(result["authority"], "provider_reported_current")
        self.assertEqual(result["value"], 1100)

    def test_a_share_changing_event_without_an_ex_date_is_unverifiable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(
                Path(tmp),
                metadata=[("AAA", 1000.0, "2026-08-01 17:00")],
                events=[("AAA", "ISS", None, "partial_unqualified_50_row_cap")])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertEqual(result["authority"], "provider_reported_unverifiable_freshness")
        self.assertIsNone(result["value"])
        self.assertEqual(result["reason"],
                         "missing_explicit_official_ex_date_on_share_relevant_event")

    def test_an_unclassified_event_code_is_never_silently_benign(self) -> None:
        self.assertEqual(shares._classify_event_code("ZZZZ"), "unclassified")
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(
                Path(tmp),
                metadata=[("AAA", 1000.0, "2026-08-01 17:00")],
                events=[("AAA", "ZZZZ", "2026-08-02", "partial_unqualified_50_row_cap")])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertEqual(result["authority"], "provider_reported_stale")


class FailClosedTests(unittest.TestCase):
    def test_an_unreadable_store_is_not_an_absent_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = shares.resolve_effective_shares("AAA", Path(tmp), "2026-08-03")
        self.assertEqual(result["authority"], "unresolved_error")
        self.assertNotEqual(result["authority"], "unavailable")
        self.assertIsNone(result["value"])

    def test_a_market_wide_read_failure_reports_no_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = shares.resolve_market_wide_shares(Path(tmp), "2026-08-03")
        self.assertEqual(summary["status"], "unresolved_error")
        self.assertIsNone(summary["counts"])
        self.assertIsNone(summary["active_universe_count"])

    def test_a_missing_or_non_positive_value_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(Path(tmp), metadata=[("AAA", 0.0, "2026-08-03 17:00"),
                                                      ("BBB", None, "2026-08-03 17:00")])
            for ticker in ("AAA", "BBB"):
                result = shares.resolve_effective_shares(ticker, root, "2026-08-03")
                self.assertEqual(result["authority"], "unavailable")
                self.assertIsNone(result["value"])

    def test_an_unparseable_observation_date_is_named_not_assumed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_runtime(Path(tmp), metadata=[("AAA", 1000.0, "not a date")])
            result = shares.resolve_effective_shares("AAA", root, "2026-08-03")
        self.assertEqual(result["authority"], "unknown_observation_date")
        self.assertIsNone(result["value"])


class MarketWideMeasurementTests(unittest.TestCase):
    def test_the_lanes_partition_the_universe(self) -> None:
        summary = shares.resolve_market_wide_shares(RUNTIME, "2026-08-03")
        self.assertEqual(summary["status"], "measured")
        self.assertTrue(summary["counts_reconcile"])
        self.assertEqual(sum(summary["counts"].values()), summary["active_universe_count"])

    def test_the_measurement_carries_its_own_lineage(self) -> None:
        summary = shares.resolve_market_wide_shares(RUNTIME, "2026-08-03")
        self.assertEqual(summary["session_date"], "2026-08-03")
        self.assertTrue(summary["measured_at"])
        self.assertIn("share_basis_citations.jsonl", summary["source"])

    def test_the_counts_move_with_the_data(self) -> None:
        """A count that cannot change is not a measurement. Two runtimes, two answers."""
        with tempfile.TemporaryDirectory() as tmp:
            small = build_runtime(Path(tmp) / "a", metadata=[("AAA", 1000.0, "2026-08-03 17:00")])
            large = build_runtime(Path(tmp) / "b", metadata=[("AAA", 1000.0, "2026-08-03 17:00"),
                                                             ("BBB", 2000.0, "2026-08-03 17:00")])
            self.assertEqual(shares.resolve_market_wide_shares(small, "2026-08-03")["active_universe_count"], 1)
            self.assertEqual(shares.resolve_market_wide_shares(large, "2026-08-03")["active_universe_count"], 2)


class MarketCapQualificationTests(unittest.TestCase):
    """A market cap is only as qualified as its weaker leg, and the price leg is a leg."""

    QUALIFIED_SHARES = {"value": 1000, "status": "qualified", "authority": "qualified_official",
                        "share_concept": "current_common_shares_outstanding"}

    def test_an_unverified_price_basis_blocks_qualification(self) -> None:
        result = readiness.evaluate_market_capitalisation(
            "2024", session_price=10.0, effective_shares=self.QUALIFIED_SHARES,
            price_basis_verified=False)
        self.assertEqual(result["status"], readiness.STATUS_PROVIDER_REPORTED)
        self.assertIn("price_basis_unverified_market_capitalisation_cannot_be_qualified",
                      result["warnings"])

    def test_both_legs_qualified_yields_a_qualified_cap(self) -> None:
        result = readiness.evaluate_market_capitalisation(
            "2024", session_price=10.0, effective_shares=self.QUALIFIED_SHARES,
            price_basis_verified=True)
        self.assertEqual(result["status"], readiness.STATUS_QUALIFIED)

    def test_price_basis_defaults_to_unverified(self) -> None:
        result = readiness.evaluate_market_capitalisation(
            "2024", session_price=10.0, effective_shares=self.QUALIFIED_SHARES)
        self.assertEqual(result["status"], readiness.STATUS_PROVIDER_REPORTED)

    def test_issued_shares_carry_a_comparability_warning(self) -> None:
        result = readiness.evaluate_market_capitalisation(
            "2024", session_price=10.0,
            effective_shares={"value": 1000, "status": "provider_reported",
                              "authority": "provider_reported_lagged",
                              "share_concept": "ISSUED_SHARES"})
        self.assertEqual(result["terms"]["share_concept"], "ISSUED_SHARES")
        self.assertTrue(any("treasury_not_deducted" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
