# Thesis-based opportunity discovery V1 — contract

Milestone `THESIS_BASED_OPPORTUNITY_DISCOVERY_V1`, admitted 2026-10-18 under the Owner's autonomous
roadmap directive to Claude Code. It starts from `74a7d76b`: the completed
[integrated opportunity comparison](integrated_investment_opportunity_comparison_v1_contract.md)
merged with origin/main `9fefb535` (R1/S1). Local only.

## Product

The comparison answers "how do these 2–5 names compare". Discovery answers "which names are worth
comparing". It covers the whole Integrated Decision universe and computes the same per-security
findings as the comparison. Those findings are built only from the existing valuation, multi-period,
sector-relative, timing, scenario and liquidity owners. Each security is then placed in evidence-pattern
research lanes. A lane is a conjunction of existing finding codes, and one security may sit in several lanes.

| Lane | Rule (existing finding codes) |
|---|---|
| QUALIFIED_ENTRY_WITH_FINANCIAL_SUPPORT | The qualified entry also has recovery, successive improvement or resilience against weak peers |
| QUALIFIED_ENTRY_WITHOUT_FINANCIAL_CONFIRMATION | Qualified entry where financial research neither confirms it nor shows weakness, or is unavailable |
| QUALIFIED_ENTRY_WITH_FINANCIAL_COUNTEREVIDENCE | Qualified entry contradicted by persistent deterioration or company-specific weakness |
| DISCOUNT_WITH_RESILIENCE_AWAITING_STRUCTURE | Sector-relative P/B discount with a resilience counter-thesis and no observed adverse structure |
| DISCOUNT_WITH_RESILIENCE_UNDER_ADVERSE_STRUCTURE | The same discount and resilience, while the strategy owner currently observes adverse structure |
| DISCOUNT_WITH_FINANCIAL_DETERIORATION | Discount with repeated or company-specific weakness: a value-trap investigation list |
| FINANCIAL_STRENGTH_AWAITING_CONFIRMATION | Recovery or resilience without a qualified entry and without adverse structure |
| SHARED_SECTOR_FINANCIAL_STRESS | Adverse changes shared with the retained compatible sector sample |

Lane members are ordered by the existing `opportunity_priority.research_priority_tier` authority
(PRIORITY_NOW, then SETUP_WATCH, MONITOR, DATA_LIMITED), and then by ticker. Lists are complete;
the Markdown shows 12 names per lane and points to the JSON for the rest. There is no score,
ranking, threshold, target, probability, sizing or policy change. Owner research exclusions are
counted, never listed. `artifact_identity` is a content hash and is re-verified before any
Markdown or AI delivery.

The comparison also gains **cross-sector relative-position axes**. When two securities do not
share a qualified P/B basis, each one's existing tie-aware percentile is shown inside its own
qualified peer cohort (`research_pb_own_sector_position`). Each one's existing sector-relative
change assessment for cash/assets and the debt ratios is also shown. Levels are never compared
across cohorts. The comparability label is `RELATIVE_POSITION_ONLY`.

## Delivery (opt-in; defaults unchanged)

- **Action Center:** `python stocklookup.py action-center --thesis-discovery` produces
  `thesis_opportunity_discovery` and a Markdown section. It combines with `--compare`. The console
  shows lane counts only.
- **AI delivery:** `build_delivery(..., include_thesis_discovery=True)` adds the same discovery to
  the primary bundle.

The Daily pipeline does not change. The `stocklookup.py` launcher AST hash and the CI test list
were updated for the opt-in flag and the new test.

## Retained acceptance (2026-10-16, isolated, read-only)

The run used the same full-source research Integrated Decision as the comparison acceptance.
Retained inputs hashed unchanged. The denominator is 1,683 issuers: 332 have qualified valuation and
financial research, and 897 have current-session timing.

| Lane | Count | Members (inspection order) |
|---|---:|---|
| Qualified entry with financial support | 1 | DBC |
| Qualified entry without financial confirmation | 24 | ACV, CDC, CSV, DPG, IDI… |
| Qualified entry with financial counterevidence | 2 | TEG, NVL |
| Discount with resilience awaiting structure | 1 | PMG |
| Discount with resilience under adverse structure | 5 | CLX, DL1, PAN, SRF, VLC |
| Discount with financial deterioration | 8 | NDX, DGT, DXS, ITC, NO1, PTL, SCR, VPH |
| Financial strength awaiting confirmation | 14 | ANT, GLT, HAG, HHV, KSV… |
| Shared sector financial stress | 51 | (sector investigation list) |

One correction was made during acceptance. A first draft labelled every qualified entry without
counterevidence as "financial support" (25 names). Only 1 actually has qualified recovery or
resilience, so the lane was split.

Comparison pairs with comparable evidence rose from 1 of 18 (same-sector level axes only) to 13 of 18.
The 12 new ones are own-cohort position pairs. The 5 remaining independent pairs involve PNJ (no
qualified research) or VCB (bank; corporate rules not applicable).

The 2026-10-16 acceptance used these real comparison groups: DL1/ITC/NO1, PAN/AAA,
HPG/FPT/PNJ/VNM/MWG, VCB/HPG and DL1/PAN/HPG. Each was checked through the packet, Action Center,
AI projection and Markdown.

Native local checkpoint `53b4a21c385950a8f0a5e4d3f7d8acd0999c8a77`
(`LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED`).

## Known limits

- Profitability lanes are absent because margin trajectories are UNKNOWN upstream. The retained
  KBS quarterly payloads repeat Q4 heads with identical period bounds, and their value slots
  duplicate other columns. The canonical layer correctly flags 2025-Q4 revenue and net income as
  `restated_period_column_disagrees` for about 1,040–1,100 issuers, which breaks every Q3→Q4→Q1 run.
  Resolving this needs provider-structure forensics or re-acquisition. Evidence:
  `operations-review/kbs-quarterly-financial-lookback-and-semantic-retention-v1-20260828/raw/`.
- Live use needs the stacked financial-research lineage released into Daily. Push, merge and
  release stay behind Owner gates.
