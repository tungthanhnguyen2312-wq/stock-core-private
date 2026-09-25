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

UNKNOWN_POSITION = {"position_state": "UNKNOWN_POSITION_NOT_SUPPLIED", "status": "NOT_SUPPLIED"}
# A legitimate private position the canonical IID itself carries (T001): copied exactly, it passes.
PRIVATE_POSITION = {"position_state": "HELD", "status": "SUPPLIED",
                    "source": {"portfolio_snapshot_identity": "private_portfolio_snapshot:fixture", "quantity": 1000}}
SCOPED = ("T000", "T001", "T002")
OWNER_FOCUS = ("T000", "T001")


def _rows(n: int) -> list[dict]:
    postures = ["AVOID", "WAIT_FOR_CONFIRMATION", "INSUFFICIENT_CURRENT_RESEARCH", "HOLD"]
    currencies = ["CURRENT_SESSION", "LAST_TRADE_AS_OF:2026-09-22", "NO_CURRENT_EVIDENCE", "CURRENT_SESSION"]
    rows = []
    for i in range(n):
        posture, currency = postures[i % 4], currencies[i % 4]
        rows.append({"ticker": f"T{i:03d}", "research_action_posture": posture, "evidence_currency": currency,
                     "opportunity_priority_tier": None})
    return rows


def _canonical_iid(rows: list[dict], *, m1: bool) -> dict:
    """A canonical Integrated Decision artifact whose identity recomputes (the index is its read model)."""
    import integrated_investment_decision_product as integrated_contract
    coverage = {"universe_denominator": len(rows)}
    if m1:
        coverage["evidence_currency_distribution"] = {"CURRENT_SESSION": 4}
    records = {}
    for row in rows:
        ticker = row["ticker"]
        records[ticker] = {
            "ticker": ticker, "decision_identity": f"integrated_decision:{ticker}", "as_of_session": SESSION,
            "research_action_posture": row["research_action_posture"], "evidence_currency": row["evidence_currency"],
            "evidence_currency_gate": {"status": "APPLIED", "source": "LEVEL_2_DISPOSITION"},
            "evidence_currency_lineage": {"disposition_session": SESSION, "source_identity": f"coverage:{ticker}"},
            "position_context": PRIVATE_POSITION if ticker == "T001" else UNKNOWN_POSITION,
            "opportunity_priority": {"tier": "SETUP_WATCH"}, "tactical_phase": "BASE_BUILDING",
            "trigger": {"trigger_type": "BREAKOUT_CLOSE", "trigger_level": 10.5, "trigger_state": "NOT_TRIGGERED",
                        "distance_to_trigger_pct": 3.2, "internal_note": "not projected"},
            "invalidation": {"invalidation_level": 9.1, "invalidation_method": "SWING_LOW",
                             "distance_to_invalidation_pct": -7.4},
        }
    artifact = {"contract_version": integrated_contract.CONTRACT_VERSION, "session": SESSION,
                "coverage": coverage, "records": records}
    artifact.update(integrated_contract.content_identity(artifact))
    return artifact


def _root(source: Path) -> Path:
    return source.parent / "root"


def _operation_identity(source: Path) -> str:
    return json.loads((source / "run_manifest.json").read_text())["operation_identity"]


def _verify(source: Path, **kwargs):
    return workflow.verify_retained_daily_brief_for_handoff(source, SESSION, root=_root(source), **kwargs)


def _operation(tmp_path: Path, *, m1: bool = True, declare: bool = True, write_brief: bool = True,
               rows: list[dict] | None = None, denominator: int = 8, index_denominator: int | None = None,
               with_index: bool = True, brief_session: str = SESSION, brief_identity: str | None = None) -> Path:
    """A sealed retained operation built through the real contracts: an identity-recomputing
    operation manifest declaring the Integrated Decision (retained under the fixture root), the
    Brief (retained with its binding wrapper) and the Daily product (3 scoped cards, 2 owner-focus
    tickers); and an AI delivery projected by the serializer's own overlay function."""
    import current_daily_decision_research_product as daily_product_contract
    import daily_integrated_decision_brief as brief_contract
    from ai_research_session_delivery import project_integrated_decision_delivery_overlay
    from daily_research_session_operations import _identity as operation_identity_of
    from daily_research_session_operations import brief_retention_identity

    source = tmp_path / "op"
    source.mkdir()
    iid = _canonical_iid(_rows(denominator), m1=m1)
    idp = iid["artifact_identity"]
    iid_path = (_root(source) / "operations-review" / "canonical-post-close-v1" / SESSION / "enrichment"
                / "integrated_investment_decision_product.json")
    iid_path.parent.mkdir(parents=True)
    iid_path.write_text(json.dumps(iid))

    brief = {"contract_version": brief_contract.CONTRACT_VERSION, "session": brief_session}
    if with_index:
        index_rows = _rows(denominator) if rows is None else rows
        brief["decision_surface_index"] = {
            "contract_version": "decision_surface_index/v1", "role": "READ_MODEL_NOT_AUTHORITY",
            "session": SESSION, "source_integrated_investment_decision_product_identity": idp,
            "denominator": len(index_rows) if index_denominator is None else index_denominator, "rows": index_rows,
        }
    brief.update(brief_contract.content_identity(brief))

    product = {"contract_version": daily_product_contract.CONTRACT_VERSION, "session": SESSION,
               "detailed_research_cards": {t: {"ticker": t, "why": f"narrative for {t}"} for t in SCOPED},
               "owner_focus": {"tickers": list(OWNER_FOCUS), "role": "OWNER_FOCUS_REVIEW_SCOPE"}}
    product.update(daily_product_contract.content_identity(product))
    (source / "current_daily_decision_research_product_artifact.json").write_text(json.dumps(product))

    outputs = {"integrated_investment_decision_product": idp, "daily_product": product["artifact_identity"]}
    if declare:
        outputs["daily_integrated_decision_brief"] = brief_identity or brief["artifact_identity"]
    manifest = {"market_session": SESSION, "outputs": outputs,
                "coverage_summary": {"integrated_investment_decision": iid["coverage"]}}
    manifest["operation_identity"] = operation_identity_of(manifest)
    (source / "run_manifest.json").write_text(json.dumps(manifest))

    if write_brief:
        wrapper = {"schema_version": "1.0.0", "contract_version": "daily_session_integrated_decision_brief_artifact/v1",
                   "session": SESSION, "daily_operation_identity": manifest["operation_identity"],
                   "integrated_investment_decision_product_identity": idp, "daily_integrated_decision_brief": brief}
        wrapper.update(brief_retention_identity(wrapper))
        (source / "daily_integrated_decision_brief_artifact.json").write_text(json.dumps(wrapper))

    overlay = project_integrated_decision_delivery_overlay(SESSION, iid, brief if declare else None)
    projections = overlay.pop("records")
    bundle: dict = {"session": SESSION, "operation_identity": manifest["operation_identity"],
                    "product_identity": product["artifact_identity"], "integrated_decision_overlay_v1": overlay}
    if m1:
        bundle["ticker_research_contexts"] = {
            t: {**product["detailed_research_cards"][t], "integrated_decision_v1": projections[t]} for t in SCOPED
        }
        bundle["owner_focus_research_contexts"] = [
            {**product["detailed_research_cards"][t], "integrated_decision_v1": projections[t]} for t in OWNER_FOCUS
        ]
        (source / "ai_research_full_universe.ndjson").write_text("".join(
            json.dumps({"ticker": t, "integrated_decision_v1": projections[t]}) + "\n" for t in sorted(projections)))
    (source / "ai_research_session_bundle.json").write_text(json.dumps(bundle))
    return source


def test_m1_operation_with_a_valid_brief_and_index_passes(tmp_path):
    source = _operation(tmp_path)
    result = _verify(source, expected_operation_identity=_operation_identity(source))
    assert result["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"
    assert result["decision_surface_index_denominator"] == 8
    assert result["brief_path"].name == "daily_integrated_decision_brief_artifact.json"
    assert result["ai_delivery_parity"] == {"ticker_research_contexts": 3, "owner_focus_research_contexts": 2,
                                            "full_universe_rows": 8}
    assert result["authority"]["expected_scoped"] == 3
    assert result["authority"]["expected_owner_focus"] == 2
    assert result["authority"]["expected_full_universe"] == 8


# ---------------------------------------------------------------- M1_LIVE_ACCEPTANCE_CORRECTIVE_V1
# The retained 2026-09-24 delivery omitted evidence_currency / position_context and the owner-focus
# overlay; independent review then showed the guard could be steered by the delivery itself
# (applicability marker, a replacement Daily product, an incomplete field list). Authority is now
# resolved only from sealed state, and each delivered overlay must be the canonical projection.

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


def _rewrite_json(path: Path, mutate) -> None:
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value))


def _scoped_of(bundle: dict, ticker: str) -> dict:
    return bundle["ticker_research_contexts"][ticker]["integrated_decision_v1"]


def _owner_of(bundle: dict, ticker: str) -> dict:
    return next(row for row in bundle["owner_focus_research_contexts"] if row["ticker"] == ticker)["integrated_decision_v1"]


def _set(overlay: dict, key: str, value) -> None:
    overlay[key] = value


def _refused(source: Path, reason: str) -> None:
    with pytest.raises(workflow.OwnerDailyError, match="^" + re.escape(reason) + "$"):
        _verify(source)


def test_m1_owner_focus_context_without_the_integrated_overlay_is_refused(tmp_path):
    source = _operation(tmp_path)
    _rewrite_bundle(source, lambda bundle: bundle["owner_focus_research_contexts"][0].pop("integrated_decision_v1"))
    _refused(source, "M1_AI_DELIVERY_INTEGRATED_DECISION_MISSING:owner_focus_research_contexts:T000")


def test_m1_full_universe_companion_must_be_exactly_one_row_per_index_ticker(tmp_path):
    source = _operation(tmp_path)
    (source / "ai_research_full_universe.ndjson").unlink()
    _refused(source, "M1_AI_FULL_UNIVERSE_COMPANION_MISSING")
    short = tmp_path / "short"
    short.mkdir()
    source = _operation(short)
    _rewrite_full_universe(source, lambda rows: rows[:-1])
    _refused(source, "M1_AI_FULL_UNIVERSE_INDEX_SET_MISMATCH:rows=7:index=8")
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    source = _operation(duplicate)
    _rewrite_full_universe(source, lambda rows: rows + [rows[3]])
    _refused(source, "M1_AI_FULL_UNIVERSE_DUPLICATE_TICKER:T003")


def test_m1_operation_with_the_brief_missing_is_refused(tmp_path):
    _refused(_operation(tmp_path, write_brief=False), "M1_DAILY_BRIEF_RETAINED_FILE_MISSING")


def test_m1_operation_that_never_declared_its_brief_is_refused(tmp_path):
    _refused(_operation(tmp_path, declare=False), "M1_DAILY_BRIEF_NOT_DECLARED")


def test_m1_brief_without_index_is_refused(tmp_path):
    _refused(_operation(tmp_path, with_index=False), "M1_DECISION_SURFACE_INDEX_MISSING")


@pytest.mark.parametrize("kwargs", [
    {"rows": _rows(7)},                                  # short index vs canonical 8
    {"index_denominator": 7},                            # self-declared short denominator
    {"rows": _rows(9), "index_denominator": 8},          # extra rows
])
def test_short_or_malformed_denominator_is_refused(tmp_path, kwargs):
    with pytest.raises(workflow.OwnerDailyError, match="^M1_DECISION_SURFACE_INDEX_DENOMINATOR_MISMATCH"):
        _verify(_operation(tmp_path, **kwargs))


def test_duplicate_ticker_is_refused(tmp_path):
    rows = _rows(8)
    rows[5] = dict(rows[5], ticker=rows[0]["ticker"])  # T000 twice, T005 missing
    _refused(_operation(tmp_path, rows=rows), "M1_DECISION_SURFACE_INDEX_DUPLICATE_TICKER:T000")


@pytest.mark.parametrize("missing", ["ticker", "research_action_posture", "evidence_currency"])
def test_row_missing_a_required_field_is_refused(tmp_path, missing):
    rows = _rows(8)
    rows[3] = {k: v for k, v in rows[3].items() if k != missing}
    _refused(_operation(tmp_path, rows=rows), "M1_DECISION_SURFACE_INDEX_ROW_MALFORMED")


def test_no_current_evidence_wait_is_refused(tmp_path):
    rows = _rows(8)
    rows[2] = dict(rows[2], research_action_posture="WAIT_FOR_CONFIRMATION", evidence_currency="NO_CURRENT_EVIDENCE")
    _refused(_operation(tmp_path, rows=rows), "M1_NO_CURRENT_EVIDENCE_WAIT_PRESENT:T002")


def test_index_that_diverges_from_the_canonical_iid_is_refused(tmp_path):
    rows = _rows(8)
    rows[4] = dict(rows[4], research_action_posture="HOLD")
    _refused(_operation(tmp_path, rows=rows), "M1_DECISION_SURFACE_INDEX_DIVERGES_FROM_CANONICAL_IID:T004")


def test_brief_bound_to_another_session_or_identity_is_refused(tmp_path):
    _refused(_operation(tmp_path, brief_session="2026-09-23"), "DAILY_BRIEF_SESSION_MISMATCH")
    other = tmp_path / "second"
    other.mkdir()
    _refused(_operation(other, brief_identity="daily_integrated_decision_brief/v1:zzz"), "DAILY_BRIEF_IDENTITY_MISMATCH")


def test_pre_m1_operation_without_a_declared_brief_keeps_legacy_behavior(tmp_path):
    result = _verify(_operation(tmp_path, m1=False, declare=False, write_brief=False))
    assert result == {"status": "LEGACY_NO_BRIEF_DECLARED", "m1": False, "brief_path": None}


def test_pre_m1_operation_that_declared_a_brief_without_index_stays_publishable(tmp_path):
    # The real 2026-09-23 operation shape: Brief declared and retained, built before M1 (no index).
    source = _operation(tmp_path, m1=False, with_index=False)
    result = _verify(source, expected_operation_identity=_operation_identity(source))
    assert result["status"] == "DECLARED_BRIEF_VERIFIED"


def test_pre_m1_declared_brief_missing_is_refused(tmp_path):
    _refused(_operation(tmp_path, m1=False, write_brief=False), "DAILY_BRIEF_RETAINED_FILE_MISSING")


def test_pre_m1_operations_need_no_canonical_root(tmp_path):
    # Genuine pre-M1 sessions are not retroactively invalidated: neither shape reads the IID.
    legacy = workflow.verify_retained_daily_brief_for_handoff(
        _operation(tmp_path, m1=False, declare=False, write_brief=False), SESSION)
    assert legacy["status"] == "LEGACY_NO_BRIEF_DECLARED"
    declared = tmp_path / "declared"
    declared.mkdir()
    result = workflow.verify_retained_daily_brief_for_handoff(_operation(declared, m1=False, with_index=False), SESSION)
    assert result["status"] == "DECLARED_BRIEF_VERIFIED"


def test_pre_m1_delivery_that_claims_m1_contradicts_the_sealed_operation(tmp_path):
    source = _operation(tmp_path, m1=False, with_index=False)
    _rewrite_bundle(source, lambda b: b["integrated_decision_overlay_v1"]["coverage"].update(
        evidence_currency_distribution={"CURRENT_SESSION": 4}))
    _refused(source, "M1_APPLICABILITY_CONTRADICTS_SEALED_OPERATION")


def _publish_stubs(monkeypatch, source: Path) -> dict:
    for name in ("daily_opportunity_decision_queue_artifact.json", "ai_research_bundle_manifest.json"):
        (source / name).write_text("{}")
    monkeypatch.setattr(workflow, "preflight_repository", lambda *a, **k: {"head": "h", "status": "UP_TO_DATE"})
    monkeypatch.setattr(workflow, "_git", lambda *a, **k: "producer-head")
    import ai_handoff_publication
    import post_handoff_presentation_attestation
    captured: dict = {}
    monkeypatch.setattr(ai_handoff_publication, "publish", lambda *a, **k: captured.update(k, called=True) or {"status": "PUBLISHED"})
    monkeypatch.setattr(ai_handoff_publication, "verify_remote_publication", lambda *a, **k: {"remote_sha": "r"})
    monkeypatch.setattr(post_handoff_presentation_attestation, "read_attestation", lambda *a, **k: None)
    return captured


def _completion(source: Path, **overrides) -> dict:
    return {"source": str(source), "session": SESSION, "operation_id": _operation_identity(source), **overrides}


def test_publish_ai_handoff_refuses_before_any_publication(monkeypatch, tmp_path):
    source = _operation(tmp_path, write_brief=False)
    captured = _publish_stubs(monkeypatch, source)
    with pytest.raises(workflow.OwnerDailyError, match="M1_DAILY_BRIEF_RETAINED_FILE_MISSING"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source))
    assert "called" not in captured


def test_publish_ai_handoff_passes_the_verified_brief(monkeypatch, tmp_path):
    source = _operation(tmp_path)
    captured = _publish_stubs(monkeypatch, source)
    result = workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source))
    assert captured["daily_integrated_decision_brief"] == source / "daily_integrated_decision_brief_artifact.json"
    assert result["daily_brief_check"]["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"


def test_publish_ai_handoff_requires_the_completed_daily_operation(monkeypatch, tmp_path):
    source = _operation(tmp_path)
    captured = _publish_stubs(monkeypatch, source)
    with pytest.raises(workflow.OwnerDailyError, match="^COMPLETED_DAILY_OPERATION_IDENTITY_MISSING$"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", {"source": str(source), "session": SESSION})
    with pytest.raises(workflow.OwnerDailyError, match="^OPERATION_MANIFEST_NOT_THE_COMPLETED_DAILY_OPERATION$"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff",
                                    _completion(source, operation_id="daily_research_session_operation:other"))
    assert "called" not in captured


def test_the_guard_never_reads_research_stance():
    import inspect
    for function in (workflow.verify_retained_daily_brief_for_handoff, workflow.resolve_m1_handoff_authority,
                     workflow._verify_m1_ai_delivery, workflow._verify_m1_projection, workflow._verify_exact_scope,
                     workflow._sealed_operation_manifest, workflow._sealed_m1_applicable):
        assert "research_stance" not in inspect.getsource(function).split('"""')[-1]


# ------------------------------------------------------------ authoritative handoff verification

def test_the_verifier_uses_the_serializers_own_projection():
    # One definition: the expected overlay is the delivery module's projection, not a field list.
    import inspect
    source = inspect.getsource(workflow.resolve_m1_handoff_authority)
    assert "project_integrated_decision_delivery_overlay" in source
    assert "_M1_CANONICAL_PROJECTED_FIELDS" not in inspect.getsource(workflow)


_PROJECTION_MUTATIONS = {
    "trigger_state": (lambda b: _scoped_of(b, "T000")["trigger"].update(trigger_state="TRIGGERED"),
                      "ticker_research_contexts:T000:trigger"),
    "evidence_currency_lineage": (lambda b: _owner_of(b, "T001")["evidence_currency_lineage"].update(disposition_session="2026-09-23"),
                                  "owner_focus_research_contexts:T001:evidence_currency_lineage"),
    "as_of_session": (lambda b: _set(_scoped_of(b, "T002"), "as_of_session", "2026-09-23"),
                      "ticker_research_contexts:T002:as_of_session"),
    "is_actionable": (lambda b: _set(_scoped_of(b, "T001"), "is_actionable", True),
                      "ticker_research_contexts:T001:is_actionable"),
    "unknown_position_to_held": (lambda b: _set(_scoped_of(b, "T000"), "position_context", {"position_state": "HELD", "status": "NOT_SUPPLIED"}),
                                 "ticker_research_contexts:T000:position_context"),
    "unknown_position_to_not_held": (lambda b: _set(_owner_of(b, "T000"), "position_context", {"position_state": "NOT_HELD", "status": "NOT_SUPPLIED"}),
                                     "owner_focus_research_contexts:T000:position_context"),
    "nested_private_position": (lambda b: _owner_of(b, "T001")["position_context"]["source"].update(quantity=2000),
                                "owner_focus_research_contexts:T001:position_context"),
    "position_of_another_ticker": (lambda b: _set(_scoped_of(b, "T000"), "position_context", dict(PRIVATE_POSITION)),
                                   "ticker_research_contexts:T000:position_context"),
    "position_missing": (lambda b: _scoped_of(b, "T002").pop("position_context"),
                         "ticker_research_contexts:T002:position_context"),
    "posture": (lambda b: _set(_scoped_of(b, "T001"), "research_action_posture", "ACCUMULATE_ON_RETEST"),
                "ticker_research_contexts:T001:research_action_posture"),
    "evidence_currency": (lambda b: _set(_owner_of(b, "T000"), "evidence_currency", "NO_CURRENT_EVIDENCE"),
                          "owner_focus_research_contexts:T000:evidence_currency"),
    "decision_identity": (lambda b: _set(_scoped_of(b, "T002"), "decision_identity", "integrated_decision:T003"),
                          "ticker_research_contexts:T002:decision_identity"),
    "ticker": (lambda b: _set(_scoped_of(b, "T002"), "ticker", "T003"), "ticker_research_contexts:T002:ticker"),
    "iid_binding": (lambda b: _set(_scoped_of(b, "T000"), "integrated_investment_decision_product_identity", "x"),
                    "ticker_research_contexts:T000:integrated_investment_decision_product_identity"),
    "extra_field": (lambda b: _set(_scoped_of(b, "T000"), "target_price", 12.0), "ticker_research_contexts:T000:target_price"),
    "stance_fallback": (lambda b: b["ticker_research_contexts"]["T000"].update(
        research_stance=_scoped_of(b, "T000").pop("research_action_posture")),
                        "ticker_research_contexts:T000:research_action_posture"),
}


@pytest.mark.parametrize("name", sorted(_PROJECTION_MUTATIONS))
def test_any_authoritative_projection_mutation_is_refused(tmp_path, name):
    mutate, where = _PROJECTION_MUTATIONS[name]
    source = _operation(tmp_path)
    _rewrite_bundle(source, mutate)
    _refused(source, "M1_AI_DELIVERY_PROJECTION_MISMATCH:" + where)


def test_full_universe_projection_mutation_is_refused(tmp_path):
    source = _operation(tmp_path)
    _rewrite_full_universe(source, lambda rows: rows[5]["integrated_decision_v1"]["trigger"].update(trigger_level=99.0))
    _refused(source, "M1_AI_DELIVERY_PROJECTION_MISMATCH:full_universe:T005:trigger")


def test_delivery_specific_card_fields_are_not_iid_authority(tmp_path):
    # Narrative/card fields outside integrated_decision_v1 may legitimately differ from the IID.
    source = _operation(tmp_path)
    _rewrite_bundle(source, lambda b: b["ticker_research_contexts"]["T000"].update(why="rewritten narrative"))
    assert _verify(source)["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"


def test_a_legitimate_canonical_private_position_copied_exactly_passes(tmp_path):
    source = _operation(tmp_path)
    bundle = json.loads((source / "ai_research_session_bundle.json").read_text())
    assert _scoped_of(bundle, "T001")["position_context"] == PRIVATE_POSITION
    assert _owner_of(bundle, "T001")["position_context"] == PRIVATE_POSITION
    assert _verify(source)["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"


_SCOPE_MUTATIONS = {
    "scoped_empty": (lambda b: b.update(ticker_research_contexts={}),
                     "M1_AI_DELIVERY_SCOPED_SET_MISMATCH:expected=3:actual=0:missing=T000,T001,T002:extra="),
    "scoped_one_missing": (lambda b: b["ticker_research_contexts"].pop("T002"),
                           "M1_AI_DELIVERY_SCOPED_SET_MISMATCH:expected=3:actual=2:missing=T002:extra="),
    "scoped_unexpected": (lambda b: b["ticker_research_contexts"].update(T005={"ticker": "T005"}),
                          "M1_AI_DELIVERY_SCOPED_SET_MISMATCH:expected=3:actual=4:missing=:extra=T005"),
    "owner_focus_missing": (lambda b: b["owner_focus_research_contexts"].pop(1),
                            "M1_AI_DELIVERY_OWNER_FOCUS_SET_MISMATCH:expected=2:actual=1:missing=T001:extra="),
    "owner_focus_empty": (lambda b: b.update(owner_focus_research_contexts=[]),
                          "M1_AI_DELIVERY_OWNER_FOCUS_SET_MISMATCH:expected=2:actual=0:missing=T000,T001:extra="),
    "owner_focus_duplicated": (lambda b: b["owner_focus_research_contexts"].append(b["owner_focus_research_contexts"][0]),
                               "M1_AI_DELIVERY_OWNER_FOCUS_DUPLICATE:T000"),
    "owner_focus_unexpected": (lambda b: b["owner_focus_research_contexts"].append({"ticker": "T002"}),
                               "M1_AI_DELIVERY_OWNER_FOCUS_SET_MISMATCH:expected=2:actual=3:missing=:extra=T002"),
    "owner_focus_non_mapping_row": (lambda b: b["owner_focus_research_contexts"].append("T002"),
                                    "M1_AI_DELIVERY_OWNER_FOCUS_CONTEXTS_MALFORMED"),
    "owner_focus_absent": (lambda b: b.pop("owner_focus_research_contexts"),
                           "M1_AI_DELIVERY_OWNER_FOCUS_CONTEXTS_MALFORMED"),
}


@pytest.mark.parametrize("name", sorted(_SCOPE_MUTATIONS))
def test_context_sets_must_be_exactly_the_sealed_products(tmp_path, name):
    mutate, reason = _SCOPE_MUTATIONS[name]
    source = _operation(tmp_path)
    _rewrite_bundle(source, mutate)
    _refused(source, reason)


def test_scoped_ticker_repeated_in_the_bundle_is_refused(tmp_path):
    # json.loads would silently keep the last of two identical keys; the guard must not.
    source = _operation(tmp_path)
    path = source / "ai_research_session_bundle.json"
    bundle = json.loads(path.read_text())
    card = json.dumps(bundle["ticker_research_contexts"]["T000"])
    path.write_text(json.dumps(bundle).replace('"ticker_research_contexts": {', '"ticker_research_contexts": {"T000": ' + card + ", ", 1))
    _refused(source, "M1_AI_DELIVERY_DUPLICATE_KEY:T000")


@pytest.mark.parametrize("key", ["ticker", "research_action_posture", "evidence_currency", "position_context"])
def test_full_universe_row_with_a_repeated_key_is_refused(tmp_path, key):
    source = _operation(tmp_path)
    path = source / "ai_research_full_universe.ndjson"
    lines = path.read_text().splitlines()
    row = json.loads(lines[4])
    if key == "ticker":
        lines[4] = '{"ticker": "T999", ' + lines[4][1:]
    else:
        # The canonical value last (what a naive loader keeps); a corrupted one hidden before it.
        overlay = json.dumps(row["integrated_decision_v1"])
        lines[4] = json.dumps({"ticker": row["ticker"]})[:-1] + ', "integrated_decision_v1": {"' + key + '": "HIDDEN", ' + overlay[1:] + "}"
    path.write_text("\n".join(lines) + "\n")
    _refused(source, f"M1_AI_DELIVERY_DUPLICATE_KEY:{key}")


def test_the_guard_never_rewrites_its_inputs(tmp_path):
    import hashlib
    source = _operation(tmp_path)

    def snapshot():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    before = snapshot()
    _verify(source)
    _rewrite_bundle(source, _PROJECTION_MUTATIONS["unknown_position_to_held"][0])
    corrupted = snapshot()
    with pytest.raises(workflow.OwnerDailyError):
        _verify(source)
    assert snapshot() == corrupted and corrupted != before


# ---- sealed-authority bypasses (independent delta review)

def _strip_distribution(bundle: dict) -> None:
    bundle["integrated_decision_overlay_v1"]["coverage"].pop("evidence_currency_distribution")


_APPLICABILITY_DOWNGRADES = {
    "distribution_removed": (_strip_distribution, "M1_AI_DELIVERY_OVERLAY_HEADER_MISMATCH:coverage"),
    "coverage_removed": (lambda b: b["integrated_decision_overlay_v1"].pop("coverage"),
                         "M1_AI_DELIVERY_OVERLAY_HEADER_MISMATCH:coverage"),
    "overlay_removed": (lambda b: b.pop("integrated_decision_overlay_v1"),
                        "M1_AI_DELIVERY_OVERLAY_HEADER_MISMATCH:<object>"),
    "overlay_malformed": (lambda b: b.update(integrated_decision_overlay_v1=["not", "a", "mapping"]),
                          "M1_AI_DELIVERY_OVERLAY_HEADER_MISMATCH:<object>"),
    "brief_marker_removed": (lambda b: b["integrated_decision_overlay_v1"].update(daily_integrated_decision_brief_identity=None),
                             "M1_AI_DELIVERY_OVERLAY_HEADER_MISMATCH:daily_integrated_decision_brief_identity"),
    "bundle_operation_rebound": (lambda b: b.update(operation_identity="daily_research_session_operation:other"),
                                 "M1_AI_DELIVERY_BINDING_MISMATCH:operation_identity"),
}


@pytest.mark.parametrize("name", sorted(_APPLICABILITY_DOWNGRADES))
def test_a_delivery_cannot_downgrade_an_m1_operation(monkeypatch, tmp_path, name):
    # Codex bypass: corrupt HPG-style position AND strip the delivery's M1 marker. The sealed
    # manifest still declares M1, so this fails -- never DECLARED_BRIEF_VERIFIED, never published.
    downgrade, reason = _APPLICABILITY_DOWNGRADES[name]
    source = _operation(tmp_path)
    _rewrite_bundle(source, _PROJECTION_MUTATIONS["unknown_position_to_held"][0])
    _rewrite_bundle(source, downgrade)
    captured = _publish_stubs(monkeypatch, source)
    with pytest.raises(workflow.OwnerDailyError, match="^" + re.escape(reason) + "$"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source))
    assert "called" not in captured


def test_m1_applicability_comes_only_from_the_sealed_manifest(tmp_path):
    source = _operation(tmp_path)
    _rewrite_bundle(source, _strip_distribution)
    manifest = json.loads((source / "run_manifest.json").read_text())
    assert workflow._sealed_m1_applicable(manifest)
    assert workflow.resolve_m1_handoff_authority(source, SESSION, root=_root(source), manifest=manifest) is not None


def test_the_sealed_manifest_cannot_be_downgraded(monkeypatch, tmp_path):
    from daily_research_session_operations import _identity as operation_identity_of
    # Editing the manifest's M1 marker breaks its own identity ...
    source = _operation(tmp_path)
    original = _operation_identity(source)
    _rewrite_json(source / "run_manifest.json",
                  lambda m: m["coverage_summary"]["integrated_investment_decision"].pop("evidence_currency_distribution"))
    _refused(source, "OPERATION_MANIFEST_IDENTITY_MISMATCH")

    # ... and re-sealing it (with the delivery stripped to match) is no longer the completed Daily's operation.
    def reseal(manifest):
        manifest["operation_identity"] = operation_identity_of(manifest)
    _rewrite_json(source / "run_manifest.json", reseal)
    _rewrite_bundle(source, _strip_distribution)
    captured = _publish_stubs(monkeypatch, source)
    with pytest.raises(workflow.OwnerDailyError, match="^OPERATION_MANIFEST_NOT_THE_COMPLETED_DAILY_OPERATION$"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source, operation_id=original))
    assert "called" not in captured


def _forge_product(source: Path, mutate) -> None:
    """Codex bypass: replace the Daily product, recompute its identity, rebind the bundle to it."""
    import current_daily_decision_research_product as daily_product_contract
    path = source / "current_daily_decision_research_product_artifact.json"
    product = json.loads(path.read_text())
    mutate(product)
    product.update(daily_product_contract.content_identity(product))
    path.write_text(json.dumps(product))

    def rebind(bundle):
        bundle["product_identity"] = product["artifact_identity"]
        bundle["ticker_research_contexts"] = {t: c for t, c in bundle["ticker_research_contexts"].items()
                                              if t in product["detailed_research_cards"]}
        bundle["owner_focus_research_contexts"] = [r for r in bundle["owner_focus_research_contexts"]
                                                   if r["ticker"] in product["owner_focus"]["tickers"]]
    _rewrite_bundle(source, rebind)


@pytest.mark.parametrize("forgery", [
    lambda p: p.update(detailed_research_cards={}),                        # zero scoped cards
    lambda p: p["owner_focus"].update(tickers=["T000"]),                   # altered owner focus
])
def test_a_forged_replacement_daily_product_is_refused(monkeypatch, tmp_path, forgery):
    source = _operation(tmp_path)
    _forge_product(source, forgery)
    captured = _publish_stubs(monkeypatch, source)
    with pytest.raises(workflow.OwnerDailyError, match="^M1_CANONICAL_DAILY_PRODUCT_IDENTITY_MISMATCH$"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source))
    assert "called" not in captured


@pytest.mark.parametrize("case, reason", [
    ("no_root", "M1_CANONICAL_ROOT_NOT_SUPPLIED"),
    ("iid_absent", "M1_CANONICAL_INTEGRATED_DECISION_UNAVAILABLE"),
    ("iid_edited_without_identity", "M1_CANONICAL_INTEGRATED_DECISION_IDENTITY_MISMATCH"),
    ("iid_of_another_session", "M1_CANONICAL_INTEGRATED_DECISION_IDENTITY_MISMATCH"),
    ("product_absent", "M1_CANONICAL_DAILY_PRODUCT_UNAVAILABLE"),
    ("product_cards_edited", "M1_CANONICAL_DAILY_PRODUCT_IDENTITY_MISMATCH"),
    ("bundle_bound_to_another_product", "M1_AI_DELIVERY_BINDING_MISMATCH:product_identity"),
    ("brief_wrapper_of_another_operation", "M1_DAILY_BRIEF_RETENTION_IDENTITY_MISMATCH"),
    ("manifest_absent", "OPERATION_MANIFEST_UNAVAILABLE"),
    ("manifest_other_session", "OPERATION_MANIFEST_SESSION_MISMATCH"),
])
def test_m1_guard_requires_the_sealed_identity_chain(tmp_path, case, reason):
    source = _operation(tmp_path)
    iid_path = next(_root(source).rglob("integrated_investment_decision_product.json"))
    if case == "no_root":
        with pytest.raises(workflow.OwnerDailyError, match=f"^{reason}$"):
            workflow.verify_retained_daily_brief_for_handoff(source, SESSION)
        return
    if case == "iid_absent":
        iid_path.unlink()
    elif case == "iid_edited_without_identity":
        # Rewriting the canonical record to match a corrupted delivery is itself caught.
        _rewrite_json(iid_path, lambda a: a["records"]["T000"].update(position_context={"position_state": "HELD"}))
    elif case == "iid_of_another_session":
        _rewrite_json(iid_path, lambda a: a.update(session="2026-09-23"))
    elif case == "product_absent":
        (source / "current_daily_decision_research_product_artifact.json").unlink()
    elif case == "product_cards_edited":
        _rewrite_json(source / "current_daily_decision_research_product_artifact.json",
                      lambda a: a["detailed_research_cards"].pop("T002"))
    elif case == "bundle_bound_to_another_product":
        _rewrite_bundle(source, lambda b: b.update(product_identity="current_daily_decision_research_product:other"))
    elif case == "brief_wrapper_of_another_operation":
        _rewrite_json(source / "daily_integrated_decision_brief_artifact.json",
                      lambda w: w.update(daily_operation_identity="daily_research_session_operation:other"))
    elif case == "manifest_absent":
        (source / "run_manifest.json").unlink()
    elif case == "manifest_other_session":
        _rewrite_json(source / "run_manifest.json", lambda m: m.update(market_session="2026-09-23"))
    _refused(source, reason)


@pytest.mark.parametrize("corruption", sorted(_PROJECTION_MUTATIONS) + sorted(_SCOPE_MUTATIONS))
def test_no_m1_failure_falls_back_to_the_pre_m1_route(monkeypatch, tmp_path, corruption):
    # Any M1 contract failure stays a failure: never DECLARED_BRIEF_VERIFIED / LEGACY, never published.
    mutate = (_PROJECTION_MUTATIONS.get(corruption) or _SCOPE_MUTATIONS[corruption])[0]
    source = _operation(tmp_path)
    _rewrite_bundle(source, mutate)
    _rewrite_bundle(source, _strip_distribution)
    captured = _publish_stubs(monkeypatch, source)
    with pytest.raises(workflow.OwnerDailyError):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source))
    assert "called" not in captured


# ---- Brief retention wrapper identity (final delta review)
# The wrapper's artifact_sha256 was checked but its declared artifact_identity was not: a forged or
# deleted identity still verified. Under the retention contract the identity is the recomputed
# digest under the contract prefix (daily_research_session_operations.brief_retention_identity).

_WRAPPER = "daily_integrated_decision_brief_artifact.json"
_WRAPPER_IDENTITY = "M1_DAILY_BRIEF_RETENTION_IDENTITY_MISMATCH"
_WRAPPER_BINDING = "M1_DAILY_BRIEF_RETENTION_BINDING_MISMATCH"


def _reseal(wrapper: dict) -> None:
    from daily_research_session_operations import brief_retention_identity
    wrapper.update(brief_retention_identity(wrapper))


def _rebind_and_reseal(key: str, value: str):
    def mutate(wrapper, _other):
        wrapper[key] = value
        _reseal(wrapper)
    return mutate


_WRAPPER_TAMPERS = {
    "missing_artifact_identity": (lambda w, o: w.pop("artifact_identity"), _WRAPPER_IDENTITY),
    "random_forged_identity": (lambda w, o: w.update(artifact_identity="forged"), _WRAPPER_IDENTITY),
    "forged_well_formed_identity": (lambda w, o: w.update(
        artifact_identity="daily_session_integrated_decision_brief_artifact:" + "0" * 64), _WRAPPER_IDENTITY),
    "identity_of_another_brief": (lambda w, o: w.update(artifact_identity=o["artifact_identity"]), _WRAPPER_IDENTITY),
    "identity_and_sha_of_another_brief": (lambda w, o: w.update(artifact_identity=o["artifact_identity"],
                                                                  artifact_sha256=o["artifact_sha256"]), _WRAPPER_IDENTITY),
    "valid_sha_bad_identity_prefix": (lambda w, o: w.update(
        artifact_identity="daily_integrated_decision_brief/v1:" + w["artifact_sha256"]), _WRAPPER_IDENTITY),
    "valid_identity_bad_sha": (lambda w, o: w.update(artifact_sha256="0" * 64), _WRAPPER_IDENTITY),
    "missing_sha": (lambda w, o: w.pop("artifact_sha256"), _WRAPPER_IDENTITY),
    "content_edited_identity_kept": (lambda w, o: w.update(schema_version="9.9.9"), _WRAPPER_IDENTITY),
    "other_contract_resealed": (_rebind_and_reseal("contract_version", "daily_session_integrated_decision_brief_artifact/v2"),
                                _WRAPPER_IDENTITY),
    "wrong_operation_binding_resealed": (_rebind_and_reseal("daily_operation_identity", "daily_research_session_operation:other"),
                                         _WRAPPER_BINDING),
    "wrong_iid_binding_resealed": (_rebind_and_reseal("integrated_investment_decision_product_identity",
                                                      "integrated_investment_decision_product/v1:other"), _WRAPPER_BINDING),
}


def test_the_valid_retained_wrapper_is_self_identifying_and_passes(monkeypatch, tmp_path):
    from daily_research_session_operations import brief_retention_identity
    source = _operation(tmp_path)
    wrapper = json.loads((source / _WRAPPER).read_text())
    assert {key: wrapper[key] for key in ("artifact_sha256", "artifact_identity")} == brief_retention_identity(wrapper)
    captured = _publish_stubs(monkeypatch, source)
    result = workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source))
    assert result["daily_brief_check"]["status"] == "M1_BRIEF_AND_INDEX_VERIFIED"
    assert captured.get("called") is True


@pytest.mark.parametrize("strip_marker", [False, True])
@pytest.mark.parametrize("name", sorted(_WRAPPER_TAMPERS))
def test_a_wrapper_that_is_not_its_own_sealed_identity_is_refused(monkeypatch, tmp_path, name, strip_marker):
    tamper, reason = _WRAPPER_TAMPERS[name]
    other_root = tmp_path / "other"
    other_root.mkdir()
    other = json.loads((_operation(other_root, denominator=9) / _WRAPPER).read_text())  # a different Brief
    base = tmp_path / "base"
    base.mkdir()
    source = _operation(base)
    _rewrite_json(source / _WRAPPER, lambda w: tamper(w, other))
    if strip_marker:  # no pre-M1 fallback either
        _rewrite_bundle(source, _strip_distribution)
    with pytest.raises(workflow.OwnerDailyError, match="^" + re.escape(reason) + "$"):
        _verify(source)
    captured = _publish_stubs(monkeypatch, source)
    with pytest.raises(workflow.OwnerDailyError, match="^" + re.escape(reason) + "$"):
        workflow.publish_ai_handoff(_root(source), tmp_path / "handoff", _completion(source))
    assert "called" not in captured


def test_the_writer_and_the_verifier_share_one_wrapper_identity_rule():
    import inspect
    import daily_research_session_operations as operations
    assert "brief_retention_identity" in inspect.getsource(operations._integrated_brief_retention_artifact)
    assert "brief_retention_identity" in inspect.getsource(workflow.resolve_m1_handoff_authority)
