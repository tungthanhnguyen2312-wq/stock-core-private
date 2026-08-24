"""Materialize the completed HNX corpus; acquisition uses bounded slice tools."""
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('materialize_hnx_enumerable_universe_artifact.py')), run_name='__main__')
