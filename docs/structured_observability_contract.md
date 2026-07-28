# Producer Structured Observability Event Contract

**Recorded:** 2026-07-28
**Component:** `stock-core-private` (Producer)
**Modules:** `observability_events.py`, `atomic_io.py`, `export_ai_bundle.py`, `publish_dashboard.py`

---

## 1. Executive Summary & Core Rules

This contract defines machine-readable structured observability events emitted across Producer artifact generation, pre-promotion validation, atomic promotion, manifest verification, and dashboard publishing:

1. **Schema Versioning:** Every event record explicitly declares `"schema_version": "1.0.0"`.
2. **Standard Event Stages:**
   - `artifact_generation`: Exporter builds `focus_extract.json`, `analysis_bundle.json`, etc.
   - `pre_promotion_validation`: `atomic_io` validates JSON/CSV structure prior to replacement.
   - `atomic_promotion`: Atomic file replacement via `os.replace`.
   - `manifest_verification`: SHA-256 manifest verification against promoted disk content.
   - `publish_dashboard`: Dashboard assets written or synced to web root.
3. **Outcome Policy:** Outcomes are strictly `success`, `failed`, or `skipped`. Ambiguous success states are prohibited.
4. **Data Privacy & Security:** Events capture metadata, file hashes, sizes, basis statuses, and error codes. Payload content (full dataset rows, SQL queries, private keys) is strictly excluded.
5. **Fail-Closed & Invariance:** Event logging failure does not suppress underlying pipeline exceptions or mutate production databases.

---

## 2. Event Schema (`schema_version: 1.0.0`)

```json
{
  "schema_version": "1.0.0",
  "timestamp": "2026-07-28T12:00:00Z",
  "stage": "atomic_promotion",
  "outcome": "success",
  "artifact_identity": {
    "filename": "analysis_bundle.json",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "size_bytes": 5607658
  },
  "basis_contract_status": {
    "price_basis": "unknown",
    "volume_basis": "raw_shares_traded",
    "is_actionable": false
  },
  "failure_reason": null,
  "production_state": {
    "is_live_write": false,
    "target_path": "C:\\Projects\\StockLookup\\dashboard-runtime\\analysis_bundle.json"
  },
  "provenance": null
}
```
