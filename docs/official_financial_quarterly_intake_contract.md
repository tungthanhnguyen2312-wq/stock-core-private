# Official financial intake and quarterly semantics V1

Offline, explicit, candidate-only capability. No cohort/registry/route activation,
official overlay, database write, production Daily or completed-session mutation.

## Existing owners and additive seams

`approved_issuer_ir_financial_evidence.prepare_financial_intake_candidate` consumes
already-reviewed rows and independently supplied original document bytes. Its
existing APPROVED_ROUTES and validate_fact gate are unchanged. Source admission
and semantic validation are independent; HPG/KBC still fail the existing cohort.

`official_financial_value_evidence.parse_accounting_integer` owns parsing through
an explicit callback; commas/dots/parentheses retain its strict integer policy.
`structured_financial_period_semantics.recognize_reported_column_period` is a separate
opt-in column recognizer. The existing recognize_statement_period Q3 block and
period_bounds/source-period admission are unchanged. No implicit fiscal calendar.

`financial_row_identity.resolve_reported_row_identity` binds statement family,
literal label and code. It maps only supported identities to existing canonical
metrics. Other proven concepts remain named research candidates with no canonical
alias: gross revenue/deductions, EPS numerator/denominator, loan/lease composites,
capital amounts and composite cash-flow adjustments. Unknown rows stay unknown.
No METRIC_REGISTRY, provider store, qualification ladder or financial engine grows.

`financial_metadata_envelope.qualify_document_metadata` remains the required
metadata owner; supplied envelopes must match original SHA, issuer and every
period/scope/currency/scale dimension. Missing explicit metadata blocks admission.
The existing common official fact admission is still the final authority, and
candidate rows deliberately use CANDIDATE_ONLY. No parser success sets QUALIFIED.

## Input and proof

Document input: original SHA and bytes, ticker/issuer, source ID and locator,
document class, explicit scope/currency/scale, page count, independent observation
and publication, assurance/status scope and optional existing metadata candidate.
Caller supplies the existing registry owner's exact bound decision; missing or
mismatched source/URL/type remains blocked. No fetch or latest-evidence loader.

Row input: statement family, native code/label/period/column, original SHA,
page/citation/review span, original raw numeric token where available, otherwise
explicitly identified reviewed integer, scope/currency/unit/scale, optional proven
covered dates and their bound evidence, independent knowledge timestamp and
original review/restatement provenance. Missing native lexemes never receive
generated separators or a claim of literal proof. Source text/image coordinates
from prior page reviews are retained; no OCR is repeated by this capability.

Original SHA is reverified; page bounds and exact citation binding fail closed.
Raw-token versus reviewed-value disagreement blocks normalization. Booleans,
malformed grouped numbers and unsupported scales fail; zero and negative integer
values survive. Exact unit normalization does not create currency/FX authority.
Review spans must bind the row's actual page; covered-date proofs require an
in-range page and literal endpoints. Monetary document scales never multiply EPS
or share quantities; mixed-unit documents remain explicitly unsupported pending
an independently qualified row-unit adapter.

## Accounting and temporal distinctions

Q3 standalone and nine-month cumulative columns have different period identities;
an ambiguous multi-period header is not a column. September30 is a balance instant,
not Q3 income or knowledge time. A quarter title cannot establish quarter cash
flow. H1's six-month label is retained with UNKNOWN_DURATION where full bounds/
year-to-date identity are unproven; no January1 start is manufactured.

Total consolidated profit, parent profit and separate-statement profit are distinct.
EPS ordinary-shareholder profit is not parent/total profit. Total equity including
NCI cannot be parent book equity; no subtraction is admitted as a source fact.
Loan/lease composites and unproven lease content cannot become pure borrowings or
debt totals. Composite depreciation adjustments cannot become EBITDA depreciation.
Capital in VND and EPS share quantities cannot become current outstanding shares.

Reviewed, unreviewed, audited and unknown assurance remain explicit. Declaring a
reviewed class cannot upgrade unreviewed evidence. The KBC absence finding is
scoped to inspected front matter; PDF creation time is not publication. Exact
observation/knowledge times and cutoff are independently checked; date-only HPG
knowledge remains unqualified. Unknown publication prohibits historical/PIT claims
without invalidating an otherwise proven numerical research candidate.

## Consumer and release boundary

Output separates schema_valid, semantic_valid, native_numeric_literal_proven,
source_admission_eligible, knowledge_cutoff_eligible and their blockers. It carries
original source identity, exact canonical candidate values/units, attribution,
period/assurance and immutable context identity. existing_consumer_usable,
official_fact_admitted and strict_valuation_eligible remain false at intake.
Existing conflict classification distinguishes period, scope, units and values.

Existing P/E_REPORTED_PERIOD, P/S_REPORTED_PERIOD and P/B_OFFICIAL_RESEARCH remain
the formula owners. Current method inputs accept only independently admitted
facts; the new candidates cannot enable a method, replace old denominators,
annualize/TTM or widen shares, policy/posture, Workspace or AI numerical authority.
Existing authorized research methods remain covered by their original tests.

The measured real cohort is 30 HPG reviewed-page records and 27 KBC formal line
candidates from three original PDFs. Candidate measurements are not production
coverage. Exact external results and the Owner source-admission docket are retained
outside Git. Missing source approval, native metadata/literal proofs, publication,
covered bounds and final common qualification remain explicit activation gates.
