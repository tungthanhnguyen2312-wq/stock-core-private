"""Bounded governed-evidence recovery for the five historical research tickers.

This is deliberately a recovery contract, not a new filing framework.  It fixes the
only permitted legacy cohort and requires a fresh, hash-verified filing path; prior
served bundles and briefs have no input path here.  VNM is the first materialized
slice.  It writes a derived page sidecar under governed retained evidence and returns
promotion records for an explicitly supplied *temporary* evidence root.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import evidence_promotion as promotion
from annual_financial_ocr_materialization import (
    render_and_ocr,
    verified_debt_extraction,
    verified_extraction,
    verified_sum_extraction,
    write_materialization,
)
import targeted_multi_period_official_financial_evidence as multi_period


DEFAULT_EVIDENCE_ROOT = Path("operations-review") / "governed-official-evidence-v1"
MATERIALIZATION_ROOT = Path("derived") / "annual_financial_ocr_materialization_v1"
VERIFIED_AT = "2026-08-09T00:00:00Z"
LEGACY_TICKERS = ("HPG", "VNM", "PAN", "PVD", "NVL")
LEGACY_FILINGS = {
    "HPG": "304a93a65e1587f625e0045d6ec9bcfba6647d19df4034cfd8fc1ec7b62eeb64",
    "VNM": "4313d34c5d2131803e87c11bdd34ff3313d607e901dd37ea6e09f5600441a6ab",
    "PAN": "f1d6fb0dde557d9e098e13cc10ca0b0506e10e446f3ac6dc8122c4fa560df006",
    "PVD": "ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14",
    "NVL": "078fe614549d6f139b3cd3e9bdcd9f99a533b03c067c5018a989166cb2eab3d3",
}

# The anchors are exact OCR occurrences checked against pages 182--187 in the retained
# report.  The report labels all figures VND million; values are normalized to VND while
# `unit_scale` retains the displayed scale in every citation.
VNM_FACTS = (
    ("cash_and_equivalents", 2_225_944_000_000, 92, "Cash and cash equivalents", "2,225,944", "balance_sheet"),
    ("shareholders_equity", 37_165_930_000_000, 92, "Equity", "37,165,930", "balance_sheet"),
    ("net_income", 8_686_245_000_000, 93, "Net profit", "8,686,245", "income_statement"),
    ("operating_cash_flow", 9_770_587_000_000, 94, "Net cash generated from operating activities", "9,770,587", "cash_flow"),
)
VNM_DEBT_COMPONENTS = (
    {"page": 92, "label": "Borrowings", "raw_value": "9,115,435", "visual_source_page_verified": True},
    {"page": 92, "label": "Borrowings", "raw_value": "157,904", "visual_source_page_verified": True},
)

# This is the complete, fixed retained source set for the recovery operation.  PAN's
# annual report is verified as governed companion provenance but its audited statement is
# the only PAN extraction source.  No URL, discovery result, or served artifact is accepted.
REMAINING_RETAINED_FILINGS = {
    "HPG_FY2022": ("HPG", "2022", "4fb8f8e0f8dd5dc429533e548e4cfd045c9a81f9d26a51a5e3cf1cee53498074", "5c29d7868c552bb25760d684d11b44db9ad74d0348407a5949e903815b860114"),
    "HPG_FY2023": ("HPG", "2023", "44919df68306d2389509d5701369c70966f3669fb5b2ce20f609b28322cfef0e", "657f9069c41deb37b3611fe366ef49da507d6ac2651db0df332f09340ad9449d"),
    "HPG_FY2024": ("HPG", "2024", "304a93a65e1587f625e0045d6ec9bcfba6647d19df4034cfd8fc1ec7b62eeb64", "1f9d1b94db13d1232ffef2fe869ed4583af81baa1f655d7aa033fa662eea7664"),
    "PAN_FY2024_AUDITED": ("PAN", "2024", "f1d6fb0dde557d9e098e13cc10ca0b0506e10e446f3ac6dc8122c4fa560df006", "4baec0dac3eb4b7ad19e0bd1b7a42a1e94a2602c567c4db7ce7da550c33d573a"),
    "PAN_FY2024_ANNUAL_REPORT": ("PAN", "2024", "757f8e5fe983013f20c8adf0f8fde1131baa3b3731a749735d26745a9420c83b", "4b97139713b225995afb5a8a317eae3158d788d4917de739808a29caca88593f"),
    "PVD_FY2022": ("PVD", "2022", "5fc2a5b4e528c381a4bd54a22e4549b529d423ae6ae5c85816c5109a0a576364", "f125cc40f2db2a3ccb0abea24f42e4939f7d0b4e7559d1270de51026df16aecf"),
    "PVD_FY2023": ("PVD", "2023", "a28d4c2647ac9b1758778eee18ca7da1ab46cdc0d48ee633ef55299eea16011b", "0a3a11d700b0936621fb1ebd768a38a7d0b528bd82cab5ed34cd29b1036bde96"),
    "PVD_FY2024": ("PVD", "2024", "ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14", "e03146183ffecb8cc94c5302edca1d8b5010e2121a00d18ae74e284cf0c306cb"),
    "NVL_FY2024": ("NVL", "2024", "078fe614549d6f139b3cd3e9bdcd9f99a533b03c067c5018a989166cb2eab3d3", "283a7aad9a705d9237474428327f430a97df17d34f90b6a638d3297b34082e41"),
}

# Four concrete FY2024 modes, each restricted to the retained source pages named here.
REMAINING_FY2024_SPECS = {
    "HPG": {"filing": "HPG_FY2024", "sidecar": "hpg-fy2024-legacy-recovery.json", "currency": "VND",
            "issuer": "Hoa Phat Group Joint Stock Company", "authority_domain": "hoaphat.com.vn",
            "pages": (7, 9, 10, 11, 13), "psm": {7: 6, 9: 6, 10: 6, 11: 6, 13: 6},
            "facts": (("cash_and_equivalents", 6_887_646_139_852, 7, "Tién va cdc khoan twong dwong tién", "Tiền và các khoản tương đương tiền", "6.887.646.139.852", "balance_sheet"),
                      ("shareholders_equity", 114_647_457_983_699, 10, "VON CHU SO HUU", "VỐN CHỦ SỞ HỮU", "114.647.457.983.699", "balance_sheet"),
                      ("net_income", 12_020_023_621_271, 11, "Loi nhuan sau thué TNDN", "Lợi nhuận sau thuế TNDN", "12.020.023.621.271", "income_statement"),
                      ("operating_cash_flow", 6_608_320_655_215, 13, "Liga chuyen tiem thuan tir hogtdag", "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "6.608.320.655.215", "cash_flow")),
            "debt": ((9, "Vay ngan han", "Vay ngắn hạn", "55.882.686.213.459", "short_term_borrowings"),
                     (9, "Vay dai han", "Vay dài hạn", "27.080.443.256.096", "long_term_borrowings_or_finance_leases"))},
    "PAN": {"filing": "PAN_FY2024_AUDITED", "sidecar": "pan-fy2024-legacy-recovery.json", "currency": "VND",
            "issuer": "The PAN Group Joint Stock Company", "authority_domain": "thepangroup.vn",
            "pages": (8, 10, 11, 12, 13), "psm": {8: 6, 10: 6, 11: 6, 12: 6, 13: 6},
            "facts": (("cash_and_equivalents", 2_958_874_263_351, 8, "Cash and cash equivalents", "Cash and cash equivalents", "2,958,874,263,351", "balance_sheet"),
                      ("shareholders_equity", 8_859_450_516_042, 11, "D. EQUITY", "D. EQUITY", "8,859,450,516,042", "balance_sheet"),
                      ("net_income", 1_167_068_107_309, 12, "Net profit after corporate income", "Net profit after corporate income tax", "1,167,068,107,309", "income_statement"),
                      ("operating_cash_flow", -1_739_184_049_701, 13, "Net cash used in operating activities", "Net cash used in operating activities", "(1,739,184,049,701)", "cash_flow")),
            "debt": ((10, "Short-term loans and obligations", "Short-term loans and obligations under finance leases", "11,493,025,595,010", "short_term_borrowings"),
                     (10, "Long-term loans and obligations", "Long-term loans and obligations under finance leases", "206,652,925,496", "long_term_borrowings_or_finance_leases"))},
    "PVD": {"filing": "PVD_FY2024", "sidecar": "pvd-fy2024-legacy-recovery.json", "currency": "USD",
            "issuer": "Petrovietnam Drilling and Well Services Corporation", "authority_domain": "pvdrilling.com.vn",
            "pages": (6, 7, 8, 9), "psm": {6: 4, 7: 4, 8: 6, 9: 6},
            "facts": (("cash_and_equivalents", 87_254_694, 6, "Cash and cash equivalents", "Cash and cash equivalents", "87,254,694", "balance_sheet"),
                      ("shareholders_equity", 635_711_153, 7, "D. EQUITY", "D. EQUITY", "635,711,153", "balance_sheet"),
                      ("net_income", 28_074_925, 8, "Net profit after corporate income tax", "Net profit after corporate income tax", "28,074,925", "income_statement"),
                      ("operating_cash_flow", 41_707_698, 9, "Net cash generated by", "Net cash generated by operating activities", "41,707,698", "cash_flow")),
            "debt": ((7, "Short-term loans", "Short-term loans", "20,090,244", "short_term_borrowings"),
                     (7, "Long-term loans", "Long-term loans", "100,645,129", "long_term_borrowings_or_finance_leases"))},
    "NVL": {"filing": "NVL_FY2024", "sidecar": "nvl-fy2024-legacy-recovery.json", "currency": "VND",
            "issuer": "Novaland Group", "authority_domain": "novaland.com.vn",
            "pages": (8, 10, 11, 12, 13), "psm": {8: 4, 10: 6, 11: 6, 12: 4, 13: 6},
            "facts": (("cash_and_equivalents", 4_607_601_921_683, 8, "Tién va cdc khoan twong dwong tién", "Tiền và các khoản tương đương tiền", "4.607.601.921.683", "balance_sheet"),
                      ("shareholders_equity", 47_291_024_358_614, 11, "Vén cha sé hitu", "Vốn chủ sở hữu", "47.291.024.358.614", "balance_sheet"),
                      ("net_income", -4_394_642_203_703, 12, "Loi nhuan sau thué thu nhip doanh nghiép", "Lợi nhuận sau thuế thu nhập doanh nghiệp", "(4.394.642.203.703)", "income_statement"),
                      ("operating_cash_flow", -5_971_178_115_653, 13, "Luu chuyén tian thuan tir hoat dng kinh doanh", "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "(5.971.178.115.653)", "cash_flow")),
            "debt": ((10, "Vay va ng thue tai chinh ngén han", "Vay và nợ thuê tài chính ngắn hạn", "36.978.198.251.788", "short_term_borrowings"),
                     (10, "Vay va ng thue tai chinh dai han", "Vay và nợ thuê tài chính dài hạn", "24.587.656.403.178", "long_term_borrowings_or_finance_leases"))},
}

# Tesseract's exact, page-local anchors are deliberately recorded separately from the
# human-readable source labels above.  Unicode escapes keep this source portable on the
# Windows shell while the materialized OCR text remains the citation authority.
REMAINING_FY2024_SPECS["HPG"].update({
    "facts": (
        ("cash_and_equivalents", 6_887_646_139_852, 7, "Ti\u00e9n va cdc khoan twong dwong ti\u00e9n", "Ti\u00e9n va cdc khoan twong dwong ti\u00e9n", "6.887.646.139.852", "balance_sheet"),
        ("shareholders_equity", 114_647_457_983_699, 10, "VON CHU SO HUU", "VON CHU SO HUU", "114.647.457.983.699", "balance_sheet"),
        ("net_income", 12_020_023_621_271, 11, "Loi nhuan sau thu\u00e9 TNDN", "Loi nhuan sau thu\u00e9 TNDN", "12.020.023.621.271", "income_statement"),
        ("operating_cash_flow", 6_608_320_655_215, 13, "Liga chuyen tiem thuan tir hogtdag", "Liga chuyen tiem thuan tir hogtdag", "6.608.320.655.215", "cash_flow"),
    ),
    "debt": ((9, "Vay ngan han", "Vay ngan han", "55.882.686.213.459", "short_term_borrowings"),
             (9, "Vay dai han", "Vay dai han", "27.080.443.256.096", "long_term_borrowings_or_finance_leases")),
})
REMAINING_FY2024_SPECS["NVL"].update({
    "dpi": 288,
    "psm": {8: 4, 10: 6, 11: 6, 12: 4, 13: 6},
    "facts": (
        ("cash_and_equivalents", 4_607_601_921_683, 8, "I. Ti\u00e9n va cdc khoan twong dwong ti\u00e9n", "I. Ti\u00e9n va cdc khoan twong dwong ti\u00e9n", "4.607.601.921.683", "balance_sheet"),
        ("shareholders_equity", 47_291_024_358_614, 11, "I. V\u00e9n cha s\u00e9 hitu", "I. V\u00e9n cha s\u00e9 hitu", "47.291.024.358.614", "balance_sheet"),
        ("net_income", -4_394_642_203_703, 12, "18. Loi nhuan sau thu\u00e9 thu nhip doanh nghi\u00e9p", "18. Loi nhuan sau thu\u00e9 thu nhip doanh nghi\u00e9p", "(4.394.642.203.703)", "income_statement"),
        ("operating_cash_flow", -5_971_178_115_653, 13, "Luu chuy\u00e9n tian thuan tir hoat dng kinh doanh", "Luu chuy\u00e9n tian thuan tir hoat dng kinh doanh", "(5.971.178.115.653)", "cash_flow"),
    ),
    "debt": ((10, "8. Vay va ng thu\u00e9 tai chinh ng\u00e9n han", "8. Vay va ng thu\u00e9 tai chinh ng\u00e9n han", "36.978.198.251.788", "short_term_borrowings"),
             (10, "4. Vay va ng thu\u00e9 tai chinh dai han", "4. Vay va ng thu\u00e9 tai chinh dai han", "24.587.656.403.178", "long_term_borrowings_or_finance_leases")),
})


def _normalize_vnd_millions(extraction: Mapping[str, Any]) -> dict[str, Any]:
    """Retain displayed-unit provenance while normalizing a cited value to VND units."""
    result = dict(extraction)
    result["normalized_value"] = int(result["normalized_value"]) * 1_000_000
    if result.get("method") == "document_line_item_sum":
        result["components"] = [{**component, "value": int(component["value"]) * 1_000_000}
                                for component in result["components"]]
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _retained_records(evidence_root: Path) -> list[dict[str, Any]]:
    manifest = json.loads((Path(evidence_root) / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError("RETAINED_FILING_MANIFEST_MALFORMED")
    return [dict(record) for record in records if isinstance(record, Mapping)]


def retained_filing(evidence_root: Path, ticker: str) -> dict[str, Any]:
    """Return exactly the fixed retained filing for one approved legacy ticker."""
    ticker = str(ticker).upper()
    if ticker not in LEGACY_FILINGS:
        raise ValueError("LEGACY_TICKER_OUT_OF_SCOPE")
    matches = [record for record in _retained_records(evidence_root)
               if str(record.get("ticker") or "").upper() == ticker
               and record.get("sha256") == LEGACY_FILINGS[ticker]
               and record.get("acquisition_status") == "retained"
               and record.get("reporting_period") == "2024"]
    if len(matches) != 1:
        raise ValueError(f"RETAINED_FILING_AMBIGUOUS_OR_MISSING:{ticker}")
    record = matches[0]
    source = Path(evidence_root) / str(record.get("relative_path") or "")
    if not source.is_file() or _sha256_file(source) != record["sha256"]:
        raise ValueError(f"RETAINED_FILING_HASH_MISMATCH:{ticker}")
    return record


def recovery_contract(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """Verify the exact five-filing recovery boundary without materializing a fact."""
    root = Path(evidence_root)
    records = {ticker: retained_filing(root, ticker) for ticker in LEGACY_TICKERS}
    return {
        "contract": "legacy_qualified_cohort_recovery/v1",
        "tickers": list(LEGACY_TICKERS),
        "restoration_sources": "retained_official_filings_only",
        "comparison_outputs_permitted_as_evidence": False,
        "documents": {ticker: {"document_id": record["document_id"], "sha256": record["sha256"],
                                "relative_path": record["relative_path"]}
                      for ticker, record in records.items()},
        "is_actionable": False,
    }


def materialize_vnm(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """OCR only VNM FY2024 statement pages 92--94 and persist the hash-bound sidecar."""
    root = Path(evidence_root)
    record = retained_filing(root, "VNM")
    materialization = render_and_ocr(record, root=root, pages=(92, 93, 94), language="eng",
                                     psm={92: 6, 93: 6, 94: 6}, dpi=288)
    write_materialization(root / MATERIALIZATION_ROOT / "vnm-fy2024.json", materialization)
    return materialization


def build_vnm_promotion(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build VNM's five fresh citation records; this does not write an evidence root."""
    root = Path(evidence_root)
    record = retained_filing(root, "VNM")
    sidecar = root / MATERIALIZATION_ROOT / "vnm-fy2024.json"
    if not sidecar.is_file():
        raise ValueError("VNM_MATERIALIZATION_REQUIRED")
    materialization = json.loads(sidecar.read_text(encoding="utf-8"))
    if materialization.get("document_sha256") != record["sha256"]:
        raise ValueError("VNM_MATERIALIZATION_SOURCE_HASH_MISMATCH")
    evidence_id = promotion._hash({"ticker": "VNM", "document_sha256": record["sha256"],
                                   "document_id": record["document_id"]})
    manifest = promotion.build_manifest_record(
        evidence_id=evidence_id, archive_document_path=root / record["relative_path"], sha256=record["sha256"],
        filename=Path(record["relative_path"]).name, ticker="VNM",
        issuer="Vietnam Dairy Products Joint Stock Company", authority=record["source_authority"],
        authority_domain="vinamilk.com.vn", evidence_type="audited_consolidated_financial_statements",
        source_url=record["canonical_url"], document_title="Vinamilk FY2024 annual report consolidated financial statements",
        document_id=record["document_id"], document_class=record["document_class"], reporting_period="2024",
        published_at=record["published_at"], observed_at=record["observed_at"], statement_scope="consolidated",
        audit_status="audited", source_id="issuer_ir",
    )
    citations = []
    for metric, value, page, label, raw_value, statement in VNM_FACTS:
        extraction = verified_extraction(materialization, page=page, raw_label=label, raw_value=raw_value,
                                         unit="VND million", statement=statement,
                                         visual_source_page_verified=True)
        extraction = _normalize_vnd_millions(extraction)
        citations.append(promotion.build_financial_identity_citation(
            ticker="VNM", metric=metric, reporting_period="2024", value=value, evidence_id=evidence_id,
            currency="VND", unit_scale=1_000_000,
            citation=f"Issuer annual-report PDF page {page}; {label}; consolidated FY2024; displayed in VND million.",
            verified_at=VERIFIED_AT, extraction=extraction,
        ))
    debt = verified_sum_extraction(materialization, components=VNM_DEBT_COMPONENTS,
                                   unit="VND million", statement="balance_sheet")
    debt = _normalize_vnd_millions(debt)
    debt_value = debt["normalized_value"]
    citations.append(promotion.build_financial_identity_citation(
        ticker="VNM", metric="total_interest_bearing_debt", reporting_period="2024", value=debt_value,
        evidence_id=evidence_id, currency="VND", unit_scale=1_000_000,
        citation=("Issuer annual-report PDF page 92; current and non-current Borrowings components; "
                  "consolidated FY2024; displayed in VND million."),
        verified_at=VERIFIED_AT, extraction=debt,
    ))
    return [manifest], citations


def retained_recovery_document(evidence_root: Path, document_key: str) -> dict[str, Any]:
    """Resolve exactly one fixed retained source and prove its live parent hash."""
    try:
        ticker, period, expected_hash, expected_document_id = REMAINING_RETAINED_FILINGS[document_key]
    except KeyError as exc:
        raise ValueError(f"RETAINED_RECOVERY_DOCUMENT_OUT_OF_SCOPE:{document_key}") from exc
    matches = [record for record in _retained_records(evidence_root)
               if str(record.get("ticker") or "").upper() == ticker
               and str(record.get("reporting_period") or "") == period
               and record.get("sha256") == expected_hash
               and record.get("document_id") == expected_document_id
               and record.get("acquisition_status") == "retained"]
    if len(matches) != 1:
        raise ValueError(f"RETAINED_RECOVERY_DOCUMENT_AMBIGUOUS_OR_MISSING:{document_key}")
    record = matches[0]
    source = Path(evidence_root) / str(record.get("relative_path") or "")
    if not source.is_file() or _sha256_file(source) != expected_hash:
        raise ValueError(f"RETAINED_RECOVERY_DOCUMENT_HASH_MISMATCH:{document_key}")
    return record


def remaining_recovery_contract(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    """Verify the exact retained-source boundary for the four continuation tickers."""
    root = Path(evidence_root)
    documents = {key: retained_recovery_document(root, key) for key in REMAINING_RETAINED_FILINGS}
    return {
        "contract": "legacy_qualified_cohort_recovery/v2",
        "tickers": ["HPG", "PAN", "PVD", "NVL"],
        "restoration_sources": "retained_official_filings_only",
        "comparison_outputs_permitted_as_evidence": False,
        "documents": {key: {"ticker": row["ticker"], "reporting_period": row["reporting_period"],
                            "document_id": row["document_id"], "sha256": row["sha256"],
                            "relative_path": row["relative_path"]}
                      for key, row in documents.items()},
        "is_actionable": False,
    }


def materialize_remaining_fy2024(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, dict[str, Any]]:
    """Materialize only the four fixed FY2024 page selections from retained filings."""
    root = Path(evidence_root)
    # Verify the entire declared source boundary first, including PAN's companion report.
    remaining_recovery_contract(root)
    materializations: dict[str, dict[str, Any]] = {}
    for ticker, spec in REMAINING_FY2024_SPECS.items():
        record = retained_recovery_document(root, str(spec["filing"]))
        materialization = render_and_ocr(record, root=root, pages=tuple(spec["pages"]), language="eng",
                                         psm=dict(spec["psm"]), dpi=int(spec.get("dpi", 216)))
        write_materialization(root / MATERIALIZATION_ROOT / str(spec["sidecar"]), materialization)
        materializations[ticker] = materialization
    return materializations


def _remaining_fy2024_promotion(evidence_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the four FY2024 retained-filing promotions without writing evidence."""
    manifests, citations = [], []
    for ticker, spec in REMAINING_FY2024_SPECS.items():
        record = retained_recovery_document(evidence_root, str(spec["filing"]))
        sidecar = evidence_root / MATERIALIZATION_ROOT / str(spec["sidecar"])
        if not sidecar.is_file():
            raise ValueError(f"LEGACY_MATERIALIZATION_REQUIRED:{ticker}")
        materialization = json.loads(sidecar.read_text(encoding="utf-8"))
        if materialization.get("document_sha256") != record["sha256"]:
            raise ValueError(f"LEGACY_MATERIALIZATION_SOURCE_HASH_MISMATCH:{ticker}")
        evidence_id = promotion._hash({"ticker": ticker, "document_sha256": record["sha256"],
                                       "document_id": record["document_id"]})
        manifests.append(promotion.build_manifest_record(
            evidence_id=evidence_id, archive_document_path=evidence_root / record["relative_path"],
            sha256=record["sha256"], filename=Path(record["relative_path"]).name, ticker=ticker,
            issuer=str(spec["issuer"]), authority=record["source_authority"],
            authority_domain=str(spec["authority_domain"]), evidence_type="audited_consolidated_financial_statements",
            source_url=record["canonical_url"], document_title=f"{ticker} FY2024 audited consolidated financial statements",
            document_id=record["document_id"], document_class=record["document_class"],
            reporting_period="2024", published_at=record["published_at"], observed_at=record["observed_at"],
            statement_scope="consolidated", audit_status="audited", source_id=record.get("source_id", "issuer_ir"),
        ))
        for metric, value, page, ocr_label, source_label, raw_value, statement in spec["facts"]:
            extraction = verified_extraction(materialization, page=page, raw_label=ocr_label, raw_value=raw_value,
                                             source_raw_label=source_label, source_raw_value=raw_value,
                                             unit=str(spec["currency"]), statement=statement,
                                             visual_source_page_verified=True)
            citations.append(promotion.build_financial_identity_citation(
                ticker=ticker, metric=metric, reporting_period="2024", value=value, evidence_id=evidence_id,
                currency=str(spec["currency"]), citation=(f"Issuer retained PDF page {page}; {source_label}; "
                                                             "audited consolidated FY2024."),
                verified_at=VERIFIED_AT, extraction=extraction,
            ))
        components = [{"page": page, "label": source_label, "ocr_label": ocr_label,
                       "source_raw_label": source_label, "raw_value": raw_value, "ocr_raw_value": raw_value,
                       "component_type": component_type, "reporting_period": "2024",
                       "visual_source_page_verified": True}
                      for page, ocr_label, source_label, raw_value, component_type in spec["debt"]]
        debt = verified_debt_extraction(materialization, components=components, unit=str(spec["currency"]),
                                        statement="balance_sheet", reporting_period="2024")
        citations.append(promotion.build_financial_identity_citation(
            ticker=ticker, metric="total_interest_bearing_debt", reporting_period="2024",
            value=debt["normalized_value"], evidence_id=evidence_id, currency=str(spec["currency"]),
            citation=(f"Issuer retained PDF page {debt['source_pages'][0]}; short- and long-term borrowing "
                      "components; audited consolidated FY2024."), verified_at=VERIFIED_AT, extraction=debt,
        ))
    return manifests, citations


def build_legacy_cohort_promotion(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the complete fixed five-ticker set: VNM plus HPG/PVD FY22--24 and PAN/NVL FY24."""
    root = Path(evidence_root)
    remaining_recovery_contract(root)
    vnm_manifests, vnm_citations = build_vnm_promotion(root)
    historical_manifests, historical_citations = multi_period.build_promotion(root)
    fy2024_manifests, fy2024_citations = _remaining_fy2024_promotion(root)
    manifests = vnm_manifests + historical_manifests + fy2024_manifests
    citations = vnm_citations + historical_citations + fy2024_citations
    if len({row["evidence_id"] for row in manifests}) != len(manifests):
        raise ValueError("LEGACY_PROMOTION_EVIDENCE_ID_CONFLICT")
    if len({row["citation_id"] for row in citations}) != len(citations):
        raise ValueError("LEGACY_PROMOTION_CITATION_ID_CONFLICT")
    return manifests, citations


def _assert_append_compatible(runtime_root: Path, manifests: list[dict[str, Any]], citations: list[dict[str, Any]]) -> None:
    """Refuse an existing ID whose payload differs instead of silently deduplicating it."""
    manifest_path = runtime_root / promotion.MANIFEST_RELATIVE
    existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"records": []}
    by_evidence_id = {row.get("evidence_id"): row for row in existing_manifest.get("records", [])}
    for row in manifests:
        prior = by_evidence_id.get(row["evidence_id"])
        if prior is not None and prior != row:
            raise ValueError(f"LEGACY_PROMOTION_EXISTING_EVIDENCE_CONFLICT:{row['evidence_id']}")
    citation_path = runtime_root / promotion.FINANCIAL_IDENTITY_RELATIVE
    existing_citations = [json.loads(line) for line in citation_path.read_text(encoding="utf-8").splitlines()
                          if line.strip()] if citation_path.exists() else []
    by_citation_id = {row.get("citation_id"): row for row in existing_citations}
    for row in citations:
        prior = by_citation_id.get(row["citation_id"])
        if prior is not None and prior != row:
            raise ValueError(f"LEGACY_PROMOTION_EXISTING_CITATION_CONFLICT:{row['citation_id']}")


def promote_legacy_cohort(runtime_root: Path, *, evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
                          dry_run: bool = True) -> dict[str, Any]:
    """Append the fixed cohort through the sole writer, preserving all existing evidence."""
    manifests, citations = build_legacy_cohort_promotion(Path(evidence_root))
    _assert_append_compatible(Path(runtime_root), manifests, citations)
    return promotion.promote(Path(runtime_root), manifest_records=manifests,
                             citation_relative=promotion.FINANCIAL_IDENTITY_RELATIVE,
                             citation_records=citations, dry_run=dry_run)
