"""The historical qualification CLI cannot launch or approve the retired family."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_qualification_cli_reports_retirement_without_launch(capsys):
    sys.path.insert(0, str(ROOT / "tools"))
    import run_provider_qualification as qualification

    assert qualification.main([]) == 2
    record = json.loads(capsys.readouterr().out)
    assert record["state"] == "RETIRED_PROVIDER"
    assert record["worker_launch"] == "PROHIBITED"
    assert record["live_qualification"] is False


def test_qualification_script_refuses_as_a_process():
    completed = subprocess.run([sys.executable, str(ROOT / "tools" / "run_provider_qualification.py")],
                               capture_output=True, text=True, check=False)
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["state"] == "RETIRED_PROVIDER"
