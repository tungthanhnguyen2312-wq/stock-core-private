"""LEGACY_ENTITY_CLASSIFICATION_TRACKED_AUTHORITY_RECOVERY_V1: legacy recovery promotion runner.

MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1 (94e6aba) reported a final
1,382 INDUSTRIAL / 85 LIMITED / 25 UNKNOWN entity-family split and explicitly stated that
526 tickers were "already-classified" and preserved byte-identical. In fact only 6 of those
526 were resolvable from tracked `entity_classification_contract` authority (seed CSV +
original promoted manifest); the remaining 520 were supplied at replay time only through
`market_wide_financial_analysis_v2_scaleout.build_scaleout()`'s optional `legacy_records`
argument, itself populated from an untracked sibling-worktree artifact
(`financial_analysis_context/v2` engine replay of the `LEGACY_HISTORICAL_FROZEN_523_V1`
cohort -- see `tests/test_entity_classification_scaleout_replay.py`). That artifact is not
part of this repository's git history (`operations-review/` is gitignored), so the
1,382/85/25 split has never been reproducible from tracked repository inputs alone.

This tool recovers the classification (not the financial feature values, which stay a
separate, explicitly-labelled regression concern) from that legacy artifact into a fourth,
tracked, self-contained `entity_classification_contract` authority tier:

  config/promoted_entity_classifications_legacy_recovery_v1.json

Fail-closed rules:
  - A legacy record whose own `issuer_type` is missing/"unknown" is never promoted, even
    though the legacy engine's binary corporate-vs-not-corporate split had bucketed it into
    `OTHER_FINANCIAL_LIMITED_ANALYSIS` -- that bucketing is a structural default, not
    positive evidence of a specific financial entity type (see F88/OGC, independently
    confirmed UNKNOWN by FUNDAMENTAL_ENTITY_CLASS_AND_SECTOR_APPLICABILITY_SCALEOUT_V1).
  - A ticker already resolvable from tracked seed/original-promoted/scale-out authority is
    never duplicated into this tier; a ticker whose tracked authority *disagrees* with the
    legacy record is excluded and reported as a conflict, never silently overridden.

Every input is read-only. No production/runtime write, no network.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from entity_classification_contract import (  # noqa: E402
    ClassificationStatus,
    ConfidenceSemantics,
    DEFAULT_LEGACY_RECOVERY_CLASSIFICATIONS_PATH,
    EntityClass,
    EntityClassificationRecord,
    EvidenceTier,
    compute_classification_evidence_id,
    load_promoted_entity_classifications,
    load_scaleout_promoted_entity_classifications,
    load_seed_profiles,
    resolve_layered_entity_classification,
)

AUTHORITY_TYPE = "RECOVERED_PREVIOUSLY_ACCEPTED_CURRENT_STATE_AUTHORITY"
SOURCE_ID = "legacy_entity_classification_tracked_authority_recovery/v1"
CONSUMING_MILESTONE = "MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1"
CONSUMING_MILESTONE_CHECKPOINT = "94e6abae38d71aa4f43331d2d212f38fa7de1cf7"
LEGACY_COHORT_SELECTOR = "LEGACY_HISTORICAL_FROZEN_523_V1"
DEFAULT_OUT_DIR = (
    PROJECT_ROOT / "operations-review"
    / "legacy-entity-classification-tracked-authority-recovery-v1-20260902"
)
VALID_ENTITY_CLASSES = {e.value for e in EntityClass if e != EntityClass.UNKNOWN}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_recovery(
    *,
    legacy_engine_artifact: Path,
    generated_at: str,
) -> tuple[dict, dict]:
    """Return (promotion_payload, diagnostics_payload)."""
    legacy = _load_json(legacy_engine_artifact)
    if legacy.get("contract_version") != "financial_analysis_context/v2":
        raise SystemExit("LEGACY_ENGINE_ARTIFACT_CONTRACT_UNSUPPORTED")
    legacy_records = legacy.get("records")
    if not isinstance(legacy_records, dict) or not legacy_records:
        raise SystemExit("LEGACY_ENGINE_ARTIFACT_RECORDS_INVALID")
    if (legacy.get("replay") or {}).get("cohort_selector") != LEGACY_COHORT_SELECTOR:
        raise SystemExit("LEGACY_ENGINE_ARTIFACT_COHORT_SELECTOR_UNEXPECTED")
    legacy_artifact_identity = legacy.get("artifact_identity")
    if not legacy_artifact_identity:
        raise SystemExit("LEGACY_ENGINE_ARTIFACT_IDENTITY_MISSING")

    seed = load_seed_profiles()
    original_promoted = load_promoted_entity_classifications()
    scaleout_promoted = load_scaleout_promoted_entity_classifications()

    promoted_records: dict[str, dict] = {}
    diagnostics_rows: list[dict] = []
    class_breakdown: Counter = Counter()
    already_tracked: list[dict] = []
    conflicts: list[dict] = []
    legacy_unknown: list[dict] = []

    for ticker in sorted(legacy_records):
        rec = legacy_records[ticker]
        issuer_type = str(rec.get("issuer_type") or "").strip().lower()
        analysis_family = rec.get("analysis_family")

        if not issuer_type or issuer_type == "unknown" or issuer_type not in VALID_ENTITY_CLASSES:
            legacy_unknown.append({"ticker": ticker, "legacy_issuer_type": rec.get("issuer_type"),
                                    "legacy_analysis_family": analysis_family})
            diagnostics_rows.append({"ticker": ticker, "outcome": "LEGACY_UNKNOWN",
                                      "reason": "legacy issuer_type is missing/unknown; the legacy "
                                                "engine's binary corporate-vs-not-corporate split is "
                                                "not positive evidence of a specific entity class"})
            continue

        # What does tracked authority *other than this new tier* already know? Pass an
        # explicit empty legacy_recovery_records so this check never sees its own output,
        # including on a re-run after the manifest below already exists on disk.
        existing = resolve_layered_entity_classification(
            ticker, seed_profiles=seed, promoted_records=original_promoted,
            scaleout_promoted_records=scaleout_promoted, legacy_recovery_records={},
        )
        if existing.is_positive_authority:
            if existing.resolved_entity_class.value == issuer_type:
                already_tracked.append({"ticker": ticker, "entity_class": issuer_type,
                                        "authority_tier": existing.authority_tier})
                diagnostics_rows.append({"ticker": ticker, "outcome": "ALREADY_TRACKED_IDENTICAL",
                                          "reason": f"already resolves via {existing.authority_tier}"})
            else:
                conflicts.append({"ticker": ticker, "legacy_entity_class": issuer_type,
                                  "tracked_entity_class": existing.resolved_entity_class.value,
                                  "tracked_authority_tier": existing.authority_tier})
                diagnostics_rows.append({"ticker": ticker, "outcome": "CONFLICT_WITH_TRACKED_HIGHER_AUTHORITY",
                                          "reason": f"legacy={issuer_type} vs tracked={existing.resolved_entity_class.value} "
                                                    f"via {existing.authority_tier}; excluded, never overridden"})
            continue

        entity_class = issuer_type
        issuer_identity = f"issuer:{ticker}"
        classification_reason = (
            "recovered_previously_accepted_legacy_authority: byte-identical to the "
            f"{LEGACY_COHORT_SELECTOR} replay in financial_analysis_context/v2 that "
            f"{CONSUMING_MILESTONE} ({CONSUMING_MILESTONE_CHECKPOINT[:7]}) itself consumed "
            "as pre-existing classification authority via build_scaleout()'s legacy_records "
            "parameter"
        )
        supporting_evidence = {
            "legacy_source_artifact_identity": legacy_artifact_identity,
            "legacy_source_cohort_selector": LEGACY_COHORT_SELECTOR,
            "legacy_source_issuer_type": rec.get("issuer_type"),
            "legacy_source_analysis_family": analysis_family,
            "legacy_source_current_research_ready": rec.get("current_research_ready"),
            "consuming_milestone": CONSUMING_MILESTONE,
            "consuming_milestone_checkpoint": CONSUMING_MILESTONE_CHECKPOINT,
            "originally_accepted_at": legacy.get("requested_at"),
        }
        evidence_id = compute_classification_evidence_id(
            issuer_identity=issuer_identity, ticker=ticker, entity_class=entity_class,
            classification_status=ClassificationStatus.QUALIFIED.value, source_id=SOURCE_ID,
            evidence_payload=supporting_evidence,
        )
        record = EntityClassificationRecord(
            issuer_identity=issuer_identity,
            ticker=ticker,
            legal_name=None,
            entity_class=EntityClass(entity_class),
            classification_status=ClassificationStatus.QUALIFIED,
            confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
            evidence_tier=EvidenceTier.LEGACY_ACCEPTED_MILESTONE_REPLAY,
            classification_evidence_id=evidence_id,
            source_id=SOURCE_ID,
            source_record_id=ticker,
            effective_from=None,
            knowledge_available_at=None,
            verified_at=generated_at,
            classification_reason=classification_reason,
            supporting_evidence=supporting_evidence,
        )
        class_breakdown[entity_class] += 1
        promoted_records[ticker] = record.to_dict()
        diagnostics_rows.append({"ticker": ticker, "outcome": "RECOVERED", "entity_class": entity_class})

    promotion_payload = {
        "schema_version": "1.0.0",
        "contract_version": "entity_classification_contract/v1",
        "authority_type": AUTHORITY_TYPE,
        "authority_scope": "CURRENT_STATE_ONLY",
        "historical_pit_authority": "NOT_ESTABLISHED",
        "source_artifact_id": "financial_analysis_context/v2",
        "source_artifact_hash": legacy_artifact_identity.split(":")[-1],
        "source_cohort_selector": LEGACY_COHORT_SELECTOR,
        "source_consuming_milestone": CONSUMING_MILESTONE,
        "source_consuming_milestone_checkpoint": CONSUMING_MILESTONE_CHECKPOINT,
        "source_seed_authority": "config/ticker_entity_profiles.csv",
        "source_original_promoted_authority": "config/promoted_entity_classifications.json",
        "source_scaleout_promoted_authority": "config/promoted_entity_classifications_scaleout_v1.json",
        "recovery_reason": (
            "MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1's own replay depended on an "
            "untracked sibling-worktree artifact for 520 of its 526 pre-existing classified "
            "tickers; this manifest persists that previously-accepted classification into tracked, "
            "self-contained authority so no future replay needs the untracked artifact"
        ),
        "promoted_at": generated_at,
        "promoted_record_count": len(promoted_records),
        "class_breakdown": {
            "corporate": class_breakdown.get("corporate", 0),
            "bank": class_breakdown.get("bank", 0),
            "securities": class_breakdown.get("securities", 0),
            "insurance": class_breakdown.get("insurance", 0),
            "finance_company": class_breakdown.get("finance_company", 0),
            "unknown": 0,
        },
        "promoted_records": promoted_records,
    }

    diagnostics_payload = {
        "schema_version": "1.0.0",
        "artifact_type": "LEGACY_ENTITY_CLASSIFICATION_TRACKED_AUTHORITY_RECOVERY_DIAGNOSTICS",
        "generated_at": generated_at,
        "legacy_record_count": len(legacy_records),
        "legacy_artifact_identity": legacy_artifact_identity,
        "recovered_count": len(promoted_records),
        "already_tracked_identical_count": len(already_tracked),
        "already_tracked_identical": already_tracked,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "legacy_unknown_count": len(legacy_unknown),
        "legacy_unknown": legacy_unknown,
        "rows": diagnostics_rows,
    }
    return promotion_payload, diagnostics_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--legacy-engine-artifact", type=Path, required=True,
                        help="Retained financial_analysis_context/v2 engine replay of the "
                             "LEGACY_HISTORICAL_FROZEN_523_V1 cohort (the exact artifact "
                             "tests/test_entity_classification_scaleout_replay.py points at).")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--promoted-output", type=Path, default=DEFAULT_LEGACY_RECOVERY_CLASSIFICATIONS_PATH)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args()

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    promotion, diagnostics = build_recovery(
        legacy_engine_artifact=args.legacy_engine_artifact, generated_at=generated_at,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "legacy_recovery_diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    args.promoted_output.parent.mkdir(parents=True, exist_ok=True)
    args.promoted_output.write_text(
        json.dumps(promotion, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "legacy_record_count": diagnostics["legacy_record_count"],
        "recovered_count": diagnostics["recovered_count"],
        "class_breakdown": promotion["class_breakdown"],
        "already_tracked_identical_count": diagnostics["already_tracked_identical_count"],
        "conflict_count": diagnostics["conflict_count"],
        "legacy_unknown_count": diagnostics["legacy_unknown_count"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
