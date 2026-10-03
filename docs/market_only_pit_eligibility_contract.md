# Market-only PIT eligibility and gross research replay

Release C adds `MARKET_ONLY_PIT_ELIGIBILITY_V1` as a signal-input contract, independent
of full Integrated Decision economics. Each result binds signal, ticker, exchange,
sessions, cutoff, source receipt identities, basis and required uses. It never grants
a global ticker-ready boolean or requires unrelated financial/valuation/narrative inputs.

The existing VNM confirmation reads `above_sma50` through the existing technical
ranking and bull-confirmation path. Its market gate therefore requires 50 compatible
daily closes, explicit active membership and CA comparability. Its signal does not
have a volume threshold; the existing next-session gross replay primitives separately
require qualified positive shares volume. VNM remains the engine's ticker scope.
Other strategies must declare their own dependencies. Relative-strength-like consumers
must supply an eligible benchmark aligned to the exact window and cutoff.

Version selection uses only information actually known by the supplied cutoff. Future
provider corrections cannot repair or alter the earlier selected window. Snapshot
identity, original receipt/known-time equality, finite OHLC, closed capture, source,
exchange and basis are checked. A raw window requires proof of no applicable CA;
an adjusted window requires the existing qualified chain and raw lineage. Missing
coverage is not proof that no CA occurred. Retrospective adjustments cannot enter PIT.
Source-effective membership covering the requested window is required; today's surviving
ticker list does not establish it. Calendar validity comes from the existing explicit
governed session ledger, never weekday arithmetic or an observed price-file list.

Exclusions include `PRICE_NOT_PIT_ELIGIBLE`, `VOLUME_NOT_PIT_ELIGIBLE`,
`ACTIVE_UNIVERSE_UNKNOWN`, `CA_FACTOR_REQUIRED_UNAVAILABLE`,
`KNOWLEDGE_CUTOFF_VIOLATION`, `LOOKBACK_WINDOW_INSUFFICIENT`,
`BASIS_INCOMPATIBLE` and `BENCHMARK_NOT_ELIGIBLE`. Missing governed sessions and
unsupported signal ticker scope are separately reported. D/W/M aggregate lineage
cannot exceed constituent fitness, mix instruments/bases, omit expected sessions or
consume future constituents. The guard creates no new technical or candle engine.

`vnm_shadow_backtest.run_market_only_gross_replay` extends the existing isolated
engine and return primitive. It requires the real T0 signal/feature lineage, separately
qualified future observations and bound gate identities. It computes explicit
close-to-close gross research outcomes. It does not invent fills, fees, slippage or
net/execution results. Synthetic tests demonstrate wiring only; they are not source
evidence, trading outcomes or alpha claims.

## Actual retained result

[Acceptance](internal/MARKET_PIT_RELEASE_C_ACCEPTANCE.json) verifies the exact R7 input
hashes: 18,514 prospective DNSE receipts, 8,740 independent HOSE receipt rows and 2,578
later Daily receipts. The market corpus has 21,092 receipt versions /20,149 distinct
ticker-session pairs /1,334 tickers /24 sessions, August 24–October 1. Qualified volume
receipts are zero. The 6,026 legacy cross-source RAW bars retain their original scoped
HOSE authority; their legacy instrument exchange field remains unknown and is not
repaired from today's universe. All 21,092 market receipt instrument fields are unknown.

Both signal-input and gross-replay input regions are empty: earliest/latest null,
zero eligible sessions/tickers/ticker-session pairs/exchanges. The VNM engine has
23 observed candidate sessions; the other 20,126 pairs are outside its ticker scope.
The actual governed calendar ends September 4; 15,568 pairs are beyond that scope.
All 20,149 pairs fail active membership, CA comparability, price fitness and lookback.
Gross inputs additionally fail volume fitness; 8,945 have knowledge-time exclusions.
No representative replay was run. Receipt-time feasibility cutoffs are actual source
receipt times, not invented emitted decision or signal times.

The old Release B universe projection has 1,701 rows, only 405 with identified source
rows and known timestamps; unknown times remain unknown. An additive continuity fix
retains the separately observed listing rows from Release A's exact verified source
acquisition, using its existing HNX bridge and universe row semantics. All 1,522 new
HNX/HOSE listing observations retain actual October 2 source receipt times. They do
not repair the old rows, establish active-time membership, widen the product denominator
or enter the earlier eligible-window scan. All 31 source captures remain unchanged.

Strategic closure and promotion gates: [14-capability dossier](internal/MARKET_PIT_FEASIBILITY_DOSSIER_20261002.md).

## October 3 prospective completeness successor

[Capture completeness V1](prospective_pit_capture_completeness_contract.md) starts a
new clock only with the first successful complete future Daily capture. Time alone
does not make any of the old incomplete receipts eligible. Additive companions,
same-session positive listing and source-native invariant component requirements
remain separate from effective ACTIVE membership and the standing VNM SMA50
RAW/volume/CA signal contract. Old cohort outputs and exclusions remain exact;
future cohorts use the shared contiguous governed capture chain. No signal
evaluation or RAW/backtest/execution promotion follows from readiness.
