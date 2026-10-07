"""Materialize the current corporate-intelligence artifact from retained inputs only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from market_wide_current_corporate_intelligence import build, content_identity


def main() -> None:
    parser = argparse.ArgumentParser(description="Build retained-evidence current corporate intelligence.")
    parser.add_argument("--session", default="2026-08-21")
    parser.add_argument("--descriptive", type=Path, default=None)
    parser.add_argument("--fundamental", type=Path, default=None)
    parser.add_argument("--official-event-context", type=Path)
    parser.add_argument("--expected-event-identity")
    parser.add_argument("--evidence-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "operations-review/market-wide-current-corporate-intelligence-v1-20260824/market_wide_current_corporate_intelligence_artifact.json")
    args = parser.parse_args()
    operations = ROOT / "operations-review"
    desc_path = args.descriptive or (operations / "market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_descriptive_research_artifact.json")
    fund_path = args.fundamental or (operations / "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json")
    descriptive = json.loads(desc_path.read_text(encoding="utf-8"))
    fundamental = json.loads(fund_path.read_text(encoding="utf-8"))
    from daily_session_level2_package import registered_official_event_context
    event = (json.loads(args.official_event_context.read_text(encoding="utf-8"))
             if args.official_event_context else registered_official_event_context(args.evidence_root, args.session))
    if args.official_event_context and not args.expected_event_identity:
        raise ValueError("EXPLICIT_EVENT_IDENTITY_REQUIRED")
    if args.expected_event_identity and (event or {}).get("artifact_identity") != args.expected_event_identity:
        raise ValueError("OFFICIAL_EVENT_SELECTION_IDENTITY_MISMATCH")
    artifact = build(descriptive=descriptive, fundamental=fundamental, session=args.session, root=args.evidence_root, official_event_context=event)
    artifact["official_event_binding"] = {
        "status": "AVAILABLE" if event else "UNAVAILABLE",
        "artifact_identity": (event or {}).get("artifact_identity"),
        "reason": None if event else "EXACT_REGISTERED_SESSION_EVENT_CONTEXT_UNAVAILABLE",
    }
    artifact.update(content_identity(artifact))
    if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]: raise ValueError("CORPORATE_INTELLIGENCE_SELF_VERIFICATION_FAILED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
