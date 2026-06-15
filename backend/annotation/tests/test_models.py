import pytest
from django.test import TestCase
from django.db import IntegrityError

from annotation.models import OCRAnnotation
from annotation.constants import (
    ANNOTATOR_ANNOTATION,
    REVIEWER_ANNOTATION,
    LABELED,
    UNLABELED,
)
from annotation.tests.factories import (
    UserFactory,
    ChatSessionFactory,
    MessageFactory,
    OCRAnnotationFactory,
)


class OCRAnnotationCreationTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.session = ChatSessionFactory(session_type="OCR")
        self.message = MessageFactory(session=self.session)

    def test_create_annotation(self):
        ann = OCRAnnotation.objects.create(
            message=self.message,
            completed_by=self.user,
            annotation_type=ANNOTATOR_ANNOTATION,
            annotation_status=UNLABELED,
            result=[],
        )
        self.assertEqual(ann.annotation_type, ANNOTATOR_ANNOTATION)
        self.assertEqual(ann.annotation_status, UNLABELED)

    def test_parent_annotation_relationship(self):
        parent = OCRAnnotationFactory(message=self.message, completed_by=self.user)
        reviewer = UserFactory()
        child = OCRAnnotationFactory(
            message=self.message,
            completed_by=reviewer,
            annotation_type=REVIEWER_ANNOTATION,
            parent_annotation=parent,
        )
        self.assertEqual(child.parent_annotation, parent)

    def test_unique_constraint(self):
        OCRAnnotationFactory(message=self.message, completed_by=self.user)
        with self.assertRaises(IntegrityError):
            OCRAnnotation.objects.create(
                message=self.message,
                completed_by=self.user,
                annotation_type=ANNOTATOR_ANNOTATION,
                annotation_status=UNLABELED,
                result=[],
            )

    def test_correct_annotation_relationship(self):
        ann = OCRAnnotationFactory(message=self.message, completed_by=self.user)
        self.session.correct_annotation = ann
        self.session.save(update_fields=["correct_annotation"])
        self.session.refresh_from_db()
        self.assertEqual(self.session.correct_annotation, ann)