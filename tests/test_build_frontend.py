"""Unit tests for tools/build_frontend.py."""

import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tools.build_frontend as bf


class BuildFrontendTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test_build_frontend_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # Create dummy directory structure
        (self.tmp / "tools" / "tailwind").mkdir(parents=True, exist_ok=True)
        (self.tmp / "assets" / "css").mkdir(parents=True, exist_ok=True)

        self.config = self.tmp / "tailwind.config.js"
        self.input_css = self.tmp / "assets" / "css" / "tailwind.src.css"
        self.output_css = self.tmp / "assets" / "css" / "tailwind.generated.css"

        self.config.write_text("module.exports = {};\n", encoding="utf-8")
        self.input_css.write_text("/* src css */\n", encoding="utf-8")
        self.output_css.write_text("/* old generated css */\n", encoding="utf-8")

    def test_missing_tailwind_exe_fails_closed(self):
        rc = bf.build_frontend(web_dir=self.tmp, live=False)
        self.assertEqual(rc, 1, "Missing tailwind executable must fail closed")

    def test_missing_config_fails_closed(self):
        exe = self.tmp / "tools" / "tailwind" / "tailwindcss.exe"
        exe.write_text("fake", encoding="utf-8")
        self.config.unlink()
        rc = bf.build_frontend(web_dir=self.tmp, live=False)
        self.assertEqual(rc, 1, "Missing config must fail closed")

    def test_missing_input_css_fails_closed(self):
        exe = self.tmp / "tools" / "tailwind" / "tailwindcss.exe"
        exe.write_text("fake", encoding="utf-8")
        self.input_css.unlink()
        rc = bf.build_frontend(web_dir=self.tmp, live=False)
        self.assertEqual(rc, 1, "Missing input CSS must fail closed")


if __name__ == "__main__":
    unittest.main()
