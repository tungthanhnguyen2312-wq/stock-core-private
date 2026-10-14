# Producer financial inputs and Home summary completion V1

Disposition: **PARTIAL_BLOCKED_NATIVE_LEASE_TRANSFER_UNAVAILABLE**. The local
checkpoint implements only an admitted, disjoint offline validation runner,
its refusal/preservation tests, and this closeout record. It does not complete
financial input publication, a reported-period assets ROA method, or integration
of the prior Home/restage changes onto current main.

## Verified starting state and native boundary

Live `origin/main` was independently verified as
`d334f1bdc17429800dae097843995526c173c48c`. A fresh worktree and branch were created
at that exact SHA. No previous checkpoint was reset, amended, replayed into main,
reopened, or relabelled as released.

The existing coordinator is bound to **Codex**, branch
`ops/integration-coordinator-20261013`, and its original checkpoint is
`d71d17b915cd41994686918411e078bbbe61b083`. The initial native check was
`ON_TRACK / VERIFIED`, revision 108. Direct native lane checks returned clean
exact heads, no errors and no unmet *activation* dependencies for:

| Prior lane | Preserved COMPLETE_LOCAL checkpoint |
|---|---|
| VN30 financial valuation research scaleout | `096b8f1676bdb3ed563ac38d68fce74f11df12a7` |
| Financial Consumer Dashboard completion / Producer Home | `ec1d281e85cbf25890995e7219a49b6d220e4472` |
| Home restage / OCR boundary | `c06fcb18b78aa877be878f5262eece3b7e8a1a82` |

The native contract's terminal states are `MERGED_RELEASED` and `ABANDONED`.
`COMPLETE_LOCAL` continues to own its allowed paths. Validation of an in-memory
proposed integration lane returned `LANE_OWNERSHIP_OVERLAP` against **all three**
preserved lanes. No state was mutated by that probe. The CLI has admission,
transition and integration-plan operations, but no transfer/edit-lane operation.
Reopening would violate this Owner directive; marking release would require an
actual authorized merge, checkpoint ancestry and post-merge review/CI evidence.

The native integration plan for the existing boundary checkpoint additionally
reported `LANE_DEPENDENCY_NOT_RELEASED`, duplicate interface owners for
`dashboard_home_notable_cards` and `financial_input_scaleout`, an undeclared
`financial_valuation_research` interface dependency, and `LANE_MAIN_BASE_DIVERGED`.
Its missing exact receipt/check attestations were not fabricated. Local completion
of dependencies permits activation, but does not meet the release dependency gate.

**Precise Owner action needed:** authorize a reviewed native control-plane
extension that transfers exact paths and corrects interface/dependency declarations
while preserving the three COMPLETE_LOCAL states, checkpoints and history. Its
scope would include the native state validator/CLI, control-plane contract and
hermetic lifecycle tests; merely authorizing new source work does not supply this
missing operation. Alternatively, separately authorize normal release of the
predecessors, after actual integration/review/CI and merge gates, then record
`MERGED_RELEASED` using the existing CLI. That alternative is outside the present
no-push/no-merge directive. Manual state editing, abandonment of completions,
copied coordinators, agent impersonation and sibling implementation around leased
numerical owners were not used.

Only `PRODUCER_FINANCIAL_INPUT_AND_HOME_SUMMARY_COMPLETION_V1_DISJOINT_VALIDATION`
was admitted (revision 109) and activated (110), through the bound coordinator.
Its three exact paths are this record, the validation tool and its test file.
The enclosing requested milestone remains partial and blocked.

## Financial evidence and exact publication result

The runner reuses the retained page-eight OCR materialization without OCR/network
acquisition. It verifies exact acquisition-manifest record equality, the retained
PDF's raw SHA-256 and observation identity, the issuer IR URL/final URL, OCR
materialization identity, re-derived unit/scope declarations and exact extraction
result equality at the clean OCR checkpoint.

- Filing SHA: `7e9b9e39901a028972fff80bc1a4f9f5cab4c1526ce4029f9b853ccff6aeaac0`.
- Retained issuer route: `ir.vincom.com.vn`, reviewed consolidated interim filing.
  This is retained-route authenticity, not a new live issuer attestation.
- Page 8, line **280**, literal `TỔNG CỘNG TÀI SẢN (280=100+200)`;
  closing column `Số cuối kỳ`, native value **62.806.214 million VND**;
  normalized candidate **62,806,214,000,000 VND**, June 30, 2026 ending assets.
- Consolidated total H1 net income: **3,214,788,000,000 VND**, January 1–June 30,
  2026, page 11 line 60, same PDF, explicitly normalized VND/units, and qualified
  consolidated interim assurance from page 5. Parent-attributable profit is not used.
- Retained raw observation and income knowledge time:
  `2026-09-29T11:31:14.408633Z`. Publication time remains unqualified. The asset is
  an extraction-qualified candidate from the October 14 OCR checkpoint; its
  canonical knowledge-time/fitness admission is **not inferred from raw observation**.
  It has no newly admitted panel row or metric-time authority.

The existing official reported-period return API accepts a qualified `net_income`
duration envelope and a `shareholders_equity` instant envelope, with same-document,
scope, normalized currency/scale and matching cutoff/end checks. It explicitly
refuses `total_assets` with `OFFICIAL_RETURN_METRIC_IDENTITY_INCOMPATIBLE`.
The official reported-period valuation input methods expose income/revenue/equity
envelopes, not a newly admitted assets-return envelope. Canonical materialization,
the financial engine and downstream valuation projection are leased. Therefore a
distinct versioned ending-assets ROA cannot legally be implemented or published in
this admitted scope. No annualization, average-assets substitution, parent/consolidated
mixing, authoritative ROA, or numerical sibling workaround is produced.

**New financial research inputs published: 0. New metrics published: 0.**
The 13 previously admitted official facts remain 13; the single extraction-qualified
assets candidate remains outside canonical publication. Existing VRE H1 ending-equity
ROE stays **0.06519456751279788**, consolidated, non-annualized research proxy.

Exact available counts below compare the *same retained 30-name predecessor method
inventory*. They are not a new current-main publication or proof of exact October 14
VN30 membership. Full fitness counts and per-metric refusal-code counts are retained
in `exact-coverage.json`; the before/after CSV files are byte-identical.

| Metric | Before | After |
|---|---:|---:|
| P/E | 2 | 2 |
| P/E reported period | 1 | 1 |
| P/E TTM | 0 | 0 |
| P/B | 2 | 2 |
| P/B current research | 28 | 28 |
| P/B official research | 1 | 1 |
| P/S | 2 | 2 |
| P/S reported period | 1 | 1 |
| P/S TTM | 0 | 0 |
| EV/EBITDA | 0 | 0 |
| EV/EBITDA calculation-ready | 0 | 0 |
| ROA average balance | 0 | 0 |
| ROA cross-provider proxy | 14 | 14 |
| ROA ending-period proxy | 0 | 0 |
| ROE average balance | 0 | 0 |
| ROE ending-period proxy | 0 | 0 |
| ROE reported-period ending-equity proxy | 1 | 1 |

Residual evidence refusals include missing compatible four-quarter continuity,
exact common outstanding-share continuity/market capitalization, compatible debt/EV/
EBITDA components and target-date membership intervals. Specialist applicability
is unchanged. This isolated candidate provides no broader VN30 valuation improvement.

## Home fixture acceptance

No Home production-path source was changed. The preserved Home/OCR checkpoint
already contains the optional block implementation. The new runner exercises that
exact code against retained presentation inputs, the actual source JSON/JS staging
writer in a temporary directory (upstream analytical owners supplied as fixtures),
and canonical restage. It requires all nine selected fields to match verbatim and
checks original insertion order, maximum four, source/session identity, enclosing
summary rehash, old summary equality and published-empty versus absent identity.
No financial calculation or recommendation is added to Home.

| Fixture | October 13 | October 14 |
|---|---|---|
| Cards in insertion order | AAS, ABW, ACB, ACG | AAA, ABB, ABI, ACB |
| Summary identity suffix | `2707cb3ae578268030d1e678b21905ddeeda0c13aca02bd06906e434aac5ab56` | `feb7aadc1d86a8f7512a3296e7c35677071f2c10cbab8dd691ece2833fd33b63` |
| Legacy twin / nine-field / staging / restage parity | PASS | PASS |

Both identities use the prefix `dashboard_home_summary/v1:`. October 13 reproduces
the prior qualified fixture exactly. October 14 binds workspace
`investment_decision_workspace_projection/v1:326c5d61c6e5fca6eeab506ab3fd17d2f7a84f9d651827623a2e228f27012263`.
These are scratch fixtures, not published artifacts or edits to historical summaries.

The retained Grok Dashboard consumer, verified at the clean live local checkpoint
`bca167ecce3616d94039fdfa5c81790f6632fb56`, accepts the actual October 14 fixture
with a fixture build-info binding to its exact session/workspace. Seven Node
assertions prove populated and empty blocks request zero workspace indexes,
absence requests one fallback index, and a wrong workspace identity is refused.
The first probe omitted the Dashboard build-info `CURRENT` status/source-session
fields and was refused; supplying the actual required fixture contract passed.
No Dashboard checkout, live build info or publication was modified.

## Validation and preservation

Validation evidence is retained locally outside the source checkout under the
milestone's `codex-reports` directory; portable source instructions take explicit
paths via `python tools/validate_producer_financial_home_completion.py --help`.
The tool refuses existing output directories and overlap with any supplied input.

- New disjoint validation tests: **23 passed**. Tests cover parent-profit/scope/
  currency/scale/date/assurance refusal, same-size protected byte tampering, missing
  files, unsafe output paths, zero-valued coverage and rehashed card/order/reason/
  source/selection tampering.
- Current-main financial engine, valuation context and frozen infrastructure:
  **324 passed** (`test_financial_analysis_engine_v2`,
  `test_current_research_valuation_context`, `test_e4_infrastructure`).
- Unfiltered prior-checkpoint financial/OCR/Home/restage/source staging:
  **198 passed, 8 skipped, 5 failed, 2 errors**. Exact failed/error nodes and causes
  are preserved in `prior-focused-tests.log`; this is not a green suite.
  The OCR panel-adapter fixture omits mandatory retained assurance evidence.
  Three runtime tests need absent governed retained source artifacts. The completed-
  session replay fixture supplies a Producer preflight dict without the now-required
  `status` key. Two source-projection tests require absent retained evidence.
  None of those leased test/source paths was edited to hide failures.
- Structural/native/Daily compatibility: **152 passed** (`test_repository_layout`,
  `test_roadmap_execution_state`, `test_parallel_domain_control_plane`,
  `test_production_call_shape_smoke`, `test_daily_publication_control_plane`,
  `test_daily_session_completion_reference`, `test_owner_daily_journal`). No
  production entrypoint is run.
- `git diff --check` passes. Only the three admitted disjoint source paths change.
- **51 exact selected files** have SHA-256/size parity: the October 14 registry and
  COMPLETE owner journal; all ten registry-linked inputs; nine final presentation
  files; and all thirty top-level files in the exact sealed operation directory,
  including T0/prospective snapshot, run manifest, sealed workspace and AI bundle.
  The journal remains run `80ef6557215c44bfbdade81272b5c37c`, session October 14,
  stage COMPLETE. This is bounded selected-artifact preservation, not a recursive
  audit of every runtime location.

No targeted Producer optimization is included: those paths are leased, and no
performance change can be admitted while preserving this boundary. No repository-
wide simplification, frozen repin, Daily contract change or successor was started.

## Single integrated source-release recommendation

**HOLD the integrated source release at the Owner gate.** Review the disjoint
validation checkpoint as evidence only. The same requested milestone still needs
a legal native ownership/declaration resolution, compatible fresh-main integration,
a distinctly contracted assets ROA method and canonical input/output provenance/
fitness acceptance, followed by the full integrated checks with the above fixture
blockers resolved. No push, merge, deploy, publication, production Daily/database
write or authority promotion has occurred or is recommended as an automatic action.
