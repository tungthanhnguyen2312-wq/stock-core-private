# VN30 financial and valuation research scaleout V1

Owner-directed milestone `VN30_FINANCIAL_VALUATION_RESEARCH_SCALEOUT_V1` starts at
PR146 merge `a9c799397a74641a0e16c8ea84454d2dc4d0745b`. The genuine Codex coordinator
closed the predecessor at revision96 after verifying run38512024681 (five successful
jobs); this single lane was admitted/activated at revisions97/98. No successor.

## Numerical owner and compatible publication

`canonical_daily_financial_v2_materialization.build_evaluated_valuation_artifact`
accepts `include_metric_research=True`. The default is false: existing Daily callers,
valuation records, thresholds and artifact identities keep their original behavior.
This is a separately versioned, opt-in `metric_research_context` member with contract
`financial_valuation_metric_research/v1` and its own content identity. Enabling it
changes the enclosing artifact's content identity; it does not change old records.
Consumer/Dashboard can copy the member and its Producer values without calculation.
No existing delivery schema, frozen pin or sealed session is amended. Source-boundary
compatibility is tested; renderer/delivery activation is a later release dependency.
No Dashboard notable_cards, scores, recommendations or execution claims are added.

The projection includes P/E, P/E TTM, exact/research P/B, P/S, P/S TTM, both existing
EV/EBITDA identities, the H1 unlocked methods, average-boundary and ending-balance
ROE/ROA, and the existing restricted cross-provider ROA proxy. Original method objects
and Financial V2 feature objects are retained exactly as lineage. Price/share inputs
are carried independently; absent timestamps, currency, scale and scope remain absent.
Fitness is `READY`, `RESEARCH_PROXY`, `STALE_BUT_RESEARCH_USABLE`,
`BLOCKED_BY_EVIDENCE` or `NOT_APPLICABLE`; original Producer fitness/status remains
separate. Explicit ends and existing quarter labels use the standing four-quarter
freshness window. Unresolved fiscal/annual labels are not silently dated. Future periods
fail closed. Stale usable values retain their original method and source fitness.

The new `ROE_REPORTED_PERIOD_END_EQUITY_PROXY` reuses Financial V2's sole ratio owner.
Its two operands are the already-admitted official denominators from the H1 financial
unlock contract. Admission, exact-source proof and latest-period conflict handling
remain there. Both operands must be from the same retained filing, VND/base units,
explicit consolidated scope and one knowledge cutoff. A duration's explicit end
must equal the equity instant. Positive ending equity is mandatory; negative income
remains a signed descriptive return. Missing shares/price cannot block this return.
Total net income and total equity include NCI as reported. No parent-profit alias,
opening balance, annualization or TTM is invented. Banks/securities need specialist
identities and cannot use this corporate method.

Existing peer owners supply medians/counts/percentiles only within their compatible
method groups. Reported ROE additionally partitions by explicit duration/instant basis,
scope and total-income/total-equity definition. The existing minimum 5 remains.
Existing valuation peer verdicts retain their upstream full-universe scope; the new
reported ROE peer verdict uses the supplied retained cohort.
Unknown-scale cross-provider ROA stays a restricted research proxy, never a peer input,
newly qualified evidence, READY denominator or voting signal.

## Retained acceptance

The read-only replay tool validates the retained HOSE membership artifact and raw
capture hashes, the full evaluated valuation content digest, the raw valuation digest
and the selected Financial V2 engine identity. It uses all30 members observed on
August24,2026. Effective membership intervals and exact October13 membership remain
UNKNOWN; this is an explicitly labelled retained cohort, not a fabricated cutoff list.
Before/after matrices use the same sources, denominator, methods and fitness criteria.
The baseline is an owner-method inventory, not a rewritten historical publication.

On October13 retained inputs: P/E2, P/S2, P/B2, research P/B28 and each of the three
H1 valuation methods1 remain unchanged. P/E TTM, P/S TTM and both EV/EBITDA methods
remain 0. Average and same-provider EOP ROE/ROA remain 0. Fourteen existing mixed-provider
ROA proxies stay restricted (unresolved scale), unchanged. One new VRE H1 ROE proxy
is computable: `0.06519456751279788` (6.519% for the reported H1 duration), using net
income3,214,786,000,000 / ending equity49,310,673,000,000 VND. Its single compatible
peer is below minimum 5. Existing full-universe peer verdicts are unchanged: 16
qualified peer values in this subset (P/B 1, research P/B 14, P/S 1). The new reported
ROE method obtains no qualified peer distribution within the retained cohort.
No qualified source evidence is added and strict-share/exact valuation authority is
unchanged. Other gaps are retained TTM continuity/monetary basis, current common-share
continuity, compatible exact EV/EBITDA, same-provider opening/ending balances and
sector identities. Missing ROA assets are not manufactured.

Acceptance tests cover numerical/source parity, co-filing/period/scope/unit joins,
missing shares, signed income/nonpositive equity, stale/future inputs, specialist
applicability, deterministic identity and default/opt-in publication compatibility.
Replay writes matrices and evidence only to a separate explicit output directory.
No production Daily, database write, source promotion, push, merge, deploy or publication.
