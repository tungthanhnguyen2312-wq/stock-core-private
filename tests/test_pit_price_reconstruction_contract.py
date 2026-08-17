# ==========================================================================
# Tests for pit_price_reconstruction_contract.py -- P0-A.3A.
#
# The module under test is a pure classifier: no I/O, no clock, no network. Every dependency
# (corporate-action observations, price-basis authorities, a candidate raw observation) is
# supplied by the caller, so every test here is a plain synchronous unit test. The two
# real-evidence classes at the bottom exercise the same retained HPG/SSI documents already
# used by tests/test_official_corporate_action_pillar.py, and skip (not fail) if that retained
# evidence is ever absent.
#
# Run: `python -m unittest tests.test_pit_price_reconstruction_contract`
# ==========================================================================

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import corporate_action_events as events  # noqa: E402
import official_corporate_action_ledger as ledger  # noqa: E402
import official_document_store as document_store  # noqa: E402
import pit_price_reconstruction_contract as contract  # noqa: E402


def _synthetic_authority(ticker: str, *, effective_from: str, effective_to: str,
                         price_basis: str = "ADJUSTED_RETROSPECTIVE") -> dict:
    """A hypothetical bounded price-basis authority, shaped like
    provider_price_basis_registry.active_bounded_authorities()'s own records, for a ticker with
    no real evidence -- used only to prove the QUALIFIED code path is reachable, never to imply
    any real ticker has this authority."""
    return {
        "authority_id": f"DNSE:ohlc_1D:{ticker}:SYN:{effective_from}",
        "provider": "DNSE", "dataset": "ohlc_1D", "dataset_aliases": ("ohlc", "ohlc_1d"),
        "instrument": ticker, "effective_from": effective_from, "effective_to": effective_to,
        "price_basis": price_basis,
    }


def _synthetic_raw_observation(ticker: str, *, retrieved_at: str, provider: str = "DNSE",
                               dataset: str = "ohlc_1D", **overrides) -> dict:
    """A well-formed observation carrying every identity field
    market_data_contracts.RawObservation requires -- used only under a synthetic RAW_AS_TRADED
    authority to prove the PIT_AS_KNOWN QUALIFIED path is reachable in principle. No real
    ticker in this repository has this authority today."""
    record = {
        "provider": provider, "dataset": dataset, "instrument": ticker,
        "retrieved_at": retrieved_at, "request_identity": f"req-{ticker.lower()}",
        "raw_payload_hash": "e" * 64, "schema_version": "1.0.0",
    }
    record.update(overrides)
    return record


def _synthetic_share_event(ticker: str, *, event_type: str = "stock_dividend",
                           observed_at: str = "2026-01-05T00:00:00Z", published_at: str = "2026-01-01",
                           ex_date: str | None = "2026-02-01", stock_ratio: float | None = 0.1,
                           shares_before: int = 100_000_000, shares_issued: int = 10_000_000,
                           **overrides) -> dict:
    """A hand-built observation shaped like corporate_action_events.extract_event_observation()'s
    own output -- never derived from a real document. Used only to prove that a fully qualified,
    ex-dated share event CAN reach the ledger's FACTOR_READY state and this contract's QUALIFIED
    corporate-action state; no real ticker in this repository has this evidence today."""
    record = {
        "schema_version": events.SCHEMA_VERSION, "ticker": ticker, "event_type": event_type,
        "lifecycle_state": "executed", "document_id": f"syn-doc-{ticker.lower()}",
        "content_sha256": "b" * 64, "observation_id": f"syn-obs-{ticker.lower()}-{event_type}",
        "observed_at": observed_at, "published_at": published_at,
        "ex_date": ex_date, "record_date": "2026-01-20",
        "shares_before": shares_before, "shares_issued": shares_issued,
        "shares_after": shares_before + shares_issued,
        "stock_ratio": stock_ratio, "ratio_basis": "new_shares_per_existing_share",
        "cash_amount_per_share": None, "warnings": [], "absent_fields": {},
    }
    record.update(overrides)
    return record


def _synthetic_cash_event(ticker: str, *, observed_at: str = "2026-01-05T00:00:00Z",
                          published_at: str = "2026-01-01", ex_date: str | None = None,
                          cash_amount_per_share: float | None = 1000.0, **overrides) -> dict:
    record = {
        "schema_version": events.SCHEMA_VERSION, "ticker": ticker, "event_type": "cash_dividend",
        "lifecycle_state": "record_date_confirmed", "document_id": f"syn-cash-doc-{ticker.lower()}",
        "content_sha256": "c" * 64, "observation_id": f"syn-cash-obs-{ticker.lower()}",
        "observed_at": observed_at, "published_at": published_at,
        "ex_date": ex_date, "record_date": "2026-01-20",
        "shares_before": None, "shares_issued": None, "shares_after": None,
        "stock_ratio": None, "cash_amount_per_share": cash_amount_per_share,
        "warnings": [], "absent_fields": {},
    }
    record.update(overrides)
    return record


# ==========================================================================
# Vocabulary and helper-level tests
# ==========================================================================

class ContractVocabularyTests(unittest.TestCase):
    def test_view_modes_are_exactly_the_two_required(self):
        self.assertEqual(contract.VIEW_MODES, {"PIT_AS_KNOWN", "RETROSPECTIVE_RESTATED"})

    def test_verdict_states_include_all_five_recommended_states(self):
        self.assertEqual(contract.VERDICT_STATES,
                         {"QUALIFIED", "PARTIAL", "UNKNOWN", "BLOCKED", "NOT_APPLICABLE"})

    def test_reason_codes_are_nonempty_and_all_strings(self):
        self.assertGreater(len(contract.REASON_CODES), 10)
        self.assertTrue(all(isinstance(code, str) and code for code in contract.REASON_CODES))

    def test_contract_summary_is_deterministic_and_self_describing(self):
        first = contract.contract_summary()
        second = contract.contract_summary()
        self.assertEqual(first, second)
        self.assertEqual(set(first["view_modes"]), contract.VIEW_MODES)


class TemporalHelperTests(unittest.TestCase):
    def test_bare_date_knowledge_cutoff_is_read_as_end_of_day(self):
        # Same-day evidence timestamped at 23:00 must be knowable by a bare-date cutoff of the
        # same day -- the "as of this date" reading, not "as of midnight this date".
        self.assertTrue(contract._instant_le("2026-08-02T23:00:00Z", "2026-08-02"))

    def test_full_timestamp_after_bare_date_cutoff_is_excluded(self):
        self.assertFalse(contract._instant_le("2026-08-03T00:00:01Z", "2026-08-02"))

    def test_naive_timestamp_is_assumed_utc_not_rejected(self):
        self.assertTrue(contract._instant_le("2026-08-02T08:10:00", "2026-08-02T08:10:00Z"))

    def test_unparseable_values_return_none_not_a_guess(self):
        self.assertIsNone(contract._instant_le("not-a-timestamp", "2026-08-02"))
        self.assertIsNone(contract._instant_le("2026-08-02", "not-a-timestamp"))
        self.assertIsNone(contract._instant_le(None, "2026-08-02"))

    def test_evidence_knowledge_time_reads_observed_at_only(self):
        obs = {"observed_at": "2026-08-02T08:10:00Z", "published_at": "2026-07-07"}
        self.assertEqual(contract.evidence_knowledge_time(obs), "2026-08-02T08:10:00Z")

    def test_evidence_knowledge_time_ignores_absent_observed_at(self):
        self.assertIsNone(contract.evidence_knowledge_time({"published_at": "2026-07-07"}))

    def test_normalized_date_rejects_malformed_value(self):
        self.assertIsNone(contract._normalized_date("not-a-date"))
        self.assertIsNone(contract._normalized_date(None))


# ==========================================================================
# Stage 1: ticker/instrument scope
# ==========================================================================

class TickerScopeTests(unittest.TestCase):
    def test_non_equity_instrument_class_is_not_applicable(self):
        for instrument_class in ("WARRANT", "BOND", "ETF", "DERIVATIVE", "INDEX"):
            verdict = contract.classify_price_reconstruction(
                ticker="ZZZ", session="2026-06-01", knowledge_cutoff="2026-08-17",
                mode=contract.MODE_PIT_AS_KNOWN, instrument_class=instrument_class)
            self.assertEqual(verdict["verdict"], contract.NOT_APPLICABLE, instrument_class)
            self.assertEqual(verdict["reason"], contract.REASON_OUT_OF_EQUITY_SCOPE)

    def test_permanent_provider_invalid_is_blocked(self):
        verdict = contract.classify_price_reconstruction(
            ticker="ZZZ", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, acquisition_status="PERMANENT")
        self.assertEqual(verdict["verdict"], contract.BLOCKED)
        self.assertEqual(verdict["reason"], contract.REASON_PERMANENT_PROVIDER_INVALID)

    def test_non_successful_non_permanent_acquisition_status_is_blocked(self):
        for status in ("RETRYABLE", "UNCLASSIFIED", "UNTOUCHED"):
            verdict = contract.classify_price_reconstruction(
                ticker="ZZZ", session="2026-06-01", knowledge_cutoff="2026-08-17",
                mode=contract.MODE_PIT_AS_KNOWN, acquisition_status=status)
            self.assertEqual(verdict["verdict"], contract.BLOCKED, status)
            self.assertEqual(verdict["reason"], contract.REASON_ACQUISITION_NOT_SUCCESSFUL)

    def test_successful_equity_ticker_proceeds_past_scope_gate(self):
        verdict = contract.classify_price_reconstruction(
            ticker="ZZZ", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, instrument_class="EQUITY", acquisition_status="SUCCESS")
        self.assertNotEqual(verdict["reason"], contract.REASON_TICKER_SCOPE_BLOCKED)
        self.assertNotEqual(verdict["reason"], contract.REASON_OUT_OF_EQUITY_SCOPE)

    def test_unspecified_instrument_class_and_status_do_not_block_scope(self):
        # This contract does not itself infer equity-ness; an omitted classification proceeds
        # rather than blocking, matching "consume P0-C's classification, never re-derive it".
        verdict = contract.classify_price_reconstruction(
            ticker="ZZZ", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN)
        self.assertIn(verdict["reason"], {contract.REASON_PRICE_BASIS_UNKNOWN})


# ==========================================================================
# Stage 2: price basis
# ==========================================================================

class PriceBasisStateTests(unittest.TestCase):
    def test_bounded_hpg_window_is_qualified_for_retrospective_restated(self):
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        self.assertEqual(verdict["price_basis"]["state"], contract.QUALIFIED)
        self.assertEqual(verdict["price_basis"]["source_price_basis"], "ADJUSTED_RETROSPECTIVE")

    def test_bounded_hpg_window_blocks_pit_as_known_without_contemporaneous_observation(self):
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_PRICE_BASIS_RETROSPECTIVE_ONLY)

    def test_outside_bounded_window_is_unknown_not_extrapolated(self):
        # One day after HPG's own qualified window (2026-05-15..2026-06-03).
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-06-10", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        self.assertEqual(verdict["price_basis"]["state"], contract.UNKNOWN)
        self.assertEqual(verdict["price_basis"]["source_price_basis"], "UNKNOWN")

    def test_ticker_with_qualified_shaped_event_but_no_own_evidence_is_not_generalized(self):
        # A third ticker is never granted HPG/VCB's bounded authority merely by requesting the
        # same provider/dataset -- coverage_generalization is "not_authorized" by construction.
        verdict = contract.classify_price_reconstruction(
            ticker="VNM", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        self.assertEqual(verdict["price_basis"]["state"], contract.UNKNOWN)

    def test_generic_ticker_never_invents_a_price_basis(self):
        verdict = contract.classify_price_reconstruction(
            ticker="FPT", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        self.assertIn(verdict["price_basis"]["state"], {contract.UNKNOWN})
        self.assertNotEqual(verdict["price_basis"].get("source_price_basis"), "RAW_AS_TRADED")


class PitAsKnownPositiveAuthorityGateTests(unittest.TestCase):
    """The bounded safety fix: retrieval-time proximity alone must never establish RAW_AS_TRADED
    or PIT/backtest authority. An observation may contribute to PIT_AS_KNOWN only if (1) an
    existing, authoritative bounded_price_basis_for verdict is positively RAW_AS_TRADED, and
    only then (2) the supplied observation itself carries authoritative retained-observation
    identity. No real ticker in this repository has (1) today, so these tests exercise the
    reachable QUALIFIED path only via a synthetic authority, and separately prove every rejection
    path a real, un-authorized caller would hit."""

    def test_bare_retrieved_at_dict_never_qualifies_pit_as_known(self):
        """Required test 1: a bare caller dict with only retrieved_at must not qualify."""
        verdict = contract.classify_price_reconstruction(
            ticker="VNM", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN,
            contemporaneous_raw_observation={"retrieved_at": "2026-06-01T15:10:00Z"})
        self.assertNotEqual(verdict["verdict"], contract.QUALIFIED)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertFalse(verdict["pit_backtest_eligible"])

    def test_plausible_looking_dict_never_qualifies_without_positive_authority(self):
        """Required test 2: a dict with several plausible-looking, official-sounding field names
        (retrieved_at, observation_id, content_sha256, provider, dataset) still must not qualify
        -- the source/basis gate is what matters, not how convincing the caller's dict looks."""
        plausible = {"retrieved_at": "2026-06-01T15:10:00Z", "observation_id": "looks-real-1",
                    "content_sha256": "f" * 64, "provider": "DNSE", "dataset": "ohlc_1D"}
        verdict = contract.classify_price_reconstruction(
            ticker="VNM", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, contemporaneous_raw_observation=plausible)
        self.assertNotEqual(verdict["verdict"], contract.QUALIFIED)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_AUTHORITATIVE)

    def test_backfill_capture_never_qualifies_regardless_of_session_age(self):
        """Look-ahead gate 5, re-verified post-fix: a current/backfill query must not be treated
        as PIT evidence merely because the requested trading date is old -- and now, more
        fundamentally, because no positive RAW_AS_TRADED authority exists for it at all."""
        verdict = contract.classify_price_reconstruction(
            ticker="VNM", session="2020-01-02", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN,
            contemporaneous_raw_observation={"retrieved_at": "2026-08-16T10:00:00Z"})
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_AUTHORITATIVE)

    def test_retrospectively_rewritten_source_rejects_close_observation_despite_proximity(self):
        """Required test 3: a real retrospectively-rewritten/current-query DNSE observation
        (HPG's own bounded ADJUSTED_RETROSPECTIVE window) retrieved close to the session must
        not qualify PIT_AS_KNOWN merely due to proximity -- ADJUSTED_RETROSPECTIVE is never
        RAW_AS_TRADED, so the observation is disregarded entirely, regardless of how close."""
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN,
            contemporaneous_raw_observation={"retrieved_at": "2026-05-20T15:10:00Z"})
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_AUTHORITATIVE)
        self.assertEqual(verdict["price_basis"]["source_price_basis"], "ADJUSTED_RETROSPECTIVE")

    def test_positive_raw_as_traded_authority_with_well_formed_observation_qualifies(self):
        """Proves the QUALIFIED path is reachable in principle -- via a synthetic authority only,
        never a real ticker in this repository today."""
        authority = _synthetic_authority("SYN3", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        observation = _synthetic_raw_observation("SYN3", retrieved_at="2026-01-15T15:10:00Z")
        no_relevant_event = _synthetic_share_event("SYN3", event_type="cancellation", ex_date=None,
                                                    stock_ratio=None)
        verdict = contract.classify_price_reconstruction(
            ticker="SYN3", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority],
            contemporaneous_raw_observation=observation,
            corporate_action_observations=[no_relevant_event])
        self.assertEqual(verdict["price_basis"]["state"], contract.QUALIFIED)
        self.assertEqual(verdict["verdict"], contract.QUALIFIED)
        self.assertTrue(verdict["pit_backtest_eligible"])

    def test_bare_dict_still_blocks_even_under_positive_raw_as_traded_authority(self):
        """Requirement (2) (authoritative observation identity) is independent of requirement (1)
        (positive basis authority): even with (1) satisfied, a bare dict must still be refused."""
        authority = _synthetic_authority("SYN3", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN3", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority],
            contemporaneous_raw_observation={"retrieved_at": "2026-01-15T15:10:00Z"})
        self.assertNotEqual(verdict["verdict"], contract.QUALIFIED)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_AUTHORITATIVE)
        # retrieved_at is present in the bare dict; the other six RawObservation identity fields
        # (provider, dataset, instrument, request_identity, raw_payload_hash, schema_version)
        # are not, which is exactly what should be refused here.
        self.assertIn("provider", verdict["price_basis"]["missing_identity_fields"])
        self.assertIn("instrument", verdict["price_basis"]["missing_identity_fields"])
        self.assertNotIn("retrieved_at", verdict["price_basis"]["missing_identity_fields"])

    def test_observation_missing_only_retrieved_at_still_blocks_under_positive_authority(self):
        authority = _synthetic_authority("SYN3", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        observation = _synthetic_raw_observation("SYN3", retrieved_at="2026-01-15T15:10:00Z")
        del observation["retrieved_at"]
        verdict = contract.classify_price_reconstruction(
            ticker="SYN3", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority],
            contemporaneous_raw_observation=observation)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_AUTHORITATIVE)
        self.assertEqual(verdict["price_basis"]["missing_identity_fields"], ["retrieved_at"])

    def test_identity_mismatched_observation_blocks_under_positive_authority(self):
        authority = _synthetic_authority("SYN3", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        wrong_ticker = _synthetic_raw_observation("OTHER", retrieved_at="2026-01-15T15:10:00Z")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN3", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority],
            contemporaneous_raw_observation=wrong_ticker)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_AUTHORITATIVE)
        self.assertTrue(verdict["price_basis"].get("identity_mismatch"))

    def test_observation_retrieved_after_cutoff_blocks_under_positive_authority(self):
        authority = _synthetic_authority("SYN3", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        observation = _synthetic_raw_observation("SYN3", retrieved_at="2026-01-16T10:00:00Z")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN3", session="2026-01-15", knowledge_cutoff="2026-01-15",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority],
            contemporaneous_raw_observation=observation)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_KNOWABLE_BY_CUTOFF)

    def test_non_contemporaneous_observation_blocks_under_positive_authority(self):
        """Temporal proximity remains a necessary supporting check even once authority (1) and
        identity (2) are both satisfied -- a backfill-style capture still fails it."""
        authority = _synthetic_authority("SYN3", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        observation = _synthetic_raw_observation("SYN3", retrieved_at="2026-02-28T10:00:00Z")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN3", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority],
            contemporaneous_raw_observation=observation)
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_CONTEMPORANEOUS)

    def test_no_observation_supplied_under_positive_authority_is_blocked_not_qualified(self):
        authority = _synthetic_authority("SYN3", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN3", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority])
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_NO_CONTEMPORANEOUS_OBSERVATION)

    def test_self_asserted_authority_flags_are_not_a_recognized_parameter(self):
        """No caller-set flag (trusted/raw/pit_safe) is a recognized part of the API -- passing
        one has no effect; only positive authority plus authoritative identity can qualify."""
        observation = _synthetic_raw_observation("VNM", retrieved_at="2026-06-01T15:10:00Z",
                                                  trusted=True, raw=True, pit_safe=True)
        verdict = contract.classify_price_reconstruction(
            ticker="VNM", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, contemporaneous_raw_observation=observation)
        self.assertNotEqual(verdict["verdict"], contract.QUALIFIED)
        self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_OBSERVATION_NOT_AUTHORITATIVE)


# ==========================================================================
# Stage 3: corporate-action dependency, including the cash-dividend additive boundary
# ==========================================================================

class CorporateActionStateTests(unittest.TestCase):
    def test_no_observations_supplied_is_unknown_not_not_applicable(self):
        verdict = contract.classify_price_reconstruction(
            ticker="ZZZ", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        self.assertEqual(verdict["corporate_action"]["state"], contract.UNKNOWN)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_NO_EVIDENCE_SUPPLIED)

    def test_non_price_relevant_event_type_is_not_applicable(self):
        obs = _synthetic_share_event("ZZZ", event_type="cancellation", ex_date=None, stock_ratio=None)
        verdict = contract.classify_price_reconstruction(
            ticker="ZZZ", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.NOT_APPLICABLE)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_NO_PRICE_RELEVANT_EVENT)

    def test_fully_qualified_ex_dated_share_event_reaches_qualified_before_ex_date(self):
        obs = _synthetic_share_event("SYN")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.QUALIFIED)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_CORPORATE_ACTION_QUALIFIED)
        self.assertEqual(len(verdict["corporate_action"]["qualifying"]), 1)

    def test_session_on_or_after_ex_date_is_not_applicable_for_that_event(self):
        obs = _synthetic_share_event("SYN")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-03-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.NOT_APPLICABLE)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_CORPORATE_ACTION_NOT_APPLICABLE)

    def test_share_event_missing_ex_date_blocks(self):
        obs = _synthetic_share_event("SYN", ex_date=None)
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_MISSING_EXPLICIT_EX_DATE)

    def test_share_event_without_share_count_identity_blocks_as_unlinked(self):
        # Mirrors SSI's real bonus_shares facet: a stock_ratio with no absolute share counts
        # never reaches a ledger entry at all (event_key() needs shares_issued or before+after).
        obs = _synthetic_share_event("SYN", shares_before=0, shares_issued=0, ex_date=None)
        obs["shares_before"] = None
        obs["shares_issued"] = None
        obs["shares_after"] = None
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_SHARE_COUNT_IDENTITY_UNAVAILABLE)


class CashDividendAdditiveBoundaryTests(unittest.TestCase):
    """The milestone's additive eligibility boundary: a cash-dividend observation must never be
    silently invisible merely because official_corporate_action_ledger.event_key() cannot link
    it (it has no share-count identity)."""

    def test_cash_dividend_is_visible_and_blocks_even_though_ledger_never_links_it(self):
        obs = _synthetic_cash_event("SYN", ex_date="2026-02-01")
        built = ledger.build_ledger([obs])
        self.assertEqual(built["entry_count"], 0, "sanity: the ledger itself must not link a pure cash event")

        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.BLOCKED)
        self.assertNotEqual(verdict["corporate_action"]["reason"], contract.REASON_NO_EVIDENCE_SUPPLIED)

    def test_cash_dividend_missing_amount_blocks_with_amount_reason(self):
        obs = _synthetic_cash_event("SYN", cash_amount_per_share=None, ex_date="2026-02-01")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_CASH_DIVIDEND_AMOUNT_UNQUALIFIED)

    def test_cash_dividend_missing_ex_date_blocks_with_ex_date_reason(self):
        obs = _synthetic_cash_event("SYN", ex_date=None)
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_MISSING_EXPLICIT_EX_DATE)

    def test_cash_dividend_with_amount_and_ex_date_still_never_fabricates_a_factor(self):
        """Even fully evidenced (amount + explicit ex-date), a cash-dividend event must never
        reach QUALIFIED here: no non-ticker-specific cash-adjustment-factor methodology is
        qualified anywhere in this repository (VCB's ~0.9917 factor is a single-event magnitude,
        not a portable formula)."""
        obs = _synthetic_cash_event("SYN", cash_amount_per_share=1000.0, ex_date="2026-02-01")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["corporate_action"]["reason"],
                         contract.REASON_CASH_DIVIDEND_NO_FACTOR_METHODOLOGY)


# ==========================================================================
# Combination: QUALIFIED is reachable, and PARTIAL/BLOCKED precedence
# ==========================================================================

class CombinationTests(unittest.TestCase):
    def test_qualified_requires_both_dimensions_clean(self):
        authority = _synthetic_authority("SYN", effective_from="2026-01-01", effective_to="2026-03-01")
        obs = _synthetic_share_event("SYN")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs],
            price_basis_authorities=[authority])
        self.assertEqual(verdict["verdict"], contract.QUALIFIED)
        self.assertIsNone(verdict["reason"])

    def test_qualified_price_basis_with_unresolved_corporate_action_is_partial_not_qualified(self):
        verdict = contract.classify_price_reconstruction(
            ticker="VCB", session="2026-07-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[])
        self.assertEqual(verdict["price_basis"]["state"], contract.QUALIFIED)
        self.assertEqual(verdict["corporate_action"]["state"], contract.UNKNOWN)
        self.assertEqual(verdict["verdict"], contract.PARTIAL)
        self.assertEqual(verdict["reason"], contract.REASON_DEPENDENCY_UNRESOLVED_PARTIAL)

    def test_blocked_corporate_action_dominates_over_unknown_price_basis(self):
        obs = _synthetic_share_event("SYN", ex_date=None)
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["price_basis"]["state"], contract.UNKNOWN)
        self.assertEqual(verdict["corporate_action"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["verdict"], contract.BLOCKED)

    def test_blocked_price_basis_dominates_over_qualified_corporate_action(self):
        authority = _synthetic_authority("SYN", effective_from="2026-01-01", effective_to="2026-03-01")
        obs = _synthetic_share_event("SYN")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, corporate_action_observations=[obs],
            price_basis_authorities=[authority])
        self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["verdict"], contract.BLOCKED)

    def test_pit_as_known_reaches_qualified_only_with_positive_authority_and_clean_corporate_action(self):
        """PIT_AS_KNOWN can reach QUALIFIED, but -- post safety-fix -- only when a positive
        RAW_AS_TRADED authority backs the observation, never from proximity alone. See
        PitAsKnownPositiveAuthorityGateTests for the full authority-gate regression."""
        authority = _synthetic_authority("SYN2", effective_from="2026-01-01", effective_to="2026-03-01",
                                         price_basis="RAW_AS_TRADED")
        observation = _synthetic_raw_observation("SYN2", retrieved_at="2026-01-15T15:10:00Z")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN2", session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, price_basis_authorities=[authority],
            contemporaneous_raw_observation=observation,
            corporate_action_observations=[_synthetic_share_event(
                "SYN2", event_type="cancellation", ex_date=None, stock_ratio=None)])
        self.assertEqual(verdict["verdict"], contract.QUALIFIED)
        self.assertTrue(verdict["pit_backtest_eligible"])

    def test_no_state_other_than_qualified_carries_a_none_reason(self):
        # Every BLOCKED/PARTIAL/UNKNOWN/NOT_APPLICABLE verdict carries a non-null reason;
        # QUALIFIED is the only state a null reason is acceptable for.
        for mode in sorted(contract.VIEW_MODES):
            for ticker in ("ZZZ", "HPG"):
                verdict = contract.classify_price_reconstruction(
                    ticker=ticker, session="2026-06-01", knowledge_cutoff="2026-08-17", mode=mode)
                self.assertNotEqual(verdict["verdict"], contract.QUALIFIED, (mode, ticker))
                self.assertIsNotNone(verdict["reason"], (mode, ticker))


# ==========================================================================
# Mode isolation (bounded safety fix 2): pit_backtest_eligible must never be true for
# RETROSPECTIVE_RESTATED, and a generic "qualified" list must never blur the two modes.
# ==========================================================================

class ModeIsolationTests(unittest.TestCase):
    def test_retrospective_restated_qualified_still_has_eligible_false(self):
        """Required test 4: RETROSPECTIVE_RESTATED bounded HPG/VCB evidence may retain its
        legitimate QUALIFIED verdict, but pit_backtest_eligible must stay False."""
        for ticker, session in (("HPG", "2026-05-20"), ("VCB", "2026-07-20")):
            verdict = contract.classify_price_reconstruction(
                ticker=ticker, session=session, knowledge_cutoff="2026-08-17",
                mode=contract.MODE_RETROSPECTIVE_RESTATED)
            self.assertEqual(verdict["price_basis"]["state"], contract.QUALIFIED, ticker)
            self.assertFalse(verdict["pit_backtest_eligible"], ticker)

    def test_retrospective_qualified_ticker_never_appears_in_pit_backtest_eligible_list(self):
        """Required test 5: a generic RETROSPECTIVE_RESTATED QUALIFIED result cannot appear in
        pit_backtest_eligible_tickers."""
        authority = _synthetic_authority("SYN4", effective_from="2026-01-01", effective_to="2026-03-01")
        obs = _synthetic_share_event("SYN4")
        records = [{"ticker": "SYN4"}]
        summary = contract.classify_universe(
            records, session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED,
            corporate_action_observations_by_ticker={"SYN4": [obs]},
            price_basis_authorities=[authority])
        self.assertIn("SYN4", summary["retrospective_qualified_tickers"])
        self.assertNotIn("SYN4", summary["pit_backtest_eligible_tickers"])

    def test_pit_as_known_blocked_and_unknown_records_are_never_eligible(self):
        """Required test 6."""
        blocked = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN)
        unknown = contract.classify_price_reconstruction(
            ticker="FPT", session="2026-06-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN)
        self.assertEqual(blocked["verdict"], contract.BLOCKED)
        self.assertEqual(unknown["verdict"], contract.UNKNOWN)
        self.assertFalse(blocked["pit_backtest_eligible"])
        self.assertFalse(unknown["pit_backtest_eligible"])

    def test_verdict_id_reflects_mode_and_eligibility_not_just_verdict_label(self):
        """Required test 7: the deterministic identity changes when a semantically relevant
        eligibility/mode field changes, even if the bare 'verdict' label were ever to coincide."""
        pit = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN)
        retro = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        self.assertNotEqual(pit["verdict_id"], retro["verdict_id"])
        self.assertNotEqual(pit["pit_backtest_eligible"], retro["price_basis"]["state"] == contract.QUALIFIED)
        # pit_backtest_eligible itself is part of the fingerprinted record.
        import json as _json
        self.assertIn("pit_backtest_eligible",
                      _json.loads(contract._canonical_json(
                          {k: v for k, v in pit.items() if k != "verdict_id"})))

    def test_no_self_asserted_authority_marker_exists_in_the_output_schema(self):
        """No caller-visible 'trusted'/'raw'/'pit_safe' field is part of the contract's own
        output vocabulary -- pit_backtest_eligible is the only eligibility signal, and it is
        entirely derived, never settable by a caller."""
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        for forbidden in ("trusted", "raw", "pit_safe"):
            self.assertNotIn(forbidden, verdict)
            self.assertNotIn(forbidden, verdict["price_basis"])


# ==========================================================================
# Look-ahead invariants (all 6 required by the milestone)
# ==========================================================================

class LookaheadGateTests(unittest.TestCase):
    def test_gate_1_document_observed_after_cutoff_is_excluded(self):
        obs = _synthetic_share_event("SYN", observed_at="2026-08-10T00:00:00Z")
        verdict = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-01",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[obs])
        self.assertEqual(verdict["corporate_action"]["state"], contract.UNKNOWN)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_NO_EVIDENCE_KNOWABLE_BY_CUTOFF)
        self.assertEqual(verdict["corporate_action"]["considered_observation_ids"], [])

    def test_gate_2_amendment_observed_after_cutoff_does_not_alter_the_as_known_ledger(self):
        original = _synthetic_share_event("SYN", observed_at="2026-01-05T00:00:00Z")
        # An amendment/cancellation for the same share-change identity, but only knowable later.
        amendment = _synthetic_share_event(
            "SYN", event_type="cancellation", observed_at="2026-09-01T00:00:00Z",
            ex_date=None, stock_ratio=None,
            observation_id="syn-amend-1", document_id="syn-amend-doc-1")
        cutoff_before_amendment = "2026-08-01"
        as_known_only_original = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff=cutoff_before_amendment,
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[original])
        as_known_with_late_amendment = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff=cutoff_before_amendment,
            mode=contract.MODE_RETROSPECTIVE_RESTATED,
            corporate_action_observations=[original, amendment])
        self.assertEqual(as_known_only_original["verdict"], as_known_with_late_amendment["verdict"])
        self.assertEqual(as_known_only_original["corporate_action"]["state"],
                         as_known_with_late_amendment["corporate_action"]["state"])

    def test_gate_3_future_event_never_adjusts_a_session_before_it_was_knowable(self):
        future_event = _synthetic_share_event("SYN", observed_at="2026-08-10T00:00:00Z")
        blind_cutoff = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-01",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[future_event])
        no_evidence = contract.classify_price_reconstruction(
            ticker="SYN", session="2026-01-15", knowledge_cutoff="2026-08-01",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[])
        # Both must land on the same UNKNOWN state (never QUALIFIED, never influenced by the
        # future event's own ex_date/ratio) -- but the reason and provenance are allowed, and
        # expected, to differ: "evidence existed but was too late" is a more informative record
        # than "no evidence was ever supplied", not a discrepancy.
        self.assertEqual(blind_cutoff["corporate_action"]["state"], no_evidence["corporate_action"]["state"])
        self.assertEqual(blind_cutoff["verdict"], no_evidence["verdict"])
        self.assertNotEqual(blind_cutoff["verdict"], contract.QUALIFIED)
        self.assertIn(future_event["observation_id"],
                      blind_cutoff["corporate_action"]["excluded_after_cutoff_observation_ids"])
        self.assertEqual(blind_cutoff["corporate_action"]["considered_observation_ids"], [])

    def test_gate_4_ticker_scope_is_a_current_snapshot_never_a_historical_listing_claim(self):
        verdict = contract.classify_price_reconstruction(
            ticker="ZZZ", session="1999-01-04", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN, instrument_class="EQUITY")
        # The scope record names only the current classification input and never asserts
        # anything about listing/active status on the (decades-earlier) requested session.
        self.assertNotIn("listing_status", verdict["ticker_scope"])
        self.assertNotIn("active_universe", verdict["ticker_scope"])

    def test_gate_5_current_dnse_query_is_not_pit_evidence_merely_because_the_date_is_old(self):
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="1999-01-04", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_PIT_AS_KNOWN)
        self.assertEqual(verdict["price_basis"]["state"], contract.UNKNOWN)
        self.assertNotEqual(verdict["price_basis"]["state"], contract.QUALIFIED)

    def test_gate_6_legacy_or_pattern_must_not_admit_evidence_known_only_after_cutoff(self):
        """The exact anti-pattern retained in point_in_time_adjusted_prices.py:
        ``verified_at <= knowledge_cutoff or decl <= knowledge_cutoff``. Real HPG evidence has
        published_at="2026-07-07" (would pass the OR) but observed_at="2026-08-02T08:10:00Z"
        (would fail a correct AND/observed_at-only rule). A cutoff strictly between the two must
        exclude the evidence."""
        html_path = (ROOT / "operations-review" / "hpg-vnm-current-share-bridge-20260802"
                    / "documents" / "HPG" / "2026" / "corporate_action_notice"
                    / "cb41c96ef78bed7654030e55bb06dea22d051b1c9fcf1a6cf024e9f964563c1c.html")
        if not html_path.is_file():
            self.skipTest("retained HPG issuer-IR listing-change notice is not present")
        payload = html_path.read_bytes()
        record = {
            "document_id": "hpg-listing-change-2026", "ticker": "HPG", "source_id": "issuer_ir",
            "source_authority": "Hoa Phat Group Joint Stock Company investor relations, reciting HOSE notice 1475/TB-SGDHCM",
            "source_url": ("https://www.hoaphat.com.vn/tin-tuc/"
                          "thong-bao-ve-ngay-giao-dich-co-phieu-phat-hanh-tra-co-tuc-nam-2025-1.html"),
            "content_sha256": document_store.sha256_bytes(payload),
            "published_at": "2026-07-07", "observed_at": "2026-08-02T08:10:00Z",
            "media_type": "text/html",
        }
        self.assertLess(record["published_at"], "2026-07-15")
        typed = events.classify_retained_document(record, payload)
        text = events.extract_text(payload, typed["media_type"])
        observation = events.extract_event_observation(typed, text)

        legacy_would_admit = (observation["observed_at"] <= "2026-07-15"
                              or observation["published_at"] <= "2026-07-15")
        self.assertTrue(legacy_would_admit, "the legacy OR-pattern would have wrongly admitted this document")

        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-07-15",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[observation])
        self.assertEqual(verdict["corporate_action"]["state"], contract.UNKNOWN)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_NO_EVIDENCE_KNOWABLE_BY_CUTOFF)
        self.assertEqual(verdict["corporate_action"]["considered_observation_ids"], [])
        self.assertIn(observation["observation_id"],
                      verdict["corporate_action"]["excluded_after_cutoff_observation_ids"])


# ==========================================================================
# Determinism / provenance
# ==========================================================================

class DeterminismTests(unittest.TestCase):
    def test_identical_inputs_produce_identical_verdict_and_id(self):
        kwargs = dict(ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
                     mode=contract.MODE_RETROSPECTIVE_RESTATED)
        first = contract.classify_price_reconstruction(**kwargs)
        second = contract.classify_price_reconstruction(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(first["verdict_id"], second["verdict_id"])

    def test_different_mode_produces_a_different_verdict_id(self):
        base = dict(ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17")
        pit = contract.classify_price_reconstruction(mode=contract.MODE_PIT_AS_KNOWN, **base)
        retro = contract.classify_price_reconstruction(mode=contract.MODE_RETROSPECTIVE_RESTATED, **base)
        self.assertNotEqual(pit["verdict_id"], retro["verdict_id"])

    def test_verdict_record_carries_full_provenance_fields(self):
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        for field in ("ticker", "session", "knowledge_cutoff", "mode", "provider", "dataset",
                     "verdict", "reason", "ticker_scope", "price_basis", "corporate_action",
                     "verdict_id", "contract_version", "schema_version"):
            self.assertIn(field, verdict)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(contract.PitPriceReconstructionContractError):
            contract.classify_price_reconstruction(
                ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17", mode="SOMETHING_ELSE")

    def test_both_modes_helper_returns_two_distinct_verdicts(self):
        both = contract.classify_price_reconstruction_both_modes(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17")
        self.assertEqual(set(both), contract.VIEW_MODES)
        self.assertNotEqual(both[contract.MODE_PIT_AS_KNOWN]["verdict_id"],
                            both[contract.MODE_RETROSPECTIVE_RESTATED]["verdict_id"])


# ==========================================================================
# classify_universe: denominator/accounting properties
# ==========================================================================

class ClassifyUniverseTests(unittest.TestCase):
    def test_denominator_equals_input_record_count_exactly(self):
        records = [{"ticker": f"T{i:03d}", "acquisition_status": "SUCCESS"} for i in range(37)]
        summary = contract.classify_universe(records, session="2026-08-01", knowledge_cutoff="2026-08-17",
                                             mode=contract.MODE_PIT_AS_KNOWN)
        self.assertEqual(summary["denominator"], 37)
        self.assertEqual(sum(summary["verdict_counts"].values()), 37)
        self.assertEqual(len(summary["results"]), 37)

    def test_permanent_instruments_remain_explicitly_accounted_for(self):
        records = ([{"ticker": f"S{i:03d}", "acquisition_status": "SUCCESS"} for i in range(5)]
                  + [{"ticker": f"P{i:03d}", "acquisition_status": "PERMANENT"} for i in range(3)])
        summary = contract.classify_universe(records, session="2026-08-01", knowledge_cutoff="2026-08-17",
                                             mode=contract.MODE_PIT_AS_KNOWN)
        self.assertEqual(summary["acquisition_status_counts"]["PERMANENT"], 3)
        self.assertEqual(summary["acquisition_status_counts"]["SUCCESS"], 5)
        self.assertEqual(summary["reason_counts"][contract.REASON_PERMANENT_PROVIDER_INVALID], 3)

    def test_zero_false_qualified_over_a_no_evidence_universe(self):
        records = [{"ticker": f"T{i:03d}", "acquisition_status": "SUCCESS"} for i in range(50)]
        summary = contract.classify_universe(records, session="2026-08-01", knowledge_cutoff="2026-08-17",
                                             mode=contract.MODE_PIT_AS_KNOWN)
        self.assertEqual(summary["verdict_counts"].get(contract.QUALIFIED, 0), 0)
        self.assertEqual(summary["pit_backtest_eligible_tickers"], [])
        self.assertEqual(summary["retrospective_qualified_tickers"], [])
        self.assertNotIn("qualified_tickers", summary)

    def test_duplicate_ticker_raises_rather_than_silently_merging(self):
        with self.assertRaises(contract.PitPriceReconstructionContractError):
            contract.classify_universe(
                [{"ticker": "AAA"}, {"ticker": "aaa"}], session="2026-08-01",
                knowledge_cutoff="2026-08-17", mode=contract.MODE_PIT_AS_KNOWN)

    def test_missing_ticker_field_raises(self):
        with self.assertRaises(contract.PitPriceReconstructionContractError):
            contract.classify_universe(
                [{"instrument_class": "EQUITY"}], session="2026-08-01",
                knowledge_cutoff="2026-08-17", mode=contract.MODE_PIT_AS_KNOWN)

    def test_per_ticker_corporate_action_observations_are_routed_correctly(self):
        records = [{"ticker": "SYN", "acquisition_status": "SUCCESS"},
                  {"ticker": "OTHER", "acquisition_status": "SUCCESS"}]
        summary = contract.classify_universe(
            records, session="2026-01-15", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED,
            corporate_action_observations_by_ticker={"SYN": [_synthetic_share_event("SYN", ex_date=None)]})
        by_ticker = {r["ticker"]: r for r in summary["results"]}
        self.assertEqual(by_ticker["SYN"]["corporate_action"]["reason"], contract.REASON_MISSING_EXPLICIT_EX_DATE)
        self.assertEqual(by_ticker["OTHER"]["corporate_action"]["reason"], contract.REASON_NO_EVIDENCE_SUPPLIED)


class ClassifyUniverseCliTests(unittest.TestCase):
    def test_cli_end_to_end_reads_json_writes_json_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe_path = root / "universe.json"
            universe_path.write_text(json.dumps([
                {"ticker": "AAA", "instrument_class": "EQUITY", "acquisition_status": "SUCCESS"},
                {"ticker": "BBB", "instrument_class": "EQUITY", "acquisition_status": "PERMANENT"},
                {"ticker": "CCC", "instrument_class": "WARRANT"},
            ]), encoding="utf-8")
            out_path = root / "out.json"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exit_code = contract.main([
                    "--universe-json", str(universe_path), "--session", "2026-08-01",
                    "--knowledge-cutoff", "2026-08-17", "--mode", "PIT_AS_KNOWN",
                    "--out", str(out_path),
                ])
            self.assertEqual(exit_code, 0)
            printed = json.loads(buffer.getvalue())
            self.assertEqual(printed["denominator"], 3)
            self.assertNotIn("results", printed)
            written = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(len(written["results"]), 3)

    def test_cli_rejects_non_list_universe_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            universe_path = Path(tmp) / "universe.json"
            universe_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
            with self.assertRaises(contract.PitPriceReconstructionContractError):
                contract.main(["--universe-json", str(universe_path), "--session", "2026-08-01",
                              "--knowledge-cutoff", "2026-08-17"])


# ==========================================================================
# Required real-evidence regressions
# ==========================================================================

class RealHpgRegressionTests(unittest.TestCase):
    """REQUIRED REAL-EVIDENCE REGRESSIONS: HPG. Real retained issuer-IR evidence; no synthetic
    ex-date, no fabricated factor, fail-closed."""

    HTML = (ROOT / "operations-review" / "hpg-vnm-current-share-bridge-20260802" / "documents"
           / "HPG" / "2026" / "corporate_action_notice"
           / "cb41c96ef78bed7654030e55bb06dea22d051b1c9fcf1a6cf024e9f964563c1c.html")

    def setUp(self):
        if not self.HTML.is_file():
            self.skipTest("retained HPG issuer-IR listing-change notice is not present")
        self.payload = self.HTML.read_bytes()
        self.record = {
            "document_id": "hpg-listing-change-2026", "ticker": "HPG", "source_id": "issuer_ir",
            "source_authority": "Hoa Phat Group Joint Stock Company investor relations, reciting HOSE notice 1475/TB-SGDHCM",
            "source_url": ("https://www.hoaphat.com.vn/tin-tuc/"
                          "thong-bao-ve-ngay-giao-dich-co-phieu-phat-hanh-tra-co-tuc-nam-2025-1.html"),
            "content_sha256": document_store.sha256_bytes(self.payload),
            "published_at": "2026-07-07", "observed_at": "2026-08-02T08:10:00Z",
            "media_type": "text/html",
        }
        typed = events.classify_retained_document(self.record, self.payload)
        text = events.extract_text(self.payload, typed["media_type"])
        self.observation = events.extract_event_observation(typed, text)

    def test_hpg_carries_no_synthetic_ex_date(self):
        self.assertIsNone(self.observation["ex_date"])

    def test_hpg_never_reaches_a_qualified_pit_adjustment_factor(self):
        for mode in sorted(contract.VIEW_MODES):
            verdict = contract.classify_price_reconstruction(
                ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17", mode=mode,
                corporate_action_observations=[self.observation])
            self.assertNotEqual(verdict["verdict"], contract.QUALIFIED, mode)

    def test_hpg_corporate_action_dimension_is_fail_closed_blocked(self):
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=[self.observation])
        self.assertEqual(verdict["corporate_action"]["state"], contract.BLOCKED)
        self.assertEqual(verdict["corporate_action"]["reason"], contract.REASON_MISSING_EXPLICIT_EX_DATE)

    def test_hpg_remains_regression_evidence_only_no_ticker_specific_branch(self):
        import inspect

        source = inspect.getsource(contract)
        self.assertNotIn('"HPG"', source)
        self.assertNotIn("'HPG'", source)


class RealSsiRegressionTests(unittest.TestCase):
    """REQUIRED REAL-EVIDENCE REGRESSIONS: SSI. Retained two-observation P0-A.2 result: record
    date preserved, ex-date remains absent, planned issuance not treated as execution, no
    fabricated factor, no fabricated cash-event ledger linkage."""

    HTML = (ROOT / "operations-review" / "ssi-vsdc-ex-date-notice-acquisition-20260811" / "documents"
           / "SSI" / "2026" / "last_registration_date_notice"
           / "bd7d4054613ae6f9c5ee1ddc6b787bf706ac6a18f551aff3c9683a85bcc06dad.html")

    def setUp(self):
        if not self.HTML.is_file():
            self.skipTest("retained SSI VSDC notice is not present")
        self.payload = self.HTML.read_bytes()
        self.record = {
            "document_id": "ssi-vsdc-198728", "ticker": "SSI",
            "document_type": "last_registration_date_notice",
            "source_authority": "Vietnam Securities Depository and Clearing Corporation",
            "source_id": "vsdc", "source_url": "https://vsd.vn/en/ad/198728",
            "content_sha256": document_store.sha256_bytes(self.payload),
            "published_at": "2026-07-29", "observed_at": "2026-08-11T00:00:00Z",
            "media_type": "text/html",
        }
        typed = events.classify_retained_document(self.record, self.payload)
        text = events.extract_text(self.payload, typed["media_type"])
        self.observations = events.extract_event_observations(typed, text)

    def test_ssi_yields_two_independent_facets(self):
        self.assertEqual(len(self.observations), 2)
        self.assertEqual(sorted(o["event_type"] for o in self.observations),
                         ["bonus_shares", "cash_dividend"])

    def test_ssi_record_date_preserved_ex_date_absent_on_both_facets(self):
        for obs in self.observations:
            self.assertEqual(obs["record_date"], "2026-08-18")
            self.assertIsNone(obs["ex_date"])

    def test_ssi_planned_bonus_never_becomes_executed(self):
        bonus = next(o for o in self.observations if o["event_type"] == "bonus_shares")
        self.assertIsNone(bonus["shares_after"])
        self.assertNotEqual(bonus["lifecycle_state"], "executed")

    def test_ssi_never_reaches_qualified_in_either_mode(self):
        for mode in sorted(contract.VIEW_MODES):
            verdict = contract.classify_price_reconstruction(
                ticker="SSI", session="2026-08-01", knowledge_cutoff="2026-08-17", mode=mode,
                corporate_action_observations=self.observations)
            self.assertNotEqual(verdict["verdict"], contract.QUALIFIED, mode)

    def test_ssi_cash_dividend_facet_blocks_without_fabricated_ledger_linkage(self):
        built = ledger.build_ledger(self.observations)
        self.assertEqual(built["entry_count"], 0)
        verdict = contract.classify_price_reconstruction(
            ticker="SSI", session="2026-08-01", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED, corporate_action_observations=self.observations)
        self.assertEqual(verdict["corporate_action"]["state"], contract.BLOCKED)


class DnseBoundedEvidenceRegressionTests(unittest.TestCase):
    """DNSE HPG/VCB bounded price-basis evidence: recognizable as bounded retrospective-only
    evidence, never promoted to generic market-wide raw-as-traded authority, and never accepted
    as PIT_AS_KNOWN merely because the (current) query resolves inside the qualified window."""

    def test_both_bounded_tickers_reach_retrospective_restated_price_basis(self):
        for ticker, session in (("HPG", "2026-05-20"), ("VCB", "2026-07-20")):
            verdict = contract.classify_price_reconstruction(
                ticker=ticker, session=session, knowledge_cutoff="2026-08-17",
                mode=contract.MODE_RETROSPECTIVE_RESTATED)
            self.assertEqual(verdict["price_basis"]["state"], contract.QUALIFIED, ticker)
            self.assertEqual(verdict["price_basis"]["source_price_basis"], "ADJUSTED_RETROSPECTIVE")

    def test_both_bounded_tickers_block_pit_as_known_without_contemporaneous_proof(self):
        for ticker, session in (("HPG", "2026-05-20"), ("VCB", "2026-07-20")):
            verdict = contract.classify_price_reconstruction(
                ticker=ticker, session=session, knowledge_cutoff="2026-08-17",
                mode=contract.MODE_PIT_AS_KNOWN)
            self.assertEqual(verdict["price_basis"]["state"], contract.BLOCKED, ticker)
            self.assertEqual(verdict["price_basis"]["reason"], contract.REASON_PRICE_BASIS_RETROSPECTIVE_ONLY)

    def test_bounded_evidence_is_never_promoted_to_raw_as_traded(self):
        verdict = contract.classify_price_reconstruction(
            ticker="HPG", session="2026-05-20", knowledge_cutoff="2026-08-17",
            mode=contract.MODE_RETROSPECTIVE_RESTATED)
        self.assertNotEqual(verdict["price_basis"]["source_price_basis"], "RAW_AS_TRADED")


class GenericMarketTickerRegressionTests(unittest.TestCase):
    """A ticker outside bounded evidence: no invented price basis, explicit UNKNOWN/BLOCKED."""

    def test_generic_ticker_both_modes_are_unknown_with_no_evidence(self):
        for mode in sorted(contract.VIEW_MODES):
            verdict = contract.classify_price_reconstruction(
                ticker="FPT", session="2026-06-01", knowledge_cutoff="2026-08-17", mode=mode)
            self.assertIn(verdict["verdict"], {contract.UNKNOWN})
            self.assertEqual(verdict["price_basis"]["source_price_basis"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
