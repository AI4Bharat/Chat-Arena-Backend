# backend/annotation/views.py

from urllib import request

from django.db import transaction
from django.utils import timezone

from rest_framework import status, mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import json
from rest_framework.decorators import action
from message.models import Message
from annotation.constants import AUTOMATIC_ANNOTATION, MANUAL_ANNOTATION

from annotation.serializers import (
    OCRAnnotationSerializer,
    OCRAnnotationCreateSerializer,
    OCRAnnotationReviewSerializer,
)
from annotation.constants import (
    ANNOTATOR_ANNOTATION,
    REVIEWER_ANNOTATION,
    SUPER_CHECKER_ANNOTATION,
    LABELED,
    DRAFT,
    SKIPPED,
    UNLABELED,
    UNREVIEWED,
    ACCEPTED,
    ACCEPTED_WITH_MINOR_CHANGES,
    ACCEPTED_WITH_MAJOR_CHANGES,
    TO_BE_REVISED,
    UNVALIDATED,
    VALIDATED,
    VALIDATED_WITH_CHANGES,
    REJECTED,
    SESSION_ANNOTATED,
    SESSION_INCOMPLETE,
    SESSION_REVIEWED,
    SESSION_SUPER_CHECKED,
)

from user.authentication import FirebaseAuthentication
from annotation.models import OCRAnnotation
from annotation.serializers import (
    OCRAnnotationSerializer,
    OCRAnnotationCreateSerializer,
)
from annotation.constants import (
    ANNOTATOR_ANNOTATION,
    REVIEWER_ANNOTATION,
    LABELED,
    DRAFT,
    SKIPPED,
    UNLABELED,
    UNREVIEWED,
    TO_BE_REVISED,
    SESSION_ANNOTATED,
    SESSION_INCOMPLETE,
)


class OCRAnnotationViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for OCR annotation workflow.

    Phase 3: Annotator create and partial_update.
    Phase 4: Reviewer create and partial_update (stubbed below).
    Phase 5: Super-checker flow.
    """

    authentication_classes = [FirebaseAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = OCRAnnotation.objects.select_related(
        "message__session",
        "completed_by",
        "parent_annotation",
    )

    def get_serializer_class(self):
        if self.action == "create":
            return OCRAnnotationCreateSerializer
        return OCRAnnotationSerializer

    # ------------------------------------------------------------------
    # create() dispatcher
    # ------------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        if request.data.get("mode") == "review":
            return self.create_review_annotation(request)
        return self.create_base_annotation(request)

    # ------------------------------------------------------------------
    # Step 3.3 — Annotator create
    # ------------------------------------------------------------------

    def create_base_annotation(self, request):
        serializer = OCRAnnotationCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        message_id = serializer.validated_data["message_id"]

        # Fetch message + session (message_id already validated by serializer)
        from message.models import Message
        message = Message.objects.select_related("session").get(id=message_id)
        session = message.session

        # Guard: soft-deleted session
        if session.deleted_at is not None:
            return Response(
                {"message": "This session has been deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Guard: annotator assignment
        if not self._validate_assigned_annotator(request.user, session):
            return Response(
                {"message": "You are not assigned as an annotator for this session."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Guard: ownership (completed_by must match request.user)
        # set in serializer.validate() — verified here as defence-in-depth
        if serializer.validated_data.get("completed_by") != request.user:
            return Response(
                {"message": "You are trying to impersonate another user :("},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Guard: duplicate annotation
        if OCRAnnotation.objects.filter(
            message=message, completed_by=request.user
        ).exists():
            return Response(
                {"message": "Cannot add more than one annotation per user!"},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            annotation = serializer.save(message=message)

            if annotation.annotation_status == LABELED:
                self._update_session_annotation_state(annotation, session)

        return Response(
            OCRAnnotationSerializer(annotation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Phase 4 stub — reviewer create
    # ------------------------------------------------------------------

    def create_review_annotation(self, request):
        serializer = OCRAnnotationReviewSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from message.models import Message
        parent_annotation = serializer._parent_annotation
        message = parent_annotation.message
        session = message.session

        if session.deleted_at is not None:
            return Response(
                {"message": "This session has been deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if session.review_user_id != request.user.id:
            return Response(
                {"message": "You are not assigned as a reviewer for this session."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if serializer.validated_data.get("completed_by") != request.user:
            return Response(
                {"message": "You are trying to impersonate another user :("},
                status=status.HTTP_403_FORBIDDEN,
            )

        if OCRAnnotation.objects.filter(
            message=message, completed_by=request.user
        ).exists():
            return Response(
                {"message": "Cannot add more than one annotation per user!"},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            annotation = serializer.save(message=message)

            accepted_statuses = {ACCEPTED, ACCEPTED_WITH_MINOR_CHANGES, ACCEPTED_WITH_MAJOR_CHANGES}
            if annotation.annotation_status in accepted_statuses:
                session.correct_annotation = annotation
                session.annotation_status = SESSION_REVIEWED
                session.save(update_fields=["correct_annotation", "annotation_status"])

        return Response(
            OCRAnnotationSerializer(annotation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Step 3.4 — Annotator partial_update
    # ------------------------------------------------------------------

    def partial_update(self, request, *args, **kwargs):
        try:
            annotation = self.get_object()
        except Exception:
            return Response(
                {"message": "Annotation object does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        session = annotation.message.session

        # Route by annotation type
        if annotation.annotation_type == ANNOTATOR_ANNOTATION:
            return self._partial_update_annotator(request, annotation, session)

        # Phase 4 placeholder — reviewer and super-checker updates

        if annotation.annotation_type == REVIEWER_ANNOTATION:
            return self._partial_update_reviewer(request, annotation, session)

        if annotation.annotation_type == SUPER_CHECKER_ANNOTATION:
            return self._partial_update_superchecker(request, annotation, session)
        
        return Response(
            {"message": "Update for this annotation type is not yet implemented."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    def _partial_update_annotator(self, request, annotation, session):
        """Handles partial_update for annotator-type annotations only."""

        # Guard: ownership
        if not self._validate_annotation_owner(request.user, annotation):
            return Response(
                {"message": "You are trying to impersonate another user :("},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Guard: annotator assignment
        if not self._validate_assigned_annotator(request.user, session):
            return Response(
                {"message": "You are not assigned as an annotator for this session."},
                status=status.HTTP_403_FORBIDDEN,
            )

        auto_save = bool(request.data.get("auto_save", False))

        if auto_save:
            return self._autosave_annotator(request, annotation)

        return self._full_save_annotator(request, annotation, session)

    def _autosave_annotator(self, request, annotation):
        """
        Autosave path — persists only result, lead_time, annotation_notes.
        No status transitions. No session updates.
        """
        update_fields = ["updated_at"]

        if "result" in request.data:
            annotation.result = request.data["result"]
            update_fields.append("result")

        if "lead_time" in request.data:
            annotation.lead_time = request.data["lead_time"]
            update_fields.append("lead_time")

        if "annotation_notes" in request.data:
            annotation.annotation_notes = request.data["annotation_notes"]
            update_fields.append("annotation_notes")

        annotation.save(update_fields=update_fields)

        return Response(
            OCRAnnotationSerializer(annotation).data,
            status=status.HTTP_200_OK,
        )

    def _full_save_annotator(self, request, annotation, session):
        """
        Full-save path — validates status transition, updates annotation
        and session state atomically.
        """
        annotation_status = request.data.get("annotation_status")
        allowed_statuses = {UNLABELED, LABELED, DRAFT, SKIPPED}

        if annotation_status not in allowed_statuses:
            return Response(
                {
                    "message": (
                        f"Missing or invalid annotation_status. "
                        f"Allowed values: {sorted(allowed_statuses)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Apply all incoming fields via partial serializer
            serializer = OCRAnnotationCreateSerializer(
                annotation,
                data=request.data,
                partial=True,
                context={"request": self.request},
            )
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            annotation = serializer.save()

            if annotation_status == LABELED:
                if annotation.annotated_at is None:
                    annotation.annotated_at = timezone.now()
                    annotation.save(update_fields=["annotated_at"])

                self._update_session_annotation_state(annotation, session)

                # Phase 4 dependency — reset reviewer to unreviewed if previously to_be_revised
                self._reset_reviewer_annotation_if_revised(annotation)

            elif annotation_status in (DRAFT, SKIPPED):
                session.annotation_status = SESSION_INCOMPLETE
                session.save(update_fields=["annotation_status"])

        return Response(
            OCRAnnotationSerializer(annotation).data,
            status=status.HTTP_200_OK,
        )


    def _partial_update_reviewer(self, request, annotation, session):
        if session.review_user_id != request.user.id:
            return Response(
                {"message": "You are not assigned as a reviewer for this session."},
                status=status.HTTP_403_FORBIDDEN,
            )

        auto_save = bool(request.data.get("auto_save", False))

        if auto_save:
            update_fields = ["updated_at"]
            for field in ("result", "lead_time", "review_notes"):
                if field in request.data:
                    setattr(annotation, field, request.data[field])
                    update_fields.append(field)
            annotation.save(update_fields=update_fields)
            return Response(OCRAnnotationSerializer(annotation).data, status=status.HTTP_200_OK)

        annotation_status = request.data.get("annotation_status")
        allowed_statuses = {
            ACCEPTED, ACCEPTED_WITH_MINOR_CHANGES, ACCEPTED_WITH_MAJOR_CHANGES,
            TO_BE_REVISED, UNREVIEWED, DRAFT, SKIPPED,
        }
        if annotation_status not in allowed_statuses:
            return Response(
                {"message": f"Invalid annotation_status. Allowed: {sorted(allowed_statuses)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OCRAnnotationReviewSerializer(
            annotation, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        accepted_statuses = {ACCEPTED, ACCEPTED_WITH_MINOR_CHANGES, ACCEPTED_WITH_MAJOR_CHANGES}

        with transaction.atomic():
            annotation = serializer.save()

            if annotation_status in accepted_statuses:
                session.correct_annotation = annotation
                session.annotation_status = SESSION_REVIEWED
                session.save(update_fields=["correct_annotation", "annotation_status"])
                self._reset_rejected_superchecks(annotation.message)

            elif annotation_status == TO_BE_REVISED:
                if not self._validate_revision_limit(session, "review_count"):
                    return Response(
                        {"message": "Revision loop limit exceeded."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                self._increment_review_revision_count(session)
                if annotation.parent_annotation:
                    annotation.parent_annotation.annotation_status = TO_BE_REVISED
                    annotation.parent_annotation.save(update_fields=["annotation_status", "updated_at"])
                session.annotation_status = SESSION_INCOMPLETE
                session.save(update_fields=["annotation_status", "revision_loop_count"])

            elif annotation_status in (DRAFT, SKIPPED):
                session.annotation_status = SESSION_ANNOTATED
                session.save(update_fields=["annotation_status"])

            elif annotation_status == UNREVIEWED:
                pass  # persist annotation only

        return Response(OCRAnnotationSerializer(annotation).data, status=status.HTTP_200_OK)


    def _partial_update_superchecker(self, request, annotation, session):
        if session.super_check_user_id != request.user.id:
            return Response(
                {"message": "You are not assigned as a super-checker for this session."},
                status=status.HTTP_403_FORBIDDEN,
            )

        auto_save = bool(request.data.get("auto_save", False))

        if auto_save:
            update_fields = ["updated_at"]
            for field in ("result", "lead_time", "supercheck_notes"):
                if field in request.data:
                    setattr(annotation, field, request.data[field])
                    update_fields.append(field)
            annotation.save(update_fields=update_fields)
            return Response(OCRAnnotationSerializer(annotation).data, status=status.HTTP_200_OK)

        annotation_status = request.data.get("annotation_status")
        allowed_statuses = {UNVALIDATED, VALIDATED, VALIDATED_WITH_CHANGES, REJECTED, DRAFT, SKIPPED}
        if annotation_status not in allowed_statuses:
            return Response(
                {"message": f"Invalid annotation_status. Allowed: {sorted(allowed_statuses)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OCRAnnotationSerializer(
            annotation, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            annotation = serializer.save()

            if annotation_status in (VALIDATED, VALIDATED_WITH_CHANGES):
                session.correct_annotation = annotation
                session.annotation_status = SESSION_SUPER_CHECKED
                session.save(update_fields=["correct_annotation", "annotation_status"])

                reviewer_annotation = OCRAnnotation.objects.filter(
                    message=annotation.message,
                    annotation_type=REVIEWER_ANNOTATION,
                ).first()
                if reviewer_annotation:
                    reviewer_annotation.annotation_status = annotation_status
                    reviewer_annotation.save(update_fields=["annotation_status", "updated_at"])

                if annotation.parent_annotation:
                    annotation.parent_annotation.annotation_status = annotation_status
                    annotation.parent_annotation.save(update_fields=["annotation_status", "updated_at"])

            elif annotation_status == REJECTED:
                if not self._validate_revision_limit(session, "super_check_count"):
                    return Response(
                        {"message": "Super-check revision loop limit exceeded."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                self._increment_supercheck_revision_count(session)

                reviewer_annotation = OCRAnnotation.objects.filter(
                    message=annotation.message,
                    annotation_type=REVIEWER_ANNOTATION,
                ).first()
                if reviewer_annotation:
                    reviewer_annotation.annotation_status = REJECTED
                    reviewer_annotation.save(update_fields=["annotation_status", "updated_at"])

                session.annotation_status = SESSION_ANNOTATED
                session.save(update_fields=["annotation_status", "revision_loop_count"])

            elif annotation_status in (DRAFT, SKIPPED):
                session.annotation_status = SESSION_REVIEWED
                session.save(update_fields=["annotation_status"])

            elif annotation_status == UNVALIDATED:
                pass  # persist only

        return Response(OCRAnnotationSerializer(annotation).data, status=status.HTTP_200_OK)

        
        # ------------------------------------------------------------------
        # Helper methods
        # ------------------------------------------------------------------

        @staticmethod
        def _validate_annotation_owner(user, annotation):
            """Returns True if the user is the annotation's completed_by."""
            return annotation.completed_by_id == user.id

        @staticmethod
        def _validate_assigned_annotator(user, session):
            """Returns True if the user is in the session's annotation_users M2M."""
            return session.annotation_users.filter(id=user.id).exists()

        @staticmethod
        def _count_labeled_annotations(message):
            """Returns count of labeled annotator annotations for the given message."""
            return OCRAnnotation.objects.filter(
                message=message,
                annotation_type=ANNOTATOR_ANNOTATION,
                annotation_status=LABELED,
            ).count()

        @staticmethod
        def _update_session_annotation_state(annotation, session):
            """
            Checks if the labeled annotation count meets session.required_annotators.
            If so, transitions session.annotation_status to 'annotated'.
            For single-annotator sessions also sets session.correct_annotation.

            Called from both create and full-save update paths.
            """
            labeled_count = OCRAnnotationViewSet._count_labeled_annotations(
                annotation.message
            )

            if session.required_annotators == labeled_count:
                session.annotation_status = SESSION_ANNOTATED

                if session.required_annotators == 1:
                    session.correct_annotation = annotation
                else:
                    # Multiple annotators — correct_annotation determined at review stage
                    session.correct_annotation = None

                session.save(update_fields=["annotation_status", "correct_annotation"])

        @staticmethod
        def _reset_reviewer_annotation_if_revised(annotation):
            """
            Phase 4 dependency.

            If a reviewer annotation exists for the same message and its status
            is TO_BE_REVISED, reset it to UNREVIEWED so the reviewer re-evaluates
            the updated annotator submission.

            This helper is intentionally isolated and has no other side effects.
            Reviewer business logic (notifications, revision_loop_count) is Phase 4.
            """
            try:
                reviewer_annotation = OCRAnnotation.objects.get(
                    message=annotation.message,
                    annotation_type=REVIEWER_ANNOTATION,
                )
                if reviewer_annotation.annotation_status == TO_BE_REVISED:
                    reviewer_annotation.annotation_status = UNREVIEWED
                    reviewer_annotation.save(update_fields=["annotation_status", "updated_at"])
            except OCRAnnotation.DoesNotExist:
                pass
        
        @staticmethod
        def _get_revision_counts(session):
            return session.revision_loop_count or {"review_count": 0, "super_check_count": 0}

        @staticmethod
        def _validate_revision_limit(session, key):
            counts = OCRAnnotationViewSet._get_revision_counts(session)
            return counts.get(key, 0) < session.revision_loop_limit

        @staticmethod
        def _increment_review_revision_count(session):
            counts = OCRAnnotationViewSet._get_revision_counts(session)
            counts["review_count"] = counts.get("review_count", 0) + 1
            session.revision_loop_count = counts

        @staticmethod
        def _increment_supercheck_revision_count(session):
            counts = OCRAnnotationViewSet._get_revision_counts(session)
            counts["super_check_count"] = counts.get("super_check_count", 0) + 1
            session.revision_loop_count = counts

        @staticmethod
        def _reset_rejected_superchecks(message):
            OCRAnnotation.objects.filter(
                message=message,
                annotation_type=SUPER_CHECKER_ANNOTATION,
                annotation_status=REJECTED,
            ).update(annotation_status=UNVALIDATED)
    
    # ------------------------------------------------------------------
    # Step 6.2 / 6.3 — Seed endpoint
    # ------------------------------------------------------------------

    @action(detail=False, methods=["post"])
    def seed(self, request):
        message_id = request.data.get("message_id")
        if not message_id:
            return Response({"message": "message_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            message = Message.objects.select_related("session").get(id=message_id)
        except Message.DoesNotExist:
            return Response({"message": "Message not found."}, status=status.HTTP_404_NOT_FOUND)

        session = message.session

        if session.session_type != "OCR":
            return Response({"message": "Session is not an OCR session."}, status=status.HTTP_400_BAD_REQUEST)

        if not session.annotation_users.filter(id=request.user.id).exists():
            return Response({"message": "You are not assigned as an annotator for this session."}, status=status.HTTP_403_FORBIDDEN)

        annotation = self._seed_from_message(message, request.user)
        return Response(
            OCRAnnotationSerializer(annotation, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _seed_from_message(message, user):
        existing = OCRAnnotation.objects.filter(message=message, completed_by=user).first()
        if existing:
            return existing

        try:
            result = json.loads(message.content) if isinstance(message.content, str) else message.content
            if not isinstance(result, list):
                result = []
        except (ValueError, TypeError):
            result = []

        return OCRAnnotation.objects.create(
            message=message,
            completed_by=user,
            annotation_type=ANNOTATOR_ANNOTATION,
            annotation_source=AUTOMATIC_ANNOTATION,
            annotation_status=UNLABELED,
            result=result,
        )

    # ------------------------------------------------------------------
    # Step 6.6 — Export endpoint
    # ------------------------------------------------------------------

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        try:
            annotation = self.get_object()
        except Exception:
            return Response({"message": "Annotation not found."}, status=status.HTTP_404_NOT_FOUND)

        session = annotation.message.session
        correct = session.correct_annotation

        if correct is not None:
            result = correct.result
        else:
            result = annotation.result

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (ValueError, TypeError):
                result = []

        return Response(result, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Step 6.7 — Centralised session metadata update
    # ------------------------------------------------------------------

    @staticmethod
    def _update_session_annotation_metadata(session, annotation=None):
        update_fields = ["annotation_status"]
        if annotation is not None:
            session.correct_annotation = annotation
            update_fields.append("correct_annotation")
        session.save(update_fields=update_fields)