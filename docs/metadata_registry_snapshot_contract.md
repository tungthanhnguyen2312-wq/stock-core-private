# vnstock_metadata_snapshot Registry Snapshot Contract

`metadata_registry_export.py --registry-snapshot [DIR]` writes one immutable JSONL file per
invocation into `registry_snapshots/metadata/` (default; pass a value after the flag to override,
e.g. for a one-off dry-run into a different location). Each line is one record conforming to
`ai-core-private/validation/schemas/vnstock_metadata_snapshot_registry_handoff.schema.json`.

## Filename

```
vnstock_metadata_snapshot_<UTC-YYYYMMDDTHHMMSSZ>_<content-sha256-12>.jsonl
```

Both the UTC timestamp and a 12-hex-char content hash are embedded, so two snapshots never
collide on name. Records are stably sorted by (ticker, field) before serializing, so the content
hash -- and therefore the filename -- depends only on the underlying data, never on incidental
ordering.

## Write guarantees

- **Atomic:** written to a temp file in the same directory, then renamed into place.
- **Never overwritten:** if the computed filename already exists, the write raises rather than
  replacing it. In practice this only happens if the exact same content were produced again
  within the same UTC second.
- **Not automatic:** only runs when an operator explicitly passes `--registry-snapshot` (or
  `--output`) to `metadata_registry_export.py`. It is not part of `daily_analysis_pipeline.py`'s
  `steps()`, `run.py`'s daily task, or any scheduled job -- same posture as `meta_sync.py` itself.

## Retention

- Every snapshot file is **immutable** once written.
- **Nothing in this repository auto-deletes a snapshot.**
- `registry_snapshots/` is gitignored -- it is generated data, not source. This contract file is
  what's tracked in git.
- A retention/archival policy (how long to keep snapshots, whether/where older ones get moved) is
  an explicit decision for a later milestone. Until one is recorded here, keep everything.
