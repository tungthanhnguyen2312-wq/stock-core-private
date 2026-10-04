"""Feedback-only kernel leases. No polling; process death releases ownership.

Windows uses a target-named global mutex, including abandoned-owner recovery.
POSIX uses stable /tmp lock files that are never unlinked. Lease identity does
not depend on either contender's TEMP/TMPDIR. Kernel waits are bounded by the
feedback parent's total deadline.
"""
from contextlib import contextmanager, ExitStack
import hashlib
import os
from pathlib import Path
import threading

_held = threading.local()


@contextmanager
def publication_lock(target, *, blocking=True):
    key = os.path.normcase(str(Path(target).resolve()))
    held = getattr(_held, "paths", None)
    if held is None:
        held = _held.paths = set()
    if key in held:
        yield
        return
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        name = "Global\\StockLookupFeedback_" + hashlib.sha256(key.encode()).hexdigest()
        mutex = kernel.CreateMutexW(None, False, name)
        if not mutex:
            raise OSError(ctypes.get_last_error(), "FEEDBACK_PUBLICATION_MUTEX_FAILED")
        try:
            wait = kernel.WaitForSingleObject(mutex, 0xFFFFFFFF if blocking else 0)
            if wait not in (0, 0x80):  # acquired / abandoned owner (death releases claim)
                if wait == 258:
                    raise BlockingIOError("FEEDBACK_PUBLICATION_BUSY")
                raise OSError(ctypes.get_last_error(), "FEEDBACK_PUBLICATION_WAIT_FAILED")
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                kernel.ReleaseMutex(mutex)
        finally:
            kernel.CloseHandle(mutex)
        return
    directory = Path("/tmp") / "stocklookup-feedback-locks"
    directory.mkdir(exist_ok=True)
    path = directory / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
    with open(path, "a+b") as handle:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        held.add(key)
        try:
            yield
        finally:
            held.remove(key)
            release()


@contextmanager
def publication_locks(*targets, blocking=True):
    """Order multiple targets consistently, including a shared current-status pointer."""
    keys = sorted({os.path.normcase(str(Path(p).resolve())) for p in targets if p is not None})
    with ExitStack() as stack:
        for key in keys:
            stack.enter_context(publication_lock(key, blocking=blocking))
        yield
