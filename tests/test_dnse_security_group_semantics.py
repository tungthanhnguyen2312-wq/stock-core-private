from __future__ import annotations

import unittest

import dnse_security_group_semantics as semantics


def record(*, raw_security_group_id, name, instrument_class="UNKNOWN_SECURITY_GROUP", **overrides):
    base = {"symbol": "X", "raw_security_group_id": raw_security_group_id, "name": name,
            "instrument_class": instrument_class, "exchange_raw": "STO"}
    base.update(overrides)
    return base


class RefineInstrumentClassTests(unittest.TestCase):
    def test_ew_code_maps_to_warrant_even_without_a_populated_name(self):
        # Code-level generalization, matching dnse_instrument_universe.py's own "ST" -> EQUITY
        # method: once a code is evidenced, every member of that code is reclassified, not only
        # the ones whose own name field happens to be populated.
        decision = semantics.refine_instrument_class(
            raw_security_group_id="EW", name=None, current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("WARRANT", decision["instrument_class"])
        self.assertEqual("security_group_id_EW_name_evidence_generalized", decision["refinement_basis"])
        self.assertEqual(semantics.RULE_VERSION, decision["rule_version"])
        self.assertEqual(697, decision["evidence_named_count"])
        self.assertEqual(1346, decision["evidence_total_count"])

    def test_bs_code_maps_to_bond(self):
        decision = semantics.refine_instrument_class(
            raw_security_group_id="BS", name="Trái phiếu Ngân hàng ABC", current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("BOND", decision["instrument_class"])

    def test_ef_code_maps_to_etf(self):
        decision = semantics.refine_instrument_class(
            raw_security_group_id="EF", name="Quỹ ETF ABC", current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("ETF", decision["instrument_class"])

    def test_fu_code_maps_to_derivative(self):
        decision = semantics.refine_instrument_class(
            raw_security_group_id="FU", name="HĐTL chỉ số VN30 1 tháng", current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("DERIVATIVE", decision["instrument_class"])

    def test_mf_code_is_deliberately_not_qualified(self):
        # MF's own evidence mixes generic "Quy dau tu" with ETF-style phrasing -- inconsistent
        # evidence, so it must stay UNKNOWN, not be folded into ETF.
        decision = semantics.refine_instrument_class(
            raw_security_group_id="MF", name="Quỹ đầu tư tăng trưởng ABC", current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("UNKNOWN_SECURITY_GROUP", decision["instrument_class"])
        self.assertNotIn("MF", semantics.EVIDENCE_BY_SECURITY_GROUP_CODE)

    def test_unmapped_code_remains_unknown_regardless_of_name_or_symbol(self):
        decision = semantics.refine_instrument_class(
            raw_security_group_id="ZZ", name="Chứng quyền something-warrant-shaped",
            current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("UNKNOWN_SECURITY_GROUP", decision["instrument_class"])
        self.assertEqual("security_group_id_not_yet_evidenced", decision["refinement_basis"])

    def test_no_code_with_index_name_maps_to_index(self):
        decision = semantics.refine_instrument_class(
            raw_security_group_id=None, name="Chỉ số VNINDEX", current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual(semantics.INDEX, decision["instrument_class"])
        self.assertEqual("security_group_id_absent_name_confirms_index", decision["refinement_basis"])

    def test_no_code_without_index_name_stays_unknown(self):
        decision = semantics.refine_instrument_class(
            raw_security_group_id=None, name="Some Other Thing", current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("UNKNOWN_SECURITY_GROUP", decision["instrument_class"])

    def test_no_code_and_no_name_stays_unknown(self):
        decision = semantics.refine_instrument_class(
            raw_security_group_id=None, name=None, current_instrument_class="UNKNOWN_SECURITY_GROUP")
        self.assertEqual("UNKNOWN_SECURITY_GROUP", decision["instrument_class"])

    def test_already_classified_equity_passes_through_untouched(self):
        # Never overrides anything other than UNKNOWN_SECURITY_GROUP -- in particular, never
        # touches dnse_instrument_universe.py's own "ST" -> EQUITY classification.
        decision = semantics.refine_instrument_class(
            raw_security_group_id="ST", name="HPG", current_instrument_class="EQUITY")
        self.assertEqual("EQUITY", decision["instrument_class"])
        self.assertEqual("not_unknown_security_group", decision["refinement_basis"])


class RefineRecordTests(unittest.TestCase):
    def test_refine_record_preserves_every_other_field(self):
        original = record(raw_security_group_id="EW", name="Chứng quyền mua ACB kỳ hạn 4 tháng của SSI",
                          discovered_at="2026-08-12T10:00:00+07:00", raw_record_json="{}")
        refined = semantics.refine_record(original)
        self.assertEqual("WARRANT", refined["instrument_class"])
        self.assertEqual(original["symbol"], refined["symbol"])
        self.assertEqual(original["exchange_raw"], refined["exchange_raw"])
        self.assertEqual(original["discovered_at"], refined["discovered_at"])
        self.assertEqual(original["raw_security_group_id"], refined["raw_security_group_id"])
        self.assertIn("security_group_refinement", refined)
        self.assertNotIn("security_group_refinement", original)  # input never mutated

    def test_refine_records_preserves_order_and_length(self):
        records = [
            record(raw_security_group_id="ST", name="HPG", instrument_class="EQUITY"),
            record(raw_security_group_id="EW", name=None),
            record(raw_security_group_id="XX", name=None),
        ]
        refined = semantics.refine_records(records)
        self.assertEqual(3, len(refined))
        self.assertEqual(["EQUITY", "WARRANT", "UNKNOWN_SECURITY_GROUP"],
                         [r["instrument_class"] for r in refined])

    def test_refinement_is_deterministic(self):
        records = [record(raw_security_group_id="EW", name=None), record(raw_security_group_id="BS", name=None)]
        first = semantics.refine_records(records)
        second = semantics.refine_records(records)
        self.assertEqual(first, second)

    def test_refinement_summary_counts_resulting_classes(self):
        records = [
            record(raw_security_group_id="EW", name=None),
            record(raw_security_group_id="EW", name=None),
            record(raw_security_group_id="ZZ", name=None),
        ]
        summary = semantics.refinement_summary(semantics.refine_records(records))
        self.assertEqual({"UNKNOWN_SECURITY_GROUP": 1, "WARRANT": 2}, summary)


if __name__ == "__main__":
    unittest.main()
