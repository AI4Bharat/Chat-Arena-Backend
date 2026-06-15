import json
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch, MagicMock

from annotation.models import OCRAnnotation
from annotation.constants import (
    ANNOTATOR_ANNOTATION, REVIEWER_ANNOTATION, SUPER_CHECKER_ANNOTATION,
    LABELED, DRAFT, SKIPPED, UNLABELED,
    ACCEPTED, ACCEPTED_WITH_MINOR_CHANGES, TO_BE_REVISED,
    VALIDATED, VALIDATED_WITH_CHANGES, REJECTED, UNVALIDATED,
    SESSION_ANNOTATED, SESSION_REVIEWED, SESSION_SUPER_CHECKED, SESSION_INCOMPLETE,
)
from annotation.tests.factories import UserFactory, ChatSessionFactory, MessageFactory, OCRAnnotationFactory

VALID_RESULT = [{"id": "r1", "box": [0, 0, 100, 50], "text": "Hello", "type": "text", "page": 1}]


def _firebase_auth(user):
    return patch(
        "user.authentication.FirebaseAuthentication.authenticate",
        return_value=(user, None),
    )


class SeedEndpointTests(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.session = ChatSessionFactory(session_type="OCR")
        self.session.annotation_users.add(self.user)
        self.message = MessageFactory(session=self.session, content=json.dumps(VALID_RESULT))

    def test_seed_creates_annotation(self):
        with _firebase_auth(self.user):
            self.client.force_authenticate(user=self.user)
            resp = self.client.post("/ocr-annotation/seed/", {"message_id": str(self.message.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(OCRAnnotation.objects.filter(message=self.message, completed_by=self.user).exists())

    def test_seed_returns_existing(self):
        existing = OCRAnnotationFactory(message=self.message, completed_by=self.user)
        with _firebase_auth(self.user):
            self.client.force_authenticate(user=self.user)
            resp = self.client.post("/ocr-annotation/seed/", {"message_id": str(self.message.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], str(existing.id))

    def test_non_ocr_session_rejected(self):
        llm_session = ChatSessionFactory(session_type="LLM")
        msg = MessageFactory(session=llm_session)
        with _firebase_auth(self.user):
            self.client.force_authenticate(user=self.user)
            resp = self.client.post("/ocr-annotation/seed/", {"message_id": str(msg.id)})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unassigned_user_rejected(self):
        other = UserFactory()
        with _firebase_auth(other):
            self.client.force_authenticate(user=other)
            resp = self.client.post("/ocr-annotation/seed/", {"message_id": str(self.message.id)})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class AnnotatorCreateTests(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.session = ChatSessionFactory(session_type="OCR", required_annotators=1)
        self.session.annotation_users.add(self.user)
        self.message = MessageFactory(session=self.session)

    def _post(self, user, data):
        self.client.force_authenticate(user=user)
        return self.client.post("/ocr-annotation/", data, format="json")

    def test_create_succeeds(self):
        resp = self._post(self.user, {"message_id": str(self.message.id), "result": VALID_RESULT, "annotation_status": "labeled"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_duplicate_rejected(self):
        OCRAnnotationFactory(message=self.message, completed_by=self.user)
        resp = self._post(self.user, {"message_id": str(self.message.id), "result": VALID_RESULT, "annotation_status": "labeled"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassigned_rejected(self):
        other = UserFactory()
        resp = self._post(other, {"message_id": str(self.message.id), "result": VALID_RESULT, "annotation_status": "labeled"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class AnnotatorUpdateTests(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.session = ChatSessionFactory(session_type="OCR", required_annotators=1)
        self.session.annotation_users.add(self.user)
        self.message = MessageFactory(session=self.session)
        self.annotation = OCRAnnotationFactory(
            message=self.message, completed_by=self.user,
            annotation_type=ANNOTATOR_ANNOTATION, annotation_status=UNLABELED,
        )

    def _patch(self, data):
        self.client.force_authenticate(user=self.user)
        return self.client.patch(f"/ocr-annotation/{self.annotation.id}/", data, format="json")

    def test_autosave_updates_only_allowed_fields(self):
        resp = self._patch({"auto_save": True, "result": VALID_RESULT, "lead_time": 5.0})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.annotation.refresh_from_db()
        self.assertEqual(self.annotation.lead_time, 5.0)
        self.assertEqual(self.annotation.annotation_status, UNLABELED)

    def test_labeled_updates_session(self):
        resp = self._patch({"annotation_status": "labeled", "result": VALID_RESULT})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.annotation_status, SESSION_ANNOTATED)

    def test_draft_marks_session_incomplete(self):
        resp = self._patch({"annotation_status": "draft", "result": VALID_RESULT})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.annotation_status, SESSION_INCOMPLETE)

    def test_skipped_marks_session_incomplete(self):
        resp = self._patch({"annotation_status": "skipped", "result": []})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.annotation_status, SESSION_INCOMPLETE)


class ReviewerWorkflowTests(APITestCase):
    def setUp(self):
        self.annotator = UserFactory()
        self.reviewer = UserFactory()
        self.session = ChatSessionFactory(
            session_type="OCR", required_annotators=1,
            annotation_status=SESSION_ANNOTATED,
            review_user=self.reviewer,
        )
        self.session.annotation_users.add(self.annotator)
        self.message = MessageFactory(session=self.session)
        self.parent = OCRAnnotationFactory(
            message=self.message, completed_by=self.annotator,
            annotation_type=ANNOTATOR_ANNOTATION, annotation_status=LABELED,
        )

    def _post(self, data):
        self.client.force_authenticate(user=self.reviewer)
        return self.client.post("/ocr-annotation/", data, format="json")

    def test_reviewer_create_succeeds(self):
        resp = self._post({"mode": "review", "parent_annotation_id": str(self.parent.id), "result": VALID_RESULT, "annotation_status": "accepted"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.session.refresh_from_db()
        self.assertEqual(self.session.annotation_status, SESSION_REVIEWED)

    def test_accepted_promotes_session(self):
        resp = self._post({"mode": "review", "parent_annotation_id": str(self.parent.id), "result": VALID_RESULT, "annotation_status": "accepted"})
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.correct_annotation)

    def test_to_be_revised_updates_parent(self):
        resp = self._post({"mode": "review", "parent_annotation_id": str(self.parent.id), "result": [], "annotation_status": "to_be_revised"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.parent.refresh_from_db()

    def test_revision_count_increments(self):
        reviewer_ann = OCRAnnotationFactory(
            message=self.message, completed_by=self.reviewer,
            annotation_type=REVIEWER_ANNOTATION, annotation_status="unreviewed",
            parent_annotation=self.parent,
        )
        self.client.force_authenticate(user=self.reviewer)
        resp = self.client.patch(
            f"/ocr-annotation/{reviewer_ann.id}/",
            {"annotation_status": "to_be_revised", "result": []},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.revision_loop_count["review_count"], 1)

    def test_revision_limit_enforced(self):
        self.session.revision_loop_count = {"review_count": 3, "super_check_count": 0}
        self.session.save(update_fields=["revision_loop_count"])
        reviewer_ann = OCRAnnotationFactory(
            message=self.message, completed_by=self.reviewer,
            annotation_type=REVIEWER_ANNOTATION, annotation_status="unreviewed",
            parent_annotation=self.parent,
        )
        self.client.force_authenticate(user=self.reviewer)
        resp = self.client.patch(
            f"/ocr-annotation/{reviewer_ann.id}/",
            {"annotation_status": "to_be_revised", "result": []},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class SuperCheckerWorkflowTests(APITestCase):
    def setUp(self):
        self.annotator = UserFactory()
        self.reviewer = UserFactory()
        self.sc = UserFactory()
        self.session = ChatSessionFactory(
            session_type="OCR", required_annotators=1,
            annotation_status=SESSION_REVIEWED,
            review_user=self.reviewer,
            super_check_user=self.sc,
        )
        self.session.annotation_users.add(self.annotator)
        self.message = MessageFactory(session=self.session)
        self.annotator_ann = OCRAnnotationFactory(
            message=self.message, completed_by=self.annotator,
            annotation_type=ANNOTATOR_ANNOTATION, annotation_status=LABELED,
        )
        self.reviewer_ann = OCRAnnotationFactory(
            message=self.message, completed_by=self.reviewer,
            annotation_type=REVIEWER_ANNOTATION, annotation_status=ACCEPTED,
            parent_annotation=self.annotator_ann,
        )
        self.sc_ann = OCRAnnotationFactory(
            message=self.message, completed_by=self.sc,
            annotation_type=SUPER_CHECKER_ANNOTATION, annotation_status=UNVALIDATED,
            parent_annotation=self.reviewer_ann,
        )

    def _patch(self, data):
        self.client.force_authenticate(user=self.sc)
        return self.client.patch(f"/ocr-annotation/{self.sc_ann.id}/", data, format="json")

    def test_validated_promotes_session(self):
        resp = self._patch({"annotation_status": "validated", "result": VALID_RESULT})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.annotation_status, SESSION_SUPER_CHECKED)

    def test_validated_with_changes_promotes_session(self):
        resp = self._patch({"annotation_status": "validated_with_changes", "result": VALID_RESULT})
        self.session.refresh_from_db()
        self.assertEqual(self.session.annotation_status, SESSION_SUPER_CHECKED)

    def test_rejected_increments_count(self):
        resp = self._patch({"annotation_status": "rejected", "result": []})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.revision_loop_count["super_check_count"], 1)

    def test_rejected_reverts_workflow(self):
        resp = self._patch({"annotation_status": "rejected", "result": []})
        self.session.refresh_from_db()
        self.assertEqual(self.session.annotation_status, SESSION_ANNOTATED)

    def test_sc_revision_limit_enforced(self):
        self.session.revision_loop_count = {"review_count": 0, "super_check_count": 3}
        self.session.save(update_fields=["revision_loop_count"])
        resp = self._patch({"annotation_status": "rejected", "result": []})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class ExportEndpointTests(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.session = ChatSessionFactory(session_type="OCR")
        self.session.annotation_users.add(self.user)
        self.message = MessageFactory(session=self.session)
        self.annotation = OCRAnnotationFactory(
            message=self.message, completed_by=self.user,
            annotation_type=ANNOTATOR_ANNOTATION,
            result=VALID_RESULT,
        )

    def _get(self):
        self.client.force_authenticate(user=self.user)
        return self.client.get(f"/ocr-annotation/{self.annotation.id}/export/")

    def test_returns_annotation_result_fallback(self):
        resp = self._get()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, VALID_RESULT)

    def test_returns_correct_annotation_result(self):
        correct = OCRAnnotationFactory(
            message=self.message, completed_by=UserFactory(),
            annotation_type=REVIEWER_ANNOTATION,
            result=[{"id": "r2", "box": [0, 0, 50, 25], "text": "Correct", "type": "text", "page": 1}],
        )
        self.session.correct_annotation = correct
        self.session.save(update_fields=["correct_annotation"])
        resp = self._get()
        self.assertEqual(resp.data[0]["text"], "Correct")

    def test_preserves_ocr_schema(self):
        resp = self._get()
        self.assertIn("id", resp.data[0])
        self.assertIn("box", resp.data[0])
        self.assertIn("text", resp.data[0])
        self.assertIn("type", resp.data[0])
        self.assertIn("page", resp.data[0])


class ChatSessionSerializerOCRTests(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.annotator = UserFactory()
        self.reviewer = UserFactory()
        self.sc = UserFactory()
        self.session = ChatSessionFactory(
            session_type="OCR",
            user=self.user,
            review_user=self.reviewer,
            super_check_user=self.sc,
        )
        self.session.annotation_users.add(self.annotator)

    def test_ocr_fields_present(self):
        from chat_session.serializers import ChatSessionRetrieveSerializer
        data = ChatSessionRetrieveSerializer(self.session).data
        self.assertIn("annotation_status", data)
        self.assertIn("correct_annotation_id", data)
        self.assertIn("has_annotation", data)
        self.assertIn("assigned_annotators", data)
        self.assertIn("review_user", data)
        self.assertIn("super_check_user", data)

    def test_non_ocr_session_unaffected(self):
        from chat_session.serializers import ChatSessionRetrieveSerializer
        llm_session = ChatSessionFactory(session_type="LLM", user=self.user)
        data = ChatSessionRetrieveSerializer(llm_session).data
        self.assertNotIn("annotation_status", data)

    def test_assigned_annotators_list(self):
        from chat_session.serializers import ChatSessionRetrieveSerializer
        data = ChatSessionRetrieveSerializer(self.session).data
        self.assertIn(self.annotator.email, data["assigned_annotators"])

    def test_review_user_email(self):
        from chat_session.serializers import ChatSessionRetrieveSerializer
        data = ChatSessionRetrieveSerializer(self.session).data
        self.assertEqual(data["review_user"], self.reviewer.email)


class EndToEndWorkflowTest(APITestCase):
    def test_full_workflow(self):
        annotator = UserFactory()
        reviewer = UserFactory()
        sc = UserFactory()

        session = ChatSessionFactory(
            session_type="OCR", required_annotators=1,
            review_user=reviewer, super_check_user=sc,
        )
        session.annotation_users.add(annotator)
        message = MessageFactory(session=session)

        # Step 1 — annotator labels
        self.client.force_authenticate(user=annotator)
        resp = self.client.post("/ocr-annotation/", {
            "message_id": str(message.id),
            "result": VALID_RESULT,
            "annotation_status": "labeled",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        session.refresh_from_db()
        self.assertEqual(session.annotation_status, SESSION_ANNOTATED)
        annotator_ann_id = resp.data["id"]

        # Step 2 — reviewer accepts
        self.client.force_authenticate(user=reviewer)
        resp = self.client.post("/ocr-annotation/", {
            "mode": "review",
            "parent_annotation_id": annotator_ann_id,
            "result": VALID_RESULT,
            "annotation_status": "accepted",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        session.refresh_from_db()
        self.assertEqual(session.annotation_status, SESSION_REVIEWED)
        reviewer_ann_id = resp.data["id"]

        # Step 3 — super-checker validates
        sc_ann = OCRAnnotationFactory(
            message=message, completed_by=sc,
            annotation_type=SUPER_CHECKER_ANNOTATION,
            annotation_status=UNVALIDATED,
            parent_annotation=OCRAnnotation.objects.get(id=reviewer_ann_id),
        )
        self.client.force_authenticate(user=sc)
        resp = self.client.patch(f"/ocr-annotation/{sc_ann.id}/", {
            "annotation_status": "validated",
            "result": VALID_RESULT,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.assertEqual(session.annotation_status, SESSION_SUPER_CHECKED)
        self.assertIsNotNone(session.correct_annotation)