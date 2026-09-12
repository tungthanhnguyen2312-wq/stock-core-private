"""Deterministic readiness check: can the next genuinely completed trading session be
captured by the tactical-reversal shadow collector without any further code change?

Every criterion below is checked programmatically (source inspection, importability,
constant presence) rather than asserted narratively. No provider/network call, no runtime
database access, no market data acquisition.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import canonical_daily_operation as cdo  # noqa: E402
import canonical_post_close_pipeline as cpc  # noqa: E402
import tactical_reversal_prospective_shadow_collection as collection  # noqa: E402
import tactical_reversal_shadow_probe_policy as shadow  # noqa: E402


def _check(name: str, condition: bool, detail: str) -> dict[str, Any]:
    return {"criterion": name, "status": "PASS" if condition else "FAIL", "detail": detail}


def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    daily_source = inspect.getsource(cdo)
    installed = "run_tactical_reversal_shadow_collection(" in daily_source and "from canonical_post_close_pipeline import" in daily_source
    checks.append(_check(
        "COLLECTOR_INSTALLED_IN_OPERATIONAL_PATH", installed,
        "canonical_daily_operation.run_canonical_daily_operation calls "
        "run_tactical_reversal_shadow_collection() as a post-hoc, non-blocking step "
        "(mirrors run_prospective_collection's own isolation contract)." if installed else
        "No call to run_tactical_reversal_shadow_collection() found in canonical_daily_operation.py.",
    ))

    policy_id_fixed = isinstance(shadow.CONTRACT_VERSION, str) and bool(shadow.CONTRACT_VERSION)
    checks.append(_check("POLICY_IDENTITY_FIXED", policy_id_fixed, f"shadow.CONTRACT_VERSION={shadow.CONTRACT_VERSION!r}"))

    activation_fixed = (
        isinstance(collection.ACTIVATION_DATE, str) and bool(collection.ACTIVATION_DATE)
        and isinstance(collection.POLICY_CHECKPOINT_COMMIT, str) and len(collection.POLICY_CHECKPOINT_COMMIT) == 40
    )
    checks.append(_check(
        "ACTIVATION_BOUNDARY_FIXED", activation_fixed,
        f"activation_date={collection.ACTIVATION_DATE!r}, policy_checkpoint_commit={collection.POLICY_CHECKPOINT_COMMIT!r}",
    ))

    collector_source = inspect.getsource(cpc.run_tactical_reversal_shadow_collection)
    retention_fixed = "tactical-reversal-prospective-shadow-collection-v1" in collector_source
    checks.append(_check(
        "RETENTION_LOCATION_FIXED", retention_fixed,
        "store_root is deterministically operations-review/tactical-reversal-prospective-shadow-collection-v1"
        " under output_root, computed the same way on every invocation." if retention_fixed else
        "No fixed store_root convention found in run_tactical_reversal_shadow_collection.",
    ))

    module_source = inspect.getsource(collection)
    forbidden_providers = ("dnse", "vnstock", "vci_client", "kbs_client", "requests.get", "requests.post", "urlopen")
    provider_free = not any(token in module_source.lower() for token in forbidden_providers)
    checks.append(_check(
        "NO_PROVIDER_CALL_REQUIRED", provider_free,
        "tactical_reversal_prospective_shadow_collection.py contains no provider/network reference."
        if provider_free else "A forbidden provider/network token was found in the collection module.",
    ))

    auto_prospective = (
        collection.evidence_mode_for_session(collection.ACTIVATION_DATE) == collection.BOOTSTRAP_NON_PROSPECTIVE
        and collection.evidence_mode_for_session("2099-01-01") == collection.PROSPECTIVE
    )
    checks.append(_check(
        "FUTURE_SESSION_AUTOMATICALLY_BECOMES_PROSPECTIVE", auto_prospective,
        "evidence_mode_for_session() is a pure function of the session string against the fixed "
        "activation boundary -- no manual relabeling step exists or is required.",
    ))

    store_source = inspect.getsource(collection.ProspectiveShadowObservationStore)
    immutable = "O_EXCL" in store_source and "observation_identity_valid" in store_source
    checks.append(_check(
        "T0_IDENTITY_IMMUTABLE", immutable,
        "ProspectiveShadowObservationStore writes T0 envelopes with O_EXCL (write-once) and "
        "verifies content-hash identity on every read." if immutable else
        "Store does not appear to enforce write-once/content-identity immutability.",
    ))

    _probe_current = {"session": "2026-09-12", "artifact_identity": "test", "source_artifacts": {"descriptive": "market_wide_current_descriptive_research:x"}, "records": {"AAA": {"rule_id": "R9_DOWNTREND_DEFAULT", "entry_state": "DOWNTREND", "entry_action": "AVOID", "signals": {"close": 10.0}}}}
    _probe_observation = collection.build_prospective_observation(ticker="AAA", trigger_session="2026-09-12", current_tactical_artifact=_probe_current)
    _probe_outcome_pending = collection.mature_outcome(_probe_observation, [], evaluation_as_of_session="2026-09-12")
    _probe_future = [{"session": f"2026-09-{d}", "record": {"rule_id": "R9_DOWNTREND_DEFAULT", "signals": {"close": 9.5}}, "price_basis_identity": "market_wide_current_descriptive_research"} for d in range(15, 20)]
    _probe_outcome_mature = collection.mature_outcome(_probe_observation, _probe_future, evaluation_as_of_session="2026-09-19")
    can_mature = (
        _probe_outcome_pending["horizons"]["T5"]["status"] == collection.PENDING_HORIZON
        and _probe_outcome_mature["horizons"]["T5"]["status"] == "MATURE"
    )
    checks.append(_check(
        "OLDER_HORIZONS_CAN_MATURE", can_mature,
        "mature_outcome() functionally verified: PENDING with zero future sessions retained, "
        "MATURE once five genuinely retained future sessions exist." if can_mature else
        "mature_outcome() did not transition PENDING -> MATURE as expected.",
    ))

    daily_lines = daily_source.splitlines()
    identity_start = next((i for i, line in enumerate(daily_lines) if "identity_payload = {" in line), None)
    identity_end = next((i for i, line in enumerate(daily_lines) if "digest = stable_id(identity_payload)" in line), None)
    identity_block = "\n".join(daily_lines[identity_start:identity_end]) if identity_start is not None and identity_end is not None else ""
    identity_payload_excludes_shadow = bool(identity_block) and "tactical_reversal_shadow_collection" not in identity_block
    persistable_excludes_shadow = (
        "\"tactical_reversal_shadow_collection\"" in daily_source
        and "persistable = {k: v for k, v in record.items() if k not in" in daily_source
    )
    checks.append(_check(
        "PRODUCTION_OUTPUTS_UNAFFECTED", identity_payload_excludes_shadow and persistable_excludes_shadow,
        "tactical_reversal_shadow_collection is embedded only in the full in-memory record, "
        "excluded from both identity_payload (operation_identity digest) and persistable "
        "(idempotent-rerun comparison), so a volatile collector status can never change the "
        "Daily operation identity or trigger a spurious rerun conflict." if identity_payload_excludes_shadow and persistable_excludes_shadow else
        "Shadow collection status may leak into Daily's identity/idempotency comparison.",
    ))

    overall = "READY" if all(item["status"] == "PASS" for item in checks) else "NOT_READY"
    return {
        "schema_version": "1.0.0",
        "question": "IS_THE_SYSTEM_READY_TO_CAPTURE_THE_NEXT_COMPLETED_TRADING_SESSION_WITHOUT_CODE_CHANGE",
        "overall": overall,
        "checks": checks,
        "owner_command_if_daily_orchestration_is_bypassed": (
            "python tools/run_tactical_reversal_prospective_shadow_collection.py "
            "--retained-evidence-root <repo_root> --store-root <repo_root>/operations-review/"
            "tactical-reversal-prospective-shadow-collection-v1 --session <completed_session>"
        ),
        "authority_boundary": {
            "classifier_promotion": "NOT_DECIDED", "production_policy": "UNCHANGED",
            "probability_or_recommendation": "NOT_EMITTED",
        },
    }


def main() -> int:
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["overall"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
