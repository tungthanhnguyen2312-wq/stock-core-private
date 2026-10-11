# Source integrity corrective — acceptance record 2026-10-11

Status: candidate for owner review; not merged. Writer handoff: Codex checkpoint
`02e686d9a6961ef00d5fca5e92ddf7d73b32fc97` resumed by Claude Code as sole writer.
Base: main `e4652aaf94561fd9eb5641a96ac857907fc617f4`. Contract:
[corrective contract](../official_financial_source_qualification_integrity_corrective_v1_contract.md).

## The six checkpoint failures

| Test | Root cause | Resolution |
|---|---|---|
| `test_retained_cash_flow_balance::test_append_only_refresh_preserves_first_qualification_and_precedence` | Regression: the checkpoint publisher dropped append-only replay semantics (same key + same value keeps first qualification), appended duplicate precedence rows and dropped `overlay_write`; fixture rows also lacked source proof. | `plan_official_overlay_publication`: order-independent append-only plan; precedence only for new keys; fixture binds owned synthetic proof; tampered value is refused at admission, bound different value is `APPEND_ONLY_OFFICIAL_FACT_CONFLICT`, reversed order is byte-identical. |
| `test_fpt_annual_earnings_component::test_retained_fpt_page_qualifies_only_the_literal_provision_amount` | Previously allowed unsafe path: the adapter qualified a row from caller status plus page assurance without document metadata or retained source. | Fail-closed assertion (UNKNOWN, not in overlay) plus a positive control through the same adapter with owned synthetic source-bound proof. |
| `test_fpt_annual_earnings_component::test_annual_component_reaches_packet_without_changing_current_or_valuation_fields` | Modern schema imposed on an older governed contract: the 27 retained `reviewed_interim_canonical_ingress/v2` rows predate `document_metadata`, so every consumer saw them UNKNOWN. | Exact-row, hash-sealed legacy admission (below). Released behaviour restored. |
| `test_retained_h1_provision_component::test_later_known_components_respect_completed_session_cutoff` | Same as above. | Same; cutoff still enforced. |
| `test_triad_current_h1_evidence::test_completed_session_excludes_and_october8_scratch_includes_vnm` | Same as above. | Same. |
| `test_qns_h1_official_detail_resolver::test_october7_excludes_qns_equity_and_prior_facts_remain` | Same as above. | Same. |

## Further corrections in this pass

- Version-specific legacy rows: `config/official_financial_legacy_row_admission_v1.json` pins the
  27 rows by canonical-JSON SHA-256 (closed set). Edited, re-derived, cross-ticker, re-contracted
  or metadata-bearing copies are not pinned. Assurance binding, period, scope, unit, time, cutoff
  and intended use still apply.
- Refresh artifact split: only producer-QUALIFIED rows are overlay candidates; blocked rows are
  `blocked_fact_diagnostics` in the refresh report. Landing manifest still written when nothing
  is published.
- Canonical citation files: no last-line-wins; conflicting values drop the key, equal values keep
  the lexicographically first citation (defect 7).
- Financial V2 official equity: decision-session cutoff enforced; equal-time conflicting values
  fail closed; no input-order winner.
- Currency packet re-admits the exact input fact, not the consumer's projected copy.
- Stale projected copies of qualified rows fed back as inputs never requalify (defect 8).

## Parity and narrowing

Restored released values: currency view 27 facts / 7 tickers (FPT 3, HPG 2, PNJ 6, PVD 7, QNS 1,
VNM 1, VRE 7); company economics PNJ 3 / PVD 3 earlier cutoff and PNJ 6 later; six annual
fields; FPT FY2025 historical component; VNM, QNS, H1 components at their cutoffs.

Narrowing (owner awareness): released main fed PVD and FPT FY2025 `AUDITED_ANNUAL_FIELD` equity
into Financial V2 P/B as official input, although the producer restricted those rows to
`EXACT_FIELD_CURRENT_RESEARCH_CONTEXT`. The corrective enforces the producer verdict; PVD/FPT P/B
use the VCI basis. QNS/VRE H1 official equity remain eligible after their knowledge time. A
change of annual-equity valuation use would need a separate owner authority decision.

## Retained evidence classification

27 rows / 9 documents, overlay SHA `a1f057017a9309f5c5a2a1a9ec53c3746500f9355bf45642e039ebf2608e33ff`
unchanged. Shape-valid: 27. Assurance proof bound: 27. Original bytes SHA-verified (offline,
read-only): 9/9 documents. Original document semantics independently verified: 0. Historical
contamination: UNKNOWN. No evidence written, resealed or requalified.

## Side effects

None: no refresh, Daily, network, production DB/runtime write, Q3 authority, `period_bounds`
change, source activation or write to D:, T:, W: or the retained overlay.
