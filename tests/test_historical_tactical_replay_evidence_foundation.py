import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import historical_tactical_replay_evidence_foundation as foundation
import market_wide_current_descriptive_research as descriptive_module
import watchlist_tactical_entry_classifier as classifier


DATES = tuple(f"2026-06-{day:02d}" for day in range(1, 20)) + ("2026-07-20",)


def _make_runtime(*, missing_close=False):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    database = root / "vn_stock.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript("""
            CREATE TABLE ohlcv(
                ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
                volume INTEGER, source TEXT, PRIMARY KEY(ticker, date)
            );
            CREATE TABLE ohlcv_lineage(
                ticker TEXT NOT NULL, trading_session_date TEXT NOT NULL, provider TEXT NOT NULL,
                provider_version TEXT NOT NULL, adapter_schema_version TEXT NOT NULL, endpoint TEXT NOT NULL,
                canonical_field TEXT NOT NULL, retrieved_at TEXT NOT NULL, source_record_hash TEXT NOT NULL,
                unit_scale INTEGER NOT NULL, PRIMARY KEY(ticker, trading_session_date)
            );
        """)
        for ticker, offset in (("SSI", 0.0), ("PNJ", 20.0), ("OTHER", 40.0)):
            for index, day in enumerate(DATES):
                close = None if missing_close and ticker == "SSI" and index == 3 else 100.0 + offset + index
                connection.execute(
                    "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (ticker, day, close, close, close, close, 1_000 + index, "DNSE"),
                )
                connection.execute(
                    "INSERT INTO ohlcv_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (ticker, day, "DNSE", "snapshot/v2", "lineage/v1", "/price/ohlc", "ohlcv", "2026-08-25T21:50:44+07:00", f"sha-{ticker}-{day}", 1),
                )
        connection.commit()
    finally:
        connection.close()
    return temp, root


class SQLiteFreezeTests(unittest.TestCase):
    def test_rolling_window_stops_at_t0_and_later_rows_do_not_change_earlier_features(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        before = foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",))
        before_artifact = foundation.build_artifact(freeze=before)
        connection = sqlite3.connect(root / "vn_stock.db")
        try:
            connection.execute(
                "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("SSI", "2026-07-21", 999.0, 999.0, 999.0, 999.0, 999, "DNSE"),
            )
            connection.execute(
                "INSERT INTO ohlcv_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("SSI", "2026-07-21", "DNSE", "snapshot/v2", "lineage/v1", "/price/ohlc", "ohlcv", "2026-08-25T21:50:44+07:00", "later-sha", 1),
            )
            connection.commit()
        finally:
            connection.close()
        after = foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",))
        after_artifact = foundation.build_artifact(freeze=after)
        self.assertEqual(before["frozen_content_identity"], after["frozen_content_identity"])
        self.assertEqual(before_artifact["artifact_identity"], after_artifact["artifact_identity"])
        self.assertTrue(all(row["date"] <= "2026-07-20" for row in before["frozen_ohlcv_rows"]))

    def test_mutable_db_rows_are_frozen_by_selected_content_identity(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        frozen = foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",))
        preserved = foundation.build_artifact(freeze=frozen)
        connection = sqlite3.connect(root / "vn_stock.db")
        try:
            connection.execute("UPDATE ohlcv SET close = 1.0 WHERE ticker = 'SSI' AND date = '2026-07-20'")
            connection.commit()
        finally:
            connection.close()
        changed = foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",))
        self.assertNotEqual(frozen["frozen_content_identity"], changed["frozen_content_identity"])
        repeated = foundation.build_artifact(freeze=frozen)
        self.assertEqual(preserved["artifact_identity"], repeated["artifact_identity"])
        self.assertEqual(preserved, repeated)

    def test_missing_close_fails_closed_without_defaulting(self):
        temp, root = _make_runtime(missing_close=True)
        self.addCleanup(temp.cleanup)
        frozen = foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",))
        artifact = foundation.build_artifact(freeze=frozen)
        row = artifact["historical_reconstructions"]["2026-07-20"]["representative_records"]["SSI"]
        self.assertEqual(row["reconstruction_qualification"], foundation.NOT_RECONSTRUCTABLE)
        self.assertIsNone(row["entry_state"])

    def test_later_fundamental_or_event_is_rejected_not_used_as_neutral_input(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        artifact = foundation.build_artifact(
            freeze=foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",)),
        )
        session = artifact["historical_reconstructions"]["2026-07-20"]
        self.assertEqual(session["fundamental_context"]["status"], foundation.NOT_RECONSTRUCTABLE)
        self.assertTrue(artifact["source_inventory"]["fundamental_and_corporate_event"]["later_evidence_rejected"])

    def test_reconstruction_never_opens_a_provider_connection(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        frozen = foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",))
        with mock.patch("socket.socket.connect", side_effect=AssertionError("provider call attempted")):
            artifact = foundation.build_artifact(freeze=frozen)
        self.assertFalse(artifact["authority_boundary"]["provider_or_network_calls"])


class ClassifierInvocationTests(unittest.TestCase):
    def test_reconstruction_invokes_current_classifier_without_a_rule_table_copy(self):
        temp, root = _make_runtime()
        self.addCleanup(temp.cleanup)
        frozen = foundation.freeze_sqlite_evidence(root, target_sessions=("2026-07-20",))
        with mock.patch.object(foundation.classifier, "build_artifact", wraps=classifier.build_artifact) as build:
            artifact = foundation.build_artifact(freeze=frozen)
        build.assert_called_once()
        kwargs = build.call_args.kwargs
        self.assertEqual(kwargs["requested_at"], "HISTORICAL_RECONSTRUCTION:2026-07-20")
        self.assertEqual(kwargs["descriptive_source"]["contract_version"], "market_wide_current_descriptive_research/v1")
        self.assertEqual(kwargs["screening_source"]["input_lineage"]["current_descriptive_artifact_identity"], kwargs["descriptive_source"]["artifact_identity"])
        self.assertEqual(kwargs["fundamental_source"]["records"], {})
        self.assertEqual(artifact["authority_boundary"]["classifier_policy_changed"], False)

    def test_r6_is_the_existing_classifier_result_with_independent_confirmation_recorded(self):
        technical = {
            "status": "SHADOW_ONLY", "is_current_session": True, "feature_as_of_session": "2026-07-20",
            "values": {"close": 99.0, "ma_20": 100.0, "momentum_20d": 0.05, "return_1d": 0.01, "volatility_20d": 0.02, "relative_volume_provider_scoped": 2.0},
        }
        descriptive = {
            "schema_version": "1.0.0", "contract_version": "market_wide_current_descriptive_research/v1", "session": "2026-07-20",
            "market_breadth": {"breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED"}, "momentum_descriptor": {"descriptor": "MOMENTUM_BREADTH_MIXED"}, "volatility": {"median": 0.03}},
            "sector_breadth": {"sector_count_available": 0, "sector_count_insufficient_coverage": 0, "sectors": {}},
            "liquidity_features": {},
            "validation": {"coverage": {"current_active_equity_denominator": 1, "observed_session_cohort": 1}, "lineage": {}},
            "records": {"SSI": {"ticker": "SSI", "in_current_descriptive_scope": True, "technical_features": technical, "trend_state": "AT_OR_BELOW_MA20", "liquidity": {"status": "UNAVAILABLE"}, "sector_classification": {}}},
        }
        descriptive.update(descriptive_module.content_identity(descriptive))
        screening = foundation.screening_module.build_artifact(descriptive)
        fundamental = foundation._fundamental_source("2026-07-20")
        result = classifier.build_artifact(
            descriptive_source=descriptive, screening_source=screening, fundamental_source=fundamental,
            requested_at="test",
        )["records"]["SSI"]
        self.assertEqual(result["rule_id"], "R6_EARLY_REVERSAL_CANDIDATE")
        r6 = foundation._r6_record(result)
        self.assertEqual(r6["disposition"], "R6_CONFIRMED_BY_EXISTING_CLASSIFIER")
        self.assertIn("MARKET_RELATIVE_MOMENTUM_UPPER_HALF", r6["independent_confirmation_evidence"])


class TimingAndBasisTests(unittest.TestCase):
    @staticmethod
    def _row(session, close, action="WAIT", state="DOWNTREND", rule="R9_DOWNTREND_DEFAULT"):
        return {
            "session": session, "entry_action": action, "entry_state": state, "rule_id": rule,
            "signals": {"close": close, "momentum_20d": -0.01},
            "price_basis": {"observed": foundation.PRICE_BASIS, "research_series_identity": foundation.RESEARCH_PRICE_SERIES_IDENTITY},
        }

    def test_same_basis_return_requires_the_explicit_internal_series_identity(self):
        start = self._row("2026-07-20", 100.0)
        end = self._row("2026-07-21", 110.0)
        result = foundation.same_basis_research_return(start=start, end=end)
        self.assertEqual(result["status"], "COMPUTED_RETROSPECTIVE_SAME_SERIES_ONLY")
        self.assertAlmostEqual(result["return_pct"], 0.1)
        mixed = copy.deepcopy(end)
        mixed["price_basis"]["research_series_identity"] = "ANOTHER_SERIES"
        self.assertEqual(
            foundation.same_basis_research_return(start=start, end=mixed)["reason_codes"],
            ["PRICE_SERIES_IDENTITY_MISMATCH"],
        )

    def test_false_start_is_detected_only_from_same_series_rows_after_signal(self):
        timing = foundation._same_series_timing([
            self._row("2026-07-20", 100.0),
            self._row("2026-07-21", 102.0, action="EARLY_ENTRY", state="EARLY_REVERSAL_CANDIDATE", rule="R6_EARLY_REVERSAL_CANDIDATE"),
            self._row("2026-07-22", 99.0),
        ])
        self.assertEqual(timing["false_start"]["status"], "LOWER_LOW_AFTER_SIGNAL")
        self.assertTrue(timing["false_start"]["lower_low_after_signal"])
        self.assertEqual(timing["mae_mfe_from_first_signal"]["mae_session"], "2026-07-22")


if __name__ == "__main__":
    unittest.main()
