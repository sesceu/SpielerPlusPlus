"""
Configuration management for SpielerPlusPlus.
Loads settings from environment variables and optional .env files.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


def parse_bool(value: Optional[str], default: bool = True) -> bool:
    """Parse a boolean value from a string."""
    if value is None:
        return default
    val = value.strip().lower()
    if val in ("1", "true", "yes", "on", "y"):
        return True
    if val in ("0", "false", "no", "off", "n"):
        return False
    return default


def parse_teams_config(raw_value: Optional[str]) -> Dict[int, Optional[str]]:
    """
    Parse team configuration into a mapping of team_id (int) -> shortcode (str | None).
    
    Supported formats:
      - Comma-separated pairs: "12345:U15, 67890:U17"
      - JSON object: '{"12345": "U15", "67890": "U17"}' or '{"12345": null}'
      - Comma-separated IDs: "12345, 67890"
      - Single ID: "12345"
      - None / empty string: {} (signals auto-detecting all account teams)
    """
    if not raw_value or not raw_value.strip():
        return {}

    raw = raw_value.strip()

    # Try JSON format first
    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                result: Dict[int, Optional[str]] = {}
                for k, v in data.items():
                    team_id = int(str(k).strip())
                    shortcode = str(v).strip() if v is not None else None
                    result[team_id] = shortcode
                return result
        except (ValueError, TypeError):
            pass

    # Try comma-separated format
    result = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            team_id_str, shortcode = part.split(":", 1)
            try:
                team_id = int(team_id_str.strip())
            except ValueError:
                continue
            sc = shortcode.strip()
            result[team_id] = sc if sc else None
        else:
            try:
                team_id = int(part.strip())
            except ValueError:
                continue
            result[team_id] = None
    return result


def load_env_file(filepath: Path | str) -> None:
    """Load environment variables from a .env file if it exists."""
    p = Path(filepath)
    if not p.is_file():
        return

    content = p.read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("\"'")
        if key not in os.environ:
            os.environ[key] = val


@dataclass
class Config:
    email: str = ""
    password: str = ""
    timezone: str = "Europe/Berlin"
    teams: Dict[int, Optional[str]] = field(default_factory=dict)
    attendance_emoji: bool = True
    attendance_days: int = 90
    show_absences: bool = False
    rate_limit_delay: float = 1.5
    rate_limit_jitter: float = 0.5
    max_retries: int = 3
    base_url: str = "https://www.spielerplus.de"
    caldav_url: str = ""
    caldav_username: str = ""
    caldav_password: str = ""
    caldav_calendar: str = "SpielerPlus"

    @classmethod
    def from_env(cls, env_file: Optional[Path | str] = None) -> Config:
        """Create Config from environment variables, optionally loading a .env file."""
        if env_file:
            load_env_file(env_file)
        elif Path(".env").is_file():
            load_env_file(".env")

        email = os.environ.get("SPIELERPLUS_EMAIL", "").strip()
        password = os.environ.get("SPIELERPLUS_PASSWORD", "").strip()
        timezone = os.environ.get("SPIELERPLUS_TIMEZONE", "Europe/Berlin").strip() or "Europe/Berlin"

        raw_teams = os.environ.get("SPIELERPLUS_TEAMS", "").strip()
        teams = parse_teams_config(raw_teams)
        if not teams:
            legacy_team_id = os.environ.get("SPIELERPLUS_TEAM_ID", "").strip()
            if legacy_team_id:
                try:
                    tid = int(legacy_team_id)
                    legacy_sc = os.environ.get("SPIELERPLUS_SHORTCODE") or os.environ.get("SPIELERPLUS_TEAM_SHORTCODE")
                    teams[tid] = legacy_sc.strip() if legacy_sc else None
                except ValueError:
                    pass

        attendance_emoji = parse_bool(os.environ.get("SPIELERPLUS_ATTENDANCE_EMOJI"), default=True)
        show_absences = parse_bool(os.environ.get("SPIELERPLUS_SHOW_ABSENCES"), default=False)

        try:
            attendance_days = int(os.environ.get("SPIELERPLUS_ATTENDANCE_DAYS", "90"))
        except ValueError:
            attendance_days = 90

        try:
            rate_limit_delay = float(os.environ.get("SPIELERPLUS_RATE_LIMIT_DELAY", "1.5"))
        except ValueError:
            rate_limit_delay = 1.5

        try:
            rate_limit_jitter = float(os.environ.get("SPIELERPLUS_RATE_LIMIT_JITTER", "0.5"))
        except ValueError:
            rate_limit_jitter = 0.5

        try:
            max_retries = int(os.environ.get("SPIELERPLUS_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3

        base_url = os.environ.get("SPIELERPLUS_BASE_URL", "https://www.spielerplus.de").strip().rstrip("/")
        caldav_url = os.environ.get("CALDAV_URL", "").strip()
        caldav_username = os.environ.get("CALDAV_USERNAME", "").strip()
        caldav_password = os.environ.get("CALDAV_PASSWORD", "").strip()
        caldav_calendar = os.environ.get("CALDAV_CALENDAR", "SpielerPlus").strip() or "SpielerPlus"

        return cls(
            email=email,
            password=password,
            timezone=timezone,
            teams=teams,
            attendance_emoji=attendance_emoji,
            attendance_days=attendance_days,
            show_absences=show_absences,
            rate_limit_delay=rate_limit_delay,
            rate_limit_jitter=rate_limit_jitter,
            max_retries=max_retries,
            base_url=base_url,
            caldav_url=caldav_url,
            caldav_username=caldav_username,
            caldav_password=caldav_password,
            caldav_calendar=caldav_calendar,
        )

        key = key.strip()
        val = val.strip().strip("\"'")
        if key not in os.environ:
            os.environ[key] = val
