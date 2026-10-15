"""Historical artifact-write API retained for frozen E4/E6 and Daily imports.

Implementation belongs to stocklookup_core.acquisition.artifact_io. The root name cannot be
removed while immutable executed sources and reviewed launchers import it.
"""
from observability_events import (
    EventOutcome, EventStage, build_observability_event, emit_observability_event,
)
from stocklookup_core.acquisition.artifact_io import (
    csv, json, os, tempfile, Path, Any, Callable, Iterable,
    _emit_event, AtomicWriteError, retain_immutable_bytes, retain_immutable_file,
    validate_json_file, validate_csv_file, atomic_write_file, atomic_write_json,
    atomic_copy_file,
)
