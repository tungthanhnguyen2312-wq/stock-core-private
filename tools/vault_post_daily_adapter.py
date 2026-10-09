"""Offline opt-in qualified completed-boundary adapter for Vault V1; no Daily hook."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path

from tools import vault_snapshot as v

MUTABLE = ("/_stream/", "_artifact_summary_cache", "_settled_cache", "prospective-pit-capture-v1/",
           "prospective-calendar-evidence-v1/", "official-corporate-event-raw-store/",
           "tactical-reversal-prospective-shadow-collection-v1/", "LATEST_", "journal.json")


@contextmanager
def qualified_boundary(source: Path, boundary: Path, boundary_sha: str, *, max_bytes):
    """Use explicit native proof references, holding provenance stable throughout Vault copy."""
    with ExitStack() as stack:
        stack.enter_context(v.locked_file(boundary))
        b, files, excluded = v.boundary_plan(source, boundary, boundary_sha, max_bytes)
        v.require(not excluded, "adapter boundary contains incomplete/mutable files")
        proof = b.get("completion_proof") or {}
        documents = {}
        pinned = []
        for key in ("registry", "completion_record", "handoff", "producer_manifest", "operation_manifest"):
            ref = proof.get(key) or {}
            path = v.safe_path(source, ref.get("relative_path", ""))
            stack.enter_context(v.locked_file(path))
            v.require(path.stat().st_size <= 8*v.CHUNK, "completion proof size ceiling")
            v.require(v.sha(path) == ref.get("sha256"), "completion proof tampered")
            documents[key] = json.loads(path.read_bytes())
            pinned.append((path, ref["sha256"]))
        session = b["session_identity"]
        registry, record, handoff, producer, operation = (documents[k] for k in
            ("registry", "completion_record", "handoff", "producer_manifest", "operation_manifest"))
        row = (registry.get("completed_sessions") or {}).get(session) or {}
        v.require(row.get("status") == "COMPLETED_RETAINED_EVIDENCE" and row.get("trading_day_valid") is True,
                  "session completion not proved")
        required = {"daily_operation_state": "LOCAL_COMPLETE", "daily_producer_status": "COMPLETED",
                    "runtime_release_status": "READY", "trusted_subset_status": "READY"}
        v.require(record.get("session") == session and all(record.get(k) == val for k, val in required.items())
                  and (record.get("acquisition") or {}).get("resolved_completed_session") == session,
                  "Daily completion boundary failed")
        from daily_research_session_operations import _identity
        from daily_producer_pipeline import _run_identity
        operation_id = operation.get("operation_identity")
        v.require(operation.get("market_session") == session and _identity(operation) == operation_id
                  and record.get("daily_producer_operation_identity") == operation_id
                  and (producer.get("daily_session_operation") or {}).get("identity") == operation_id,
                  "sealed operation binding failed")
        run_id = _run_identity(session, producer["producer_head"], producer["consumer_head"],
                               producer["source_plan"], operation_id)
        v.require(producer.get("target_market_session") == session and producer.get("run_identity") == run_id
                  and record.get("daily_producer_run_identity") == run_id
                  and handoff.get("daily_producer") == dict(status="COMPLETED", run_identity=run_id,
                                                            operation_identity=operation_id)
                  and (handoff.get("market_session_proof") or {}).get("resolved_completed_session") == session
                  and b["source_identity"] == operation_id, "Producer/handoff identity mismatch")
        refs = {r["relative_path"]: r["sha256"] for r in b["receipt_refs"] + b["seal_refs"]}
        for key in ("completion_record", "handoff", "producer_manifest", "operation_manifest"):
            ref = proof[key]
            v.require(refs.get(ref["relative_path"]) == ref["sha256"], "completion/seal outside boundary closure")
        for row in files:
            rel = row["relative_path"]
            v.require(not rel.startswith(("config/", "data/", "dashboard-runtime/"))
                      and not any(token in rel for token in MUTABLE), "mutable source refused")
        t0 = handoff.get("prospective_decision_snapshot") or {}
        if any(row["family"] == "T0" for row in files):
            from prospective_t0_seal_index import load_verified
            ref = dict(t0.get("seal_index") or {})
            index_path = v.safe_path(source, ref.get("path", ""))
            snapshot_path = v.safe_path(source, t0.get("path", ""))
            receipt_path = index_path.parent / "prospective_t0_snapshot_write_receipt.json"
            native = {row["relative_path"]: row for row in files}
            for path in (snapshot_path, index_path, receipt_path):
                relative = path.relative_to(source).as_posix()
                v.require(relative in native, "original T0 proof outside closure")
                stack.enter_context(v.locked_file(path))
            ref["path"] = str(index_path)
            v.require(load_verified(ref, expected_snapshot_identity=t0.get("identity"), session=session) is not None,
                      "original T0 binding unverified")
            index = json.loads(index_path.read_bytes())
            v.require(snapshot_path == index_path.parent / index["snapshot_file"]
                      and native[t0["path"]]["sha256"] == index["snapshot_file_sha256"],
                      "T0 native hash/path differs from original seal")
        yield b
        for path, expected_sha in pinned:
            v.require(v.sha(path) == expected_sha, "completion provenance changed")


def snapshot_completed(source, vault, boundary, boundary_sha, expected, *, opt_in=False,
                       observer=v.native_volume, max_bytes=64*v.CHUNK, previous=None, previous_sha=None,
                       on_chunk=None):
    v.require(opt_in, "explicit opt-in required")
    # Only unavailable volume is optional; corrupt completion proof fails qualification.
    try:
        v.verify_volumes(source, vault, expected, observer)
    except v.Refused as exc:
        return dict(status="OPTIONAL_BACKUP_UNAVAILABLE", reason=str(exc), daily_completion_changed=False)
    with qualified_boundary(source, boundary, boundary_sha, max_bytes=max_bytes):
        receipt = v.snapshot(source, vault, boundary, boundary_sha, expected, observer=observer,
                             max_bytes=max_bytes, previous=previous, previous_sha=previous_sha, on_chunk=on_chunk)
    return dict(status="COMPLETE", receipt=receipt, daily_completion_changed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opt-in", action="store_true")
    for name in ("source", "vault", "boundary", "volumes", "previous"):
        parser.add_argument("--" + name, type=Path, required=name != "previous")
    parser.add_argument("--boundary-sha", required=True)
    parser.add_argument("--previous-sha")
    parser.add_argument("--max-bytes", type=int, default=64*v.CHUNK)
    args = parser.parse_args()
    v.require(args.vault.absolute().drive.upper() == "W:", "explicit W destination required")
    print(json.dumps(snapshot_completed(args.source, args.vault, args.boundary, args.boundary_sha,
        json.loads(args.volumes.read_bytes()), opt_in=args.opt_in, max_bytes=args.max_bytes,
        previous=args.previous, previous_sha=args.previous_sha), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
