# E1 official exchange evidence package migration

Owner-admitted structural relocation, based on verified main
`56cdc36f860532678ae2c8c26eddea2730988ef8` (PR123 E0 merge; post-merge Producer CI
run `38139163689`, four jobs success). Native execution state remains `ROADMAP_STATE.json`.
`authority_effect` is NONE: no evidence, identity, PIT, source-authority, Daily, launcher
or Consumer/Dashboard change. No push, PR, merge, E2 or production write follows.

## Frozen cohort

Thirteen official exchange disclosure/event-evidence modules moved from the repository root
to `stocklookup_core/evidence/` with byte-identical bodies except their own cohort imports:

| Module | Role |
|---|---|
| `corporate_action_events` | typed corporate-action extraction from retained official documents |
| `corporate_action_evidence_registry` | official stock-dividend promotion / shadow share factor |
| `hnx_disclosure_feed_parser` | HNX disclosure RSS/detail parsing from stored bytes |
| `hnx_filing_evidence_binding` | HNX filing parent binding |
| `hnx_financial_filing_scaleout` | HNX financial filing discovery over the document store |
| `hnx_multi_attachment_binding` | HNX multi-attachment parent binding |
| `hnx_official_issuer_profile_multi_gate` | HNX issuer-profile fetch/retain/parse |
| `hose_source_surface_authority_qualification` | HOSE surface catalog qualification |
| `insider_and_major_holder_events` | insider / major-holder event projection |
| `official_authority_candidates` | registered, inactive official authority candidates |
| `official_issuer_disclosure_registry` | retained issuer-disclosure projection |
| `official_listing_page_parser` | official listing-page candidate links |
| `real_official_corporate_action_factor_evidence` | real official factor-candidate selection |

The cohort was reconstructed from the AST import graph because the design inventory was
not available in the workspace. Membership evidence: no static reachability from
`stocklookup.py`, `tools/run_owner_daily.py` or any of the 31 reviewed path-launch targets;
no internal cycle; exactly three outward dependencies (`official_source_registry`,
`official_financial_period_identity`, `stocklookup_core.evidence.official_document_store`);
no `__file__`, `sys.path`, dynamic-import, source-digest, provider-bundle or
path-launch reference; no sibling-repository consumer.

## Compatibility

No root shim and no compatibility entrypoint: the only importers are 12 offline `tools/`
runners and 20 test files (41 import sites), all updated to absolute `stocklookup_core.evidence` imports
(`import X as Y` keeps its alias; `from X import ...` keeps its names). Old root paths are absent,
removed from `grandfathered_root_python` and recorded in `config/repository_layout.json`
relocations (107 → 120). Recreating a root copy fails the placement guard.
Docstrings, comments and serialized labels that name the old module/file (for example the
`route` label written by `derive_current_common_shares_authority_recovery_v1.py` and the
`corporate_action_events` manifest key) are identity text and stay byte-identical.

## Dependency ratchet

The sealed E0 baseline is unchanged (identity digest still verified). Five existing
root edges become `evidence → root` names after relocation. `tools/check_architecture.py`
accepts such a row only if it is listed in `relocated_debt_edges` of
`config/architecture_dependency_policy.json` **and**, after reversing the layout relocation,
equals an exact sealed-baseline edge (same context and form). Unrelocated rows, new targets,
lazy-to-module-load promotion and stale rows fail; without the layout manifest nothing is
carried. The debt is carried, not approved. No new cycle, unresolved or unsupported dynamic site.

## Acceptance

Local implementation checkpoint `fbee4265a559255a7d91e707ccb8344928660288`; native disposition
`LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED`. Owner review/push/PR is the next gate; no E2.
[Retained acceptance](internal/E1_LOCAL_ACCEPTANCE_20261011.md).

## Verified release

PR124 merged by Owner at `e99000494ab52374c01383f4c57891165b58768f`; candidate
`8443a19132436236621e52ad85e2f1ffd407fa3b` is an ancestor. Four pre-merge jobs
PASS (38147082549) and four post-merge jobs PASS (38148897543). The earlier
local-only gate above records the historical checkpoint; E2/E3 has a separate
explicit Owner admission. Evidence and production authority remain unchanged.
