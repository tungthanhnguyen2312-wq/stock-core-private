# Share Basis, Price, and Market Cap Qualification

Bounded to HPG, annual, FY2024. Three share-count identities are strictly
distinct and never aliased or substituted for one another:

| Identity | Result | Source | Required by |
|---|---|---|---|
| Period-end shares outstanding (31/12/2024) | **qualified**: 6,396,250,200 common shares | Audited consolidated statement, Note 27 "Vốn cổ phần", page 57 (par value 10,000 VND, explicitly stated) | Net-Net (equity-base consistency); P/B |
| Weighted-average basic shares (FY2024) | **qualified**: 6,396,250,200 (numerically equal to period-end this year only, because the FY2024 stock dividend is retroactively applied per EPS convention -- not the same fact, kept as a separate citation) | Same statement, Note 40.1 "Số lượng cổ phiếu phổ thông bình quân gia quyền", page 64 | P/E |
| Valuation-date (current/live) shares outstanding | **unqualified** | `Company(source="VCI").overview().issue_share` carries no basis/as-of-date/currency metadata (see `financial_identity_source_qualification.md`); `Company.events()` shows at least one post-FY2024 stock dividend (ratio 0.10, ex-date 2026-05-11) plus a further, larger gap versus the live `issue_share` figure with no fully documented adjustment lineage connecting them | P/S if reconstructing market cap; EV multiples' market-cap derivation |

Both qualified facts are retained additively in
`data/official-evidence/share_basis_citations.jsonl`, hash-verified against
the same consolidated PDF `evidence_id` already on file (no new evidence
document). They are standalone, PDF-note-cited facts, not linked to any raw
VCI observation -- share count is never part of a VCI financial-statement
response, so there is no `observation_id` to cross-check against the way
`qualification_citations.jsonl` does. `semantic_evidence_bridge.load_verified_share_basis`
verifies each entry's evidence hash, deterministic citation ID, and
identity-type membership in an explicit allowed set (which also lists
`valuation_date_shares_outstanding` and the diluted weighted-average variant,
for schema readiness -- neither has a citation yet, and nothing falls back to
a different identity when one is missing).

Price: `current_price` (screen_snapshot_live.csv, freshness-gated) is a
valuation-date (today's) price with its own established provenance and is
left as-is; it is not period-end, and FY2024 book equity was never combined
with it. Market cap: no qualified figure or derivation exists; none is
reconstructed here.

Wiring: `export_ai_bundle._net_net_share_count` passes the cited
period-end count into `evaluate_intrinsic_valuation`'s Net-Net method only.
`intrinsic_valuation.py`'s Net-Net additively accepts `semantics="period_end"`
(alongside the pre-existing `"basic"/"diluted"`, unchanged for backward
compatibility) and, when the share count declares its own `period_identity`,
requires it to match the balance-sheet components' single common period --
fail-closed on mismatch, never inferred when absent.

`relative_valuation.py` deliberately receives no `share_count` or
`market_cap`: its single `share_count` input feeds P/E (needs
weighted-average) and P/B (needs period-end) identically, so populating it
for either would silently alias the other. Restructuring that shared slot
into two identity-tagged inputs is a real, separate fix, out of scope for
this bounded qualification pass. P/E, P/B, and P/S stay unavailable for this
reason plus the missing valuation-date price/share alignment; EV multiples
stay unavailable for missing `market_cap` (and, for `ev_ebitda`, missing
`ebitda`, unrelated to this pass and not derived here per the no-EBITDA
constraint).
