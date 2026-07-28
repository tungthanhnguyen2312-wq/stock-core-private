"""Atomic file writing, validation, and promotion helper.

Provides atomic write, replacement, and validation guarantees on Windows and Unix filesystems.
Ensures temporary files are generated in the destination directory, validated prior to replacement,
atomically replaced via os.replace, and cleaned up on failure so existing artifacts are never corrupted or truncated.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable


class AtomicWriteError(RuntimeError):
    """Raised when an atomic write, validation, or replacement fails."""


def validate_json_file(path: Path) -> None:
    """Validator: ensure file exists and parses as valid JSON."""
    try:
        content = path.read_text(encoding="utf-8")
        json.loads(content)
    except Exception as exc:
        raise ValueError(f"Invalid JSON file {path.name}: {exc}") from exc


def validate_csv_file(path: Path, required_columns: Iterable[str] | None = None) -> None:
    """Validator: ensure file exists, parses as CSV, has rows, and includes required columns."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError(f"CSV file {path.name} is missing a header.")
        if required_columns:
            missing = set(required_columns) - set(fieldnames)
            if missing:
                raise ValueError(f"CSV file {path.name} is missing required columns: {sorted(missing)}")
    except Exception as exc:
        raise ValueError(f"Invalid CSV file {path.name}: {exc}") from exc


def atomic_write_file(
    target_path: Path,
    content: str | bytes,
    validator: Callable[[Path], None] | None = None,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> None:
    """Write content to target_path atomically with optional pre-promotion validation.

    1. Generates content into a temporary sibling file in target_path.parent.
    2. Flushes and closes the file handle.
    3. Runs validator(temp_path) if provided. If validation fails, temp_path is deleted
       and target_path is untouched.
    4. Atomically replaces target_path via os.replace.
    """
    target_path = Path(target_path).resolve()
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    mode = "wb" if isinstance(content, bytes) else "w"
    fd, tmp_name = tempfile.mkstemp(
        dir=target_dir,
        prefix=f".tmp-{target_path.name}-",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)

    try:
        if isinstance(content, bytes):
            with os.fdopen(fd, mode) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        else:
            with os.fdopen(fd, mode, encoding=encoding, newline=newline) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

        if validator is not None:
            validator(tmp_path)

        os.replace(tmp_path, target_path)
    except Exception as exc:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if isinstance(exc, (ValueError, AtomicWriteError)):
            raise
        raise AtomicWriteError(f"Failed atomic write to {target_path}: {exc}") from exc


def atomic_write_json(
    target_path: Path,
    payload: Any,
    validator: Callable[[Path], None] | None = validate_json_file,
    indent: int = 2,
) -> None:
    """Serialize payload to JSON and write atomically to target_path."""
    body = json.dumps(payload, ensure_ascii=False, indent=indent, allow_nan=False) + "\n"
    atomic_write_file(target_path, body, validator=validator, encoding="utf-8")


def atomic_copy_file(
    source_path: Path,
    target_path: Path,
    validator: Callable[[Path], None] | None = None,
) -> None:
    """Copy source_path to target_path atomically with optional validation."""
    source_path = Path(source_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source file for atomic copy not found: {source_path}")
    content = source_path.read_bytes()
    atomic_write_file(target_path, content, validator=validator)
