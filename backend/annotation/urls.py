from rest_framework.routers import DefaultRouter

from annotation.views import OCRAnnotationViewSet

router = DefaultRouter()
router.register(
    r"ocr-annotation",
    OCRAnnotationViewSet,
    basename="ocr-annotation"
)

urlpatterns = router.urls