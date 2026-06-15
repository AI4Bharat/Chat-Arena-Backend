# backend/annotation/constants.py

# ---------------------------------------------------------------------------
# Annotation Type — which role produced this annotation
# ---------------------------------------------------------------------------

ANNOTATOR_ANNOTATION = 1
REVIEWER_ANNOTATION = 2
SUPER_CHECKER_ANNOTATION = 3

ANNOTATION_TYPE = [
    (ANNOTATOR_ANNOTATION, "Annotator's Annotation"),
    (REVIEWER_ANNOTATION, "Reviewer's Annotation"),
    (SUPER_CHECKER_ANNOTATION, "Super Checker's Annotation"),
]

# ---------------------------------------------------------------------------
# Annotation Source — how the annotation was produced
# ---------------------------------------------------------------------------

MANUAL_ANNOTATION = 0
AUTOMATIC_ANNOTATION = 1

ANNOTATION_SOURCE = [
    (MANUAL_ANNOTATION, "Manual Annotation"),
    (AUTOMATIC_ANNOTATION, "Automatic Annotation"),
]

# ---------------------------------------------------------------------------
# Annotation Status — lifecycle state of a single annotation record
# ---------------------------------------------------------------------------

UNLABELED = "unlabeled"
LABELED = "labeled"
DRAFT = "draft"
SKIPPED = "skipped"
ACCEPTED = "accepted"
ACCEPTED_WITH_MINOR_CHANGES = "accepted_with_minor_changes"
ACCEPTED_WITH_MAJOR_CHANGES = "accepted_with_major_changes"
TO_BE_REVISED = "to_be_revised"
VALIDATED = "validated"
VALIDATED_WITH_CHANGES = "validated_with_changes"
REJECTED = "rejected"
UNREVIEWED = "unreviewed"
UNVALIDATED = "unvalidated"

ANNOTATION_STATUS = [
    (UNLABELED, "Unlabeled"),
    (LABELED, "Labeled"),
    (DRAFT, "Draft"),
    (SKIPPED, "Skipped"),
    (UNREVIEWED, "Unreviewed"),
    (ACCEPTED, "Accepted"),
    (ACCEPTED_WITH_MINOR_CHANGES, "Accepted with Minor Changes"),
    (ACCEPTED_WITH_MAJOR_CHANGES, "Accepted with Major Changes"),
    (TO_BE_REVISED, "To be Revised"),
    (UNVALIDATED, "Unvalidated"),
    (VALIDATED, "Validated"),
    (VALIDATED_WITH_CHANGES, "Validated with Changes"),
    (REJECTED, "Rejected"),
]

# ---------------------------------------------------------------------------
# Session Annotation Status — workflow state tracked at ChatSession level
# ---------------------------------------------------------------------------

SESSION_UNANNOTATED = "unannotated"
SESSION_ANNOTATED = "annotated"
SESSION_REVIEWED = "reviewed"
SESSION_SUPER_CHECKED = "super_checked"
SESSION_INCOMPLETE = "incomplete"

SESSION_ANNOTATION_STATUS = [
    (SESSION_UNANNOTATED, "Unannotated"),
    (SESSION_ANNOTATED, "Annotated"),
    (SESSION_REVIEWED, "Reviewed"),
    (SESSION_SUPER_CHECKED, "Super Checked"),
    (SESSION_INCOMPLETE, "Incomplete"),
]