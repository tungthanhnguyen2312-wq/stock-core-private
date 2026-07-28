# Producer Atomic Artifact Build & Promotion Contract

**Recorded:** 2026-07-28
**Component:** `stock-core-private` (Producer)
**Modules:** `atomic_io.py`, `export_ai_bundle.py`, `publish_dashboard.py`, `metadata_registry_export.py`

---

## 1. Overview & Objectives

This contract defines the atomic generation, validation, and promotion rules for Producer-owned runtime artifacts. It guarantees that generated artifacts (e.g. `focus_extract.json`, `analysis_bundle.json`, `bundle_manifest.json`, and published dashboard runtime assets) are never corrupted, truncated, or left in a partial state if generation, validation, or file replacement fails.

---

## 2. Guaranteed Properties

1. **Temporary Staging:** Content is written to a uniquely named temporary file (`.tmp-<filename>-<random>.tmp`) in the target directory (`dir=target_path.parent`).
2. **Handle Flush & Sync:** The temporary file handle is explicitly flushed and synced (`os.fsync`) before validation or replacement begins.
3. **Pre-Promotion Validation:**
   - **JSON artifacts:** Parsed and validated via `validate_json_file` before promotion.
   - **CSV artifacts:** Header and row integrity checked via `validate_csv_file` before promotion.
   - If validation fails, the temporary file is immediately removed and the existing target file remains untouched.
4. **Atomic Promotion / Replacement:**
   - On Windows and Unix, file replacement uses `os.replace(tmp_path, target_path)`.
   - On NTFS / FAT, `os.replace` atomically overwrites the target file on the same volume without truncating or deleting it beforehand.
5. **Failure Isolation:**
   - Generation, validation, or OS replace failures leave the pre-existing target file unchanged.
   - Temporary staging files are cleaned up in `finally` blocks under all execution branches.
6. **Manifest & SHA-256 Consistency:**
   - Manifest entry hashes (e.g. `bundle_manifest.json` SHA-256 fields) are calculated *after* content files (`focus_extract.json`, `analysis_bundle.json`) are generated and atomically promoted.

---

## 3. Producer Artifact Ownership Matrix

| Artifact | Producer Owner | Staging & Validation Contract |
|---|---|---|
| `focus_extract.json` | `export_ai_bundle.py` | `atomic_write_json` with JSON validation |
| `analysis_bundle.json` | `export_ai_bundle.py` | `atomic_write_json` with JSON validation |
| `bundle_manifest.json` | `export_ai_bundle.py` | `atomic_write_json` with JSON validation |
| `vnstock_metadata_snapshot_*.jsonl` | `metadata_registry_export.py` | `write_registry_snapshot` (temp file + rename) |
| Published Dashboard Assets | `publish_dashboard.py` | `write_if_changed` & `copy_public_artifacts` using `atomic_write_file` / `atomic_copy_file` |

*Out-of-scope outputs:* Consumer context packages (`ai-core-private/context_packages/*`), mutable database instances (`vn_stock.db`), and untracked temporary scratch files.

---

## 4. Rollback & Fail-Closed Behavior

If any promotion step encounters a failure (disk full, invalid JSON schema, permission error):
- The error is logged or raised to the caller.
- The pre-existing valid artifact on disk remains active.
- No partial or corrupted file is exposed to downstream consumers.
