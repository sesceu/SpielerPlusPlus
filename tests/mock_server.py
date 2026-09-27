"""
In-process HTTP Mock Server for SpielerPlus.
Serves login, teams, official .ics feeds, and participation data for 100% offline tests.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str, fallback: str) -> str:
    """Load content from tests/fixtures if present, otherwise return default."""
    target = FIXTURES_DIR / filename
    if target.is_file():
        return target.read_text(encoding="utf-8")
    return fallback


class MockSpielerPlusHandler(BaseHTTPRequestHandler):
    active_team_id: int = 12345
    rate_limit_hits: int = 0
    server_error_hits: int = 0

    def log_message(self, format, *args):
        pass

    def _send_response_data(self, content: str, content_type: str, status: int = 200, headers: dict | None = None):
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _is_authenticated(self) -> bool:
        cookie = self.headers.get("Cookie", "")
        return "PHPSESSID=mock-session-valid" in cookie

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/site/login":
            if "no_form" in query:
                return self._send_response_data("<html><body>No form</body></html>", "text/html")
            if "no_fields" in query:
                return self._send_response_data(
                    '<html><body><form action="/site/login"><input name="_csrf" value="c1"></form></body></html>',
                    "text/html",
                )
            fallback = """<form action="/site/login" method="post"><input type="hidden" name="_csrf" value="mock-csrf"><input type="email" name="LoginForm[email]"><input type="password" name="LoginForm[password]"><input type="checkbox" name="LoginForm[rememberMe]" value="0"><input type="submit" value="Submit"></form>"""
            return self._send_response_data(load_fixture("login.html", fallback), "text/html")

        if path == "/dashboard":
            if not self._is_authenticated():
                return self._send_response_data("", "text/html", status=302, headers={"Location": "/site/login"})
            fallback = """<html><body><div class="user-menu"><a href="/user/view?id=42">Max Mustermann</a></div></body></html>"""
            return self._send_response_data(load_fixture("dashboard.html", fallback), "text/html")

        if path == "/site/select-team":
            if not self._is_authenticated():
                return self._send_response_data("", "text/html", status=302, headers={"Location": "/site/login"})
            fallback = """<html><body><div class="select-team-item"><a href="/site/switch-user?id=12345"><div class="select-team-item-meta"><h4>1. Herren</h4>Max Mustermann (Papa)</div></a></div><div class="select-team-item"><a href="/site/switch-user?id=67890"><div class="select-team-item-meta"><h4>2. Herren</h4>Max Mustermann</div></a></div></body></html>"""
            return self._send_response_data(load_fixture("select_team.html", fallback), "text/html")

        if path == "/site/switch-user":
            if not self._is_authenticated():
                return self._send_response_data("", "text/html", status=302, headers={"Location": "/site/login"})
            tids = query.get("id", [])
            if tids:
                MockSpielerPlusHandler.active_team_id = int(tids[0])
            return self._send_response_data("", "text/html", status=302, headers={"Location": "/dashboard"})

        if path == "/events/calendar":
            if not self._is_authenticated():
                return self._send_response_data("", "text/html", status=302, headers={"Location": "/site/login"})
            if "no_link" in query:
                return self._send_response_data("<html><body>Kein Kalender</body></html>", "text/html")

            tid = MockSpielerPlusHandler.active_team_id
            host = self.headers.get("Host", "127.0.0.1")
            webcal_link = f"webcal://{host}/events/ics?t=team{tid}&amp;u=user42"
            return self._send_response_data(f'<a href="{webcal_link}">Kalender abonnieren</a>', "text/html")

        if path == "/events/ics":
            tid = MockSpielerPlusHandler.active_team_id
            fb_ics = (
                "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//spielerplus.de\n"
                f"X-WR-CALNAME:SpielerPlus - Team {tid}\nX-WR-TIMEZONE:Europe/Berlin\n"
                "BEGIN:VEVENT\nUID:training.101\nSUMMARY:Training\n"
                "DTSTART;TZID=Europe/Berlin:20261001T180000\nDTEND;TZID=Europe/Berlin:20261001T193000\n"
                "LOCATION:Sporthalle\nURL:https://www.spielerplus.de/training/view?id=101\n"
                "STATUS:CONFIRMED\nEND:VEVENT\n"
                "BEGIN:VEVENT\nUID:game.102\nSUMMARY:Meisterschaftsspiel\n"
                "DTSTART;TZID=Europe/Berlin:20261004T150000\nDTEND;TZID=Europe/Berlin:20261004T170000\n"
                "LOCATION:Stadion\nURL:https://www.spielerplus.de/game/view?id=102\n"
                "STATUS:CONFIRMED\nEND:VEVENT\n"
                "BEGIN:VEVENT\nUID:training.999\nSUMMARY:Altes Training\n"
                "DTSTART;TZID=Europe/Berlin:20260101T180000\nDTEND;TZID=Europe/Berlin:20260101T193000\n"
                "LOCATION:Sporthalle\nURL:https://www.spielerplus.de/training/view?id=999\n"
                "STATUS:CONFIRMED\nEND:VEVENT\n"
                "BEGIN:VEVENT\nUID:absence.888\nSUMMARY:Abwesend\n"
                "DTSTART;VALUE=DATE:20261015\nSTATUS:CONFIRMED\nEND:VEVENT\n"
                "END:VCALENDAR"
            )
            if "full" in query:
                ics = load_fixture("calendar_feed.ics", fb_ics)
            else:
                ics = fb_ics
            return self._send_response_data(ics, "text/calendar; charset=utf-8")

        if path == "/test/rate-limit":
            MockSpielerPlusHandler.rate_limit_hits += 1
            if MockSpielerPlusHandler.rate_limit_hits == 1:
                return self._send_response_data("Rate limited", "text/plain", status=429, headers={"Retry-After": "0.1"})
            return self._send_response_data("OK", "text/plain")

        if path == "/test/server-error":
            MockSpielerPlusHandler.server_error_hits += 1
            if MockSpielerPlusHandler.server_error_hits == 1:
                return self._send_response_data("Error", "text/plain", status=500)
            return self._send_response_data("OK", "text/plain")

        return self._send_response_data("Not Found", "text/plain", status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        form_data = parse_qs(post_data)

        if path == "/site/login":
            email = form_data.get("LoginForm[email]", [""])[0]
            password = form_data.get("LoginForm[password]", [""])[0]

            if email == "wrong@example.com" or password == "wrongpass":
                html = """<html><body><div class="help-block-error">Falsche Zugangsdaten.</div></body></html>"""
                return self._send_response_data(html, "text/html", status=200)

            headers = {
                "Set-Cookie": "PHPSESSID=mock-session-valid; Path=/",
                "Location": "/dashboard",
            }
            return self._send_response_data("", "text/html", status=302, headers=headers)

        if path == "/events/ajaxgetparticipation":
            fallback = """{
              "html": "<div class=\\"participation-list\\"><h4 class=\\"participation-list-header\\">Zugesagt</h4><div class=\\"participation-list-user\\"><div class=\\"participation-list-user-name\\">Max Mustermann</div></div></div><div class=\\"participation-list\\"><h4 class=\\"participation-list-header\\">Absagen</h4><div class=\\"participation-list-user\\"><div class=\\"participation-list-user-name\\">Erika Musterfrau</div></div></div><div class=\\"participation-list\\"><h4 class=\\"participation-list-header\\">Noch nicht zu/abgesagt</h4><div class=\\"participation-list-user\\"><div class=\\"participation-list-user-name\\">Offener Spieler</div></div></div>"
            }"""
            return self._send_response_data(load_fixture("participation.json", fallback), "application/json")

        return self._send_response_data("Not Found", "text/plain", status=404)


class MockSpielerPlusServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        MockSpielerPlusHandler.active_team_id = 12345
        MockSpielerPlusHandler.rate_limit_hits = 0
        MockSpielerPlusHandler.server_error_hits = 0
        self.server = HTTPServer((host, port), MockSpielerPlusHandler)
        self.host, self.port = self.server.server_address
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

