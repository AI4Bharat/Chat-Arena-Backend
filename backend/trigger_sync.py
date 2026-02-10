import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arena_backend.settings')
django.setup()

from synthetic_asr.tasks import main_orchestrator_task

def trigger_task(job_id):
    print(f"Triggering main_orchestrator_task for {job_id}...")
    # Run the task asynchronously via Celery
    result = main_orchestrator_task.delay(job_id)
    print(f"Task triggered! Task ID: {result.id}")
    print("The task will now poll the PAI server and update the DB to COMPLETED.")

if __name__ == "__main__":
    trigger_task('1769848445379')
