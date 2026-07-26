import sqlite3
import unittest

import corporate_events_sync as sync


class CorporateEventActionTypeRetentionTests(unittest.TestCase):
    def test_action_type_fields_survive_append_only_ingestion(self):
        conn = sqlite3.connect(":memory:")
        try:
            sync.init_db(conn)
            sync.ingest_events(conn, "HPG", "VCI", [{"id":"a", "ticker":"HPG", "event_code":"DDIND", "action_type_vi":"Mua", "action_type_en":"Buy"}], "2026-07-26T00:00:00+00:00")
            self.assertEqual(conn.execute("SELECT action_type_vi,action_type_en FROM corporate_event_records").fetchone(), ("Mua", "Buy"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
