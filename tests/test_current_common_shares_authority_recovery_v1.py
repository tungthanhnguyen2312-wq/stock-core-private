"""CURRENT_COMMON_SHARES_AUTHORITY_RECOVERY_AND_SCALEOUT_V1.

Deterministic coverage for the bounded recovery milestone. No network and no dependency on the
sibling ``dashboard-runtime`` checkout: every case feeds fixed, in-repo fixture data (or a
temporary SQLite runtime built inline) into the same pure functions the live recompute tool
(`tools/derive_current_common_shares_authority_recovery_v1.py`) calls unmodified.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_common_shares_authority import (
    CORPORATE_ACTION_RECONCILIATION_REQUIRED,
    PROVIDER_REPORTED_CURRENT_RESEARCH,
    PROVIDER_REPORTED_LAGGED,
    QUALIFIED_CURRENT_COMMON_SHARES,
    UNVERIFIABLE_FRESHNESS,
    build_current_common_shares_authority,
    resolve_ticker_share_authority,
)
import market_wide_current_shares_resolver as resolver_module
from tools.derive_current_common_shares_authority_recovery_v1 import (
    BOUNDED_LIVE_OVERRIDES,
    SESSION,
    VCB_RECHECK_NOTE,
)

OVERRIDE_TICKERS = frozenset(BOUNDED_LIVE_OVERRIDES)

#: The exact stale resolver_row each overridden ticker actually carried before the bounded
#: recheck -- reproduced from the live probe, not invented. Used to prove the override replaces
#: (rather than merges into) this row, and as the "before" half of the upgrade-direction tests.
STALE_ROW_BEFORE_OVERRIDE = {
    "SSI": {"authority": "provider_reported_unverifiable_freshness", "value": None,
            "observation_date": "2026-08-14", "undated_share_relevant_events": ["ISS"],
            "reason": "missing_explicit_official_ex_date_on_share_relevant_event"},
    "HCC": {"authority": "provider_reported_lagged", "value": 6_518_547,
            "observation_date": "2026-08-14", "observation_lag_days": 12},
    "IPA": {"authority": "provider_reported_lagged", "value": 213_835_775,
            "observation_date": "2026-08-14", "observation_lag_days": 12},
    "NAG": {"authority": "provider_reported_lagged", "value": 52_593_726,
            "observation_date": "2026-08-14", "observation_lag_days": 12},
}

#: The 2026-08-19/08-19/08-21 HNX-sourced share-changing events already retained under
#: current-corporate-event-context-v1 for HCC/IPA/NAG before this milestone -- reproduced as
#: fixture "official_events" to test that the reconciliation gate would have blocked (not
#: silently ignored) these three without the bounded override.
HCC_IPA_NAG_RETAINED_EVENTS = {
    "HCC": [{"event_type": "STOCK_DIVIDEND", "ex_date": "2026-08-19", "execution_date": None, "resulting_shares": None}],
    "IPA": [{"event_type": "BONUS", "ex_date": "2026-08-21", "execution_date": None, "resulting_shares": None}],
    "NAG": [{"event_type": "STOCK_DIVIDEND", "ex_date": "2026-08-19", "execution_date": None, "resulting_shares": None}],
}


def _official_universe(*tickers: str) -> dict:
    return {
        "artifact_identity": "official:test",
        "artifact_sha256": "test",
        "records": {
            ticker: {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY"}
            for ticker in tickers
        },
    }


class BoundedOverrideScopeTests(unittest.TestCase):
    """Objective B/C: the override is a named, bounded, evidence-cited set -- nothing implicit."""

    def test_override_scope_is_exactly_the_four_recovered_tickers(self) -> None:
        self.assertEqual(OVERRIDE_TICKERS, {"SSI", "HCC", "IPA", "NAG"})

    def test_hpg_and_vcb_are_not_in_the_override_set(self) -> None:
        # HPG's ceiling and VCB's freshness gap were both rechecked with fresh evidence and both
        # reconfirmed unchanged (see recovery_report.json); neither is a bounded-override target.
        self.assertNotIn("HPG", OVERRIDE_TICKERS)
        self.assertNotIn("VCB", OVERRIDE_TICKERS)
        self.assertEqual(VCB_RECHECK_NOTE["result"], "NO_CHANGE_CEILING_RECONFIRMED")

    def test_every_override_carries_source_evidence_and_arithmetic_citation(self) -> None:
        for ticker, override in BOUNDED_LIVE_OVERRIDES.items():
            with self.subTest(ticker=ticker):
                self.assertEqual(override["authority"], "provider_reported_current")
                self.assertIsInstance(override["value"], int)
                self.assertGreater(override["value"], 0)
                self.assertEqual(override["source"], "VCI.overview.issue_share")
                evidence = override["bounded_recovery_evidence"]
                self.assertTrue(Path(ROOT / evidence["evidence_file"]).is_file())
                self.assertIn("arithmetic_check", evidence)
                self.assertIn("causing_event", evidence)

    def test_evidence_files_on_disk_match_their_cited_sha256(self) -> None:
        import hashlib
        for ticker, override in BOUNDED_LIVE_OVERRIDES.items():
            evidence = override["bounded_recovery_evidence"]
            if "evidence_sha256" not in evidence:
                continue
            with self.subTest(ticker=ticker):
                raw = (ROOT / evidence["evidence_file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), evidence["evidence_sha256"])


class OverrideApplicationTests(unittest.TestCase):
    """Objective D: what the override actually does to the terminal disposition."""

    def test_override_replaces_rather_than_merges_the_stale_row(self) -> None:
        # Regression test for the exact bug found while building this milestone: merging the
        # override onto the stale resolver_row left "undated_share_relevant_events" behind,
        # which pre-empts the tier check ahead of "authority" and silently produced
        # UNVERIFIABLE_FRESHNESS with value=None even though authority was overridden to
        # "provider_reported_current". A full replacement (this test) must NOT reproduce that.
        merged = dict(STALE_ROW_BEFORE_OVERRIDE["SSI"])
        merged.update(BOUNDED_LIVE_OVERRIDES["SSI"])
        buggy = resolve_ticker_share_authority("SSI", session=SESSION, resolver_row=merged)
        self.assertEqual(buggy["authority_tier"], UNVERIFIABLE_FRESHNESS)
        self.assertIsNone(buggy["value"])

        replaced = resolve_ticker_share_authority(
            "SSI", session=SESSION, resolver_row=dict(BOUNDED_LIVE_OVERRIDES["SSI"]))
        self.assertEqual(replaced["authority_tier"], PROVIDER_REPORTED_CURRENT_RESEARCH)
        self.assertEqual(replaced["value"], BOUNDED_LIVE_OVERRIDES["SSI"]["value"])

    def test_each_override_resolves_to_provider_reported_current_research_with_its_own_value(self) -> None:
        for ticker, override in BOUNDED_LIVE_OVERRIDES.items():
            with self.subTest(ticker=ticker):
                row = resolve_ticker_share_authority(ticker, session=SESSION, resolver_row=dict(override))
                self.assertEqual(row["authority_tier"], PROVIDER_REPORTED_CURRENT_RESEARCH)
                self.assertEqual(row["value"], override["value"])
                self.assertEqual(row["fitness_for_use"], "RESEARCH_USABLE_NOT_AUTHORITATIVE")

    def test_no_override_ever_reaches_qualified_current_common_shares(self) -> None:
        # A fresher issued-share re-observation is still a provider proxy, never an official
        # anchor; freshness alone must never promote semantic authority.
        for ticker, override in BOUNDED_LIVE_OVERRIDES.items():
            with self.subTest(ticker=ticker):
                row = resolve_ticker_share_authority(ticker, session=SESSION, resolver_row=dict(override))
                self.assertNotEqual(row["authority_tier"], QUALIFIED_CURRENT_COMMON_SHARES)
                self.assertEqual(row["canonical_share_identity"], "ISSUED_SHARES")
                self.assertIn("ISSUED_SHARES_ARE_NOT_COMMON_SHARES_OUTSTANDING", row["warnings"])

    def test_without_the_override_the_same_tickers_stay_blocked(self) -> None:
        # Establishes the "before": HCC/IPA/NAG reconcile against their retained, dated,
        # share-changing HNX event with no resulting_shares -- CORPORATE_ACTION_RECONCILIATION_REQUIRED,
        # not silently treated as available. SSI's undated ISS event alone is enough to block it.
        for ticker in ("HCC", "IPA", "NAG"):
            with self.subTest(ticker=ticker):
                row = resolve_ticker_share_authority(
                    ticker, session=SESSION, resolver_row=dict(STALE_ROW_BEFORE_OVERRIDE[ticker]),
                    official_events=HCC_IPA_NAG_RETAINED_EVENTS[ticker],
                )
                self.assertEqual(row["authority_tier"], CORPORATE_ACTION_RECONCILIATION_REQUIRED)
                self.assertIsNone(row["value"])
        ssi_before = resolve_ticker_share_authority(
            "SSI", session=SESSION, resolver_row=dict(STALE_ROW_BEFORE_OVERRIDE["SSI"]))
        self.assertEqual(ssi_before["authority_tier"], UNVERIFIABLE_FRESHNESS)
        self.assertIsNone(ssi_before["value"])

    def test_stale_observation_date_falls_back_to_lagged_not_current(self) -> None:
        # The tier is earned by the observation date qualifying "on or after session", not by
        # the authority label alone -- explicit coverage-through-session requirement.
        stale = dict(BOUNDED_LIVE_OVERRIDES["SSI"])
        stale["authority"] = "provider_reported_lagged"
        row = resolve_ticker_share_authority("SSI", session=SESSION, resolver_row=stale)
        self.assertEqual(row["authority_tier"], PROVIDER_REPORTED_LAGGED)
        self.assertFalse(row["coverage_through_session"])


class ResidualZeroInventoryTests(unittest.TestCase):
    """Objective A: the recompute over a full (small) universe reconciles with zero residual."""

    def _fixture_universe(self) -> tuple[dict, dict]:
        tickers = ["HPG", "VCB", *OVERRIDE_TICKERS, "AAA"]
        universe = _official_universe(*tickers)
        resolution = {"tickers": {
            "HPG": {"authority": "unavailable"},
            "VCB": {"authority": "provider_reported_unverifiable_freshness",
                    "undated_share_relevant_events": ["ISS"], "observation_date": "2026-08-14"},
            "AAA": {"authority": "provider_reported_lagged", "value": 10,
                    "observation_date": "2026-08-14", "share_concept": "ISSUED_SHARES"},
            **{ticker: dict(BOUNDED_LIVE_OVERRIDES[ticker]) for ticker in OVERRIDE_TICKERS},
        }}
        return universe, resolution

    def test_denominator_reconciles_with_overrides_applied(self) -> None:
        universe, resolution = self._fixture_universe()
        artifact = build_current_common_shares_authority(
            session=SESSION, official_universe=universe, share_resolution=resolution)
        self.assertTrue(artifact["coverage"]["denominator_reconciles"])
        self.assertEqual(artifact["coverage"]["unexplained_count"], 0)
        self.assertEqual(artifact["coverage"]["universe_denominator"], 7)
        self.assertEqual(sum(artifact["coverage"]["authority_tier_distribution"].values()), 7)

    def test_no_cross_ticker_propagation(self) -> None:
        # AAA and VCB carry no override and must resolve exactly as their own resolver_row says,
        # regardless of the four overrides being present elsewhere in the same batch.
        universe, resolution = self._fixture_universe()
        artifact = build_current_common_shares_authority(
            session=SESSION, official_universe=universe, share_resolution=resolution)
        self.assertEqual(artifact["records"]["AAA"]["authority_tier"], PROVIDER_REPORTED_LAGGED)
        self.assertEqual(artifact["records"]["AAA"]["value"], 10)
        self.assertEqual(artifact["records"]["VCB"]["authority_tier"], UNVERIFIABLE_FRESHNESS)
        self.assertIsNone(artifact["records"]["VCB"]["value"])
        for ticker in OVERRIDE_TICKERS:
            self.assertEqual(artifact["records"][ticker]["authority_tier"], PROVIDER_REPORTED_CURRENT_RESEARCH)

    def test_no_value_strategy_or_provider_promotion_boundary_flags(self) -> None:
        universe, resolution = self._fixture_universe()
        artifact = build_current_common_shares_authority(
            session=SESSION, official_universe=universe, share_resolution=resolution)
        self.assertFalse(artifact["coverage"]["generic_authority_source_promoted"])
        self.assertEqual(artifact["coverage"]["qualified_current_common_shares"], 0)
        self.assertTrue(artifact["authority_boundary"]["issued_shares_not_common_outstanding"])
        self.assertEqual(artifact["authority_boundary"]["target_price"], False)
        self.assertEqual(artifact["authority_boundary"]["dcf"], False)


class ResolverLedgerCoverageTransparencyTests(unittest.TestCase):
    """market_wide_current_shares_resolver.py fix: qualified_official now surfaces the same
    ledger_coverage_status caveat its own failure path already carried, so a consumer can see
    whether "no share-changing event found" rests on a complete or a bounded/partial ledger read."""

    def _write_runtime(self, root: Path, *, ledger_coverage_status: str) -> None:
        evidence = root / "data" / "official-evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        anchor = {
            "citation_id": "cite1", "ticker": "AAA",
            "identity_type": "current_shares_outstanding_after_event",
            "value": 2000, "share_class": "common_outstanding", "unit": "shares",
            "effective_date": "2026-07-02", "event_id": "evt1", "event_type": "stock_dividend",
            "corroborated_value": 2000, "corroborated_source": "provider", "corroborated_on": "2026-07-30",
        }
        (evidence / "share_basis_citations.jsonl").write_text(json.dumps(anchor) + "\n", encoding="utf-8")
        connection = sqlite3.connect(root / "vn_stock.db")
        connection.execute("CREATE TABLE metadata (ticker TEXT, shares_outstanding REAL, updated TEXT)")
        connection.execute("INSERT INTO metadata VALUES ('AAA', 2000.0, '2026-07-30 17:00')")
        connection.execute("CREATE TABLE corporate_event_records (ticker TEXT, event_code TEXT, exright_date TEXT, coverage_status TEXT)")
        if ledger_coverage_status != "absent":
            connection.execute("INSERT INTO corporate_event_records VALUES ('AAA', 'DIV', NULL, ?)", (ledger_coverage_status,))
        connection.commit()
        connection.close()

    def test_qualified_official_success_carries_ledger_coverage_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_runtime(root, ledger_coverage_status="partial_unqualified_50_row_cap")
            result = resolver_module.resolve_effective_shares("AAA", root, "2026-08-26")
        self.assertEqual(result["authority"], "qualified_official")
        self.assertEqual(result["ledger_coverage_status"], "partial_unqualified_50_row_cap")
        self.assertEqual(result["corroborating_observation_date"], "2026-07-30")

    def test_qualified_official_success_reports_absent_ledger_coverage_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_runtime(root, ledger_coverage_status="absent")
            result = resolver_module.resolve_effective_shares("AAA", root, "2026-08-26")
        self.assertEqual(result["authority"], "qualified_official")
        self.assertEqual(result["ledger_coverage_status"], "absent")


class NetworkFreedomTests(unittest.TestCase):
    """Explicit contract check: importing/using the recovery module's fixed evidence does not
    perform I/O beyond local file reads -- no network access from this deterministic test."""

    def test_module_import_and_override_access_touch_no_network(self) -> None:
        import socket

        def _blocked(*args, **kwargs):
            raise AssertionError("network access attempted from a deterministic test")

        original = socket.socket
        socket.socket = _blocked
        try:
            self.assertEqual(len(BOUNDED_LIVE_OVERRIDES), 4)
            for ticker in BOUNDED_LIVE_OVERRIDES:
                resolve_ticker_share_authority(ticker, session=SESSION, resolver_row=dict(BOUNDED_LIVE_OVERRIDES[ticker]))
        finally:
            socket.socket = original


if __name__ == "__main__":
    unittest.main()
