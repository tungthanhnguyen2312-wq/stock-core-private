# Official unreviewed quarterly statement intake V1 — contract

Milestone `OFFICIAL_UNREVIEWED_QUARTERLY_STATEMENT_INTAKE_V1` implements Owner decision **D-1**
(2026-10-19). Vietnamese quarterly statements are neither reviewed nor audited, so the reviewed
ingress correctly refuses them (`ASSURANCE_STATUS_NOT_EXPLICIT`). D-1 admits them into a
**separate research tier**. Each fact carries all three labels below:

- `evidence_tier = UNREVIEWED_QUARTERLY`
- `audit_or_review_status = unreviewed`
- `qualification_state = QUALIFIED_UNREVIEWED_QUARTERLY_RESEARCH`

A fact is never promoted to reviewed or audited. Facts are written to their own file,
`derived/financial-evidence-currency-refresh-v1/unreviewed_quarterly_official_facts.jsonl`, and
never to the reviewed overlay. `load_unreviewed_quarterly_facts` refuses any row whose tier labels
differ. No Q1 is derived by subtraction, nothing is annualized, no TTM is built, and the
publication date stays unknown (not PIT).

## Engine changes (opt-in; existing paths byte-identical)

- `materialize_tsv_pages(detect_orientation=True)`: Tesseract OSD (`--psm 0`) rotates a rendered
  page only when the content is rotated by 90, 180 or 270 degrees with confidence of at least 5.0.
  The rendered and corrected image SHA values are recorded in `ocr_adapters`.
- `materialize_tsv_pages(normalize_superscript_digits=True)`: Tesseract `vie` reads "2" as "²".
  The adapter normalizes superscript digits **only in non-amount tokens** (years, quarter labels)
  and keeps `source_text`. Amounts are never repaired, so a damaged amount stays ambiguous.
- `match_quarterly_four_column_row` handles the B02a quarterly layout: this quarter, the same
  quarter last year, and year-to-date for both years. It requires all of the following:
  - a heading for the exact target quarter;
  - a cumulative heading (Lũy kế, 6 tháng, Year to date, or the period-end date) over the
    right-hand pair;
  - four value columns measured from the coded rows, with page skew measured from those rows;
  - years, or "năm nay / năm trước", bound to the quarter pair. The alternative binding is two
    visible quarter headings plus an explicit current-then-prior cumulative pair, recorded as
    `QUARTER_PAIR_BY_EXPLICIT_CUMULATIVE_ORDER`.

  A quarterly target never falls back to the two-column engine. Without this matcher, NVL's
  dated year-to-date pair would have been bound as Q2. Year-to-date values are ignored.
- On the quarterly path only, a short sign qualifier after "nhuận" ("Lợi nhuận/(lỗ)", including OCR
  damage such as "(Ié)") is dropped before the existing row-label contract runs. All forbidden
  terms (minority interest, parent company) still apply, and the shared contract is unchanged.
- Scope is the income statement: revenue (line 10), net income (60) and attributable net income
  (61). A comparative column becomes a separate prior-year quarter fact with
  `COMPARATIVE_COLUMN_OF_LATER_REPORT`.

## Result on the retained Q2/2026 reports (offline)

6 facts across 2 issuers and 2 quarters each:

| Issuer | Metric | Q2/2026 | Q2/2025 |
|---|---|---|---|
| PNJ | Revenue | 8,483,734,461,474 | 7,582,449,574,137 |
| PNJ | Net income | (283,029,272,213) | 436,997,250,814 |
| NVL | Net income | 912,001,107,054 | (189,868,378,915) |

These values were checked three ways:
- PNJ: against the page image, and with the row identity 60 = 50 − 51 − 52.
- NVL: against the document's own native text layer.
- KBS was used for comparison only. It matches PNJ Q2/25 revenue and NVL Q2/25 net income. It
  differs on PNJ Q2/25 net income (441.6B), where the official comparative governs.

Issuers that fail closed:

| Issuer | Reason |
|---|---|
| HPG | Lines 10 and 60 contain superscript-damaged amounts, or their line code was lost to OCR |
| FPT | Superscript-damaged amounts |
| PVD | OCR splits mixed-separator amounts |
| PNJ line 61 | OCR damaged "công ty mẹ" |

Higher fidelity would need amount-level repair (variant B) or a second OCR read of value cells.
Both are policy changes that need Owner decisions.

## Integration on released main (2026-10-22)

The tier coexists with PR177's stricter intake semantics and PR168's payload-period
guard. It does not enter PR177's candidate-to-official admission path. Even the
opt-in OCR result carries the unreviewed research qualification instead of generic
`QUALIFIED`, with existing-consumer, official-fact and strict-valuation eligibility
explicitly false. The reviewed OCR/overlay path is unchanged.

The loader validates the retained issuer/document/page, line-code/metric, column role,
exact current/comparative quarter, covered bounds, raw numeric token and normalized
value, fact identity, provenance and research-only restrictions. A correct tier label
cannot hide altered period/value/source bindings or an authority promotion.
Non-year bare numeric glyphs are not repaired, and the short loss qualifier is limited
to the retained loss spellings, preserving identity-bearing parent/minority terms.

The six original retained rows and intake report are preserved byte-for-byte from
PR169. Replays operate in memory and write diagnostic output only to scratch; the
reviewed overlay and pinned semantic/feature-store artifacts are not changed.

Local retained replay of the five exact documents reproduced all six facts and the
original intake report identity. PNJ's superscript quarter digit is normalized only
when geometrically adjacent to an explicit quarter label; unbound numeric tokens
and damaged amounts remain untouched. The reviewed panel adapter explicitly refuses
this tier. Required intake CI selection: 295 passed, 2 existing skips; final
consumer/guard selection: 106 passed. Five legacy OCR tests lack their host-local
manifest and fail identically on unchanged main; they are not new regressions or
part of the required CI selection. No admission standard or failing check was disabled.
