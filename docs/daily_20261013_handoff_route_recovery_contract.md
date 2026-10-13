# October 13 Daily handoff route recovery

Owner-authorized P0 publication corrective on base
`1a10bf60b24e7e4a62694b22a4a4e678cce87776`. Authority effect: `NONE`.
Canonical Daily completed; recovery may replay publication only.

## Cause and lineage

AI handoff validation classified every leading-slash string as an absolute
filesystem path. Three retained valuation numerator source descriptors contain
the legitimate DNSE API endpoint `/price/ohlc`, with provider `DNSE` and dataset
`DNSE_OHLC_1D`. These are strings, not private filesystem locators:

- `/daily_integrated_decision_brief/watchlist/records/5/valuation_methods/P~1E_REPORTED_PERIOD/numerator_price_input/source/endpoint`
- `/daily_integrated_decision_brief/watchlist/records/5/valuation_methods/P~1S_REPORTED_PERIOD/numerator_price_input/source/endpoint`
- `/daily_integrated_decision_brief/watchlist/records/8/valuation_methods/P~1B_OFFICIAL_RESEARCH/numerator_price_input/source/endpoint`

Records 5 and 8 are PNJ and QNS. The endpoint registry in `dnse_market_data.py`
feeds `mva_exact_session_snapshot.py`'s source descriptor. The valuation input
scaleout preserves that descriptor in the price input, the valuation context
places it in `numerator_price_input`, and the Integrated Decision's methods
pass through the Daily brief's research-safe projection. The rejected filename
identified the JSON document, rather than a leaked path.

The operation identity is
`daily_research_session_operation:cfc00c52d9446aa46a43f66f24f7d04d263083d9d673483287629bca100f7382`.
The sealed brief identity remains
`daily_integrated_decision_brief/v1:6860425e247b270d35ffedd19053f36e6eed5a5ba48efb1ca83e4550e4dd36f8`.

## Validation and replay behavior

Recognize only the exact provider/dataset/endpoint tuple above, solely for the
`endpoint` entry. Recursively validate every other dictionary key and value and
every list element. Windows, UNC and Unix absolute paths remain forbidden,
including paths beside a recognized route. Diagnostics identify an escaped JSON
pointer without including the rejected value; unsafe keys use a redacted token.
No filename exemption, payload projection, schema change or source rewrite is
needed. Existing consumers receive identical original bytes and identities.
Each new immutable build includes a local Git attributes policy disabling text,
clean-filter and ident conversion for its files. This preserves original sealed
bytes even when Windows Git defaults or parent attributes normalize line endings;
existing builds and operator Git settings remain untouched.

The publisher refuses an older session before mutating a newer LATEST pointer.
An identical committed build returns the actual pointer HEAD separately from
the immutable build commit and retries a pending push when requested. A crash
after the immutable build commit can finish its pointer commit while preserving
the build bytes. Uncommitted build directories and conflicting pointers fail
closed. Independent remote verification checks pointer/session/build, remote
blob hashes, lineage, pointer hash fields and immutable commit identity.
The publisher's crash recovery does not bypass Owner checkout preflight: a dirty
or local-ahead handoff checkout requires inspection and verified reconciliation
of its exact pending commits before the official Owner replay can proceed.

## Acceptance and boundaries

Regression evidence covers the retained incident shape, nested route versus
filesystem locators, immutable bytes, deterministic package identity, legacy
packages, zero-Git-mutation `local_only=True`, remote replay, interrupted pointer
publication and push recovery. Focused Owner tests cover completed-session replay
without calling the Canonical Daily kernel. Strict retained M1 verifies 1,683
index entries and delivery parity (60 scoped, 10 Owner focus, 1,683 full universe).

Release requires native lane receipts and exact-head hosted CI, followed by
post-merge CI. Production acceptance separately requires fresh host/checkout
preflight, retained source hash parity, governed Dashboard/public-byte reuse,
remote AI ordering and byte verification, Action Center output, actual Owner
presentation result and COMPLETE journal/PASS workflow. External operator
reports retain these live receipts; source docs do not fabricate their outcome.

No acquisition, analytical rerun, T0 materialization, completed-session database
write, source promotion, financial qualification or Dashboard rebuild belongs to
this corrective.
