"""
Tests for SyncEngine pushing to CalDAV.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from spielerplus.caldav_client import CaldavClient
from spielerplus.client import SpielerPlusClient
from spielerplus.config import Config
from spielerplus.rate_limiter import RateLimiter, SpielerPlusError
from spielerplus.sync import SyncEngine
from tests.mock_server import MockSpielerPlusServer


class TestSyncEngine(unittest.TestCase):
    server: MockSpielerPlusServer

    @classmethod
    def setUpClass(cls):
        cls.server = MockSpielerPlusServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.limiter = RateLimiter(delay=0.0, jitter=0.0, max_retries=1, sleeper=lambda d: None)
        self.mock_caldav = MagicMock(spec=CaldavClient)
        self.mock_cal = MagicMock()
        self.mock_caldav.get_or_create_calendar.return_value = self.mock_cal
        self.mock_caldav.upsert_event.return_value = "created"

    def test_sync_multiple_teams_dry_run(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={12345: "H1", 67890: "H2"},
            attendance_emoji=True,
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=True)
        self.assertGreater(stats["created"], 0)
        self.mock_caldav.get_or_create_calendar.assert_not_called()

    def test_sync_real_upserts(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={12345: "H1"},
            attendance_emoji=True,
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=False)
        self.mock_caldav.get_or_create_calendar.assert_called_once()
        self.assertGreater(stats["created"], 0)

    def test_sync_hide_absences_by_default(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={12345: "H1"},
            show_absences=False,
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        upserted_uids = []
        self.mock_caldav.upsert_event.side_effect = lambda c, ev: (upserted_uids.append(str(ev.get("uid"))), "created")[1]

        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)
        engine.run(dry_run=False)

        self.assertFalse(any("absence" in uid for uid in upserted_uids))

    def test_sync_show_absences_when_configured(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={12345: "H1"},
            show_absences=True,
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        upserted_uids = []
        self.mock_caldav.upsert_event.side_effect = lambda c, ev: (upserted_uids.append(str(ev.get("uid"))), "created")[1]

        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)
        engine.run(dry_run=False)

        self.assertTrue(any("absence" in uid for uid in upserted_uids))

    def test_sync_auto_discover_teams(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={},
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=True)
        self.assertGreater(stats["created"], 0)

    def test_sync_specific_team_id(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={12345: "H1", 67890: "H2"},
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=True, specific_team_id=67890)
        self.assertGreater(stats["created"], 0)

    def test_sync_no_teams_discovered_fallback(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={},
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        client.list_teams = lambda: []
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=True)
        self.assertGreater(stats["created"], 0)

    def test_sync_switch_team_failure_graceful(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={99999: "BAD"},
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        client.switch_team = lambda tid: (_ for _ in ()).throw(SpielerPlusError("Switch err"))
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=True)
        self.assertGreater(stats["created"], 0)

    def test_sync_fetch_ics_failure_graceful(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={12345: "H1"},
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        client.fetch_team_ics = lambda: (_ for _ in ()).throw(RuntimeError("Fetch err"))
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=True)
        self.assertEqual(stats["created"], 0)

    def test_sync_parse_ics_failure_graceful(self):
        cfg = Config(
            email="test@example.com",
            password="correctpassword",
            base_url=self.server.url,
            teams={12345: "H1"},
        )
        client = SpielerPlusClient(
            email=cfg.email, password=cfg.password, base_url=cfg.base_url, rate_limiter=self.limiter
        )
        client.fetch_team_ics = lambda: "INVALID ICS DATA"
        engine = SyncEngine(config=cfg, client=client, caldav_client=self.mock_caldav)

        stats = engine.run(dry_run=True)
        self.assertEqual(stats["created"], 0)


if __name__ == "__main__":
    unittest.main()

