from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/asr/jobs/$', consumers.JobStatusConsumer.as_asgi()),
]
