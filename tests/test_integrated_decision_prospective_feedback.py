from __future__ import annotations

import json

import pytest

import integrated_decision_prospective_feedback as feedback


def _p3f9b(ticker: str, observations: list[dict]) -> dict:
    return {"records": {ticker: {"observations": observations}}}


def _obs(session: str, close: float, price_basis: str = "BASIS_A") -> dict:
    return {"session": session, "close": close, "price_basis": price_basis}


CHAIN = ["2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]


class TestGovernedSessionChain:
    def test_empty_when_directory_missing(self, tmp_path):
        assert feedback.governed_session_chain(tmp_path) == []

    def test_dedupes_and_sorts_real_manifests(self, tmp_path):
        base = tmp_path / "operations-review" / "daily-research-session-operations-v1"
        for session, run_id in [("2026-08-28", "run1"), ("2026-08-28", "run2"), ("2026-08-25", "run3")]:
            d = base / session / run_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "run_manifest.json").write_text(json.dumps({"market_session": session}), encoding="utf-8")
        assert feedback.governed_session_chain(tmp_path) == ["2026-08-25", "2026-08-28"]


class TestForwardHorizon:
    def test_pending_when_not_enough_future_sessions(self):
        p3f9b = _p3f9b("HPG", [_obs(s, 10.0) for s in CHAIN])
        outcome = feedback.evaluate_decision_forward_outcome(decision_record={"ticker": "HPG", "as_of_session": "2026-08-27"}, p3f9b_snapshot=p3f9b, governed_chain=CHAIN)
        assert outcome["horizons"]["forward_close_return_5"]["status"] == feedback.PENDING

    def test_mature_when_horizon_session_available(self):
        # T0 = 2026-08-21 (index 0); T+5 -> index 5 = 2026-08-28
        closes = {s: 10.0 for s in CHAIN}
        closes["2026-08-28"] = 11.0
        p3f9b = _p3f9b("HPG", [_obs(s, closes[s]) for s in CHAIN])
        outcome = feedback.evaluate_decision_forward_outcome(decision_record={"ticker": "HPG", "as_of_session": "2026-08-21"}, p3f9b_snapshot=p3f9b, governed_chain=CHAIN)
        h5 = outcome["horizons"]["forward_close_return_5"]
        assert h5["status"] == feedback.MATURE
        assert h5["future_session"] == "2026-08-28"
        assert h5["return"] == pytest.approx(0.1)

    def test_session_not_in_governed_chain(self):
        p3f9b = _p3f9b("HPG", [_obs(s, 10.0) for s in CHAIN])
        outcome = feedback.evaluate_decision_forward_outcome(decision_record={"ticker": "HPG", "as_of_session": "2025-01-01"}, p3f9b_snapshot=p3f9b, governed_chain=CHAIN)
        assert outcome["horizons"]["forward_close_return_5"]["status"] == feedback.SESSION_NOT_RETAINED

    def test_price_basis_incompatible_is_never_silently_averaged(self):
        obs = [_obs(s, 10.0, price_basis="BASIS_A") for s in CHAIN]
        obs[5] = _obs("2026-08-28", 11.0, price_basis="BASIS_B")
        p3f9b = _p3f9b("HPG", obs)
        outcome = feedback.evaluate_decision_forward_outcome(decision_record={"ticker": "HPG", "as_of_session": "2026-08-21"}, p3f9b_snapshot=p3f9b, governed_chain=CHAIN)
        assert outcome["horizons"]["forward_close_return_5"]["status"] == feedback.PRICE_BASIS_INCOMPATIBLE

    def test_close_path_names_are_never_called_mfe_mae(self):
        closes = {s: 10.0 + i for i, s in enumerate(CHAIN)}
        p3f9b = _p3f9b("HPG", [_obs(s, closes[s]) for s in CHAIN])
        outcome = feedback.evaluate_decision_forward_outcome(decision_record={"ticker": "HPG", "as_of_session": "2026-08-21"}, p3f9b_snapshot=p3f9b, governed_chain=CHAIN)
        close_path = outcome["close_path"]
        assert "max_favorable_close_excursion" in close_path
        assert "max_adverse_close_excursion" in close_path
        assert "mfe" not in close_path and "mae" not in close_path
        assert close_path["semantics"] == "CLOSE_ONLY_PATH_STATISTIC_NOT_TRUE_INTRADAY_MFE_MAE"
        assert close_path["max_favorable_close_excursion"] >= close_path["max_adverse_close_excursion"]


class TestClassifyDecisionFeedback:
    def test_insufficient_when_t5_pending(self):
        outcome = {"horizons": {"forward_close_return_5": {"status": feedback.PENDING, "return": None}}}
        result = feedback.classify_decision_feedback(decision_record={"research_action_posture": "INITIATE_ON_BREAKOUT"}, forward_outcome=outcome)
        assert result["label"] == "INSUFFICIENT_OUTCOME_EVIDENCE"

    def test_good_entry_signal_on_mature_favorable_initiate(self):
        outcome = {"horizons": {"forward_close_return_5": {"status": "MATURE", "return": 0.05}}}
        result = feedback.classify_decision_feedback(decision_record={"research_action_posture": "INITIATE_ON_BREAKOUT"}, forward_outcome=outcome)
        assert result["label"] == "GOOD_ENTRY_SIGNAL"

    def test_adverse_outcome_after_initiation_on_negative_return(self):
        outcome = {"horizons": {"forward_close_return_5": {"status": "MATURE", "return": -0.05}}}
        result = feedback.classify_decision_feedback(decision_record={"research_action_posture": "INITIATE_ON_BREAKOUT"}, forward_outcome=outcome)
        assert result["label"] == "ADVERSE_OUTCOME_AFTER_INITIATION"

    def test_authority_boundary_present(self):
        outcome = {"horizons": {"forward_close_return_5": {"status": "MATURE", "return": 0.01}}}
        result = feedback.classify_decision_feedback(decision_record={"research_action_posture": "HOLD"}, forward_outcome=outcome)
        assert result["authority_boundary"] == "RESEARCH_EVALUATION_LABEL_NOT_CAUSAL_PROOF_OR_WIN_RATE"


class TestBuildProspectiveFeedbackStatus:
    def test_empty_records_is_unavailable(self):
        result = feedback.build_prospective_feedback_status(current_records={}, p3f9b_snapshot=None, governed_chain=[])
        assert result["availability"] == "UNAVAILABLE"

    def test_reports_pending_when_governed_chain_too_short(self):
        records = {"HPG": {"ticker": "HPG", "as_of_session": "2026-08-27", "research_action_posture": "INITIATE_ON_BREAKOUT", "decision_identity": "decision:HPG:x"}}
        result = feedback.build_prospective_feedback_status(current_records=records, p3f9b_snapshot=None, governed_chain=["2026-08-27"])
        assert result["availability"] == "AVAILABLE"
        assert result["outcome_horizons"]["forward_close_return_5"]["status"] == "PENDING_FUTURE_SESSIONS"
        assert "decision_identity" in result["decision_retention"]["every_decision_carries"]
