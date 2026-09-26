"""Windows production OS-enforcement backend (WINDOWS_PROVIDER_RUNTIME_OS_CONTAINMENT_AND_ATTESTATION_V1).

Implements the ``provider_os_enforcement.ProviderOSEnforcementBackend`` contract with real Win32
controls, read back from the OS for every launch:

* **Identity** -- the worker runs as the dedicated standard local account provisioned by
  ``tools/provision_provider_os_containment.ps1`` (never a Codex/sandbox/service account). The
  account's random logon secret exists only as a DPAPI (owner, current-user scope) blob in the
  ACL-protected host directory; it is decrypted in memory per launch and never logged. The worker
  is started with ``CreateProcessWithLogonW`` -- the one mechanism that starts a process as another
  account from a non-elevated Producer without a service. Its user SID is read back from the OS
  (token query where the token DACL allows it, otherwise the process object's owner), and the
  interpreter's SID again by impersonating it on the gateway pipe.
* **Process containment** -- a per-launch Job object ``Local\\StockLookupProvider-<launch_id>``
  (explicit DACL: SYSTEM + the Producer identity only) with KILL_ON_JOB_CLOSE, the approved
  active-process limit and no breakaway / silent breakaway. Launch order: Job created and its limits
  read back; worker created *suspended*; assigned; membership verified through this Job's own handle
  (``IsProcessInJob`` + the Job's PID list); limits verified again; only then resumed. The Producer
  keeps the Job handle for the worker's lifetime; ``kill`` terminates the whole Job and closing the
  handle kills anything left.
* **ACLs** -- effective access for exactly the launch's ACL policy roots, computed by the kernel
  access check (``AccessCheck``) against each root's security descriptor with a real logon token
  of the worker account -- never inferred from an ACL listing. Per-launch scratch/bundle/contract
  ACLs are applied by the Producer (their owner) before the worker exists.
* **Egress** -- the worker identity has no direct egress: a Windows Defender Firewall (WFP) rule
  scoped to the worker SID blocks every outbound protocol to every remote address, IPv4 and IPv6.
  The rule and all firewall profiles are read back per launch and compared with the provisioned
  firewall policy digest; the owner's containment qualification report (live probes run *as* the
  worker: IPv4/IPv6/DNS direct paths fail) must be the manifest-bound
  ``os_containment.verification_evidence_sha256``. The only allow path is the per-launch
  ``provider_egress_gateway`` named pipe (not TCP, not a proxy).

This backend enforces; it never trusts a declaration. Everything it reports is re-validated by
``provider_os_enforcement.issue_attestation`` against the launch and the approved manifest.
Residual limits (recorded, not hidden): Windows resolves names in the DNS Client service, so the
worker identity's firewall block stops direct DNS but not queries handed to that service (the
worker's in-process containment refuses every resolution; the gateway path needs none); Windows
Firewall does not filter loopback, so the probe reports loopback reachability separately.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import provider_build_manifest as build_manifest
import provider_egress_gateway as gateway_module

BACKEND_ID = "stocklookup-windows-os-enforcement"
BACKEND_CONTRACT_VERSION = build_manifest.OS_ENFORCEMENT_BACKEND_CONTRACT_VERSION
HOST_RECORD_CONTRACT_VERSION = "provider_windows_host_provisioning/v1"
QUALIFICATION_REPORT_CONTRACT_VERSION = "provider_windows_containment_qualification/v1"
FIREWALL_POLICY_CONTRACT_VERSION = "provider_windows_firewall_policy/v1"

RUNTIME_ROOT = r"C:\ProgramData\StockLookup\provider-runtime"
HOST_RECORD_PATH = os.path.join(RUNTIME_ROOT, "host", "provisioning_record.json")
SUBTREES = {"host": "host", "runtime": "runtime", "state": "state", "scratch": "scratch",
            "ledger": "gateway-ledger", "evidence": "evidence"}
WORKER_ACCOUNT_NAME = "StockLookupProvider"
FIREWALL_RULE_NAME = "StockLookup-ProviderWorker-DenyAllOutbound"
FIREWALL_GROUP = "StockLookup Provider Runtime"
DPAPI_ENTROPY = b"StockLookupProviderWorkerLogon/v1"
CREDENTIAL_BLOB_NAME = "worker-logon.dpapi"

EGRESS_MECHANISM = "WINDOWS_FILTERING_PLATFORM_DEFAULT_DENY"
EGRESS_MECHANISM_DETAIL = "DEFENDER_FIREWALL_WORKER_SID_OUTBOUND_BLOCK_ALL_PROTOCOLS_IPV4_IPV6"
PROCESS_CONTROL_MECHANISM = build_manifest.PROCESS_CONTROL_BY_PLATFORM["win32"]

# Job limit flags.
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
REQUIRED_JOB_FLAGS = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION

# File access rights (effective-access classification).
FILE_READ_DATA = 0x0001
FILE_WRITE_DATA = 0x0002
FILE_APPEND_DATA = 0x0004
FILE_WRITE_EA = 0x0010
FILE_EXECUTE = 0x0020
FILE_DELETE_CHILD = 0x0040
FILE_WRITE_ATTRIBUTES = 0x0100
DELETE = 0x00010000
WRITE_DAC = 0x00040000
WRITE_OWNER = 0x00080000
WRITE_BITS = (FILE_WRITE_DATA | FILE_APPEND_DATA | FILE_WRITE_EA | FILE_WRITE_ATTRIBUTES | FILE_DELETE_CHILD
              | DELETE | WRITE_DAC | WRITE_OWNER)
FILE_GENERIC_READ_EXECUTE = 0x001200A9
# provider_os_enforcement's access-class vocabulary (kept literal: that module imports this one lazily).
ACCESS_READ_EXECUTE, ACCESS_READ_WRITE, ACCESS_NONE = "READ_EXECUTE", "READ_WRITE", "NO_ACCESS"
FILE_MODIFY = 0x001301BF

R_HOST_NOT_PROVISIONED = "PROVIDER_WINDOWS_HOST_NOT_PROVISIONED"
R_HOST_RECORD_INVALID = "PROVIDER_WINDOWS_HOST_RECORD_INVALID"
R_IDENTITY_MISMATCH = "PROVIDER_WINDOWS_WORKER_IDENTITY_MISMATCH"
R_ACCOUNT_UNRESOLVED = "PROVIDER_WINDOWS_WORKER_ACCOUNT_UNRESOLVED"
R_CREDENTIAL_UNAVAILABLE = "PROVIDER_WINDOWS_WORKER_LOGON_SECRET_UNAVAILABLE"
R_FIREWALL_POLICY_MISMATCH = "PROVIDER_WINDOWS_FIREWALL_POLICY_MISMATCH"
R_QUALIFICATION_EVIDENCE_INVALID = "PROVIDER_WINDOWS_CONTAINMENT_QUALIFICATION_EVIDENCE_INVALID"
R_GATEWAY_IDENTITY_MISMATCH = "PROVIDER_WINDOWS_GATEWAY_IDENTITY_MISMATCH"
R_ROOT_OUTSIDE_RUNTIME = "PROVIDER_WINDOWS_ROOT_OUTSIDE_PROVIDER_RUNTIME"
R_ACL_EFFECTIVE_ACCESS = "PROVIDER_WINDOWS_ACL_EFFECTIVE_ACCESS_MISMATCH"
R_JOB_FAILED = "PROVIDER_WINDOWS_JOB_CONTROL_FAILED"
R_SPAWN_FAILED = "PROVIDER_WINDOWS_CONTAINED_SPAWN_FAILED"
R_NOT_THIS_BACKEND = "PROVIDER_WINDOWS_PROCESS_NOT_SPAWNED_BY_THIS_BACKEND"

_SID_RE = re.compile(r"^S-1-[0-9]+(?:-[0-9]+){1,14}$")


class WindowsContainmentError(OSError):
    """A containment step failed; nothing about the launch is trusted. Carries a reason code."""

    def __init__(self, reason_code: str, detail: Mapping[str, Any] | None = None):
        self.reason_code = reason_code
        self.detail = dict(detail or {})
        super().__init__(f"{reason_code}:{json.dumps(self.detail, sort_keys=True, default=str)[:400]}")


def _utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(path: Any) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _within(path: Any, root: Any) -> bool:
    candidate, base = _norm(path), _norm(root)
    return candidate == base or candidate.startswith(base.rstrip("\\/") + os.sep)


# ---------------------------------------------------------------------------------------------
# Policy identities (platform-neutral: the provisioning script and tests compute the same digests).
# ---------------------------------------------------------------------------------------------


def firewall_policy(worker_sid: str) -> dict[str, Any]:
    """The exact Defender Firewall rule the worker identity is contained by."""
    return {
        "contract_version": FIREWALL_POLICY_CONTRACT_VERSION, "rule_name": FIREWALL_RULE_NAME, "group": FIREWALL_GROUP,
        "direction": "Outbound", "action": "Block", "profile": "Any", "protocol": "Any", "remote_address": ["Any"],
        "local_address": ["Any"], "program": "Any", "local_user_sddl": f"D:(A;;CC;;;{worker_sid})", "enabled": "True",
    }


def firewall_policy_sha256(worker_sid: str) -> str:
    return build_manifest.canonical_sha256(firewall_policy(worker_sid))


def firewall_violations(observed: Mapping[str, Any], worker_sid: str) -> list[dict[str, Any]]:
    """Compare a read-back rule + profiles with the provisioned policy. Empty = enforced."""
    policy = firewall_policy(worker_sid)
    failures = []
    rule = observed.get("rule") if isinstance(observed.get("rule"), Mapping) else {}
    for key in ("direction", "action", "profile", "protocol", "program", "enabled"):
        if str(rule.get(key)) != str(policy[key]):
            failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": f"rule.{key}", "observed": rule.get(key)})
    for key in ("remote_address", "local_address"):
        if [str(item) for item in rule.get(key) or []] != policy[key]:
            failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": f"rule.{key}", "observed": rule.get(key)})
    if str(rule.get("local_user") or "") != policy["local_user_sddl"]:
        failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": "rule.local_user", "observed": rule.get("local_user")})
    if str(rule.get("primary_status") or "") != "OK":
        failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": "rule.primary_status", "observed": rule.get("primary_status")})
    if str(rule.get("name")) != FIREWALL_RULE_NAME:
        failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": "rule.name"})
    if sorted(str(item) for item in observed.get("group_rules") or []) != [FIREWALL_RULE_NAME]:
        failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": "group_rules", "observed": observed.get("group_rules")})
    profiles = {str(item.get("name")): item for item in observed.get("profiles") or [] if isinstance(item, Mapping)}
    for name in ("Domain", "Private", "Public"):
        item = profiles.get(name) or {}
        if str(item.get("enabled")) != "True":
            failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": f"profiles.{name}.enabled", "observed": item.get("enabled")})
        if str(item.get("allow_local_firewall_rules")) == "False":
            failures.append({"code": R_FIREWALL_POLICY_MISMATCH, "field": f"profiles.{name}.allow_local_firewall_rules"})
    return failures


def classify_access(granted: int) -> str:
    """Effective-access class of a kernel-granted mask (MAXIMUM_ALLOWED access check)."""
    if not granted & (FILE_READ_DATA | FILE_WRITE_DATA | FILE_APPEND_DATA | DELETE | WRITE_DAC | WRITE_OWNER):
        return ACCESS_NONE
    readable = bool(granted & FILE_READ_DATA)
    if readable and granted & FILE_EXECUTE and not granted & WRITE_BITS:
        return ACCESS_READ_EXECUTE
    if readable and granted & FILE_WRITE_DATA and granted & FILE_APPEND_DATA and not granted & (WRITE_DAC | WRITE_OWNER):
        return ACCESS_READ_WRITE
    return f"PARTIAL:0x{granted:08x}"


def per_launch_sddl(owner_sid: str, worker_sid: str, *, worker_rights: int, inherit: bool = True) -> str:
    """Protected DACL for a per-launch path: SYSTEM, Administrators and the Producer identity full;
    the worker exactly ``worker_rights``."""
    flags = "OICI" if inherit else ""
    return (f"D:P(A;{flags};FA;;;SY)(A;{flags};FA;;;BA)(A;{flags};FA;;;{owner_sid})"
            f"(A;{flags};0x{worker_rights:08x};;;{worker_sid})")


# ---------------------------------------------------------------------------------------------
# Host provisioning record.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class HostRecord:
    worker_account: str
    worker_sid: str
    runtime_root: str
    firewall_policy_sha256: str
    credential_blob: str
    denied_roots_provisioned: tuple[str, ...]
    raw: Mapping[str, Any]

    def subtree(self, name: str) -> str:
        return os.path.join(self.runtime_root, SUBTREES[name])


def host_record_violations(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return [{"code": R_HOST_RECORD_INVALID, "error": "not an object"}]
    failures = []
    if payload.get("contract_version") != HOST_RECORD_CONTRACT_VERSION:
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "contract_version"})
    if payload.get("backend_id") != BACKEND_ID:
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "backend_id"})
    if payload.get("worker_account") != WORKER_ACCOUNT_NAME:
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "worker_account"})
    sid = payload.get("worker_sid")
    if not isinstance(sid, str) or not _SID_RE.match(sid) or build_manifest.restricted_identity_problem(sid):
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "worker_sid"})
    elif payload.get("firewall_policy_sha256") != firewall_policy_sha256(sid):
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "firewall_policy_sha256"})
    if _norm(payload.get("runtime_root") or "") != _norm(RUNTIME_ROOT):
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "runtime_root"})
    blob = payload.get("credential_blob")
    if not isinstance(blob, str) or _norm(blob) != _norm(os.path.join(RUNTIME_ROOT, SUBTREES["host"], CREDENTIAL_BLOB_NAME)):
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "credential_blob"})
    if not isinstance(payload.get("denied_roots_provisioned"), list):
        failures.append({"code": R_HOST_RECORD_INVALID, "field": "denied_roots_provisioned"})
    return failures


def load_host_record(path: str | None = None) -> HostRecord | None:
    """The provisioned host record, or ``None`` when this host is not provisioned (absent file).
    A present but invalid record raises: a half-provisioned host never reads as unprovisioned."""
    record_path = path or HOST_RECORD_PATH
    try:
        payload = json.loads(Path(record_path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise WindowsContainmentError(R_HOST_RECORD_INVALID, {"error": type(exc).__name__}) from None
    failures = host_record_violations(payload)
    if failures:
        raise WindowsContainmentError(failures[0]["code"], {"failures": failures})
    return HostRecord(worker_account=payload["worker_account"], worker_sid=payload["worker_sid"],
                      runtime_root=payload["runtime_root"], firewall_policy_sha256=payload["firewall_policy_sha256"],
                      credential_blob=payload["credential_blob"],
                      denied_roots_provisioned=tuple(payload["denied_roots_provisioned"]), raw=dict(payload))


def qualification_report_violations(report: Any, record: HostRecord) -> list[dict[str, Any]]:
    """The owner containment qualification report a launch relies on for the live-probe facts."""
    if not isinstance(report, Mapping):
        return [{"code": R_QUALIFICATION_EVIDENCE_INVALID, "error": "not an object"}]
    failures = []
    if report.get("contract_version") != QUALIFICATION_REPORT_CONTRACT_VERSION:
        failures.append({"code": R_QUALIFICATION_EVIDENCE_INVALID, "field": "contract_version"})
    if report.get("status") != "PASS":
        failures.append({"code": R_QUALIFICATION_EVIDENCE_INVALID, "field": "status", "observed": report.get("status")})
    if report.get("worker_sid") != record.worker_sid:
        failures.append({"code": R_QUALIFICATION_EVIDENCE_INVALID, "field": "worker_sid"})
    if report.get("firewall_policy_sha256") != record.firewall_policy_sha256:
        failures.append({"code": R_QUALIFICATION_EVIDENCE_INVALID, "field": "firewall_policy_sha256"})
    if report.get("backend_id") != BACKEND_ID:
        failures.append({"code": R_QUALIFICATION_EVIDENCE_INVALID, "field": "backend_id"})
    required = ("DIRECT_IPV4_EGRESS_BLOCKED", "DIRECT_IPV6_EGRESS_BLOCKED", "DIRECT_DNS_BLOCKED")
    results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    for key in required:
        if (results.get(key) or {}).get("outcome") != "PASS":
            failures.append({"code": R_QUALIFICATION_EVIDENCE_INVALID, "field": f"results.{key}"})
    return failures


def find_qualification_report(record: HostRecord, sha256: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The retained qualification report whose file SHA-256 is ``sha256`` (the manifest-bound
    ``os_containment.verification_evidence_sha256``)."""
    if not build_manifest._is_sha256(sha256):
        return None, [{"code": R_QUALIFICATION_EVIDENCE_INVALID, "error": "no bound evidence digest"}]
    evidence_dir = Path(record.subtree("evidence"))
    try:
        candidates = sorted(evidence_dir.glob("containment_qualification_*.json"))
    except OSError:
        candidates = []
    for path in candidates:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if hashlib.sha256(data).hexdigest() == sha256:
            try:
                report = json.loads(data.decode("utf-8"))
            except ValueError:
                return None, [{"code": R_QUALIFICATION_EVIDENCE_INVALID, "error": "malformed"}]
            return report, qualification_report_violations(report, record)
    return None, [{"code": R_QUALIFICATION_EVIDENCE_INVALID, "error": "bound evidence digest not retained"}]


# ---------------------------------------------------------------------------------------------
# Win32 layer (ctypes; loaded lazily so the module imports on every platform).
# ---------------------------------------------------------------------------------------------


class _Win32:
    """Typed bindings for exactly the Win32 calls this backend makes."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise WindowsContainmentError(build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE, {"platform": sys.platform})
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        self.k32, self.adv, self.ntdll, self.crypt = k32, adv, ntdll, crypt
        H, D, B, P = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.c_void_p

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [("cb", D), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                        ("lpTitle", wintypes.LPWSTR), ("dwX", D), ("dwY", D), ("dwXSize", D), ("dwYSize", D),
                        ("dwXCountChars", D), ("dwYCountChars", D), ("dwFillAttribute", D), ("dwFlags", D),
                        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", P),
                        ("hStdInput", H), ("hStdOutput", H), ("hStdError", H)]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [("hProcess", H), ("hThread", H), ("dwProcessId", D), ("dwThreadId", D)]

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("nLength", D), ("lpSecurityDescriptor", P), ("bInheritHandle", B)]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", D), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", D),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", D), ("SchedulingClass", D)]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                                                              "OtherOperationCount", "ReadTransferCount",
                                                              "WriteTransferCount", "OtherTransferCount")]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        class BASIC_ACCOUNTING(ctypes.Structure):
            _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                        ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                        ("TotalPageFaultCount", D), ("TotalProcesses", D), ("ActiveProcesses", D),
                        ("TotalTerminatedProcesses", D)]

        class GENERIC_MAPPING(ctypes.Structure):
            _fields_ = [("GenericRead", D), ("GenericWrite", D), ("GenericExecute", D), ("GenericAll", D)]

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", D), ("pbData", ctypes.POINTER(ctypes.c_char))]

        class UNICODE_STRING(ctypes.Structure):
            _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]

        self.STARTUPINFOW, self.PROCESS_INFORMATION, self.SECURITY_ATTRIBUTES = STARTUPINFOW, PROCESS_INFORMATION, SECURITY_ATTRIBUTES
        self.EXTENDED_LIMIT, self.BASIC_ACCOUNTING, self.GENERIC_MAPPING = EXTENDED_LIMIT, BASIC_ACCOUNTING, GENERIC_MAPPING
        self.DATA_BLOB, self.UNICODE_STRING = DATA_BLOB, UNICODE_STRING

        def bind(dll, name, restype, argtypes):
            function = getattr(dll, name)
            function.restype, function.argtypes = restype, argtypes
            return function

        self.CreateJobObjectW = bind(k32, "CreateJobObjectW", H, [P, wintypes.LPCWSTR])
        self.SetInformationJobObject = bind(k32, "SetInformationJobObject", B, [H, ctypes.c_int, P, D])
        self.QueryInformationJobObject = bind(k32, "QueryInformationJobObject", B, [H, ctypes.c_int, P, D, ctypes.POINTER(D)])
        self.AssignProcessToJobObject = bind(k32, "AssignProcessToJobObject", B, [H, H])
        self.IsProcessInJob = bind(k32, "IsProcessInJob", B, [H, H, ctypes.POINTER(B)])
        self.TerminateJobObject = bind(k32, "TerminateJobObject", B, [H, wintypes.UINT])
        self.TerminateProcess = bind(k32, "TerminateProcess", B, [H, wintypes.UINT])
        self.ResumeThread = bind(k32, "ResumeThread", D, [H])
        self.CreateProcessW = bind(k32, "CreateProcessW", B, [wintypes.LPCWSTR, wintypes.LPWSTR, P, P, B, D, P,
                                                             wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW),
                                                             ctypes.POINTER(PROCESS_INFORMATION)])
        self.CreateProcessWithLogonW = bind(adv, "CreateProcessWithLogonW", B, [
            wintypes.LPCWSTR, wintypes.LPCWSTR, P, D, wintypes.LPCWSTR, wintypes.LPWSTR, D, P, wintypes.LPCWSTR,
            ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION)])
        self.CreatePipe = bind(k32, "CreatePipe", B, [ctypes.POINTER(H), ctypes.POINTER(H), ctypes.POINTER(SECURITY_ATTRIBUTES), D])
        self.SetHandleInformation = bind(k32, "SetHandleInformation", B, [H, D, D])
        self.WaitForSingleObject = bind(k32, "WaitForSingleObject", D, [H, D])
        self.GetExitCodeProcess = bind(k32, "GetExitCodeProcess", B, [H, ctypes.POINTER(D)])
        self.GetProcessTimes = bind(k32, "GetProcessTimes", B, [H] + [ctypes.POINTER(ctypes.c_uint64)] * 4)
        self.CloseHandle = bind(k32, "CloseHandle", B, [H])
        self.LocalFree = bind(k32, "LocalFree", P, [P])
        self.GetCurrentProcess = bind(k32, "GetCurrentProcess", H, [])
        self.OpenProcessToken = bind(adv, "OpenProcessToken", B, [H, D, ctypes.POINTER(H)])
        self.GetTokenInformation = bind(adv, "GetTokenInformation", B, [H, ctypes.c_int, P, D, ctypes.POINTER(D)])
        self.ConvertSidToStringSidW = bind(adv, "ConvertSidToStringSidW", B, [P, ctypes.POINTER(wintypes.LPWSTR)])
        self.ConvertStringSidToSidW = bind(adv, "ConvertStringSidToSidW", B, [wintypes.LPCWSTR, ctypes.POINTER(P)])
        self.LookupAccountSidW = bind(adv, "LookupAccountSidW", B, [wintypes.LPCWSTR, P, wintypes.LPWSTR, ctypes.POINTER(D),
                                                                   wintypes.LPWSTR, ctypes.POINTER(D), ctypes.POINTER(D)])
        self.GetSecurityInfo = bind(adv, "GetSecurityInfo", D, [H, ctypes.c_int, D, ctypes.POINTER(P), ctypes.POINTER(P),
                                                               ctypes.POINTER(P), ctypes.POINTER(P), ctypes.POINTER(P)])
        self.GetFileSecurityW = bind(adv, "GetFileSecurityW", B, [wintypes.LPCWSTR, D, P, D, ctypes.POINTER(D)])
        self.ConvertStringSecurityDescriptorToSecurityDescriptorW = bind(
            adv, "ConvertStringSecurityDescriptorToSecurityDescriptorW", B, [wintypes.LPCWSTR, D, ctypes.POINTER(P), ctypes.POINTER(D)])
        self.GetSecurityDescriptorDacl = bind(adv, "GetSecurityDescriptorDacl", B, [P, ctypes.POINTER(B), ctypes.POINTER(P), ctypes.POINTER(B)])
        self.SetNamedSecurityInfoW = bind(adv, "SetNamedSecurityInfoW", D, [wintypes.LPWSTR, ctypes.c_int, D, P, P, P, P])
        self.LogonUserW = bind(adv, "LogonUserW", B, [wintypes.LPCWSTR, wintypes.LPCWSTR, P, D, D, ctypes.POINTER(H)])
        self.DuplicateToken = bind(adv, "DuplicateToken", B, [H, ctypes.c_int, ctypes.POINTER(H)])
        self.AccessCheck = bind(adv, "AccessCheck", B, [P, H, D, ctypes.POINTER(GENERIC_MAPPING), P, ctypes.POINTER(D),
                                                        ctypes.POINTER(D), ctypes.POINTER(B)])
        self.CryptUnprotectData = bind(crypt, "CryptUnprotectData", B, [ctypes.POINTER(DATA_BLOB), P, ctypes.POINTER(DATA_BLOB),
                                                                         P, P, D, ctypes.POINTER(DATA_BLOB)])
        self.NtQueryObject = bind(ntdll, "NtQueryObject", ctypes.c_long, [H, ctypes.c_int, P, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)])

    def error(self, where: str) -> WindowsContainmentError:
        return WindowsContainmentError(R_JOB_FAILED, {"call": where, "win32_error": self.ctypes.get_last_error()})

    # -- SIDs ---------------------------------------------------------------------------------

    def sid_string(self, sid_pointer: Any) -> str | None:
        text = self.wintypes.LPWSTR()
        if not self.ConvertSidToStringSidW(sid_pointer, self.ctypes.byref(text)):
            return None
        try:
            return text.value
        finally:
            self.LocalFree(text)

    def account_name(self, sid: str) -> str | None:
        ctypes, wintypes = self.ctypes, self.wintypes
        pointer = ctypes.c_void_p()
        if not self.ConvertStringSidToSidW(sid, ctypes.byref(pointer)):
            return None
        try:
            name, domain = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
            name_len, domain_len, use = wintypes.DWORD(256), wintypes.DWORD(256), wintypes.DWORD()
            if not self.LookupAccountSidW(None, pointer, name, ctypes.byref(name_len), domain, ctypes.byref(domain_len),
                                          ctypes.byref(use)):
                return None
            return name.value
        finally:
            self.LocalFree(pointer)

    def token_user_sid(self, token: Any) -> str | None:
        ctypes, wintypes = self.ctypes, self.wintypes
        size = wintypes.DWORD()
        self.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not size.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if not self.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            return None
        return self.sid_string(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])

    def process_identity(self, process: Any) -> list[dict[str, Any]]:
        """User SID of a process we hold a handle to: token query (when the token DACL allows the
        Producer) and the process object's owner (always readable with our full handle)."""
        ctypes, wintypes = self.ctypes, self.wintypes
        readbacks = []
        token = wintypes.HANDLE()
        if self.OpenProcessToken(process, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            try:
                readbacks.append({"source": "OS_TOKEN_QUERY", "sid": self.token_user_sid(token)})
            finally:
                self.CloseHandle(token)
        else:
            readbacks.append({"source": "OS_TOKEN_QUERY", "sid": None, "win32_error": ctypes.get_last_error()})
        owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
        status = self.GetSecurityInfo(process, 6, 0x1, ctypes.byref(owner), None, None, None, ctypes.byref(descriptor))
        if status == 0:
            try:
                readbacks.append({"source": "OS_PROCESS_QUERY", "sid": self.sid_string(owner)})
            finally:
                self.LocalFree(descriptor)
        else:
            readbacks.append({"source": "OS_PROCESS_QUERY", "sid": None, "win32_error": int(status)})
        return readbacks

    def self_identification_token(self) -> Any:
        """An identification-level duplicate of this process's own token (diagnostics/tests)."""
        ctypes, wintypes = self.ctypes, self.wintypes
        token, duplicate = wintypes.HANDLE(), wintypes.HANDLE()
        if not self.OpenProcessToken(self.GetCurrentProcess(), 0x0008 | 0x0002, ctypes.byref(token)):
            raise self.error("OpenProcessToken(self)")
        try:
            if not self.DuplicateToken(token, 1, ctypes.byref(duplicate)):
                raise self.error("DuplicateToken(self)")
            return duplicate
        finally:
            self.CloseHandle(token)

    def current_sid(self) -> str:
        ctypes, wintypes = self.ctypes, self.wintypes
        token = wintypes.HANDLE()
        if not self.OpenProcessToken(self.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise self.error("OpenProcessToken(self)")
        try:
            sid = self.token_user_sid(token)
        finally:
            self.CloseHandle(token)
        if not sid:
            raise self.error("GetTokenInformation(self)")
        return sid

    # -- security descriptors -----------------------------------------------------------------

    def set_path_dacl(self, path: str, sddl: str) -> None:
        """Apply a protected DACL from SDDL (inheritable ACEs propagate to existing children)."""
        ctypes, wintypes = self.ctypes, self.wintypes
        descriptor = ctypes.c_void_p()
        if not self.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise self.error("ConvertStringSecurityDescriptorToSecurityDescriptorW")
        try:
            present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ctypes.c_void_p()
            if not self.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
                raise self.error("GetSecurityDescriptorDacl")
            # SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION
            status = self.SetNamedSecurityInfoW(ctypes.create_unicode_buffer(path), 1, 0x00000004 | 0x80000000,
                                                None, None, dacl, None)
            if status != 0:
                raise WindowsContainmentError(R_ACL_EFFECTIVE_ACCESS, {"call": "SetNamedSecurityInfoW", "path": path,
                                                                       "win32_error": int(status)})
        finally:
            self.LocalFree(descriptor)

    def effective_access(self, path: str, token: Any) -> int:
        """Kernel access check (MAXIMUM_ALLOWED) of ``token`` against the path's descriptor."""
        ctypes, wintypes = self.ctypes, self.wintypes
        needed = wintypes.DWORD()
        info = 0x1 | 0x2 | 0x4  # OWNER | GROUP | DACL
        self.GetFileSecurityW(path, info, None, 0, ctypes.byref(needed))
        if not needed.value:
            raise WindowsContainmentError(R_ACL_EFFECTIVE_ACCESS, {"call": "GetFileSecurityW", "path": path,
                                                                   "win32_error": ctypes.get_last_error()})
        descriptor = ctypes.create_string_buffer(needed.value)
        if not self.GetFileSecurityW(path, info, descriptor, needed, ctypes.byref(needed)):
            raise WindowsContainmentError(R_ACL_EFFECTIVE_ACCESS, {"call": "GetFileSecurityW", "path": path,
                                                                   "win32_error": ctypes.get_last_error()})
        mapping = self.GENERIC_MAPPING(0x00120089, 0x00120116, 0x001200A0, 0x001F01FF)
        privileges = ctypes.create_string_buffer(256)
        privileges_len, granted, status = wintypes.DWORD(256), wintypes.DWORD(), wintypes.BOOL()
        if not self.AccessCheck(descriptor, token, 0x02000000, ctypes.byref(mapping), privileges,
                                ctypes.byref(privileges_len), ctypes.byref(granted), ctypes.byref(status)):
            raise WindowsContainmentError(R_ACL_EFFECTIVE_ACCESS, {"call": "AccessCheck", "path": path,
                                                                   "win32_error": ctypes.get_last_error()})
        return int(granted.value) if status.value else 0

    # -- logon / DPAPI ------------------------------------------------------------------------

    def unprotect(self, blob: bytes) -> Any:
        """DPAPI (current user) decrypt into a ctypes unicode buffer the caller must wipe."""
        ctypes = self.ctypes
        source = ctypes.create_string_buffer(blob, len(blob))
        entropy_buffer = ctypes.create_string_buffer(DPAPI_ENTROPY, len(DPAPI_ENTROPY))
        data_in = self.DATA_BLOB(len(blob), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
        entropy = self.DATA_BLOB(len(DPAPI_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_char)))
        data_out = self.DATA_BLOB()
        if not self.CryptUnprotectData(ctypes.byref(data_in), None, ctypes.byref(entropy), None, None, 0x1,
                                       ctypes.byref(data_out)):
            raise WindowsContainmentError(R_CREDENTIAL_UNAVAILABLE, {"call": "CryptUnprotectData",
                                                                     "win32_error": ctypes.get_last_error()})
        try:
            raw = ctypes.string_at(data_out.pbData, data_out.cbData)
            secret = ctypes.create_unicode_buffer(raw.decode("utf-8"))
            return secret
        finally:
            ctypes.memset(data_out.pbData, 0, data_out.cbData)
            self.LocalFree(data_out.pbData)

    def logon_token(self, account: str, secret: Any) -> Any:
        """An identification-level token of the worker account (for kernel access checks)."""
        ctypes, wintypes = self.ctypes, self.wintypes
        primary = wintypes.HANDLE()
        if not self.LogonUserW(account, ".", ctypes.cast(secret, ctypes.c_void_p), 2, 0, ctypes.byref(primary)):
            raise WindowsContainmentError(R_CREDENTIAL_UNAVAILABLE, {"call": "LogonUserW", "win32_error": ctypes.get_last_error()})
        try:
            duplicate = wintypes.HANDLE()
            if not self.DuplicateToken(primary, 1, ctypes.byref(duplicate)):  # SecurityIdentification
                raise self.error("DuplicateToken")
            return duplicate
        finally:
            self.CloseHandle(primary)

    # -- processes ------------------------------------------------------------------------------

    def creation_time_utc(self, process: Any) -> str | None:
        ctypes = self.ctypes
        times = [ctypes.c_uint64() for _ in range(4)]
        if not self.GetProcessTimes(process, *[ctypes.byref(item) for item in times]):
            return None
        created = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=times[0].value // 10)
        return _utc(created)

    def object_name(self, handle: Any) -> str | None:
        ctypes, wintypes = self.ctypes, self.wintypes
        buffer = ctypes.create_string_buffer(2048)
        returned = wintypes.ULONG()
        if self.NtQueryObject(handle, 1, buffer, len(buffer), ctypes.byref(returned)) != 0:  # ObjectNameInformation
            return None
        name = self.UNICODE_STRING.from_buffer(buffer)
        if not name.Buffer:
            return None
        return ctypes.wstring_at(name.Buffer, name.Length // 2)

    def process_snapshot(self) -> dict[int, dict[str, Any]]:
        """PID -> image name + parent PID for every process (Toolhelp; no process handle needed)."""
        ctypes, wintypes = self.ctypes, self.wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

        snapshot_fn = self.k32.CreateToolhelp32Snapshot
        snapshot_fn.restype, snapshot_fn.argtypes = wintypes.HANDLE, [wintypes.DWORD, wintypes.DWORD]
        first, following = self.k32.Process32FirstW, self.k32.Process32NextW
        first.argtypes = following.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        snapshot = snapshot_fn(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            raise self.error("CreateToolhelp32Snapshot")
        entries: dict[int, dict[str, Any]] = {}
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            more = first(snapshot, ctypes.byref(entry))
            while more:
                entries[int(entry.th32ProcessID)] = {"image": entry.szExeFile, "ppid": int(entry.th32ParentProcessID)}
                more = following(snapshot, ctypes.byref(entry))
        finally:
            self.CloseHandle(snapshot)
        return entries


_API: _Win32 | None = None
_API_LOCK = threading.Lock()


def win32() -> _Win32:
    global _API
    with _API_LOCK:
        if _API is None:
            _API = _Win32()
        return _API


CONSOLE_HOST_IMAGE = "conhost.exe"


def classify_job_members(pids: Sequence[int], spawned_pid: int, snapshot: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    """Split a Job's PID list into the worker's processes and the console hosts Windows attaches to
    a console process's Job. The interpreter is the spawned process itself, or (Windows venv
    redirector) its one python child. Any other member makes ``interpreter_pid`` ``None``."""
    members = [{"pid": int(pid), **dict(snapshot.get(int(pid)) or {"image": None, "ppid": None})} for pid in pids]
    member_pids = {item["pid"] for item in members}
    console = [item["pid"] for item in members if str(item.get("image") or "").lower() == CONSOLE_HOST_IMAGE
               and item.get("ppid") in member_pids]
    workers = sorted(member_pids - set(console))
    interpreter = None
    if workers == [spawned_pid]:
        interpreter = spawned_pid
    elif len(workers) == 2 and spawned_pid in workers:
        other = next(pid for pid in workers if pid != spawned_pid)
        entry = next(item for item in members if item["pid"] == other)
        if entry.get("ppid") == spawned_pid and str(entry.get("image") or "").lower() == "python.exe":
            interpreter = other
    return {"members": members, "console_host_pids": sorted(console), "worker_pids": workers, "interpreter_pid": interpreter}


def local_job_name(kernel_name: str | None) -> str | None:
    """``\\Sessions\\<n>\\BaseNamedObjects\\X`` -> ``Local\\X`` (the name the Job was created as)."""
    if not kernel_name:
        return None
    match = re.fullmatch(r"\\Sessions\\[0-9]+\\BaseNamedObjects\\(.+)", kernel_name)
    if match:
        return "Local\\" + match.group(1)
    match = re.fullmatch(r"\\BaseNamedObjects\\(.+)", kernel_name)
    return ("Local\\" + match.group(1)) if match else None


# ---------------------------------------------------------------------------------------------
# Job object.
# ---------------------------------------------------------------------------------------------


class WindowsJob:
    """One per-launch Job. The creator keeps the only handle; closing it kills every member."""

    def __init__(self, api: _Win32, handle: Any, name: str, active_process_limit: int):
        self.api, self.handle, self.name, self.active_process_limit = api, handle, name, active_process_limit
        self._closed = False

    @classmethod
    def create(cls, name: str, *, owner_sid: str, active_process_limit: int) -> "WindowsJob":
        api = win32()
        ctypes = api.ctypes
        if not isinstance(active_process_limit, int) or isinstance(active_process_limit, bool) or active_process_limit < 1:
            raise WindowsContainmentError(R_JOB_FAILED, {"error": "active process limit"})
        descriptor = ctypes.c_void_p()
        if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"D:P(A;;GA;;;SY)(A;;GA;;;{owner_sid})", 1, ctypes.byref(descriptor), None):
            raise api.error("ConvertStringSecurityDescriptorToSecurityDescriptorW(job)")
        try:
            attributes = api.SECURITY_ATTRIBUTES(ctypes.sizeof(api.SECURITY_ATTRIBUTES), descriptor, False)
            handle = api.CreateJobObjectW(ctypes.byref(attributes), name)
            error = ctypes.get_last_error()
        finally:
            api.LocalFree(descriptor)
        if not handle:
            raise WindowsContainmentError(R_JOB_FAILED, {"call": "CreateJobObjectW", "win32_error": error})
        if error == 183:  # ERROR_ALREADY_EXISTS: someone else's Job of this name is never ours
            api.CloseHandle(handle)
            raise WindowsContainmentError(R_JOB_FAILED, {"call": "CreateJobObjectW", "error": "job name already exists"})
        job = cls(api, handle, name, active_process_limit)
        limits = api.EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = REQUIRED_JOB_FLAGS
        limits.BasicLimitInformation.ActiveProcessLimit = active_process_limit
        if not api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            job.close()
            raise api.error("SetInformationJobObject")
        return job

    def limits(self) -> dict[str, Any]:
        api, ctypes = self.api, self.api.ctypes
        info = api.EXTENDED_LIMIT()
        if not api.QueryInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info), None):
            raise api.error("QueryInformationJobObject(limits)")
        flags = int(info.BasicLimitInformation.LimitFlags)
        return {"limit_flags": flags, "kill_on_job_close": bool(flags & JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE),
                "breakaway_ok": bool(flags & JOB_OBJECT_LIMIT_BREAKAWAY_OK),
                "silent_breakaway_ok": bool(flags & JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK),
                "die_on_unhandled_exception": bool(flags & JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION),
                "active_process_limit": int(info.BasicLimitInformation.ActiveProcessLimit)
                if flags & JOB_OBJECT_LIMIT_ACTIVE_PROCESS else None}

    def limit_violations(self) -> list[dict[str, Any]]:
        limits = self.limits()
        failures = []
        if not limits["kill_on_job_close"]:
            failures.append({"code": R_JOB_FAILED, "field": "kill_on_job_close"})
        if limits["breakaway_ok"] or limits["silent_breakaway_ok"]:
            failures.append({"code": R_JOB_FAILED, "field": "breakaway"})
        if limits["active_process_limit"] != self.active_process_limit:
            failures.append({"code": R_JOB_FAILED, "field": "active_process_limit"})
        return failures

    def pids(self) -> list[int]:
        api, ctypes = self.api, self.api.ctypes
        capacity = 64
        buffer = ctypes.create_string_buffer(8 + ctypes.sizeof(ctypes.c_size_t) * capacity)
        if not api.QueryInformationJobObject(self.handle, 3, buffer, len(buffer), None):
            raise api.error("QueryInformationJobObject(pids)")
        assigned, listed = ctypes.c_uint32.from_buffer(buffer, 0).value, ctypes.c_uint32.from_buffer(buffer, 4).value
        ids = (ctypes.c_size_t * capacity).from_buffer(buffer, 8)
        if listed != assigned:
            raise WindowsContainmentError(R_JOB_FAILED, {"error": "job process list truncated"})
        return sorted(int(ids[index]) for index in range(listed))

    def accounting(self) -> dict[str, int]:
        api, ctypes = self.api, self.api.ctypes
        info = api.BASIC_ACCOUNTING()
        if not api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise api.error("QueryInformationJobObject(accounting)")
        return {"total_processes": int(info.TotalProcesses), "active_processes": int(info.ActiveProcesses),
                "total_terminated_processes": int(info.TotalTerminatedProcesses)}

    def contains(self, process: Any) -> bool:
        api, ctypes = self.api, self.api.ctypes
        result = api.wintypes.BOOL()
        if not api.IsProcessInJob(process, self.handle, ctypes.byref(result)):
            raise api.error("IsProcessInJob")
        return bool(result.value)

    def assign(self, process: Any) -> None:
        if not self.api.AssignProcessToJobObject(self.handle, process):
            raise self.api.error("AssignProcessToJobObject")

    def kernel_name(self) -> str | None:
        return self.api.object_name(self.handle)

    def terminate(self, exit_code: int = 1) -> None:
        if not self._closed:
            self.api.TerminateJobObject(self.handle, exit_code)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.api.CloseHandle(self.handle)


# ---------------------------------------------------------------------------------------------
# Suspended spawn and the Popen-compatible contained process.
# ---------------------------------------------------------------------------------------------


def environment_block(environment: Mapping[str, str]) -> str:
    items = sorted(((str(k), str(v)) for k, v in environment.items()), key=lambda kv: kv[0].upper())
    for key, value in items:
        if "=" in key or "\0" in key or "\0" in value:
            raise WindowsContainmentError(R_SPAWN_FAILED, {"error": "invalid environment entry"})
    return "".join(f"{k}={v}\0" for k, v in items) + "\0"


class _Spawner:
    """Creates a suspended process with redirected standard handles."""

    identity_kind = "ABSTRACT"

    def create(self, api: _Win32, command_line: Any, env_block: Any, cwd: str, startup: Any, info: Any) -> bool:
        raise NotImplementedError


class LogonSpawner(_Spawner):
    """Production: ``CreateProcessWithLogonW`` as the dedicated worker account (no profile load)."""

    identity_kind = "DEDICATED_WORKER_ACCOUNT"

    def __init__(self, account: str, secret_provider: Callable[[], Any]):
        self.account = account
        self._secret_provider = secret_provider

    def create(self, api: _Win32, command_line: Any, env_block: Any, cwd: str, startup: Any, info: Any) -> bool:
        ctypes = api.ctypes
        secret = self._secret_provider()
        try:
            return bool(api.CreateProcessWithLogonW(self.account, ".", ctypes.cast(secret, ctypes.c_void_p), 0, None,
                                                    command_line, 0x00000004 | 0x00000400, env_block, cwd,
                                                    ctypes.byref(startup), ctypes.byref(info)))
        finally:
            ctypes.memset(secret, 0, ctypes.sizeof(secret))


class SameIdentitySpawner(_Spawner):
    """TEST/PROBE HARNESS ONLY: ``CreateProcessW`` under the Producer's own identity. Exercises the
    Job/suspend/assign/verify/pipe machinery without the worker account; never used by the
    production backend (whose identity check would refuse it anyway)."""

    identity_kind = "SAME_IDENTITY_TEST_HARNESS"

    def create(self, api: _Win32, command_line: Any, env_block: Any, cwd: str, startup: Any, info: Any) -> bool:
        ctypes = api.ctypes
        return bool(api.CreateProcessW(None, command_line, None, None, True, 0x00000004 | 0x00000400 | 0x08000000,
                                       env_block, cwd, ctypes.byref(startup), ctypes.byref(info)))


class ContainedWorkerProcess:
    """The subset of ``subprocess.Popen`` the worker client uses, over a Job-contained process.
    ``kill`` terminates the whole Job; the Job handle closes once the process is reaped."""

    def __init__(self, *, api: _Win32, process_handle: Any, pid: int, job: WindowsJob, argv: Sequence[str],
                 stdin_fd: int, stdout_fd: int, stderr_fd: int, launch_id: str | None,
                 on_close: Callable[[], None] | None = None):
        self.api, self._handle, self.pid, self.job, self.args = api, process_handle, pid, job, list(argv)
        self.launch_id = launch_id
        self.returncode: int | None = None
        self.stdin = open(stdin_fd, "w", encoding="utf-8", newline="\n", buffering=1)  # noqa: SIM115
        self.stdout = open(stdout_fd, "r", encoding="utf-8", newline=None)  # noqa: SIM115
        self.stderr = None
        self.stderr_tail = b""
        self._stderr_file = open(stderr_fd, "rb", buffering=0)  # noqa: SIM115
        self._on_close = on_close
        self._finalized = False
        self._lock = threading.Lock()
        self._drain = threading.Thread(target=self._drain_stderr, name="provider-worker-stderr", daemon=True)
        self._drain.start()

    def _drain_stderr(self) -> None:
        try:
            while True:
                chunk = self._stderr_file.read(4096)
                if not chunk:
                    return
                self.stderr_tail = (self.stderr_tail + chunk)[-65536:]
        except (OSError, ValueError):
            return
        finally:
            try:
                self._stderr_file.close()
            except OSError:
                pass

    @property
    def handle(self) -> Any:
        return self._handle

    def _finalize(self) -> None:
        with self._lock:
            if self._finalized:
                return
            self._finalized = True
        self.job.terminate(1)
        self.job.close()
        if self._on_close is not None:
            self._on_close()

    def poll(self) -> int | None:
        if self.returncode is None and self.api.WaitForSingleObject(self._handle, 0) == 0:
            code = self.api.wintypes.DWORD()
            self.api.GetExitCodeProcess(self._handle, self.api.ctypes.byref(code))
            self.returncode = int(code.value)
            self._finalize()
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        milliseconds = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        if self.returncode is None and self.api.WaitForSingleObject(self._handle, milliseconds) != 0:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return int(self.poll() if self.returncode is None else self.returncode)

    def kill(self) -> None:
        """Deterministic revocation: the whole Job, not just the spawned process."""
        self.job.terminate(1)

    terminate = kill


def spawn_suspended_in_job(
    *, spawner: _Spawner, argv: Sequence[str], environment: Mapping[str, str], cwd: str, job: WindowsJob,
    launch_id: str | None, before_resume: Callable[[Any, int], None] | None = None,
    on_close: Callable[[], None] | None = None,
) -> ContainedWorkerProcess:
    """Steps 2-9 of the containment launch: create suspended, assign to ``job``, verify membership
    through ``job``'s own handle and its limits, then resume. Any failure kills the process."""
    import msvcrt

    api = win32()
    ctypes, wintypes = api.ctypes, api.wintypes
    attributes = api.SECURITY_ATTRIBUTES(ctypes.sizeof(api.SECURITY_ATTRIBUTES), None, True)
    pipes = {}
    for name in ("stdin", "stdout", "stderr"):
        read, write = wintypes.HANDLE(), wintypes.HANDLE()
        if not api.CreatePipe(ctypes.byref(read), ctypes.byref(write), ctypes.byref(attributes), 0):
            raise api.error("CreatePipe")
        pipes[name] = (read, write)
    parent_ends = {"stdin": pipes["stdin"][1], "stdout": pipes["stdout"][0], "stderr": pipes["stderr"][0]}
    child_ends = {"stdin": pipes["stdin"][0], "stdout": pipes["stdout"][1], "stderr": pipes["stderr"][1]}
    for handle in parent_ends.values():
        api.SetHandleInformation(handle, 0x1, 0)  # HANDLE_FLAG_INHERIT off for the Producer's ends
    startup = api.STARTUPINFOW()
    startup.cb = ctypes.sizeof(startup)
    startup.dwFlags = 0x00000100 | 0x00000001  # STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
    startup.wShowWindow = 0  # SW_HIDE
    startup.hStdInput, startup.hStdOutput, startup.hStdError = child_ends["stdin"], child_ends["stdout"], child_ends["stderr"]
    info = api.PROCESS_INFORMATION()
    command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(argv)))
    env_block = ctypes.create_unicode_buffer(environment_block(environment))
    try:
        created = spawner.create(api, command_line, env_block, cwd, startup, info)
        error = ctypes.get_last_error()
    except BaseException:
        for handle in (*child_ends.values(), *parent_ends.values()):
            api.CloseHandle(handle)
        raise
    for handle in child_ends.values():
        api.CloseHandle(handle)
    if not created:
        for handle in parent_ends.values():
            api.CloseHandle(handle)
        raise WindowsContainmentError(R_SPAWN_FAILED, {"spawner": spawner.identity_kind, "win32_error": error})
    try:
        job.assign(info.hProcess)
        if not job.contains(info.hProcess):
            raise WindowsContainmentError(R_JOB_FAILED, {"error": "process not in the launch Job after assignment"})
        membership = classify_job_members(job.pids(), int(info.dwProcessId), api.process_snapshot())
        if membership["worker_pids"] != [int(info.dwProcessId)]:
            raise WindowsContainmentError(R_JOB_FAILED, {"error": "launch Job membership is not exactly the spawned process",
                                                         "members": membership["members"]})
        failures = job.limit_violations()
        if failures:
            raise WindowsContainmentError(R_JOB_FAILED, {"failures": failures})
        if before_resume is not None:
            before_resume(info.hProcess, int(info.dwProcessId))
        if api.ResumeThread(info.hThread) == 0xFFFFFFFF:
            raise api.error("ResumeThread")
    except BaseException:
        api.TerminateProcess(info.hProcess, 1)
        api.CloseHandle(info.hThread)
        api.CloseHandle(info.hProcess)
        for handle in parent_ends.values():
            api.CloseHandle(handle)
        raise
    api.CloseHandle(info.hThread)
    fds = {name: msvcrt.open_osfhandle(int(handle.value), os.O_BINARY if hasattr(os, "O_BINARY") else 0)
           for name, handle in parent_ends.items()}
    return ContainedWorkerProcess(api=api, process_handle=info.hProcess, pid=int(info.dwProcessId), job=job, argv=argv,
                                  stdin_fd=fds["stdin"], stdout_fd=fds["stdout"], stderr_fd=fds["stderr"],
                                  launch_id=launch_id, on_close=on_close)


# ---------------------------------------------------------------------------------------------
# The production backend.
# ---------------------------------------------------------------------------------------------


@dataclass
class _LaunchState:
    preflight: dict[str, Any] = field(default_factory=dict)
    acl_section: dict[str, Any] | None = None
    firewall: dict[str, Any] | None = None
    gateway: Any = None
    process: ContainedWorkerProcess | None = None


def query_firewall(worker_sid: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Read the worker rule, its group and every firewall profile back from the active store."""
    script = (
        "$ErrorActionPreference='Stop';"
        f"$r=Get-NetFirewallRule -Name '{FIREWALL_RULE_NAME}' -PolicyStore ActiveStore;"
        "$s=$r|Get-NetFirewallSecurityFilter;$a=$r|Get-NetFirewallAddressFilter;"
        "$p=$r|Get-NetFirewallPortFilter;$x=$r|Get-NetFirewallApplicationFilter;"
        f"$g=@(Get-NetFirewallRule -Group '{FIREWALL_GROUP}' -PolicyStore ActiveStore|ForEach-Object{{$_.Name}});"
        "$f=@(Get-NetFirewallProfile -PolicyStore ActiveStore|ForEach-Object{[pscustomobject]@{name=[string]$_.Name;"
        "enabled=[string]$_.Enabled;allow_local_firewall_rules=[string]$_.AllowLocalFirewallRules}});"
        "[pscustomobject]@{rule=[pscustomobject]@{name=[string]$r.Name;enabled=[string]$r.Enabled;"
        "direction=[string]$r.Direction;action=[string]$r.Action;profile=[string]$r.Profile;"
        "primary_status=[string]$r.PrimaryStatus;local_user=[string]$s.LocalUser;"
        "remote_address=@($a.RemoteAddress|ForEach-Object{[string]$_});local_address=@($a.LocalAddress|ForEach-Object{[string]$_});"
        "protocol=[string]$p.Protocol;program=[string]$x.Program};group_rules=$g;profiles=$f}|ConvertTo-Json -Depth 5 -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": type(exc).__name__, "failures": [{"code": R_FIREWALL_POLICY_MISMATCH, "error": "query failed"}]}
    try:
        observed = json.loads(completed.stdout or "null")
    except ValueError:
        observed = None
    if completed.returncode != 0 or not isinstance(observed, dict):
        return {"error": "rule not readable", "failures": [{"code": R_FIREWALL_POLICY_MISMATCH, "error": "rule absent or unreadable"}]}
    failures = firewall_violations(observed, worker_sid)
    return {"observed": observed, "failures": failures,
            "firewall_policy_sha256": firewall_policy_sha256(worker_sid) if not failures else None}


class WindowsProductionOSBackend:
    """The production ``ProviderOSEnforcementBackend`` for a provisioned Windows host."""

    kind = build_manifest.OS_ENFORCEMENT_PRODUCTION
    backend_id = BACKEND_ID
    contract_version = BACKEND_CONTRACT_VERSION

    def __init__(self, record: HostRecord, *, spawner: _Spawner | None = None,
                 firewall_query: Callable[[str], dict[str, Any]] = query_firewall):
        self.record = record
        self._spawner = spawner
        self._firewall_query = firewall_query
        self._launches: dict[str, _LaunchState] = {}
        self._lock = threading.Lock()

    # -- helpers --------------------------------------------------------------------------------

    def _secret(self) -> Any:
        try:
            blob = Path(self.record.credential_blob).read_bytes()
        except OSError as exc:
            raise WindowsContainmentError(R_CREDENTIAL_UNAVAILABLE, {"error": type(exc).__name__}) from None
        return win32().unprotect(blob)

    def spawner(self) -> _Spawner:
        return self._spawner or LogonSpawner(self.record.worker_account, self._secret)

    def _state(self, launch: build_manifest.ProviderLaunchAuthorization) -> _LaunchState:
        with self._lock:
            return self._launches.setdefault(launch.launch_id, _LaunchState())

    def _require_launch(self, launch: Any) -> None:
        if not isinstance(launch, build_manifest.ProviderLaunchAuthorization) or not launch.issued_by_attestation:
            raise WindowsContainmentError(R_NOT_THIS_BACKEND, {"error": "launch not issued by attestation"})
        if build_manifest.os_enforcement_requirement(launch.manifest, launch.launch_mode) != build_manifest.OS_ENFORCEMENT_PRODUCTION:
            raise WindowsContainmentError(R_NOT_THIS_BACKEND, {"error": "not a production-enforced launch"})
        if sys.platform != "win32":
            raise WindowsContainmentError(build_manifest.R_OS_ENFORCEMENT_UNAVAILABLE, {"platform": sys.platform})

    def static_violations(self, launch: build_manifest.ProviderLaunchAuthorization) -> list[dict[str, Any]]:
        """Launch/manifest/host-record agreement (no OS mutation)."""
        manifest = launch.manifest
        containment = manifest.get("os_containment") or {}
        failures = []
        backend = containment.get("enforcement_backend") or {}
        if backend.get("backend_id") != BACKEND_ID or backend.get("contract_version") != BACKEND_CONTRACT_VERSION:
            failures.append({"code": R_NOT_THIS_BACKEND, "field": "os_containment.enforcement_backend"})
        if containment.get("restricted_identity_sid") != self.record.worker_sid:
            failures.append({"code": R_IDENTITY_MISMATCH, "field": "os_containment.restricted_identity_sid"})
        gateway = (manifest.get("network") or {}).get("egress_gateway") or {}
        wanted = gateway_module.gateway_identity()
        for key in ("gateway_id", "implementation", "transport", "ipc_endpoint", "executable_sha256"):
            if gateway.get(key) != wanted[key]:
                failures.append({"code": R_GATEWAY_IDENTITY_MISMATCH, "field": f"network.egress_gateway.{key}"})
        runtime = manifest.get("runtime") or {}
        for field_name, value in (("runtime.venv_root", runtime.get("venv_root")), ("state_root", launch.state_root),
                                  ("scratch_root", launch.scratch_root), ("interpreter", launch.interpreter)):
            if not value or not _within(value, self.record.runtime_root):
                failures.append({"code": R_ROOT_OUTSIDE_RUNTIME, "field": field_name})
        if not _within(launch.interpreter, runtime.get("venv_root") or "\0"):
            failures.append({"code": R_ROOT_OUTSIDE_RUNTIME, "field": "interpreter", "error": "not inside the venv"})
        return failures

    # -- the three contract phases --------------------------------------------------------------

    def preflight(self, launch: build_manifest.ProviderLaunchAuthorization) -> Mapping[str, Any]:
        import provider_os_enforcement as os_enforcement

        self._require_launch(launch)
        state = self._state(launch)
        if state.preflight:
            return state.preflight
        failures = self.static_violations(launch)
        if failures:
            raise os_enforcement.OSEnforcementUnavailable(failures[0]["code"], {"failures": failures})
        api = win32()
        if api.account_name(self.record.worker_sid) != self.record.worker_account:
            raise os_enforcement.OSEnforcementUnavailable(R_ACCOUNT_UNRESOLVED, {"worker_sid": self.record.worker_sid})
        firewall = self._firewall_query(self.record.worker_sid)
        if firewall.get("failures") or firewall.get("firewall_policy_sha256") != self.record.firewall_policy_sha256:
            raise os_enforcement.OSEnforcementUnavailable(R_FIREWALL_POLICY_MISMATCH, {"failures": firewall.get("failures")})
        report, report_failures = find_qualification_report(
            self.record, (launch.manifest.get("os_containment") or {}).get("verification_evidence_sha256"))
        if report_failures:
            raise os_enforcement.OSEnforcementUnavailable(R_QUALIFICATION_EVIDENCE_INVALID, {"failures": report_failures})
        owner_sid = api.current_sid()
        worker_sid = self.record.worker_sid
        # Per-launch ACLs, applied by the Producer (the paths' owner) before the worker exists.
        api.set_path_dacl(launch.scratch_root, per_launch_sddl(owner_sid, worker_sid, worker_rights=FILE_MODIFY))
        api.set_path_dacl(launch.bundle_root, per_launch_sddl(owner_sid, worker_sid, worker_rights=FILE_GENERIC_READ_EXECUTE))
        api.set_path_dacl(launch.contract_path, per_launch_sddl(owner_sid, worker_sid, worker_rights=FILE_GENERIC_READ_EXECUTE,
                                                                inherit=False))
        state.acl_section = self._effective_acl_section(launch)
        bad = [item for item in state.acl_section["roots"] if not item["effective_access_verified"]]
        if bad or state.acl_section["identity"] != worker_sid:
            raise os_enforcement.OSEnforcementUnavailable(R_ACL_EFFECTIVE_ACCESS, {"roots": bad[:10]})
        state.firewall = {**firewall, "qualification_report_sha256": (launch.manifest.get("os_containment") or {}).get(
            "verification_evidence_sha256"), "qualification_generated_at_utc": (report or {}).get("generated_at_utc")}
        state.preflight = {"backend_id": BACKEND_ID, "launch_id": launch.launch_id, "worker_sid": worker_sid,
                           "owner_sid": owner_sid, "firewall_policy_sha256": firewall.get("firewall_policy_sha256"),
                           "acl_policy_sha256": state.acl_section["policy_sha256"]}
        return state.preflight

    def _effective_acl_section(self, launch: build_manifest.ProviderLaunchAuthorization) -> dict[str, Any]:
        import provider_os_enforcement as os_enforcement

        api = win32()
        policy = os_enforcement.acl_policy(launch)
        secret = self._secret()
        try:
            token = api.logon_token(self.record.worker_account, secret)
        finally:
            api.ctypes.memset(secret, 0, api.ctypes.sizeof(secret))
        try:
            identity = api.token_user_sid(token)
            roots = []
            for item in policy["roots"]:
                try:
                    granted = api.effective_access(item["path"], token)
                    observed = classify_access(granted)
                except WindowsContainmentError as exc:
                    granted, observed = None, f"UNREADABLE:{exc.detail.get('win32_error')}"
                roots.append({"path": item["path"], "access_class": item["access_class"], "observed_access_class": observed,
                              "granted_mask": granted, "effective_access_verified": observed == item["access_class"]})
        finally:
            api.CloseHandle(token)
        return {"source": "OS_ACL_QUERY", "identity": identity, "policy_sha256": build_manifest.canonical_sha256(policy),
                "method": "AccessCheck(MAXIMUM_ALLOWED) with an interactive logon token of the worker account",
                "roots": roots}

    def spawn_contained(self, launch: build_manifest.ProviderLaunchAuthorization) -> ContainedWorkerProcess:
        import provider_os_enforcement as os_enforcement
        import provider_worker_containment as worker_containment

        self.preflight(launch)
        state = self._state(launch)
        if state.process is not None:
            raise WindowsContainmentError(R_SPAWN_FAILED, {"error": "launch already spawned"})
        api = win32()
        manifest = launch.manifest
        containment = manifest.get("os_containment") or {}
        job = WindowsJob.create(build_manifest.expected_job_name(launch.launch_id), owner_sid=state.preflight["owner_sid"],
                                active_process_limit=int(containment["job_active_process_limit"]))
        failures = job.limit_violations()
        if failures:
            job.close()
            raise WindowsContainmentError(R_JOB_FAILED, {"failures": failures})
        policy = worker_containment.EgressPolicy.from_endpoints(manifest["network"]["endpoints"],
                                                                gateway=manifest["network"].get("egress_gateway"))
        ledger_dir = Path(self.record.subtree("ledger"))
        core = gateway_module.GatewayCore(
            launch_id=launch.launch_id, egress_policy=policy,
            egress_policy_sha256=build_manifest.egress_policy_sha256(manifest),
            rate_per_minute=min(int(launch.governor_rpm), build_manifest.OWNER_APPROVED_GOVERNOR_CEILING_RPM),
            denied_telemetry_hosts=[str(item.get("host")) for item in manifest.get("telemetry_disposition") or []
                                    if item.get("layer") == "NETWORK"],
            ledger_path=str(ledger_dir / f"{launch.launch_id}.jsonl"),
        )
        server = gateway_module.NamedPipeGatewayServer(
            core, pipe_name=gateway_module.ipc_endpoint_for(launch.launch_id), owner_sid=state.preflight["owner_sid"],
            worker_sid=self.record.worker_sid, client_pid_allowed=lambda pid: pid in job.pids())
        try:
            server.start()
            binding = Path(launch.scratch_root) / "gateway_binding.json"
            binding.write_bytes(build_manifest.canonical_json_bytes({
                "contract_version": gateway_module.CONTRACT_VERSION, "launch_id": launch.launch_id,
                "ipc_endpoint_instance": server.pipe_name, "server_pid": server.server_pid}))
            api.set_path_dacl(str(binding), per_launch_sddl(state.preflight["owner_sid"], self.record.worker_sid,
                                                            worker_rights=FILE_GENERIC_READ_EXECUTE, inherit=False))
            process = spawn_suspended_in_job(
                spawner=self.spawner(), argv=launch.argv, environment=launch.environment, cwd=launch.cwd, job=job,
                launch_id=launch.launch_id, on_close=server.stop)
        except BaseException:
            server.stop()
            job.terminate(1)
            job.close()
            raise
        state.gateway, state.process = server, process
        return process

    def verify_spawned_process(self, launch: build_manifest.ProviderLaunchAuthorization,
                               process: Any) -> Any:
        import provider_os_enforcement as os_enforcement

        self._require_launch(launch)
        state = self._state(launch)
        if process is not state.process or not isinstance(process, ContainedWorkerProcess):
            raise WindowsContainmentError(R_NOT_THIS_BACKEND, {"error": "process not spawned by this backend for this launch"})
        api = win32()
        job = process.job
        kernel_name = job.kernel_name()
        pids = job.pids()
        limits = job.limits()
        in_job = job.contains(process.handle)
        membership = classify_job_members(pids, process.pid, api.process_snapshot())
        interpreter_pid = membership["interpreter_pid"]
        spawned_identity = api.process_identity(process.handle)
        server: gateway_module.NamedPipeGatewayServer = state.gateway
        handshakes = [item for item in server.accepted_clients if item.get("pid") == interpreter_pid]
        readbacks = [dict(item, pid=process.pid) for item in spawned_identity if item.get("sid")]
        readbacks += [{"source": "OS_TOKEN_QUERY", "via": "NAMED_PIPE_CLIENT_IMPERSONATION", "pid": item["pid"],
                       "sid": item["sid"]} for item in handshakes if item.get("sid")]
        sids = {item["sid"] for item in readbacks}
        value = sids.pop() if len(sids) == 1 else None
        interpreter_observed = any(item.get("pid") == interpreter_pid for item in readbacks)
        identity_source = "OS_TOKEN_QUERY" if any(item["source"] == "OS_TOKEN_QUERY" for item in readbacks) else "OS_PROCESS_QUERY"
        firewall = state.firewall or {}
        gateway_identity = server.identity()
        manifest_gateway = (launch.manifest.get("network") or {}).get("egress_gateway") or {}
        gateway_verified = (gateway_identity["server_is_this_process"]
                            and gateway_identity["executable_sha256"] == manifest_gateway.get("executable_sha256")
                            and gateway_identity["egress_policy_sha256"] == build_manifest.egress_policy_sha256(launch.manifest)
                            and bool(handshakes))
        result = {
            "binding": {"launch_id": launch.launch_id, "manifest_sha256": launch.manifest_sha256,
                        "build_id": launch.manifest.get("build_id"), "policy_decision_id": launch.policy.decision_id,
                        "platform": sys.platform},
            "worker_process": {"spawned_pid": process.pid, "interpreter_pid": interpreter_pid,
                               "creation_time_utc": api.creation_time_utc(process.handle)},
            "restricted_identity": {"source": identity_source, "value": value if interpreter_observed else None,
                                    "readbacks": readbacks},
            "process_control": {
                "mechanism": PROCESS_CONTROL_MECHANISM, "source": "OS_JOB_QUERY",
                "job": {"name": local_job_name(kernel_name), "kernel_name": kernel_name,
                        "membership_verified_with_job_handle": in_job and process.pid in pids,
                        "assigned_pids": pids, "members": membership["members"],
                        "console_host_pids": membership["console_host_pids"], "limits": limits,
                        "accounting": job.accounting()},
            },
            "acl": dict(state.acl_section or {}),
            "egress": {
                "source": "OS_FIREWALL_QUERY", "mechanism": EGRESS_MECHANISM, "mechanism_detail": EGRESS_MECHANISM_DETAIL,
                "policy_sha256": server.core.egress_policy_sha256,
                "telemetry_policy_sha256": build_manifest.telemetry_policy_sha256(launch.manifest),
                "direct_egress_prohibited_verified": not firewall.get("failures") and bool(firewall.get("firewall_policy_sha256")),
                "firewall_policy_sha256": firewall.get("firewall_policy_sha256"),
                "qualification_report_sha256": firewall.get("qualification_report_sha256"),
                "gateway": {**{key: manifest_gateway.get(key) for key in (
                    "gateway_id", "implementation", "transport", "ipc_endpoint", "host", "port")},
                    "executable_sha256": gateway_identity["executable_sha256"],
                    "ipc_endpoint_instance": gateway_identity["ipc_endpoint_instance"],
                    "server_pid": gateway_identity["server_pid"], "rate_per_minute": gateway_identity["rate_per_minute"],
                    "identity_verified": gateway_verified},
            },
        }
        raw = {"job_kernel_name": kernel_name, "job_pids": pids, "job_limits": limits, "spawned_identity": spawned_identity,
               "gateway_accepted_clients": list(server.accepted_clients), "gateway_rejected_clients": list(server.rejected_clients),
               "gateway_identity": gateway_identity, "firewall": firewall.get("observed"), "acl": state.acl_section}
        return os_enforcement.BackendVerification(backend_id=self.backend_id, contract_version=self.contract_version,
                                                  raw_observations=raw, result=result, verified_at_utc=_utc(_now()))


_CONFIGURED: WindowsProductionOSBackend | None = None
_CONFIGURED_LOCK = threading.Lock()


# Disable-only switch: ``disabled`` makes this process treat the host as unprovisioned (the test
# session sets it so the suite is deterministic on a provisioned owner host). It can never enable
# or redirect anything.
DISABLE_ENV = "STOCKLOOKUP_PROVIDER_OS_BACKEND"
DISABLE_VALUE = "disabled"


def configured_backend() -> WindowsProductionOSBackend | None:
    """The production backend when this host is provisioned (Windows + a valid host record);
    ``None`` otherwise. One instance per process, so issuance can compare by identity."""
    global _CONFIGURED
    if sys.platform != "win32" or os.environ.get(DISABLE_ENV, "").strip().lower() == DISABLE_VALUE:
        return None
    with _CONFIGURED_LOCK:
        try:
            record = load_host_record(HOST_RECORD_PATH)
        except WindowsContainmentError:
            return None
        if record is None:
            _CONFIGURED = None
            return None
        if _CONFIGURED is None or _CONFIGURED.record != record:
            _CONFIGURED = WindowsProductionOSBackend(record)
        return _CONFIGURED
