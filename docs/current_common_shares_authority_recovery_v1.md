# Current common-share authority recovery and scale-out V1 (2026-08-27)

`tools/derive_current_common_shares_authority_recovery_v1.py` advances the existing
`current_common_shares_authority.py` lane at the current session (2026-08-26) using retained and
already-approved evidence routes. It is not a new valuation engine: it reuses, unchanged,
`market_wide_current_shares_resolver.resolve_market_wide_shares`,
`current_common_shares_authority.build_current_common_shares_authority`, and
`market_wide_current_valuation_input_scaleout.build_current_valuation_artifact`.

## What changed

A live, read-only re-run of the resolver against the retained `dashboard-runtime` evidence
(`vn_stock.db` + `data/official-evidence/share_basis_citations.jsonl`) at session 2026-08-26
reproduces the same ceiling as the frozen 2026-08-25 authority artifact, with one exception: four
tickers (SSI, HCC, IPA, NAG) had a share-changing event whose ex-date has since passed, while the
only retained provider (`VCI.overview.issue_share`) observation still predated it. A bounded
re-observation of that same already-approved route (13 live requests total: 6 HNX issuer-profile,
2 VCI `events()`, 5 VCI `overview()`; zero retries; zero `vn_stock.db` writes) shows each of the
four now carries a fresh, dated, post-event issued-share count that reconciles exactly to a clean
whole-percent ratio against its retained corporate action (SSI +20.0% bonus, HCC +10.0% stock
dividend, IPA +15.0% bonus, NAG +5.8% stock dividend). Applying that as a cited, ticker-scoped
override moves all four from a fully blocked, no-value tier
(`UNVERIFIABLE_FRESHNESS` / `CORPORATE_ACTION_RECONCILIATION_REQUIRED`) to
`PROVIDER_REPORTED_CURRENT_RESEARCH` -- research-usable, still explicitly non-authoritative.

HPG and VCB were rechecked with the identical bounded-route pattern and both reconfirm their
existing ceiling: HPG's official anchor still has no independent corroboration past its retained
2026-08-14 observation (short of the 2026-08-26 session), and VCB's most recent share-issue event
is still undated at the provider. Neither changes. No ticker reaches
`QUALIFIED_CURRENT_COMMON_SHARES`: a fresher issued-share re-observation is a provider proxy, not
an official anchor, and freshness alone never promotes semantic authority (`SOURCE_AND_SEMANTIC_
QUALIFICATION` and `TEMPORAL_SHARE_CONTRACT` in `current_common_shares_authority.py` are
unmodified).

Isolated retained-mode valuation (three points, to separate the code-path switch from the
evidence effect) shows the frozen 26/8 baseline (`share_authority_artifact=None`) at
`market_cap` research-usable 887; the same evidence routed through `share_authority_artifact`
with no new evidence at 884; and the recovered artifact at 888. `P/E` moves 8 -> 9, `P/B` moves
9 -> 10. `READY` and `VALUE` stay 0/1,507 throughout -- research-usable is not authoritative, and
this milestone does not activate VALUE.

## Fix alongside

`market_wide_current_shares_resolver.py`'s successful `qualified_official` result previously
omitted `ledger_coverage_status` and the corroborating observation date -- both were already
computed and already carried on the *failure* path, just not the success path. A consumer could
not tell whether "no later share-changing event recorded" rested on a complete or a bounded
(`partial_unqualified_50_row_cap`) ledger read. Both fields are now present on every result;
this is additive only and does not change any tier or value.

## What did not change

- No provider source was promoted to official authority.
- No new market-data provider was added; every request reused
  `vnstock.api.company.Company(source="VCI")` and `hnx_official_issuer_profile_multi_gate.py`'s
  existing `fetch`/`retain`/`parse_profile` functions unmodified.
- `vn_stock.db` was not written to; every re-observation is retained as a separate, hash-verified
  evidence file under
  `operations-review/current-common-shares-authority-recovery-and-scaleout-v1-20260827/`.
- No frozen 2026-08-21/24/26 artifact was rewritten; every output here is a new file.
- VALUE strategy activation and RAW_AS_TRADED/PIT promotion remain untouched.

See `operations-review/current-common-shares-authority-recovery-and-scaleout-v1-20260827/recovery_report.json`
for the full before/after inventory, acquisition budget, and valuation isolation detail.
