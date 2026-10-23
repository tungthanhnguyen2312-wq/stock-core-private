# NSO_CPI_ACQUISITION_PARSER_FRESHNESS_CORRECTIVE_20261023

Owner-admitted 2026-10-23. Bounded corrective of the NSO CPI route in
`stocklookup_core/evidence/vietnam_official_macro_evidence.py`, plus one ceiling guard in
`current_macro_regime.session_context`. Authority effect: none.

## Defects corrected

1. **Static locators.** `NSO_CPI_RELEASES` (June/July 2026) is kept. `acquire()` now fetches the NSO homepage
   first and also follows CPI release links found there. A link qualifies only if it matches
   `NSO_CPI_RELEASE_LOCATOR` (`https://www.nso.gov.vn/en/data-and-statistics/YYYY/MM/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-…/`).
   - The complete matching inventory is kept (bound `MAX_DISCOVERY_INVENTORY` = 32; exceeding it is
     `DISCOVERY_INVENTORY_LIMIT_EXCEEDED` and blocks currency). The fetch budget is separate:
     at most `MAX_FETCHED_DISCOVERED_RELEASES` = 3 are fetched, in a deterministic order that is never
     evidence of publication period. Each inventoried link beyond the budget is retained as
     `NOT_FETCHED:FETCH_BUDGET_EXCEEDED`.
   - Each discovered record carries `discovered_from`: the homepage `source_id`, its locator and its payload SHA-256.
   - A discovered page that cannot be fetched is retained as `FETCH_FAILED:<type>` with no payload and never yields a value.
2. **Release followed but not acquired.** `build()` records `release_discovery`, the status of each discovered link:
   `PARSED`, `PARSE_BLOCKED`, `FETCH_FAILED`, `NOT_FETCHED` or `DISCOVERED_NOT_RETAINED`. Any retained or
   discovered CPI release that is not parsed may be newer (its period is never inferred from the locator) and blocks currency.
3. **YoY wording.** The parser reads only CPI-subject sentences of the lead, under one clause grammar:
   `<verb> by X% <comparator>` with verb `rose`/`increased`/`decreased`/`fell` and comparator year-on-year,
   over/compared with the same period last year, compared with the previous month (MoM) or compared with
   December YYYY (year-to-date, not emitted). A clause without its own verb (`…, by X%`, `…, and by X%`)
   inherits the immediately preceding clause's verb only across a bare list separator.

   It fails closed in these cases:
   - any other word before "by" (`declined`, `changed`, `but`, …): `NSO_CPI_UNSUPPORTED_GOVERNING_VERB`;
   - an elliptical clause with no validated predecessor: `NSO_CPI_GOVERNING_VERB_UNRESOLVED`;
   - a claim not governed by the CPI subject (e.g. `…, while food prices rose by …`): `NSO_CPI_CLAIM_SUBJECT_UNRESOLVED`;
   - zero YoY claims, or more than one distinct claim;
   - the title or lead month differs from `Reference period`;
   - a negative number appears with a decrease verb.

   `decreased`/`fell` yields a negative value. MoM is recorded as `month_on_month` (`vn_cpi_mom`, `NOT_AN_AXIS`), distinct from YoY.
4. **Calendar supersession.** Every CPI entry in the bounded "Next releases" block is parsed. Each entry is
   `CALENDAR_ENTRY_ALREADY_RETAINED` individually when its named reference month is at or before the latest
   parsed period, or (unnamed) its date is at or before the latest publication date.
   `next_expected_official_release` is the earliest outstanding entry, or `null` when none remains.

## Freshness states (`freshness_rules.vn_cpi_yoy`)

| Status | When |
|---|---|
| `CURRENT` | An outstanding calendar entry exists and the session is before the earliest one (stricter rule, applied first). |
| `CURRENT_NEXT_RELEASE_UNANNOUNCED` | The latest observation is `QUALIFIED_OFFICIAL_RELEASE_TEXT`, no entry is outstanding, no retained or discovered release is unqualified, and the session is ≤ `valid_through`. |
| `STALE_OR_UNAVAILABLE` | Otherwise, with `reason_codes` (`NEXT_OFFICIAL_RELEASE_DUE`, `NEWER_DISCOVERED_RELEASE_NOT_QUALIFIED`, `DISCOVERY_INVENTORY_LIMIT_EXCEEDED`, `FRESHNESS_CEILING_EXCEEDED`, `NO_PARSED_RETAINED_NSO_CPI_RELEASE`). |

**Hard ceiling.** `valid_through` is the last day of the month after the next expected reference period. For 2026-09 CPI that is 2026-11-30.
- With an outstanding calendar entry, `valid_through` is the earlier of the ceiling and the day before the earliest one; the ceiling never extends an earlier official deadline.
- `session_context` excludes any row whose session is past `valid_through` (`FRESHNESS_CEILING_EXCEEDED`). This holds even for an artifact built earlier.
- The ceiling is not a promise of freshness and is not an exemption.

## Direction

`current_macro_observations` exposes `previous_value` only for the exactly adjacent prior month. Otherwise it adds the limitation `PREDECESSOR_PERIOD_NOT_ADJACENT:<prev>-><latest>`, and `INFLATION_PRESSURE` stays `UNKNOWN`. Nothing is interpolated.

Consequence for September 2026: July → September is not adjacent, and no qualified August YoY exists (the official XLSX does not state one). The level 5.08% is exposed; the direction is `UNKNOWN`.

## Not changed

- The regime rules and the `>4 unknown` limit.
- SBV: HTTP 403 remains a source blocker.
- XLSX ingestion, foreign flow and breadth.
- Sealed sessions: replay of a completed session performs no macro I/O.
