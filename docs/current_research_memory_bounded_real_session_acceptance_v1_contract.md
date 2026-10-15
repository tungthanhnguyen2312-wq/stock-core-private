# Memory-bounded retained-session research acceptance

Milestone `CURRENT_RESEARCH_MEMORY_BOUNDED_REAL_SESSION_ACCEPTANCE_V1`.
Source baseline: `ee27482d852df19c6dfb48a806b33d5917254b62` (October 15 Daily).
Local, read-only, opt-in. Authority effect **NONE**. No automatic successor or release.

## Governance

The Owner's October 15 directive explicitly appoints Codex successor to Grok and
overrides the empty roadmap queue for this exact milestone. Native succession
revision 183 → 184 used predecessor Grok, successor Codex, coordinator HEAD
`178768fa9dc75e277eec22f71a247701fdb3eb84`, and `successor_lanes=[]`:
all Grok source lanes were terminal, with no in-flight predecessor lane. No Python,
Grok or Claude writer was observed at transfer. Succession checkpoint
`4e1cb1a2b50cde32394d60843168990d13529d1e`; post-transfer **ON_TRACK / VERIFIED**.
Admission revision 185 was committed as `07f3c3f6`; ACTIVE revision 186 as `fda2b9a5`.
Every historical lane and lease remains. Both Codex VRE COMPLETE_LOCAL lanes keep
their original checkpoints, blockers and leases. `ACTIVE_STATE.md` remains under
the existing VRE lease; this contract and native lane record describe this work
without changing that leased navigation file.

## Architecture choice

**A — verified streaming projection** is selected. The preview-private adapter in
[`bounded_research_preview.py`](../stocklookup_core/decision/bounded_research_preview.py)
subclasses the frozen E4 `ObjectStream`, reusing its sorted-unique member traversal
and adaptive decoding. Its scoped decoder rejects nested duplicates/nonfinite
values, bounds refills and metadata, and checks the deadline. The frozen public
verifier has no parser-injection parameter, so the preview owns the small native
canonical hash traversal, using the unchanged `bounded_json.py` encoder. Each source
is completed before the next begins. Only explicitly selected original records
survive, inside a distinct projection envelope, until the existing Action Center
evidence/conditional/setup-transition functions render them.

The root `bounded_artifact_stream.py` is a retained compatibility implementation;
it imports retention/sanitization owners and is not copied into this path. The
frozen package implementation is byte-identical to the E4 baseline; its public API,
caller-owned sanitization and unrelated consumers retain their original behavior.
No production monkeypatch or general-purpose parser framework is introduced.

The Owner-authorized E4 corrective continues this same lane and preserves original
checkpoint `63e662857003133cf642c7ba6b3fa76f5146dfca` in history. PR159 CI exposed
two additional E5/E6 frozen-source failures missed by that checkpoint's bounded
review. The earlier zero-new-failures statement below refers only to the recorded
neighbour suite; it did not cover those freezes. The corrective restores E4 bytes
without changing pins, manifests, existing E4/E5/E6 assertions or CI policy.
Original V1 digest is `fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46`;
V2 is `07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567`.
New exact-head acceptance and CI evidence govern the corrected candidate; the
historical measurements below belong to the original checkpoint. Updating PR159
and validating hosted CI are authorized; merge requires a new Owner directive.

**B — compact retained artifact only** is rejected. `decision_surface_index` has
posture, currency and priority, but lacks condition, counter-thesis, uncertainty,
per-axis eligibility and exact per-ticker decision identity. Daily Integrated Brief
and the research packet are useful consumer projections, but neither substitutes
for recomputation of the complete original IID content identity required here.

**C — full verification plus a separate compact artifact** is unnecessary: once a
record has been decoded for native hashing, the selected original row is available.
A second persisted projection, join authority and stale-sidecar lifecycle add no
benefit. There is no new materialized source layer or parallel classifier.

## Opt-in interface and scope

`personal_investment_decision_action_center.evaluate_selected_research_preview`
takes an explicit evidence root, current session, ticker sequence and original
operation directories. It returns `action_center_selected_research_preview/v1`.
`selected_research_preview_markdown` reuses the existing investor renderer.
`tools/evaluate_bounded_research_preview.py` is an offline evaluation tool, not a
production entrypoint. Its only writes are into one new external result directory;
source and evidence roots and existing output directories are refused.

The ordinary `build_artifact`, retained full-universe resolver, default Markdown,
JSON and identity remain unchanged. A selected map never enters that full builder.
The full source identity is retained as **lineage**, never claimed as the selected
projection's identity. The preview and transition projection have distinct hashes.
The latter is explicitly not a `next_session_decision_brief/v2` artifact.

Every result states requested tickers, available selected count, full denominator,
excluded source count, unavailable selections, full verification status, and
`FOCUSED_SELECTED_PREVIEW_NOT_FULL_ACTION_CENTER`. Every transition/confirmation,
missing-evidence and numeric-withholding statistic is **selected-ticker-only**;
no selected counts represent a full 1,683-ticker Action Center.

## Integrity and temporal qualification

1. Strictly decode the governed input registry. Require its exact contract,
   COMPLETED_RETAINED_EVIDENCE status, valid trading-day flag and frozen inputs.
   Select the immediately preceding qualified date from that ledger independently;
   an absent, wrong-date or non-native previous operation is refused. A first
   qualified session keeps an unavailable transition, with no invented label.
2. Verify each original run manifest's exact operation contract, schema, session,
   `DAILY_PRODUCER_RETAINED_COMPLETED_SESSION` generation context (replays refuse),
   native `stable_id` identity, content-addressed operation directory and every
   frozen registry reference. The operation builder's known extra `macro` and
   `explicit_portfolio` inputs may be declared but are not read or consumed.
   Unknown extra inputs fail. IID must be named in the manifest outputs.
3. Resolve IID at the existing fixed per-session locator. Stream the whole sorted,
   unique source to EOF and hash the native canonical content, excluding exactly
   `artifact_sha256`, `artifact_identity`, `requested_at`, as IID's authoritative
   `content_identity` does. Compare computed hash to both original identity fields
   and the operation manifest's expected identity. A byte-file hash or header is
   never substituted. Require exact IID contract and schema.
4. Validate **every** row, selected or not: mapping shape, ticker key, original
   session, native decision identity, supported posture policy and root/record
   policy agreement. Check declared full coverage denominators against streamed
   record count. Never skip a bad record. Check file size/mtime/inode before and
   after reading. No source record is returned before full verification succeeds.
5. Strict parsing rejects duplicate keys at every nesting level, nonfinite values
   (including numeric overflow), truncation, malformed members, invalid JSON
   whitespace, trailing garbage, unsorted/duplicate stream keys and size excesses.
   Default legacy parsing/sanitization remains unchanged.
6. Verify the complete registered tactical artifact with its native owner function
   before projecting confirmation membership, using the brief's existing
   `TACTICAL_CONFIRMATION_STATES` and exact gained/retained/lost set semantics.
   This small auxiliary input is bounded separately; no market data is acquired.

The preview calls the existing `_expected_posture_label` and
`_setup_transition_for_ticker`; no posture or transition labels are added. Research
epoch changes retain NOT_COMPARABLE_POLICY_CHANGE. Fundamental epoch changes also
mark the fundamental comparison non-comparable, even if its raw label is unchanged.
Current observed technical, market and sector labels remain source-bound. Market
and sector *aggregate direction* fields are unavailable when no qualified brief
is supplied; raw per-ticker context changes do not become causal explanations.

Current numeric boundaries use the existing conditional research qualification,
with an additional selected-view narrowing when the price unit is missing.
Conflicting declared price unit, currency or scale fails the selected comparison.
No cross-session numeric distance is copied. Missing basis/freshness keeps
qualitative future conditions visible while numerical fields are withheld. Source
condition hashes are labelled lineage, not hashes of the narrowed display.
WAIT_TO_INITIATE is not a trade; BREAKOUT_FAILED is not measured loss; PRIORITY_NOW
is research attention; future conditions are not observed events. Source posture,
counter-thesis, uncertainty, financial freshness/proxies, share and valuation
restrictions, axis fitness, provenance and missing-evidence effects pass through.

No private workbook or portfolio is accepted/read. Source position/portfolio
context is not selected into the rendered evidence. This adds no valuation,
portfolio allocation, sizing, RAW/PIT, execution or provider authority.

## Resource contract

- Source maximum: 4 GiB per IID file; zero-length or larger files refuse before read.
- Selected maximum: 20 unique explicit ticker names; 16 MiB of canonical selected
  row content **per source**, plus bounded metadata. No full-universe source graph.
- Largest member/input buffer: 4 Mi decoded characters (UTF-8 can need four bytes
  per character). Initial refill 64 Ki characters, adaptive up to the cap; metadata
  retained across root members is limited to 4 MiB canonical bytes.
- Tactical auxiliary: at most 16 MiB on disk, strictly decoded and fully verified.
  Registry/operation metadata: at most 4 MiB each. No network or scratch materialization.
- Admission: at least 1 GiB currently available physical memory; fail before source
  reads if unavailable. This is a separate read-only consumer gate, not a relaxation
  of any Daily host guard. No production memory policy changes.
- One 600-second monotonic deadline covers the pair; parser refills and each record
  check it. It is cooperative, not a hard OS I/O cancellation guarantee.
- Windows process high-water working set and private commit are measured directly,
  with baseline and incremental peaks, elapsed wall time and I/O counters. Acceptance
  refuses the measured result at ≥1 GiB incremental resident/private memory.
- No temporary scratch is needed and nothing is deleted. The only retained output
  is the explicitly requested new local result directory.

The old full-object path could not safely render the retained ~1.42-GB pair with
~2.3 GB available RAM. Initial real bounded rendering read 2,852,302,361 bytes,
had zero evaluator I/O writes before explicit result publication, took 72.87 s,
peaked at 174,497,792 resident bytes (58,953,728 incremental), and 58,249,216
incremental private bytes. Final validation evidence below governs the checkpoint.

## Genuine retained acceptance and validation

Candidate pair: current **2026-10-15**, previous **2026-10-14**. Both independently
qualified; no substitution, Daily execution, provider contact or retained rewrite.

| Evidence | Previous | Current |
|---|---|---|
| Source bytes | 1,421,551,198 | 1,422,665,239 |
| Operation digest | `13d1779073dcb174de917afc069a6d238f02be1431619e444033bf3830349bc2` | `ce632bf88b63c48ac2e6af0a811cbf17a43f471376e1ad2030daf49c4143b6e5` |
| IID digest | `e979d0129a40fb2fd3b11d082e05143e1bb6d31c08ee2c010efd34de093cf580` | `63a1f8eca6901d817025bf0ad76fd9a276175b295ce2d8618824c246e986fcd5` |
| Full attempted source denominator | 1,683 | 1,683 |

The original manifests name Producer revisions
`a9c799397a74641a0e16c8ea84454d2dc4d0745b` (previous) and
`1f777aa2d7631e853a20c1777d8e2333fa1f1d38` (current), respectively.

Digests retain native prefixes `daily_research_session_operation:` and
`integrated_investment_decision_product/v1:` respectively.

Explicit selected cohort: FPT, HPG, NVL, PNJ, POW, PVD, QNS, SSI, VNM, VRE.
Initial successful renderer: 10 comparable selections, 1,673 excluded, zero missing;
7 POSTURE_UNCHANGED, 2 POSTURE_CHANGED_OTHER, 1 AVOID_TO_RECOVERY_WATCH. No selected
EARLY_WATCH persistence, setup-to-confirmation, failed/invalidation transition or
PRIORITY_NOW/WAIT disagreement. All 20 trigger/invalidation numeric boundaries
were withheld. QNS is the real AVOID → EARLY_WATCH example; this is research
attention with its retained future confirmation and invalidation conditions, not
capital authorization. Aggregate counts are not a classifier-only acceptance:
the investor Markdown actually rendered for all ten tickers after both proofs.

Validation includes native hash equivalence (Unicode, nested data, floats, exact
identity exclusions), all-row tampering, schema/record/operation mismatches,
duplicate/nonnumeric/oversized/malformed/truncated JSON, policy epochs, confirmation
membership, price dimensions, resource refusal before reads, selected/full scope,
privacy and read-only calls, deterministic repeated identity, and a 10 → 1,000
record stress case retaining exactly one row without proportional memory growth.
Baseline focused tests: **87 passed**. Final focused preview tests: **45 passed**.
The broad candidate run returned **483 passed, 1 skipped, 11 failed, 17 errors**;
the identical released-main neighbour run returned **443 passed, 1 skipped,
11 failed, 17 errors** (the earlier candidate run included 40 new tests; five
subsequent schema/resource/iterator/replay tests are included in the final 45-test focused pass).
All **28 failure/error IDs are identical**, all in the existing
`test_next_session_decision_brief.py` suite's August-28 latest-session fixture
assumption; the actual current pointer is October 15. There are zero new failing
IDs and zero hidden fixture rewrites. The broad pass includes default golden
identities, Integrated Decision, existing stream/feedback, brief posture comparison,
Conditional Opportunity, setup transition, Action Center, call-shape, E0 ratchet,
registry/session qualification, roadmap and governance-tool tests. The native
lane scope check passes with no unmet dependencies. `py_compile` and
`git diff --check` pass.

The additional native parallel-domain, declaration-amendment and active-control
plane suites passed **109 tests** in **759.79 seconds**, including exact owner
succession, refusal, historical-lane and durable-lease preservation cases.
All historical lane records were also compared directly against coordinator
`178768fa`: every existing record, including both VRE lanes, remains identical.
Producer main remains `ee27482d`; its native checkout-cleanliness classification
is PASS (zero tracked dirt or unsafe untracked paths; existing governed runtime
files are retained). No Daily launch or host READY claim is made.

Final real result: **COMPLETE_LOCAL_REAL_SESSION_ACCEPTED**, with preview identity
`action_center_selected_research_preview/v1:b7e8b69e784864349b43731eecfbb4dcb4b62834b1fc62e1f64df248a5e2e2ec`.
The original source identities, selected counts and transition labels match the
initial rendering. Final elapsed time **100.2197 seconds**; OS peak resident
**172,118,016 bytes** (164.14 MiB), incremental resident **56,815,616 bytes**
(54.18 MiB), incremental private commit **56,115,200 bytes** (53.52 MiB).
Available physical memory at admission was **1,231,175,680 bytes**. Measured reads:
**2,852,302,361 bytes**, with zero read-only evaluator write operations before
explicit output publication. Actual consumer mismatch: **none**.

One intervening final-run attempt refused at PREVIEW_RESOURCE_BUDGET_REFUSED before
either large source was opened. No threshold was changed and no process was killed.
After the native test suite finished, memory availability changed; a fresh native
consumer admission passed and the complete final evaluation above succeeded.
There was no background polling/sleep/retry loop. Earlier successful previews
retain the same final content identity, and remain local diagnostic evidence.

Selected numeric reasons: PRICE_BASIS_UNVERIFIED **20**,
CONDITION_NOT_MACHINE_EVALUABLE **7** (reasons overlap). Missing or non-comparable
selected cases: **0**. Current numbers remain withheld; raw qualitative context,
future conditions and source provenance remain visible.

Local review evidence lives in the operator's external job report directory:
`accepted-checkpoint/{preview.json,preview.md,measurements.json}`,
`regression-comparison.json`, test transcripts and native query receipts.
Those local paths are not additional artifact authorities or production outputs.
No private portfolio data is committed. Source-release review is the next gate;
no push, PR, merge, deploy, publication or production activation is authorized.
