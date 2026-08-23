"""Materialize the current flow/positioning projection from an explicit retained packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import canonical_market_evidence_integration as canonical
from current_market_flow_positioning import build, content_identity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    artifact = build(canonical_integration=canonical.integrate_session_packet(packet))
    if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]:
        raise ValueError("FLOW_ARTIFACT_SELF_VERIFICATION_FAILED")
    payload = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output.exists() and args.output.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_FLOW_ARTIFACT_CONTENT_CONFLICT")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "session": artifact["session"], "coverage": artifact["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
