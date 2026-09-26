"""Throwaway fake provider venv/runtime for APPROVED_PROVIDER_BUILD_AND_EXECUTION_BOUNDARY_V1.

No pip, no network, no real vnstock/vnai. ``python -m venv --without-pip`` plus planted fake
distributions is enough to exercise attestation, containment, credential/rate binding,
revocation and offline qualification.

Two launch styles share one cached fake venv:

* ``protocol`` -- attested launch whose bundled entrypoint is ``tests/fixtures/fake_vnstock_worker.py``
  (existing isolation/client tests keep their ticker-prefix protocol).
* ``governed`` -- attested launch of the real ``vnstock_worker_process.py`` against the fake
  packages (Gate B / self-attestation / containment qualification).
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import provider_build_manifest as build_manifest
import provider_runtime_state as runtime_contract
import vnstock_worker_client as worker_client

ROOT = Path(__file__).resolve().parents[1]
FAKE_WORKER = Path(__file__).with_name("fixtures") / "fake_vnstock_worker.py"
FAKE_WORKER_RELATIVE = "tests/fixtures/fake_vnstock_worker.py"
MODE_OFFLINE_FAKE = "OFFLINE_FAKE_PROVIDER_QUALIFICATION"
TEST_DECISION_ID = "TEST_FIXTURE_PROVIDER_BUILD_DECISION"
TEST_BUILD_ID = "VNSTOCK_KBS_VCI-TEST-FIXTURE-UNAPPROVED-NOT-A-LIVE-BUILD"
FAKE_ENDPOINT_HOST = "fake-provider.test"
FAKE_ENDPOINT_PATH = "/ohlc/{symbol}"
FAKE_ENDPOINT_URL = f"https://{FAKE_ENDPOINT_HOST}{FAKE_ENDPOINT_PATH}"
PROTOCOL_CONTROL_ENV = (
    "FAKE_WORKER_STARTUP_FAIL",
    "FAKE_WORKER_STARTUP_KIND",
    "FAKE_WORKER_STARTUP_HANG",
    "FAKE_WORKER_READY_GARBAGE",
    "FAKE_WORKER_REPORT_ENV",
)
_VENV_CACHE: Path | None = None
_LIVE: list["FakeProviderRuntime"] = []


def _probe_env() -> dict[str, str]:
    env = {}
    for name in ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC"):
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _site_dir(venv_root: Path, *, os_name: str = os.name) -> Path:
    if os_name == "nt":
        return venv_root / "Lib" / "site-packages"
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return venv_root / "lib" / version / "site-packages"


def _venv_python(venv_root: Path) -> Path:
    return venv_root / "Scripts" / "python.exe" if os.name == "nt" else venv_root / "bin" / "python"


def _write(path: Path, body: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, bytes):
        path.write_bytes(body)
    else:
        path.write_text(body, encoding="utf-8")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plant_distribution(site: Path, name: str, version: str, files: Mapping[str, str | bytes]) -> dict[str, Any]:
    """Write a fake installed distribution (modules + dist-info METADATA/RECORD). No wheel, no pip."""
    written: list[Path] = []
    for relative, body in files.items():
        path = site / relative
        _write(path, body)
        written.append(path)
    dist_info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    metadata = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nSummary: TEST_FIXTURE_ONLY fake {name}\n"
    )
    _write(dist_info / "METADATA", metadata)
    record_lines = []
    for path in [*written, dist_info / "METADATA"]:
        relative = path.relative_to(site).as_posix()
        digest = build_manifest.sha256_file(path)
        record_lines.append(f"{relative},sha256={digest},{path.stat().st_size}")
    record_lines.append(f"{dist_info.name}/RECORD,,")
    _write(dist_info / "RECORD", "\n".join(record_lines) + "\n")
    return {
        "name": name,
        "version": version,
        "dist_info": dist_info.name,
        "site_dir": "Lib/site-packages" if os.name == "nt" else _posix_site_rel(site),
        "installed_manifest_sha256": build_manifest.distribution_manifest_sha256(site, dist_info.name),
        "artifact_filename": f"{name}-{version}-py3-none-any.whl",
        "artifact_sha256": _sha256_text(f"TEST_FIXTURE_ARTIFACT:{name}:{version}"),
        "artifact_size": 1,
        "artifact_source_url": f"https://{FAKE_ENDPOINT_HOST}/wheels/{name}-{version}-py3-none-any.whl",
        "native_manifest_sha256": None,
        "provenance_classification": "TEST_FIXTURE_ONLY",
        "provenance_evidence_sha256": None,
        "requires_dist": [],
    }


def _posix_site_rel(site: Path) -> str:
    # Relative to venv root; used only when not on Windows.
    return site.relative_to(site.parents[2] if "site-packages" in site.name else site.parent).as_posix()


_FAKE_REQUESTS = '''
class Request:
    def __init__(self, method, url):
        self.method = method
        self.url = url

class Response:
    def __init__(self, status_code=200, payload=None, headers=None, url=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = dict(headers or {})
        self.url = url
        self.is_redirect = 300 <= status_code < 400
        self.is_permanent_redirect = status_code in (301, 308)
    def json(self):
        return self._payload
    def close(self):
        return None

class Session:
    def request(self, method, url, **kwargs):
        return self.send(Request(method, url), **kwargs)
    def send(self, request, **kwargs):
        return Response(200, {"status": "fake-ok"}, url=getattr(request, "url", ""))
    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)
    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

def get(url, **kwargs):
    return Session().get(url, **kwargs)

def post(url, **kwargs):
    return Session().post(url, **kwargs)

class exceptions:
    class RequestException(Exception):
        pass
    class Timeout(RequestException):
        pass
    class ConnectTimeout(Timeout):
        pass
    class ReadTimeout(Timeout):
        pass
    class ConnectionError(RequestException):
        pass
'''

_FAKE_PANDAS = '''
class DataFrame:
    def __init__(self, data=None, **kwargs):
        if isinstance(data, list):
            self._rows = list(data)
        elif isinstance(data, dict):
            keys = list(data)
            length = len(next(iter(data.values()), []))
            self._rows = [{key: data[key][i] for key in keys} for i in range(length)]
        else:
            self._rows = []
        self.attrs = {}
        self.columns = list(self._rows[0]) if self._rows else []
    def __len__(self):
        return len(self._rows)
    def __getitem__(self, key):
        if isinstance(key, str):
            return [row.get(key) for row in self._rows]
        return self
    @property
    def iloc(self):
        return self
    def to_json(self, orient=None, date_format=None):
        import json
        return json.dumps(self._rows)
'''

_FAKE_VNSTOCK = '''
"""TEST_FIXTURE_ONLY fake vnstock. Never a real vendor package."""
from vnstock.core.utils import client as client  # noqa: F401 -- re-exported for the adapter patch

class _Provider:
    def __init__(self, symbol, source):
        self.symbol = symbol
        self.source = source
    def history(self, start=None, end=None, interval=None):
        from vnstock.core.utils import client as client_mod
        url = "https://fake-provider.test/ohlc/" + str(self.symbol)
        payload = client_mod.send_request_direct(url, headers={}, method="GET")
        rows = (payload or {}).get("rows") or [{
            "time": "2026-09-10", "open": 10000, "high": 10200, "low": 9900, "close": 10100,
            "volume": 123456,
        }]
        import pandas as pd
        return pd.DataFrame(rows)

class Quote:
    def __init__(self, symbol, source, random_agent=True):
        self.symbol = symbol
        self.source = source
        self.provider = _Provider(symbol, source)

class Listing:
    def __init__(self, source="VCI"):
        self.source = source
    def symbols_by_exchange(self):
        import pandas as pd
        return pd.DataFrame({"symbol": [], "type": []})
'''

_FAKE_VNSTOCK_CLIENT = '''
def send_request_direct(url, headers, method="GET", params=None, payload=None, timeout=30, proxies=None):
    raise AssertionError("FAKE_VNSTOCK_CLIENT_UNPATCHED")
'''

_FAKE_VNSTOCK_UPGRADE = '''
def update_notice(verbose=False):
    return None
def migrate_to_sponsor(target_dir="."):
    return None
'''

_FAKE_VNAI_TEMPLATE = '''
"""TEST_FIXTURE_ONLY fake vnai. Attempts the vendor start-up side effects under containment.

With _PROBE_OWNER_PROFILE it also tries the owner-profile secrets (an unexpected denial: the
worker must fail closed). Without it, only the manifest-declared telemetry/process side effects
are attempted (expected denials: the worker must reach READY)."""
import os
import subprocess
from pathlib import Path

_OWNER_PROFILE = {owner_profile!r}
_PROBE_OWNER_PROFILE = {probe_owner_profile!r}
_TELEMETRY_URL = "https://hq.vnstocks.com/analytics"

def setup():
    if _PROBE_OWNER_PROFILE:
        try:
            Path(_OWNER_PROFILE).joinpath(".vnstock", "api_key.json").read_text(encoding="utf-8")
        except Exception:
            pass
        try:
            Path(_OWNER_PROFILE).joinpath(".stocklookup", "secrets.env").read_text(encoding="utf-8")
        except Exception:
            pass
    try:
        import urllib.request
        urllib.request.urlopen(_TELEMETRY_URL, timeout=1)
    except Exception:
        pass
    try:
        subprocess.Popen(["git", "status"])
    except Exception:
        pass
    try:
        subprocess.run(["python", "-c", "pass"], check=False)
    except Exception:
        pass
'''


def _tzif_fixed_offset(offset_seconds: int, abbreviation: str, posix_tz: str) -> bytes:
    """Minimal RFC 8536 TZif v2 zone: no transitions, one local-time type, POSIX TZ footer."""
    abbr = abbreviation.encode("ascii") + b"\0"

    def block() -> bytes:
        header = b"TZif2" + b"\0" * 15 + struct.pack(">6l", 0, 0, 0, 0, 1, len(abbr))
        return header + struct.pack(">lBB", offset_seconds, 0, 0) + abbr

    return block() + block() + b"\n" + posix_tz.encode("ascii") + b"\n"


# The real worker imports vn_time (a bundled worker source), which builds
# ZoneInfo("Asia/Ho_Chi_Minh") at import. Windows has no system tz database, so the governed
# runtime needs the ``tzdata`` distribution -- pinned in the tracked candidate lock (tzdata 2025.3,
# pandas Requires-Dist ``tzdata>=2022.7``, member of RUNTIME_MINIMAL_23). The fake mirrors the
# real package layout that zoneinfo resolves (``tzdata.zoneinfo.Asia`` / ``Ho_Chi_Minh``).
_FAKE_TZDATA_FILES: dict[str, str | bytes] = {
    "tzdata/__init__.py": 'IANA_VERSION = "TEST_FIXTURE_ONLY"\n',
    "tzdata/zoneinfo/__init__.py": "",
    "tzdata/zoneinfo/Asia/__init__.py": "",
    "tzdata/zoneinfo/Asia/Ho_Chi_Minh": _tzif_fixed_offset(7 * 3600, "+07", "<+07>-7"),
}


def _plant_fake_packages(
    site: Path, *, owner_profile: str, include_tzdata: bool = True, vnai_probes_owner_profile: bool = True,
) -> list[dict[str, Any]]:
    packages = []
    if include_tzdata:
        packages.append(_plant_distribution(site, "tzdata", "0.0.0", _FAKE_TZDATA_FILES))
    packages.append(_plant_distribution(site, "requests", "0.0.0", {
        "requests/__init__.py": _FAKE_REQUESTS,
        "requests/sessions.py": "from requests import Session, Request, Response\n",
    }))
    packages.append(_plant_distribution(site, "pandas", "0.0.0", {
        "pandas/__init__.py": _FAKE_PANDAS,
    }))
    packages.append(_plant_distribution(site, "vnstock", "0.0.0", {
        "vnstock/__init__.py": "from vnstock.api.quote import Quote\nfrom vnstock.api.listing import Listing\nfrom vnstock.core.utils import upgrade as _upgrade\n_upgrade.update_notice(verbose=False)\n",
        "vnstock/api/__init__.py": "",
        "vnstock/api/quote.py": _FAKE_VNSTOCK,
        "vnstock/api/listing.py": "from vnstock.api.quote import Listing\n",
        "vnstock/core/__init__.py": "",
        "vnstock/core/utils/__init__.py": "",
        "vnstock/core/utils/client.py": _FAKE_VNSTOCK_CLIENT,
        "vnstock/core/utils/upgrade.py": _FAKE_VNSTOCK_UPGRADE,
    }))
    packages.append(_plant_distribution(site, "vnai", "0.0.0", {
        "vnai/__init__.py": _FAKE_VNAI_TEMPLATE.format(
            owner_profile=owner_profile, probe_owner_profile=vnai_probes_owner_profile,
        ),
    }))
    return sorted(packages, key=lambda item: item["name"])


def _create_venv(venv_root: Path) -> Path:
    venv_root.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv_root)],
        capture_output=True, text=True, env=_probe_env() or None, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"FAKE_PROVIDER_VENV_CREATE_FAILED:{completed.stderr[-400:]}")
    python = _venv_python(venv_root)
    if not python.is_file():
        raise RuntimeError(f"FAKE_PROVIDER_VENV_PYTHON_MISSING:{python}")
    return python


def cached_fake_venv(*, owner_profile: str) -> Path:
    """Process-cached fake venv. Recreated only when missing (packages include owner-profile path)."""
    global _VENV_CACHE
    if _VENV_CACHE is not None and (_VENV_CACHE / "pyvenv.cfg").is_file():
        marker = _VENV_CACHE / "Lib" / "site-packages" / "vnai" / "__init__.py"
        if not marker.is_file():
            marker = next(_VENV_CACHE.glob("lib/python*/site-packages/vnai/__init__.py"), None)
        if marker is not None and marker.is_file() and owner_profile in marker.read_text(encoding="utf-8"):
            return _VENV_CACHE
    root = Path(tempfile.mkdtemp(prefix="sl-fake-provider-venv-"))
    _create_venv(root)
    _plant_fake_packages(_site_dir(root), owner_profile=owner_profile)
    _VENV_CACHE = root
    atexit.register(lambda: shutil.rmtree(root, ignore_errors=True))
    return root


def _worker_sources(entrypoint: str) -> list[dict[str, Any]]:
    files = list(build_manifest.WORKER_SOURCE_FILES)
    if entrypoint not in files:
        files.append(entrypoint)
    return [build_manifest.file_identity(ROOT / relative, relative) for relative in files]


def _telemetry_deny() -> list[dict[str, Any]]:
    return [
        {"decision": "DENY", "endpoint_ref": "VNAI_ANALYTICS", "expected_failure_behavior": "recorded",
         "host": "hq.vnstocks.com", "layer": "NETWORK", "method": "POST", "path_pattern": "/analytics",
         "port": 443, "reachability": "fake vnai.setup()", "scheme": "https"},
        {"decision": "DENY", "endpoint_ref": "VNAI_GIT_PROBE", "expected_failure_behavior": "recorded",
         "layer": "PROCESS", "process": "git", "reachability": "fake vnai.setup()"},
        {"decision": "DENY", "endpoint_ref": "VNSTOCK_UPDATE_PIP_LIST", "expected_failure_behavior": "recorded",
         "layer": "PROCESS", "process": "python", "reachability": "fake vnai.setup()"},
    ]


def _approved_endpoint() -> dict[str, Any]:
    return {
        "scheme": "https", "host": FAKE_ENDPOINT_HOST, "port": 443, "method": "GET",
        "path_pattern": FAKE_ENDPOINT_PATH, "purpose": "TEST_FIXTURE_FAKE_OHLC", "max_redirects": 0,
    }


@dataclass
class FakeProviderRuntime:
    """One throwaway fake provider environment + attested launch inputs (not a live qualification)."""

    root: Path
    venv_root: Path
    interpreter: str
    owner_profile: Path
    state_root: Path
    scratch_base: Path
    manifest_path: Path
    lock_path: Path
    registry_path: Path
    tree_path: Path
    policy: runtime_contract.ProviderPolicy
    manifest: dict[str, Any]
    manifest_sha256: str
    launch_mode: str = build_manifest.LAUNCH_MODE_GATE_B
    extra_env: dict[str, str] = field(default_factory=dict)
    parent_env: dict[str, str] = field(default_factory=dict)
    mode: str = MODE_OFFLINE_FAKE
    style: str = "protocol"

    def parent_environ(self, **extra: str) -> dict[str, str]:
        env = dict(self.parent_env)
        env.update(extra)
        return env

    def authorize(self, **overrides: Any) -> build_manifest.ProviderLaunchAuthorization:
        kwargs: dict[str, Any] = {
            "policy": self.policy,
            "configured_executable": self.interpreter,
            "parent_environ": self.parent_environ(),
            "launch_mode": self.launch_mode,
            "manifest_path": self.manifest_path,
            "registry_path": self.registry_path,
            "worker_script": ROOT / self.manifest["worker"]["entrypoint"],
            "extra_env": self.extra_env or None,
            "producer_root": ROOT,
        }
        kwargs.update(overrides)
        return build_manifest.authorize_provider_launch(**kwargs)

    def fetcher(self, **overrides: Any) -> worker_client.VnstockWorkerFetcher:
        launch = overrides.pop("launch", None) or self.authorize()
        kwargs: dict[str, Any] = {
            "python_executable": self.interpreter,
            "policy": self.policy,
            "launch": launch,
            "request_timeout": 10.0,
            "startup_timeout": 15.0,
            "shutdown_timeout": 5.0,
        }
        kwargs.update(overrides)
        return worker_client.VnstockWorkerFetcher(**kwargs)

    def open_provider_runtime(self, **overrides: Any) -> worker_client.ProviderRuntimeHandle:
        kwargs: dict[str, Any] = {
            "policy": self.policy,
            "environ": self.parent_environ(),
            "core_executable": str(Path("/nonexistent/core/python")),
            "worker_script": ROOT / self.manifest["worker"]["entrypoint"],
            "manifest_path": self.manifest_path,
            "revocation_registry_path": self.registry_path,
            "launch_mode": self.launch_mode,
            "producer_root": ROOT,
            "extra_env": self.extra_env or None,
            "startup_timeout": 15.0,
            "request_timeout": 10.0,
            "shutdown_timeout": 5.0,
        }
        kwargs.update(overrides)
        return worker_client.open_provider_runtime(**kwargs)

    def write_registry(self, payload: Mapping[str, Any]) -> None:
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    def revoke(self, *, reason: str = "TEST_FIXTURE_REVOKED", epoch: int = 1) -> None:
        self.write_registry({
            "contract_version": build_manifest.REVOCATION_REGISTRY_CONTRACT_VERSION,
            "provider_family": runtime_contract.PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
            "current_epoch": epoch,
            "revoked_manifest_sha256": [self.manifest_sha256],
            "builds": {self.manifest["build_id"]: {
                "state": "REVOKED", "epoch": epoch, "reason": reason,
                "revoked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "decision_id": TEST_DECISION_ID,
            }},
            "description": "TEST_FIXTURE_ONLY revocation registry",
        })


def _empty_registry() -> dict[str, Any]:
    return {
        "contract_version": build_manifest.REVOCATION_REGISTRY_CONTRACT_VERSION,
        "provider_family": runtime_contract.PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
        "current_epoch": 0,
        "revoked_manifest_sha256": [],
        "builds": {},
        "description": "TEST_FIXTURE_ONLY revocation registry",
    }


def _write_lock(path: Path, packages: list[dict[str, Any]]) -> str:
    names = [item["name"] for item in packages]
    lock = {
        "contract_version": build_manifest.DEPENDENCY_LOCK_CONTRACT_VERSION,
        "approval_state": "CANDIDATE_FOR_OWNER_REVIEW_NOT_APPROVED",
        "authority_effect": "NONE_OPERATIONAL_METADATA_ONLY",
        "provider_family": runtime_contract.PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
        "description": "TEST_FIXTURE_ONLY lock. Not a live provider qualification result.",
        "candidate_closure": {
            "count": len(packages),
            "kind": "TEST_FIXTURE_ONLY",
            "packages": [
                {
                    "name": item["name"], "version": item["version"],
                    "artifact_filename": item["artifact_filename"],
                    "artifact_sha256": item["artifact_sha256"],
                    "artifact_size": item["artifact_size"],
                    "artifact_source_url_claim": item["artifact_source_url"],
                    "installed_bytes_match_artifact": True,
                    "provenance_classification": "TEST_FIXTURE_ONLY",
                    "trust_evidence": "TEST_FIXTURE_ONLY",
                }
                for item in packages
            ],
            "status": "TEST_FIXTURE_ONLY",
        },
        "runtime_minimal_hypothesis": {
            "kind": "TEST_FIXTURE_ONLY", "packages": names, "status": "TEST_FIXTURE_ONLY",
            "note": "Fake fixture packages only.",
        },
        "unnecessary_for_governed_worker": {
            "kind": "TEST_FIXTURE_ONLY", "packages": [], "note": "none",
        },
        "not_required_for_governed_worker": {
            "anthropic": "not a worker dependency",
            "core_requirements_txt": "core tier is separate",
            "plotting_chart_stack": "not planted",
            "notebook_ipython_ui": "not planted",
        },
    }
    path.write_text(json.dumps(lock, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    _, digest = build_manifest.load_dependency_lock(path)
    return digest


def build_fake_provider_runtime(
    root: Path | None = None,
    *,
    style: str = "protocol",
    extra_env: Mapping[str, str] | None = None,
    credential_mechanism: str = build_manifest.CREDENTIAL_NONE,
    credential_value: str | None = None,
    governor_rpm: int | None = None,
    endpoints: list[dict[str, Any]] | None = None,
    status: str = build_manifest.STATUS_APPROVED,
    launch_authorized: bool | None = None,
    launch_mode: str = build_manifest.LAUNCH_MODE_GATE_B,
    include_packages: bool = True,
    mutate_manifest: Any = None,
    python_build_override: str | None = None,
    unexpected_pth: bool = False,
    startup_hook: bool = False,
    system_site: bool = False,
    include_tzdata: bool = True,
    vnai_probes_owner_profile: bool = True,
) -> FakeProviderRuntime:
    """Construct a throwaway fake provider environment under ``root`` (or a temp dir)."""
    root = Path(root) if root is not None else Path(tempfile.mkdtemp(prefix="sl-fake-provider-rt-"))
    root.mkdir(parents=True, exist_ok=True)
    owner_profile = root / "owner-profile"
    (owner_profile / ".vnstock").mkdir(parents=True, exist_ok=True)
    (owner_profile / ".stocklookup").mkdir(parents=True, exist_ok=True)
    (owner_profile / ".vnstock" / "api_key.json").write_text('{"api_key":"owner-secret-must-not-leak"}\n', encoding="utf-8")
    (owner_profile / ".stocklookup" / "secrets.env").write_text("DNSE_API_KEY=owner-dnse\n", encoding="utf-8")
    if unexpected_pth or startup_hook or system_site or not include_tzdata or not vnai_probes_owner_profile:
        venv_root = Path(tempfile.mkdtemp(prefix="sl-fake-provider-venv-mut-"))
        _create_venv(venv_root)
        _plant_fake_packages(
            _site_dir(venv_root), owner_profile=str(owner_profile),
            include_tzdata=include_tzdata, vnai_probes_owner_profile=vnai_probes_owner_profile,
        )
    else:
        venv_root = cached_fake_venv(owner_profile=str(owner_profile))
        vnai_init = _site_dir(venv_root) / "vnai" / "__init__.py"
        if vnai_init.is_file() and str(owner_profile) not in vnai_init.read_text(encoding="utf-8"):
            _plant_fake_packages(_site_dir(venv_root), owner_profile=str(owner_profile))
    interpreter = str(_venv_python(venv_root).resolve())
    site = _site_dir(venv_root)
    if system_site:
        cfg = (venv_root / "pyvenv.cfg").read_text(encoding="utf-8")
        (venv_root / "pyvenv.cfg").write_text(
            cfg.replace("include-system-site-packages = false", "include-system-site-packages = true"),
            encoding="utf-8",
        )

    state_root = root / "provider-state"
    scratch_base = root / "provider-scratch"
    state_root.mkdir(parents=True, exist_ok=True)
    scratch_base.mkdir(parents=True, exist_ok=True)
    terms_text = "TEST_FIXTURE_ONLY terms\n"
    terms_path = state_root / ".vnstock" / "id" / "terms_agreement.txt"
    _write(terms_path, terms_text)

    if unexpected_pth:
        (site / "unexpected.pth").write_text("import os\n", encoding="utf-8")
    if startup_hook:
        (site / "sitecustomize.py").write_text("HOOK = 1\n", encoding="utf-8")
    described = build_manifest.describe_provider_runtime(interpreter, probe_env=_probe_env())
    if system_site:
        described["runtime"]["include_system_site_packages"] = False
    if unexpected_pth or startup_hook:
        # Bind the clean inventory, then leave the extra hook in the tree so attestation sees it.
        described["runtime"]["startup_hook_files"] = [
            item for item in described["runtime"]["startup_hook_files"]
            if not str(item.get("relative_path", "")).endswith(("unexpected.pth", "sitecustomize.py"))
        ]
    packages = described["packages"] if include_packages else []
    tree = described["installed_tree_manifest"]
    tree_path = root / "installed_tree.json"
    tree_path.write_bytes(build_manifest.canonical_json_bytes(tree))
    lock_path = root / "provider_dependency_lock.json"

    entrypoint = FAKE_WORKER_RELATIVE if style == "protocol" else build_manifest.WORKER_ENTRYPOINT
    now = datetime.now(timezone.utc)
    tier = build_manifest.TIER_GUEST if credential_mechanism == build_manifest.CREDENTIAL_NONE else build_manifest.TIER_FREE
    reviewed = build_manifest.REVIEWED_VENDOR_TIER_LIMITS[tier]
    rpm = governor_rpm if governor_rpm is not None else min(
        int(build_manifest.MAX_FRACTION_OF_TIER_MINUTE_LIMIT * reviewed["min"]),
        build_manifest.OWNER_APPROVED_GOVERNOR_CEILING_RPM,
    )
    allowed_names = sorted(runtime_contract.BASE_ENV_ALLOWLIST | set(PROTOCOL_CONTROL_ENV))
    credential_names: list[str] = []
    if credential_mechanism == build_manifest.CREDENTIAL_APPROVED_ENV_NAME:
        credential_names = [build_manifest.VENDOR_CREDENTIAL_NAME]
        allowed_names = sorted(set(allowed_names) | {build_manifest.VENDOR_CREDENTIAL_NAME})

    runtime_section = dict(described["runtime"])
    runtime_section["installed_tree_manifest"] = {
        "path": str(tree_path), "sha256": build_manifest.canonical_sha256(tree), "file_count": len(tree["files"]),
    }
    if python_build_override is not None:
        runtime_section["python_build"] = python_build_override

    package_records = []
    for item in packages:
        package_records.append({
            **item,
            "artifact_filename": f"{item['name']}-{item['version']}-py3-none-any.whl",
            "artifact_sha256": _sha256_text(f"TEST_FIXTURE_ARTIFACT:{item['name']}:{item['version']}"),
            "artifact_size": 1,
            "artifact_source_url": f"https://{FAKE_ENDPOINT_HOST}/wheels/{item['name']}-{item['version']}-py3-none-any.whl",
            "native_manifest_sha256": None,
            "provenance_classification": "TEST_FIXTURE_ONLY",
            "provenance_evidence_sha256": None,
            "requires_dist": [],
        })

    # Lock pins must match package artifact hashes.
    lock_digest = _write_lock(lock_path, package_records)

    manifest = {
        "contract_version": build_manifest.MANIFEST_CONTRACT_VERSION,
        "schema_ref": "config/provider_build_manifest.schema.json",
        "authority_effect": build_manifest.AUTHORITY_EFFECT,
        "build_id": TEST_BUILD_ID,
        "provider_family": runtime_contract.PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
        "status": status,
        "launch_authorized": True if launch_authorized is None and status == build_manifest.STATUS_APPROVED else bool(launch_authorized),
        "description": "TEST_FIXTURE_ONLY fake provider build. Not a live qualification result. Mode=" + MODE_OFFLINE_FAKE,
        "dependency_graph_sha256": None,
        "qualification_evidence_sha256": None,
        "approval": None if status != build_manifest.STATUS_APPROVED else {
            "owner_id": "TEST_FIXTURE_OWNER",
            "decision_id": TEST_DECISION_ID,
            "policy_decision_id": TEST_DECISION_ID,
            "approved_at_utc": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at_utc": (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "evidence_bundle_sha256": "a" * 64,
            "signature": None, "signature_algorithm": None, "trust_key_id": None,
        },
        "launch_mode": {
            "mode": launch_mode,
            "ordinary_daily_requires_qualification_evidence": True,
            "request_budget": {"max_seconds": 15, "max_total_http": 0 if style == "protocol" else 4},
        },
        "runtime": runtime_section,
        "packages": package_records,
        "dependency_lock": {
            "path": str(lock_path), "selected_closure": "CANDIDATE_CLOSURE", "sha256": lock_digest,
        },
        "worker": {
            "entrypoint": entrypoint,
            "adapter_module": build_manifest.WORKER_ADAPTER_MODULE,
            "protocol_version": "vnstock_worker_protocol/1.2.0",
            "argv_flags": list(runtime_contract.WORKER_INTERPRETER_FLAGS),
            "source_files": _worker_sources(entrypoint),
            "startup_stubs": [dict(item) for item in build_manifest.WORKER_STARTUP_STUBS],
            "lineage_endpoint_map": dict(build_manifest.LINEAGE_ENDPOINT_MAP),
            "git_commit": None,
        },
        "environment": {
            "allowed_names": allowed_names,
            "credential_names": credential_names,
            "denied_secret_classes": list(build_manifest.DENIED_SECRET_CLASSES),
            "forbidden_names": list(build_manifest.REQUIRED_FORBIDDEN_NAMES),
            "forbidden_prefixes": list(build_manifest.REQUIRED_FORBIDDEN_PREFIXES),
            "inherit_parent": False,
            "redirected_profile_names": {name: "PROVIDER_STATE_ROOT" for name in build_manifest.REDIRECTED_PROFILE_NAMES},
        },
        "filesystem": {
            "acl_policy_sha256": None,
            "denied_root_classes": list(
                json.loads((ROOT / "config" / "provider_build_manifest.json").read_text(encoding="utf-8"))
                ["filesystem"]["denied_root_classes"]
            ),
            "provider_state_root": str(state_root.resolve()),
            "provider_scratch_base": str(scratch_base.resolve()),
            "read_only_roots": [str(venv_root), runtime_section["base_prefix"]],
            "writable_roots": [str(state_root.resolve()), str(scratch_base.resolve())],
            "reparse_points_allowed": False,
        },
        "network": {
            "default_deny": True,
            "egress_gateway": None,
            "endpoints": endpoints if endpoints is not None else ([_approved_endpoint()] if style == "governed" else []),
            "enforcement_policy_sha256": None,
            "review_candidate_endpoints": [],
        },
        "telemetry_disposition": _telemetry_deny(),
        "vendor_credential": {
            "mechanism": credential_mechanism,
            "credential_name": build_manifest.VENDOR_CREDENTIAL_NAME if credential_mechanism == build_manifest.CREDENTIAL_APPROVED_ENV_NAME else None,
            "expected_vnai_tier": tier,
            "fabricated_or_placeholder_key_forbidden": True,
            "owner_decision_id": TEST_DECISION_ID if credential_mechanism != build_manifest.CREDENTIAL_NONE else None,
        },
        "rate_tier_binding": {
            "tier": tier,
            "tier_limits": dict(reviewed),
            "max_fraction_of_tier_minute_limit": build_manifest.MAX_FRACTION_OF_TIER_MINUTE_LIMIT,
            "governor_effective_rpm": rpm,
            "planned_session_request_budget": 0,
        },
        "terms_acceptance": {
            "agreement_file_policy": build_manifest.TERMS_PREPROVISIONED,
            "agreement_file_relative_path": ".vnstock/id/terms_agreement.txt",
            "owner_decision_id": TEST_DECISION_ID,
            "terms_text_sha256": _sha256_text(terms_text),
            "license_identities": ["TEST_FIXTURE_ONLY"],
        },
        "os_containment": {
            "state": "OWNER_VERIFIED",
            "requirements": ["TEST_FIXTURE_ONLY -- not an owner OS verification"],
            "restricted_identity_sid": "TEST_FIXTURE",
            "job_object_kill_on_close": True,
            "egress_gateway_verified": True,
            "runtime_root_read_only_acl": True,
            "verification_evidence_sha256": "b" * 64,
        },
        "revocation": {
            "state": "ACTIVE", "epoch": 0, "kill_active_workers_on_revoke": True,
            "reason": None, "revoked_at_utc": None,
            "registry_identity": "TEST_FIXTURE_REGISTRY",
        },
    }
    if mutate_manifest is not None:
        mutate_manifest(manifest)
    if status != build_manifest.STATUS_APPROVED:
        manifest["approval"] = None
        manifest["launch_authorized"] = False if launch_authorized is None else bool(launch_authorized)

    manifest_path = root / "provider_build_manifest.json"
    manifest_path.write_bytes(build_manifest.canonical_json_bytes(manifest))
    digest = build_manifest.manifest_digest(manifest)
    registry_path = root / "provider_revocation_registry.json"
    registry_path.write_text(json.dumps(_empty_registry(), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    parent_env = dict(_probe_env())
    parent_env.update({
        runtime_contract.PROVIDER_PYTHON_ENV: interpreter,
        "USERPROFILE": str(owner_profile),
        "HOME": str(owner_profile),
        "APPDATA": str(owner_profile / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(owner_profile / "AppData" / "Local"),
        "TEMP": str(root / "owner-temp"),
        "TMP": str(root / "owner-temp"),
    })
    if credential_mechanism == build_manifest.CREDENTIAL_APPROVED_ENV_NAME and credential_value:
        parent_env[build_manifest.VENDOR_CREDENTIAL_NAME] = credential_value
    extra = dict(extra_env or {})

    policy = runtime_contract.ProviderPolicy(
        provider_family=runtime_contract.PROVIDER_FAMILY_VNSTOCK_KBS_VCI,
        policy=runtime_contract.POLICY_ALLOW_CONFIGURED_PROVIDER_RUNTIME,
        reason="TEST_FIXTURE_EXPLICIT_ALLOW_FAKE_PROVIDER_ONLY",
        source="TEST_FIXTURE",
        approved_manifest_path=str(manifest_path),
        approved_manifest_sha256=digest,
        decision_id=TEST_DECISION_ID,
        allowed_provider_env=tuple(credential_names),
    )
    runtime = FakeProviderRuntime(
        root=root, venv_root=venv_root, interpreter=interpreter, owner_profile=owner_profile,
        state_root=state_root, scratch_base=scratch_base, manifest_path=manifest_path,
        lock_path=lock_path, registry_path=registry_path, tree_path=tree_path, policy=policy,
        manifest=manifest, manifest_sha256=digest, launch_mode=launch_mode, extra_env=extra,
        parent_env=parent_env, style=style,
    )
    _LIVE.append(runtime)
    return runtime


def protocol_runtime(root: Path | None = None, **kwargs: Any) -> FakeProviderRuntime:
    kwargs.setdefault("style", "protocol")
    return build_fake_provider_runtime(root, **kwargs)


def governed_runtime(root: Path | None = None, **kwargs: Any) -> FakeProviderRuntime:
    kwargs.setdefault("style", "governed")
    return build_fake_provider_runtime(root, **kwargs)
