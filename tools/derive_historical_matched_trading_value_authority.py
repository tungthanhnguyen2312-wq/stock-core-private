"""Offline materializer for historical matched-trading-value authority.

Replays the retained 12-row G1/FHSC exact contract. It does not fetch, does not
impute missing trades as zero, and does not overwrite frozen 2026-08-21/24 artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_official_market_universe import _identity as official_identity
from historical_matched_trading_value_authority import build_historical_matched_trading_value_authority, content_identity

OPS = ROOT / "operations-review"
DEFAULT_OUTPUT_DIR = OPS / "historical-matched-trading-value-authority-v1"
DEFAULT_OFFICIAL_UNIVERSE = OPS / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"
DEFAULT_QUALIFIED_ROWS = (
    OPS / "historical-matched-value-existing-store-requalification-v1-20260824"
    / "prior-contract-replay" / "historical_matched_value_qualified_rows.json"
)
DEFAULT_PRIOR_AUTHORITY = (
    OPS / "historical-matched-value-existing-store-requalification-v1-20260824"
    / "prior-contract-replay" / "historical_matched_traded_value_authority_artifact.json"
)
FINAL_SESSION_MANIFEST = (
    WORKSPACE / "operations-review" / "dnse-market-wide-trades-multi-session-v1-20260812"
    / "session=2026-08-11" / "data" / "market_raw_lake" / "manifests"
    / "DNSE__trades_history__market-wide-trades-40sessions-ending-20260811-v1__20260811.json"
)
FROZEN_OUTPUTS = {
    (OPS / "market-wide-current-valuation-v1-20260824" / "market_wide_current_valuation_artifact.json").resolve(),
    (OPS / "market-wide-current-valuation-v1-20260824-session20260824" / "market_wide_current_valuation_artifact.json").resolve(),
}
FROZEN_IDENTITIES = {
    "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a",
    "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _trades_universe(manifest: Path) -> list[str]:
    payload = _load(manifest)
    suffix = "__20260811__ALL_BOARDS"
    tickers = sorted({
        unit[: -len(suffix)] for unit in payload["requested_units"]
        if isinstance(unit, str) and unit.endswith(suffix)
    })
    if len(tickers) != 1660:
        raise ValueError(f"unexpected_final_trades_universe_size:{len(tickers)}")
    return tickers


def _refuse_frozen(path: Path) -> None:
    if path.resolve() in FROZEN_OUTPUTS:
        raise ValueError("REFUSING_TO_OVERWRITE_FROZEN_VALUATION_ARTIFACT")


def materialize(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict:
    output = output_dir / "historical_matched_trading_value_authority_artifact.json"
    report_path = output_dir / "historical_matched_trading_value_authority_report.json"
    _refuse_frozen(output)
    official = _load(DEFAULT_OFFICIAL_UNIVERSE)
    expected = official_identity(official)
    if expected["artifact_sha256"] != official.get("artifact_sha256"):
        raise ValueError("SOURCE_SELF_VERIFICATION_FAILED:official_universe")
    qualified_rows = _load(DEFAULT_QUALIFIED_ROWS)
    prior = _load(DEFAULT_PRIOR_AUTHORITY)
    if len(qualified_rows) != 12:
        raise ValueError("EXPECTED_12_QUALIFIED_G1_FHSC_ROWS")
    artifact = build_historical_matched_trading_value_authority(
        official_universe=official,
        qualified_rows=qualified_rows,
        trades_universe=_trades_universe(FINAL_SESSION_MANIFEST),
        source_identities={
            "official_universe": official.get("artifact_identity"),
            "prior_matched_value_replay": prior.get("artifact_identity"),
        },
        trades_source_contract=prior.get("trades_source_contract") or {},
    )
    recomputed = content_identity(artifact)
    if recomputed["artifact_sha256"] != artifact["artifact_sha256"]:
        raise ValueError("ARTIFACT_SELF_VERIFICATION_FAILED")
    report = {
        "artifact_identity": artifact["artifact_identity"],
        "verdict": artifact["verdict"],
        "universe_denominator": artifact["coverage"]["universe_denominator"],
        "denominator_reconciles": artifact["coverage"]["denominator_reconciles"],
        "unexplained_count": artifact["coverage"]["unexplained_count"],
        "authority_tier_distribution": artifact["coverage"]["authority_tier_distribution"],
        "reconciliation": artifact["reconciliation"],
        "adtv20_ready_count": artifact["coverage"]["adtv20_ready_count"],
        "adv20_matched_volume_ready_count": artifact["coverage"]["adv20_matched_volume_ready_count"],
        "qualified_liquidity_inputs": artifact["authority_boundary"]["qualified_liquidity_inputs"],
        "position_sizing_is_safe": artifact["authority_boundary"]["position_sizing_is_safe"],
        "frozen_identities_unchanged": sorted(FROZEN_IDENTITIES),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"artifact": artifact, "report": report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = materialize(args.output_dir)
    print(json.dumps({
        "artifact_identity": result["artifact"]["artifact_identity"],
        "verdict": result["artifact"]["verdict"],
        "authority_tier_distribution": result["artifact"]["coverage"]["authority_tier_distribution"],
        "adtv20_ready_count": result["artifact"]["coverage"]["adtv20_ready_count"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
