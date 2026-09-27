"""
CalDAV Client for ownCloud / Nextcloud / standard CalDAV servers.
Handles calendar discovery, creation, and event upserts by UID.
"""

from __future__ import annotations

import logging
from typing import Optional

import caldav
from icalendar import Calendar, Event

from spielerplus.rate_limiter import SpielerPlusError

logger = logging.getLogger(__name__)


class CaldavError(SpielerPlusError):
    """Raised when CalDAV operations fail."""
    pass


class CaldavClient:
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        calendar_name: str = "SpielerPlus",
    ):
        self.url = url
        self.username = username
        self.password = password
        self.calendar_name = calendar_name
        self._dav_client: Optional[caldav.DAVClient] = None

    def _get_client(self) -> caldav.DAVClient:
        if self._dav_client is None:
            self._dav_client = caldav.DAVClient(
                url=self.url,
                username=self.username,
                password=self.password,
            )
        return self._dav_client

    def check_connection(self) -> dict:
        """
        Test CalDAV connection without modifying anything.
        Returns a dict with calendar names and whether target calendar exists.
        """
        try:
            client = self._get_client()
            principal = client.principal()
            calendars = principal.calendars()

            cal_names = []
            for c in calendars:
                name = getattr(c, "name", None) or getattr(c, "id", None) or "Unnamed"
                cal_names.append(str(name))

            target_exists = any(name.lower() == self.calendar_name.lower() for name in cal_names)
            return {
                "calendars": cal_names,
                "target_calendar_exists": target_exists,
            }
        except Exception as exc:
            raise CaldavError(f"Failed to connect to CalDAV server: {exc}") from exc

    def get_or_create_calendar(self) -> caldav.Calendar:
        """Connect to CalDAV server, find or create the target calendar."""
        try:
            client = self._get_client()
            principal = client.principal()
            calendars = principal.calendars()

            for c in calendars:
                name = getattr(c, "name", None) or getattr(c, "id", None)
                if name and name.lower() == self.calendar_name.lower():
                    logger.info("Found existing CalDAV calendar '%s'", name)
                    return c

            logger.info("Calendar '%s' not found. Creating it...", self.calendar_name)
            return principal.make_calendar(name=self.calendar_name)
        except Exception as exc:
            raise CaldavError(f"Failed to access or create CalDAV calendar '{self.calendar_name}': {exc}") from exc

    def upsert_event(self, calendar: caldav.Calendar, vevent: Event) -> str:
        """
        Upsert event to CalDAV calendar by UID.
        Returns 'created', 'updated', or 'unchanged'.
        """
        uid = str(vevent.get("uid", "")).strip()
        if not uid:
            raise CaldavError("Cannot upload event to CalDAV without UID.")

        vcal = Calendar()
        vcal.add("prodid", "-//SpielerPlusPlus//DE")
        vcal.add("version", "2.0")
        vcal.add_component(vevent)
        vevent_str = vcal.to_ical().decode("utf-8")

        new_summary = str(vevent.get("summary", "")).strip()

        try:
            existing = calendar.event_by_uid(uid)
        except Exception:
            existing = None

        if existing:
            existing_data = existing.data if hasattr(existing, "data") else ""
            # Check if summary changed
            if new_summary and new_summary in existing_data:
                logger.debug("Event %s is unchanged.", uid)
                return "unchanged"

            existing.data = vevent_str
            existing.save()
            logger.debug("Event %s updated.", uid)
            return "updated"

        calendar.save_event(vevent_str)
        logger.debug("Event %s created.", uid)
        return "created"
