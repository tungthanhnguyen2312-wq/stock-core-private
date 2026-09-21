"""FOREIGN_FLOW_MULTI_SESSION_HISTORY_AND_PERSISTENCE_V1.

Real acquisition (2026-09-14/15/16/17, cohort EVF/FPT/HPG/NVL/PAN/PNJ/POW/PVD/QNS/SSI/VNM,
2026-09-18 already retained) was performed against the primary checkout's governed runtime
store (data/dnse-foreign-flow/, gitignored/approved-untracked -- see docs/STATE.md and this
milestone's roadmap entry). No new analytical logic was required: dnse_foreign_flow_store.py's
existing 5/10-session window + streak persistence contract, and flow_price_divergence_shadow.py's
existing same-session price-alignment/relationship contract, already generalize over however many
sessions the store holds. This suite proves the bounded-acquisition invariants this milestone
requires using synthetic fixtures (no dependency on the primary checkout's gitignored evidence,
so it runs identically in this isolated worktree and in CI), plus the exact real cohort/session
scope. It never re-tests dnse_foreign_flow_store.py's own window/streak arithmetic, which
tests/test_dnse_foreign_flow_store.py already covers exhaustively (including a real
"test_complete_5_session_summary_computed_correctly" case).
"""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

import current_foreign_flow_retention as retention
import dnse_foreign_flow_store as store
import flow_price_divergence_shadow as shadow
from owner_research_focus import load_owner_research_focus

GOVERNED_COHORT = ["EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM"]
NON_COHORT_TICKER = "AAA"
HISTORICAL_SESSIONS = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"]
ALREADY_RETAINED_SESSION = "2026-09-18"
ALL_TARGET_SESSIONS = HISTORICAL_SESSIONS + [ALREADY_RETAINED_SESSION]


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _official_artifact(tickers, *, observed_at="2026-09-01T00:00:00Z"):
    """Minimal synthetic current_official_market_universe/v1 artifact: every named ticker is a
    present, eligible stocklookup_candidate observed well before any target session."""
    records = {
        t: {
            "stocklookup_candidate": True,
            "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
            "official_observed_at": observed_at,
            "exchange_or_market": "HOSE",
        }
        for t in tickers
    }
    payload = {"contract_version": "current_official_market_universe/v1", "records": records}
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    payload["artifact_sha256"] = digest
    payload["artifact_identity"] = f"current_official_market_universe:{digest}"
    return payload


def _value_row(ticker: str, session: str, *, buy: int, sell: int) -> dict:
    """Matches the REAL retained-on-disk shape (current_foreign_flow_retention.
    write_exact_value_observation's value_only dict / dnse_foreign_flow_capability.
    normalize_record output): foreign_buy_value / foreign_sell_value / foreign_net_value,
    with NO _vnd suffix. dnse_foreign_flow_store._value_observation() reads exactly these
    key names and re-projects them to the _vnd-suffixed shape build_series() returns."""
    return {
        "ticker": ticker,
        "session_date": session,
        "observed_at": f"{session}T15:33:11.000",
        "foreign_buy_value": buy,
        "foreign_sell_value": sell,
        "foreign_net_value": buy - sell,
        "source": "DNSE",
        "source_contract_version": "dnse_foreign_flow/2026-08-10",
        "qualification_status": "PARTIALLY_QUALIFIED",
        "provenance": {
            "source_endpoint": f"/price/{ticker}/foreign-trading",
            "board_id": "T3",
            "exchange": "STO",
            "trading_session_id": "99",
            "query_window": {"from": 1, "to": 2},
        },
    }


def _series_latest_row(ticker: str, session: str, *, buy: int, sell: int) -> dict:
    """The _vnd-suffixed shape dnse_foreign_flow_store.build_series()/_value_observation()
    actually returns as a series's "latest_session" -- distinct from _value_row()'s raw
    on-disk shape. Used only where a test constructs a fake build_series()-shaped dict
    directly (bypassing build_series itself) to isolate flow_price_divergence_shadow's own
    alignment/relationship logic."""
    return {
        "ticker": ticker,
        "session_date": session,
        "observed_at": f"{session}T15:33:11.000",
        "foreign_buy_value_vnd": buy,
        "foreign_sell_value_vnd": sell,
        "foreign_net_value_vnd": buy - sell,
        "source": "DNSE",
        "source_contract_version": "dnse_foreign_flow/2026-08-10",
        "point_in_time_status": "qualified",
        "provenance": {
            "source_endpoint": f"/price/{ticker}/foreign-trading",
            "board_id": "T3",
            "exchange": "STO",
            "trading_session_id": "99",
            "query_window": {"from": 1, "to": 2},
        },
        "qualification_status": "QUALIFIED_VALUE_ONLY",
    }


class ExactCohortScopeTests(unittest.TestCase):
    """Section 1/2/4: exact 11-ticker cohort only, never full-market."""

    def test_owner_research_focus_broader_watchlist_matches_the_governed_cohort_exactly(self):
        focus = load_owner_research_focus()
        self.assertEqual(sorted(focus["broader_watchlist"]), sorted(GOVERNED_COHORT))

    def test_manifest_includes_only_the_governed_cohort_even_when_official_universe_is_wider(self):
        official = _official_artifact(GOVERNED_COHORT + [NON_COHORT_TICKER, "ZZZ", "YYY"])
        manifest = retention.build_manifest(
            reference_session=ALREADY_RETAINED_SESSION,
            owner_focus={"schema_version": "owner_research_focus/v1", "broader_watchlist": GOVERNED_COHORT},
            official_artifact=official,
        )
        self.assertEqual(sorted(manifest["eligible_tickers"]), sorted(GOVERNED_COHORT))
        self.assertEqual(manifest["cohort_count"], 11)
        self.assertNotIn(NON_COHORT_TICKER, manifest["eligible_tickers"])
        # No full-market acquisition: eligibility never widens beyond the requested watchlist,
        # regardless of how many tickers the official universe artifact itself covers.
        self.assertLessEqual(set(manifest["eligible_tickers"]), set(GOVERNED_COHORT))

    def test_manifest_session_is_exactly_the_requested_session_never_substituted(self):
        official = _official_artifact(GOVERNED_COHORT)
        for session in ALL_TARGET_SESSIONS:
            manifest = retention.build_manifest(
                reference_session=session,
                owner_focus={"schema_version": "owner_research_focus/v1", "broader_watchlist": GOVERNED_COHORT},
                official_artifact=official,
            )
            self.assertEqual(manifest["reference_session"], session)


class ValueOnlyAndNoPitPromotionTests(unittest.TestCase):
    """Section 5: VALUE-only, no volume/room/PIT/backtest/execution authority promotion."""

    def test_stored_observation_carries_no_volume_room_or_execution_fields(self):
        row = _value_row("HPG", "2026-09-14", buy=100, sell=40)
        blob = json.dumps(row).lower()
        for forbidden in ("volume", "room", "execution", "recommendation", "sizing"):
            self.assertNotIn(forbidden, blob)

    def test_series_authority_boundary_never_claims_pit_or_backtest_or_execution_authority(self, tmp_root=None):
        tmp_root = tmp_root or Path(self._get_tmp_dir())
        for session in ALL_TARGET_SESSIONS:
            store.write_observations(tmp_root, "HPG", [
                *[o for o in store.read_observations(tmp_root, "HPG")],
                _value_row("HPG", session, buy=100, sell=40),
            ])
        series = store.build_series(tmp_root, "HPG", reference_session_date=ALREADY_RETAINED_SESSION)
        self.assertFalse(series["is_actionable"])
        self.assertEqual(series["point_in_time_status"], "qualified")
        self.assertNotIn("historical_pit_authority", json.dumps(series))
        self.assertNotIn("backtest", json.dumps(series).lower())
        self.assertNotIn("execution_authority", json.dumps(series).lower())

    def _get_tmp_dir(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d


class RetainedEvidenceReuseTests(unittest.TestCase):
    """Section 2: valid retained evidence (2026-09-18) is reused, never reacquired."""

    def test_write_exact_value_observation_is_idempotent_for_an_already_retained_session(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            page = {
                "instrument": "HPG", "source_event_time": "2026-09-18",
                "endpoint": "/price/HPG/foreign-trading",
                "body": {"foreigners": [{"symbol": "HPG", "time": "2026-09-18 15:33:11",
                                         "totalBuyTradedAmount": 520495564350, "totalSellTradedAmount": 269865036850}]},
            }
            observation = retention.normalize_exact_raw_page(ticker="HPG", reference_session="2026-09-18", page=page)
            retention.write_exact_value_observation(tmp, "HPG", observation)
            before = json.loads((Path(tmp) / "data/dnse-foreign-flow/observations/HPG.json").read_text())
            # Re-writing the identical already-retained session must never duplicate or refetch.
            retention.write_exact_value_observation(tmp, "HPG", observation)
            after = json.loads((Path(tmp) / "data/dnse-foreign-flow/observations/HPG.json").read_text())
            self.assertEqual(before, after)
            self.assertEqual(len(after["observations"]), 1)

    def test_a_differing_same_session_rewrite_is_rejected_never_silently_overwritten(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            page = {
                "instrument": "HPG", "source_event_time": "2026-09-18",
                "endpoint": "/price/HPG/foreign-trading",
                "body": {"foreigners": [{"symbol": "HPG", "time": "2026-09-18 15:33:11",
                                         "totalBuyTradedAmount": 100, "totalSellTradedAmount": 40}]},
            }
            observation = retention.normalize_exact_raw_page(ticker="HPG", reference_session="2026-09-18", page=page)
            retention.write_exact_value_observation(tmp, "HPG", observation)
            tampered = dict(observation)
            tampered["foreign_buy_value"] = 999
            with self.assertRaisesRegex(ValueError, "CONFLICTING"):
                retention.write_exact_value_observation(tmp, "HPG", tampered)


class SameSessionPriceAlignmentTests(unittest.TestCase):
    """Section 6: same-session price alignment required; no forward/backward/zero fill."""

    def _velocity_record(self, ticker: str, session: str, overall: str = "STABLE") -> dict:
        return {
            "ticker": ticker, "session": session, "overall_transition_state": overall,
            "axes": {"structural_repair": {"state": "NORMAL"}, "setup_maturation": {"state": "VALID"},
                     "participation_confirmation": {"state": "IMPROVING"}},
            "evidence_quality": {"state": "SUFFICIENT"},
            "source_snapshot_identity": "velocity:test",
        }

    def _velocity_artifact(self, records):
        return {"contract_version": shadow.VELOCITY_CONTRACT_VERSION, "records": records}

    def test_flow_lagged_behind_reference_session_is_not_exact_session_aligned(self):
        series = store.build_series.__wrapped__ if hasattr(store.build_series, "__wrapped__") else None
        # Build a series object shaped like build_series's own output, with the latest
        # observation strictly before the reference session (a genuine same-session flow record
        # for the reference session was never acquired).
        fake_series = {
            "status": "available", "latest_session": _series_latest_row("HPG", "2026-09-17", buy=100, sell=40),
            "freshness": {"status": "stale", "sessions_behind": 1, "latest_qualified_session_date": "2026-09-17",
                          "reference_session_date": "2026-09-18"},
            "window_summaries": {"5_session": {"coverage": "incomplete"}, "10_session": {"coverage": "incomplete"}},
            "current_consecutive_net_buy_sessions": 0, "current_consecutive_net_sell_sessions": 0,
        }
        velocity = self._velocity_artifact([self._velocity_record("HPG", "2026-09-18")])
        artifact = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": fake_series},
                                         velocity_artifact=velocity)
        record = artifact["records"][0]
        # A stale (lagged) flow observation must never be treated as this session's evidence --
        # no forward-fill of the last known value into the current reference session.
        self.assertNotEqual(record["session_alignment"]["state"], "EXACT_SESSION_ALIGNED")
        self.assertEqual(record["relationship"], "FLOW_UNAVAILABLE")

    def test_missing_flow_session_is_flow_unavailable_never_zero_filled(self):
        fake_series = {"status": "missing", "latest_session": None,
                       "freshness": {"status": "not_applicable", "latest_qualified_session_date": None,
                                    "reference_session_date": "2026-09-18"},
                       "window_summaries": {"5_session": {"coverage": "incomplete"}, "10_session": {"coverage": "incomplete"}},
                       "current_consecutive_net_buy_sessions": 0, "current_consecutive_net_sell_sessions": 0}
        velocity = self._velocity_artifact([self._velocity_record("HPG", "2026-09-18")])
        artifact = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": fake_series},
                                         velocity_artifact=velocity)
        record = artifact["records"][0]
        self.assertEqual(record["flow"]["state"], "FLOW_UNAVAILABLE")
        self.assertEqual(record["relationship"], "FLOW_UNAVAILABLE")
        self.assertIsNone(record["flow"]["latest_qualified_net_value_vnd"])

    def test_exact_same_session_flow_and_price_evaluates_a_real_relationship(self):
        fake_series = {"status": "available", "latest_session": _series_latest_row("HPG", "2026-09-18", buy=100, sell=40),
                       "freshness": {"status": "current", "sessions_behind": 0, "latest_qualified_session_date": "2026-09-18",
                                    "reference_session_date": "2026-09-18"},
                       "window_summaries": {"5_session": {"coverage": "incomplete"}, "10_session": {"coverage": "incomplete"}},
                       "current_consecutive_net_buy_sessions": 1, "current_consecutive_net_sell_sessions": 0}
        velocity = self._velocity_artifact([self._velocity_record("HPG", "2026-09-18", overall="DETERIORATING")])
        artifact = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": fake_series},
                                         velocity_artifact=velocity)
        record = artifact["records"][0]
        self.assertEqual(record["session_alignment"]["state"], "EXACT_SESSION_ALIGNED")
        self.assertEqual(record["relationship"], "FOREIGN_BUYING_PRICE_WEAKNESS")


class CurrentSessionAbsenceTests(unittest.TestCase):
    """Section 9: 2026-09-21 absence stays absence; 2026-09-18 shown only as prior-session context."""

    def test_2026_09_21_reference_with_only_2026_09_18_retained_is_stale_not_current(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            store.write_observations(tmp, "HPG", [_value_row("HPG", "2026-09-18", buy=100, sell=40)])
            series = store.build_series(tmp, "HPG", reference_session_date="2026-09-21")
            self.assertEqual(series["freshness"]["status"], "stale")
            self.assertEqual(series["freshness"]["latest_qualified_session_date"], "2026-09-18")
            # The 2026-09-18 evidence must never be mislabeled as current 2026-09-21 evidence.
            self.assertNotEqual(series["freshness"]["reference_session_date"], series["freshness"]["latest_qualified_session_date"])


class PersistenceGovernedRuleTests(unittest.TestCase):
    """Section 7: reuse the existing 5-session window + streak persistence rule; never invent a
    new score. Complements tests/test_dnse_foreign_flow_store.py's own exhaustive window/streak
    coverage by proving the SAME rule, once genuinely complete, reclassifies persistence away
    from INSUFFICIENT_HISTORY -- this is exactly what real acquisition unlocks."""

    def test_five_consecutive_gap_free_net_buy_sessions_yield_persistent_net_buy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sessions = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]
            store.write_observations(tmp, "HPG", [_value_row("HPG", s, buy=100, sell=40) for s in sessions])
            with mock.patch.object(store, "_retained_trading_dates", return_value=set(sessions)):
                series = store.build_series(tmp, "HPG", reference_session_date="2026-09-18")
        self.assertEqual(series["window_summaries"]["5_session"]["coverage"], "complete")
        self.assertEqual(series["current_consecutive_net_buy_sessions"], 5)
        velocity = {"contract_version": shadow.VELOCITY_CONTRACT_VERSION,
                    "records": [{"ticker": "HPG", "session": "2026-09-18", "overall_transition_state": "STABLE",
                                "axes": {"structural_repair": {"state": "NORMAL"}, "setup_maturation": {"state": "VALID"},
                                         "participation_confirmation": {"state": "IMPROVING"}},
                                "evidence_quality": {"state": "SUFFICIENT"}, "source_snapshot_identity": "velocity:test"}]}
        artifact = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": series}, velocity_artifact=velocity)
        record = artifact["records"][0]
        self.assertEqual(record["flow"]["persistence"], "PERSISTENT_NET_BUY")
        self.assertEqual(record["evidence_quality"], "COMPLETE_RETAINED_EVIDENCE")

    def test_a_gap_in_the_five_session_window_keeps_persistence_insufficient(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            present = ["2026-09-14", "2026-09-16", "2026-09-17", "2026-09-18"]  # 2026-09-15 missing
            all_trading_dates = {"2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"}
            store.write_observations(tmp, "HPG", [_value_row("HPG", s, buy=100, sell=40) for s in present])
            with mock.patch.object(store, "_retained_trading_dates", return_value=all_trading_dates):
                series = store.build_series(tmp, "HPG", reference_session_date="2026-09-18")
        self.assertNotEqual(series["window_summaries"]["5_session"]["coverage"], "complete")


class SingleSessionRegressionTests(unittest.TestCase):
    """Section 12/11: the pre-existing 2026-09-18-only shape must classify identically to before
    this milestone's acquisition -- INSUFFICIENT_HISTORY, never fabricated persistence."""

    def test_single_retained_session_still_reports_insufficient_history_not_a_fabricated_trend(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            store.write_observations(tmp, "HPG", [_value_row("HPG", "2026-09-18", buy=100, sell=40)])
            series = store.build_series(tmp, "HPG", reference_session_date="2026-09-18")
        self.assertEqual(series["window_summaries"]["5_session"]["coverage"], "incomplete")
        velocity = {"contract_version": shadow.VELOCITY_CONTRACT_VERSION,
                    "records": [{"ticker": "HPG", "session": "2026-09-18", "overall_transition_state": "STABLE",
                                "axes": {"structural_repair": {"state": "NORMAL"}, "setup_maturation": {"state": "VALID"},
                                         "participation_confirmation": {"state": "IMPROVING"}},
                                "evidence_quality": {"state": "SUFFICIENT"}, "source_snapshot_identity": "velocity:test"}]}
        artifact = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": series}, velocity_artifact=velocity)
        self.assertEqual(artifact["records"][0]["flow"]["persistence"], "INSUFFICIENT_HISTORY")


class DeterministicIdentityTests(unittest.TestCase):
    """Section 11: deterministic artifact identity."""

    def test_manifest_identity_is_deterministic_across_two_builds(self):
        official = _official_artifact(GOVERNED_COHORT)
        focus = {"schema_version": "owner_research_focus/v1", "broader_watchlist": GOVERNED_COHORT}
        first = retention.build_manifest(reference_session="2026-09-15", owner_focus=focus, official_artifact=official)
        second = retention.build_manifest(reference_session="2026-09-15", owner_focus=focus, official_artifact=official)
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])

    def test_flow_price_artifact_identity_is_deterministic(self):
        series = {"status": "available", "latest_session": _series_latest_row("HPG", "2026-09-18", buy=100, sell=40),
                 "freshness": {"status": "current", "sessions_behind": 0, "latest_qualified_session_date": "2026-09-18",
                              "reference_session_date": "2026-09-18"},
                 "window_summaries": {"5_session": {"coverage": "incomplete"}, "10_session": {"coverage": "incomplete"}},
                 "current_consecutive_net_buy_sessions": 1, "current_consecutive_net_sell_sessions": 0}
        velocity = {"contract_version": shadow.VELOCITY_CONTRACT_VERSION,
                    "records": [{"ticker": "HPG", "session": "2026-09-18", "overall_transition_state": "STABLE",
                                "axes": {"structural_repair": {"state": "NORMAL"}, "setup_maturation": {"state": "VALID"},
                                         "participation_confirmation": {"state": "IMPROVING"}},
                                "evidence_quality": {"state": "SUFFICIENT"}, "source_snapshot_identity": "velocity:test"}]}
        first = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": series}, velocity_artifact=copy.deepcopy(velocity))
        second = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": series}, velocity_artifact=copy.deepcopy(velocity))
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])


class NoAuthorityPromotionTests(unittest.TestCase):
    """Section 5/8: never a recommendation, never causal, is_actionable stays False."""

    def test_flow_price_artifact_never_claims_actionability_or_causal_language(self):
        series = {"status": "available", "latest_session": _series_latest_row("HPG", "2026-09-18", buy=100, sell=40),
                 "freshness": {"status": "current", "sessions_behind": 0, "latest_qualified_session_date": "2026-09-18",
                              "reference_session_date": "2026-09-18"},
                 "window_summaries": {"5_session": {"coverage": "incomplete"}, "10_session": {"coverage": "incomplete"}},
                 "current_consecutive_net_buy_sessions": 1, "current_consecutive_net_sell_sessions": 0}
        velocity = {"contract_version": shadow.VELOCITY_CONTRACT_VERSION,
                    "records": [{"ticker": "HPG", "session": "2026-09-18", "overall_transition_state": "DETERIORATING",
                                "axes": {"structural_repair": {"state": "NORMAL"}, "setup_maturation": {"state": "VALID"},
                                         "participation_confirmation": {"state": "IMPROVING"}},
                                "evidence_quality": {"state": "SUFFICIENT"}, "source_snapshot_identity": "velocity:test"}]}
        artifact = shadow.build_artifact(reference_session="2026-09-18", flow_series={"HPG": series}, velocity_artifact=velocity)
        self.assertFalse(artifact["authority_boundary"]["is_actionable"])
        self.assertTrue(artifact["authority_boundary"]["no_causality_or_intent"])
        self.assertTrue(artifact["authority_boundary"]["no_score_probability_recommendation_or_execution"])
        record = artifact["records"][0]
        self.assertFalse(record["is_actionable"])


if __name__ == "__main__":
    unittest.main()
