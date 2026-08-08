"""Deterministic SSI FY2024 financial-identity qualification boundary.

The real governed document is retained outside the runtime store.  These tests exercise
the existing manifest/citation schema in a temporary root with the direct field that the
retained page supports; they never write dashboard-runtime.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import canonical_fact_store  # noqa: E402
import evidence_promotion as promotion  # noqa: E402
import semantic_evidence_bridge as bridge  # noqa: E402


class SsiFy2024FinancialIdentityQualificationTests(unittest.TestCase):
    """The existing financial-identity authority admits only direct, cited fields."""

    TICKER = "SSI"
    REPORTING_PERIOD = "2024"
    CURRENT_LIABILITIES = 46_599_438_522_989
    SOURCE_URL = (
        "https://www.ssi.com.vn/upload/files/IR/"
        "20250320_SSI_Bao_cao_tai_chinh_hop_nhat_nam_2024_EN.pdf"
    )
    PAGE_CITATION = "25630bfe0e11e7c0f4dcf728c15b351dae13e9342f9f5be35e8e1cf20f5e8e95"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.document = self.root / "retained" / "ssi-fy2024-audited.pdf"
        self.document.parent.mkdir()
        self.document.write_bytes(b"SSI FY2024 audited financial statements test fixture")
        self.sha256 = hashlib.sha256(self.document.read_bytes()).hexdigest()
        self.evidence_id = promotion._hash({
            "ticker": self.TICKER,
            "document_sha256": self.sha256,
            "document_id": "3fd72890fe43b78071d641b8d89523d4aa28e340d4f1904a90667f8c1d794bf0",
        })

    def _manifest(self) -> dict:
        return promotion.build_manifest_record(
            evidence_id=self.evidence_id,
            archive_document_path=self.document,
            sha256=self.sha256,
            filename=self.document.name,
            ticker=self.TICKER,
            authority="SSI Securities Corporation investor relations",
            source_url=self.SOURCE_URL,
            document_id="3fd72890fe43b78071d641b8d89523d4aa28e340d4f1904a90667f8c1d794bf0",
            document_class="audited_annual_financial_statements",
            reporting_period=self.REPORTING_PERIOD,
            published_at="2025-03-20",
            observed_at="2026-07-30T00:00:00Z",
        )

    def _citation(self, *, value: int | None = None) -> dict:
        return promotion.build_financial_identity_citation(
            ticker=self.TICKER,
            metric="current_liabilities",
            reporting_period=self.REPORTING_PERIOD,
            value=self.CURRENT_LIABILITIES if value is None else value,
            evidence_id=self.evidence_id,
            statement_scope="consolidated",
            currency="VND",
            unit_scale=1,
            reporting_frequency="annual",
            citation=(
                f"OCR page 10 citation {self.PAGE_CITATION}: "
                "Consolidated Statement of Financial Position as at 31 December 2024, "
                "Currency: VND; Current liabilities."
            ),
            verified_at="2026-08-08T00:00:00+07:00",
        )

    def _promote(self, citations: list[dict] | None = None) -> None:
        promotion.promote(
            self.root,
            manifest_records=[self._manifest()],
            citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
            citation_records=citations or [self._citation()],
            dry_run=False,
        )

    def test_direct_field_qualifies_with_hash_and_citation_lineage(self) -> None:
        self._promote()

        verified = bridge.load_verified_financial_identities(self.root)
        entry = verified["by_key"][(self.TICKER, "current_liabilities", self.REPORTING_PERIOD)]
        self.assertEqual(verified["rejected"], [])
        self.assertEqual(entry["value"], self.CURRENT_LIABILITIES)
        self.assertEqual(entry["statement_scope"], "consolidated")
        self.assertEqual(entry["currency"], "VND")
        self.assertEqual(entry["citation"].split(":", 1)[0], f"OCR page 10 citation {self.PAGE_CITATION}")
        self.assertEqual(entry["evidence_id"], self.evidence_id)

        manifest = json.loads((self.root / promotion.MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        self.assertEqual(manifest["records"][0]["sha256"], self.sha256)
        self.assertEqual(manifest["records"][0]["source_url"], self.SOURCE_URL)

    def test_unavailable_identity_is_not_synthesized(self) -> None:
        self._promote()
        verified = bridge.load_verified_financial_identities(self.root)

        self.assertIsNone(bridge.latest_financial_identity(
            verified["by_key"], self.TICKER, "retained_earnings"))
        self.assertNotIn((self.TICKER, "retained_earnings", self.REPORTING_PERIOD), verified["by_key"])

    def test_annual_stock_identity_preserves_year_end_temporal_alias_only(self) -> None:
        self._promote()
        citations = canonical_fact_store.load_official_citations(self.root)

        annual = citations[(self.TICKER, "current_liabilities", "2024")]
        q4 = citations[(self.TICKER, "current_liabilities", "2024-Q4")]
        self.assertEqual(annual["value"], self.CURRENT_LIABILITIES)
        self.assertEqual(q4["value"], self.CURRENT_LIABILITIES)
        self.assertEqual(q4["period_alias"], "annual_year_end_is_q4_end")
        self.assertNotIn((self.TICKER, "current_liabilities", "2024-Q3"), citations)

    def test_conflicting_direct_citation_fails_closed(self) -> None:
        self._promote([self._citation(), self._citation(value=self.CURRENT_LIABILITIES + 1)])

        verified = bridge.load_verified_financial_identities(self.root)
        key = (self.TICKER, "current_liabilities", self.REPORTING_PERIOD)
        self.assertNotIn(key, verified["by_key"])
        self.assertIn({"key": key, "reason": "conflicting_citations"}, verified["rejected"])

    def test_unresolved_issuer_remains_unavailable(self) -> None:
        self._promote()
        verified = bridge.load_verified_financial_identities(self.root)

        self.assertIsNone(bridge.latest_financial_identity(
            verified["by_key"], "UNRESOLVED", "current_liabilities"))


if __name__ == "__main__":
    unittest.main()
