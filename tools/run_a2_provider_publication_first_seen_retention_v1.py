"""Write the deterministic A2 temporal-retention validation summary; no acquisition occurs."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from temporal_retention import TEMPORAL_RETENTION_CONTRACT_VERSION


OUTPUT = ROOT / "operations-review" / "a2-provider-publication-first-seen-retention-v1-20260829" / "artifact.json"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_artifact() -> dict:
    artifact = {
        "contract": "a2_provider_publication_and_first_seen_retention/v1",
        "temporal_retention_contract": TEMPORAL_RETENTION_CONTRACT_VERSION,
        "scope": "prospective_retention_only_no_network_no_runtime_database_mutation",
        "retention_surfaces": {
            "governed_official_financial_document_acquisition": "ENABLED_QUALIFIED_PUBLICATION_ONLY_WHEN_EXPLICITLY_QUALIFIED",
            "kbs_quarterly_financial_sidecars": "ENABLED_PROVIDER_METADATA_RETAINED_LEGACY_RECEIPT_UNKNOWN",
            "dnse_closed_ohlc_websocket_shadow": "ENABLED_PROSPECTIVE_RECEIPT_AND_PROVIDER_EVENT",
            "offline_official_corporate_event_import": "ENABLED_RECEIPT_RETAINED_PUBLICATION_UNQUALIFIED_UNLESS_SEMANTIC_GATE_EXISTS",
        },
        "temporal_fitness_matrix": {
            "qualified_exact_publication": "QUALIFIED_SOURCE_PUBLICATION_EXACT",
            "qualified_date_only_publication": "QUALIFIED_SOURCE_PUBLICATION_DATE_ONLY",
            "provider_or_unqualified_with_aware_receipt": "FIRST_OBSERVED_FORWARD_ONLY",
            "legacy_or_timezone_unknown_receipt": "BLOCKED",
        },
        "invariants": [
            "raw_receipt_is_utc_and_captured_at_byte_or_message_boundary",
            "http_metadata_is_not_publication_authority",
            "provider_dates_are_not_official_publication",
            "identical_bytes_preserve_earliest_first_observed",
            "changed_bytes_remain_distinct_and_only_same_logical_identity_may_link_supersession",
            "no_historical_backfill_with_current_timestamp",
            "raw_as_traded_historical_price_pit_and_same_close_execution_remain_blocked",
        ],
        "outcome": "OUTCOME_B_PROVIDER_TEMPORAL_RETENTION_ACTIVE_WITH_HISTORICAL_CEILING",
    }
    identity_payload = dict(artifact)
    artifact["artifact_identity"] = "a2_provider_temporal_retention:" + hashlib.sha256(canonical_json(identity_payload).encode("utf-8")).hexdigest()
    return artifact


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_artifact(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
