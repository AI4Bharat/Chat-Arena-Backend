import uuid
from django.contrib.auth import get_user_model
from annotation.models import OCRAnnotation
from annotation.constants import ANNOTATOR_ANNOTATION, UNLABELED, MANUAL_ANNOTATION

User = get_user_model()


def UserFactory(**kwargs):
    defaults = {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "testpass",
    }
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def ChatSessionFactory(**kwargs):
    from chat_session.models import ChatSession
    defaults = {
        "session_type": "OCR",
        "mode": "single",
        "required_annotators": 1,
        "revision_loop_limit": 3,
        "revision_loop_count": {"review_count": 0, "super_check_count": 0},
        "annotation_status": "unannotated",
    }
    defaults.update(kwargs)
    user = defaults.pop("user", None) or UserFactory()
    return ChatSession.objects.create(user=user, **defaults)


def MessageFactory(**kwargs):
    from message.models import Message
    defaults = {
        "role": "assistant",
        "content": "[]",
        "status": "completed",
    }
    defaults.update(kwargs)
    return Message.objects.create(**defaults)


def OCRAnnotationFactory(**kwargs):
    defaults = {
        "annotation_type": ANNOTATOR_ANNOTATION,
        "annotation_status": UNLABELED,
        "annotation_source": MANUAL_ANNOTATION,
        "result": [],
        "lead_time": 0.0,
    }
    defaults.update(kwargs)
    return OCRAnnotation.objects.create(**defaults)