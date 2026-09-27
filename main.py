#!/usr/bin/env python3
"""
Main entry point for SpielerPlusPlus iCal Proxy.
Can be run locally or within GitHub Actions.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from spielerplus.caldav_client import CaldavClient, CaldavError
from spielerplus.client import SpielerPlusClient
from spielerplus.config import Config
from spielerplus.rate_limiter import AuthenticationError, RateLimiter, SpielerPlusError
from spielerplus.sync import SyncEngine


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(message)s"
    logging.basicConfig(level=level, format=format_str, datefmt="%H:%M:%S")


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SpielerPlusPlus: Synchronize SpielerPlus events directly to an ownCloud / CalDAV calendar."
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to a custom .env file (default: .env if present)",
    )
    parser.add_argument(
        "--test-auth",
        action="store_true",
        help="Test authentication with SpielerPlus and CalDAV server without modifying anything",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the run and log events without writing to CalDAV",
    )
    parser.add_argument(
        "--team",
        type=int,
        default=None,
        help="Sync only this specific team ID (overrides configured teams)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser.parse_args(args)


def run_test_auth(config: Config) -> int:
    """Test authentication against SpielerPlus and CalDAV without modifying data."""
    if not config.email or not config.password:
        logging.error(
            "Missing SpielerPlus credentials! Please set SPIELERPLUS_EMAIL and SPIELERPLUS_PASSWORD."
        )
        return 1

    if not config.caldav_url or not config.caldav_username or not config.caldav_password:
        logging.error(
            "Missing CalDAV credentials! Please set CALDAV_URL, CALDAV_USERNAME, and CALDAV_PASSWORD."
        )
        return 1

    print("=== Testing SpielerPlus Authentication ===")
    try:
        limiter = RateLimiter(delay=0, jitter=0, max_retries=config.max_retries)
        sp_client = SpielerPlusClient(
            email=config.email,
            password=config.password,
            base_url=config.base_url,
            rate_limiter=limiter,
        )
        sp_client.login()
        teams = sp_client.list_teams()

        is_ci = os.environ.get("CI", "").strip().lower() in ("true", "1")
        if is_ci and sp_client.user_name:
            print(f"::add-mask::{sp_client.user_name}")

        user_display = "[redacted in CI]" if is_ci else (sp_client.user_name or "Unknown")
        print(f"  [OK] Successfully logged in to SpielerPlus! User: {user_display}")
        print(f"  [OK] Found {len(teams)} team(s):")
        for t in teams:
            t_name = f"Team {t['id']}" if is_ci else t["name"]
            print(f"       - ID {t['id']}: {t_name}")
    except AuthenticationError as e:
        logging.error("SpielerPlus authentication failed: %s", e)
        return 2
    except SpielerPlusError as e:
        logging.error("SpielerPlus error: %s", e)
        return 2

    print("\n=== Testing CalDAV Connection ===")
    try:
        caldav_client = CaldavClient(
            url=config.caldav_url,
            username=config.caldav_username,
            password=config.caldav_password,
            calendar_name=config.caldav_calendar,
        )
        info = caldav_client.check_connection()
        caldav_url_display = "[redacted in CI]" if is_ci else config.caldav_url
        print(f"  [OK] Successfully connected to CalDAV server at {caldav_url_display}")
        cals = info["calendars"]
        if is_ci:
            print(f"  [OK] Found {len(cals)} accessible calendar(s).")
        else:
            print(f"  [OK] Found {len(cals)} accessible calendar(s): {', '.join(cals) if cals else '(none)'}")

        if info["target_calendar_exists"]:
            print(f"  [OK] Target calendar '{config.caldav_calendar}' exists and is accessible.")
        else:
            print(
                f"  [INFO] Target calendar '{config.caldav_calendar}' does not exist yet "
                "(it will be created automatically on the first sync)."
            )
    except CaldavError as e:
        logging.error("CalDAV connection failed: %s", e)
        return 3

    print("\nAll authentication checks passed successfully! (Read-only mode: no changes were made)")
    return 0


def main(args=None) -> int:
    parsed = parse_args(args)
    setup_logging(verbose=parsed.verbose)

    config = Config.from_env(env_file=parsed.env_file)

    if parsed.test_auth:
        return run_test_auth(config)

    if not config.email or not config.password:
        logging.error(
            "Missing credentials! Please set SPIELERPLUS_EMAIL and SPIELERPLUS_PASSWORD "
            "as environment variables or in a .env file."
        )
        return 1

    if not parsed.dry_run and (not config.caldav_url or not config.caldav_username or not config.caldav_password):
        logging.error(
            "Missing CalDAV credentials! Please set CALDAV_URL, CALDAV_USERNAME, and CALDAV_PASSWORD."
        )
        return 1

    engine = SyncEngine(config=config)

    try:
        stats = engine.run(dry_run=parsed.dry_run, specific_team_id=parsed.team)
        if parsed.dry_run:
            print(f"Dry-run complete: {stats['created']} event(s) would be synchronized.")
        else:
            print(
                f"Sync complete: {stats['created']} created, "
                f"{stats['updated']} updated, {stats['unchanged']} unchanged."
            )
        return 0
    except AuthenticationError as e:
        logging.error("Authentication failed: %s", e)
        return 2
    except SpielerPlusError as e:
        logging.error("SpielerPlus error occurred: %s", e)
        return 3
    except Exception as e:
        logging.exception("Unexpected error during sync: %s", e)
        return 4


if __name__ == "__main__":
    sys.exit(main())
