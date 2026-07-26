import tempfile
import unittest
from pathlib import Path

import pandas as pd

from financial_observations import append_observations, canonical_records, observations_from_frame, read_observations


class FinancialObservationsTests(unittest.TestCase):
    def test_ids_schema_idempotency_and_canonical_linkage(self):
        frame=pd.DataFrame([{"item_id":"net_cash_inflows_outflows_from_operating_activities","item":"CFO","item_en":"CFO","2025":0,"2025-Q1":-2}])
        annual=observations_from_frame(frame,ticker="HPG",entity_type="corporate",method="cash_flow",requested_frequency="year",retrieved_at="t",version="4.0.4")
        quarter=observations_from_frame(frame,ticker="HPG",entity_type="corporate",method="cash_flow",requested_frequency="quarter",retrieved_at="t",version="4.0.4")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"observations.jsonl"; self.assertEqual(append_observations(path,annual+quarter)["added"],2); self.assertEqual(append_observations(path,annual+quarter)["added"],0)
            rows=read_observations(path); self.assertNotEqual(rows[0]["observation_id"],rows[1]["observation_id"]); self.assertEqual(rows[0]["statement_scope"],"unknown")
            output=canonical_records(path,{"HPG":"corporate"})["HPG"]; self.assertEqual({r["value"] for r in output},{0,-2}); self.assertTrue(all(r["observation_ids"] for r in output))

    def test_changed_value_is_versioned_not_overwritten(self):
        frame=pd.DataFrame([{"item_id":"cash_and_cash_equivalents","item":"Cash","2025":1}]); a=observations_from_frame(frame,ticker="HPG",entity_type="corporate",method="balance_sheet",requested_frequency="year",retrieved_at="t",version="4.0.4"); frame.loc[0,"2025"]=2; b=observations_from_frame(frame,ticker="HPG",entity_type="corporate",method="balance_sheet",requested_frequency="year",retrieved_at="t",version="4.0.4")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"o.jsonl"; append_observations(path,a+b); self.assertEqual(len(read_observations(path)),2); self.assertEqual(canonical_records(path,{"HPG":"corporate"})["HPG"],[])


if __name__ == "__main__": unittest.main()
