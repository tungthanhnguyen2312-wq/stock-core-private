"""Document identity: logical identity vs content identity.

A document's *logical* identity - "the same thing we asked for" - is
derived only from where it was requested from (domain + source locator).
Its *content* identity is its SHA-256. The two are deliberately different
concepts: the same logical identity can point at different content over
time (a filing gets amended/reissued at the same URL), and the same
content can in principle be reachable from more than one logical identity.
Neither identity is ever derived from a filename, URL pattern, or date -
see docs/acquisition_landing_framework.md, "What this framework does not
infer".
"""

from __future__ import annotations

import hashlib

from acquisition_landing_contract import AcquisitionSpec


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def logical_identity(spec: AcquisitionSpec) -> str:
    """Stable identity for "the same requested document", independent of its
    bytes. Deliberately excludes issuer_identity/document_type, since both
    may be unknown at acquisition time (see AcquisitionSpec)."""
    basis = spec.logical_identity_basis().encode("utf-8")
    return hashlib.sha256(basis).hexdigest()
