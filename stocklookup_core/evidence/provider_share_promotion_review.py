"""Pure policy helpers for a provider-share promotion review.

Nothing here promotes a provider field, changes a resolver, or supplies a
market-cap denominator.  It preserves the provider namespace so a review can
compare evidence without rewriting its semantic identity.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

CANDIDATE_SOURCE = "VCI.overview.issue_share"
PROVIDER_IDENTITY = "ISSUED_SHARES"
AUTHORITY_STATE = "AUTHORITY_NOT_PROMOTED_PENDING_OWNER_DECISION"
MVA_ENVELOPE = {
    "is_actionable_for_execution": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_scope": "CURRENT_DESCRIPTIVE_ONLY",
}
UNSAFE_PROVIDER_STATES = frozenset({
    "provider_reported_stale", "provider_reported_unverifiable_freshness",
    "unknown_observation_date", "unavailable", "unresolved_error",
})


def classify_official_comparison(provider: Mapping[str, Any], official: Mapping[str, Any] | None, *,
                                corporate_action_ambiguous: bool = False) -> str:
    """Classify a retained comparison without treating equal numbers as identity proof."""
    if corporate_action_ambiguous:
        return "CORPORATE_ACTION_AMBIGUOUS"
    if official is None:
        return "INSUFFICIENT_OFFICIAL_REFERENCE"
    value = provider.get("value")
    if not isinstance(value, int) or value <= 0:
        return "INSUFFICIENT_OFFICIAL_REFERENCE"
    official_value = official.get("value")
    if value != official_value:
        return "VALUE_DIFFERENCE"
    if provider.get("identity") != official.get("identity"):
        return "SEMANTICALLY_COMPATIBLE_DIFFERENT_SCOPE"
    if provider.get("observed_on") != official.get("effective_on"):
        return "DATE_MISMATCH"
    return "EXACT_MATCH"


def provider_freshness_state(resolution: Mapping[str, Any]) -> str:
    """Bound the provider observation at its own timestamp, never at a guessed date."""
    authority = str(resolution.get("authority") or "")
    if authority == "provider_reported_current":
        return "PROVIDER_REPORTED_CURRENT"
    if authority == "provider_reported_lagged":
        return "PROVIDER_REPORTED_STALE"
    if authority in UNSAFE_PROVIDER_STATES:
        return "UNKNOWN"
    if authority == "qualified_official":
        return "OFFICIAL_CURRENT_REFERENCE_EXISTS"
    return "UNKNOWN"


def projected_provider_proxy_coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count a hypothetical MVA proxy separately from authoritative readiness."""
    total = len(rows)
    proxy_eligible = sum(
        isinstance(row.get("provider_value"), int) and row["provider_value"] > 0
        and str(row.get("resolver_authority")) not in UNSAFE_PROVIDER_STATES
        for row in rows
    )
    safety_blocked = total - proxy_eligible
    return {
        "cohort_size": total,
        "authoritative_share_ready": 0,
        "authoritative_both_ready": 0,
        "hypothetical_provider_proxy_share_observations": proxy_eligible,
        "hypothetical_provider_proxy_market_cap_inputs": proxy_eligible,
        "hypothetical_provider_proxy_valuation_inputs": proxy_eligible,
        "hypothetical_provider_safety_blocked": safety_blocked,
    }
