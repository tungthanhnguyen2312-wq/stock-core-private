# Official financial source qualification integrity corrective V1

Owner scope: `OFFICIAL_FINANCIAL_SOURCE_QUALIFICATION_INTEGRITY_CORRECTIVE_V1`.
Admission follows PR120's owner-approved release at
`498b02dd8471078a9cd627eb75241a4ed2da0de5`; release closeout is separate from this corrective.
This is a correction to existing evidence owners, not a new source authority.

## Required boundary

One deterministic, side-effect-free admission rule must bind source identity and
retained document identity, explicit document metadata and period, document-bound
assurance, literal metric/value/citation and normalization, qualification/conflicts,
knowledge time and intended use. Missing proof stays UNKNOWN or BLOCKED.
Caller labels, discovery hints and a syntactically valid SHA are not documentary proof.
The rule must govern extraction, qualification, publication and every reachable
canonical citation, fundamental and valuation consumer. No order-selected conflict winner.

Period classification must distinguish statement headers from comparative annual notes.
Audit engagement notices and incidental or negative assurance wording cannot establish
an audited/reviewed statement. Q3/9M numeric authority and period bounds stay closed.
Publication must validate the complete candidate set before replacement, refuse conflicts,
preserve retained history and refuse empty destructive replacement.

## Publication, citation and consumer semantics

Overlay publication is append-only and order-independent. Only producer-QUALIFIED rows are
candidates; every candidate must be admitted or nothing is written. A replayed retained key with
the same value/currency/unit keeps its first qualification; a different value is
`APPEND_ONLY_OFFICIAL_FACT_CONFLICT`; distinct candidates for one new key are refused.
Blocked extractions are diagnostics in the refresh report, never qualified-overlay rows.
Precedence rows are appended only for newly published keys. Canonical citation files and the
overlay resolve duplicates without line order: conflicting values drop the key; equal values
keep the lexicographically first citation. Financial V2 official equity applies the decision
session's knowledge cutoff and fails closed on equal-time conflicting values.

## Version-specific legacy rows

`config/official_financial_legacy_row_admission_v1.json` is a closed, hash-sealed list of the 27
rows published under `reviewed_interim_canonical_ingress/v2` by owner-merged PRs #78-#90 (overlay
LF SHA `bd83de2d...`; Windows CRLF checkout `a1f05701...`). Only an exact pinned row (canonical-JSON SHA-256, governing contract fields,
document SHA and issuer) may substitute for the newer document-metadata and literal-span schema.
Assurance binding, period, scope, unit, knowledge time, cutoff and intended use still apply.
Any edited, re-derived or new row must carry modern retained-source proof. Classification is
shape-valid, assurance-proof-bound, original bytes SHA-verified offline; original document
semantics are not independently re-verified and historical contamination stays UNKNOWN.

## Validation and preservation

Synthetic adversarial regressions execute the actual owners before and after fixes;
positive controls cover FY2025 and H1/Q2 within existing use limits. A classifier
reproduction is not proof of a complete network-to-Daily exploit or production contamination.
Bounded read-only reconciliation of the existing 27 rows and nine document identities
distinguishes row shape, bound proof, reopened original PDF verification and incomplete proof.
Unproved dependent uses fail closed without rewriting historical evidence.

No production refresh, Daily, deployment, source activation, provider substitution,
private/runtime data repair, or writes to the 27-row overlay. Default production call
shapes and completed Daily artifacts are preserved. No second repository writer.

## Release gate

Focused and broad financial/valuation/packet regressions, native checks and four hosted
CI jobs must pass on the exact candidate HEAD. A new corrective PR requires separate
owner approval at that HEAD; PR120 approval does not authorize its merge.
On quota interruption, retain a valid checkpoint and an exact local handoff recording
worktree, branch, HEAD/base/main, files, tests, failures, PR status and next action.
