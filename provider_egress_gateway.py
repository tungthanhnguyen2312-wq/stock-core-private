"""Governed provider egress gateway (WINDOWS_PROVIDER_RUNTIME_OS_CONTAINMENT_AND_ATTESTATION_V1).

The provider worker has no direct network egress: the OS denies its identity every outbound
connection (``provider_windows_os_backend``). Its only path to a provider host is this gateway:

    worker --(ACL-protected local named pipe)--> gateway (Producer process) --HTTPS--> provider host

The gateway is not a proxy. It has no CONNECT, no tunnel, no generic URL fetch and no arbitrary
host: a worker request names one governed HTTP operation (method + absolute https URL + allow-listed
headers + bounded body) and the gateway itself performs it only when the approved manifest's
endpoint contract allow-lists it -- scheme, host, port, method and path
(``provider_worker_containment.EgressPolicy``, the same evaluator the worker uses in-process).
Redirects are never followed (every approved endpoint has ``max_redirects`` 0): a 3xx answer is
refused, never chased. The owner's hard 20 requests/minute ceiling is enforced here as well, by
refusal (never by sleeping): the gateway is the one choke point the worker cannot route around.
Telemetry hosts are never endpoint rules, so their requests are refused (the manifest's DENY).

Every request the gateway performs is recorded as lineage (request id, launch, rule, safe URL,
acquired-at, response digest) in a ledger the worker cannot read or write. Header values and
bodies are never logged.

Three parts, one module (bundled into the worker for the client side only):

* ``GatewayCore`` -- platform-neutral validation, rate ceiling, HTTPS execution and lineage. Its
  HTTP performer is injectable, so hermetic tests run it without a network or a pipe.
* ``NamedPipeGatewayServer`` -- Windows: one per launch, pipe
  ``\\\\.\\pipe\\StockLookupProviderGateway-<launch_id>`` created as the first instance with an
  explicit DACL (SYSTEM + the Producer identity: full; the worker identity: read/write, no new
  instances), remote clients rejected. Each connecting client must be a process of the launch's
  Job (``client_pid_allowed``) and, read back by impersonating it, the worker identity.
* ``NamedPipeGatewayClient`` -- the worker side: connects, verifies the server process, performs
  the HELLO handshake (launch id + egress policy digest) and turns gateway answers into
  ``requests.Response`` objects for the in-worker requests guard.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import re
import struct
import sys
import threading
import time
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CONTRACT_VERSION = "provider_egress_gateway/v1"
GATEWAY_ID = "stocklookup-provider-egress-gateway"
IMPLEMENTATION = "PYTHON_IN_PROCESS_NAMED_PIPE_HTTPS_GATEWAY_V1"
TRANSPORT_WINDOWS_NAMED_PIPE = "WINDOWS_NAMED_PIPE"
IPC_ENDPOINT_TEMPLATE = r"\\.\pipe\StockLookupProviderGateway-{launch_id}"

OP_HELLO = "HELLO"
OP_HTTP_REQUEST = "HTTP_REQUEST"
OPERATIONS = (OP_HELLO, OP_HTTP_REQUEST)

MAX_FRAME_BYTES = 48 * 1024 * 1024
MAX_REQUEST_BODY_BYTES = 256 * 1024
MAX_RESPONSE_BODY_BYTES = 32 * 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 30.0
RATE_WINDOW_SECONDS = 60.0

# Headers a worker may ask the gateway to send. Anything else (Host, Proxy-*, Connection, Cookie,
# Authorization, transfer/hop-by-hop headers, X-Forwarded-*) is dropped -- the gateway builds the
# request itself.
FORWARDED_REQUEST_HEADERS = frozenset({
    "accept", "accept-language", "cache-control", "content-type", "origin", "pragma", "referer", "user-agent",
})
# Response headers returned to the worker (the body is already decoded, so no Content-Encoding).
RETURNED_RESPONSE_HEADERS = frozenset({
    "cache-control", "content-language", "content-type", "date", "etag", "expires", "last-modified",
    "retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
})
_SECRET_QUERY_NAME = re.compile(r"(key|token|secret|sig|signature|password|auth)", re.IGNORECASE)

# --- deterministic reason codes -----------------------------------------------------------------
R_FRAME_INVALID = "GATEWAY_FRAME_INVALID"
R_OPERATION_NOT_GOVERNED = "GATEWAY_OPERATION_NOT_GOVERNED"
R_HELLO_REQUIRED = "GATEWAY_HELLO_REQUIRED"
R_LAUNCH_MISMATCH = "GATEWAY_LAUNCH_ID_MISMATCH"
R_POLICY_DIGEST_MISMATCH = "GATEWAY_EGRESS_POLICY_DIGEST_MISMATCH"
R_CLIENT_NOT_AUTHORIZED = "GATEWAY_CLIENT_NOT_AUTHORIZED"
R_BODY_TOO_LARGE = "GATEWAY_REQUEST_BODY_TOO_LARGE"
R_RESPONSE_TOO_LARGE = "GATEWAY_RESPONSE_BODY_TOO_LARGE"
R_RATE_CEILING = "GATEWAY_RATE_CEILING_EXCEEDED"
R_REDIRECT_NOT_PERMITTED = "GATEWAY_REDIRECT_NOT_PERMITTED"
R_UPSTREAM_CONNECT_TIMEOUT = "GATEWAY_UPSTREAM_CONNECT_TIMEOUT"
R_UPSTREAM_READ_TIMEOUT = "GATEWAY_UPSTREAM_READ_TIMEOUT"
R_UPSTREAM_CONNECTION_FAILED = "GATEWAY_UPSTREAM_CONNECTION_FAILED"
R_UPSTREAM_TLS_FAILED = "GATEWAY_UPSTREAM_TLS_FAILED"
R_GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
R_SERVER_IDENTITY_MISMATCH = "GATEWAY_SERVER_IDENTITY_MISMATCH"
R_PIPE_ALREADY_EXISTS = "GATEWAY_PIPE_ALREADY_EXISTS"

KIND_POLICY = "POLICY_REFUSAL"
KIND_UPSTREAM = "UPSTREAM_FAILURE"
KIND_PROTOCOL = "PROTOCOL_FAILURE"

_UPSTREAM_FAILURE_CODES = frozenset({R_UPSTREAM_CONNECT_TIMEOUT, R_UPSTREAM_READ_TIMEOUT,
                                     R_UPSTREAM_CONNECTION_FAILED, R_UPSTREAM_TLS_FAILED})


class GatewayRefusal(Exception):
    """A gateway answer that is not an HTTP response. Never carries header values or bodies."""

    def __init__(self, code: str, kind: str, detail: Mapping[str, Any] | None = None):
        self.code = code
        self.kind = kind
        self.detail = dict(detail or {})
        super().__init__(f"{code}:{kind}")


def module_sha256() -> str:
    """Identity of this gateway implementation: the SHA-256 of the module's own source bytes."""
    with open(os.path.abspath(__file__), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def ipc_endpoint_for(launch_id: str, template: str = IPC_ENDPOINT_TEMPLATE) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", str(launch_id or "")):
        raise ValueError("GATEWAY_LAUNCH_ID_INVALID")
    return template.format(launch_id=launch_id)


def gateway_identity(*, executable_sha256: str | None = None) -> dict[str, Any]:
    """The identity an approved manifest binds as ``network.egress_gateway``."""
    return {
        "gateway_id": GATEWAY_ID, "implementation": IMPLEMENTATION, "transport": TRANSPORT_WINDOWS_NAMED_PIPE,
        "ipc_endpoint": IPC_ENDPOINT_TEMPLATE, "executable_sha256": executable_sha256 or module_sha256(),
        "host": None, "port": None,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def lineage_url(url: str) -> str:
    """The URL as lineage records it: scheme/host/path plus the query, with any secret-shaped
    parameter value replaced by a digest (provider query strings carry symbols and dates)."""
    parts = urlsplit(url)
    query = [(name, ("sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16])
              if _SECRET_QUERY_NAME.search(name) else value)
             for name, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, urlencode(query), ""))


# ---------------------------------------------------------------------------------------------
# Framing (4-byte little-endian length + UTF-8 JSON).
# ---------------------------------------------------------------------------------------------


def encode_frame(message: Mapping[str, Any]) -> bytes:
    payload = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_FRAME_BYTES:
        raise GatewayRefusal(R_FRAME_INVALID, KIND_PROTOCOL, {"error": "frame too large"})
    return struct.pack("<I", len(payload)) + payload


def decode_frame(read_exact: Callable[[int], bytes]) -> dict[str, Any]:
    header = read_exact(4)
    (length,) = struct.unpack("<I", header)
    if length > MAX_FRAME_BYTES:
        raise GatewayRefusal(R_FRAME_INVALID, KIND_PROTOCOL, {"error": "frame too large"})
    try:
        message = json.loads(read_exact(length).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise GatewayRefusal(R_FRAME_INVALID, KIND_PROTOCOL, {"error": "not JSON"}) from None
    if not isinstance(message, dict):
        raise GatewayRefusal(R_FRAME_INVALID, KIND_PROTOCOL, {"error": "not an object"})
    return message


# ---------------------------------------------------------------------------------------------
# Core (platform-neutral).
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    reason: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    final_url: str


def _decode_body(body: bytes, encoding: str) -> bytes:
    encoding = (encoding or "").strip().lower()
    if encoding in ("", "identity"):
        return body
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    raise GatewayRefusal(R_UPSTREAM_CONNECTION_FAILED, KIND_UPSTREAM, {"error": f"unsupported content-encoding {encoding}"})


def https_perform(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> UpstreamResponse:
    """The gateway's own HTTPS request: certificate-verified TLS, no proxy, no redirect following.
    Name resolution and the connection are made by the gateway process, never by the worker."""
    import http.client
    import socket
    import ssl

    parts = urlsplit(url)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=CONNECT_TIMEOUT_SECONDS,
                                             context=ssl.create_default_context())
    try:
        try:
            connection.connect()
        except (socket.timeout, TimeoutError):
            raise GatewayRefusal(R_UPSTREAM_CONNECT_TIMEOUT, KIND_UPSTREAM) from None
        except ssl.SSLError as exc:
            raise GatewayRefusal(R_UPSTREAM_TLS_FAILED, KIND_UPSTREAM, {"error": type(exc).__name__}) from None
        except OSError as exc:
            raise GatewayRefusal(R_UPSTREAM_CONNECTION_FAILED, KIND_UPSTREAM, {"error": type(exc).__name__}) from None
        if connection.sock is not None:
            connection.sock.settimeout(READ_TIMEOUT_SECONDS)
        try:
            connection.request(method, target, body=body, headers=dict(headers))
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BODY_BYTES + 1)
        except (socket.timeout, TimeoutError):
            raise GatewayRefusal(R_UPSTREAM_READ_TIMEOUT, KIND_UPSTREAM) from None
        except (OSError, http.client.HTTPException) as exc:
            raise GatewayRefusal(R_UPSTREAM_CONNECTION_FAILED, KIND_UPSTREAM, {"error": type(exc).__name__}) from None
        if len(raw) > MAX_RESPONSE_BODY_BYTES:
            raise GatewayRefusal(R_RESPONSE_TOO_LARGE, KIND_UPSTREAM)
        header_items = tuple((str(k), str(v)) for k, v in response.getheaders())
        encoding = next((v for k, v in header_items if k.lower() == "content-encoding"), "")
        body_bytes = _decode_body(raw, encoding)
        if len(body_bytes) > MAX_RESPONSE_BODY_BYTES:
            raise GatewayRefusal(R_RESPONSE_TOO_LARGE, KIND_UPSTREAM)
        return UpstreamResponse(status=int(response.status), reason=str(response.reason or ""), headers=header_items,
                                body=body_bytes, final_url=url)
    finally:
        connection.close()


class RateCeiling:
    """Hard per-minute ceiling by refusal: at most ``per_minute`` admitted requests in any rolling
    60-second window. Never sleeps."""

    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic):
        if not isinstance(per_minute, int) or isinstance(per_minute, bool) or per_minute < 1:
            raise ValueError("GATEWAY_RATE_CEILING_INVALID")
        self.per_minute = per_minute
        self._clock = clock
        self._admitted: list[float] = []
        self._lock = threading.Lock()

    def admit(self) -> bool:
        with self._lock:
            now = self._clock()
            self._admitted = [stamp for stamp in self._admitted if now - stamp < RATE_WINDOW_SECONDS]
            if len(self._admitted) >= self.per_minute:
                return False
            self._admitted.append(now)
            return True


class GatewayCore:
    """Validation, rate ceiling, execution and lineage for one launch. Never a proxy."""

    def __init__(
        self, *, launch_id: str, egress_policy: Any, egress_policy_sha256: str, rate_per_minute: int,
        denied_telemetry_hosts: Iterable[str] = (), perform: Callable[..., UpstreamResponse] = https_perform,
        ledger_path: str | None = None, clock: Callable[[], float] = time.monotonic,
    ):
        self.launch_id = launch_id
        self.egress_policy = egress_policy
        self.egress_policy_sha256 = egress_policy_sha256
        self.rate = RateCeiling(rate_per_minute, clock=clock)
        self.denied_telemetry_hosts = frozenset(host.lower() for host in denied_telemetry_hosts)
        self._perform = perform
        self._ledger_path = ledger_path
        self._ledger_lock = threading.Lock()
        self.counters = {"admitted": 0, "refused": 0, "upstream_failures": 0, "telemetry_denied": 0}
        self.handshakes: list[dict[str, Any]] = []

    # -- lineage ------------------------------------------------------------------------------

    def _record(self, entry: Mapping[str, Any]) -> None:
        if not self._ledger_path:
            return
        line = json.dumps(dict(entry), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._ledger_lock, open(self._ledger_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    # -- operations ---------------------------------------------------------------------------

    def hello(self, message: Mapping[str, Any], *, client: Mapping[str, Any]) -> dict[str, Any]:
        if message.get("launch_id") != self.launch_id:
            raise GatewayRefusal(R_LAUNCH_MISMATCH, KIND_POLICY)
        if message.get("egress_policy_sha256") != self.egress_policy_sha256:
            raise GatewayRefusal(R_POLICY_DIGEST_MISMATCH, KIND_POLICY)
        record = {"at_utc": _utc_now(), "client": dict(client), "launch_id": self.launch_id}
        self.handshakes.append(record)
        self._record({"event": "HELLO", **record})
        return {"ok": True, "gateway_id": GATEWAY_ID, "implementation": IMPLEMENTATION,
                "contract_version": CONTRACT_VERSION, "egress_policy_sha256": self.egress_policy_sha256,
                "rate_per_minute": self.rate.per_minute, "server_pid": os.getpid()}

    def _refuse(self, request_id: str, code: str, kind: str, *, method: str, url: str,
                detail: Mapping[str, Any] | None = None) -> GatewayRefusal:
        host = (urlsplit(url).hostname or "").lower() if url else ""
        expected = kind == KIND_POLICY and host in self.denied_telemetry_hosts
        self.counters["refused" if kind == KIND_POLICY else "upstream_failures"] += 1
        if expected:
            self.counters["telemetry_denied"] += 1
        self._record({"event": "REFUSED", "request_id": request_id, "launch_id": self.launch_id, "at_utc": _utc_now(),
                      "code": code, "kind": kind, "method": method, "endpoint": _safe(url),
                      "expected_telemetry_denial": expected})
        return GatewayRefusal(code, kind, {**dict(detail or {}), "expected_telemetry_denial": expected})

    def http_request(self, message: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(message.get("request_id") or uuid.uuid4().hex)
        method = str(message.get("method") or "").upper()
        url = str(message.get("url") or "")
        reason = self.egress_policy.evaluate_http(method, url)
        if reason is not None:
            raise self._refuse(request_id, reason, KIND_POLICY, method=method, url=url)
        body = None
        if message.get("body_b64") is not None:
            try:
                body = base64.b64decode(str(message["body_b64"]), validate=True)
            except (ValueError, TypeError):
                raise self._refuse(request_id, R_FRAME_INVALID, KIND_POLICY, method=method, url=url) from None
            if len(body) > MAX_REQUEST_BODY_BYTES:
                raise self._refuse(request_id, R_BODY_TOO_LARGE, KIND_POLICY, method=method, url=url)
        headers = {}
        for item in message.get("headers") or []:
            if isinstance(item, (list, tuple)) and len(item) == 2 and str(item[0]).lower() in FORWARDED_REQUEST_HEADERS:
                headers[str(item[0])] = str(item[1])
        headers["Accept-Encoding"] = "gzip, deflate"
        if not self.rate.admit():
            raise self._refuse(request_id, R_RATE_CEILING, KIND_POLICY, method=method, url=url,
                               detail={"rate_per_minute": self.rate.per_minute})
        acquired_at = _utc_now()
        try:
            upstream = self._perform(method, url, headers, body)
        except GatewayRefusal as exc:
            raise self._refuse(request_id, exc.code, exc.kind, method=method, url=url, detail=exc.detail) from None
        if 300 <= upstream.status < 400:
            # Every approved endpoint has max_redirects 0: a redirect is refused, never followed.
            location = next((v for k, v in upstream.headers if k.lower() == "location"), "")
            raise self._refuse(request_id, R_REDIRECT_NOT_PERMITTED, KIND_POLICY, method=method, url=url,
                               detail={"status": upstream.status, "redirect_target": _safe(location)})
        self.counters["admitted"] += 1
        digest = hashlib.sha256(upstream.body).hexdigest()
        lineage = {"request_id": request_id, "launch_id": self.launch_id, "gateway_id": GATEWAY_ID,
                   "method": method, "url": lineage_url(url), "acquired_at_utc": acquired_at,
                   "status": upstream.status, "response_sha256": digest, "response_bytes": len(upstream.body)}
        self._record({"event": "PERFORMED", **lineage})
        headers_out = [[k, v] for k, v in upstream.headers if k.lower() in RETURNED_RESPONSE_HEADERS]
        return {"ok": True, "status": upstream.status, "reason": upstream.reason, "headers": headers_out,
                "body_b64": base64.b64encode(upstream.body).decode("ascii"), "url": upstream.final_url,
                "lineage": lineage}

    def handle(self, message: Mapping[str, Any], *, client: Mapping[str, Any], greeted: bool) -> dict[str, Any]:
        """One request frame -> one answer frame. Refusals become ``{"ok": false, ...}`` answers."""
        op = message.get("op")
        try:
            if op not in OPERATIONS:
                raise GatewayRefusal(R_OPERATION_NOT_GOVERNED, KIND_POLICY, {"op": str(op)[:40]})
            if op == OP_HELLO:
                return self.hello(message, client=client)
            if not greeted:
                raise GatewayRefusal(R_HELLO_REQUIRED, KIND_PROTOCOL)
            return self.http_request(message)
        except GatewayRefusal as exc:
            return {"ok": False, "code": exc.code, "kind": exc.kind, "detail": exc.detail}


def _safe(url: str) -> str:
    try:
        from provider_worker_containment import safe_endpoint
    except ImportError:  # pragma: no cover -- both modules ship together
        return "UNAVAILABLE"
    return safe_endpoint(url)


# ---------------------------------------------------------------------------------------------
# Windows named-pipe transport.
# ---------------------------------------------------------------------------------------------

_PIPE_ACCESS_DUPLEX = 0x00000003
_FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
_PIPE_TYPE_BYTE = 0x0
_PIPE_WAIT = 0x0
_PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
_ERROR_PIPE_CONNECTED = 535
_ERROR_ACCESS_DENIED = 5
_ERROR_PIPE_BUSY = 231
_INVALID_HANDLE_VALUE = -1
_TOKEN_QUERY = 0x0008
# FILE_GENERIC_READ | FILE_GENERIC_WRITE without FILE_CREATE_PIPE_INSTANCE (FILE_APPEND_DATA).
PIPE_CLIENT_RIGHTS = 0x0012019B


def pipe_sddl(owner_sid: str, worker_sid: str) -> str:
    """Protected DACL: SYSTEM + the Producer identity full; the worker read/write only."""
    for sid in (owner_sid, worker_sid):
        if not re.fullmatch(r"S-1-[0-9]+(?:-[0-9]+){1,14}", str(sid or "")):
            raise ValueError("GATEWAY_PIPE_SID_INVALID")
    return f"D:P(A;;GA;;;SY)(A;;GA;;;{owner_sid})(A;;0x{PIPE_CLIENT_RIGHTS:08x};;;{worker_sid})"


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateNamedPipeW.restype = wintypes.HANDLE
    k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    k32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    k32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
    k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    k32.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    k32.GetCurrentThread.restype = wintypes.HANDLE
    k32.OpenThread.restype = wintypes.HANDLE
    k32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    return k32


class _SecurityAttributes:
    """A SECURITY_ATTRIBUTES built from an SDDL string (freed on close)."""

    def __init__(self, sddl: str):
        import ctypes
        from ctypes import wintypes

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                        ("bInheritHandle", wintypes.BOOL)]

        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.ULONG)]
        self._descriptor = ctypes.c_void_p()
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(self._descriptor), None):
            raise OSError(ctypes.get_last_error(), "ConvertStringSecurityDescriptorToSecurityDescriptorW")
        self.value = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), self._descriptor, False)
        self.pointer = ctypes.pointer(self.value)

    def close(self) -> None:
        if self._descriptor:
            _kernel32().LocalFree(self._descriptor)
            self._descriptor = None


def _impersonated_client_sid(k32, pipe) -> dict[str, Any]:
    """Read the connected client's token user SID by impersonating it (identification level is
    enough) and reverting immediately. Returns the SID plus which read-back succeeded."""
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.ImpersonateNamedPipeClient.argtypes = [wintypes.HANDLE]
    advapi.OpenThreadToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    if not advapi.ImpersonateNamedPipeClient(pipe):
        return {"sid": None, "error": f"ImpersonateNamedPipeClient:{ctypes.get_last_error()}"}
    token = wintypes.HANDLE()
    errors = []
    try:
        opened = False
        for as_self in (True, False):
            if advapi.OpenThreadToken(k32.GetCurrentThread(), _TOKEN_QUERY, as_self, ctypes.byref(token)):
                opened = True
                break
            errors.append(f"OpenThreadToken(as_self={as_self}):{ctypes.get_last_error()}")
    finally:
        advapi.RevertToSelf()
    if not opened:
        return {"sid": None, "error": ";".join(errors)}
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            return {"sid": None, "error": f"GetTokenInformation:{ctypes.get_last_error()}"}
        text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.byref(text)):
            return {"sid": None, "error": f"ConvertSidToStringSidW:{ctypes.get_last_error()}"}
        try:
            return {"sid": text.value, "error": None}
        finally:
            k32.LocalFree(text)
    finally:
        k32.CloseHandle(token)


class NamedPipeGatewayServer:
    """The per-launch gateway endpoint (Windows). One pipe instance; one client at a time."""

    def __init__(self, core: GatewayCore, *, pipe_name: str, owner_sid: str, worker_sid: str,
                 client_pid_allowed: Callable[[int], bool]):
        if sys.platform != "win32":
            raise OSError("GATEWAY_NAMED_PIPE_REQUIRES_WINDOWS")
        self.core = core
        self.pipe_name = pipe_name
        self.owner_sid = owner_sid
        self.worker_sid = worker_sid
        self._client_pid_allowed = client_pid_allowed
        self._k32 = _kernel32()
        self._pipe = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._stopping = threading.Event()
        self._ready = threading.Event()
        self.server_pid: int | None = None
        self.rejected_clients: list[dict[str, Any]] = []
        self.accepted_clients: list[dict[str, Any]] = []

    def start(self) -> None:
        import ctypes
        from ctypes import wintypes

        attributes = _SecurityAttributes(pipe_sddl(self.owner_sid, self.worker_sid))
        try:
            handle = self._k32.CreateNamedPipeW(
                self.pipe_name, _PIPE_ACCESS_DUPLEX | _FILE_FLAG_FIRST_PIPE_INSTANCE,
                _PIPE_TYPE_BYTE | _PIPE_WAIT | _PIPE_REJECT_REMOTE_CLIENTS, 1, 1 << 20, 1 << 20, 0, attributes.pointer)
            error = ctypes.get_last_error()
        finally:
            attributes.close()
        if handle is None or handle == _INVALID_HANDLE_VALUE or int(handle or 0) == 2 ** 64 - 1:
            # FIRST_PIPE_INSTANCE: a pre-existing (possibly squatted) pipe of this name is refused.
            # (ACCESS_DENIED for FIRST_PIPE_INSTANCE, PIPE_BUSY when the one instance already exists)
            raise GatewayRefusal(R_PIPE_ALREADY_EXISTS if error in (_ERROR_ACCESS_DENIED, _ERROR_PIPE_BUSY)
                                 else R_GATEWAY_UNAVAILABLE,
                                 KIND_PROTOCOL, {"win32_error": error})
        self._pipe = handle
        server = wintypes.ULONG()
        if not self._k32.GetNamedPipeServerProcessId(handle, ctypes.byref(server)):
            self._k32.CloseHandle(handle)
            raise GatewayRefusal(R_GATEWAY_UNAVAILABLE, KIND_PROTOCOL, {"win32_error": ctypes.get_last_error()})
        self.server_pid = int(server.value)
        self._thread = threading.Thread(target=self._serve, name=f"provider-gateway-{self.core.launch_id[:8]}", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def identity(self) -> dict[str, Any]:
        return {"gateway_id": GATEWAY_ID, "implementation": IMPLEMENTATION, "transport": TRANSPORT_WINDOWS_NAMED_PIPE,
                "ipc_endpoint_instance": self.pipe_name, "server_pid": self.server_pid,
                "server_is_this_process": self.server_pid == os.getpid(), "executable_sha256": module_sha256(),
                "egress_policy_sha256": self.core.egress_policy_sha256, "rate_per_minute": self.core.rate.per_minute,
                "pipe_sddl": pipe_sddl(self.owner_sid, self.worker_sid)}

    # -- serving ------------------------------------------------------------------------------

    def _read_exact(self, size: int) -> bytes:
        import ctypes
        from ctypes import wintypes

        chunks, remaining = [], size
        while remaining:
            buffer = ctypes.create_string_buffer(min(remaining, 1 << 20))
            read = wintypes.DWORD()
            if not self._k32.ReadFile(self._pipe, buffer, len(buffer), ctypes.byref(read), None) or read.value == 0:
                raise EOFError
            chunks.append(buffer.raw[:read.value])
            remaining -= read.value
        return b"".join(chunks)

    def _write(self, data: bytes) -> None:
        import ctypes
        from ctypes import wintypes

        view = memoryview(data)
        while view:
            written = wintypes.DWORD()
            chunk = bytes(view[:1 << 20])
            if not self._k32.WriteFile(self._pipe, chunk, len(chunk), ctypes.byref(written), None):
                raise EOFError
            view = view[written.value:]

    def _serve(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._thread_id = threading.get_native_id()
        self._ready.set()
        while not self._stopping.is_set():
            if not self._k32.ConnectNamedPipe(self._pipe, None) and ctypes.get_last_error() != _ERROR_PIPE_CONNECTED:
                if self._stopping.is_set():
                    break
                continue
            if self._stopping.is_set():
                break
            client_pid = wintypes.ULONG()
            self._k32.GetNamedPipeClientProcessId(self._pipe, ctypes.byref(client_pid))
            client: dict[str, Any] = {"pid": int(client_pid.value), "sid": None}
            if not client["pid"] or not self._client_pid_allowed(client["pid"]):
                # Not a process of this launch's Job: dropped before a single frame is read
                # (DisconnectNamedPipe discards anything unread); the refusal is recorded here.
                self.rejected_clients.append({**client, "at_utc": _utc_now(), "code": R_CLIENT_NOT_AUTHORIZED,
                                              "reason": "CLIENT_PROCESS_NOT_IN_LAUNCH_JOB"})
                self._k32.DisconnectNamedPipe(self._pipe)
                continue
            try:
                first = decode_frame(self._read_exact)
            except (GatewayRefusal, EOFError, OSError):
                self._k32.DisconnectNamedPipe(self._pipe)
                continue
            # Impersonation needs data read from the pipe first; identification level suffices.
            identity = _impersonated_client_sid(self._k32, self._pipe)
            client.update(sid=identity.get("sid"), sid_readback_error=identity.get("error"))
            if client["sid"] != self.worker_sid:
                self.rejected_clients.append({**client, "at_utc": _utc_now(), "code": R_CLIENT_NOT_AUTHORIZED,
                                              "reason": "CLIENT_TOKEN_NOT_WORKER_IDENTITY"})
                self._k32.DisconnectNamedPipe(self._pipe)
                continue
            self.accepted_clients.append({**client, "at_utc": _utc_now()})
            greeted = False
            pending: dict[str, Any] | None = first
            try:
                while not self._stopping.is_set():
                    if pending is not None:
                        message, pending = pending, None
                    else:
                        try:
                            message = decode_frame(self._read_exact)
                        except GatewayRefusal as exc:
                            self._write(encode_frame({"ok": False, "code": exc.code, "kind": exc.kind}))
                            break
                    answer = self.core.handle(message, client=client, greeted=greeted)
                    if message.get("op") == OP_HELLO and answer.get("ok"):
                        greeted = True
                    self._write(encode_frame(answer))
            except (EOFError, OSError):
                pass
            self._k32.DisconnectNamedPipe(self._pipe)

    def stop(self) -> None:
        self._stopping.set()
        if self._thread_id is not None and self._thread is not None and self._thread.is_alive():
            thread = self._k32.OpenThread(0x0001, False, self._thread_id)  # THREAD_TERMINATE (CancelSynchronousIo)
            if thread:
                self._k32.CancelSynchronousIo(thread)
                self._k32.CloseHandle(thread)
            self._thread.join(timeout=5)
        if self._pipe is not None:
            self._k32.CloseHandle(self._pipe)
            self._pipe = None


# ---------------------------------------------------------------------------------------------
# Worker-side client.
# ---------------------------------------------------------------------------------------------


class NamedPipeGatewayClient:
    """Connects to the launch's gateway pipe, verifies the server process, greets it, and performs
    governed requests. One persistent connection; requests are serialised."""

    def __init__(self, *, pipe_name: str, launch_id: str, egress_policy_sha256: str, expected_server_pid: int | None):
        self.pipe_name = pipe_name
        self.launch_id = launch_id
        self.egress_policy_sha256 = egress_policy_sha256
        self.expected_server_pid = expected_server_pid
        self._handle: io.RawIOBase | None = None
        self._lock = threading.Lock()
        self.server: dict[str, Any] = {}

    def _read_exact(self, size: int) -> bytes:
        assert self._handle is not None
        chunks, remaining = [], size
        while remaining:
            chunk = self._handle.read(remaining)
            if not chunk:
                raise GatewayRefusal(R_GATEWAY_UNAVAILABLE, KIND_PROTOCOL, {"error": "pipe closed"})
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _exchange(self, message: Mapping[str, Any]) -> dict[str, Any]:
        assert self._handle is not None
        self._handle.write(encode_frame(message))
        return decode_frame(self._read_exact)

    def connect(self) -> dict[str, Any]:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        try:
            self._handle = open(self.pipe_name, "r+b", buffering=0)  # noqa: SIM115 -- persistent connection
        except OSError as exc:
            raise GatewayRefusal(R_GATEWAY_UNAVAILABLE, KIND_PROTOCOL, {"error": type(exc).__name__}) from None
        k32 = _kernel32()
        server = wintypes.ULONG()
        if not k32.GetNamedPipeServerProcessId(msvcrt.get_osfhandle(self._handle.fileno()), ctypes.byref(server)):
            raise GatewayRefusal(R_SERVER_IDENTITY_MISMATCH, KIND_PROTOCOL, {"error": "server pid unreadable"})
        if self.expected_server_pid is not None and int(server.value) != int(self.expected_server_pid):
            raise GatewayRefusal(R_SERVER_IDENTITY_MISMATCH, KIND_PROTOCOL, {"observed_server_pid": int(server.value)})
        try:
            answer = self._exchange({"op": OP_HELLO, "launch_id": self.launch_id,
                                     "egress_policy_sha256": self.egress_policy_sha256, "client_pid": os.getpid()})
        except OSError as exc:
            # The gateway drops a client it does not authorise without answering.
            raise GatewayRefusal(R_GATEWAY_UNAVAILABLE, KIND_PROTOCOL, {"error": type(exc).__name__,
                                                                        "stage": "HELLO"}) from None
        if not answer.get("ok"):
            raise GatewayRefusal(str(answer.get("code") or R_GATEWAY_UNAVAILABLE), str(answer.get("kind") or KIND_PROTOCOL))
        if answer.get("egress_policy_sha256") != self.egress_policy_sha256 or answer.get("gateway_id") != GATEWAY_ID:
            raise GatewayRefusal(R_POLICY_DIGEST_MISMATCH, KIND_POLICY)
        self.server = {"server_pid": int(server.value), **{k: answer.get(k) for k in (
            "gateway_id", "implementation", "contract_version", "egress_policy_sha256", "rate_per_minute")}}
        return dict(self.server)

    def request(self, *, method: str, url: str, headers: Iterable[tuple[str, str]], body: bytes | None) -> dict[str, Any]:
        message = {"op": OP_HTTP_REQUEST, "request_id": uuid.uuid4().hex, "method": method, "url": url,
                   "headers": [[str(k), str(v)] for k, v in headers],
                   "body_b64": base64.b64encode(body).decode("ascii") if body else None}
        with self._lock:
            if self._handle is None:
                raise GatewayRefusal(R_GATEWAY_UNAVAILABLE, KIND_PROTOCOL, {"error": "not connected"})
            try:
                return self._exchange(message)
            except OSError as exc:
                raise GatewayRefusal(R_GATEWAY_UNAVAILABLE, KIND_PROTOCOL, {"error": type(exc).__name__}) from None

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            finally:
                self._handle = None


def answer_to_requests_response(answer: Mapping[str, Any], prepared_request: Any):
    """Turn a gateway answer into a ``requests.Response`` (or raise the matching ``requests``
    exception for an upstream failure, so provider retry classification is unchanged)."""
    import requests
    from requests.structures import CaseInsensitiveDict

    if not answer.get("ok"):
        code = str(answer.get("code") or R_GATEWAY_UNAVAILABLE)
        if code == R_UPSTREAM_CONNECT_TIMEOUT:
            raise requests.exceptions.ConnectTimeout(code, request=prepared_request)
        if code == R_UPSTREAM_READ_TIMEOUT:
            raise requests.exceptions.ReadTimeout(code, request=prepared_request)
        if code in _UPSTREAM_FAILURE_CODES:
            raise requests.exceptions.ConnectionError(code, request=prepared_request)
        raise GatewayRefusal(code, str(answer.get("kind") or KIND_POLICY), answer.get("detail") or {})
    response = requests.models.Response()
    response.status_code = int(answer["status"])
    response.reason = str(answer.get("reason") or "")
    response.headers = CaseInsensitiveDict({str(k): str(v) for k, v in answer.get("headers") or []})
    body = base64.b64decode(str(answer.get("body_b64") or ""))
    response._content = body
    response._content_consumed = True
    response.raw = io.BytesIO(body)
    response.url = str(answer.get("url") or getattr(prepared_request, "url", ""))
    response.request = prepared_request
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    response.gateway_lineage = dict(answer.get("lineage") or {})  # type: ignore[attr-defined]
    return response
