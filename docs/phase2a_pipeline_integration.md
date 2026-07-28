# Phase 2A — End-to-End Pipeline & Runtime Integration Contract

**Recorded:** 2026-07-28
**Component:** `stock-core-private` (Producer)
**Modules:** `daily_analysis_pipeline.py`, `publish_dashboard.py`, `export_ai_bundle.py`, `observability_events.py`

---

## 1. Executive Summary & Architecture

Phase 2A integrates post-session data ingestion and analysis routines with atomic artifact export, structured event telemetry, subsource freshness gating, and dashboard publishing:

1. **Subsource Freshness Gating:** `daily_analysis_pipeline.py` enforces mandatory pre-export freshness checks (`check_subsource_freshness()`) on DB-resident tables (e.g. `vnstock_metadata_snapshot`) before allowing bundle export.
2. **Atomic Manifest Enrichment:** Pipeline enrichment (`enrich()`) serializes execution step orders, timestamps, artifact verifications, and subsource freshness matrices atomically into `bundle_manifest.json` via `atomic_io.py`.
3. **Structured Observability Telemetry:** Standardized schema version `1.0.0` observability events (`observability_events.py`) are emitted at each pipeline step (`pre_promotion_validation`, `atomic_promotion`, `manifest_verification`, `publish_dashboard`).
4. **Publishing Orchestration:** Supports `--publish-dashboard` and `--live-publish` flags to integrate `publish_dashboard.py` seamlessly into sequential execution.
5. **Fail-Closed Principles:** Pipeline execution halts immediately on any failing step, unverified price/volume basis payload, or stale subsource. Existing production artifacts and `vn_stock.db` remain untouched on failure.
