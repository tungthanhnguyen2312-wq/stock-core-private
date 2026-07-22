import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from runtime_paths import RUNTIME_ROOT_ENV, runtime_root


class RuntimeRootTests(unittest.TestCase):
    def setUp(self):
        self.original = os.environ.pop(RUNTIME_ROOT_ENV, None)
        self.addCleanup(self._restore_environment)

    def _restore_environment(self):
        if self.original is not None:
            os.environ[RUNTIME_ROOT_ENV] = self.original

    def test_uses_legacy_default_when_unset(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(runtime_root(directory), Path(directory).resolve())

    def test_uses_process_cwd_when_no_default_is_given(self):
        with mock.patch.dict(os.environ, {RUNTIME_ROOT_ENV: ""}, clear=False):
            self.assertEqual(runtime_root(), Path.cwd().resolve())
    def test_uses_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            configured = Path(directory) / "dashboard-runtime"
            os.environ[RUNTIME_ROOT_ENV] = str(configured)
            self.assertEqual(runtime_root(Path("ignored")), configured.resolve())
