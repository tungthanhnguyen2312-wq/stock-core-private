"""Provider-agnostic structured securities-firm financial-research component contract.

``securities_financial_research_component/v1`` is a bounded, retained-observation
boundary analogous in spirit to ``bank_financial_research_component.py``.  It is
deliberately separate from the ``canonical_financial_facts``/
``financial_analysis_context/v2`` row shape: that pipeline's canonical metric
vocabulary is built for the generic corporate (industrial) statement template and
has no securities-firm-specific raw components (FVTPL financial assets, brokerage
revenue, margin/loan-receivable interest income, securities-business profit) --
this milestone does not widen it.  This module only defines the shape a retained
securities-firm observation must have and the fitness tiers it may carry -- it
never acquires evidence, calls a live provider, or promotes a proxy to
deterministic authority.

UNLIKE THE BANK CASE: retained evidence check (2026-09-02, governed securities
cohort of 41 tickers under ``entity_classification_contract``) found the raw
securities-firm chart-of-accounts vocabulary (FVTPL assets, brokerage revenue,
loan/receivable interest income, ...) is *already* present verbatim in the
retained ``data_bctc/<TICKER>_{balance_sheet,income_statement}_quarter.parquet``
payloads for all 41/41 governed tickers -- it simply has no canonical consumer
yet.  ``securities_statement_capture_import.py`` maps the exact retained native
item ids this milestone proved into this contract's shape; see that module's
vocabulary table and docstring for the field-by-field evidence.

FITNESS TIERS (per observation -- distinct from the per-*feature* fitness
vocabulary in ``financial_analysis_engine_v2.py``, which is READY /
RESEARCH_PROXY / BLOCKED_BY_EVIDENCE / NOT_APPLICABLE):

    STRUCTURED_RESEARCH_COMPONENT
        A raw retained component (e.g. ``fvtpl_financial_assets``) usable as an
        input to Stock Lookup's own deterministic same-provider ratio arithmetic.
    RESEARCH_PROXY
        A ratio or value the *provider* already computed.  Retained verbatim for
        research context; never an input to a Stock Lookup formula, and a
        feature built from it can never rise above RESEARCH_PROXY fitness.
    UNKNOWN
        Retained but not yet classified into either tier above.

PERIOD SEMANTICS: this milestone does not reopen ``VCI_PERIOD_DURATION_REMAINS_
UNKNOWN``.  It reuses two *already-shipped, item-id-agnostic* routes recognized
by ``structured_financial_period_semantics.py``'s ``_period_state``:

    - any ``balance_sheet`` observation with a resolvable reporting period is
      treated as ``POINT_IN_TIME`` regardless of provider (that rule keys only
      on ``statement_family`` and period resolvability, never on which line item
      or which provider -- the same route that already qualifies the generic
      ``total_assets``/``shareholders_equity`` point-in-time facts, VCI included);
    - any ``income_statement`` observation from provider ``KBS`` at quarterly
      reporting frequency is treated as ``STANDALONE_QUARTER`` (the same
      ``kbs_income_statement_quarter_contract/v1`` route that already qualifies
      the generic ``gross_profit`` canonical metric -- again keyed only on
      provider + statement family + period type, never on item id).

Both routes are asserted here as ``DOCUMENTED_PROVIDER_CONTRACT``: this contract
reuses an already-proven, item-id-independent evidentiary basis rather than
inventing a fresh empirical claim.  Any other combination (a non-KBS income
statement, a cash-flow observation, an annual-only column, ...) is out of this
milestone's scope and must not be built as an observation at all.

PRIVACY BOUNDARY: this contract is public-company financial research only, and
reuses ``bank_financial_research_component.reject_private_fields`` verbatim --
that gate is domain-agnostic (account-number/OAuth/session-token/OTP-shaped
keys), not bank-specific, so a future authenticated securities-data importer is
covered by the same denylist without duplicating it.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import bank_financial_research_component as bank_component
import monetary_basis_contract as basis_contract

CONTRACT_VERSION = "securities_financial_research_component/v1"

# --- Per-observation fitness tiers (task-specified names; distinct spelling from
# bank_financial_research_component's PROVIDER_DERIVED_RESEARCH_PROXY is deliberate) ---
STRUCTURED_RESEARCH_COMPONENT = "STRUCTURED_RESEARCH_COMPONENT"
RESEARCH_PROXY = "RESEARCH_PROXY"
UNKNOWN = "UNKNOWN"
FITNESS_TIERS = frozenset({STRUCTURED_RESEARCH_COMPONENT, RESEARCH_PROXY, UNKNOWN})

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

#: Statement families this contract accepts. Retained securities-firm cash-flow
#: statements are out of scope for this milestone (no target metric needs one).
BALANCE_SHEET = "balance_sheet"
INCOME_STATEMENT = "income_statement"
STATEMENT_FAMILIES = frozenset({BALANCE_SHEET, INCOME_STATEMENT})

#: The raw securities-firm component vocabulary this milestone's real retained-
#: evidence check proved present (see securities_statement_capture_import.py for
#: the native item id each maps from, and REPORT.md for the full per-field proof).
#: Presence here is not a promise a value is currently retained for every ticker;
#: metric_id itself stays free-form (provider-agnostic), this is reference only.
KNOWN_RAW_METRIC_IDS = frozenset({
    "fvtpl_financial_assets", "total_assets", "margin_lending_receivable",
    "brokerage_revenue", "loan_receivable_interest_income", "fvtpl_gain", "fvtpl_loss",
    "securities_business_profit", "total_securities_operating_income",
})


class SecuritiesResearchComponentError(ValueError):
    pass


class SecuritiesResearchComponentPrivacyError(SecuritiesResearchComponentError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def reject_private_fields(payload: Mapping[str, Any] | None) -> None:
    """Raise the moment a private/account-level key is present anywhere in `payload`.

    Delegates to ``bank_financial_research_component``'s denylist verbatim: the
    public-company-research privacy boundary is domain-agnostic, not bank-specific.
    """
    try:
        bank_component.reject_private_fields(payload)
    except bank_component.BankResearchComponentPrivacyError as exc:
        raise SecuritiesResearchComponentPrivacyError(str(exc)) from exc


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
                      statement_family: str, metric_id: str, raw_value: Any,
                      source_identity: str, retrieved_at: str, fitness: str,
                      currency: Any = None, scale: Any = None,
                      limitations: Sequence[str] = (),
                      source_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build one normalized `securities_financial_research_component/v1` observation.

    Never authority-grade.  `fitness` is asserted by the caller (never inferred
    from magnitude or provider reputation) and must be one of `FITNESS_TIERS`.
    `source_payload`, if given, is the raw provider payload this observation was
    derived from -- it is scanned by `reject_private_fields` and never retained
    itself.
    """
    reject_private_fields(source_payload)
    if not str(provider or "").strip():
        raise SecuritiesResearchComponentError("PROVIDER_REQUIRED")
    if not str(ticker or "").strip():
        raise SecuritiesResearchComponentError("TICKER_REQUIRED")
    if str(entity_type or "").strip().lower() != "securities":
        raise SecuritiesResearchComponentError("ENTITY_TYPE_MUST_BE_SECURITIES")
    if period_kind not in PERIOD_KINDS:
        raise SecuritiesResearchComponentError("PERIOD_KIND_UNRECOGNIZED")
    if statement_family not in STATEMENT_FAMILIES:
        raise SecuritiesResearchComponentError("STATEMENT_FAMILY_UNRECOGNIZED")
    if (not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool)
            or not math.isfinite(raw_value)):
        raise SecuritiesResearchComponentError("RAW_VALUE_MUST_BE_NUMERIC")
    if not str(metric_id or "").strip():
        raise SecuritiesResearchComponentError("METRIC_ID_REQUIRED")
    if fitness not in FITNESS_TIERS:
        raise SecuritiesResearchComponentError("FITNESS_MUST_BE_A_DECLARED_TIER")
    if not str(source_identity or "").strip():
        raise SecuritiesResearchComponentError("SOURCE_IDENTITY_REQUIRED")
    if not str(retrieved_at or "").strip():
        raise SecuritiesResearchComponentError("RETRIEVED_AT_REQUIRED")
    if quarter is not None and (not isinstance(quarter, int) or isinstance(quarter, bool)):
        raise SecuritiesResearchComponentError("QUARTER_MUST_BE_INT_OR_NONE")

    native_currency = basis_contract.unit_component(currency)
    native_scale = basis_contract.unit_component(scale)
    monetary_basis = basis_contract.build_basis(currency=native_currency, scale=native_scale,
                                                basis_source=source_identity)

    observation: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "provider": str(provider).strip(),
        "ticker": str(ticker).strip().upper(),
        "entity_type": "securities",
        "year": int(year),
        "quarter": int(quarter) if quarter is not None else None,
        "period_kind": period_kind,
        "period_semantics_status": normalize_period_semantics_status(period_semantics_status),
        "statement_family": statement_family,
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
