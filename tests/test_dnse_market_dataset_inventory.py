from __future__ import annotations

import unittest

import dnse_market_dataset_inventory as inventory
from dnse_market_data import MARKET_DATA_ENDPOINTS


class DatasetInventoryTests(unittest.TestCase):
    def test_every_allowlisted_market_endpoint_is_classified(self):
        entries = inventory.dataset_inventory()
        self.assertEqual(set(MARKET_DATA_ENDPOINTS), {entry["capability"] for entry in entries})
        self.assertTrue(all(entry["classification"] in {
            inventory.READY_FOR_RAW_INGEST, inventory.REQUIRES_REQUEST_CONTRACT_FIX,
            inventory.NOT_APPLICABLE, inventory.DEFERRED,
        } for entry in entries))

    def test_ready_datasets_preserve_unknown_analytical_semantics(self):
        ready = inventory.inventory_by_classification()[inventory.READY_FOR_RAW_INGEST]
        self.assertEqual({"instruments", "ohlc", "working_dates"}, {entry["capability"] for entry in ready})
        self.assertTrue(all("not_promoted" in entry["raw_semantics"] for entry in ready))


if __name__ == "__main__":
    unittest.main()
