import os
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Load environment variables BEFORE Django initialization
from dotenv import load_dotenv
load_dotenv(dotenv_path=BASE_DIR / '.env')

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arena_backend.settings')

# Initialize Django ASGI application
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

# Now import Channels and your consumers
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import re_path
from chat_session.consumers import ChatSessionConsumer

websocket_urlpatterns = [
    re_path(r'ws/chat/session/(?P<session_id>[^/]+)/$', ChatSessionConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})