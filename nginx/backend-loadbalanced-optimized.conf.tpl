# =============================================================================
# OPTIMIZED Load-balanced backend configuration for ${domain}
# =============================================================================
# Key changes from original:
# - Reduced rate limits to sustainable levels
# - Increased health check tolerance
# - Better timeout alignment with Gunicorn
# - Improved buffering for large AI responses
# =============================================================================

access_log /var/log/nginx/${domain}.access.log load_balanced;
error_log /var/log/nginx/${domain}.error.log warn;

# Client configuration - allow large file uploads for audio/documents
client_max_body_size 100M;
client_body_timeout 300s;
client_header_timeout 60s;
client_body_buffer_size 128k;

# -----------------------------------------------------------------------------
# HEALTH CHECK ENDPOINTS
# -----------------------------------------------------------------------------
location /health/ {
    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Short timeouts - health checks should be fast
    proxy_connect_timeout 5s;
    proxy_send_timeout 10s;
    proxy_read_timeout 30s;

    proxy_buffering off;
    access_log off;
}

location ~ ^/(ready|live)/ {
    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_connect_timeout 5s;
    proxy_read_timeout 10s;
    proxy_buffering off;
    access_log off;
}

# -----------------------------------------------------------------------------
# STREAMING ENDPOINTS (SSE for AI responses)
# -----------------------------------------------------------------------------
# These are long-lived connections for AI model streaming
location ~ ^/(messages/(stream|[^/]+/regenerate/?)|chat/stream|models/([^/]+/test/?|compare/?)) {
    # Rate limiting - allow burst for initial connection
    limit_req zone=streaming_limit burst=20 nodelay;
    limit_conn conn_limit 100;

    proxy_pass http://django_streaming;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # Standard headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;

    # CRITICAL: Disable ALL buffering for SSE
    proxy_buffering off;
    proxy_cache off;
    proxy_request_buffering off;
    proxy_set_header X-Accel-Buffering no;
    proxy_set_header Cache-Control no-cache;

    # Long timeouts for AI streaming (match Gunicorn timeout)
    proxy_connect_timeout 60s;
    proxy_send_timeout 330s;  # Slightly longer than Gunicorn 300s
    proxy_read_timeout 330s;

    chunked_transfer_encoding on;

    # Retry on backend failure
    proxy_next_upstream error timeout http_502 http_503 http_504;
    proxy_next_upstream_tries 2;
    proxy_next_upstream_timeout 30s;
}

# -----------------------------------------------------------------------------
# WEBSOCKET ENDPOINTS
# -----------------------------------------------------------------------------
location /ws/ {
    limit_req zone=general_limit burst=50 nodelay;

    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # WebSocket timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 600s;
    proxy_read_timeout 600s;
    proxy_buffering off;
}

# -----------------------------------------------------------------------------
# AUTHENTICATION ENDPOINTS
# -----------------------------------------------------------------------------
location ~ ^/(auth|login|logout|register|api/auth)/ {
    # Strict rate limiting for auth (prevent brute force)
    limit_req zone=auth_limit burst=10 nodelay;
    limit_conn conn_limit 20;

    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;

    # Standard timeouts for auth
    proxy_connect_timeout 10s;
    proxy_send_timeout 30s;
    proxy_read_timeout 30s;

    proxy_buffering on;
    proxy_buffer_size 4k;
    proxy_buffers 8 4k;

    proxy_next_upstream error timeout http_502 http_503;
    proxy_next_upstream_tries 2;
}

# -----------------------------------------------------------------------------
# FILE UPLOAD ENDPOINTS
# -----------------------------------------------------------------------------
location ~ ^/api/(messages/(upload|audio|document)|upload)/ {
    # Allow larger uploads, moderate rate limit
    limit_req zone=general_limit burst=10 nodelay;

    client_max_body_size 100M;
    client_body_timeout 300s;

    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Longer timeouts for uploads
    proxy_connect_timeout 30s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    # Buffer uploads in memory for better performance
    proxy_request_buffering on;
    proxy_buffering on;
    proxy_buffer_size 128k;
    proxy_buffers 16 128k;
}

# -----------------------------------------------------------------------------
# STATIC FILES
# -----------------------------------------------------------------------------
location /static/ {
    alias /usr/src/backend/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
    add_header X-Content-Type-Options nosniff;
    access_log off;

    # Gzip static files
    gzip_static on;
}

# -----------------------------------------------------------------------------
# API DOCUMENTATION (Swagger/ReDoc)
# -----------------------------------------------------------------------------
location ~ ^/(swagger|redoc|api/docs)/ {
    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Cache API docs
    proxy_cache api_cache;
    proxy_cache_valid 200 10m;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
    add_header X-Cache-Status $upstream_cache_status;
}

# -----------------------------------------------------------------------------
# ALL OTHER API ENDPOINTS
# -----------------------------------------------------------------------------
location / {
    # General rate limiting
    limit_req zone=general_limit burst=100 nodelay;
    limit_conn conn_limit 200;

    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # Standard headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;

    # Timeouts aligned with Gunicorn (300s) + buffer
    proxy_connect_timeout 30s;
    proxy_send_timeout 330s;
    proxy_read_timeout 330s;

    # Buffering for normal requests
    proxy_buffering on;
    proxy_buffer_size 16k;
    proxy_buffers 32 16k;
    proxy_busy_buffers_size 64k;

    # Retry logic
    proxy_next_upstream error timeout http_502 http_503 http_504;
    proxy_next_upstream_tries 3;
    proxy_next_upstream_timeout 60s;

    # Debug headers
    add_header X-Backend-Server $upstream_addr always;
    add_header X-Request-ID $request_id always;
    add_header X-Response-Time $upstream_response_time always;
}

# -----------------------------------------------------------------------------
# ERROR PAGES
# -----------------------------------------------------------------------------
error_page 502 503 504 /50x.html;
location = /50x.html {
    root /usr/share/nginx/html;
    internal;
}

# Custom 429 (rate limit) response
error_page 429 /429.html;
location = /429.html {
    default_type application/json;
    return 429 '{"error": "Too many requests. Please slow down.", "retry_after": 60}';
}
