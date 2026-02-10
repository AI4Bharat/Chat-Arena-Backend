"""
Celery configuration for Chat Arena Backend.
DO NOT MODIFY EXISTING DJANGO APPS OR CELERY BEAT SCHEDULE.
"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arena_backend.settings')

app = Celery('arena_backend')

# Load configuration from Django settings with namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered Django apps
# This includes synthetic_asr.tasks
app.autodiscover_tasks()

# Celery Configuration (can be customized in settings.py)
# Default broker: Redis
# Default backend: Redis
# These are configured in settings.py

# Optional: Add synthetic_asr specific tasks to beat schedule
# Note: CELERY_BEAT_SCHEDULE in settings.py already has other tasks
# This is just documentation of what could be added:
#
# 'cleanup-old-jobs': {
#     'task': 'synthetic_asr.tasks.cleanup_old_jobs',
#     'schedule': crontab(day_of_week=0, hour=3, minute=0),  # Weekly
# },


@app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working"""
    print(f'Request: {self.request!r}')
