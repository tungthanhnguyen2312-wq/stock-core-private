"""Locale-independent subprocess capture for isolated operational harnesses."""
from __future__ import annotations
import subprocess
from typing import Sequence
from pathlib import Path
def run_utf8(command: Sequence[str], **kwargs):
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
    stdout=result.stdout.decode("utf-8",errors="replace")
    stderr=result.stderr.decode("utf-8",errors="replace")
    return result.returncode,stdout,stderr


def write_utf8(path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")
