import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from official_evidence import load_cited_financial_records


class OfficialEvidenceTests(unittest.TestCase):
    def _runtime(self, valid_hash=True):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        evidence = root / "data" / "official-evidence"
        evidence.mkdir(parents=True)
        pdf = evidence / "hpg.pdf"
        pdf.write_bytes(b"qualified document")
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest() if valid_hash else "bad"
        (evidence / "manifest.json").write_text(json.dumps({"schema_version":"1.0.0","records":[{"evidence_id":"e1","ticker":"HPG","reporting_period":"2025","qualification_state":"qualified","filename":"hpg.pdf","sha256":digest,"source_url":"https://example.test/hpg.pdf","retrieved_at":"2026-07-26T00:00:00+07:00"}]}), encoding="utf-8")
        return tmp, root

    def test_hpg_cited_facts_are_deterministic_and_consolidated(self):
        tmp, root = self._runtime()
        with tmp:
            one = load_cited_financial_records(root, "HPG")
            self.assertEqual(one, load_cited_financial_records(root, "HPG"))
            self.assertEqual(one["status"], "available")
            self.assertEqual({r["canonical_metric"] for r in one["records"]}, {"revenue", "total_assets", "shareholders_equity"})
            self.assertTrue(all(r["statement_scope"] == "consolidated" and r["official_evidence"]["page"] == 35 for r in one["records"]))

    def test_hash_mismatch_fails_closed(self):
        tmp, root = self._runtime(valid_hash=False)
        with tmp:
            result = load_cited_financial_records(root, "HPG")
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["records"], [])


if __name__ == "__main__":
    unittest.main()
