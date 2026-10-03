# Market PIT foundation and ordinary Daily continuity

Release B extends the existing prospective snapshot contract. Ordinary Daily retains
immutable market receipt versions immediately after exact-session validation and before
corporate, fundamental, valuation or Integrated Decision work. Each component reports
its own failure. No additional entrypoint, scheduled job or manual future build is needed.

The acquisition result and final Daily operation carry `prospective_market_evidence`.
The Integrated Decision builder no longer writes the old shared session manifest.
Existing archived manifests remain untouched. New receipts and manifests live under
`operations-review/prospective-market-evidence-v1/<session>/` in the explicit output root.
Receipt identity binds instrument/source/session/original retrieval time. Same bytes
reuse; different bytes at that receipt fail closed. Later observations reference the
previous known-time version and preserve both price and volume revision information.
Neither reruns nor future provider corrections replace T0 or invent an earlier timestamp.

Canonical retained observation JSON and exact provider HTTP body hashes have different
hash kinds. Daily hashes the complete retained observation and never relabels it as raw
provider bytes. Ticker, exchange, board, qualified instrument identity, price, volume,
reported traded value/unit, finality and basis are retained; absent semantics remain unknown.
Closed-session observation is not proof of provider finality. Price and volume fitness
are independent. Shares/lots/value/other units remain as reported, with no inferred scale
or lot normalization. Unknown volume units have no qualified volume-dependent use.

New independent RAW comparisons require exactly four finite numeric OHLC values,
exact ticker/session and HOSE exchange, the admitted independent HOSE tradingresult
source, an identified receipt available by the compared receipt time, explicit matching
price units, and no adjusted contradiction. Bare arrays, malformed values, future
comparisons and HNX/UPCoM rows cannot qualify. This hardening does not recompute or
widen the retained **6,026 cross-source HOSE bars**. DNSE-only observations remain
as-known. RAW morphology, gaps and actual event reaction do not establish comparability
across corporate actions. `RAW_AS_TRADED`, `PIT_CA_ADJUSTED` and
`RETROSPECTIVE_ADJUSTED` remain distinct modes; a future qualified continuous chain must
keep raw lineage. No factor is inferred from a price move.

The explicit selected official universe reuses its existing contract verifier and
evidence retainer. Every source row keeps its status, exchange/board fields and exact
observation time. Current presence never establishes `ACTIVE_UNIVERSE_AT_TIME` or
historical membership; current 1,683-name product scope is not backfilled into history.
Selected Release A corporate context is retained with all source observations,
publication/observation times, explicit dates, terms, corrections and version identities.
Missing stable source event IDs stay missing. Index source-record identity is not promoted
to a stable lifecycle identity. Calendar execution/payment dates do not prove execution.
The existing official-document ledger and `build_factor_chain_entry` own factors.
Index evidence cannot create ledger terms; missing terms/publication/executed lifecycle
keeps factor qualification unavailable. There is no second factor framework.

## Retained acceptance and historical closure

[Exact-input offline acceptance](internal/MARKET_PIT_RELEASE_B_ACCEPTANCE.json) retains
852 October 1 price/volume observations without changing source bytes. All price
receipts are prospective as-known; their volume units are unknown. The selected universe
has 1,701 retained projection rows (including official-only/unresolved records), zero active-time
qualifications. The October 2 corporate context has 188 rows including two excluded
observations, zero qualified factors. These are different scopes from the 174-name/186-row
current candidate corporate overlay. Retained tests ran under socket/HTTP/provider guards.
This validates infrastructure, not a fabricated new live trading session.

Release C distinguishes the projection denominator from actual known-time source
observations: only 405 of those old rows have identified source rows and timestamps.
It separately retains 1,522 newly observed HNX/HOSE listing rows from A's exact verified
acquisition, with original source receipt times and no historical backfill or active
membership inference. [Release C contract](market_only_pit_eligibility_contract.md).

Existing bounded source-route evidence closes HOSE historical prices as
`EMPIRICALLY_UNADJUSTED_SCOPED / SOURCE_BASIS_UNDOCUMENTED`.
HNX/UPCoM historical bulk series remain `ENGINEERING_READY /
EXTERNAL_DATA_RIGHTS_REQUIRED`; admitted current listing/event routes do not grant bulk
history rights. No new crawl, commercial provider, adjustment or source promotion occurs.
The existing [authority findings](prospective_raw_pit_authority.md) and
[R7 input manifest](internal/R7_RETAINED_INPUT_MANIFEST.json) remain the source baseline.

October 3 successor: [prospective capture completeness](prospective_pit_capture_completeness_contract.md)
adds immutable companion/listing/calendar/readiness records for future complete
captures. Old incomplete receipts remain incomplete regardless of elapsed time.
Stable native scale supports only separately qualified same-series invariant uses;
it establishes neither economic units, effective ACTIVE membership nor global RAW.
