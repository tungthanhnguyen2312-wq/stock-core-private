from __future__ import annotations

import math
import json
import unittest
from pathlib import Path

from current_portfolio_risk_research import (
    ANNUALIZATION_SESSIONS,
    STANDARD_RISK_LOOKBACKS,
    _window_for,
    build_artifact,
    content_identity,
    simple_close_to_close_returns,
)


def _inputs(*, tickers=("AAA", "BBB"), sessions=20, missing=None, mixed_basis=False):
    calendar = [f"2026-01-{day:02d}" for day in range(1, sessions + 1)]
    records = {}
    shadow_records = {}
    case_records = {}
    sector_records = {}
    for ordinal, ticker in enumerate(tickers):
        observations = []
        close = 100.0 + ordinal
        for index, session in enumerate(calendar):
            if (ticker, session) == missing:
                continue
            # The terms vary by ticker and time, preserving full rank for a small joint fixture.
            close *= 1.0 + 0.001 * (ordinal + 1) + 0.0001 * ((index + ordinal) ** 2)
            observations.append({"session": session, "close": close,
                                 "price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"
                                 if not (mixed_basis and ticker == tickers[0] and index == 0) else "RAW_AS_TRADED"})
        records[ticker] = {"observations": observations}
        shadow_records[ticker] = {"action_readiness_gate": "READY_SHADOW", "shadow_posture": "INITIATE_CANDIDATE" if ordinal == 0 else "ACCUMULATE_CANDIDATE"}
        case_records[ticker] = {"as_of_session": calendar[-1], "entity_class": "corporate"}
        sector_records[ticker] = {"sector_leadership_context": {"group_key": "sector-a" if ordinal < 2 else "sector-b"}}
    return {
        "shadow_readiness": {"artifact_identity": "shadow", "records": shadow_records},
        "research_cases": {"artifact_identity": "cases", "records": case_records},
        "price_snapshot": {"snapshot_identity": "prices", "resolved_completed_session": calendar[-1], "records": records},
        "sector_context": {"artifact_identity": "sectors", "ticker_contexts": sector_records},
    }


class CurrentPortfolioRiskResearchTest(unittest.TestCase):
    def test_frozen_lookback_and_return_contract(self):
        self.assertEqual(STANDARD_RISK_LOOKBACKS, (20, 60, 120, 250))
        self.assertEqual(ANNUALIZATION_SESSIONS, 250)
        self.assertAlmostEqual(simple_close_to_close_returns([100.0, 110.0, 99.0])[0], 0.1)
        self.assertAlmostEqual(simple_close_to_close_returns([100.0, 110.0, 99.0])[1], -0.1)

    def test_exact_window_rejects_one_missing_close(self):
        result = _window_for(ticker="AAA", lookback=20, sessions=[str(item) for item in range(20)],
                             close_index={str(item): 10.0 for item in range(19)}, duplicate_sessions=[], input_problems=[])
        self.assertEqual(result["status"], "UNAVAILABLE_FULL_WINDOW")
        self.assertEqual(result["missing_sessions"], ["19"])

    def test_pairwise_is_unordered_and_joint_guard_is_independent(self):
        artifact = build_artifact(**_inputs())
        self.assertEqual(len(artifact["pairwise_relationships"]), 4)
        pairs = [row for row in artifact["pairwise_relationships"] if row["lookback_sessions"] == 20]
        self.assertTrue(all(row["ticker_i"] < row["ticker_j"] for row in pairs))
        self.assertTrue(all(row["status"] == "PAIRWISE_CORRELATION_READY" for row in pairs))
        self.assertEqual(artifact["joint_matrix_context"]["L20"]["status"], "JOINT_MATRIX_READY")
        self.assertEqual(artifact["joint_matrix_context"]["L60"]["status"], "JOINT_MATRIX_NO_COMPLETE_TICKERS")

    def test_partial_pair_and_basis_conflict_fail_closed(self):
        seeded = _inputs(missing=("AAA", "2026-01-20"))
        artifact = build_artifact(**seeded)
        pair = next(row for row in artifact["pairwise_relationships"] if row["lookback_sessions"] == 20)
        self.assertEqual(pair["status"], "PAIRWISE_PARTIAL_OVERLAP")
        self.assertIsNone(pair["correlation"])
        conflicted = build_artifact(**_inputs(mixed_basis=True))
        self.assertEqual(conflicted["ticker_risk_context"]["AAA"]["volatility_context"]["L20"]["status"], "PRICE_BASIS_CONFLICT")

    def test_joint_guard_blocks_when_dimension_exceeds_observations(self):
        tickers = tuple(f"T{index:02d}" for index in range(20))
        artifact = build_artifact(**_inputs(tickers=tickers, sessions=20))
        joint = artifact["joint_matrix_context"]["L20"]
        self.assertEqual(joint["status"], "JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N")
        self.assertEqual((joint["T"], joint["N"]), (19, 20))
        self.assertIsNone(joint["covariance_matrix"])

    def test_deterministic_identity_and_non_portfolio_boundaries(self):
        first = build_artifact(**_inputs())
        second = build_artifact(**_inputs())
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(content_identity(first)["artifact_sha256"], first["artifact_sha256"])
        boundary = first["authority_boundaries"]
        self.assertEqual(boundary["portfolio_weights"], "NOT_EMITTED")
        self.assertEqual(boundary["position_sizing"], "NOT_EMITTED")
        self.assertEqual(boundary["historical_price_pit"], "BLOCKED")
        self.assertEqual(boundary["raw_as_traded"], "NOT_PROMOTED")
        self.assertTrue(first["validation"]["shadow_posture_unchanged"])
        self.assertTrue(math.isfinite(first["ticker_risk_context"]["AAA"]["volatility_context"]["L20"]["annualized_research_volatility"]))

    def test_retained_real_data_golden_coverage(self):
        root = Path(__file__).resolve().parents[1]
        def load(relative):
            return json.loads((root / relative).read_text(encoding="utf-8"))
        artifact = build_artifact(
            shadow_readiness=load("operations-review/shadow-action-readiness-v1-20260828/artifact.json"),
            research_cases=load("operations-review/thesis-catalyst-downside-and-dual-invalidation-v1-20260828/artifact.json"),
            price_snapshot=load("operations-review/p3f9b-market-wide-exact-session-scaleout-20260825/p3f9b_mva_exact_session_snapshot.json"),
            sector_context=load("operations-review/current-market-sector-leadership-context-v1-20260825/current_market_sector_leadership_context_artifact.json"),
        )
        self.assertEqual(artifact["cohort_summary"]["primary_cohort_count"], 40)
        self.assertEqual(artifact["validation"]["exact_ready_ticker_counts"], {"L20": 40, "L60": 34, "L120": 34, "L250": 26})
        self.assertEqual(artifact["joint_matrix_context"]["L20"]["status"], "JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N")
        self.assertEqual(artifact["joint_matrix_context"]["L60"]["status"], "JOINT_MATRIX_READY")
