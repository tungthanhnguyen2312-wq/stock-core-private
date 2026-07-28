"""Automated pipeline scheduler and operational monitoring runner."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    import fcntl
except ImportError:
    fcntl = None

from runtime_paths import RUNTIME_ROOT_ENV, runtime_root

try:
    from observability_events import (
        EventOutcome,
        EventStage,
        build_observability_event,
        emit_observability_event,
    )
except ImportError:
    try:
        from stock_core_private.observability_events import (
            EventOutcome,
            EventStage,
            build_observability_event,
            emit_observability_event,
        )
    except ImportError:
        EventOutcome = EventStage = build_observability_event = emit_observability_event = None

SCRIPT_DIR = Path(__file__).resolve().parent

class FileLockError(RuntimeError):
    """Raised when a pipeline lock file cannot be acquired."""
    pass

class PipelineLock:
    """Cross-platform single-instance file lock for pipeline runs."""
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._file_obj = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file_obj = open(self.lock_path, "w")
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file_obj.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._file_obj.write(f"pid={os.getpid()}\ntime={datetime.now(timezone.utc).isoformat()}\n")
            self._file_obj.flush()
        except (OSError, IOError) as exc:
            if self._file_obj:
                try:
                    self._file_obj.close()
                except Exception:
                    pass
                self._file_obj = None
            raise FileLockError(f"Pipeline lock active at {self.lock_path}: {exc}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._file_obj:
            try:
                if os.name == "nt":
                    import msvcrt
                    try:
                        self._file_obj.seek(0)
                        msvcrt.locking(self._file_obj.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                else:
                    try:
                        fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                self._file_obj.close()
            except Exception:
                pass
            self._file_obj = None
        if self.lock_path.is_file():
            try:
                self.lock_path.unlink()
            except Exception:
                pass

def rotate_log_file(log_path: Path, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 5) -> None:
    """Rotates log file when it exceeds max_bytes."""
    if not log_path.is_file() or log_path.stat().st_size < max_bytes:
        return
    for i in range(backup_count - 1, 0, -1):
        s = log_path.with_name(f"{log_path.name}.{i}")
        d = log_path.with_name(f"{log_path.name}.{i + 1}")
        if s.is_file():
            if d.is_file():
                d.unlink()
            s.rename(d)
    first_backup = log_path.with_name(f"{log_path.name}.1")
    if first_backup.is_file():
        first_backup.unlink()
    log_path.rename(first_backup)

def emit_scheduler_event(root: Path, outcome: str, reason: str | None = None) -> None:
    if build_observability_event and emit_observability_event:
        try:
            ev = build_observability_event(
                EventStage.PIPELINE_SCHEDULER if hasattr(EventStage, "PIPELINE_SCHEDULER") else EventStage.ARTIFACT_GENERATION,
                EventOutcome.SUCCESS if outcome == "success" else EventOutcome.FAILED,
                artifact_filename="pipeline_scheduler.log",
                reason=reason,
                target_path=root / "logs" / "daily_pipeline.log",
            )
            emit_observability_event(ev, root / "logs" / "observability_events.jsonl")
        except Exception:
            pass

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run pipeline scheduler and operational monitoring.")
    p.add_argument("--runtime-root", help="Explicit runtime root directory")
    p.add_argument("--tickers", nargs="+", help="Tickers watchlist")
    p.add_argument("--publish-dashboard", action="store_true", help="Trigger dashboard publisher step post-export")
    p.add_argument("--live-publish", action="store_true", help="Run dashboard publisher in live mode")
    p.add_argument("--skip-price-update", action="store_true")
    p.add_argument("--skip-macro", action="store_true")
    p.add_argument("--skip-news", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    return p.parse_args(argv)

def main(argv=None, pipeline_runner: Callable | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.runtime_root).expanduser().resolve() if args.runtime_root else runtime_root()
    if not root.is_dir():
        print(f"[scheduler] runtime root does not exist: {root}", file=sys.stderr)
        return 2

    locks_dir = root / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_path = locks_dir / "pipeline.lock"

    try:
        with PipelineLock(lock_path):
            logs_dir = root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_file = logs_dir / "daily_pipeline.log"
            rotate_log_file(log_file)

            emit_scheduler_event(root, "success", reason="scheduler_lock_acquired")

            if pipeline_runner is not None:
                res = pipeline_runner(args, root)
                if res != 0:
                    emit_scheduler_event(root, "failed", reason=f"pipeline_run_failed_exit_{res}")
                return res

            import daily_analysis_pipeline
            pipeline_args = ["--runtime-root", str(root)]
            if args.tickers:
                pipeline_args.extend(["--tickers", *args.tickers])
            if args.publish_dashboard:
                pipeline_args.append("--publish-dashboard")
            if args.live_publish:
                pipeline_args.append("--live-publish")
            if args.skip_price_update:
                pipeline_args.append("--skip-price-update")
            if args.skip_macro:
                pipeline_args.append("--skip-macro")
            if args.skip_news:
                pipeline_args.append("--skip-news")
            if args.verify_only:
                pipeline_args.append("--verify-only")

            res = daily_analysis_pipeline.main(pipeline_args)
            if res != 0:
                emit_scheduler_event(root, "failed", reason=f"daily_analysis_pipeline_failed_exit_{res}")
            return res
    except FileLockError as exc:
        print(f"[scheduler] CONCURRENCY LOCKED: {exc}", file=sys.stderr)
        emit_scheduler_event(root, "failed", reason=str(exc))
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
