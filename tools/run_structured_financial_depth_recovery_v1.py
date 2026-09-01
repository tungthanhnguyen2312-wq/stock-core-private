"""Materialize retained-only structured financial depth recovery evidence."""
from __future__ import annotations
import argparse, gzip, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import structured_financial_depth_recovery as recovery  # noqa: E402


def _write_rows(path: Path, rows: list[dict]) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            text = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            digest.update(text.encode("utf-8")); handle.write(text)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic-rows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--requested-at", default="2026-09-01T00:00:00+07:00")
    args = parser.parse_args()
    with gzip.open(args.semantic_rows, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    result = recovery.recover(rows, requested_at=args.requested_at)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    recovered_path = args.output_dir / "recovered_structured_financial_depth_rows.jsonl.gz"
    payload_sha = _write_rows(recovered_path, result["recovered_rows"])
    artifact = result["artifact"]
    artifact["recovered_rows_payload"] = {"path": recovered_path.name, "record_count": len(result["recovered_rows"]),
                                            "canonical_jsonl_sha256": payload_sha}
    artifact.update(recovery.content_identity(artifact))
    (args.output_dir / "structured_financial_depth_context_artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"artifact_identity": artifact["artifact_identity"], "coverage": artifact["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
