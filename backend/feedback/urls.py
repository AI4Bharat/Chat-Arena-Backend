from django.urls import path, include
from rest_framework.routers import DefaultRouter
from feedback.views import FeedbackViewSet, ModelFeedbackView, FeedbackReportView

app_name = 'feedback'

router = DefaultRouter()
router.register(r'feedback', FeedbackViewSet, basename='feedback')

urlpatterns = [
    path('', include(router.urls)),
    path('models/<uuid:model_id>/feedback/', ModelFeedbackView.as_view(), name='model-feedback'),
    path('reports/', FeedbackReportView.as_view(), name='feedback-report'),
]

# URL patterns will be:
# GET /api/feedback/ - List feedback
# POST /api/feedback/ - Create feedback
# GET /api/feedback/{id}/ - Get feedback details
# PATCH /api/feedback/{id}/ - Update feedback
# DELETE /api/feedback/{id}/ - Delete feedback
# POST /api/feedback/bulk_create/ - Create multiple feedbacks
# GET /api/feedback/session_summary/ - Get session feedback summary
# GET /api/feedback/my_stats/ - Get user's feedback statistics
# GET /api/feedback/model_comparison/ - Compare two models
# GET /api/feedback/trending_categories/ - Get trending categories
# GET /api/feedback/user_tracking_stats/ - Admin: per-turn tracking stats for a user
# GET /api/models/{model_id}/feedback/ - Get model feedback stats
# GET /api/reports/ - Generate feedback report