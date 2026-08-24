"""Acquire one bounded official Vietnam macro evidence slice and replay Macro V1."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_macro_regime import build as build_macro, content_identity as macro_identity
from vietnam_official_macro_evidence import acquire, build, current_macro_observations

BASE_MACRO = ROOT / "operations-review" / "current-macro-regime-v1-20260824" / "current_macro_regime_artifact.json"
OUTPUT_DIR = ROOT / "operations-review" / "vietnam-official-macro-evidence-v1-20260824-r2"


def _write_immutable(path: Path, value: object) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_CONTENT_CONFLICT:" + str(path))
    path.write_text(payload, encoding="utf-8")


def macro_from_evidence(evidence: dict, base_macro: dict) -> dict:
    retained = dict(base_macro.get("observations") or {})
    for row in current_macro_observations(evidence):
        retained[row["indicator_id"]] = row
    raw_sources = list(base_macro.get("raw_sources") or []) + [{"source_identity": "vietnam_official_macro_evidence", "artifact_identity": evidence["artifact_identity"], "sha256": evidence["artifact_sha256"], "status": "RETAINED_EVIDENCE_ARTIFACT"}]
    macro = build_macro(observations=list(retained.values()), raw_sources=raw_sources, retrieved_at=str(evidence["retrieved_at"]))
    macro["vietnam_official_macro_evidence_identity"] = evidence["artifact_identity"]
    macro["vietnam_official_macro_evidence_sha256"] = evidence["artifact_sha256"]
    macro.update(macro_identity(macro))
    return macro


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieved-at", default=None)
    parser.add_argument("--replay", action="store_true", help="Rebuild only from retained evidence; no network request.")
    args = parser.parse_args(); evidence_path = OUTPUT_DIR / "vietnam_official_macro_evidence_artifact.json"
    if args.replay:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8")); rebuilt = build(raw_records=evidence["raw_payloads"], retrieved_at=evidence["retrieved_at"])
        if rebuilt["artifact_identity"] != evidence["artifact_identity"]:
            raise ValueError("EVIDENCE_REPLAY_IDENTITY_MISMATCH")
    else:
        evidence = acquire(retrieved_at=args.retrieved_at); _write_immutable(evidence_path, evidence)
    macro = macro_from_evidence(evidence, json.loads(BASE_MACRO.read_text(encoding="utf-8")))
    _write_immutable(OUTPUT_DIR / "current_macro_regime_v1_with_vietnam_evidence.json", macro)
    print(evidence["artifact_identity"]); print(macro["artifact_identity"])


if __name__ == "__main__":
    main()
