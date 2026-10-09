"""Bounded metadata reconciliation of pinned architecture inputs; no source/apply I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from tools.vault_snapshot import require


def reconcile(candidates: dict, receipt: dict, keep_sessions: list[str]) -> dict:
    require(len(set(keep_sessions)) >= 3, "current and previous two sessions required")
    coverage = candidates["vault_coverage"]
    require(receipt.get("result") == "VERIFIED", "historical backup receipt not verified")
    groups, union = {}, {}
    for name, entries in sorted(candidates["groups"].items()):
        group = name.split("_", 1)[0]
        if group not in {"G1", "G2", "G3", "G5"}:
            continue
        rows = []
        for original in sorted(entries, key=lambda r: r["relative_path"]):
            rel = original["relative_path"].replace("\\", "/")
            require(rel.startswith("operations-review/") and ".." not in rel.split("/"), "unsafe retained path")
            dates = re.findall(r"20\d{2}-?\d{2}-?\d{2}", rel)
            raw_session = str(original.get("session") or (dates[-1] if dates else ""))
            digits = raw_session.replace("-", "")
            session = f"{digits[:4]}-{digits[4:6]}-{digits[6:]}" if len(digits) == 8 else None
            blockers = ["FRESH_DUAL_HASH_AND_STRONG_VAULT_FINGERPRINT_REQUIRED", "EXACT_PATH_OWNER_APPROVAL_REQUIRED"]
            dependencies = {
                "G1": "Legacy alias write lifecycle/reference closure is unqualified; new delivery reuse does not qualify historical files.",
                "G2": "Own-session feedback readers and October-2 oracle; cold-aware reader/restore closure must be qualified.",
                "G3": "Same-session DNSE fallback if MVA absent; preserve and prove MVA and exact replay closure.",
                "G5": "Architecture no-reference finding is pinned to 3f3d4fe; current code/config/manual/external closure unproved.",
            }[group]
            blockers.append("HISTORICAL_WRITE_CLOSURE_UNQUALIFIED" if group == "G1" else "RESOLVER_DEPENDENCY_CLOSURE_REQUIRED")
            if group != "G1":
                blockers.append("SECOND_VERIFIED_COPY_OR_EXPLICIT_SINGLE_COPY_RISK_ACCEPTANCE_REQUIRED")
            protected = original.get("protected_reason") or original.get("t0_domain") or session in keep_sessions
            if protected:
                blockers.append("PROTECTED_OR_RECENT_SESSION")
            if session is None:
                blockers.append("EXACT_SESSION_IDENTITY_UNQUALIFIED")
            require(len(original["vault_sha256"]) == 64, "missing historical native hash")
            row = dict(group=group, relative_path=rel, session_identity=session,
                source_identity={"volume_guid": receipt["source"]["volume_guid"], "historical_file_id": original["c_file_id"],
                                 "native_sha256": original["vault_sha256"], "artifact_seal_identity": "NOT_FRESHLY_QUALIFIED"},
                vault_identity={"volume_guid": receipt["destination"]["volume_guid"],
                                "object_path": receipt["destination"]["root"] + "\\" + rel.split("/", 1)[1].replace("/", "\\"),
                                "native_sha256": original["vault_sha256"], "receipt_sha256": coverage["receipt_sha256"],
                                "ledger_sha256": coverage["ledger_sha256"], "qualification": "HISTORICAL_RECEIPT_ONLY"},
                logical_bytes=original["size"], physical_bytes_estimate=original["allocation_estimate"],
                dependencies_requiring_c=dependencies, restore_path=receipt["source"]["root"] + "\\" + rel.split("/", 1)[1].replace("/", "\\"),
                restore_prerequisites=["Exact original bytes and native SHA", "Original artifact/session/seal verifier", "Verified W identity", "Explicit verified catalog event", "No T0 fingerprint compatibility granted"],
                eligibility="BLOCKED", blockers=blockers,
                conditional_reclaim_bytes=0 if protected else original["allocation_estimate"], verified_reclaimable_bytes=0)
            rows.append(row)
            key = (receipt["source"]["volume_guid"], original["c_file_id"])
            if row["conditional_reclaim_bytes"]:
                union[key] = row["conditional_reclaim_bytes"]
        groups[group] = {"rows": rows, "exact_path_count": len(rows),
                         "conditional_estimate_bytes": sum(r["conditional_reclaim_bytes"] for r in rows),
                         "verified_reclaimable_bytes": 0}
    return dict(schema="capacity_retained_metadata_eligibility/v1", keep_sessions=keep_sessions, groups=groups,
                conditional_union_physical_bytes_estimate=sum(union.values()), verified_reclaimable_bytes=0,
                actual_reclaimed_bytes=0, production_apply_implemented=False, authority_effect="NONE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--candidates-sha", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--keep-session", action="append", required=True)
    args = parser.parse_args()
    raw = args.candidates.read_bytes()
    require(len(raw) <= 2*1024*1024 and hashlib.sha256(raw).hexdigest() == args.candidates_sha, "candidate input pin/ceiling failed")
    candidates = json.loads(raw)
    receipt_raw = args.receipt.read_bytes()
    require(len(receipt_raw) <= 2*1024*1024 and hashlib.sha256(receipt_raw).hexdigest() == candidates["vault_coverage"]["receipt_sha256"], "backup receipt pin/ceiling failed")
    result = reconcile(candidates, json.loads(receipt_raw), args.keep_session)
    result["inputs"] = {"candidates_sha256": args.candidates_sha, "receipt_sha256": candidates["vault_coverage"]["receipt_sha256"]}
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
