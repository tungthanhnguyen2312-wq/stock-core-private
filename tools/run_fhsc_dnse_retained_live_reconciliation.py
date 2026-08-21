"""Execute the bounded FHSC historical-OHLCV reconciliation exactly once per ticker."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fhsc_retained_live_reconciliation import (  # noqa: E402
    TICKERS, fetch_and_retain, fetch_realtime_and_retain, load_finhay_api_key, parse_retained_history,
    parse_retained_realtime, reconciliation_artifact,
)
from provider_reference_reconciliation import _retained_dnse_observations  # noqa: E402


OUTPUT = ROOT / "operations-review" / "fhsc-dnse-retained-live-reconciliation-v1-20260821"


def main() -> int:
    api_key = load_finhay_api_key()
    if not api_key:
        print("credential_present = NO")
        return 2
    artifact_path = OUTPUT / "fhsc_dnse_retained_live_reconciliation_artifact.json"
    previous = json.loads(artifact_path.read_text(encoding="utf-8")) if artifact_path.is_file() else {}
    records = []
    for record in previous.get("request_records", []):
        restored = dict(record)
        restored.setdefault("endpoint_capability", "price_histories_chart_1d")
        if restored.get("raw_path"):
            restored["raw_path"] = ROOT / restored["raw_path"]
        records.append(restored)
    have_history = {item["symbol"] for item in records if item.get("endpoint_capability") != "stock_realtime" and item.get("successful")}
    records.extend(fetch_and_retain(ticker, api_key, OUTPUT / "raw") for ticker in TICKERS if ticker not in have_history)
    have_realtime = {item["symbol"] for item in records if item.get("endpoint_capability") == "stock_realtime" and item.get("successful")}
    records.extend(fetch_realtime_and_retain(ticker, api_key, OUTPUT / "raw") for ticker in TICKERS if ticker not in have_realtime)
    parsed = []
    for record in records:
        result = parse_retained_realtime(record) if record.get("endpoint_capability") == "stock_realtime" else parse_retained_history(record)
        if "symbol" not in result:
            result["symbol"] = record["symbol"]
        parsed.append(result)
    artifact = reconciliation_artifact(_retained_dnse_observations(), records, parsed, OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("credential_present = YES")
    print(json.dumps({"requests_used": len(records), "successful_responses": sum(record["successful"] for record in records)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
