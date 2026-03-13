from django.http import JsonResponse, HttpResponse

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated

from user.authentication import FirebaseAuthentication, AnonymousTokenAuthentication

import json
import os
import http.client
import uuid
from urllib.parse import urlparse

from user.models import User
from user.services import UserService
from .models import Job
from .engine import (
    sample_sub_domain_handler,
    sample_topic_and_persona_handler,
    sample_scenario_handler,
    sample_sentence_handler,
)
import time
import os
import random
from urllib.parse import urlparse
from .utils import http_utils
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.http import StreamingHttpResponse


def job_status_stream(request):
    """
    SSE endpoint that streams job status updates to the frontend.
    """
    print(f"DEBUG: job_status_stream called for user: {request.user}")
    from django.http import StreamingHttpResponse
    user = request.user
    
    # SSE EventSource doesn't support headers, so we check query params for tokens
    if not user or user.is_anonymous:
        token = request.GET.get('token')
        anonymous_token = request.GET.get('anonymous_token')
        
        if token:
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(token)
                user_id = validated_token.get('user_id')
                if user_id:
                    user = User.objects.get(id=user_id)
            except Exception:
                # Try Firebase if JWT fails
                try:
                    firebase_user = UserService.verify_google_token_with_pyrebase(token)
                    if firebase_user:
                        user = User.objects.get(firebase_uid=firebase_user['localId'])
                except Exception:
                    pass
        
        if (not user or user.is_anonymous) and anonymous_token:
            user = User.objects.filter(is_anonymous=True, preferences__anonymous_token=anonymous_token).first()

    if not user or user.is_anonymous:
        # Note: EventSource might not handle 401 well, but standard for SSE
        return HttpResponse("Unauthorized", status=401)

    print(f"DEBUG: Authenticated user for SSE stream: {user.email}")

    def event_stream():
        last_known_state = {}
        first_run = True
        
        while True:
            try:
                # 1. Heartbeat Ping
                hb_data = json.dumps({
                    'type': 'ping', 
                    'time': time.time()
                })
                yield f"data: {hb_data}\n\n"

                # 2. Get jobs
                # We include COMPLETED/FAILED jobs so that the "final" state update can be sent.
                # The state tracking logic below will ensure we don't spam redundant updates for finished jobs.
                query = Job.objects.filter(created_by=user).order_by('-created_at').exclude(status='DRAFT')
                
                active_jobs = list(query)

                all_current_jobs = []
                for job in active_jobs:
                    updated_job = _sync_job_status_from_pai(job)
                    
                    # Format
                    payload = updated_job.payload or {}
                    config = payload if (isinstance(payload, dict) and 'language' in payload) else payload.get('config', payload if isinstance(payload, dict) else {})
                    sentence_config = config.get('sentence', {})

                    job_data = {
                        'jobId': updated_job.job_id,
                        'language': config.get('language') or payload.get('language') or 'Unknown',
                        'size': config.get('size') or payload.get('size') or 0,
                        'status': updated_job.status,
                        'progress': updated_job.progress_percentage,
                        'currentStage': updated_job.current_step or 'Pending',
                        'createdAt': updated_job.created_at.isoformat() if updated_job.created_at else None,
                        'completedAt': updated_job.updated_at.isoformat() if updated_job.status == 'COMPLETED' and updated_job.updated_at else None,
                        'category': sentence_config.get('category') or config.get('category') or '',
                        'generationAttempts': updated_job.generation_attempts or 0,
                    }
                    all_current_jobs.append(job_data)

                # 3. YIELD UPDATES (Differential)
                to_send = []
                for job_data in all_current_jobs:
                    job_id = job_data['jobId']
                    last_state = last_known_state.get(job_id)
                    # Send if it's the first time we see the job OR if status/progress changed
                    if (first_run or last_state is None or 
                        job_data['status'] != last_state['status'] or 
                        job_data['progress'] != last_state['progress']):
                        to_send.append(job_data)
                        last_known_state[job_id] = {'status': job_data['status'], 'progress': job_data['progress']}

                if to_send:
                    data = json.dumps({
                        'type': 'jobs_update', 
                        'jobs': to_send, 
                        'server_time': time.time()
                    })
                    # Use padding to bypass potential proxy buffers
                    padding = ":" + (" " * 2048) + "\n"
                    yield f"data: {data}\n{padding}\n\n"
                
                first_run = False
            except Exception as e:
                data = json.dumps({'type': 'error', 'message': str(e)})
                yield f"data: {data}\n\n"
            
            time.sleep(5)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache, no-transform'
    response['X-Accel-Buffering'] = 'no'
    return response


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


def _submit_to_pai(job):
    """
    Submit a job to the PAI server synchronously.
    Returns (pai_job_id, error_message). On success error_message is None.
    """
    pai_server_url = os.getenv('SYNTHETIC_ASR_PAI_SERVER_URL')
    if not pai_server_url:
        return None, 'SYNTHETIC_ASR_PAI_SERVER_URL not configured'

    parsed_url = urlparse(pai_server_url)
    host = parsed_url.netloc
    scheme = parsed_url.scheme or 'https'
    is_https = scheme == 'https'

    headers = {'Content-Type': 'application/json'}
    payload = {'config': job.payload}

    if is_https:
        result, err = http_utils.make_post_request(host, '/pai/create', headers, payload)
    else:
        result, err = http_utils.make_local_post_request(host, '/pai/create', headers, payload, port=80)

    if err:
        return None, f'Failed to submit to PAI server: {err}'

    pai_job_id = str(result) if result else None
    if not pai_job_id:
        return None, 'PAI server did not return job ID'

    return pai_job_id, None


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
    # Ensure is_sample is always False for final jobs
    config_dict['is_sample'] = False
    is_draft = body.get('is_draft', False)

    # Store job in Django DB
    try:
        job, created = Job.objects.get_or_create(
            job_id=job_id,
            defaults={
                'payload': config_dict,
                'status': 'DRAFT' if is_draft else 'SUBMITTED',
                'created_by': getattr(request, 'user', None)
            }
        )
        if not created:
            job.payload = config_dict
            job.status = 'DRAFT' if is_draft else 'SUBMITTED'
            job.save(update_fields=['payload', 'status', 'updated_at'])
    except Exception as e:
        return _error(f'Server error occured, {e}', 405)

    if is_draft:
        wizard_stage = body.get('wizard_stage', 1)
        wizard_form_data = body.get('wizard_form_data', None)
        if wizard_form_data:
            config_dict['_wizard_form_data'] = wizard_form_data
            job.payload = config_dict
        job.current_step = 'Saved as Draft'
        job.step_details = {**(job.step_details or {}), 'wizard_stage': wizard_stage}
        job.save(update_fields=['payload', 'current_step', 'step_details', 'updated_at'])
        return HttpResponse(job_id, status=200, content_type='text/plain')

    # Submit to PAI server synchronously
    job.status = 'SUBMITTING'
    job.current_step = 'Submitting to PAI server'
    job.save(update_fields=['status', 'current_step', 'updated_at'])

    pai_job_id, err = _submit_to_pai(job)
    if err:
        job.status = 'FAILED'
        job.error = {'step': 'pai_submit', 'message': err}
        job.current_step = 'PAI submission failed'
        job.save(update_fields=['status', 'error', 'current_step', 'updated_at'])
        return HttpResponse(job_id, status=200, content_type='text/plain')

    job.status = 'SUBMITTED'
    job.current_step = 'SUBMITTED'
    job.step_details = {'pai_job_id': pai_job_id}
    job.save(update_fields=['status', 'current_step', 'step_details', 'updated_at'])

    return HttpResponse(job_id, status=200, content_type='text/plain')


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def resubmit_job(request, job_id: str):
    """
    Re-submit a job that is FAILED.
    Resets the job state and submits to PAI server directly.
    """
    try:
        if getattr(request.user, 'is_anonymous', False):
            return _error('Sign in required.', 403)
    except Exception:
        pass

    try:
        job = Job.objects.get(job_id=job_id)
    except Job.DoesNotExist:
        return _error('Job not found.', 404)

    # Only the owner can resubmit
    try:
        if job.created_by and getattr(request, 'user', None) and job.created_by != request.user:
            return _error('Forbidden', 403)
    except Exception:
        pass

    # Only allow resubmit for failed jobs
    allowed_statuses = ['SUBMITTED', 'FAILED', 'SUBMITTING']
    if job.status not in allowed_statuses:
        return _error(f'Job is currently {job.status} and cannot be resubmitted.', 409)

    # Generate a new job ID for the PAI side to avoid 500 Internal Server Error conflicts
    from time import time
    new_pai_job_id = str(int(time() * 1000))
    
    # Update the payload with the new ID for the PAI server
    new_payload = dict(job.payload) if job.payload else {}
    new_payload['job_id'] = new_pai_job_id
    job.payload = new_payload

    # Reset job state
    job.status = 'SUBMITTING'
    job.error = None
    job.progress_percentage = 0
    job.current_step = 'Resubmitted by user'
    job.step_details = {**(job.step_details or {}), 'resubmitted': True, 'old_pai_job_id': job.step_details.get('pai_job_id')}
    job.generation_attempts = (job.generation_attempts or 0) + 1
    job.save()

    # Submit to PAI directly
    pai_job_id, err = _submit_to_pai(job)
    if err:
        job.status = 'FAILED'
        job.error = {'step': 'pai_submit', 'message': err}
        job.save(update_fields=['status', 'error', 'updated_at'])
        return JsonResponse({'message': 'Job resubmitted but failed to reach PAI', 'job_id': job_id}, status=200)

    job.status = 'SUBMITTED'
    job.current_step = 'SUBMITTED'
    job.step_details = {**(job.step_details or {}), 'pai_job_id': pai_job_id}
    job.save(update_fields=['status', 'current_step', 'step_details', 'updated_at'])

    return HttpResponse(job_id, status=200, content_type='text/plain')


def _sync_job_status_from_pai(job):
    """
    Internal helper to sync a job's status from the PAI server if it's currently processing.
    """
    if job.status not in ['SUBMITTING', 'SUBMITTED', 'PROCESSING', 'SENTENCE_GENERATED', 'AUDIO_GENERATED', 'AUDIO_VERIFIED', 'DATASET_GENERATED']:
        return job

    pai_job_id = job.step_details.get('pai_job_id') if job.step_details else None
    if not pai_job_id:
        return job

    try:
        # Get PAI server URL
        pai_server_url = os.getenv('SYNTHETIC_ASR_PAI_SERVER_URL')
        if not pai_server_url:
            return job

        parsed_url = urlparse(pai_server_url)
        host = parsed_url.netloc
        scheme = parsed_url.scheme or 'https'
        is_https = scheme == 'https'

        # Fetch status from PAI server
        if is_https:
            conn = http.client.HTTPSConnection(host)
        else:
            conn = http.client.HTTPConnection(host)
            
        conn.request('GET', f'/pai/status/{pai_job_id}', headers={})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()

        if resp.status == 200:
            decoded_data = data.decode('utf-8').strip()
            try:
                pai_status_data = json.loads(decoded_data)
                print(f"PAI status data for {pai_job_id}: {pai_status_data}")
                pai_status_raw = pai_status_data.get('status')
                pai_status = str(pai_status_raw).upper() if pai_status_raw else None
            except json.JSONDecodeError:
                # Fallback: the endpoint might be returning plain text e.g., "SUBMITTED"
                pai_status = decoded_data.upper() if decoded_data else None
        else:
            print(f"Failed to fetch status for {pai_job_id}: {resp.status} {data}")
            return job

        # Update job based on PAI status
        status_changed = False
        if pai_status == 'ACCEPTED' and job.status != 'PROCESSING':
            job.status = 'PROCESSING'
            job.current_step = 'STARTED'
            job.progress_percentage = 10
            status_changed = True
        elif pai_status == 'SENTENCE_GENERATED' and job.status != 'SENTENCE_GENERATED':
            job.status = 'SENTENCE_GENERATED'
            job.current_step = 'GENERATED SENTENCES'
            job.progress_percentage = 25
            status_changed = True
        elif pai_status == 'AUDIO_GENERATED' and job.status != 'AUDIO_GENERATED':
            job.status = 'AUDIO_GENERATED'
            job.current_step = 'GENERATING AUDIO'
            job.progress_percentage = 50
            status_changed = True
        elif pai_status == 'AUDIO_VERIFIED' and job.status != 'AUDIO_VERIFIED':
            job.status = 'AUDIO_VERIFIED'
            job.current_step = 'VERIFYING AUDIO'
            job.progress_percentage = 75
            status_changed = True
        elif pai_status == 'DATASET_GENERATED' and job.status != 'DATASET_GENERATED':
            job.status = 'DATASET_GENERATED'
            job.current_step = 'FINISHING UP'
            job.progress_percentage = 90
            status_changed = True
        elif pai_status in ['DATASET_UPLOADED', 'COMPLETED'] and job.status != 'COMPLETED':
            job.status = 'COMPLETED'
            job.current_step = 'DATASET READY'
            job.progress_percentage = 100
            job.result = {'pai_job_id': pai_job_id, 'status': 'completed'}
            job.save()
            # Send email notification to job creator
            try:
                _send_dataset_ready_email(job)
            except Exception:
                pass
            status_changed = False # Already saved
        elif pai_status == 'FAILED' and job.status != 'FAILED':
            job.status = 'FAILED'
            job.error = {'message': 'PAI server reported failure'}
            status_changed = True

        if status_changed:
            job.save()

    except Exception as e:
        print(f"Error fetching status from PAI server for {job.job_id}: {e}")

    return job


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def job_status(request, job_id: str):
    """
    Get job status. Fetches latest status from PAI server on-demand and updates DB.
    """
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

        # Fetch latest status from PAI server
        job = _sync_job_status_from_pai(job)

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
                query = query.filter(status__in=['SUBMITTED', 'PROCESSING', 'SENTENCE_GENERATED', 'AUDIO_GENERATED', 'AUDIO_VERIFIED', 'DATASET_GENERATED'])
            else:
                query = query.filter(status=sf)

        # Get total count before pagination
        total_count = query.count()

        # Apply pagination
        jobs = query.order_by('-created_at')[offset:offset + limit]

        # Build response items
        items = []
        for job in jobs:
            # First, if the job is processing, sync its status from the PAI server
            if job.status in ['SUBMITTING', 'SUBMITTED', 'PROCESSING', 'SENTENCE_GENERATED', 'AUDIO_GENERATED', 'AUDIO_VERIFIED', 'DATASET_GENERATED']:
                job = _sync_job_status_from_pai(job)
            # Extract language and size from payload
            payload = job.payload or {}
            # In create_dataset_job we store the config dict directly in payload.
            # Some older jobs might wrap it as {'config': {...}}; support both.
            if isinstance(payload, dict) and 'language' in payload:
                config = payload
            else:
                config = payload.get('config', payload if isinstance(payload, dict) else {})
            
            sentence_config = config.get('sentence', {})
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
                'category': sentence_config.get('category') or config.get('category') or '',
                'generationAttempts': job.generation_attempts or 0,
            }
            
            # Apply language filter
            if language_filter and language_filter != 'all':
                if item['language'] != language_filter:
                    continue
            # Include full payload for DRAFT jobs so frontend can pre-fill the edit form
            if job.status == 'DRAFT':
                item['payload'] = payload
                item['wizardStage'] = (job.step_details or {}).get('wizard_stage', 1)

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


@api_view(["DELETE"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def delete_draft_job(request, job_id: str):
    """
    Delete a job that is in DRAFT status.
    Only the owner can delete their own drafts.
    """
    try:
        if getattr(request.user, 'is_anonymous', False):
            return _error('Sign in required.', 403)
    except Exception:
        pass

    try:
        job = Job.objects.get(job_id=job_id)
    except Job.DoesNotExist:
        return _error('Job not found.', 404)

    # Only the owner can delete
    try:
        if job.created_by and getattr(request, 'user', None) and job.created_by != request.user:
            return _error('Forbidden', 403)
    except Exception:
        pass

    if job.status != 'DRAFT':
        return _error('Only draft jobs can be deleted.', 409)

    job.delete()
    return JsonResponse({'status': 'deleted', 'jobId': job_id}, status=200)


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def get_job_dataset(request, job_id: str):
    """
    Proxy endpoint to fetch the generated audio dataset from PAI server.
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
        
        headers = {}
        
        # Get limit from query params, default to 50
        limit = request.GET.get('limit', '50')
        path = f'/pai/job/{job_id}?limit={limit}'
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
    Proxy endpoint to fetch individual audio file from PAI server.
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
        
        headers = {}
        
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


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def get_job_metrics(request, job_id: str):
    """
    Compute dataset metrics from PAI audio list.
    PAI has no dedicated /metrics endpoint, so we fetch all audio items and
    aggregate: total_audio, vocabulary_size, total_tokens, total_duration.
    """
    try:
        pai_server_url = os.getenv('SYNTHETIC_ASR_PAI_SERVER_URL', '')
        if not pai_server_url:
            return _error('PAI server URL not configured', 500)

        parsed_url = urlparse(pai_server_url)
        host = parsed_url.netloc
        scheme = parsed_url.scheme

        if scheme == 'https':
            conn = http.client.HTTPSConnection(host)
        else:
            conn = http.client.HTTPConnection(host)

        # Fetch all audio items (PAI requires a limit param)
        path = f'/pai/job/{job_id}?limit=100000'
        conn.request('GET', path, headers={})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()

        if resp.status != 200:
            error_text = data.decode('utf-8') if data else 'Job not found'
            return _error(f'PAI server error: {error_text}', resp.status)

        items = json.loads(data.decode('utf-8'))
        if not isinstance(items, list):
            items = []

        # Aggregate metrics
        total_audio = len(items)
        total_duration_secs = sum(float(item.get('duration', 0) or 0) for item in items)
        total_duration_hrs = round(total_duration_secs / 3600, 2)

        all_words = []
        for item in items:
            sentence = item.get('sentence', '') or ''
            words = sentence.split()
            all_words.extend(words)

        total_tokens = len(all_words)
        vocabulary_size = len(set(all_words))

        metrics = {
            'total_audio': total_audio,
            'vocabulary_size': vocabulary_size,
            'total_tokens': total_tokens,
            'total_duration': total_duration_hrs,
        }

        return JsonResponse(metrics, status=200)

    except Exception as e:
        return _error(f'Error computing metrics: {str(e)}', 500)


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def get_download_link(request, job_id: str):
    """
    Proxy endpoint to get download link for a job's dataset from PAI server.
    Returns download URL or file.
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
        
        headers = {}
        
        path = f'/pai/download/{job_id}'
        conn.request('GET', path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        
        if resp.status != 200:
            error_text = data.decode('utf-8') if data else 'Download link not found'
            return _error(f'PAI server error: {error_text}', resp.status)

        # PAI returns a plain-text signed URL. Normalise to JSON so the
        # frontend can always do response.json() and read r.download_url.
        raw = data.decode('utf-8').strip().strip('"')
        try:
            parsed = json.loads(raw)
            # Already JSON — ensure it has a download_url key
            if 'download_url' not in parsed:
                parsed['download_url'] = parsed.get('url', raw)
            return JsonResponse(parsed, status=200)
        except (json.JSONDecodeError, TypeError):
            # Plain-text URL — wrap it
            return JsonResponse({'download_url': raw}, status=200)
    
    except Exception as e:
        return _error(f'Error fetching download link: {str(e)}', 500)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def report_failed_job(request, job_id: str):
    """Report a failed job — sends email notification to admins."""
    try:
        job = Job.objects.get(job_id=job_id)
    except Job.DoesNotExist:
        return _error('Job not found.', 404)

    body = _json_body(request)
    message = body.get('message', '')

    _send_failure_email(job, message, getattr(request, 'user', None))

    return JsonResponse({'message': 'Report submitted successfully'}, status=200)


def _send_failure_email(job, message, user):
    """Send failure report email notification to admins."""
    
    recipients = getattr(django_settings, 'FAILURE_REPORT_RECIPIENTS', [])
    if not recipients:
        return

    subject = f'[Arena] Job {job.job_id} Failure Report'
    body = (
        f'Job ID: {job.job_id}\n'
        f'Status: {job.status}\n'
        f'Language: {job.payload.get("language", "N/A")}\n'
        f'Reported by: {user}\n'
        f'Message: {message or "No message provided"}\n'
        f'Error: {job.error}\n'
    )

    try:
        send_mail(subject, body, None, recipients, fail_silently=True)
    except Exception as e:
        print(f'Failed to send failure email: {e}')


def _send_dataset_ready_email(job):
    """Send email to the job creator when the dataset is ready."""
    
    if not job.created_by or not getattr(job.created_by, 'email', None):
        return

    subject = f'[Arena] Your dataset {job.job_id} is ready!'
    body = (
        f'Hi {job.created_by.username or job.created_by.email},\n\n'
        f'Your synthetic ASR dataset is ready for download.\n\n'
        f'Job ID: {job.job_id}\n'
        f'Language: {job.payload.get("language", "N/A")}\n'
        f'Status: {job.status}\n\n'
        f'You can download it from the Arena dashboard.\n\n'
        f'— Arena Team'
    )

    try:
        send_mail(
            subject, body,
            getattr(django_settings, 'DEFAULT_FROM_EMAIL', None),
            [job.created_by.email],
            fail_silently=True,
        )
    except Exception as e:
        print(f'Failed to send dataset ready email: {e}')

