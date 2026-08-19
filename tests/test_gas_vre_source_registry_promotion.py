"""Unit and integration tests for P2-D2 GAS and VRE official source registry promotion.

Validates exact-host admission, document-class scoping, negative host/class rejections,
and unpromoted status of MWG and VIC.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import official_document_acquisition as acquisition
import official_source_registry as registry


class RecordingFetcher:
    """Stands in for the network. Records every URL requested."""

    def __init__(self, body: bytes = b"%PDF-1.4 simulated pdf bytes"):
        self.urls: list[str] = []
        self.body = body

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        return 200, {"Content-Type": "application/pdf"}, self.body, url


def spec(**overrides) -> dict:
    base = {
        "ticker": "GAS",
        "source_id": "issuer_ir",
        "document_class": "audited_annual_financial_statements",
        "reporting_period": "2024",
        "canonical_url": "https://www.pvgas.com.vn/quan-he-co-%C4%91ong/tai-lieu-co-%C4%91ong/fy2024.pdf",
    }
    base.update(overrides)
    return base


def run(specs, *, reg=None, fetcher=None):
    fetcher = fetcher or RecordingFetcher()
    with tempfile.TemporaryDirectory() as tmp:
        result = acquisition.acquire(
            specs, Path(tmp), fetcher=fetcher,
            registry=reg if reg is not None else registry.load_registry()
        )
    return result, fetcher


class GasVreSourceRegistryPromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = registry.load_registry()

    def test_gas_official_host_admitted_for_audited_annual_financial_statements(self) -> None:
        url = "https://www.pvgas.com.vn/quan-he-co-%C4%91ong/tai-lieu-co-%C4%91ong/bctc-2024.pdf"
        decision = registry.admit("issuer_ir", url, "audited_annual_financial_statements", registry=self.reg)
        self.assertEqual(decision["decision"], registry.ADMITTED)
        self.assertEqual(decision["reason"], "admitted_by_registry")

        # Via acquisition runner
        result, fetcher = run([spec(ticker="GAS", canonical_url=url)], reg=self.reg)
        self.assertEqual(result["outcomes"][0]["state"], "retained")
        self.assertEqual(fetcher.urls, [url])

    def test_gas_unrelated_or_unadmitted_hosts_rejected(self) -> None:
        # Non-www pvgas.com.vn is not on allowed_hosts per P2-D2 scope
        for rejected_url in (
            "https://pvgas.com.vn/bctc-2024.pdf",
            "https://reports.pvgas.com.vn/bctc-2024.pdf",
            "https://evil-pvgas.com.vn/bctc-2024.pdf",
            "https://cdn.pvgas.com.vn/bctc-2024.pdf",
        ):
            decision = registry.admit("issuer_ir", rejected_url, "audited_annual_financial_statements", registry=self.reg)
            self.assertEqual(decision["decision"], registry.REFUSED)
            self.assertEqual(decision["reason"], registry.REASON_HOST_NOT_ALLOWED)

            result, fetcher = run([spec(ticker="GAS", canonical_url=rejected_url)], reg=self.reg)
            self.assertEqual(fetcher.urls, [])
            self.assertEqual(result["outcomes"][0]["state"], "refused_by_source_registry")

    def test_gas_unauthorized_document_class_rejected(self) -> None:
        url = "https://www.pvgas.com.vn/press-release.pdf"
        decision = registry.admit("issuer_ir", url, "press_release", registry=self.reg)
        self.assertEqual(decision["decision"], registry.REFUSED)
        self.assertEqual(decision["reason"], registry.REASON_DOCUMENT_TYPE)

    def test_vre_official_host_and_concrete_pdf_url_admitted(self) -> None:
        url = "https://ir.vincom.com.vn/wp-content/uploads/2026/03/BCTC-hop-nhat-2025-1.pdf"
        decision = registry.admit("issuer_ir", url, "audited_annual_financial_statements", registry=self.reg)
        self.assertEqual(decision["decision"], registry.ADMITTED)
        self.assertEqual(decision["reason"], "admitted_by_registry")

        # Via acquisition runner
        result, fetcher = run([spec(ticker="VRE", reporting_period="2025", canonical_url=url)], reg=self.reg)
        self.assertEqual(result["outcomes"][0]["state"], "retained")
        self.assertEqual(fetcher.urls, [url])

    def test_vre_unrelated_hosts_rejected(self) -> None:
        for rejected_url in (
            "https://vincom.com.vn/bctc.pdf",
            "https://www.vincom.com.vn/bctc.pdf",
            "https://cdn.vincom.com.vn/bctc.pdf",
            "https://evil-vincom.com.vn/bctc.pdf",
        ):
            decision = registry.admit("issuer_ir", rejected_url, "audited_annual_financial_statements", registry=self.reg)
            self.assertEqual(decision["decision"], registry.REFUSED)
            self.assertEqual(decision["reason"], registry.REASON_HOST_NOT_ALLOWED)

            result, fetcher = run([spec(ticker="VRE", reporting_period="2025", canonical_url=rejected_url)], reg=self.reg)
            self.assertEqual(fetcher.urls, [])
            self.assertEqual(result["outcomes"][0]["state"], "refused_by_source_registry")

    def test_mwg_and_vic_remain_unpromoted_and_refused(self) -> None:
        for url in (
            "https://mwg.vn/bao-cao/bctc.pdf",
            "https://www.mwg.vn/bao-cao/bctc.pdf",
            "https://vingroup.net/ir/bctc.pdf",
            "https://www.vingroup.net/ir/bctc.pdf",
            "https://ircdn.vingroup.net/storage/bctc.pdf",
        ):
            decision = registry.admit("issuer_ir", url, "audited_annual_financial_statements", registry=self.reg)
            self.assertEqual(decision["decision"], registry.REFUSED)
            self.assertEqual(decision["reason"], registry.REASON_HOST_NOT_ALLOWED)

    def test_exact_host_matching_without_suffix_or_wildcard(self) -> None:
        for fake_url in (
            "https://fakewww.pvgas.com.vn/doc.pdf",
            "https://notir.vincom.com.vn/doc.pdf",
            "https://evil-pvgas.com.vn/doc.pdf",
        ):
            decision = registry.admit("issuer_ir", fake_url, "audited_annual_financial_statements", registry=self.reg)
            self.assertEqual(decision["decision"], registry.REFUSED)
            self.assertEqual(decision["reason"], registry.REASON_HOST_NOT_ALLOWED)

    def test_existing_registry_sources_continue_to_function(self) -> None:
        # HOSE
        decision = registry.admit("hose", "https://www.hsx.vn/notice.html", "corporate_action_notice", registry=self.reg)
        self.assertEqual(decision["decision"], registry.ADMITTED)

        # HNX
        decision = registry.admit("hnx", "https://www.hnx.vn/event.html", "corporate_action_notice", registry=self.reg)
        self.assertEqual(decision["decision"], registry.ADMITTED)

        # VSDC
        decision = registry.admit("vsdc", "https://www.vsdc.vn/record.html", "last_registration_date_notice", registry=self.reg)
        self.assertEqual(decision["decision"], registry.ADMITTED)

        # Existing issuer_ir hosts
        for host in ("file.hoaphat.com.vn", "www.vinamilk.com.vn", "www.vietcombank.com.vn", "www.ssi.com.vn", "cdn.pnj.io", "fpt.com", "www.pvdrilling.com.vn", "www.qns.com.vn", "pvpower.vn", "www.novaland.com.vn"):
            decision = registry.admit("issuer_ir", f"https://{host}/report.pdf", "audited_annual_financial_statements", registry=self.reg)
            self.assertEqual(decision["decision"], registry.ADMITTED)


if __name__ == "__main__":
    unittest.main()
