"""
Tests for RateLimiter and error handling.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import requests

from spielerplus.rate_limiter import (
    AuthenticationError,
    RateLimitError,
    RateLimiter,
    SpielerPlusError,
)


class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self.current_time = 100.0

        def fake_sleep(duration):
            self.sleeps.append(duration)
            self.current_time += duration

        def fake_time():
            return self.current_time

        def fake_random():
            return 0.5  # Deterministic jitter: 0.5 * jitter

        self.fake_sleep = fake_sleep
        self.fake_time = fake_time
        self.fake_random = fake_random

    def test_wait_before_request_throttling(self):
        limiter = RateLimiter(
            delay=1.0,
            jitter=0.4,
            sleeper=self.fake_sleep,
            time_func=self.fake_time,
            random_func=self.fake_random,
        )

        # First request: no sleep needed
        limiter.wait_before_request()
        self.assertEqual(len(self.sleeps), 0)

        # Immediate next request: should sleep for delay + jitter
        limiter.wait_before_request()
        self.assertEqual(len(self.sleeps), 1)
        self.assertAlmostEqual(self.sleeps[0], 1.2)

    def test_successful_request_first_try(self):
        limiter = RateLimiter(
            delay=1.0,
            jitter=0.0,
            sleeper=self.fake_sleep,
            time_func=self.fake_time,
            random_func=self.fake_random,
        )
        session = MagicMock()
        mock_response = MagicMock(status_code=200)
        session.request.return_value = mock_response

        res = limiter.request(session, "GET", "http://example.com/test")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(session.request.call_count, 1)

    def test_rate_limit_429_retry_with_header(self):
        limiter = RateLimiter(
            delay=1.0,
            jitter=0.0,
            max_retries=2,
            sleeper=self.fake_sleep,
            time_func=self.fake_time,
            random_func=self.fake_random,
        )
        session = MagicMock()
        r_429 = MagicMock(status_code=429, headers={"Retry-After": "2.5"})
        r_200 = MagicMock(status_code=200, headers={})
        session.request.side_effect = [r_429, r_200]

        res = limiter.request(session, "GET", "http://example.com/test")
        self.assertEqual(res.status_code, 200)
        self.assertIn(2.5, self.sleeps)

    def test_rate_limit_429_exhausted_raises(self):
        limiter = RateLimiter(
            delay=1.0,
            jitter=0.0,
            max_retries=1,
            sleeper=self.fake_sleep,
            time_func=self.fake_time,
            random_func=self.fake_random,
        )
        session = MagicMock()
        r_429 = MagicMock(status_code=429, headers={"Retry-After": "invalid"})
        session.request.return_value = r_429

        with self.assertRaises(RateLimitError):
            limiter.request(session, "GET", "http://example.com/test")

    def test_server_error_500_retries(self):
        limiter = RateLimiter(
            delay=1.0,
            jitter=0.0,
            max_retries=2,
            sleeper=self.fake_sleep,
            time_func=self.fake_time,
            random_func=self.fake_random,
        )
        session = MagicMock()
        r_500 = MagicMock(status_code=500)
        r_200 = MagicMock(status_code=200)
        session.request.side_effect = [r_500, r_200]

        res = limiter.request(session, "GET", "http://example.com/test")
        self.assertEqual(res.status_code, 200)

    def test_server_error_500_exhausted_returns_response(self):
        limiter = RateLimiter(
            delay=1.0,
            jitter=0.0,
            max_retries=1,
            sleeper=self.fake_sleep,
            time_func=self.fake_time,
            random_func=self.fake_random,
        )
        session = MagicMock()
        r_503 = MagicMock(status_code=503)
        session.request.return_value = r_503

        res = limiter.request(session, "GET", "http://example.com/test")
        self.assertEqual(res.status_code, 503)

    def test_request_exception_retries_and_raises(self):
        limiter = RateLimiter(
            delay=1.0,
            jitter=0.0,
            max_retries=1,
            sleeper=self.fake_sleep,
            time_func=self.fake_time,
            random_func=self.fake_random,
        )
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError("Connection failed")

        with self.assertRaises(SpielerPlusError):
            limiter.request(session, "GET", "http://example.com/test")


if __name__ == "__main__":
    unittest.main()
