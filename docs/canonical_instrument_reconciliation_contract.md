# Canonical instrument reconciliation foundation

**Status:** P0-C.1 foundation · **Schema:** `1.0.0` · **Module:**
`canonical_instrument_reconciliation.py`

The artifact is a deterministic reconciliation layer over explicit, already-retained source
inputs. It is not a source authority or a listed/active universe. A retained DNSE JSON or
modern-lane Parquet snapshot is required by the file builder. VCI, legacy metadata, and
company-profile inputs are optional additive retained inputs.
The builder never imports an acquisition client or opens `vn_stock.db`.

## Identity policy

Provider identities stay independently addressable: `dnse:symbol:<symbol>`,
`vci:symbol:<symbol>`, `legacy:ticker:<symbol>`, and
`company_profile:<provider>:<provider_identity>`. Exact uppercase symbol equality is only the
`exact_uppercase_symbol_candidate_link/v1` candidate-link rule. A multi-source link starts as
`PROVISIONAL_MATCH`; C.1 has no path to `QUALIFIED_MATCH`.

A `COMPANY_PROFILE` source carries every field -- `symbol`, `name`/`organ_name`, `exchange`, and
`instrument_class`/`instrument_type` alike -- nested under its own `qualified_fields`, never at the
top level of the retained record; a top-level key of the same name on a `COMPANY_PROFILE` record is
never read.

Candidate IDs hash the rule version and participating provider identities, never a symbol alone.
Each link records its rule, identities, evidence-observation IDs, and resolution state.

## Field and conflict policy

Every field observation carries source/provider, source reference, `observed_at`, raw value,
explicitly qualified normalized value where applicable, selected state, conflict identity, and
semantic status. Raw provider records are retained verbatim in provider identities.

Listing status defaults to `UNKNOWN`; source presence, absence of `DELISTED`, missing price
history, and legacy `DELISTED` markers do not promote an active or delisted status. Exchange raw
values are retained but not cross-provider-equated. DNSE `marketId` and unsupported mappings have
normalized value `null` with `provider_raw_only_mapping_unknown`.

Conflicting usable provider observations produce a `canonical_instrument_conflict` and leave the
candidate `CONFLICT`; no field precedence is invented. Absence from one source is not a conflict.

## Downstream consequence for C.2

Both `exchange` and `listing_status` are unconditionally non-`usable` for every provider today (no
provider's raw value for either field is ever `provider_reported`) -- this is intentional, not a
gap in this module, since no verified `marketId`-to-exchange-label or listing-status mapping exists
anywhere in this codebase yet. A concrete, practical consequence: C.2's `ACTIVE_UNIVERSE` tier (and
everything downstream of it) cannot resolve any candidate to `INCLUDED` from C.1 output alone,
regardless of how many providers agree on `instrument_class`. That will remain true until a new,
separately-qualified evidence source for listing-status or exchange enters C.1 through its own
retained-input reconciliation -- see `docs/canonical_universe_tiers_contract.md`.

## Storage contract

`write_artifact(output_root, result)` writes one immutable content-addressed JSON artifact beneath
the explicit `output_root` at `data/canonical_instrument_reconciliation/artifacts/<hash>.json`.
This follows the existing modern-lane raw-lake pattern of explicit roots, content/provenance
identity, and atomic writes, while keeping this compact reconciliation graph portable for C.2.
Rerunning identical inputs is a no-op; there is no default runtime path or production promotion.
