"""Operator tool: materialize ``current_research_ai_handoff_packet/v1`` for one already-completed
governed Daily session, from already-retained evidence only.

Never acquires data, never reruns Daily, never recomputes Workspace/Screener/descriptive
research: reads the exact same already-governed artifacts
``canonical_current_product_projections.py`` / ``daily_research_session_operations.py`` /
``governed_previous_operation.py`` already resolve deterministically for that session.

Usage:
    python tools/build_current_research_ai_handoff_packet.py --session 2026-09-15
    python tools/build_current_research_ai_handoff_packet.py --session 2026-09-15 \
        --tickers HPG,SSI,PAN,FPT,VCB,PNJ,PVD,QNS,VNM,EVF,POW,NVL
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import canonical_current_product_projections as ccpp  # noqa: E402
import current_research_ai_handoff_packet as packet_module  # noqa: E402
import daily_research_session_operations as dso  # noqa: E402
import governed_previous_operation as gpo  # noqa: E402

_OPERATIONS = Path("operations-review") / "daily-research-session-operations-v1"


class BuildAiHandoffPacketError(ValueError):
    pass


def _resolve_operation_dir(root: Path, session: str, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_dir():
            raise BuildAiHandoffPacketError(f"OPERATION_DIR_NOT_FOUND:{path}")
        return path
    session_dir = root / _OPERATIONS / session
    if not session_dir.is_dir():
        raise BuildAiHandoffPacketError(f"NO_OPERATION_DIRECTORY_FOR_SESSION:{session}")
    candidates = [
        path for path in session_dir.iterdir()
        if path.is_dir() and (path / "investment_decision_workspace_projection.json").is_file()
        and (path / "screener_master_projection.json").is_file()
    ]
    if not candidates:
        raise BuildAiHandoffPacketError(f"NO_WORKSPACE_SCREENER_OPERATION_FOR_SESSION:{session}")
    if len(candidates) > 1:
        raise BuildAiHandoffPacketError(
            f"AMBIGUOUS_OPERATION_DIRECTORY_FOR_SESSION:{session}:{','.join(str(p) for p in candidates)}"
        )
    return candidates[0]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _producer_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except OSError:
        pass
    return "UNKNOWN"


def build(*, root: Path, session: str, requested_at: str, operation_dir: str | None = None) -> tuple[dict, Path]:
    root = Path(root)
    op_dir = _resolve_operation_dir(root, session, operation_dir)
    workspace = _load_json(op_dir / "investment_decision_workspace_projection.json")
    screener = _load_json(op_dir / "screener_master_projection.json")
    run_manifest = _load_json(op_dir / "run_manifest.json") if (op_dir / "run_manifest.json").is_file() else {}

    registry = _load_json(root / "config" / "daily_research_session_input_registry.json")
    values, _ = dso.resolve_inputs(root, session, registry)
    descriptive_current = values.get("descriptive")

    previous = gpo.resolve_governed_previous_operation(session, registry, root)
    descriptive_previous = None
    previous_session = previous.get("previous_session")
    if previous.get("status") == gpo.AVAILABLE and previous_session:
        try:
            previous_values, _ = dso.resolve_inputs(root, previous_session, registry)
            descriptive_previous = previous_values.get("descriptive")
        except Exception:  # noqa: BLE001 - market_context degrades to unavailable, never blocks the packet
            descriptive_previous = None

    current_research_scope = ccpp.resolve_current_research_official_universe_scope(root, session)

    packet = packet_module.build_packet(
        session=session,
        requested_at=requested_at,
        producer_commit=_producer_commit(root),
        daily_operation_identity=run_manifest.get("operation_identity"),
        workspace_artifact=workspace,
        screener_artifact=screener,
        descriptive_current=descriptive_current,
        descriptive_previous=descriptive_previous,
        previous_session=previous_session if descriptive_previous is not None else None,
        current_research_scope=current_research_scope,
    )
    return packet, op_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--requested-at", default=None)
    parser.add_argument("--operation-dir", default=None)
    parser.add_argument("--out", default=None, help="Default: <operation_dir>/investment_research_handoff_packet.json")
    parser.add_argument("--tickers", default=None, help="Comma-separated ticker list for a watchlist subset")
    parser.add_argument("--watchlist-out", default=None, help="Default: <operation_dir>/investment_research_handoff_watchlist.json")
    args = parser.parse_args()

    requested_at = args.requested_at or f"{args.session}T00:00:00Z"
    packet, op_dir = build(root=REPO_ROOT, session=args.session, requested_at=requested_at, operation_dir=args.operation_dir)
    out_path = Path(args.out) if args.out else op_dir / "investment_research_handoff_packet.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE:{out_path}:{packet['artifact_identity']}")

    if args.tickers:
        tickers = [item.strip() for item in args.tickers.split(",") if item.strip()]
        subset = packet_module.build_watchlist_subset(packet, tickers)
        watchlist_path = Path(args.watchlist_out) if args.watchlist_out else op_dir / "investment_research_handoff_watchlist.json"
        watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        watchlist_path.write_text(json.dumps(subset, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE:{watchlist_path}:{subset['artifact_identity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
