#!/usr/bin/env python3
"""Producer-owned Python helper to build Tailwind CSS offline.

Replaces legacy build_frontend.bat with strict Python subprocess execution (shell=False).
Supports --live for live disk updates and dry-run (default) for zero-mutation checks.
"""

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import subprocess
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def build_frontend(web_dir: Path | None = None, live: bool = False) -> int:
    root = (web_dir or SCRIPT_ROOT).resolve()
    tailwind_exe = root / "tools" / "tailwind" / "tailwindcss.exe"
    tailwind_config = root / "tailwind.config.js"
    tailwind_input = root / "assets" / "css" / "tailwind.src.css"
    tailwind_output = root / "assets" / "css" / "tailwind.generated.css"

    print("============================================================")
    print(f"BUILD FRONTEND (Python helper) - Tailwind CSS v3.4.19")
    print(f"Web Root : {root}")
    print(f"Mode     : {'LIVE' if live else 'DRY-RUN (zero-mutation)'}")
    print("============================================================")

    if not tailwind_exe.is_file():
        sys.stderr.write(f"[ERROR] Tailwind CLI not found at: {tailwind_exe}\n")
        return 1
    if not tailwind_config.is_file():
        sys.stderr.write(f"[ERROR] Missing config: {tailwind_config}\n")
        return 1
    if not tailwind_input.is_file():
        sys.stderr.write(f"[ERROR] Missing input CSS: {tailwind_input}\n")
        return 1

    temp_fd, temp_path_str = tempfile.mkstemp(prefix="tailwind_tmp_", suffix=".css")
    os.close(temp_fd)
    temp_path = Path(temp_path_str)

    try:
        cmd = [
            str(tailwind_exe),
            "-i", str(tailwind_input),
            "-o", str(temp_path),
            "-c", str(tailwind_config),
            "--minify",
        ]
        print(f"Building Tailwind CSS to temporary target: {temp_path}")
        res = subprocess.run(cmd, cwd=root, capture_output=True, text=True, shell=False)
        if res.returncode != 0:
            sys.stderr.write(f"[ERROR] Tailwind build failed (code {res.returncode}): {res.stderr}\n")
            return res.returncode

        if not temp_path.is_file() or temp_path.stat().st_size == 0:
            sys.stderr.write("[ERROR] Build reported success but temp output file is empty/missing.\n")
            return 1

        if live:
            tailwind_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_path, tailwind_output)
            print(f"[OK] Frontend build complete (LIVE updated): {tailwind_output}")
        else:
            print(f"[OK] Frontend build check complete (DRY-RUN zero-mutation): {tailwind_output} remains unchanged.")
        return 0
    finally:
        if temp_path.is_file():
            try:
                temp_path.unlink()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Tailwind CSS offline (Python helper).")
    parser.add_argument("--live", action="store_true", help="Cho phép ghi file tailwind.generated.css thật")
    parser.add_argument("--web-dir", type=str, default=None, help="Thư mục web root")
    args = parser.parse_args()

    web_dir = Path(args.web_dir).resolve() if args.web_dir else None
    return build_frontend(web_dir=web_dir, live=args.live)


if __name__ == "__main__":
    sys.exit(main())
