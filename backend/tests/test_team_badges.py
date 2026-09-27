import unittest
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import requests

from team_badges import BadgeResult, _download, badge_proxy_path, clear_badge_cache, provider_badge_id, resolve_badge


class TeamBadgeTests(unittest.TestCase):
    def setUp(self):
        clear_badge_cache()
        self.now = datetime(2026, 9, 27, tzinfo=timezone.utc)

    def tearDown(self):
        clear_badge_cache()

    def test_canonical_provider_binding_fails_closed_for_ambiguous_sentinel(self):
        self.assertEqual(provider_badge_id(42), 42)
        self.assertEqual(badge_proxy_path(42), "/teams/42/badge")
        self.assertIsNone(provider_badge_id(-1))
        self.assertIsNone(badge_proxy_path(-1))
        self.assertIsNone(badge_proxy_path(None))

    def test_valid_badge_is_cached_without_a_second_upstream_call(self):
        calls = []

        def download(provider_team_id):
            calls.append(provider_team_id)
            return BadgeResult(b"png", "image/png", "digest")

        first = resolve_badge(42, now=self.now, downloader=download)
        second = resolve_badge(42, now=self.now + timedelta(hours=1), downloader=download)
        self.assertEqual(first, second)
        self.assertEqual(calls, [42])

    def test_missing_or_placeholder_badge_is_negatively_cached(self):
        calls = []

        def download(provider_team_id):
            calls.append(provider_team_id)
            return None

        self.assertIsNone(resolve_badge(42, now=self.now, downloader=download))
        self.assertIsNone(resolve_badge(42, now=self.now + timedelta(hours=1), downloader=download))
        self.assertEqual(calls, [42])

    def test_upstream_failure_uses_stale_valid_badge(self):
        valid = BadgeResult(b"png", "image/png", "digest")
        resolve_badge(42, now=self.now, downloader=lambda _team_id: valid)

        def fail(_provider_team_id):
            raise requests.ConnectionError("offline")

        stale = resolve_badge(42, now=self.now + timedelta(days=3), downloader=fail)
        self.assertIsNotNone(stale)
        self.assertTrue(stale.stale)
        self.assertEqual(stale.content, b"png")

    def test_upstream_failure_without_cache_collapses_to_missing(self):
        def fail(_provider_team_id):
            raise requests.Timeout("slow")

        self.assertIsNone(resolve_badge(42, now=self.now, downloader=fail))

    def test_known_provider_placeholder_hash_is_rejected(self):
        content = b"provider-default-placeholder"
        response = SimpleNamespace(
            content=content,
            headers={"content-type": "image/png"},
            raise_for_status=lambda: None,
        )
        with patch("team_badges.requests.get", return_value=response), patch(
            "team_badges.PLACEHOLDER_SHA256", frozenset({hashlib.sha256(content).hexdigest()})
        ):
            self.assertIsNone(_download(42))

    def test_valid_transparent_png_bytes_are_not_transformed(self):
        content = b"\x89PNG\r\n\x1a\ntransparent-payload"
        response = SimpleNamespace(
            content=content,
            headers={"content-type": "image/png"},
            raise_for_status=lambda: None,
        )
        with patch("team_badges.requests.get", return_value=response):
            result = _download(42)
        self.assertEqual(result.content, content)
        self.assertEqual(result.media_type, "image/png")


if __name__ == "__main__":
    unittest.main()
