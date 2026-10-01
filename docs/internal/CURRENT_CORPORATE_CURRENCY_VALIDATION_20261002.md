# Current corporate evidence currency — bounded acquisition

Owner continuation on main `22ce3147e0b373ba8b447e23ba0032bf727db6d5` authorizes sequential implementation, admitted official-route acquisition, retention and ordinary release. Existing R1–R7 evidence is not reopened.

## Shared resource contract

`official_acquisition_budget.py` is a local synchronous transport-boundary resource contract shared by the existing HNX and HOSE builders, including standalone builder/fetch defaults. It is not a crawler or provider abstraction. Default policy: 64 dispatched HTTP requests, 32 MiB downloaded payload, 8 MiB per response, 180 seconds monotonic elapsed time, 30 seconds per blocking request, and 16 pages per surface. No retries or automatic redirects. A route redirect requires explicit requalification rather than hidden HTTP. The elapsed deadline is checked before dispatch, between bounded reads and before successful acquisition; blocking transport has a timeout capped by remaining time. DNS/system transport scheduling is not a hard real-time guarantee.

Byte counting uses raw returned bytes. A one-byte overflow probe distinguishes exact EOF from truncation and is included in downloaded usage; oversized payloads never reach retention. Injected offline fetchers have post-return byte accounting; production built-in transports bound reads themselves. Reports contain ordered surface/URL/page receipts, request ordinal, byte totals, elapsed time and terminal reason. Budget termination is an explicit FAILURE, not source-empty evidence. Completeness-dependent HNX acquisition remains failed; prior successful sessions remain usable. HNX disclosures stay disabled by default.

## Admitted route inventory and one-attempt plan

Authority references: STATE entries “HNX enumerable universe, event, and disclosure scaleout V1” (2026-08-24), “HOSE public XHR and periodic-series reconciliation V1” (2026-08-24), and “OFFICIAL_CORPORATE_EVENT_INCREMENTAL_ACQUISITION_AND_FRESHNESS_V1”; exact source constants remain in the two existing acquisition modules. Current wrapper admission is explicitly confirmed by the owner continuation.

| Class | Surface / role | This attempt |
|---|---|---|
| A admitted | HNX/UPCoM list landing + POST issuer-list bulk; current identity/context denominator | Existing 4 requests; labels remain exchange list/KLLH, never accounting common shares |
| A admitted | HNX/UPCoM rights landing + paginated rights index; official event context | Existing 4 initial requests plus pages; complete totals required; max 16 pages per surface |
| A admitted | HOSE listing dashboard, stock master, index catalog, VN30; universe/reconciliation | Existing 4 requests |
| A admitted | HOSE HPG detail, foreign room, current market, rights; bounded issuer context | Existing 4 requests; no market-wide semantic extrapolation |
| A admitted | HOSE RSS, market/HPG dated disclosure window | Existing 3 requests; disclosure observations remain bounded index rows, not complete filing facts |
| B code present, excluded for this use | HNX financial disclosure traversal | Not consumed by current official event context; disabled; no hundreds-page walk |
| C historical/legacy | Frozen August 24 outputs and prior September sessions | Reused only as retained reference; never overwritten or asserted current |
| D redundant/unnecessary | Re-fetching HNX identical rights/disclosure landing twice with disclosures enabled; historical full disclosure walk | Excluded by existing default |

No new route/provider, issuer attachment crawl, financial-document acquisition, HNX liquidity/bulk-price lane or broker endpoint is admitted by this plan. No source family is closed by this inventory. Exact sibling surfaces already present are assessed by role; absent fresh bodies leave those surfaces unresolved, with a new bounded admitted-route attempt as the reopening gate.

The one foreground acquisition uses a scratch root with copied, hash-checked exact existing universe inputs, the bounded default above and actual Vietnam acquisition date. It never runs Daily or materializes a failed attempt. Raw bodies and the success/failure manifest remain private local evidence; portable findings will record hashes and counters, not copied source bodies. No historical T0 repair, authority promotion or source-registry change.


## Evidence-driven current window

The initial full-index attempt deliberately terminated at the UPCoM rights page cap after nine requests / 3,466,786 downloaded bytes. No HOSE calls or materialization followed. A separate two-request governed probe retained unfiltered and date-filtered first pages on the same admitted UPCoM rights route: unfiltered 3,267 records / 327 pages / ten rows per page despite pNumRecord=1000; September 2–October 2 filtered 107 records / 11 pages. These are empirical observations at retrieval, not a permanent source guarantee. Current scope now has an explicit caller-supplied inclusive ex-date window; date fields are not interpreted as publication or executed lifecycle. Builders validate every returned ex-date against the window and reconcile all declared rows/pages. Out-of-window/missing dates fail the scoped acquisition; no silent local truncation.

The second attempt selects September 2–October 16 (30-day recent event carry plus a two-week upcoming calendar), explicitly a current research event horizon rather than a strategy threshold or complete historical index. It uses a separate scratch root, the same default resource ceilings and no automatic retry. No authority is widened. Existing callers retain full-index semantics unless they explicitly supply a window. The CLI exposes both window dates and an explicit retention root.


## Retained result and consumer correction

The explicit September 2–October 16 window succeeded: 31 HTTP requests, 3,216,925 downloaded bytes, 24.542608 seconds, all 31 raw capture hashes replayed unchanged. The retained official-universe denominator remains 1,507, dated August 24; this is not a freshly qualified whole-market universe. Current event materialization produces 186 observations for 174 names. The existing R4 rules yield 160 available explanatory drivers across 153 names, with 26 blocked observations. They remain non-voting current explanations, not forecasts, valuation assumptions, stronger source authority, historical PIT or executed corporate-action evidence. October 2 evidence is rejected by the driver consumer for October 1.

Live materialization exposed an existing lifecycle error: a passed payment/execution calendar date became EXECUTED; CONFIRMED_RECENT was also projected to EXECUTED and CONFIRMED_UPCOMING to APPROVED. Those calendar statuses now project to ANNOUNCED, while explicit retained EXECUTED source statuses remain supported. Planned/approved actions remain planned irrespective of scheduled dates. Fresh source data now has zero inferred executed lifecycle records (184 ANNOUNCED, two UNKNOWN). No frozen source/decision artifacts are rewritten. The window is retained in bridge/context metadata and HNX event warnings.

Validation: 175 focused hermetic budget/acquisition/consumer/driver/production-smoke tests and three subtests pass; five explicitly declared retained cases are separately accounted. Four existing acquisition tests depended on a private official-universe fixture; one supplemental-CI test depended on three private manifests. These dependencies are now declared in the existing retained tier rather than failing silently in a clean clone. The supplemental fixture is absent in the isolated worktree; no replacement evidence was fabricated. Exact current acquired bytes replay successfully and source universe inputs remain unchanged. No production Daily, source registry, authority registry, broker route, portfolio or policy mutation occurred. Scratch materialization does not claim published/dashboard/live acceptance.

## Next roadmap assessment

Corporate currency now offers useful explanatory coverage through an existing consumer. Read-only call-graph search of canonical_daily_operation, canonical_post_close_pipeline, daily_producer_pipeline, daily_session_level2_package and stocklookup.ps1 finds no call to the incremental corporate acquisition runner: Daily resolves the latest materialized context but does not refresh it. Therefore `CURRENT_CORPORATE_CURRENCY_DAILY_ROLLFORWARD_V1` is selected NEXT, ahead of governed valuation inputs. Reuse this bounded acquisition path at the existing canonical stage, reuse same-session SUCCESS, prevent retroactive/historical T0 repair, and retain non-fatal explicit availability/budget failures with no hidden retry. Add meaningful offline orchestration tests before changing a production default; no Daily is run merely for acceptance.

`GOVERNED_VALUATION_INPUT_COVERAGE_V1` remains an unstarted candidate. Existing intrinsic input mapping requires qualified monetary/share semantics and sourced forecast/rate assumptions; current calendar evidence supplies neither. No new calculators, made-up rates, broad disclosure crawler or automatic R8 is justified by this result. Capability checkpoint `1ae44e84eec1c588d4ef4fda91756da17ed5e044` is retained; roadmap closure and release follow in a separate commit. No external blocker prevents the queued bounded implementation. A natural clean checkpoint follows the tested acquisition/consumer release and safe main synchronization.
