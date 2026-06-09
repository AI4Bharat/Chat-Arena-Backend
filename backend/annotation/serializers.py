# backend/annotation/serializers.py

from rest_framework import serializers
from annotation.models import OCRAnnotation
from message.models import Message
from user.serializers import UserPublicSerializer
from annotation.constants import (
    ANNOTATOR_ANNOTATION,
    REVIEWER_ANNOTATION,
    ACCEPTED,
    ACCEPTED_WITH_MINOR_CHANGES,
    ACCEPTED_WITH_MAJOR_CHANGES,
    TO_BE_REVISED,
    UNREVIEWED,
    DRAFT,
    SKIPPED,
)


# ---------------------------------------------------------------------------
# OCR region validation mixin
# Shared between Create and Review serializers to avoid duplication.
# ---------------------------------------------------------------------------

class OCRResultValidatorMixin:
    """
    Provides validate_result() for serializers that accept OCR region payloads.
    Each region must conform to the Chat Arena OCR schema:
        {id, box: [x1,y1,x2,y2], text, type, page}
    """

    @staticmethod
    def _validate_ocr_region(region, index):
        """Validate a single OCR region dict. Raises ValidationError on failure."""
        if not isinstance(region, dict):
            raise serializers.ValidationError(
                f"result[{index}]: each region must be an object."
            )

        # id
        if "id" not in region:
            raise serializers.ValidationError(
                f"result[{index}]: 'id' is required."
            )
        if not isinstance(region["id"], (str, int)):
            raise serializers.ValidationError(
                f"result[{index}]: 'id' must be a string or integer."
            )

        # box
        if "box" not in region:
            raise serializers.ValidationError(
                f"result[{index}]: 'box' is required."
            )
        box = region["box"]
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise serializers.ValidationError(
                f"result[{index}]: 'box' must be a list of exactly 4 numeric values [x1, y1, x2, y2]."
            )
        for coord in box:
            if not isinstance(coord, (int, float)):
                raise serializers.ValidationError(
                    f"result[{index}]: all 'box' values must be numeric."
                )

        # text
        if "text" not in region:
            raise serializers.ValidationError(
                f"result[{index}]: 'text' is required."
            )
        if not isinstance(region["text"], str):
            raise serializers.ValidationError(
                f"result[{index}]: 'text' must be a string."
            )

        # type
        if "type" not in region:
            raise serializers.ValidationError(
                f"result[{index}]: 'type' is required."
            )
        if not isinstance(region["type"], str):
            raise serializers.ValidationError(
                f"result[{index}]: 'type' must be a string."
            )

        # page
        if "page" not in region:
            raise serializers.ValidationError(
                f"result[{index}]: 'page' is required."
            )
        if not isinstance(region["page"], int) or region["page"] < 1:
            raise serializers.ValidationError(
                f"result[{index}]: 'page' must be an integer >= 1."
            )

    def validate_result(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "'result' must be a list of OCR region objects."
            )
        for i, region in enumerate(value):
            self._validate_ocr_region(region, i)
        return value


# ---------------------------------------------------------------------------
# Step 2.1 — Read serializer
# ---------------------------------------------------------------------------

class OCRAnnotationSerializer(serializers.ModelSerializer):
    """Read serializer for OCR annotations."""

    completed_by = UserPublicSerializer(read_only=True)

    parent_annotation = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    def get_parent_annotation(self, obj):
        if obj.parent_annotation_id is None:
            return None
        return {"id": str(obj.parent_annotation_id)}

    def get_message(self, obj):
        return {
            "id": str(obj.message_id),
            "session_id": str(obj.message.session_id),
        }

    class Meta:
        model = OCRAnnotation
        fields = [
            "id",
            "message",
            "result",
            "annotation_status",
            "annotation_type",
            "annotation_source",
            "completed_by",
            "parent_annotation",
            "annotation_notes",
            "review_notes",
            "supercheck_notes",
            "lead_time",
            "annotated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Step 2.2 — Annotator create serializer
# ---------------------------------------------------------------------------

class OCRAnnotationCreateSerializer(OCRResultValidatorMixin, serializers.ModelSerializer):
    """
    Validates an annotator's OCR correction submission.
    Does not implement create() — that belongs to Phase 3.
    """

    message_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = OCRAnnotation
        fields = [
            "message_id",
            "result",
            "annotation_status",
            "annotation_notes",
            "lead_time",
        ]

    def validate_annotation_status(self, value):
        # Annotators may only submit labeled or draft records.
        allowed = {"labeled", "draft", "skipped"}
        if value not in allowed:
            raise serializers.ValidationError(
                f"annotation_status must be one of {sorted(allowed)} for annotator submissions."
            )
        return value

    def validate_message_id(self, value):
        try:
            message = Message.objects.select_related("session").get(id=value)
        except Message.DoesNotExist:
            raise serializers.ValidationError("Message not found.")

        if message.session.session_type != "OCR":
            raise serializers.ValidationError(
                "Annotations can only be submitted for OCR sessions."
            )

        return value

    def validate(self, attrs):
        # Enforce annotation_type = ANNOTATOR_ANNOTATION regardless of payload.
        attrs["annotation_type"] = ANNOTATOR_ANNOTATION

        # completed_by is always the requesting user — never trusted from input.
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            attrs["completed_by"] = request.user

        return attrs


# ---------------------------------------------------------------------------
# Step 2.3 — Reviewer serializer
# ---------------------------------------------------------------------------

REVIEWER_ALLOWED_STATUSES = {
    ACCEPTED,
    ACCEPTED_WITH_MINOR_CHANGES,
    ACCEPTED_WITH_MAJOR_CHANGES,
    TO_BE_REVISED,
    UNREVIEWED,
    DRAFT,
    SKIPPED,
}


class OCRAnnotationReviewSerializer(OCRResultValidatorMixin, serializers.ModelSerializer):
    """
    Validates a reviewer's annotation record.
    Does not implement create() — that belongs to Phase 3.
    """

    parent_annotation_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = OCRAnnotation
        fields = [
            "parent_annotation_id",
            "result",
            "annotation_status",
            "review_notes",
            "lead_time",
        ]

    def validate_annotation_status(self, value):
        if value not in REVIEWER_ALLOWED_STATUSES:
            raise serializers.ValidationError(
                f"annotation_status must be one of "
                f"{sorted(REVIEWER_ALLOWED_STATUSES)} for reviewer submissions."
            )
        return value

    def validate_parent_annotation_id(self, value):
        try:
            parent = OCRAnnotation.objects.select_related("message").get(id=value)
        except OCRAnnotation.DoesNotExist:
            raise serializers.ValidationError("Parent annotation not found.")

        if parent.annotation_type != ANNOTATOR_ANNOTATION:
            raise serializers.ValidationError(
                "Parent annotation must be an annotator annotation."
            )

        # Stash for cross-field validation.
        self._parent_annotation = parent
        return value

    def validate(self, attrs):
        # Enforce annotation_type = REVIEWER_ANNOTATION.
        attrs["annotation_type"] = REVIEWER_ANNOTATION

        # completed_by is always the requesting user.
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            attrs["completed_by"] = request.user

        # Cross-field: parent annotation must belong to the same message
        # as the message_id implied by the parent. Stashed in validate_parent_annotation_id.
        parent = getattr(self, "_parent_annotation", None)
        if parent:
            attrs["message_id"] = parent.message_id
            attrs["parent_annotation"] = parent

        return attrs