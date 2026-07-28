# Phase 2B — Automated Pipeline Scheduling & Operational Monitoring Contract

**Recorded:** 2026-07-28
**Component:** `stock-core-private` (Producer)
**Modules:** `pipeline_scheduler.py`, `daily_analysis_pipeline.py`, `observability_events.py`

---

## 1. Executive Summary & Architecture

Phase 2B implements single-instance concurrency control, operational log rotation, structured scheduling observability events, and execution orchestration for the automated post-session analysis pipeline:

1. **Single-Instance Concurrency Control:** `pipeline_scheduler.py` manages cross-platform non-blocking file locks (`locks/pipeline.lock`) via `PipelineLock`. If another pipeline run is active, `pipeline_scheduler.py` fails closed immediately with exit code `3` and logs a structured observability event.
2. **Operational Log Rotation:** `rotate_log_file()` rotates `logs/daily_pipeline.log` when file size exceeds 5MB, maintaining up to 5 backup logs (`daily_pipeline.log.1`, `daily_pipeline.log.2`, etc.).
3. **Structured Observability:** Emits version `1.0.0` structured observability telemetry (`observability_events.py`) for stage `pipeline_scheduler` during lock acquisition, execution start, and step completion or failure.
4. **Execution Orchestration:** Delegates pipeline execution to `daily_analysis_pipeline.py`, maintaining subsource freshness gates (`check_subsource_freshness()`), atomic file updates (`atomic_io.py`), and optional `--live-publish` dashboard updates.
