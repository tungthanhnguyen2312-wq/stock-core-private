"""DATA_INTEGRITY_AND_TACTICAL_REFERENCE_INTEGRATION_V1.

session_bar_integrity is the only duplicate policy. The tactical reference window, the momentum
context, and technical-history recovery selection delegate to it instead of keeping their own
field lists. ACG (2026-09-16) is the regression: its two 2026-09-15 bars differ only in ``high``
(31.20 vs 31.19), which the pre-integration tactical rule -- close, volume, basis and
transformation only -- treated as an exact copy.
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

import market_wide_current_technical_coverage_scaleout as recovery_module
import session_bar_integrity as integrity
import tactical_reference_window as window
import technical_structure_context as structure_module
from test_session_bar_integrity import PRIOR, TARGET, _pipeline, _series, _with_copy_after

REPO = Path(__file__).resolve().parents[1]
UP = [20.0 + 0.1 * i for i in range(60)]


class SingleDuplicatePolicyTests(unittest.TestCase):
    def test_the_window_keeps_no_duplicate_rule_of_its_own(self) -> None:
        source = (REPO / "tactical_reference_window.py").read_text(encoding="utf-8")
        self.assertFalse(hasattr(window, "collapse_exact_duplicate_sessions"))
        self.assertNotIn("_DUPLICATE_IDENTITY_FIELDS", source)
        self.assertIn("session_bar_integrity.resolve_session_bars", source)
        self.assertEqual(window.INTEGRITY_BLOCKERS, frozenset({integrity.REFUSAL_REASON, window.BLOCKER_MIXED_PRICE_BASIS}))
        momentum_source = (REPO / "tactical_momentum_context.py").read_text(encoding="utf-8")
        self.assertNotIn("collapse_exact_duplicate_sessions", momentum_source)

    def test_window_delegation_matches_the_shared_function_row_for_row(self) -> None:
        clean = _series(UP)
        rows = lambda obs: [{"date": o["session"], "close": o["close"], "volume": o["volume"],  # noqa: E731
                             "price_basis": o["price_basis"], "transformation_identity": o["transformation_identity"]} for o in obs]
        self.assertEqual(window.reference_values(rows(_with_copy_after(clean, PRIOR)), as_of_session=TARGET),
                         window.reference_values(rows(clean), as_of_session=TARGET))
        conflicting = window.reference_values(rows(_with_copy_after(clean, PRIOR, volume=1)), as_of_session=TARGET)
        self.assertEqual(conflicting["blockers"], [integrity.REFUSAL_REASON])


class AcgRegressionTests(unittest.TestCase):
    """A duplicate differing only in a field the tactical window never reads is still a conflict."""

    @classmethod
    def setUpClass(cls) -> None:
        clean = _series(UP)
        cls.acg = _with_copy_after(clean, PRIOR, high=next(o["high"] for o in clean if o["session"] == PRIOR) - 0.01)
        cls.built = _pipeline({"ACG": cls.acg, "CLN": clean})

    def test_acg_shape_is_a_conflict_under_the_shared_definition(self) -> None:
        resolution = integrity.resolve_session_bars(self.acg, as_of_session=TARGET)
        self.assertEqual(resolution["status"], integrity.CONFLICTING_DUPLICATE_REFUSED)
        self.assertEqual(resolution["conflicting_fields"], {PRIOR: ["high"]})

    def test_every_consumer_refuses_acg_with_one_reason(self) -> None:
        technical = self.built["descriptive"]["records"]["ACG"]["technical_features"]
        self.assertEqual((technical["status"], technical["blockers"]), ("MISSING", [integrity.REFUSAL_REASON]))
        self.assertEqual(self.built["structure"]["records"]["ACG"]["eligibility"]["status"], "NOT_ELIGIBLE")
        self.assertEqual(self.built["momentum"]["records"]["ACG"]["eligibility"]["status"], "NOT_ELIGIBLE")
        self.assertEqual(self.built["rvol"]["records"]["ACG"]["reason"], integrity.REFUSAL_REASON)
        self.assertEqual(self.built["historical"]["ACG"]["drawdown"]["reason"], integrity.REFUSAL_REASON)
        self.assertEqual(self.built["descriptive"]["records"]["CLN"]["technical_features"]["status"], "SHADOW_ONLY")


class SharedSeriesTests(unittest.TestCase):
    def test_structural_momentum_and_classifier_series_are_the_same_resolved_series(self) -> None:
        clean = _series(UP)
        run = _pipeline({"EXA": _with_copy_after(clean, PRIOR)})
        resolved, source = structure_module.resolve_target_session_observations(
            pf_record=run["pf"]["records"]["EXA"], recovery_override=None, target_session=TARGET)
        self.assertEqual(source, "P3F9B_EXACT_SESSION_RECORD")
        sessions = [o["session"] for o in resolved["observations"]]
        self.assertEqual(len(sessions), len(set(sessions)))
        self.assertEqual(run["structure"]["records"]["EXA"]["close_history_depth"], len(clean))
        self.assertEqual(run["momentum"]["records"]["EXA"]["close_history_depth"], len(clean))
        values = run["descriptive"]["records"]["EXA"]["technical_features"]["values"]
        reference = run["momentum"]["records"]["EXA"]["reference_window"]
        self.assertEqual(values["ma_20"], reference["ma_20"])
        self.assertEqual(values["momentum_20d"], reference["momentum_20d"])
        self.assertEqual(values["ma_20"], sum(UP[-20:]) / 20)
        self.assertEqual(run["momentum"]["records"]["EXA"]["moving_averages"]["20"]["value"], values["ma_20"])


class RecoveryUsesTheSharedPolicyTests(unittest.TestCase):
    def _baseline_and_snapshot(self, observations):
        from test_session_bar_integrity import _pipeline as pipeline
        run = pipeline({"ACG": observations})
        return run["descriptive"], run["pf"]

    def test_refused_record_is_a_recovery_candidate_even_when_projected_rows_look_identical(self) -> None:
        clean = _series(UP)
        acg = _with_copy_after(clean, PRIOR, high=99.0)
        baseline, _ = self._baseline_and_snapshot(clean)  # prior-session descriptive: ticker was fine
        _, snapshot = self._baseline_and_snapshot(acg)
        self.assertEqual(recovery_module.recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=snapshot), ["ACG"])
        _, exact_snapshot = self._baseline_and_snapshot(_with_copy_after(clean, PRIOR))
        self.assertEqual(recovery_module.recovery_candidates(baseline_artifact=baseline, p3f9b_snapshot=exact_snapshot), [])

    def test_contradictory_refetch_is_not_labelled_lifetime_insufficiency(self) -> None:
        import mva_exact_session_snapshot
        clean = _series(UP)
        epochs = [mva_exact_session_snapshot.datetime.fromisoformat(f"{o['session']}T00:00:00+07:00").timestamp() for o in clean]
        body = {"t": epochs, "o": [o["open"] for o in clean], "h": [o["high"] for o in clean], "l": [o["low"] for o in clean],
                "c": [o["close"] for o in clean], "v": [o["volume"] for o in clean]}
        index = [o["session"] for o in clean].index(PRIOR)
        conflicting = copy.deepcopy(body)
        for key in conflicting:
            conflicting[key].insert(index + 1, conflicting[key][index] + (3600 if key == "t" else 0))
        conflicting["c"][index + 1] += 1.0
        query = {"symbol": "ACG", "resolution": "1D", "from": 1, "to": 2, "type": "STOCK"}
        record = recovery_module.recovery_record(ticker="ACG", response={"ok": True, "body": conflicting}, target_session=TARGET,
                                                 query=query, retrieved_at="2026-09-16T18:00:00+07:00")
        self.assertEqual((record["state"], record["reason"]), ("SESSION_BAR_CONFLICT_REFUSED", integrity.REFUSAL_REASON))
        clean_record = recovery_module.recovery_record(ticker="ACG", response={"ok": True, "body": body}, target_session=TARGET,
                                                       query=query, retrieved_at="2026-09-16T18:00:00+07:00")
        self.assertEqual(clean_record["state"], "RECOVERED_COMPLETE_TECHNICAL_HISTORY")


if __name__ == "__main__":
    unittest.main()
