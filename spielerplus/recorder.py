"""
Fixture recorder: connects to SpielerPlus, captures authentic responses
including official .ics feeds, and saves them as fixtures in tests/fixtures/.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from icalendar import Calendar
from spielerplus.calendar import extract_event_info
from spielerplus.client import SpielerPlusClient

logger = logging.getLogger(__name__)


def sanitize_html(html: str, email: str = "") -> str:
    """Anonymize sensitive personal info while keeping HTML/DOM structure intact."""
    result = html
    if email and email in result:
        result = result.replace(email, "user@example.com")
    return result


class FixtureRecorder:
    def __init__(
        self,
        client: SpielerPlusClient,
        output_dir: Path | str = "tests/fixtures",
        sanitize: bool = True,
    ):
        self.client = client
        self.output_dir = Path(output_dir)
        self.sanitize = sanitize

    def _save_file(self, filename: str, content: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self.output_dir / filename
        data = sanitize_html(content, self.client.email) if self.sanitize else content
        target.write_text(data, encoding="utf-8")
        logger.info("Saved fixture: %s", target)
        return target

    def record_all(self, max_teams: int = 3) -> Dict[str, str]:
        """Record all key pages including official .ics feeds."""
        recorded: Dict[str, str] = {}

        # 1. Login Page
        logger.info("Recording /site/login...")
        r_login = self.client._get("/site/login")
        self._save_file("login.html", r_login.text)
        recorded["login"] = "login.html"

        # 2. Authenticate
        logger.info("Logging into SpielerPlus...")
        self.client.login()

        # 3. Dashboard
        logger.info("Recording /dashboard...")
        r_dash = self.client._get("/dashboard")
        self._save_file("dashboard.html", r_dash.text)
        recorded["dashboard"] = "dashboard.html"

        # 4. Select Team
        logger.info("Recording /site/select-team...")
        r_teams = self.client._get("/site/select-team")
        self._save_file("select_team.html", r_teams.text)
        recorded["select_team"] = "select_team.html"

        teams = self.client.list_teams()
        logger.info("Found %d team(s): %s", len(teams), [t["name"] for t in teams])

        # 5. Process teams
        for idx, team in enumerate(teams[:max_teams]):
            tid = team["id"]
            logger.info("Switching to team '%s' (id=%d)...", team["name"], tid)
            self.client.switch_team(tid)

            # Calendar page (contains webcal subscription link)
            r_cal_page = self.client._get("/events/calendar")
            cal_page_name = f"calendar_page_{tid}.html"
            self._save_file(cal_page_name, r_cal_page.text)
            recorded[f"calendar_page_{tid}"] = cal_page_name
            if idx == 0:
                self._save_file("calendar_page.html", r_cal_page.text)
                recorded["calendar_page"] = "calendar_page.html"

            # Official .ics feed
            try:
                ics_text = self.client.fetch_team_ics()
                ics_name = f"calendar_feed_{tid}.ics"
                self._save_file(ics_name, ics_text)
                recorded[f"calendar_feed_{tid}"] = ics_name
                if idx == 0:
                    self._save_file("calendar_feed.ics", ics_text)
                    recorded["calendar_feed"] = "calendar_feed.ics"

                    if "participation" not in recorded:
                        try:
                            cal_obj = Calendar.from_ical(ics_text)
                            for ev in cal_obj.walk():
                                if ev.name == "VEVENT":
                                    info = extract_event_info(ev)
                                    if info:
                                        etype, eid = info
                                        r_part = self.client._post(
                                            "/events/ajaxgetparticipation",
                                            data={"eventid": eid, "eventtype": etype},
                                            headers={"X-Requested-With": "XMLHttpRequest"},
                                        )
                                        self._save_file("participation.json", r_part.text)
                                        recorded["participation"] = "participation.json"
                                        break
                        except Exception as e:
                            logger.warning("Could not record participation fixture: %s", e)
            except Exception as e:
                logger.warning("Could not record .ics feed for team %d: %s", tid, e)

        # 6. Save metadata
        meta = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "teams_count": len(teams),
            "fixtures": recorded,
        }
        meta_file = self.output_dir / "metadata.json"
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        logger.info("Recording complete! Saved %d fixtures.", len(recorded))
        return recorded
