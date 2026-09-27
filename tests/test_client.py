"""
Tests for SpielerPlusClient using MockSpielerPlusServer.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from bs4 import BeautifulSoup

from spielerplus.client import SpielerPlusClient
from spielerplus.rate_limiter import AuthenticationError, RateLimiter, SpielerPlusError
from tests.mock_server import MockSpielerPlusServer


class TestSpielerPlusClient(unittest.TestCase):
    server: MockSpielerPlusServer

    @classmethod
    def setUpClass(cls):
        cls.server = MockSpielerPlusServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        limiter = RateLimiter(delay=0.0, jitter=0.0, max_retries=1, sleeper=lambda d: None)
        self.client = SpielerPlusClient(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            rate_limiter=limiter,
        )

    def test_login_success(self):
        self.client.login()
        r = self.client._get("/dashboard")
        self.assertEqual(r.status_code, 200)

    def test_login_wrong_credentials(self):
        self.client.email = "wrong@example.com"
        with self.assertRaises(AuthenticationError):
            self.client.login()

    def test_login_no_form(self):
        self.client.base_url = f"{self.server.url}/site/login?no_form=1"
        with self.assertRaises(AuthenticationError):
            self.client.login()

    def test_login_no_fields(self):
        self.client.base_url = f"{self.server.url}/site/login?no_fields=1"
        with self.assertRaises(AuthenticationError):
            self.client.login()

    def test_login_form_remember_and_unnamed_input(self):
        form_html = (
            '<form action="/site/login" method="post">'
            '<input type="hidden" name="_csrf" value="csrf">'
            '<input type="email" name="email" value="">'
            '<input type="password" name="password" value="">'
            '<input type="checkbox" name="rememberMe" value="0">'
            '<input type="submit" value="Go">'
            '</form>'
        )
        orig_get = self.client._get
        orig_post = self.client._post
        self.client._get = lambda path, **kw: type("Resp", (), {
            "text": form_html if path == "/site/login" else "<html><body>Dashboard</body></html>",
            "url": "http://example.com" + path,
            "status_code": 200,
            "raise_for_status": lambda: None,
        })()
        self.client._post = lambda path, **kw: type("Resp", (), {
            "text": "ok",
            "url": "http://example.com/dashboard",
            "status_code": 302,
            "raise_for_status": lambda: None,
        })()
        self.client.login()
        self.client._get = orig_get
        self.client._post = orig_post

    def test_login_session_not_established(self):
        # Trigger dashboard redirecting back to login
        self.client.session.cookies.clear()
        # Mock _get to return /site/login URL for /dashboard
        orig_get = self.client._get
        def mock_get(path, **kwargs):
            if path == "/dashboard":
                r = orig_get(path, **kwargs)
                r.url = f"{self.client.base_url}/site/login"
                return r
            return orig_get(path, **kwargs)
        self.client._get = mock_get
        with self.assertRaises(AuthenticationError):
            self.client.login()

    def test_list_teams_and_user_name(self):
        self.client.login()
        teams = self.client.list_teams()
        self.assertGreaterEqual(len(teams), 2)
        self.assertTrue(any(t["name"] for t in teams))
        self.assertTrue(bool(self.client.user_name))

    def test_list_teams_edge_cases(self):
        # Test HTML containing items without link, link without ID, duplicated ID
        html = """
        <div class="select-team-item"><div>No link here</div></div>
        <div class="select-team-item"><a href="/site/switch-user?no_id=1">Link without id</a></div>
        <div class="select-team-item"><a href="/site/switch-user?id=123"><h4>Team 123</h4></a></div>
        <div class="select-team-item"><a href="/site/switch-user?id=123"><h4>Team 123 Dup</h4></a></div>
        """
        orig_get = self.client._get
        self.client._get = lambda path, **kw: type("Resp", (), {"text": html, "status_code": 200})()
        teams = self.client.list_teams()
        self.assertEqual(len(teams), 1)
        self.assertEqual(teams[0]["id"], 123)
        self.client._get = orig_get

    def test_switch_team(self):
        self.client.login()
        self.client.switch_team(67890)
        url = self.client.get_team_calendar_url()
        self.assertIn("team67890", url)

    def test_get_team_calendar_url_missing(self):
        self.client.login()
        self.client.base_url = f"{self.server.url}/events/calendar?no_link=1"
        with self.assertRaises(SpielerPlusError):
            self.client.get_team_calendar_url()

    def test_fetch_team_ics(self):
        self.client.login()
        ics_text = self.client.fetch_team_ics()
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("UID:", ics_text)

    def test_get_event_attendance(self):
        self.client.login()
        # Read confirmed/declined users from fixture
        import json
        with open("tests/fixtures/participation.json", encoding="utf-8") as f:
            data = json.load(f)
        soup = BeautifulSoup(data.get("html", ""), "html.parser")

        zugesagt_user = None
        abgesagt_user = None
        offen_user = None
        for b in soup.select(".participation-list"):
            head = b.select_one(".participation-list-header")
            if not head:
                continue
            txt = head.get_text().lower()
            u = b.select_one(".participation-list-user")
            if not u:
                continue
            name_node = u.select_one(".participation-list-user-name")
            name_str = name_node.get_text(strip=True) if name_node else u.get_text(strip=True)

            if "zugesagt" in txt and not zugesagt_user:
                zugesagt_user = name_str
            elif ("absage" in txt or "abwesend" in txt) and not abgesagt_user:
                abgesagt_user = name_str
            elif ("noch nicht" in txt or "offen" in txt) and not offen_user:
                offen_user = name_str

        if zugesagt_user:
            self.client.user_name = zugesagt_user
            status = self.client.get_event_attendance("training", 101)
            self.assertEqual(status, "zugesagt")

        if abgesagt_user:
            self.client.user_name = abgesagt_user
            status_declined = self.client.get_event_attendance("training", 101)
            self.assertEqual(status_declined, "abgesagt")

        if offen_user:
            self.client.user_name = offen_user
            status_offen = self.client.get_event_attendance("training", 101)
            self.assertEqual(status_offen, "offen")

    def test_get_event_attendance_block_without_header(self):
        # Also tests csrf cookie and unrecognized block header
        self.client.session.cookies.set("_csrf", "token123")
        json_data = {
            "html": (
                '<div class="participation-list"><div>No header</div></div>'
                '<div class="participation-list"><div class="participation-list-header">Unbekannte Gruppe</div></div>'
            )
        }
        orig_post = self.client._post
        self.client._post = lambda path, **kw: type("Resp", (), {
            "json": lambda *a, **k: json_data,
            "status_code": 200,
            "raise_for_status": lambda: None,
        })()
        status = self.client.get_event_attendance("training", 101)
        self.assertEqual(status, "offen")
        self.client._post = orig_post

    def test_get_event_attendance_unknown_user(self):
        self.client.login()
        self.client.user_name = "Non Existent Player"
        status = self.client.get_event_attendance("training", 101)
        self.assertEqual(status, "offen")

    def test_get_event_attendance_network_error(self):
        self.client.login()
        self.client.base_url = "http://127.0.0.1:1"
        status = self.client.get_event_attendance("training", 101)
        self.assertEqual(status, "offen")

    def test_helpers(self):
        self.assertEqual(SpielerPlusClient._status_key("Zugesagt (10)"), "zugesagt")
        self.assertEqual(SpielerPlusClient._status_key("Unsicher"), "unsicher")
        self.assertEqual(SpielerPlusClient._status_key("Absagen / Abwesend"), "abgesagt")
        self.assertEqual(SpielerPlusClient._status_key("Nicht nominiert"), "nicht_nominiert")
        self.assertEqual(SpielerPlusClient._status_key("Noch nicht geantwortet"), "offen")
        self.assertEqual(SpielerPlusClient._status_key("Noch nicht zu/abgesagt 9"), "offen")
        self.assertIsNone(SpielerPlusClient._status_key("Unbekannt"))

        err_html = '<div class="alert alert-danger">Fehler aufgetreten</div>'
        self.assertIn("Fehler", SpielerPlusClient._form_error(err_html))
        self.assertIsNone(SpielerPlusClient._form_error("<div>Kein Fehler</div>"))

        soup = BeautifulSoup('<form><input name="User[login]" type="text"><input name="pass_field" type="password"></form>', "html.parser")
        form = soup.find("form")
        self.assertEqual(SpielerPlusClient._guess_field(form, ("login", "email")), "User[login]")
        self.assertEqual(SpielerPlusClient._guess_field(form, ("password", "pass")), "pass_field")
        self.assertIsNone(SpielerPlusClient._guess_field(form, ("non_existent",)))

        soup_pw = BeautifulSoup('<form id="f1"></form><form id="f2"><input type="password"></form>', "html.parser")
        self.assertEqual(SpielerPlusClient._find_login_form(soup_pw).get("id"), "f2")


if __name__ == "__main__":
    unittest.main()
