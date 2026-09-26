"""In-worker provider containment (APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1).

Standard-library only; ``requests`` is wrapped when importable but never required. Installed by
``vnstock_worker_process`` right after self-attestation and BEFORE any provider package is
discovered, imported or initialised, so provider start-up code (``vnai.setup()``: telemetry,
profile reads, background threads, subprocesses) already runs under it.

Four layers, all driven by the approved build manifest through the launch contract:

1. HTTP layer -- ``EgressPolicy.evaluate_http``: scheme + host + port + method + path of every
   request. Enforced by ``enforce_transport_policy`` (called by the quote transport
   ``vn_stock_pipeline._bounded_send_request_direct`` before it consumes a rate-governor slot) and
   by a wrapper around ``requests.sessions.Session.send`` that covers every ``requests`` call,
   including vendor telemetry that never touches the quote transport. Redirects are never followed:
   an approved endpoint's ``max_redirects`` is 0, so a 3xx answer fails closed with
   ``TRANSPORT_REDIRECT_TO_UNAPPROVED_HOST`` or ``TRANSPORT_REDIRECT_NOT_PERMITTED``.
2. Socket layer -- an audit hook (PEP 578; irremovable once added) denies name resolution and
   connections for any host that is not allow-listed, before any DNS query leaves the process. A
   connection to an IP address is allowed only when that address was resolved from an
   allow-listed host in this process.
3. Process layer -- the same hook denies every process-creation route: ``subprocess.Popen``
   (which covers ``run``/``call``/``check_output``), ``os.system``, ``os.exec*``, ``os.spawn*``,
   ``os.posix_spawn``, ``os.startfile``, ``os.fork``/``forkpty`` and ``_winapi.CreateProcess``.
   This closes the old interception gap that only short-circuited ``subprocess.run``.
4. Filesystem layer -- the hook denies ``open``/``listdir``/``scandir`` and every mutating ``os``
   call under a denied root (the owner profile and its ``.vnstock``/``.stocklookup`` state, the
   producer checkout, the runtime root, secrets files) unless the path lies inside a more specific
   approved root (read-only: interpreter, venv, worker bundle; read-write: provider state root,
   per-launch scratch root).

Every denial is recorded in ``ContainmentEventLog`` with a deterministic reason code. A denial the
manifest's telemetry disposition names (``DENY``) is *expected* -- vendor telemetry is refused on
purpose and is not a failure. Any other denial is *unexpected*; the worker fails closed on it at
its next controlled boundary (end of start-up, or the next request). Nothing here widens access
after a denial.

This is in-process containment, not a security sandbox. Native code and ``ctypes`` can bypass audit
hooks, and existence probes (``os.stat``) raise no audit event. The dossier's OS-level controls --
restricted identity, NTFS deny ACLs, Job object, default-deny egress gateway, read-only runtime --
remain required before any owner approval.
"""
from __future__ import annotations

import ipaddress
import os
import re
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Mapping
from urllib.parse import urljoin, urlsplit

from provider_execution_guard import ProviderContainmentViolation

CONTRACT_VERSION = "provider_worker_containment/v1"

PHASE_STARTUP = "STARTUP"
PHASE_OPERATION = "OPERATION"

LAYER_TRANSPORT = "TRANSPORT"
LAYER_REQUESTS = "REQUESTS"
LAYER_SOCKET = "SOCKET"
LAYER_PROCESS = "PROCESS"
LAYER_FILESYSTEM = "FILESYSTEM"
LAYER_NATIVE = "NATIVE"

# --- deterministic reason codes -----------------------------------------------------------------
TRANSPORT_POLICY_NOT_INSTALLED = "TRANSPORT_POLICY_NOT_INSTALLED"
TRANSPORT_URL_UNPARSEABLE = "TRANSPORT_URL_UNPARSEABLE"
TRANSPORT_CREDENTIALS_IN_URL = "TRANSPORT_CREDENTIALS_IN_URL"
TRANSPORT_HOST_NOT_ALLOWLISTED = "TRANSPORT_HOST_NOT_ALLOWLISTED"
TRANSPORT_SCHEME_NOT_ALLOWED = "TRANSPORT_SCHEME_NOT_ALLOWED"
TRANSPORT_PORT_NOT_ALLOWED = "TRANSPORT_PORT_NOT_ALLOWED"
TRANSPORT_METHOD_NOT_ALLOWED = "TRANSPORT_METHOD_NOT_ALLOWED"
TRANSPORT_PATH_NOT_ALLOWLISTED = "TRANSPORT_PATH_NOT_ALLOWLISTED"
TRANSPORT_REDIRECT_NOT_PERMITTED = "TRANSPORT_REDIRECT_NOT_PERMITTED"
TRANSPORT_REDIRECT_TO_UNAPPROVED_HOST = "TRANSPORT_REDIRECT_TO_UNAPPROVED_HOST"
SOCKET_HOST_NOT_ALLOWLISTED = "SOCKET_HOST_NOT_ALLOWLISTED"
SOCKET_ADDRESS_NOT_RESOLVED_FROM_ALLOWLISTED_HOST = "SOCKET_ADDRESS_NOT_RESOLVED_FROM_ALLOWLISTED_HOST"
SOCKET_BIND_DENIED = "SOCKET_BIND_DENIED"
SOCKET_DATAGRAM_DENIED = "SOCKET_DATAGRAM_DENIED"
PROCESS_CREATION_DENIED = "PROCESS_CREATION_DENIED"
FILESYSTEM_DENIED_ROOT = "FILESYSTEM_DENIED_ROOT"
FILESYSTEM_WRITE_TO_READ_ONLY_ROOT = "FILESYSTEM_WRITE_TO_READ_ONLY_ROOT"
FILESYSTEM_PATH_UNRESOLVABLE = "FILESYSTEM_PATH_UNRESOLVABLE"
NATIVE_LIBRARY_LOAD_OBSERVED = "NATIVE_LIBRARY_LOAD_OBSERVED"

ACTION_DENIED = "DENIED"
ACTION_OBSERVED = "OBSERVED"

_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
ALLOWED_METHODS = ("GET", "POST")


class ProviderContainmentDenied(PermissionError):
    """Raised inside provider code by the audit hook. A ``PermissionError`` on purpose: provider
    code that already tolerates an unavailable binary or path (``OSError``) degrades exactly as it
    would on a machine without that resource -- and the denial is recorded, never silent."""

    def __init__(self, reason_code: str, target: str):
        self.reason_code = reason_code
        self.target = target
        super().__init__(f"{reason_code}:{target}")


class TransportPolicyViolation(ProviderContainmentViolation):
    """An HTTP request outside the approved endpoint allow-list (never a provider outcome)."""

    def __init__(self, reason_code: str, method: str, url: Any, *, layer: str, detail: Mapping[str, Any] | None = None):
        self.reason_code = reason_code
        self.method = str(method or "").upper()
        self.endpoint = safe_endpoint(url)
        self.layer = layer
        self.detail = dict(detail or {})
        super().__init__(f"{reason_code}:{layer}:{self.method} {self.endpoint}")


def safe_endpoint(url: Any) -> str:
    """``scheme://host[:port]/path`` -- never query strings, user info or fragments."""
    try:
        parts = urlsplit(str(url))
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port is not None else ""
    except ValueError:
        return "UNPARSEABLE_URL"
    if not parts.scheme or not host:
        return parts.path or "UNPARSEABLE_URL"
    host = f"[{host}]" if ":" in host else host
    return f"{parts.scheme}://{host}{port}{parts.path}"


def compile_path_pattern(template: str) -> re.Pattern[str]:
    """``/a/{symbol}/b`` -> exact regex where each ``{placeholder}`` matches one path segment."""
    if not isinstance(template, str) or not template.startswith("/") or "*" in template:
        raise ValueError(f"ENDPOINT_PATH_PATTERN_INVALID:{template!r}")
    pieces, cursor = [], 0
    for match in _PLACEHOLDER_RE.finditer(template):
        pieces.append(re.escape(template[cursor:match.start()]))
        pieces.append(r"[^/?#]+")
        cursor = match.end()
    pieces.append(re.escape(template[cursor:]))
    return re.compile("^" + "".join(pieces) + "$")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class EndpointRule:
    scheme: str
    host: str
    port: int
    method: str
    path_pattern: str
    purpose: str
    max_redirects: int = 0
    _regex: re.Pattern[str] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.scheme != "https":
            raise ValueError(f"ENDPOINT_SCHEME_NOT_HTTPS:{self.scheme!r}")
        if self.port != 443:
            raise ValueError(f"ENDPOINT_PORT_NOT_443:{self.port!r}")
        if self.method not in ALLOWED_METHODS:
            raise ValueError(f"ENDPOINT_METHOD_NOT_ALLOWED:{self.method!r}")
        if not isinstance(self.host, str) or self.host != self.host.lower() or not _HOST_RE.match(self.host) \
                or _is_ip_literal(self.host):
            raise ValueError(f"ENDPOINT_HOST_INVALID:{self.host!r}")
        if self.max_redirects != 0:
            raise ValueError("ENDPOINT_MAX_REDIRECTS_MUST_BE_ZERO")
        object.__setattr__(self, "_regex", compile_path_pattern(self.path_pattern))

    def matches_path(self, path: str) -> bool:
        return bool(self._regex and self._regex.match(path))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EndpointRule":
        return cls(
            scheme=str(raw.get("scheme")), host=str(raw.get("host")), port=int(raw.get("port", 0)),
            method=str(raw.get("method")), path_pattern=str(raw.get("path_pattern")),
            purpose=str(raw.get("purpose") or ""), max_redirects=int(raw.get("max_redirects", -1)),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme, "host": self.host, "port": self.port, "method": self.method,
            "path_pattern": self.path_pattern, "purpose": self.purpose, "max_redirects": self.max_redirects,
        }


@dataclass(frozen=True)
class EgressPolicy:
    rules: tuple[EndpointRule, ...]
    gateway_host: str | None = None
    gateway_port: int | None = None
    source: str = "APPROVED_BUILD_MANIFEST"

    @classmethod
    def from_endpoints(
        cls, endpoints: Iterable[Mapping[str, Any]], *, gateway: Mapping[str, Any] | None = None,
        source: str = "APPROVED_BUILD_MANIFEST",
    ) -> "EgressPolicy":
        rules = tuple(EndpointRule.from_mapping(item) for item in endpoints)
        host = port = None
        if gateway:
            host, port = str(gateway.get("host") or "").lower(), int(gateway.get("port") or 0)
            if not host or port <= 0:
                raise ValueError("EGRESS_GATEWAY_INVALID")
        return cls(rules=rules, gateway_host=host, gateway_port=port, source=source)

    def hosts(self) -> frozenset[str]:
        return frozenset(rule.host for rule in self.rules)

    def evaluate_http(self, method: Any, url: Any) -> str | None:
        """``None`` when the request is allow-listed, else the deterministic reason code."""
        try:
            parts = urlsplit(str(url))
            host = (parts.hostname or "").lower()
            port = parts.port
        except ValueError:
            return TRANSPORT_URL_UNPARSEABLE
        if not parts.scheme or not host:
            return TRANSPORT_URL_UNPARSEABLE
        if parts.username or parts.password:
            return TRANSPORT_CREDENTIALS_IN_URL
        candidates = [rule for rule in self.rules if rule.host == host]
        if not candidates:
            return TRANSPORT_HOST_NOT_ALLOWLISTED
        scheme = parts.scheme.lower()
        if scheme != "https":
            return TRANSPORT_SCHEME_NOT_ALLOWED
        port = port if port is not None else 443
        candidates = [rule for rule in candidates if rule.port == port]
        if not candidates:
            return TRANSPORT_PORT_NOT_ALLOWED
        verb = str(method or "").upper()
        candidates = [rule for rule in candidates if rule.method == verb]
        if not candidates:
            return TRANSPORT_METHOD_NOT_ALLOWED
        path = parts.path or "/"
        if not any(rule.matches_path(path) for rule in candidates):
            return TRANSPORT_PATH_NOT_ALLOWLISTED
        return None

    def host_allowed(self, host: str) -> bool:
        host = (host or "").lower().rstrip(".")
        return host in self.hosts() or (self.gateway_host is not None and host == self.gateway_host)

    def to_record(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "rules": [rule.to_record() for rule in self.rules],
            "egress_gateway": ({"host": self.gateway_host, "port": self.gateway_port}
                               if self.gateway_host else None),
        }


# ---------------------------------------------------------------------------------------------
# Event log.
# ---------------------------------------------------------------------------------------------


class ContainmentEventLog:
    """Thread-safe, bounded record of every containment decision (never secret values)."""

    MAX_EVENTS = 512

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._sequence = 0
        self._dropped = 0
        self._unexpected = 0

    def record(self, *, phase: str, layer: str, action: str, reason_code: str, target: str,
               expected: bool, thread: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event = {
                "sequence": self._sequence, "phase": phase, "layer": layer, "action": action,
                "reason_code": reason_code, "target": str(target)[:300], "expected": bool(expected),
                "thread": thread if thread is not None else threading.current_thread().name,
            }
            if action == ACTION_DENIED and not expected:
                self._unexpected += 1
            if len(self._events) < self.MAX_EVENTS:
                self._events.append(event)
            else:
                self._dropped += 1
            return event

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence

    def events(self, *, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in self._events if event["sequence"] > after]

    def unexpected_after(self, after: int) -> list[dict[str, Any]]:
        return [event for event in self.events(after=after)
                if event["action"] == ACTION_DENIED and not event["expected"]]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            by_reason: dict[str, int] = {}
            for event in self._events:
                by_reason[event["reason_code"]] = by_reason.get(event["reason_code"], 0) + 1
            return {
                "event_count": self._sequence, "retained_event_count": len(self._events),
                "dropped_event_count": self._dropped, "unexpected_denial_count": self._unexpected,
                "by_reason": dict(sorted(by_reason.items())),
            }


# ---------------------------------------------------------------------------------------------
# Filesystem policy.
# ---------------------------------------------------------------------------------------------

_ROOT_DENIED = "DENIED"
_ROOT_READ_ONLY = "READ_ONLY"
_ROOT_WRITABLE = "WRITABLE"


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _norm_real(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _within(candidate: str, root: str) -> bool:
    return candidate == root or candidate.startswith(root.rstrip("\\/") + os.sep)


@dataclass(frozen=True)
class FilesystemPolicy:
    denied_roots: tuple[str, ...]
    read_only_roots: tuple[str, ...]
    writable_roots: tuple[str, ...]
    _index: tuple[tuple[str, str], ...] = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        index: dict[str, str] = {}
        # Later classes win on an identical root: an approved root is always explicit.
        for kind, roots in ((_ROOT_DENIED, self.denied_roots), (_ROOT_READ_ONLY, self.read_only_roots),
                            (_ROOT_WRITABLE, self.writable_roots)):
            for root in roots:
                if not root:
                    continue
                for form in {_norm(root), _norm_real(root)}:
                    index[form] = kind
        ordered = tuple(sorted(index.items(), key=lambda item: len(item[0]), reverse=True))
        object.__setattr__(self, "_index", ordered)

    def _classify(self, candidate: str) -> str | None:
        for root, kind in self._index:
            if _within(candidate, root):
                return kind
        return None

    def evaluate(self, path: Any, *, write: bool) -> str | None:
        """``None`` when access is permitted, else a reason code. The most specific root decides;
        a path outside every known root is left to the OS controls."""
        try:
            raw = os.fsdecode(path)
        except TypeError:
            return None  # a file descriptor or an object that is not a path
        forms = {_norm(raw), _norm_real(raw)}
        for form in forms:
            kind = self._classify(form)
            if kind == _ROOT_DENIED:
                return FILESYSTEM_DENIED_ROOT
            if kind == _ROOT_READ_ONLY and write:
                return FILESYSTEM_WRITE_TO_READ_ONLY_ROOT
        return None

    def to_record(self) -> dict[str, Any]:
        return {"denied_roots": list(self.denied_roots), "read_only_roots": list(self.read_only_roots),
                "writable_roots": list(self.writable_roots)}


_WRITE_FLAGS = 0
for _flag_name in ("O_WRONLY", "O_RDWR", "O_APPEND", "O_CREAT", "O_TRUNC"):
    _WRITE_FLAGS |= getattr(os, _flag_name, 0)


def _open_is_write(mode: Any, flags: Any) -> bool:
    if isinstance(mode, str) and any(char in mode for char in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _process_name(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    text = os.fsdecode(value) if isinstance(value, (bytes, os.PathLike)) else str(value or "")
    first = text.strip().split()[0] if text.strip() else ""
    base = os.path.basename(first.strip("\"'"))
    return os.path.splitext(base)[0].lower()


# ---------------------------------------------------------------------------------------------
# The worker containment.
# ---------------------------------------------------------------------------------------------

_HOOK_STATE = threading.local()


class WorkerContainment:
    """All four layers for one worker process. Created and installed once, from the launch contract."""

    def __init__(
        self, *, egress: EgressPolicy, filesystem: FilesystemPolicy,
        expected_network_denials: Iterable[str] = (), expected_process_denials: Iterable[str] = (),
    ):
        self.egress = egress
        self.filesystem = filesystem
        self.expected_network_denials = frozenset(host.lower() for host in expected_network_denials)
        self.expected_process_denials = frozenset(name.lower() for name in expected_process_denials)
        self.log = ContainmentEventLog()
        self.phase = PHASE_STARTUP
        self._resolved_addresses: set[str] = set()
        self._resolved_lock = threading.Lock()
        self._installed = False
        self.requests_guard = "NOT_INSTALLED"
        self._handlers: dict[str, Callable[[tuple], None]] = {
            "subprocess.Popen": self._deny_process,
            "os.system": self._deny_process,
            "os.exec": lambda args: self._deny_process(args[:2]),
            "os.spawn": lambda args: self._deny_process(args[1:3]),
            "os.posix_spawn": self._deny_process,
            "os.startfile": self._deny_process,
            "os.startfile/2": self._deny_process,
            "os.fork": lambda _args: self._deny_process(("fork",)),
            "os.forkpty": lambda _args: self._deny_process(("forkpty",)),
            "_winapi.CreateProcess": self._deny_process,
            "socket.getaddrinfo": self._check_resolution,
            "socket.gethostbyname": self._check_resolution,
            "socket.gethostbyname_ex": self._check_resolution,
            "socket.gethostbyaddr": self._check_address_lookup,
            "socket.getnameinfo": self._check_address_lookup,
            "socket.connect": self._check_connect,
            "socket.bind": self._deny_bind,
            "socket.sendto": self._deny_datagram,
            "socket.sendmsg": self._deny_datagram,
            "open": self._check_open,
            "os.listdir": lambda args: self._check_path(args[0] if args else ".", write=False),
            "os.scandir": lambda args: self._check_path(args[0] if args else ".", write=False),
            "os.remove": lambda args: self._check_path(args[0], write=True, dir_fd=args[1] if len(args) > 1 else None),
            "os.rmdir": lambda args: self._check_path(args[0], write=True, dir_fd=args[1] if len(args) > 1 else None),
            "os.mkdir": lambda args: self._check_path(args[0], write=True, dir_fd=args[2] if len(args) > 2 else None),
            "os.chmod": lambda args: self._check_path(args[0], write=True, dir_fd=args[2] if len(args) > 2 else None),
            "os.chown": lambda args: self._check_path(args[0], write=True, dir_fd=args[3] if len(args) > 3 else None),
            "os.utime": lambda args: self._check_path(args[0], write=True, dir_fd=args[3] if len(args) > 3 else None),
            "os.truncate": lambda args: self._check_path(args[0], write=True),
            "os.rename": self._check_two_paths,
            "os.link": self._check_two_paths,
            "os.symlink": self._check_symlink,
            "ctypes.dlopen": self._observe_native,
        }

    # -- installation -------------------------------------------------------------------------

    def install(self) -> None:
        if self._installed:
            raise ProviderContainmentViolation("WORKER_CONTAINMENT_ALREADY_INSTALLED")
        sys.addaudithook(self._audit)
        self._wrap_name_resolution()
        self._installed = True

    def install_requests_guard(self) -> str:
        """Wrap ``requests.Session.send`` when ``requests`` is part of the attested closure."""
        try:
            import requests.sessions  # noqa: F401 -- part of the approved dependency closure
        except ImportError:
            self.requests_guard = "REQUESTS_NOT_IN_RUNTIME"
            return self.requests_guard
        install_requests_transport_guard(lambda: self.egress, log=self.log, phase=lambda: self.phase,
                                         expected_hosts=self.expected_network_denials)
        self.requests_guard = "INSTALLED"
        return self.requests_guard

    @property
    def installed(self) -> bool:
        return self._installed

    def set_phase(self, phase: str) -> None:
        if phase not in (PHASE_STARTUP, PHASE_OPERATION):
            raise ValueError(f"CONTAINMENT_PHASE_UNKNOWN:{phase!r}")
        self.phase = phase

    def summary(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION, "phase": self.phase, "requests_guard": self.requests_guard,
            "egress": self.egress.to_record(), "filesystem": self.filesystem.to_record(),
            "expected_network_denials": sorted(self.expected_network_denials),
            "expected_process_denials": sorted(self.expected_process_denials),
            "events": self.log.summary(),
        }

    # -- the audit hook ----------------------------------------------------------------------

    def _audit(self, event: str, args: tuple) -> None:
        handler = self._handlers.get(event)
        if handler is None or getattr(_HOOK_STATE, "active", False):
            return
        _HOOK_STATE.active = True
        try:
            handler(args)
        finally:
            _HOOK_STATE.active = False

    def _deny(self, layer: str, reason_code: str, target: str, *, expected: bool) -> None:
        self.log.record(phase=self.phase, layer=layer, action=ACTION_DENIED, reason_code=reason_code,
                        target=target, expected=expected)
        raise ProviderContainmentDenied(reason_code, target)

    def _deny_process(self, args: tuple) -> None:
        name = _process_name(args[0] if args else "")
        if not name and len(args) > 1:
            name = _process_name(args[1])
        name = name or "UNKNOWN"
        self._deny(LAYER_PROCESS, PROCESS_CREATION_DENIED, name, expected=name in self.expected_process_denials)

    def _host_text(self, host: Any) -> str:
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        return str(host or "").lower().rstrip(".").strip("[]")

    def _address_allowed(self, host: str) -> bool:
        with self._resolved_lock:
            return host in self._resolved_addresses

    def _check_resolution(self, args: tuple) -> None:
        host = self._host_text(args[0] if args else "")
        if not host:
            self._deny(LAYER_SOCKET, SOCKET_BIND_DENIED, "<passive>", expected=False)
        if _is_ip_literal(host):
            if self._address_allowed(host):
                return
            self._deny(LAYER_SOCKET, SOCKET_ADDRESS_NOT_RESOLVED_FROM_ALLOWLISTED_HOST, host, expected=False)
        if self.egress.host_allowed(host):
            return
        self._deny(LAYER_SOCKET, SOCKET_HOST_NOT_ALLOWLISTED, host, expected=host in self.expected_network_denials)

    def _check_address_lookup(self, args: tuple) -> None:
        value = args[0] if args else ""
        host = self._host_text(value[0] if isinstance(value, tuple) and value else value)
        if self._address_allowed(host) or self.egress.host_allowed(host):
            return
        self._deny(LAYER_SOCKET, SOCKET_ADDRESS_NOT_RESOLVED_FROM_ALLOWLISTED_HOST, host, expected=False)

    def _check_connect(self, args: tuple) -> None:
        address = args[1] if len(args) > 1 else None
        if not isinstance(address, tuple) or not address:
            self._deny(LAYER_SOCKET, SOCKET_ADDRESS_NOT_RESOLVED_FROM_ALLOWLISTED_HOST, repr(address)[:120], expected=False)
        host = self._host_text(address[0])
        if self._address_allowed(host) or (not _is_ip_literal(host) and self.egress.host_allowed(host)):
            return
        self._deny(LAYER_SOCKET, SOCKET_ADDRESS_NOT_RESOLVED_FROM_ALLOWLISTED_HOST, host,
                   expected=host in self.expected_network_denials)

    def _deny_bind(self, args: tuple) -> None:
        address = args[1] if len(args) > 1 else None
        self._deny(LAYER_SOCKET, SOCKET_BIND_DENIED, repr(address)[:120], expected=False)

    def _deny_datagram(self, args: tuple) -> None:
        address = args[1] if len(args) > 1 else None
        host = self._host_text(address[0]) if isinstance(address, tuple) and address else repr(address)[:120]
        self._deny(LAYER_SOCKET, SOCKET_DATAGRAM_DENIED, host, expected=False)

    def _check_open(self, args: tuple) -> None:
        path = args[0] if args else None
        if path is None or isinstance(path, int):
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        self._check_path(path, write=_open_is_write(mode, flags))

    def _check_two_paths(self, args: tuple) -> None:
        self._check_path(args[0], write=True, dir_fd=args[2] if len(args) > 2 else None)
        self._check_path(args[1], write=True, dir_fd=args[3] if len(args) > 3 else None)

    def _check_symlink(self, args: tuple) -> None:
        # A link inside an approved root that points into a denied root is refused at creation,
        # not only when it is later read through.
        self._check_path(args[0], write=False)
        self._check_path(args[1], write=True, dir_fd=args[2] if len(args) > 2 else None)

    def _check_path(self, path: Any, *, write: bool, dir_fd: Any = None) -> None:
        if path is None or isinstance(path, int):
            return
        try:
            text = os.fsdecode(path)
        except TypeError:
            return
        if dir_fd is not None and not os.path.isabs(text):
            resolved = None
            if isinstance(dir_fd, int) and os.path.isdir(f"/proc/self/fd/{dir_fd}"):
                resolved = os.path.join(os.readlink(f"/proc/self/fd/{dir_fd}"), text)
            if resolved is None:
                self._deny(LAYER_FILESYSTEM, FILESYSTEM_PATH_UNRESOLVABLE, text, expected=False)
            text = resolved
        reason = self.filesystem.evaluate(text, write=write)
        if reason is not None:
            self._deny(LAYER_FILESYSTEM, reason, text, expected=False)

    def _observe_native(self, args: tuple) -> None:
        name = os.fsdecode(args[0]) if args and args[0] is not None else "<self>"
        self.log.record(phase=self.phase, layer=LAYER_NATIVE, action=ACTION_OBSERVED,
                        reason_code=NATIVE_LIBRARY_LOAD_OBSERVED, target=name, expected=True)

    # -- name-resolution tracking ------------------------------------------------------------

    def _wrap_name_resolution(self) -> None:
        import socket

        original = socket.getaddrinfo
        containment = self

        def getaddrinfo(host, port, *args, **kwargs):  # noqa: ANN001 -- mirrors socket.getaddrinfo
            results = original(host, port, *args, **kwargs)
            name = containment._host_text(host)
            if containment.egress.host_allowed(name):
                with containment._resolved_lock:
                    for item in results:
                        sockaddr = item[4]
                        if isinstance(sockaddr, tuple) and sockaddr:
                            containment._resolved_addresses.add(str(sockaddr[0]).lower())
            return results

        socket.getaddrinfo = getaddrinfo


# ---------------------------------------------------------------------------------------------
# Process-wide activation.
# ---------------------------------------------------------------------------------------------

_CONTAINMENT: WorkerContainment | None = None
_SCOPED_POLICY: EgressPolicy | None = None
_ACTIVATION_LOCK = threading.Lock()


def install_worker_containment(containment: WorkerContainment) -> WorkerContainment:
    """Install ``containment`` for this process (one-shot; it can never be removed)."""
    global _CONTAINMENT
    with _ACTIVATION_LOCK:
        if _CONTAINMENT is not None:
            raise ProviderContainmentViolation("WORKER_CONTAINMENT_ALREADY_INSTALLED")
        containment.install()
        _CONTAINMENT = containment
    return containment


def containment_installed() -> bool:
    return _CONTAINMENT is not None and _CONTAINMENT.installed


def active_containment() -> WorkerContainment | None:
    return _CONTAINMENT


def active_egress_policy() -> EgressPolicy | None:
    if _CONTAINMENT is not None:
        return _CONTAINMENT.egress
    return _SCOPED_POLICY


@contextmanager
def egress_policy_scope(policy: EgressPolicy) -> Iterator[EgressPolicy]:
    """Reversible in-process activation of an egress policy (tests, bounded diagnostics).

    Refused inside a worker: there the manifest-derived policy is installed once and locked.
    """
    global _SCOPED_POLICY
    if _CONTAINMENT is not None:
        raise ProviderContainmentViolation("EGRESS_POLICY_LOCKED_BY_WORKER_CONTAINMENT")
    if not isinstance(policy, EgressPolicy):
        raise TypeError("EGRESS_POLICY_REQUIRED")
    previous = _SCOPED_POLICY
    _SCOPED_POLICY = policy
    try:
        yield policy
    finally:
        _SCOPED_POLICY = previous


def enforce_transport_policy(method: Any, url: Any, *, layer: str = LAYER_TRANSPORT) -> None:
    """Refuse ``method url`` unless the active egress policy allow-lists it.

    No active policy is itself a refusal (``TRANSPORT_POLICY_NOT_INSTALLED``): the quote transport
    never sends a request that no approved manifest scoped.
    """
    policy = active_egress_policy()
    reason = TRANSPORT_POLICY_NOT_INSTALLED if policy is None else policy.evaluate_http(method, url)
    if reason is None:
        return
    containment = _CONTAINMENT
    if containment is not None:
        host = (urlsplit(str(url)).hostname or "") if reason != TRANSPORT_URL_UNPARSEABLE else ""
        containment.log.record(
            phase=containment.phase, layer=layer, action=ACTION_DENIED, reason_code=reason,
            target=f"{str(method).upper()} {safe_endpoint(url)}",
            expected=host.lower() in containment.expected_network_denials,
        )
    raise TransportPolicyViolation(reason, method, url, layer=layer)


def install_requests_transport_guard(
    policy: Callable[[], EgressPolicy | None], *, log: ContainmentEventLog | None = None,
    phase: Callable[[], str] = lambda: PHASE_OPERATION, expected_hosts: Iterable[str] = (),
) -> Callable[[], None]:
    """Wrap ``requests.sessions.Session.send``; returns an uninstall callable (tests only).

    Every hop is checked before it leaves the process and redirects are never followed.
    """
    import requests.sessions as sessions

    original = sessions.Session.send
    if getattr(original, "_stocklookup_transport_guard", False):
        raise ProviderContainmentViolation("REQUESTS_TRANSPORT_GUARD_ALREADY_INSTALLED")
    expected = frozenset(host.lower() for host in expected_hosts)

    def _refuse(reason: str, method: str, url: str, detail: Mapping[str, Any] | None = None) -> None:
        if log is not None:
            host = (urlsplit(str(url)).hostname or "").lower() if reason != TRANSPORT_URL_UNPARSEABLE else ""
            log.record(phase=phase(), layer=LAYER_REQUESTS, action=ACTION_DENIED, reason_code=reason,
                       target=f"{str(method).upper()} {safe_endpoint(url)}", expected=host in expected)
        raise TransportPolicyViolation(reason, method, url, layer=LAYER_REQUESTS, detail=detail)

    def guarded_send(self, request, **kwargs):  # noqa: ANN001 -- mirrors requests.Session.send
        active = policy()
        method, url = request.method, request.url
        reason = TRANSPORT_POLICY_NOT_INSTALLED if active is None else active.evaluate_http(method, url)
        if reason is not None:
            _refuse(reason, method, url)
        kwargs["allow_redirects"] = False
        response = original(self, request, **kwargs)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location") or ""
            target = urljoin(url, location)
            response.close()
            target_reason = active.evaluate_http("GET", target) if location else TRANSPORT_URL_UNPARSEABLE
            unapproved = target_reason in (TRANSPORT_HOST_NOT_ALLOWLISTED, TRANSPORT_SCHEME_NOT_ALLOWED,
                                           TRANSPORT_PORT_NOT_ALLOWED, TRANSPORT_URL_UNPARSEABLE,
                                           TRANSPORT_CREDENTIALS_IN_URL)
            _refuse(TRANSPORT_REDIRECT_TO_UNAPPROVED_HOST if unapproved else TRANSPORT_REDIRECT_NOT_PERMITTED,
                    method, url, {"redirect_target": safe_endpoint(target)})
        return response

    guarded_send._stocklookup_transport_guard = True  # type: ignore[attr-defined]
    sessions.Session.send = guarded_send

    def uninstall() -> None:
        if sessions.Session.send is guarded_send:
            sessions.Session.send = original

    return uninstall
