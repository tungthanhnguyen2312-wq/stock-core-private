"""Altman Z'-Score (1983 private-firm variant) over already-qualified canonical inputs.

Why Z' and not the classic 1968 Z: the classic Z's X4 is *market* value of equity /
total liabilities. This project's price basis is globally `unknown/unverified`
(docs/STATE.md), so a classic Z would import an unqualified market basis into a
fundamental model and couple this contract to the P0 price-basis blocker. Z' replaces
that single term with *book* value of equity / total liabilities, making every input a
balance-sheet or income-statement identity from one already-qualified annual period.
No market price, no current-session data, and no prior-year comparative is consumed --
Altman is a single-period cross-sectional model, so the unresolved FY2023 comparative
gap (docs/ROADMAP.md, Phase 6C) does not block it.

Fail-closed rules:
  - Every one of the six required identities must be present, from the same
    (period, statement_scope, currency, unit_scale). Any mismatch or absence yields
    status="insufficient_evidence" with the exact missing/conflicting names -- never a
    partial score, never a substituted proxy.
  - total_assets must be strictly positive (every ratio divides by it) and
    total_liabilities strictly positive (X4 divides by it).
  - The variant is always declared explicitly in the output. Z' has its own threshold
    band (distress < 1.23, grey 1.23-2.90, safe > 2.90); the classic Z bands
    (1.81/2.99) are never applied to a Z' value.
  - is_actionable is always False: this contract emits an evidence-qualified,
    historical single-period diagnostic, never an investment signal.
"""
from __future__ import annotations

from typing import Any, Mapping

from altman_applicability import evaluate_altman_applicability

VERSION = "1.0.0"
VARIANT = "altman_z_prime_1983_private_firm"
FORMULA = "0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4 + 0.998*X5"
COEFFICIENTS = {"X1": 0.717, "X2": 0.847, "X3": 3.107, "X4": 0.420, "X5": 0.998}
DISTRESS_THRESHOLD = 1.23
SAFE_THRESHOLD = 2.90

REQUIRED_IDENTITIES = (
    "current_assets", "current_liabilities", "retained_earnings",
    "total_assets", "total_liabilities", "net_sales", "owners_equity", "ebit",
)

# Altman's corporate Z/Z' models were estimated on manufacturing/non-financial firms and
# are not applicable to financial institutions: a bank has no meaningful working-capital
# or current-asset/current-liability split (its balance sheet is a funding structure, not
# an operating cycle), and "sales / total assets" has no equivalent meaning. Same
# entity-type set analysis_lane_eligibility.py treats as non-generic-corporate. This is a
# structural inapplicability, distinct from insufficient_evidence -- citing bank
# identities would not make the score meaningful.
_NON_APPLICABLE_ENTITY_TYPES = frozenset({"bank", "securities", "insurance", "finance_company"})
# Absent/unknown is a third state, distinct from both "corporate" and "known to be a
# financial institution". It blocks rather than defaulting -- see evaluate_altman_z_score.
_UNQUALIFIED_ENTITY_TYPES = frozenset({"", "unknown", "none", "null"})

_IDENTITY_ALIGNMENT_KEYS = ("period", "statement_scope", "currency", "unit_scale")


def _out(status: str, **extra: Any) -> dict[str, Any]:
    result = {
        "schema_version": VERSION, "model": "altman_z_score", "variant": VARIANT,
        "formula": FORMULA, "status": status, "score": None, "zone": None, "zone_proximity": None,
        "applicability": None,
        "components": {}, "inputs": {}, "missing_inputs": [], "blocking_reasons": [],
        "thresholds": {"distress_below": DISTRESS_THRESHOLD, "safe_above": SAFE_THRESHOLD},
        "period": None, "statement_scope": None, "currency": None, "unit_scale": None,
        "historical_only": True, "market_dependent": False,
        "limitations": [
            "Z'-score (private-firm variant): X4 uses book value of equity, never market value. "
            "Not comparable with a classic 1968 Z-score or its 1.81/2.99 thresholds.",
            "Single-period cross-sectional diagnostic for the stated reporting period only; "
            "not a current-market assessment and not a trend.",
        ],
        "is_actionable": False,
    }
    result.update(extra)
    return result


# A zone label is a step function over a continuous score, so a score sitting just inside
# a boundary carries far less information than the bare label suggests -- VNM FY2024 lands
# at 2.8976 against a 2.90 safe threshold, 0.08% away from a different verdict. Reporting
# the distance to the nearest boundary, and flagging it when it is within this relative
# tolerance, keeps the label from being read as more decisive than the arithmetic is.
NEAR_THRESHOLD_RELATIVE_TOLERANCE = 0.02


def _zone(score: float) -> str:
    if score < DISTRESS_THRESHOLD:
        return "distress"
    if score > SAFE_THRESHOLD:
        return "safe"
    return "grey"


def _zone_proximity(score: float) -> dict[str, Any]:
    """Distance from `score` to the nearer zone boundary, plus a near-threshold flag."""
    distances = {"distress_below": abs(score - DISTRESS_THRESHOLD), "safe_above": abs(score - SAFE_THRESHOLD)}
    nearest = min(distances, key=distances.get)
    threshold = DISTRESS_THRESHOLD if nearest == "distress_below" else SAFE_THRESHOLD
    distance = distances[nearest]
    return {
        "nearest_threshold": nearest, "nearest_threshold_value": threshold,
        "distance_to_nearest_threshold": distance,
        "relative_distance": distance / threshold,
        "near_threshold": distance / threshold <= NEAR_THRESHOLD_RELATIVE_TOLERANCE,
    }


def evaluate_altman_z_score(identities: Mapping[str, Mapping[str, Any]] | None,
                             entity_type: str = "corporate", industry: Any = None,
                             statement_taxonomy: Any = None) -> dict[str, Any]:
    """Pure. `identities` maps identity name -> {"value", "period", "statement_scope",
    "currency", "unit_scale", and optional lineage keys carried through unchanged}.

    Returns a fail-closed envelope; see module docstring. Never raises on missing or
    malformed input.

    Applicability is decided first, by `altman_applicability.evaluate_altman_applicability`,
    and a non-eligible verdict short-circuits before any arithmetic. `entity_type` alone is
    NOT sufficient: Z' retains the industry-sensitive X5 term and was estimated on
    manufacturing firms, so a confirmed non-financial issuer in a non-manufacturing industry
    still yields "insufficient_evidence" rather than a score.

    `statement_taxonomy` is optional GENERATED evidence (see `statement_taxonomy_sidecar`)
    and is forwarded unchanged to the applicability gate, which consults it only to
    *withhold* applicability -- an observed specialized-financial template yields
    `not_applicable` even with no resolved entity type, while `corporate_vas` alone never
    grants eligibility. A manually verified `entity_type` always takes precedence.
    """
    applicability = evaluate_altman_applicability(entity_type, industry,
                                                   statement_taxonomy=statement_taxonomy)
    if applicability["applicability"] != "eligible":
        status = applicability["applicability"]
        missing = ["entity_type"] if str(entity_type or "").strip().lower() in _UNQUALIFIED_ENTITY_TYPES else []
        if status == "insufficient_evidence" and not missing and not applicability["industry_qualified_manufacturing"]:
            missing = ["qualified_manufacturing_industry"]
        return _out(status, applicability=applicability, missing_inputs=missing,
                    blocking_reasons=[applicability["reason"]])
    identities = identities if isinstance(identities, Mapping) else {}
    present = {name: identities[name] for name in REQUIRED_IDENTITIES
               if isinstance(identities.get(name), Mapping) and _number(identities[name].get("value")) is not None}
    missing = [name for name in REQUIRED_IDENTITIES if name not in present]
    if missing:
        return _out("insufficient_evidence", applicability=applicability, missing_inputs=missing,
                    blocking_reasons=[f"required identity not qualified: {', '.join(missing)}"])

    alignment = {key: {present[name].get(key) for name in present} for key in _IDENTITY_ALIGNMENT_KEYS}
    conflicting = [key for key, values in alignment.items() if len(values) != 1]
    if conflicting:
        return _out("insufficient_evidence", applicability=applicability,
                    blocking_reasons=[f"qualified identities disagree on {', '.join(conflicting)}; "
                                       "never combined across a mismatch"])

    values = {name: _number(entry["value"]) for name, entry in present.items()}
    total_assets, total_liabilities = values["total_assets"], values["total_liabilities"]
    if total_assets <= 0:
        return _out("insufficient_evidence", applicability=applicability,
                    blocking_reasons=["total_assets must be strictly positive"])
    if total_liabilities <= 0:
        return _out("insufficient_evidence", applicability=applicability,
                    blocking_reasons=["total_liabilities must be strictly positive"])

    working_capital = values["current_assets"] - values["current_liabilities"]
    ratios = {
        "X1": working_capital / total_assets,
        "X2": values["retained_earnings"] / total_assets,
        "X3": values["ebit"] / total_assets,
        "X4": values["owners_equity"] / total_liabilities,
        "X5": values["net_sales"] / total_assets,
    }
    score = sum(COEFFICIENTS[name] * ratio for name, ratio in ratios.items())
    sample = next(iter(present.values()))
    proximity = _zone_proximity(score)
    limitations = None
    if proximity["near_threshold"]:
        limitations = _out("available")["limitations"] + [
            f"Score is {proximity['distance_to_nearest_threshold']:.4f} from the "
            f"{proximity['nearest_threshold']} boundary ({proximity['nearest_threshold_value']}), within "
            f"{NEAR_THRESHOLD_RELATIVE_TOLERANCE:.0%} of it: the zone label is not robust to small "
            "input revisions and should not be read as a decisive classification."]
    return _out(
        "available", score=score, zone=_zone(score), zone_proximity=proximity,
        applicability=applicability,
        **({"limitations": limitations} if limitations else {}),
        components={name: {"ratio": ratio, "coefficient": COEFFICIENTS[name],
                            "weighted": COEFFICIENTS[name] * ratio,
                            "definition": _DEFINITIONS[name]} for name, ratio in ratios.items()},
        inputs={**{name: dict(entry) for name, entry in present.items()},
                "working_capital": {"value": working_capital,
                                     "derivation": "current_assets - current_liabilities"}},
        period=sample.get("period"), statement_scope=sample.get("statement_scope"),
        currency=sample.get("currency"), unit_scale=sample.get("unit_scale"),
    )


_DEFINITIONS = {
    "X1": "working capital / total assets",
    "X2": "retained earnings / total assets",
    "X3": "EBIT / total assets",
    "X4": "book value of equity / total liabilities",
    "X5": "sales / total assets",
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number
