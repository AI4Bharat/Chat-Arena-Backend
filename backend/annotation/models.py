# backend/annotation/models.py

import uuid
from django.db import models
from user.models import User
from message.models import Message
from annotation.constants import (
    ANNOTATION_STATUS,
    ANNOTATION_TYPE,
    ANNOTATION_SOURCE,
    UNLABELED,
    ANNOTATOR_ANNOTATION,
    MANUAL_ANNOTATION,
)


class OCRAnnotation(models.Model):
    """
    Stores a single annotator's, reviewer's, or super-checker's correction
    of the OCR regions attached to a Message.

    The three-level review chain is represented via the parent_annotation
    self-FK:
        Annotator annotation  (annotation_type=1, parent=None)
        Reviewer annotation   (annotation_type=2, parent=annotator annotation)
        Super-check annotation(annotation_type=3, parent=reviewer annotation)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ------------------------------------------------------------------
    # Core relationships
    # ------------------------------------------------------------------

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="ocr_annotations",
        help_text="The OCR message whose regions are being corrected.",
    )

    completed_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ocr_annotations",
        help_text="The annotator, reviewer, or super-checker who produced this annotation.",
    )

    parent_annotation = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        default=None,
        related_name="child_annotations",
        help_text=(
            "Reviewer annotations point to the annotator annotation they are reviewing. "
            "Super-check annotations point to the reviewer annotation they are validating."
        ),
    )

    # ------------------------------------------------------------------
    # Annotation payload
    # ------------------------------------------------------------------

    result = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of corrected OCR region objects. Each object matches the "
            "Chat Arena OCR schema: {id, box: [x1,y1,x2,y2], text, type, page}."
        ),
    )

    # ------------------------------------------------------------------
    # Workflow state
    # ------------------------------------------------------------------

    annotation_status = models.CharField(
        max_length=100,
        choices=ANNOTATION_STATUS,
        default=UNLABELED,
        help_text="Lifecycle state of this annotation record.",
    )

    annotation_type = models.PositiveSmallIntegerField(
        choices=ANNOTATION_TYPE,
        default=ANNOTATOR_ANNOTATION,
        help_text="Which role in the review chain produced this record.",
    )

    annotation_source = models.PositiveSmallIntegerField(
        choices=ANNOTATION_SOURCE,
        default=MANUAL_ANNOTATION,
        help_text="Whether the annotation was produced manually or automatically.",
    )

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    annotation_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Free-text notes left by the annotator.",
    )

    review_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Free-text notes left by the reviewer.",
    )

    supercheck_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Free-text notes left by the super-checker.",
    )

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    lead_time = models.FloatField(
        default=0.0,
        help_text="Time in seconds the annotator spent on this annotation (client-reported).",
    )

    annotated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when this annotation was first moved into an active state "
            "(e.g. labeled, accepted, validated). Null while still unlabeled or draft."
        ),
    )

    # ------------------------------------------------------------------
    # Standard timestamps (Chat Arena convention: auto_now_add / auto_now)
    # ------------------------------------------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------

    class Meta:
        db_table = "ocr_annotations"
        ordering = ["-created_at"]
        unique_together = ("message", "completed_by")
        indexes = [
            models.Index(fields=["message", "annotation_type"]),
            models.Index(fields=["completed_by", "annotation_status"]),
            models.Index(fields=["annotation_status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (
            f"OCRAnnotation({self.annotation_type}) "
            f"by {self.completed_by_id} on message {self.message_id} "
            f"[{self.annotation_status}]"
        )