"""Emit P3-F2's deterministic generic authority and coverage artifact."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import current_valuation_input_authority as authority

P3E = repo_root / "operations-review/p3e-fundamental-coverage-closeout-20260820/p3e_fundamental_coverage_closeout_artifact.json"
OUTPUT = repo_root / "operations-review/p3f2-current-valuation-input-authority-20260820"


def _instruments(p3e: dict) -> list[dict]:
    return [authority.canonical_instrument(row["issuer_identity"]["ticker"])
            for row in p3e["refreshed_panel_data"]["issuers"]]


def _reference_at(root: Path, instruments: list[dict]) -> str:
    """Freeze the scan at the latest retained daily session, not wall-clock now."""
    sessions = []
    for instrument in instruments:
        evidence = authority.dnse_current_market_observations(root, instrument)
        sessions.extend(str(row["session"]) for row in evidence.get("observations", []) if row.get("session"))
    if not sessions:
        raise ValueError("P3F2_NO_RETAINED_DNSE_SESSION")
    return f"{max(sessions)}T16:00:00+07:00"


def _hpg_positive_proof(root: Path, instruments: list[dict]) -> dict:
    instrument = next(row for row in instruments if row["canonical_ticker"] == "HPG")
    evidence = authority.dnse_current_market_observations(root, instrument)
    for observation in reversed(evidence.get("observations") or []):
        session = observation["session"]
        requested_at = f"{session}T16:00:00+07:00"
        shares = authority.runtime_share_candidates(root, instrument, session)
        resolved = authority.resolve_current_valuation_inputs(
            instrument, requested_at=requested_at, financial_input_state={}, market_evidence=evidence,
            share_evidence=shares,
        )
        if resolved["market_cap_readiness"] == "MARKET_CAP_READY":
            return resolved
    return authority.resolve_current_valuation_inputs(
        instrument, requested_at=_reference_at(root, [instrument]), financial_input_state={}, market_evidence=evidence,
        share_evidence=authority.runtime_share_candidates(root, instrument, _reference_at(root, [instrument])[:10]),
    )


def build_p3f2_artifact(*, runtime_root: Path) -> dict:
    p3e = json.loads(P3E.read_text(encoding="utf-8"))
    instruments = _instruments(p3e)
    reference_at = _reference_at(runtime_root, instruments)
    coverage = authority.scan_current_valuation_input_coverage(instruments, runtime_root=runtime_root, requested_at=reference_at)
    hpg_proof = _hpg_positive_proof(runtime_root, instruments)
    hpg_share_rows = authority.runtime_share_candidates(runtime_root, authority.canonical_instrument("HPG"), hpg_proof["valuation_session"])
    invalidation = authority.qualify_current_share_basis(
        authority.canonical_instrument("HPG"), hpg_share_rows, valuation_date=hpg_proof["valuation_session"],
        corporate_actions=[{"potential_share_change": True, "effective_date": None, "lifecycle": "announced"}],
    )
    payload = {
        "artifact_type": "P3F2_CURRENT_VALUATION_INPUT_AUTHORITY", "contract_version": authority.CONTRACT_VERSION,
        "source_artifacts": {"p3e": p3e.get("artifact_identity")}, "reference_at": reference_at,
        "session_policy": "latest_completed_vietnam_weekday_with_exact_retained_observation",
        "representative_proofs": {"hpg_current_price_and_share": hpg_proof,
            "vcb_runtime_price_evidence": next(row for row in coverage["rows"] if row["canonical_instrument"]["canonical_ticker"] == "VCB")["price"],
            "corporate_action_timing_unresolved_contract_proof": invalidation},
        "coverage_scan": coverage,
        "instance_vs_contract_authority": {"generic_contract": "COMPLETE", "qualified_instances": "EVIDENCE_INSTANCE_SCOPED", "no_generic_dnse_ticker_promotion": True, "no_current_share_continuity_inference": True},
        "boundaries": {"raw_as_traded": "NOT_PROMOTED", "historical_pit": "NOT_AUTHORIZED", "p3a": "UNCHANGED_BLOCKED_PENDING_QUALIFIED_EX_DATE", "recommendations": "NOT_IMPLEMENTED"},
        "operational_work_queue": {"price": "Materialize structurally valid retained DNSE current-session observations with canonical instrument mapping.", "shares": "Materialize official common-outstanding records with explicit coverage-through dates; resolve evidence registration/hash failures before use."},
        "is_actionable": False,
    }
    payload["artifact_sha256"] = authority.stable_id(payload)
    payload["artifact_identity"] = f"p3f2_current_valuation_input_authority:{payload['artifact_sha256']}"
    return payload


def run_p3f2_current_valuation_input_authority(output_dir: Path = OUTPUT, runtime_root: Path | None = None) -> dict:
    root = runtime_root or (Path(os.environ["STOCK_LOOKUP_RUNTIME_ROOT"]) if os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT") else None)
    if root is None:
        raise ValueError("STOCK_LOOKUP_RUNTIME_ROOT_REQUIRED")
    artifact = build_p3f2_artifact(runtime_root=root)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "p3f2_current_valuation_input_authority_artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    print(run_p3f2_current_valuation_input_authority()["artifact_identity"])
