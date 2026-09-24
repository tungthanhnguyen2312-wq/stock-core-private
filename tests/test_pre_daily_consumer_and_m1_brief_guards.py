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
import re
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

BRIEF_ID = "daily_integrated_decision_brief/v1:def"
UNKNOWN_POSITION = {"position_state": "UNKNOWN_POSITION_NOT_SUPPLIED", "status": "NOT_SUPPLIED"}
# A legitimate private position the canonical IID itself carries (T001): copied exactly, it passes.
PRIVATE_POSITION = {"position_state": "HELD", "status": "SUPPLIED",
                    "source": {"portfolio_snapshot_identity": "private_portfolio_snapshot:fixture", "quantity": 1000}}


def _rows(n: int) -> list[dict]:
    postures = ["AVOID", "WAIT_FOR_CONFIRMATION", "INSUFFICIENT_CURRENT_RESEARCH", "HOLD"]
    currencies = ["CURRENT_SESSION", "LAST_TRADE_AS_OF:2026-09-22", "NO_CURRENT_EVIDENCE", "CURRENT_SESSION"]
    rows = []
    for i in range(n):
        posture, currency = postures[i % 4], currencies[i % 4]
        rows.append({"ticker": f"T{i:03d}", "research_action_posture": posture, "evidence_currency": currency,
                     "opportunity_priority_tier": None})
    return rows


def _canonical_iid(rows: list[dict]) -> dict:
    """A canonical Integrated Decision artifact whose identity recomputes (the index is its read model)."""
    import integrated_investment_decision_product as integrated_contract
    artifact = {"contract_version": "integrated_investment_decision_product/v1", "session": SESSION, "records": {
        row["ticker"]: {"ticker": row["ticker"], "decision_identity": f"integrated_decision:{row['ticker']}",
                        "research_action_posture": row["research_action_posture"],
                        "evidence_currency": row["evidence_currency"],
                        "position_context": PRIVATE_POSITION if row["ticker"] == "T001" else UNKNOWN_POSITION}
        for row in rows}}
    artifact.update(integrated_contract.content_identity(artifact))
    return artifact


def _delivered(record: dict, idp: str) -> dict:
    """The M1 AI-delivery projection of one canonical record (ai_research_session_delivery shape)."""
    return {**{key: json.loads(json.dumps(record[key])) for key in
               ("ticker", "decision_identity", "research_action_posture", "evidence_currency", "position_context")},
            "integrated_investment_decision_product_identity": idp}


def _root(source: Path) -> Path:
    return source.parent / "root"


def _verify(source: Path, **kwargs):
    return workflow.verify_retained_daily_brief_for_handoff(source, SESSION, root=_root(source), **kwargs)


def _operation(tmp_path: Path, *, m1: bool = True, declare: bool = True, write_brief: bool = True,
               rows: list[dict] | None = None, denominator: int = 8, index_denominator: int | None = None,
               with_index: bool = True, brief_session: str = SESSION, brief_identity: str = BRIEF_ID) -> Path:
    source = tmp_path / "op"
    source.mkdir()
    # The canonical IID, retained where the governed loader reads it, under the fixture root.
    iid = _canonical_iid(_rows(denominator))
    idp = iid["artifact_identity"]
    iid_path = (_root(source) / "operations-review" / "canonical-post-close-v1" / SESSION / "enrichment"
                / "integrated_investment_decision_product.json")
    iid_path.parent.mkdir(parents=True)
    iid_path.write_text(json.dumps(iid))
    coverage = {"universe_denominator": denominator}
    if m1:
        coverage["evidence_currency_distribution"] = {"CURRENT_SESSION": 4}
    overlay = {"contract_version": "integrated_decision_delivery_overlay/v1", "session": SESSION,
               "integrated_investment_decision_product_identity": idp, "coverage": coverage,
               "daily_integrated_decision_brief_identity": BRIEF_ID if declare else None}
    bundle: dict = {"integrated_decision_overlay_v1": overlay}
    if m1:
        # A coherent M1 AI delivery: the sealed product's 3 scoped cards and 2 owner-focus tickers,
        # and one full-universe companion row per canonical record, each its exact projection.
        import current_daily_decision_research_product as daily_product_contract
        records = iid["records"]
        product = {"session": SESSION, "detailed_research_cards": {t: {"ticker": t} for t in ("T000", "T001", "T002")},
                   "owner_focus": {"tickers": ["T000", "T001"], "role": "OWNER_FOCUS_REVIEW_SCOPE"}}
        product.update(daily_product_contract.content_identity(product))
        (source / "current_daily_decision_research_product_artifact.json").write_text(json.dumps(product))
        bundle["product_identity"] = product["artifact_identity"]
        bundle["ticker_research_contexts"] = {
            t: {"ticker": t, "integrated_decision_v1": _delivered(records[t], idp)} for t in ("T000", "T001", "T002")
        }
        bundle["owner_focus_research_contexts"] = [
            {"ticker": t, "status": "AVAILABLE", "integrated_decision_v1": _delivered(records[t], idp)} for t in ("T000", "T001")
        ]
        (source / "ai_research_full_universe.ndjson").write_text("".join(
            json.dumps({"ticker": t, "integrated_decision_v1": _delivered(records[t], idp)}) + "\n" for t in sorted(records)))
    (source / "ai_research_session_bundle.json").write_text(json.dumps(bundle))
    outputs = {"integrated_investment_decision_product": idp}
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
                "session": SESSION, "source_integrated_investment_decision_product_identity": idp,
                "denominator": len(rows) if index_denominator is None else index_denominator, "rows": rows,
            }
        (source / "daily_integrated_decision_brief_artifact.json").write_text(json.dumps(
            {"session": SESSION, "daily_integrated_decision_brief": brief}))
    return source


def test_m1_operation_with_a_valid_brief_and_index_passes(tmp_path):
    result = _verify(_operation(tmp_path))
    assert result["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"
    assert result["decision_surface_index_denominator"] == 8
    assert result["brief_path"].name == "daily_integrated_decision_brief_artifact.json"
    assert result["ai_delivery_parity"] == {"ticker_research_contexts": 3, "owner_focus_research_contexts": 2,
                                            "full_universe_rows": 8}


# ---------------------------------------------------------------- M1_LIVE_ACCEPTANCE_CORRECTIVE_V1
# The retained 2026-09-24 delivery carried research_action_posture but no evidence_currency /
# position_context on every overlay, and no overlay at all on the owner-focus contexts. The
# handoff guard now refuses exactly those shapes, on every AI surface, before publication.

def _rewrite_bundle(source: Path, mutate) -> None:
    path = source / "ai_research_session_bundle.json"
    bundle = json.loads(path.read_text())
    mutate(bundle)
    path.write_text(json.dumps(bundle))


def _rewrite_full_universe(source: Path, mutate) -> None:
    path = source / "ai_research_full_universe.ndjson"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    replaced = mutate(rows)  # in-place mutators return whatever they return; only a list replaces
    rows = replaced if isinstance(replaced, list) else rows
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _scoped(bundle: dict) -> dict:
    return bundle["ticker_research_contexts"]["T000"]["integrated_decision_v1"]


def _owner(bundle: dict) -> dict:
    return bundle["owner_focus_research_contexts"][1]["integrated_decision_v1"]


@pytest.mark.parametrize("surface", ["ticker_research_contexts", "owner_focus_research_contexts", "full_universe"])
@pytest.mark.parametrize("field", ["evidence_currency", "position_context"])
def test_m1_delivery_missing_a_decision_surface_field_is_refused(tmp_path, surface, field):
    source = _operation(tmp_path)
    if surface == "full_universe":
        _rewrite_full_universe(source, lambda rows: rows[5]["integrated_decision_v1"].pop(field))
        ticker = "T005"
    else:
        _rewrite_bundle(source, lambda bundle: (_scoped if surface == "ticker_research_contexts" else _owner)(bundle).pop(field))
        ticker = "T000" if surface == "ticker_research_contexts" else "T001"
    reason = ("M1_AI_DELIVERY_DECISION_SURFACE_MISMATCH:" if field == "evidence_currency"
              else "M1_AI_DELIVERY_POSITION_CONTEXT_MISSING:")
    with pytest.raises(workflow.OwnerDailyError, match=f"{reason}{surface}:{ticker}"):
        _verify(source)


def test_m1_owner_focus_context_without_the_integrated_overlay_is_refused(tmp_path):
    source = _operation(tmp_path)
    _rewrite_bundle(source, lambda bundle: bundle["owner_focus_research_contexts"][0].pop("integrated_decision_v1"))
    with pytest.raises(workflow.OwnerDailyError,
                       match="M1_AI_DELIVERY_INTEGRATED_DECISION_MISSING:owner_focus_research_contexts:T000"):
        _verify(source)


def test_m1_delivery_posture_that_disagrees_with_the_index_is_refused(tmp_path):
    # e.g. a delivery that re-derived posture from research_stance instead of projecting the IID.
    source = _operation(tmp_path)
    _rewrite_bundle(source, lambda bundle: _scoped(bundle).update(research_action_posture="ACCUMULATE_ON_RETEST"))
    with pytest.raises(workflow.OwnerDailyError,
                       match="M1_AI_DELIVERY_DECISION_SURFACE_MISMATCH:ticker_research_contexts:T000:research_action_posture"):
        _verify(source)


def test_m1_delivery_bound_to_another_integrated_decision_is_refused(tmp_path):
    source = _operation(tmp_path)
    _rewrite_full_universe(source, lambda rows: rows[0]["integrated_decision_v1"].update(
        integrated_investment_decision_product_identity="integrated_investment_decision_product/v1:other"))
    with pytest.raises(workflow.OwnerDailyError, match="M1_AI_DELIVERY_INTEGRATED_DECISION_IDENTITY_MISMATCH:full_universe:T000"):
        _verify(source)


def test_m1_full_universe_companion_must_be_exactly_one_row_per_index_ticker(tmp_path):
    source = _operation(tmp_path)
    (source / "ai_research_full_universe.ndjson").unlink()
    with pytest.raises(workflow.OwnerDailyError, match="M1_AI_FULL_UNIVERSE_COMPANION_MISSING"):
        _verify(source)
    short = tmp_path / "short"
    short.mkdir()
    source = _operation(short)
    _rewrite_full_universe(source, lambda rows: rows[:-1])
    with pytest.raises(workflow.OwnerDailyError, match="M1_AI_FULL_UNIVERSE_INDEX_SET_MISMATCH:rows=7:index=8"):
        _verify(source)
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    source = _operation(duplicate)
    _rewrite_full_universe(source, lambda rows: rows + [rows[3]])
    with pytest.raises(workflow.OwnerDailyError, match="M1_AI_FULL_UNIVERSE_DUPLICATE_TICKER:T003"):
        _verify(source)


def test_m1_operation_with_the_brief_missing_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DAILY_BRIEF_RETAINED_FILE_MISSING"):
        _verify(_operation(tmp_path, write_brief=False))


def test_m1_operation_that_never_declared_its_brief_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DAILY_BRIEF_NOT_DECLARED"):
        _verify(_operation(tmp_path, declare=False))


def test_m1_brief_without_index_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_MISSING"):
        _verify(_operation(tmp_path, with_index=False))


@pytest.mark.parametrize("kwargs", [
    {"rows": _rows(7)},                                  # short index vs canonical 8
    {"index_denominator": 7},                            # self-declared short denominator
    {"rows": _rows(9), "index_denominator": 8},          # extra rows
])
def test_short_or_malformed_denominator_is_refused(tmp_path, kwargs):
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_DENOMINATOR_MISMATCH"):
        _verify(_operation(tmp_path, **kwargs))


def test_duplicate_ticker_is_refused(tmp_path):
    rows = _rows(8)
    rows[5] = dict(rows[5], ticker=rows[0]["ticker"])  # T000 twice, T005 missing
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_DUPLICATE_TICKER:T000"):
        _verify(_operation(tmp_path, rows=rows))


@pytest.mark.parametrize("missing", ["ticker", "research_action_posture", "evidence_currency"])
def test_row_missing_a_required_field_is_refused(tmp_path, missing):
    rows = _rows(8)
    rows[3] = {k: v for k, v in rows[3].items() if k != missing}
    with pytest.raises(workflow.OwnerDailyError, match="M1_DECISION_SURFACE_INDEX_ROW_MALFORMED"):
        _verify(_operation(tmp_path, rows=rows))


def test_no_current_evidence_wait_is_refused(tmp_path):
    rows = _rows(8)
    rows[2] = dict(rows[2], research_action_posture="WAIT_FOR_CONFIRMATION", evidence_currency="NO_CURRENT_EVIDENCE")
    with pytest.raises(workflow.OwnerDailyError, match="M1_NO_CURRENT_EVIDENCE_WAIT_PRESENT:T002"):
        _verify(_operation(tmp_path, rows=rows))


def test_brief_bound_to_another_session_or_identity_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="DAILY_BRIEF_SESSION_MISMATCH"):
        _verify(_operation(tmp_path, brief_session="2026-09-23"))
    other = tmp_path / "second"
    other.mkdir()
    with pytest.raises(workflow.OwnerDailyError, match="DAILY_BRIEF_IDENTITY_MISMATCH"):
        _verify(_operation(other, brief_identity="daily_integrated_decision_brief/v1:zzz"))


def test_pre_m1_operation_without_a_declared_brief_keeps_legacy_behavior(tmp_path):
    result = _verify(_operation(tmp_path, m1=False, declare=False, write_brief=False))
    assert result == {"status": "LEGACY_NO_BRIEF_DECLARED", "m1": False, "brief_path": None}


def test_pre_m1_operation_that_declared_a_brief_without_index_stays_publishable(tmp_path):
    # The real 2026-09-23 operation shape: Brief declared and retained, built before M1 (no index).
    result = _verify(_operation(tmp_path, m1=False, with_index=False))
    assert result["status"] == "DECLARED_BRIEF_VERIFIED"


def test_pre_m1_declared_brief_missing_is_refused(tmp_path):
    with pytest.raises(workflow.OwnerDailyError, match="^DAILY_BRIEF_RETAINED_FILE_MISSING$"):
        _verify(_operation(tmp_path, m1=False, write_brief=False))


def test_publish_ai_handoff_refuses_before_any_publication(monkeypatch, tmp_path):
    source = _operation(tmp_path, write_brief=False)
    for name in ("daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json"):
        (source / name).write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "h", "status": "UP_TO_DATE"})
    import ai_handoff_publication
    monkeypatch.setattr(ai_handoff_publication, "publish", lambda *a, **k: pytest.fail("must not publish"))
    with pytest.raises(workflow.OwnerDailyError, match="M1_DAILY_BRIEF_RETAINED_FILE_MISSING"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", {"source": str(source), "session": SESSION})


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
    result = workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", {"source": str(source), "session": SESSION})
    assert captured["daily_integrated_decision_brief"] == source / "daily_integrated_decision_brief_artifact.json"
    assert result["daily_brief_check"]["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"


def test_the_guard_never_reads_research_stance():
    import inspect
    assert "research_stance" not in inspect.getsource(workflow.verify_retained_daily_brief_for_handoff).split('"""')[-1]
    for helper in (workflow._verify_m1_ai_delivery, workflow._verify_m1_integrated_projection,
                   workflow._m1_canonical_sources, workflow._verify_exact_scope):
        assert "research_stance" not in inspect.getsource(helper).split('"""')[-1]


# ---------------------------------------------------- M1_LIVE_ACCEPTANCE_CORRECTIVE_V1 hardening
# Independent review: a delivered HPG position_context rewritten UNKNOWN_POSITION_NOT_SUPPLIED ->
# HELD (canonical IID unchanged) still verified, and an empty/short/repeated scoped or owner-focus
# context set was not bounded. Every delivered overlay must now be the exact projection of the
# bound canonical IID record, and each context set exactly the sealed Daily product's.

def _scoped_of(bundle: dict, ticker: str) -> dict:
    return bundle["ticker_research_contexts"][ticker]["integrated_decision_v1"]


def _owner_of(bundle: dict, ticker: str) -> dict:
    return next(row for row in bundle["owner_focus_research_contexts"] if row["ticker"] == ticker)["integrated_decision_v1"]


def _set_position(overlay: dict, value) -> None:
    overlay["position_context"] = value


def _nested_quantity(bundle: dict) -> None:
    _owner_of(bundle, "T001")["position_context"]["source"]["quantity"] = 2000


def _extra_scoped(bundle: dict) -> None:
    bundle["ticker_research_contexts"]["T005"] = json.loads(json.dumps(bundle["ticker_research_contexts"]["T002"]))
    bundle["ticker_research_contexts"]["T005"]["ticker"] = "T005"


def _extra_owner_focus(bundle: dict) -> None:
    bundle["owner_focus_research_contexts"].append({"ticker": "T002", "status": "AVAILABLE",
                                                    "integrated_decision_v1": _scoped_of(bundle, "T002")})


_MUTATIONS = {
    # position_context integrity against the canonical IID
    "unknown_to_held": (lambda b: _set_position(_scoped_of(b, "T000"), {"position_state": "HELD", "status": "NOT_SUPPLIED"}),
                        "M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:ticker_research_contexts:T000:position_context"),
    "unknown_to_not_held": (lambda b: _set_position(_scoped_of(b, "T002"), {"position_state": "NOT_HELD", "status": "NOT_SUPPLIED"}),
                            "M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:ticker_research_contexts:T002:position_context"),
    "nested_position_field": (_nested_quantity,
                              "M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:owner_focus_research_contexts:T001:position_context"),
    "position_missing": (lambda b: _scoped_of(b, "T002").pop("position_context"),
                         "M1_AI_DELIVERY_POSITION_CONTEXT_MISSING:ticker_research_contexts:T002"),
    "position_malformed": (lambda b: _set_position(_scoped_of(b, "T002"), "UNKNOWN_POSITION_NOT_SUPPLIED"),
                           "M1_AI_DELIVERY_POSITION_CONTEXT_MISSING:ticker_research_contexts:T002"),
    "position_of_another_ticker": (lambda b: _set_position(_scoped_of(b, "T000"), dict(PRIVATE_POSITION)),
                                   "M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:ticker_research_contexts:T000:position_context"),
    "owner_focus_position_corrupted": (lambda b: _set_position(_owner_of(b, "T000"), {"position_state": "HELD"}),
                                       "M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:owner_focus_research_contexts:T000:position_context"),
    "posture_mismatch": (lambda b: _scoped_of(b, "T001").update(research_action_posture="ACCUMULATE_ON_RETEST"),
                         "M1_AI_DELIVERY_DECISION_SURFACE_MISMATCH:ticker_research_contexts:T001:research_action_posture"),
    "evidence_currency_mismatch": (lambda b: _owner_of(b, "T000").update(evidence_currency="NO_CURRENT_EVIDENCE"),
                                   "M1_AI_DELIVERY_DECISION_SURFACE_MISMATCH:owner_focus_research_contexts:T000:evidence_currency"),
    "decision_identity_of_another_ticker": (lambda b: _scoped_of(b, "T002").update(decision_identity="integrated_decision:T003"),
                                            "M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:ticker_research_contexts:T002:decision_identity"),
    # scoped completeness against the sealed Daily product
    "scoped_empty": (lambda b: b.update(ticker_research_contexts={}),
                     "M1_AI_DELIVERY_SCOPED_SET_MISMATCH:expected=3:actual=0:missing=T000,T001,T002:extra="),
    "scoped_one_missing": (lambda b: b["ticker_research_contexts"].pop("T002"),
                           "M1_AI_DELIVERY_SCOPED_SET_MISMATCH:expected=3:actual=2:missing=T002:extra="),
    "scoped_unexpected": (_extra_scoped, "M1_AI_DELIVERY_SCOPED_SET_MISMATCH:expected=3:actual=4:missing=:extra=T005"),
    # owner-focus completeness against the sealed Daily product
    "owner_focus_missing": (lambda b: b["owner_focus_research_contexts"].pop(1),
                            "M1_AI_DELIVERY_OWNER_FOCUS_SET_MISMATCH:expected=2:actual=1:missing=T001:extra="),
    "owner_focus_empty": (lambda b: b.update(owner_focus_research_contexts=[]),
                          "M1_AI_DELIVERY_OWNER_FOCUS_SET_MISMATCH:expected=2:actual=0:missing=T000,T001:extra="),
    "owner_focus_duplicated": (lambda b: b["owner_focus_research_contexts"].append(b["owner_focus_research_contexts"][0]),
                               "M1_AI_DELIVERY_OWNER_FOCUS_DUPLICATE:T000"),
    "owner_focus_unexpected": (_extra_owner_focus, "M1_AI_DELIVERY_OWNER_FOCUS_SET_MISMATCH:expected=2:actual=3:missing=:extra=T002"),
    "owner_focus_overlay_missing": (lambda b: b["owner_focus_research_contexts"][1].pop("integrated_decision_v1"),
                                    "M1_AI_DELIVERY_INTEGRATED_DECISION_MISSING:owner_focus_research_contexts:T001"),
    "owner_focus_non_mapping_row": (lambda b: b["owner_focus_research_contexts"].append("T002"),
                                    "M1_AI_DELIVERY_OWNER_FOCUS_CONTEXTS_MALFORMED"),
    "owner_focus_absent": (lambda b: b.pop("owner_focus_research_contexts"),
                           "M1_AI_DELIVERY_OWNER_FOCUS_CONTEXTS_MALFORMED"),
}


@pytest.mark.parametrize("name", sorted(_MUTATIONS))
def test_m1_delivery_that_is_not_the_exact_canonical_projection_is_refused(tmp_path, name):
    mutate, reason = _MUTATIONS[name]
    source = _operation(tmp_path)
    _rewrite_bundle(source, mutate)
    with pytest.raises(workflow.OwnerDailyError, match="^" + re.escape(reason) + "$"):
        _verify(source)


def test_m1_full_universe_position_corruption_is_refused(tmp_path):
    source = _operation(tmp_path)
    _rewrite_full_universe(source, lambda rows: _set_position(rows[5]["integrated_decision_v1"],
                                                              {"position_state": "HELD", "status": "NOT_SUPPLIED"}))
    with pytest.raises(workflow.OwnerDailyError,
                       match="^M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:full_universe:T005:position_context$"):
        _verify(source)


def test_m1_scoped_ticker_repeated_in_the_bundle_is_refused(tmp_path):
    # json.loads would silently keep the last of two identical keys; the guard must not.
    source = _operation(tmp_path)
    path = source / "ai_research_session_bundle.json"
    bundle = json.loads(path.read_text())
    card = json.dumps(bundle["ticker_research_contexts"]["T000"])
    text = json.dumps(bundle).replace('"ticker_research_contexts": {', '"ticker_research_contexts": {"T000": ' + card + ", ", 1)
    path.write_text(text)
    with pytest.raises(workflow.OwnerDailyError, match="^M1_AI_DELIVERY_DUPLICATE_KEY:T000$"):
        _verify(source)


def test_m1_delivery_that_fell_back_to_research_stance_is_refused(tmp_path):
    source = _operation(tmp_path)

    def stance_fallback(bundle):
        card = bundle["ticker_research_contexts"]["T000"]
        card["research_stance"] = card["integrated_decision_v1"].pop("research_action_posture")
    _rewrite_bundle(source, stance_fallback)
    with pytest.raises(workflow.OwnerDailyError,
                       match="M1_AI_DELIVERY_DECISION_SURFACE_MISMATCH:ticker_research_contexts:T000:research_action_posture"):
        _verify(source)


def test_a_legitimate_canonical_private_position_copied_exactly_passes(tmp_path):
    source = _operation(tmp_path)
    bundle = json.loads((source / "ai_research_session_bundle.json").read_text())
    assert _scoped_of(bundle, "T001")["position_context"] == PRIVATE_POSITION
    assert _owner_of(bundle, "T001")["position_context"] == PRIVATE_POSITION
    result = _verify(source)
    assert result["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"
    assert result["ai_delivery_parity"] == {"ticker_research_contexts": 3, "owner_focus_research_contexts": 2,
                                            "full_universe_rows": 8}


@pytest.mark.parametrize("corrupt", [None, "unknown_to_held"])
def test_the_guard_never_rewrites_its_inputs(tmp_path, corrupt):
    import hashlib
    source = _operation(tmp_path)
    if corrupt:
        _rewrite_bundle(source, _MUTATIONS[corrupt][0])

    def snapshot():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    before = snapshot()
    try:
        _verify(source)
    except workflow.OwnerDailyError:
        assert corrupt
    assert snapshot() == before


def _rewrite_canonical_iid(source: Path, mutate) -> None:
    path = next(_root(source).rglob("integrated_investment_decision_product.json"))
    artifact = json.loads(path.read_text())
    mutate(artifact)
    path.write_text(json.dumps(artifact))


def _rewrite_product(source: Path, mutate) -> None:
    path = source / "current_daily_decision_research_product_artifact.json"
    artifact = json.loads(path.read_text())
    mutate(artifact)
    path.write_text(json.dumps(artifact))


@pytest.mark.parametrize("case, reason", [
    ("no_root", "M1_CANONICAL_ROOT_NOT_SUPPLIED"),
    ("iid_absent", "M1_CANONICAL_INTEGRATED_DECISION_UNAVAILABLE"),
    ("iid_edited_without_identity", "M1_CANONICAL_INTEGRATED_DECISION_IDENTITY_MISMATCH"),
    ("iid_of_another_session", "M1_CANONICAL_INTEGRATED_DECISION_IDENTITY_MISMATCH"),
    ("product_absent", "M1_CANONICAL_DAILY_PRODUCT_UNAVAILABLE"),
    ("product_cards_edited", "M1_CANONICAL_DAILY_PRODUCT_IDENTITY_MISMATCH"),
    ("product_not_the_bundles", "M1_CANONICAL_DAILY_PRODUCT_IDENTITY_MISMATCH"),
])
def test_m1_guard_requires_the_bound_canonical_sources(tmp_path, case, reason):
    source = _operation(tmp_path)
    if case == "no_root":
        with pytest.raises(workflow.OwnerDailyError, match=f"^{reason}$"):
            workflow.verify_retained_daily_brief_for_handoff(source, SESSION)
        return
    if case == "iid_absent":
        next(_root(source).rglob("integrated_investment_decision_product.json")).unlink()
    elif case == "iid_edited_without_identity":
        # Rewriting the canonical record to match a corrupted delivery is itself caught.
        _rewrite_canonical_iid(source, lambda a: a["records"]["T000"].update(position_context={"position_state": "HELD"}))
    elif case == "iid_of_another_session":
        _rewrite_canonical_iid(source, lambda a: a.update(session="2026-09-23"))
    elif case == "product_absent":
        (source / "current_daily_decision_research_product_artifact.json").unlink()
    elif case == "product_cards_edited":
        _rewrite_product(source, lambda a: a["detailed_research_cards"].pop("T002"))
    elif case == "product_not_the_bundles":
        _rewrite_bundle(source, lambda b: b.update(product_identity="current_daily_decision_research_product:other"))
    with pytest.raises(workflow.OwnerDailyError, match=f"^{reason}$"):
        _verify(source)


def test_a_corrupted_position_never_reaches_ai_publication(monkeypatch, tmp_path):
    # The independent-review probe end to end: canonical unknown position, delivered HELD.
    source = _operation(tmp_path)
    _rewrite_bundle(source, _MUTATIONS["owner_focus_position_corrupted"][0])
    for name in ("daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json"):
        (source / name).write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "h", "status": "UP_TO_DATE"})
    import ai_handoff_publication
    monkeypatch.setattr(ai_handoff_publication, "publish", lambda *a, **k: pytest.fail("must not publish"))
    with pytest.raises(workflow.OwnerDailyError,
                       match="M1_AI_DELIVERY_CANONICAL_IID_MISMATCH:owner_focus_research_contexts:T000:position_context"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", {"source": str(source), "session": SESSION})


def test_pre_m1_operations_need_no_canonical_root(tmp_path):
    # Genuine pre-M1 sessions are not retroactively invalidated: neither shape reads the IID.
    legacy = workflow.verify_retained_daily_brief_for_handoff(
        _operation(tmp_path, m1=False, declare=False, write_brief=False), SESSION)
    assert legacy["status"] == "LEGACY_NO_BRIEF_DECLARED"
    declared = tmp_path / "declared"
    declared.mkdir()
    result = workflow.verify_retained_daily_brief_for_handoff(_operation(declared, m1=False, with_index=False), SESSION)
    assert result["status"] == "DECLARED_BRIEF_VERIFIED"
