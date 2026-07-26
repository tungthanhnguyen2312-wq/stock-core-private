# Corporate-events source qualification

**Decision:** `SOURCE_PARTIALLY_QUALIFIED` for forward-only ingestion from
`vnstock==4.0.4` **VCI only**. This is a research record, not an ingestion
implementation or an authorization to create runtime tables.

## Scope and method

- Project requirement: `vnstock>=4.0.4`; the isolated study used exactly
  `vnstock==4.0.4` in `C:\tmp\corporate-events-qualification-20260726`.
- Official package helpers `show_api` and `show_docs` were exercised. The
  public `Company` adapter dynamically dispatches `events`; provider method
  signatures and provider metadata were then inspected directly.
- The package accepts only `VCI` and `KBS` for `Company`. Samples were bounded
  to HPG (large liquid issuer), SSI (securities), VCB (bank/dividend), and VNM
  (dividend and multiple historical event types). Temporary adapter-response
  evidence was retained outside the repository during analysis.
- Each VCI sample was repeated. A VNM `DIV` date-window probe was repeated,
  overlapped, and paged. Valid and invalid ticker probes were also made for
  both providers.

## Endpoints and observed contracts

| Provider | Public endpoint | Parameters exposed by public adapter | Result | Qualification |
| --- | --- | --- | --- | --- |
| VCI | `Company(source="VCI", symbol=ticker).events()` | none | 50-row, deterministic bounded history | partial, usable with gates below |
| KBS | `Company(source="KBS", symbol=ticker).events(event_type, page, page_size)` | event type 1--5, one-indexed page, page size | empty DataFrame for every valid/invalid sample | not usable |

VCI's underlying adapter calls its event API with ticker, event-code list,
`fromDate`, `toDate`, zero-indexed `page`, and `size`; the public method fixes
these to its rolling ten-year window, page 0, size 50. Its documented code set
is `DIV, ISS, DDIND, DDINS, DDRP, AGME, AGMR, EGME, AIS, MA, MOVE, NLIS, OTHE,
RETU, SUSP`. KBS documents five broader categories (AGM, dividend, issuance,
insider trading, other), but its successful empty payload is indistinguishable
from an invalid ticker or a source-empty response. It must fail closed rather
than be used as corroboration or fallback.

## VCI schema and temporal semantics

Observed VCI records contain these canonicalizable fields:

`id`, `ticker`, `event_code`, `category`, `event_name_vi`, `event_name_en`,
`event_title_vi`, `event_title_en`, `public_date`, `display_date1`,
`display_date2`, `record_date`, `exright_date`, `issue_date`, `start_date`,
`end_date`, `payout_date`, `listing_date`, `exercise_ratio`, and
`value_per_share`.

Strings/dates are delivered as nullable object values after the adapter's date
normalization; `exercise_ratio` and `value_per_share` are nullable floats.
Missing values remain null. No missing date, cash amount, ratio, or status may
be inferred or coerced to zero.

The provider labels `public_date` as publication/announcement timing;
`record_date`, `exright_date`, and `payout_date` appear in cash-dividend rows;
`start_date`/`end_date` appear in announced trading windows; and `issue_date`
or `listing_date` appear only where relevant. They are provider-supplied
attributes, not interchangeable event timestamps. `DIV` represents cash
dividend rows in the samples; `ISS` issuance/stock-distribution rows were
classified by the provider as `DIVIDEND`; insider/major-shareholder trading
codes were also present. The endpoint therefore mixes completed historical
events and announced upcoming events. It provides no reliable cancellation,
revision, completion, or execution-status field.

The two immediate VCI calls for each ticker produced equal record hashes and
50 rows. The VNM `DIV` window gave the same single provider ID on repeated and
overlapping ranges; its next page was empty. This demonstrates only bounded
call determinism and overlap deduplication for the sample--not immutability of
future or historical source records. The public VCI method does not expose
date-range or pagination controls, so a future adapter must call only a
documented/verified provider surface or otherwise fail closed when coverage
cannot be proven.

## Identity, revisions, and provider comparison

`VCI.id` is the candidate stable provider event ID and is the only qualified
identity: `(provider="VCI", provider_event_id=id)`. The observed IDs were
non-null and unique within each sample and stable across repeated/overlapping
calls. Do not fall back to a composite key or a canonical hash when `id` is
missing; reject that record as `parse_failed` because titles, dates, and
amounts can be revised.

VCI does not expose a revision number or cancellation flag. Represent a change
as an append-only observation/version: retain the original raw payload and
its hash, collect timestamp, package version, endpoint parameters, and
provider identity; never overwrite an earlier observation. An event is only
eligible for a current projection when the latest observation has the required
identity, ticker, event code, title, and at least one provider date. Status
must be `announced` only when evidence is an announcement; `completed`,
`cancelled`, and `revised` must remain null/unknown unless supplied by the
provider or an explicit later observation establishes the change. A changed
payload is `revised_or_unknown`, never silently treated as a correction or
cancellation.

KBS and VCI must not be merged: their category vocabularies and observed
payload behavior do not establish semantic equivalence. KBS cannot be used to
declare completeness, absence, cancellation, or a cross-provider match.

## Proposed forward-only contract gates

If ingestion design is approved later, preserve raw payloads and provenance
and require all of the following before a VCI record is admitted:

1. `source="VCI"`, exact package version, endpoint/method, request parameters,
   retrieval timestamp, raw payload, and raw SHA-256 are retained.
2. `id`, uppercase ticker, `event_code`, and a nonblank title are present;
   `id` is unique per provider and conflicts create a new observation rather
   than an overwrite.
3. At least one source date is parseable; each supplied date retains its
   semantic field name. Amounts and ratios remain nullable decimals.
4. The response is schema-validated. Empty, malformed, transport-failed,
   truncated/unpageable, duplicate-ID-conflicting, or missing-ID responses are
   explicit `source_empty`, `parse_failed`, `network_failed`, or
   `incomplete`, never a complete snapshot.
5. Historical-completed, announced-upcoming, revised/cancelled, and
   unclassifiable views are separate. Without explicit provider status, rows
   are `historical_or_announced_unknown` and are not eligible for a completed
   event claim.

## Unresolved risks and next source

The VCI public method caps output at 50 and hides date/pagination controls;
there is no observed total count, ordering guarantee, update timestamp,
revision sequence, cancellation marker, or execution/completion confirmation.
Accordingly this source supports audited forward observation, not an assured
complete historical ledger or completed-event feed. No source contract supports
cross-provider reconciliation.

If this partial VCI-only contract is insufficient for the intended product,
qualify `insider_transactions` next: it is already an explicit VCI event-code
family and can be assessed without conflating it with corporate actions.
