"""
Celery tasks for synthetic ASR dataset generation pipeline.
Orchestrates the complete flow: sentences → audio → verification → evaluation.
DO NOT MODIFY EXISTING synthetic_asr MODULES WHEN USING THIS FILE.
"""

import os
from celery import shared_task
from django.utils import timezone
from .models import Job
from .entities import Config
from .pipelines.sentence_generator import generate_sentence_pipeline
from .pipelines.audio_generator import generate_audio_pipeline
from .pipelines.audio_verifier import verify_audio_pipeline
from .pipelines.audio_evaluator import evaluate_audio_pipeline


@shared_task(bind=True, max_retries=3)
def sentence_generation_task(self, job_id: str):
    """This task is deprecated - keeping for backward compatibility"""
    return "Deprecated - use main_orchestrator_task"


@shared_task(bind=True, max_retries=2)
def audio_generation_task(self, job_id: str):
    """This task is deprecated - keeping for backward compatibility"""
    return "Deprecated - use main_orchestrator_task"


@shared_task(bind=True, max_retries=2)
def audio_verification_task(self, job_id: str):
    """This task is deprecated - keeping for backward compatibility"""
    return "Deprecated - use main_orchestrator_task"


@shared_task(bind=True, max_retries=1)
def audio_evaluation_task(self, job_id: str, max_attempts: int = 3):
    """This task is deprecated - keeping for backward compatibility"""
    return "Deprecated - use main_orchestrator_task"


@shared_task(bind=True)
def main_orchestrator_task(self, job_id: str):
    """
    Simplified orchestrator: Delegates entire pipeline to dmubox server
    
    Flow:
    1. Get job config from our DB
    2. Send to dmubox POST /pai/create
    3. Poll dmubox GET /pai/status/<dmubox_job_id>
    4. Update our DB with progress
    
    Args:
        job_id: Our job ID
        
    Returns:
        Result message
    """
    import os
    import time
    from synthetic_asr.utils import http_utils
    from urllib.parse import urlparse
    
    try:
        job = Job.objects.get(job_id=job_id)
        print(f"DEBUG: Job {job_id} loaded. Step details: {job.step_details}")
        
        # Get PAI server URL
        pai_server_url = os.getenv('SYNTHETIC_ASR_PAI_SERVER_URL')
        if not pai_server_url:
            raise Exception("SYNTHETIC_ASR_PAI_SERVER_URL not configured")
        
        parsed_url = urlparse(pai_server_url)
        host = parsed_url.netloc
        scheme = parsed_url.scheme or 'https'
        is_https = scheme == 'https'
        
        # Step 1: Send job to dmubox server (ONLY if not already submitted)
        dmubox_job_id = None
        
        # Common headers
        headers = {
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true'
        }
        
        # Check if we already have a remote ID (recovery mode)
        if job.step_details and 'pai_job_id' in job.step_details:
            dmubox_job_id = job.step_details['pai_job_id']
            print(f"Resuming monitoring for existing PAI job: {dmubox_job_id}")
            # Ensure status is at least PROCESSING so polling logic works
            if job.status == 'FAILED' or job.status == 'SUBMITTING':
                job.status = 'PROCESSING'
                job.current_step = 'Resumed monitoring'
                job.save()
        else:
            # Normal flow: Submit new job
            job.status = 'SUBMITTING'
            job.current_step = 'Submitting to PAI server'
            job.save()
            
            payload = {'config': job.payload}
            
            # Use appropriate connection method based on scheme
            if is_https:
                result, err = http_utils.make_post_request(
                    host,
                    '/pai/create',
                    headers,
                    payload
                )
            else:
                result, err = http_utils.make_local_post_request(
                    host,
                    '/pai/create',
                    headers,
                    payload,
                    port=80
                )
            
            if err:
                raise Exception(f"Failed to submit to PAI server: {err}")
            
            # Get dmubox job ID (it returns just the job_id as string)
            dmubox_job_id = str(result) if result else None
            if not dmubox_job_id:
                raise Exception("PAI server did not return job ID")
            
            job.status = 'PROCESSING'
            job.current_step = 'Processing on PAI server'
            job.step_details = {'pai_job_id': dmubox_job_id}
            job.save()
            
            return f"Job {job_id} submitted successfully. PAI Job ID: {dmubox_job_id}"
        
    except Job.DoesNotExist:
        return f"Job {job_id} not found"
    except Exception as e:
        try:
            job = Job.objects.get(job_id=job_id)
            job.status = 'FAILED'
            job.error = {'step': 'orchestrator', 'message': str(e)}
            job.save()
        except:
            pass
        raise
