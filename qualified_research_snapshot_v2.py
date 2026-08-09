"""Immutable production-universe-aware research snapshot semantics (v2)."""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping

PRODUCTION_UNIVERSE = ("POW","SSI","HPG","EVF","PAN","PNJ","FPT","QNS","VNM","PVD","NVL")
SCHEMA_VERSION = "2.0.0"

def _stable(value: Any) -> str: return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",",":"))
def _hash(value: Any) -> str: return sha256(_stable(value).encode()).hexdigest()
def _m(value: Any) -> Mapping[str, Any]: return value if isinstance(value, Mapping) else {}

def build(bundle: Mapping[str, Any], *, source_identity: Mapping[str, Any]) -> dict[str, Any]:
    """Capture all fixed production tickers; missing state is explicit but never guessed."""
    entries = _m(bundle.get("tickers")); rows=[]
    for ticker in PRODUCTION_UNIVERSE:
        entry=_m(entries.get(ticker)); matrix=_m(entry.get("ticker_capability_matrix")); research=_m(matrix.get("research")); capability=_m(research.get("qualified_research_brief")); brief=_m(entry.get("qualified_research_brief"))
        status=str(capability.get("status") or "unknown") if entry else "unknown"
        rows.append({"ticker":ticker,"research_status":status,"reason_codes":sorted(str(x) for x in capability.get("reason_codes",[]) if x is not None),"brief_sha256":_hash(brief) if brief else None,"capability_sha256":_hash(capability) if capability else None,"semantic_sha256":_hash({"status":status,"capability":capability,"brief":brief})})
    identity={"schema_version":SCHEMA_VERSION,"production_universe":list(PRODUCTION_UNIVERSE),"source_identity":dict(source_identity),"ticker_semantics":[{"ticker":x["ticker"],"semantic_sha256":x["semantic_sha256"]} for x in rows]}
    return {"schema_version":SCHEMA_VERSION,"snapshot_id":"qrs2-"+_hash(identity),"identity":identity,"tickers":rows,"historical_only":True,"is_actionable":False}

def from_served_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct the V2 snapshot an already-served analysis bundle actually represents.

    This is the authoritative "immediately previous served state" for the next release's
    comparison baseline: the identical pure computation `build()` performed when the bundle
    was generated, replayed against that bundle's own retained content -- never a separately
    retained or hand-picked snapshot file that can drift from what was truly served.
    """
    return build(bundle, source_identity={"reference_session_date": bundle.get("reference_session_date"),
                                          "bundle_generation": "export_ai_bundle"})
