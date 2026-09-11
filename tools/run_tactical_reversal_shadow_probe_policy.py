"""Build the shadow-only tactical reversal probe policy overlay for one real session.

Reads two already-retained, real daily `watchlist_tactical_entry_classifier` artifacts
(the target session and its immediately adjacent prior session) and annotates every
ticker with the two supported shadow candidates from
TACTICAL_REVERSAL_PROBE_POLICY_COUNTERFACTUAL_EVALUATION_V1. Never invokes the
classifier, never writes to any runtime database, and never mutates the inputs.

Runtime discovery is a recoverable precondition, not a separate step: this tool verifies
`vn_stock.db` is present and openable read-only under the given/default runtime root and
injects `STOCK_LOOKUP_RUNTIME_ROOT` into this process only if it is not already set, but
the shadow computation itself consumes already-retained tactical artifacts and does not
query the database further.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tactical_reversal_shadow_probe_policy as shadow  # noqa: E402


DEFAULT_RUNTIME_ROOT = Path("C:/Projects/StockLookup/dashboard-runtime")


def verify_runtime_precondition(runtime_root: Path) -> dict[str, Any]:
    """Confirm vn_stock.db is present and openable read-only; never write to it.

    Sets STOCK_LOOKUP_RUNTIME_ROOT for this process only (never persisted) when it is
    not already set, since some sibling tooling in this repository reads that variable.
    A missing or unopenable database is reported as an explicit blocker, not raised,
    since the shadow computation itself does not require it.
    """
    database = runtime_root / "vn_stock.db"
    result: dict[str, Any] = {"runtime_root": str(runtime_root), "database_path": str(database)}
    if not database.is_file():
        result.update(status="BLOCKED", reason="RUNTIME_CAPABILITY_VN_STOCK_DB_MISSING")
        return result
    try:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as error:
        result.update(status="BLOCKED", reason=f"RUNTIME_CAPABILITY_VN_STOCK_DB_UNREADABLE:{error}")
        return result
    if not os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT"):
        os.environ["STOCK_LOOKUP_RUNTIME_ROOT"] = str(runtime_root)
        result["stock_lookup_runtime_root_injected"] = True
    else:
        result["stock_lookup_runtime_root_injected"] = False
    result["status"] = "VERIFIED"
    return result


def _load_tactical_artifact(retained_evidence_root: Path, *, session: str) -> Mapping[str, Any] | None:
    path = retained_evidence_root / "operations-review" / f"watchlist-tactical-entry-decision-v1-{session.replace('-', '')}" / "watchlist_tactical_entry_classifier_artifact.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT, help="Runtime root containing vn_stock.db (precondition check only).")
    parser.add_argument("--retained-evidence-root", type=Path, required=True, help="Root holding retained operations-review daily tactical artifacts.")
    parser.add_argument("--session", required=True, help="Target session (must have a retained tactical artifact).")
    parser.add_argument("--prior-session", help="Immediately adjacent prior trading session (optional; omit if unavailable).")
    parser.add_argument("--out", type=Path, required=True, help="Tracked artifact path in this checkout.")
    args = parser.parse_args(argv)

    precondition = verify_runtime_precondition(args.runtime_root)

    current_artifact = _load_tactical_artifact(args.retained_evidence_root, session=args.session)
    if current_artifact is None:
        print(json.dumps({
            "blocker": "RETAINED_TACTICAL_ARTIFACT_NOT_FOUND_FOR_SESSION",
            "session": args.session,
            "runtime_precondition": precondition,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    prior_artifact = None
    if args.prior_session:
        prior_artifact = _load_tactical_artifact(args.retained_evidence_root, session=args.prior_session)

    artifact = shadow.build_shadow_artifact(
        session=args.session, current_tactical_artifact=current_artifact,
        prior_session=args.prior_session, prior_tactical_artifact=prior_artifact,
    )
    write_artifact(args.out, artifact)

    pan_record = artifact["records"].get("PAN")
    print(json.dumps({
        "artifact_identity": artifact["artifact_identity"],
        "runtime_precondition": precondition,
        "session": args.session,
        "prior_session": args.prior_session,
        "prior_session_evidence_supplied": artifact["prior_session_evidence_supplied"],
        "disposition_counts": artifact["disposition_counts"],
        "pan_record": pan_record,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
