"""No-provider contracts for governed previous Daily-operation selection."""
from __future__ import annotations

import json
from pathlib import Path

import canonical_daily_operation as cdo
import daily_execution_environment as environment
import governed_previous_operation as selector
import stocklookup


PRIOR = "2026-09-11"
CURRENT = "2026-09-14"
FROZEN = {"descriptive": "descriptive:locked"}


def _registry(root: Path, *, sessions: tuple[str, ...] = (PRIOR,)) -> dict:
    completed = {
        session: {"status": "COMPLETED_RETAINED_EVIDENCE", "frozen_input_identities": FROZEN}
        for session in sessions
    }
    value = {"contract_version": "daily_research_session_input_registry/v1", "completed_sessions": completed}
    path = root / "config" / "daily_research_session_input_registry.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def _operation(root: Path, name: str, *, frozen: dict | None = None, session: str = PRIOR,
               bundle_session: str | None = None, bundle_operation: str | None = None,
               bundle_product: str | None = None) -> tuple[Path, str]:
    directory = root / "operations-review" / "daily-research-session-operations-v1" / session / name
    directory.mkdir(parents=True)
    operation_identity = "daily_research_session_operation:" + name
    product_identity = "current_daily_decision_research_product:" + name
    manifest = {
        "market_session": session,
        "operation_identity": operation_identity,
        "input_artifacts": {key: {"artifact_identity": value} for key, value in (FROZEN if frozen is None else frozen).items()},
        "outputs": {"daily_product": product_identity},
    }
    bundle = {
        "session": bundle_session if bundle_session is not None else session,
        "operation_identity": bundle_operation if bundle_operation is not None else operation_identity,
        "product_identity": bundle_product if bundle_product is not None else product_identity,
    }
    (directory / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "ai_research_session_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    return directory, operation_identity


def _latest_pointer(root: Path, operation_directory: Path, operation_identity: str) -> None:
    runs = root / "operations-review" / "daily-producer-runs-v1"
    run = runs / PRIOR / "producer-run"
    run.mkdir(parents=True)
    run_identity = "daily_producer_run:producer-run"
    operation_manifest = json.loads((operation_directory / "run_manifest.json").read_text(encoding="utf-8"))
    (run / "run_manifest.json").write_text(json.dumps({
        "run_identity": run_identity,
        "target_market_session": PRIOR,
        "daily_product_identity": operation_manifest["outputs"]["daily_product"],
        "daily_session_operation": {
            "identity": operation_identity,
            "directory": str(operation_directory.relative_to(root)).replace("\\", "/"),
        },
    }), encoding="utf-8")
    (runs / "LATEST_COMPLETED_RUN.json").write_text(json.dumps({
        "schema_version": "daily_producer_latest_completed_navigation/v1",
        "navigation_only": True,
        "session": PRIOR,
        "run_identity": run_identity,
        "daily_session_operation_identity": operation_identity,
        "relative_directory": f"{PRIOR}/producer-run",
    }), encoding="utf-8")


def test_no_prior_governed_session_is_explicit_and_preflight_n_a(tmp_path):
    registry = _registry(tmp_path, sessions=())
    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, tmp_path)
    assert resolved["status"] == selector.NO_PRIOR_GOVERNED_SESSION
    row = next(item for item in environment.required_retained_inputs(tmp_path, CURRENT)
               if item["contract"] == "governed_previous_session_bundle")
    assert row["status"] == "AVAILABLE"
    assert row["reason_code"] == "NOT_APPLICABLE_NO_PRIOR_COMPLETED_SESSION"


def test_sole_qualified_operation_is_selected_and_unqualified_newer_session_ignored(tmp_path):
    registry = _registry(tmp_path, sessions=("2026-09-10",))
    valid, identity = _operation(tmp_path, "valid", session="2026-09-10")
    _operation(tmp_path, "unqualified-current", session=PRIOR)
    # The current session is after both retained directories, but the ledger admits only 09-10.
    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, tmp_path)
    assert resolved["status"] == selector.AVAILABLE
    assert resolved["operation_identity"] == identity
    assert Path(resolved["operation_directory"]) == valid


def test_invalid_same_session_candidates_are_rejected_without_directory_order_selection(tmp_path):
    registry = _registry(tmp_path)
    selected, selected_identity = _operation(tmp_path, "authority", frozen=FROZEN)
    _operation(tmp_path, "wrong-inputs", frozen={"descriptive": "other"})
    _operation(tmp_path, "wrong-session", bundle_session="2026-09-10")
    _operation(tmp_path, "wrong-operation", bundle_operation="operation:other")
    _operation(tmp_path, "wrong-product", bundle_product="product:other")
    malformed = tmp_path / "operations-review" / "daily-research-session-operations-v1" / PRIOR / "malformed"
    malformed.mkdir()
    (malformed / "run_manifest.json").write_text("not json", encoding="utf-8")
    _latest_pointer(tmp_path, selected, selected_identity)
    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, tmp_path)
    assert resolved["status"] == selector.AVAILABLE
    assert resolved["operation_identity"] == selected_identity
    assert resolved["candidate_count"] == 6
    assert resolved["qualified_candidate_count"] == 1


def test_multiple_lineage_qualified_operations_use_the_retained_producer_run_binding(tmp_path):
    registry = _registry(tmp_path)
    chosen, chosen_identity = _operation(tmp_path, "governed")
    _operation(tmp_path, "historical-retry")
    _latest_pointer(tmp_path, chosen, chosen_identity)
    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, tmp_path)
    assert resolved["status"] == selector.AVAILABLE
    assert resolved["qualified_candidate_count"] == 2
    assert resolved["operation_identity"] == chosen_identity
    assert resolved["selection_basis"] == "LATEST_COMPLETED_RUN_IMMUTABLE_PRODUCER_RUN_LINEAGE"


def test_equally_lineage_qualified_operations_without_pointer_remain_ambiguous(tmp_path):
    registry = _registry(tmp_path)
    _operation(tmp_path, "a")
    _operation(tmp_path, "b")
    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, tmp_path)
    assert resolved["status"] == selector.AMBIGUOUS_GOVERNED_PREVIOUS_OPERATION
    assert resolved["qualified_candidate_count"] == 2


def test_pointer_must_bind_to_a_lineage_qualified_operation(tmp_path):
    registry = _registry(tmp_path)
    valid, _ = _operation(tmp_path, "valid")
    _latest_pointer(tmp_path, valid, "daily_research_session_operation:not-a-candidate")
    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, tmp_path)
    assert resolved["status"] == selector.GOVERNED_PREVIOUS_OPERATION_LINEAGE_MISMATCH


def test_all_three_consumers_resolve_the_exact_same_bundle(tmp_path):
    registry = _registry(tmp_path)
    chosen, identity = _operation(tmp_path, "chosen")
    _operation(tmp_path, "historical", frozen={"descriptive": "superseded"})
    _latest_pointer(tmp_path, chosen, identity)

    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, tmp_path)
    preflight = next(item for item in environment.required_retained_inputs(tmp_path, CURRENT)
                     if item["contract"] == "governed_previous_session_bundle")
    preseal = cdo._previous_qualified_operation_source(tmp_path, session=CURRENT, registry=registry)
    public_bundle = stocklookup._previous(CURRENT, tmp_path)

    assert resolved["status"] == selector.AVAILABLE
    assert preflight["status"] == "AVAILABLE"
    assert preflight["operation_identity"] == identity
    assert preseal == (PRIOR, chosen)
    assert public_bundle == chosen / "ai_research_session_bundle.json"
    assert public_bundle == Path(resolved["bundle_path"])
