from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from werkschau.gh_api import GhError, gh_api, rate_limit_status


def _make_result(stdout: str = "null") -> MagicMock:
    r = MagicMock()
    r.stdout = stdout
    return r


class TestGhApiLogging(unittest.TestCase):
    def test_success_emits_ok_record(self):
        with patch("subprocess.run", return_value=_make_result('{"x": 1}')):
            with self.assertLogs("werkschau.gh_api", level="DEBUG") as cm:
                gh_api("/repos/foo/bar")
        self.assertEqual(len(cm.output), 1)
        msg = cm.output[0]
        self.assertIn("/repos/foo/bar", msg)
        self.assertIn("status=ok", msg)
        self.assertIn("duration=", msg)

    def test_called_process_error_emits_failed_record(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="some error")
        with patch("subprocess.run", side_effect=exc):
            with self.assertLogs("werkschau.gh_api", level="DEBUG") as cm:
                with self.assertRaises(GhError):
                    gh_api("/repos/foo/bar")
        self.assertEqual(len(cm.output), 1)
        msg = cm.output[0]
        self.assertIn("/repos/foo/bar", msg)
        self.assertIn("status=failed", msg)
        self.assertIn("exit=1", msg)
        self.assertIn("duration=", msg)

    def test_file_not_found_emits_no_record(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with self.assertNoLogs("werkschau.gh_api", level="DEBUG"):
                with self.assertRaises(GhError):
                    gh_api("/repos/foo/bar")

    def test_retry_success_emits_two_records(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="could not resolve host")
        ok = _make_result('{"x": 1}')
        with patch("subprocess.run", side_effect=[exc, ok]):
            with patch("time.sleep"):
                with self.assertLogs("werkschau.gh_api", level="DEBUG") as cm:
                    gh_api("/repos/foo/bar")
        self.assertEqual(len(cm.output), 2)
        self.assertIn("status=failed", cm.output[0])
        self.assertIn("exit=1", cm.output[0])
        self.assertIn("status=ok", cm.output[1])

    def test_rate_limit_status_emits_no_record(self):
        payload = json.dumps({"resources": {"core": {"limit": 5000, "remaining": 4999, "reset": 9999999999}}})
        ok = _make_result(payload)
        with patch("subprocess.run", return_value=ok):
            with self.assertNoLogs("werkschau.gh_api", level="DEBUG"):
                rate_limit_status()
