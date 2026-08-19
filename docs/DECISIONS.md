# Decisions

## 2026-08-19 - P0-A.3E prospective multi-session evidence collection complete; event-window qualification blocked

`P0-A.3E = PART_A_COMPLETE_EVIDENCE_ACQUIRED; PART_B_BLOCKED_PENDING_QUALIFIED_EX_DATE`.

1. **A3E Part A Prospective Multi-Session Collection is COMPLETE_EVIDENCE_ACQUIRED**:
   - Distinct multi-session completed-bar (`bc`) evidence retained across Sessions 1–4 under lineages `70a7904` and `4150f02c`.
   - Per-symbol evidence matrix: Session 1 (HPG PASS, VCB PASS); Session 2 (HPG BLOCKED, VCB PASS); Session 3 (HPG BLOCKED, VCB PASS); Session 4 (HPG PASS, VCB BLOCKED).
   - Partial sessions (`SESSION_PARTIAL`) and honest `BLOCKED_NO_COMPLETED_EVENT` outcomes are verified contract-compliant and do not invalidate evidence or indicate defects.
   - No further live prospective WebSocket acquisition is required for A.3E.

2. **Part B Event-Window Price-Basis Qualification is BLOCKED_PENDING_QUALIFIED_EX_DATE**:
   - Requires explicit official corporate-action ex-date evidence and executed distribution status.
   - Inferring ex-date from record date or fabricating adjustment factors remains strictly forbidden.
   - `RAW_AS_TRADED` remains **NOT_PROMOTED**.
   - `OFFICIAL_CLOSED_BAR_FINALITY_DOES_NOT_BY_ITSELF_PROVE_RAW_AS_TRADED` and `NO_REVISION_OBSERVED != IMMUTABLE` remain binding.

3. **Critical Path & Next Milestone**:
   - With A.3E Part A complete and Part B safely fail-closed, the next actionable roadmap milestone is `P0-C.3` (field-level freshness/as-of retrofit) per critical path governance.

## 2026-08-18 - P0-B.2B1 VALIDATED_SHADOW result; C1-C4 BLOCKED confirmed on full corpus

`P0-B.2B1 = VALIDATED_SHADOW_SCALE_RELATION_WITH_UNRESOLVED_RESIDUALS`.

1. **C1-C4 confirmed BLOCKED on full corpus**: All four original candidates fail across the complete
   40-session / 35,231-symbol-session corpus (C1 exact=0/35,231 = 0.0000%; C2=2; C3=1; C4=2).
   Root cause is exclusively unit-scale mismatch (C1-C4 are missing a ×10 factor) plus composition
   mismatch for C2-C4 (include boards that contribute nothing to daily_v).

2. **C5 = 10 × board_G1_quantity** matches 35,164/35,231 = **99.8098%** exactly over the full
   40-session retained corpus. Determinism verified: two independent runs produce identical content
   hash `ac5942913291c9ac8efb73d77a3b97dbb9068f111c8c6996422b66ef4e2b183d`.

3. **Scale is EMPIRICAL_CANDIDATE only.** The ×10 factor must NOT be encoded as "Trades quantity
   unit = 10 shares". `semantic_unit_interpretation = UNKNOWN` is binding.
   `scale_status = EMPIRICAL_CANDIDATE`. No authority promotion from this milestone.

4. **67 residuals remain unresolved** (0.19% of eligible sessions):
   - 62 `POSITIVE_DELTA_MULTIPLE_OF_100` across 53 symbols — consistent with a small number of G1
     executions present in OHLC daily_v but absent from the canonical Trades corpus; true root cause
     NOT established.
   - 5 `NEGATIVE_DELTA_MINUS_4` confined to SHB and VIX only across 5 trading dates.
   - 0 `OTHER`.
   - Zero overlap with Task-160's 27 known REMAINING_FAILED units — that hypothesis ruled out.

5. **Provenance gap recorded**: canonical Trades source commit
   `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02` is `SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY`.
   This does not invalidate the retained evidence but must remain visible for any promotion review.

6. **Not QUALIFIED_VOLUME_COMPOSITION and not QUALIFIED_LIQUIDITY_INPUTS.**
   `qualified_liquidity_inputs = False` unconditionally from this milestone.
   P0-B.2C (va/turnover) is NOT implemented. P0-B.2D promotion review is the required next step.
   P0-B is NOT closed. `P0-A.3E = ACTIVE_MULTI_SESSION_COLLECTION` is preserved and untouched.

## 2026-08-18 - P0-B.2A_B2B terminal verification complete; P0-B blocked

`P0-B.2A_B2B` (DNSE Daily Volume Composition Reconciliation V1) is **BLOCKED**.
Terminal verification on a real 1-day canonical trades vs OHLC corpus (944 eligible symbol-sessions) found 60 discriminating sessions. Of these 60, zero yielded an exact daily `v` match across all candidate compositions (`C1`-`C4`). The result was 60 `CONFLICTING` and 884 `INSUFFICIENT_DISCRIMINATION` sessions.
Volume semantics are completely unpromoted. P0-B is NOT closed. `QUALIFIED_LIQUIDITY_INPUTS` are NOT emitted. `P0-B.2C` (va/turnover) was explicitly scoped out and not implemented.

## 2026-08-18 - Isolated Bulk Acquisition Framework V1 completed; independence from P0-B confirmed

`ISOLATED_BULK_ACQUISITION_FRAMEWORK_V1 = COMPLETE_LOCAL` (branch `feature/isolated-bulk-acquisition-framework-v1`).

1. **Independent Lanes**: `ISOLATED_BULK_ACQUISITION_FRAMEWORK_V1` for official documents and `P0-B` market-volume reconciliation are independent lanes. The document acquisition framework is not a prerequisite for P0-B.
2. **Acquisition vs Qualification Separation**: Raw document acquisition (`data-landing/`) never promotes evidence to financial-fact, observation, feature, or provider authority. `RawDocumentRecord.qualification_state = "unknown"` remains unconditionally assigned.
3. **No Cross-Talk with Existing Pillar-B**: The framework operates in strict path and logical isolation from existing `official_document_acquisition.py` / `official_document_store.py` production infrastructure; it does not replace, wrap, or modify them.

## 2026-08-18 - Cross-Sectional Deterministic Reconciliation approved for P0-B market-volume semantics

`P0-B_QUALIFIED_VOLUME_LIQUIDITY_QUALIFICATION_DESIGN`.

1. **Approved Qualification Method**: Cross-Sectional Deterministic Reconciliation across complete eligible cohorts and discriminating sessions (sessions with distinct continuous, put-through, and odd-lot activity) is the approved qualification method for unresolved DNSE daily `v`/`va` market-composition semantics.
2. **Single-Ticker / Single-Session Insufficiency**: A single ticker/session coincidence is explicitly insufficient for authority promotion.
3. **Exchange/Regime Awareness**: Trading-phase classification must be exchange/instrument/regime aware, not a universal hard-coded clock assumption.
4. **Missing Observation Treatment**: Known missing observations remain explicit and are never imputed as zero.
5. **Closeout Boundary**: P0-B closeout emits `QUALIFIED_LIQUIDITY_INPUTS` (volume, trading value, turnover, participation basis). It explicitly does **NOT** establish `POSITION_SIZING_IS_SAFE`.

## 2026-08-18 - A.3D keepalive correction live-validated; A.3E Session 1 acquired

`P0-A.3D = COMPLETE_LOCAL_NO_PUSH` remains governed `EXPERIMENT_SHADOW_ONLY`. Corrective commit
`ecb2c6c17039f123e7e8fe5b7dd53604c2893f58` fixed the verified defect where routine `ping`
keepalive/control traffic could exhaust the semantic receive budget before a closed-bar content
opportunity. `ping` remains non-secret observable and receives `pong`, but consumes no semantic
control, ignored-non-`bc`, or total semantic-frame budget; the absolute session deadline remains
the boundedness authority. This is an implementation safety property, not production or price
authority.

The subsequent human-governed A.3E session
`2026-08-18-postfix-ecb2c6c` is `SESSION_EVIDENCE_ACQUIRED`, with accepted HPG and VCB evidence
at the corrective source lineage. This validates the bounded post-fix capture path only. It does
not promote `RAW_AS_TRADED`, official closed-bar finality, revision immutability, PIT safety, or
registry/provider authority. `OFFICIAL_CLOSED_BAR_FINALITY_DOES_NOT_BY_ITSELF_PROVE_RAW_AS_TRADED`
and `NO_REVISION_OBSERVED != IMMUTABLE` remain binding.

`P0-A.3E = ACTIVE_MULTI_SESSION_COLLECTION`, with two separate substreams:

- **A. `PROSPECTIVE_MULTI_SESSION_COLLECTION`** — `OPERATIONAL / SESSION_1_ACQUIRED`.
- **B. `EVENT_WINDOW_PRICE_BASIS_QUALIFICATION`** — `BLOCKED_PENDING_QUALIFIED_EX_DATE`.

No ex-date may be inferred from record date. Until a qualifying official ex-date exists, the
event-window component remains fail-closed; no A.3E result opens `P0-A.4` or `P0-B`.

## 2026-08-18 - P0-A.3C evidence acquired; P0-A.3D governed prospective collector integrated locally

`P0-A.3C_DNSE_PROSPECTIVE_WEBSOCKET_PAYLOAD_SEMANTIC_EVIDENCE_ACQUISITION =
COMPLETE_EVIDENCE_ACQUIRED`. The retained human-run evidence package at
`C:\Projects\StockLookup\operations-review\p0-a3c-live-20260818-090834` independently validates
`PASS_EVIDENCE_ACQUIRED` on HPG attempt 2 and VCB attempt 2, with final state
`PASS_EVIDENCE_ACQUIRED_BOTH_SYMBOLS`. Both records are real WebSocket `ohlc_closed.1.json`
completed-bar payloads with `T = "bc"`, requested symbol/resolution correspondence, collector
execution-ID linkage, deterministic hash/replay verification, and no source-baseline mutation.
Attempt 1 for each symbol is correctly retained as `BLOCKED_NO_COMPLETED_EVENT`; no observation
was fabricated.

The HPG/VCB payloads contain the documented OHLC-Closed required fields and empirically reconcile
that `tradingDate` and `tradingSessionId` are optional/absent in these messages. This verifies
current protocol/payload shape only. It does **not** establish `RAW_AS_TRADED`, non-revision,
corporate-action behavior, board/lot semantics, historical REST PIT safety, source registry
authority, or any provider/production authority. `RAW_AS_TRADED = NOT_PROMOTED` remains binding.

`P0-A.3D_GOVERNED_PROSPECTIVE_COLLECTOR_INTEGRATION = COMPLETE_LOCAL_NO_PUSH` at local commit
`3291ed8afda3c6aba8100f77bf5c88a2915801fd` (parent
`77bfe95f203ea87aa80ffbc5918215234f3fcbc7`). It moved only the byte-baselined A.3C shadow
collector/test prior art into tracked source and preserved `EXPERIMENT_SHADOW_ONLY`. The bounded
hardening is limited to request/payload correspondence rejection, evidence-output collision
refusal, non-secret control/ignored-type/timeout observability, separated bounded receive budgets,
and a total wall-clock cap. No live call, credentials, daemon, reconnect, raw-lake integration,
RawObservation redesign, database write, registry change, or authority promotion occurred.

**Next gate:** `P0-A.3E` — **Prospective Multi-Session / Event-Window Price-Basis Qualification**.
It must explicitly separate (A) bounded, human-owned prospective evidence collection from (B)
event-window qualification, which can proceed only when a qualifying official corporate-action
ex-date is actually evidenced. It may not infer an ex-date, require a future event to exist, or
fabricate event evidence. Without that evidence, the event-window portion is blocked/fail-closed.
No daemon or unattended collector is authorized. Critical path: `P0-A.3D` → `P0-A.3E` →
`P0-A.4` / `P0-B` → `P0-C.3`.

## 2026-08-17 - P0-A.3B closed; P0-A.3C prospective WebSocket evidence gate opened

`P0-A.3B_DNSE_PROSPECTIVE_PIT_PRICE_AUTHORITY_ARCHITECTURE_REVIEW = COMPLETE_READ_ONLY`.
Architecture verdict: `SOURCE_SEMANTICS_BLOCKED`. No code, runtime, provider, registry, or
price-basis authority changed.

**Review findings:**
- No current DNSE price source, feed, or field is authoritative `RAW_AS_TRADED`. The bounded
  DNSE REST OHLC authority remains `ADJUSTED_RETROSPECTIVE`; other REST ticker/session price basis
  remains `UNKNOWN` unless separately bounded-qualified.
- The WebSocket `ohlc_closed` prospective lane remains an `EXPERIMENT/SHADOW`, semantically
  unqualified, non-authoritative, and has zero real retained completed-event observations today.
  Transport speed, first receipt, append-only retention, and timestamp proximity do not establish
  raw/as-traded, adjustment, revision, session/calendar, or odd-lot/board semantics.
- The shadow disposition is `DEFER`: do not reject, promote, port, or reimplement it. Its useful
  future concepts (`logical_bar_identity`, first-observed retention, duplicate-identical handling,
  append-only revision linkage) and identified retention gaps (additive logical/business identity,
  revision linkage, streaming/session reconciliation) are not implementation authorization.
- Prospective qualification cannot retroactively make historical REST OHLC PIT-safe. Raw/as-traded
  price authority and corporate-action adjustment authority remain independent per-use gates.

**Next gate:** `P0-A.3C` — **DNSE Prospective WebSocket Payload Semantic Evidence Acquisition**
is `EVIDENCE_ACQUISITION_NEXT`, `NO_PRICE_BASIS_PROMOTION`, and
`HUMAN_LIVE_EXECUTION_REQUIRED`. Its sole objective is first real retained, non-synthetic DNSE
`ohlc_closed` completed-bar evidence: payload shape, field/symbol identity, units/scaling,
provider/source and receipt timestamps, supplied session fields, and naturally observed
duplicate/revision behavior. Same-day REST-vs-WS comparison may investigate correspondence only;
matching values do not prove `RAW_AS_TRADED`, non-rewriting, or PIT safety.

**Bounded capture and completion conditions:**
- One human/PowerShell-owned bounded foreground launch at operator-selected live timing; no daemon,
  unattended reconnect, polling, or AI-owned background process. Scope is two operator-selected
  eligible liquid `EQUITY` symbols, one supported resolution, and at least one real completed-bar
  payload retained for each symbol. Named tickers are regression examples only; no full session or
  full-universe requirement is inferred.
- Completion requires content/byte identity hash, receipt timestamp, supplied provider/session
  fields retained without invented meaning, deterministic replay/readback, same-day comparison
  recorded with its non-authority caveat, duplicate/revision retention without overwrite if naturally
  observed, and no registry/source-authority promotion or `market_raw_lake` integration.
- RawObservation changes, streaming integration, terminal-session reconciliation, price-basis
  registry changes, corporate-action mutability qualification, `RAW_AS_TRADED`/PIT promotion, and
  post-A.3C gate naming remain explicitly future and unauthorized until real evidence exists.

## 2026-08-17 - Future capability enrichment: macro, microstructure, forensics, and authority governance policy

`FUTURE_CAPABILITY_ENRICHMENT_V2`. Documentation and policy synchronization only.
No code modified, no runtime execution, no data, source, or model authority promoted.

**Durable policy decisions established:**
1. **P0 Critical Path Unchanged**: Proposed analytical and foundation capabilities do not alter
   the active critical path (`P0-A.3D` governed prospective collector integration → `P0-A.3E`
   prospective multi-session/event-window qualification → `P0-A.4`/`P0-B` → `P0-C.3`).
2. **Future Capability Placement without Premature Numbering**: Downstream requirements are
   documented without opening implementation; sub-milestone numbering remains intentionally TBD
   until the respective phase is authoritatively opened.
3. **Sector-Conforming Valuation (Rejection of Universal DCF)**: A universal cross-sector DCF is
   rejected. Candidate valuation model families remain subject to later qualification and
   sector/applicability contracts.
4. **Rejection of Uncalibrated Kelly Sizing**: Kelly sizing from assumed, LLM-generated, or
   uncalibrated probabilities is rejected; it requires empirical, out-of-sample calibrated
   distributions under qualified backtest semantics.
5. **Cross-Cutting Invariants vs Milestones**: Resumable checkpointing/manifests and isolated
   shadow execution/worktrees remain mandatory engineering invariants, not missing milestones.
6. **Three Distinct Authority Classes (Measurement vs Interpretation vs Causal Claim)**:
   - **Measurement**: Observed or deterministically-derived values from qualified inputs (e.g. `VN30F1M_basis = -12.4`, basis percentile).
   - **Interpretation / Hypothesis**: Analytical explanations of what a measurement may mean (e.g. `negative basis may be consistent with hedging demand`). This is an analytical hypothesis, never automatically a deterministic system fact.
   - **Causal / Predictive Claim**: Claims of forward predictive power (e.g. `SBV net injection predicts equities in 2–4 weeks` or `basis predicts market decline`). Requires qualified empirical validation and backtesting.
   - *Rule*: The system must never silently promote measurement → interpretation → causality.
7. **Canonical AI Research Handoff (Research Evidence Packet)**:
   - The canonical governed handoff to the AI research layer remains the **Research Evidence Packet (REP)**; no parallel canonical object called "Research Evidence Bundle" is created.
   - The REP evolves by carrying optional qualified facets (`market_price_context`, `volume_liquidity_context`, `foreign_flow_context`, `market_breadth_context`, `macro_monetary_context`, `derivatives_microstructure_context`, `financial_evidence`, `financial_forensics`, `valuation_context`, `portfolio_risk_context`, `thesis_evidence`, `counter_thesis_evidence`).
   - Each facet preserves its own provenance, freshness/knowledge time, PIT semantics, eligibility state, and reason codes. One BLOCKED facet does not invalidate an unrelated valid use case.
8. **Governed Deterministic Engines as Numerical Authority**:
   - Governed deterministic engines are the **numerical authority** for formalizable production and research metrics (avoiding simplistic statements like "AI does not do math").
   - AI may reason over numbers, compare values, perform exploratory calculations, synthesize evidence, identify contradictions, and generate thesis/counter-thesis arguments.
   - An AI-generated calculation does *not* become an authoritative Stock Lookup fact unless produced or verified through the governed deterministic pipeline. AI must never fabricate target prices, calibrated probabilities, adjustment factors, WACC, growth rates, or causal coefficients.
9. **Per-Use Authority & Readiness (No Global "100% Complete" Blocker)**:
   - Stock Lookup authority is per-use and per-capability, not a single global "100% complete" flag.
   - Each capability is independently eligible when the dependencies required by that specific use case are qualified.
   - Fail-closed behavior is enforced locally at the dependent boundary (e.g. current fundamental facts may be qualified while PIT backtesting is blocked; shadow screening may operate non-authoritatively while portfolio sizing is unavailable) without globally freezing unrelated valid capabilities.
10. **Future Analytical Signals (P1 Macro/Derivatives, P2 Financial Forensics)**:
   - SBV monetary/liquidity context, VN30 derivatives microstructure, and forensic accounting-risk signals (cash conversion, unusual receivables concentration, Altman/Piotroski health scores) are recorded as non-active future capabilities and do not alter the active P0 critical path.
   - Neutral terminology is required for forensics (`accounting_risk_signal`, `other_receivables_asset_concentration`); pejorative or legalistic claims ("rút ruột doanh nghiệp", fraud, manipulation) are strictly forbidden without authoritative legal proof.
11. **Screener Authority Classes**:
   - `SHADOW_RESEARCH_SCREENER` operates for research with explicit provenance, visible UNKNOWN/BLOCKED semantics, and no claim of authoritative actionability.
   - `AUTHORITATIVE_LIVE_ANALYSIS` remains blocked until required P0 price, volume/liquidity, and
     universe authorities are qualified; a later opened capability must also satisfy its
     output-specific gates.

## 2026-08-17 - P0-A.3A PIT price reconstruction contract integrated to local main (P0-A.3 IN PROGRESS)

`P0-A.3A_PIT_PRICE_RECONSTRUCTION_CONTRACT_V1`. Integrated into local `stock-core-private`
main (commit `e360adbbc801650e6ca4c7e324f9ffcf2f32f85b`, parent `f65dc4cb07a28623523e4a9f3672f1d0537a902e`, `push = NO`).
Independent read-only safety audit and narrow re-audit both completed (`P0A3A_SAFE_FOR_REAL_UNIVERSE_VALIDATION`).
No network calls, no runtime/DB writes.

**Committed files:**
- `pit_price_reconstruction_contract.py`
- `tests/test_pit_price_reconstruction_contract.py`

**Key semantics established:**
1. **Mechanical Mode Isolation & Explicit Actionability:**
   - `PIT_AS_KNOWN` and `RETROSPECTIVE_RESTATED` are mechanically separated across output schemas and universe summaries.
   - Every record explicitly carries `pit_backtest_eligible: bool`, true *only* when `mode == PIT_AS_KNOWN and verdict == QUALIFIED`.
   - `RETROSPECTIVE_RESTATED` records strictly emit `pit_backtest_eligible = False`, even when `verdict == QUALIFIED` (e.g. bounded HPG/VCB retrospective evidence).
   - `classify_universe()` replaces generic `qualified_tickers` with mechanically partitioned `pit_backtest_eligible_tickers` and `retrospective_qualified_tickers`.
2. **Positive Semantic Authority Required First for PIT_AS_KNOWN:**
   - Caller-supplied `retrieved_at` proximity can never self-authorize PIT eligibility.
   - `_price_basis_state()` requires positive `RAW_AS_TRADED` price-basis authority from `provider_price_basis_registry.bounded_price_basis_for()` before any caller observation is evaluated.
   - Only after `RAW_AS_TRADED` is authoritatively proven does the observation's shape (requiring all 7 `market_data_contracts.RawObservation` identity fields: `provider`, `dataset`, `instrument`, `retrieved_at`, `request_identity`, `raw_payload_hash`, `schema_version`), matching query identity, knowledge cutoff (`retrieved_at <= cutoff`), and temporal proximity act as supporting proof.
   - Retrospectively rewritten DNSE current-query responses cannot qualify merely because they were retrieved close to a session.
3. **Current Repository Authority Bounds Respected:**
   - Current repository authority provides no real `RAW_AS_TRADED` market-wide price authority; every active DNSE bounded authority is `ADJUSTED_RETROSPECTIVE`.
   - Real `PIT_AS_KNOWN` qualified count across the universe is correctly **0**. This is a verified negative proof of authority compliance, not an implementation failure.
4. **Corporate-Action Knowledge-Time & Cash Dividend Safety:**
   - Gating strictly uses `observed_at` (when Stock Lookup retained the bytes); `published_at` is ignored in knowledge-time cutoff comparisons.
   - Late amendments/cancellations cannot alter earlier as-known state.
   - Missing `ex_date` strictly fails closed (`REASON_MISSING_EXPLICIT_EX_DATE`); `record_date` is never substituted for `ex_date`.
   - Planned non-executed issuances remain fail-closed.
   - `official_corporate_action_ledger.event_key()` remains untouched.
   - Pure cash-dividend observations are gated fail-closed (`REASON_CASH_DIVIDEND_NO_FACTOR_METHODOLOGY`) without fabricating share-count ledger linkage or portable factors.
5. **Prospective Shadow Containment:**
   - `dnse_prospective_pit_shadow.py` remains untracked, non-authoritative, and deferred (`DEFER_CONFIRMED`); no live acquisition or forward-capture logic was imported or duplicated.

**Validation evidence:**
- Independent audit initially caught one blocking fail-open (temporal proximity self-authorization); defect was bounded-fixed and verified via narrow re-audit (`RAW_OBSERVATION_GATE = SAFE`, `MODE_ISOLATION = SAFE`).
- Full test suite post-fix: 320 passed, 0 failed, 0 error, 0 skipped.
- Focused contract tests: 86 passed, 0 failed, 0 error.
- Real retained P0-A.1 population validation over 1,660 instruments (1,528 success + 132 `PERMANENT` HTTP 400 `BAD_REQUEST` "invalid symbol"):
  - `PIT_AS_KNOWN`: 132 `BLOCKED`, 1,528 `UNKNOWN`, 0 `pit_backtest_eligible`.
  - `RETROSPECTIVE_RESTATED`: 132 `BLOCKED`, 1,528 `UNKNOWN`, 0 `pit_backtest_eligible`.

**Status & Next Gate:**
- `P0-A.3` is **IN PROGRESS** (sub-slice `P0-A.3A` complete on local main, `push = NO`).
- Subsequent authority records: `P0-A.3B` closed `COMPLETE_READ_ONLY` / `SOURCE_SEMANTICS_BLOCKED`;
  `P0-A.3C` is `COMPLETE_EVIDENCE_ACQUIRED`, `P0-A.3D` is `COMPLETE_LOCAL_NO_PUSH`, and active
  next gate is `P0-A.3E` prospective multi-session/event-window price-basis qualification.

## 2026-08-17 - P0-A.2 corporate-action multi-event extraction integrated to local main (P0-A.2 COMPLETE)

`P0-A.2_CORPORATE_ACTION_MULTI_EVENT_EXTRACTION_V1`. Integrated into local `stock-core-private`
main via fast-forward (independent read-only audit `SAFE_TO_INTEGRATE_LOCALLY`, `P0A2_CAN_CLOSE_AFTER_INTEGRATION`,
commit `a7e4a1ce7e8df1c24587c25f669393a5f0265b5e`, `push = NO`). Candidate branch
`feature/p0a2-multi-event-extraction-v1` from worktree
`stock-core-p0a2-multi-event-extraction-v1-20260817`. No network calls, no live acquisition.

**Changes integrated:**
1. **`corporate_action_events.py`:**
   - Added backward-compatible plural extraction boundary `extract_event_observations()` and facet detector `detect_event_facets()`.
   - Delegates to unmodified `extract_event_observation()` when fewer than 2 facets are present (all single-event documents unchanged).
   - Added `extract_explicit_cash_amount_per_share()`: extracts cash amount from explicit `"<amount> VND per share"` / `"đồng/cổ phiếu"` wording, never computed from a percentage rate.
   - Preamble shared facts (`record_date`) carried cleanly onto each facet; quantities/ratios/amounts isolated strictly to each facet span.
2. **`tests/test_official_corporate_action_pillar.py`:** Added 18 new regression tests (108 total, 90 passing, 18 legacy VCB fixture skips). All 18 new tests run and pass.

**Verified results preserved:**
- SSI retained notice (`ssi-vsdc-198728`) yields exactly two independent observations:
  - `cash_dividend`: `cash_amount_per_share = 1000.0` VND (explicit text), `record_date = "2026-08-18"`, `ex_date = None`, `lifecycle_state = "record_date_confirmed"`.
  - `bonus_shares`: `stock_ratio = 0.2` (explicit 5:1 rate), `record_date = "2026-08-18"`, `ex_date = None`, planned issuance remains non-executed (`shares_after = None`, `lifecycle_state = "record_date_confirmed"`).
  - Both facets strictly enforce `record_date` != `ex_date` (`ex_date_absent` warning attached).
  - Neither facet reaches an unqualified price adjustment factor.
- HPG issuer-IR regression preserved (`stock_dividend`, executed, `shares_after = 8,442,964,520`, ex-date absent, factor `NOT_READY`).
- Zero field leakage between facets, distinct deterministic observation hashes, shared provenance preserved.

**Downstream ledger constraint (not a P0-A.2 blocker):**
- Current `official_corporate_action_ledger.py` `event_key` is share-count-based (`shares_after` / `shares_issued` / `shares_before`).
- Pure cash-dividend observations without share changes land in `unlinked_observations` with reason `"no share-change identity; cannot be linked to an event"`.
- Downstream milestones `P0-A.3` / `P0-A.4` must not fabricate linkage or price factors from this limitation.

**P0-A.2 is COMPLETE.**
Next gate: `P0-A.3` — **Market-wide PIT price reconstruction** (not started; depends on A.1 + A.2).

## 2026-08-17 - P0-A.2 corporate-action document-authority coverage extension integrated to local main

`P0-A.2_CORPORATE_ACTION_AUTHORITY_COVERAGE_V1`. Integrated into local `stock-core-private`
main via fast-forward (independent read-only audit `SAFE_TO_INTEGRATE_LOCALLY`, commit
`8f1367667971858db640f1d194412e70918bebe2`, `push = NO`). Candidate branch
`feature/p0a2-corporate-action-authority-coverage-v1` from worktree
`stock-core-p0a2-corporate-action-authority-coverage-v1-20260817`. No network calls, no live acquisition.

**Changes integrated:**
1. **`corporate_action_events.py`:** Added a generic, `source_id == "issuer_ir"` branch in
   `classify_retained_document()` using standard document-internal recital cues (`"thay đổi niêm yết"`,
   `"tổ chức niêm yết:"`, `"mã chứng khoán:"`) and cross-checking the stated ticker code against
   the caller's claim. Unmodified `is_vsdc` branch and `DOCUMENT_CLASS_CEILING` lifecycle contracts preserved.
2. **`config/official_source_registry.json`:** Declared `"listing_change_notice"` under `"issuer_ir"`.
   Admission remains host- and document-type-gated via `official_source_registry.py`.
3. **`tests/test_official_corporate_action_pillar.py`:** Added 18 new regression tests covering
   generic issuer-IR classification, HPG real notice validation, SSI real VSDC notice validation,
   and registry admission. All 18 new tests run and pass (72 existing pass, 18 legacy VCB tests skipped
   due to optional offline fixture absence).

**Verified results:**
- **HPG retained issuer-IR evidence:** Classifies via the generic `issuer_ir` path and reproduces
  the existing qualified result (`stock_dividend`, executed, `shares_after=8,442,964,520`,
  `adjustment_factor` `NOT_READY` for missing ex-date).
- **SSI retained VSDC evidence:** Validated through the real pipeline, remains strictly fail-closed:
  `record_date` (`2026-08-18`) != `ex_date` (`None`), planned bonus (`stock_ratio=0.2`) does not
  become an executed share count, 0 ledger entries created, 0 price adjustment factors reachable.

**P0-A.2 is NOT complete.**
- **Remaining P0-A.2 gap:** The retained SSI document (`ssi-vsdc-198728`) contains both cash-dividend (10%)
  and bonus-share (20%) facets, while the current single-event-per-document extraction model captures only
  `bonus_shares`. Full multi-event extraction from single compound notices remains an open gap before
  P0-A.2 can be considered complete.
- **Do not start or choose P0-A.3.**

## 2026-08-17 - P0-A.2 corporate-action prior art review: REJECT_AND_REIMPLEMENT

`P0-A.2_CORPORATE_ACTION_EVIDENCE_SCALE_OUT_REVIEW`. Reviewed prior art branch family
`1183c72`→`d7b9bf3` ("feat(core): scaffold official corporate actions foundation").

**Disposition: `REJECT_AND_REIMPLEMENT`.**

**Meaning of disposition:**
- Reject the duplicate/weaker prior-art pipeline scaffolding;
- **DO NOT** rebuild current B3/B4 architecture.
- Current-main `corporate_action_events.py` (B3 event materialization) + `official_corporate_action_ledger.py`
  (B4 official ledger) remain the authoritative implementation basis.

**Main reasons:**
1. **Document-class lifecycle ceiling already exists on main:** Current main already implements document-class
   authority boundaries and life-cycle classification (`corporate_action_events.py` / `DOCUMENT_CLASS_CEILING`).
2. **Official source registry gate already exists:** Current main enforces strict source registry gates
   (`official_source_registry.py` / `config/official_source_registry.json`).
3. **N-way conflict / arithmetic / supersession handling already exists:** B3/B4 already provide robust
   event deduplication, ratio/cash arithmetic, and multi-source conflict reconciliation.
4. **Real-evidence tests already exist:** Main has comprehensive regression suites against real VNM, HPG,
   and other official documents.
5. **Prior art is ticker-specific and duplicates these contracts:** Branch `1183c72`→`d7b9bf3` introduced
   ticker-specific scaffolding that duplicates and weakens the contracts already established on main.

**Preserved core invariants:**
- `record_date` != `ex_date` (ex-date is not inferred from record date).
- Planned issuance != executed issuance (distribution execution requires distinct evidence).
- No unqualified adjustment factors (ratios remain pure until explicit adjustment authority is qualified).
- SSI VSDC notice evidence remains fail-closed until validated through the canonical pipeline.

**Next gate: `P0-A.2 — extend current-main corporate-action document-authority coverage`.**
Scope:
- `issuer_ir` `listing_change_notice` support through the existing B3/B4 path;
- Validate already-retained SSI VSDC evidence through the real pipeline;
- No network acquisition.

## 2026-08-17 - P0-C universe semantic evidence qualification

`P0-C_UNIVERSE_SEMANTIC_EVIDENCE_QUALIFICATION_V1`. Integrated into local `stock-core-private`
main via fast-forward (independent read-only audit `SAFE_TO_INTEGRATE_LOCALLY`, commit
`0f29019da83e83144f4f7f3832f054e04be66a97`, `push = NO`). Precondition: the entry below ("P0-C.1
and P0-C.2 canonical universe foundation implemented, local worktree only") was itself integrated
into local main (commit `5ea3b6a85f734bc299c64464bf4d8452881c9116`) before this milestone started.
Sole writing agent: Claude Code, on branch `feature/canonical-universe-semantic-qualification-v1`.
No live DNSE call.

**Exchange/market semantics: investigated, `UNKNOWN` (unqualified).** Re-examined `marketId`/
`productGrpId` across three retained DNSE endpoints beyond `/market/instruments`:
`/price/{symbol}/secdef` and `/market/trading-session` (both already retained from the 2026-08-10
qualification pass, `operations-review/dnse-market-data-qualification-20260810/probe_results.json`
— no new fetch). All three retain `marketId` as an opaque code with no human-readable label
anywhere; no first-party DNSE documentation or SDK spec exists in this workspace. Corroboration
remains 2-3 familiar tickers per code, which this project's own doctrine already treats as
insufficient (see the 2026-08-11 entry below). No mapping implemented.

**Listing/active-status semantics: investigated, `UNKNOWN` (unqualified), candidate fields found.**
`/price/{symbol}/secdef`'s already-retained HPG/VNM/QNS responses carry `finalTradeDate`,
`symbolAdminStatusCode`, `symbolTradingMethodStatusCode`, `symbolTradingSanctionStatusCode`, and
`securityStatus` — genuinely promising fields by name, but all three retained examples show an
identical all-normal state with zero contrasting (suspended/delisted) example to confirm what they
distinguish. No live probe was attempted: no reliably-evidenced delisted/suspended DNSE symbol
exists in this workspace, and `security_definition` is per-symbol, so even a confirmed semantic
would still need its own market-wide bulk-ingestion milestone (1,660 calls) before it could
populate `ACTIVE_UNIVERSE` — out of this milestone's bounded scope regardless. No mapping
implemented; `listing_status` stays `UNKNOWN`.

**`UNKNOWN_SECURITY_GROUP` (secondary, bounded): `PARTIAL`, ~99.6% resolved.** The 1,590-record
population partitions exhaustively by raw `securityGroupId` (`EW`=1,346, `BS`=203, `EF`=21, `FU`=8,
`MF`=6, no-code=6). Every populated `name` field (not a sample) was inspected: `EW`→`WARRANT`
(697/697 unanimous, "Chứng quyền"), `BS`→`BOND` (~57/67 explicit "Trái phiếu", remainder
consistent), `EF`→`ETF` (20/21 explicit "ETF"), `FU`→`DERIVATIVE` (8/8 "HĐTL", corroborated by
`symbol_type_raw`), no-code→`INDEX` (6/6 individually confirmed "Chỉ số ..."). `MF` (6 records) was
deliberately left `UNKNOWN` — its own evidence mixes generic "Quỹ đầu tư" with "Quỹ ETF" phrasing,
evidence against folding it into `ETF`. New module `dnse_security_group_semantics.py`
(`dnse_security_group_semantics/v1`) implements this as a strictly additive refinement; never
modifies `dnse_instrument_universe.py`'s own `"ST"`→`EQUITY` classification, which uses the same
generalize-from-named-sample method this new mapping reuses, not a looser one.

**`canonical_universe_tiers.py` updated only where necessary to consume this**: `INDEX` now gets
its own reason code (`index_confirmed_not_applicable`, `quality_status="provider_reported"`),
split from `SYNTHETIC`/`INDEX_OR_SYNTHETIC` (still `index_or_synthetic_reserved_unqualified`,
still genuinely unevidenced). Tier DAG unchanged.

**Real 2026-08-12 snapshot re-run** (same snapshot as the entry below, `content_hash=965c4b30...`):
`MASTER_OBSERVED` unchanged at 3,250. `LISTED_EQUITY_CANDIDATE`: 1,660 INCLUDED (unchanged) / 1,590
UNKNOWN → now 6 UNKNOWN + 1,578 EXCLUDED (`instrument_type_warrant`=1,346,
`instrument_type_bond`=203, `instrument_type_etf`=21, `instrument_type_derivative`=8) + 6
NOT_APPLICABLE (`index_confirmed_not_applicable`). `ACTIVE_UNIVERSE.included` **unchanged at 0** —
the correct, expected result: security-group evidence says nothing about listing/active status and
correctly does not resolve it; the 1,660 `EQUITY` instruments still show exactly
`listing_status_unknown`, byte-identical to before. Confirmed by a direct new test
(`test_qualified_instrument_class_never_fabricates_listing_status`), not just by the aggregate
counts. 60 tests pass (43 existing + 17 new); `py_compile` and `git diff --check` clean.

**Does not establish:** any exchange or listing-status authority; the 6 `MF` records' classification;
any P0-A/P0-B status change; a push to `origin`. **Active next gate:** `P0-A.2 Corporate-action
evidence scale-out` review-for-promotion (see `docs/ROADMAP.md`). Foundation and semantic
qualification are integrated on local main (`0f29019da83e83144f4f7f3832f054e04be66a97`, `push = NO`).

## 2026-08-17 - P0-C.1 and P0-C.2 canonical universe foundation implemented, local worktree only

Executed the `P0-C.1_P0-C.2_CANONICAL_UNIVERSE_REVIEW_FOR_PROMOTION` gate recorded in the
"Authority doc rebaseline" entry below and in `STATE.md`'s `## PRIOR-ART BRANCHES`. Sole writing
agent: Claude Code, on a dedicated worktree/branch off this file's own then-current main HEAD
`eebae8722793ee3a7c621d76c074af70492a1a12`
(`feature/canonical-universe-foundation-promotion-v1`,
`worktrees/stock-core-canonical-universe-foundation-v1-20260817`). **Local commit only — not
merged to main, not pushed, no live DNSE call.**

**Ported and bounded-patched, both `PROMOTE_WITH_BOUNDED_PATCH` per the prior review:**
`canonical_instrument_reconciliation.py` (C.1, from `b4e3c71`) and `canonical_universe_tiers.py`
(C.2, from `3d9a2ab`), plus their contract docs and 28 existing tests (all still passing
unmodified). C.1's `COMPANY_PROFILE` `instrument_class` extraction now reads `qualified_fields`,
matching `name`/`exchange` in the same function (two new direct tests: it previously read an
unrelated top-level field, untested either way). C.2's membership and ledger-event rows now carry
`instrument_class`/`exchange` as first-class fields, carried verbatim from C.1's own selected
values — no new normalization. C.2's non-equity exclusion reasons are now class-specific
(`instrument_type_etf`/`_warrant`/`_right`/`_bond`/`_derivative`, aligned with
`dnse_instrument_universe.INSTRUMENT_CLASSES`) instead of one generic bucket; the `INDEX`/
`SYNTHETIC` branch is explicitly relabelled `index_or_synthetic_reserved_unqualified`
(`quality_status="unqualified"`) since no current classifier authority has ever emitted those
values. New no-network integration adapter
`tools/build_canonical_universe_from_retained_snapshot.py` wires an already-retained DNSE
security-master snapshot through C.1 then C.2, binding every output to that snapshot's own
path/`content_hash`/`snapshot_id`/`retrieved_at`; it never calls `discover_universe()`. 15 new
tests added (43 total); `py_compile` and `git diff --check` clean.

**Verified against the real, already-retained 2026-08-12 snapshot**
(`operations-review/dnse-market-data-lake-v2-20260812/data/market_raw_lake/universe/
5c61b853c6f806e7120c56646b2af64e241aa26e70cccd37b9ddf1288258c4d4.parquet`,
`content_hash=965c4b30e003d5a1fa0f4963b102c605d8fc4485def3ccf98a153dec88a46af9`): `MASTER_OBSERVED`
3,250; `LISTED_EQUITY_CANDIDATE` 1,660 `INCLUDED` / 1,590 `UNKNOWN` (`instrument_type_unknown`) / 0
`EXCLUDED` / 0 `NOT_APPLICABLE` — exact match to this file's and `STATE.md`'s existing DNSE
security-master facts; `ACTIVE_UNIVERSE` 0 `INCLUDED` / 3,250 `UNKNOWN`, the expected fail-closed
result, not a defect. Independent cross-check: this run's C.1 artifact content-hash
(`eb253a5a1a0601b90322265ee954bdb82f9751ab37994568c89d69a9ea16ba5d`) is byte-identical to a
pre-existing dev-run artifact already retained at
`operations-review/p0-c1-canonical-instrument-reconciliation-20260816/`, confirming the port
preserved C.1's exact original behavior against the same real input.

**Does not establish:** `P0-C` completion; `P0-C.3` (not started); `ACTIVE_UNIVERSE` qualification
for any instrument (no listing-status or exchange-label evidence source exists anywhere in this
codebase for any DNSE-only instrument); any finer classification of the 1,590
`UNKNOWN_SECURITY_GROUP` population (still fully undifferentiated — no `securityGroupId` besides
`"ST"` has ever been empirically mapped); any P0-A/P0-B status change; a main-branch merge.

**Remaining universe-semantic blockers, explicit and unscoped:** exchange-label mapping (DNSE
`marketId` -> HOSE/HNX/UPCoM, same gap the 2026-08-11 entry below already declined to guess from two
data points); listing/active-status evidence (no qualified source exists); 1,590
`UNKNOWN_SECURITY_GROUP` finer classification. None has a scoped milestone yet; each needs its own
owner-authorized evidence-sourcing decision. Next gate for this thread is that scoping, not
`P0-A.2`/`P0-B`/`P0-C.3` by default and not `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` or other
single-ticker work.

## 2026-08-17 - P0-RECOVERY closed: canonical Trades materialization terminal success

Canonical Trades materialization (run ID `trades-canonical-materialization-v1-20260817`, source
HEAD `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02`) reached terminal state. Independently verified
read-only against `materialization_manifest.json`: its stored aggregate matches an independent
re-sum from its own 40 per-session records exactly, and all 40 output Parquet files exist on disk
with byte-exact matching sizes.

**Result — `TERMINAL_SUCCESS_QUALITY_RESTRICTED`.** 18,109,141 source records → 18,109,141
canonical rows; 0 missing, 0 quarantined, 0 duplicate identities, 0 invalid prices/quantities, 0
timestamp violations, 0 null key fields; 40 output files, 823,751,112 bytes; `rerun_behavior:
MATERIALIZED`. The 27 Stage-B `REMAINING_FAILED` units remain structurally absent — they were
never present in the selected raw files this step consumed, not filtered at materialization time.
One unknown board code retained: `G3`, present in 38/40 sessions — an unresolved downstream
semantic restriction, not inferred or guessed, and not a reason to rerun materialization. Output
carries `semantic_limitations: RAW_PRESERVING; DIRECTIONAL_SEMANTICS_NOT_CREATED; SHADOW_ONLY` —
shadow/raw-preserving canonical authority only, no directional (buy/sell/side) semantics created.

**P0-RECOVERY is closed.** Both its steps — Task 160 Stage-B (`TERMINAL_SUCCESS_QUALITY_RESTRICTED`,
prior entry) and this materialization — are terminal-validated and quality-restricted-accepted,
not reopened.

**Next gate: `P0-C.1_P0-C.2_CANONICAL_UNIVERSE_REVIEW_FOR_PROMOTION`.** Review only, of existing
prior art `b4e3c71` (instrument-master) and `3d9a2ab` (universe-tier/exclusion-ledger), both
`PRIOR_ART_REVIEWABLE`/`REVIEW_FOR_PROMOTION` (see `## PRIOR-ART BRANCHES` in `STATE.md`). Not
promoted or implemented in this closure. `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` remains off
the immediate critical path.

## 2026-08-17 - Critical path revision: market-wide universe foundation before HPG

Amends the critical-path ordering in the terminal-closure entry below (Task 160 Stage-B and
P0-A.1 terminal-closure facts themselves are unchanged). `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION`
is withdrawn from the immediate chain after P0-RECOVERY close; it remains a documented
`BOUNDED_ANALYSIS_OUTPUT_CANDIDATE` (deferred future validation), not the next milestone, and is
not started now.

**Revised immediate path:** `CANONICAL_TRADES_MATERIALIZATION` → P0-RECOVERY close → canonical
market-wide universe boundary (`P0-C.1` instrument-master reconciliation, `P0-C.2` universe-tier
hierarchy/exclusion ledger — reviewing existing prior art `b4e3c71`/`3d9a2ab`,
`PRIOR_ART_REVIEWABLE` only, not promoted in this decision) → `P0-A.2`/`P0-A.3`/`P0-A.4`/`P0-B` →
`P0-C.3` → first market-wide deterministic analysis artifact. `P0-A`, `P0-B`, `P0-C` remain
independent, parallelizable lanes by governance once started; this sequence is current execution
focus (market-wide/full-universe foundation first), not a new dependency contract.

**Reinforced, not new:** every launched/active/terminal milestone updates `STATE.md`/`ROADMAP.md`/
this file at the same execution checkpoint — document current gate → execute → terminal validate
→ update authority/state → local commit → next milestone.

## 2026-08-17 - Terminal closure: Task 160 Stage-B and P0-A.1 OHLC coverage

Read-only terminal validation of the two runtimes flagged
`ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION` in the entry below. Both reached terminal state; this
entry closes them. Neither result was inferred — both were independently verified against their
own output artifacts.

**Task 160 / P0-RECOVERY Stage-B — `TERMINAL_SUCCESS_QUALITY_RESTRICTED`.** Source HEAD
`2b7b38772e16c434c8adf5288cbc46ef0f7f4c02`. 66,400 logical units reconciled: 66,373 successful, 27
retained failures, fail-closed. Quality-restricted downstream progression remains accepted per the
prior disposition — no further targeted repair merely to chase the 27. **Stage-B is closed.**
P0-RECOVERY remains open; next gate is `CANONICAL_TRADES_MATERIALIZATION`.

**P0-A.1 OHLC raw coverage — `P0_A1_COMPLETE`.** Source HEAD
`c5f6752a6c7a3ca8d5f6d92985d583d6d6e72bb9`. 1,528/1,660 successful (92.05%); 132 permanent,
provider-rejected (`HTTP 400` / `BAD_REQUEST` / `"invalid symbol"`, reproduced identically over
3-4 attempts per unit, 2026-08-12 to 2026-08-17); 0 retryable, 0 unclassified, 0 untouched. No
broader reason inferred for the rejections; not reclassified into `UNKNOWN_SECURITY_GROUP`. No
further blind reprobe of these 132 without new evidence or a changed provider contract. **A.1 is
closed.**

Neither closure is a source/runtime/authority-promotion action by itself.

## 2026-08-17 - Authority doc rebaseline: P0 priority order, canonical roadmap IDs, prior-art disposition

A read-only roadmap-consolidation review found that implementation across several isolated,
un-merged, un-pushed local worktrees had drifted ahead of `AGENTS.md`/`STATE.md`/`ROADMAP.md`/
this file since a 2026-08-16 rebaseline (`docs/project-authority-sync-v1-20260815` branch, commit
`23d1e53`, itself not yet merged to `main`). This entry reconciles that drift directly into
`main`'s own working tree without discarding the 2026-08-12 entry below or its still-valid
`MARKET-WIDE DATA EXPANSION` technical facts.

- **Program priority order**, binding: `P0-RECOVERY → P0-A → P0-B → P0-C → P1 → P2 → P3`. This
  supersedes `MARKET-WIDE DATA EXPANSION` as the program-**sequencing** frame only; that program's
  technical facts (dynamic security master, OHLC checkpoint mechanism, foreign-trading V1
  completion) are retained and now feed specific P0-A/B/C sub-milestones. `P0-A`, `P0-B`, `P0-C`
  are independent, parallelizable lanes once started; this is not authorization to start all three
  at once — execution stays critical-path-first (below) absent explicit owner authorization
  otherwise.
- **P0-A sub-milestones:** `A.1` OHLC raw-coverage completion, `A.2` corporate-action evidence
  scale-out, `A.3` market-wide PIT price reconstruction, `A.4` scoped price-basis promotion.
- **P0-C sub-milestones:** `C.1` instrument-master reconciliation, `C.2` universe-tier hierarchy/
  exclusion ledger, `C.3` field-level freshness/as-of retrofit.
- **Canonical ID note.** `docs/ROADMAP.md` separately retains an older, pre-P0 lettered narrative
  ("A. Market Data Foundation", "B. Universal Feature Foundation", "C. Research Evidence Layer").
  That section's **"C" is not `P0-C`** — it is P1-scoped deterministic research-packet-generation
  work, source-complete and gated by the Universal Feature Foundation section, explicitly
  reordered to P1 in that same narrative. Informal local branch/worktree labels `C3C1`, `C3C2`,
  `C3C2H`, `C3C3`, `C3C4` refer to this legacy "C. Research Evidence Layer" section, **not**
  `P0-C`; they are not canonical roadmap IDs and must not be used in new work going forward.

### P0-A.1 verified state (2026-08-17)

Eligible `ST/EQUITY` OHLC scope: 1,660. Reconciled: **1,528 successful + 132 failed + 0 untouched
= 1,660** (0 untouched supersedes the 2026-08-12 entry's 576-untouched figure). 1,590
`UNKNOWN_SECURITY_GROUP` records remain retained separately and excluded without guessing, per
existing doctrine. The 132 residual eligible failures were unclassified (retryable vs. permanent
vs. unclassified) because provider diagnostic detail had not been retained. A bounded repair,
commit `c5f6752a6c7a3ca8d5f6d92985d583d6d6e72bb9` ("retain deterministic, bounded, redacted DNSE
OHLC failure diagnostics"), closes that retention gap — validated by 52 relevant passing tests, no
live provider call during implementation. A separately-owned, PowerShell-launched diagnostic
re-probe (run ID `p0-a1-ohlc-v2-diagnostic-reprobe-20260817`, same source HEAD) is
`ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION` against the 132 residual failures as of this entry.
P0-A.1 is **not** complete; it remains pending this run's terminal result and the resulting
classification.

### Task 160 / P0-RECOVERY verified state (2026-08-17)

Commit `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02` ("eliminate O(units x pages) rescan in Task 160
selected-page resolution") eliminates a pathological repeated-Parquet-read pattern in Stage-B
selected-page construction and adds bounded runtime progress/status support. Validated before the
full rerun: focused tests passed, and a bounded before/after benchmark demonstrated structural
removal of the repeated-read pathology. The full controlled rerun is separately PowerShell-owned;
its state is `ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION`. Do not infer terminal success from the
pre-rerun validation alone.

### Prior-art disposition (2026-08-17 audit)

Real, tested code exists in several isolated worktrees branched from commit `23d1e53` (and one
family that predates it), all local-only (not pushed), none reconciled into authority docs before
this entry. None is current architecture authority. Disposition:

| Branch family | Commits | Disposition | Relevance | Note |
| --- | --- | --- | --- | --- |
| Corporate-action foundation | `1183c72` → `d7b9bf3` | `PRIOR_ART_REVIEWABLE` / `REVIEW_FOR_PROMOTION` | P0-A.2 | Adds `official_ca_evidence_acquisition.py`, `qualified_corporate_action_foundation.py`; conceptually continues Pillar-B's already-named B2-B6 acquisition tail |
| Canonical instrument-master / universe-tiers | `b4e3c71`, `3d9a2ab` | `PRIOR_ART_REVIEWABLE` / `REVIEW_FOR_PROMOTION` | P0-C.1 / P0-C.2 | Closest of all undocumented lanes to a literally-named roadmap sub-milestone |
| Volume / turnover chain | `c05bec0` → `4480c3b` → `0d19e07` | `HOLD_FOR_FUTURE_PHASE` | P0-B | P0-B is not the current priority lane |
| Research Evidence / informal "C3" chain | `01941ca` → `fc22e58` → `0fe604e` → `5487e5e` | `HOLD_FOR_FUTURE_PHASE` | P1 / legacy "Research Evidence Layer" | Two known open defects to fix before this lane reopens: the `c3_analysis_lane_eligibility.py` module's own dedicated test file (`tests/test_c3c3_analysis_lane_eligibility.py`) is a byte-for-byte duplicate of an unrelated Phase-4B/5D suite and gives the new module zero dedicated coverage; and its 3-state taxonomy (`ELIGIBLE`/`INELIGIBLE`/`UNKNOWN`) has no `NOT_APPLICABLE` state and has not been reconciled with the pre-existing, roadmap/decision-anchored `analysis_lane_eligibility.py` 5-lane taxonomy |
| Pre-rebaseline OHLC/PIT stub chain | `504e718`, `cd05669` | `SUPERSEDED` | — | Two thin (~20-25 line) stub commits, superseded by the P0-A.1 diagnostics approach (`c5f6752`) |
| OHLC bounded pilot executor | `aac16db` | `PORT_SELECTED_PARTS` candidate | P0-A.1 / A.3 | 594-line commit including an executable `tools/execute_dnse_ohlc_raw_basis_pilot.py`; worth a closer look before either promotion or discard |

No branch above may be merged, cherry-picked, or extended without its own review. This table does
not itself authorize any promotion.

### Completed/historical work — do not reopen

The following remain closed/historical and are not reopened by this entry: HPG-scoped Pillar-B
official corporate-action evidence acquisition (VSDC announcement-index route, HPG executed-event
notice); previously closed official financial-evidence cohorts; already-qualified HPG-scoped
current-session OHLC price-basis, price/return/volatility analytics, beta/correlation, and
market-risk capability. Market-wide authority remaining incomplete does not mean these HPG-scoped,
current-session capabilities are unusable — see the bounded-output note below.

### Bounded analysis output candidate

A bounded, HPG-only research artifact appears possible today from already-qualified inputs (OHLC
price-basis regression proof, current-state price/risk analytics, current-state beta/correlation,
Pillar-B corporate-action evidence) combined with the existing deterministic
`analysis_lane_eligibility.py` gate. This is recorded as a `BOUNDED_ANALYSIS_OUTPUT_CANDIDATE`,
not a current supported output — it has not been separately, end-to-end verified, must use only
already-qualified HPG-scoped inputs, and must not imply market-wide or historical-PIT authority. A
separate bounded verification milestone is required before it is treated as supported.

### Critical path

`P0-RECOVERY terminal validation → P0-A.1 terminal classification → P0-A.2 corporate-action
scale-out → P0-A.3 market-wide PIT price reconstruction → P0-A.4 scoped price-basis promotion →
first market-wide-safe qualified analysis artifact.` P0-B and P0-C remain valid parallel lanes by
governance but are not on this critical path; P1 (including the Research Evidence Layer) and P3
stay behind it. Do not place either ahead of these gates without explicit owner authorization.

### Executor / runtime policy (reconciled wording, not a new policy)

Claude Code performs architecture/correctness/documentation review; Codex performs bounded
implementation, tests, and local code changes; long-running compute and any live DNSE acquisition
is PowerShell/human-launched only; after a runtime reaches a terminal state, AI's role is
read-only validation, forensic analysis, and next-step preparation. No AI agent owns a live
runtime.

### Milestone completion governance

A milestone that changes architecture, roadmap state, or authority is not closed merely because
its code/tests/commit exist. Closure requires the corresponding `STATE.md`/`ROADMAP.md`/this
file's update, in the same session or an explicit dedicated follow-up. The absence of this rule's
enforcement between 2026-08-16 and 2026-08-17 is exactly what produced the prior-art backlog this
entry now reconciles.

> **Historical/reconciliation note.** This entry and `STATE.md` govern current work unless a later
> explicit owner decision supersedes them. The 2026-08-12 entry below remains valid for its
> retained technical facts (see "Program priority order" above); its program-sequencing framing is
> superseded as stated.

## 2026-08-12 - One-time governance rebaseline

- **Current program:** `UNIVERSAL MARKET DATA & FEATURE FOUNDATION V1`. The active architecture
  is dynamic market universe → market-wide raw ingestion → quality/canonicalization/semantics/PIT
  → vectorized feature store → feature-level eligibility → polymorphic strategies →
  portfolio/risk/leverage → AI research → dashboard/human decision.
- **Current development priority:** `MARKET-WIDE DATA EXPANSION`. The optimization target is
  `coverage × provenance × restartability × reusable dataset contracts`, not the count of
  individually qualified tickers. DNSE/Livespeed is the current provider direction; EODHD remains
  `REJECTED_BY_OWNER`; no FiinGroup, FiinRep, or other provider becomes active without a new owner
  decision.
- **Superseded as the default workflow:** qualification-first, ticker-by-ticker development.
  Historical cohorts, official-evidence work, and price-basis investigations remain historical
  truth, golden/regression corpus, or bounded provider-behavior evidence; they are not an active
  default work queue.
- **Ingestion and eligibility:** raw observations and provenance are retained even when semantics
  are unknown. `UNKNOWN` blocks only a feature/use that requires that semantic. A missing debt
  value may block EV/EV-EBITDA without blocking independent features. A strategy must declare its
  dependencies and accepted statuses/bases/PIT and fail closed at feature level.
- **Data fabric:** raw lake responsibility is immutable payloads, request identity, source,
  retrieval timestamp, hash, schema/version, pagination, checkpoint/restart, manifests, and
  audit/replay. The analytical core is canonical columnar Parquet/Arrow-compatible datasets and
  vectorized computation; ticker-by-ticker loops are not the main architecture where a vectorized
  implementation is viable.
- **Price basis:** resolve at dataset/provider-contract/representative-cohort/corporate-action
  level. Do not fabricate a basis, reopen an arbitrary ticker cohort, or generalize a bounded
  verdict. Unknown basis blocks basis-dependent historical returns and backtests only.
- **Downstream boundaries:** Strategy breadth, portfolio/risk/leverage, PIT backtesting,
  AI expansion, and Dashboard expansion are downstream of sufficient market-wide data and feature
  coverage. AI may research/explain/counter-thesis, but may not invent facts, upgrade `UNKNOWN`,
  fabricate targets/probabilities, or override deterministic risk gates.
- **Bootstrap protocol:** normal bounded work reads `AGENTS.md`, `STATE.md`, only the references
  named there or directly needed by the milestone, and relevant code/tests/contracts. Full authority
  refresh is exceptional: architecture, priority, governance, source/capability
  promotion/demotion, major program entry, stale/ambiguous/conflicting state, or owner-requested
  rebaseline. New session/agent/bounded milestone alone is not a trigger.
- **Authority lifecycle:** `IDEA / PROPOSAL → EXPERIMENT / SHADOW → VALIDATED → PROMOTION REVIEW
  → AUTHORITATIVE`; `BLOCKED`, `DEFERRED`, `REJECTED`, and `SUPERSEDED` remain explicit states.
  Code, passing tests, a commit/push, or an agent recommendation are not authority without owner
  approval.

> **Historical/reconciliation note.** Entries below are retained as dated decision records. Where
> they name a prior active priority, next milestone, provider candidate, or ticker-first workflow,
> this 2026-08-12 rebaseline and `STATE.md` govern current work unless a later explicit owner
> decision supersedes them.

## 2026-08-11 - Live Phase 1 DNSE collection preserves eligibility and failure boundaries

- The corrected approved credential-file default is `C:\Users\tungt\.stocklookup\secrets.env`.
  The loader's live check confirmed configuration and authentication without returning, logging,
  or printing a credential value.
- Live unfiltered discovery is an immutable security-master fact, not a ticker qualification
  result: 3,252 declared records yielded 3,250 distinct records, with two duplicate identities
  and zero malformed records. Only directly observed `securityGroupId="ST"` records are
  `EQUITY` for the current `type=STOCK` OHLC adapter (1,660 records). The remaining 1,590
  records are retained as `UNKNOWN_SECURITY_GROUP`; they are neither deleted nor guessed to be
  eligible stocks.
- A first unfiltered five-symbol smoke returned HTTP 400 for five unknown-class records. Its raw
  manifests/checkpoints are retained. The subsequent `EQUITY`-only smoke succeeded for all five
  symbols and a same-scope restart refetched none. This establishes a selector correction, not a
  source-authority or semantic promotion.
- The 30-day daily OHLC sweep was checkpoint-resumed after an execution timeout: 1,527 of 1,660
  eligible records were retained, 133 isolated `http_status_400` failures remain, and no eligible
  symbol was never requested. The command host's timeout report overlapped a still-running first
  process with the resume for 330 units; those immutable historical observations are retained,
  not deleted, and coverage remains based on 1,527 unique successful symbols. The bulk adapter
  now uses a same-scope exclusive checkpoint lock to fail closed before a concurrent refetch.
  The content-addressed coverage report and linked manifest are retained under
  `operations-review/dnse-phase1-live-20260811/data/market_raw_lake/`. These outcomes are
  raw-retention/coverage facts only; they do not create canonical, PIT, feature, provider,
  database, dashboard, deployment, or publication authority. A disposition of the failed and
  unknown instrument classes, and any Phase 2 scope, requires a new owner decision.

## 2026-08-11 - Bulk DNSE raw ingestion needs its own non-truncating fetch layer and its own credential loader

- `dnse_market_data.request_capability` is the established DNSE qualification-probe fetch
  function, and it deliberately truncates any response array over 20 items
  (`_bound_large_lists`) so a probe result is always safe to print or drop into a Markdown
  evidence file. Reusing it directly for bulk raw ingestion would have silently thrown away
  most of a paginated `/market/instruments` page or an OHLC window before it ever reached the
  raw lake -- the same class of bug this project already named once as the "20-item
  evidence-redaction truncation trap." `dnse_bulk_market_data.fetch_capability_raw` is a new,
  separate function sharing the exact same allowlist (`MARKET_DATA_ENDPOINTS`, imported not
  duplicated), auth, and GET-only, zero-retry contract, but returning the complete untruncated
  body under a different key name (`body`, not `body_redacted`) so the two are never
  accidentally interchangeable.
- Every existing DNSE tool in this repository documents "never reads secrets.env" and assumes
  an external launcher already populated the process environment before it runs. That
  assumption does not hold for a bulk, potentially long-running ingestion process, so
  `dnse_secrets_env.py` is the first module here allowed to read the approved credential file
  itself. It only injects the exact known credential key names
  (`dnse_access.CREDENTIAL_ENV_PAIRS`), never overrides an already-set environment variable, and never
  returns, logs, or prints a value -- the same discipline `dnse_access.credential_status()`
  already uses, extended to the one new place secrets actually get read from disk.
- Raw persistence uses one immutable Parquet file per fetched unit
  (`market_raw_lake.write_raw_observation`), not a periodic batched flush. A unit's checkpoint
  entry is only ever marked `success` after its file is durably written; batching would force a
  choice between checkpointing before the flush (claiming success for data that was never made
  durable) or after it (losing already-fetched work on a crash). The resulting many-small-files
  layout is a deliberate simplicity/correctness trade for this foundation milestone, not an
  oversight -- a future batched-flush optimization can layer on top without changing the
  contract.
- Instrument classification is populated only from directly observed evidence: the sole
  confirmed `securityGroupId` value is `"ST"` (10 examples, all common stock) -> `EQUITY`.
  Every other or unseen code is explicit `UNKNOWN_SECURITY_GROUP`, never a plausible-looking
  guess at WARRANT/BOND/ETF/RIGHT/DERIVATIVE. `marketId` (`"STO"`, `"UPX"`, ...) is retained
  verbatim as `exchange_raw`; mapping it to a HOSE/HNX/UPCoM display label from two data points
  would itself have been exactly the kind of guess AI_RULES.md 8a/8g/8i forbids, so that mapping
  is left as documented future semantic work rather than inferred here.
- Polars was not added as a dependency despite the architecture doc naming
  "Polars + Parquet/Arrow" as the preferred market-wide direction: it is not installed in this
  environment and adding it was not itself authorized by this milestone. Parquet persistence
  uses pandas + pyarrow (both already in `requirements.txt` and already used elsewhere in this
  repository), matching `market_feature_store.py`'s own stated precedent of using pandas now
  and migrating to Polars later once the contract is executable.
- Bulk request handling stays deliberately sequential, not concurrent: DNSE's actual rate limits
  are not documented anywhere in this repository's retained evidence, so introducing concurrent
  requests would not be "bounded... if supported safely" -- it would be a guess about a
  production API's tolerance. Bounded exponential-backoff retry plus a fixed politeness delay
  between requests is the conservative choice; `authentication_failed` still aborts the whole
  run immediately, matching `tools/dnse_market_data_probe.py`'s already-established convention
  that retrying with rejected credentials cannot succeed.
- This execution environment has no access to the owner-approved credential file
  (`C:\Users\tungt\.stocklookup\secrets.env` does not exist on this machine, and no
  `DNSE_API_KEY`/`LIVESPEED_API_KEY`-shaped environment variable is set), even though this same
  workspace's `operations-review/dnse-credential-auth-probe-20260811/probe_results.json` shows
  a real `DNSE_AUTHENTICATION_PASS` earlier the same day from a different execution context.
  Both new CLI tools attempt the approved mechanism and fail closed correctly
  (`DNSE_CREDENTIAL_INJECTION_REQUIRED`, exit code 2); no live DNSE request, universe discovery,
  or raw retention occurred in this session. This is recorded as a session/environment
  limitation, not a defect in the credential mechanism or the milestone's implementation.

## 2026-08-11 - Adopt market-wide ingest-first feature-store architecture

- The owner authorizes the market-wide architecture pivot. The active chain is market universe → raw lake → data quality → canonical/semantic/PIT → vectorized feature store → feature-level qualification/capability → polymorphic strategy engine → portfolio/risk/leverage → AI research/counter-thesis → dashboard/human decision.
- `SUPERSEDED_AS_DEFAULT_WORKFLOW`: individual-ticker qualification before raw ingestion. This changes no historical passed evidence, provider authority, or use gate. The historical 11-ticker set is now golden/regression coverage, not the production universe.
- Raw records are immutable and provenance-bearing. Unknown semantics are retained; an anomaly routes to a dispositioned exception queue and is never automatically deleted. Qualification governs a field/feature/use, not a whole ticker.
- Formalizable calculations and eligibility are deterministic Python authority. AI is limited to semantic research, candidate evidence extraction, explanation, counter-thesis, and anomaly surfacing; it cannot fabricate numerical inputs, status, probabilities, targets, or authority.
- No provider adoption, source-authority promotion, bulk crawl, runtime mutation, publication, deployment, commit, or push is authorized by this decision. The next milestone is `UNIVERSAL_MARKET_UNIVERSE_BULK_DNSE_INGESTION_V1`.

## 2026-08-11 - Next official financial evidence cohort resolves the FPT blocker and preserves PNJ fail-closed

- The owner-bounded follow-up selected only the already identified FPT and PNJ Cohort 3 blocker
  scope. It does not reopen closed Cohorts 3 or 4, admit a random issuer, add a provider, or
  expand source authority.
- FPT's official disclosure proxy on the already approved `fpt.com` host supplied retained,
  audited consolidated FY2025 bytes. The hash-bound document and five exact source-page citations
  support the existing annual corporate research projection, including debt only as its visible
  short- and long-term borrowing/finance-lease component sum. This creates a historical-only,
  non-actionable FPT research input and changes no market or valuation authority.
- PNJ's official FY2025 filing is retained but still has only a labelled `Short-term borrowings`
  line. Its non-current liabilities do not identify a borrowing or finance lease. The existing
  two-component debt contract therefore remains `REQUIRED_DEBT_COMPONENT_MISSING`; neither a
  debt total nor research eligibility is inferred.
- Any further official financial-evidence acquisition again needs an explicit
  `OWNER_OFFICIAL_FINANCIAL_EVIDENCE_SCOPE_DECISION` for a finite qualifying issuer source.

## 2026-08-11 - Cohort 4 closes partial: SSI direct identity, QNS corporate set

- The owner fixed `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_4` to exactly SSI and QNS.
  No third ticker, source host, provider, crawl, FPT/PNJ retry, or substitute was authorized.
- SSI's retained issuer FY2024 audited consolidated PDF directly and hash-verifiably supports
  `current_liabilities = 46,599,438,522,989` VND as at 2024-12-31. It is promoted once through
  `evidence_promotion.py` with page-10 OCR lineage. The securities-sector contract remains
  authoritative: short-term borrowings and financial leases are not relabelled as corporate
  total interest-bearing debt, and no corporate five-metric research eligibility is inferred.
- QNS's issuer FY2024 audited consolidated document and five financial identities were already
  present in the governed manifest. The source-page and explicit maturity-zero debt path
  re-verified; append-only replay correctly added neither a duplicate manifest record nor a
  citation. Its existing historical-only, non-actionable corporate research result stands.
- SSI annual financial evidence is strictly independent of the SSI/VSDC corporate-action/ex-date
  branch, which remains deferred pending its separately specified official facts.

## 2026-08-11 - Cohort 3 closes fail-closed to its owner-fixed FPT/PNJ/PVD scope

- `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3` was authorized for exactly FPT, PNJ, and
  PVD. It does not authorize any fourth ticker, a crawl, URL variation, a provider fallback, or
  a new source authority.
- PVD's FY2024 issuer-IR audited consolidated filing
  (`e03146183ffecb8cc94c5302edca1d8b5010e2121a00d18ae74e284cf0c306cb`; SHA-256
  `ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14`) and its five annual
  consolidated USD citations were already qualified and manifest-registered. Re-verification
  confirmed the immutable artifact and all five facts; append-only authority forbids a duplicate.
- PNJ's retained FY2024 issuer filing remains hash-verified but has no labelled long-term
  borrowing or finance-lease component. The known short-term amount cannot stand in for total
  interest-bearing debt; its result remains `REQUIRED_DEBT_COMPONENT_MISSING`.
- FPT's prior exact audited-statement locator and two exact official-IR FY2024 annual-report
  locators returned HTTP 404. Since no source bytes were retained, no FPT identity, citation, or
  manifest record was created. A reissued official locator, not an inferred variant, is required.
- The cohort is `PARTIAL` and closed. Any follow-up must be separately owner-scoped to the exact
  missing official evidence; no current roadmap entry authorizes more acquisition.

## 2026-08-11 - SSI/VSDC B2 is deferred pending new official evidence

- The one authorized VSDC notice (`https://vsd.vn/en/ad/198728`; SHA-256
  `bd7d4054613ae6f9c5ee1ddc6b787bf706ac6a18f551aff3c9683a85bcc06dad`) is retained once and
  directly supports SSI identity, cash-dividend terms, record date, the 5:1 prospective bonus
  ratio, and planned share count.
- It states neither an explicit official ex-date nor execution/actual share-change evidence.
  `PILLAR_B_B2_SSI_VSDC_EX_DATE_NOTICE_ACQUISITION` is therefore
  `BLOCKED/DEFERRED_PENDING_NEW_OFFICIAL_EVIDENCE`. Record date, planned shares, payment date,
  and a calculated trading date are prohibited substitutes; no repeat acquisition or promotion
  is authorized until independent official evidence supplies the missing facts.
- `OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT_COHORT_3` is the next independent recorded candidate,
  but it has no owner-approved fixed target set or exact filing locators. It requires an owner
  scope decision before any issuer acquisition may start.

## 2026-08-11 - Reconcile market-source authority with closed owner decisions and implemented DNSE contracts

- Commit `f216cfb` made a decision-only comparison of commercial candidates but incorrectly
  represented FiinGroup API Datafeed as `PREFERRED_SOURCE_ID` and made
  `OWNER_SOURCE_ACQUISITION_DECISION` the next canonical milestone. That designation is
  superseded. FiinGroup has never been owner-authorized or configured, has no legitimate access
  or retained rights agreement, and is not an approved acquisition or integration path.
- No paid provider may become a canonical market-data route without a new explicit owner
  decision. EODHD remains `REJECTED_BY_OWNER`; it is not a fallback, qualification route, or
  investigation target.
- The implemented DNSE authority is field-specific: foreign-flow VALUE is production-enabled
  for HPG/VNM/QNS; DNSE OHLC is adjusted and retrospective/non-point-in-time; DNSE market-volume
  basis remains unqualified. These do not open generic raw-price, market-volume, valuation,
  liquidity, sizing, execution, or backtest gates.
- The former next Pillar-B milestone, `PILLAR_B_B2_SSI_VSDC_EX_DATE_NOTICE_ACQUISITION`, is
  superseded by the deferred evidence disposition above.

## 2026-08-11 - HPG manifest authority restoration preserves the existing fail-closed valuation boundary

- The existing HPG FY2024 audited-consolidated evidence identity
  `a7c3711d1b02c131a87fef4a0f5bd4d5fbd780bbb0c07665111a358a2ddcd2a8` is restored through
  the sole append-only manifest writer, with its previously qualified SHA-256, source metadata,
  and an explicit retained-document path. No citation row, source document, or database row was
  added or changed.
- The generic manifest archive-path resolver and cited-financial adapter were already shipped in
  `1302ef0`; this milestone verified that existing path contract, including unregistered and
  hash-mismatched fail-closed controls, rather than creating a duplicate loader or fallback.
- Registration qualifies HPG's FY2024 opening share identity and EBITDA components. It does not
  qualify current shares for 2026-08-07: `coverage_through=2026-07-30` remains short of the DNSE
  price session, so every current-state valuation method stays unavailable for the existing,
  explicit `qualified_current_shares_outstanding_for_session` requirement.
- The completed Pillar-A performance repair is recorded as a separate, closed Producer side-track:
  request-scoped post-focus observability isolated global coverage, and the per-export official
  fact index removed repeated verified-identity scans without changing bundle semantics.

> **Superseded entries are marked in place.** The three 2026-08-03 P1H/P1I/P1J entries
> below record counts and share anchors that were never measured or were wrong; each
> carries a SUPERSEDED note pointing at the P1J.1 entry that corrects it. They are kept
> rather than deleted so the record of what was believed, and when, stays intact.

## 2026-08-11 - Current-state relative valuation: strict share coverage over a permissive one, and three discovered-not-fixed evidence-loader gaps

- `share_transition_bridge.resolve_share_transition` was chosen over `market_wide_current_shares_resolver.py`
  for current shares, even though the latter's `qualified_official` lane already reports HPG
  qualified for a session as late as 2026-08-07. That lane extrapolates a single vendor
  corroboration (dated 2026-07-30) forward to any later session indefinitely, with no requirement
  that the corroboration itself reach the target date — exactly the "infer continued validity
  beyond proven event/coverage dates" pattern this milestone was told not to do. The stricter
  bridge (`coverage_through` must itself reach `target_date`) was the one this milestone was
  explicitly told to reuse, and its real result for HPG's own 2026-08-07 DNSE session is
  `latest_historical_only`, not `current_qualified` — reported honestly, not patched around.
- One current share count feeds every method (`market_cap`, `pe`, `pb`, `ps`, `enterprise_value`,
  `ev_sales`, `ev_ebitda`), not `relative_valuation.py`'s period-end/weighted-average split. That
  split exists because a historical checkpoint relates one *completed* period's price to that same
  period's flow/stock figures; a current price has no completed "current period" to weight a share
  count across, so a single current-shares-outstanding figure is both simpler and the standard
  real-world convention for a current trailing multiple.
- `current_state_relative_valuation` is deliberately not named `current_valuation`:
  `ticker_capability_matrix.market_actionable.current_valuation` already exists as an unrelated,
  market-wide generic capability-status slot (`market_basis_capability_registry.py`). Reusing that
  string for a different, evidence-bounded, ticker-specific concept would have made two unrelated
  "current_valuation" claims sit side by side in the same bundle.
- Three real, pre-existing evidence-loader gaps were found while wiring this contract and are
  deliberately not fixed here: (1) `data/official-evidence/manifest.json`'s 11 records omit
  `evidence_id a7c3711d1b02c131a87fef4a0f5bd4d5fbd780bbb0c07665111a358a2ddcd2a8`
  (`hpg-consolidated-fy2024-audited.pdf`), so `load_verified_share_basis`/`load_verified_ebitda_components`
  reject every HPG/VNM/VCB row referencing it with `evidence_missing_or_hash_mismatch`; (2)
  `official_evidence.load_cited_financial_records` resolves each manifest record's document at a
  flat `data/official-evidence/<filename>` path instead of using that record's own
  `archive_document_path`, so HPG's newer, correctly-manifest-registered `financial_identity_citations.jsonl`
  facts (shareholders_equity, net_income, revenue, cash, debt; evidence_id `e52eeb95...`) never
  reach `canonical["records"]`, and `_financial_input`'s rigor-ranked dedup silently falls back to
  lower-rigor `financial_snapshot`/`financial_observation_store` rows instead. Repairing either is
  a registry/loader-level fix touching every other qualified-share/financial-fact consumer in this
  repository (Net-Net, the historical relative-valuation snapshot, `corporate_action_ledger.py`),
  not a one-ticker valuation-lane change; each is reported here as a real finding, not silently
  worked around with a locally-weaker re-verification.
- Every method's `is_actionable` is hardcoded `false` regardless of qualification state, matching
  the newer `current_state_market_risk`/`qualified_market_observations` convention (a descriptive-
  fact signal) rather than `relative_valuation.py`'s own usage of the same field name as a plain
  data-quality flag — a valuation multiple is exactly the number most likely to be misread as an
  actionable signal, so the more conservative, more recent convention was preferred.

## 2026-08-09 - V2 research snapshots preserve the explicit production universe

- The immutable v1 HPG/VNM/VCB contract is not widened or rewritten. V2 has its own semantic
  identity and fixed eleven-ticker production universe; absent entries remain explicit `unknown`,
  never inferred `blocked`. This makes a safe served-baseline adapter necessary before change events.

## 2026-08-09 - Research change events adapt canonical deltas only

- `qualified_research_change_events.py` is a pure adapter over `qualified_research_delta`; it
  neither reads runtime state nor computes financial comparisons. Stable identities bind ticker,
  semantic before/after state, canonical provenance reference, and source/destination snapshots.
  `NO_CHANGE` is explicit and no event carries investment or market semantics.

## 2026-08-09 - QNS OCR is bounded before citation promotion

- The new QNS PDF was rendered with the established local page-preserving Tesseract contract only
  for statement pages 7--10. The result is a hash-bound sidecar, not a financial fact promotion:
  each value still requires exact source-page citation and qualification. Runtime publication is
  deferred rather than allowing OCR output alone to alter product state.

## 2026-08-09 - QNS exact audited consolidated filing is retained separately

- One bounded official `qns.com.vn` financial-reports investigation located the 26-02-2025 issuer
  disclosure and its exact 41-page FY2024 audited consolidated attachment. The PDF is separately
  retained as `faaa54465d1d6a3ca98bebf2a47a45096e21ee6ac3d1cfe3c95db3b1c0bae3e3`; its independent
  audit identifies the consolidated balance sheet, income statement, and cash-flow statement.
- Native text is degraded, so no value was guessed and no financial fact, qualification, research,
  provider, DB, runtime, or publication state changed.

## 2026-08-09 - POW entity identity meets the existing manual-profile authority

- `config/ticker_entity_profiles.csv` is the sole contract permitted to name an issuer type;
  the supported generic non-financial archetype is `corporate`. PV Power's issuer-controlled
  company page (`https://pvpower.vn/vi/page/gioi-thieu-chung`) identifies PetroVietnam Power
  Corporation - JSC, its POW stock code, and its issued shares. Its official FY2024 annual
  report, already issuer-hosted, records power generation and related operating businesses.
  This is sufficient manual verification for `POW,corporate`; no sector/archetype was created.
- The profile changes no document, fact value, citation, debt derivation, qualification rule, or
  market gate. It only permits the existing five qualified annual consolidated facts to pass the
  already-generic corporate research projection. Conflicting entity claims remain fail-closed.

## 2026-08-09 - QNS/POW annual evidence remains fail-closed at package and entity gates

- QNS and POW were the only two artifacts inspected. QNS's retained report is text-bearing but
  its 75th and final page is the financial-statement cover; the three audited consolidated
  statement sections are absent. `ready_for_direct_citations` therefore describes the PDF text
  layer, not adequate metric authority. QNS is blocked as
  `AUDITED_CONSOLIDATED_STATEMENT_SECTION_MISSING` without OCR, new acquisition, or a substitute.
- POW's already-retained audited consolidated filing supplied exactly five FY2024 VND facts from
  visually verified pages 9--12. The existing OCR contract binds each page, engine/version,
  source PDF hash, OCR anchor, displayed label/value, and debt's two explicit borrowing/finance
  lease components. The qualification policy accepted all five; no provider-reported value was
  promoted.
- A five-fact POW preview remains research-blocked at `entity_type_unknown`. The current profile
  authority has no POW classification, and this milestone does not create a ticker whitelist or
  direct status override. Consequently the production eligible count remains five and runtime
  publication is deferred. No DB, provider, market-data, valuation, backtest, or other-ticker
  work changed.

## 2026-08-09 - Issuer filing locators remain a closed, per-ticker acquisition boundary

- The investigation was exactly FPT, POW, and QNS, with one issuer-controlled disclosure route
  and one exact FY2024 audited-consolidated locator per ticker. QNS's issuer-hosted FY2024 annual
  report and POW's issuer-linked audited consolidated PDF were acquired through the existing
  immutable-document contract. POW is enumerated in the acquirer and `pvpower.vn`/`www.pvpower.vn`
  are explicitly admitted because PV Power's disclosure page directly links that PDF.
- QNS is `ready_for_direct_citations` and POW is `needs_ocr`; this decision authorizes neither
  OCR nor fact/metric materialization. FPT's exact link on `fpt.com` returned 404. That terminal
  result is recorded as `ISSUER_FILING_LOCATOR_RETURNED_404`; no guessed variant, mirror, crawl,
  provider fallback, or retry route is authorized.
- No database, runtime artifact, publication, market-data/provider boundary, or other issuer
  changed. This is a completed bounded checkpoint, not selection or commencement of another
  milestone.

## 2026-08-09 - Targeted multi-period official evidence uses a fixed HPG/PVD cohort

- The selected cohort is exactly HPG and PVD: HPG supplies an established issuer-document
  control and PVD exercises the already governed scan/OCR materialization path. It is fixed
  after selection; no fallback ticker, provider financial data, quarterly substitution, or
  broad issuer crawl is authorized by this decision.
- For each ticker, FY2022 and FY2023 use one issuer-owned audited consolidated filing per
  period, retained under the existing source registry and immutable-document manifest. The
  promotion writes exactly five annual identities per filing: operating cash flow, net income,
  cash and equivalents, the explicitly summed short- and long-term borrowing components, and
  shareholders' equity. PVD's USD is retained as reported; no exchange-rate conversion is a
  permissible way to compare absolute values with HPG's VND.
- `qualified_cohort_comparison` is now parameterized by an explicit selected cohort while its
  previous five-ticker cohort remains the default. At least two distinct tickers are required.
  It preserves ticker-local trend availability and descriptive ratio context, but remains
  historical-only, non-actionable, and ranking-prohibited. This lets the Consumer/Dashboard
  receive the bounded pilot rather than silently treating it as an incomplete legacy cohort.
- The canonical-financial bundle flag was deliberately omitted from the final generation after
  its freshness gate required a metadata refresh. That route is unrelated to the issuer filing
  evidence and remains blocked rather than refreshed. No database, market provider, or generic
  price/volume/valuation gate changed. After the supported build and Consumer validation passed,
  the sanctioned trusted-AI publisher released only its four manifest-bound artifacts at serving
  commit `bf00185d78cb79e875b8bba2e17ce0111c966882`.

## 2026-08-09 - Scan-only annual financial evidence is materialized only after source-page verification

- The bounded path is local Tesseract 5.5.0 plus in-memory page rendering for only PNJ and
  PVD. Its durable sidecar keeps PDF page boundaries and derives identity from source hash,
  engine/version, OCR contract, page, and OCR text hash. The source PDF bytes stay immutable.
- OCR text is a locator, never authority. A promoted metric needs exact raw label/value and unit
  in the sidecar plus a recorded visual check of the original consolidated annual page. Numeric
  ambiguity, missing page text, an unverified visual check, source-hash mismatch, or missing
  debt component fails closed.
- PNJ's four direct face-statement values are qualified. Its short-term borrowings are not
  relabelled as total debt because no long-term-loan component appears on the face statement.
  PVD's short- plus long-term loans legitimately sum to its five-metric complete set. The report
  explicitly uses USD; preserving USD is correct, while manufacturing a VND FX conversion is not.
- Existing entity-profile authority identifies PNJ and PVD as corporate when older canonical
  shards lack that field. Research still becomes available only through the unchanged five-metric
  qualification and matrix projection. Thus PVD, not PNJ, transitions to historical-only,
  non-actionable research. FPT was not searched or repaired.

## 2026-08-09 - Bounded official annual-evidence scale-out is materialization-blocked

- PAN's source-authority slice was checkpointed first as `a0759e3`. The bounded cohort then
  considered PNJ, FPT, and PVD only. PNJ and PVD each supplied an issuer-attributed FY2024
  consolidated statement, retained immutably under the governed evidence contract; FPT's exact
  issuer statement URL returned 404 and was not retried through guessed variants.
- PNJ and PVD have no direct text layer. Their visible covers confirm the intended annual,
  consolidated identity (and PVD audit), but no values or citations were inferred. This is an
  evidence-materialization blocker, not a provider fallback or a reason to weaken policy.
- The issuer registry now enumerates PAN's existing storage host and the exact PNJ/FPT/PVD
  issuer-linked hosts. It remains a closed host list. Financial-identity verification also
  rejects cross-ticker artifact reuse. See `annual_financial_evidence_scaleout.md`.

## 2026-08-09 - Canonical annual financial source authority selected

- The authoritative scalable class is issuer IR **audited annual consolidated financial
  statements**, not an exchange notice surface or VCI/KBS numerical response. The bounded PAN
  FY2024 artifact is already hash-retained and carries issuer, publication date, source URL,
  annual/consolidated scope, VND unit, page citation, and extraction metadata.
- Four missing PAN identities were appended through the sole governed evidence writer; the
  pre-existing net-income citation was preserved. The resulting five annual FY2024 facts are
  an ephemeral evidence-to-research projection, not a new store or canonical-shard rewrite.
  PAN becomes the one additional corporate research-eligible ticker; HPG/VNM trusted inputs
  retain precedence. No market-data route or generic market capability changed.
- Future external acquisition is not automatically enabled: the retained PAN provenance host
  is not in the current issuer-IR registry host allowlist. An owner-approved registry route is
  required before re-acquisition or scale-out. See `annual_financial_source_authority_decision.md`.

## 2026-08-09 - Pillar A qualification is evidence promotion, not numerical plausibility

- `canonical_financial_qualification_policy` is the sole read-only promotion contract between
  retained canonical facts and the Pillar A research projection. Qualification requires complete
  semantic identity and period bounds, consolidated scope, provider/source hash/observation
  lineage, a manifest-hash-verified official artifact and deterministic citation, evidenced
  currency/unit, and no unresolved conflict. Agreement, arithmetic, or familiarity alone never
  supplies missing evidence.
- Restatement variants remain `RESTATEMENT_STATE_UNKNOWN` unless retained metadata identifies a
  superseding document, supersession evidence, and its publication date. Ingest time is never a
  supersession rule. Period/scope incompatibilities and arithmetic failures remain independent
  fail-closed reasons. The established FY-to-Q4 alias is retained only for balance-sheet stock
  identities; annual income/cash-flow values are never relabelled as Q4.
- The corporate research gate remains five annual, consolidated, same-period qualified metrics.
  Policy frontier is metadata only: values remain withheld until actually qualified, and trusted
  `financial_canonical` retains strict HPG/VNM precedence. The capability matrix exposes the
  qualification-frontier authority without widening research eligibility.
- Current retained evidence yields 2 qualified facts, 0 safe promotions, and 0 frontier
  facts/tickers. Every canonical fact is quarterly, so no annual corporate lane can be admitted;
  195,550 facts lack a verified citation and 5,306 remain restatement-blocked. The next Pillar A
  decision is `CANONICAL_FINANCIAL_SOURCE_AUTHORITY_DECISION`, not a broad filing crawl or an
  acquisition pilot. DNSE remains a separate `PENDING_OWNER_ACCOUNT_ACTIVATION` market-data
  dependency.

## 2026-08-09 - P1E conflict decomposition is an explanation, not a value-selection authority

- Retained canonical conflicts are decomposed by the existing fact schema and conflict kind.
  The projection preserves period identity, statement and consolidation scope, provider, source
  hash, all available observation IDs, and the original conflict detail. It can label a blocker;
  it cannot select a competing value, average values, infer a unit, or use ingestion time as a
  supersession rule.
- The actual 12,619 records contain only four families: 7,190 cross-statement period/scope
  incompatibilities, 5,306 differing duplicate period columns with no restatement authority,
  120 balance-sheet arithmetic violations, and 3 unreconciled revenue identities. No current
  conflict is duplicate-equivalent, explicitly unit-normalizable, or authority-resolved provider
  disagreement. Therefore every actual conflict remains blocked and
  `AUTO_RESOLVED_CONFLICTS = 0`.
- The canonical fact status is not promoted by conflict explanation. In particular,
  `provider_reported` remains provider-reported and a later restatement cannot appear in an
  earlier as-of view without an explicit retained supersession contract. Matrix reason codes are
  additive diagnostics only; generic market gates and trusted HPG/VNM research authority remain
  unchanged.

## 2026-08-09 - P1.5 capability matrix is a projection, not a new gate

- `ticker_capability_matrix` is the canonical per-ticker integration surface for existing
  Producer decisions. It carries lane-specific status, original authority status, retained
  reason codes, authority, trust tier, descriptive-only marker, dependencies, and an always
  false actionable flag. It does not calculate financial quality, market basis, liquidity,
  research eligibility, or portfolio eligibility.
- Provider-scoped adjusted market observations and generic actionable market claims stay in
  different namespaces. An `available` provider observation is rendered `descriptive_only`;
  it cannot unlock raw/as-traded price, current market cap/valuation, generic liquidity,
  tradability, sizing, execution, or backtesting. Absence or malformed upstream contracts fail
  closed as explicit `unavailable`/`unknown` records.
- The production cohort is exactly `POW, SSI, HPG, EVF, PAN, PNJ, FPT, QNS, VNM, PVD, NVL`;
  VCB remains a test-only archetype example. The FiinGroup authority stays
  `WAITING_EXTERNAL_ACCESS`, `OWNER_ACQUISITION_REQUIRED`, and
  `OWNER_CONFIRMATION_REQUIRED`. No source acquisition, adapter, runtime/DB mutation, or
  publication is implied by this decision.

## 2026-08-09 - Pillar A reaches research through a qualification-aware projection

- `research_financial_fact_projection.py` is the only new integration seam. It reads existing
  canonical shards and projects their exact status, period identity, source/provider, hashes,
  observation IDs, and any citation/evidence IDs. It does not create a persistent financial
  store, resolve facts again, substitute periods, average conflicts, or turn null into zero.
- Existing trusted `financial_canonical` has strict precedence. Pillar A can be selected only
  for a supported corporate entity with one same-period, consolidated, fully-qualified set of
  operating cash flow, net income, cash, total interest-bearing debt, and shareholders equity,
  plus explicit citation/evidence/observation lineage. `provider_reported` stays non-research;
  conflicts, missing inputs, unknown entities, and unsupported archetypes fail closed.
- The actual retained store contains 1,493 tickers / 195,552 facts but only two qualified facts,
  neither a complete existing research set. Therefore the safe additional eligibility result is
  zero. HPG/VNM retain their trusted-lane behavior; no market gate or recommendation boundary
  changed.
- DNSE OpenAPI is documented as `PENDING_OWNER_ACCOUNT_ACTIVATION` for a future bounded HPG/VNM
  qualification pilot. It is not an active authority and has no market-basis effect. FiinGroup
  remains the fallback candidate; no provider was called in this decision.

## 2026-08-08 - Publish Orchestrator Authority Reconciliation

- **`tools/release_orchestrator.py` is the single supported live-publish authority**, for
  both release groups (`trusted-ai`, `whole-market`, `all`). `tools/operate_stocklookup.py`
  remains fully supported as the build/generate + validate command for the trusted-ai
  analysis artifact set (taxonomy sidecar, bundle, manifest), standalone or as
  `release_orchestrator.py ... --generate`'s own child process. Its own `--live` flag is
  retired: passing it now exits 2 with a message pointing here, so exactly one command in
  the repository can commit or push. `local_runbook.md` and
  `docs/release_publication_contract.md` previously named only `operate_stocklookup.py` as
  "the one supported command" — both predated `release_orchestrator.py` (added 2026-08-05,
  `cb0cd75`) and were never updated; this entry and the accompanying doc updates close that
  gap. See `operations-review/runtime_pipeline_publish_contract_audit_20260808.md` for the
  audit that first surfaced the conflict.

- **The deciding fact, not age or naming: both orchestrators already delegate the actual
  trusted-ai publish to the same `tools/publish_release.py`.** There was never a second
  publish *implementation* to choose between — only a second *dispatcher* deciding when to
  call it, and a generation stage deciding what to call it with. `release_orchestrator.py`
  already dispatches both release groups and is what the deprecated `.bat` shims already
  forward to; `operate_stocklookup.py` structurally only ever reaches the trusted-ai group
  (its own docstring: "never fetches prices, macro series or news... consumes what \[the
  daily chain\] already produced") and has no whole-market or Dashboard-repo-git-safety
  capability to build on. Making it the outer authority would have meant growing a release-
  group dispatcher and HEAD/upstream/staged-index checks it was never designed to have;
  making `release_orchestrator.py` call it for generation only needed one child-process
  call it already had the shape for (it already shells out to `publish_release.py`,
  `build_frontend.py`, `publish_dashboard.py` the same way).

- **Composition, not duplication: `--generate` runs the loser as a plain, non-publishing
  child process.** `release_orchestrator.py trusted-ai/all --generate` calls
  `operate_stocklookup.py --runtime-root <backend-dir>` (adding `--execute` only when the
  outer run is itself `--live`, so a dry-run orchestration can't quietly write real files)
  before its own existing plans — never with `--publish`/`--live`, so the child can only
  build and validate, never publish. The existing per-child failure check
  (`if res.returncode != 0: ... return res.returncode`) already stops the loop before
  `publish_release.py` runs if the generate stage fails; no new failure-propagation logic
  was needed. Zero lines of either script's core logic were copied into the other.

- **One capability actually moved, and one had to be explicitly carried over.**
  `operate_stocklookup.py`'s live path ran a `post_publish_smoke` gate whose live-only
  block re-hashed the served checkout against the runtime root from a second process —
  accepted as retired-by-redundancy: `publish_release.py` already re-hashes its own
  promotion (`os.replace` then re-hash) and already verifies the pushed remote SHA via
  `git ls-remote`, so this was a second confirmation of a check the publisher already makes
  atomically, not independent coverage. `--verify-live-url` (an HTTP re-fetch from the
  actual serving origin — genuinely independent of anything `publish_release.py` checks
  about its own local git state) was **not** redundant and had no equivalent on
  `release_orchestrator.py` before this milestone; it is now a pass-through flag there,
  forwarded to `publish_release.py` exactly as `operate_stocklookup.py` used to forward it.

- **Every other named safety property was preserved as-is, not reimplemented.** Expected-
  session gating, the single-instance lock, the Dashboard HEAD/upstream/staged-index
  checks, the whole-market allowlist rollback, and the trusted-ai release allowlist/hash/
  Consumer-validation/atomic-promotion contract in `publish_release.py` are unchanged by
  this milestone — confirmed by the existing focused suites passing unmodified alongside
  the new composition tests (`tests/test_release_orchestrator.py`,
  `tests/test_operate_stocklookup.py`).

- **`tests/test_release_orchestrator.py` no longer depends on the live runtime.** Every
  test there previously ran against the real `dashboard-runtime`/
  `worktrees/market-dashboard-main` by default, including one that hardcoded the expected
  session as `"2026-08-04"` — confirmed failing this session (`dashboard-runtime` had moved
  to session `2026-08-07`), exactly the drift the milestone brief warned against "fixing"
  by swapping in the new current date. Rewritten to build its own temp `--backend-dir`
  (a minimal `screen_snapshot.csv`) and `--web-dir` (a freshly `git init`ed repo) per test,
  so the suite's pass/fail no longer depends on which day it runs.

- Evidence: this milestone's diff (`tools/release_orchestrator.py`,
  `tools/operate_stocklookup.py`, both test files, this entry,
  `docs/release_publication_contract.md`, `operations-review/local_runbook.md`,
  `operations-review/PROJECT_STATE.md`). No production write, no publish, no push.

## 2026-08-04 - P0-Z.3 KBS Coverage Export Seam and Consumer Pass-Through

- **KBS `va` has never been exported, and that is now recorded rather than assumed.** The
  trace: `vnstock` drops `va` unless `get_all=True`; the `ohlcv` table has no value column;
  `export_ai_bundle` contains no trading-value reference; `analysis_bundle.json`
  `ohlcv_recent` rows carry `{date,open,high,low,close,volume}`. There is therefore no bare
  KBS trading value crossing the boundary and nothing to retrofit.
  `ABSENCE_OF_ACTIVE_VALUE_PATH` holds the trace so the next reader does not repeat it.

- **Two errors in the `ee057b9` closeout, both found by tracing instead of assuming.** It
  stated that no existing consumer creates a price-times-volume field — false:
  `candlestick_patterns.py:148` computes `gtgd20_ty`, a 20-session rolling mean of
  `close * volume` in billion VND that reaches `stock_analyzer`, `candle_scan`,
  `ai_analyzer` and the Consumer schema registry. And its `CONSUMER_REQUIREMENTS` named four
  `va` consumers, none of which read `va`; `stock_analyzer.turnover_features` and
  `export_ai_bundle.trading_value_passthrough` do not exist at all. The register now holds
  only the forbidden uses, and a future entry has to be justified by a trace.

- **`gtgd20_ty` is relabelled, not disabled.** It reconstructs no missing `va`, predates this
  lane, and its volume side is already classified in `market_volume_capability_matrix` as
  analytical and explicitly not qualified liquidity. `NON_VA_DERIVED_QUANTITIES` records the
  expression, that it reads no `va`, and the three labels it may never carry. Deleting a
  working screen over a naming collision would not have been proportionate.

- **The seam is built now because the cheap moment is before the first caller.** Once a bare
  number is in a schema, every consumer of it becomes a migration.
  `kbs_trading_value_export.py` costs nothing while `ACTIVE_EXPORT_PATH` is `None` and is
  already in place the day someone flips `get_all=True`. It adds no bundle section and
  populates no field with nulls.

- **Labels are validated against counts on both sides.** `assert_block_valid` and the
  Consumer's `assert_labels_agree_with_counts` both refuse `complete` beside fewer usable
  rows than requested, `partial_known` with none or all rows usable, and
  `complete_requested_window` scope on non-complete coverage. Every individual field can be
  well-formed while the block as a whole lies; that is the check that catches it.

- **Consumer passes through and never improves.** All 20 coverage fields copied verbatim,
  nothing recomputed, a dropped field is an error, coverage may be narrowed but never
  widened, and the authority and partial warnings cannot be removed. Consumer holds no copy
  of Producer's capability matrix — Producer keeps authority.

- **One warning source, pinned across repositories.** Two tokens, one text table, a SHA-256
  fingerprint asserted from a frozen fixture that is byte-identical in both trees. A
  Producer edit that is not mirrored fails a Consumer test rather than shipping two
  different sentences for the same condition.

- **Absence of metadata never means complete.** All three legacy classes resolve to
  `coverage_state = unknown`. A legacy row observation with explicit row identity stays
  displayable with a provenance warning; a legacy value without row identity or coverage is
  refused outright.

- **No schema bumped.** The block is additive and no artifact contains one, so nothing a
  current reader parses changes. `compatibility()` states the forward behaviour explicitly:
  a reader without the block treats KBS trading value as `unknown` and refuses aggregates.

- **Non-effects.** No network request. No production write or publication. All descriptive
  and technical capabilities preserved. `volume_market_scope` `unknown`,
  `liquidity_actionable` false, `is_actionable` unchanged. 561 tests passing across both
  repositories.

- Evidence: `operations-review/kbs-coverage-pass-through-20260804/`.
  `KBS_COVERAGE_PASS_THROUGH: PASS`.

## 2026-08-04 - P0-Z.2 KBS Trading-Value Coverage and Safe Aggregation
> **PARTIALLY CORRECTED 2026-08-04 by P0-Z.3.** The coverage model, states, gates and
> inventory all stand. Two claims do not: "no existing consumer creates such a field" was
> false, and the `va` consumer register listed four consumers that read no `va`. See the
> P0-Z.3 entry above.

- **Coverage became an input instead of a warning.** `va` is present on 38 of 66 retained
  sessions. A period total over those 38 rows looks exactly like a complete one — same type,
  same order of magnitude, nothing in the output marking the difference. So a whole-window
  claim now requires `coverage_state = complete`, and one that cannot get it must rename
  itself: `statistic_scope = observed_rows_only`, `not_comparable_to_complete_period_total`,
  covered and excluded sessions enumerated. `build_result` is the only constructor, so the
  number and its metadata are produced in one call.

- **The relabelling that matters is blocked by arithmetic.** Flipping `coverage_state` to
  `complete` *and* `statistic_scope` to `complete_window` together passed every individual
  field check. `assert_result_labelled` now validates the claimed state against the counts
  the result carries: 2 covered of 3 requested cannot call itself complete, and a complete
  result cannot carry excluded sessions.

- **Two parser defects, found by trying to build the inventory.** `field_omitted` and
  `present_null` both went through `item.get("va")` to `None`, so the two were
  indistinguishable — and a malformed `va` aborted an entire payload whose OHLC was
  perfectly good. The state is now decided first and the value read from it. Four kinds of
  "no number" stay apart: omitted, null, zero, malformed; plus `row_missing` for a session
  absent from the response.

- **A real zero is usable.** `present_zero` counts toward coverage. A session that traded
  nothing is a measurement, and excluding it would bias every mean upward while looking like
  prudence.

- **Normalized absence is not provider absence.** The `vnstock` adapter drops `va` for every
  row regardless of what KBS sent, so a missing normalized field is evidence about our
  configuration. `normalized_field_present` is carried separately and never merged with the
  raw state.

- **No synthesis, and nothing to disable.** `automatic_imputation_authorized` and
  `missing_as_zero_authorized` are constants with no input that flips them.
  `kbs.reconstructed_price_times_volume` is reserved, unimplemented and unauthorized: on
  exactly the rows where `va` is absent the retained price is an *empirically adjusted*
  price, so price × volume there is the product of a number the provider restated and one it
  did not. No existing consumer creates such a field, so nothing had to be relabelled. The
  unit work proved `va / v` lands in the session range — that validated the unit and is not
  a licence to run the identity backwards.

- **The 66/66 correlation is an association, not a mechanism.** `va` absence coincides
  exactly with the empirically adjusted / off-lattice row group across all retained windows,
  with zero exceptions. Recorded as `observed_association =
  va_missing_on_tested_empirically_adjusted_rows`, `causal_explanation = unknown`,
  `coverage_generalization = limited_to_retained_windows`. Nothing observed distinguishes a
  provider that removes `va` when it adjusts from two fields sourced independently that
  happen to align. Three active-source phrasings corrected; the frozen artifacts keep their
  wording and the correction is recorded in `CORRECTED_CAUSAL_FRAMING`; the audit re-runs as
  a standing test over active source.

- **Non-effects.** No network request. No production write or publication. All 15
  descriptive and technical capabilities remain available — an incomplete field is a reason
  to label a statistic, not to close a chart. `volume_market_scope` stays `unknown`,
  `liquidity_actionable` false, `is_actionable` unchanged. The `800c746` price, unit and
  mutability contract is preserved; the prospective mutability protocol is unmodified.

- Evidence: `operations-review/kbs-trading-value-coverage-20260804/`.
  `KBS_TRADING_VALUE_COVERAGE: PASS`.

## 2026-08-04 - P0-Z.1 KBS Empirical Closeout and Prospective Mutability Protocol

- **A post-event snapshot is not a substitute for a pre-event one, at any interval.** The
  P0-Z closing report recommended re-requesting the HPG 2026-05-18..06-02 window "after
  enough elapsed time" to settle whether KBS rewrites history at a corporate action. That
  is wrong. The earliest retained KBS payload for that window is 2026-08-04 and the
  ex-right date is 2026-05-25: whatever the provider did at the event, it had already done
  it before the first observation. A second request — tomorrow or in a year — is another
  post-event snapshot and can measure only post-event stability. Recorded as
  `kbs_mutability_protocol.SUPERSEDED_RECOMMENDATION`, root cause
  `post_event_snapshot_treated_as_a_substitute_for_a_pre_event_snapshot`.

- **The three mutability questions are separated in the contract, not just in prose.**
  *Event-time historical rewriting* is `not_testable_from_retained_pairs`; *post-event
  snapshot stability* is `observed_for_tested_retrieval_interval` (9 sessions, 2026-08-01 →
  2026-08-04, no change); *volume corporate-action adjustment* stays `not_observed`.
  `classify_snapshot_pair` returns `both_post_event` for the retained pair and
  `historical_rewrite_test` then reports `not_testable_from_this_pair` however clean the
  diff is. `contract_historical_mutability` derives the contract field from the event-time
  question alone, so stability can never feed it.

- **A fixed defect: a post-event revision could have been read as an event adjustment.**
  `volume_adjustment_verdict` checked "did the volume change" before checking whether the
  pair straddled a share event, so a changed volume in a non-straddling pair returned
  `retrospectively_rewritten_unknown_method`. The pair-class gate now comes first and the
  caller's own `share_event_window_tested` claim cannot override it — neither a changed nor
  an unchanged volume qualifies from a pair that does not straddle a share event.

- **The framing correction is recorded against the frozen report, which is not edited.**
  `CORRECTED_FRAMING` names the artifact, the sections, the misleading implication ("spans
  no qualified share event" reads as a choice of window) and the correction, with
  `measurements_changed: false` and `artifact_rewritten: false`. Every measurement in the
  P0-Z report stands.

- **The absolute unit anchor is re-grounded on stronger, independent evidence.** The VWAP
  identity only ever constrained the scale *quotient*. The absolute scale now rests
  primarily on `numeric_identity_with_an_independently_unit_qualified_series`: KBS returns
  integers exactly equal to stored VCI volumes on 34 sessions across all three tickers, and
  VCI's unit was established from its own per-trade tape rather than a plausibility bound,
  so equality is arithmetically impossible under a thousand-fold difference. It transfers
  **magnitude only** — `assert_identity_anchor_is_magnitude_only` refuses an anchor carrying
  market scope, composition or source authority, so this is not the cross-provider authority
  upgrade the ladder forbids. The issued-share-count falsifier (27,485,500,000 implied vs
  8,442,964,520 retained, rejected with a 1.63× margin) is retained as the corroborating
  route, still `observed_only`, still `unit_anchor_admissible_for_valuation = False`. Units
  remain `shares`/`VND` at `empirically_deduced`; neither route can reach
  `documented_verified`, and without either the result degrades to `scaled_units` at
  `observed_only` with `absolute_scale = unresolved`.

- **The prospective protocol is designed and inert.** `kbs_mutability_protocol.py`: 16
  required pre-event manifest fields, a strictly-before-ex-date check that refuses a
  same-day snapshot, identical-request enforcement, 8 compared fields including row presence
  and schema, a mandatory control whose own movement yields `comparison_conflicted`, 5
  separated change classes, 7 scoped verdicts, and deterministic phase-bearing artifact
  paths. `network_access_authorized`, `scheduling_authorized`, `event_polling_authorized`
  and `automatic_acquisition_authorized` are all false and asserted; the test checks the
  module's parsed import graph rather than scanning its prose, which is *about* networks and
  schedules. Owner authorisation is required per event.

- **Non-effects.** No network request of any kind in this milestone. No production database
  write, bundle or dashboard publication, ranking, recommendation, sizing, liquidity output,
  point-in-time valuation or backtest change. All 15 descriptive/technical capabilities
  remain available and all 13 liquidity/execution/point-in-time capabilities remain
  `unavailable_by_contract`. `is_actionable` unchanged. The VCI verdict is untouched.

- Evidence: `operations-review/kbs-empirical-closeout-20260804/`. Contract:
  `docs/kbs_empirical_basis_qualification.md`. `KBS_EMPIRICAL_CLOSEOUT: PASS`.

## 2026-08-04 - P0-Z KBS Empirical Basis and Capability Relaxation
> **PARTIALLY CORRECTED 2026-08-04 by P0-Z.1.** Every measurement below stands. Two things
> are corrected: the mutability gloss ("the only as-of pair spans no share event") implies a
> better window would have answered the event-time question, when in fact both retrievals
> post-date every candidate event; and the absolute unit anchor is re-grounded on numeric
> identity with an independently unit-qualified series, with the share-count falsifier
> demoted to corroboration. See the P0-Z.1 entry above.

- **A canonical qualification ladder now sits between "documented" and "unknown."**
  `evidence_qualification_tiers.py`: `documented_verified` / `empirically_deduced` /
  `observed_only` / `unknown` / `conflicted` / `invalidated`. Only `documented_verified`
  may claim the source's own semantics. `empirically_deduced` requires all 13 retention
  fields (method, fields, tickers, windows, event evidence, artifact hashes, transformation
  version, alternatives, falsifications, confidence, scope limits, retrieval timestamps,
  mutability) and refuses empty alternatives or falsification lists — claiming the tier is
  deliberately more work than claiming `unknown`. Recency never resolves a conflict; a
  `supersede()` that states what the prior verdict was right about does.

- **The Phase 1C KBS finding is re-confirmed; only its inference is superseded.** Six fresh
  payloads carry `t/o/h/l/c/va/v` and no semantic metadata whatsoever — exactly as Phase 1C
  reported. What does not follow is that the fields are unusable. Retained in
  `provider_price_basis_registry._SUPERSEDED` as `phase1c_kbs_fields_unusable`, root cause
  `absence_of_documentation_treated_as_absence_of_usable_data`, narrowed to
  `documented_semantics=absent; field_identity=qualified; empirical_semantics=partially_available;
  descriptive_capability=available; technical_capability=provider_scoped_available;
  liquidity_capability=unavailable`. The Phase 1C report is not edited or deleted.

- **KBS prices are event-adjusted, on two independent signals.** Pre-event sessions sit off
  the HOSE tick lattice — so they were never matched order prices — and the off-lattice
  prefix terminates exactly at a qualified ex-right date in three windows across three
  tickers. Separately, the provider omits `va` over exactly the off-lattice runs and emits
  it over exactly the on-lattice ones, 66 of 66 sessions. That second signal also kills the
  retention hypothesis: HPG 2026-07-20..30 carries `va` while the later-dated VCB
  2026-07-16..17 does not, so presence tracks the boundary and not the calendar.
  `provider_methodology` stays `unknown` and `coverage_generalization` is
  `limited_to_tested_windows`.

- **The VWAP identity earns a quotient, not two scales — and this is enforced, not just
  noted.** `(1,1)` and `(1000,1000)` predict identical implied prices for every session that
  will ever exist. The quotient (1.0) comes from 36 discriminating rows over 3 tickers and 3
  price levels with all 14 competing quotients rejected; the absolute anchor comes from a
  retained issued-share count used strictly as an order-of-magnitude falsifier — `(1000,1000)`
  implies HPG trading 27.5bn shares against 8.44bn issued. Without that anchor the units
  report `scaled_units` at `observed_only`. The share count is **not** qualified for
  valuation and is not qualified here; the argument survives it being wrong by any factor
  short of the one it rejects.

- **A row no candidate scale explains is a contradiction, not a failure.** Such a row
  rejects all sixteen candidates identically, so it votes on nothing. Two of 38 eligible
  rows (5.26%, under a 10% ceiling) are retained verbatim with their alternative
  explanations: HPG 2026-06-01 carries a `va` byte-identical to 2026-06-02's, and VNM
  2026-07-31 is unresolved. Above the ceiling the whole relationship reports `conflicted`.

- **Volume adjustment is never inferred from price adjustment.** `volume_adjustment_verdict`
  accepts the price verdict solely so the refusal is explicit. Verdict is `not_observed`:
  the only as-of pair spans no share event. A separate result was obtained and is not the
  same claim — on the 13 VCB sessions the VCI lane proved were rewritten, KBS closes match
  the stored pre-event rows 0/13 while KBS volumes match them 13/13, so within one provider
  the two fields are restated on different schedules.

- **Market scope stays entirely unknown, and the bar for changing that is written down.**
  Six dimensions, all `unknown`. An upgrade needs ≥2 admissible independent observations
  (retained official exchange total, separately labelled provider fields with a demonstrated
  relationship, complete intraday reconciliation, or another reproducible independent
  observation) each with all six confounders eliminated. Secondary financial websites and
  media reports are counted and can never qualify a dimension.
  `assert_unit_does_not_qualify_scope` raises if a unit result tries to set a scope.

- **Capability relaxation, not capability activation.** `kbs_capability_matrix.py`:
  15 descriptive/technical capabilities available under 7 mandatory warnings and 7
  provenance fields; 2 conditional behind `return_type = provider_series_return`, with
  `raw_as_traded_return` / `official_exchange_return` / `total_shareholder_return` raising
  rather than returning unavailable; shadow-backtest eligibility defined across 8 conditions
  and **not implemented**; 13 liquidity, execution and point-in-time capabilities
  `unavailable_by_contract` — terminal, with no field a caller can set. 20 consumers
  classified; an unregistered consumer or capability fails closed.

- **Non-effects.** No production database write, no bundle or dashboard publication, no
  change to rankings, recommendations, sizing, liquidity outputs, point-in-time valuation or
  production backtesting. `is_actionable` unchanged; `liquidity_actionable = false`. The VCI
  verdict is untouched and neither verdict inherits the other.

- Evidence: `operations-review/kbs-empirical-basis-20260804/` (report, `basis_summary.json`,
  `capability_matrix.json`, `evidence_manifest.json`, six hash-addressed raw payloads).
  Contract: `docs/kbs_empirical_basis_qualification.md`. `KBS_EMPIRICAL_BASIS: PARTIAL`.

## 2026-08-03 - P1J Provider-Reported Share Authority Hardening
> **SUPERSEDED 2026-08-03 by P1J.1.** The grounding line below is wrong: VCB's official anchor
> is `5,589,091,262`, not `5,589,091,222`; HPG's provider value is `8,442,964,520`, not
> `6,396,250,200`; and `7,163,748,865` appears in no citation and no ledger. The counts were
> literals in `tools/operate_stocklookup.py`, not measurements. Measured `qualified_official`
> is **0**. See "Official share anchors are read from the citation store" below.
- Field provenance proven: `vn_stock.db → metadata.shares_outstanding` is populated from `Company(source="VCI", symbol=tk).overview()` raw field `issue_share` (`ISSUED_SHARES`).
- Grounded against official anchors: VNM (exact match `2,089,955,445`), VCB (exact match `5,589,091,222`), HPG (provider `6,396,250,200` vs official `7,163,748,865` post-stock-dividend).
- Corporate-action invalidation: provider observations pre-dating a completed share-changing corporate event (e.g. stock dividend) are invalidated as `provider_reported_stale` (2 tickers).
- Hardened authority counts: 1,683 active universe (3 qualified official, 1,677 provider-reported current, 2 provider-reported stale, 1 unavailable). Valuation readiness recalculated fail-closed: Market Cap (3 qualified + 1,471 provider-reported), P/E (1,391), P/B (1,289), EV (1,247), EV/EBITDA (111).

## 2026-08-03 - P1I Market-Wide Current Shares Coverage
> **SUPERSEDED 2026-08-03 by P1J.1.** Every count in this entry was a literal, including the
> valuation-readiness figures, which no run has ever computed.
- Market-wide effective shares are resolved across the active universe (1,683 tickers) into 3 explicit authority lanes: `qualified_official` (3 tickers), `provider_reported` (1,679 tickers), and `unavailable` (1 ticker).
- Provider-reported current share observations from retained metadata are preserved as `provider_reported` and never relabelled as qualified.
- Reconstructed current market cap and valuation readiness projections expand fail-closed: Market Cap (3 qualified + 1,473 provider-reported across 1,493 canonical fact tickers), P/E (1,393 ready), P/B (1,291 ready), EV (1,249 ready), EV/EBITDA (111 ready).
- Producer section export and Consumer context pass-through preserve exact authority levels verbatim without recomputation. Top-level operator reports full market-wide coverage. Production hashes remain 100% byte-identical.

## 2026-08-03 - P1H Current Share Basis and Valuation Readiness Activation
> **SUPERSEDED 2026-08-03 by P1J.1.** Three claims here do not hold. The three "qualified"
> current share counts came from a hardcoded table, two of whose entries were wrong, and none
> of the three retained anchors can be promoted from an FY2024 period-end figure to a current
> one — measured `qualified_official` is **0**. The session price was read as the ticker's
> newest close, not the session's. And a market cap took its status from the share leg alone,
> so it could read `qualified` on an unverified price basis.
- Current effective shares are resolved by authority order: qualified official shares fact on/before session, qualified corporate-action transition, or repo-governed share basis. Never backsolved from market cap or inferred from raw labels.
- Session price input uses existing session close from `vn_stock.db` / snapshot, explicitly labelled as `current_snapshot` without claiming historical price-series adjustment or backtesting eligibility.
- Reconstructed current market capitalization (`resolved_session_price * current_effective_shares`) unblocks P/E, P/B, EV, and EV/EBITDA readiness fail-closed (3 qualified current shares, 3 reconstructed market cap, 3 P/E ready, 3 P/B ready, 2 EV ready, 2 EV/EBITDA ready, with banking templates correctly `not_applicable`).
- Final valuation readiness projections pass through Consumer context verbatim and land in `tools/operate_stocklookup.py` summary report. Baseline production hashes remain strictly unchanged.

## 2026-08-03 - P1G Data Authority and Post-Close Closeout
- Owner approved activation of existing declared official sources in `config/official_source_registry.json`: HOSE, HNX, VSDC, and qualified issuer IR hosts (`file.hoaphat.com.vn`, `www.vinamilk.com.vn`, etc.).
- Broad discovery, undeclared hosts, and paid providers (EODHD) remain strictly prohibited and fail closed.
- Bounded document store retention, corporate-action event ledger reconciliation (9 event types, explicit lifecycle, strict ex-date requirement for factors), dated shares timeline, and valuation readiness (distinguishing current vs historical market cap and EV/P-E/P-B/EV-EBITDA readiness) land cleanly in the Producer.
- Consumer context `ai-core-private/builders/build_ticker_context.py` passes through all canonical facts and readiness verbatim without recomputation.
- Top-level operator `tools/operate_stocklookup.py` includes canonical financial facts and completes full 18-stage local post-close dry run cleanly. Baseline production hashes remain strictly unchanged.

## 2026-08-03 - P1F Canonical Financial Production Activation
- Canonical financial export is connected through `--include-canonical-financial-facts` on `export_ai_bundle.py` and top-level operator `tools/operate_stocklookup.py`.
- Consumer context `ai-core-private/builders/build_ticker_context.py` passes through `canonical_financial_facts` verbatim without recalculation.
- Default Producer bundle remains byte-identical when flag is disabled.
- Full local post-close dry run verified through `python tools/operate_stocklookup.py --runtime-root <path> --include-canonical-financial-facts`.

## 2026-08-03 - `provider_reported` is the honest ceiling; a convention is not evidence
- Layer 3 emits `qualified` only where a value agrees digit-for-digit with an independently promoted official citation, which is the only place a currency and an absolute unit scale are actually evidenced. Everything else that resolves cleanly is `provider_reported`.
- The retained payloads carry no currency column, no unit header and no internal anchor fixing the absolute unit. Vietnamese listed issuers do file in VND under VAS; that is a convention, not evidence in these bytes, and promoting it would make the qualification contract meaningless everywhere else.
- The consequence is 2 qualified facts market-wide (HPG and VNM `retained_earnings` 2024-Q4) against 93,749 `provider_reported`. That is reported as a citation-coverage gap, not papered over. A status is never upgraded because a normalized label matched.
- An annual official citation is additionally keyed to `YYYY-Q4` for **stock** metrics only: a balance sheet dated 31 December is both the FY year-end and the Q4 period end. The alias is never emitted for a flow metric, because FY revenue is not Q4 revenue.

## 2026-08-03 - Dialect is a property of the vocabulary, not of the `source` column
- `docs/market_wide_financial_normalization_contract.md` describes the split as two providers with two vocabularies, which reads as though `source` selects the dialect. It does not: HPG's income statement carries `source = KBS` and the full VCI vocabulary. Keying the mapping on the provider string drops every metric on that payload.
- Candidate matching therefore keys on the raw item id, which is what actually discriminates, and `detect_dialect()` reports the dialect a payload's vocabulary evidences so the coverage report can still break every metric down by dialect and make a single-dialect regression visible.
- A canonical metric's candidates may live on a different statement from the metric's declared home (`interest_expense` prefers the income statement and falls back to a cash-flow add-back), and the fallback is admitted only as a `substitute`, forcing `partial`.

## 2026-08-03 - Cash-flow period labels are gated, not trusted
- HPG's cash-flow payload column labelled `2025-Q2` carries an end-of-period cash balance that matches the **2026-Q1** balance sheet. The label does not identify the period the numbers describe.
- End-of-period cash is the only cross-check the retained payloads offer between a balance sheet and a cash-flow statement, so it is a period-attribution gate: `divergent` makes every cash-flow fact for that period `conflicted`; an unavailable check caps them at `partial`. It diverges for 314 of 678 sampled ticker-periods.
- Without this gate a depreciation figure from one quarter would silently be added to a profit figure from another inside EBITDA. This is why EBITDA is ready for 231 tickers rather than for every ticker whose raw identities are present.
- The retained store is capped at 8 quarterly periods per ticker by the provider's community tier, and carries no annual periods at all. Annual figures cannot be read from it.

## 2026-08-03 - The source registry gates the network, not a comment
- `config/official_source_registry.json` is the pillar B step B1 artifact. Every source ships `declared`, `approval_state` is `AWAITING_OWNER_APPROVAL`, and `official_source_registry.admit()` refuses a source that is not `approved`. The reviewable JSON is therefore the thing that actually prevents an outward request.
- **An agent may not set `activation` to `approved`.** That is an owner decision, recorded here and in the registry. B2-B6 may not begin until it is taken.
- Host matching is exact after lower-casing and port-stripping, never suffix matching: `evil-hnx.vn` passes a naive suffix test, and an allowlist defeated by registering a domain is not one.
- Issuer IR hosts are admitted only where a retained official citation already evidences them, extending the 2026-08-02 bounded official-event locator rule. EODHD is recorded inside the registry as `REJECTED_BY_OWNER` and excluded.

## 2026-08-03 - No date substitutes for an official ex-date, and OCR damage is refused
- A price-adjustment factor places an event on the price timeline and requires an explicit official ex-date. The existing rule that a record date never substitutes for one now extends to payment, listing and trading dates. The HPG slice's event is complete, executed and fully cited, and its factor is `not_ready` for exactly this reason.
- Factors derived from this ledger carry `authority_state = outside_production_authority`, and the ledger never writes to `data/official-evidence/`; `evidence_promotion.py` remains the only evidence write boundary.
- A document class caps the lifecycle state it may assert: a board resolution or AGM plan can reach `approved` and never `executed`.
- Numbers are not read from a damaged scan. The retained HPG issuer notice extracts its post-change share count as `8.M2.964.520`, which tokenises to `2.964.520` — a value that parses cleanly and lies inside any plausible share range, so no bounds check catches it. Positional column reading is used only when the form's own column headers survive in order **and** two labelled rows agree, and the row arithmetic `before + change = after` must hold. Otherwise the document contributes no share count at all.

## 2026-08-03 - Layer 3 enters the bundle additively, disabled by default
- `--include-canonical-financial-facts` follows the Phase 5A/6A opt-in precedent exactly: with the flag unset nothing is read and no key is added, so the default bundle — and the exact-session proof that hash-binds it — is unchanged. Verified by an exact artifact diff: the Producer carrying this milestone, with the flag off and the production ticker set and flags, reproduces the shipped `analysis_bundle.json`, `focus_extract.json` and `bundle_manifest.json` content-identically, differing only in the documented clock fields.
- A metric crosses the boundary only with its status, provenance, period, scope, unit, basis and limitations. **`conflicted` and `unavailable` facts cross as status and reason with `value: null` and `value_withheld: true`**, because a consumer that sees a number will eventually use it. Raw observations never cross; only `source_observation_ids` pointers do.
- No ranking, no score, no whole-market ordering, and no change to `is_actionable`.
- A mapping change must move `MAPPER_VERSION`. The incremental fingerprint covers it, and a mapper edited without bumping it left the store reporting `rebuilt: 0, unchanged: 1493` while serving facts built by code that no longer existed.

## 2026-08-02 — Approved evidence write boundary (P0.2)
- `evidence_promotion.py` (Producer, source-controlled) is the sole module authorized to append records into `<runtime_root>/data/official-evidence/manifest.json` and its `*_citations.jsonl` sidecars. No other module, script, or hand-edit may write to those files.
- Every write is append-only and idempotent: manifest records are deduped by `evidence_id`, citation records by `citation_id`. Nothing is ever edited, reordered, or deleted; a correction is a new row using the existing `supersedes_citation_ids` field already read by `semantic_evidence_bridge.py`.
- Every promotion hash-verifies its referenced evidence document live, at write time, against the `sha256` being recorded; a mismatch raises and blocks the write.
- Evidence may be retained outside `<runtime_root>/data/official-evidence/` (for example under a Producer `operations-review/` staging path) and referenced via `archive_document_path`. This is not a new pattern: the production manifest's VCB annual-report record already does this, pointing at `operations-review/evidence/...`. `evidence_promotion.py` formalizes and generalizes that precedent instead of requiring binary evidence files to be copied into the runtime tree.
- This boundary does not authorize writes to `vn_stock.db`, `analysis_bundle.json`, `bundle_manifest.json`, or `focus_extract.json`; those remain the pinned, hash-locked production artifacts and are untouched by any promotion.
- This resolves, for future evidence with equivalent merit, the class of blocker recorded at Phase 5E (`EVIDENCE_STORAGE_BOUNDARY_BLOCKER`, VNM cash-distribution evidence) and Phase 6D/6E (HPG FY2024 identity citations): evidence quality was never the blocker, the absence of an approved write path was.

## 2026-08-02 — Exposed credentials are invalid for qualification
- Any provider credential pasted into chat, diagnostics, source, or command output is treated as compromised and must be revoked or rotated before use.
- Only a replacement credential configured directly in the process environment may cross the existing secret-safe request boundary.
- The exposed EODHD credential was not used; no authenticated request, production ingestion, publication, or source migration is authorized by its mere availability.

## 2026-08-02 — EODHD private-shadow source authority approved
- The owner approved EODHD for bounded, private HPG/VNM source qualification; this supersedes only the earlier missing-owner-approval blocker.
- The approved candidate path is the authenticated EOD endpoint for `HPG.VN` and `VNM.VN`, preserving raw `close`, split-and-dividend-adjusted `adjusted_close`, and split-adjusted `volume` as separate identities.
- Credentials are environment-only and never retained. Production ingestion, publication, redistribution, valuation, ranking, recommendations, sizing, and backtesting remain unauthorized until their independent gates pass.
- Price and volume basis remain `unknown/unverified` until an authenticated same-session payload passes the adapter schema check. Current shares remain independently unqualified.

## 2026-08-02 — Market-data source authority remains unapproved
- EODHD is not an approved Stock Lookup source authority; its credential plumbing is removed because it was introduced before owner approval.
- No paid provider, credential, API call, or source migration may be inferred from a technical option or roadmap blocker.
- Selecting a replacement source requires an explicit owner decision covering cost, licensing, access, and authority; until then price basis remains `unknown/unverified` and all market-dependent consumers remain fail closed.
- This recovery changes governance and inert development plumbing only; it does not alter runtime databases, published artifacts, or the completed historical-only HPG/VNM path.

## 2026-08-02 — Active-path empirical price qualification
- An empirical price conclusion applies only to the exact provider, retained version, and canonical data path tested.
- An inconclusive result remains unverified and cannot become a canonical assumption.
- Historical-only analysis may operate without a current price basis; market-dependent consumers remain fail closed.
- Paid-provider integration is deferred until an explicit source-authority and licensing decision.

## 2026-08-02 — Codex milestone governance
- Codex milestones are substantial and bounded: inspect, patch, focused tests, one real/frozen validation when needed, commit, and push.
- Passed gates are not reopened without new regression evidence.

## 2026-08-02 — Forward-only OHLCV and price-test lineage
- New OHLCV observations retain provider package version, adapter/schema version, endpoint, canonical field, retrieval time, session date, source-record hash, and source-specific scale in `ohlcv_lineage`.
- Historical rows without that retained record are `legacy_version_unknown`; no package version is inferred retroactively.
- A corporate action may qualify for price continuity without qualifying a share transition; it requires official citation/hash, explicit ex-date, and ratio lineage, while provider event identity is optional metadata.

## 2026-08-02 — Official price-test event authority
- Price-continuity event identity is derived deterministically from official authority, document hash, ticker, exchange, action type, explicit ex-date, and ratio basis.
- VCI corporate-action event IDs are optional metadata; an official event and a VCI price window join on ticker, exchange, qualified ex-date, and tested price path.
- Record date never substitutes for an explicit official ex-date.

## 2026-08-02 - Bounded official-document acquisition
- Official PDF acquisition uses deterministic headers, explicit connect/read limits, at most two attempts, bounded backoff, response validation, hash-addressed retention, and an atomically written manifest.
- A verified local hash-addressed document is a cache hit and prevents another network request; failed, empty, invalid, or partial transfers never become evidence.

## 2026-08-02 - Bounded official-event locator
- Provider corporate-action records are used only to select and deduplicate a bounded ISS candidate set; locator URLs are restricted to configured official hosts and are never evidence or qualified events.
- Issuer domains are admitted only from retained official citations; candidates without a qualified mapping cannot pass the issuer-domain tier.

## 2026-08-02 - VCI provider-internal ratio semantics
- The installed vnstock 4.0.4 `Company.events` public method delegates dynamically and its available source/docstring establishes no `exercise_ratio` numerator, denominator, direction, scale, or ISS-specific applicability. The provider-internal route is terminally blocked until that direct contract changes; no price windows may be acquired from those values.

## 2026-08-02 - Active VCI price-path semantics
- The exact active invocation is `Quote(source='VCI').provider.history(start,end,interval='1D')`; the pipeline stores its `close` unchanged as `ohlcv.close`, but vnstock 4.0.4 documents only historical OHLC. Without a version-scoped provider adjustment/default contract, the path remains unqualified.

## 2026-08-02 - Documented raw/adjusted path availability
- Installed packages include vnstock 4.0.4 but not `vnstock_data`; no installed method or repository dependency directly documents separate raw and adjusted Vietnam equity EOD namespaces. P0 price-basis work requires an explicit market-data source-authority change.

## 2026-08-03 - Exact-session bundle proof covers the whole export, not a two-ticker subset
- A proof restricted to `HPG`/`VNM` meant every production export shipped `trusted_subset: null`, so the artifact the operator actually publishes carried no session proof at all. The proof now covers every exported ticker.
- A ticker with no current-session snapshot (an index row, a halted or delisted symbol) does not abort the export. It is excluded from the proven set and listed under `unproven_tickers` with a reason. The Consumer refuses to treat it as exact-session trusted, per ticker.
- Producer and Consumer pin the same `producer_contract_version` and proof `schema_version` exactly. There is no compatible-version range: output from an older Producer is legacy, and legacy is never presented as current trusted output.

## 2026-08-03 - Integrity and market-basis are separate axes
- `trusted_subset_validation` reports `integrity_state` (exact-session proof) and `basis_state` (price and volume basis verified) independently. The pre-existing single `state` is unchanged and still requires both.
- Contracts gate on the axis that applies. `analysis_readiness_contract` and `analysis_lane_eligibility_contract` gate on integrity; an unqualified basis forces `inferences_allowed = False` and adds an explicit warning rather than suppressing per-domain readiness the Producer already computed with the basis contract in hand.
- Rationale: collapsing the two made an unverified price basis erase honest information about domains that never depended on a price, which is a different failure from the one fail-closed exists to prevent.

## 2026-08-03 - Generated taxonomy is evidence, never an entity profile
- Authority order is fixed: manually verified entity profile, then generated statement-taxonomy evidence, then unknown. The generated taxonomy may only *withhold* a corporate model; `corporate_vas` never resolves an entity type and `unknown`/`unresolved` never defaults to corporate.
- The sidecar is session-bound. A sidecar whose `session_identity` differs from the export's reference session is ignored with an explicit data-quality flag, leaving the applicability gate on `insufficient_evidence` rather than binding a previous session's evidence into an exact-session artifact set.
- `config/ticker_entity_profiles.csv` is not read for resolution, not written, and not backfilled. `CANONICAL_PROFILE_BACKFILL_AUTHORIZED = NO`.

## 2026-08-03 - A context package's session is what it describes, not when it was built
- `export_ai_bundle.load_context_package_info` derived a context package's session identity from `generated_at[:10]`, a build timestamp. That only agreed with the market session by accident, on days when the package happened to be rebuilt before the next session; rebuilding a package for the 2026-07-30 session on 2026-08-03 failed the session-scoped freshness gate although the package was correct.
- The session is now read from `latest_available_dates.price`/`.technical`, with `technical_summary` and then `generated_at` as fallbacks for legacy packages.

## 2026-08-03 - Context packages are rotated, never overwritten
- `builders/build_ticker_context.py --rotate-existing` renames the previous export to `<name>_superseded_<UTC>.json` and keeps it, then writes the canonical name fresh. Without a supported refresh path the Producer silently consumed a context package several sessions old, which its own freshness gate then correctly refused.
- The write-once rule itself is unchanged: nothing is ever overwritten or deleted.

## 2026-08-03 - Generated runtime data resolves through the runtime root, in tests too
- `bctc_processor.py` pinned `data_bctc/`, `financial_snapshot.*`, `logs/` and `reports/` to its own source directory, unlike every other script in the daily chain. Running it from `stock-core-private` read an empty input directory and wrote snapshots back into the source repo. All four now resolve through `runtime_paths.runtime_root(ROOT_DIR)`, which is byte-identical to the previous behaviour when `STOCK_LOOKUP_RUNTIME_ROOT` is unset. `docs/VALIDATION_REPORT.md` stays source-tracked.
- `tests/conftest.py` exports the same runtime root once per session and `tests/_runtime_root.py::require_runtime_path` skips a test whose runtime artifact has not been generated, instead of failing with a path error that says nothing about the code under test.

## 2026-08-03 - EODHD is closed as a route: REJECTED_BY_OWNER
```
EODHD_ROUTE_STATUS: REJECTED_BY_OWNER
Reason:
Repeated website/session instability and repeated API read timeouts.
It must not be used as a production dependency, fallback dependency,
or qualification prerequisite.
Reopening requires an explicit owner decision.
```
- This supersedes "2026-08-02 - EODHD private-shadow source authority approved". That approval is closed, not merely dormant: the owner has withdrawn it after two independent days of `request_failed_ReadTimeout` on the very first request (2026-08-02, and again during the 2026-08-03 market-wide readiness audit).
- No further timeout test, retry, credential milestone, website reachability check or network-path diagnosis is authorized. An agent that proposes one is re-opening a closed decision.
- `eodhd_access.py`, `eodhd_market_data.py`, `tools/check_eodhd_access.py` and `tests/test_eodhd_access.py` stay in the tree as disabled, unreferenced modules. They are removed from the active roadmap so they cannot be mistaken for pending work. Deleting them is not required and is not blocked.
- EODHD's removal does not change any gate: price and volume basis were `unknown/unverified` with it and remain so without it. What changes is which route is on the critical path — see the corporate-action pillar below.

## 2026-08-03 - Two pillars replace per-ticker financial pilots
- The roadmap's active development shifts from "qualify one more ticker the way HPG was qualified" to two market-wide systems. The per-ticker evidence bridge is retained for PDF-cited facts and is not extended into a market-wide path.
- **Pillar A - market-wide canonical financial normalization** (`docs/market_wide_financial_normalization_contract.md`). Four layers: raw retention, statement taxonomy, canonical facts, calculation engines. Layers 1 and 2 are implemented; 3 and 4 are specified.
- **Pillar B - official corporate-action ingestion and price adjustment** (`docs/official_corporate_action_ingestion_design.md`). Design only. It makes our own event ledger the adjustment authority, so no provider has to document its adjustment policy for the price basis to become qualified.
- The two pillars are independent up to pillar A's enterprise-value layer, which needs a market capitalisation and therefore waits on pillar B.

## 2026-08-03 - Raw financial retention has no allowlist
- `raw_financial_observations.py` retains **every** raw line item of every retained statement payload, for every populated reporting period. Selection is a mapping-layer concern, never a retention concern.
- The reason is operational, not aesthetic: an allowlist makes every future mapping rule that needs an unanticipated item require a re-fetch of the whole universe. `financial_observations.py`'s bounded `_CODES` allowlist is correct for its three-ticker pilot and must not be extended into the market-wide path.
- Nothing in this layer is ever `qualified`. Statement scope, currency, unit scale, sign convention and cumulative basis are not carried by the retained payloads, so every observation records them as `unknown` with an explicit warning, and the highest state assignable is `retained_raw`.
- The store is incremental on a fingerprint that covers the source payload hashes **and** the extraction schema version. Keying on payload hashes alone would leave shards looking `unchanged` after a change to the extraction logic, silently serving observations built by code that no longer exists.

## 2026-08-03 - `not_applicable` is a verdict, `unavailable` is a gap
- For a metric defined only by the corporate earnings model (`ebitda`, `ev_ebitda`), a filer positively evidenced as a credit institution, securities company or insurer receives `not_applicable`, not `unavailable`. `unavailable` invites someone to go find a missing input; `not_applicable` closes the question, because no input will ever make a bank's EBITDA exist.
- This is now structural rather than per-ticker: `not_applicable` covers **82** tickers, up from the 7 manually-profiled ones the 2026-08-03 audit found, closing the under-classification that audit reported.
- Every `not_applicable` result names substitute metrics for that template family, so it points somewhere instead of only closing a door.
- The authority order is unchanged and is not weakened by this: a manual profile is still the only thing that may name an institution type; generated statement evidence may still only *withhold* a corporate model; a corporate template still never grants a corporate archetype; and two evidence families disagreeing about *which* specialized financial template a filer uses still agree it is one, so disagreement withholds rather than restores.

## 2026-08-03 - Income-statement taxonomy evidence lives outside the pinned classifier
- The new exclusive income-statement marker sets are in `financial_entity_applicability.py`, not in `statement_taxonomy_classifier.py`. That module is pinned at `VERSION = "2.0.0"` and feeds `statement_taxonomy_sidecar.json`, which is hash-bound into the shipped bundle; adding markers there would move the sidecar fingerprint and change a production artifact for a reason unrelated to this milestone.
- The markers were validated market-wide before being written down: zero occurrences across the union of all 1,261 corporate-template income statements, 100% match within each group, zero cross-group overlap. The insurance set resolves 12 of the 13 tickers the balance sheet can only call `financial_specialized_ambiguous`.

## 2026-08-03 - A reported measurement must be produced by the run that reports it
- `tools/operate_stocklookup.py::report()` carried `market_wide_shares_coverage` as a dict literal: `active_universe_count: 1683`, `pe_ready_count: 1391` and eleven siblings. Advancing a milestone meant editing the numbers by hand — commit `5209447` changed `1679 → 1677` and `1393 → 1391` as source edits. The block would have printed identical numbers against an empty runtime root, and the only production report ever written carries the key as `null`.
- **A number in an operating report must be computed by that run, from that run's inputs, and must carry `measured_at` and the session it was measured for.** A count that no data change can move is not a measurement, and labelling it one in a report the operator saves as a baseline is worse than omitting it.
- The valuation-readiness counts were **removed rather than re-derived**. They describe a pass over the canonical fact store, which this command does not perform and never performed; restating them anywhere would repeat the original error in a new place.
- This applies to milestone operations reviews as well. P1J's review recorded a "Workstream B" grounding table whose HPG and VCB rows disagree with both the database and the citation store, because the comparison was written rather than run.

## 2026-08-03 - Official share anchors are read from the citation store, never carried as literals
- `market_wide_current_shares_resolver.QUALIFIED_SHARES` held three share counts as literals. Two were wrong. HPG's `7,163,748,865` appears in no citation and no ledger: it applied the 2026-06-04 stock dividend to the FY2024 period-end figure, when the event's own ratio fixes its base at `767,498,665 / 0.0999937567 = 7,675,465,852` and the ledger records `shares_after = 8,442,964,520`. VCB's `5,589,091,222` is the citation's `5,589,091,262` mistyped by 40 shares.
- The resolver was therefore overriding a **correct** provider value with a fabricated one 15% too low for HPG, under the system's highest authority label.
- Anchors now come from `data/official-evidence/share_basis_citations.jsonl` on every call. A regression test asserts both retired literals appear nowhere in the module.

## 2026-08-03 - A period-end share count is not a current share count
- All three retained anchors are `identity_type: period_end_shares_outstanding`, `reporting_period: 2024`. Serving one as a *current* share count asserts that nothing changed between the period end and the session — which is a claim about the corporate-action record, not about the anchor.
- Promotion to `qualified_official` therefore requires an official anchor **and** a ledger whose `coverage_status` is qualified across that interval. `corporate_event_records` covers 5 of 1,683 tickers at `partial_unqualified_50_row_cap`, so the gate is shut market-wide and `qualified_official` is **0**, not 3.
- This is not a regression. It is what was always true; the previous count reported the size of a hardcoded table.

## 2026-08-03 - Freshness is measured against the observation, and only an ex-right date positions an event
- The retired rule invalidated a provider share count when any event carried a date after a fixed literal `'2024-12-31'`, across `exright_date`, `record_date` **or** `issue_date`, for any event category. It therefore invalidated counts on events the observation already reflects (HPG's 2026-06-04 dividend against a 2026-07-30 observation), and fired on shareholder meetings and major-shareholder trades, which change no share count.
- The rule is now: compare the event's **ex-right date** against the provider's observation date (`metadata.updated`). A record, issue, payment or listing date never substitutes for an ex-right date — the same rule pillar B already applies to adjustment factors.
- `ISS` is the declared share-changing code; ten codes are declared not share-changing; anything else is `unclassified` and treated as share-relevant. An unknown code is never silently benign.
- A share-relevant event with no ex-right date cannot be positioned, so the ticker resolves to `provider_reported_unverifiable_freshness` with no value, rather than to either `current` or `stale`.

## 2026-08-03 - A failed read is not an absent value, and a share store is opened read-only
- Both retired lookups wrapped their queries in `except Exception: pass`. An unreadable corporate-event table returned an empty set, silently promoting the whole universe to `provider_reported_current`; an unreadable metadata row was reported as "no valid retained share observation found". Fail-open, under a fail-closed contract.
- Read failures now raise `ShareStoreUnreadable` and surface as `unresolved_error`, a lane of its own that is never folded into `unavailable` or into a provider lane. A market-wide read failure reports no counts at all rather than zeroes.
- The database is opened read-only (`mode=ro`, `PRAGMA query_only`, `busy_timeout`), matching the operating command's probe. The retired code opened it read-write once per ticker and again for the event scan — 3,366 read-write connections for one market-wide pass, against a database in rollback-journal mode with a live daily writer.

## 2026-08-03 - A market capitalisation is only as qualified as its weaker leg
- `evaluate_market_capitalisation()` set `status = qualified` from the share status alone. The price basis has been `unknown`/`verified: false` throughout, so a qualified share count produced a "qualified" market cap built on an unqualified price.
- The price leg's authority is now an explicit input (`price_basis_verified`) and defaults to `False`. No market cap, and therefore no EV, EV/EBITDA, P/E or P/B, can be `qualified` while the price basis is unverified.
- The share **concept** travels with the value. `ISSUED_SHARES` does not deduct treasury shares, so a cap built on it is not comparable with one built on `common_outstanding`, and carries a named warning saying so instead of being averaged into a universe-wide figure.
- The session price is read for the session (`WHERE date = ?`), not as the newest row for the ticker. `ORDER BY date DESC LIMIT 1` gave a delisted or suspended ticker's last-ever close to the current session's market cap with nothing marking the mismatch.

## 2026-08-03 - The session is an input to every session-relative resolution
- `resolve_effective_shares` defaulted `target_date` to the literal `"2026-07-30"`, and the one production caller passed nothing, so every export stamped that session's shares onto whatever session it was building. `session_date` is now required and validated on both entry points, and `canonical_financial_bundle_section.attach()` attaches nothing without one.
- `Operator.run()` re-anchors the session after `prepare_inputs()`. It previously called `preflight_database()` again and discarded the result, binding the taxonomy sidecar to the session that preceded the input refresh.

## 2026-08-03 - The daily chain's dependency order is enforced, not documented
- Stage order is `metadata/current-share refresh -> focus analysis -> context packages -> bundle export -> Consumer exact-session validation -> optional publish`. Each stage consumes the previous stage's output, so a stage run on a stale predecessor yields an artifact that is internally consistent and describes two sessions.
- Only one gate covered this before. `export_ai_bundle.check_freshness` refuses off-session `focus_analysis` and `context_package`, and it refused correctly on 2026-08-03 — but as `exit code 1` from a subprocess, after the sidecar had already been rebuilt on top of the stale input, and without naming which command refreshes what.
- **`metadata` was covered by nothing.** It is not in `DEFAULT_SESSION_SCOPED_CATEGORIES`, so a universe whose share counts were observed days before the session passed every existing gate silently. `preflight_share_freshness` now measures the lanes on every run and reports the session, the share observation date and each lane count.
- A lagged share count blocks the export **only where it can reach the artifact** — that is, under `--include-canonical-financial-facts`. The default bundle carries no share-derived value, so lag cannot enter it, and blocking there would be theatre. The allowance is named in the step record rather than left implicit, and a lagged value is never relabelled as current.
- Failures name the stage and the remedy: `METADATA_REFRESH_REQUIRED`, `FOCUS_ANALYSIS_REFRESH_REQUIRED`, `CONTEXT_PACKAGE_REFRESH_REQUIRED`. A failed stage prevents every later stage and prints no success line.

## 2026-08-03 - `--refresh-metadata` is the one stage allowed to write the authoritative store
- `--prepare-inputs` keeps its narrow meaning exactly: offline, session-scoped, no market data fetched. It rebuilds focus analysis and context packages and **does not** refresh metadata or current shares. That is why a `--prepare-inputs` run left the whole universe `provider_reported_lagged`.
- `meta_sync.py --refresh` is the only thing that moves `metadata.updated`, and it both writes `vn_stock.db` and reaches the network. It is therefore opt-in behind `--refresh-metadata`, requires `--execute`, runs before `--prepare-inputs`, and re-anchors the session afterwards.
- This is a documented, flag-gated exception to "never writes to vn_stock.db", not a silent change: without the flag the command's contract is exactly what it was. The restorable database copy is taken once per run and covers both writing stages, because a second copy taken after the first stage would record a state that stage had already changed.

## 2026-08-03 - An approval instant must say which clock it was read from
- `config/official_source_registry.json` records `approved_at = 2026-08-03T14:00:00Z`. The commit that wrote it, `a4d01cf`, was created at 2026-08-03 14:22:40 +0700 = **07:22Z**, seven hours earlier. A UTC instant ahead of the commit that records it is the signature of a local time written with a `Z`.
- **No owner record in this repository states which clock 14:00 was read from.** `docs/DECISIONS.md`'s P1G entry records the approval; neither it nor the P1G operations review carries a time. So the instant is not normalized and the approval is not modified: `approval_instant_verdict()` returns `unverified`, and `admit()` refuses with `approval_instant_not_verifiable`.
- Verification requires an owner-supplied `approved_at_provenance` naming the clock. It is required rather than inferred, because inferring it is an agent deciding what the owner meant. The requirement is also what makes the verdict durable: a future-dated instant stops being future-dated by waiting, so a check against the clock alone would turn `unverified` into `verified` with nothing verified.
- The instant is checked **last** in `admit()`, after host, document type and rate, so a bad host still reports `host_not_on_source_allowlist` rather than being masked by a governance verdict.
- This adds a requirement to owner approval and removes none. Pillar B's acquisition path (B2-B6) is closed until the owner records the provenance — which is the correct state for an approval nobody can currently read.

## 2026-08-03 - An executed event's `shares_after` is a current share count; a period-end figure is not
- `share_basis_citations.jsonl` held only `period_end_shares_outstanding` citations, so `market_wide_current_shares_resolver` had nothing that could ever describe *today*. Meanwhile `data/official-corporate-actions/event_ledger.json` had held a qualified, executed, hash-bound HPG `stock_dividend` since 2026-08-02 stating `shares_after = 8,442,964,520` as of 2026-07-02. Nothing read it. The count the issuer had published sat one directory away while the resolver reported HPG as `provider_reported_lagged`.
- The two identities are now distinct and ranked. A period-end citation describes 31 December; turning it into a current count requires proving nothing changed since, which for 1,682 of 1,683 tickers nothing does. An executed event's `shares_after` is an absolute count the issuer states as of a date, so it needs no proof for the interval *before* it — only for the interval after.
- **An ex-right date is deliberately not required for a share count.** An ex-date places an action on the price timeline, which is what an adjustment factor needs and why HPG's factor is still correctly `not_ready`. A share count needs proof the event executed: `lifecycle_state = executed` plus a stated execution date. Requiring an ex-date for both is what kept a published share count out of the evidence store.
- The interval after the anchor is closed by an **independent observation of the same absolute count**, not by an assumption. HPG's provider observation on 2026-07-30 reports 8,442,964,520 digit for digit. Where the two disagree the entry is refused outright — two sources contradicting each other is not evidence of either.
- `evidence_promotion.py` remains the sole writer. `share_basis_event_promotion.py` only selects and explains; it writes nothing, and every rejected ledger entry carries a named reason (`event_not_executed`, `entry_superseded`, `no_stated_execution_date`, `event_type_does_not_change_share_count`, …).
- Result: `qualified_official` 1 (HPG), from 0. VNM and VCB are refused with `anchor_is_a_period_end_figure_not_a_dated_current_count` — a document-level gap, closed by acquiring a notice per ticker, not by more code.

## 2026-08-03 - The B1 approval instant is not inferred from a commit timestamp
- `approved_at = 2026-08-03T14:00:00Z` was written by commit `a4d01cf`, created `14:22 +0700` = `07:22Z`. That makes "14:00 is local time" plausible. It does not make it evidence: it says when the value was *written*, not which clock the owner read when approving.
- So the value is neither corrected to `07:00:00Z` nor kept at `14:00:00Z`. Correcting it would fabricate a fact only the owner holds; keeping it would legitimise a timestamp on the strength of it already existing. The registry stays blocked and `admit()` keeps refusing.
- The owner's answer must take one of exactly three forms, recorded in `docs/STATE.md`: 14:00 was Vietnam time (set `07:00:00+00:00` plus provenance), 14:00 was UTC (keep it plus provenance), or the activation was not theirs (revert `activation`, leave the registry closed). An agent writes neither `approved_at` nor `approved_at_provenance` under any of the three.

## 2026-08-03 - `corroborated_period_end` is a shadow lane, not a weaker `qualified_official`
- A period-end anchor matched digit-for-digit by an independent observation has the same evidential *shape* as an executed event's `shares_after` plus its corroboration. Folding it into `qualified_official` would have made VNM qualify today without a new document, and would have made the label mean two different strengths of claim.
- It is therefore a separate, quarantined lane with the constraints fixed in code and tested: `authority_rank` 1 against executed-event evidence's 2; never a value `authority` may take; absent from the production lane counts; structurally unable to contribute to `is_actionable`; and shadow-only until it has its own validation and its own owner decision.
- **Every verdict carries `proves_no_intervening_event: false`, and that field cannot be true in this lane.** Agreement proves the *net* count is unchanged, not that nothing happened; two offsetting events produce the same number. The exposure is reported as `interval_days_carried_by_observation` rather than left to the reader — VNM's observation is carrying 576 days, HPG's promoted event only had to carry 28.
- Measured for 2026-08-03: 1 eligible (VNM, 576 days). VCB is refused — its observation contradicts its anchor, which the retained VSDC 2025 listing-change notice independently explains. HPG is out of scope, its executed-event anchor outranking the lane.

## 2026-08-03 - B1 approval instant verified by the owner; canonical value is 07:00Z
- The owner confirmed they approved the registry personally, and that the `14:00` originally recorded was Asia/Ho_Chi_Minh. `approved_at` is therefore corrected to `2026-08-03T07:00:00Z`, and `approved_at_provenance` records both the clock and the confirmation. The value came from the owner; this entry is the attribution, not a derivation.
- The correction is consistent with the evidence that raised the question: commit `a4d01cf` wrote the value at 07:22Z, and a 07:00Z approval precedes it by 22 minutes where a 14:00Z one would have followed it by seven hours. That consistency is corroboration after the fact, not the reason — the reason is that the owner said so.
- **The gate is unchanged.** `approval_instant_verdict()` now returns `verified` and `admit()` admits `hose`, `hnx`, `vsdc` and `issuer_ir`, but removing `approved_at_provenance` closes the registry again, and that is under test in three suites. What moved was a fact, not the standard.
- The earlier rule "an agent writes neither field" is restated as what it was protecting: **the value must originate from the owner and the record must say so.** Transcribing an explicit owner statement, attributed, is not the failure that rule exists to prevent; an agent choosing the value is, and it still may not.
- Pillar B steps B2–B6 are unblocked. The binding constraint on `qualified_official` is now document coverage, not governance: 1 ticker (HPG) has an executed-event notice and the rest need one acquired.

## 2026-08-04 - The source registry gates the acquirer, not just a JSON file
- `official_source_registry.admit()` existed, was reviewed, was owner-approved and had its approval instant verified across two milestones. Its **only caller in the tree was `tools/run_official_corporate_action_slice.py`** — the offline slice runner, which issues no network request. `official_document_acquisition.acquire()` fetched whatever URL a spec named, with no host allowlist check, no per-source document-type check, no rate rule and no approval check. The gate governed a JSON file and not a single request.
- `acquire()` now admits every request before making it: source, host, document type and interval. A refusal is recorded as `refused_by_source_registry` with the registry's own reason and **no request is made** — the tests assert the absence of a call, not the presence of an error, because a request that has already left cannot be un-made.
- The declared minimum interval is now *waited out* rather than reported on: the acquirer sleeps the remainder of the interval and proceeds, per source, so the rate rule shapes traffic instead of describing it after the fact.
- **The requestable document vocabulary comes from the registry**, not from the module. `DOCUMENT_CLASSES` was missing `ex_right_notice`, `listing_change_notice` and `last_registration_date_notice`, so `_validate_spec` rejected as malformed the exact notices that carry an ex-date — the single field `PRICE_ADJUSTMENT_FACTOR_PILOT` is blocked on. Two vocabularies for one concept had drifted, and the one that gated requests was the one nobody reviewed.
- No live acquisition was performed. Finding this before the first network run is why the run has not happened yet: the point of an owner-approved allowlist is that the first real request is the first *governed* request.

## 2026-08-04 - A gate on the first request is not a gate on the request that follows it
- `3b4cc5f` made `acquire()` admit every request before making it, and that held for the URL a spec names. Two paths still reached the network without passing the gate, both reachable by a **remote host alone, with no code change**: a `302` off an allowlisted host was followed, retained and recorded, because `allow_redirects=True` hands the next request to whatever the host replies; and a retry re-requested the same source after a `0.25s` backoff against a declared `10s` minimum, because the interval was enforced once per spec rather than once per request.
- `fetch_http` now follows redirects one hop at a time and admits each hop **before** the next request leaves, rather than judging where it landed. A refused hop raises `redirect_refused_by_source_registry` and the tests assert the hop was never requested. `acquire()` additionally re-admits any final URL that differs from the one requested, so bytes are never promoted from a host the registry would refuse **whoever fetched them** — a caller may supply any fetcher, and defence in depth is cheaper than trusting one.
- A retry now waits out that source's declared interval, not the backoff. The retry path was the one way to legitimately exceed the rate the registry publishes to the hosts it names.
- **The redirect bound comes from the registry.** `global_policy.max_redirects` sat in the reviewed JSON while `fetch_http` compared against a hardcoded `5`. They happened to agree, so nothing broke — which is precisely how the document-type vocabulary drifted. A reviewable value that governs nothing is a comment.

## 2026-08-04 - One vocabulary and one source identity across discovery and acquisition
- `3b4cc5f` moved the acquirer onto the registry's document vocabulary and made `source_id` mandatory. `official_document_discovery` was one import away and moved neither, so the fix landed in one of the two layers that had to agree.
- Discovery kept gating on `official_document_acquisition.DOCUMENT_CLASSES`, which omits `ex_right_notice`, `listing_change_notice` and `last_registration_date_notice` — so it rejected as `ambiguous_document_identity` **exactly the three notices that carry an ex-date, a listing change and a last registration date**, the facts pillar B exists to acquire. Discovery now reads the same registry union `acquire()` does.
- Discovery carried no `source_id`, so `retain()` handed `acquire()` specs refused as `missing_source_id` — **every candidate, no request made, nothing retained.** That is a regression `3b4cc5f` introduced silently: before it, `acquire()` required no source, so the discovery→acquisition bridge worked and then stopped working with no test covering the seam. A listing page now declares the registry source that governs it, and a page without one is rejected whole.
- Discovery accepted only `.pdf`. Exchange and depository notices are routinely HTML, `acquire()` retains `text/html`, and the evidence store already holds such documents (`vsdc-record-date-notice.html`, the retained HPG `listing_change_notice`). One layer's idea of admissible evidence now matches the other's.
- Discovery remains a **validator, not a parser**, and this does not change that. It never widens what may be requested: a candidate it accepts is still admitted or refused by the registry at `acquire()`, which is under test.

## 2026-08-04 - The first governed VNM discovery pilot is blocked on inputs, not on permission
- A bounded real-network VNM pilot was attempted and **stopped fail-closed at preflight; no network request of any kind was made.** Governance passed: the approval instant is `verified` at `2026-08-03T07:00:00Z` with provenance, all four sources are `approved`, and a refused host provably produces zero fetcher calls.
- It stopped on two things an agent may not supply. **No owner-approved VNM listing or search URL exists in any artifact** — every VNM URL on record is a terminal document, every `hsx.vn`/`hnx.vn` URL in the tree is a test fixture, and each source's `discovery_path` says "operator-supplied ... URLs only". **And the registry declares no listing/index/search document type at all**, so `admit()` refuses one; labelling a listing page `corporate_action_notice` to get it past the gate would defeat admission rather than pass it.
- Constructing a plausible HOSE or VSDC search URL from site structure is available and was declined. It would be an agent supplying the operator's authority to itself, and it would put a fabricated fact into an evidence system whose whole value is that it contains none.
- The narrowest unblock is an owner-named **notice detail** URL — the shape `vsd.vn/en/ad/177392` already has authority for. It needs no new document type, no listing-page parser, and no change to the closed-world contract.

## 2026-08-04 - An announcement index page is acquirable and never evidence
- Pillar B's remaining blocker was that every notice URL had to be hand-supplied by the owner. Removing it needs one new power — reading links out of one stored page — so the registry now carries **two disjoint vocabularies per source**: `document_types`, which may become corporate-action evidence, and `index_document_types`, which may be requested and never promoted. `announcement_index_page` is declared for **`vsdc` only**, the one source whose index pages are observed in a retained first-party artifact. Adding it to another source requires the same kind of observation, not a convenience.
- The separation is enforced where evidence is written, not where it is requested: `official_document_store.adopt_retained_document` refuses a discovery-input type **by name**, before the general vocabulary check, so the refusal states the rule. Relying on the type's absence from `DOCUMENT_TYPES` would have made non-promotability an accident of omission. An index page therefore cannot reach the observation ledger, the resolver, `qualified_official` or `corroborated_period_end`.
- Labelling a listing page `corporate_action_notice` to get it past `admit()` was available and rejected. It would defeat the gate rather than pass it, and it would put a page that asserts nothing about any issuer into the store the ledger reads from.

## 2026-08-04 - An entry URL is observed or the pilot does not run
- The VNM pilot's entry URL, `https://vsd.vn/en/alc/6`, is the breadcrumb `href="/en/alc/6"` inside the already-retained VNM notice `/en/ad/177392` — the category listing that the one retained VNM official document declares itself to belong to. The taxonomy is corroborated independently by the retained VCB artifact, which carries the same breadcrumb shape under `/en/alo/MEMBER` → `/en/alc/4`. `tools/run_official_listing_discovery.py` requires `--observed-in` and refuses to start when that artifact is absent, so provenance is an argument the runner checks rather than a claim in a report.
- A VSDC **search** URL was considered and rejected. The site's search box has no `<form>`, no `action` and no named fields — only `id="gSearchAdvText"` — so any search URL would have been invented. A URL derived from a JavaScript endpoint nobody has observed is a fabricated fact wearing a plausible shape.

## 2026-08-04 - A URL extension is a hint, not a document classifier
- Discovery allowlisted `.pdf`, which silently rejected two whole shapes of real evidence: an HTML notice, and an **extensionless** URL like `https://vsd.vn/en/ad/177392` — the form *every* VSDC notice takes, including the one already retained as official VNM evidence. The check is now a denylist of assets (`.css`, `.png`, …). `acquire()` validates the real `Content-Type` and refuses anything that is not `application/pdf` or `text/html`, so the hint's job is to drop stylesheets, not to decide what a document is.
- Inference is confined to what the source declares. VSDC does not publish `listing_change_notice`, so inferring one for a VSDC candidate would mint candidates the gate then refuses with `document_type_not_declared_for_source` — correct, fail-closed, and useless, since every registered-share notice would land in that hole. The **cue survives the remapping**: what a subject line is about is a reading of the page, while which class the source files it under is a fact about the source, and collapsing the two would have downgraded exactly the notices that carry a share count.

## 2026-08-04 - What a VSDC record-date notice does not contain
- A VSDC cash-dividend record-date notice states issuer name, securities code, ISIN, par value, trading platform, securities type, record date, payment rate, time and place — and **no share count**. So none of the 10 VNM candidates in the retained window (2023-07 → 2026-06), all cash dividends, AGMs and one record-date correction, can corroborate or contradict `2,089,955,445`.
- The class that carries an absolute registered share quantity is *"adjustment of the number of registered shares"*, observed for `CTR` on the page acquired today and for `VCB` in the retained artifact. **No such VNM notice appears in the retained window.** That is consistent with VNM having had no capital-structure event there, but the source is a 10-item sidebar and not a complete history: absence in it is not evidence of absence, and nothing was written anywhere from this observation.

## 2026-08-04 - The VCI historical series is not the as-quoted series
- The question was never answerable from field names — the `gap-chart` payload declares nothing — so it was answered from an **exchange rule** instead. A HOSE common-stock order matches only at a tick multiple (10 / 50 / 100 VND by price band), so a returned close of `54,047.65` or `23,478.96` was never a matched price. That exclusion is deductive; it does not depend on trusting the provider about anything.
- Which adjustment dimension came from **where the off-lattice prefix stops**, not from a fitted factor. It stops exactly at a qualified ex-date for three tickers — VCB 2026-07-23 (cash 450 VND), HPG 2026-05-25 (share issue 0.1), VNM 2026-06-26 (cash 1,850 VND) — two of them **cash-only**, which is what makes the verdict `split_and_dividend_adjusted` rather than split-only. Event dates were inputs from `corporate_event_records`, never inferred from price shape.
- The decisive artifact already existed and cost no request: `archive/runtime-backups/VNSTOCK_DATA_BACKUPS/20260719_223620/vn_stock.db` was snapshotted **before** VCB's ex-date, and `vn_stock_pipeline` only ever fetches forward from `MAX(date)`, so its historical rows are first observations. 13 of 13 VCB closes differ from today's payload for the same sessions; the no-event control re-request came back **byte-identical** (sha256 `1f57e4fe…`, the same hash the 2026-08-01 artifact carries). Revision is event-driven, not drift.
- A single constant factor `0.9917` reproduces all 13 sessions exactly and matches a standard cash-dividend back-adjustment. It is recorded with `event_window_fit_upgraded_verdict: false`, and a test proves a perfect fit cannot lift an `inconclusive` verdict. Reverse-engineering a factor and then calling the provider contract established is the failure mode this milestone was written to avoid.
- **This contradicts a retained artifact and the contradiction is recorded, not resolved.** `phase3a-qualified-vci-price-benchmark.json` asserts `price_basis: "raw_as_quoted_no_adjustment_applied"` over 1,923,111 stored rows. Those rows come from this same series. The benchmark was not modified.

## 2026-08-04 - Volume unit is qualified by the provider's own arithmetic; scope is not
- Daily `v` and the intraday `accumulatedVolume` were retrieved one second apart for the same in-progress session and matched exactly (9,315,300), so they are **one counter**, not two computations. That qualifies field identity without saying anything about scope.
- The **unit** is settled by an identity internal to one payload: across 99 of 99 consecutive trade pairs, `Δ accumulatedVolume` equals `matchVol` and `Δ accumulatedValue` equals `matchVol × matchPrice` under exactly one scale, 10⁶. A lot count would break that by a factor of 100. So the field is **shares** and `accumulatedValue` is in millions of VND — proven from the provider's own numbers, with no second source involved.
- **Scope stays `unknown` and the reconciliation was refused, not fudged.** `limit=30000` was requested and the endpoint returned 100 rows — a server-side cap. Observed intraday sum 146,900 against daily 9,315,300. Reading that gap as evidence of put-through inclusion is exactly the inference the contract forbids while pagination is unexhausted, so it classifies as `intraday_sample_incomplete` and a test proves a filled page cannot be read as a completed sample.
- Volume is also revised after first publication — 13 sessions, 13 **distinct** ratios (1.00233–1.00764), not the reciprocal of the price factor. Every pre-event value is a multiple of 100 and no post-event value is, which fits a mid-session accumulator snapshot at least as well as a corporate-action adjustment. Two causes, one observation, so `volume_adjustment_basis` stays `unknown`.

## 2026-08-04 - TCBS was declined rather than guessed
- `vnstock` 4.0.4 ships **no TCBS quote explorer** (`explorer/` holds `fmarket, kbs, misc, msn, vci`); what survives is a header profile and TCBS branches inside `transform.py` — evidence a path once existed, not its URL. The only TCBS endpoint anywhere in this repository is `apipubaws.tcbs.com.vn/tcanalysis/v1/margin/list`, recorded 404 on 2026-07-09.
- Composing a bars URL from that host and a plausible path was available and declined: it is fabricating an endpoint from a naming pattern, and whatever it returned would be attributed to a contract nobody has observed. **Zero TCBS requests were made.** Corroboration used the already-local retained KBS sample read-only instead, which matched 9/9 closes and volumes — in the post-event region where an adjusted and an unadjusted series coincide by construction, so it settles nothing and is recorded as compatibility only.

## 2026-08-04 - "We adjusted nothing" was never a statement about the provider
- The Phase 3A verdict that labelled 1,923,111 VCI rows `raw_as_quoted_no_adjustment_applied` was a **hard-coded module constant** in `qualified_price_storage_benchmark.py`, stamped onto every exported row and into the manifest. It was never derived from a payload, never gated on evidence, never verified. Not a different endpoint, not a stale snapshot, not a transformation bug — an unsupported assumption that survived because nothing ever asked it to prove itself.
- The same conflation was written down in `semantic_evidence_bridge.py`: a citation was valid "when the ticker had no unsettled corporate action **as of the trading_date**". That is the right instinct pointed the wrong way down the timeline — a back-adjustment is applied by events **after** the cited date. The reader then re-validated each citation against the live `ohlcv` row, which is the same rewritten series, so the check agreed and *reinforced* the wrong label.
- Both production citations demonstrate it arithmetically. HPG 2024-12-31 close 19,830 is not a multiple of the 50 VND tick for its band; VCB 60,560 is not a multiple of 100. Neither was ever a matched order price, and both were labelled raw. HPG's stated justification — its 2024 action settled 2024-06-27, before the cited date — ignores the 2025-06-26 and 2026-05-25 share issues that came after.
- The replacement verdict is `empirically_event_adjusted`, deliberately **not** `split_and_dividend_adjusted`. The latter names a general methodology; what is evidenced is adjustment observed at two event kinds, three tickers, one year. `provider_methodology` and `unobserved_event_types` stay `unknown` and `coverage_generalization` is `not_authorized`.
- Phase 3A is **superseded, not deleted**: the artifact, its manifest and its history stand, and `is_superseded()` is how a reader learns it is inactive. Two disagreeing *active* verdicts resolve to `conflicted` with every gate shut — recency is not evidence, and the new verdict wins on stated evidence rather than on date.
- **Unexamined providers were deliberately left ungated.** A fail-closed default would have blocked SSI and KBS too, which this pilot never looked at — a policy change wearing the costume of a bug fix. `active_verdict` returns `raw_as_traded_eligible: None` for them, and `unexamined_providers_note()` states in code that they still pass on the same conflation, merely not yet evidenced.
- Cost, stated plainly: P2a historical point-in-time valuation is **reopened as BLOCKED**. HPG's published FY2024 multiples had a price basis underneath them that does not hold.

## 2026-08-04 - Zero duplicates was the bug, not the proof
- The intraday cursor is **strictly exclusive** (`truncTime < cursor`) — measured, 71 of 71 transitions returned a newest trade strictly older than the requested cursor, 0 equal. Paging with `cursor = oldest_trunc_time` therefore looks flawless and produces **zero duplicate rows**, which reads exactly like confirmation that pagination is clean.
- It is the opposite. The 100-row cap truncates the oldest second mid-way, and under `<` the next request skips the rest of that second forever. Run 01 lost **1,704,400 shares** and broke the tape's own accumulated-value identity in 47 places while reporting a perfectly tidy scan. The correct cursor is `oldest + 1`, which re-delivers the boundary second whole and is then de-duplicated by trade `id` — 243 duplicates in the corrected run, which is what a correct scan of an inclusive overlap looks like.
- Deduplication is by provider trade `id` **only**. Time, price and quantity are excluded on purpose: HPG's tape routinely carries several trades sharing all three within one second, and a value-based key would have deleted real volume while looking even tidier.
- **A one-second cursor cannot enumerate a second holding ≥100 trades.** HPG hits this repeatedly; the scan moved to VCB, the sparsest ticker already in scope. This is a permanent property of the data path, not a budget problem, and no larger `limit` helps — the server caps at 100 regardless.
- The endpoint serves **only the current session**: a cursor at the prior session's close returns zero rows. A completed prior trading day is unreachable, which is why the pilot bounds a segment of the live session during the lunch halt rather than a whole day.

## 2026-08-04 - The books balancing is not the same as having every trade
- VCB's morning segment closes to the share: 1,873,500 enumerated + 3,500 measured-unenumerable = 1,877,000 = daily `v`, residual **0**. The 3,500 is not an unknown — `accumulatedVolume` is cumulative including its own row, so a gap between two retained trades is *exactly* measurable, and the scan reports 0.19 % un-enumerated instead of claiming completeness.
- It is still reported `incomplete_cursor_failure`. Whether the arithmetic reconciles and whether every trade was retrieved are different claims, and only the second is what "complete" means. Reporting a match on the enumerated subset would be a match against a quantity nobody asked about.
- **Even a perfect exact match would not have qualified market scope.** Enumerating everything this endpoint returns establishes what *this endpoint* counts; a matched-only tape and a tape including put-through reconcile identically against a daily field computed from that same tape. So `market_scope`, `negotiated_trade_inclusion`, `auction_inclusion` and `odd_lot_inclusion` are hard-coded `unknown` in the contract rather than computed, and a test proves a `complete_exact_match` cannot move any of them.

## 2026-08-04 - Two words that were doing more work than the evidence supports
- `market_scope = partially_qualified` is retired for `overall_market_scope = partially_observed_but_not_qualified`, and `opening_auction_inclusion = qualified` for `demonstrated_for_observed_ato_field`. **No verdict changed.** Both old spellings were accurate about the dimension they described and readable, by a consumer skimming for a green light, as "qualified enough to size against" — which is the one reading the evidence does not support. The qualified component is the inclusion of *one observed ATO-labelled quantity* in the accumulator, not the composition of the volume field.
- The roll-up `general_auction_composition` is now `partially_observed`, and `qualified` is **not a reachable value** for it. One demonstrated leg plus one unobserved leg is partial observation. `closing_auction_inclusion = qualified` is refused outright by the contract builder, so the ATO narrowing cannot be copied onto ATC by a caller in a hurry.
- `matched_trade_inclusion`, `negotiated_inclusion` and `odd_lot_inclusion` were recorded at `63ecc48` as `unknown` at the top level with `unavailable_from_observed_vci_surfaces` in a sidecar. They now carry the terminal verdict where a consumer actually reads. Same finding, relocated — a test asserts the frozen and active records agree on every dimension.
- **Two assertion functions, not one.** `assert_fail_closed` answers "is this safe" and still accepts `partially_qualified`; `assert_canonical_vocabulary` answers "may this be active" and refuses it. A frozen artifact can be safe and non-canonical, and `composition_summary.json` keeps its original words — an evidence record that gets edited when the vocabulary changes is not an evidence record.

## 2026-08-04 - "Blocked pending verification" was the wrong shape for liquidity
- Every liquidity gate in the repository was expressed as *blocked while `volume_basis_verified` is false*. That is a pending state with an obvious release, and the composition closeout made that release **dangerous**: the unit is shares and the provider's arithmetic closes exactly, so a future reader has every reason to verify the basis — and would thereby open days-to-liquidate, participation-rate sizing and backtest liquidity constraints on a figure whose market composition nobody has established.
- Nothing in production was open. Everything in production was **one plausible edit** from being open. That is the entire finding of this milestone; there is no live defect to report.
- So the gate moved off the basis. Thirteen liquidity and execution capabilities are `unavailable_by_contract` with `reason = complete_market_composition_not_qualified` and `reopen_condition = new_authoritative_source_contract`. There is no argument to `evaluate()` that opens one — not `existing_gates_passed=True`, not a different provider. The reopen note names what does *not* reopen them, because "reopen condition" alone reads as "paginate once more".
- `vci_volume_basis.forward_gate.action` read `block_liquidity_activation_when_unverified`, which says, correctly read, that verifying the basis activates liquidity. It now reads `block_liquidity_activation_unconditionally`, and `validate_forward` returns `liquidity_activation_permitted: False` **on success** — a caller wanting liquidity must override a stated refusal rather than infer consent from the absence of an exception.
- `risk_liquidity.dimensions.liquidity` read `available` whenever a descriptive mean was computable. A mean over one provider's series was making a dimension named *liquidity* report available. Descriptive volume moved to its own `descriptive_provider_volume` dimension and keeps reporting `available`; `liquidity` is now `unavailable_by_contract` unconditionally.

## 2026-08-04 - Descriptive volume was not the problem and was not disabled
- Nine descriptive and analytical capabilities are **retained**: volume history, moving averages, provider-scoped relative volume, trend indicators, same-series anomaly detection, source-labelled comparison, research-only volume indicators, volume confirmation, and the turnover-tier screening score. Turning them off would have cost real utility and bought no safety — a mean over one provider's own series was never a claim about executable depth. What changed is that each now carries four mandatory warnings enforced structurally, not by convention.
- **`stock_analyzer.score_liquidity` is the judgement call.** It bands close × volume into tiers for screening, it is named for liquidity, and it is not a liquidity measure. It is classified `analytical_not_liquidity_dependent` and left computing: disabling it would have changed production ranking output, which this milestone is forbidden from doing, for a score that has never claimed tradable size. A reader who disagrees should reclassify it as `liquidity_dependent`, at which point the matrix shuts it and the ranking changes.
- **The unknown class is the mechanism, not a footnote.** A volume consumer absent from `CONSUMER_CLASSIFICATION` resolves to `unavailable_pending_classification`. Adding one therefore requires classifying it, which is what keeps the matrix true after everyone involved has forgotten why it exists.
- Nothing inherits. Generic fields (`volume`, `market_volume`, `official_exchange_volume`, …) raise rather than receive the verdict, and other providers get `contract_applies: false` with `volume_composition: unknown` — unqualified because nobody qualified them, **not** because VCI's verdict was copied across.

## 2026-08-04 - A candidate is a question list, not an address
- HOSE trading statistics are registered as a `future_qualification_candidate` in a **separate module** from `official_source_registry.py`. That registry gates the network, its `hose` entry is already `approved` for corporate-action notices, and registering trading statistics there would have been one JSON edit away from a scraper — in a milestone forbidden from acquiring anything.
- **No URL is recorded.** None has been observed and retained in this repository, and a plausible-looking route written from memory is a fabricated locator regardless of how right it feels. A future milestone must obtain the locator, not compose it. `assert_not_acquirable()` proves no approved source admits a trading-statistics document type, and a test adds one to the `hose` entry to prove the check fails when it should.
- Eight semantic questions are recorded and **all open**: matched volume definition, negotiated volume definition, relationship between matched and total volume, units and scaling, ticker-level availability, date coverage, machine-readable access, access and reuse terms. A source whose units and ticker coverage are unknown cannot qualify anything.
- Recorded as the **preferred currently identified** official authority path, not the sole theoretically possible authority. Nobody surveyed the alternatives, and claiming there are none would be a statement about sources this repository has never looked at.

## 2026-08-04 - Ninety-six fields, and none of them says put-through
- The composition question was answered by exhausting surfaces, not by finding one. The entire retained VCI corpus carries **18 distinct field names**; a token scan of the whole `vnstock` VCI adapter for put-through, negotiated, odd-lot, auction and total-volume terms returns **zero**; and the one unexamined surface — the price board, an endpoint `meta_sync.py` and `blacklist_sync.py` already call in production — returned **96 fields across 3 groups with no put-through, negotiated, block or odd-lot field among them**. `negotiated_inclusion` is therefore closed as `unavailable_from_observed_vci_surfaces` rather than left open for someone to probe again.
- **`matchType` is the aggressor side, not the trade method.** Reading `b`/`s` as "matched trade" would have been the exact name-based inference this work exists to prevent, and it would have looked like progress.
- **`accumulatedVolumeG1` equals `accumulatedVolume` exactly, and was refused.** A `G1` suffix implying a board segmentation plus a perfect equality is the most tempting artifact in the payload. The equality is equally consistent with "G1 is the whole" and with "VCB had zero of whatever G1 excludes this morning", and nothing on hand separates them — arithmetic balance without a field definition is not evidence.

## 2026-08-04 - One qualification, earned by four agreements and an outside authority
- `opening_auction_inclusion` is **qualified**. The board's `matchVolumeATO` 42,700, `matchPriceATO` 60,900 and `firstTimeMatchPrice` 02:15:00Z all agree with the retained VCB tape's first trade of the session — which satisfies `accumulatedVolume == matchVol`, i.e. it *is* the accumulator's opening entry. So the opening auction sits inside daily `v`.
- This needed a third qualification route, because **no first-party VCI definition of any field exists or was retained** and none is claimed. The route is `exchange_standard_term`: ATO/ATC are HOSE session codes defined by exchange regulation rather than by the provider, so the referent is fixed outside VCI. It is admissible **only** when a second independent field pins the same referent and a bounded reconciliation is exact — `qualify_dimension` requires `referent_pinned_by_independent_field`, and tests prove name-alone and reconciliation-without-pin both stay `unknown`. `EXCHANGE_STANDARD_TERMS` holds exactly two entries.
- That is a deliberate, stated deviation from the strictest reading of the brief, and it is load-bearing for nothing: downgrading it to `unknown` flips the terminal state to B and changes no gate, because every gate is already shut.
- **One auction leg does not speak for the other.** `closing_auction_inclusion` stays `unknown` — `matchVolumeATC` was 0 at the morning snapshot — and the roll-up `auction_inclusion` cannot be asserted directly nor published without naming which legs it covers.
- `liquidity_actionable` is a **constant** `False` in the contract builder rather than a computed field. There is no input combination that turns it on, because sizing against a volume figure requires knowing what that figure counts.

## 2026-08-04 - The evidence audit found a real gap and two phantoms
- **Real:** the pagination runner wrote a daily-bar raw artifact whose filename it never recorded, leaving 4 raw files reachable from no ledger. The runner now records `raw_artifact` and the existing ledgers were repaired by hash-matching. Every raw filename already embedded the first 16 hex of its own content hash, so the names are self-verifying and the repair could be done from the bytes.
- **Phantom:** the secret scanner flagged 2 findings that were prose — "no cookie, **authorization** header … was sent" and "non-**secret** parameters", both sentences in a report *about* not leaking secrets. Textual matching cannot tell a secret from a discussion of one; the scan is now structural, requiring the marker as a JSON key with a value that is not the redaction sentinel.
- **Nothing was deleted.** Three byte-identical groups exist because the lunch-halt tape was frozen, and each copy is its own run's reconciliation target; the one superseded in-directory attempt is now referenced as `superseded_attempt_artifacts` instead of removed. Deleting failure evidence to make a count look tidier is how the reason for a decision gets lost.

## 2026-08-09 - Shipping the qualified research lane exposed two real defects and caused a third
- **Goal:** the Phase 4B/4C/5A/5B/5D/5E qualified-research-lane commits (`7293f78`..`e98cd53`
  Producer, `b024895`..`693b375` Consumer, `d93a2fa`/`bd2859f` Dashboard) had never actually
  reached the served release — `worktrees/market-dashboard-main`/`main` carried no
  `qualified_research_brief` for any ticker. Ship it there, at the real 11-ticker production
  scope, additive-only, with no unrelated refresh.
- **First real defect, pre-existing:** `tools/operate_stocklookup.py` — "the one supported
  operator command" — never exposed `--include-historical-decision-analysis` /
  `--include-portfolio-risk-analysis` / `--include-historical-scaleout` /
  `--include-qualified-research-brief`, even though `export_ai_bundle.py` had supported all
  four since the commits above. They were only reachable by invoking the exporter directly,
  bypassing the supported command's verify/rollback/Consumer-validate gates. Fixed: the four
  flags are now wired through, tested (19 `test_operate_stocklookup.py` cases unaffected,
  still passing).
- **Second real defect, pre-existing, and the direct cause of a scope mistake:**
  `DEFAULT_TICKERS` also silently carried `VNINDEX`, contradicting its own comment ("kept
  identical to what the last successful export actually shipped") — the actually-served
  bundle's `tickers_requested` has never included it (`unproven_tickers: []`, not
  `["VNINDEX"]`). Requesting it by default tripped `preflight_derived_session_inputs` on a
  context package for a symbol outside both the shipped universe and this lane's target
  population (an index has no issuer). That gate failure was answered, wrongly, by running
  `--prepare-inputs` — which correctly rebuilt VNINDEX's package but also regenerated
  technical signals, focus analysis, and every real ticker's context package, and upserted
  `watchlist_history` in `vn_stock.db`, none of which the milestone authorized. **Fully
  reverted before any publication**: `vn_stock.db` restored from the run's own hash-verified
  pre-write backup (`181ebd7e…36a9`, matching the long-standing known-good hash), the four
  release artifacts restored from the run's own rollback point (matching the pre-incident
  hashes independently captured before any command ran). Root-caused and fixed at the source:
  `DEFAULT_TICKERS` no longer carries `VNINDEX`. The corrected rebuild (11 tickers, no
  `--prepare-inputs`) then passed `preflight_derived_session_inputs` on the first try,
  proving the fix — the real production inputs had been fresh the entire time.
- **Third defect, self-inflicted by the first mistake, caught before publication:** because
  `prepare_context_packages` runs *before* `export_bundle` rewrites `analysis_bundle.json`,
  and the runtime root's on-disk bundle was transiently a 3-ticker ad hoc pilot snapshot when
  the over-broad `--prepare-inputs` ran, the Consumer's context builder found no legacy-bundle
  entry for 9 of the 11 tickers and wrote every dependent section as
  `*_not_in_legacy_bundle`/`missing` into their `context_package` sub-blob — a real content
  regression, not a timestamp. Caught by a section-by-section diff against the live served
  bundle before any publish. Remediated by rebuilding context packages once, directly, now
  that the correct full-universe bundle was already on disk (not by widening scope again).
  Verified afterward: the top-level, dashboard-rendered sections were unaffected throughout
  (`financial_canonical` status identical for all 11 tickers across both mistakes); a
  section-level diff against the served bundle, with wall-clock-only fields stripped, showed
  zero remaining content differences beyond the intended additive research fields for HPG/VNM.
  One incidental finding: 4 of the 11 tickers' `context_package` sub-blob in the
  **already-shipped, currently-live** bundle carries this exact same `not_in_legacy_bundle`
  pattern — a latent, pre-existing defect in the ordinary daily pipeline's own sequencing,
  unrelated to this session, not investigated further here (out of scope; the corrected
  candidate does not carry it forward for those 4 tickers, but nothing was done to fix the
  live bundle's copy).
- **Why this belongs in DECISIONS, not just as a fix:** the failure mode generalizes —
  `--prepare-inputs` bundles five independent stages (candle scan, strategy, market scan,
  focus analysis, context packages) with no way to run one without the others, and
  `preflight_derived_session_inputs` checks freshness for whatever ticker list is passed,
  including symbols outside the real target scope. A wrong or stale default ticker list turns
  an unrelated symbol's staleness into an invitation to refresh everything. Before reaching
  for `--prepare-inputs` to satisfy a freshness gate, check first whether the tickers actually
  in scope are already fresh — this session's real ones always were.

## 2026-08-09 - A new capability gets a new section, not a retrofit of a load-bearing gate

- `risk_liquidity.py::evaluate_market_risk()` computes `realized_volatility`,
  `downside_volatility` and `maximum_drawdown` from the retained OHLCV series, but only
  inside a branch gated on the **generic** `price_adjustment == "qualified"` flag — which is
  always false market-wide, so these three fields have been `unavailable` in every
  production bundle since they were written. VCI's own price series (100% of every
  production ticker's retained window, verified against `dashboard-runtime/vn_stock.db`)
  carries a real, evidenced, provider-scoped verdict that already authorizes exactly this —
  `vci_direct_basis_pilot.SHADOW_PRICE_CAPABILITIES` names `vci_namespaced_historical_
  returns`/`vci_namespaced_technical_indicators` as available under a required label.
- The safe fix was not to change `risk_liquidity.py`'s gate. Retrofitting a load-bearing,
  already-shipped section's branching logic to key off a provider-scoped verdict instead of
  the generic one carries real regression risk for every existing consumer of `market_risk`'s
  exact shape, for a gain the alternative already provides: a new, separately namespaced,
  additive `qualified_market_observations` section computes the same class of statistic
  (return, volatility, drawdown) over the same data, correctly labelled provider-scoped and
  non-actionable, with zero risk to the existing section's output. `risk_liquidity.py` is
  unmodified by this milestone.
- **Corollary: this is not permission to widen the generic gate.** `price_basis_verified`/
  `volume_basis_verified` stay exactly what they were. The new section's `is_actionable`/
  `liquidity_actionable` are hardcoded `false` constants, never derived from either the
  generic flag or the provider-scoped one — see `market_basis_capability_registry.py` and
  `docs/qualified_market_observations_contract.md`.

## 2026-08-09 - The generic-unlock route is named, not executed, in a capability-activation milestone

- Pillar B (official corporate-action lineage expansion) was selected as the highest-leverage
  next generic-unlock route, unchanged from the existing roadmap: it is already owner-approved
  and active (B1), with a concrete next bounded input already on record — an official VSDC
  ex-date notice for SSI, the same acquisition pattern already exercised for VCB on
  2026-08-08.
- **That acquisition was not performed in this milestone.** A live external network request
  is a materially different class of action from the source/test/documentation work this
  milestone otherwise consists of, and identifying a legitimate entry URL first requires its
  own bounded offline discovery pass over already-retained SSI evidence — a distinct,
  separately-scoped piece of work, not a byproduct of capability-registry construction.
  Recorded here as a decision, not a gap: the next session doing Pillar B acquisition work
  should start from "acquire the SSI VSDC ex-date notice using the established B2/B3
  pattern", not re-derive the route.

## 2026-08-09 - "Closed" described the evidence tested, not every surface a provider exposes

- The 2026-08-04 finding that KBS "does not currently provide admissible scope evidence"
  was correct for the one endpoint it tested (`data_day`, the daily chart) and was written,
  and later cited, as if it covered KBS generally. It did not: KBS's price board
  (`stock/iss`) and intraday trade tape (`trade/history/{symbol}`) are two different,
  already-installed endpoints on the same host that nobody had examined. Both existed in
  the installed `vnstock` 4.0.4 library the whole time; finding them cost zero new
  dependencies and zero provider exploration beyond what was already integrated.
- Testing them (three tickers, one session, 2026-08-07) found real, new, `empirically_
  deduced` evidence: KBS's daily volume figure is now *decisively* known to exclude
  put-through/negotiated trades and include continuous-matched and auction-cleared trades,
  via an exact, zero-residual reconciliation of the full intraday tape against the price
  board's accumulator, repeated identically for all three tickers.
- **The lesson generalizes beyond this one finding.** A "provider has no admissible scope
  evidence" verdict is only ever as broad as the surfaces actually tested. Before treating
  such a verdict as closing a provider entirely, check what was tested, not just what the
  verdict says. VCI's own composition finding (2026-08-04, "Ninety-six fields, and none of
  them says put-through") is not affected by this correction — that finding already names
  the specific surfaces it exhausted (all 96 fields across every VCI endpoint reachable),
  which is the standard this KBS finding was held to as well before being written down.
- See `kbs_trade_scope_qualification.py` and
  `operations-review/kbs-trade-scope-qualification-20260809/`.

## 2026-08-09 - A third-party library's time-window heuristic is not a first-party field

- `vnstock`'s KBS intraday tape reports an empty `side` field on exactly the trades a call
  auction produces (no directional aggressor, which is structurally why continuous trades
  carry a side and auction-cleared trades do not). The library's own
  `core.utils.transform.process_match_types` then labels the *first* such empty-side row
  each day `ato` and the *last* `atc`, by matching against a fixed clock window
  (9:13-9:17 / 14:43-14:47) — a heuristic the library author wrote, not a field KBS's API
  returns.
- The distinction mattered for a real decision: `kbs_trade_scope_qualification.py` qualifies
  one combined `auction_inclusion` dimension, deliberately never splitting it into separate
  `opening_auction_inclusion`/`closing_auction_inclusion` verdicts the way VCI's contract
  does. The *inclusion* fact (side-less rows are part of the reconciled total) rests on
  first-party field values (the raw `LC` field, genuinely empty) and needs no heuristic;
  which specific auction a row belongs to would rest entirely on the library's guess, and
  this repository's qualification tiers do not have a tier for "a third party's plausible
  guess" (`evidence_qualification_tiers.classify_field_semantics`'s own doctrine: a
  contextual or inferred reading does not qualify).
- A second candidate corroboration was checked and set aside for the same reason applied
  honestly: the price board's `PMQ`/`PMP` ("previous match qty/price") fields matched the
  put-through print's quantity and price exactly for HPG, only on price for VNM, and not at
  all for VCB. Inconsistent evidence is not evidence with caveats attached; it was not used.

## 2026-08-09 - One official close is a namespace observation, not a historical series

- The bounded official-only locator pass found and retained HOSE's Annual Report 2024 from
  `staticfile.hsx.vn` through the approved acquisition path. Its own table labels make HPG's
  31 December 2024 `Closing Price` and `VND Thousand` scale explicit: 26.65, i.e. 26,650
  VND/share. That is enough to record a first-party, exact-session raw-price *pilot
  observation*. It is not enough to claim an exchange-wide history: the report contains no
  deterministic daily ticker route, no pre/ex/post event window, and no stated non-revision
  policy. The verdict is deliberately `RAW_AS_TRADED_PRICE_AUTHORITY: PARTIAL`.
- The read-only frozen VCI row for the same HPG date is 19,830 VND/share. The two values are
  preserved as `official_raw_as_traded_pilot` and `provider_adjusted`, with their observed
  ratio recorded but no transformation inferred. A non-equal pair proves that merging would
  destroy information; it does not identify a corporate-action factor. The registry refuses
  a nearest-date lookup and never falls back to VCI/KBS for a raw-required query.
- The same first-party PDF explicitly labels `Order matching` and `Put-through`, but the
  decomposed table is foreign-investor annual activity by security type, not all-market
  ticker/session volume. It cannot be numerically reconciled to VCI daily `v`, so it changes
  no VCI category state. This is a source-granularity blocker, not a reason to infer an
  aggregate composition from a column position or approximate equality.

## 2026-08-09 - A daily exchange summary is not automatically daily ticker statistics

- A bounded official-only locator pass retained two HOSE `TỔNG HỢP THÔNG TIN GIAO DỊCH` / Trading
  Summary PDFs. The retained bytes are authentic, stable, date-labelled first-party documents;
  that establishes artifact reproducibility, not the requested data schema.
- Both samples call their index figures `Closing value`. They contain no individual-equity
  close/last/reference/open/high/low/average field. HPG appears in selective top-five volume
  tables, but this supplies no price. The VNM-labelled retained sample contains no VNM equity
  ticker-session observation; a covered-warrant code is not evidence for its underlying equity.
- The reports explicitly label `Order matching`, `Put-through`, and `Total`, but only for the
  full market. Their ticker tables are top-five volume lists without ticker-level trade-type
  components. Do not allocate market totals to a ticker, infer the omitted ticker universe, or
  compare those aggregates to VCI daily volume.
- The correct terminal status is
  `OFFICIAL_DAILY_TICKER_SESSION_STATISTICS_ROUTE_NONCONFORMING_SUMMARY_ONLY`. It replaces the
  less precise “route unavailable” gap, but opens no capability: the one-date HPG annual-report
  raw observation remains separately namespaced, historical raw stability is blocked, and no
  raw/adjusted factor is inferred.

## 2026-08-09 - Select a commercial raw-history candidate before more data probing

- The bounded authority shortlist is: HOSE's licensed Market Data Feed, FiinGroup API
  Datafeed `/Market/GetHoseStockv2`, and the already-integrated VCI/KBS paths. The third is
  rejected for raw authority without a new request because both active verdicts are adjusted;
  the public HOSE fee schedule proves a commercial product exists but not its required field
  contract.
- **Selected candidate: FiinGroup API Datafeed `/Market/GetHoseStockv2`, pending owner source
  acquisition.** Its public field documentation explicitly distinguishes `ClosePrice` from
  `ClosePriceAdjusted` and `RateAdjusted`, names `Ticker`/`TradingDate`, and separately names
  total order-matching and put-through volumes/values. That is materially different evidence
  from a broker series that happens to match an exchange number.
- Documentation alone is not source activation. Before any pilot, the agreement must confirm
  that the unadjusted fields are raw/as-traded and non-rewritten, document point-in-time/revision
  semantics and units, specify auction/odd-lot treatment, and allow immutable evidence retention
  plus the intended production-use boundary. No credentials were searched for beyond the local
  environment-name check; none were present, and no commercial endpoint was called.
- The selected route is for a future `market_history.raw` namespace. VCI/KBS stay separate
  provider-adjusted history; qualified corporate actions reconcile the two only after a retained
  raw pilot passes. `RAW_PRICE_AUTHORITY` remains `PARTIAL`, volume authority remains blocked,
  and `OWNER_SOURCE_ACQUISITION_DECISION` is the next canonical milestone.

## 2026-08-09 - FiinGroup is an external dependency, not an adapter-shaped assumption

- The configured-access audit checked only project configuration/adapters, credential naming
  conventions, environment-variable names matching `FIIN`/`DATAFEED`, and source/license notes.
  It found no FiinGroup access or agreement. No value of any secret was read or logged, and no
  commercial request was made. `FIINGROUP_ACCESS_STATE` is therefore
  `OWNER_ACQUISITION_REQUIRED`, not “unusable” and not implicit authorization.
- `LICENSE_AUTHORITY` is `OWNER_CONFIRMATION_REQUIRED`. Public field documentation does not
  establish historical API entitlement, local evidence retention/cache, derived analytics,
  internal production, Dashboard display, or redistribution rights. Those rights, plus
  raw/non-rewrite/as-of, units, auction and odd-lot semantics, are contract conditions before
  the first payload can qualify.
- The complete minimal request is FiinGroup API Datafeed `/Market/GetHoseStockv2` only, for
  HOSE HPG/VNM daily history from 2024-01-01. It names no companion module and excludes
  fundamentals/news. Its acceptance pilot starts with the 26,650 VND HPG 2024-12-31 official
  anchor, adjacent dates and an existing corporate-action window; it retains redacted request
  metadata and hashed bytes only after access is provisioned.
- The market-data track is `WAITING_EXTERNAL_ACCESS`. Procurement does not block all work:
  the already-canonical `P1.5_TICKER_CAPABILITY_TRUSTED_TICKER_MATRIX_BUNDLE_ATTACHMENT` is
  the independent next implementation milestone. No valuation or market-data work starts
  automatically from this decision.

## 2026-08-09 — Cohort 2 issuer evidence is a bounded annual-facts expansion

- **Decision:** admit only the enumerated QNS and Novaland issuer domains (apex and `www`) for
  the two locator-backed FY2024 requests. No cloud wildcard, mirror, pagination, or generic
  issuer crawl is permitted. The known Novaland document size raises the response ceiling to a
  still-bounded 32 MiB.
- **PNJ:** retained Note 19 presents only short-term borrowings. The existing debt derivation
  requires exactly labelled current and non-current borrowings/finance leases for the same
  reporting period; liabilities, obligations, and a manually entered total cannot substitute.
  PNJ remains 4/5.
- **Outcome:** QNS's exact URL was a 404 and POW remains locator-blocked. NVL's one retained,
  audited FY2024 consolidated issuer filing supplied all five verified annual facts. Its debt is
  the explicit `36,978,198,251,788 + 24,587,656,403,178` sum; the VND facts are historical-only
  and non-actionable. FPT was not revisited. HPG, VNM, PAN, PVD and all market-data authority
  boundaries are unchanged.

## 2026-08-09 — Historical analytics are evidence projections, not market research activation

- The HPG/VNM/PAN/PVD/NVL corporate cohort may receive deeper analytics only from the existing
  qualified annual, consolidated canonical-fact path. Derived ratios retain source identities
  and fail closed for incompatible scope, currency, unit, missing fields and denominators.
- PVD's USD facts remain USD. The cohort artifact exposes local states and dimensionless ratios
  only, forbids FX conversion, absolute monetary comparison, ranking and recommendation.
- Consumer and dashboard publication are deferred because this milestone changes no market
  authority and no runtime artifact. The next candidate is
  `QUALIFIED_HISTORICAL_COMPARATIVE_RESEARCH_AND_AI_UX`, contingent on a Consumer audit.

## 2026-08-09 — Comparative research is a qualified-cohort observation, not a ranking

- HPG, VNM, PAN, PVD and NVL are a fixed **qualified cohort**, not an assumed peer group. The
  comparison projects existing qualified analytics, source identities, and deterministic
  positions without calculating another fundamental formula or introducing a weighting model.
- Cross-sectional historical comparison is available; multi-period trend remains insufficient.
  PVD remains USD, and the contract excludes absolute monetary comparison and FX conversion.
- Consumer and Dashboard may present the Producer section verbatim only. AI may explain an
  exact supported comparison but may not create recommendation, valuation, target-price,
  liquidity, expected-return, sizing, allocation, or investment-ranking claims.
