from django.urls import path
from .views import FrontendErrorLogView

urlpatterns = [
    path('logs/frontend-error/', FrontendErrorLogView.as_view(), name='frontend-error-log'),
]
