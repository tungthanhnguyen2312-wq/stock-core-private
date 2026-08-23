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
from market_wide_current_valuation_input_scaleout import attach_shadow_proxy_valuation, build_current_valuation_artifact, content_identity
from market_wide_current_shares_resolver import resolve_market_wide_shares
from tools.run_p3f6_mva_provider_share_proxy import _metadata

OPS = ROOT / "operations-review"
DEFAULT_OUTPUT = OPS / "market-wide-current-valuation-v1-20260824" / "market_wide_current_valuation_artifact.json"
DEFAULT_PRICE = OPS / "p3f9b-market-wide-exact-session-scaleout-20260821" / "p3f9b_mva_exact_session_snapshot.json"
DEFAULT_FUNDAMENTAL = OPS / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json"
DEFAULT_SHARES = OPS / "p3f5-current-share-promotion-review-20260820" / "p3f5_current_share_promotion_review_artifact.json"
DEFAULT_P3E = OPS / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_sources(price: dict, fundamental: dict, shares: dict, p3e: dict) -> None:
    for source, hash_key in ((price, "snapshot_sha256"), (shares, "artifact_sha256"), (p3e, "artifact_sha256")):
        payload = dict(source)
        for key in ("artifact_sha256", "artifact_identity", "snapshot_sha256", "snapshot_identity"):
            payload.pop(key, None)
        if stable_id(payload) != source.get(hash_key):
            raise ValueError(f"SOURCE_SELF_VERIFICATION_FAILED:{hash_key}")
    if fundamental_content_identity(fundamental)["artifact_sha256"] != fundamental.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:fundamental")


def materialize(output: Path = DEFAULT_OUTPUT, *, price: Path = DEFAULT_PRICE,
                fundamental: Path = DEFAULT_FUNDAMENTAL, shares: Path = DEFAULT_SHARES,
                p3e: Path = DEFAULT_P3E, runtime_root: Path | None = None) -> dict:
    if runtime_root is None:
        raise ValueError("RUNTIME_ROOT_REQUIRED_FOR_RETAINED_PROVIDER_SHARE_INVENTORY")
    price_source, fundamental_source, share_source, p3e_source = _load(price), _load(fundamental), _load(shares), _load(p3e)
    _verify_sources(price_source, fundamental_source, share_source, p3e_source)
    artifact = build_current_valuation_artifact(price_snapshot=price_source, fundamental_artifact=fundamental_source,
                                                share_promotion_artifact=share_source)
    session = str(price_source["resolved_completed_session"])
    safety = resolve_market_wide_shares(runtime_root, session)
    if safety.get("status") != "measured" or not safety.get("counts_reconcile"):
        raise ValueError("RETAINED_SHARE_INVENTORY_UNREADABLE_OR_NONRECONCILING")
    artifact = attach_shadow_proxy_valuation(authoritative_artifact=artifact, price_snapshot=price_source,
                                             p3e_artifact=p3e_source, provider_observations=_metadata(runtime_root),
                                             safety_states=safety["tickers"])
    artifact["retained_provider_share_inventory"] = {
        "runtime_metadata_universe": safety["active_universe_count"], "usable_positive_observations": safety["usable_share_value_count"],
        "authority_counts": safety["counts"], "session": session,
    }
    artifact.update(content_identity(artifact))
    if content_identity(artifact)["artifact_sha256"] != artifact["artifact_sha256"]:
        raise ValueError("ARTIFACT_SELF_VERIFICATION_FAILED")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    print(materialize(args.output, runtime_root=args.runtime_root)["artifact_identity"])


if __name__ == "__main__":
    main()
