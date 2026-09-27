"""
Tests for iCalendar Augmenter and Merger.
"""

from __future__ import annotations

import datetime
import unittest
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from spielerplus.calendar import (
    augment_event,
    build_event_summary,
    extract_event_info,
    is_absence_event,
    is_event_upcoming,
)


class TestCalendar(unittest.TestCase):
    def test_build_event_summary(self):
        s1 = build_event_summary("Training", shortcode="U15", status="zugesagt", include_emoji=True)
        self.assertEqual(s1, "[U15, 👍] Training")

        s2 = build_event_summary("Training", shortcode="U15", status="zugesagt", include_emoji=False)
        self.assertEqual(s2, "[U15] Training")

        s3 = build_event_summary("Training", shortcode=None, status="abgesagt", include_emoji=True)
        self.assertEqual(s3, "[👎] Training")

        s4 = build_event_summary("Training", shortcode=None, status=None, include_emoji=True)
        self.assertEqual(s4, "Training")

        self.assertIn("👍", build_event_summary("T", status="zugesagt"))
        self.assertIn("👎", build_event_summary("T", status="abgesagt"))
        self.assertIn("❓", build_event_summary("T", status="unsicher"))
        self.assertIn("⏳", build_event_summary("T", status="offen"))
        self.assertIn("🚫", build_event_summary("T", status="nicht_nominiert"))

    def test_extract_event_info(self):
        ev1 = Event()
        ev1.add("uid", "training.74856637")
        self.assertEqual(extract_event_info(ev1), ("training", 74856637))

        ev2 = Event()
        ev2.add("uid", "game-14557386")
        self.assertEqual(extract_event_info(ev2), ("game", 14557386))

        ev3 = Event()
        ev3.add("url", "https://www.spielerplus.de/event/view?id=2443447")
        self.assertEqual(extract_event_info(ev3), ("event", 2443447))

        ev4 = Event()
        self.assertIsNone(extract_event_info(ev4))
    def test_is_absence_event(self):
        ev1 = Event()
        ev1.add("uid", "absence.8758679.20261001")
        self.assertTrue(is_absence_event(ev1))

        ev2 = Event()
        ev2.add("uid", "absence-12345")
        self.assertTrue(is_absence_event(ev2))

        ev3 = Event()
        ev3.add("summary", "Abwesend")
        self.assertTrue(is_absence_event(ev3))

        ev4 = Event()
        ev4.add("summary", "[U15] Abwesend")
        self.assertTrue(is_absence_event(ev4))

        ev5 = Event()
        ev5.add("summary", "Abwesenheit Urlaub")
        self.assertTrue(is_absence_event(ev5))

        ev_normal = Event()
        ev_normal.add("uid", "training.101")
        ev_normal.add("summary", "Training")
        self.assertFalse(is_absence_event(ev_normal))



    def test_is_event_upcoming(self):
        tz = ZoneInfo("Europe/Berlin")
        now = datetime.datetime.now(tz)

        # Future event
        ev_future = Event()
        ev_future.add("dtstart", now + datetime.timedelta(days=5))
        self.assertTrue(is_event_upcoming(ev_future, reference_time=now))

        # Past event (10 days ago)
        ev_past = Event()
        ev_past.add("dtstart", now - datetime.timedelta(days=10))
        self.assertFalse(is_event_upcoming(ev_past, reference_time=now))

        # Date only (date object)
        ev_date = Event()
        ev_date.add("dtstart", (now + datetime.timedelta(days=2)).date())
        self.assertTrue(is_event_upcoming(ev_date, reference_time=now))

        # Naive event_dt with aware ref
        ev_naive = Event()
        ev_naive.add("dtstart", datetime.datetime(2026, 10, 10, 18, 0))
        self.assertTrue(is_event_upcoming(ev_naive, reference_time=now))

        # Aware event_dt with naive ref
        ref_naive = datetime.datetime(2026, 10, 1, 12, 0)
        self.assertTrue(is_event_upcoming(ev_future, reference_time=ref_naive))

        # Missing dtstart
        ev_none = Event()
        self.assertTrue(is_event_upcoming(ev_none, reference_time=now))

    def test_augment_event(self):
        ev = Event()
        ev.add("summary", "Training")
        ev.add("description", "Notizen")

        augment_event(ev, shortcode="U15", user_status="zugesagt", include_emoji=True)
        self.assertEqual(str(ev["summary"]), "[U15, 👍] Training")
        self.assertIn("👤 Eigener Status: Zugesagt 👍", str(ev["description"]))
        self.assertIn("Notizen", str(ev["description"]))

        # Without prior description
        ev2 = Event()
        ev2.add("summary", "Spiel")
        augment_event(ev2, shortcode="U17", user_status="abgesagt", include_emoji=True)
        self.assertEqual(str(ev2["summary"]), "[U17, 👎] Spiel")
        self.assertEqual(str(ev2["description"]), "👤 Eigener Status: Abgesagt 👎")

        # Past event: no status, no emoji
        ev3 = Event()
        ev3.add("summary", "Altes Spiel")
        augment_event(ev3, shortcode="H1", user_status=None, include_emoji=False)
        self.assertEqual(str(ev3["summary"]), "[H1] Altes Spiel")


if __name__ == "__main__":
    unittest.main()
