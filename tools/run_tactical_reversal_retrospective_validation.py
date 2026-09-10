"""Run the tactical-reversal retained-data diagnostic without provider or Daily calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import daily_research_session_operations as session_operations  # noqa: E402
import tactical_reversal_retrospective_validation as validation  # noqa: E402


def build_diagnostic(*, runtime_root: Path) -> dict[str, Any]:
    registry = session_operations.load_registry(runtime_root)
    registered_sessions = sorted((registry.get("sessions") or {}).keys())
    inputs_by_session: dict[str, Mapping[str, Mapping[str, Any]]] = {}
    selections_by_session: dict[str, Mapping[str, Mapping[str, Any]]] = {}
    for session in registered_sessions:
        inputs, selection = session_operations.resolve_inputs(runtime_root, session, registry)
        inputs_by_session[session] = inputs
        selections_by_session[session] = selection
    return validation.build_diagnostic(
        registry=registry,
        inputs_by_session=inputs_by_session,
        selections_by_session=selections_by_session,
    )


def write_diagnostic(path: Path, artifact: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True, help="Read-only governed retained-evidence root.")
    parser.add_argument("--out", type=Path, default=None, help="Diagnostic JSON path in this checkout.")
    args = parser.parse_args(argv)
    artifact = build_diagnostic(runtime_root=args.runtime_root)
    if args.out:
        write_diagnostic(args.out, artifact)
    print(json.dumps({
        "artifact_identity": artifact["artifact_identity"],
        "replay_sessions": len(artifact["replay_sessions"]),
        "missed_opportunity": {ticker: case["missed_opportunity"]["classification"] for ticker, case in artifact["cases"].items()},
        "pan_now": artifact["pan_now"].get("entry_state"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
