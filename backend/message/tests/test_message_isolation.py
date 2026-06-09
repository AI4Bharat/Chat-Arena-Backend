"""
Tests for message access isolation (IDOR hardening).

Verifies that MessageViewSet.get_queryset is scoped to the requesting user's
own sessions, so `GET /messages/?session_id=<other user's session>` cannot
return another user's conversation.
"""
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from message.views import MessageViewSet
from user.models import User


class MessageQuerysetScopingTests(TestCase):
    def setUp(self):
        self.me = User.objects.create(email='me@example.com')

    def _view_with_user(self, user):
        view = MessageViewSet()
        drf_request = Request(APIRequestFactory().get('/messages/'))
        drf_request.user = user
        view.request = drf_request
        return view

    def test_unauthenticated_returns_empty(self):
        view = self._view_with_user(AnonymousUser())
        self.assertEqual(list(view.get_queryset()), [])

    def test_queryset_is_scoped_to_requesting_user(self):
        view = self._view_with_user(self.me)
        sql = str(view.get_queryset().query)
        # The WHERE clause must constrain on the session's owning user...
        self.assertIn('session', sql.lower())
        # ...bound to *this* user's id (uuid rendered into the query params).
        self.assertIn(self.me.id.hex, sql.replace('-', ''))
