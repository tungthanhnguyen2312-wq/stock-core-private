"""Deterministic PAN FY2024 flow-identity qualification boundary.

Uses the existing temporary-root promotion path only.  The real PAN document stays in
governed retained evidence and is never copied into, or written to, dashboard-runtime.
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
from provider_official_bridge import exact_links, provider_observation, provider_snapshot  # noqa: E402


class PanFy2024FinancialIdentityQualificationTests(unittest.TestCase):
    TICKER = "PAN"
    REPORTING_PERIOD = "2024"
    NET_INCOME = 1_167_068_107_309
    SOURCE_URL = (
        "https://storage.thepangroup.vn/Data/2025/03/31/"
        "20250331-pan-audited-2024-consolidated-fs-638790383114311854.pdf"
    )
    DOCUMENT_ID = "4baec0dac3eb4b7ad19e0bd1b7a42a1e94a2602c567c4db7ce7da550c33d573a"
    PAGE_CITATION = "722fa880496affdd35e0f344faf8d973a5d9ba86ca3ea9e840c233b05f075550"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.document = self.root / "retained" / "pan-fy2024-audited.pdf"
        self.document.parent.mkdir()
        self.document.write_bytes(b"PAN FY2024 audited consolidated statement test fixture")
        self.sha256 = hashlib.sha256(self.document.read_bytes()).hexdigest()
        self.evidence_id = promotion._hash({
            "ticker": self.TICKER,
            "document_sha256": self.sha256,
            "document_id": self.DOCUMENT_ID,
        })

    def _manifest(self) -> dict:
        return promotion.build_manifest_record(
            evidence_id=self.evidence_id,
            archive_document_path=self.document,
            sha256=self.sha256,
            filename=self.document.name,
            ticker=self.TICKER,
            authority="The PAN Group Joint Stock Company investor relations",
            source_url=self.SOURCE_URL,
            document_id=self.DOCUMENT_ID,
            document_class="audited_annual_financial_statements",
            reporting_period=self.REPORTING_PERIOD,
            published_at="2025-03-31",
            observed_at="2026-07-30T02:51:46.062254Z",
        )

    def _citation(self, *, value: int | None = None) -> dict:
        return promotion.build_financial_identity_citation(
            ticker=self.TICKER,
            metric="net_income",
            reporting_period=self.REPORTING_PERIOD,
            value=self.NET_INCOME if value is None else value,
            evidence_id=self.evidence_id,
            statement_scope="consolidated",
            currency="VND",
            unit_scale=1,
            reporting_frequency="annual",
            citation=(
                f"OCR page 12 citation {self.PAGE_CITATION}: "
                "Consolidated statement of income for the year ended 31 December 2024, "
                "Unit: VND; Net profit after corporate income tax."
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

    def test_direct_pan_flow_identity_qualifies_with_lineage_and_replay(self) -> None:
        self._promote()
        first = bridge.load_verified_financial_identities(self.root)
        second = bridge.load_verified_financial_identities(self.root)
        entry = first["by_key"][(self.TICKER, "net_income", self.REPORTING_PERIOD)]

        self.assertEqual(first, second)
        self.assertEqual(first["rejected"], [])
        self.assertEqual(entry["value"], self.NET_INCOME)
        self.assertEqual(entry["statement_scope"], "consolidated")
        self.assertEqual(entry["currency"], "VND")
        self.assertIn(self.PAGE_CITATION, entry["citation"])
        manifest = json.loads((self.root / promotion.MANIFEST_RELATIVE).read_text(encoding="utf-8"))
        self.assertEqual(manifest["records"][0]["sha256"], self.sha256)
        self.assertEqual(manifest["records"][0]["source_url"], self.SOURCE_URL)

    def test_annual_flow_has_no_q4_alias_and_unavailable_fields_stay_unavailable(self) -> None:
        self._promote()
        citations = canonical_fact_store.load_official_citations(self.root)
        verified = bridge.load_verified_financial_identities(self.root)

        self.assertEqual(citations[(self.TICKER, "net_income", "2024")]["value"], self.NET_INCOME)
        self.assertNotIn((self.TICKER, "net_income", "2024-Q4"), citations)
        self.assertIsNone(bridge.latest_financial_identity(
            verified["by_key"], self.TICKER, "retained_earnings"))

    def test_compatible_annual_provider_cross_check_requires_same_identity_period_scope_and_unit(self) -> None:
        snapshot = provider_snapshot(
            provider="VCI", method="income_statement", version="4.0.4",
            parameters={"ticker": self.TICKER, "period": "year"},
            retrieved_at="2026-07-30T05:18:22.557654Z", raw_payload=[{"fixture": True}],
        )
        provider = provider_observation(
            snapshot, identity="profit_after_tax_total", period="2024", scope="consolidated",
            unit="VND", sign="positive", raw_item_id="net_profit_loss_after_tax",
            raw_label="Net profit/(loss) after tax", value=self.NET_INCOME,
        )
        official = {
            "identity": "profit_after_tax_total", "reporting_period": "2024",
            "statement_scope": "consolidated", "unit": "VND", "sign": "positive",
            "raw_item_id": "net_profit_loss_after_tax", "raw_value": self.NET_INCOME,
            "citation_id": self.PAGE_CITATION, "document_sha256": self.sha256,
        }
        self.assertEqual(len(exact_links([provider], [official])["links"]), 1)
        incompatible = {**official, "reporting_period": "2024-Q4"}
        self.assertEqual(exact_links([provider], [incompatible])["links"], [])

    def test_conflicting_pan_citations_and_unresolved_issuer_fail_closed(self) -> None:
        self._promote([self._citation(), self._citation(value=self.NET_INCOME + 1)])
        verified = bridge.load_verified_financial_identities(self.root)
        key = (self.TICKER, "net_income", self.REPORTING_PERIOD)

        self.assertNotIn(key, verified["by_key"])
        self.assertIn({"key": key, "reason": "conflicting_citations"}, verified["rejected"])
        self.assertIsNone(bridge.latest_financial_identity(
            verified["by_key"], "UNRESOLVED", "net_income"))


if __name__ == "__main__":
    unittest.main()
