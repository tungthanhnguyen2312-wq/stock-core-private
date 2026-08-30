"""Test suite for canonical dashboard_release_publisher.py in Producer."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from dashboard_release_publisher import (
    DashboardReleaseError,
    publish_dashboard_release,
)


def test_publish_dashboard_release_exact_run_binding(tmp_path):
    # Setup dummy producer root & runtime root & web root
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    web_root = tmp_path / "web"
    web_root.mkdir()
    op_dir = tmp_path / "op-test-run-12345"
    op_dir.mkdir()

    session = "2026-08-28"

    # Seed runtime files
    (runtime_root / "screen_snapshot.csv").write_text(
        "ticker,exchange,date,structure,rs_rating,close\nVNM,HSX,2026-08-28,UP,85,72000\n",
        encoding="utf-8",
    )
    (runtime_root / "market_breadth.csv").write_text(
        "ticker,exchange,date\nVNM,HSX,2026-08-28\n",
        encoding="utf-8",
    )
    (runtime_root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": "2026-08-28"}}),
        encoding="utf-8",
    )
    (runtime_root / "bundle_manifest.json").write_text(
        json.dumps({"freshness": {"reference_session": "2026-08-28"}}),
        encoding="utf-8",
    )

    result = publish_dashboard_release(
        session=session,
        operation_dir=op_dir,
        runtime_root=runtime_root,
        web_root=web_root,
        replay_local=True,
    )

    assert result["status"] == "DASHBOARD_RELEASE_READY"
    assert result["market_session"] == "2026-08-28"
    assert result["producer_run_identity"] == "op-test-run-12345"

    # Verify build_info was written
    build_info = json.loads((web_root / "data" / "build_info.json").read_text(encoding="utf-8"))
    assert build_info["market_session"] == "2026-08-28"
    assert build_info["producer_run_identity"] == "op-test-run-12345"
    assert build_info["release_status"] == "READY"
    assert "screen_snapshot.csv" in build_info["files"]

    # Verify screener_data.js was written
    screener_data = (web_root / "data" / "screener_data.js").read_text(encoding="utf-8")
    assert "SCREENER_DATA_META" in screener_data
    assert "2026-08-28" in screener_data


def test_publish_dashboard_release_fails_on_mixed_session(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    web_root = tmp_path / "web"
    web_root.mkdir()
    op_dir = tmp_path / "op-mismatch"
    op_dir.mkdir()

    session = "2026-08-28"

    # Seed mismatched runtime files (analysis_latest.json has 2026-08-27)
    (runtime_root / "screen_snapshot.csv").write_text(
        "ticker,exchange,date\nVNM,HSX,2026-08-28\n",
        encoding="utf-8",
    )
    (runtime_root / "market_breadth.csv").write_text(
        "ticker,exchange,date\nVNM,HSX,2026-08-28\n",
        encoding="utf-8",
    )
    (runtime_root / "analysis_latest.json").write_text(
        json.dumps({"summary": {"session_date": "2026-08-27"}}),
        encoding="utf-8",
    )
    (runtime_root / "bundle_manifest.json").write_text(
        json.dumps({"freshness": {"reference_session": "2026-08-28"}}),
        encoding="utf-8",
    )

    with pytest.raises(DashboardReleaseError) as excinfo:
        publish_dashboard_release(
            session=session,
            operation_dir=op_dir,
            runtime_root=runtime_root,
            web_root=web_root,
            replay_local=True,
        )
    assert "MIXED_SESSION_DASHBOARD_RELEASE" in str(excinfo.value)
