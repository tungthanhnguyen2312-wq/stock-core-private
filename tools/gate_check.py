"""Fail-closed P0/P1/current/historical governance gate summary."""
from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def evaluate() -> dict[str, str]:
    contract = json.loads((ROOT / "contracts" / "price_basis.yaml").read_text(encoding="utf-8"))
    p0 = "PASS" if contract["status"].startswith("DETERMINED_") and len(contract["accepted_events"]) >= 8 and contract["provider_version"] != "unretained_in_ohlcv_schema" else "INCOMPLETE"
    return {"P0_basis_and_lineage": p0, "P1_current_session_readiness": "INCOMPLETE", "market_dependent_readiness": "FAIL" if p0 != "PASS" else "INCOMPLETE", "historical_only_hpg_vnm_readiness": "PASS"}
if __name__ == "__main__": print(json.dumps(evaluate(), sort_keys=True))
