# P1J.1 — Current-share authority integrity repair

Milestone operations review. Date: **2026-08-03**. Base commit: `987d632` (Producer),
`66733a4` (Consumer). Runtime root: `C:\Projects\StockLookup\dashboard-runtime`.

Not a feature milestone. P1H, P1I and P1J each reported a market-wide result that the pipeline
did not compute, on top of an official anchor table that was wrong in two of its three entries.
This milestone makes every number in that chain a measurement with lineage, or removes it.

---

## 1. What was wrong

### F1 — The coverage counts were literals

`tools/operate_stocklookup.py::report()` carried `active_universe_count: 1683`,
`pe_ready_count: 1391` and eleven siblings as hardcoded values in a dict literal. Advancing
the milestone meant editing them by hand: commit `5209447`'s diff changes `1679 → 1677` and
`1393 → 1391` as source edits. Nothing in the operating command called
`resolve_market_wide_shares()`; the only callers were the tests and a per-ticker path used by
the 12-ticker bundle export.

The block would have printed those numbers for any runtime root, including an empty one. The
last real production report — `reports/operate_stocklookup_latest.json`, 2026-08-03T01:03Z —
carries `market_wide_shares_coverage: null`, so no run has ever emitted them.

### F2 — Two of the three official anchors were wrong

`QUALIFIED_SHARES` in the resolver held three literals presented as `qualified_official`, the
system's highest authority tier. Against `data/official-evidence/share_basis_citations.jsonl`:

| ticker | resolver literal | official citation | provider (`metadata`, obs. 2026-07-30) |
| --- | --- | --- | --- |
| HPG | 7,163,748,865 | 6,396,250,200 | **8,442,964,520** |
| VNM | 2,089,955,445 | 2,089,955,445 | 2,089,955,445 |
| VCB | 5,589,091,2**22** | 5,589,091,2**62** | 8,355,675,094 |

- **HPG's literal appears in no citation and in no ledger.** Its stated lineage is
  `6,396,250,200 + 767,498,665`, but the qualified stock-dividend event records
  `shares_after = 8,442,964,520`, and the event's own ratio fixes the pre-event base at
  `767,498,665 / 0.0999937567 = 7,675,465,852`, not 6,396,250,200. The FY2024 period-end
  figure was used as the event base when the company had already issued shares between the
  FY2024 close and the dividend. The resolver was overriding a correct provider value with a
  fabricated one **15% too low**.
- **VCB's literal is the citation mistyped by 40 shares**, and the citation is in any case an
  FY2024 period-end figure being served as a current share count while the provider reports
  8,355,675,094 — a 49% divergence that the "exact agreement" line in P1J's review did not
  detect because it compared the literal against itself.
- P1J's review recorded HPG's *provider* value as 6,396,250,200. The database holds
  8,442,964,520. The review's workstream B table was wrong on both HPG rows and on VCB.

### F3 — The session was a default, not an input

`resolve_effective_shares(ticker, runtime_root, target_date="2026-07-30")`. The only
production caller, `canonical_financial_bundle_section.py`, passed no `target_date`, so every
export stamped 2026-07-30 onto its share results regardless of the session being exported.

Separately, `Operator.run()` called `self.preflight_database()` again after `prepare_inputs()`
but discarded the return, so a `--prepare-inputs` run bound the taxonomy sidecar to the session
that preceded the input refresh.

### F4 — The freshness rule was inverted, and fired on the wrong events

`_get_stale_corporate_event_tickers()` selected any ticker with an event dated after a fixed
literal `'2024-12-31'`, across `exright_date`, `record_date` *or* `issue_date`, for any event
category. Three consequences:

- It compared against a constant, not against the provider observation date, so it invalidated
  share counts on events the observation already reflects. HPG is the live case: its
  2026-06-04 dividend is fully reflected in the 2026-07-30 observation.
- It fired on `MAJOR_SHAREHOLDER_TRADING`, `SHAREHOLDER_MEETING` and `OTHER` events, none of
  which change a share count.
- `record_date` and `issue_date` were treated as interchangeable with an ex-right date, which
  `docs/STATE.md` already forbids elsewhere.

The retained ledger covers **5 of 1,683 tickers** at `coverage_status =
partial_unqualified_50_row_cap`. The "2 stale" headline was 5 covered tickers minus the 3 in
the hardcoded qualified table — an artefact of table membership, not a market-wide finding.

On error the function returned an empty set, so an unreadable ledger silently promoted the
entire universe to `provider_reported_current`. The value lookup swallowed exceptions the same
way and reported a failed read as "no valid retained share observation found".

### F5 — The price leg carried no authority

`evaluate_market_capitalisation()` set `status = qualified` whenever the *share* status was
qualified, with no reference to the price basis. The bundle root has been
`price_basis: unknown`, `price_basis_verified: false`, `is_actionable: false` throughout. The
price itself came from `SELECT close FROM ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 1` —
the newest row for that ticker, whatever session it belonged to.

---

## 2. What changed

`market_wide_current_shares_resolver.py` — rewritten (`RESOLVER_VERSION 2.0.0`).

- Anchors are read from `share_basis_citations.jsonl`. No share count is a literal. A
  regression test asserts the two retired values appear nowhere in the source.
- `session_date` is a required argument on both entry points and is validated as a date.
- Promotion to `qualified_official` requires an official anchor **and** a ledger whose
  `coverage_status` is qualified across the interval. Enforced, not assumed.
- Freshness compares the event's ex-right date against the provider observation date. Only
  `ISS` is share-changing; ten codes are declared not share-changing; anything else is
  `unclassified` and is treated as share-relevant rather than silently benign.
- A share-relevant event with no ex-right date yields
  `provider_reported_unverifiable_freshness`, never a resolved value.
- Read failures raise `ShareStoreUnreadable` and surface as `unresolved_error`, which is never
  folded into `unavailable` or into a provider lane.
- The database is opened read-only (`mode=ro`, `query_only`, `busy_timeout`), matching the
  operating command's probe. The previous code opened it read-write, once per ticker, twice
  over — 3,366 read-write connections for a market-wide pass against a database in
  rollback-journal mode.
- Lanes are `qualified_official`, `provider_reported_current`, `provider_reported_lagged`,
  `provider_reported_stale`, `provider_reported_unverifiable_freshness`,
  `unknown_observation_date`, `unavailable`, `unresolved_error`.

`tools/operate_stocklookup.py`

- `market_wide_shares_coverage()` measures on every run against the session just resolved, and
  carries `measured_at`, `session_date` and `source`. A failed measurement reports
  `unresolved_error` and never fails a run whose artifacts are sound.
- The fabricated valuation-readiness counts (`pe_ready_count` and siblings) are **removed**
  rather than re-derived. They belong to a measurement over the canonical fact store, which is
  not this command's job and was never this command's output.
- `session` is re-anchored after `prepare_inputs()`.

`market_wide_calculation_readiness.py`

- `evaluate_market_capitalisation()` takes `price_basis_verified` and cannot return
  `qualified` without it. The share concept travels into `terms`, and an `ISSUED_SHARES` basis
  carries an explicit non-comparability warning.

`canonical_financial_bundle_section.py`

- `attach()` requires `session_date` and returns unchanged entries without one.
- The price fallback asks for the session's close (`date = ?`), not the newest close.
- One shared store read per export instead of one per ticker.

---

## 3. Measured result

Measured on 2026-08-03 against the retained runtime, replacing the asserted counts.

| lane | session 2026-07-30 | session 2026-08-03 |
| --- | --- | --- |
| `qualified_official` | **0** | **0** |
| `provider_reported_current` | 1,680 | 0 |
| `provider_reported_lagged` | 0 | 1,680 |
| `provider_reported_unverifiable_freshness` | 2 | 2 |
| `unavailable` | 1 | 1 |
| **active universe** | **1,683** | **1,683** |

`counts_reconcile: true` in both. Official anchors retained: 3. Ledger tickers covered: 5.

The two withheld tickers are **VCB** and **SSI**, each carrying an `ISS` event with no
ex-right date. The previously reported stale pair was a different pair, selected by a
different rule, for a reason that did not hold.

**`qualified_official` is 0, not 3.** No ticker has both an official anchor and a ledger able
to prove that nothing changed between the anchor date and the session. That was true before
this milestone as well; the three qualified results were the hardcoded table reporting itself.

The 1,680-ticker lane split by session is the honest freshness statement: against the retained
2026-07-30 session the provider observation is same-session; against a 2026-08-03 session it is
four days behind, with no ledger covering the interval for 1,678 of them.

---

## 4. What this does not change

- The bundle still carries `price_basis: unknown`, `price_basis_verified: false`,
  `is_actionable: false`. Market capitalisation, EV, EV/EBITDA, P/E and P/B remain
  unqualified for every ticker, and now say why on both legs rather than one.
- The production artifact set is untouched by this milestone. The
  `canonical_financial_facts` section remains opt-in and absent from the published bundle, and
  the Consumer still has no share-authority pass-through. Wiring it is deliberately **not**
  done here: publishing provider-reported market caps into the AI context while the price basis
  is unverified is the failure the fail-closed contract exists to prevent.
- `config/official_source_registry.json` is untouched and remains
  `AWAITING_OWNER_APPROVAL`. No agent may change it.

---

## 5. Tests

`tests/test_p1j1_share_authority_integrity.py` — 25 cases, one per defect, most against
synthetic runtime roots so they assert rules rather than this week's data.

`tests/test_p1i_market_wide_shares.py` and `tests/test_p1j_provider_share_authority.py` —
rewritten. The pinned counts (`assertEqual(summary["active_universe_ticker_count"], 1683)` and
five siblings) are replaced by partition and reconciliation invariants: any legitimate change
to the universe used to break them, while a wrong lane rule that preserved the totals passed.
