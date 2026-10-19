"""Split code/evidence roots: frozen inputs recorded as absolute retained paths (2026-10-19)."""
from __future__ import annotations

import json
from pathlib import Path

import pending_session_input_freeze as freeze


def _artifact(path: Path, identity: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"artifact_identity": identity}), encoding="utf-8")


def _bind_retained(monkeypatch, retained: Path | None) -> None:
    import runtime_paths
    monkeypatch.delenv("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", raising=False)
    monkeypatch.setattr(
        runtime_paths, "workspace_profile",
        (lambda **_k: {"paths": {"retained": retained}}) if retained else (lambda **_k: None),
    )


def test_absolute_path_inside_governed_retained_root_is_admitted(tmp_path, monkeypatch):
    producer, retained = tmp_path / "producer", tmp_path / "retained"
    producer.mkdir()
    target = retained / "operations-review/x-v1-20261019/a.json"
    _artifact(target, "x:1")
    _bind_retained(monkeypatch, retained)
    assert freeze._artifact_matches(producer, {"path": str(target), "artifact_identity": "x:1"}, "x:1")


def test_absolute_path_identity_is_still_verified(tmp_path, monkeypatch):
    producer, retained = tmp_path / "producer", tmp_path / "retained"
    producer.mkdir()
    target = retained / "operations-review/x/a.json"
    _artifact(target, "x:other")
    _bind_retained(monkeypatch, retained)
    assert not freeze._artifact_matches(producer, {"path": str(target), "artifact_identity": "x:1"}, "x:1")


def test_absolute_path_outside_retained_root_is_refused(tmp_path, monkeypatch):
    producer, retained = tmp_path / "producer", tmp_path / "retained"
    producer.mkdir()
    retained.mkdir()
    outside = tmp_path / "elsewhere/a.json"
    _artifact(outside, "x:1")
    _bind_retained(monkeypatch, retained)
    assert not freeze._artifact_matches(producer, {"path": str(outside), "artifact_identity": "x:1"}, "x:1")


def test_absolute_path_without_split_roots_is_refused(tmp_path, monkeypatch):
    producer = tmp_path / "producer"
    target = producer / "operations-review/x/a.json"
    _artifact(target, "x:1")
    _bind_retained(monkeypatch, None)
    # Single-root legacy contract unchanged: recorded paths must be checkout-relative.
    assert not freeze._artifact_matches(producer, {"path": str(target), "artifact_identity": "x:1"}, "x:1")
    assert freeze._artifact_matches(producer, {"path": "operations-review/x/a.json", "artifact_identity": "x:1"}, "x:1")


def test_unqualified_profile_admits_nothing_extra(tmp_path, monkeypatch):
    import runtime_paths
    producer, retained = tmp_path / "producer", tmp_path / "retained"
    producer.mkdir()
    target = retained / "operations-review/x/a.json"
    _artifact(target, "x:1")

    def refuse(**_k):
        raise RuntimeError("workspace volume wrong/unavailable")

    monkeypatch.setattr(runtime_paths, "workspace_profile", refuse)
    assert not freeze._artifact_matches(producer, {"path": str(target), "artifact_identity": "x:1"}, "x:1")
