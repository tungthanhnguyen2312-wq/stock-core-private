import unittest
from opportunity_contract_validation import find_prohibited_fields, validate_no_prohibited_capabilities


class OpportunityContractValidationTests(unittest.TestCase):
    def test_limitation_and_warning_wording_is_not_a_field(self):
        payload={"scenarios":{"base":{"interpretation_limits":["No probability, target price, recommendation, or portfolio position size."],"data_warnings":["recommendation unavailable"]}}}
        self.assertEqual(find_prohibited_fields(payload), [])
        validate_no_prohibited_capabilities(payload)

    def test_real_prohibited_fields_fail(self):
        payload={"scenario_probability":0.5,"target_price":10,"recommendation":"buy","portfolio_position_size":0.1}
        fields=find_prohibited_fields(payload)
        self.assertEqual(len(fields),4)
        with self.assertRaisesRegex(ValueError,"prohibited_opportunity_capability_fields"):
            validate_no_prohibited_capabilities(payload)

    def test_nested_aliases_and_casing_cannot_bypass(self):
        payload={"scenarios":[{"TargetPrice":1,"nested":{"RECOMMENDATIONStatus":"x","portfolioPositionSize":1}}]}
        fields=find_prohibited_fields(payload)
        self.assertEqual(fields,["$.scenarios[0].TargetPrice","$.scenarios[0].nested.RECOMMENDATIONStatus","$.scenarios[0].nested.portfolioPositionSize"])

    def test_valid_hpg_vnm_vcb_shape_passes(self):
        payload={"tickers":{"HPG":{"opportunity_ranking":{"dimensions":{},"interpretation_limits":["No target price."]}},"VNM":{"scenario_analysis":{"scenarios":{"bear":{"state":"unknown"},"base":{"state":"limited"},"bull":{"state":"unknown"}}}},"VCB":{"opportunity_ranking":{"dimensions":{"valuation":{"state":"available"}}}}}}
        validate_no_prohibited_capabilities(payload)

if __name__ == "__main__": unittest.main()
