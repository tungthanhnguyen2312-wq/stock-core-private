"""Retain official DNSE endpoint pages and replay the bounded native-OHLC contract."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dnse_provider_native_closed_ohlc import (  # noqa: E402
    CONTRACT_VERSION, cross_provider_native_agreement, qualify_provider_native_closed_ohlc,
)


OUTPUT = ROOT / "operations-review" / "dnse-provider-native-closed-ohlc-semantics-v1-20260821"
ANCHOR_ARTIFACT = ROOT / "operations-review" / "dnse-uniform-ohlc-anchor-qualification-v1-20260821" / "dnse_uniform_ohlc_anchor_qualification_artifact.json"
DNSE_DOCS = (
    ("ohlc_history", "https://developers.dnse.com.vn/docs/dnse/get-ohlc-history/", "/price/ohlc"),
    ("symbol_close", "https://developers.dnse.com.vn/docs/dnse/get-price-symbol-close/", "/price/:symbol/close"),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def retain_official_documents(output: Path) -> list[dict[str, Any]]:
    directory = output / "official-documentation"
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for name, url, endpoint in DNSE_DOCS:
        response = requests.get(url, timeout=(5, 20), allow_redirects=True)
        body = bytes(response.content)
        digest = _sha256(body)
        suffix = ".html" if "html" in response.headers.get("Content-Type", "").lower() else ".bin"
        path = directory / f"{name}_{digest[:16]}{suffix}"
        path.write_bytes(body)
        records.append({"name": name, "requested_url": url, "final_url": str(response.url), "endpoint": endpoint,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(), "http_status": int(response.status_code),
                        "mime_type": response.headers.get("Content-Type"), "raw_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "raw_sha256": digest, "bytes": len(body)})
    return records


def _document_verdict(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    result = []
    for record in records:
        raw = (ROOT / str(record["raw_path"])).read_text(encoding="utf-8", errors="replace")
        result.append({"endpoint": record["endpoint"], "http_status": record["http_status"],
                       "endpoint_literal_present": str(record["endpoint"]).replace(":symbol", "{symbol}") in raw or "/price/" in raw,
                       "verdict": "OFFICIAL_DNSE_DOCUMENTATION_RETAINED_ENDPOINT_CAPABILITY_ONLY"})
    return {"records": result, "numeric_unit": "UNRESOLVED", "adjustment_basis": "UNRESOLVED", "bar_finalization": "UNRESOLVED"}


def _stable(value: dict[str, Any]) -> dict[str, Any]:
    digest = _sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return value | {"artifact_sha256": digest, "artifact_identity": f"dnse_provider_native_closed_ohlc_semantics:{digest}"}


def main() -> int:
    artifact_path = OUTPUT / "dnse_provider_native_closed_ohlc_semantics_artifact.json"
    if artifact_path.exists():
        raise FileExistsError("IMMUTABLE_ARTIFACT_PATH_ALREADY_EXISTS")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    documentation = retain_official_documents(OUTPUT)
    anchor_artifact = json.loads(ANCHOR_ARTIFACT.read_text(encoding="utf-8"))
    qualified = [qualify_provider_native_closed_ohlc(anchor) for anchor in anchor_artifact["corrected_dnse_anchors"]]
    matrix = [{"instrument": anchor["instrument"], "session": anchor["session"],
               "raw_values": {field: anchor["fields"][field]["raw_numeric_value"] for field in ("open", "high", "low", "close")},
               "source_payload_identity": anchor["source_evidence"]["source_payload_identity"]}
              for anchor in anchor_artifact["corrected_dnse_anchors"]]
    replay = anchor_artifact["fhsc_replay"]
    agreement = cross_provider_native_agreement(replay) | {"replay_rows": replay}
    artifact = _stable({
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "artifact_type": "DNSE_PROVIDER_NATIVE_CLOSED_OHLC_SEMANTICS",
        "official_dnse_documentation": documentation, "documentation_verdict": _document_verdict(documentation),
        "retained_dnse_anchor_artifact": {"path": str(ANCHOR_ARTIFACT.relative_to(ROOT)).replace("\\", "/"), "identity": anchor_artifact["artifact_identity"],
                                         "sha256": _sha256(ANCHOR_ARTIFACT.read_bytes())},
        "qualified_provider_native_closed_ohlc": qualified, "dnse_native_ohlc_matrix": matrix, "dnse_fhsc_agreement": agreement,
        "authority_boundaries": {"authority_effect": "NONE", "raw_as_traded_promoted": False, "adjustment_basis_qualified": False,
                                 "formal_price_unit_qualified": False, "fhsc_promoted": False, "dnse_replaced": False,
                                 "runtime_or_database_mutated": False},
    })
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(artifact["artifact_identity"])


if __name__ == "__main__":
    main()
