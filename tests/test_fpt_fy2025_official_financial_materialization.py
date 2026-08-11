import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fpt_fy2025_official_financial_materialization as fpt  # noqa: E402
import evidence_promotion as promotion  # noqa: E402
from canonical_financial_qualification_policy import load_evidence_index  # noqa: E402
from official_annual_financial_fact_projection import facts_for_ticker  # noqa: E402
from research_financial_fact_projection import build_projection  # noqa: E402


class FptFy2025OfficialFinancialMaterializationTests(unittest.TestCase):
    def test_builds_exact_five_hash_bound_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "documents" / "FPT" / "2025" / "audited" / "fpt.pdf"
            document.parent.mkdir(parents=True)
            document.write_bytes(b"immutable FPT FY2025 fixture")
            sha256 = hashlib.sha256(document.read_bytes()).hexdigest()
            document_id = "fpt-fixture-document"
            record = {
                "ticker": "FPT", "document_id": document_id, "sha256": sha256, "acquisition_status": "retained",
                "relative_path": document.relative_to(root).as_posix(), "source_authority": "issuer_ir",
                "canonical_url": "https://fpt.com/ir/fpt-fy2025.pdf", "document_class": "audited_annual_financial_statements",
                "reporting_period": "2025", "published_at": "2026-03-19", "observed_at": "2026-08-11T00:00:00Z", "source_id": "issuer_ir",
            }
            (root / "official_document_acquisition_manifest.json").write_text(json.dumps({"records": [record]}), encoding="utf-8")
            texts = {
                8: "Ti\u00e9n va cac khoan tuong dwong ti\u00e9n 10.522.105.729.992",
                10: "Vay v\u00e0 n\u1ee3 thu\u00ea t\u00e0i ch\u00ednh ng\u1eafn h\u1ea1n 19.169.697.497.955\nVay va no\u2019 thu\u00e9 tai chinh dai han 1.903.789.988.184",
                11: "VON CHU SO H\u1eeeU 43.748.040.747.539",
                12: "Loi nhuan sau thu\u00e9 TNDN 11.232.339.450.734",
                13: "Luu chuy\u00e9n ti\u00e9n thuan tir hoat d\u00e9ng kinh doanh 10.136.043.915.911",
            }
            pages = [{"page": page, "status": "ocr_available", "text": text,
                      "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "document_id": document_id,
                      "document_sha256": sha256, "materialization_id": f"page-{page}", "ocr_engine": "fixture", "render_dpi": 240}
                     for page, text in texts.items()]
            sidecar = root / "derived" / "annual_financial_ocr_materialization_v1" / "fpt-fy2025.json"
            sidecar.parent.mkdir(parents=True)
            sidecar.write_text(json.dumps({"document_id": document_id, "document_sha256": sha256, "pages": pages}), encoding="utf-8")
            with patch.object(fpt, "FPT_FY2025_DOCUMENT_ID", document_id), patch.object(fpt, "FPT_FY2025_SHA256", sha256):
                manifests, citations = fpt.build_fpt_fy2025_promotion(root)
                self.assertEqual(len(manifests), 1)
                self.assertEqual({row["metric"] for row in citations}, {
                    "cash_and_equivalents", "shareholders_equity", "net_income", "operating_cash_flow", "total_interest_bearing_debt"})
                debt = next(row for row in citations if row["metric"] == "total_interest_bearing_debt")
                self.assertEqual(debt["value"], 21_073_487_486_139)
                promotion.promote(root, manifest_records=manifests, citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                                  citation_records=citations, dry_run=False)
                result = build_projection("FPT", facts_for_ticker(root, "FPT"), entity_type="corporate",
                                          entity_authority="manual_profile", evidence_index=load_evidence_index(root))
                self.assertTrue(result["research_eligible"])
                self.assertTrue(result["historical_only"])
                self.assertFalse(result["is_actionable"])


if __name__ == "__main__":
    unittest.main()
