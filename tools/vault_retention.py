"""Deterministic offline retention/capacity preflight. No deletion or reacquisition API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.vault_snapshot import canonical, digest, require

GIB = 1024 ** 3
CATEGORIES = ("ACTIVE_REQUIRED", "VERIFIED_RECOVERABLE_COLD_CANDIDATE", "HISTORICAL_DISTINCT",
              "EXACT_DUPLICATE_BUT_REFERENCED", "UNVERIFIED_OR_UNKNOWN", "REGENERABLE_WITH_PROOF")
PROOFS = ("source_volume", "physical_allocation_bytes", "evidence_identity", "verified_coverage",
          "runtime_refs", "code_refs", "manifest_refs", "cross_session_dependencies",
          "hardlink_consequences", "restore_destination", "restore_procedure", "invalidates_without_vault")


def classify(candidate: dict, proof: dict, *, vault_available: bool) -> dict:
    """Proof records are external audited evidence, never inferred from backup=true."""
    missing = [key for key in PROOFS if key not in proof or proof[key] is None or proof[key] == "UNKNOWN"]
    referenced = any(isinstance(proof.get(key), list) and proof[key] for key in
                     ("runtime_refs", "code_refs", "manifest_refs", "cross_session_dependencies"))
    coverage = proof.get("verified_coverage")
    complete_coverage = (isinstance(coverage, dict) and coverage.get("status") == "VERIFIED"
                         and coverage.get("complete") is True and coverage.get("manifest_sha256")
                         and coverage.get("restore_receipt_sha256")
                         and coverage.get("destination_volume")
                         and coverage.get("absolute_paths") == candidate["absolute_paths"])
    if not isinstance(proof.get("physical_allocation_bytes"), int) or isinstance(proof.get("physical_allocation_bytes"), bool) or proof.get("physical_allocation_bytes", -1) < 0:
        missing.append("nonnegative measured allocation")
    for key in ("runtime_refs", "code_refs", "manifest_refs", "cross_session_dependencies"):
        if not isinstance(proof.get(key), list):
            missing.append(key + " closure")
    if isinstance(proof.get("runtime_refs"), list) and proof["runtime_refs"]:
        category = "ACTIVE_REQUIRED"
    elif referenced and candidate.get("classification") == "EXACT_DUPLICATE":
        category = "EXACT_DUPLICATE_BUT_REFERENCED"
    elif proof.get("historically_distinct") is True:
        category = "HISTORICAL_DISTINCT"
    elif missing or not vault_available or not complete_coverage:
        category = "UNVERIFIED_OR_UNKNOWN"
    elif proof.get("regeneration_proof") and not referenced:
        category = "REGENERABLE_WITH_PROOF"
    elif not referenced and proof.get("invalidates_without_vault") is True:
        category = "VERIFIED_RECOVERABLE_COLD_CANDIDATE"
    else:
        category = "UNVERIFIED_OR_UNKNOWN"
    return dict(candidate_rank=candidate["rank"], candidate_identity=digest(canonical(candidate)),
                absolute_paths=candidate["absolute_paths"],
                category=category, proof=proof, missing_proofs=missing,
                cold_preflight_pass=category == "VERIFIED_RECOVERABLE_COLD_CANDIDATE",
                deletion_authorized=False, execute=False,
                vault_absent_disposition="ARCHIVE_UNAVAILABLE_RESTORE_BLOCKED_NO_ACQUISITION",
                proposal_identity=digest(canonical(candidate)))


def retention_report(proposal: dict, proofs: dict, *, vault_available: bool) -> dict:
    require(proposal.get("mode") == "PROPOSAL_ONLY_NO_DELETION", "not a retention proposal")
    candidates = proposal["candidates"]
    require(len({digest(canonical(c)) for c in candidates}) == len(candidates), "duplicate proposal identities")
    rows = [classify(c, proofs.get(digest(canonical(c)), {}), vault_available=vault_available)
            for c in sorted(candidates, key=lambda c: (c["rank"], digest(canonical(c))))]
    return dict(schema="vault_retention_preflight/v1", proposal_sha256=digest(canonical(proposal)),
                authority_effect="NONE", deletion_implementation=False, candidates=rows,
                counts={cat: sum(r["category"] == cat for r in rows) for cat in CATEGORIES})


def archive_resolution(*, local_present: bool, archive_registered: bool, vault_available: bool) -> str:
    if local_present:
        return "LOCAL_PRESENT"
    if archive_registered:
        return "EXPLICIT_RESTORE_REQUIRED" if vault_available else "ARCHIVE_UNAVAILABLE"
    return "MISSING_UNCLASSIFIED_NO_AUTOMATIC_REACQUISITION"


def unique_allocation(records: list[dict]) -> dict:
    """Count a file allocation once per volume/file ID, not once per hardlink path."""
    seen, total = set(), 0
    for r in records:
        key = (r["volume"], r["device"], r["inode"])
        if key not in seen:
            seen.add(key)
            total += r["physical_bytes"]
    return dict(logical_bytes=sum(r["size"] for r in records), unique_physical_bytes=total,
                file_ids=len(seen), path_count=len(records), reclaimable_bytes="UNKNOWN_WITHOUT_LINK_CLOSURE")


def capacity_model(free_c: int, free_w: int, observed: dict, reclaim: dict) -> dict:
    require(free_c >= 0 and free_w >= 0, "invalid free capacity")
    daily = [r["bytes"] for date, r in observed["recent"].items() if date != "2026-10-02"]
    mean = sum(daily) / len(daily)
    budget = max(0, free_c - 25 * GIB)
    growth = {"observed_logical_mean": mean, "planning_8_GiB": 8 * GIB, "stressed_12_GiB": 12 * GIB}
    projections = []
    for days, sessions in ((30, 22), (90, 64), (180, 128)):
        for label, per_session in growth.items():
            remaining = free_c - sessions * per_session
            projections.append(dict(days=days, assumed_successful_sessions=sessions, scenario=label,
                                    c_free_bytes_signed=remaining, c_guard_shortfall_bytes=max(0, 25 * GIB - remaining),
                                    w_free_bytes_signed=free_w - sessions * (per_session + 275177472)))
    return dict(schema="vault_capacity_preflight/v1", free_c_bytes=free_c, free_w_bytes=free_w,
                ready_guard_bytes=25 * GIB, admission_guard_unchanged=True,
                measured_physical_growth="UNKNOWN", measured_logical_growth=observed,
                per_session_assumptions_bytes=growth,
                whole_sessions_until_guard={k: int(budget // v) for k, v in growth.items()},
                reclaim=reclaim, projections=projections, backup_alone_solves_capacity=False,
                assumptions="Weekdays 22/64/128; no holidays/retries/unrelated host growth; logical growth is not physical. "
                            "W receives all assumed new retained bytes plus one 275177472-byte DB backup per Daily.",
                remaining_gates=["approved explicit archive resolver with original identity/cutoff preservation",
                                 "measured physical growth and hardlink/reference closure",
                                 "owner exact-path source-retention authorization after complete recovery proof"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--vault-available", action="store_true", help="Audited observation only; does not authorize deletion")
    args = parser.parse_args()
    print(canonical(retention_report(json.loads(args.proposal.read_bytes()),
                                     json.loads(args.proofs.read_bytes()),
                                     vault_available=args.vault_available)).decode())


if __name__ == "__main__":
    main()
