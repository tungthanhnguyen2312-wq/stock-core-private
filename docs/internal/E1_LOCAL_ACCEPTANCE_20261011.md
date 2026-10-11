# E1 local acceptance — 2026-10-11

Base: verified main `56cdc36f860532678ae2c8c26eddea2730988ef8` (PR123 E0 merge; post-merge run
`38139163689`, four jobs success). Branch `refactor/e1-official-exchange-evidence-migration-20261011`.
Python 3.13 on Windows; `PYTHONPATH=tests/provider_import_block`; markers
`not retained_evidence and not provider_runtime` unless stated.

## Relocation

13 modules root → `stocklookup_core/evidence/`; root Python 489 → 476, tracked root files 507 → 494.
Layout relocations 107 → 120; grandfathered root list 501 → 488; compatibility entrypoints unchanged (1).
9 bodies byte-identical; 4 differ only by their one cohort import line. 41 import sites rewritten
(4 package, 20 test files, 12 tools); no root shim, no compatibility entrypoint, no cross-repository consumer.

## Results

| Check | Before (`56cdc36`) | After |
|---|---|---|
| Focused cohort + structural selection, 34 files, hermetic | 655 pass / 4 fail / 43 skip | 659 / 4 / 43; 0 outcome changes, +4 new guard tests |
| Same selection with retained evidence copied read-only (VCB/HPG/SSI/VNM real artifacts) | 698 / 4+2 err / 2 | 702 / 4+2 err / 2; 0 outcome changes |
| Structural + production smoke + Owner Daily launcher | — | 155 pass |
| CI focused selection, first 130 of 263 entries | — | 2357 pass / 24 skip / 0 fail |
| CI focused selection, remaining 133 entries | — | 3160 pass / 19 skip / 0 fail (all 263: 5517 pass / 43 skip / 0 fail) |
| `check_architecture.py` / `check_daily_launchers.py` | PASS / PASS | PASS / PASS |
| Public-name identity fingerprint, 13 modules / 368 names, both import orders, `PYTHONHASHSEED=0` | `7c5deb3e…` | `7c5deb3e…` (equal) |

Residual failures are identical before and after and outside the cohort: two
`test_current_common_shares_authority_recovery_v1` resolver tests (partial retained evidence in the
worktree) and two `test_official_source_registry_owner_promotion` tests whose fixtures are refused by
the canonical-evidence write guard. Not E1 defects.

## Incident

An import check of the 12 updated runners imported `tools/run_hose_source_surface_authority_qualification.py`,
which has no `__main__` guard (pre-existing). It performed five public GETs to hsx.vn and wrote a fresh
qualification artifact under the E1 worktree's gitignored `operations-review/`. The output was deleted;
canonical retained evidence (`12:21` artifact) and production were not touched. The missing guard is
recorded as a pre-existing hazard, not changed by E1.

Evidence (JUnit XML, digests, scripts, edit list, fingerprints) is retained outside Git in
`claude-reports/e1-official-exchange-evidence-migration-20261011/` in the workspace.
