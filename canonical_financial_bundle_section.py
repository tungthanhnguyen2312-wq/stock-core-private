"""Additive, opt-in bundle section carrying canonical financial facts and readiness.

WHAT THIS IS
    The integration boundary between pillar A and the Producer. It builds one per-ticker
    section from the canonical fact store and the calculation-readiness policy, in the shape
    the bundle already uses for opt-in evidence sections.

WHY IT IS DISABLED BY DEFAULT AND WHY THAT IS NOT TIMIDITY
    The exact-session proof in `bundle_manifest.json` hash-binds the whole artifact set.
    Adding a section to the default bundle changes `analysis_bundle.json`, which changes the
    proof, which changes a production artifact -- for a layer whose market-wide ceiling is
    `provider_reported`. So the section follows the Phase 5A/6A precedent exactly: with
    `include=False` no builder runs and no key is added, and the default bundle is
    byte-identical to the one built before this module existed. That identity is asserted, not
    assumed -- see `tests/test_canonical_financial_facts.py` and the milestone's double-build.

WHAT MAY AND MAY NOT CROSS THE BOUNDARY

    * A metric enters only with its **status, provenance, period, scope, unit, basis and
      limitations** attached. A bare number never crosses.
    * `conflicted` and `unavailable` facts cross as **status only**, with their reason. Their
      values do not, because a consumer that sees a number will eventually use it.
    * Raw observations never cross. The section carries `source_observation_ids`, which are
      pointers into the layer-1 store, not the 1.5 million observations themselves.
    * No ranking, no score, no whole-market ordering, and no `is_actionable` change. The
      section reports per-ticker readiness and nothing comparative.

BACKWARD COMPATIBILITY
    Every key this module writes is new. It never reads, writes or reorders `financial_canonical`,
    `fundamental_quality`, `financial_period_coverage` or any other pre-existing field, so a
    consumer pinned to the current schema sees exactly what it saw before.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from canonical_financial_facts import (
    CONTRACT_VERSION,
    MAPPER_VERSION,
    STATUS_CONFLICTED,
    STATUS_PARTIAL,
    STATUS_PROVIDER_REPORTED,
    STATUS_QUALIFIED,
    STATUS_UNAVAILABLE,
)
from canonical_financial_resolvers import VERSION as RESOLVER_VERSION
from market_wide_calculation_readiness import (
    CAPABILITIES,
    POLICY_VERSION,
    STILL_BLOCKED_BY_PRICE_BASIS,
)

SECTION_VERSION = "1.0.0"
SECTION_KEY = "canonical_financial_facts"

#: Statuses whose numeric value may cross the boundary. Everything else crosses as a status
#: and a reason only.
_VALUE_BEARING = frozenset({STATUS_QUALIFIED, STATUS_PROVIDER_REPORTED, STATUS_PARTIAL})

_LIMITATIONS = (
    "Canonical facts are not evidence-qualified unless `status` is `qualified`; the "
    "market-wide ceiling is `provider_reported`, which means the identity is resolved and "
    "internally coherent but currency and absolute unit scale are unevidenced.",
    "`statement_scope` is `consolidated` only where a non-zero minority interest evidences "
    "it; `unknown` never means `separate`.",
    "Quarterly cash-flow facts are period-attributable only where end-of-period cash agrees "
    "with the balance sheet; where it does not, the fact is `conflicted`.",
    "Nothing in this section is current-market dependent, and nothing in it changes "
    "`is_actionable`, which remains governed by the price and volume basis.",
    "No value here is a ranking, a score or a recommendation.",
)


def _fact_view(fact: Mapping[str, Any]) -> dict[str, Any]:
    """One canonical fact reduced to what a consumer may safely see."""
    status = str(fact["status"])
    view = {
        "canonical_metric": fact["canonical_metric"],
        "status": status,
        "reason": fact["reason"],
        "reporting_period": fact["reporting_period"],
        "period_start": fact["period_start"],
        "period_end": fact["period_end"],
        "reporting_frequency": fact["reporting_frequency"],
        "statement_family": fact["statement_family"],
        "statement_scope": fact["statement_scope"],
        "currency": fact["currency"],
        "scale": fact["scale"],
        "unit_authority": fact["unit_authority"],
        "sign_convention": fact["sign_convention"],
        "cumulative_state": fact["cumulative_state"],
        "confidence": fact["confidence"],
        "warnings": list(fact["warnings"]),
        "conflicts": [conflict.get("kind") for conflict in fact.get("conflicts") or []],
        "provenance": {
            "provider": fact["provider"],
            "dialect": fact["dialect"],
            "raw_item_id": fact["raw_item_id"],
            "source_file": fact["source_file"],
            "source_sha256": fact["source_sha256"],
            "source_observation_ids": list(fact["source_observation_ids"] or []),
            "observed_at": fact["observed_at"],
            "mapper_version": fact["mapper_version"],
            "contract_version": fact["contract_version"],
            "resolver_version": fact["resolver_version"],
        },
    }
    # A number crosses only with a usable status. A conflicted or unavailable metric crosses
    # as a status and a reason, so no consumer can pick up a value the layer refused.
    view["value"] = fact["value"] if status in _VALUE_BEARING else None
    view["value_withheld"] = status not in _VALUE_BEARING
    return view


def _readiness_view(period: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reporting_period": period["reporting_period"],
        **{
            name: {
                "readiness": period[name]["readiness"],
                "status": period[name]["status"],
                "value": period[name]["value"],
                "formula": period[name]["formula"],
                "reason": period[name]["reason"],
                "blocked_by": list(period[name]["blocked_by"]),
                "terms": period[name]["terms"],
            }
            for name in CAPABILITIES
        },
    }


def build_section(ticker: str, facts: Sequence[Mapping[str, Any]],
                  readiness: Mapping[str, Any] | None,
                  store_state_fingerprint: str | None = None) -> dict[str, Any]:
    """The complete additive section for one ticker. Pure: no I/O, no clock."""
    latest = max((str(fact["reporting_period"]) for fact in facts), default=None)
    status_counts: dict[str, int] = {}
    for fact in facts:
        key = str(fact["status"])
        status_counts[key] = status_counts.get(key, 0) + 1

    return {
        "section_version": SECTION_VERSION,
        "mapper_version": MAPPER_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "readiness_policy_version": POLICY_VERSION,
        "fact_store_state_fingerprint": store_state_fingerprint,
        "ticker": str(ticker).upper(),
        "latest_reporting_period": latest,
        "reporting_periods": sorted({str(fact["reporting_period"]) for fact in facts}),
        "status_counts": dict(sorted(status_counts.items())),
        "facts": [_fact_view(fact) for fact in facts
                  if str(fact["reporting_period"]) == latest],
        "calculation_readiness": [
            _readiness_view(period) for period in (readiness or {}).get("periods", [])
            if str(period["reporting_period"]) == latest
        ],
        "still_blocked_by_price_basis": list(STILL_BLOCKED_BY_PRICE_BASIS),
        "limitations": list(_LIMITATIONS),
    }


def attach(bundle_entries: Mapping[str, dict], runtime_root: Path | str,
           include: bool) -> Mapping[str, dict]:
    """Disabled-by-default opt-in, matching the Phase 5A/6A wiring exactly.

    With `include=False` nothing is read, nothing is built and no key is added, so the default
    bundle is unchanged. A ticker whose section cannot be built is skipped rather than
    partially written, so one bad shard can never corrupt another ticker's entry.
    """
    if not include:
        return bundle_entries

    from canonical_fact_store import _load_state, read_facts
    from financial_entity_applicability import metric_applicability
    from market_wide_calculation_readiness import evaluate_ticker

    state = _load_state(runtime_root)
    if not state:
        return bundle_entries
    fingerprint = state.get("state_fingerprint")
    records = {str(record["ticker"]): record for record in state.get("tickers") or []}

    for ticker, entry in bundle_entries.items():
        record = records.get(str(ticker).upper())
        if record is None:
            continue
        try:
            facts = read_facts(runtime_root, ticker)
            if not facts:
                continue
            archetype = {
                "ticker": str(ticker).upper(),
                "issuer_entity_type": record.get("issuer_entity_type"),
                "template_family": record.get("template_family"),
                "authority": record.get("archetype_authority"),
            }
            readiness = evaluate_ticker(ticker, facts, {
                "ticker": str(ticker).upper(), "archetype": archetype,
                "metric_applicability": {metric: metric_applicability(archetype, metric)
                                         for metric in ("ebitda", "ev_ebitda")}})
            entry[SECTION_KEY] = build_section(ticker, facts, readiness, fingerprint)
        except Exception:  # noqa: BLE001 - one ticker failing never corrupts the export
            continue
    return bundle_entries
