"""The Claude SDK install hint must name the exact Python that runs ShortsRadar."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from shortsradar import ai


def fake_app(key: str = "sk-ant-test"):
    return SimpleNamespace(settings=SimpleNamespace(get=lambda k: key if k == "anthropic_api_key" else None))


@mock.patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": ""})
class SdkInstallHintTests(unittest.TestCase):
    def status(self, sdk=False, managed=False, key="sk-ant-test", min_python=(3, 0)):
        with mock.patch.object(ai, "sdk_available", return_value=sdk), \
                mock.patch.object(ai, "_externally_managed", return_value=managed), \
                mock.patch.object(ai, "SDK_MIN_PYTHON", min_python):
            return ai.status(fake_app(key))

    def test_command_targets_the_running_python(self):
        st = self.status()
        self.assertFalse(st["ready"])
        cmd = st["install"]["command"]
        self.assertEqual(cmd, f'{ai._shell_quote(sys.executable)} -m pip install "anthropic>=1.8"')
        self.assertTrue(st["install"]["python_ok"])
        self.assertIn(cmd, st["hint"])
        self.assertIn("restart", st["hint"])

    def test_externally_managed_python_installs_into_a_venv(self):
        st = self.status(managed=True)
        cmd = st["install"]["command"]
        self.assertTrue(st["install"]["venv"])
        self.assertTrue(cmd.startswith("cd "))
        self.assertIn(" -m venv .venv && .venv/bin/python -m pip install \"anthropic>=1.8\"", cmd)
        self.assertIn("start.sh", st["install"]["after"])

    def test_python_too_old(self):
        st = self.status(min_python=(99, 0))
        self.assertFalse(st["install"]["python_ok"])
        self.assertIn("python.org", st["hint"])
        self.assertNotIn("pip install", st["hint"])

    def test_ready_when_sdk_and_key_present(self):
        st = self.status(sdk=True)
        self.assertTrue(st["ready"])
        self.assertIsNone(st["install"])
        self.assertIsNone(st["hint"])

    def test_missing_key_comes_first(self):
        st = self.status(key="")
        self.assertIn("API key", st["hint"])
        self.assertIsNotNone(st["install"])  # Settings still shows the install command

    def test_paths_with_spaces_are_quoted(self):
        self.assertEqual(ai._shell_quote("/usr/bin/python3"), "/usr/bin/python3")
        self.assertEqual(ai._shell_quote("/Users/My Name/.pyenv/bin/python3"), "'/Users/My Name/.pyenv/bin/python3'")
        with mock.patch.object(ai.os, "name", "nt"):
            self.assertEqual(ai._shell_quote(r"C:\Python313\python.exe"), r"C:\Python313\python.exe")
            self.assertEqual(ai._shell_quote(r"C:\Program Files\Python313\python.exe"), r'"C:\Program Files\Python313\python.exe"')


if __name__ == "__main__":
    unittest.main()
