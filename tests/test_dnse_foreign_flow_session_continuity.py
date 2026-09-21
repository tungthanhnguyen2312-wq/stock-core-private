"""QUALIFIED_SESSION_REFERENCE_CORRECTIVE: the non-exhaustive Daily completed-session
registry as a bounded, fail-closed SECONDARY proof of foreign-flow window/streak
continuity, used only when vn_stock.db's exhaustive OHLCV reference is unavailable.

Covers both the low-level proof function (`_prove_continuity`) directly and the full
`build_series()` integration, so a regression in either layer is caught. Never tests
dnse_foreign_flow_store.py's pre-existing exhaustive-only window/streak arithmetic,
which tests/test_dnse_foreign_flow_store.py already covers exhaustively; this file
tests exactly what QUALIFIED_SESSION_REFERENCE_CORRECTIVE adds.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import dnse_foreign_flow_store as store
from daily_session_completion_reference import registry_path
from dnse_foreign_flow_capability import normalize_record


def _raw(session_date: str, ticker: str = "HPG", buy: int = 100, sell: int = 40) -> dict:
    return {
        "boardId": "G4", "buyTradedAmount": 0, "buyVolume": 0,
        "foreignerBuyPossibleQuantity": 1, "foreignerOrderLimitQuantity": 1,
        "marketId": "STO", "sellTradedAmount": 0, "sellVolume": 0,
        "symbol": ticker, "time": f"{session_date} 15:33:11.407",
        "totalBuyTradedAmount": buy, "totalBuyVolume": 1,
        "totalSellTradedAmount": sell, "totalSellVolume": 1, "tradingSessionId": "99",
    }


def _normalized(session_date: str, ticker: str = "HPG", buy: int = 100, sell: int = 40) -> dict:
    return normalize_record(_raw(session_date, ticker, buy, sell), source_endpoint=f"/price/{ticker}/foreign-trading")


def _write_registry(tmp: str, qualified_dates: list[str]) -> Path:
    path = registry_path(tmp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"completed_sessions": {
        d: {"status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True} for d in qualified_dates
    }}), encoding="utf-8")
    return path


def _make_ohlcv(tmp: str, ticker: str, dates: list[str]) -> None:
    conn = sqlite3.connect(Path(tmp) / "vn_stock.db")
    conn.execute("CREATE TABLE ohlcv (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume INTEGER, source TEXT)")
    conn.executemany("INSERT INTO ohlcv (ticker, date, open, high, low, close, volume, source) "
                      "VALUES (?, ?, 1, 1, 1, 1, 1, 'VCI')", [(ticker, d) for d in dates])
    conn.commit()
    conn.close()


class ProveContinuityUnitTests(unittest.TestCase):
    """Direct tests of the pure proof function, independent of the store/registry I/O."""

    def test_five_consecutive_civil_dates_all_registry_qualified_are_proven_continuous(self):
        dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
        proof = store._prove_continuity(dates, exhaustive_dates=set(), registry_dates=frozenset(dates))
        self.assertEqual(store.PROOF_CONTINUOUS, proof["proof_state"])
        self.assertEqual(store.AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE, proof["authority_scope"])
        self.assertFalse(proof["exhaustive"])

    def test_civil_adjacency_alone_never_creates_trading_session_authority(self):
        """Two civil-adjacent dates that are NOT registry-qualified must never be
        proven continuous -- adjacency proves only "nothing could be missing between
        them", never "these dates themselves are trading sessions"."""
        proof = store._prove_continuity(["2026-09-14", "2026-09-15"], exhaustive_dates=set(), registry_dates=frozenset())
        self.assertEqual(store.PROOF_UNVERIFIABLE, proof["proof_state"])

    def test_friday_to_monday_gap_without_exhaustive_reference_stays_unverifiable(self):
        # 2026-09-18 (Fri) -> 2026-09-21 (Mon): both individually registry-qualified,
        # but the registry's silence about 2026-09-19/20 does not prove they were
        # non-trading days, so this can never be resolved to complete OR incomplete.
        registry = frozenset({"2026-09-18", "2026-09-21"})
        proof = store._prove_continuity(["2026-09-18", "2026-09-21"], exhaustive_dates=set(), registry_dates=registry)
        self.assertEqual(store.PROOF_UNVERIFIABLE, proof["proof_state"])
        self.assertNotEqual(store.PROOF_CONTINUOUS, proof["proof_state"])
        self.assertNotEqual(store.PROOF_GAP, proof["proof_state"])

    def test_a_missing_daily_session_inside_the_window_stays_unverifiable(self):
        # 2026-09-16 was never recorded in the registry at all (Daily could have
        # failed, or the day could genuinely not have been a trading session) --
        # its absence must never be treated as proof either way.
        dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
        registry = frozenset(d for d in dates if d != "2026-09-16")
        proof = store._prove_continuity(dates, exhaustive_dates=set(), registry_dates=registry)
        self.assertEqual(store.PROOF_UNVERIFIABLE, proof["proof_state"])

    def test_exhaustive_reference_takes_precedence_over_registry_when_available(self):
        dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
        proof = store._prove_continuity(dates, exhaustive_dates=set(dates), registry_dates=frozenset())
        self.assertEqual(store.AUTHORITY_SCOPE_EXHAUSTIVE, proof["authority_scope"])
        self.assertTrue(proof["exhaustive"])

    def test_exhaustive_gap_is_proven_gap_not_unverifiable(self):
        exhaustive = {"2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"}
        proof = store._prove_continuity(["2026-08-03", "2026-08-06"], exhaustive_dates=exhaustive, registry_dates=frozenset())
        self.assertEqual(store.PROOF_GAP, proof["proof_state"])


class StaleNonemptyExhaustiveReferenceTests(unittest.TestCase):
    """STALE_NONEMPTY_EXHAUSTIVE_REFERENCE_CORRECTIVE: a real, non-empty vn_stock.db
    that simply stopped updating before the candidate window began (e.g. retained
    through 2026-08-25, candidate window 2026-09-14..18 -- the real dashboard-runtime
    shape) must never be treated as authoritative for that window. Before this fix,
    `if exhaustive_dates:` alone selected the exhaustive path, sliced an empty
    sub-range, and wrongly reported PROVEN_GAP with an empty missing list --
    silently suppressing a valid registry fallback."""

    STALE_EXHAUSTIVE = {"2026-08-20", "2026-08-21", "2026-08-24", "2026-08-25"}
    CANDIDATE = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]

    def test_stale_nonempty_exhaustive_reference_is_marked_interval_not_covered(self):
        proof = store._prove_continuity(self.CANDIDATE, exhaustive_dates=self.STALE_EXHAUSTIVE,
                                        registry_dates=frozenset(self.CANDIDATE))
        self.assertEqual(store.EXHAUSTIVE_REFERENCE_INTERVAL_NOT_COVERED, proof["interval_capability"])

    def test_stale_nonempty_exhaustive_reference_falls_through_to_registry_proof(self):
        proof = store._prove_continuity(self.CANDIDATE, exhaustive_dates=self.STALE_EXHAUSTIVE,
                                        registry_dates=frozenset(self.CANDIDATE))
        self.assertEqual(store.PROOF_CONTINUOUS, proof["proof_state"])
        self.assertEqual(store.AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE, proof["authority_scope"])
        self.assertFalse(proof["exhaustive"])

    def test_stale_nonempty_exhaustive_reference_never_reports_a_gap_with_no_missing_dates(self):
        """The exact defect Grok's review caught: PROVEN_GAP with an empty missing
        list, because the interval slice against a stale-but-nonempty set was empty
        by construction. That state must never occur again for any input."""
        proof = store._prove_continuity(self.CANDIDATE, exhaustive_dates=self.STALE_EXHAUSTIVE,
                                        registry_dates=frozenset(self.CANDIDATE))
        self.assertNotEqual(store.PROOF_GAP, proof["proof_state"])

    def test_stale_nonempty_exhaustive_plus_incomplete_registry_stays_unverifiable(self):
        registry = frozenset(d for d in self.CANDIDATE if d != "2026-09-16")
        proof = store._prove_continuity(self.CANDIDATE, exhaustive_dates=self.STALE_EXHAUSTIVE, registry_dates=registry)
        self.assertEqual(store.PROOF_UNVERIFIABLE, proof["proof_state"])
        self.assertEqual(store.EXHAUSTIVE_REFERENCE_INTERVAL_NOT_COVERED, proof["interval_capability"])

    def test_exhaustive_spanning_interval_and_detecting_a_gap_is_unaffected(self):
        exhaustive = {"2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10"}
        skip_gap = ["2026-08-03", "2026-08-04", "2026-08-06", "2026-08-07", "2026-08-10"]
        proof = store._prove_continuity(skip_gap, exhaustive_dates=exhaustive, registry_dates=frozenset())
        self.assertEqual(store.PROOF_GAP, proof["proof_state"])
        self.assertEqual(store.EXHAUSTIVE_REFERENCE_INTERVAL_COVERED, proof["interval_capability"])

    def test_exhaustive_spanning_interval_and_matching_exactly_is_unaffected(self):
        dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
        proof = store._prove_continuity(dates, exhaustive_dates=set(dates), registry_dates=frozenset())
        self.assertEqual(store.PROOF_CONTINUOUS, proof["proof_state"])
        self.assertEqual(store.EXHAUSTIVE_REFERENCE_INTERVAL_COVERED, proof["interval_capability"])

    def test_freshness_never_reports_zero_sessions_behind_from_a_stale_nonempty_reference(self):
        """The matching defect in `_freshness`: a real, non-empty exhaustive
        reference that stops before the reference session must not silently count
        zero trading dates in its own unreachable range and report that as an exact
        "0 sessions behind" -- that would sit self-contradictorily next to
        status="stale"."""
        latest = store._freshness("2026-09-18", "2026-09-21", self.STALE_EXHAUSTIVE)
        self.assertEqual("stale", latest["status"])
        self.assertIsNone(latest["sessions_behind"])

    def test_real_dashboard_runtime_shape_end_to_end_via_build_series(self):
        """Full-stack reproduction of the exact reported real edge: a real, non-empty
        vn_stock.db retained through 2026-08-25 (dashboard-runtime's actual shape),
        with the retained 14-18 foreign-flow observations and a qualifying registry."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_ohlcv(tmp, "FPT", sorted(self.STALE_EXHAUSTIVE))
            registry = _write_registry(tmp, self.CANDIDATE)
            store.write_observations(tmp, "FPT", [_normalized(d, "FPT", buy=100, sell=40) for d in self.CANDIDATE])
            result = store.build_series(tmp, "FPT", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=registry)
            summary = result["window_summaries"]["5_session"]
            self.assertEqual("complete", summary["coverage"])
            self.assertEqual(store.EXHAUSTIVE_REFERENCE_INTERVAL_NOT_COVERED,
                              summary["continuity_reference"]["interval_capability"])
            self.assertEqual(store.AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE,
                              summary["continuity_reference"]["authority_scope"])
            self.assertEqual(5 * (100 - 40), summary["cumulative_net_value_vnd"])
            self.assertEqual(5, result["current_consecutive_net_buy_sessions"])


class WindowAndStreakIntegrationTests(unittest.TestCase):
    """Full build_series() integration: no vn_stock.db, registry supplies the proof."""

    def test_real_14_to_18_window_is_complete_via_registry_when_vn_stock_db_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            registry = _write_registry(tmp, dates)
            store.write_observations(tmp, "HPG", [_normalized(d, buy=100, sell=40) for d in dates])
            # An empty vn_stock.db (present but no ohlcv rows) must not block the registry fallback.
            _make_ohlcv(tmp, "HPG", [])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=registry)
            summary = result["window_summaries"]["5_session"]
            self.assertEqual("complete", summary["coverage"])
            self.assertEqual(5 * (100 - 40), summary["cumulative_net_value_vnd"])
            self.assertEqual(store.AUTHORITY_SCOPE_QUALIFIED_NONEXHAUSTIVE,
                              summary["continuity_reference"]["authority_scope"])
            self.assertFalse(summary["continuity_reference"]["exhaustive"])
            self.assertEqual(5, result["current_consecutive_net_buy_sessions"])

    def test_stale_empty_vn_stock_db_does_not_block_the_registry_proven_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            registry = _write_registry(tmp, dates)
            store.write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            # No vn_stock.db file at all this time (not even present).
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=registry)
            self.assertEqual("complete", result["window_summaries"]["5_session"]["coverage"])

    def test_without_registry_path_the_same_window_stays_unverifiable(self):
        """Backward compatibility: omitting the new parameter entirely (every
        pre-existing caller) must reproduce the exact pre-corrective behavior."""
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            store.write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18")
            self.assertEqual("unverifiable", result["window_summaries"]["5_session"]["coverage"])

    def test_a_registry_gap_wider_than_one_civil_day_keeps_the_window_unverifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            registry = _write_registry(tmp, dates + ["2026-09-21"])
            # Replace 2026-09-18 with 2026-09-21 in the retained observations so the
            # candidate window itself spans the Fri->Mon gap.
            window_dates = ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"]
            store.write_observations(tmp, "HPG", [_normalized(d) for d in window_dates])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-21",
                                        qualified_session_registry_path=registry)
            self.assertEqual("unverifiable", result["window_summaries"]["5_session"]["coverage"])

    def test_10_session_window_stays_incomplete_with_only_5_registry_proven_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            registry = _write_registry(tmp, dates)
            store.write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=registry)
            summary = result["window_summaries"]["10_session"]
            self.assertEqual("incomplete", summary["coverage"])
            self.assertIsNone(summary["cumulative_net_value_vnd"])

    def test_streak_persists_when_continuity_is_registry_proven(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            registry = _write_registry(tmp, dates)
            store.write_observations(tmp, "HPG", [_normalized(d, buy=100, sell=40) for d in dates])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=registry)
            self.assertEqual(5, result["current_consecutive_net_buy_sessions"])

    def test_streak_resets_when_continuity_is_entirely_unproven(self):
        """No exhaustive reference and no registry path at all: every adjacent pair
        is UNVERIFIABLE, so the streak must never silently carry forward across
        observations whose gap-freeness was never established."""
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            store.write_observations(tmp, "HPG", [_normalized(d, buy=100, sell=40) for d in dates])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18")
            # Only the single most-recent observation counts toward the streak once
            # every prior link in the chain is unproven.
            self.assertEqual(1, result["current_consecutive_net_buy_sessions"])

    def test_streak_resets_across_an_unverifiable_registry_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = _write_registry(tmp, ["2026-09-18", "2026-09-21"])
            store.write_observations(tmp, "HPG", [_normalized("2026-09-18", buy=100, sell=40),
                                                   _normalized("2026-09-21", buy=100, sell=40)])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-21",
                                        qualified_session_registry_path=registry)
            self.assertEqual(1, result["current_consecutive_net_buy_sessions"])

    def test_current_2026_09_21_flow_stays_stale_with_only_2026_09_18_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = _write_registry(tmp, ["2026-09-18"])
            store.write_observations(tmp, "HPG", [_normalized("2026-09-18")])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-21",
                                        qualified_session_registry_path=registry)
            self.assertEqual("stale", result["freshness"]["status"])
            self.assertEqual("2026-09-18", result["freshness"]["latest_qualified_session_date"])
            self.assertNotEqual(result["freshness"]["reference_session_date"],
                                result["freshness"]["latest_qualified_session_date"])

    def test_cumulative_net_value_never_appears_unless_coverage_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = _write_registry(tmp, ["2026-09-18", "2026-09-21"])  # non-adjacent, unverifiable
            store.write_observations(tmp, "HPG", [_normalized("2026-09-18"), _normalized("2026-09-21")])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-21",
                                        qualified_session_registry_path=registry)
            for window in result["window_summaries"].values():
                if window["coverage"] != "complete":
                    self.assertIsNone(window["cumulative_net_value_vnd"])

    def test_no_pit_or_backtest_or_execution_authority_promoted_via_registry_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            registry = _write_registry(tmp, dates)
            store.write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=registry)
            self.assertFalse(result["is_actionable"])
            dumped = json.dumps(result).lower()
            for forbidden in ("historical_pit_authority", "backtest", "execution_authority"):
                self.assertNotIn(forbidden, dumped)

    def test_deterministic_across_repeated_calls_with_the_same_registry_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            registry = _write_registry(tmp, dates)
            store.write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            first = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                       qualified_session_registry_path=registry)
            second = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=registry)
            self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_malformed_registry_file_fails_closed_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            store.write_observations(tmp, "HPG", [_normalized(d) for d in dates])
            path = registry_path(tmp)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not valid json", encoding="utf-8")
            result = store.build_series(tmp, "HPG", reference_session_date="2026-09-18",
                                        qualified_session_registry_path=path)
            self.assertEqual("unverifiable", result["window_summaries"]["5_session"]["coverage"])

    def test_existing_exhaustive_vn_stock_db_behavior_is_unaffected_by_a_registry_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dates = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]
            _make_ohlcv(tmp, "HPG", dates)
            # Deliberately wrong/irrelevant registry -- exhaustive vn_stock.db must win.
            registry = _write_registry(tmp, ["2020-01-01"])
            store.write_observations(tmp, "HPG", [_normalized(d, buy=100, sell=40) for d in dates])
            result = store.build_series(tmp, "HPG", reference_session_date="2026-08-07",
                                        qualified_session_registry_path=registry)
            summary = result["window_summaries"]["5_session"]
            self.assertEqual("complete", summary["coverage"])
            self.assertEqual(store.AUTHORITY_SCOPE_EXHAUSTIVE, summary["continuity_reference"]["authority_scope"])
            self.assertEqual(5 * (100 - 40), summary["cumulative_net_value_vnd"])


if __name__ == "__main__":
    unittest.main()
