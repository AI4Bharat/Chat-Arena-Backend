"""
Tests for the public /status/ endpoint (arena_backend.health.detailed_status).

The endpoint is unauthenticated, so it must not disclose infrastructure
details or — critically — the Redis connection string, which embeds the
Redis password (CACHES['default']['LOCATION'] = redis://:<password>@host).
"""
import json

from django.test import TestCase, RequestFactory

from arena_backend.health import detailed_status


class DetailedStatusDisclosureTests(TestCase):
    def setUp(self):
        self.body = self._fetch_body()

    def _fetch_body(self):
        request = RequestFactory().get('/status/')
        response = detailed_status(request)
        return response.content.decode()

    def test_does_not_leak_cache_location(self):
        self.assertNotIn('location', self.body.lower())

    def test_does_not_leak_redis_connection_string(self):
        self.assertNotIn('redis://', self.body)

    def test_does_not_leak_db_host_name_or_version(self):
        payload = json.loads(self.body)
        db_check = payload.get('checks', {}).get('database', {})
        self.assertNotIn('host', db_check)
        self.assertNotIn('name', db_check)
        self.assertNotIn('version', db_check)

    def test_still_reports_status(self):
        payload = json.loads(self.body)
        self.assertEqual(payload.get('status'), 'operational')
