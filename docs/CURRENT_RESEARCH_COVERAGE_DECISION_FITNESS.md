# Current Research Coverage & Decision Fitness V1

Status: IMPLEMENTED / PR CANDIDATE

Date: 2026-10-01

## Purpose

This capability answers one bounded question:

> Across the attempted Current Research cohort, which dimensions are usable, partial, blocked, non-applicable, or proxy — and which explicit reason codes account for the gaps?

It does not recompute market, technical, financial, valuation, corporate, liquidity, portfolio, or action-posture logic.

## Source contract

The source of truth is the already-existing current_research_decision_input/v1 attached to each integrated_investment_decision_product/v1 record.

That source already owns these dimensions:

- MARKET
- TECHNICAL
- FUNDAMENTAL
- VALUATION
- CORPORATE
- LIQUIDITY

and their existing states: AVAILABLE, PARTIAL, BLOCKED, NON_APPLICABLE.

R2 adds no second semantic ladder for those dimensions.

## Decision-fitness read model

R2 exposes a deliberately small coverage vocabulary:

- FULL_MULTI_FACTOR_CURRENT_RESEARCH
- PARTIAL_MULTI_FACTOR_CURRENT_RESEARCH
- LIMITED_SINGLE_LANE_CURRENT_RESEARCH
- BLOCKED_CURRENT_RESEARCH
- OUTSIDE_CURRENT_RESEARCH_SCOPE

The mapping is a read model over the existing evidence class. It is not a score or recommendation.

An explicit action_posture_gated_by_current_evidence=true remains blocked even if other research dimensions exist.

## Market-wide output

The deterministic artifact reports:

- denominator count;
- decision-fitness distribution;
- research-usable / blocked / outside-scope counts;
- evidence-class distribution;
- per-dimension state distributions;
- per-dimension authority distributions;
- AVAILABLE counts;
- research-proxy counts;
- research-action-posture distribution;
- current-evidence gate count;
- primary-factor gap combinations;
- gap reason-code prevalence;
- non-applicable reason-code prevalence.

Gap prevalence is descriptive count data. It is explicitly not a roadmap priority score.

## Authority boundary

This capability does not change research_action_posture or any ticker decision; does not promote dimension authority; does not create PIT or execution authority; does not create probability, target price, ranking, or score; does not write a production database; and does not acquire provider data.

Missing higher authority remains local to the dependent use.

## Implementation

Reusable logic is added to current_research_decision_input.py rather than adding a new root-level Python module.

CLI:

python tools/build_current_research_decision_fitness.py --input <integrated-decision.json> --output <decision-fitness.json>

The CLI performs no network access and writes the output atomically through a temporary sibling file.

## Validation

Focused tests cover state and gap aggregation, current-evidence gating, order-independent deterministic identity, read-only authority boundaries, and contract rejection.

The test is part of the Producer CI focused selection.
