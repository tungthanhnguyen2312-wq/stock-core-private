"""Official-versus-legacy provider precedence for one financial fact key.

Same ticker + metric + period + scope:

* EXACT_MATCH — official becomes qualified factual authority only when the
  official row has already passed value-level qualification; legacy remains a
  visible research proxy and is never deleted or relabelled official.
* TRUE_CONFLICT — fail closed for that key; retain both provenances.
* Different period, metric, or consolidated/standalone scope — NOT_COMPARABLE.
* Missing official — not negative evidence; legacy research proxy remains.
* Both absent — no usable evidence.
* DOCUMENT_METADATA_QUALIFIED is never value-level factual authority.
"""
from __future__ import annotations

from typing import Any, Mapping

from canonical_financial_facts import STATUS_QUALIFIED
from canonical_financial_qualification_policy import QUALIFIED as POLICY_QUALIFIED
from financial_evidence_currency_contract import (
    CONTRACT_VERSION,
    LEGACY_PROVIDER_LABEL,
    LEGACY_SOURCE_STATUS,
    canonical_stock_period_alias,
)
from official_financial_filing_evidence import METADATA_QUALIFIED

EXACT_MATCH = "EXACT_MATCH"
TRUE_CONFLICT = "TRUE_CONFLICT"
NOT_COMPARABLE = "NOT_COMPARABLE"
OFFICIAL_ONLY = "OFFICIAL_ONLY"
LEGACY_ONLY = "LEGACY_ONLY"
BOTH_ABSENT = "BOTH_ABSENT"

# Existing value-level official states. DOCUMENT_METADATA_QUALIFIED is not among them.
_VALUE_LEVEL_OFFICIAL_STATES = frozenset({
    "QUALIFIED",  # financial_evidence_currency_refresh._qualify_extracted_fact
    POLICY_QUALIFIED,  # canonical_financial_qualification_policy
    STATUS_QUALIFIED,  # canonical_financial_facts
    "CANONICAL_QUALIFIED",  # official_financial_value_evidence
})

ALLOWED_USES_OFFICIAL_QUALIFIED = (
    "CURRENT_RESEARCH_FACTUAL_AUTHORITY",
    "VALUATION_INPUT_WHERE_METRIC_PERMITS",
)
ALLOWED_USES_LEGACY_PROXY = ("CURRENT_RESEARCH_PROXY_ONLY",)
ALLOWED_USES_CONFLICTED = ()


def _int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != int(number):
            return None
        return int(number)


def official_is_value_qualified(record: Mapping[str, Any] | None) -> bool:
    """True only after value-level official qualification.

    DOCUMENT_METADATA_QUALIFIED is document-level and is never sufficient.
    Numeric agreement with a legacy row does not establish this state.
    """
    if not isinstance(record, Mapping):
        return False
    states = {
        str(record.get("qualification_state") or ""),
        str(record.get("qualification_status") or ""),
        str(record.get("canonical_qualification") or ""),
        str(record.get("metadata_qualification") or ""),
    }
    if METADATA_QUALIFIED in states and not (states & _VALUE_LEVEL_OFFICIAL_STATES):
        return False
    if not (states & _VALUE_LEVEL_OFFICIAL_STATES):
        return False
    if str(record.get("currency") or "") != "VND":
        return False
    scale = record.get("unit_scale") if record.get("unit_scale") is not None else record.get("scale")
    if not scale:
        return False
    if not str(record.get("statement_scope") or ""):
        return False
    if not str(record.get("reporting_period") or ""):
        return False
    if not (
        record.get("document_sha256")
        or record.get("citation_id")
        or record.get("source_span")
        or record.get("citation")
    ):
        return False
    return True


def _normalized(record: Mapping[str, Any] | None) -> int | None:
    if not record:
        return None
    scale = _int(record.get("unit_scale") if record.get("unit_scale") is not None else record.get("scale")) or 1
    raw = record.get("normalized_value")
    if raw is None:
        raw = record.get("value")
    number = _int(raw)
    if number is None:
        return None
    # Values already scaled to VND units leave unit_scale=1 after normalization.
    if record.get("already_normalized") is True:
        return number
    if record.get("normalized_value") is not None and record.get("value") is None:
        return number
    if record.get("normalized_value") is not None:
        return _int(record.get("normalized_value"))
    return number * scale


def compare_official_and_legacy(
    official: Mapping[str, Any] | None,
    legacy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Fail-closed comparison.  Does not mutate either record."""
    if official is None and legacy is None:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": BOTH_ABSENT,
            "reason": "BOTH_ABSENT",
            "allowed_uses": ALLOWED_USES_CONFLICTED,
            "official_becomes_factual_authority": False,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
        }
    if official is None:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": LEGACY_ONLY,
            "reason": "MISSING_OFFICIAL_NOT_NEGATIVE_EVIDENCE",
            "allowed_uses": ALLOWED_USES_LEGACY_PROXY,
            "official_becomes_factual_authority": False,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
            "legacy_source_status": legacy.get("status") or LEGACY_SOURCE_STATUS,
            "legacy_label": LEGACY_PROVIDER_LABEL,
        }
    value_qualified = official_is_value_qualified(official)
    if legacy is None:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": OFFICIAL_ONLY,
            "reason": "NO_LEGACY_ROW",
            "allowed_uses": ALLOWED_USES_OFFICIAL_QUALIFIED if value_qualified else ALLOWED_USES_CONFLICTED,
            "official_becomes_factual_authority": value_qualified,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
        }

    official_period = str(official.get("reporting_period") or "")
    legacy_period = str(legacy.get("reporting_period") or "")
    family = str(official.get("statement_family") or legacy.get("statement_family") or "")
    aliases = set(canonical_stock_period_alias(official_period, family))
    if legacy_period not in aliases and official_period != legacy_period:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": NOT_COMPARABLE,
            "reason": "PERIOD_DIFFERENCE",
            "allowed_uses": ALLOWED_USES_LEGACY_PROXY,
            "official_becomes_factual_authority": False,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
            "official_period": official_period,
            "legacy_period": legacy_period,
        }

    official_scope = str(official.get("statement_scope") or "")
    legacy_scope = str(legacy.get("statement_scope") or "")
    if not official_scope or not legacy_scope or official_scope != legacy_scope:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": NOT_COMPARABLE,
            "reason": "SCOPE_DIFFERENCE",
            "allowed_uses": ALLOWED_USES_LEGACY_PROXY,
            "official_becomes_factual_authority": False,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
            "official_scope": official_scope,
            "legacy_scope": legacy_scope,
        }

    official_metric = str(official.get("canonical_metric") or "")
    legacy_metric = str(legacy.get("canonical_metric") or "")
    if not official_metric or not legacy_metric or official_metric != legacy_metric:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": NOT_COMPARABLE,
            "reason": "METRIC_DIFFERENCE",
            "allowed_uses": ALLOWED_USES_LEGACY_PROXY,
            "official_becomes_factual_authority": False,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
        }

    left, right = _normalized(official), _normalized(legacy)
    if left is None or right is None:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": TRUE_CONFLICT,
            "reason": "VALUE_UNNORMALIZABLE",
            "allowed_uses": ALLOWED_USES_CONFLICTED,
            "official_becomes_factual_authority": False,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
        }
    if left == right:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": EXACT_MATCH,
            "reason": "DIGIT_FOR_DIGIT_AFTER_SCALE",
            "allowed_uses": (
                ALLOWED_USES_OFFICIAL_QUALIFIED if value_qualified else ALLOWED_USES_LEGACY_PROXY
            ),
            "official_becomes_factual_authority": value_qualified,
            "legacy_relabelled_official": False,
            "legacy_deleted": False,
            "legacy_source_status": LEGACY_SOURCE_STATUS,
            "legacy_label": LEGACY_PROVIDER_LABEL,
            "official_value": left,
            "legacy_value": right,
        }
    return {
        "contract_version": CONTRACT_VERSION,
        "status": TRUE_CONFLICT,
        "reason": "VALUE_DISAGREEMENT",
        "allowed_uses": ALLOWED_USES_CONFLICTED,
        "official_becomes_factual_authority": False,
        "legacy_relabelled_official": False,
        "legacy_deleted": False,
        "official_value": left,
        "legacy_value": right,
    }
