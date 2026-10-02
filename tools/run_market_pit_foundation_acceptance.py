"""Exact-input offline Release B acceptance; output counts/hashes only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prospective_market_evidence_retention as retention
import prospective_market_snapshot_contract as market


def run(*, inputs: dict[str, tuple[Path, str]], output_root: Path) -> dict:
    source_bytes = {key: path.read_bytes() for key, (path, _) in inputs.items()}
    for key, body in source_bytes.items():
        if market.sha256_hex(body) != inputs[key][1]:
            raise ValueError("INPUT_HASH_MISMATCH:" + key)
    price = json.loads(source_bytes["price"])
    session = price["resolved_completed_session"]
    first = retention.retain_market(price, session=session, root=output_root)
    before = {p: p.read_bytes() for p in (output_root / "operations-review/prospective-market-evidence-v1" / session).rglob("*.json")}
    repeat = retention.retain_market(price, session=session, root=output_root)
    if first["artifact_identity"] != repeat["artifact_identity"] or any(p.read_bytes() != body for p,body in before.items()):
        raise ValueError("IDEMPOTENCE_FAILURE")
    universe = retention.retain_universe(inputs["universe"][0], root=output_root)
    corporate = retention.retain_corporate(json.loads(source_bytes["corporate"]), root=output_root)
    if any(path.read_bytes() != source_bytes[key] for key, (path, _) in inputs.items()):
        raise ValueError("SOURCE_MUTATED")
    report = {"contract_version": "market_pit_foundation_acceptance/v1", "session": session,
              "input_sha256": {key: digest for key, (_,digest) in inputs.items()},
              "market": {k:v for k,v in first.items() if k != "path"},
              "universe": {k:v for k,v in universe.items() if k != "path"},
              "corporate": {k:v for k,v in corporate.items() if k != "path"},
              "idempotence": "PASS", "source_bytes_unchanged": True,
              "authority_effect": "NONE", "acquisition_requests": 0, "production_writes": 0}
    report.update(market.content_identity(report, kind="market_pit_foundation_acceptance"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("price", "universe", "corporate"):
        parser.add_argument("--" + key + "-source", required=True, type=Path)
        parser.add_argument("--" + key + "-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run(inputs={key:(getattr(args,key+"_source"),getattr(args,key+"_sha256")) for key in ("price","universe","corporate")}, output_root=args.output_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
