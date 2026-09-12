"""Descriptive, cadence-aware macro presentation context for the AI handoff.

This wraps the existing runtime macro synchronizer's retained web snapshot
(``macro_sync.py`` -> ``data/macro_snapshot.json``) for AI-consumer presentation.

It is deliberately NOT ``current_macro_regime/v1`` (see ``current_macro_regime.py``):
that is a distinct, evidence-bound research artifact with its own regime/state-axis
classification, retained raw provider payloads, and session-compatibility contract.
The runtime macro snapshot has no regime classification and no retained raw evidence
per observation -- presenting it under the ``current_macro_regime`` contract name would
be schema masquerading and an implicit authority upgrade. This module's
``CONTRACT_VERSION`` names it as a separate, purely descriptive presentation context.

No network calls happen here. The snapshot file is either already on disk (refreshed by
the existing ``macro_sync.py`` subprocess elsewhere) or it is not; this module only reads
and reshapes whatever is retained.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from field_temporal_contract import stable_id
from freshness_history import freshness_envelope

CONTRACT_VERSION = "macro_presentation_context/v1"

# macro_sync.py's own SOURCE_LABELS values -> whether the originating data source is an
# official/first-party quote or an unofficial market-data mirror. Being "current" never
# upgrades a source's authority tier -- Yahoo stays unofficial regardless of freshness.
SOURCE_AUTHORITY = {
    "FRED": "OFFICIAL_PUBLIC_SOURCE",
    "World Bank": "OFFICIAL_MULTILATERAL_SOURCE",
    "Vietcombank": "FIRST_PARTY_QUOTE_UNOFFICIAL_TRANSPORT",
    "SJC": "FIRST_PARTY_QUOTE_UNOFFICIAL_TRANSPORT",
    "Yahoo Finance": "UNOFFICIAL_MARKET_DATA_SOURCE",
}

# macro_sync.py FREQUENCY_META keys -> freshness_history.py domain rules. "annual" gets its
# own domain (not folded into macro_quarterly) so a 300-day-old GDP print is not misjudged
# stale against a 92-day quarterly cadence.
FREQUENCY_TO_DOMAIN = {
    "daily": "macro_daily",
    "weekly": "macro_weekly",
    "monthly": "macro_monthly",
    "quarterly": "macro_quarterly",
    "annual": "macro_annual",
}


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {k: v for k, v in value.items() if k not in ("artifact_identity", "artifact_sha256")}
    digest = stable_id(payload)
    return {"artifact_sha256": digest, "artifact_identity": "macro_presentation_context:" + digest}


def load_snapshot(path: Path) -> Mapping[str, Any] | None:
    """Read the retained macro_sync web snapshot. Never raises; a missing/corrupt file is
    reported as an absent snapshot, not a Daily-blocking failure."""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _indicator_context(row: Mapping[str, Any], *, generated_at: str) -> dict[str, Any]:
    frequency = str(row.get("frequency") or "")
    domain = FREQUENCY_TO_DOMAIN.get(frequency, "macro_daily")
    envelope = freshness_envelope(
        domain=domain,
        as_of_date=row.get("period"),
        generated_at=row.get("pipeline_updated_at") or generated_at,
        source=row.get("source"),
        reference_at=generated_at,
    )
    source_label = row.get("source")
    return {
        "key": row.get("key"),
        "label": row.get("label"),
        "category": row.get("category"),
        "value": row.get("value"),
        "unit": row.get("unit"),
        "period": row.get("period"),
        "expected_frequency": frequency,
        "source": source_label,
        "source_authority": SOURCE_AUTHORITY.get(str(source_label), "UNKNOWN_SOURCE_AUTHORITY"),
        "source_url": row.get("source_url"),
        "freshness_domain": domain,
        "freshness": envelope,
    }


def build(
    snapshot: Mapping[str, Any] | None,
    *,
    generated_at: str,
    refresh_status: str | None = None,
    refresh_reason_code: str | None = None,
) -> dict[str, Any]:
    """Build the descriptive macro presentation context from a retained snapshot dict
    (as loaded by ``load_snapshot``). Never raises and never blocks: an absent or empty
    snapshot yields an explicit UNAVAILABLE context, not an exception."""
    if not isinstance(snapshot, Mapping) or not snapshot.get("indicators"):
        artifact = {
            "schema_version": "1.0.0",
            "contract_version": CONTRACT_VERSION,
            "status": "UNAVAILABLE",
            "reason_code": "NO_RETAINED_MACRO_SNAPSHOT" if refresh_status != "FAILED" else "MACRO_SNAPSHOT_REFRESH_FAILED_AND_NO_RETAINED_SNAPSHOT",
            "refresh_status": refresh_status,
            "refresh_reason_code": refresh_reason_code,
            "generated_at": generated_at,
            "indicators": {},
            "foreign_flow": None,
            "authority_boundary": {
                "current_research_only": True,
                "forecast_probability_target_recommendation_sizing_execution": "NOT_EMITTED",
                "distinct_from": "current_macro_regime/v1",
            },
            "is_actionable": False,
        }
        artifact.update(content_identity(artifact))
        return artifact

    indicators = {
        str(row.get("key")): _indicator_context(row, generated_at=generated_at)
        for row in snapshot["indicators"]
        if row.get("key")
    }
    current_count = sum(1 for row in indicators.values() if row["freshness"]["freshness_status"] == "current")
    stale_count = sum(1 for row in indicators.values() if row["freshness"]["freshness_status"] in {"stale", "expiring"})
    unknown_count = sum(1 for row in indicators.values() if row["freshness"]["freshness_status"] in {"missing", "unknown"})
    if not indicators:
        status = "UNAVAILABLE"
    elif stale_count == 0 and unknown_count == 0:
        status = "AVAILABLE"
    elif current_count > 0:
        status = "PARTIAL"
    else:
        status = "UNAVAILABLE"

    foreign_flow = snapshot.get("foreign_flow")
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "reason_code": None if status == "AVAILABLE" else "SOME_OR_ALL_SERIES_STALE_OR_UNKNOWN",
        "refresh_status": refresh_status,
        "refresh_reason_code": refresh_reason_code,
        "generated_at": generated_at,
        "snapshot_generated_at": snapshot.get("generated_at"),
        "snapshot_data_as_of": snapshot.get("data_as_of"),
        "quality": {
            "catalog_count": len(indicators),
            "current_count": current_count,
            "stale_or_expiring_count": stale_count,
            "unknown_or_missing_count": unknown_count,
        },
        "indicators": indicators,
        # macro_sync's own snapshot-level foreign-flow field: always a distinct, honestly
        # unavailable slot in this snapshot today. Never conflate with the qualified DNSE
        # foreign-flow/value evidence (a separate current-session input) or with the broader
        # market_flow_positioning product -- see ai_handoff_source_freshness_matrix.py.
        "foreign_flow": {
            "status": str((foreign_flow or {}).get("status") or "unavailable").upper(),
            "reason": (foreign_flow or {}).get("reason"),
            "source": "macro_sync_runtime_snapshot",
        },
        "authority_boundary": {
            "current_research_only": True,
            "forecast_probability_target_recommendation_sizing_execution": "NOT_EMITTED",
            "distinct_from": "current_macro_regime/v1",
        },
        "is_actionable": False,
    }
    artifact.update(content_identity(artifact))
    return artifact


def build_from_runtime(
    root: Path,
    runtime_root: Path,
    *,
    generated_at: str,
    refresh_status: str | None = None,
    refresh_reason_code: str | None = None,
) -> dict[str, Any]:
    """Production entry point: load the retained snapshot from the runtime root and build
    the presentation context. A failed or skipped refresh does not prevent loading whatever
    snapshot is already retained on disk from a previous run."""
    snapshot = load_snapshot(Path(runtime_root) / "data" / "macro_snapshot.json")
    return build(snapshot, generated_at=generated_at, refresh_status=refresh_status, refresh_reason_code=refresh_reason_code)
