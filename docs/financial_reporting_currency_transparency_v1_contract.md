# Financial reporting currency transparency V1

Milestone `FINANCIAL_REPORTING_CURRENCY_TRANSPARENCY_V1`; native admission from
verified main `3d9abf8fdcd4f8f4a13276ae55d26da8bf2a66b2`, after PR119's approved
release and closeout. Owner program `FINANCIAL_RESEARCH_COMPLETENESS_WEEKEND_20261011`
and [standing delegation](financial_research_package_v1_contract.md) authorize
one C checkout/writer, offline implementation and one feature PR. Future exact-HEAD
merge remains owner-gated. No production activation follows this contract.

## Owners and interface

`stocklookup_core/financial/financial_reporting_currency.py` is a descriptive
product adapter over the existing compact Financial V2 product and official
`market_wide_current_fundamental_research.project_session` admission. It computes
no financial ratio, substitutes no metric, and grants no source authority.
Period interpretation remains in `decision/opportunity_axis_freshness.py`, next
to the unchanged analytical lag-window classifier. Fiscal interpretation and
provider flow/statement semantics retain their current owners.

`financial_reporting_currency/v1` separates five dimensions in each ticker record:

1. `report_period_coverage`: native label, period family, explicit start/end,
   duration versus instant, cumulative basis, scope, currency/unit, metric and
   entity-specific applicability. Q1–Q4, H1, 9M and annual native labels are
   supported. Labels never supply missing dates or a fiscal-calendar mapping.
2. `source_update`: pinned provider state, retained retrieval/qualification times,
   publication times/null, and bounded official-route receipts. A previously
   successful check is not proof of a currently live route. Approved-but-unchecked
   routes and notice-only evidence cannot establish an authenticated filing.
3. `newer_period_evidence`: admitted exact facts, retained-document context,
   source notices, checked-negative scope, blocked/unchecked routes and conflicts.
   Explicit end-date progress is distinguished from native-label progress whose
   calendar mapping is unproven. Neither proves the global latest report.
4. `knowledge_cutoff_eligibility`: timezone-bearing consultation cutoff, observed
   and qualification knowledge times, publication known/unknown, exclusions and
   sealed-decision/PIT non-eligibility. Unknown publication is never imputed from
   observation, URL, label, deadline or a later acquisition.
5. `investor_interpretation`: field-level historical usefulness, known period
   context, material evidence-backed warnings, qualification gaps and unknown
   update state. Missing dimensions never reject the whole ticker.

Inputs are never mutated. Eligible compact Financial V2 contexts and feature
measurements are copied unchanged, with original source identities and fitness.
Provider observation detail is optional and joins the compact product's exact
provider/hash/fact references. Unjoined observations cannot expand the baseline.
Measurements unproven at cutoff are withheld from the consultation view, with
source references and explicit exclusion reasons; stored source data is untouched.

Official rows are strictly finite numeric values (zero remains zero; null and
missing never become zero). Observed/qualified/publication cutoff filtering runs
before the standing owner's conflict detector, so a future revision cannot poison
an earlier available fact. Existing cohort, assurance, normalized-unit, ingress,
annual, component and foreign-currency gates are reused. This adapter additionally
requires the existing ingress period registry: describing Q3/9M is not registering
them as new official financial facts. Conflicts do not elect a winner.

The adapter also requires an existing `official_financial_assurance_evidence/v1`
envelope for both audited and reviewed claims: qualified state, matching document
and status, retained title/anchor/image references, and the resolver's matching
content identity. The opt-in packet rechecks that envelope after artifact identity
validation. Explicitly blocked metadata stays excluded. This closes the new
consumer's demonstrated bare-audited bypass without changing the upstream owner.
It verifies the retained proof contract, not original PDF classification or a
filing header's reporting period. Those upstream integrity checks remain a
separate corrective; no blanket source-integrity certification is implied.

Comparability requires explicit metric, statement family/time basis, scope,
currency, scale, dates, period family and cumulative basis. H1 is not standalone
Q2; IS/CF duration and BS instant remain distinct. Newer end dates alone permit
no substitution. Selected comparison groups require identical complete bases;
different bases are shown separately, without ranking. Provider native-label
ordering is explicitly unproven calendar ordering, never a hidden fiscal map.
An older history row cannot make a filing newer than the latest available anchor.

The denominator is the explicitly selected 1–32 distinct securities, not the
Financial V2 cohort or a financial peer population. Missing selected records
remain ABSENT. Coverage counts state this denominator; there is no freshness score.

## Actual opt-in consumer

Use the existing entrypoint, with exact retained files (no latest-file search):

```text
python stocklookup.py research financial-currency \
  --financial-product <financial_analysis_product_integration_v1.json> \
  --facts <qualified_official_facts.jsonl> \
  --cohort-report <cohort_report.json> \
  --provider-observations <structured_period_semantics_facts.jsonl.gz> \
  --session 2026-10-08 --cutoff 2026-10-08T15:00:00+07:00 \
  --ticker PNJ --ticker PVD --format markdown
```

Required: exact compact product, official facts, session/cutoff and selection.
Report and provider observations are optional; missing context stays unknown.
`--source-checks` optionally accepts explicit JSONL descriptive receipts: ticker,
kind (`RETAINED_DOCUMENT`, `SOURCE_NOTICE`, `CHECKED_NO_POSITIVE_EVIDENCE`,
`BLOCKED_OR_UNCHECKED`), reporting_period, source_identity, citation_id,
observed_at, knowledge_available_at, publication_date/null, checked_scope and
blocker. Retained-document receipts also require document_sha256. These receipts
assert retained context only, never admit a field or approve a source route.
No URL is fetched. A receipt without time or checked scope cannot establish
availability. Same-document repeated observations retain receipts without double
counting the document.

The existing refresh-report identity is checked using its producer hash rule.
A mismatch becomes `UNVERIFIED_CHECK_RECEIPT`/`SOURCE_REPORT_IDENTITY_MISMATCH`;
retention assertions are visible but cannot establish newer authenticated evidence
or a successful source route. Byte references are not trust/authority qualification.
The adapter never repairs or reseals retained artifacts.

JSON output contains the sealed projection, actual Human/AI evidence packets,
selected comparison and readable presentation. Markdown displays unchanged
provider measurements/fitness, exact official facts with accounting dates and
citations, formal policy labels, source claims, publication unknowns and gaps.
Optional `--canonical-packet` verifies a sealed reference only: it is not enriched
in place, and does not prove consultation evidence was available to that decision.

Packet `financial_reporting_currency=` is optional; reserved stock, uncertainty
and counter-thesis fields refuse collisions. It verifies identity, ticker/session,
cutoff eligibility and fixed non-voting boundaries. The mixed view is a DATA_WARNING,
not a new policy verdict. AI owns narration; the human retains the capital decision.

The CLI verifies all input byte hashes before and after inspection, rejects
duplicate JSON keys/nonfinite numbers, writes no artifact and sanitizes errors.
Do not publish a private source body or portfolio input. Public tests use synthetic
provider data and already-public exact-fact metadata only.

## CURRENT wording and deferred gates

The released official projection calls only `TARGET_INTERIM_PERIODS` in the
session year CURRENT. This label feeds nonzero current earnings-component quality
context; changing it is therefore not a descriptive-only change. Existing numerical
paths, CURRENT/HISTORICAL labels, votes and default identities remain unchanged.
The new consultation view explicitly says policy CURRENT is not latest reporting
currency. In 2027, the same 2026 H1 evidence can retain its measurement/basis and
known-period context while the existing formal label becomes HISTORICAL.

Q3 document types/period registration, unreviewed assurance, cohort widening and
source cadence remain four separate owner/source-qualification gates from the
Claude review. Fiscal mapping also needs source-bound issuer calendar, exact
provider/statement/label linkage, covered dates and distinct publication/retrieval/
qualification proof under the existing contract. No deadlines or calendars are
fabricated. No provider activation, RAW/PIT authority, strict-share qualification,
valuation change, Daily, Dashboard or default AI handoff field/identity change.

## Acceptance

Adversarial accounting periods, scopes, currencies/units, entity methods, conflicts,
duplicate receipts, null/zero/missing, blocked assurance, cutoff ordering, unknown
publication, frozen provider provenance, year transition, native-label ambiguity,
strict JSON, input order and opt-in/default packet parity are exercised offline.
Real measurement uses only explicitly named pinned static snapshots and the public
overlay/report, never runtime discovery or private source-body scans.
Targeted financial/valuation/packet regressions, structural/call-shape/native checks
and four exact-HEAD hosted jobs govern candidate review. Exact real counts and
differences from Claude's earlier snapshot are recorded in the acceptance note.
