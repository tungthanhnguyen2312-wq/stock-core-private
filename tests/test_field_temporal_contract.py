"""Tests for P0-C.3 Field-Level Freshness, Temporal Provenance, and PIT-Eligibility Contract."""

from datetime import datetime, timezone
import unittest
import pandas as pd

from field_temporal_contract import (
    CONTRACT_VERSION,
    FreshnessState,
    PitStatus,
    TemporalField,
    canonical_json,
    evaluate_field_temporal,
    evaluate_record_freshness,
    extract_field_values,
    stable_id,
    wrap_temporal_fields,
)
from market_data_contracts import (
    CanonicalRecord,
    FeatureStatus,
    PriceBasis,
    RawObservation,
    canonicalize_market_record,
)
from market_feature_store import (
    build_historical_features,
    build_temporal_feature_records,
)


REF_FRIDAY = datetime(2026, 8, 14, 16, 0, tzinfo=timezone.utc)
REF_SATURDAY = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
REF_SUNDAY = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
REF_MONDAY_MORNING = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
REF_MONDAY_AFTERNOON = datetime(2026, 8, 17, 16, 0, tzinfo=timezone.utc)
REF_WEDNESDAY = datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc)


class FieldTemporalContractTests(unittest.TestCase):
    def test_boundary_dates_weekend_and_market_cadence(self):
        # Friday market data evaluated on Saturday and Sunday must remain current
        fri_sat = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_SATURDAY
        )
        self.assertEqual(FreshnessState.CURRENT.value, fri_sat.freshness_status)
        self.assertIsNone(fri_sat.stale_reason)
        self.assertTrue(fri_sat.is_actionable())

        fri_sun = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_SUNDAY
        )
        self.assertEqual(FreshnessState.CURRENT.value, fri_sun.freshness_status)
        self.assertTrue(fri_sun.is_actionable())

        # Friday data evaluated on Monday before market close (10:00) remains current
        fri_mon_am = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_MONDAY_MORNING
        )
        self.assertEqual(FreshnessState.CURRENT.value, fri_mon_am.freshness_status)

        # Friday data evaluated on Monday after close (16:00): Monday session completed -> Friday is stale
        fri_mon_pm = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_MONDAY_AFTERNOON
        )
        self.assertEqual(FreshnessState.STALE.value, fri_mon_pm.freshness_status)
        self.assertIn("exceeds_1d_grace", fri_mon_pm.stale_reason)

        # Evaluated on Wednesday: age exceeds cadence + grace -> stale
        fri_wed = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY
        )
        self.assertEqual(FreshnessState.STALE.value, fri_wed.freshness_status)
        self.assertIn("exceeds_1d_grace", fri_wed.stale_reason)
        self.assertFalse(fri_wed.is_actionable())

    def test_unknown_and_missing_timestamps(self):
        missing = evaluate_field_temporal(
            "volume", 1000, observed_at=None, as_of=None,
            domain="daily_market", reference_at=REF_WEDNESDAY
        )
        self.assertEqual(FreshnessState.MISSING.value, missing.freshness_status)
        self.assertEqual("source_timestamp_missing", missing.stale_reason)
        self.assertFalse(missing.pit_eligible)
        self.assertEqual(PitStatus.TIMESTAMP_MISSING_OR_INVALID.value, missing.pit_status)

        malformed = evaluate_field_temporal(
            "volume", 1000, observed_at="bad-timestamp", as_of="invalid-date",
            domain="daily_market", reference_at=REF_WEDNESDAY
        )
        self.assertEqual(FreshnessState.UNKNOWN.value, malformed.freshness_status)
        self.assertEqual("source_timestamp_malformed", malformed.stale_reason)
        self.assertFalse(malformed.pit_eligible)

        bad_ref = evaluate_field_temporal(
            "volume", 1000, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at="not-a-valid-iso-ref"
        )
        self.assertEqual(FreshnessState.UNKNOWN.value, bad_ref.freshness_status)
        self.assertEqual("invalid_reference_timestamp", bad_ref.stale_reason)

    def test_stale_but_valid_data_preserves_numeric_value(self):
        stale_field = evaluate_field_temporal(
            "close", 20.95, observed_at="2026-08-01T15:00:00Z", as_of="2026-08-01",
            domain="daily_market", reference_at=REF_WEDNESDAY
        )
        self.assertEqual(FreshnessState.STALE.value, stale_field.freshness_status)
        self.assertEqual(20.95, stale_field.value)  # value is not altered or dropped
        self.assertFalse(stale_field.is_actionable())
        self.assertIn("exceeds_1d_grace", stale_field.stale_reason)

    def test_future_and_lookahead_rejection(self):
        # as_of in the future
        future_as_of = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-25",
            domain="daily_market", reference_at=REF_WEDNESDAY
        )
        self.assertEqual(FreshnessState.UNKNOWN.value, future_as_of.freshness_status)
        self.assertEqual("future_as_of_date_rejected", future_as_of.stale_reason)
        self.assertFalse(future_as_of.pit_eligible)
        self.assertEqual(PitStatus.LOOKAHEAD_VIOLATION.value, future_as_of.pit_status)

        # observed_at in the future relative to reference_at
        future_obs = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-25T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY
        )
        self.assertEqual(FreshnessState.UNKNOWN.value, future_obs.freshness_status)
        self.assertEqual("future_observed_at_rejected", future_obs.stale_reason)
        self.assertFalse(future_obs.pit_eligible)

        # observed_at past knowledge_cutoff
        lookahead = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY,
            knowledge_cutoff="2026-08-10T00:00:00Z", price_basis="RAW_AS_TRADED"
        )
        self.assertFalse(lookahead.pit_eligible)
        self.assertEqual(PitStatus.LOOKAHEAD_VIOLATION.value, lookahead.pit_status)

    def test_pit_eligibility_with_price_basis_authority(self):
        # RAW_AS_TRADED with valid cutoff -> PIT_ELIGIBLE
        raw_price = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY,
            knowledge_cutoff="2026-08-14T16:00:00Z", price_basis="RAW_AS_TRADED"
        )
        self.assertTrue(raw_price.pit_eligible)
        self.assertEqual(PitStatus.QUALIFIED.value, raw_price.pit_status)

        # PIT_OBSERVED with valid cutoff -> PIT_ELIGIBLE
        pit_obs = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY,
            knowledge_cutoff="2026-08-14T16:00:00Z", price_basis="PIT_OBSERVED"
        )
        self.assertTrue(pit_obs.pit_eligible)
        self.assertEqual(PitStatus.QUALIFIED.value, pit_obs.pit_status)

        # ADJUSTED_RETROSPECTIVE -> strictly inelligible for PIT
        adj_price = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY,
            knowledge_cutoff="2026-08-14T16:00:00Z", price_basis="ADJUSTED_RETROSPECTIVE"
        )
        self.assertFalse(adj_price.pit_eligible)
        self.assertEqual(PitStatus.UNQUALIFIED_PRICE_BASIS.value, adj_price.pit_status)

        # UNKNOWN price basis -> strictly ineligible for PIT
        unknown_basis = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY,
            knowledge_cutoff="2026-08-14T16:00:00Z", price_basis="UNKNOWN"
        )
        self.assertFalse(unknown_basis.pit_eligible)
        self.assertEqual(PitStatus.UNQUALIFIED_PRICE_BASIS.value, unknown_basis.pit_status)

    def test_mixed_field_freshness_evaluation(self):
        fields = {
            "current_a": TemporalField("current_a", 10.0, "2026-08-18", "2026-08-18", FreshnessState.CURRENT.value, True, PitStatus.QUALIFIED.value),
            "current_b": TemporalField("current_b", 20.0, "2026-08-18", "2026-08-18", FreshnessState.CURRENT.value, True, PitStatus.QUALIFIED.value),
            "stale_c": TemporalField("stale_c", 30.0, "2026-08-01", "2026-08-01", FreshnessState.STALE.value, False, PitStatus.QUALIFIED.value, stale_reason="source_age_15d_exceeds_1d_grace"),
        }
        res = evaluate_record_freshness(fields)
        self.assertEqual(FreshnessState.STALE.value, res["composite_status"])
        self.assertEqual(2, res["actionable_fields_count"])
        self.assertEqual(3, res["total_fields_count"])
        self.assertFalse(res["all_actionable"])
        self.assertEqual("current", res["field_summaries"]["current_a"]["status"])
        self.assertEqual("stale", res["field_summaries"]["stale_c"]["status"])

    def test_historical_reporting_period_semantics(self):
        quarterly = evaluate_field_temporal(
            "net_revenue", 15000000000.0, observed_at="2025-04-15T10:00:00Z",
            as_of="2024-12-31", domain="financial_quarterly", reference_at=REF_WEDNESDAY
        )
        self.assertEqual(FreshnessState.HISTORICAL.value, quarterly.freshness_status)
        self.assertEqual("reporting_period_historical", quarterly.stale_reason)
        self.assertFalse(quarterly.is_actionable())

    def test_deterministic_serialization_and_immutability(self):
        t1 = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY, price_basis="RAW_AS_TRADED",
            knowledge_cutoff="2026-08-14T16:00:00Z"
        )
        t2 = evaluate_field_temporal(
            "close", 25.5, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY, price_basis="RAW_AS_TRADED",
            knowledge_cutoff="2026-08-14T16:00:00Z"
        )
        self.assertEqual(t1.field_id, t2.field_id)
        self.assertEqual(t1.canonical_json(), t2.canonical_json())
        self.assertEqual(t1.record(), t2.record())

        # Changing value or parameter alters field_id
        t3 = evaluate_field_temporal(
            "close", 26.0, observed_at="2026-08-14T15:00:00Z", as_of="2026-08-14",
            domain="daily_market", reference_at=REF_WEDNESDAY, price_basis="RAW_AS_TRADED",
            knowledge_cutoff="2026-08-14T16:00:00Z"
        )
        self.assertNotEqual(t1.field_id, t3.field_id)

    def test_canonical_record_temporal_integration(self):
        raw = RawObservation(
            provider="DNSE", dataset="daily_ohlc", instrument="HPG",
            retrieved_at="2026-08-14T15:00:00Z", request_identity="req-1",
            raw_payload_hash="hash-1", schema_version="1.0",
            raw_payload={"open": 20.0, "close": 21.0, "volume": 1000},
            source_event_time="2026-08-14T15:00:00Z"
        )
        record = canonicalize_market_record(
            raw, exchange="HOSE", board="G1", instrument_class="EQUITY",
            fields={"open": 20.0, "close": 21.0, "volume": 1000},
            price_basis=PriceBasis.UNKNOWN, reference_at=REF_SATURDAY,
            knowledge_cutoff="2026-08-14T16:00:00Z"
        )
        self.assertIn("close", record.temporal_fields)
        close_tf = record.temporal_fields["close"]
        self.assertEqual(21.0, close_tf.value)
        self.assertEqual(FreshnessState.CURRENT.value, close_tf.freshness_status)
        # UNKNOWN price basis prevents PIT eligibility
        self.assertFalse(close_tf.pit_eligible)
        self.assertEqual(PitStatus.UNQUALIFIED_PRICE_BASIS.value, close_tf.pit_status)

        # with_temporal_evaluation evaluates with new reference/cutoff
        evaluated = record.with_temporal_evaluation(reference_at=REF_WEDNESDAY)
        self.assertEqual(FreshnessState.STALE.value, evaluated.temporal_fields["close"].freshness_status)

    def test_market_feature_store_temporal_integration(self):
        df = pd.DataFrame({
            "ticker": ["HPG", "HPG", "HPG"],
            "date": ["2026-08-12", "2026-08-13", "2026-08-14"],
            "open": [20.0, 20.5, 21.0],
            "high": [20.5, 21.0, 21.5],
            "low": [19.5, 20.0, 20.5],
            "close": [20.2, 20.8, 21.2],
            "volume": [1000, 1200, 1100],
        })
        features = build_historical_features(df, price_basis=PriceBasis.RAW_AS_TRADED, window=2)
        records = build_temporal_feature_records(
            features, reference_at=REF_SATURDAY, knowledge_cutoff="2026-08-15T00:00:00Z"
        )
        self.assertEqual(3, len(records))
        last_row = records[-1]
        self.assertEqual("HPG", last_row["ticker"])
        self.assertEqual("2026-08-14", last_row["date"])
        self.assertIn("market.close", last_row["temporal_fields"])
        close_tf = last_row["temporal_fields"]["market.close"]
        self.assertEqual(21.2, close_tf["value"])
        self.assertEqual(FreshnessState.CURRENT.value, close_tf["freshness_status"])
        self.assertTrue(close_tf["pit_eligible"])
        self.assertEqual(PitStatus.QUALIFIED.value, close_tf["pit_status"])


if __name__ == "__main__":
    unittest.main()
