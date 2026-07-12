import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.nightly_project_health import DEFAULT_PROJECT_ROOT, DEFAULT_REGISTRY_PATH, PROXY_ENV_VARS, run_command


class NightlyProjectHealthTest(unittest.TestCase):
    def test_defaults_use_canonical_psr_gas_checkout(self):
        self.assertEqual(str(DEFAULT_PROJECT_ROOT), r"C:\Dev\psr-gas")
        self.assertEqual(str(DEFAULT_REGISTRY_PATH), r"C:\Dev\psr-gas\arm_webapp_registry.json")

    def test_run_command_strips_proxy_environment(self):
        captured: dict[str, object] = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=b"",
                stderr=b"",
            )

        with patch("tools.nightly_project_health.subprocess.run", side_effect=fake_run):
            run_command(["python", "--version"], cwd=Path("."))

        env = captured["env"]
        self.assertIsInstance(env, dict)
        for name in PROXY_ENV_VARS:
            self.assertNotIn(name, env)
        self.assertEqual(captured["command"], ["python", "--version"])

    def test_run_command_preserves_unrelated_environment(self):
        original = os.environ.get("PROJECT_HEALTH_TEST_SENTINEL")
        os.environ["PROJECT_HEALTH_TEST_SENTINEL"] = "kept"
        captured: dict[str, object] = {}

        def fake_run(command, **kwargs):
            captured["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=b"",
                stderr=b"",
            )

        try:
            with patch("tools.nightly_project_health.subprocess.run", side_effect=fake_run):
                run_command(["python", "--version"], cwd=Path("."))
        finally:
            if original is None:
                os.environ.pop("PROJECT_HEALTH_TEST_SENTINEL", None)
            else:
                os.environ["PROJECT_HEALTH_TEST_SENTINEL"] = original

        env = captured["env"]
        self.assertIsInstance(env, dict)
        self.assertEqual(env.get("PROJECT_HEALTH_TEST_SENTINEL"), "kept")


if __name__ == "__main__":
    unittest.main()
