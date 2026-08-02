# Altman Z'-Score Qualification (HPG FY2024)

Closes the Phase 6D "Altman readiness" gate that had been open since 2026-08-01.
Bounded to one model (`altman_z_score.py`), one variant, and one already-retained
evidence document.

## Why Z' (1983 private-firm) and not the classic 1968 Z

The classic Z's `X4` is **market** value of equity / total liabilities. This project's
price basis is globally `unknown/unverified` (`docs/STATE.md`), so a classic Z would pull
an unqualified market basis into a fundamental model and couple this contract to the P0
price-basis blocker -- which depends on an external vendor and has no completion date.
Z' replaces that single term with **book** value of equity / total liabilities. Every
input then comes from one already-qualified annual balance sheet / income statement.

Two consequences worth stating explicitly:

- **No FY2023 needed.** Altman is a single-period cross-sectional model. The unresolved
  FY2023 comparative gap (Phase 6C, Case C) blocks Beneish and comparative DuPont trend
  work; it never blocked Altman. Phase 6D's own report already implied this but the
  roadmap had them entangled.
- **Z' has its own thresholds**: distress < 1.23, grey 1.23-2.90, safe > 2.90. The
  classic Z bands (1.81 / 2.99) are never applied to a Z' value, and the variant is
  declared in every output (`variant: altman_z_prime_1983_private_firm`).

## What was missing, and what it actually was

Phase 6D reported `current_liabilities` and `retained_earnings` as "never retained by any
upstream sync" -- correct about `financial-observations/observations.jsonl`, whose
retention allowlist (`financial_observations._CODES`) has never included either item.
A 2026-08-02 audit initially concluded from this that a new VCI/KBS sync was required.
**That conclusion was wrong.** The "standalone PDF-cited fact" pattern already existed and
was already in production for exactly this situation -- `share_basis_citations.jsonl` and
`ebitda_component_citations.jsonl` both hold facts that have no raw VCI observation to
cross-check against. `ebitda_component_citations.jsonl` already carried HPG's and VNM's
`profit_before_tax` and `interest_expense`, so EBIT was already derivable.

Only two facts were genuinely absent, and both were printed on pages of the
already-retained, already-hash-verified consolidated PDF.

## Evidence

`data/official-evidence/financial_identity_citations.jsonl` (new), verified by
`semantic_evidence_bridge.load_verified_financial_identities` on the same terms as the
EBITDA components: the cited document must still hash-verify against `manifest.json`, the
`citation_id` must be the deterministic hash of its own content, the metric must be in
`_SUPPORTED_FINANCIAL_IDENTITIES`, the scope must be supported, and no two citations may
conflict for the same `(ticker, metric, reporting_period)`.

Both values were read directly from rendered pages of
`hpg-consolidated-fy2024-audited.pdf` (evidence_id `a7c3711d...ddcd2a8`; the pages are
scanned images with no text layer) and each was cross-checked against the statement's own
printed arithmetic before promotion:

| Identity | Code | Page | Value (VND) | Cross-check |
|---|---|---|---|---|
| `current_liabilities` | 310 | 9 | 75,225,243,262,689 | `310 + 330 = 300`: 75,225,243,262,689 + 34,617,006,307,593 = 109,842,249,570,282, equal to the already-qualified `liabilities` citation |
| `retained_earnings` | 421 | 10 | 49,599,124,109,203 | `421a + 421b = 421`: 37,624,250,548,129 + 11,974,873,561,074 = 49,599,124,109,203; and `300 + 400 = 440` = 224,489,707,553,981, equal to the already-qualified `total_assets` citation |

Promoted through `evidence_promotion.py` (the approved write boundary, see
`docs/DECISIONS.md`). No manifest record was added -- the document was already retained.
The four pinned production artifacts were hash-checked byte-identical before and after.

## Result

HPG FY2024 consolidated, VND, unit_scale 1, computed end-to-end from the evidence store
(no hardcoded values):

| Term | Definition | Ratio | Weighted |
|---|---|---|---|
| X1 | working capital / total assets | 0.051000 | 0.036567 |
| X2 | retained earnings / total assets | 0.220942 | 0.187138 |
| X3 | EBIT / total assets | 0.071188 | 0.221180 |
| X4 | book value of equity / total liabilities | 1.043746 | 0.438374 |
| X5 | sales / total assets | 0.618537 | 0.617300 |

**Z' = 1.5006 -> grey zone.** `is_actionable` is `False` and `historical_only` is `True`:
this is an evidence-qualified single-period diagnostic for FY2024, not a current-market
assessment and not an investment signal.

Working capital is derived inside the model (`current_assets - current_liabilities`) and
is never accepted as a supplied input. EBIT is derived as
`profit_before_tax + interest_expense` from the already-qualified EBITDA components.

## Scope and fail-closed behaviour

- **VNM**: `insufficient_evidence`, naming exactly `current_liabilities` and
  `retained_earnings`. VNM's own consolidated PDF is retained and hash-verified, so the
  same two-citation promotion would close it -- deliberately not done here; each value
  must be read and cross-checked individually, not assumed by analogy with HPG.
- **VCB**: `not_applicable` on `entity_type`, independent of evidence. Altman's corporate
  Z/Z' was estimated on non-financial firms; a bank's balance sheet has no operating-cycle
  current/non-current split and no meaningful asset turnover. Structural inapplicability
  is reported as itself, never as an evidence gap -- citing bank identities would not make
  the score meaningful.
- Any disagreement among the qualified identities on period, statement scope, currency, or
  unit scale fails closed rather than combining across the mismatch.
- `total_assets` and `total_liabilities` must both be strictly positive.

## Not wired into the bundle

`altman_z_score.py` is a standalone, pure contract with its own tests. It is **not** yet
attached to `analysis_bundle.json` and does not change `fundamental_quality.py`'s existing
`altman_z_score` model slot (still `inapplicable`). Wiring it is a separate milestone --
it needs the opt-in flag pattern used by the other Phase 5/6 contracts plus Consumer
pass-through, and must not silently change default bundle output.
