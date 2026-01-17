from rest_framework import status, permissions, views
from rest_framework.response import Response
from google.cloud import storage
from django.conf import settings
import json
import uuid
from datetime import datetime
import os


class FrontendErrorLogView(views.APIView):
    """Accept frontend error logs and persist them into GCS under
    bucket: indic-arena-storage
    prefix: error-logs-json/
    daily files named: DD-MM-YY.log (newline-delimited JSON)
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data if isinstance(request.data, dict) else {}

        # Enrich with server-side fields
        user_email = None
        try:
            if hasattr(request, 'user') and request.user and request.user.is_authenticated:
                user_email = getattr(request.user, 'email', None)
        except Exception:
            user_email = None

        if not user_email:
            user_email = data.get('user_email') or data.get('user') or None

        entry = {
            'endpoint': data.get('endpoint'),
            'method': data.get('method'),
            'timestamp': data.get('timestamp') or datetime.utcnow().isoformat() + 'Z',
            'user_email': user_email,
            'status': data.get('status'),
            'error_message': data.get('error_message'),
            'request_body': data.get('request_body'),
            'response_body': data.get('response_body'),
            'tenant': data.get('tenant'),
            'domain': data.get('domain') or request.get_host(),
            'client': data.get('client'),
            'received_at': datetime.utcnow().isoformat() + 'Z',
        }

        try:
            write_log_to_gcs(entry)
        except Exception as e:
            # Return 503 to indicate the logging service failed
            return Response({'detail': 'failed to persist log', 'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({'detail': 'ok'}, status=status.HTTP_201_CREATED)


def _get_storage_client():
    # Let google library pick up credentials from environment; allow an optional
    # service account json path in settings.GOOGLE_APPLICATION_CREDENTIALS or repo
    return storage.Client()


def write_log_to_gcs(entry):
    # Bucket and prefix
    bucket_name = os.environ.get('ERROR_LOG_BUCKET_NAME', 'indic-arena-storage')
    prefix = os.environ.get('ERROR_LOG_PREFIX', 'error-logs-json')

    client = _get_storage_client()
    bucket = client.bucket(bucket_name)

    # Daily file name according to spec: DD-MM-YY.log
    date_str = datetime.utcnow().strftime('%d-%m-%y')
    daily_path = f"{prefix}/{date_str}.log"

    # Prepare a small temporary object for this event
    tmp_name = f"{prefix}/tmp/{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex}.json"
    tmp_blob = bucket.blob(tmp_name)
    line = json.dumps(entry, ensure_ascii=False) + '\n'
    tmp_blob.upload_from_string(line, content_type='application/json')

    daily_blob = bucket.blob(daily_path)

    if not daily_blob.exists():
        # If daily file doesn't exist, simply copy tmp -> daily (acts as create)
        bucket.copy_blob(tmp_blob, bucket, daily_path)
        # delete tmp
        tmp_blob.delete()
        return

    # If daily exists, compose daily + tmp into a new temp daily and overwrite
    compose_tmp_name = f"{prefix}/tmp/{date_str}.compose.{uuid.uuid4().hex}.tmp"
    compose_blob = bucket.blob(compose_tmp_name)

    # Compose: sources must be existing blobs
    # Create the composed object from [daily_blob, tmp_blob]
    compose_blob.compose([daily_blob, tmp_blob])

    # Overwrite the daily file with the composed blob
    bucket.copy_blob(compose_blob, bucket, daily_path)

    # Cleanup
    compose_blob.delete()
    tmp_blob.delete()
