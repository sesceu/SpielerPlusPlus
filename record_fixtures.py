#!/usr/bin/env python3
"""
CLI tool to record real HTTP responses from SpielerPlus.
Saves sanitized responses as fixtures in tests/fixtures/.
Run this tool whenever the upstream SpielerPlus pages change.

Usage:
    python3 record_fixtures.py [--env-file .env] [--output-dir tests/fixtures]
"""

from __future__ import annotations

import argparse
import logging
import sys

from spielerplus.client import SpielerPlusClient
from spielerplus.config import Config
from spielerplus.recorder import FixtureRecorder


def main(args=None) -> int:
    parser = argparse.ArgumentParser(
        description="Record live SpielerPlus HTML responses and save as fixtures for the mock server."
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to .env file containing credentials (default: .env)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="tests/fixtures",
        help="Target folder for fixtures (default: tests/fixtures)",
    )
    parser.add_argument(
        "--no-sanitize",
        action="store_true",
        help="Do not anonymize email or personal details",
    )
    parser.add_argument(
        "--max-teams",
        type=int,
        default=3,
        help="Max teams to record (default: 3)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parsed = parser.parse_args(args)

    level = logging.DEBUG if parsed.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")

    config = Config.from_env(env_file=parsed.env_file)
    if not config.email or not config.password:
        logging.error(
            "Missing credentials! Please set SPIELERPLUS_EMAIL and SPIELERPLUS_PASSWORD "
            "in your environment or in .env."
        )
        return 1

    from spielerplus.rate_limiter import RateLimiter
    limiter = RateLimiter(
        delay=config.rate_limit_delay,
        jitter=config.rate_limit_jitter,
        max_retries=config.max_retries,
    )

    client = SpielerPlusClient(
        email=config.email,
        password=config.password,
        base_url=config.base_url,
        rate_limiter=limiter,
    )

    recorder = FixtureRecorder(
        client=client,
        output_dir=parsed.output_dir,
        sanitize=not parsed.no_sanitize,
    )

    try:
        recorded = recorder.record_all(max_teams=parsed.max_teams)
        print(f"\nSuccessfully recorded {len(recorded)} fixtures to: {parsed.output_dir}")
        for key, fname in recorded.items():
            print(f"  - {key}: {fname}")
        return 0
    except Exception as exc:
        logging.exception("Failed to record fixtures: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
