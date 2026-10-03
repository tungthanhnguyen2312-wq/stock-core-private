"""Feedback-only kernel file leases. No polling; process death releases ownership.

Stable lock files live outside evidence and are never unlinked (unlinking a POSIX
lock would let another writer lock a different inode). Windows LockFileEx and
POSIX flock wait in the kernel; the feedback parent's total deadline bounds waits.
"""
from contextlib import contextmanager, ExitStack
import hashlib
import os
from pathlib import Path
import tempfile
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
    directory = Path(tempfile.gettempdir()) / "stocklookup-feedback-locks"
    directory.mkdir(exist_ok=True)
    path = directory / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
    with open(path, "a+b") as handle:
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            class OVERLAPPED(ctypes.Structure):
                _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                            ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            signature = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                         wintypes.DWORD, ctypes.POINTER(OVERLAPPED)]
            kernel.LockFileEx.argtypes = signature
            kernel.UnlockFileEx.argtypes = [signature[0], signature[1], signature[3], signature[4], signature[5]]
            overlap = OVERLAPPED()
            native = wintypes.HANDLE(msvcrt.get_osfhandle(handle.fileno()))
            if not kernel.LockFileEx(native, 2 | (0 if blocking else 1), 0, 1, 0, ctypes.byref(overlap)):
                raise BlockingIOError(ctypes.get_last_error(), "FEEDBACK_PUBLICATION_BUSY")
            release = lambda: kernel.UnlockFileEx(native, 0, 1, 0, ctypes.byref(overlap))
        else:
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
