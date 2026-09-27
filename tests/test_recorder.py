"""
Tests for FixtureRecorder and record_fixtures.py CLI.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from record_fixtures import main as recorder_main
from spielerplus.client import SpielerPlusClient
from spielerplus.rate_limiter import RateLimiter
from spielerplus.recorder import FixtureRecorder, sanitize_html
from tests.mock_server import MockSpielerPlusServer


class TestRecorder(unittest.TestCase):
    server: MockSpielerPlusServer

    @classmethod
    def setUpClass(cls):
        cls.server = MockSpielerPlusServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.tmp_dir.name)
        limiter = RateLimiter(delay=0.0, jitter=0.0, max_retries=1, sleeper=lambda d: None)
        self.client = SpielerPlusClient(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            rate_limiter=limiter,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_sanitize_html(self):
        html = '<p>Contact me at user@real.de or help</p>'
        sanitized = sanitize_html(html, email="user@real.de")
        self.assertNotIn("user@real.de", sanitized)
        self.assertIn("user@example.com", sanitized)

    def test_fixture_recorder_with_team_ics_failure(self):
        recorder = FixtureRecorder(
            client=self.client,
            output_dir=self.out_dir,
            sanitize=True,
        )
        orig_fetch = self.client.fetch_team_ics
        self.client.fetch_team_ics = lambda: (_ for _ in ()).throw(RuntimeError("ICS fetch fail"))
        recorded = recorder.record_all(max_teams=1)
        self.assertNotIn("calendar_feed_12345", recorded)
        self.client.fetch_team_ics = orig_fetch

    def test_fixture_recorder_with_participation_failure(self):
        recorder = FixtureRecorder(
            client=self.client,
            output_dir=self.out_dir,
            sanitize=True,
        )
        orig_post = self.client._post
        # Force exception when recording participation
        self.client._post = lambda path, **kw: (_ for _ in ()).throw(RuntimeError("Part fail")) if "participation" in path else orig_post(path, **kw)
        recorded = recorder.record_all(max_teams=1)
        self.assertNotIn("participation", recorded)
        self.client._post = orig_post
        recorder = FixtureRecorder(
            client=self.client,
            output_dir=self.out_dir,
            sanitize=True,
        )
        recorded = recorder.record_all(max_teams=2)
        self.assertIn("login", recorded)
        self.assertIn("dashboard", recorded)
        self.assertIn("select_team", recorded)
        self.assertTrue((self.out_dir / "login.html").is_file())
        self.assertTrue((self.out_dir / "dashboard.html").is_file())
        self.assertTrue((self.out_dir / "select_team.html").is_file())
        self.assertTrue((self.out_dir / "metadata.json").is_file())

    def test_recorder_cli_missing_credentials(self):
        for k in list(os.environ.keys()):
            if k.startswith("SPIELERPLUS_"):
                del os.environ[k]
        code = recorder_main(["--output-dir", str(self.out_dir), "--env-file", "non_existent.env"])
        self.assertEqual(code, 1)

    def test_recorder_cli_success(self):
        os.environ["SPIELERPLUS_EMAIL"] = "test@example.com"
        os.environ["SPIELERPLUS_PASSWORD"] = "correctpassword"
        os.environ["SPIELERPLUS_BASE_URL"] = self.server.url
        os.environ["SPIELERPLUS_RATE_LIMIT_DELAY"] = "0"
        os.environ["SPIELERPLUS_RATE_LIMIT_JITTER"] = "0"
        try:
            code = recorder_main(["--output-dir", str(self.out_dir), "-v"])
            self.assertEqual(code, 0)
        finally:
            for k in list(os.environ.keys()):
                if k.startswith("SPIELERPLUS_"):
                    del os.environ[k]

    def test_recorder_cli_exception_returns_code_2(self):
        from unittest.mock import patch
        with patch("record_fixtures.FixtureRecorder.record_all", side_effect=RuntimeError("Boom")):
            os.environ["SPIELERPLUS_EMAIL"] = "test@example.com"
            os.environ["SPIELERPLUS_PASSWORD"] = "correctpassword"
            try:
                code = recorder_main(["--output-dir", str(self.out_dir)])
                self.assertEqual(code, 2)
            finally:
                for k in list(os.environ.keys()):
                    if k.startswith("SPIELERPLUS_"):
                        del os.environ[k]


if __name__ == "__main__":
    unittest.main()
