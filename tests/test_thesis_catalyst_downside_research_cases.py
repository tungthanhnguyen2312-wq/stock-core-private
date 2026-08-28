from __future__ import annotations

import unittest

from thesis_catalyst_downside_research_cases import _terminal_set_proof, build_artifact


def _record(*, state="BREAKOUT_READY", quality_band="HIGH_QUALITY", percentile=.9, valuation=True):
    axes = {axis: {"axis_status": "READY_RESEARCH_ONLY", "score": .9, "method": "axis/v1", "evidence_tier": "OPERATIONAL_PROXY"}
            for axis in ("PROFITABILITY_QUALITY", "CAPITAL_EFFICIENCY", "BALANCE_SHEET_TRAJECTORY")}
    rank = "STRONG" if state in {"BREAKOUT_READY", "UPTREND_CONFIRMED"} else "WEAK" if state == "DOWNTREND" else "EARLY_REVERSAL"
    return {"ticker": "AAA", "entity_class": "corporate", "sector": "corporate", "market_session": "2026-08-25",
            "fundamental_axes": axes,
            "fundamental_quality": {"status": "READY_RESEARCH_ONLY", "quality_band": quality_band,
                                    "actual_comparable_cohort_percentile": percentile, "method": "quality/v1"},
            "market_technical_strength": {"status": "READY_RESEARCH_ONLY", "market_technical_rank": rank,
                                          "momentum_20d": .1, "method": "technical/v1"},
            "tactical_setup": {"state": state, "rule_id": "R1", "method": "tactical/v1"},
            "relative_value": {"status": "READY_RESEARCH_ONLY" if valuation else "INSUFFICIENT_INPUTS",
                               "size_context": {"market_cap": {"status": "READY", "value": 1}, "enterprise_value": {"status": "READY", "value": 2}}},
            "research_classifications": {"SUPER_SETUP_RESEARCH": {"status": "PRESENT" if state == "BREAKOUT_READY" and percentile >= .8 else "NOT_PRESENT"},
                                        "HIGH_RISK_SPECULATION": {"status": "RESEARCH_WARNING" if percentile <= .25 and state == "BREAKOUT_READY" else "NOT_PRESENT"}},
            "opportunity_lanes": ["VALUE_WITH_CONFIRMATION"] if valuation else [],
            "opportunity_research_priority": {"bucket": "HIGH_QUALITY_WEAK_SETUP" if state == "DOWNTREND" else "HIGH_QUALITY_STRONG_SETUP"},
            "data_confidence": {"status": "READY_RESEARCH_ONLY", "score": .1}, "warnings": []}


def _ttm(*, compatible=True):
    income = {"provider": "KBS", "statement_scope": "consolidated", "currency": "unknown", "scale": "unknown", "method": "TTM_ROLLING_4_STANDALONE_QUARTERS"}
    revenue = dict(income)
    if not compatible:
        revenue["statement_scope"] = "separate"
    return {"status": "AVAILABLE", "ttm": {"net_income": income, "revenue": revenue},
            "derived_metrics": {"ttm_net_margin": {"status": "AVAILABLE", "value": .25, "method": "TTM_NET_INCOME_DIVIDED_BY_TTM_REVENUE", "evidence_tier": "OPERATIONAL_PROXY"}}}


class ThesisCatalystDownsideCasesTest(unittest.TestCase):
    def _build(self, record=None, events=None, ttm=None):
        return build_artifact(opportunity={"artifact_identity": "opp", "records": {"AAA": record or _record()}},
                              events={"artifact_identity": "events", "records": {"AAA": events or {"events": [], "research_session": "2026-08-21"}}},
                              ttm={"artifact_identity": "ttm", "records": {"AAA": ttm or {}}})

    def test_optional_contexts_do_not_block_case_and_identity_is_deterministic(self):
        artifact = self._build(record=_record(valuation=False))
        record = artifact["records"]["AAA"]
        self.assertEqual(record["terminal_disposition"], "OPPORTUNITY_CASE_ELIGIBLE")
        self.assertEqual(record["catalyst_status"], "NO_QUALIFIED_CATALYST")
        self.assertIn({"dimension": "VALUATION", "status": "EVIDENCE_GAP", "reason": "OPTIONAL_CONTEXT_UNAVAILABLE"}, record["evidence_gaps"])
        self.assertEqual(artifact["artifact_sha256"], self._build(record=_record(valuation=False))["artifact_sha256"])

    def test_technical_is_never_a_corporate_catalyst_and_level_is_not_fabricated(self):
        record = self._build()["records"]["AAA"]
        self.assertEqual(record["market_confirmation_trigger"]["trigger_type"], "MARKET_CONFIRMATION_TRIGGER")
        self.assertEqual(record["catalysts"], [])
        self.assertEqual(record["technical_invalidation"]["status"], "CONDITIONAL")
        self.assertIsNone(record["technical_invalidation"]["threshold"])

    def test_strong_weak_and_high_risk_archetypes_remain_distinct(self):
        self.assertEqual(self._build()["records"]["AAA"]["thesis_archetype"], "QUALITY_BREAKOUT_THESIS")
        weak = self._build(record=_record(state="DOWNTREND"))["records"]["AAA"]
        self.assertEqual(weak["thesis_archetype"], "HIGH_QUALITY_WAIT_THESIS")
        risk = self._build(record=_record(percentile=.2))["records"]["AAA"]
        self.assertEqual(risk["thesis_archetype"], "HIGH_RISK_SPECULATION_THESIS")
        self.assertTrue(risk["counter_thesis_evidence"])

    def test_margin_trigger_is_relative_margin_led_and_requires_compatible_inputs(self):
        record = self._build(ttm=_ttm())["records"]["AAA"]
        invalidation = record["fundamental_invalidation"]
        self.assertEqual(invalidation["trigger_type"], "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT")
        self.assertEqual(invalidation["threshold"], .2)
        self.assertNotIn("AUDIT_RISK_ESCALATION", str(record))
        incompatible = self._build(ttm=_ttm(compatible=False))["records"]["AAA"]
        self.assertNotEqual(incompatible["fundamental_invalidation"]["status"], "READY")
        non_margin = self._build(record=_record(percentile=.2), ttm=_ttm())["records"]["AAA"]
        self.assertNotEqual(non_margin["fundamental_invalidation"].get("trigger_type"), "NET_MARGIN_RELATIVE_DRAWDOWN_20PCT")

    def test_historical_or_unlinked_event_is_context_only_and_no_authority_is_emitted(self):
        events = {"research_session": "2026-08-21", "events": [{"event_status": "CONFIRMED_UPCOMING", "event_type": "CASH_DIVIDEND", "evidence_tier": "OFFICIAL_QUALIFIED", "source": "issuer", "source_record_identity": "x", "warnings": []}]}
        record = self._build(events=events)["records"]["AAA"]
        self.assertEqual(record["catalyst_status"], "NO_QUALIFIED_CATALYST")
        self.assertEqual(record["catalysts"], [])
        self.assertEqual(record["retained_event_context"][0]["context_status"], "RETAINED_EVENT_CONTEXT")
        self.assertTrue(record["authority_boundaries"]["case_is_not_decision_authority"])

    def test_qualified_catalyst_requires_explicit_temporal_and_thesis_linkage(self):
        events = {"research_session": "2026-08-21", "events": [{
            "event_id": "event:1", "event_status": "CONFIRMED_UPCOMING", "event_type": "CORPORATE_ACTION",
            "evidence_tier": "OFFICIAL_QUALIFIED", "source": "issuer", "source_record_identity": "x",
            "effective_date": "2026-09-01", "known_at": "2026-08-20", "thesis_linkage": "capacity pathway",
            "causal_thesis_reason": "The retained action explicitly advances the stated pathway.", "warnings": [],
        }]}
        record = self._build(events=events)["records"]["AAA"]
        self.assertEqual(record["catalyst_status"], "QUALIFIED_CATALYST_AVAILABLE")
        catalyst = record["catalysts"][0]
        self.assertEqual(catalyst["effective_or_expected_date"], "2026-09-01")
        self.assertEqual(catalyst["thesis_linkage"], "capacity pathway")

    def test_market_only_and_terminal_reconciliation(self):
        source = _record()
        source["fundamental_quality"] = {"status": "INSUFFICIENT_INPUTS"}
        artifact = self._build(record=source)
        self.assertEqual(artifact["records"]["AAA"]["terminal_disposition"], "MARKET_ONLY_RESEARCH_CASE")
        self.assertEqual(artifact["denominator"], 1)
        self.assertEqual(artifact["residual"], 0)

    def test_terminal_dispositions_are_disjoint_and_cover_the_denominator(self):
        market_only = _record()
        market_only["fundamental_quality"] = {"status": "INSUFFICIENT_INPUTS"}
        insufficient = _record()
        insufficient["market_technical_strength"] = {"status": "INSUFFICIENT_INPUTS"}
        artifact = build_artifact(
            opportunity={"records": {"AAA": _record(), "BBB": market_only, "CCC": insufficient}},
            events={"records": {}}, ttm={"records": {}},
        )
        proof = artifact["terminal_disposition_reconciliation"]
        self.assertEqual(proof["union_count"], artifact["denominator"])
        self.assertEqual(proof["residual"], 0)
        self.assertTrue(all(not intersection for intersection in proof["pairwise_intersections"].values()))
        self.assertEqual(sum(artifact["coverage"]["terminal_dispositions"].values()), artifact["denominator"])
        self.assertEqual(set(artifact["coverage"]["terminal_dispositions"]), {
            "OPPORTUNITY_CASE_ELIGIBLE", "MARKET_ONLY_RESEARCH_CASE", "INSUFFICIENT_CASE_EVIDENCE",
        })
        self.assertNotIn("has_market_confirmation_trigger", artifact["coverage"]["terminal_dispositions"])
        with self.assertRaisesRegex(ValueError, "TERMINAL_DISPOSITION_SET_RECONCILIATION_FAILED"):
            _terminal_set_proof({"BAD": {"terminal_disposition": "NOT_A_TERMINAL_DISPOSITION"}})
