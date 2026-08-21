"""Run the bounded FHSC legacy-price semantics calibration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fhsc_historical_price_semantics import (  # noqa: E402
    CALIBRATION_TICKERS, build_artifact, fetch_legacy_history_and_retain, load_finhay_api_key,
    retain_official_documents, retained_dnse_ohlc,
)

OUTPUT = ROOT / "operations-review" / "fhsc-historical-price-semantics-qualification-v1-20260821"
DNSE_SNAPSHOT = ROOT / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20260820" / "p3f9b_mva_exact_session_snapshot.json"


def main() -> int:
    key = load_finhay_api_key()
    if not key:
        print("credential_present = NO")
        return 2
    artifact_path = OUTPUT / "fhsc_historical_price_semantics_qualification_artifact.json"
    previous = json.loads(artifact_path.read_text(encoding="utf-8")) if artifact_path.is_file() else {}
    docs = []
    for record in previous.get("official_documentation", []):
        restored = dict(record)
        restored["raw_path"] = ROOT / restored["raw_path"]
        docs.append(restored)
    if not docs:
        docs = retain_official_documents(OUTPUT)
    dnse_rows, dnse_identity = retained_dnse_ohlc(DNSE_SNAPSHOT)
    records = []
    for record in previous.get("ohcl_scale_matrix", {}).get("fhsc_retained_evidence", []):
        restored = dict(record)
        restored["raw_path"] = ROOT / restored["raw_path"]
        restored["raw_sha256"] = restored.pop("sha256")
        restored["successful"] = True
        restored["request_parameters"] = {}
        records.append(restored)
    present = {record["symbol"] for record in records}
    records.extend(fetch_legacy_history_and_retain(ticker, key, OUTPUT / "raw") for ticker in CALIBRATION_TICKERS if ticker not in present)
    artifact = build_artifact(docs, dnse_rows, dnse_identity, records)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("credential_present = YES")
    print(json.dumps({"fhsc_requests": len(records), "successful": sum(record["successful"] for record in records)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
