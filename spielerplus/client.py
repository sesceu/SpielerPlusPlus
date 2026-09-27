"""
SpielerPlus HTTP Client (Minimal).
Authentication, team switching, official .ics fetch, and attendance check.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from spielerplus.rate_limiter import (
    AuthenticationError,
    RateLimiter,
    SpielerPlusError,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


class SpielerPlusClient:
    def __init__(
        self,
        email: str,
        password: str,
        base_url: str = "https://www.spielerplus.de",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.email = email
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter or RateLimiter()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.user_name: Optional[str] = None

    def _get(self, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", 30)
        resp = self.rate_limiter.request(self.session, "GET", url, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", 30)
        resp = self.rate_limiter.request(self.session, "POST", url, **kwargs)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------ Login
    def login(self) -> None:
        """Authenticate with SpielerPlus using CSRF extraction and form parsing."""
        login_url = f"{self.base_url}/site/login"
        r = self._get("/site/login")
        soup = BeautifulSoup(r.text, "html.parser")

        form = self._find_login_form(soup)
        if form is None:
            raise AuthenticationError("Login form not found on SpielerPlus login page.")

        action = form.get("action") or "/site/login"
        post_url = action if action.startswith("http") else urljoin(self.base_url, action)

        data = {}
        for inp in form.find_all(("input", "textarea")):
            name = inp.get("name")
            if not name:
                continue
            data[name] = inp.get("value", "")

        email_field = self._guess_field(form, ("email", "username", "login"))
        pass_field = self._guess_field(form, ("password", "pass"))
        if not email_field or not pass_field:
            raise AuthenticationError(
                f"Could not identify email or password fields. Found fields: {list(data.keys())}"
            )
        data[email_field] = self.email
        data[pass_field] = self.password

        for name in list(data.keys()):
            if "remember" in name.lower():
                data[name] = "1"

        r2 = self._post(
            post_url,
            data=data,
            headers={"Referer": login_url},
            allow_redirects=True,
        )

        err = self._form_error(r2.text)
        if err:
            raise AuthenticationError(f"Login failed: {err}")

        # Check protected dashboard
        check = self._get("/dashboard")
        if "/site/login" in check.url:
            raise AuthenticationError("Login failed: session not established. Please verify credentials.")

    # ------------------------------------------------------------------ Teams
    def list_teams(self) -> List[Dict[str, any]]:
        """List all teams, extracting team ID, team name, and user name."""
        r = self._get("/site/select-team")
        soup = BeautifulSoup(r.text, "html.parser")
        teams = []
        seen = set()

        for item in soup.select(".select-team-item"):
            a = item.find("a", href=re.compile(r"/(?:site|team)/switch-user"))
            if not a:
                continue
            m = re.search(r"[?&]id=(\d+)", a["href"])
            if not m:
                continue
            tid = int(m.group(1))
            if tid in seen:
                continue
            seen.add(tid)
            name_el = item.select_one(".select-team-item-meta h4, h4, .team-name")
            name = name_el.get_text(strip=True) if name_el else f"Team {tid}"

            meta = item.select_one(".select-team-item-meta")
            if meta:
                text_parts = [t.strip() for t in meta.stripped_strings if t.strip() != name]
                if text_parts and not self.user_name:
                    clean_name = re.sub(r"\s*\(.*?\)", "", text_parts[0]).strip()
                    if clean_name:
                        self.user_name = clean_name

            teams.append({"id": tid, "name": name})

        return teams

    def switch_team(self, team_id: int) -> None:
        """Switch active team context."""
        self._get(f"/site/switch-user?id={team_id}")

    # -------------------------------------------------------- Official .ics
    def get_team_calendar_url(self) -> str:
        """Extract official .ics subscription URL from /events/calendar."""
        r = self._get("/events/calendar")
        m = re.search(r'(?:webcal|https?)://[^\s"\'<>]+/events/ics\?([^\s"\'<>]+)', r.text)
        if not m:
            raise SpielerPlusError("Official calendar subscription link not found on /events/calendar.")

        query_str = html_lib.unescape(m.group(1)).split('"')[0].split("'")[0]
        return f"{self.base_url}/events/ics?{query_str}"

    def fetch_team_ics(self) -> str:
        """Download raw official .ics content for active team."""
        url = self.get_team_calendar_url()
        return self._get(url).text

    # ----------------------------------------------------------- Attendance
    def get_event_attendance(self, event_type: str, event_id: int) -> str:
        """
        Query /events/ajaxgetparticipation and determine user's attendance status:
        'zugesagt', 'abgesagt', 'unsicher', 'offen', or 'nicht_nominiert'.
        """
        headers = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{self.base_url}/events/index"}
        csrf = self.session.cookies.get("_csrf")
        data = {"eventid": event_id, "eventtype": event_type}
        if csrf:
            data["_csrf"] = csrf

        try:
            r = self._post("/events/ajaxgetparticipation", data=data, headers=headers)
            json_data = r.json()
            inner_html = json_data.get("html", "")
        except Exception:
            return "offen"

        soup = BeautifulSoup(inner_html, "html.parser")
        for block in soup.select(".participation-list"):
            head = block.select_one(".participation-list-header")
            if not head:
                continue
            status = self._status_key(head.get_text(" ", strip=True))
            if not status:
                continue

            for user in block.select(".participation-list-user"):
                name_el = user.select_one(".participation-list-user-name")
                name = name_el.get_text(" ", strip=True) if name_el else user.get_text(" ", strip=True)
                if self.user_name and self.user_name.lower() in name.lower():
                    return status

        return "offen"

    # ---------------------------------------------------------------- Helpers
    @staticmethod
    def _status_key(label: str) -> Optional[str]:
        low = label.lower()
        if "noch nicht" in low or "offen" in low:
            return "offen"
        if "nicht nominiert" in low:
            return "nicht_nominiert"
        if "zugesagt" in low:
            return "zugesagt"
        if "unsicher" in low:
            return "unsicher"
        if "absage" in low or "abwesend" in low or "abgesagt" in low:
            return "abgesagt"
        return None

    @staticmethod
    def _find_login_form(soup: BeautifulSoup):
        for form in soup.find_all("form"):
            if form.find("input", {"type": "password"}):
                return form
        return soup.find("form")

    @staticmethod
    def _guess_field(form, keywords) -> Optional[str]:
        if "password" in keywords:
            pw = form.find("input", {"type": "password"})
            if pw and pw.get("name"):
                return pw["name"]
        for inp in form.find_all("input"):
            name = (inp.get("name") or "") + " " + (inp.get("id") or "")
            itype = inp.get("type", "")
            if itype == "email" and "email" in keywords:
                return inp.get("name")
            if any(k in name.lower() for k in keywords):
                if inp.get("name"):
                    return inp["name"]
        return None

    @staticmethod
    def _form_error(html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        for sel in (".help-block-error", ".help-block", ".alert", "[class*=error]"):
            for node in soup.select(sel):
                txt = node.get_text(" ", strip=True)
                if txt:
                    return txt
        return None

