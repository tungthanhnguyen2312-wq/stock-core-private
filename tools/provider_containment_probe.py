"""Containment probe run AS the provider worker identity (WINDOWS_PROVIDER_RUNTIME_OS_CONTAINMENT_AND_ATTESTATION_V1).

Launched only by ``tools/run_provider_os_containment_qualification.py`` through the production
spawn path (dedicated account, suspended, per-launch Job). Standard library only; never imports a
provider package and never contacts a provider. It attempts exactly the accesses the containment
must allow or refuse and reports what the OS answered, as one JSON line on stdout:

* its own token SID and Job membership (read from the OS by the probe itself -- corroborative);
* file reads/writes on the approved roots (must work) and on owner/secret/production roots (must fail);
* direct IPv4 / IPv6 TCP connects and a direct UDP DNS query (must fail with the OS block);
* the system resolver and a loopback TCP connect (recorded as residual observations, not passes);
* the governed named-pipe gateway: HELLO, one allow-listed self-test request, and requests the
  gateway must refuse (unapproved host / method / path / scheme, redirect, non-governed operation);
* process creation with and without breakaway (must fail: active-process limit, no breakaway).

Mode ``block`` only waits on stdin (used to prove KILL_ON_JOB_CLOSE). No test here sends anything
but a fixed DNS query for ``example.com`` and TCP SYNs to well-known public anycast resolvers.
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import struct
import subprocess
import sys
from ctypes import wintypes

WSAEACCES = 10013


def _token_sid() -> str | None:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(k32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        return None
    size = wintypes.DWORD()
    advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
        return None
    text = wintypes.LPWSTR()
    advapi.ConvertSidToStringSidW(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.byref(text))
    return text.value


def _in_job() -> bool | None:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    result = wintypes.BOOL()
    if not k32.IsProcessInJob(k32.GetCurrentProcess(), None, ctypes.byref(result)):
        return None
    return bool(result.value)


def _attempt(action) -> dict:
    try:
        detail = action()
        return {"succeeded": True, "detail": detail}
    except OSError as exc:
        return {"succeeded": False, "error": type(exc).__name__, "errno": exc.errno,
                "winerror": getattr(exc, "winerror", None)}
    except Exception as exc:  # noqa: BLE001 -- every probe outcome is data
        return {"succeeded": False, "error": type(exc).__name__}


def _read(path: str):
    def action():
        if os.path.isdir(path):
            return {"entries": len(os.listdir(path))}
        with open(path, "rb") as handle:
            return {"bytes": len(handle.read(64))}
    return action


def _write_then_delete(directory: str):
    def action():
        target = os.path.join(directory, f"probe-write-{os.getpid()}.tmp")
        with open(target, "wb") as handle:
            handle.write(b"probe")
        os.remove(target)
        return {"written": True}
    return action


def _write_only(directory: str):
    def action():
        target = os.path.join(directory, f"probe-denied-{os.getpid()}.tmp")
        with open(target, "wb") as handle:
            handle.write(b"probe")
        os.remove(target)
        return {"written": True}
    return action


def _tcp(family: int, address: tuple):
    def action():
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(address)
            return {"connected": True}
    return action


def _dns_udp(server: str):
    def action():
        query = struct.pack(">HHHHHH", 0x5354, 0x0100, 1, 0, 0, 0)
        query += b"".join(bytes([len(part)]) + part.encode("ascii") for part in "example.com".split(".")) + b"\x00"
        query += struct.pack(">HH", 1, 1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.sendto(query, (server, 53))
            data, _ = sock.recvfrom(512)
            return {"answer_bytes": len(data)}
    return action


def _resolver():
    return {"addresses": len(socket.getaddrinfo("example.com", 443))}


def _spawn(flags: int):
    def action():
        completed = subprocess.run([sys.executable, "-I", "-S", "-c", "0"], creationflags=flags, capture_output=True,
                                   timeout=15, check=False)
        return {"returncode": completed.returncode}
    return action


def _gateway(plan: dict) -> dict:
    sys.path.insert(0, plan["bundle"])
    import provider_egress_gateway as gateway

    results: dict = {}
    client = gateway.NamedPipeGatewayClient(pipe_name=plan["pipe_name"], launch_id=plan["launch_id"],
                                            egress_policy_sha256=plan["egress_policy_sha256"],
                                            expected_server_pid=plan["server_pid"])
    try:
        results["hello"] = {"ok": True, "server": client.connect()}
    except Exception as exc:  # noqa: BLE001
        results["hello"] = {"ok": False, "code": getattr(exc, "code", type(exc).__name__)}
        return results
    base = plan["selftest_base_url"]
    cases = {
        "allowed": ("GET", base + "/selftest/ok"),
        "unapproved_host": ("GET", "https://example.com/selftest/ok"),
        "unapproved_method": ("POST", base + "/selftest/ok"),
        "unapproved_path": ("GET", base + "/other/ok"),
        "unapproved_scheme": ("GET", base.replace("https://", "http://") + "/selftest/ok"),
        "redirect": ("GET", base + "/selftest/redirect"),
    }
    for name, (method, url) in cases.items():
        answer = client.request(method=method, url=url, headers=[("Accept", "application/json")], body=None)
        results[name] = {"ok": answer.get("ok"), "code": answer.get("code"), "status": answer.get("status"),
                         "lineage": bool(answer.get("lineage"))}
    # A non-governed operation (a tunnel request) on the same connection.
    raw = client._exchange({"op": "CONNECT", "target": "example.com:443"})
    results["connect_tunnel"] = {"ok": raw.get("ok"), "code": raw.get("code")}
    client.close()
    return results


def main() -> int:
    plan = json.loads(open(sys.argv[1], encoding="utf-8").read())
    if plan.get("mode") == "block":
        sys.stdout.write(json.dumps({"mode": "block", "pid": os.getpid()}) + "\n")
        sys.stdout.flush()
        sys.stdin.readline()
        return 0
    report: dict = {"pid": os.getpid(), "ppid": os.getppid(), "token_sid": _token_sid(), "in_job": _in_job()}
    report["files"] = {
        "allowed_read": {path: _attempt(_read(path)) for path in plan["allowed_read"]},
        "allowed_write": {path: _attempt(_write_then_delete(path)) for path in plan["allowed_write"]},
        "denied_read": {path: _attempt(_read(path)) for path in plan["denied_read"]},
        "denied_write": {path: _attempt(_write_only(path)) for path in plan["denied_write"]},
    }
    report["network"] = {
        "ipv4_tcp": {target: _attempt(_tcp(socket.AF_INET, (target, 443))) for target in plan["ipv4_targets"]},
        "ipv6_tcp": {target: _attempt(_tcp(socket.AF_INET6, (target, 443, 0, 0))) for target in plan["ipv6_targets"]},
        "dns_udp_direct": {server: _attempt(_dns_udp(server)) for server in plan["dns_servers"]},
        "system_resolver": _attempt(_resolver),
        "loopback_tcp": _attempt(_tcp(socket.AF_INET, ("127.0.0.1", int(plan["loopback_port"])))),
    }
    report["process"] = {
        "child": _attempt(_spawn(0x08000000)),
        "child_breakaway": _attempt(_spawn(0x08000000 | 0x01000000)),  # CREATE_BREAKAWAY_FROM_JOB
    }
    try:
        report["gateway"] = _gateway(plan)
    except Exception as exc:  # noqa: BLE001
        report["gateway"] = {"error": type(exc).__name__, "code": getattr(exc, "code", None)}
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    sys.stdout.flush()
    sys.stdin.readline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
