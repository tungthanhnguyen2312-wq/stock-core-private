"""Provider-agnostic structured bank financial-research component contract.

``bank_financial_research_component/v1`` is a bounded, retained-observation
boundary a future bank-data importer (TCBS or otherwise) can feed.  It is
deliberately separate from the ``canonical_financial_facts``/
``financial_analysis_context/v2`` row shape: that pipeline's canonical metric
vocabulary has no bank-specific raw components (customer loans, deposits,
non-performing loans, provisioning, operating-income/expense split) yet, and
this milestone does not widen it.  This module only defines the shape a
retained bank observation must have and the fitness tiers it may carry --
it never acquires evidence, calls a live provider, or promotes a proxy to
deterministic authority.

FITNESS TIERS (per observation -- distinct from the per-*feature* fitness
vocabulary in ``financial_analysis_engine_v2.py``, which is READY /
RESEARCH_PROXY / BLOCKED_BY_EVIDENCE / NOT_APPLICABLE):

    STRUCTURED_RESEARCH_COMPONENT
        A raw retained component (e.g. ``customer_loan``) usable as an input
        to Stock Lookup's own deterministic same-provider ratio arithmetic.
    PROVIDER_DERIVED_RESEARCH_PROXY
        A ratio the *provider* already computed (e.g. NIM).  Retained
        verbatim for research context; never an input to a Stock Lookup
        formula, and a feature built from it can never rise above
        RESEARCH_PROXY fitness.
    UNKNOWN
        Retained but not yet classified into either tier above.

A bounded 2026-09-01 TCBS MCP capability probe (MBB/SSI/HPG) empirically
reproduced CIR/LDR/NPL from raw components but could not independently
reconstruct NIM -- see ``docs/bank_specialist_financial_research_foundation.md``.
That is why NIM has no deterministic formula anywhere in this module or its
consumer: only a verbatim provider-derived proxy.

PRIVACY BOUNDARY: this contract is public-company financial research only.
``reject_private_fields`` fails closed the moment an account-level or
credential-shaped key is present in a raw source payload, before any of it
reaches ``build_observation``.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import monetary_basis_contract as basis_contract

CONTRACT_VERSION = "bank_financial_research_component/v1"

# --- Per-observation fitness tiers ---------------------------------------
STRUCTURED_RESEARCH_COMPONENT = "STRUCTURED_RESEARCH_COMPONENT"
PROVIDER_DERIVED_RESEARCH_PROXY = "PROVIDER_DERIVED_RESEARCH_PROXY"
UNKNOWN = "UNKNOWN"
FITNESS_TIERS = frozenset({STRUCTURED_RESEARCH_COMPONENT, PROVIDER_DERIVED_RESEARCH_PROXY, UNKNOWN})

# --- Period semantics status (never PIT/audit authority) ------------------
DOCUMENTED_PROVIDER_CONTRACT = "DOCUMENTED_PROVIDER_CONTRACT"
EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS = "EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS"
UNKNOWN_PERIOD_SEMANTICS = "UNKNOWN_PERIOD_SEMANTICS"
PERIOD_SEMANTICS_STATUSES = frozenset({
    DOCUMENTED_PROVIDER_CONTRACT,
    EMPIRICALLY_VERIFIED_PROVIDER_PERIOD_SEMANTICS,
    UNKNOWN_PERIOD_SEMANTICS,
})

QUARTER = "QUARTER"
FISCAL_YEAR = "FISCAL_YEAR"
PERIOD_KINDS = frozenset({QUARTER, FISCAL_YEAR})

#: The raw bank component vocabulary established by the bounded 2026-09-01 TCBS
#: MCP capability probe (MBB/SSI/HPG).  Listing the full probed set here -- not
#: just the subset this milestone's formulas consume -- gives a future importer
#: one typo-checked vocabulary instead of each caller inventing its own
#: spelling.  Presence in this set is not a promise a value is currently
#: retained anywhere; `metric_id` itself stays free-form (provider-agnostic),
#: this is reference only.
KNOWN_RAW_METRIC_IDS = frozenset({
    "customer_loan", "deposit", "non_performing_loan", "provision", "total_asset",
    "total_debt", "total_equity", "operation_expense", "total_operation_income",
    "pre_provision_operating_profit", "net_interest_income", "post_tax_profit",
})

#: Provider-precomputed ratios.  Retained only as PROVIDER_DERIVED_RESEARCH_PROXY
#: observations -- Stock Lookup never recomputes these from raw components.
KNOWN_PROVIDER_RATIO_METRIC_IDS = frozenset({
    "net_interest_margin", "non_performing_loans_ratio_provider", "cost_to_income_provider",
    "loan_on_deposit_provider", "provision_on_non_performing_loans_provider", "loan_growth_provider",
})

#: Field names this contract must never retain -- personal/account-level data,
#: never public-company financial research.  Checked against key names only
#: (never value content) in any raw source payload a future importer supplies
#: for provenance, independent of the normalized observation's own fields.
PRIVATE_FIELD_NAMES = frozenset({
    "account_number", "portfolio_holdings", "personal_asset_allocation",
    "personal_transaction_history", "oauth_token", "session_token",
    "iotp", "otp", "private_account_identity", "customer_id", "password",
})


class BankResearchComponentError(ValueError):
    pass


class BankResearchComponentPrivacyError(BankResearchComponentError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def reject_private_fields(payload: Mapping[str, Any] | None) -> None:
    """Raise the moment a private/account-level key is present anywhere in `payload`.

    This is the input-contract gate a future importer must run over a raw
    provider payload before any of it is normalized into an observation.
    """
    if not payload:
        return
    present = {str(key).strip().lower() for key in payload}
    rejected = PRIVATE_FIELD_NAMES & present
    if rejected:
        raise BankResearchComponentPrivacyError(f"PRIVATE_ACCOUNT_FIELDS_REJECTED:{','.join(sorted(rejected))}")


def normalize_period_semantics_status(value: Any) -> str:
    """Fail closed to UNKNOWN_PERIOD_SEMANTICS; never inferred from context."""
    text = str(value) if value not in (None, "") else ""
    return text if text in PERIOD_SEMANTICS_STATUSES else UNKNOWN_PERIOD_SEMANTICS


def content_identity(observation: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in observation.items()
               if key not in {"component_sha256", "component_identity"}}
    digest = _hash(payload)
    return {"component_sha256": digest, "component_identity": f"{CONTRACT_VERSION}:{digest}"}


def build_observation(*, provider: str, ticker: str, entity_type: str, year: int,
                      quarter: int | None, period_kind: str, period_semantics_status: Any,
                      metric_id: str, raw_value: Any, source_identity: str, retrieved_at: str,
                      fitness: str, currency: Any = None, scale: Any = None,
                      limitations: Sequence[str] = (),
                      source_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build one normalized `bank_financial_research_component/v1` observation.

    Never authority-grade.  `fitness` is asserted by the caller (never
    inferred from magnitude or provider reputation) and must be one of
    `FITNESS_TIERS`.  `source_payload`, if given, is the raw provider payload
    this observation was derived from -- it is scanned by
    `reject_private_fields` and never retained itself.
    """
    reject_private_fields(source_payload)
    if not str(provider or "").strip():
        raise BankResearchComponentError("PROVIDER_REQUIRED")
    if not str(ticker or "").strip():
        raise BankResearchComponentError("TICKER_REQUIRED")
    if str(entity_type or "").strip().lower() != "bank":
        raise BankResearchComponentError("ENTITY_TYPE_MUST_BE_BANK")
    if period_kind not in PERIOD_KINDS:
        raise BankResearchComponentError("PERIOD_KIND_UNRECOGNIZED")
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        raise BankResearchComponentError("RAW_VALUE_MUST_BE_NUMERIC")
    if not str(metric_id or "").strip():
        raise BankResearchComponentError("METRIC_ID_REQUIRED")
    if fitness not in FITNESS_TIERS:
        raise BankResearchComponentError("FITNESS_MUST_BE_A_DECLARED_TIER")
    if not str(source_identity or "").strip():
        raise BankResearchComponentError("SOURCE_IDENTITY_REQUIRED")
    if not str(retrieved_at or "").strip():
        raise BankResearchComponentError("RETRIEVED_AT_REQUIRED")
    if quarter is not None and (not isinstance(quarter, int) or isinstance(quarter, bool)):
        raise BankResearchComponentError("QUARTER_MUST_BE_INT_OR_NONE")

    native_currency = basis_contract.unit_component(currency)
    native_scale = basis_contract.unit_component(scale)
    monetary_basis = basis_contract.build_basis(currency=native_currency, scale=native_scale,
                                                basis_source=source_identity)

    observation: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "provider": str(provider).strip(),
        "ticker": str(ticker).strip().upper(),
        "entity_type": "bank",
        "year": int(year),
        "quarter": int(quarter) if quarter is not None else None,
        "period_kind": period_kind,
        "period_semantics_status": normalize_period_semantics_status(period_semantics_status),
        "metric_id": str(metric_id).strip(),
        "raw_value": raw_value,
        "currency_status": "KNOWN" if basis_contract.known(native_currency) else "UNKNOWN",
        "scale_status": "KNOWN" if basis_contract.known(native_scale) else "UNKNOWN",
        "monetary_basis": monetary_basis,
        "source_identity": str(source_identity).strip(),
        "retrieved_at": str(retrieved_at).strip(),
        "fitness": fitness,
        "limitations": list(limitations),
    }
    observation.update(content_identity(observation))
    return observation
