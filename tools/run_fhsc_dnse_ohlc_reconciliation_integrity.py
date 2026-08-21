"""Replay FHSC/DNSE OHLC integrity checks from retained evidence only."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fhsc_historical_price_semantics import calibration_matrix, retained_dnse_ohlc  # noqa: E402


PRIOR_OUTPUT = ROOT / "operations-review" / "fhsc-historical-price-semantics-qualification-v1-20260821"
PRIOR_ARTIFACT = PRIOR_OUTPUT / "fhsc_historical_price_semantics_qualification_artifact.json"
DNSE_SNAPSHOT = ROOT / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20260820" / "p3f9b_mva_exact_session_snapshot.json"
OUTPUT = ROOT / "operations-review" / "fhsc-dnse-ohlc-reconciliation-integrity-v1-20260821"
ARTIFACT_PATH = OUTPUT / "fhsc_dnse_ohlc_reconciliation_integrity_artifact.json"


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _restored_fhsc_records(prior: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for item in prior["ohcl_scale_matrix"]["fhsc_retained_evidence"]:
        records.append({
            "symbol": item["symbol"], "successful": True, "raw_path": ROOT / item["raw_path"],
            "raw_sha256": item["sha256"], "request_url": item["request_url"],
        })
    return records


def _group_before_ssi(prior: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in prior["ohcl_scale_matrix"]["pairs"] if row["instrument"] == "SSI"]
    sessions: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["classification"] in {"EXACT_1_TO_1", "EXACT_1000_TO_1"}:
            continue
        item = sessions.setdefault(row["session"], {"session": row["session"], "fields": {}})
        item["fields"][row["field"]] = {
            "fhsc_retained_raw_value": row["fhsc_raw_value"],
            "dnse_retained_snapshot_value": row["dnse_raw_value"],
            "ratio_dnse_to_fhsc": row["ratio_dnse_to_fhsc"],
            "prior_classification": row["classification"],
            "reason": "MIXED_DNSE_SNAPSHOT_REPRESENTATION_INVALIDATES_COMPARISON",
        }
    return [sessions[key] for key in sorted(sessions)]


def _stable_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()
    return payload | {"artifact_sha256": digest, "artifact_identity": f"fhsc_dnse_ohlc_reconciliation_integrity:{digest}"}


def build_artifact(prior: dict[str, Any], matrix: dict[str, Any], dnse_identity: dict[str, Any]) -> dict[str, Any]:
    hpg_trace = [row for row in matrix["pairs"] if row["instrument"] == "HPG" and row["session"] == "2026-08-20"]
    return _stable_artifact({
        "schema_version": "1.0.0",
        "contract_version": "fhsc_dnse_ohlc_reconciliation_integrity/v1",
        "artifact_type": "FHSC_DNSE_OHLC_RECONCILIATION_INTEGRITY_REVIEW",
        "retained_evidence": {
            "prior_calibration_artifact": {"path": str(PRIOR_ARTIFACT.relative_to(ROOT)).replace("\\", "/"), "sha256": _sha256_bytes(PRIOR_ARTIFACT), "identity": prior["artifact_identity"]},
            "dnse_snapshot": dnse_identity,
            "fhsc_raw_responses": matrix["fhsc_retained_evidence"],
        },
        "hpg_2026_08_20_field_trace": hpg_trace,
        "dnse_anchor_integrity": {
            "status": "UNSUITABLE_FOR_FHSC_OHLC_SCALE_CALIBRATION",
            "source_materializer": "mva_exact_session_snapshot._observation_rows",
            "source_materializer_transform": {"open": "identity", "high": "identity", "low": "identity", "close": "float(provider_close) * 1000.0"},
            "field_representation": dnse_identity["field_representation"],
            "reason": dnse_identity["anchor_exclusion_reason"],
        },
        "fhsc_raw_field_integrity": {
            "status": "PASS",
            "parser": "fhsc_retained_live_reconciliation.parse_retained_history",
            "rule": "All O/H/L/C values are read from aligned arrays in the same SHA-verified retained response/session; no FHSC normalization is applied.",
        },
        "ssi_six_session_deviation_analysis": _group_before_ssi(prior),
        "primary_root_cause": "MIXED_SOURCE_REPRESENTATION_DEFECT",
        "secondary_findings": [
            "DNSE_CLOSE_MVA_SNAPSHOT_X1000_WHILE_OPEN_HIGH_LOW_PROVIDER_NATIVE",
            "Prior calibration compared mixed DNSE retained snapshot representations to FHSC provider-native values.",
            "No retained evidence establishes an FHSC field-specific numeric scale.",
        ],
        "correction": {
            "implemented": "Calibration requires explicit, uniform DNSE OHLC field representations. Mixed or undeclared anchors yield NOT_COMPARABLE for every OHLC field.",
            "evidence_mutated": False,
            "provider_contract_mutated": False,
        },
        "before_after_scale_matrix": {
            "before": {"field_summary": prior["ohcl_scale_matrix"]["field_summary"], "total_pairs": prior["ohcl_scale_matrix"]["total_pairs"], "total_comparable_pairs": prior["ohcl_scale_matrix"]["total_comparable_pairs"]},
            "after": {"field_summary": matrix["field_summary"], "total_pairs": matrix["total_pairs"], "total_comparable_pairs": matrix["total_comparable_pairs"], "excluded_pair_count": matrix["excluded_pair_count"], "excluded_reason_counts": matrix["excluded_reason_counts"], "maximum_residual_after_candidate_x1000": matrix["maximum_residual_after_candidate_x1000"]},
        },
        "normalization_verdict": {
            "status": "NO_TRANSFORM_QUALIFIED",
            "reason": "DNSE calibration anchor is representation-inconsistent; no raw-to-raw or explicitly-normalized-to-normalized 10x10 OHLC comparison remains.",
            "authority_effect": "NONE",
        },
        "authority_boundaries": {
            "fhsc_promoted": False, "dnse_authority_altered": False, "raw_as_traded_promoted": False,
            "historical_adjustment_basis_promoted": False, "volume_or_foreign_flow_qualified": False,
            "runtime_or_database_mutated": False, "network_requests_issued": False,
        },
    })


def main() -> int:
    prior = json.loads(PRIOR_ARTIFACT.read_text(encoding="utf-8"))
    dnse_rows, dnse_identity = retained_dnse_ohlc(DNSE_SNAPSHOT)
    matrix = calibration_matrix(dnse_rows, _restored_fhsc_records(prior))
    artifact = build_artifact(prior, matrix, dnse_identity)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if ARTIFACT_PATH.exists():
        existing = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        if existing.get("artifact_identity") != artifact["artifact_identity"]:
            raise FileExistsError("IMMUTABLE_ARTIFACT_PATH_ALREADY_EXISTS_WITH_DIFFERENT_CONTENT")
    else:
        ARTIFACT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
