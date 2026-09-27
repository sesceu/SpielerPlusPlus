"""
Tests for CaldavClient.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from icalendar import Event

from spielerplus.caldav_client import CaldavClient, CaldavError


class TestCaldavClient(unittest.TestCase):
    def setUp(self):
        self.client = CaldavClient(
            url="https://owncloud.example.com/remote.php/dav",
            username="testuser",
            password="testpassword",
            calendar_name="SpielerPlus",
        )

    @patch("caldav.DAVClient")
    def test_get_or_create_calendar_existing(self, mock_dav):
        mock_instance = MagicMock()
        mock_dav.return_value = mock_instance
        mock_principal = MagicMock()
        mock_instance.principal.return_value = mock_principal

        mock_cal1 = MagicMock(name="Other")
        mock_cal1.name = "Personal"
        mock_cal2 = MagicMock(name="Match")
        mock_cal2.name = "SpielerPlus"
        mock_principal.calendars.return_value = [mock_cal1, mock_cal2]

        cal = self.client.get_or_create_calendar()
        self.assertEqual(cal, mock_cal2)
        mock_principal.make_calendar.assert_not_called()

    @patch("caldav.DAVClient")
    def test_get_or_create_calendar_creates_new(self, mock_dav):
        mock_instance = MagicMock()
        mock_dav.return_value = mock_instance
        mock_principal = MagicMock()
        mock_instance.principal.return_value = mock_principal

        mock_cal1 = MagicMock()
        mock_cal1.name = "Work"
        mock_principal.calendars.return_value = [mock_cal1]
        mock_new_cal = MagicMock()
        mock_principal.make_calendar.return_value = mock_new_cal

        cal = self.client.get_or_create_calendar()
        self.assertEqual(cal, mock_new_cal)
        mock_principal.make_calendar.assert_called_once_with(name="SpielerPlus")

    @patch("caldav.DAVClient")
    def test_get_or_create_calendar_failure_raises(self, mock_dav):
        mock_dav.side_effect = RuntimeError("Connection refused")
        with self.assertRaises(CaldavError):
            self.client.get_or_create_calendar()

    @patch("caldav.DAVClient")
    def test_check_connection_success(self, mock_dav):
        mock_instance = MagicMock()
        mock_dav.return_value = mock_instance
        mock_principal = MagicMock()
        mock_instance.principal.return_value = mock_principal

        mock_cal1 = MagicMock()
        mock_cal1.name = "Work"
        mock_cal2 = MagicMock()
        mock_cal2.name = "SpielerPlus"
        mock_principal.calendars.return_value = [mock_cal1, mock_cal2]

        res = self.client.check_connection()
        self.assertEqual(res["calendars"], ["Work", "SpielerPlus"])
        self.assertTrue(res["target_calendar_exists"])

    @patch("caldav.DAVClient")
    def test_check_connection_target_not_exists(self, mock_dav):
        mock_instance = MagicMock()
        mock_dav.return_value = mock_instance
        mock_principal = MagicMock()
        mock_instance.principal.return_value = mock_principal

        mock_cal1 = MagicMock()
        mock_cal1.name = None
        mock_cal1.id = "Other"
        mock_principal.calendars.return_value = [mock_cal1]

        res = self.client.check_connection()
        self.assertEqual(res["calendars"], ["Other"])
        self.assertFalse(res["target_calendar_exists"])

    @patch("caldav.DAVClient")
    def test_check_connection_failure(self, mock_dav):
        mock_dav.side_effect = RuntimeError("Network error")
        with self.assertRaises(CaldavError):
            self.client.check_connection()

    def test_upsert_event_missing_uid_raises(self):
        mock_cal = MagicMock()
        ev = Event()
        with self.assertRaises(CaldavError):
            self.client.upsert_event(mock_cal, ev)

    def test_upsert_event_created(self):
        mock_cal = MagicMock()
        mock_cal.event_by_uid.side_effect = RuntimeError("Not found")

        ev = Event()
        ev.add("uid", "training.101")
        ev.add("summary", "[U15, 👍] Training")

        action = self.client.upsert_event(mock_cal, ev)
        self.assertEqual(action, "created")
        mock_cal.save_event.assert_called_once()

    def test_upsert_event_updated(self):
        mock_cal = MagicMock()
        mock_existing = MagicMock()
        mock_existing.data = "SUMMARY:[U15, ⏳] Training"
        mock_cal.event_by_uid.return_value = mock_existing

        ev = Event()
        ev.add("uid", "training.101")
        ev.add("summary", "[U15, 👍] Training")  # Changed from ⏳ to 👍

        action = self.client.upsert_event(mock_cal, ev)
        self.assertEqual(action, "updated")
        mock_existing.save.assert_called_once()

    def test_upsert_event_unchanged(self):
        mock_cal = MagicMock()
        mock_existing = MagicMock()
        mock_existing.data = "SUMMARY:[U15, 👍] Training"
        mock_cal.event_by_uid.return_value = mock_existing

        ev = Event()
        ev.add("uid", "training.101")
        ev.add("summary", "[U15, 👍] Training")

        action = self.client.upsert_event(mock_cal, ev)
        self.assertEqual(action, "unchanged")
        mock_existing.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
