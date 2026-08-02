# Producer Runtime Basis-Artifact Propagation Contract

**Recorded:** 2026-07-28
**Component:** `stock-core-private` (Producer)
**Modules:** `export_ai_bundle.py`, `publish_dashboard.py`, `price_basis_contract.py`

---

## 1. Executive Summary & Core Rules

This contract formalizes the propagation of Producer-qualified price and volume basis metadata through Producer-generated runtime artifacts (`analysis_bundle.json`, `focus_extract.json`, `bundle_manifest.json`) and publisher metadata (`data/build_info.json`):

1. **Complete Metadata Propagation:** All runtime artifacts propagate `price_basis`, `price_basis_verified`, `is_actionable`, `volume_basis`, `volume_basis_verified`, `adjustment_source`, `effective_date`, `limitations`, and `price_basis_provenance`.
2. **Fail-Closed Default:** Unverified or missing basis fields default to `price_basis="unknown"`, `price_basis_verified=False`, `is_actionable=False`, `volume_basis="unknown"`, and `volume_basis_verified=False`.
3. **Decoupled Volume Semantics:** Historical volume is maintained as an independent metadata field (`volume_basis`). A price adjustment claim does not imply volume adjustment.
4. **Publisher Metadata Sync:** `publish_dashboard.py` parses `analysis_bundle.json` when generating `data/build_info.json` and `data/build_info.js` to ensure web dashboards expose `price_basis_contract` metadata.
5. **Backward Compatibility:** Legacy top-level scalar fields (`price_basis` string, `price_basis_verified` bool) are retained for existing consumers alongside the structured `price_basis_provenance` dictionary.
