"""
Rate limiting and retry logic for HTTP requests to SpielerPlus.
Prevents server overload, enforces minimum delays with jitter,
and handles HTTP 429 (Too Many Requests) and 5xx errors with backoff.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Optional

import requests


class SpielerPlusError(Exception):
    """Base exception for all SpielerPlus operations."""
    pass


class RateLimitError(SpielerPlusError):
    """Raised when rate limit is exceeded and maximum retries are exhausted."""
    pass


class AuthenticationError(SpielerPlusError):
    """Raised when authentication fails."""
    pass


class RateLimiter:
    def __init__(
        self,
        delay: float = 1.5,
        jitter: float = 0.5,
        max_retries: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
        time_func: Callable[[], float] = time.time,
        random_func: Callable[[], float] = random.random,
    ):
        self.delay = max(0.0, delay)
        self.jitter = max(0.0, jitter)
        self.max_retries = max(0, max_retries)
        self.sleeper = sleeper
        self.time_func = time_func
        self.random_func = random_func
        self._last_request_time: float = 0.0

    def wait_before_request(self) -> None:
        """Enforce minimum spacing between successive requests."""
        now = self.time_func()
        elapsed = now - self._last_request_time
        target_wait = self.delay + (self.random_func() * self.jitter)
        if elapsed < target_wait and self._last_request_time > 0:
            sleep_duration = target_wait - elapsed
            self.sleeper(sleep_duration)
        self._last_request_time = self.time_func()

    def _parse_retry_after(self, response: requests.Response, default: float) -> float:
        """Parse Retry-After header as seconds or return default."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                val = float(retry_after.strip())
                return max(0.5, val)
            except ValueError:
                pass
        return default

    def request(
        self,
        session: requests.Session,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        """
        Execute an HTTP request with rate limiting and exponential backoff retry.
        """
        attempts = 0
        while True:
            self.wait_before_request()
            try:
                response = session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                attempts += 1
                if attempts > self.max_retries:
                    raise SpielerPlusError(f"HTTP request failed after {attempts} attempts: {exc}") from exc
                backoff = (2 ** (attempts - 1)) * max(1.0, self.delay)
                self.sleeper(backoff)
                continue

            # Handle 429 Too Many Requests
            if response.status_code == 429:
                attempts += 1
                if attempts > self.max_retries:
                    raise RateLimitError(
                        f"HTTP 429 Too Many Requests: max retries ({self.max_retries}) exhausted for {url}"
                    )
                backoff = self._parse_retry_after(response, default=(2 ** (attempts - 1)) * 2.0)
                self.sleeper(backoff)
                continue

            # Handle 5xx Server Errors
            if 500 <= response.status_code <= 599:
                attempts += 1
                if attempts > self.max_retries:
                    return response  # Caller or raise_for_status will handle
                backoff = (2 ** (attempts - 1)) * 1.5
                self.sleeper(backoff)
                continue

            return response
