# Reviewed interim earnings and cash research V1

Owner scope: [contract](../reviewed_interim_earnings_and_cash_research_v1_contract.md).
Stacked on open PR182 `effc9b8ab8c55429e4c758ab57d475d65b641b8b`; not a main release.
[Machine results](REVIEWED_INTERIM_EARNINGS_CASH_V1_ACCEPTANCE.json).

## What changed

`stocklookup_core/financial/interim_earnings_cash_research.py` adds one non-voting
`interim_earnings_cash_research_context` beside the official income context. It shares
the extracted `official_research_row_reasons` gate (D-1, tier, entity, issuer, unit,
cutoff; income behavior unchanged) and reaches the same surfaces: the market-wide
fundamental record, product summary, AI primary/owner-focus cards, cockpit ticker and
decision cards and the full-universe companion (`earnings_cash`).

Methods are labelled: operating cash flow over profit after tax inside one statement set
(document, explicit bounds, scope, currency, comparative basis), ratio only over positive
profit; matched prior-year comparisons with issuer cautions; profit/cash co-movement and
conversion change only on the same matched pair. Exceptional lines are the explicitly
qualified ones; share basis, operating profit and working capital stay UNKNOWN, so a
reported profit increase is labelled economics-unresolved. Cash balance is never free cash
flow or net cash. Financial/unresolved entities: NOT_APPLICABLE.

`config/interim_earnings_cash_issuer_gates_v1.json` is closed and amount-free: VNM
reclassified comparatives and tax/dividend timing lines; FPT FTEL full-to-equity scope
change (income like-for-like basis only; cash-flow comparative not restated), deconsolidated
cash on investing line 26b, unreviewed 9M release; QNS TT43 codes 320/321 and no
qualified net-cash definition. Plus exact qualification blockers and Owner decisions.

## Qualification result

The existing ingress (existing options, no write) on SHA-verified retained VNM/QNS bytes
qualifies zero new rows; modern admission refuses even the retained VNM cash and QNS
equity re-derivations (CMS host not admitted, ticker literal absent, OCR value spans).
FPT H1 is not retained; issuer bytes were verified in isolated scratch only. The governed
OCR profile reads every GrokBot amount literally, so the candidates are corroborated but
not qualified. No overlay row, route, OCR or qualifier change.

## Real outputs

Retained October20/22 (523 records each, read-only, hashes identical before/after):
447 UNKNOWN, 71 NOT_APPLICABLE, 4 partial, 1 measured. VRE H1: OCF 1,555,752,000,000 vs
profit 3,214,788,000,000, ratio 0.48, investment-property gain 5.7% of profit, recurrence
UNKNOWN. PNJ: FY2025 OCF and H1 profit are different periods, conversion refused.
VNM/QNS UNKNOWN, FPT partial, each with exact blockers and cautions. Every bundle card
is unchanged apart from the additive context; decision projections unchanged on all 139
fixture cards.

Isolated candidate preview (not consumer data): VNM profit +38.4% vs OCF −9.1% on
reclassified comparatives, conversion 0.94→0.62; FPT like-for-like revenue +12.6%, parent
+14.1%, positive profit with negative OCF, reported-basis and OCF comparisons refused; QNS
profit +2.1%, OCF +29.1%, conversion 0.38→0.48, no net cash.

## Validation and gates

40 new tests; official income, delivery and transition suites pass. A broad 4,000-test
selection has 198 failing ids, identical on the untouched base (missing retained host
data); none introduced. Hosted CI governs the PR head. Remaining gates: VNM CMS host,
multi-column image binding, TT43 code map, issuer-name literal binding, FPT acquisition and
like-for-like contract. Authority NONE; production writes zero; no Daily, merge or successor.
