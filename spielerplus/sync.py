"""
Sync engine: orchestrates downloading official team .ics feeds,
filtering for upcoming events, querying personal attendance, and upserting directly to ownCloud CalDAV.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from icalendar import Calendar, Event

from spielerplus.caldav_client import CaldavClient
from spielerplus.calendar import (
    augment_event,
    extract_event_info,
    is_absence_event,
    is_event_upcoming,
)
from spielerplus.client import SpielerPlusClient
from spielerplus.config import Config
from spielerplus.rate_limiter import RateLimiter, SpielerPlusError

logger = logging.getLogger(__name__)


class SyncEngine:
    def __init__(
        self,
        config: Config,
        client: Optional[SpielerPlusClient] = None,
        caldav_client: Optional[CaldavClient] = None,
    ):
        self.config = config
        limiter = RateLimiter(
            delay=config.rate_limit_delay,
            jitter=config.rate_limit_jitter,
            max_retries=config.max_retries,
        )
        self.client = client or SpielerPlusClient(
            email=config.email,
            password=config.password,
            base_url=config.base_url,
            rate_limiter=limiter,
        )
        self.caldav_client = caldav_client or CaldavClient(
            url=config.caldav_url,
            username=config.caldav_username,
            password=config.caldav_password,
            calendar_name=config.caldav_calendar,
        )

    def run(self, dry_run: bool = False, specific_team_id: Optional[int] = None) -> Dict[str, int]:
        """
        Execute full sync:
        1. Login to SpielerPlus.
        2. Resolve target teams.
        3. For each team:
           - Fetch official .ics feed.
           - Filter for FUTURE/UPCOMING events only.
           - Skip user absences if show_absences is False.
           - Query personal attendance for those upcoming events.
           - Augment event title and description.
           - Upsert to ownCloud CalDAV calendar (or log in dry-run mode).
        4. Return summary counts: {"created": X, "updated": Y, "unchanged": Z}.
        """
        logger.info("Logging into SpielerPlus at %s...", self.config.base_url)
        self.client.login()

        all_teams = self.client.list_teams()
        team_name_map = {t["id"]: t["name"] for t in all_teams}
        logger.info("Login successful. User: %s", self.client.user_name or "Authenticated")

        target_teams: Dict[int, Optional[str]] = {}
        if specific_team_id is not None:
            target_teams[specific_team_id] = self.config.teams.get(specific_team_id)
        elif self.config.teams:
            target_teams = dict(self.config.teams)
        elif all_teams:
            target_teams = {t["id"]: None for t in all_teams}
        else:
            target_teams = {0: None}

        calendar = None
        if not dry_run:
            calendar = self.caldav_client.get_or_create_calendar()

        stats = {"created": 0, "updated": 0, "unchanged": 0}

        for team_id, shortcode in target_teams.items():
            team_name = team_name_map.get(team_id, f"Team {team_id}")
            logger.info("Processing team '%s' (id=%d, shortcode=%s)...", team_name, team_id, shortcode)

            if team_id > 0:
                try:
                    self.client.switch_team(team_id)
                except SpielerPlusError as exc:
                    logger.warning("Could not switch to team %d: %s. Continuing...", team_id, exc)

            try:
                raw_ics = self.client.fetch_team_ics()
            except Exception as exc:
                logger.warning("Failed to fetch official .ics for team %d: %s", team_id, exc)
                continue

            try:
                team_cal = Calendar.from_ical(raw_ics)
            except Exception as exc:
                logger.warning("Failed to parse .ics for team %d: %s", team_id, exc)
                continue

            team_events = [c for c in team_cal.walk() if c.name == "VEVENT"]

            for ev in team_events:
                # 1. Only process FUTURE/UPCOMING events (past events remain permanently in ownCloud)
                if not is_event_upcoming(ev, days_ahead=self.config.attendance_days):
                    continue

                # 2. Skip user absences if show_absences is False
                if not self.config.show_absences and is_absence_event(ev):
                    logger.debug("Skipping absence event: %s", ev.get("summary"))
                    continue

                # 3. Query personal attendance
                info = extract_event_info(ev)
                user_status = None
                if info:
                    etype, eid = info
                    user_status = self.client.get_event_attendance(etype, eid)

                augment_event(
                    vevent=ev,
                    shortcode=shortcode,
                    user_status=user_status,
                    include_emoji=self.config.attendance_emoji if user_status else False,
                )

                # 4. Upsert to CalDAV
                if dry_run:
                    logger.info("[dry-run] Would sync event: %s (UID: %s)", ev.get("summary"), ev.get("uid"))
                    stats["created"] += 1
                else:
                    action = self.caldav_client.upsert_event(calendar, ev)
                    stats[action] += 1

        logger.info(
            "CalDAV Sync complete: %d created, %d updated, %d unchanged.",
            stats["created"],
            stats["updated"],
            stats["unchanged"],
        )
        return stats
