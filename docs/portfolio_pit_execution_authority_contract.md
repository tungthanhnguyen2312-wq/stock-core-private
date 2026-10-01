# Portfolio / PIT / execution capability and readiness

R7 implements `portfolio_pit_execution_authority_readiness/v1`. Capability completion
does not promote authority. The source registries, historical promotion evaluator,
liquidity semantics, decision policy and execution prohibitions are unchanged.

## Producer to consumer path

`daily_producer_pipeline` retains the exact-session price snapshot;
`daily_session_level2_package.session_artifact_paths` binds that snapshot, descriptive
liquidity, optional same-session official liquidity, strategy boundaries and the
prospective receipt manifest. The Integrated Decision builder consumes those products
and builds Current Research dimensions. Its final copy-only R7 adapter attaches
`portfolio_context.authority_readiness` and a reference on the existing
`evidence_axes.PORTFOLIO_FIT` axis. Neither field enters the action policy or decision
identity. The existing product content hash includes these additive fields.

The optional private portfolio path already joins explicit holdings, price, governed
policy, risk denominator and `execution_capacity_research.build_envelope`. R7's strict
`portfolio_aware_decision.governed_research_sizing` reuses its risk-budget and minimum-cap
functions without calling the default policy resolver. Exposure aggregation reuses
`current_portfolio_risk_envelope.build`. Descriptive window/volatility readiness reuses
`current_portfolio_risk_research`'s existing basis, full-window and numerical guards.
The existing isolated `vnm_shadow_backtest` and `vnm_execution_contract` supply the
signal, next qualified session, fixed holding exit and round-trip return method.

## One feature/use/scope matrix

`raw_pit_authority_matrix.authority_row` preserves source status, original fitness,
source/basis identities, temporal semantics, known time, cutoff, authority tier,
warnings, blockers and promotion status. Its lens distinguishes `RESEARCH_USABLE`,
`PIT_USABLE`, `EXECUTION_USABLE`, `BLOCKED_BY_EVIDENCE`, `NOT_APPLICABLE` and
`UNKNOWN_SEMANTICS`. An absent binding stays unknown at the feature level and blocks
only dependent calculations. A partial research input remains partial in source
fitness; it does not satisfy a stronger prerequisite requiring ELIGIBLE.

Eight use cases remain separate: CURRENT_RESEARCH, PORTFOLIO_RISK_RESEARCH,
POSITION_SIZING_RESEARCH, HISTORICAL_PIT_ANALYSIS, BACKTEST, EXECUTION_REPLAY,
LIVE_POSITION_SIZING and LIVE_EXECUTION. CURRENT_RESEARCH aggregate readiness in the
acceptance report concerns the joint current price/volume calculation only. It is
not global ticker fitness, opportunity rejection or an action posture.

Each row is bound to its feature, ticker and session. Retained retrospective window
rows additionally enumerate their exact `session_scope`; the stronger use is denied
for every session in that scope, without filling missing historical knowledge.
Consumers may narrow upstream fitness; status/identity alone cannot grant a use.
The matrix never calls the older promotion evaluator or writes an authority registry.

Historical calculation requires qualified raw price, CA timing/factor lineage,
historical knowledge and universe/listing facts. Offset-aware timestamps must prove
knowledge by the supplied decision cutoff. Current shares/listing facts and later
provider basis verdicts cannot become historical inputs. Ex-date cannot be inferred
from record date, and planned shares cannot become execution evidence. An explicit
prospective observation cannot be relabelled backtest evidence. ADTV requires VND
value; ADV requires share volume; non-normalized volume cannot satisfy a normalized
liquidity feature.

## Sizing and portfolio research

The strict sizing adapter requires explicit input/policy identities, qualified
research price identity, comparable monetary units, capital, risk fraction and a
positive long invalidation distance with deterministic boundary identity. It uses
the existing risk calculation and minimum of qualified caps. Missing risk input
cannot fall through to a liquidity-only quantity. Missing concentration/liquidity
caps leave theoretical research size partial. No stop, capital, cash, risk percentage,
position/sector cap, participation, margin, cost or slippage default is introduced.
`THEORETICAL_RISK_SIZE_RESEARCH` remains distinct from `EXECUTION_ELIGIBLE_SIZE`;
the latter is unavailable because the existing size contract grants no execution
quantity. A stronger owner-authorized contract is the exact reopen gate.

Explicit portfolio aggregation accepts comparable long market values with source
identity, rejects duplicate tickers and mixed value/weight semantics, and reuses the
existing concentration engine. Capital usage, cash fraction and gross/net exposure
depend on explicit capital/cash. Sector concentration requires supplied sector
identities. Cash usage without a proposed trade/ledger, covariance-dependent portfolio
risk without qualified common windows/holdings, and optimization without a governed
objective remain unavailable. Candidate volatility is descriptive; correlation is
descriptive, not causal. No expected returns or efficient frontier are emitted.

Canonical Current Research does not bind account capital/holdings. Its public
readiness context exposes this absence and retains current source dimension statuses;
it does not import an owner's account or convert a watchlist into a portfolio.

## Historical dry-run replay

`run_authority_gated_replay` is an adapter of the existing VNM engine, not a generic
backtester. Non-VNM, leveraged and short simulations remain blocked by that engine's
scope. Every required feature is checked before calculation; each later fill requires
its own session-specific authority and cutoff. Future prices are outcome observations,
never retroactive signal inputs. Duplicate sessions and fills outside an explicitly
qualified band fail closed. Lot size, bands and leverage must have explicit governed
values. No order quantity or broker request is created.

The method remains next qualified raw session and an explicitly supplied supported
fixed holding-session exit. No default holding input is introduced by the R7 adapter.
It preserves signal/cutoff, entry/exit provenance, eligibility, CA treatment and costs.
Valid gross research can survive missing fees/slippage. NET requires the existing
validated fee/tax/slippage model and matching governed policy identities on both
cost feature bindings. Missing or invalid costs never become zero. The existing
multiplicative round-trip bps return method is shared by both replay entry points.

## Retained inventory and owner review

[Input manifest](internal/R7_RETAINED_INPUT_MANIFEST.json) lists exact paths/hashes
under owner-supplied read-only root aliases. The offline runner verifies every input
before and after analysis. It has no discovery scan, provider call, Daily run,
production/runtime write or registry operation; outputs are restricted to this
worktree's scratch directory. `--emit-rows` materializes the complete private matrix;
the portable report records its row count and identity chain, counts and source hashes.
Manifest input order and historical-use iteration are canonicalized.

[Acceptance](internal/R7_PORTFOLIO_PIT_EXECUTION_ACCEPTANCE.json) separates October 1
coverage from the older September 28 official window, retains all actual receipt
states, and reports later adjusted series as retrospective research. Synthetic CA
mechanics never count as real qualified factor chains. The real three-event outcome
and the existing upstream authority matrix are retained with their original statuses.

[Machine dossier](internal/R7_EXECUTION_AUTHORITY_PROMOTION_DOSSIER.json) and
[owner review dossier](internal/R7_EXECUTION_AUTHORITY_PROMOTION_DOSSIER.md) name each
stronger use, supporting scope, coverage, validation, limitations and reopen gates.
Only genuinely eligible bounded scopes can be recommended for owner review. Even
such a recommendation does not grant authority. Live consumers remain blocked under
this implementation-only authorization. R7 has no automatic successor milestone;
the next action is owner roadmap review/rebaseline.
