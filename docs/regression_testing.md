# Regression testing

Phase 8 protects the missing-data contracts introduced across financial statements, news, shareholders, and AI context validation. The suite is deterministic and offline: it reads only files under `tests/fixtures`, uses in-memory payloads, and must not call a provider API, write a production database, or rebuild a production snapshot.

## Fixture profiles

`tests/fixtures/regression/entity_financial_rows.csv` contains representative rows for PAN (corporate), HPG (corporate/manufacturing), SSI (securities), VCB (bank), and BVH (insurance). Rows retain ticker, entity/report type, provider, raw identifier/label, period, period basis, raw unit, value, and an explicit latest null PAN period. News and shareholder payloads are stored beside it.

Expected PAN outputs live in `tests/fixtures/expected`. Golden comparisons select stable business fields only. Volatile timestamps, absolute paths, request identifiers, and unordered collections are excluded or normalized before comparison.

## Running the suites

From `VNSTOCK`:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -m unittest discover -s tests/regression -p "test_*.py"
```

From `AI ANALYZE`:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -m unittest discover -s tests/regression -p "test_*.py"
```

The cross-phase suite includes the 19 named acceptance regressions from Phase 8. It also includes nine mutation cases: removed news alias; changed OCF identifier/label; reversed interest sign; missing quarter; unit drift; latest null; empty shareholder payload; malformed shareholder payload; and removal of the valuation OCF contract.

## Coverage thresholds

Profile thresholds remain owned by `AI ANALYZE/validation/context_validation_profiles.json`. The valuation regression verifies at least 90% fixture coverage while independently requiring OCF as a blocking metric. A `not_applicable` metric is excluded from the denominator, so sector-specific fields do not create artificial coverage regressions.

Add a fixture when a provider contract or supported entity shape changes. Update a golden only after reviewing the semantic change and its provenance; never accept a golden change merely to make a failure disappear.

## Phase 9 snapshot and consumer tests

`tests/test_snapshot_rebuild.py` validates schema v2, advanced columns, PAN values, duplicate keys, explicit unknown units, representative entity behavior, and the rebuild report. AI ANALYZE adds downstream compatibility tests for legacy scalars, parallel metadata, context use of the rebuilt snapshot, zero/null handling, status contracts, and point-in-time profile guards.
