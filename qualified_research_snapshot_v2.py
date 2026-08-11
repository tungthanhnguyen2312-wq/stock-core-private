"""Immutable production-universe-aware research snapshot semantics (v2)."""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping

PRODUCTION_UNIVERSE = ("POW","SSI","HPG","EVF","PAN","PNJ","FPT","QNS","VNM","PVD","NVL")
SCHEMA_VERSION = "2.1.0"
COMPATIBLE_SCHEMA_VERSIONS = frozenset({"2.0.0", SCHEMA_VERSION})

# These are projections of existing Producer capability contracts, not new eligibility
# decisions. Keep this deliberately narrow: a research snapshot must show why market-facing
# conclusions remain unavailable, but must not ingest raw/PIT OHLCV or manufacture a price,
# probability, target, or corporate-action interpretation.
_CAPABILITY_PATHS = {
    "historical_research": ("research", "qualified_research_brief"),
    "raw_as_traded_price": ("market_actionable", "raw_as_traded_price"),
    "current_valuation": ("market_actionable", "current_valuation"),
    "generic_liquidity": ("market_actionable", "generic_liquidity"),
}

def _stable(value: Any) -> str: return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",",":"))
def _hash(value: Any) -> str: return sha256(_stable(value).encode()).hexdigest()
def _m(value: Any) -> Mapping[str, Any]: return value if isinstance(value, Mapping) else {}


def _reason_codes(record: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("reason_codes", "qualification_reason_codes", "blocking_reasons", "missing_evidence"):
        raw = record.get(key)
        if isinstance(raw, (list, tuple, set)):
            values.extend(str(item) for item in raw if item is not None and str(item))
        elif raw is not None and str(raw):
            values.append(str(raw))
    if record.get("reason"):
        values.append(str(record["reason"]))
    return sorted(set(values))


def _capability_state(matrix: Mapping[str, Any], path: tuple[str, str]) -> dict[str, Any]:
    section = _m(matrix.get(path[0]))
    record = _m(section.get(path[1]))
    if not record:
        return {"status": "unknown", "reason_codes": ["capability_contract_not_attached"]}
    return {
        "status": str(record.get("status") or "unknown"),
        "authority_status": record.get("authority_status"),
        "reason_codes": _reason_codes(record),
    }


def _analysis_states(entry: Mapping[str, Any], matrix: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    states = {name: _capability_state(matrix, path) for name, path in _CAPABILITY_PATHS.items()}
    foreign_flow = _m(entry.get("foreign_flow"))
    states["foreign_flow_value"] = {
        "status": str(foreign_flow.get("status") or "unknown"),
        "reason_codes": _reason_codes(foreign_flow),
    }
    return states

def build(bundle: Mapping[str, Any], *, source_identity: Mapping[str, Any]) -> dict[str, Any]:
    """Capture all fixed production tickers; missing state is explicit but never guessed."""
    entries = _m(bundle.get("tickers")); rows=[]
    for ticker in PRODUCTION_UNIVERSE:
        entry=_m(entries.get(ticker)); matrix=_m(entry.get("ticker_capability_matrix")); research=_m(matrix.get("research")); capability=_m(research.get("qualified_research_brief")); brief=_m(entry.get("qualified_research_brief"))
        status=str(capability.get("status") or "unknown") if entry else "unknown"
        analysis_states = _analysis_states(entry, matrix) if entry else {
            name: {"status": "unknown", "reason_codes": ["ticker_not_present_in_source_bundle"]}
            for name in (*_CAPABILITY_PATHS, "foreign_flow_value")
        }
        rows.append({"ticker":ticker,"research_status":status,"reason_codes":_reason_codes(capability),"brief_sha256":_hash(brief) if brief else None,"capability_sha256":_hash(capability) if capability else None,"analysis_states":analysis_states,"semantic_sha256":_hash({"status":status,"capability":capability,"brief":brief,"analysis_states":analysis_states})})
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
