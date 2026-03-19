import os
import django
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'arena_backend.settings')
django.setup()

from synthetic_asr.models import Job

def fix_job_state(job_id_to_fix):
    try:
        job = Job.objects.get(job_id=job_id_to_fix)
        print(f"Current state: status={job.status}, step_details={job.step_details}, error={job.error}")
        
        # Update to trigger polling
        job.status = 'PROCESSING'
        job.step_details = {'pai_job_id': job_id_to_fix}
        job.error = None
        job.current_step = 'Resuming monitoring'
        job.save()
        
        print(f"Updated state: status={job.status}, step_details={job.step_details}, error={job.error}")
        print("Success: Job state fixed. Celery should now be able to poll correctly.")
        
    except Job.DoesNotExist:
        print(f"Error: Job {job_id_to_fix} not found in database.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fix_job_state('1769848445379')
