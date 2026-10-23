# NSO_CPI_ACQUISITION_PARSER_FRESHNESS_CORRECTIVE_20261023

Owner-admitted 2026-10-23. Bounded corrective of the NSO CPI route in
`stocklookup_core/evidence/vietnam_official_macro_evidence.py`, plus one ceiling guard in
`current_macro_regime.session_context`. Authority effect: none.

## Defects corrected

1. **Static locators.** `NSO_CPI_RELEASES` (June/July 2026) is kept. `acquire()` now fetches the NSO homepage
   first and also follows CPI release links found there. A link qualifies only if it matches
   `NSO_CPI_RELEASE_LOCATOR` (`https://www.nso.gov.vn/en/data-and-statistics/YYYY/MM/consumer-price-index-gold-price-index-and-us-dollar-price-index-in-…/`).
   - Discovery is capped at 3 links, newest publication path first.
   - Each discovered record carries `discovered_from`: the homepage `source_id`, its locator and its payload SHA-256.
   - A discovered page that cannot be fetched is retained as `FETCH_FAILED:<type>` with no payload and never yields a value.
2. **Release followed but not acquired.** `build()` records `release_discovery`, the status of each discovered link:
   `PARSED`, `PARSE_BLOCKED`, `FETCH_FAILED` or `DISCOVERED_NOT_RETAINED`.
3. **YoY wording.** The parser reads only the lead CPI sentence and accepts these forms:
   - `rose by X% year-on-year`
   - `rose by X% over the same period last year`
   - `…, and by X% year on year` (a bare "by" takes the nearest preceding verb)
   - `compared with/to the same period last year`

   It fails closed in these cases:
   - zero YoY claims, or more than one distinct claim;
   - the title or lead month differs from `Reference period`;
   - a negative number appears with a decrease verb.

   `decreased`/`fell` yields a negative value. MoM is recorded as `month_on_month` (`vn_cpi_mom`, `NOT_AN_AXIS`), distinct from YoY.
4. **Calendar supersession.** A "Next releases" CPI entry is `CALENDAR_ENTRY_ALREADY_RETAINED` when either holds:
   - its named reference month is at or before the latest parsed period;
   - its date is at or before the latest publication date.

   In that case `next_expected_official_release` is `null`.

## Freshness states (`freshness_rules.vn_cpi_yoy`)

| Status | When |
|---|---|
| `CURRENT` | A future calendar entry exists and the session is before it (stricter rule, unchanged). |
| `CURRENT_NEXT_RELEASE_UNANNOUNCED` | The latest observation is `QUALIFIED_OFFICIAL_RELEASE_TEXT`, no future entry is known, no same-or-later discovered release is unqualified, and the session is ≤ `valid_through`. |
| `STALE_OR_UNAVAILABLE` | Otherwise, with `reason_codes` (`NEXT_OFFICIAL_RELEASE_DUE`, `NEWER_DISCOVERED_RELEASE_NOT_QUALIFIED`, `FRESHNESS_CEILING_EXCEEDED`, `NO_PARSED_RETAINED_NSO_CPI_RELEASE`). |

**Hard ceiling.** `valid_through` is the last day of the month after the next expected reference period. For 2026-09 CPI that is 2026-11-30.
- With a future calendar entry, `valid_through` is the earlier of the ceiling and the day before that entry.
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
