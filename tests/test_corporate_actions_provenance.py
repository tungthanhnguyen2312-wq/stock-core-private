import unittest

from corporate_actions_export import build_corporate_actions_section


class CorporateActionsProvenanceTests(unittest.TestCase):
    def test_existing_event_provenance_reaches_canonical_record(self):
        coverage = "partial_unqualified_50_row_cap"
        source_provenance = {"provider":"VCI", "vnstock_version":"4.0.4", "endpoint":"Company.events", "parameters":{}, "retrieved_at":"t", "raw_payload_hash":"h"}
        result = build_corporate_actions_section({"status":"partial", "coverage_status":coverage, "sources":[{"source_name":"VCI", "coverage_status":coverage, "records":[{"provider_event_id":"d", "fields":{"event_code":"DIV", "event_name_en":"Cash Dividend", "value_per_share":1}, "provenance":source_provenance}]}]})
        self.assertEqual(result["sources"][0]["records"][0]["provenance"], {**source_provenance, "event_source":"corporate_events"})


if __name__ == "__main__":
    unittest.main()
