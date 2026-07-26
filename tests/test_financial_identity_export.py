import unittest

from financial_identity import empty_identity_export


class FinancialIdentityExportTests(unittest.TestCase):
    def test_legacy_runtime_without_retained_observations_exports_no_fake_fields(self):
        self.assertEqual(empty_identity_export(), {
            "status": "unavailable", "records": [],
            "reason": "no_persisted_qualified_financial_identity_observation",
        })


if __name__ == "__main__":
    unittest.main()
