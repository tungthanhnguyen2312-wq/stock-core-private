"""PRE_DAILY_WORKSPACE_READINESS_CORRECTIVE_V1 -- final hardening.

Phase B: canonical Daily (and the release path's trusted-subset verification) EXECUTES code from
the sibling ai-core-private checkout, so Owner Daily governs that checkout before analytical work
with the one shared safe-sync ``preflight_repository`` engine and an explicit Consumer untracked
contract. Real, unmocked git repositories.

Phase C: a retained operation that declares the Daily Integrated Decision Brief (and, for M1, the
full-universe ``decision_surface_index``) can no longer reach AI handoff publication without it;
genuine pre-M1 operations that never declared a Brief keep the legacy behavior.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import canonical_daily_operation
from checkout_cleanliness_contract import APPROVED_RUNTIME_EVIDENCE_PREFIXES, CONSUMER_APPROVED_UNTRACKED_PREFIXES
from tools import run_owner_daily as workflow

SESSION = "2026-09-24"


# ============================================================================= Phase B

def _git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _identity(path: Path) -> None:
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _workspace_with_consumer(tmp_path: Path) -> tuple[Path, Path, Path]:
    """<ws>/stock-core-private (Producer dir) + <ws>/ai-core-private cloned from a bare origin."""
    ws = tmp_path / "ws"
    producer = ws / "stock-core-private"
    producer.mkdir(parents=True)
    origin = tmp_path / "ai-core-private.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    _identity(seed)
    (seed / "builders").mkdir()
    (seed / "builders" / "build_ticker_context.py").write_text("VERSION = 1\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "branch", "-M", "main")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-qu", "origin", "main")
    consumer = ws / "ai-core-private"
    subprocess.run(["git", "clone", "-q", str(origin), str(consumer)], check=True)
    _git(consumer, "checkout", "-q", "main")
    _identity(consumer)
    return producer, consumer, origin


def _advance(tmp_path: Path, origin: Path, name: str) -> str:
    other = tmp_path / f"other-{name}"
    subprocess.run(["git", "clone", "-q", str(origin), str(other)], check=True)
    _git(other, "checkout", "-q", "main")
    _identity(other)
    (other / "builders" / f"{name}.py").write_text("X = 1\n")
    _git(other, "add", ".")
    _git(other, "commit", "-qm", name)
    _git(other, "push", "-q")
    return _git(other, "rev-parse", "HEAD")


def _local_commit(consumer: Path) -> str:
    (consumer / "builders" / "local.py").write_text("LOCAL = 1\n")
    _git(consumer, "add", ".")
    _git(consumer, "commit", "-qm", "local only")
    return _git(consumer, "rev-parse", "HEAD")


def test_consumer_up_to_date_passes(tmp_path):
    producer, consumer, _origin = _workspace_with_consumer(tmp_path)
    head = _git(consumer, "rev-parse", "HEAD")
    assert workflow.preflight_consumer_repository(consumer, producer_root=producer) == {"head": head, "status": "UP_TO_DATE"}


def test_consumer_clean_behind_is_fast_forwarded(tmp_path):
    producer, consumer, origin = _workspace_with_consumer(tmp_path)
    remote = _advance(tmp_path, origin, "financial_v2")
    assert workflow.preflight_consumer_repository(consumer, producer_root=producer) == {"head": remote, "status": "FAST_FORWARDED"}
    assert (consumer / "builders" / "financial_v2.py").is_file()


def test_consumer_tracked_dirty_is_refused_and_kept(tmp_path):
    producer, consumer, origin = _workspace_with_consumer(tmp_path)
    _advance(tmp_path, origin, "remote")
    target = consumer / "builders" / "build_ticker_context.py"
    target.write_text("VERSION = 'local edit'\n")
    with pytest.raises(workflow.OwnerDailyError, match="UNEXPECTED_TRACKED_CHANGES"):
        workflow.preflight_consumer_repository(consumer, producer_root=producer)
    assert target.read_text() == "VERSION = 'local edit'\n"


@pytest.mark.parametrize("relative", ["json.py", "builders/shadow.py", "hpg_multi_angle_eval/result.json",
                                      "data/dnse-foreign-flow/x.json"])
def test_consumer_unsafe_untracked_is_refused(tmp_path, relative):
    producer, consumer, _origin = _workspace_with_consumer(tmp_path)
    path = consumer / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n")
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_UNTRACKED_CHECKOUT"):
        workflow.preflight_consumer_repository(consumer, producer_root=producer)
    assert path.is_file(), "never cleaned"


def test_consumer_nested_worktrees_are_the_only_approved_untracked_root(tmp_path):
    producer, consumer, _origin = _workspace_with_consumer(tmp_path)
    _git(consumer, "worktree", "add", "-q", "-b", "side", str(consumer / ".worktrees" / "side"))
    assert workflow.preflight_consumer_repository(consumer, producer_root=producer)["status"] == "UP_TO_DATE"
    assert CONSUMER_APPROVED_UNTRACKED_PREFIXES == (".worktrees/",)
    assert not set(CONSUMER_APPROVED_UNTRACKED_PREFIXES) & set(APPROVED_RUNTIME_EVIDENCE_PREFIXES), \
        "Producer data/... exceptions must not apply to the Consumer"


def test_consumer_ahead_is_refused(tmp_path):
    producer, consumer, _origin = _workspace_with_consumer(tmp_path)
    local = _local_commit(consumer)
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_GIT_DIVERGENCE"):
        workflow.preflight_consumer_repository(consumer, producer_root=producer)
    assert _git(consumer, "rev-parse", "HEAD") == local


def test_consumer_diverged_is_refused(tmp_path):
    producer, consumer, origin = _workspace_with_consumer(tmp_path)
    _advance(tmp_path, origin, "remote")
    local = _local_commit(consumer)
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_GIT_DIVERGENCE"):
        workflow.preflight_consumer_repository(consumer, producer_root=producer)
    assert _git(consumer, "rev-parse", "HEAD") == local, "never reset/rebase"


def test_consumer_wrong_branch_origin_or_path_is_refused(tmp_path):
    producer, consumer, _origin = _workspace_with_consumer(tmp_path)
    _git(consumer, "checkout", "-qb", "feature")
    with pytest.raises(workflow.OwnerDailyError, match="BRANCH_IS_NOT_MAIN"):
        workflow.preflight_consumer_repository(consumer, producer_root=producer)
    _git(consumer, "checkout", "-q", "main")
    _git(consumer, "remote", "set-url", "origin", str(tmp_path / "somewhere-else.git"))
    with pytest.raises(workflow.OwnerDailyError, match="WRONG_ORIGIN"):
        workflow.preflight_consumer_repository(consumer, producer_root=producer)
    clone = tmp_path / "elsewhere" / "ai-core-private"
    with pytest.raises(workflow.OwnerDailyError, match="WRONG_CONSUMER_PATH"):
        workflow.preflight_consumer_repository(clone, producer_root=producer)


def test_consumer_path_is_exactly_the_one_canonical_daily_executes():
    source = Path(canonical_daily_operation.__file__).read_text(encoding="utf-8")
    assert '_git_head(root.parent / "ai-core-private")' in source
    assert workflow.consumer_root_for(Path(r"C:\Projects\StockLookup\stock-core-private")) == \
        Path(r"C:\Projects\StockLookup\ai-core-private").resolve()


def _workflow_stubs(monkeypatch, order: list[str], seen_heads: list[str]) -> None:
    real = workflow.preflight_repository

    def preflight(root, *, expected_name, expected_remote_fragment, **kwargs):
        if expected_name == "ai-core-private":
            order.append("consumer_preflight")
            return real(root, expected_name=expected_name, expected_remote_fragment=expected_remote_fragment, **kwargs)
        order.append(f"{expected_name}_preflight")
        return {"head": expected_name, "status": "UP_TO_DATE"}

    monkeypatch.setattr(workflow, "preflight_repository", preflight)
    monkeypatch.setattr(workflow, "_resolve_intended_session", lambda: SESSION)
    monkeypatch.setattr(workflow, "_auto_resumable_session", lambda *a, **k: None)

    def run_daily(root, _runtime_root):
        order.append("daily")
        # Exactly what canonical_daily_operation records as consumer_head.
        seen_heads.append(canonical_daily_operation._git_head(Path(root).parent / "ai-core-private"))
        raise RuntimeError("STOP_AFTER_DAILY_START")

    monkeypatch.setattr(workflow, "_run_daily", run_daily)


def test_consumer_preflight_runs_before_daily_and_daily_records_the_preflighted_head(monkeypatch, tmp_path):
    producer, consumer, origin = _workspace_with_consumer(tmp_path)
    remote = _advance(tmp_path, origin, "financial_v2")
    order: list[str] = []
    seen: list[str] = []
    _workflow_stubs(monkeypatch, order, seen)
    with pytest.raises(RuntimeError, match="STOP_AFTER_DAILY_START"):
        workflow.run_workflow(root=producer, runtime_root=tmp_path / "runtime", handoff_repo=tmp_path / "h",
                              publish_dashboard=False)
    assert order == ["stock-core-private_preflight", "consumer_preflight", "daily"]
    assert seen == [remote], "Daily must record the HEAD the preflight fast-forwarded to"


def test_diverged_consumer_blocks_owner_daily_before_analytical_work(monkeypatch, tmp_path):
    producer, consumer, origin = _workspace_with_consumer(tmp_path)
    _advance(tmp_path, origin, "remote")
    _local_commit(consumer)
    order: list[str] = []
    _workflow_stubs(monkeypatch, order, [])
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_GIT_DIVERGENCE"):
        workflow.run_workflow(root=producer, runtime_root=tmp_path / "runtime", handoff_repo=tmp_path / "h",
                              publish_dashboard=False)
    assert "daily" not in order


def test_consumer_preflight_also_governs_replay(monkeypatch, tmp_path):
    producer, consumer, _origin = _workspace_with_consumer(tmp_path)
    (consumer / "json.py").write_text("shadow\n")
    order: list[str] = []
    _workflow_stubs(monkeypatch, order, [])
    monkeypatch.setattr(workflow, "verify_daily_completion",
                        lambda *a, **k: pytest.fail("replay must not proceed past a dirty Consumer"))
    with pytest.raises(workflow.OwnerDailyError, match="UNSAFE_UNTRACKED_CHECKOUT"):
        workflow.run_workflow(root=producer, runtime_root=tmp_path / "runtime", handoff_repo=tmp_path / "h",
                              publish_dashboard=False, replay_completed_session=SESSION)


# ============================================================================= Phase C

IDP = "integrated_investment_decision_product/v1:abc"
BRIEF_ID = "daily_integrated_decision_brief/v1:def"


def _rows(n: int) -> list[dict]:
    postures = ["AVOID", "WAIT_FOR_CONFIRMATION", "INSUFFICIENT_CURRENT_RESEARCH", "HOLD"]
    currencies = ["CURRENT_SESSION", "LAST_TRADE_AS_OF:2026-09-22", "NO_CURRENT_EVIDENCE", "CURRENT_SESSION"]
    rows = []
    for i in range(n):
        posture, currency = postures[i % 4], currencies[i % 4]
        rows.append({"ticker": f"T{i:03d}", "research_action_posture": posture, "evidence_currency": currency,
                     "opportunity_priority_tier": None})
    return rows


def _operation(tmp_path: Path, *, m1: bool = True, declare: bool = True, write_brief: bool = True,
               rows: list[dict] | None = None, denominator: int = 8, index_denominator: int | None = None,
               with_index: bool = True, brief_session: str = SESSION, brief_identity: str = BRIEF_ID) -> Path:
    source = tmp_path / "op"
    source.mkdir()
    coverage = {"universe_denominator": denominator}
    if m1:
        coverage["evidence_currency_distribution"] = {"CURRENT_SESSION": 4}
    overlay = {"contract_version": "integrated_decision_delivery_overlay/v1", "session": SESSION,
               "integrated_investment_decision_product_identity": IDP, "coverage": coverage,
               "daily_integrated_decision_brief_identity": BRIEF_ID if declare else None}
    (source / "ai_research_session_bundle.json").write_text(json.dumps({"integrated_decision_overlay_v1": overlay}))
    outputs = {"integrated_investment_decision_product": IDP}
    if declare:
        outputs["daily_integrated_decision_brief"] = BRIEF_ID
    (source / "run_manifest.json").write_text(json.dumps({"outputs": outputs}))
    if write_brief:
        rows = _rows(denominator) if rows is None else rows
        brief = {"contract_version": "daily_integrated_decision_brief/v1", "session": brief_session,
                 "artifact_identity": brief_identity}
        if with_index:
            brief["decision_surface_index"] = {
                "contract_version": "decision_surface_index/v1", "role": "READ_MODEL_NOT_AUTHORITY",
                "session": SESSION, "source_integrated_investment_decision_product_identity": IDP,
                "denominator": len(rows) if index_denominator is None else index_denominator, "rows": rows,
            }
        (source / "daily_integrated_decision_brief_artifact.json").write_text(json.dumps(
            {"session": SESSION, "daily_integrated_decision_brief": brief}))
    return source


def test_m1_operation_with_a_valid_brief_and_index_passes(tmp_path):
    result = workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path), SESSION)
    assert result["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"
    assert result["decision_surface_index_denominator"] == 8
    assert result["brief_path"].name == "daily_integrated_decision_brief_artifact.json"


def test_m1_operation_with_the_brief_missing_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DAILY_BRIEF_RETAINED_FILE_MISSING"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, write_brief=False), SESSION)


def test_m1_operation_that_never_declared_its_brief_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DAILY_BRIEF_NOT_DECLARED"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, declare=False), SESSION)


def test_m1_brief_without_index_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_MISSING"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, with_index=False), SESSION)


@pytest.mark.parametrize("kwargs", [
    {"rows": _rows(7)},                                  # short index vs canonical 8
    {"index_denominator": 7},                            # self-declared short denominator
    {"rows": _rows(9), "index_denominator": 8},          # extra rows
])
def test_short_or_malformed_denominator_is_refused(tmp_path, kwargs):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_DENOMINATOR_MISMATCH"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, **kwargs), SESSION)


def test_duplicate_ticker_is_refused(tmp_path):
    rows = _rows(8)
    rows[5] = dict(rows[5], ticker=rows[0]["ticker"])  # T000 twice, T005 missing
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_DUPLICATE_TICKER:T000"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, rows=rows), SESSION)


@pytest.mark.parametrize("missing", ["ticker", "research_action_posture", "evidence_currency"])
def test_row_missing_a_required_field_is_refused(tmp_path, missing):
    rows = _rows(8)
    rows[3] = {k: v for k, v in rows[3].items() if k != missing}
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_ROW_MALFORMED"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, rows=rows), SESSION)


def test_no_current_evidence_wait_is_refused(tmp_path):
    rows = _rows(8)
    rows[2] = dict(rows[2], research_action_posture="WAIT_FOR_CONFIRMATION", evidence_currency="NO_CURRENT_EVIDENCE")
    with pytest.raises(workflow.OwnerDailyError, match="M1_NO_CURRENT_EVIDENCE_WAIT_PRESENT:T002"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, rows=rows), SESSION)


def test_brief_bound_to_another_session_or_identity_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="DAILY_BRIEF_SESSION_MISMATCH"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, brief_session="2026-09-23"), SESSION)
    other = tmp_path / "second"
    other.mkdir()
    with pytest.raises(workflow.OwnerDailyError, match="DAILY_BRIEF_IDENTITY_MISMATCH"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(other, brief_identity="daily_integrated_decision_brief/v1:zzz"), SESSION)


def test_pre_m1_operation_without_a_declared_brief_keeps_legacy_behavior(tmp_path):
    result = workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, m1=False, declare=False, write_brief=False), SESSION)
    assert result == {"status": "LEGACY_NO_BRIEF_DECLARED", "m1": False, "brief_path": None}


def test_pre_m1_operation_that_declared_a_brief_without_index_stays_publishable(tmp_path):
    # The real 2026-09-23 operation shape: Brief declared and retained, built before M1 (no index).
    result = workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, m1=False, with_index=False), SESSION)
    assert result["status"] == "DECLARED_BRIEF_VERIFIED"


def test_pre_m1_declared_brief_missing_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="^DAILY_BRIEF_RETAINED_FILE_MISSING$"):
        workflow.verify_retained_daily_brief_for_handoff(_operation(tmp_path, m1=False, write_brief=False), SESSION)


def test_publish_ai_handoff_refuses_before_any_publication(monkeypatch, tmp_path):
    source = _operation(tmp_path, write_brief=False)
    for name in ("daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json"):
        (source / name).write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "h", "status": "UP_TO_DATE"})
    import ai_handoff_publication
    monkeypatch.setattr(ai_handoff_publication, "publish", lambda *a, **k: pytest.fail("must not publish"))
    with pytest.raises(workflow.OwnerDailyError, match="M1_DAILY_BRIEF_RETAINED_FILE_MISSING"):
        workflow.publish_ai_handoff(tmp_path, tmp_path / "handoff", {"source": str(source), "session": SESSION})


def test_publish_ai_handoff_passes_the_verified_brief(monkeypatch, tmp_path):
    source = _operation(tmp_path)
    for name in ("daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json"):
        (source / name).write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "h", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_git", lambda *a, **k: "producer-head")
    import ai_handoff_publication
    import post_handoff_presentation_attestation
    captured = {}
    monkeypatch.setattr(ai_handoff_publication, "publish", lambda *a, **k: captured.update(k) or {"status": "PUBLISHED"})
    monkeypatch.setattr(ai_handoff_publication, "verify_remote_publication", lambda *a, **k: {"remote_sha": "r"})
    monkeypatch.setattr(post_handoff_presentation_attestation, "read_attestation", lambda *a, **k: None)
    result = workflow.publish_ai_handoff(tmp_path, tmp_path / "handoff", {"source": str(source), "session": SESSION})
    assert captured["daily_integrated_decision_brief"] == source / "daily_integrated_decision_brief_artifact.json"
    assert result["daily_brief_check"]["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"


def test_the_guard_never_reads_research_stance():
    import inspect
    assert "research_stance" not in inspect.getsource(workflow.verify_retained_daily_brief_for_handoff).split('"""')[-1]
