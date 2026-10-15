# Parallel domain development control plane V1

Owner-approved source-development extension of the existing roadmap authority.
`docs/ROADMAP_STATE.json` remains the only execution-state source; the existing
`current`, milestones, queue, checkpoints and historical bytes retain their meaning.
The optional `development_control` object uses `stocklookup_development_lanes/1`.
Absent extension: all existing admission/continuation/closeout behavior is unchanged.
Once initialized, unscoped legacy mutations are refused; use scoped lane operations
while preserving the historical current pointer. Read-only legacy queries remain.

## Authority and roles

Development writers (Codex, Claude, Grok) own explicitly admitted domains and paths
in separate registered branches/worktrees. Reviewers and external researchers are
read-only. SHADOW work is source experimentation without release eligibility.
Only the bound integration agent changes shared execution state and controls the
integration/release process. Lane commands never merge, fetch, create worktrees,
run tests, publish, deploy, or grant runtime/database/evidence authority.
Owner merge approval and existing single production writer, host admission,
session seals and evidence-use contracts remain mandatory and unchanged.

Identity is an explicit local attestation, as with the existing owner override;
the CLI does not authenticate humans or sandbox an arbitrary editor. Git/PR review
and branch protection remain enforcement boundaries. Merely naming an agent or
passing an override is not a human approval. Spec/receipt files are inputs and
evidence, not competing execution-state registries.

## Coordinator and admission

After release, the Owner designates one integration checkout and agent. Execute
the released CLI with `--repo <integration-checkout>` and
`--state-file <integration-checkout>/docs/ROADMAP_STATE.json` for every mutation.
`--init-lanes --agent Integrator --owner-override --scope-note <exact-directive>`
binds its exact branch/path. No default migration or automatic admission occurs.
Branches consult that same state file; editing their copied roadmap is forbidden.
Coordinator changes must be committed/reviewed and carried forward by the integration
owner; another checkout's copied state cannot silently become the coordinator.
CI/foreign clones validate structural lane state and legacy Git checkpoints; live
lane observations are explicitly SKIPPED_NON_COORDINATOR_CLONE, with a warning.
That result grants no lane start or integration permission. On the bound host,
native checks verify live lanes; `--check-lane` and integration operations always
require their real registered worktrees, even when invoked from another clone.

Each lane spec supplies: milestone_id, responsible_agent, branch, worktree, exact
40-character base_sha, domain, mode, allowed_paths, shared_paths, dependencies,
provides, consumes, required_checks; lease_note is required for any shared lease.
No checkpoint/state/authority fields may be injected. Admission requires an exact
new ID, registered clean worktree at base, correct repository and branch identity,
explicit Owner scope note and disjoint domains/paths. No main/coordinator branch
may be a development lane. No source permissions follow from an existing worktree.

Paths are exact relative files or trailing-slash directory prefixes. Globs,
traversal, absolute paths and platform-specific separators are rejected. Case-folded
overlap detection is conservative across Windows/Linux. Shared governance, configs,
CI, dependencies, source registries and release entrypoints require an exact-file
lease to the integration owner, with a narrowly approved note. Directory leases
cannot authorize shared files. Protected data/evidence/runtime/Git/scratch paths
are never development scope. Existing frozen-source / reviewed-launcher manifest
members require an exact integration lease; manifests are read at immutable base.
This is bounded navigation coverage, not exhaustive dynamic identity discovery.
Check-lane examines committed, staged, unstaged and
untracked names, including both sides of renames; it does not read their payloads.
Ignored runtime files are not proof of safe deletion and are outside this tool.

## Lifecycle and crash recovery

ADMITTED → ACTIVE → REVIEW_READY → COMPLETE_LOCAL → MERGED_RELEASED.
ACTIVE → PAUSED → ACTIVE is the interruption path; ADMITTED/ACTIVE/PAUSED may be
ABANDONED without deleting anything. Review-ready/local-complete may return ACTIVE
for corrections, retaining history. Completed/released state cannot be reopened by
inference. Nonimplementation modes cannot enter any release-candidate/completion state.

`--transition-lane ID --lane-state STATE --agent Integrator --owner-override
--scope-note <exact-directive>` records one lane, leaving all others and legacy
milestones intact. PAUSED/REVIEW_READY/COMPLETE_LOCAL/MERGED_RELEASED require
`--checkpoint-at <full-live-clean-HEAD>`. Commit first; never represent uncommitted
work as a durable checkpoint. Keep external handoffs for outstanding dirty work.
ACTIVE requires dependencies COMPLETE_LOCAL or released/legacy-complete; integration
requires dependencies actually released and reachable from exact main. No automatic
dependency promotion. Checkpoints must stay ancestors of the real branch HEAD.

Mutations use a nonblocking, process-released OS lock, byte comparison and fsynced
atomic replacement. Concurrent stale state fails with reload-required; no polling,
background coordinator or persistent lock ownership. A crash preserves either old
or new complete state, including revision/history and exact lane checkpoints.
Legacy JSON is preserved textually; only the extension changes through lane commands.

## Declaration-only correction extension

`--amend-lane-declarations --declaration-spec <reviewed-batch>` adds an explicit
metadata-only operation to the existing CLI. It uses the same native coordinator,
bound integration owner, Owner directive, lock, byte CAS and atomic writer. The
existing schema and legacy queries/commands remain unchanged. A locally admitted,
validated candidate CLI may be used for this Owner-authorized local correction;
that use does not authorize merging or releasing the extension.

The batch schema is `stocklookup_lane_declaration_amendment/1`, with exact
`expected_revision` and a nonempty `amendments` list. Each item contains only
`milestone_id`, the preserved `checkpoint`, `before`, `after`, and `review_note`.
Both declaration maps contain exactly `provides`, `consumes`, `dependencies`.
Targets must be IMPLEMENTATION lanes at exact clean REVIEW_READY/COMPLETE_LOCAL
checkpoints, with matching before-values. Duplicate targets, stale revision/HEAD,
dirty sources, terminal lanes, reserved fields, malformed declarations, cycles,
duplicate interface owners, mismatched versions, missing direct dependencies and
new/orphaned consumed interfaces fail without writing anything. Existing
dependencies cannot be removed by this narrow operation.

All items are validated together before one atomic write. A correction appends a
single global `AMEND_DECLARATIONS` event and one event per affected lane, retaining
exact before/after declarations and review notes. Historical event prefixes and
unrelated lanes are preserved. IDs, branches, worktrees, bases, leases, ownership,
checkpoints, states, required checks and authority cannot be supplied or changed.
No reopening, lease transfer, release, dependency promotion or new authority is
performed. The normal integration plan still enforces actual released dependencies,
main/checkpoint ancestry, file conflicts and fresh exact review/test receipts.

The October14 correction distinguishes Home's optional-card builder from its
consumer/restaging interface and OCR's extraction-qualified assets candidate.
It removes a nonexistent financial-input publication declaration from Home; it
does not publish that input or a financial metric. Governance source merge remains
an explicit Owner review gate.

## Integration owner succession

`--transfer-integration-owner --transfer-spec <owner-reviewed-spec>` hands the single
integration-owner role to an Owner-appointed successor, for example when the bound agent
can no longer run. It runs only in the bound coordinator worktree and branch, with the
explicit Owner directive, lock, byte CAS and atomic writer. `--agent` must equal the
spec's successor, and the spec must name the current owner as predecessor. That makes it
a recorded succession, not impersonation or a second writer.

The schema is `stocklookup_integration_owner_transfer/1`. It has exactly these keys:
`expected_revision`, `from_agent`, `to_agent`, the exact clean `coordinator_head`, and
`successor_lanes`. Each lane entry is a `milestone_id` with its exact `state`,
`checkpoint` and worktree `head`. The list must name exactly the predecessor's in-flight
lanes (ADMITTED, ACTIVE, PAUSED or REVIEW_READY), and only their responsible agent
changes. The command refuses to run when:

- the revision, owner or HEAD is stale;
- the coordinator is dirty;
- a lane's state or head has changed;
- an in-flight lane is omitted or an extra lane is named;
- the transfer is a no-op;
- the spec has reserved fields;
- the acting agent is not the named successor.

A refusal writes nothing.

A predecessor's COMPLETE_LOCAL and terminal records keep their agent and leases unchanged.
Those leases stay valid until that lane's own normal release, so a transfer never takes
over or reopens unrelated work. The command appends one global `INTEGRATION_OWNER_TRANSFER`
event plus one event per transferred lane, and adds an `integration_owner_succession`
chain entry. Validation then requires every in-flight leased lane to belong to the
current owner.

## Integration planning

`--integration-plan --main-sha <observed-main> [--candidate-lane ID]` reads
`ls-remote origin refs/heads/main` and requires the local origin/main to match.
It does not fetch. Stale metadata, unavailable remote, dirty/unreviewed candidates,
base/checkpoint mismatch, same-file changes, main overlap, unsatisfied release
dependencies and declared interface-version/owner conflicts fail closed.
Ordering is deterministic dependency order with lexical ties. A dependent successor
does not stop planning its prerequisite via `--candidate-lane`.

Interface declarations are semantic review inputs, not automatic import/schema
compatibility proof. Include canonical and cross-repo API contracts and frozen
identity/pin impacts in explicit provides/consumes version declarations and tests.
Every candidate needs an exact plan receipt: plan_identity, reviewed_by (integration
owner), review_note, cross_repo_review, frozen_identity_review, checks mapping
lane ID → required check → status PASS + evidence locator. Recheck after main or
candidate changes; the identity binds heads, changed files, declared interfaces,
dependencies/order and check requirements. A receipt is an attestation to actual
tests/review, not a substitute for running them. Unknown semantic impacts remain
blocked until the responsible reviewer supplies that proof.

For shared pins/CI changes, review actual source identity and dispatch effects;
regenerate normalized workflow hash only after reviewing the changed workflow.
No automatic frozen repin or architecture baseline refresh is implemented.
No clean/green branch auto-merges. A behind but disjoint candidate can be checked
against new main using an external temporary integration fixture and fresh exact
receipt; the original branch need not be reset or rebased. Same-file overlap needs
a reviewed forward merge/correction and new checks, never silent conflict resolution.

MERGED_RELEASED additionally requires actual checkpoint ancestry of exact remote
main, an exact post-merge review receipt, Owner merge directive and post-merge CI
evidence. It records a merge already performed by an authorized integration owner;
it does not perform one. Runtime authorization is always false in lane reports.
Squash/rebase merges that do not preserve candidate ancestry require a separately
reviewed future equivalence contract; this version does not guess patch equivalence.

## Command example (after Owner admits each exact scope)

## Explicit two-lane coupled source release

The optional `--coupled-spec` on `--integration-plan` accepts exactly two clean,
durable source candidates linked by a declared dependency, their exact checkpoints,
one immutable integration fixture SHA and retained failed standalone checks.
Schema: `stocklookup_coupled_source_release/1`; keys: `schema`, `checkpoints`,
`fixture_sha`, `standalone_failures`. Failures name actual required checks with
`status:FAIL` and evidence; they are retained separately from joint acceptance.

The fixture must contain both checkpoint ancestries and exact changed source blobs,
with no additional paths against main. A dependent base may belong to its selected
producer only by actual ancestry. External dependencies must already be released
on verified main. All existing lease, interface/version, cycle, clean-HEAD, main
overlap, frozen review and required-check receipt gates remain. The exact plan binds
the group, fixture, original failures and coordinator revision. Checks attest the
combined fixture explicitly; no standalone PASS is inferred. Ordinary plans and
single-lane release rules are unchanged.

`--release-coupled-lanes --coupled-spec ...` uses the same bound owner, explicit
Owner directive, lock/CAS/fsynced atomic writer. It requires a fresh exact post-merge
joint receipt, Owner merge directive, post-merge CI evidence, both original checkpoints
and the exact fixture actually ancestral to independently verified remote main.
Only then are both true `MERGED_RELEASED` records appended in dependency order in
one atomic revision. There is no intermediate dependency promotion, lease bypass or
release before source is on main. Original checkpoints, identities, owners, leases,
history prefixes and unrelated lanes remain. Runtime/authority effects remain NONE.
This bounded operation permits the semantically coupled Home/restage release;
it does not execute merges, tests, publication or deployment.

## Admission example

In an isolated integration checkout, initialize once using the command above.
Create developer worktrees separately using ordinary reviewed Git procedures.
An example financial lane spec (absolute worktree supplied locally):

```json
{"milestone_id":"OFFICIAL_FINANCIAL_DEV","responsible_agent":"Codex",
 "branch":"feature/official-financial-dev","worktree":"<absolute-worktree>",
 "base_sha":"<full-main-SHA>","domain":"financial-evidence","mode":"IMPLEMENTATION",
 "allowed_paths":["stocklookup_core/financial/","tests/test_financial_lane.py"],
 "shared_paths":[],"dependencies":[],"provides":{},"consumes":{},
 "required_checks":["financial-contracts","integration-offline"]}
```

Claude's separately reviewed spec may own `tools/reliability/` plus its exact tests
with domain `architecture-reliability`; Grok's may own a disjoint acquisition
component and tests with domain `official-acquisition`. These are examples, not
admission of the current prototypes or HPG facts. Source registry changes go through
the integration owner, not an adapter's directory ownership.

```text
python tools/stocklookup_roadmap.py --repo <coordinator> --state-file <native-state> --admit-lane OFFICIAL_FINANCIAL_DEV --lane-spec <financial-spec> --agent Integrator --owner-override --scope-note <Owner-directive>
python tools/stocklookup_roadmap.py --repo <coordinator> --state-file <native-state> --transition-lane OFFICIAL_FINANCIAL_DEV --lane-state ACTIVE --agent Integrator --owner-override --scope-note <Owner-directive>
python tools/stocklookup_roadmap.py --repo <developer> --state-file <native-state> --check-lane OFFICIAL_FINANCIAL_DEV
# Developer checks/commits, then Integrator records REVIEW_READY with --checkpoint-at.
python tools/stocklookup_roadmap.py --repo <coordinator> --state-file <native-state> --integration-plan --main-sha <remote-main> --candidate-lane OFFICIAL_FINANCIAL_DEV
# Run named integration tests in an isolated fixture, review APIs/frozen identities.
python tools/stocklookup_roadmap.py --repo <coordinator> --state-file <native-state> --integration-plan --main-sha <remote-main> --candidate-lane OFFICIAL_FINANCIAL_DEV --review-receipt <exact-receipt>
# Stop at Owner merge approval. After separately authorized merge and green CI,
# obtain a fresh post-merge plan/receipt and record MERGED_RELEASED with exact HEAD/main.
```

The same admission/check/checkpoint commands apply independently to Claude and Grok.
The hermetic tests execute these actual commands with three registered temporary
worktrees and a local bare remote, integrate A and verify unchanged B against new
main, and assert shared/state/authority restrictions. No production Daily or secrets
are needed. Optional GitHub merge queue/branch-protection configuration is a later
Owner administration decision; this milestone changes neither.
