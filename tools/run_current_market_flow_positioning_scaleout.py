"""Build the session-attested retained flow scaleout artifact from explicit inputs."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from current_evidence_bound_scenario import PREOPEN_47, WATCHLIST
from current_market_flow_positioning import content_identity
from current_market_flow_positioning_scaleout import build_scaleout

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--packets", nargs="+", required=True, type=Path); parser.add_argument("--descriptive", required=True, type=Path); parser.add_argument("--tactical", required=True, type=Path); parser.add_argument("--triage", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); parser.add_argument("--session", default="2026-08-21")
    args = parser.parse_args(); descriptive=json.loads(args.descriptive.read_text(encoding="utf-8")); tactical=json.loads(args.tactical.read_text(encoding="utf-8")); triage=json.loads(args.triage.read_text(encoding="utf-8")); source=triage.get("all_entry_relevant_records", {}); rows=[row for values in source.values() for row in values] if isinstance(source, dict) else source; entry=[row["ticker"] for row in rows if isinstance(row, dict) and row.get("ticker")]
    artifact=build_scaleout(packet_paths=args.packets, session=args.session, candidate_tickers=descriptive["records"].keys(), tactical=tactical, watchlist=WATCHLIST, preopen_47=PREOPEN_47, entry_relevant_90=entry)
    if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]: raise ValueError("FLOW_SCALEOUT_ARTIFACT_SELF_VERIFICATION_FAILED")
    payload=json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2)+"\n"
    if args.output.exists() and args.output.read_text(encoding="utf-8") != payload: raise ValueError("IMMUTABLE_FLOW_SCALEOUT_ARTIFACT_CONTENT_CONFLICT")
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(payload, encoding="utf-8"); print(json.dumps({"artifact_identity":artifact["artifact_identity"],"coverage":artifact["coverage"],"terminal_status":artifact["scaleout"]["terminal_status"]},sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
