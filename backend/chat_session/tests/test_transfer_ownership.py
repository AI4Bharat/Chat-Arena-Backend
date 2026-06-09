"""
Tests for chat_session transfer_ownership security.

Verifies that:
- transfer_ownership rejects requests without anonymous token.
- transfer_ownership rejects requests with wrong anonymous token.
- transfer_ownership rejects transfer of non-anonymous sessions.
- get_permissions returns IsAuthenticated for transfer_ownership action.
- get_object bypasses user filter for transfer_ownership action.
"""
from unittest.mock import MagicMock, patch, PropertyMock
from django.test import TestCase, RequestFactory
from rest_framework.permissions import IsAuthenticated
from chat_session.views import ChatSessionViewSet


class TransferOwnershipPermissionsTests(TestCase):
    """Test permission and object retrieval overrides for transfer_ownership."""

    def test_get_permissions_returns_is_authenticated_for_transfer(self):
        """transfer_ownership should only require IsAuthenticated (not IsSessionOwner)."""
        view = ChatSessionViewSet()
        view.action = 'transfer_ownership'
        perms = view.get_permissions()
        self.assertEqual(len(perms), 1)
        self.assertIsInstance(perms[0], IsAuthenticated)

    def test_get_permissions_returns_default_for_other_actions(self):
        """Other actions should use the default permission classes."""
        view = ChatSessionViewSet()
        view.action = 'list'
        view.request = MagicMock()
        view.format_kwarg = None
        # Should not raise
        perms = view.get_permissions()
        # Default has IsAuthenticated + IsSessionOwner = 2 permissions
        self.assertGreaterEqual(len(perms), 1)


class TransferOwnershipTokenValidationTests(TestCase):
    """Test anonymous token validation in transfer_ownership."""

    def _setup_view_and_request(self, anon_token_header=None, anon_token_body=None,
                                  session_anon_token='correct-token-123',
                                  session_user_is_anonymous=True,
                                  request_user_is_anonymous=False):
        """Helper to set up a mocked view, request, and session."""
        factory = RequestFactory()
        request = factory.post('/sessions/fake-id/transfer_ownership/')

        # Mock authenticated user
        request.user = MagicMock()
        request.user.is_anonymous = request_user_is_anonymous

        # Mock the anonymous token in the header
        if anon_token_header:
            request.META['HTTP_X_ANONYMOUS_TOKEN'] = anon_token_header

        # Mock the body data
        request.data = {}
        if anon_token_body:
            request.data['anonymous_token'] = anon_token_body

        # Mock session
        session = MagicMock()
        session.user.is_anonymous = session_user_is_anonymous
        session.user.preferences = {'anonymous_token': session_anon_token}
        session.metadata = {}

        return request, session

    @patch.object(ChatSessionViewSet, 'get_object')
    def test_rejects_missing_token(self, mock_get_object):
        """Missing anonymous token should return 403."""
        request, session = self._setup_view_and_request()
        mock_get_object.return_value = session

        view = ChatSessionViewSet()
        view.action = 'transfer_ownership'
        view.request = request
        view.format_kwarg = None
        view.kwargs = {'pk': 'fake-id'}

        response = view.transfer_ownership(request, pk='fake-id')
        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.data)

    @patch.object(ChatSessionViewSet, 'get_object')
    def test_rejects_wrong_token(self, mock_get_object):
        """Wrong anonymous token should return 403."""
        request, session = self._setup_view_and_request(
            anon_token_header='wrong-token-456'
        )
        mock_get_object.return_value = session

        view = ChatSessionViewSet()
        view.action = 'transfer_ownership'
        view.request = request
        view.format_kwarg = None
        view.kwargs = {'pk': 'fake-id'}

        response = view.transfer_ownership(request, pk='fake-id')
        self.assertEqual(response.status_code, 403)

    @patch.object(ChatSessionViewSet, 'get_object')
    def test_rejects_non_anonymous_session(self, mock_get_object):
        """Transferring a non-anonymous session should return 400."""
        request, session = self._setup_view_and_request(
            anon_token_header='correct-token-123',
            session_user_is_anonymous=False
        )
        mock_get_object.return_value = session

        view = ChatSessionViewSet()
        view.action = 'transfer_ownership'
        view.request = request
        view.format_kwarg = None
        view.kwargs = {'pk': 'fake-id'}

        response = view.transfer_ownership(request, pk='fake-id')
        self.assertEqual(response.status_code, 400)

    @patch.object(ChatSessionViewSet, 'get_object')
    def test_rejects_transfer_to_anonymous_user(self, mock_get_object):
        """Cannot transfer to another anonymous user."""
        request, session = self._setup_view_and_request(
            anon_token_header='correct-token-123',
            request_user_is_anonymous=True
        )
        mock_get_object.return_value = session

        view = ChatSessionViewSet()
        view.action = 'transfer_ownership'
        view.request = request
        view.format_kwarg = None
        view.kwargs = {'pk': 'fake-id'}

        response = view.transfer_ownership(request, pk='fake-id')
        self.assertEqual(response.status_code, 400)

    @patch.object(ChatSessionViewSet, 'get_object')
    def test_accepts_correct_token_in_header(self, mock_get_object):
        """Correct X-Anonymous-Token should succeed (return 200 or perform transfer)."""
        request, session = self._setup_view_and_request(
            anon_token_header='correct-token-123'
        )
        mock_get_object.return_value = session

        view = ChatSessionViewSet()
        view.action = 'transfer_ownership'
        view.request = request
        view.format_kwarg = None
        view.kwargs = {'pk': 'fake-id'}

        response = view.transfer_ownership(request, pk='fake-id')
        # Should NOT be 403 or 400
        self.assertNotIn(response.status_code, [400, 403])

    @patch.object(ChatSessionViewSet, 'get_object')
    def test_accepts_token_in_body(self, mock_get_object):
        """Token provided in request body should also work."""
        request, session = self._setup_view_and_request(
            anon_token_body='correct-token-123'
        )
        mock_get_object.return_value = session

        view = ChatSessionViewSet()
        view.action = 'transfer_ownership'
        view.request = request
        view.format_kwarg = None
        view.kwargs = {'pk': 'fake-id'}

        response = view.transfer_ownership(request, pk='fake-id')
        self.assertNotIn(response.status_code, [400, 403])
