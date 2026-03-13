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
application = get_asgi_application()