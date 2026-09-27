"""
Tests for Config and environment variable loading.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from spielerplus.config import Config, load_env_file, parse_bool, parse_teams_config


class TestConfig(unittest.TestCase):
    def test_parse_bool(self):
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("YES"))
        self.assertTrue(parse_bool("on"))
        self.assertTrue(parse_bool("y"))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("NO"))
        self.assertFalse(parse_bool("off"))
        self.assertFalse(parse_bool("n"))
        self.assertTrue(parse_bool(None, default=True))
        self.assertFalse(parse_bool(None, default=False))
        self.assertTrue(parse_bool("unknown", default=True))
        self.assertFalse(parse_bool("unknown", default=False))

    def test_parse_teams_config(self):
        self.assertEqual(parse_teams_config(None), {})
        self.assertEqual(parse_teams_config(""), {})
        self.assertEqual(parse_teams_config("   "), {})

        # Comma-separated with shortcodes
        res = parse_teams_config("12345:U15, 67890:U17")
        self.assertEqual(res, {12345: "U15", 67890: "U17"})

        # Comma-separated without shortcodes
        res = parse_teams_config("12345, 67890,")
        self.assertEqual(res, {12345: None, 67890: None})

        # Single ID
        self.assertEqual(parse_teams_config("42"), {42: None})

        # JSON format
        json_str = '{"100": "Team A", "200": null}'
        self.assertEqual(parse_teams_config(json_str), {100: "Team A", 200: None})

        # Malformed JSON falls back
        self.assertEqual(parse_teams_config('{"invalid_json": "test"'), {})

        # JSON with non-integer keys
        self.assertEqual(parse_teams_config('{"not_an_int": "test"}'), {})

        # Comma-separated with invalid integer
        self.assertEqual(parse_teams_config("invalid_team_id"), {})

    def test_load_env_file(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as f:
            f.write("# Comment\n")
            f.write("TEST_KEY_1=value1\n")
            f.write("TEST_KEY_2='quoted_value'\n")
            f.write("TEST_KEY_3=\"double_quoted\"\n")
            f.write("INVALID_LINE\n")
            f_path = Path(f.name)
        f.close()

        try:
            os.environ["TEST_KEY_1"] = "already_set"
            load_env_file(f_path)
            self.assertEqual(os.environ.get("TEST_KEY_1"), "already_set")
            self.assertEqual(os.environ.get("TEST_KEY_2"), "quoted_value")
            self.assertEqual(os.environ.get("TEST_KEY_3"), "double_quoted")

            load_env_file(Path("non_existent_file_path.env"))
        finally:
            if f_path.is_file():
                f_path.unlink()
            os.environ.pop("TEST_KEY_1", None)
            os.environ.pop("TEST_KEY_2", None)
            os.environ.pop("TEST_KEY_3", None)

    def test_config_from_env_defaults(self):
        for k in list(os.environ.keys()):
            if k.startswith("SPIELERPLUS_"):
                del os.environ[k]

        cfg = Config.from_env(env_file="non_existent.env")
        self.assertEqual(cfg.email, "")
        self.assertEqual(cfg.password, "")
        self.assertEqual(cfg.timezone, "Europe/Berlin")
        self.assertEqual(cfg.teams, {})
        self.assertTrue(cfg.attendance_emoji)
        self.assertEqual(cfg.attendance_days, 90)
        self.assertFalse(cfg.show_absences)
        self.assertEqual(cfg.rate_limit_delay, 1.5)
        self.assertEqual(cfg.rate_limit_jitter, 0.5)
        self.assertEqual(cfg.max_retries, 3)
        self.assertEqual(cfg.base_url, "https://www.spielerplus.de")
        self.assertEqual(cfg.caldav_url, "")
        self.assertEqual(cfg.caldav_username, "")
        self.assertEqual(cfg.caldav_password, "")
        self.assertEqual(cfg.caldav_calendar, "SpielerPlus")

    def test_config_from_env_custom(self):
        os.environ["SPIELERPLUS_EMAIL"] = "test@example.com"
        os.environ["SPIELERPLUS_PASSWORD"] = "secret123"
        os.environ["SPIELERPLUS_TIMEZONE"] = "Europe/Vienna"
        os.environ["SPIELERPLUS_TEAMS"] = "111:T1, 222:T2"
        os.environ["SPIELERPLUS_ATTENDANCE_EMOJI"] = "false"
        os.environ["SPIELERPLUS_ATTENDANCE_DAYS"] = "60"
        os.environ["SPIELERPLUS_SHOW_ABSENCES"] = "true"
        os.environ["SPIELERPLUS_RATE_LIMIT_DELAY"] = "2.0"
        os.environ["SPIELERPLUS_RATE_LIMIT_JITTER"] = "0.8"
        os.environ["SPIELERPLUS_MAX_RETRIES"] = "5"
        os.environ["SPIELERPLUS_BASE_URL"] = "http://localhost:8080/"
        os.environ["CALDAV_URL"] = "https://owncloud.example.com/dav"
        os.environ["CALDAV_USERNAME"] = "user1"
        os.environ["CALDAV_PASSWORD"] = "pass1"
        os.environ["CALDAV_CALENDAR"] = "Sports"

        try:
            cfg = Config.from_env()
            self.assertEqual(cfg.email, "test@example.com")
            self.assertEqual(cfg.password, "secret123")
            self.assertEqual(cfg.timezone, "Europe/Vienna")
            self.assertEqual(cfg.teams, {111: "T1", 222: "T2"})
            self.assertFalse(cfg.attendance_emoji)
            self.assertEqual(cfg.attendance_days, 60)
            self.assertTrue(cfg.show_absences)
            self.assertEqual(cfg.rate_limit_delay, 2.0)
            self.assertEqual(cfg.rate_limit_jitter, 0.8)
            self.assertEqual(cfg.max_retries, 5)
            self.assertEqual(cfg.base_url, "http://localhost:8080")
            self.assertEqual(cfg.caldav_url, "https://owncloud.example.com/dav")
            self.assertEqual(cfg.caldav_username, "user1")
            self.assertEqual(cfg.caldav_password, "pass1")
            self.assertEqual(cfg.caldav_calendar, "Sports")
        finally:
            for k in list(os.environ.keys()):
                if k.startswith("SPIELERPLUS_") or k.startswith("CALDAV_"):
                    del os.environ[k]

    def test_config_legacy_team_id(self):
        for k in list(os.environ.keys()):
            if k.startswith("SPIELERPLUS_"):
                del os.environ[k]

        os.environ["SPIELERPLUS_TEAM_ID"] = "9999"
        os.environ["SPIELERPLUS_SHORTCODE"] = "LEGACY"
        try:
            cfg = Config.from_env(env_file="non_existent.env")
            self.assertEqual(cfg.teams, {9999: "LEGACY"})
        finally:
            os.environ.pop("SPIELERPLUS_TEAM_ID", None)
            os.environ.pop("SPIELERPLUS_SHORTCODE", None)

        # Invalid legacy team ID should be ignored
        os.environ["SPIELERPLUS_TEAM_ID"] = "not_an_int"
        try:
            cfg2 = Config.from_env(env_file="non_existent.env")
            self.assertEqual(cfg2.teams, {})
        finally:
            os.environ.pop("SPIELERPLUS_TEAM_ID", None)

    def test_config_invalid_numbers_fallback(self):
        os.environ["SPIELERPLUS_RATE_LIMIT_DELAY"] = "not_a_number"
        os.environ["SPIELERPLUS_RATE_LIMIT_JITTER"] = "not_a_number"
        os.environ["SPIELERPLUS_MAX_RETRIES"] = "not_a_number"
        os.environ["SPIELERPLUS_ATTENDANCE_DAYS"] = "not_a_number"
        try:
            cfg = Config.from_env(env_file="non_existent.env")
            self.assertEqual(cfg.rate_limit_delay, 1.5)
            self.assertEqual(cfg.rate_limit_jitter, 0.5)
            self.assertEqual(cfg.max_retries, 3)
            self.assertEqual(cfg.attendance_days, 90)
        finally:
            os.environ.pop("SPIELERPLUS_RATE_LIMIT_DELAY", None)
            os.environ.pop("SPIELERPLUS_RATE_LIMIT_JITTER", None)
            os.environ.pop("SPIELERPLUS_MAX_RETRIES", None)
            os.environ.pop("SPIELERPLUS_ATTENDANCE_DAYS", None)


if __name__ == "__main__":
    unittest.main()
