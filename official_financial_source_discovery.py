"""Closed-world route discovery: candidate evidence is never source approval."""
from __future__ import annotations
import hashlib, json
from collections import Counter
from typing import Any, Mapping, Sequence

VERSION = "1.0.0"
def _hash(x: Any) -> str: return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def discover_routes(cohort: Sequence[Mapping[str, Any]], signals: Mapping[str, Mapping[str, Any]], registry: Mapping[str, Any]) -> dict[str, Any]:
    """Classify every supplied target once, admitting only explicit existing registry hosts."""
    approved_hosts = {host.lower() for source in registry.get("sources", []) if source.get("activation") == "approved" for host in source.get("allowed_hosts", [])}
    rows=[]
    for target in sorted(cohort, key=lambda x: str(x.get("ticker"))):
        ticker=str(target.get("ticker") or "").upper(); signal=dict(signals.get(ticker) or {})
        url=str(signal.get("candidate_url") or ""); host=url.split("/")[2].lower() if url.startswith(("http://","https://")) and len(url.split("/"))>2 else ""
        evidence=signal.get("issuer_domain_evidence")
        if host and evidence and host in approved_hosts:
            state="APPROVABLE_OFFICIAL_ROUTE_DISCOVERED"; blocker=None; recommendation="existing_approved_source_class"
        elif host and evidence:
            state="CANDIDATE_ROUTE_NEEDS_MORE_EVIDENCE"; blocker="HOST_NOT_IN_APPROVED_REGISTRY"; recommendation="no_registry_change_without_owner_authority"
        elif host:
            state="IDENTITY_AMBIGUOUS"; blocker="ISSUER_DOMAIN_OWNERSHIP_EVIDENCE_MISSING"; recommendation="not_approved"
        else:
            state="NO_OFFICIAL_ROUTE_DISCOVERABLE"; blocker="NO_RETAINED_ISSUER_DOMAIN_OR_EXCHANGE_DETAIL_SIGNAL"; recommendation="not_approved"
        rows.append({"canonical_instrument":ticker,"issuer_legal_identity":signal.get("issuer_legal_identity"),"candidate_url":url or None,"candidate_domain":host or None,"source_class":signal.get("source_class"),"discovery_mechanism":signal.get("discovery_mechanism","retained_closed_world_signal_inventory"),"issuer_domain_evidence":evidence,"observed_at":signal.get("observed_at"),"provenance":signal.get("provenance",[]),"authority_recommendation":recommendation,"disposition":state,"blockers":[blocker] if blocker else []})
    return {"schema_version":VERSION,"route_candidates":rows,"disposition_counts":dict(sorted(Counter(x["disposition"] for x in rows).items())),"identity":_hash(rows)}
