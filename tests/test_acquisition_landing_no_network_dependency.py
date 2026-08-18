"""Architectural test: the deterministic retention/checkpoint/quarantine/
identity core must have zero network or LLM dependency. Enforced by
inspecting real AST Import/ImportFrom nodes (not a bare substring check,
which this repo has previously had to loosen after a false positive on
documentation prose - see docs/acquisition_landing_framework.md)."""

import ast
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent

DETERMINISTIC_CORE_MODULES = (
    "acquisition_landing_contract.py",
    "acquisition_landing_atomic_io.py",
    "acquisition_landing_identity.py",
    "acquisition_landing_isolation.py",
    "acquisition_landing_quarantine.py",
    "acquisition_landing_retention.py",
    "acquisition_landing_checkpoint.py",
)

FORBIDDEN_TOP_LEVEL_MODULES = {
    "requests",
    "urllib",
    "urllib2",
    "urllib3",
    "socket",
    "http",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "websockets",
    "websocket",
    "anthropic",
    "openai",
    "google",
    "cohere",
}


def _imported_top_level_modules(source: str) -> set:
    tree = ast.parse(source)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    return found


class NoNetworkOrLlmDependencyTests(unittest.TestCase):
    def test_deterministic_core_modules_exist(self):
        for filename in DETERMINISTIC_CORE_MODULES:
            self.assertTrue((MODULE_ROOT / filename).exists(), f"missing {filename}")

    def test_deterministic_core_modules_import_no_networking_or_llm_libraries(self):
        for filename in DETERMINISTIC_CORE_MODULES:
            path = MODULE_ROOT / filename
            with self.subTest(module=filename):
                source = path.read_text(encoding="utf-8")
                imported = _imported_top_level_modules(source)
                offenders = imported & FORBIDDEN_TOP_LEVEL_MODULES
                self.assertEqual(offenders, set(), f"{filename} imports forbidden module(s): {offenders}")


if __name__ == "__main__":
    unittest.main()
