# KBS quarterly income period alignment corrective V1 — contract

Milestone `KBS_QUARTERLY_INCOME_PERIOD_ALIGNMENT_CORRECTIVE_V1`. It was admitted on 2026-10-19 under the
Owner directive to restore trustworthy multi-period profit data while staying independent of the
10-19 Daily. It is built on the PR167 head (`3e905aba`). It is a development-only corrective. There
are no Daily, T:, provider, evidence, re-acquisition or merge actions.

## Finding (retained evidence only)

In the retained KBS KQKD quarterly income payloads, some period heads repeat. Retained raw
responses show two or three `Quarter 4 / 2025` heads with identical PeriodBegin, PeriodEnd and
ReportDate. Their value slots also repeat other columns. The canonical layer already flags the
duplicated column as `restated_period_column_disagrees`. The official anchors below show that the
**other columns of the same payload are mislabelled too**.

The anchors were read from retained official PDFs as diagnostic page reads. They were not promoted
as facts. Amounts are net revenue, in billions of VND.

| Issuer | Official anchor | Retained KBS label → value | Conclusion |
|---|---|---|---|
| HPG | Audited FY2025 = 156,116.09 (annual report p.8) | 2026-Q1 46,176.5; 2025-Q4_1 37,621.7; 2025-Q4 36,407.4; 2025-Q3 35,910.5 → sum 156,116.09 (518 VND rounding) | The four columns are FY2025's four quarters |
| HPG | Q2/2026 report p.5: Q2/25 35,910.5; H1/25 − Q2/25 = Q1/25 37,621.7; Q1/26 = 52,900.8 | "2025-Q3" = 35,910.5; "2025-Q4_1" = 37,621.7; "2026-Q1" = 46,176.5 | The labels are wrong; "2026-Q1" is not Q1/2026 |
| NVL | Q2/2026 report (text): Q1/25 1,778.18; Q1/26 3,586.66 | "2025-Q4_1" = 1,778.18; "2026-Q1" = 1,567.44 | Same pattern |
| PVD | Q2/2026 report p.5: Q2/25 2,430.06; Q1/26 3,409.53 | "2025-Q3" = 2,430.06; "2026-Q1" = 4,312.95 | Same pattern |

There are 1,114 of 1,406 retained KBS income payloads (1,114 issuers) with a repeated head. The
dominant signatures are `2026-Q1, 2025-Q4_1, 2025-Q4, 2025-Q3` (909 issuers) and
`2026-Q2, 2026-Q1, 2025-Q4_1, 2025-Q4` (195).

Before this corrective, the standalone flows of these payloads entered margins, QoQ, YoY and TTM
under wrong period labels. For example, a Q4/2025 margin was presented as 2026-Q1 and paired with a
real 2026-Q1 VCI balance sheet.

## Rule

`financial_flow_semantics_ttm_bridge.gate_kbs_period_alignment` runs at the single semantic-row
loader (`canonical_daily_financial_v2_materialization.load_semantic_rows`).

- Every STANDALONE_QUARTER row from a repeated-head KBS income payload becomes UNKNOWN_DURATION,
  with `KBS_DUPLICATE_PERIOD_HEAD_ALIGNMENT_UNVERIFIED`. The original states are kept in
  `period_alignment_gate`. Values and provenance are unchanged, and retained files are never rewritten.
- For those issuers the Financial V2 scaleout does not fall back to the feature store for the
  flow-derived features: net_income_sign, net_margin, cfo_to_net_income, ROA proxy and ROE proxy.
  The store was built from the same labels.
- Other providers, balance-sheet facts and KBS payloads without repeated heads are untouched.
  KBS operating cash flow is left out of scope: its resolver already requires agreement with the
  independent VCI balance-sheet end cash. That is a residual risk, recorded here.

The gate removes 18,869 standalone flow rows: 3,183 revenue, 3,188 gross profit, 3,342 each of
PBT, net income and attributable net income, and 2,472 interest expense. 292 payloads keep their
standalone flows. Expect lower READY counts for current net and PBT margins, P/E and ROE, for
those issuers. That loss is intended: the gate fails closed on demonstrably wrong periods.

## Recovery path (Owner-gated)

A relabel inferred from three anchors is not admitted, even though the HPG mapping is exact
(label 2026-Q1 → Q4/25, 2025-Q4_1 → Q1/25, 2025-Q4 → Q3/25, 2025-Q3 → Q2/25). It would need either:

1. A fresh KBS acquisition that retains raw heads (the lookback retention contract), with
   per-payload head/value verification. This is a provider and evidence write.
2. Official quarterly anchors per issuer.

Both need Owner authorization. The 10-19 Daily runs on released code without this corrective.

Validation: the full CI hermetic selection passes locally (277 files), the new gate tests pass,
and the module-scoped failure set is identical to the PR167 head.
