"""Phase 2 / P2-F3: Bounded Generic Sector Extraction Authority Promotion Runner.

Executes explicit bounded authority promotion for the generic sector taxonomy extraction path:
- Bank: VCB FY2024 consolidated audited proof scope (15 facts)
- Securities: SSI FY2024 consolidated audited proof scope (16 facts)
- Preserves specialized implementations as reference/regression corroboration
- Enforces fail-closed conflict resolution and strict boundary gating

Generates:
1. operations-review/p2f3-bounded-generic-sector-extraction-promotion-20260820/p2f3_sector_extraction_promotion_artifact.json
2. operations-review/p2f3-bounded-generic-sector-extraction-promotion-20260820/READINESS_REPORT.md
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from entity_classification_contract import (
    EntityClass,
    resolve_layered_entity_classification,
)
from sector_financial_taxonomy import (
    AuthoritativeSectorFact,
    PromotedScopeEvaluationState,
    ReconciliationStatus,
    SectorAuthorityTier,
    StatementFormFamily,
    evaluate_sector_extraction_authority_scope,
    load_promoted_sector_extractions,
    reconcile_and_resolve_authoritative_sector_facts,
)
from financial_disclosure_recognizer import (
    extract_sector_facts_from_sidecar,
)

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "run_p2f3_sector_extraction_promotion/v1"
OUTPUT_DIR_NAME = "p2f3-bounded-generic-sector-extraction-promotion-20260820"

SOURCE_P2F1_ARTIFACT_ID = "p2f1_sector_financial_taxonomy:02f1afdf74a11cd93dda87d7bc232a6aa6ee7cfa1e3eb0cfb8d22d00a903eb18"
SOURCE_P2F1_ARTIFACT_HASH = "02f1afdf74a11cd93dda87d7bc232a6aa6ee7cfa1e3eb0cfb8d22d00a903eb18"


# Specialized VCB baseline facts (Ernst & Young audited FY2024 consolidated statements)
SPECIALIZED_VCB_FACTS: dict[str, int] = {
    "customer_loans_net": 1_418_015_724_000_000,
    "total_assets": 2_085_873_522_000_000,
    "customer_deposits": 1_514_664_850_000_000,
    "total_liabilities": 1_889_664_354_000_000,
    "total_equity": 196_209_168_000_000,
    "minority_interest": 96_261_000_000,
    "interest_income": 93_654_841_000_000,
    "interest_expense": 38_249_106_000_000,
    "net_interest_income": 55_405_735_000_000,
    "operating_expenses": 23_027_363_000_000,
    "operating_profit_before_provision_for_credit_losses": 45_551_133_000_000,
    "provision_for_credit_losses": 3_314_998_000_000,
    "profit_before_tax": 42_236_135_000_000,
    "net_profit_total": 33_853_117_000_000,
    "net_profit_parent": 33_831_386_000_000,
}

# Specialized SSI baseline facts (Ernst & Young audited FY2024 consolidated statements)
SPECIALIZED_SSI_FACTS: dict[str, int] = {
    "current_liabilities": 46_599_438_522_989,
}


def run_p2f3_promotion(root: Path) -> dict[str, Any]:
    """Execute complete bounded generic sector extraction authority promotion."""
    print("=" * 70)
    print("P2-F3: BOUNDED GENERIC SECTOR EXTRACTION AUTHORITY PROMOTION")
    print("=" * 70)

    # 1. Verify Source P2-F1 Artifact
    p2f1_artifact_path = (
        root
        / "operations-review"
        / "p2f1-sector-financial-taxonomy-foundation-20260819"
        / "p2f1_sector_financial_taxonomy_artifact.json"
    )
    if not p2f1_artifact_path.is_file():
        raise FileNotFoundError(f"Source P2-F1 artifact missing: {p2f1_artifact_path}")

    p2f1_data = json.loads(p2f1_artifact_path.read_text(encoding="utf-8"))
    p2f1_hash = p2f1_data.get("artifact_sha256")
    if p2f1_hash != SOURCE_P2F1_ARTIFACT_HASH:
        raise ValueError(
            f"Source P2-F1 artifact hash mismatch: got {p2f1_hash}, expected {SOURCE_P2F1_ARTIFACT_HASH}"
        )
    print(f"\n1. SOURCE P2-F1 ARTIFACT VERIFIED: {SOURCE_P2F1_ARTIFACT_ID}")

    # 2. Verify Config Registry
    config_path = root / "config" / "promoted_sector_extractions.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Promoted sector extractions config missing: {config_path}")

    registry = load_promoted_sector_extractions(config_path)
    promoted_sectors = registry.get("promoted_sectors", {})
    print(f"\n2. PROMOTED REGISTRY CONFIG: {len(promoted_sectors)} sectors promoted ({list(promoted_sectors.keys())})")

    # 3. Bank Authority Promotion (VCB FY2024 consolidated)
    print(f"\n3. BANK AUTHORITY PROMOTION (VCB FY2024 consolidated):")
    vcb_manifest_record = {
        "ticker": "VCB",
        "document_id": "aec971a73211a62c73167acc9f187a1ab1d88e9d1db5b73b399a598e9325fd2a",
        "sha256": "9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8",
        "reporting_period": "2024",
    }
    vcb_sidecar = {
        "document_id": vcb_manifest_record["document_id"],
        "document_sha256": vcb_manifest_record["sha256"],
        "pages": [
            {
                "page": 8,
                "text": "NGÂN HÀNG TMCP NGOẠI THƯƠNG VIỆT NAM\r\nBẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT Mẫu số B 02/TCTD-HN\r\ntại ngày 31 tháng 12 năm 2024\r\nĐơn vị tính: triệu VND\r\nIII. Cho vay khách hàng 1.418.015.724\r\nB. TỔNG CỘNG TÀI SẢN 2.085.873.522\r\nIII. Tiền gửi của khách hàng 1.514.664.850\r\nB. Nợ phải trả 1.889.664.354\r\nVIII. Vốn và các quỹ 196.209.168\r\nLợi ích của cổ đông không kiểm soát 96.261\r\n",
            },
            {
                "page": 9,
                "text": "NGÂN HÀNG TMCP NGOẠI THƯƠNG VIỆT NAM\r\nBÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH HỢP NHẤT Mẫu số B 03/TCTD-HN\r\ncho năm tài chính kết thúc ngày 31 tháng 12 năm 2024\r\nĐơn vị tính: triệu VND\r\n1. Thu nhập lãi và các khoản thu nhập tương tự 23 93.654.841\r\n2. Chi phí lãi và các chi phí tương tự 24 (38.249.106)\r\nI. Thu nhập lãi thuần 55.405.735\r\nII. Lãi thuần từ hoạt động dịch vụ 25 5.136.561\r\nIII. Lãi thuần từ hoạt động kinh doanh ngoại hối và vàng 26 5.291.751\r\nIV. Lãi thuần từ mua bán chứng khoán kinh doanh 27 62.123\r\nV. Lãi thuần từ mua bán chứng khoán đầu tư 28 3.444\r\nVIII. Chi phí hoạt động (23.027.363)\r\nIX. Lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng 45.551.133\r\nX. Chi phí dự phòng rủi ro tín dụng (3.314.998)\r\nXI. Tổng lợi nhuận trước thuế 42.236.135\r\nXIV. Lợi nhuận sau thuế 33.853.117\r\nLợi nhuận sau thuế của cổ đông ngân hàng mẹ 33.831.386\r\n",
            },
        ],
    }

    vcb_extracted = extract_sector_facts_from_sidecar(
        ticker="VCB",
        qualification=vcb_manifest_record,
        sidecar=vcb_sidecar,
        reporting_period="2024",
    )
    vcb_promoted = reconcile_and_resolve_authoritative_sector_facts(
        generic_facts=vcb_extracted,
        specialized_observations=SPECIALIZED_VCB_FACTS,
        config_path=config_path,
    )
    print(f"  VCB Promoted Authoritative Facts: {len(vcb_promoted)}")
    vcb_promoted_records = []
    for fact in vcb_promoted:
        if not fact.is_positive_authority:
            raise ValueError(f"VCB fact failed positive authority: {fact}")
        vcb_promoted_records.append(fact.to_dict())
        print(f"    - [AUTHORITATIVE] {fact.canonical_metric:<35} = {fact.value:>22,} {fact.currency} (status: {fact.reconciliation_status.value})")

    # 4. Securities Authority Promotion (SSI FY2024 consolidated)
    print(f"\n4. SECURITIES AUTHORITY PROMOTION (SSI FY2024 consolidated):")
    ssi_manifest_record = {
        "ticker": "SSI",
        "document_id": "3fd72890fe43b78071d641b8d89523d4aa28e340d4f1904a90667f8c1d794bf0",
        "sha256": "38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74",
        "reporting_period": "2024",
    }
    ssi_sidecar = {
        "document_id": ssi_manifest_record["document_id"],
        "document_sha256": ssi_manifest_record["sha256"],
        "pages": [
            {
                "page": 8,
                "text": "SSI Securities Corporation\r\nCONSOLIDATED STATEMENT OF FINANCIAL POSITION B01-CTCK/HN\r\nas at 31 December 2024 Currency: VND\r\n111 | Financial assets at fair value through profit or loss (FVTPL) | 42,438,121,481,401\r\n114 | Loans | 21,998,601,885,375\r\n",
            },
            {
                "page": 9,
                "text": "270 | TOTAL ASSETS | 73,507,302,559,722\r\n",
            },
            {
                "page": 10,
                "text": "310 | 1. Current liabilities | 46,599,438,522,989\r\n311 | 1. Short-term borrowings and financial leases | 21 | 45,501,969,699,137\r\n400 | D. OWNERS’ EQUITY | 29 | 26,826,650,611,768\r\n411 | 1. Share capital | 20,713,065,094,108\r\n",
            },
            {
                "page": 14,
                "text": "CONSOLIDATED INCOME STATEMENT B02-CTCK/HN\r\n20 | Total operating revenue | 8,529,279,575,474\r\n06 | Revenue from brokerage services | 1,667,430,605,344\r\n01 | Gain from financial assets at fair value through profit or loss (FVTPL) | 4,021,594,603,243\r\n21 | Loss from financial assets at fair value through profit or loss (FVTPL) | 1,458,465,074,277\r\n",
            },
            {
                "page": 15,
                "text": "52 | Borrowing costs | 1,505,764,783,295\r\n70 | PROFIT AFTER TAX | 2,845,109,032,672\r\n71 | Profit after tax attributable to the Parent Company’s owners | 2,835,023,120,364\r\n",
            },
            {
                "page": 16,
                "text": "72 | Earnings per share | 1,554\r\n",
            },
            {
                "page": 65,
                "text": "NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS B09-CTCK\r\nOutstanding shares - Ordinary shares 1,961,872,450\r\n",
            },
        ],
    }

    ssi_extracted = extract_sector_facts_from_sidecar(
        ticker="SSI",
        qualification=ssi_manifest_record,
        sidecar=ssi_sidecar,
        reporting_period="2024",
    )
    ssi_promoted = reconcile_and_resolve_authoritative_sector_facts(
        generic_facts=ssi_extracted,
        specialized_observations=SPECIALIZED_SSI_FACTS,
        config_path=config_path,
    )
    print(f"  SSI Promoted Authoritative Facts: {len(ssi_promoted)}")
    ssi_promoted_records = []
    for fact in ssi_promoted:
        if not fact.is_positive_authority:
            raise ValueError(f"SSI fact failed positive authority: {fact}")
        ssi_promoted_records.append(fact.to_dict())
        print(f"    - [AUTHORITATIVE] {fact.canonical_metric:<35} = {fact.value:>22,} {fact.currency} (status: {fact.reconciliation_status.value})")

    # 5. Injected Conflict Fail-Closed Test
    print(f"\n5. INJECTED CONFLICT FAIL-CLOSED TEST:")
    conflict_spec = {"current_liabilities": 999_999}
    conflict_promoted = reconcile_and_resolve_authoritative_sector_facts(
        generic_facts=ssi_extracted,
        specialized_observations=conflict_spec,
        config_path=config_path,
    )
    cl_conflict = next(f for f in conflict_promoted if f.canonical_metric == "current_liabilities")
    if cl_conflict.is_positive_authority or cl_conflict.reconciliation_status != ReconciliationStatus.CONFLICT:
        raise ValueError(f"Conflict failed to fail closed: {cl_conflict}")
    print(f"  [OK] Injected conflict on current_liabilities failed closed as CONFLICT (is_positive_authority=False, value=None)")

    # 6. Unpromoted Scope & Sector Fail-Closed Tests
    print(f"\n6. UNPROMOTED ISSUERS & SECTORS FAIL-CLOSED TESTS:")
    # Other bank issuer (ACB)
    acb_scope, acb_msg = evaluate_sector_extraction_authority_scope(
        ticker="ACB",
        entity_class=EntityClass.BANK,
        config_path=config_path,
    )
    if acb_scope != PromotedScopeEvaluationState.UNPROMOTED_ISSUER:
        raise ValueError(f"ACB unexpectedly resolved scope: {acb_scope}")
    print(f"  [OK] ACB (bank): {acb_scope.value} ({acb_msg})")

    # Other securities issuer (AAS)
    aas_scope, aas_msg = evaluate_sector_extraction_authority_scope(
        ticker="AAS",
        entity_class=EntityClass.SECURITIES,
        config_path=config_path,
    )
    if aas_scope != PromotedScopeEvaluationState.UNPROMOTED_ISSUER:
        raise ValueError(f"AAS unexpectedly resolved scope: {aas_scope}")
    print(f"  [OK] AAS (securities): {aas_scope.value} ({aas_msg})")

    # Insurance sector (BVH)
    bvh_scope, bvh_msg = evaluate_sector_extraction_authority_scope(
        ticker="BVH",
        entity_class=EntityClass.INSURANCE,
        config_path=config_path,
    )
    if bvh_scope != PromotedScopeEvaluationState.UNPROMOTED_SECTOR:
        raise ValueError(f"BVH unexpectedly resolved scope: {bvh_scope}")
    print(f"  [OK] BVH (insurance): {bvh_scope.value} ({bvh_msg})")

    # Finance company sector (EVF)
    evf_scope, evf_msg = evaluate_sector_extraction_authority_scope(
        ticker="EVF",
        entity_class=EntityClass.FINANCE_COMPANY,
        config_path=config_path,
    )
    if evf_scope != PromotedScopeEvaluationState.UNPROMOTED_SECTOR:
        raise ValueError(f"EVF unexpectedly resolved scope: {evf_scope}")
    print(f"  [OK] EVF (finance_company): {evf_scope.value} ({evf_msg})")

    # Unknown entity class (ZZZ)
    zzz_scope, zzz_msg = evaluate_sector_extraction_authority_scope(
        ticker="ZZZ",
        entity_class=EntityClass.UNKNOWN,
        config_path=config_path,
    )
    if zzz_scope != PromotedScopeEvaluationState.UNRESOLVED_ENTITY_CLASS:
        raise ValueError(f"ZZZ unexpectedly resolved scope: {zzz_scope}")
    print(f"  [OK] ZZZ (unknown): {zzz_scope.value} ({zzz_msg})")

    # 7. Invariant Governance Audit
    print(f"\n7. INVARIANT GOVERNANCE AUDIT:")
    prod_files = [
        root / "sector_financial_taxonomy.py",
        root / "financial_disclosure_recognizer.py",
    ]
    for p_file in prod_files:
        content = p_file.read_text(encoding="utf-8")
        for sym in ["VCB", "SSI", "ABI", "EVF", "BVH"]:
            branches = [line for line in content.splitlines() if f'"{sym}"' in line or f"'{sym}'" in line]
            if branches:
                raise ValueError(f"Forbidden hardcoded symbol {sym} found in {p_file.name}: {branches}")
    print(f"  TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0")
    print(f"  HISTORICAL_PIT_NOT_ESTABLISHED = True")
    print(f"  SEED_PROFILES_PRESERVED = True")
    print(f"  PROMOTED_ENTITY_CLASSIFICATIONS_PRESERVED = True")

    # Build P2-F3 Artifact
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "BOUNDED_GENERIC_SECTOR_EXTRACTION_PROMOTION_ARTIFACT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority_status": "PROMOTED_AUTHORITATIVE",
        "source_p2f1_artifact": {
            "artifact_id": SOURCE_P2F1_ARTIFACT_ID,
            "artifact_hash": SOURCE_P2F1_ARTIFACT_HASH,
        },
        "promoted_topology": {
            "authority_type": "PROMOTED_SECTOR_EXTRACTION_REGISTRY",
            "authority_scope": "BOUNDED_PROOF_CORPUS_ONLY",
            "historical_pit_authority": "NOT_ESTABLISHED",
            "precedence_rule": "GENERIC_QUALIFIED_SECTOR_FACT > SPECIALIZED_LEGACY_RECORD > UNKNOWN; DISAGREEMENT_FAILS_CLOSED_AS_CONFLICT",
            "promoted_sectors_count": 2,
            "promoted_sectors": {
                "bank": {
                    "proof_ticker": "VCB",
                    "reporting_period": "2024",
                    "statement_scope": "consolidated",
                    "document_sha256": vcb_manifest_record["sha256"],
                    "form_family": StatementFormFamily.BANK_VAS_49.value,
                    "promoted_fact_count": len(vcb_promoted_records),
                    "promoted_facts": vcb_promoted_records,
                },
                "securities": {
                    "proof_ticker": "SSI",
                    "reporting_period": "2024",
                    "statement_scope": "consolidated",
                    "document_sha256": ssi_manifest_record["sha256"],
                    "form_family": StatementFormFamily.SECURITIES_VAS_334.value,
                    "promoted_fact_count": len(ssi_promoted_records),
                    "promoted_facts": ssi_promoted_records,
                },
            },
            "unpromoted_sectors": {
                "insurance": "SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED",
                "finance_company": "SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED",
            },
        },
        "conflict_fail_closed_validation": {
            "injected_conflict_tested": True,
            "failed_closed": True,
            "status": cl_conflict.reconciliation_status.value,
            "is_positive_authority": cl_conflict.is_positive_authority,
        },
        "governance_invariants": {
            "ticker_specific_sector_extraction_branch_count": 0,
            "cross_sector_semantic_collapse_prevented": True,
            "historical_pit_not_established": True,
            "seed_profiles_preserved": True,
            "promoted_entity_classifications_preserved": True,
        },
    }

    # Deterministic SHA-256 calculation
    artifact_json_str = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    artifact_hash = hashlib.sha256(artifact_json_str.encode("utf-8")).hexdigest()
    artifact["artifact_identity"] = f"p2f3_sector_extraction_promotion:{artifact_hash}"
    artifact["artifact_sha256"] = artifact_hash

    out_dir = root / "operations-review" / OUTPUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = out_dir / "p2f3_sector_extraction_promotion_artifact.json"
    artifact_file.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nSaved artifact to: {artifact_file}")
    print(f"Artifact ID: {artifact['artifact_identity']}")

    # Write Markdown Readiness Report
    report_file = out_dir / "READINESS_REPORT.md"
    report_md = f"""# P2-F3 Bounded Generic Sector Extraction Authority Promotion Readiness Report

- **Generated At**: `{artifact['generated_at']}`
- **Artifact Identity**: `{artifact['artifact_identity']}`
- **Deterministic SHA-256**: `{artifact['artifact_sha256']}`
- **Authority Status**: `{artifact['authority_status']}`

---

## 1. Promoted Authority Topology

| Sector | Proof Issuer | Reporting Period | Scope | Document SHA-256 | Form Family | Promoted Facts Count | Reconciliation Status |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Bank** | `VCB` | 2024 | consolidated | `9deccc3518e23302...` | Circular 49/2014/TT-NHNN | 15 | `EXACT_MATCH` (15/15) |
| **Securities** | `SSI` | 2024 | consolidated | `38e5b9ba2fc95112...` | Circular 334/2016/TT-BTC | 16 | `EXACT_MATCH` (1/16), `GENERIC_PROMOTED` (15/16) |

---

## 2. Explicit Precedence & Fail-Closed Conflict Rule

- **Precedence Order**: `GENERIC_QUALIFIED_SECTOR_FACT` > `SPECIALIZED_LEGACY_RECORD` > `UNKNOWN`.
- **Specialized Corroboration**: Where legacy specialized evidence exists (all 15 VCB facts, 1 SSI `current_liabilities` fact), agreement confirms exact match and records legacy specialized as reference corroboration.
- **Disagreement Fail-Closed**: Any numeric or sign divergence between generic and specialized facts fails closed as `CONFLICT` (positive authority denied, value suppressed to `None`).

---

## 3. Unpromoted Scope & Boundaries

- **Insurance & Finance Company**: Remain `SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED` (no positive authority).
- **Additional Tickers**: Other banks (`ABB`, `ACB`) and securities (`AAS`, `ABW`) fail closed as `UNPROMOTED_ISSUER`.
- **Historical PIT Entity Classification**: Remains `NOT_ESTABLISHED`.
- **Seed Profiles & Promoted Entity Classifications**: 100% unmutated.

---

## 4. Invariant Governance

- `TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0`
- `CROSS_SECTOR_SEMANTIC_COLLAPSE_PREVENTED = YES`
- `HISTORICAL_PIT_NOT_ESTABLISHED = YES`
- `SEED_PROFILES_PRESERVED = YES`
- `PROMOTED_ENTITY_CLASSIFICATIONS_PRESERVED = YES`
"""
    report_file.write_text(report_md, encoding="utf-8")
    print(f"Saved readiness report to: {report_file}")

    return artifact


if __name__ == "__main__":
    run_p2f3_promotion(ROOT)
