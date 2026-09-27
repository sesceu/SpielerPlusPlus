"""
Tests for main.py CLI interface.
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import main
from spielerplus.rate_limiter import AuthenticationError, SpielerPlusError
from tests.mock_server import MockSpielerPlusServer


class TestMain(unittest.TestCase):
    server: MockSpielerPlusServer

    @classmethod
    def setUpClass(cls):
        cls.server = MockSpielerPlusServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        os.environ["SPIELERPLUS_EMAIL"] = "test@example.com"
        os.environ["SPIELERPLUS_PASSWORD"] = "correctpassword"
        os.environ["SPIELERPLUS_BASE_URL"] = self.server.url
        os.environ["SPIELERPLUS_RATE_LIMIT_DELAY"] = "0"
        os.environ["SPIELERPLUS_RATE_LIMIT_JITTER"] = "0"
        os.environ["CALDAV_URL"] = "https://mock.caldav/dav"
        os.environ["CALDAV_USERNAME"] = "mockuser"
        os.environ["CALDAV_PASSWORD"] = "mockpass"
        os.environ["CALDAV_CALENDAR"] = "SpielerPlus"
        os.environ["CI"] = "false"

    def tearDown(self):
        os.environ.pop("CI", None)
        for k in list(os.environ.keys()):
            if k.startswith("SPIELERPLUS_") or k.startswith("CALDAV_"):
                del os.environ[k]

    def test_missing_credentials(self):
        os.environ["SPIELERPLUS_EMAIL"] = ""
        os.environ["SPIELERPLUS_PASSWORD"] = ""
        exit_code = main([])
        self.assertEqual(exit_code, 1)

    def test_missing_caldav_credentials(self):
        os.environ["CALDAV_URL"] = ""
        exit_code = main([])
        self.assertEqual(exit_code, 1)

    def test_dry_run_success(self):
        with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            exit_code = main(["--dry-run", "-v"])
            self.assertEqual(exit_code, 0)
            output = fake_out.getvalue()
            self.assertIn("Dry-run complete", output)

    def test_sync_caldav_success(self):
        with patch("spielerplus.sync.SyncEngine.run", return_value={"created": 1, "updated": 0, "unchanged": 2}):
            exit_code = main(["--team", "12345"])
            self.assertEqual(exit_code, 0)

    def test_auth_error_exit_code(self):
        os.environ["SPIELERPLUS_EMAIL"] = "wrong@example.com"
        exit_code = main([])
        self.assertEqual(exit_code, 2)

    def test_spielerplus_error_exit_code(self):
        with patch("spielerplus.sync.SyncEngine.run", side_effect=SpielerPlusError("Mock SP error")):
            exit_code = main([])
            self.assertEqual(exit_code, 3)

    def test_unexpected_error_exit_code(self):
        with patch("spielerplus.sync.SyncEngine.run", side_effect=RuntimeError("Unexpected")):
            exit_code = main([])
            self.assertEqual(exit_code, 4)



    def test_test_auth_missing_sp_credentials(self):
        os.environ["SPIELERPLUS_EMAIL"] = ""
        exit_code = main(["--test-auth"])
        self.assertEqual(exit_code, 1)

    def test_test_auth_missing_caldav_credentials(self):
        os.environ["CALDAV_PASSWORD"] = ""
        exit_code = main(["--test-auth"])
        self.assertEqual(exit_code, 1)

    @patch("spielerplus.caldav_client.CaldavClient.check_connection")
    def test_test_auth_success_with_target_cal(self, mock_check):
        mock_check.return_value = {
            "calendars": ["SpielerPlus", "Work"],
            "target_calendar_exists": True,
        }
        with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            exit_code = main(["--test-auth"])
            self.assertEqual(exit_code, 0)
            out = fake_out.getvalue()
            self.assertIn("Testing SpielerPlus Authentication", out)
            self.assertIn("Testing CalDAV Connection", out)
            self.assertIn("Target calendar 'SpielerPlus' exists", out)

    @patch("spielerplus.caldav_client.CaldavClient.check_connection")
    def test_test_auth_success_without_target_cal(self, mock_check):
        mock_check.return_value = {
            "calendars": [],
            "target_calendar_exists": False,
        }
        with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            exit_code = main(["--test-auth"])
            self.assertEqual(exit_code, 0)
            out = fake_out.getvalue()
            self.assertIn("Target calendar 'SpielerPlus' does not exist yet", out)

    @patch("spielerplus.caldav_client.CaldavClient.check_connection")
    def test_test_auth_success_ci_redaction(self, mock_check):
        os.environ["CI"] = "true"
        mock_check.return_value = {
            "calendars": ["SpielerPlus"],
            "target_calendar_exists": True,
        }
        with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
            exit_code = main(["--test-auth"])
            self.assertEqual(exit_code, 0)
            out = fake_out.getvalue()
            self.assertIn("[redacted in CI]", out)
            self.assertIn("::add-mask::", out)


    def test_test_auth_sp_auth_error(self):
        os.environ["SPIELERPLUS_EMAIL"] = "wrong@example.com"
        exit_code = main(["--test-auth"])
        self.assertEqual(exit_code, 2)

    @patch("spielerplus.client.SpielerPlusClient.login")
    def test_test_auth_sp_general_error(self, mock_login):
        mock_login.side_effect = SpielerPlusError("General SP error")
        exit_code = main(["--test-auth"])
        self.assertEqual(exit_code, 2)

    @patch("spielerplus.caldav_client.CaldavClient.check_connection")
    def test_test_auth_caldav_error(self, mock_check):
        from spielerplus.caldav_client import CaldavError
        mock_check.side_effect = CaldavError("CalDAV Auth error")
        exit_code = main(["--test-auth"])
        self.assertEqual(exit_code, 3)

if __name__ == "__main__":
    unittest.main()
