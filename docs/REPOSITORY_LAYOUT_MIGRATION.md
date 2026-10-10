# Repository Layout Migration

Status: GOVERNED_MIGRATION_PLAN / NON-AUTHORITY

Date: 2026-10-01

This document defines how Stock Lookup will improve repository structure without turning cleanup into a risky wholesale refactor.

## 1. Current problem

The public `main` root currently exposes hundreds of top-level Python modules. On the 2026-10-01 baseline it contained 577 entries, including 551 `.py` files and only 8 directories.

That creates three problems:

1. the GitHub front door is difficult for humans to understand;
2. capability boundaries are not visible from the filesystem;
3. coding agents face a very large flat namespace and can more easily confuse current, historical, operational, and consumer-facing modules.

This is real technical debt, but it is not justification for a one-shot package migration.

## 2. Target shape

The 2026-10-10 admitted scope uses ordinary source-checkout packages. No packaging
system or installation is added; `stocklookup.py` stays the owner CLI. The target is:

```text
stock-core/
├─ stocklookup.py / stocklookup.ps1
├─ stocklookup_core/
│  ├─ acquisition/  # landing contract, isolation, checkpoint and retention
│  ├─ evidence/     # official documents and temporal receipts
│  └─ research/     # independent thesis research
├─ tools/           # existing operator and developer launchers
├─ tests/
├─ contracts/
├─ config/
└─ docs/            # active navigation, contracts and preserved history
```

Admission and safety boundaries: [V1 contract](repository_root_structure_simplification_v1_contract.md).
The measured starting HEAD has 613 root files, including 595 Python files, plus 8
directories. Each slice records exact counts and validation before committing.
`config/repository_layout.json` owns the migration map and root placement exceptions.
CI rejects new root Python names; this is a placement rule, not a deletion quota.

## 3. Migration rules

A capability family may move only when all of the following are known:

- production entry points;
- direct and indirect imports;
- subprocess/path-based invocation;
- tests and fixtures;
- runtime/generated-path assumptions;
- public documentation links;
- compatibility shims, if required.

Never classify a module as dead or legacy from its filename alone.

Do not perform a repository-wide import rewrite.

Do not move `operations-review/` merely for aesthetics; some runtime contracts read exact retained paths.

Do not hide operational evidence with a global ignore rule when current code still consumes it.

## 4. Strangler migration strategy

Migration happens alongside useful roadmap work.

For each capability family:

1. freeze the current behavior with focused tests;
2. map its call graph;
3. create the destination package boundary;
4. move one coherent family;
5. update imports and explicit subprocess paths;
6. preserve a compatibility import/shim only where a live consumer requires it;
7. run focused regression + production call-shape checks;
8. remove the old root module only after no production consumer references it;
9. update `docs/SYSTEM_MAP.md`.

A migration must not change analytical output, authority, thresholds, acquisition semantics, or publication behavior unless the capability milestone explicitly calls for such a change.

## 5. Suggested family order

The exact order is dependency-driven, but a reasonable default is:

1. low-risk shared utilities and pure contracts;
2. evidence / temporal contracts;
3. financial analysis family;
4. valuation family;
5. tactical / market research family;
6. integrated decision family;
7. publishing / handoff family;
8. daily orchestration last.

Daily orchestration should move late because it binds many root paths and subprocess entry points.

## 6. Public-root target

The root should eventually contain only front-door and compatibility files, approximately 10–20 entries rather than hundreds of implementation modules.

Expected root categories:

- README / LICENSE / CONTRIBUTING / SECURITY;
- dependency and packaging metadata;
- owner CLI / PowerShell entry point;
- a very small number of explicit compatibility launchers;
- top-level directories.

## 7. Naming

The current public repository name still contains `-private`. Renaming it is deferred until:

- package boundaries are stable;
- automation/remotes/worktrees can be updated atomically;
- documentation and release links are inventoried.

A future public-facing name such as `stock-core` or `stocklookup-core` is preferable, but repository rename is an account-level operation and remains separately governed.

## 8. Acceptance criteria

Repository-layout work is successful only when it improves navigation without reducing operational reliability.

For every migration slice:

- tests for the moved capability pass;
- production call-shape checks pass;
- no generated/runtime data enters source Git;
- no stale import path remains in current production entry points;
- no authority changes occur by side effect;
- `git diff --check` passes;
- `docs/SYSTEM_MAP.md` remains truthful.

The owner explicitly made bounded root simplification the current scope on 2026-10-10.
It changes source layout only. Analytical roadmap work is reassessed after acceptance
and never starts automatically from this maintenance milestone.
