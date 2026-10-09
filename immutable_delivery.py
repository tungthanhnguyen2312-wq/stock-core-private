"""Private staging and write-once publication for the two recurring AI deliveries.

Reuse is opt-in, limited to new protected outputs. Legacy files are never sealed
or relinked. Published bytes cannot be replaced through this API.
"""
from __future__ import annotations

import hashlib
import ctypes
import os
from pathlib import Path
import stat
import tempfile

from atomic_io import AtomicWriteError

DELIVERIES = {"ai_research_session_bundle.json", "ai_research_full_universe.ndjson"}
CHUNK = 1024 * 1024


def _namespace(path):
    path = Path(path).absolute()
    protected_domains = {"prospective-decision-retention-v1", "thesis-evidence-t0-v1"}
    if any(part.casefold() in protected_domains for part in path.parts):
        raise AtomicWriteError("DELIVERY_PROTECTED_EVIDENCE_DOMAIN")
    for node in (path, *path.parents):
        if node.is_symlink() or (node.exists() and getattr(node.lstat(), "st_file_attributes", 0) & 0x400):
            raise AtomicWriteError("DELIVERY_REPARSE_PATH_REFUSED")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def protected(path):
    st = Path(path).lstat()
    return stat.S_ISREG(st.st_mode) and (
        bool(getattr(st, "st_file_attributes", 0) & 1) if os.name == "nt"
        else not st.st_mode & 0o222)


def volume_id(path):
    if os.name != "nt":
        return Path(path).stat().st_dev
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    mount, guid, filesystem = (ctypes.create_unicode_buffer(1024) for _ in range(3))
    kernel.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeNameForVolumeMountPointW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
    if not (kernel.GetVolumePathNameW(str(Path(path).absolute()), mount, len(mount))
            and kernel.GetVolumeNameForVolumeMountPointW(mount, guid, len(guid))
            and kernel.GetVolumeInformationW(mount, None, 0, None, None, None, filesystem, len(filesystem))):
        raise AtomicWriteError("DELIVERY_VOLUME_ID_UNAVAILABLE")
    if filesystem.value != "NTFS":
        raise AtomicWriteError("DELIVERY_VOLUME_NOT_NTFS")
    return guid.value


def _sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _publish(stage, target):
    # Windows rename refuses an existing target. POSIX rename would replace it.
    if os.name == "nt":
        os.rename(stage, target)
    else:
        os.link(stage, target)
    _sync_directory(target.parent)


def _discard_private(stage):
    if stage.exists():
        # Only our private single-link file on Windows is made writable for cleanup.
        # A POSIX published inode may still share stage; unlink needs no mode change.
        if os.name == "nt":
            if stage.stat().st_nlink != 1:
                raise AtomicWriteError("PRIVATE_STAGE_UNEXPECTED_LINKS")
            stage.chmod(stat.S_IREAD | stat.S_IWRITE)
        stage.unlink()


def publish_bytes(target, content, *, protect=False, on_stage=None):
    target = Path(target)
    _namespace(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_symlink() or target.read_bytes() != content:
            raise AtomicWriteError("IMMUTABLE_DELIVERY_CONTENT_CONFLICT:" + target.name)
        return "REUSED"
    fd, name = tempfile.mkstemp(prefix=".delivery-staging-", dir=target.parent)
    stage = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if sha(stage) != hashlib.sha256(content).hexdigest():
            raise AtomicWriteError("DELIVERY_STAGE_HASH_MISMATCH")
        if protect:
            stage.chmod(stat.S_IREAD | (stat.S_IRGRP | stat.S_IROTH if os.name != "nt" else 0))
        if on_stage:
            on_stage(stage)
        try:
            _publish(stage, target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != content:
                raise AtomicWriteError("IMMUTABLE_DELIVERY_CONTENT_CONFLICT:" + target.name)
            return "REUSED"
        return "PUBLISHED_IMMUTABLE"
    finally:
        _discard_private(stage)


def retain_alias(source, target, *, expected_sha, expected_size, volume=None):
    """Reuse a protected delivery on one device; otherwise retain an independent copy.

    The caller has finished DRO materialization and validated its delivery manifest.
    No existing alias is replaced, including an equal legacy independent copy.
    """
    source, target = Path(source), Path(target)
    _namespace(source)
    _namespace(target)
    if source.name not in DELIVERIES or target.name != source.name:
        raise AtomicWriteError("DELIVERY_FAMILY_NOT_QUALIFIED")
    if source.is_symlink() or target.is_symlink():
        raise AtomicWriteError("DELIVERY_SYMLINK_REFUSED")
    target.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    if before.st_size != expected_size or sha(source) != expected_sha:
        raise AtomicWriteError("DELIVERY_SOURCE_PROOF_MISMATCH")
    if target.exists():
        if target.stat().st_size != expected_size or sha(target) != expected_sha:
            raise AtomicWriteError("IMMUTABLE_DELIVERY_CONTENT_CONFLICT:" + target.name)
        return "REUSED"
    observe = volume or volume_id
    source_volume = observe(source)
    if not protected(source) or source_volume != observe(target.parent):
        # The independent fallback is intentional; legacy bytes remain untouched.
        content = source.read_bytes()
        after = source.stat()
        if (hashlib.sha256(content).hexdigest() != expected_sha
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise AtomicWriteError("DELIVERY_SOURCE_PROOF_MISMATCH")
        return publish_bytes(target, content, protect=True)
    try:
        os.link(source, target)
    except FileExistsError:
        if target.stat().st_size != expected_size or sha(target) != expected_sha:
            raise AtomicWriteError("IMMUTABLE_DELIVERY_CONTENT_CONFLICT:" + target.name)
        return "REUSED"
    after, linked = source.stat(), target.stat()
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or (after.st_dev, after.st_ino) != (linked.st_dev, linked.st_ino)
            or not protected(target) or sha(target) != expected_sha
            or observe(source) != source_volume or observe(target.parent) != source_volume):
        raise AtomicWriteError("DELIVERY_PUBLICATION_IDENTITY_MISMATCH")
    _sync_directory(target.parent)
    return "SHARED_IMMUTABLE"
