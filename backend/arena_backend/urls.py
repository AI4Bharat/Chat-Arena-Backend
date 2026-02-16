"""arena_backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions, routers
from . import health

schema_view = get_schema_view(
    openapi.Info(
        title="AI Model Playground API",
        default_version='v1',
        description="API for AI Model comparison and interaction platform",
        terms_of_service="https://www.yourapp.com/terms/",
        contact=openapi.Contact(email="contact@yourapp.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Health check endpoints (must be first for load balancers)
    path('health/', health.health, name='health'),
    path('ready/', health.readiness, name='readiness'),
    path('live/', health.liveness, name='liveness'),
    path('status/', health.detailed_status, name='detailed-status'),

    path("admin/", admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('user.urls')),
    path('', include('ai_model.urls')),
    path('', include('chat_session.urls')),
    path('', include('feedback.urls')),
    path('', include('message.urls')),
    path('', include('model_metrics.urls')),
    path('', include('leaderboards.urls')),

    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/docs/', include('rest_framework.urls')),
]

router = routers.DefaultRouter()
urlpatterns += router.urls