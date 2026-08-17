# DNSE security-group semantic refinement

**Status:** P0-C semantic-evidence qualification (2026-08-17) · **Rule version:**
`dnse_security_group_semantics/v1` · **Module:** `dnse_security_group_semantics.py`

This is a strictly additive, optional refinement over `dnse_instrument_universe.py`'s already-shipped
production classification. It never modifies that module, never touches `UNKNOWN_SECURITY_GROUP`'s
`"ST"`-derived `EQUITY` classification, and performs no network or database access. It exists
because the P0-C.1/C.2 canonical-universe foundation exposed a concrete, well-evidenced gap: DNSE's
`/market/instruments` classifier only ever distinguishes `EQUITY` (`securityGroupId="ST"`) from a
single undifferentiated `UNKNOWN_SECURITY_GROUP` bucket, even though several of the other raw codes
turn out to carry unambiguous first-party evidence of their own.

## Evidence source

The retained 2026-08-12 DNSE security-master snapshot
(`operations-review/dnse-market-data-lake-v2-20260812/data/market_raw_lake/universe/
5c61b853c6f806e7120c56646b2af64e241aa26e70cccd37b9ddf1288258c4d4.parquet`, manifest
`content_hash=965c4b30...`) retains 1,590 `UNKNOWN_SECURITY_GROUP` records. Their raw
`securityGroupId` values partition exactly:

| Code | Count | `name` populated | Evidence |
| --- | --- | --- | --- |
| `EW` | 1,346 | 697 (52%) | 697/697 named records begin `"Chứng quyền"` ("covered warrant") — zero exceptions |
| `BS` | 203 | 67 (33%) | ~57/67 named records begin `"Trái phiếu"` ("bond"); the remainder name only the issuing bank/company, consistent with (not contradicting) a bond |
| `EF` | 21 | 21 (100%) | 20/21 explicitly contain `"ETF"` in Vietnamese (`"Quỹ ETF ..."`); the remaining one names only the fund manager |
| `FU` | 8 | 8 (100%) | 8/8 named `"HĐTL chỉ số ... [1/2] tháng/quý"` ("futures contract on index ..., 1/2 month/quarter"); `symbol_type_raw` independently corroborates (`VN30F1M`, `V100F2Q`, ...) |
| `MF` | 6 | 6 (100%) | Mixed: 4/6 say `"Quỹ đầu tư ..."` (generic investment fund, not ETF-specific); 2/6 name only the fund manager. **Not qualified** — see below. |
| *(none)* | 6 | 6 (100%) | All 6 named `"Chỉ số ..."` ("index ...") and match known Vietnamese market index names exactly (HNX, HNX30, UPCOM, VN30, VNINDEX, VNXALLSHARE) |

`1,346 + 203 + 21 + 8 + 6 + 6 = 1,590` — exhaustive, no residual population.

## Qualified mappings

| Raw code / condition | Canonical class | Confidence basis |
| --- | --- | --- |
| `securityGroupId="EW"` | `WARRANT` | Every named member's own name field, unanimous |
| `securityGroupId="BS"` | `BOND` | Large majority of named members explicit; remainder consistent, none contradicting |
| `securityGroupId="EF"` | `ETF` | Near-unanimous explicit `"ETF"` string in the provider's own name field |
| `securityGroupId="FU"` | `DERIVATIVE` | Unanimous, independently corroborated by a second field (`symbol_type_raw`) |
| No `securityGroupId`, `name` starts with `"Chỉ số"` | `INDEX` | 6/6 direct, individually confirmed — not a code-level generalization |

Per this project's evidence doctrine, generalizing from a representative named sample to every
member sharing the same *code* is the same method `dnse_instrument_universe.py`'s own
`"ST"` → `EQUITY` mapping already uses (10 named examples generalized to the full `"ST"`
population); this is not a new or looser evidentiary standard. The no-code/`INDEX` case is
different in kind: since there is no code to generalize from, every one of its 6 members was
checked individually, so nothing there is generalized at all.

## Explicitly NOT qualified

- **`MF` (6 records) stays `UNKNOWN_SECURITY_GROUP`.** Its own name-field evidence is internally
  inconsistent with `EF`'s ("Quỹ đầu tư", a generic investment-fund phrase, not "Quỹ ETF") —
  evidence *against* folding it into `ETF`, not evidence for any classification. Whether these are
  closed-end funds, a different fund structure, or something else remains genuinely unknown from
  currently retained evidence.
- **Any `raw_security_group_id` not in `EVIDENCE_BY_SECURITY_GROUP_CODE`** (i.e. not yet observed,
  or observed but not evidenced) stays `UNKNOWN_SECURITY_GROUP` unconditionally — this module never
  infers from ticker/symbol pattern, frequency, or a plausible-looking code.
- **`SYNTHETIC` / `INDEX_OR_SYNTHETIC`** are not produced by this module at all (only literal
  `INDEX`) — see `docs/canonical_universe_tiers_contract.md` for why those two remain reserved.

## Usage contract

- `refine_instrument_class(...)` is pure and stateless; `refine_record()`/`refine_records()` apply
  it to already-normalized `dnse_instrument_universe`-shaped records without mutating the input.
- Only ever narrows `UNKNOWN_SECURITY_GROUP`; any other `instrument_class` (including `EQUITY`)
  passes through unchanged, with `refinement_basis="not_unknown_security_group"`.
- Every output record carries a `security_group_refinement` provenance block
  (`instrument_class`, `refinement_basis`, `rule_version`, and — for a code-level mapping — the
  exact `evidence_named_count`/`evidence_total_count` this contract records above).
- Deterministic: the same input always produces the same output; no randomness, no network, no
  database, no live provider call.
