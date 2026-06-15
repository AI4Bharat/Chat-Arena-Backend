from django.test import TestCase
from unittest.mock import MagicMock

from annotation.permissions import IsAssignedAnnotator, IsAssignedReviewer, IsAssignedSuperChecker
from annotation.tests.factories import UserFactory, ChatSessionFactory, MessageFactory, OCRAnnotationFactory


def _request(user):
    r = MagicMock()
    r.user = user
    return r


class IsAssignedAnnotatorTests(TestCase):
    def setUp(self):
        self.perm = IsAssignedAnnotator()
        self.session = ChatSessionFactory()
        self.message = MessageFactory(session=self.session)
        self.annotation = OCRAnnotationFactory(message=self.message, completed_by=UserFactory())

    def test_assigned_user_allowed(self):
        user = UserFactory()
        self.session.annotation_users.add(user)
        self.assertTrue(self.perm.has_object_permission(_request(user), None, self.annotation))

    def test_unassigned_user_denied(self):
        user = UserFactory()
        self.assertFalse(self.perm.has_object_permission(_request(user), None, self.annotation))


class IsAssignedReviewerTests(TestCase):
    def setUp(self):
        self.perm = IsAssignedReviewer()
        self.reviewer = UserFactory()
        self.session = ChatSessionFactory(review_user=self.reviewer)
        self.message = MessageFactory(session=self.session)
        self.annotation = OCRAnnotationFactory(message=self.message, completed_by=UserFactory())

    def test_reviewer_allowed(self):
        self.assertTrue(self.perm.has_object_permission(_request(self.reviewer), None, self.annotation))

    def test_non_reviewer_denied(self):
        self.assertFalse(self.perm.has_object_permission(_request(UserFactory()), None, self.annotation))


class IsAssignedSuperCheckerTests(TestCase):
    def setUp(self):
        self.perm = IsAssignedSuperChecker()
        self.sc = UserFactory()
        self.session = ChatSessionFactory(super_check_user=self.sc)
        self.message = MessageFactory(session=self.session)
        self.annotation = OCRAnnotationFactory(message=self.message, completed_by=UserFactory())

    def test_superchecker_allowed(self):
        self.assertTrue(self.perm.has_object_permission(_request(self.sc), None, self.annotation))

    def test_other_user_denied(self):
        self.assertFalse(self.perm.has_object_permission(_request(UserFactory()), None, self.annotation))