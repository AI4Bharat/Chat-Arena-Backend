from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated

from user.authentication import FirebaseAuthentication, AnonymousTokenAuthentication

import json

from .models import Job
from .engine import (
    sample_sub_domain_handler,
    sample_topic_and_persona_handler,
    sample_scenario_handler,
    sample_sentence_handler,
)
from .tasks import main_orchestrator_task


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return {}


def _error(message: str, status: int = 400):
    return HttpResponse(message, status=status, content_type='text/plain')


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_sub_domain(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 405)
    result, err = sample_sub_domain_handler(config_dict, body)
    if err:
        return _error('Error occured while generating sub-domains', 405)
    return JsonResponse(result, status=200, safe=False)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_topic_and_persona(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 405)
    prompt_config = body.get('prompt_config', {})
    if not prompt_config:
        return _error('Prompt config was not send or is empty', 405)

    result, err = sample_topic_and_persona_handler(config_dict, prompt_config)
    if err:
        return _error(err, 405)
    return JsonResponse(result, status=200, safe=False)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_scenario(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 405)
    prompt_config = body.get('prompt_config', {})
    if not prompt_config:
        return _error('Prompt config was not send or is empty', 405)

    result, err = sample_scenario_handler(config_dict, prompt_config)
    if err:
        return _error(err, 405)
    return JsonResponse(result, status=200, safe=False)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def sample_sentence(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 405)
    prompt_config = body.get('prompt_config', {})
    if not prompt_config:
        return _error('Prompt config was not send or is empty', 405)

    sentences, err = sample_sentence_handler(config_dict, prompt_config)
    if err:
        return _error(err, 405)

    # Frontend expects an object with { sentences: { sentence_0: "…", ... } }
    sentences_obj = {f'sentence_{i}': s for i, s in enumerate(sentences)}
    return JsonResponse({'sentences': sentences_obj}, status=200)


@api_view(["POST"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def create_dataset_job(request):
    body = _json_body(request)
    config_dict = body.get('config', {})
    if not config_dict:
        return _error('Config was not send', 405)

    job_id = str(config_dict.get('job_id') or '')
    if not job_id:
        return _error('Job id is missing', 405)

    # Store job in Django DB
    try:
        Job.objects.create(job_id=job_id, payload=config_dict, status='SUBMITTED')
    except Exception as e:
        return _error(f'Server error occured, {e}', 405)

    # Trigger async pipeline execution
    try:
        main_orchestrator_task.delay(job_id)
    except Exception as e:
        return _error(f'Failed to enqueue task, {e}', 405)

    return HttpResponse(job_id, status=200, content_type='text/plain')


@api_view(["GET"])
@authentication_classes([FirebaseAuthentication, AnonymousTokenAuthentication])
@permission_classes([IsAuthenticated])
def job_status(request, job_id: str):
    if not job_id:
        return _error('job_id cannot be empty', 405)
    try:
        job = Job.objects.get(job_id=job_id)
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

