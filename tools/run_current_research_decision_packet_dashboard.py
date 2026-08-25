"""Shadow/opt-in dashboard product projection over the retained current research packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from current_research_decision_packet_product import (
    load_verified_packet,
    markdown,
    project_shadow_panel,
    validate_market_wide,
)

DEFAULT_PACKET = ROOT / "operations-review/current-research-decision-packet-v1/current_research_decision_packet_artifact.json"
DEFAULT_OUTPUT = ROOT / "operations-review/current-research-decision-packet-dashboard-shadow-v1"
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM", "VCB", "AAA")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-path", default=str(DEFAULT_PACKET))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--tickers", nargs="*", default=list(WATCHLIST))
    args = parser.parse_args(argv)
    packet = load_verified_packet(Path(args.packet_path))
    if packet is None:
        print("PACKET_IDENTITY_FAIL_CLOSED")
        return 1
    validation = validate_market_wide(packet)
    panel = project_shadow_panel(packet, list(args.tickers))
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "market_wide_product_validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "current_research_decision_packet_shadow_panel.json").write_text(
        json.dumps(panel, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "current_research_decision_packet_shadow_brief.md").write_text(markdown(panel), encoding="utf-8")
    print(packet.get("artifact_identity"))
    print(json.dumps({k: validation.get(k) for k in (
        "universe_denominator", "unexplained_ticker_residual", "malformed_product_payload_count",
        "partial_packets_remain_usable", "passed",
    )}, sort_keys=True))
    return 0 if validation and validation.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
