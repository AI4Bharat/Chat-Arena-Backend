"""
Tests for user account isolation (IDOR hardening).

Verifies that:
- UserSerializer never serializes the sensitive `anonymous_token` preference.
- UserViewSet.get_queryset scopes records to the requesting user only, so
  `GET /users/` and `GET /users/{id}/` cannot enumerate or read other users.
"""
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, SimpleTestCase
from rest_framework.test import APIRequestFactory

from user.models import User
from user.serializers import UserSerializer
from user.views import UserViewSet


class UserSerializerRedactionTests(SimpleTestCase):
    """UserSerializer must strip sensitive preference keys."""

    def test_strips_anonymous_token(self):
        user = User(
            email='a@example.com',
            preferences={'anonymous_token': 'super-secret-tok', 'theme': 'dark'},
        )
        data = UserSerializer(user).data
        self.assertNotIn('anonymous_token', data['preferences'])
        # Non-sensitive preferences are preserved.
        self.assertEqual(data['preferences'].get('theme'), 'dark')

    def test_handles_empty_preferences(self):
        user = User(email='a@example.com', preferences={})
        data = UserSerializer(user).data
        self.assertEqual(data['preferences'], {})

    def test_token_never_leaks_to_string(self):
        user = User(
            email='a@example.com',
            preferences={'anonymous_token': 'super-secret-tok'},
        )
        self.assertNotIn('super-secret-tok', str(UserSerializer(user).data))


class UserViewSetQuerysetScopingTests(TestCase):
    """UserViewSet must only ever surface the requesting user's own record."""

    def setUp(self):
        self.me = User.objects.create(email='me@example.com')
        self.other = User.objects.create(
            email='other@example.com',
            preferences={'anonymous_token': 'victim-token'},
        )

    def _queryset_for(self, user):
        view = UserViewSet()
        request = APIRequestFactory().get('/users/')
        request.user = user
        view.request = request
        return view.get_queryset()

    def test_only_returns_self(self):
        self.assertEqual(list(self._queryset_for(self.me)), [self.me])

    def test_cannot_see_other_user(self):
        self.assertNotIn(self.other, list(self._queryset_for(self.me)))

    def test_unauthenticated_returns_empty(self):
        request = APIRequestFactory().get('/users/')
        request.user = AnonymousUser()
        view = UserViewSet()
        view.request = request
        self.assertEqual(list(view.get_queryset()), [])
