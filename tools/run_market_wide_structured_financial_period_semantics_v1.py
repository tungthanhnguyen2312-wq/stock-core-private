"""Build the retained-only structured financial-period-semantics review artifact."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import structured_financial_period_semantics as semantics  # noqa: E402

OUTPUT_DIR = ROOT / "operations-review" / "market-wide-structured-financial-period-semantics-v1-20260831"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_records(path: Path, records: list[dict]) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in records:
            text = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            digest.update(text.encode("utf-8"))
            handle.write(text)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts-root", required=True, type=Path,
                        help="Read-only directory containing retained canonical *.jsonl.gz fact files.")
    parser.add_argument("--source-root-label", default="retained_canonical_financial_facts/facts",
                        help="Portable lineage label only; no local absolute path is emitted.")
    parser.add_argument("--requested-at", default="2026-08-31T00:00:00+07:00")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    if not args.facts_root.is_dir():
        raise SystemExit("RETAINED_FACTS_ROOT_MISSING")
    files = sorted(args.facts_root.glob("*.jsonl.gz"))
    if not files:
        raise SystemExit("RETAINED_FACTS_ROOT_EMPTY")
    source_contract = {
        "source_root_label": args.source_root_label,
        "file_count": len(files), "file_format": "jsonl.gz",
        "read_only": True, "network_used": False, "producer_authority_widened": False,
    }
    artifact = semantics.build_artifact(facts=semantics.load_facts(args.facts_root),
                                        source_contract=source_contract, requested_at=args.requested_at)
    records = artifact.pop("records")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    facts_path = args.output_dir / "structured_financial_period_semantics_facts.jsonl.gz"
    facts_sha = _write_records(facts_path, records)
    artifact["facts_payload"] = {"path": facts_path.name, "record_count": len(records),
                                  "canonical_jsonl_sha256": facts_sha}
    artifact.update(semantics.content_identity(artifact))
    _write_json(args.output_dir / "structured_financial_period_semantics_artifact.json", artifact)
    _write_json(args.output_dir / "README.json", {
        "artifact": "structured_financial_period_semantics_artifact.json",
        "facts_payload": facts_path.name,
        "boundary": "projection_only_no_feature_calculation_or_authority_promotion",
    })
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "coverage": artifact["coverage"],
                      "compatibility": artifact["compatibility"], "facts_payload": facts_path.name},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
