from django.test import TestCase, RequestFactory
from unittest.mock import MagicMock

from annotation.serializers import OCRAnnotationCreateSerializer, OCRAnnotationReviewSerializer
from annotation.constants import ANNOTATOR_ANNOTATION, LABELED, DRAFT
from annotation.tests.factories import UserFactory, ChatSessionFactory, MessageFactory, OCRAnnotationFactory


VALID_RESULT = [{"id": "r1", "box": [0, 0, 100, 50], "text": "Hello", "type": "text", "page": 1}]


def _request(user):
    r = MagicMock()
    r.user = user
    return r


class OCRAnnotationCreateSerializerTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.session = ChatSessionFactory(session_type="OCR")
        self.message = MessageFactory(session=self.session)

    def _serialize(self, data):
        return OCRAnnotationCreateSerializer(data=data, context={"request": _request(self.user)})

    def test_valid_payload(self):
        s = self._serialize({"message_id": str(self.message.id), "result": VALID_RESULT, "annotation_status": "labeled"})
        self.assertTrue(s.is_valid(), s.errors)

    def test_malformed_box(self):
        result = [{"id": "r1", "box": [0, 0], "text": "Hi", "type": "text", "page": 1}]
        s = self._serialize({"message_id": str(self.message.id), "result": result, "annotation_status": "labeled"})
        self.assertFalse(s.is_valid())

    def test_missing_text(self):
        result = [{"id": "r1", "box": [0, 0, 100, 50], "type": "text", "page": 1}]
        s = self._serialize({"message_id": str(self.message.id), "result": result, "annotation_status": "labeled"})
        self.assertFalse(s.is_valid())

    def test_missing_page(self):
        result = [{"id": "r1", "box": [0, 0, 100, 50], "text": "Hi", "type": "text"}]
        s = self._serialize({"message_id": str(self.message.id), "result": result, "annotation_status": "labeled"})
        self.assertFalse(s.is_valid())

    def test_invalid_annotation_status(self):
        s = self._serialize({"message_id": str(self.message.id), "result": VALID_RESULT, "annotation_status": "accepted"})
        self.assertFalse(s.is_valid())

    def test_non_ocr_session_rejected(self):
        llm_session = ChatSessionFactory(session_type="LLM")
        msg = MessageFactory(session=llm_session)
        s = self._serialize({"message_id": str(msg.id), "result": VALID_RESULT, "annotation_status": "labeled"})
        self.assertFalse(s.is_valid())


class OCRAnnotationReviewSerializerTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.session = ChatSessionFactory(session_type="OCR")
        self.message = MessageFactory(session=self.session)
        self.parent = OCRAnnotationFactory(message=self.message, completed_by=UserFactory(), annotation_type=1)

    def _serialize(self, data):
        return OCRAnnotationReviewSerializer(data=data, context={"request": _request(self.user)})

    def test_valid_parent(self):
        s = self._serialize({"parent_annotation_id": str(self.parent.id), "result": VALID_RESULT, "annotation_status": "accepted"})
        self.assertTrue(s.is_valid(), s.errors)

    def test_invalid_parent(self):
        import uuid
        s = self._serialize({"parent_annotation_id": str(uuid.uuid4()), "result": VALID_RESULT, "annotation_status": "accepted"})
        self.assertFalse(s.is_valid())

    def test_invalid_review_status(self):
        s = self._serialize({"parent_annotation_id": str(self.parent.id), "result": VALID_RESULT, "annotation_status": "labeled"})
        self.assertFalse(s.is_valid())