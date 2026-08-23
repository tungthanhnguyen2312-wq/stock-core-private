"""Offline materializer for the retained market-wide current valuation snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from field_temporal_contract import stable_id
from market_wide_current_fundamental_research import content_identity as fundamental_content_identity
from market_wide_current_valuation_input_scaleout import build_current_valuation_artifact, content_identity

OPS = ROOT / "operations-review"
DEFAULT_OUTPUT = OPS / "market-wide-current-valuation-v1-20260824" / "market_wide_current_valuation_artifact.json"
DEFAULT_PRICE = OPS / "p3f9b-market-wide-exact-session-scaleout-20260821" / "p3f9b_mva_exact_session_snapshot.json"
DEFAULT_FUNDAMENTAL = OPS / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json"
DEFAULT_SHARES = OPS / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_sources(price: dict, fundamental: dict, shares: dict) -> None:
    for source, hash_key in ((price, "snapshot_sha256"), (shares, "artifact_sha256")):
        payload = dict(source)
        for key in ("artifact_sha256", "artifact_identity", "snapshot_sha256", "snapshot_identity"):
            payload.pop(key, None)
        if stable_id(payload) != source.get(hash_key):
            raise ValueError(f"SOURCE_SELF_VERIFICATION_FAILED:{hash_key}")
    if fundamental_content_identity(fundamental)["artifact_sha256"] != fundamental.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:fundamental")


def materialize(output: Path = DEFAULT_OUTPUT, *, price: Path = DEFAULT_PRICE,
                fundamental: Path = DEFAULT_FUNDAMENTAL, shares: Path = DEFAULT_SHARES) -> dict:
    price_source, fundamental_source, share_source = _load(price), _load(fundamental), _load(shares)
    _verify_sources(price_source, fundamental_source, share_source)
    artifact = build_current_valuation_artifact(price_snapshot=price_source, fundamental_artifact=fundamental_source,
                                                share_promotion_artifact=share_source)
    if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]:
        raise ValueError("ARTIFACT_SELF_VERIFICATION_FAILED")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(materialize(args.output)["artifact_identity"])


if __name__ == "__main__":
    main()
