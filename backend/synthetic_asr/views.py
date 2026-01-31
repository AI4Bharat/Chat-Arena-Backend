from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated

from user.authentication import FirebaseAuthentication, AnonymousTokenAuthentication

import json
import os
import http.client
from urllib.parse import urlparse

from .models import Job
from .engine import (
    sample_sub_domain_handler,
    sample_topic_and_persona_handler,
    sample_scenario_handler,
    sample_sentence_handler,
)
from .tasks import main_orchestrator_task
import time
import random


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return {}


def _error(message: str, status: int = 400):
    return HttpResponse(message, status=status, content_type='text/plain')


def _validate_config(config_dict: dict) -> str:
    """Validate that required config fields exist. Returns error message or empty string if valid."""
    sentence = config_dict.get('sentence', {})
    category = sentence.get('category', '').strip()
    
    if not category:
        return 'category is required'
    
    return ''


def _ensure_numeric_job_id(config_dict: dict) -> str:
    """
    TEMPORARY FOR DEMO: ensure job_id is numeric for downstream services
    that expect an integer job_id.
    """
    job_id = str(config_dict.get('job_id') or '').strip()
    if job_id.isdigit():
        return job_id
    numeric_job_id = str(int(time.time() * 1000) + random.randint(0, 999))
    config_dict['job_id'] = numeric_job_id
    return numeric_job_id


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_sub_domain(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 422)
    
    # Validate required fields
    validation_err = _validate_config(config_dict)
    if validation_err:
        return _error(validation_err, 422)
    
    _ensure_numeric_job_id(config_dict)
    result, err = sample_sub_domain_handler(config_dict, body)
    if err:
        # Return the actual error for easier debugging
        return _error(err, 500)
    return JsonResponse(result, status=200, safe=False)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_topic_and_persona(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 422)
    _ensure_numeric_job_id(config_dict)
    prompt_config = body.get('prompt_config', {})
    if not prompt_config:
        return _error('Prompt config was not send or is empty', 422)

    result, err = sample_topic_and_persona_handler(config_dict, prompt_config)
    if err:
        return _error(err, 500)
    return JsonResponse(result, status=200, safe=False)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_scenario(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 422)
    _ensure_numeric_job_id(config_dict)
    prompt_config = body.get('prompt_config', {})
    if not prompt_config:
        return _error('Prompt config was not send or is empty', 422)

    result, err = sample_scenario_handler(config_dict, prompt_config)
    if err:
        return _error(err, 500)
    return JsonResponse(result, status=200, safe=False)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_sentence(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 422)
    _ensure_numeric_job_id(config_dict)
    prompt_config = body.get('prompt_config', {})
    if not prompt_config:
        return _error('Prompt config was not send or is empty', 422)

    sentences, err = sample_sentence_handler(config_dict, prompt_config)
    if err:
        return _error(err, 500)

    # Frontend expects an object with { sentences: { sentence_0: "…", ... } }
    sentences_obj = {f'sentence_{i}': s for i, s in enumerate(sentences)}
    return JsonResponse({'sentences': sentences_obj}, status=200)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def create_dataset_job(request):
    # Block anonymous users explicitly
    try:
        if getattr(request.user, 'is_anonymous', False):
            return _error('Sign in required to create dataset jobs.', 403)
    except Exception:
        pass
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 422)

    job_id = _ensure_numeric_job_id(config_dict)

    # Store job in Django DB
    try:
        Job.objects.create(
            job_id=job_id,
            payload=config_dict,
            status='SUBMITTED',
            created_by=getattr(request, 'user', None)
        )
    except Exception as e:
        return _error(f'Server error occured, {e}', 405)

    # Trigger async pipeline execution (best-effort). If queue is down, keep the job and return 200.
    try:
        main_orchestrator_task.delay(job_id)
    except Exception as e:
        # Update job with failure info but still return job_id so UI can show status
        try:
            job = Job.objects.get(job_id=job_id)
            job.status = 'FAILED'
            job.error = {'message': 'Failed to enqueue task', 'details': str(e)}
            job.current_step = 'QUEUE_ENQUEUE'
            job.step_details = {**(job.step_details or {}), 'enqueue_error': str(e)}
            job.save(update_fields=['status', 'error', 'current_step', 'step_details', 'updated_at'])
        except Exception:
            pass
        # Do NOT 405 the client; allow UI to move forward and show failure state
        return HttpResponse(job_id, status=200, content_type='text/plain')

    return HttpResponse(job_id, status=200, content_type='text/plain')


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def job_status(request, job_id: str):
    if not job_id:
        return _error('job_id cannot be empty', 405)
    try:
        job = Job.objects.get(job_id=job_id)
        # Optional: ensure only owner can see status
        try:
            if job.created_by and getattr(request, 'user', None) and job.created_by != request.user:
                return _error('Forbidden', 403)
        except Exception:
            pass
        # Return detailed JSON with progress information
        response_data = {
            'job_id': job.job_id,
            'status': job.status,
            'progress_percentage': job.progress_percentage,
            'current_step': job.current_step,
            'step_details': job.step_details,
            'error': job.error,
            'result': job.result,
        }
        return JsonResponse(response_data, status=200)
    except Job.DoesNotExist:
        return _error('There is no job with this id', 405)


@api_view(["GET", "OPTIONS"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def list_jobs(request):
    """
    List all jobs with pagination and filtering.
    Query params:
    - page: Page number (default: 1)
    - limit: Items per page (default: 10)
    - status: Filter by status (optional)
    - language: Filter by language from payload (optional)
    """
    try:
        # Get pagination params
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 10))
        offset = (page - 1) * limit
        
        # Get filter params
        status_filter = request.GET.get('status', '')
        language_filter = request.GET.get('language', '')
        
        # Build query
        # Only jobs created by current user
        query = Job.objects.filter(created_by=request.user)
        
        # Apply status filter (accept lowercase aliases from UI)
        if status_filter and status_filter != 'all':
            sf = str(status_filter).strip().upper()
            if sf == 'PROCESSING':
                query = query.filter(status__in=['SUBMITTED', 'SENTENCE_GENERATED', 'AUDIO_GENERATED', 'AUDIO_VERIFIED'])
            else:
                query = query.filter(status=sf)
        
        # Get total count before pagination
        total_count = query.count()
        
        # Apply pagination
        jobs = query.order_by('-created_at')[offset:offset + limit]
        
        # Build response items
        items = []
        for job in jobs:
            # Extract language and size from payload
            payload = job.payload or {}
            # In create_dataset_job we store the config dict directly in payload.
            # Some older jobs might wrap it as {'config': {...}}; support both.
            if isinstance(payload, dict) and 'language' in payload:
                config = payload
            else:
                config = payload.get('config', payload if isinstance(payload, dict) else {})
            
            item = {
                'jobId': job.job_id,
                'language': config.get('language') or payload.get('language') or 'Unknown',
                'size': config.get('size') or payload.get('size') or 0,
                'status': job.status,
                'progress': job.progress_percentage,
                'currentStage': job.current_step or 'Pending',
                'createdAt': job.created_at.isoformat() if job.created_at else None,
                'completedAt': job.updated_at.isoformat() if job.status == 'COMPLETED' and job.updated_at else None,
                'errorMessage': job.error.get('message', '') if job.error else None,
            }
            
            # Apply language filter
            if language_filter and language_filter != 'all':
                if item['language'] != language_filter:
                    continue
            
            items.append(item)
        
        # Recount after language filter
        filtered_count = len(items)
        
        response_data = {
            'items': items,
            'total': total_count,
            'page': page,
            'limit': limit,
            'hasMore': (offset + limit) < total_count,
        }
        
        return JsonResponse(response_data, status=200)
    
    except Exception as e:
        return _error(f'Failed to fetch jobs: {str(e)}', 400)


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def get_job_dataset(request, job_id: str):
    """
    Proxy endpoint to fetch the generated audio dataset from PAI server (ngrok).
    This bypasses CORS issues by doing server-to-server communication.
    """
    try:
        # Get PAI server URL from environment
        pai_server_url = os.getenv('SYNTHETIC_ASR_PAI_SERVER_URL', '')
        if not pai_server_url:
            return _error('PAI server URL not configured', 500)
        
        parsed_url = urlparse(pai_server_url)
        host = parsed_url.netloc
        scheme = parsed_url.scheme
        
        # Make request to PAI server
        if scheme == 'https':
            conn = http.client.HTTPSConnection(host)
        else:
            conn = http.client.HTTPConnection(host)
        
        headers = {
            'ngrok-skip-browser-warning': 'true'
        }
        
        path = f'/pai/job/{job_id}'
        conn.request('GET', path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        
        if resp.status != 200:
            error_text = data.decode('utf-8')
            return _error(f'PAI server error: {error_text}', resp.status)
        
        # Return the JSON data from PAI server
        return HttpResponse(data, status=200, content_type='application/json')
    
    except Exception as e:
        return _error(f'Error fetching dataset: {str(e)}', 500)


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def get_audio_file(request, audio_id: str):
    """
    Proxy endpoint to fetch individual audio file from PAI server (ngrok).
    Returns the audio file as a response.
    """
    try:
        # Get PAI server URL from environment
        pai_server_url = os.getenv('SYNTHETIC_ASR_PAI_SERVER_URL', '')
        if not pai_server_url:
            return _error('PAI server URL not configured', 500)
        
        parsed_url = urlparse(pai_server_url)
        host = parsed_url.netloc
        scheme = parsed_url.scheme
        
        # Make request to PAI server
        if scheme == 'https':
            conn = http.client.HTTPSConnection(host)
        else:
            conn = http.client.HTTPConnection(host)
        
        headers = {
            'ngrok-skip-browser-warning': 'true'
        }
        
        path = f'/pai/audio/{audio_id}'
        conn.request('GET', path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        
        if resp.status != 200:
            error_text = data.decode('utf-8') if data else 'Audio not found'
            return _error(f'PAI server error: {error_text}', resp.status)
        
        # Return the audio file
        return HttpResponse(data, status=200, content_type='audio/wav')
    
    except Exception as e:
        return _error(f'Error fetching audio: {str(e)}', 500)
