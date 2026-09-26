"""WINDOWS_PROVIDER_RUNTIME_OS_CONTAINMENT_AND_ATTESTATION_V1 -- Windows production backend + egress gateway.

Two tiers in one module:

* hermetic contract tests (every platform, Linux CI included): firewall/host-record/qualification
  contracts, access classification, Job-member classification, the named-pipe gateway contract in
  the manifest validator and the attestation checker, the gateway core (policy, redirect, rate
  ceiling, lineage, telemetry DENY), the requests-guard forwarding path, and that no production
  backend is configured off Windows / on an unprovisioned or disabled host;
* Windows-only primitive tests (``skipif`` off Windows): real Job objects (limits, kill-on-close,
  name squatting), suspended spawn + assignment + resume, the named-pipe gateway end to end with a
  Job-member client and a refused non-member, and a kernel ``AccessCheck``. They run under the
  owner's own identity (``SameIdentitySpawner``) and never claim worker-identity containment;
  that is proven only by ``tools/run_provider_os_containment_qualification.py`` on a provisioned
  host. No network, no provider package, no elevation.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import provider_build_manifest as build_manifest
import provider_egress_gateway as gateway
import provider_os_enforcement as os_enforcement
import provider_windows_os_backend as backend
import provider_worker_containment as worker_containment

ROOT = Path(__file__).resolve().parents[1]
WORKER_SID = "S-1-5-21-270160003-185743851-2814889227-1105"
ON_WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(not ON_WINDOWS, reason="Win32 primitive test (Windows host only)")
RULES = [{"scheme": "https", "host": "kbbuddywts.kbsec.com.vn", "port": 443, "method": "GET",
          "path_pattern": "/iis-server/investment/stocks/{symbol}/data_day", "purpose": "KBS", "max_redirects": 0}]


def _firewall_observation(sid=WORKER_SID, **overrides):
    rule = {"name": backend.FIREWALL_RULE_NAME, "enabled": "True", "direction": "Outbound", "action": "Block",
            "profile": "Any", "primary_status": "OK", "local_user": f"D:(A;;CC;;;{sid})", "remote_address": ["Any"],
            "local_address": ["Any"], "protocol": "Any", "program": "Any"}
    rule.update(overrides)
    return {"rule": rule, "group_rules": [backend.FIREWALL_RULE_NAME],
            "profiles": [{"name": name, "enabled": "True", "allow_local_firewall_rules": "NotConfigured"}
                         for name in ("Domain", "Private", "Public")]}


def _record_payload(sid=WORKER_SID, **overrides):
    payload = {"contract_version": backend.HOST_RECORD_CONTRACT_VERSION, "backend_id": backend.BACKEND_ID,
               "worker_account": backend.WORKER_ACCOUNT_NAME, "worker_sid": sid, "runtime_root": backend.RUNTIME_ROOT,
               "firewall_policy_sha256": backend.firewall_policy_sha256(sid),
               "credential_blob": os.path.join(backend.RUNTIME_ROOT, "host", backend.CREDENTIAL_BLOB_NAME),
               "denied_roots_provisioned": [r"C:\Projects\StockLookup"]}
    payload.update(overrides)
    return payload


def _named_pipe_gateway():
    return gateway.gateway_identity(executable_sha256="a" * 64)


# ---------------------------------------------------------------------------------------------
# Firewall / host record / qualification report contracts.
# ---------------------------------------------------------------------------------------------


def test_firewall_policy_digest_is_bound_to_the_worker_sid():
    assert backend.firewall_policy_sha256(WORKER_SID) == backend.firewall_policy_sha256(WORKER_SID)
    assert backend.firewall_policy_sha256(WORKER_SID) != backend.firewall_policy_sha256(WORKER_SID[:-1] + "6")
    policy = backend.firewall_policy(WORKER_SID)
    assert (policy["direction"], policy["action"], policy["protocol"], policy["remote_address"]) == (
        "Outbound", "Block", "Any", ["Any"])


def test_firewall_readback_must_match_the_provisioned_rule_exactly():
    assert backend.firewall_violations(_firewall_observation(), WORKER_SID) == []
    for override, field_name in (({"action": "Allow"}, "rule.action"), ({"direction": "Inbound"}, "rule.direction"),
                                 ({"remote_address": ["LocalSubnet"]}, "rule.remote_address"),
                                 ({"protocol": "TCP"}, "rule.protocol"), ({"enabled": "False"}, "rule.enabled"),
                                 ({"local_user": "D:(A;;CC;;;S-1-5-11)"}, "rule.local_user"),
                                 ({"program": r"C:\x.exe"}, "rule.program"), ({"primary_status": "Error"}, "rule.primary_status")):
        fields = {item["field"] for item in backend.firewall_violations(_firewall_observation(**override), WORKER_SID)}
        assert field_name in fields, override
    other_sid = backend.firewall_violations(_firewall_observation(), "S-1-5-21-1-2-3-1999")
    assert {item["field"] for item in other_sid} == {"rule.local_user"}


def test_firewall_profiles_must_all_be_enabled_and_no_extra_group_rule():
    observed = _firewall_observation()
    observed["profiles"][2]["enabled"] = "False"
    observed["group_rules"].append("Something-Else")
    fields = {item["field"] for item in backend.firewall_violations(observed, WORKER_SID)}
    assert {"profiles.Public.enabled", "group_rules"} <= fields


def test_host_record_contract(tmp_path):
    assert backend.host_record_violations(_record_payload()) == []
    for override in ({"backend_id": "offline-fake-direct-popen"}, {"worker_sid": "S-1-5-18"}, {"worker_sid": "not-a-sid"},
                     {"runtime_root": r"C:\Users\x\provider"}, {"firewall_policy_sha256": "0" * 64},
                     {"credential_blob": r"C:\Users\x\.vnstock\api_key.json"}, {"worker_account": "CodexSandboxOffline"}):
        assert backend.host_record_violations(_record_payload(**override)), override
    assert backend.load_host_record(str(tmp_path / "absent.json")) is None
    bad = tmp_path / "record.json"
    bad.write_text(json.dumps(_record_payload(backend_id="x")), encoding="utf-8")
    with pytest.raises(backend.WindowsContainmentError):  # half-provisioned never reads as unprovisioned
        backend.load_host_record(str(bad))
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_record_payload()), encoding="utf-8")
    assert backend.load_host_record(str(good)).worker_sid == WORKER_SID


def test_qualification_report_must_pass_for_this_worker_and_firewall(tmp_path):
    record = backend.HostRecord(backend.WORKER_ACCOUNT_NAME, WORKER_SID, str(tmp_path),
                                backend.firewall_policy_sha256(WORKER_SID), "blob", (), {})
    report = {"contract_version": backend.QUALIFICATION_REPORT_CONTRACT_VERSION, "status": "PASS", "worker_sid": WORKER_SID,
              "backend_id": backend.BACKEND_ID, "firewall_policy_sha256": record.firewall_policy_sha256,
              "results": {key: {"outcome": "PASS"} for key in ("DIRECT_IPV4_EGRESS_BLOCKED", "DIRECT_IPV6_EGRESS_BLOCKED",
                                                                "DIRECT_DNS_BLOCKED")}}
    assert backend.qualification_report_violations(report, record) == []
    assert backend.qualification_report_violations({**report, "status": "HARNESS_ONLY_NOT_QUALIFICATION"}, record)
    assert backend.qualification_report_violations({**report, "worker_sid": "S-1-5-21-1-2-3-4"}, record)
    failing = json.loads(json.dumps(report))
    failing["results"]["DIRECT_DNS_BLOCKED"]["outcome"] = "FAIL"
    assert backend.qualification_report_violations(failing, record)
    # Bound by the exact file digest of a retained report.
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    data = json.dumps(report).encode("utf-8")
    (evidence / "containment_qualification_20260926T000000Z.json").write_bytes(data)
    found, failures = backend.find_qualification_report(record, build_manifest.sha256_bytes(data))
    assert found == report and failures == []
    assert backend.find_qualification_report(record, "f" * 64)[1]
    assert backend.find_qualification_report(record, None)[1]


def test_effective_access_classification():
    assert backend.classify_access(0) == backend.ACCESS_NONE
    assert backend.classify_access(0x00100020) == backend.ACCESS_NONE  # traverse + synchronize only
    assert backend.classify_access(backend.FILE_GENERIC_READ_EXECUTE) == backend.ACCESS_READ_EXECUTE
    assert backend.classify_access(backend.FILE_MODIFY) == backend.ACCESS_READ_WRITE
    assert backend.classify_access(0x001F01FF).startswith("PARTIAL")  # full control incl. WRITE_DAC is not READ_WRITE
    assert backend.classify_access(backend.FILE_GENERIC_READ_EXECUTE | backend.FILE_WRITE_DATA).startswith("PARTIAL")


def test_per_launch_sddl_grants_the_worker_exactly_the_requested_rights():
    sddl = backend.per_launch_sddl("S-1-5-21-1-2-3-1001", WORKER_SID, worker_rights=backend.FILE_GENERIC_READ_EXECUTE)
    assert sddl.startswith("D:P(") and f"(A;OICI;0x001200a9;;;{WORKER_SID})" in sddl
    assert "WD" not in sddl and "AU" not in sddl and ";BU)" not in sddl
    assert "(A;;0x001200a9;;;" in backend.per_launch_sddl("S-1-5-21-1-2-3-1001", WORKER_SID, worker_rights=0x1200A9,
                                                          inherit=False)


def test_job_member_classification_handles_console_host_and_venv_redirector():
    snapshot = {10: {"image": "python.exe", "ppid": 1}, 11: {"image": "conhost.exe", "ppid": 10},
                12: {"image": "python.exe", "ppid": 10}, 13: {"image": "cmd.exe", "ppid": 12}}
    direct = backend.classify_job_members([10, 11], 10, snapshot)
    assert (direct["interpreter_pid"], direct["console_host_pids"], direct["worker_pids"]) == (10, [11], [10])
    redirector = backend.classify_job_members([10, 11, 12], 10, snapshot)
    assert redirector["interpreter_pid"] == 12
    assert backend.classify_job_members([10, 11, 12, 13], 10, snapshot)["interpreter_pid"] is None
    # A conhost whose parent is not a Job member is not "our" console host.
    assert backend.classify_job_members([10, 11], 10, {**snapshot, 11: {"image": "conhost.exe", "ppid": 999}})["interpreter_pid"] is None


def test_job_kernel_name_maps_to_the_local_name_only():
    name = "StockLookupProvider-" + "a" * 32
    assert backend.local_job_name(f"\\Sessions\\1\\BaseNamedObjects\\{name}") == f"Local\\{name}"
    assert backend.local_job_name(None) is None
    assert backend.local_job_name(f"\\Device\\{name}") is None


def test_environment_block_is_sorted_and_rejects_injection():
    block = backend.environment_block({"b": "2", "A": "1"})
    assert block == "A=1\0b=2\0\0"
    with pytest.raises(backend.WindowsContainmentError):
        backend.environment_block({"X=Y": "1"})
    with pytest.raises(backend.WindowsContainmentError):
        backend.environment_block({"X": "a\0b"})


def test_no_production_backend_off_windows_disabled_or_unprovisioned(monkeypatch, tmp_path):
    # The test session disables the backend (conftest); nothing is configured under it.
    assert os.environ.get(backend.DISABLE_ENV) == backend.DISABLE_VALUE
    assert os_enforcement.production_backend() is None
    monkeypatch.delenv(backend.DISABLE_ENV)
    monkeypatch.setattr(backend, "HOST_RECORD_PATH", str(tmp_path / "absent.json"))
    assert backend.configured_backend() is None
    assert os_enforcement.production_backend() is None
    record = tmp_path / "record.json"
    record.write_text(json.dumps(_record_payload()), encoding="utf-8")
    monkeypatch.setattr(backend, "HOST_RECORD_PATH", str(record))
    configured = backend.configured_backend()
    if ON_WINDOWS:
        assert isinstance(configured, backend.WindowsProductionOSBackend)
        assert configured is backend.configured_backend() is os_enforcement.production_backend()
        assert configured.kind == os_enforcement.BACKEND_PRODUCTION and configured.backend_id == backend.BACKEND_ID
        monkeypatch.setenv(backend.DISABLE_ENV, "disabled")
        assert os_enforcement.production_backend() is None
    else:
        assert configured is None  # there is no POSIX production backend


# ---------------------------------------------------------------------------------------------
# Named-pipe gateway contract in the manifest validator and the attestation checker.
# ---------------------------------------------------------------------------------------------


def _manifest_with_gateway(gateway_block):
    return {"network": {"egress_gateway": gateway_block, "endpoints": RULES},
            "os_containment": {"egress_gateway_verified": True, "state": build_manifest.OS_CONTAINMENT_OWNER_VERIFIED}}


def test_manifest_accepts_the_named_pipe_gateway_identity():
    assert build_manifest.egress_gateway_violations(_manifest_with_gateway(_named_pipe_gateway()), approved=True) == []


@pytest.mark.parametrize("override", [
    {"host": "127.0.0.1"}, {"port": 8080}, {"ipc_endpoint": "tcp://127.0.0.1:8080"},
    {"ipc_endpoint": "\\\\.\\pipe\\StockLookupProviderGateway"}, {"ipc_endpoint": "\\\\server\\pipe\\x-{launch_id}"},
    {"transport": "HTTP_CONNECT_PROXY"}, {"executable_sha256": "not-a-digest"}, {"gateway_id": ""},
])
def test_manifest_refuses_a_malformed_named_pipe_gateway(override):
    block = {**_named_pipe_gateway(), **override}
    assert build_manifest.egress_gateway_violations(_manifest_with_gateway(block), approved=True)


def test_attestation_checks_named_pipe_gateway_identity_without_an_address():
    wanted = _named_pipe_gateway()
    expected = {"egress_policy_sha256": "e" * 64, "telemetry_policy_sha256": "t" * 64, "gateway": wanted}
    section = {"source": "OS_FIREWALL_QUERY", "mechanism": backend.EGRESS_MECHANISM, "policy_sha256": "e" * 64,
               "telemetry_policy_sha256": "t" * 64, "direct_egress_prohibited_verified": True,
               "gateway": {**wanted, "identity_verified": True}}
    assert os_enforcement.egress_violations(section, expected, platform="win32") == []
    for key, value in (("transport", "TCP"), ("ipc_endpoint", "\\\\.\\pipe\\other-{launch_id}"),
                       ("executable_sha256", "b" * 64), ("identity_verified", False)):
        broken = json.loads(json.dumps(section))
        broken["gateway"][key] = value
        assert os_enforcement.egress_violations(broken, expected, platform="win32"), key
    assert os_enforcement.egress_violations({**section, "direct_egress_prohibited_verified": False}, expected, platform="win32")
    assert os_enforcement.egress_violations({**section, "source": "DECLARED"}, expected, platform="win32")


def test_named_pipe_egress_policy_gives_the_worker_no_direct_socket():
    policy = worker_containment.EgressPolicy.from_endpoints(RULES, gateway=_named_pipe_gateway())
    assert policy.direct_network is False and not policy.host_allowed("kbbuddywts.kbsec.com.vn")
    assert policy.evaluate_http("GET", "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/FPT/data_day") is None
    assert policy.evaluate_http("GET", "https://hq.vnstocks.com/analytics") == worker_containment.TRANSPORT_HOST_NOT_ALLOWLISTED
    with pytest.raises(ValueError):
        worker_containment.EgressPolicy.from_endpoints(RULES, gateway={**_named_pipe_gateway(), "host": "127.0.0.1"})
    legacy = worker_containment.EgressPolicy.from_endpoints(RULES)
    assert legacy.direct_network is True and legacy.host_allowed("kbbuddywts.kbsec.com.vn")


def test_backend_static_checks_bind_manifest_record_and_runtime_roots(tmp_path):
    record = backend.HostRecord(backend.WORKER_ACCOUNT_NAME, WORKER_SID, backend.RUNTIME_ROOT,
                                backend.firewall_policy_sha256(WORKER_SID), "blob", (), {})
    instance = backend.WindowsProductionOSBackend(record)
    venv = os.path.join(backend.RUNTIME_ROOT, "runtime", "venv")
    manifest = {
        "os_containment": {"restricted_identity_sid": WORKER_SID,
                           "enforcement_backend": {"backend_id": backend.BACKEND_ID,
                                                   "contract_version": backend.BACKEND_CONTRACT_VERSION}},
        "network": {"egress_gateway": gateway.gateway_identity()}, "runtime": {"venv_root": venv},
    }
    launch = SimpleNamespace(manifest=manifest, state_root=os.path.join(backend.RUNTIME_ROOT, "state"),
                             scratch_root=os.path.join(backend.RUNTIME_ROOT, "scratch", "launch-x"),
                             interpreter=os.path.join(venv, "Scripts", "python.exe"))
    assert instance.static_violations(launch) == []
    bad = json.loads(json.dumps(manifest))
    bad["os_containment"]["restricted_identity_sid"] = "S-1-5-21-1-2-3-1001"
    bad["os_containment"]["enforcement_backend"]["backend_id"] = build_manifest.OFFLINE_FAKE_BACKEND_ID
    bad["network"]["egress_gateway"]["executable_sha256"] = "0" * 64
    codes = {item["code"] for item in instance.static_violations(SimpleNamespace(**{**vars(launch), "manifest": bad}))}
    assert {backend.R_IDENTITY_MISMATCH, backend.R_NOT_THIS_BACKEND, backend.R_GATEWAY_IDENTITY_MISMATCH} <= codes
    outside = SimpleNamespace(**{**vars(launch), "state_root": str(tmp_path), "interpreter": sys.executable})
    assert {item["field"] for item in instance.static_violations(outside)} >= {"state_root", "interpreter"}


def test_backend_refuses_a_launch_it_was_not_issued():
    record = backend.HostRecord(backend.WORKER_ACCOUNT_NAME, WORKER_SID, backend.RUNTIME_ROOT,
                                backend.firewall_policy_sha256(WORKER_SID), "blob", (), {})
    instance = backend.WindowsProductionOSBackend(record)
    with pytest.raises(backend.WindowsContainmentError):
        instance.preflight(SimpleNamespace(launch_id="x"))
    with pytest.raises(backend.WindowsContainmentError):
        instance.verify_spawned_process(SimpleNamespace(launch_id="x"), SimpleNamespace(pid=1))


# ---------------------------------------------------------------------------------------------
# Gateway core (platform-neutral).
# ---------------------------------------------------------------------------------------------


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _core(tmp_path, perform=None, clock=None, rate=20):
    calls = []

    def default_perform(method, url, headers, body):
        calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        if "/redirect/" in url:
            return gateway.UpstreamResponse(302, "Found", (("Location", "https://evil.example/"),), b"", url)
        return gateway.UpstreamResponse(200, "OK", (("Content-Type", "application/json"), ("Set-Cookie", "a=b")), b'{"ok":1}', url)

    policy = worker_containment.EgressPolicy.from_endpoints(RULES + [{**RULES[0], "path_pattern": "/redirect/{x}"}])
    core = gateway.GatewayCore(launch_id="a" * 32, egress_policy=policy, egress_policy_sha256="e" * 64, rate_per_minute=rate,
                               denied_telemetry_hosts=["hq.vnstocks.com"], perform=perform or default_perform,
                               ledger_path=str(tmp_path / "ledger.jsonl"), clock=clock or _Clock())
    return core, calls


def _hello(core):
    return core.handle({"op": gateway.OP_HELLO, "launch_id": "a" * 32, "egress_policy_sha256": "e" * 64},
                       client={"pid": 5, "sid": WORKER_SID}, greeted=False)


URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/FPT/data_day?sdate=2026-09-01&token=secret123"


def test_gateway_performs_only_the_governed_operation_with_lineage(tmp_path):
    core, calls = _core(tmp_path)
    assert _hello(core)["ok"] is True
    answer = core.handle({"op": gateway.OP_HTTP_REQUEST, "request_id": "r1", "method": "GET", "url": URL,
                          "headers": [["Accept", "application/json"], ["Cookie", "x=1"], ["Authorization", "Bearer k"],
                                      ["Host", "evil.example"], ["Proxy-Authorization", "p"], ["User-Agent", "ua"]]},
                         client={}, greeted=True)
    assert answer["ok"] is True and answer["status"] == 200
    assert base64.b64decode(answer["body_b64"]) == b'{"ok":1}'
    assert {k.lower() for k, _ in answer["headers"]} == {"content-type"}  # Set-Cookie is never returned
    sent = calls[0]["headers"]
    assert {k.lower() for k in sent} == {"accept", "user-agent", "accept-encoding"}
    lineage = answer["lineage"]
    assert lineage["request_id"] == "r1" and lineage["gateway_id"] == gateway.GATEWAY_ID and lineage["launch_id"] == "a" * 32
    assert "secret123" not in lineage["url"] and "sdate=2026-09-01" in lineage["url"]
    ledger = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    assert "secret123" not in ledger and "Bearer" not in ledger and '"PERFORMED"' in ledger


@pytest.mark.parametrize("method,url,code", [
    ("GET", "https://example.com/iis-server/investment/stocks/FPT/data_day", worker_containment.TRANSPORT_HOST_NOT_ALLOWLISTED),
    ("POST", "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/FPT/data_day", worker_containment.TRANSPORT_METHOD_NOT_ALLOWED),
    ("GET", "https://kbbuddywts.kbsec.com.vn/admin", worker_containment.TRANSPORT_PATH_NOT_ALLOWLISTED),
    ("GET", "http://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/FPT/data_day", worker_containment.TRANSPORT_SCHEME_NOT_ALLOWED),
    ("GET", "https://kbbuddywts.kbsec.com.vn:8443/iis-server/investment/stocks/FPT/data_day", worker_containment.TRANSPORT_PORT_NOT_ALLOWED),
    ("GET", "https://user:pw@kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/FPT/data_day", worker_containment.TRANSPORT_CREDENTIALS_IN_URL),
])
def test_gateway_refuses_everything_outside_the_endpoint_contract(tmp_path, method, url, code):
    core, calls = _core(tmp_path)
    answer = core.handle({"op": gateway.OP_HTTP_REQUEST, "method": method, "url": url}, client={}, greeted=True)
    assert (answer["ok"], answer["code"], answer["kind"]) == (False, code, gateway.KIND_POLICY)
    assert calls == []  # nothing left the gateway


def test_gateway_has_no_tunnel_and_requires_hello(tmp_path):
    core, calls = _core(tmp_path)
    for op in ("CONNECT", "FETCH_URL", None):
        assert core.handle({"op": op, "url": URL}, client={}, greeted=True)["code"] == gateway.R_OPERATION_NOT_GOVERNED
    assert core.handle({"op": gateway.OP_HTTP_REQUEST, "method": "GET", "url": URL}, client={}, greeted=False)["code"] == \
        gateway.R_HELLO_REQUIRED
    assert core.handle({"op": gateway.OP_HELLO, "launch_id": "b" * 32, "egress_policy_sha256": "e" * 64},
                       client={}, greeted=False)["code"] == gateway.R_LAUNCH_MISMATCH
    assert core.handle({"op": gateway.OP_HELLO, "launch_id": "a" * 32, "egress_policy_sha256": "f" * 64},
                       client={}, greeted=False)["code"] == gateway.R_POLICY_DIGEST_MISMATCH
    assert calls == []


def test_gateway_never_follows_a_redirect(tmp_path):
    core, calls = _core(tmp_path)
    answer = core.handle({"op": gateway.OP_HTTP_REQUEST, "method": "GET",
                          "url": "https://kbbuddywts.kbsec.com.vn/redirect/x"}, client={}, greeted=True)
    assert answer["code"] == gateway.R_REDIRECT_NOT_PERMITTED and answer["detail"]["status"] == 302
    assert len(calls) == 1  # the 3xx target was never requested


def test_gateway_rate_ceiling_refuses_without_sleeping(tmp_path):
    clock = _Clock()
    core, calls = _core(tmp_path, clock=clock, rate=20)
    request = {"op": gateway.OP_HTTP_REQUEST, "method": "GET", "url": URL}
    assert all(core.handle(request, client={}, greeted=True)["ok"] for _ in range(20))
    refused = core.handle(request, client={}, greeted=True)
    assert refused["code"] == gateway.R_RATE_CEILING and refused["detail"]["rate_per_minute"] == 20
    clock.now += 60.0
    assert core.handle(request, client={}, greeted=True)["ok"] is True
    assert len(calls) == 21
    with pytest.raises(ValueError):
        gateway.RateCeiling(0)


def test_gateway_telemetry_hosts_are_denied_and_counted_as_expected(tmp_path):
    core, _ = _core(tmp_path)
    answer = core.handle({"op": gateway.OP_HTTP_REQUEST, "method": "POST", "url": "https://hq.vnstocks.com/analytics"},
                         client={}, greeted=True)
    assert answer["code"] == worker_containment.TRANSPORT_HOST_NOT_ALLOWLISTED
    assert answer["detail"]["expected_telemetry_denial"] is True and core.counters["telemetry_denied"] == 1


def test_gateway_bounds_request_bodies_and_maps_upstream_failures(tmp_path):
    core, _ = _core(tmp_path)
    big = base64.b64encode(b"x" * (gateway.MAX_REQUEST_BODY_BYTES + 1)).decode("ascii")
    assert core.handle({"op": gateway.OP_HTTP_REQUEST, "method": "GET", "url": URL, "body_b64": big},
                       client={}, greeted=True)["code"] == gateway.R_BODY_TOO_LARGE

    def timeout(*_args):
        raise gateway.GatewayRefusal(gateway.R_UPSTREAM_CONNECT_TIMEOUT, gateway.KIND_UPSTREAM)

    core, _ = _core(tmp_path, perform=timeout)
    answer = core.handle({"op": gateway.OP_HTTP_REQUEST, "method": "GET", "url": URL}, client={}, greeted=True)
    assert (answer["code"], answer["kind"]) == (gateway.R_UPSTREAM_CONNECT_TIMEOUT, gateway.KIND_UPSTREAM)


def test_gateway_answers_become_requests_responses_or_requests_exceptions():
    requests = pytest.importorskip("requests")
    prepared = requests.Request("GET", URL).prepare()
    ok = gateway.answer_to_requests_response({"ok": True, "status": 200, "reason": "OK", "headers": [["Content-Type", "application/json"]],
                                              "body_b64": base64.b64encode(b'{"a":1}').decode(), "url": URL,
                                              "lineage": {"request_id": "r"}}, prepared)
    assert ok.status_code == 200 and ok.json() == {"a": 1} and ok.gateway_lineage["request_id"] == "r"
    assert list(ok.iter_content(3))
    for code, exc in ((gateway.R_UPSTREAM_CONNECT_TIMEOUT, requests.exceptions.ConnectTimeout),
                      (gateway.R_UPSTREAM_READ_TIMEOUT, requests.exceptions.ReadTimeout),
                      (gateway.R_UPSTREAM_TLS_FAILED, requests.exceptions.ConnectionError)):
        with pytest.raises(exc):
            gateway.answer_to_requests_response({"ok": False, "code": code, "kind": gateway.KIND_UPSTREAM}, prepared)
    with pytest.raises(gateway.GatewayRefusal) as refused:
        gateway.answer_to_requests_response({"ok": False, "code": gateway.R_RATE_CEILING, "kind": gateway.KIND_POLICY}, prepared)
    assert refused.value.code == gateway.R_RATE_CEILING


def test_frames_round_trip_and_reject_garbage():
    import io

    frame = gateway.encode_frame({"op": "HELLO", "x": "ü"})
    stream = io.BytesIO(frame)
    assert gateway.decode_frame(stream.read) == {"op": "HELLO", "x": "ü"}
    with pytest.raises(gateway.GatewayRefusal):
        gateway.decode_frame(io.BytesIO(b"\x03\x00\x00\x00abc").read)
    with pytest.raises(gateway.GatewayRefusal):
        gateway.decode_frame(io.BytesIO(b"\xff\xff\xff\xff").read)


def test_pipe_names_and_dacl():
    assert gateway.ipc_endpoint_for("a" * 32) == "\\\\.\\pipe\\StockLookupProviderGateway-" + "a" * 32
    with pytest.raises(ValueError):
        gateway.ipc_endpoint_for("../evil")
    sddl = gateway.pipe_sddl("S-1-5-21-1-2-3-1001", WORKER_SID)
    assert sddl.startswith("D:P(") and f"(A;;0x0012019b;;;{WORKER_SID})" in sddl and "WD" not in sddl
    assert gateway.PIPE_CLIENT_RIGHTS & 0x4 == 0  # FILE_CREATE_PIPE_INSTANCE is never granted to the worker
    with pytest.raises(ValueError):
        gateway.pipe_sddl("S-1-5-21-1-2-3-1001", "Everyone")


def test_requests_guard_forwards_allowed_requests_and_records_gateway_refusals():
    requests = pytest.importorskip("requests")
    policy = worker_containment.EgressPolicy.from_endpoints(RULES, gateway=_named_pipe_gateway())
    log = worker_containment.ContainmentEventLog()
    forwarded = []

    def forward(prepared, **_kwargs):
        forwarded.append(prepared.url)
        if "RATE" in prepared.url:
            raise gateway.GatewayRefusal(gateway.R_RATE_CEILING, gateway.KIND_POLICY)
        return gateway.answer_to_requests_response({"ok": True, "status": 200, "headers": [], "body_b64": "", "url": prepared.url},
                                                   prepared)

    uninstall = worker_containment.install_requests_transport_guard(lambda: policy, log=log, forward=forward)
    try:
        assert requests.get("https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/FPT/data_day").status_code == 200
        with pytest.raises(worker_containment.TransportPolicyViolation) as refused:
            requests.get("https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/RATE/data_day")
        assert refused.value.reason_code == gateway.R_RATE_CEILING
        with pytest.raises(worker_containment.TransportPolicyViolation):
            requests.get("https://example.com/")
    finally:
        uninstall()
    assert len(forwarded) == 2  # the unapproved host never reached the gateway
    assert [event["reason_code"] for event in log.events()] == [gateway.R_RATE_CEILING, worker_containment.TRANSPORT_HOST_NOT_ALLOWLISTED]


def test_worker_bundle_includes_the_gateway_client_and_the_draft_manifest_binds_it():
    assert "provider_egress_gateway.py" in build_manifest.WORKER_SOURCE_FILES
    manifest = json.loads((ROOT / "config" / "provider_build_manifest.json").read_text(encoding="utf-8"))
    bound = {item["relative_path"]: item for item in manifest["worker"]["source_files"]}
    for relative in build_manifest.WORKER_SOURCE_FILES:
        assert bound[relative] == build_manifest.file_identity(ROOT / relative, relative), relative
    assert manifest["status"] == build_manifest.STATUS_DRAFT and manifest["launch_authorized"] is False


# ---------------------------------------------------------------------------------------------
# Windows primitives (non-elevated, owner identity, no network).
# ---------------------------------------------------------------------------------------------


def _job(limit=1):
    api = backend.win32()
    return backend.WindowsJob.create(f"Local\\StockLookupProviderTest-{uuid.uuid4().hex}", owner_sid=api.current_sid(),
                                     active_process_limit=limit)


@windows_only
def test_job_limits_are_read_back_and_a_name_cannot_be_squatted():
    job = _job(limit=2)
    try:
        limits = job.limits()
        assert limits["kill_on_job_close"] and not limits["breakaway_ok"] and not limits["silent_breakaway_ok"]
        assert limits["active_process_limit"] == 2 and job.limit_violations() == []
        assert backend.local_job_name(job.kernel_name()) == job.name
        with pytest.raises(backend.WindowsContainmentError):
            backend.WindowsJob.create(job.name, owner_sid=backend.win32().current_sid(), active_process_limit=1)
    finally:
        job.close()


@windows_only
def test_suspended_spawn_assign_verify_resume_and_kill_the_whole_job(tmp_path):
    job = _job(limit=2)
    script = "import sys,subprocess;print(sys.stdin.readline().strip()[::-1], flush=True);sys.stdin.readline()"
    seen = {}

    def before_resume(handle, pid):
        seen["in_job_before_resume"] = job.contains(handle)
        seen["pids_before_resume"] = job.pids()

    process = backend.spawn_suspended_in_job(
        spawner=backend.SameIdentitySpawner(), argv=[sys.executable, "-I", "-S", "-c", script],
        environment={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")}, cwd=str(tmp_path), job=job,
        launch_id=None, before_resume=before_resume)
    try:
        assert seen["in_job_before_resume"] is True and seen["pids_before_resume"] == [process.pid]
        process.stdin.write("olleh\n")
        process.stdin.flush()
        assert process.stdout.readline().strip() == "hello"
        members = backend.classify_job_members(job.pids(), process.pid, backend.win32().process_snapshot())
        assert members["interpreter_pid"] == process.pid
        assert {item["source"] for item in backend.win32().process_identity(process.handle) if item["sid"]} >= {"OS_PROCESS_QUERY"}
        assert process.poll() is None
        process.kill()  # the whole Job
        assert process.wait(timeout=15) == 1
    finally:
        process.kill()


@windows_only
def test_kill_on_job_close_ends_the_worker_without_terminate(tmp_path):
    job = _job(limit=1)
    process = backend.spawn_suspended_in_job(
        spawner=backend.SameIdentitySpawner(), argv=[sys.executable, "-I", "-S", "-c", "import sys;sys.stdin.readline()"],
        environment={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")}, cwd=str(tmp_path), job=job, launch_id=None)
    assert process.poll() is None
    job.close()
    assert process.api.WaitForSingleObject(process.handle, 15000) == 0


@windows_only
def test_kernel_access_check_reads_a_real_descriptor(tmp_path):
    api = backend.win32()
    token = api.self_identification_token()
    try:
        granted = api.effective_access(str(tmp_path), token)
    finally:
        api.CloseHandle(token)
    assert granted & backend.FILE_READ_DATA and granted & backend.FILE_WRITE_DATA


@windows_only
def test_named_pipe_gateway_serves_a_job_member_and_refuses_everyone_else(tmp_path):
    api = backend.win32()
    owner_sid = api.current_sid()
    launch_id = uuid.uuid4().hex
    job = _job(limit=1)
    policy = worker_containment.EgressPolicy.from_endpoints(RULES)

    def perform(method, url, headers, body):
        return gateway.UpstreamResponse(200, "OK", (("Content-Type", "text/plain"),), b"fake-upstream", url)

    core = gateway.GatewayCore(launch_id=launch_id, egress_policy=policy, egress_policy_sha256="e" * 64, rate_per_minute=20,
                               perform=perform, ledger_path=str(tmp_path / "ledger.jsonl"))
    # The test process's identity plays the worker SID here; Job membership still decides.
    server = gateway.NamedPipeGatewayServer(core, pipe_name=gateway.ipc_endpoint_for(launch_id), owner_sid=owner_sid,
                                            worker_sid=owner_sid, client_pid_allowed=lambda pid: pid in job.pids())
    server.start()
    try:
        outsider = gateway.NamedPipeGatewayClient(pipe_name=server.pipe_name, launch_id=launch_id,
                                                  egress_policy_sha256="e" * 64, expected_server_pid=server.server_pid)
        with pytest.raises(gateway.GatewayRefusal):
            outsider.connect()
        outsider.close()
        deadline = time.monotonic() + 5
        while not server.rejected_clients and time.monotonic() < deadline:  # recorded on the server thread
            time.sleep(0.05)
        assert server.rejected_clients[-1]["pid"] == os.getpid()
        assert server.rejected_clients[-1]["reason"] == "CLIENT_PROCESS_NOT_IN_LAUNCH_JOB"
        with pytest.raises(gateway.GatewayRefusal) as squatted:  # FIRST_PIPE_INSTANCE: a second server is refused
            gateway.NamedPipeGatewayServer(core, pipe_name=server.pipe_name, owner_sid=owner_sid, worker_sid=owner_sid,
                                           client_pid_allowed=lambda pid: False).start()
        assert squatted.value.code == gateway.R_PIPE_ALREADY_EXISTS
        client_code = textwrap.dedent(f"""
            import json, sys
            sys.path.insert(0, {str(ROOT)!r})
            import provider_egress_gateway as g
            c = g.NamedPipeGatewayClient(pipe_name={server.pipe_name!r}, launch_id={launch_id!r},
                                         egress_policy_sha256="e" * 64, expected_server_pid={server.server_pid})
            out = {{"hello": c.connect()}}
            url = "https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/FPT/data_day"
            out["allowed"] = c.request(method="GET", url=url, headers=[], body=None)
            out["denied"] = c.request(method="GET", url="https://hq.vnstocks.com/analytics", headers=[], body=None)
            print(json.dumps(out), flush=True)
        """)
        process = backend.spawn_suspended_in_job(
            spawner=backend.SameIdentitySpawner(), argv=[sys.executable, "-I", "-S", "-c", client_code],
            environment={"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")}, cwd=str(tmp_path), job=job,
            launch_id=launch_id)
        try:
            result = json.loads(process.stdout.readline())
            process.wait(timeout=30)
        finally:
            process.kill()
        assert result["hello"]["server_pid"] == os.getpid() and result["hello"]["gateway_id"] == gateway.GATEWAY_ID
        assert result["allowed"]["ok"] is True and base64.b64decode(result["allowed"]["body_b64"]) == b"fake-upstream"
        assert result["denied"]["code"] == worker_containment.TRANSPORT_HOST_NOT_ALLOWLISTED
        accepted = [item for item in server.accepted_clients if item["pid"] == process.pid]
        assert accepted and accepted[0]["sid"] == owner_sid  # read back by impersonating the client
        assert server.identity()["server_is_this_process"] is True
    finally:
        server.stop()
        job.close()


@windows_only
def test_provisioning_script_digest_matches_the_backend_and_plan_mutates_nothing():
    script = ROOT / "tools" / "provision_provider_os_containment.ps1"
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                                str(script), "-SelfTestDigestSid", WORKER_SID], capture_output=True, text=True, timeout=120)
    assert completed.stdout.strip() == backend.firewall_policy_sha256(WORKER_SID)


# ---------------------------------------------------------------------------------------------
# Provisioning script: parameter limits, resumable/idempotent APPLY, completion marker last.
# ---------------------------------------------------------------------------------------------

PROVISION_SCRIPT = ROOT / "tools" / "provision_provider_os_containment.ps1"


def _ps_constant(text, name):
    import re

    match = re.search(rf"^\${name}\s*=\s*'([^']*)'", text, re.MULTILINE)
    assert match, name
    return match.group(1)


def test_provisioning_constants_fit_the_local_accounts_parameter_limits():
    # Regression (owner APPLY 2026-09-26): New-LocalUser -Description is ValidateLength(0, 48).
    text = PROVISION_SCRIPT.read_text(encoding="utf-8")
    assert len(_ps_constant(text, "AccountDescription")) <= 48
    name = _ps_constant(text, "AccountName")
    assert len(name) <= 20 and name == backend.WORKER_ACCOUNT_NAME
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if "-Description" in line and "LocalUser" in line:
            assert "-Description $AccountDescription" in line, line
        if line.strip().startswith("-FullName"):
            assert "-Description $AccountDescription" in line, line  # never an inline literal


def test_provisioning_writes_the_completion_record_only_after_verification_and_never_deletes():
    text = PROVISION_SCRIPT.read_text(encoding="utf-8")
    apply_body = text.split("function Invoke-Apply", 1)[1].split("function Test-Provisioned", 1)[0]
    assert "Write-CompletionRecord" not in apply_body and "WriteAllText" not in apply_body
    main = text.split("# --- main ---", 1)[1]
    assert main.index("$failures = Test-Provisioned $sid") < main.index("Write-CompletionRecord $sid")
    assert main.index("exit 2") < main.index("Write-CompletionRecord $sid")
    # A pre-existing record is moved aside before any mutation; nothing is ever removed.
    assert apply_body.index("SUPERSEDE_THEN_WRITE_LAST") < apply_body.index("New-Item -ItemType Directory")
    for verb in ("Remove-NetFirewallRule", "Remove-LocalUser", "Remove-Item", "RemoveAccessRule", "Disable-NetFirewall"):
        assert verb not in text, verb


def test_qualification_reports_partial_provisioning_without_a_completion_record(monkeypatch, tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("qualification_tool", ROOT / "tools" / "run_provider_os_containment_qualification.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    runtime = tmp_path / "StockLookup" / "provider-runtime"
    monkeypatch.setattr(backend, "RUNTIME_ROOT", str(runtime))
    monkeypatch.setattr(backend, "HOST_RECORD_PATH", str(runtime / "host" / "provisioning_record.json"))
    assert tool.qualify(harness_root=None, owner_profile=str(tmp_path))["status"] == tool.NOT_PROVISIONED
    (runtime / "host").mkdir(parents=True)
    report = tool.qualify(harness_root=None, owner_profile=str(tmp_path))
    assert report["status"] == tool.PARTIAL_PROVISIONING and str(runtime) in report["leftovers"]
    assert {item["outcome"] for item in report["results"].values()} == {tool.NOT_PROVISIONED}


DENY_ROOT = "C:\\Projects\\StockLookup"


def _deny_root(**overrides):
    root = {"path": DENY_ROOT, "exists": True, "explicit_deny": False, "explicit_allow": False}
    root.update(overrides)
    return root


def _observed(**overrides):
    state = {
        "elevated": True, "current_sid": "S-1-5-21-1-2-3-1001",
        "account": {"exists": False, "sid": None, "description": None, "enabled": None, "groups": []},
        "programdata_children": [], "runtime_root_exists": False, "blob_exists": False,
        "record": {"exists": False, "worker_sid": None}, "rule": {"exists": False}, "group_rules": [],
        "firewall_profiles": [], "deny_roots": [_deny_root()], "seclogon_start_mode": "Manual",
    }
    state.update(overrides)
    return state


def _our_account(**overrides):
    text = PROVISION_SCRIPT.read_text(encoding="utf-8")
    account = {"exists": True, "sid": WORKER_SID, "description": _ps_constant(text, "AccountDescription"), "enabled": True,
               "groups": ["S-1-5-32-545"]}
    account.update(overrides)
    return account


def _exact_rule(sid=WORKER_SID, **overrides):
    rule = {"exists": True, "enabled": "True", "direction": "Outbound", "action": "Block", "profile": "Any",
            "group": backend.FIREWALL_GROUP, "protocol": "Any", "remote_address": ["Any"], "local_address": ["Any"],
            "program": "Any", "local_user": f"D:(A;;CC;;;{sid})"}
    rule.update(overrides)
    return rule


def _plan(tmp_path, state):
    fixture = tmp_path / f"observed-{uuid.uuid4().hex}.json"
    fixture.write_text(json.dumps(state), encoding="utf-8")
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                                str(PROVISION_SCRIPT), "-SelfTestPlanFixture", str(fixture)],
                               capture_output=True, text=True, timeout=120)
    return json.loads(completed.stdout.strip().splitlines()[-1])


@windows_only
def test_provisioning_script_parses_and_its_constants_pass_the_live_cmdlet_limits():
    command = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
               f"'{PROVISION_SCRIPT}', [ref]$null, [ref]$e); $e.Count")
    parsed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, timeout=120)
    assert parsed.stdout.strip() == "0", parsed.stdout + parsed.stderr
    limits = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                             str(PROVISION_SCRIPT), "-SelfTestParameterLimits"], capture_output=True, text=True, timeout=120)
    observed = json.loads(limits.stdout)
    assert observed["New-LocalUser -Description"]["max"] == 48
    assert all(item["ok"] for item in observed.values()), observed


@windows_only
def test_provisioning_plan_fresh_resume_and_idempotent(tmp_path):
    fresh = _plan(tmp_path, _observed())
    assert fresh["ok"] and fresh["actions"]["account"] == "CREATE" and fresh["actions"]["secret"] == "GENERATE_AND_STORE"
    assert fresh["actions"]["firewall"] == "CREATE" and fresh["actions"]["record"] == "WRITE_LAST"
    assert set(fresh["actions"]["deny_aces"].values()) == {"ADD"}
    # Interrupted after the account was created, before its secret was stored: reset once, complete the rest.
    resumed = _plan(tmp_path, _observed(account=_our_account(), runtime_root_exists=True,
                                        programdata_children=["provider-runtime"]))
    assert resumed["ok"] and resumed["actions"]["account"] == "REUSE_VERIFIED"
    assert resumed["actions"]["secret"] == "RESET_AND_STORE"
    assert resumed["actions"]["directories"] == "COMPLETE_AND_CONVERGE_ACLS"
    # Interrupted after the secret was stored: the blob is kept (validated at apply), never rotated.
    kept = _plan(tmp_path, _observed(account=_our_account(), runtime_root_exists=True, blob_exists=True))
    assert kept["actions"]["secret"] == "KEEP_EXISTING_BLOB_AFTER_VALIDATION"
    # Fully provisioned: nothing is created or added again; the record is superseded, then rewritten last.
    complete = _plan(tmp_path, _observed(
        account=_our_account(), runtime_root_exists=True, blob_exists=True, programdata_children=["provider-runtime"],
        record={"exists": True, "worker_sid": WORKER_SID}, rule=_exact_rule(), group_rules=[backend.FIREWALL_RULE_NAME],
        deny_roots=[_deny_root(explicit_deny=True)]))
    actions = complete["actions"]
    assert complete["ok"] and actions["account"] == "REUSE_VERIFIED"
    assert actions["secret"] == "KEEP_EXISTING_BLOB_AFTER_VALIDATION"
    assert actions["firewall"] == "PRESENT_EXACT" and set(actions["deny_aces"].values()) == {"PRESENT"}
    assert actions["record"] == "SUPERSEDE_THEN_WRITE_LAST"


CONFLICTS = {
    "foreign_account": ({"account": "FOREIGN"}, "ACCOUNT_CONFLICT"),
    "admin_member": ({"account": "ADMIN_MEMBER"}, "ACCOUNT_CONFLICT"),
    "allow_rule": ({"account": "OURS", "rule": "ALLOW_RULE"}, "FIREWALL_CONFLICT"),
    "other_sid_rule": ({"account": "OURS", "rule": "OTHER_SID_RULE"}, "FIREWALL_CONFLICT"),
    "extra_group_rule": ({"group_rules": [backend.FIREWALL_RULE_NAME, "Someone-Else"]}, "FIREWALL_CONFLICT"),
    "unrelated_programdata": ({"programdata_children": ["provider-runtime", "unrelated-app"]}, "RUNTIME_ROOT_CONFLICT"),
    "other_worker_ace": ({"account": "OURS", "deny_roots": "OTHER_ACE"}, "ACL_CONFLICT"),
    "record_other_sid": ({"account": "OURS", "record": {"exists": True, "worker_sid": "S-1-5-21-9-9-9-1234"}}, "RECORD_CONFLICT"),
    "record_without_account": ({"record": {"exists": True, "worker_sid": WORKER_SID}}, "RECORD_CONFLICT"),
    "deny_root_missing": ({"deny_roots": "MISSING"}, "DENY_ROOT_MISSING"),
}


@windows_only
@pytest.mark.parametrize("case", sorted(CONFLICTS))
def test_provisioning_plan_fails_closed_on_conflicting_state(tmp_path, case):
    overrides, code = CONFLICTS[case]
    resolved = dict(overrides)
    accounts = {"OURS": _our_account(), "FOREIGN": _our_account(description="someone else's account"),
                "ADMIN_MEMBER": _our_account(groups=["S-1-5-32-545", "S-1-5-32-544"])}
    if "account" in resolved:
        resolved["account"] = accounts[resolved["account"]]
    rules = {"ALLOW_RULE": _exact_rule(action="Allow"), "OTHER_SID_RULE": _exact_rule(sid="S-1-5-21-9-9-9-1234")}
    if "rule" in resolved:
        resolved["rule"] = rules[resolved["rule"]]
    roots = {"OTHER_ACE": [_deny_root(explicit_allow=True)], "MISSING": [_deny_root(exists=False)]}
    if isinstance(resolved.get("deny_roots"), str):
        resolved["deny_roots"] = roots[resolved["deny_roots"]]
    result = _plan(tmp_path, _observed(**resolved))
    assert result["ok"] is False and f"PROVISIONING_REFUSED:{code}" in result["refused"], result


# ---------------------------------------------------------------------------------------------
# Post-provision verifier (owner APPLY 2026-09-26: ACCOUNT; FIREWALL_RULE; DENY_ACE failed while the
# host state was exact). Root cause: Invoke-Apply's Write-Step lines are pipeline output, so
# `$sid = Invoke-Apply ...` captured "[provision] ... [provision] ... S-1-5-21-...". The fixtures
# below are the Windows-native read-back representations measured on that host.
# ---------------------------------------------------------------------------------------------

HOST_WORKER_SID = "S-1-5-21-270160003-185743851-2814889227-1005"
POLLUTED_SID = ("[provision] creating local account StockLookupProvider [provision] adding worker deny ACE on "
                "C:\\Projects\\StockLookup (propagating) " + HOST_WORKER_SID)


def _host_ace(**overrides):
    # Get-Acl .Access for (D;OICI;FA;;;<worker>) on C:\Projects\StockLookup, normalized to strings.
    ace = {"sid": HOST_WORKER_SID, "type": "Deny", "rights": "FullControl",
           "inheritance": "ContainerInherit, ObjectInherit", "propagation": "None", "inherited": False}
    ace.update(overrides)
    return ace


def _host_observation(**overrides):
    text = PROVISION_SCRIPT.read_text(encoding="utf-8")
    runtime = "C:\\ProgramData\\StockLookup\\provider-runtime"
    observed = {
        "account": {"exists": True, "sid": HOST_WORKER_SID, "enabled": True,
                    "description": _ps_constant(text, "AccountDescription"), "groups": ["S-1-5-32-545"]},
        "dirs": [{"path": p, "exists": True, "protected": True} for p in
                 [runtime] + [f"{runtime}\\{name}" for name in ("host", "runtime", "state", "scratch", "gateway-ledger", "evidence")]],
        "blob_exists": True,
        "rule": _exact_rule(sid=HOST_WORKER_SID),
        "group_rule_count": 1,
        "deny_roots": [{"path": DENY_ROOT, "exists": True, "aces": [
            {"sid": "S-1-5-18", "type": "Allow", "rights": "FullControl", "inheritance": "ContainerInherit, ObjectInherit",
             "propagation": "None", "inherited": True},
            _host_ace()]}],
    }
    observed.update(overrides)
    return observed


def _verify(tmp_path, observed, sid=HOST_WORKER_SID):
    fixture = tmp_path / f"verify-{uuid.uuid4().hex}.json"
    fixture.write_text(json.dumps({"sid": sid, "observed": observed}), encoding="utf-8")
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                                str(PROVISION_SCRIPT), "-SelfTestVerifyFixture", str(fixture)],
                               capture_output=True, text=True, timeout=120)
    return json.loads(completed.stdout.strip().splitlines()[-1])["failures"]


@windows_only
def test_post_provision_verifier_accepts_the_exact_windows_readback_of_this_host(tmp_path):
    assert _verify(tmp_path, _host_observation()) == []


@windows_only
def test_post_provision_verifier_refuses_a_pipeline_polluted_sid_explicitly(tmp_path):
    # The exact string the pre-fix main passed: now a named failure, never a silent mismatch.
    assert _verify(tmp_path, _host_observation(), sid=POLLUTED_SID) == ["WORKER_SID_MALFORMED"]
    assert _verify(tmp_path, _host_observation(), sid="") == ["WORKER_SID_MALFORMED"]


def _one_root(*aces):
    return [{"path": DENY_ROOT, "exists": True, "aces": list(aces)}]


@windows_only
@pytest.mark.parametrize("case,expected", [
    ("disabled", "ACCOUNT"), ("other_sid", "ACCOUNT"), ("admin_group", "GROUP:S-1-5-32-544"),
    ("rule_other_sid", "FIREWALL_RULE"), ("rule_disabled", "FIREWALL_RULE"), ("extra_group_rule", "FIREWALL_GROUP"),
    ("deny_inherited_only", f"DENY_ACE:{DENY_ROOT}"), ("deny_inherit_only_propagation", f"DENY_ACE:{DENY_ROOT}"),
    ("deny_not_full", f"DENY_ACE:{DENY_ROOT}"), ("deny_plus_allow", f"DENY_ACE:{DENY_ROOT}"), ("no_deny", f"DENY_ACE:{DENY_ROOT}"),
    ("unprotected_dir", "ACL_NOT_PROTECTED:C:\\ProgramData\\StockLookup\\provider-runtime"), ("no_blob", "CREDENTIAL_BLOB"),
])
def test_post_provision_verifier_still_fails_on_genuinely_wrong_enforcement(tmp_path, case, expected):
    observed = _host_observation()
    account = dict(observed["account"])
    if case == "disabled":
        account["enabled"] = False
    elif case == "other_sid":
        account["sid"] = "S-1-5-21-270160003-185743851-2814889227-1006"
    elif case == "admin_group":
        account["groups"] = ["S-1-5-32-545", "S-1-5-32-544"]
    observed["account"] = account
    if case == "rule_other_sid":
        observed["rule"] = _exact_rule(sid="S-1-5-21-270160003-185743851-2814889227-1006")
    elif case == "rule_disabled":
        observed["rule"] = _exact_rule(sid=HOST_WORKER_SID, enabled="False")
    elif case == "extra_group_rule":
        observed["group_rule_count"] = 2
    elif case == "deny_inherited_only":  # (D;OICIID;FA;;;<worker>) as read back on a child
        observed["deny_roots"] = _one_root(_host_ace(inherited=True))
    elif case == "deny_inherit_only_propagation":
        observed["deny_roots"] = _one_root(_host_ace(propagation="InheritOnly"))
    elif case == "deny_not_full":
        observed["deny_roots"] = _one_root(_host_ace(rights="Write, Synchronize"))
    elif case == "deny_plus_allow":
        observed["deny_roots"] = _one_root(_host_ace(), _host_ace(type="Allow", rights="ReadAndExecute, Synchronize"))
    elif case == "no_deny":
        observed["deny_roots"] = _one_root()
    elif case == "unprotected_dir":
        observed["dirs"] = [dict(observed["dirs"][0], protected=False)] + observed["dirs"][1:]
    elif case == "no_blob":
        observed["blob_exists"] = False
    assert _verify(tmp_path, observed) == [expected]


def test_apply_returns_no_pipeline_value_and_main_rereads_the_worker_sid():
    text = PROVISION_SCRIPT.read_text(encoding="utf-8")
    apply_body = text.split("function Invoke-Apply", 1)[1].split("function Resolve-ProvisionedWorkerSid", 1)[0]
    assert "Write-Step" in apply_body  # its steps are pipeline output, so it must not return a value
    assert not any(line.strip().startswith("return") for line in apply_body.splitlines())
    main = text.split("# --- main ---", 1)[1]
    assert "= Invoke-Apply" not in main
    assert main.index("$sid = Resolve-ProvisionedWorkerSid $state") < main.index("$failures = Test-Provisioned $sid")
    record = text.split("function Write-CompletionRecord", 1)[1].split("\n}", 1)[0]
    assert "Test-WorkerSidShape $Sid" in record
