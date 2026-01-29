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
    """
    Task 1: Generate sentences for the dataset
    
    Args:
        job_id: Job ID
        
    Returns:
        Success message or error
    """
    try:
        job = Job.objects.get(job_id=job_id)
        
        # Update job status
        job.status = 'PROCESSING_SENTENCES'
        job.current_step = 'Generating sentences'
        job.sentence_generation_started_at = timezone.now()
        job.save()
        
        # Parse config from payload
        config, config_issues = Config.create_obj_from_dict(job.payload)
        if config_issues or not config:
            raise ValueError(f"Invalid config: {config_issues}")
        
        # Call sentence generation pipeline
        sentences, err = generate_sentence_pipeline(config)
        if err:
            raise Exception(f"Sentence generation failed: {err}")
        
        if not sentences:
            raise Exception("No sentences were generated")
        
        # Update job
        job.status = 'SENTENCE_GENERATED'
        job.current_step = 'Sentences ready'
        job.progress_percentage = 20
        job.sentence_generation_completed_at = timezone.now()
        job.step_details = {
            'sentences_generated': len(sentences),
            'message': f'Successfully generated {len(sentences)} sentences'
        }
        job.save()
        
        return f"Generated {len(sentences)} sentences"
        
    except Job.DoesNotExist:
        return f"Job {job_id} not found"
    except Exception as e:
        job.status = 'FAILED'
        job.error = {'step': 'sentence_generation', 'message': str(e)}
        job.save()
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=min(2 ** self.request.retries, 600))


@shared_task(bind=True, max_retries=2)
def audio_generation_task(self, job_id: str):
    """
    Task 2: Generate audio from sentences
    
    Args:
        job_id: Job ID
        
    Returns:
        Success message or error
    """
    try:
        job = Job.objects.get(job_id=job_id)
        
        # Verify previous step completed
        if job.status != 'SENTENCE_GENERATED':
            raise Exception(f"Cannot generate audio - job status is {job.status}, expected SENTENCE_GENERATED")
        
        job.status = 'PROCESSING_AUDIO'
        job.current_step = 'Generating audio'
        job.audio_generation_started_at = timezone.now()
        job.save()
        
        # Parse config
        config, config_issues = Config.create_obj_from_dict(job.payload, require_audio_config=True)
        if config_issues or not config:
            raise ValueError(f"Invalid config: {config_issues}")
        
        # Call audio generation pipeline
        manifest_path, audio_count, err = generate_audio_pipeline(config)
        if err:
            raise Exception(f"Audio generation failed: {err}")
        
        # Update job
        job.status = 'AUDIO_GENERATED'
        job.current_step = 'Audio ready'
        job.progress_percentage = 40
        job.audio_manifest_path = manifest_path
        job.audio_generation_completed_at = timezone.now()
        job.step_details = {
            'audio_files_generated': audio_count,
            'manifest_path': manifest_path,
            'message': f'Successfully generated {audio_count} audio files'
        }
        job.save()
        
        return f"Generated {audio_count} audio files"
        
    except Job.DoesNotExist:
        return f"Job {job_id} not found"
    except Exception as e:
        job.status = 'FAILED'
        job.error = {'step': 'audio_generation', 'message': str(e)}
        job.save()
        
        raise self.retry(exc=e, countdown=min(2 ** self.request.retries, 600))


@shared_task(bind=True, max_retries=2)
def audio_verification_task(self, job_id: str):
    """
    Task 3: Verify audio quality
    
    Args:
        job_id: Job ID
        
    Returns:
        Success message or error
    """
    try:
        job = Job.objects.get(job_id=job_id)
        
        # Verify previous step completed
        if job.status != 'AUDIO_GENERATED':
            raise Exception(f"Cannot verify audio - job status is {job.status}, expected AUDIO_GENERATED")
        
        job.status = 'VERIFYING_AUDIO'
        job.current_step = 'Verifying audio quality'
        job.audio_verification_started_at = timezone.now()
        job.save()
        
        # Parse config
        config, config_issues = Config.create_obj_from_dict(job.payload, require_audio_config=True)
        if config_issues or not config:
            raise ValueError(f"Invalid config: {config_issues}")
        
        # Call audio verification pipeline
        good_count, bad_count, err = verify_audio_pipeline(config)
        if err:
            raise Exception(f"Audio verification failed: {err}")
        
        # Update job
        job.status = 'AUDIO_VERIFIED'
        job.current_step = 'Audio verified'
        job.progress_percentage = 60
        job.audio_verification_completed_at = timezone.now()
        job.step_details = {
            'good_audio_count': good_count,
            'bad_audio_count': bad_count,
            'message': f'Verified audio - {good_count} good, {bad_count} bad'
        }
        job.save()
        
        return f"Verified audio: {good_count} good, {bad_count} bad"
        
    except Job.DoesNotExist:
        return f"Job {job_id} not found"
    except Exception as e:
        job.status = 'FAILED'
        job.error = {'step': 'audio_verification', 'message': str(e)}
        job.save()
        
        raise self.retry(exc=e, countdown=min(2 ** self.request.retries, 600))


@shared_task(bind=True, max_retries=1)
def audio_evaluation_task(self, job_id: str, max_attempts: int = 3):
    """
    Task 4: Evaluate audio and assemble final dataset
    Loops until target duration is reached
    
    Args:
        job_id: Job ID
        max_attempts: Maximum generation attempts
        
    Returns:
        Success message or error
    """
    try:
        job = Job.objects.get(job_id=job_id)
        
        # Verify previous step completed
        if job.status != 'AUDIO_VERIFIED':
            raise Exception(f"Cannot evaluate audio - job status is {job.status}, expected AUDIO_VERIFIED")
        
        job.current_step = 'Evaluating dataset'
        job.save()
        
        # Parse config
        config, config_issues = Config.create_obj_from_dict(job.payload, require_audio_config=True)
        if config_issues or not config:
            raise ValueError(f"Invalid config: {config_issues}")
        
        # Call evaluation pipeline (may retry internally)
        dataset_path, total_duration, err = evaluate_audio_pipeline(config, max_attempts)
        if err:
            raise Exception(f"Audio evaluation failed: {err}")
        
        # Update job to COMPLETED
        job.status = 'COMPLETED'
        job.current_step = 'Generation complete'
        job.progress_percentage = 100
        job.dataset_manifest_path = dataset_path
        job.result = {
            'dataset_path': dataset_path,
            'total_duration_hours': round(total_duration, 2),
            'target_duration_hours': config.size,
            'message': f'Dataset ready - {total_duration:.2f} hours of audio'
        }
        job.save()
        
        return f"Dataset completed - {total_duration:.2f} hours of audio"
        
    except Job.DoesNotExist:
        return f"Job {job_id} not found"
    except Exception as e:
        job.status = 'FAILED'
        job.error = {'step': 'audio_evaluation', 'message': str(e)}
        job.save()
        
        raise self.retry(exc=e, countdown=min(2 ** self.request.retries, 600))


@shared_task(bind=True)
def main_orchestrator_task(self, job_id: str):
    """
    Main orchestrator task that chains all pipeline steps
    Executes: sentences → audio → verification → evaluation
    
    Args:
        job_id: Job ID to process
        
    Returns:
        Final result message
    """
    try:
        job = Job.objects.get(job_id=job_id)
        job.progress_percentage = 0
        job.current_step = 'Pipeline starting'
        job.save()
        
        # Chain tasks: each calls the next on success
        # Step 1: Generate sentences
        result1 = sentence_generation_task.apply_async(args=[job_id])
        result1.get(timeout=3600)  # Wait up to 1 hour
        
        # Step 2: Generate audio
        result2 = audio_generation_task.apply_async(args=[job_id])
        result2.get(timeout=7200)  # Wait up to 2 hours
        
        # Step 3: Verify audio
        result3 = audio_verification_task.apply_async(args=[job_id])
        result3.get(timeout=3600)  # Wait up to 1 hour
        
        # Step 4: Evaluate and complete
        result4 = audio_evaluation_task.apply_async(args=[job_id])
        result4.get(timeout=3600)  # Wait up to 1 hour
        
        job.refresh_from_db()
        return f"Dataset generation complete - {job.job_id}"
        
    except Job.DoesNotExist:
        return f"Job {job_id} not found"
    except Exception as e:
        job = Job.objects.get(job_id=job_id)
        job.status = 'FAILED'
        job.error = {'step': 'orchestrator', 'message': str(e)}
        job.save()
        
        raise
