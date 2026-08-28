"""Build the bounded A1 semantic-contract validation artifact without runtime mutation."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bitemporal_semantic_contract import (
    CONTRACT_VERSION, PublicationAuthorityTier, PublicationTime, TemporalPrecision,
    build_temporal_envelope, content_identity, project_official_evidence_temporal_metadata,
    project_provider_temporal_metadata, propagate_derived_knowledge, validate_valid_time,
)


MANIFEST = ROOT / "operations-review" / "governed-official-evidence-v1" / "official_document_acquisition_manifest.json"
CITATIONS = ROOT / "operations-review" / "governed-official-evidence-v1" / "data" / "official-evidence" / "financial_identity_citations.jsonl"
KBS_ARTIFACT = ROOT / "operations-review" / "kbs-quarterly-financial-lookback-and-semantic-retention-v1-20260828" / "artifact.json"
OUTPUT = ROOT / "operations-review" / "a1-bitemporal-semantic-contract-v1-20260828" / "artifact.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _citation_count() -> int:
    return sum(bool(line.strip()) for line in CITATIONS.read_text(encoding="utf-8").splitlines()) if CITATIONS.is_file() else 0


def build_artifact() -> dict:
    manifest = _read_json(MANIFEST)
    kbs = _read_json(KBS_ARTIFACT)
    documents = [row for row in manifest.get("records", []) if isinstance(row, dict)]
    projected = [project_official_evidence_temporal_metadata(row) for row in sorted(documents, key=lambda row: str(row.get("document_id") or row.get("sha256")))[:3]]
    exact = build_temporal_envelope(
        valid_time=validate_valid_time(domain="MARKET_OBSERVATION", reference_session="2026-08-25"),
        publication_time=PublicationTime("2026-08-25T17:30:00+07:00", TemporalPrecision.EXACT_DATETIME,
            PublicationAuthorityTier.OFFICIAL_ISSUER_IR_OR_EXCHANGE, "SYNTHETIC_CONTRACT_FIXTURE", "QUALIFIED", "AWARE"),
        first_observed_at=None, raw_identity="synthetic-raw-identity", governed_sessions=["2026-08-25", "2026-08-26"],
    ).to_dict()
    derived = propagate_derived_knowledge(required_inputs=[exact["knowledge_resolution"], projected[0]["knowledge_resolution"]] if projected else [exact["knowledge_resolution"]]).to_dict()
    publication_dates = sum(bool(row.get("published_at") or row.get("publication_date")) for row in documents)
    observed_only = sum(not (row.get("published_at") or row.get("publication_date")) and bool(row.get("observed_at") or row.get("retrieved_at")) for row in documents)
    retained_kbs = next((row for row in kbs.get("metadata", []) if isinstance(row, dict)), {})
    kbs_projection = project_provider_temporal_metadata(provider="KBS", metadata=retained_kbs,
                                                          first_observed_at=retained_kbs.get("retrieved_at"))
    artifact = {
        "contract_version": CONTRACT_VERSION, "implementation_commit": "PRE_COMMIT_LOCAL_CHECKPOINT",
        "support_evidence": {"anti_gravity_v2": "UNAVAILABLE_AT_STATED_PATH_NOT_USED_AS_AUTHORITY"},
        "official_panel_reconciliation": {
            "AUTHORITATIVE_ISSUER_REGISTRY_COUNT": 13,
            "GOVERNED_OFFICIAL_DOCUMENT_COUNT": len(documents),
            "GOVERNED_OFFICIAL_UNIQUE_TICKER_COUNT": len({str(row.get("ticker")) for row in documents if row.get("ticker")}),
            "DOCUMENTS_WITH_QUALIFIED_PUBLICATION_DATE_COUNT": publication_dates,
            "DOCUMENTS_WITHOUT_QUALIFIED_PUBLICATION_DATE_COUNT": len(documents) - publication_dates,
            "DOCUMENTS_FIRST_OBSERVED_ONLY_COUNT": observed_only,
            "OFFICIAL_FACT_COUNT": _citation_count(), "OFFICIAL_CITATION_COUNT": _citation_count(),
            "historical_temporal_scope": "READY_FOR_RETAINED_QUALIFIED_PANEL_ONLY_NOT_MARKET_WIDE_PIT_READY",
        },
        "semantic_examples": {
            "official_retained_vectors": projected,
            "synthetic_exact_publication_vector": exact,
            "kbs_retained_metadata_projection": {"source_metadata_identity": retained_kbs.get("metadata_identity"),
                                                   "projection": kbs_projection},
            "dnse_provider_mapping_fixture": project_provider_temporal_metadata(provider="DNSE", metadata={"lastUpdated": "2026-08-25T19:00:00+07:00"}, first_observed_at="2026-08-25T18:00:00+07:00"),
            "derived_required_input_example": derived,
        },
        "golden_vector_provenance": {"REAL_RETAINED_VECTOR": len(projected), "REAL_RETAINED_VECTOR_WITH_DERIVED_EXPECTED_OUTPUT": 0,
                                     "SYNTHETIC_CONTRACT_FIXTURE": 3, "UNVERIFIED_LITERAL_REJECTED": 0},
        "authority_boundaries": {"eod_cutoff": "18:00 Asia/Ho_Chi_Minh OWNER_OPERATING_CONVENTION_V1 safety cutoff, not exchange close",
            "close_price_execution_eligibility": "NOT_ESTABLISHED", "raw_as_traded": "NOT_PROMOTED",
            "historical_price_pit": "BLOCKED", "historical_full_system_backtest": "BLOCKED", "runtime_database_mutation": "NONE"},
        "test_summary": {"focused_contract_tests": "see tests/test_bitemporal_semantic_contract.py", "deterministic": True},
    }
    artifact.update(content_identity(artifact))
    return artifact


def run(output: Path = OUTPUT) -> dict:
    artifact = build_artifact()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    run()
