import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

import tactical_reversal_shadow_probe_policy as shadow


def _classifier_record(*, rule_id, entry_state="SELLING_PRESSURE_EASING", entry_action="WAIT",
                        momentum_bucket=None, elevated_volume=None, return_1d=None, close=10.0):
    return {
        "entry_state": entry_state,
        "entry_action": entry_action,
        "rule_id": rule_id,
        "signals": {
            "close": close,
            "momentum_bucket": momentum_bucket,
            "elevated_volume_vs_cohort_median": elevated_volume,
            "return_1d": return_1d,
        },
    }


R8 = "R8_SELLING_PRESSURE_EASING"
R9 = "R9_DOWNTREND_DEFAULT"


class ShadowVerdictTests(unittest.TestCase):
    def test_candidate_a_only(self):
        current = _classifier_record(rule_id=R8, momentum_bucket="UPPER_QUARTILE")
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current)
        self.assertEqual(result["shadow_disposition"], shadow.PROBE_ELIGIBLE)
        self.assertEqual(result["probe_eligible_candidates"], ["CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET"])
        self.assertFalse(result["candidate_verdicts"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]["eligible"])

    def test_candidate_b_only(self):
        current = _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")
        prior = _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE")
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current, prior_record=prior)
        self.assertEqual(result["shadow_disposition"], shadow.PROBE_ELIGIBLE)
        self.assertEqual(result["probe_eligible_candidates"], ["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"])
        self.assertFalse(result["candidate_verdicts"]["CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET"]["eligible"])

    def test_both_candidates_eligible(self):
        current = _classifier_record(rule_id=R8, momentum_bucket="UPPER_MIDDLE")
        prior = _classifier_record(rule_id=R8, momentum_bucket="UPPER_MIDDLE")
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current, prior_record=prior)
        self.assertEqual(result["shadow_disposition"], shadow.PROBE_ELIGIBLE)
        self.assertCountEqual(result["probe_eligible_candidates"], list(shadow.ELIGIBLE_CANDIDATES))

    def test_neither_candidate_eligible(self):
        current = _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE", elevated_volume=False, return_1d=-0.01)
        prior = _classifier_record(rule_id=R9)
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current, prior_record=prior)
        self.assertEqual(result["shadow_disposition"], shadow.NOT_PROBE_ELIGIBLE)
        self.assertEqual(result["probe_eligible_candidates"], [])

    def test_non_r8_state_is_not_probe_eligible_not_not_evaluable(self):
        current = _classifier_record(rule_id="R3_UPTREND_CONFIRMED_DEFAULT", entry_state="UPTREND_CONFIRMED", entry_action="ADD_ON_STRENGTH")
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current)
        self.assertEqual(result["shadow_disposition"], shadow.NOT_PROBE_ELIGIBLE)


class PanVetoRegressionTests(unittest.TestCase):
    """Locks in the exact real PAN 2026-09-08/09/10 outcome from the retained artifacts."""

    SESSION_08 = _classifier_record(rule_id=R9, entry_state="DOWNTREND", entry_action="AVOID", momentum_bucket="LOWER_MIDDLE", elevated_volume=True, return_1d=-0.0159)
    SESSION_09 = _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE", elevated_volume=True, return_1d=0.0081)
    SESSION_10 = _classifier_record(rule_id=R9, entry_state="DOWNTREND", entry_action="AVOID", momentum_bucket="LOWER_MIDDLE", elevated_volume=True, return_1d=-0.008)

    def test_pan_2026_09_09_is_never_probe_eligible_under_the_shadow_policy(self):
        result = shadow.evaluate_shadow_probe(
            ticker="PAN", session="2026-09-09", current_record=self.SESSION_09, prior_record=self.SESSION_08,
        )
        self.assertEqual(result["shadow_disposition"], shadow.NOT_PROBE_ELIGIBLE)
        self.assertEqual(result["probe_eligible_candidates"], [])
        self.assertEqual(
            result["candidate_verdicts"]["CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET"]["reason_codes"],
            ["R8_MOMENTUM_BUCKET_NOT_UPPER_HALF"],
        )
        self.assertEqual(
            result["candidate_verdicts"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]["reason_codes"],
            ["PRIOR_SESSION_NOT_R8_NO_PERSISTENCE"],
        )

    def test_pan_2026_09_10_deterioration_is_not_probe_eligible(self):
        result = shadow.evaluate_shadow_probe(ticker="PAN", session="2026-09-10", current_record=self.SESSION_10, prior_record=self.SESSION_09)
        self.assertEqual(result["shadow_disposition"], shadow.NOT_PROBE_ELIGIBLE)
        self.assertEqual(result["source_classifier_state"]["rule_id"], R9)

    def test_candidate_c_is_named_as_excluded_and_never_evaluated(self):
        result = shadow.evaluate_shadow_probe(ticker="PAN", session="2026-09-09", current_record=self.SESSION_09, prior_record=self.SESSION_08)
        self.assertNotIn("CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE", result["candidate_verdicts"])
        self.assertIn("CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE", result["excluded_candidates"])
        self.assertIn("PROBE_ELIGIBLE", result["excluded_candidates"]["CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE"])


class MissingHistoryAndUnevaluableTests(unittest.TestCase):
    def test_no_prior_evidence_supplied_at_all_marks_persistence_unevaluable(self):
        current = _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE", elevated_volume=False, return_1d=-0.01)
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current, prior_evidence_supplied=False)
        b_verdict = result["candidate_verdicts"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]
        self.assertIsNone(b_verdict["eligible"])
        self.assertEqual(result["shadow_disposition"], shadow.PARTIALLY_UNEVALUABLE)
        self.assertEqual(result["unevaluable_candidates"], ["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"])

    def test_a_genuine_prior_session_gap_is_distinguished_from_no_evidence_supplied(self):
        current = _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE", elevated_volume=False, return_1d=-0.01)
        gap_result = shadow.evaluate_shadow_probe(
            ticker="XXX", session="2026-09-09", current_record=current, prior_record=None, prior_evidence_supplied=True,
        )
        no_lookup_result = shadow.evaluate_shadow_probe(
            ticker="XXX", session="2026-09-09", current_record=current, prior_record=None, prior_evidence_supplied=False,
        )
        gap_reason = gap_result["candidate_verdicts"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]["reason_codes"]
        no_lookup_reason = no_lookup_result["candidate_verdicts"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]["reason_codes"]
        self.assertIn("PRIOR_SESSION_GAP", gap_reason)
        self.assertIn("NO_PRIOR_SESSION_EVIDENCE", no_lookup_reason)

    def test_source_classifier_state_unavailable_falls_back_without_fabrication(self):
        current = _classifier_record(rule_id=shadow.R0_RULE_ID, entry_state=None, entry_action="WAIT")
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current)
        self.assertEqual(result["shadow_disposition"], shadow.NOT_EVALUABLE)
        self.assertEqual(result["fallback_reason"], "SOURCE_CLASSIFIER_STATE_UNAVAILABLE")
        self.assertEqual(result["probe_eligible_candidates"], [])


class UnchangedProductionOutputTests(unittest.TestCase):
    def test_source_classifier_fields_are_echoed_verbatim_and_never_mutated(self):
        current = _classifier_record(rule_id=R8, entry_state="SELLING_PRESSURE_EASING", entry_action="WAIT", momentum_bucket="LOWER_MIDDLE")
        prior = _classifier_record(rule_id=R9, entry_state="DOWNTREND", entry_action="AVOID")
        before_current, before_prior = copy.deepcopy(current), copy.deepcopy(prior)
        result = shadow.evaluate_shadow_probe(ticker="XXX", session="2026-09-09", current_record=current, prior_record=prior)
        self.assertEqual(current, before_current)
        self.assertEqual(prior, before_prior)
        self.assertEqual(result["source_classifier_state"], {
            "entry_state": "SELLING_PRESSURE_EASING", "entry_action": "WAIT", "rule_id": R8,
        })
        self.assertTrue(result["classifier_state_unchanged"])
        self.assertTrue(result["no_probability_target_or_sizing_emitted"])
        self.assertEqual(result["authority"], "SHADOW_ONLY / NOT_PRODUCTION_POLICY")

    def test_evaluate_shadow_probe_never_invokes_the_classifier(self):
        self.assertNotIn("watchlist_tactical_entry_classifier", shadow.__dict__)
        import inspect
        source = inspect.getsource(shadow)
        self.assertNotIn("import watchlist_tactical_entry_classifier", source)
        self.assertNotIn("_entry_state_rule", source)
        self.assertNotIn("RULE_DEFINITIONS =", source)


class ShadowArtifactTests(unittest.TestCase):
    def _tactical_artifact(self, *, session, records):
        return {"session": session, "artifact_identity": f"watchlist_tactical_entry_classifier:fake-{session}", "records": records}

    def test_build_shadow_artifact_annotates_every_ticker_and_counts_dispositions(self):
        current = self._tactical_artifact(session="2026-09-09", records={
            "AAA": _classifier_record(rule_id=R8, momentum_bucket="UPPER_QUARTILE"),
            "BBB": _classifier_record(rule_id=R9),
            "PAN": self._pan_09(),
        })
        prior = self._tactical_artifact(session="2026-09-08", records={
            "AAA": _classifier_record(rule_id=R9),
            "PAN": self._pan_08(),
        })
        artifact = shadow.build_shadow_artifact(session="2026-09-09", current_tactical_artifact=current, prior_session="2026-09-08", prior_tactical_artifact=prior)
        self.assertEqual(set(artifact["records"]), {"AAA", "BBB", "PAN"})
        self.assertEqual(artifact["records"]["AAA"]["shadow_disposition"], shadow.PROBE_ELIGIBLE)
        self.assertEqual(artifact["records"]["BBB"]["shadow_disposition"], shadow.NOT_PROBE_ELIGIBLE)
        self.assertEqual(artifact["records"]["PAN"]["shadow_disposition"], shadow.NOT_PROBE_ELIGIBLE)
        self.assertEqual(sum(artifact["disposition_counts"].values()), 3)
        self.assertTrue(artifact["authority_boundary"]["shadow_only"])
        self.assertFalse(artifact["authority_boundary"]["classifier_invoked"])
        self.assertFalse(artifact["authority_boundary"]["classifier_policy_changed"])

    def test_missing_ticker_in_prior_artifact_is_a_genuine_gap(self):
        current = self._tactical_artifact(session="2026-09-09", records={
            "CCC": _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE", elevated_volume=False, return_1d=-0.01),
        })
        prior = self._tactical_artifact(session="2026-09-08", records={})
        artifact = shadow.build_shadow_artifact(session="2026-09-09", current_tactical_artifact=current, prior_session="2026-09-08", prior_tactical_artifact=prior)
        b_verdict = artifact["records"]["CCC"]["candidate_verdicts"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]
        self.assertIsNone(b_verdict["eligible"])
        self.assertIn("PRIOR_SESSION_GAP", b_verdict["reason_codes"])

    def test_deterministic_repeated_builds_are_byte_identical(self):
        current = self._tactical_artifact(session="2026-09-09", records={"AAA": _classifier_record(rule_id=R8, momentum_bucket="UPPER_QUARTILE")})
        first = shadow.build_shadow_artifact(session="2026-09-09", current_tactical_artifact=current)
        second = shadow.build_shadow_artifact(session="2026-09-09", current_tactical_artifact=current)
        self.assertEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(first, second)

    @staticmethod
    def _pan_08():
        return _classifier_record(rule_id=R9, entry_state="DOWNTREND", entry_action="AVOID", momentum_bucket="LOWER_MIDDLE", elevated_volume=True, return_1d=-0.0159)

    @staticmethod
    def _pan_09():
        return _classifier_record(rule_id=R8, momentum_bucket="LOWER_MIDDLE", elevated_volume=True, return_1d=0.0081)


class RuntimePreconditionTests(unittest.TestCase):
    def setUp(self):
        import os
        self._saved_env = os.environ.pop("STOCK_LOOKUP_RUNTIME_ROOT", None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        import os
        if self._saved_env is None:
            os.environ.pop("STOCK_LOOKUP_RUNTIME_ROOT", None)
        else:
            os.environ["STOCK_LOOKUP_RUNTIME_ROOT"] = self._saved_env

    def test_missing_database_is_reported_as_a_blocker_not_raised(self):
        sys_path_root = Path(__file__).resolve().parents[1] / "tools"
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_shadow_tool", sys_path_root / "run_tactical_reversal_shadow_probe_policy.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = module.verify_runtime_precondition(Path(temp_dir))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "RUNTIME_CAPABILITY_VN_STOCK_DB_MISSING")

    def test_present_database_is_verified_read_only_without_writing(self):
        sys_path_root = Path(__file__).resolve().parents[1] / "tools"
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_shadow_tool", sys_path_root / "run_tactical_reversal_shadow_probe_policy.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connection = sqlite3.connect(root / "vn_stock.db")
            connection.execute("CREATE TABLE ohlcv(ticker TEXT)")
            connection.commit()
            connection.close()
            result = module.verify_runtime_precondition(root)
        self.assertEqual(result["status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
