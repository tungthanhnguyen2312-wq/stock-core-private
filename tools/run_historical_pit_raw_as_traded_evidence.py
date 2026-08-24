"""Build the historical PIT/corporate-action evidence artifact from retained official bytes.

This runner performs no network I/O.  The separate governed acquisition step is deliberately
single-request/no-retry; this runner verifies the retained hash and makes the authority result
replayable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atomic_io import atomic_write_json
from corporate_action_events import classify_retained_document, extract_event_observations, extract_text
from historical_pit_raw_as_traded_evidence import build_artifact, event_from_observation


def run(raw_root: Path, output: Path) -> dict:
    manifest = json.loads((raw_root / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    records = list(manifest.get("records") or [])
    notices = [record for record in records if record.get("document_class") != "announcement_index_page"
               and record.get("acquisition_status") == "retained"]
    events, results = [], []
    for record in notices:
        payload = (raw_root / record["relative_path"]).read_bytes()
        classified = classify_retained_document(record, payload)
        classified["source_url"] = record["canonical_url"]
        classified["content_type"] = record["content_type"]
        observations = extract_event_observations(classified, extract_text(payload, record["content_type"]))
        events.extend(event_from_observation(record, observation) for observation in observations)
        results.append({"source_id": record["source_id"], "url": record["canonical_url"],
                        "document_id": record["document_id"], "ticker": record["ticker"],
                        "result": "retained_and_extracted", "event_count": len(observations)})
    index_count = sum(record.get("document_class") == "announcement_index_page" for record in records)
    results.insert(0, {"source_id": "vsdc", "route": "one approved announcement index page",
                       "result": "retained_discovery_input_not_event_evidence", "document_count": index_count})
    artifact = build_artifact(events, official_source_results=results)
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output, artifact)
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--twice", action="store_true")
    args = parser.parse_args(argv)
    first = run(args.raw_root, args.output)
    if args.twice:
        second = run(args.raw_root, args.output)
        if first["artifact_identity"] != second["artifact_identity"]:
            return 1
    print(json.dumps({"artifact_identity": first["artifact_identity"], "coverage": first["coverage"],
                      "lane_terminal_status": first["lane_terminal_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
