# Freshness and History Contract

Every additive `freshness` envelope has `generated_at`, `as_of_date`, `source`,
`freshness_status`, `expected_update_frequency`, `stale_reason`, and
`is_actionable`. Status is exactly `current`, `expiring`, `stale`, `missing`,
`historical`, or `unknown`. `generated_at` is a documented source generation or
retrieval timestamp; filesystem time is never evidence.

Freshness describes age, completeness describes coverage, and actionability is a
separate conservative decision. Missing/malformed timestamps, incomplete
coverage, unknown provenance, or a stale dependency are never current or
actionable. Evaluation receives an explicit ISO reference timestamp and uses the
latest completed weekday trading session for market domains (weekends stay
current when the Friday session is latest); a holiday calendar can be injected by
the caller when available.

Daily prices/breadth, technical/candlestick outputs, and AI reports use their
market-data timestamp. Technical and AI outputs inherit a non-current dependency.
Macro uses daily, weekly, monthly, or quarterly cadence inferred from its series
metadata. Quarterly financials are normally `historical`, not stale: their period
is evidence, while an absent/unverified latest filing is fail-closed. The
vnstock metadata snapshot (external pe/pb/roe/market_cap/shares_outstanding/
free_float/foreign_room, refreshed on the same quarterly cadence) is the
opposite case: it is a live-current snapshot, not reporting-period evidence, so
it uses the same 92-day/35-day cadence and grace as quarterly macro and genuinely
becomes `stale` — never `historical` — once unrefreshed past that window.
Corporate
profile, ownership, subsidiaries, and qualified shareholder snapshots retain
their existing completeness/comparability gates and are actionable only when a
complete available snapshot is current. Corporate Events are forward
observations: `partial_unqualified_50_row_cap` never represents complete history,
coverage, lifecycle, or actionability, even when retrieval is recent.

Examples: Friday daily prices evaluated Sunday are `current`; a monthly macro
series inside its cadence/grace is `current`; a valid older financial quarter is
`historical`; a snapshot with no source date is `missing`; an event observation
with the 50-row cap can be fresh but is not actionable. Null source values remain
null; numeric zero remains zero.
