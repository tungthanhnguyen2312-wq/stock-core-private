"""Post-provision Windows containment qualification (WINDOWS_PROVIDER_RUNTIME_OS_CONTAINMENT_AND_ATTESTATION_V1).

Run from a NON-elevated owner shell after ``tools/provision_provider_os_containment.ps1 -Apply``.
Proves, before any provider call and without importing any provider package, the controlled
enforcement tests of the milestone contract (L1-L18):

  L1  worker launches under the exact provisioned SID (OS read-back + probe self-view + pipe impersonation)
  L2  worker is in the exact per-launch Job (kernel object name, PID list via our Job handle)
  L3  KILL_ON_JOB_CLOSE (closing the Job handle ends a blocked worker)
  L4  breakaway disabled (limits read back; child / CREATE_BREAKAWAY_FROM_JOB both refused)
  L5  ACL positive cases (kernel AccessCheck with a worker logon token + probe reads/writes)
  L6  owner profile access fails          L7  Stock Lookup secrets access fails
  L8  production DB / checkout / evidence / host secrets access fails
  L9  direct IPv4 egress fails            L10 direct IPv6 egress fails
  L11 direct DNS fails (UDP 53 from the worker)
  L12 the governed named pipe works (HELLO + an allow-listed self-test operation, with lineage)
  L13 the wrong identity cannot use the pipe (the owner process is refused by the gateway)
  L14 the gateway refuses an unapproved host
  L15 the gateway refuses unapproved method/path/scheme and a CONNECT-style tunnel operation
  L16 the gateway applies the governed redirect policy (max_redirects 0: refused, never followed)
  L17 the attestation validators accept these real read-backs (process control, ACL policy digest, firewall digest)
  L18 the offline fake backend can never satisfy a live (production) attestation

The self-test gateway uses a stub upstream: no request leaves the Producer either. Residual
observations (system resolver via the DNS Client service, loopback) are reported, never scored.

The report is written to ``C:\\ProgramData\\StockLookup\\provider-runtime\\evidence\\
containment_qualification_<utc>.json``; its SHA-256 is what an approved manifest binds as
``os_containment.verification_evidence_sha256``.

``--same-identity-harness`` exercises the same spawn/Job/pipe/probe plumbing under the owner's own
identity in a scratch directory (for development on an unprovisioned host). Its report is always
``HARNESS_ONLY_NOT_QUALIFICATION`` and is never written to the evidence directory.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import provider_build_manifest as build_manifest  # noqa: E402
import provider_egress_gateway as gateway  # noqa: E402
import provider_os_enforcement as os_enforcement  # noqa: E402
import provider_windows_os_backend as backend  # noqa: E402
import provider_worker_containment as worker_containment  # noqa: E402

PROBE_SOURCE = ROOT / "tools" / "provider_containment_probe.py"
SELFTEST_HOST = "gateway-selftest.stocklookup.invalid"
IPV4_TARGETS = ("1.1.1.1", "8.8.8.8")
IPV6_TARGETS = ("2606:4700:4700::1111", "2001:4860:4860::8888")
DNS_SERVERS = ("1.1.1.1", "8.8.8.8")
# Harness mode never sends to real resolvers: RFC 5737 / RFC 3849 documentation addresses only.
HARNESS_TARGETS = {"ipv4": ("192.0.2.1",), "ipv6": ("2001:db8::1",), "dns": ("192.0.2.53",)}
WSAEACCES = 10013
PASS, FAIL, NOT_PROVISIONED = "PASS", "FAIL", "NOT_PROVISIONED"
STATUS_HARNESS = "HARNESS_ONLY_NOT_QUALIFICATION"
RESULT_KEYS = (
    "WORKER_SID_EXACT", "JOB_EXACT_MEMBERSHIP", "JOB_KILL_ON_CLOSE", "BREAKAWAY_BLOCKED", "ACL_POSITIVE",
    "OWNER_PROFILE_DENIED", "STOCKLOOKUP_SECRETS_DENIED", "PRODUCTION_DATA_DENIED", "DIRECT_IPV4_EGRESS_BLOCKED",
    "DIRECT_IPV6_EGRESS_BLOCKED", "DIRECT_DNS_BLOCKED", "NAMED_PIPE_GATEWAY", "PIPE_WRONG_IDENTITY_REFUSED",
    "GATEWAY_REJECTS_UNAPPROVED_HOST", "GATEWAY_REJECTS_UNAPPROVED_METHOD_PATH", "GATEWAY_REDIRECT_POLICY",
    "ATTESTATION_VALIDATORS", "FAKE_BACKEND_REFUSED_FOR_LIVE",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(ok: bool, **detail: Any) -> dict[str, Any]:
    return {"outcome": PASS if ok else FAIL, **detail}


def _blocked_by_os(attempt: dict[str, Any]) -> bool:
    return not attempt.get("succeeded") and WSAEACCES in (attempt.get("winerror"), attempt.get("errno"))


def _access_denied(attempt: dict[str, Any]) -> bool:
    return not attempt.get("succeeded") and attempt.get("error") == "PermissionError"


def _owner_tcp_control(family: int, target: str) -> dict[str, Any]:
    """Owner-side connectivity baseline for the same destination (establishes that a worker
    failure is the OS block, not an absent route)."""
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect((target, 443) if family == socket.AF_INET else (target, 443, 0, 0))
        return {"succeeded": True}
    except OSError as exc:
        return {"succeeded": False, "errno": exc.errno, "winerror": getattr(exc, "winerror", None)}


def _selftest_perform(method: str, url: str, headers: Any, body: Any) -> gateway.UpstreamResponse:
    path = url.split(SELFTEST_HOST, 1)[-1]
    if path.startswith("/selftest/redirect"):
        return gateway.UpstreamResponse(302, "Found", (("Location", "https://example.com/"),), b"", url)
    return gateway.UpstreamResponse(200, "OK", (("Content-Type", "application/json"),), b'{"selftest":true}', url)


def _selftest_policy() -> tuple[Any, str]:
    rules = [{"scheme": "https", "host": SELFTEST_HOST, "port": 443, "method": "GET", "path_pattern": "/selftest/{name}",
              "purpose": "CONTAINMENT_QUALIFICATION_SELFTEST", "max_redirects": 0}]
    return worker_containment.EgressPolicy.from_endpoints(rules), build_manifest.canonical_sha256(
        {"contract_version": "provider_containment_selftest_policy/v1", "rules": rules})


class _Context:
    """Where the qualification runs and as whom."""

    def __init__(self, *, record: backend.HostRecord | None, harness_root: Path | None):
        self.api = backend.win32()
        self.owner_sid = self.api.current_sid()
        self.record = record
        self.harness = record is None
        if record is not None:
            self.runtime_root = Path(record.runtime_root)
            self.worker_sid = record.worker_sid
            self.worker_account = record.worker_account
            self.production = backend.WindowsProductionOSBackend(record)
            self.spawner: backend._Spawner = self.production.spawner()
        else:
            assert harness_root is not None
            self.runtime_root = harness_root
            for name in backend.SUBTREES.values():
                (harness_root / name).mkdir(parents=True, exist_ok=True)
            self.worker_sid = self.owner_sid
            self.worker_account = None
            self.production = None
            self.spawner = backend.SameIdentitySpawner()

    def subtree(self, name: str) -> Path:
        return self.runtime_root / backend.SUBTREES[name]


def _probe_layout(ctx: _Context, probe_id: str) -> dict[str, Path]:
    root = ctx.subtree("scratch") / f"probe-{probe_id}"
    bundle, work = root / "bundle", root / "work"
    bundle.mkdir(parents=True)
    work.mkdir()
    shutil.copyfile(PROBE_SOURCE, bundle / "provider_containment_probe.py")
    shutil.copyfile(ROOT / "provider_egress_gateway.py", bundle / "provider_egress_gateway.py")
    if not ctx.harness:
        ctx.api.set_path_dacl(str(root), backend.per_launch_sddl(ctx.owner_sid, ctx.worker_sid, worker_rights=backend.FILE_MODIFY))
        ctx.api.set_path_dacl(str(bundle), backend.per_launch_sddl(ctx.owner_sid, ctx.worker_sid,
                                                                   worker_rights=backend.FILE_GENERIC_READ_EXECUTE))
    return {"root": root, "bundle": bundle, "work": work}


def _write_plan(ctx: _Context, layout: dict[str, Path], plan: dict[str, Any]) -> Path:
    path = layout["bundle"] / "plan.json"
    path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    if not ctx.harness:
        ctx.api.set_path_dacl(str(path), backend.per_launch_sddl(ctx.owner_sid, ctx.worker_sid,
                                                                 worker_rights=backend.FILE_GENERIC_READ_EXECUTE, inherit=False))
    return path


def _probe_environment(layout: dict[str, Path]) -> dict[str, str]:
    work = str(layout["work"])
    return {"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"), "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
            "PATH": os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32"), "TEMP": work, "TMP": work,
            "USERPROFILE": work, "HOME": work, "PYTHONUTF8": "1"}


def _base_python() -> str:
    candidate = Path(sys.base_prefix) / "python.exe"
    return str(candidate if candidate.is_file() else Path(sys.executable))


def denied_paths(owner_profile: str) -> dict[str, list[str]]:
    import runtime_paths

    profile = Path(owner_profile)
    main_checkout = Path(r"C:\Projects\StockLookup\stock-core-private")
    # The configured runtime root, else this workspace's dashboard runtime (where vn_stock.db lives).
    runtime_root = runtime_paths.runtime_root(default=r"C:\Projects\StockLookup\dashboard-runtime")
    return {
        "OWNER_PROFILE_DENIED": [str(profile), str(profile / "Documents"), str(profile / ".vnstock"),
                                 str(profile / ".vnstock" / "api_key.json")],
        "STOCKLOOKUP_SECRETS_DENIED": [str(profile / ".stocklookup"), str(profile / ".stocklookup" / "secrets.env"),
                                       *([os.environ["STOCK_LOOKUP_SECRETS_FILE"]] if os.environ.get("STOCK_LOOKUP_SECRETS_FILE") else [])],
        "PRODUCTION_DATA_DENIED": [r"C:\Projects\StockLookup", str(main_checkout), str(main_checkout / "AGENTS.md"),
                                   str(main_checkout / "operations-review"), str(runtime_root), str(runtime_root / "vn_stock.db"),
                                   str(ROOT / "AGENTS.md")],
    }


def run_probe(ctx: _Context, *, owner_profile: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    probe_id = uuid.uuid4().hex
    layout = _probe_layout(ctx, probe_id)
    policy, policy_digest = _selftest_policy()
    job_name = build_manifest.expected_job_name(probe_id)
    job = backend.WindowsJob.create(job_name, owner_sid=ctx.owner_sid, active_process_limit=1)
    core = gateway.GatewayCore(launch_id=probe_id, egress_policy=policy, egress_policy_sha256=policy_digest,
                               rate_per_minute=build_manifest.OWNER_APPROVED_GOVERNOR_CEILING_RPM,
                               perform=_selftest_perform, ledger_path=str(ctx.subtree("ledger") / f"probe-{probe_id}.jsonl"))
    server = gateway.NamedPipeGatewayServer(core, pipe_name=gateway.ipc_endpoint_for(probe_id), owner_sid=ctx.owner_sid,
                                            worker_sid=ctx.worker_sid, client_pid_allowed=lambda pid: pid in job.pids())
    server.start()
    loopback = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    loopback.bind(("127.0.0.1", 0))
    loopback.listen(4)
    threading.Thread(target=lambda: [loopback.accept()[0].close() for _ in range(1)], daemon=True).start()
    try:
        # L13 first: the owner (not a Job member, not the worker SID) must be refused.
        wrong = gateway.NamedPipeGatewayClient(pipe_name=server.pipe_name, launch_id=probe_id,
                                               egress_policy_sha256=policy_digest, expected_server_pid=server.server_pid)
        try:
            wrong.connect()
            wrong_outcome = {"connected": True}
        except gateway.GatewayRefusal as exc:
            wrong_outcome = {"connected": False, "client_code": exc.code}
        finally:
            wrong.close()
        for _ in range(100):  # the refusal is recorded on the gateway thread
            if any(item.get("pid") == os.getpid() for item in server.rejected_clients):
                break
            time.sleep(0.05)
        recorded = [item for item in server.rejected_clients if item.get("pid") == os.getpid()]
        wrong_outcome["refused"] = not wrong_outcome["connected"] and bool(recorded)             and recorded[0].get("code") == gateway.R_CLIENT_NOT_AUTHORIZED
        wrong_outcome["server_record"] = recorded[:1]
        results["PIPE_WRONG_IDENTITY_REFUSED"] = _result(
            bool(wrong_outcome.get("refused")) and not ctx.harness, observed=wrong_outcome,
            server_rejections=len(server.rejected_clients),
            note="harness: the owner IS the harness worker identity, so refusal relies on Job membership only" if ctx.harness else None)

        denied = denied_paths(owner_profile)
        plan = {
            "mode": "full", "bundle": str(layout["bundle"]), "pipe_name": server.pipe_name, "launch_id": probe_id,
            "server_pid": server.server_pid, "egress_policy_sha256": policy_digest,
            "selftest_base_url": f"https://{SELFTEST_HOST}", "loopback_port": loopback.getsockname()[1],
            "allowed_read": [str(Path(sys.base_prefix) / "Lib"), str(layout["bundle"]), str(ctx.subtree("runtime"))],
            "allowed_write": [str(layout["work"]), str(ctx.subtree("state"))],
            "denied_read": sorted({path for paths in denied.values() for path in paths}
                                  | {str(ctx.subtree("host")), str(ctx.subtree("evidence")), str(ctx.subtree("ledger"))}),
            "denied_write": [str(layout["bundle"]), str(ctx.subtree("runtime"))],
            "ipv4_targets": list(HARNESS_TARGETS["ipv4"] if ctx.harness else IPV4_TARGETS),
            "ipv6_targets": list(HARNESS_TARGETS["ipv6"] if ctx.harness else IPV6_TARGETS),
            "dns_servers": list(HARNESS_TARGETS["dns"] if ctx.harness else DNS_SERVERS),
        }
        plan_path = _write_plan(ctx, layout, plan)
        argv = [_base_python(), "-I", "-S", "-X", "utf8", "-u", str(layout["bundle"] / "provider_containment_probe.py"),
                str(plan_path)]
        process = backend.spawn_suspended_in_job(spawner=ctx.spawner, argv=argv, environment=_probe_environment(layout),
                                                 cwd=str(layout["work"]), job=job, launch_id=probe_id)
        try:
            line = _read_line(process, timeout=120)
            report = json.loads(line) if line else {}
            kernel_name = job.kernel_name()
            pids = job.pids()
            membership = backend.classify_job_members(pids, process.pid, ctx.api.process_snapshot())
            accounting = job.accounting()
            limits = job.limits()
            in_job = job.contains(process.handle)
            identity = ctx.api.process_identity(process.handle)
            accepted = list(server.accepted_clients)
        finally:
            try:
                process.stdin.write("done\n")
                process.stdin.flush()
            except OSError:
                pass
            try:
                process.wait(timeout=30)
            except Exception:  # noqa: BLE001
                process.kill()
                process.wait(timeout=10)
    finally:
        server.stop()
        loopback.close()
        job.close()

    results["_probe"] = {"report": report, "job_kernel_name": kernel_name, "job_pids": pids, "job_limits": limits,
                         "job_membership": membership, "job_accounting": accounting,
                         "identity_readbacks": identity, "gateway_accepted": accepted, "probe_stderr_tail":
                         process.stderr_tail.decode("utf-8", "replace")[-2000:]}
    readback_sids = {item["sid"] for item in identity if item.get("sid")}
    pipe_sids = {item.get("sid") for item in accepted if item.get("pid") == report.get("pid")}
    results["WORKER_SID_EXACT"] = _result(
        readback_sids == {ctx.worker_sid} and report.get("token_sid") == ctx.worker_sid and pipe_sids == {ctx.worker_sid},
        os_readbacks=identity, probe_token_sid=report.get("token_sid"), pipe_impersonation_sids=sorted(s for s in pipe_sids if s))
    results["JOB_EXACT_MEMBERSHIP"] = _result(
        backend.local_job_name(kernel_name) == job_name and membership["worker_pids"] == [process.pid]
        and membership["interpreter_pid"] == process.pid == report.get("pid") and in_job and report.get("in_job") is True,
        job_name=backend.local_job_name(kernel_name), kernel_name=kernel_name, pids=pids, spawned_pid=process.pid,
        members=membership["members"], console_host_pids=membership["console_host_pids"], accounting=accounting)
    children = (report.get("process") or {})
    results["BREAKAWAY_BLOCKED"] = _result(
        not limits["breakaway_ok"] and not limits["silent_breakaway_ok"]
        and not (children.get("child") or {}).get("succeeded", True)
        and not (children.get("child_breakaway") or {}).get("succeeded", True),
        limits=limits, child=children.get("child"), child_breakaway=children.get("child_breakaway"))
    files = report.get("files") or {}
    positive = {**(files.get("allowed_read") or {}), **{f"write:{k}": v for k, v in (files.get("allowed_write") or {}).items()}}
    results["ACL_POSITIVE_PROBE"] = _result(bool(positive) and all(v.get("succeeded") for v in positive.values()), attempts=positive)
    denied_read = files.get("denied_read") or {}
    for key, paths in denied.items():
        attempts = {path: denied_read.get(path) for path in paths if path in denied_read}
        existing = {path: item for path, item in attempts.items() if item and item.get("error") != "FileNotFoundError"}
        results[key] = _result(bool(existing) and all(_access_denied(item) for item in existing.values()), attempts=attempts)
    private = {path: denied_read.get(path) for path in (str(ctx.subtree("host")), str(ctx.subtree("evidence")),
                                                        str(ctx.subtree("ledger")))}
    denied_write = files.get("denied_write") or {}
    results["PRODUCTION_DATA_DENIED"]["host_private_subtrees"] = private
    results["PRODUCTION_DATA_DENIED"]["denied_write"] = denied_write
    if not all(item and _access_denied(item) for item in [*private.values(), *denied_write.values()]):
        results["PRODUCTION_DATA_DENIED"]["outcome"] = FAIL
    network = report.get("network") or {}
    v4 = network.get("ipv4_tcp") or {}
    results["DIRECT_IPV4_EGRESS_BLOCKED"] = _result(bool(v4) and all(_blocked_by_os(item) for item in v4.values()),
                                                    worker=v4, owner_control={t: _owner_tcp_control(socket.AF_INET, t) for t in v4})
    v6 = network.get("ipv6_tcp") or {}
    v6_control = {t: _owner_tcp_control(socket.AF_INET6, t) for t in v6}
    v6_blocked = bool(v6) and all(_blocked_by_os(item) for item in v6.values())
    no_route = bool(v6) and not any(item.get("succeeded") for item in v6.values()) \
        and not any(item.get("succeeded") for item in v6_control.values())
    results["DIRECT_IPV6_EGRESS_BLOCKED"] = _result(
        v6_blocked or no_route, worker=v6, owner_control=v6_control,
        basis="OS_BLOCK_OBSERVED" if v6_blocked else ("HOST_HAS_NO_IPV6_ROUTE_RULE_SCOPE_ANY" if no_route else "WORKER_REACHED_IPV6"))
    dns = network.get("dns_udp_direct") or {}
    results["DIRECT_DNS_BLOCKED"] = _result(bool(dns) and all(_blocked_by_os(item) for item in dns.values()), worker=dns)
    results["_residual_observations"] = {
        "SYSTEM_RESOLVER_VIA_DNS_CLIENT_SERVICE": network.get("system_resolver"),
        "LOOPBACK_TCP": network.get("loopback_tcp"),
        "note": "Name queries handed to the DNS Client service and loopback TCP are outside a per-user WFP block; "
                "the worker's in-process containment refuses all resolution/sockets and the gateway path needs neither.",
    }
    gw = report.get("gateway") or {}
    results["NAMED_PIPE_GATEWAY"] = _result(
        bool((gw.get("hello") or {}).get("ok")) and (gw.get("allowed") or {}).get("status") == 200
        and (gw.get("allowed") or {}).get("lineage") is True, observed={k: gw.get(k) for k in ("hello", "allowed")})
    results["GATEWAY_REJECTS_UNAPPROVED_HOST"] = _result(
        (gw.get("unapproved_host") or {}).get("code") == worker_containment.TRANSPORT_HOST_NOT_ALLOWLISTED, observed=gw.get("unapproved_host"))
    results["GATEWAY_REJECTS_UNAPPROVED_METHOD_PATH"] = _result(
        (gw.get("unapproved_method") or {}).get("code") == worker_containment.TRANSPORT_METHOD_NOT_ALLOWED
        and (gw.get("unapproved_path") or {}).get("code") == worker_containment.TRANSPORT_PATH_NOT_ALLOWLISTED
        and (gw.get("unapproved_scheme") or {}).get("code") == worker_containment.TRANSPORT_SCHEME_NOT_ALLOWED
        and (gw.get("connect_tunnel") or {}).get("code") == gateway.R_OPERATION_NOT_GOVERNED,
        observed={k: gw.get(k) for k in ("unapproved_method", "unapproved_path", "unapproved_scheme", "connect_tunnel")})
    results["GATEWAY_REDIRECT_POLICY"] = _result(
        (gw.get("redirect") or {}).get("code") == gateway.R_REDIRECT_NOT_PERMITTED, observed=gw.get("redirect"))
    # L17 (process-control part): the contract's own validator over these real read-backs.
    section = {"mechanism": backend.PROCESS_CONTROL_MECHANISM, "source": "OS_JOB_QUERY",
               "job": {"name": backend.local_job_name(kernel_name), "membership_verified_with_job_handle": in_job,
                       "assigned_pids": pids, "limits": limits}}
    results["_l17_process_control_violations"] = os_enforcement.process_control_violations(
        section, {"process_control_mechanism": backend.PROCESS_CONTROL_MECHANISM, "job_name": job_name,
                  "job_active_process_limit": 1}, platform="win32", spawned_pid=process.pid, interpreter_pid=process.pid)
    return results


def _read_line(process: backend.ContainedWorkerProcess, *, timeout: float) -> str:
    box: dict[str, str] = {}
    reader = threading.Thread(target=lambda: box.setdefault("line", process.stdout.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    return box.get("line", "").strip()


def run_kill_on_close(ctx: _Context) -> dict[str, Any]:
    probe_id = uuid.uuid4().hex
    layout = _probe_layout(ctx, probe_id)
    plan_path = _write_plan(ctx, layout, {"mode": "block"})
    job = backend.WindowsJob.create(build_manifest.expected_job_name(probe_id), owner_sid=ctx.owner_sid, active_process_limit=1)
    argv = [_base_python(), "-I", "-S", "-u", str(layout["bundle"] / "provider_containment_probe.py"), str(plan_path)]
    process = backend.spawn_suspended_in_job(spawner=ctx.spawner, argv=argv, environment=_probe_environment(layout),
                                             cwd=str(layout["work"]), job=job, launch_id=probe_id)
    started = _read_line(process, timeout=60)
    alive_before = process.api.WaitForSingleObject(process.handle, 0) != 0
    job.close()  # no TerminateJobObject: KILL_ON_JOB_CLOSE alone must end the worker
    ended = process.api.WaitForSingleObject(process.handle, 15000) == 0
    return _result(bool(started) and alive_before and ended, started=bool(started), alive_before_close=alive_before,
                   ended_after_handle_close=ended)


def acl_access_checks(ctx: _Context, *, owner_profile: str) -> dict[str, Any]:
    """L5-L8 from the kernel side: AccessCheck with a real worker logon token."""
    if ctx.harness:
        return {"outcome": "NOT_APPLICABLE_HARNESS"}
    api = ctx.api
    secret = ctx.production._secret()
    try:
        token = api.logon_token(ctx.worker_account, secret)
    finally:
        api.ctypes.memset(secret, 0, api.ctypes.sizeof(secret))
    try:
        identity = api.token_user_sid(token)
        wanted: list[tuple[str, str]] = [
            (str(ctx.subtree("runtime")), backend.ACCESS_READ_EXECUTE), (str(Path(sys.base_prefix)), backend.ACCESS_READ_EXECUTE),
            (str(ctx.subtree("state")), backend.ACCESS_READ_WRITE), (str(ctx.subtree("host")), backend.ACCESS_NONE),
            (str(ctx.subtree("evidence")), backend.ACCESS_NONE), (str(ctx.subtree("ledger")), backend.ACCESS_NONE),
        ]
        for paths in denied_paths(owner_profile).values():
            wanted += [(path, backend.ACCESS_NONE) for path in paths if os.path.exists(path)]
        roots = []
        for path, access_class in wanted:
            try:
                granted = api.effective_access(path, token)
                observed = backend.classify_access(granted)
            except backend.WindowsContainmentError as exc:
                granted, observed = None, f"UNREADABLE:{exc.detail.get('win32_error')}"
            roots.append({"path": path, "access_class": access_class, "observed_access_class": observed,
                          "granted_mask": granted, "effective_access_verified": observed == access_class})
    finally:
        api.CloseHandle(token)
    policy = {"contract_version": "provider_acl_policy/v1", "identity": ctx.worker_sid,
              "roots": sorted(({"path": p, "access_class": c} for p, c in wanted), key=lambda i: (i["path"], i["access_class"]))}
    section = {"source": "OS_ACL_QUERY", "identity": identity, "policy_sha256": build_manifest.canonical_sha256(policy), "roots": roots}
    violations = os_enforcement.acl_violations(section, {"acl_policy": policy, "acl_policy_sha256": build_manifest.canonical_sha256(policy)})
    return {"outcome": PASS if not violations else FAIL, "identity": identity, "roots": roots, "violations": violations}


def fake_backend_refused() -> dict[str, Any]:
    """L18: an offline-fake-issued result can never satisfy a PRODUCTION requirement."""
    expected = {"backend_id": backend.BACKEND_ID, "backend_contract_version": backend.BACKEND_CONTRACT_VERSION}
    normalized = {"contract_version": os_enforcement.ATTESTATION_CONTRACT_VERSION, "evidence_sha256": "0" * 64,
                  "verified_at_utc": _utc(),
                  "backend": {"kind": os_enforcement.BACKEND_OFFLINE_FAKE, "backend_id": os_enforcement.OFFLINE_FAKE_BACKEND_ID,
                              "contract_version": os_enforcement.BACKEND_CONTRACT_VERSION}}
    failures = os_enforcement.attestation_contract_violations(
        normalized, expected, requirement=os_enforcement.BACKEND_PRODUCTION, spawned_pid=1, worker_facts={}, platform="win32")
    codes = {item["code"] for item in failures}
    configured = os_enforcement.production_backend()
    ok = os_enforcement.R_BACKEND_NOT_AUTHORIZED in codes and (
        configured is None or (configured.kind == os_enforcement.BACKEND_PRODUCTION
                               and configured.backend_id != os_enforcement.OFFLINE_FAKE_BACKEND_ID))
    return _result(ok, refusal_codes=sorted(codes), configured_backend=getattr(configured, "backend_id", None))


def qualify(*, harness_root: Path | None, owner_profile: str) -> dict[str, Any]:
    record = None
    if harness_root is None:
        try:
            record = backend.load_host_record()
        except backend.WindowsContainmentError as exc:
            return {"contract_version": backend.QUALIFICATION_REPORT_CONTRACT_VERSION, "status": FAIL, "generated_at_utc": _utc(),
                    "error": exc.reason_code, "results": {key: {"outcome": FAIL} for key in RESULT_KEYS}}
        if record is None:
            return {"contract_version": backend.QUALIFICATION_REPORT_CONTRACT_VERSION, "status": NOT_PROVISIONED,
                    "generated_at_utc": _utc(), "host_record": backend.HOST_RECORD_PATH,
                    "results": {key: {"outcome": NOT_PROVISIONED} for key in RESULT_KEYS}}
    ctx = _Context(record=record, harness_root=harness_root)
    report: dict[str, Any] = {
        "contract_version": backend.QUALIFICATION_REPORT_CONTRACT_VERSION, "generated_at_utc": _utc(),
        "backend_id": backend.BACKEND_ID, "worker_sid": ctx.worker_sid, "worker_account": ctx.worker_account,
        "owner_sid": ctx.owner_sid, "runtime_root": str(ctx.runtime_root), "harness": ctx.harness,
        "firewall_policy_sha256": record.firewall_policy_sha256 if record else None,
        "gateway_module_sha256": gateway.module_sha256(), "backend_module_sha256": build_manifest.sha256_file(backend.__file__),
        "provider_packages_imported": sorted(name for name in sys.modules if name.split(".")[0] in ("vnstock", "vnai")),
    }
    firewall = backend.query_firewall(ctx.worker_sid) if record else {"failures": [], "note": "harness"}
    probe = run_probe(ctx, owner_profile=owner_profile)
    results: dict[str, Any] = {key: value for key, value in probe.items() if not key.startswith("_")}
    results["JOB_KILL_ON_CLOSE"] = run_kill_on_close(ctx)
    acl = acl_access_checks(ctx, owner_profile=owner_profile)
    results["ACL_POSITIVE"] = dict(results.pop("ACL_POSITIVE_PROBE"))
    results["ACL_POSITIVE"]["kernel_access_check"] = acl
    if acl.get("outcome") not in (PASS, "NOT_APPLICABLE_HARNESS"):
        results["ACL_POSITIVE"]["outcome"] = FAIL
    process_control_violations = probe["_l17_process_control_violations"]
    results["ATTESTATION_VALIDATORS"] = _result(
        not process_control_violations and acl.get("outcome") == PASS and not firewall.get("failures")
        and (record is None or firewall.get("firewall_policy_sha256") == record.firewall_policy_sha256),
        process_control_violations=process_control_violations, acl_outcome=acl.get("outcome"),
        firewall_failures=firewall.get("failures"), firewall_policy_sha256=firewall.get("firewall_policy_sha256"))
    results["FAKE_BACKEND_REFUSED_FOR_LIVE"] = fake_backend_refused()
    report["results"] = {key: results.get(key, {"outcome": FAIL, "error": "not evaluated"}) for key in RESULT_KEYS}
    report["firewall"] = firewall
    report["probe"] = probe["_probe"]
    report["residual_observations"] = probe["_residual_observations"]
    report["provider_packages_imported"] = sorted(name for name in sys.modules if name.split(".")[0] in ("vnstock", "vnai"))
    passed = all(report["results"][key]["outcome"] == PASS for key in RESULT_KEYS) and not report["provider_packages_imported"]
    report["status"] = STATUS_HARNESS if ctx.harness else (PASS if passed else FAIL)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--same-identity-harness", metavar="SCRATCH_DIR",
                        help="exercise the plumbing under the owner identity in SCRATCH_DIR (never a qualification)")
    parser.add_argument("--output", help="also write the report here")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print(json.dumps({"status": "NOT_APPLICABLE", "platform": sys.platform}))
        return 3
    harness_root = Path(args.same_identity_harness).resolve() if args.same_identity_harness else None
    owner_profile = os.environ.get("USERPROFILE") or str(Path.home())
    report = qualify(harness_root=harness_root, owner_profile=owner_profile)
    data = (json.dumps(report, indent=1, sort_keys=True, default=str) + "\n").encode("utf-8")
    written = None
    if report.get("status") in (PASS, FAIL) and harness_root is None and report.get("backend_id"):
        evidence = Path(backend.RUNTIME_ROOT) / backend.SUBTREES["evidence"]
        written = evidence / f"containment_qualification_{report['generated_at_utc'].replace(':', '').replace('-', '')}.json"
        written.write_bytes(data)
    if args.output:
        Path(args.output).write_bytes(data)
    summary = {"status": report.get("status"), "report": str(written) if written else args.output,
               "report_sha256": build_manifest.sha256_bytes(data),
               "results": {key: (report.get("results") or {}).get(key, {}).get("outcome") for key in RESULT_KEYS}}
    print(json.dumps(summary, indent=1))
    return 0 if report.get("status") in (PASS, STATUS_HARNESS) else (3 if report.get("status") == NOT_PROVISIONED else 2)


if __name__ == "__main__":
    raise SystemExit(main())
