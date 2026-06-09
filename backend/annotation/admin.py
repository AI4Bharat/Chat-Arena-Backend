from django.contrib import admin

from annotation.models import OCRAnnotation


@admin.register(OCRAnnotation)
class OCRAnnotationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "message",
        "completed_by",
        "annotation_type",
        "annotation_status",
        "annotated_at",
        "created_at",
    ]
    list_filter = [
        "annotation_type",
        "annotation_status",
        "annotation_source",
        "annotated_at",
        "created_at",
    ]
    search_fields = [
        "message__id",
        "message__session__id",
        "completed_by__email",
    ]
    readonly_fields = ["created_at", "updated_at", "annotated_at"]
    ordering = ["-created_at"]
    list_select_related = ["message", "completed_by", "parent_annotation"]
    fieldsets = (
        ("Core Information", {
            "fields": (
                "message",
                "completed_by",
                "annotation_type",
                "annotation_status",
                "annotation_source",
                "parent_annotation",
            )
        }),
        ("Annotation Data", {
            "fields": (
                "result",
                "annotation_notes",
                "review_notes",
                "supercheck_notes",
                "lead_time",
            )
        }),
        ("Workflow", {
            "fields": ("annotated_at",)
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at")
        }),
    )