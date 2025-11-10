# Load-balanced backend configuration for ${domain}
# This file should be placed in /etc/nginx/vhosts/${domain}.conf

# Access log with load balancer info
access_log /var/log/nginx/${domain}.access.log load_balanced;
error_log /var/log/nginx/${domain}.error.log warn;

# Client configuration
client_max_body_size 100M;
client_body_timeout 300s;
client_header_timeout 300s;

# Health check endpoint (no rate limiting)
location /health/ {
    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # Basic headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Short timeouts for health checks
    proxy_connect_timeout 5s;
    proxy_send_timeout 10s;
    proxy_read_timeout 10s;

    # No buffering for health checks
    proxy_buffering off;

    # Don't log health checks (reduce log noise)
    access_log off;
}

# Readiness and liveness probes
location ~ ^/(ready|live)/ {
    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_buffering off;
    access_log off;
}

# Streaming endpoints (SSE) - use dedicated upstream with least_conn
location ~ ^/(messages/(stream|[^/]+/regenerate/?)|chat/stream) {
    # Rate limiting for streaming
    limit_req zone=streaming_limit burst=5000 nodelay;
    limit_conn conn_limit 5000;

    # Route to streaming-optimized upstream
    proxy_pass http://django_streaming;

    # HTTP/1.1 with keepalive
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # Headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;

    # CRITICAL: Disable buffering for Server-Sent Events (SSE)
    proxy_buffering off;
    proxy_cache off;
    proxy_request_buffering off;

    # Headers to ensure streaming works
    proxy_set_header X-Accel-Buffering no;
    proxy_set_header Cache-Control no-cache;

    # Extended timeouts for long-lived streaming connections
    proxy_connect_timeout 300s;
    proxy_send_timeout 600s;
    proxy_read_timeout 600s;

    # Disable timeout during chunked transfer
    chunked_transfer_encoding on;

    # Connection settings
    proxy_next_upstream error timeout http_502 http_503 http_504;
    proxy_next_upstream_tries 3;
    proxy_next_upstream_timeout 10s;
}

# WebSocket endpoints
location /ws/ {
    # Rate limiting
    limit_req zone=general_limit burst=500 nodelay;

    proxy_pass http://django_backend;

    # WebSocket upgrade headers
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    # Standard headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Extended timeouts for WebSocket
    proxy_connect_timeout 300s;
    proxy_send_timeout 600s;
    proxy_read_timeout 600s;

    # No buffering for WebSocket
    proxy_buffering off;
}

# Authentication endpoints
location ~ ^/(auth|login|logout|register)/ {
    # Stricter rate limiting for auth endpoints
    limit_req zone=auth_limit burst=1000 nodelay;
    limit_conn conn_limit 5000;

    proxy_pass http://django_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;

    # Standard timeouts
    proxy_connect_timeout 30s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;

    # Enable buffering for auth
    proxy_buffering on;
    proxy_buffer_size 4k;
    proxy_buffers 8 4k;

    # Retry on failure
    proxy_next_upstream error timeout http_502 http_503;
    proxy_next_upstream_tries 2;
}

# Static files
location /static/ {
    alias /usr/src/backend/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
    access_log off;
}

# API documentation (Swagger/ReDoc) - cacheable
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

# All other API endpoints
location / {
    # General rate limiting
    limit_req zone=general_limit burst=1000 nodelay;
    limit_conn conn_limit 5000;

    # Pass to load-balanced backend
    proxy_pass http://django_backend;

    # HTTP/1.1 with keepalive
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # Standard proxy headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;

    # Timeouts
    proxy_connect_timeout 30s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;

    # Buffering settings (enabled for normal requests)
    proxy_buffering on;
    proxy_buffer_size 8k;
    proxy_buffers 16 8k;
    proxy_busy_buffers_size 16k;

    # Retry logic
    proxy_next_upstream error timeout http_502 http_503 http_504;
    proxy_next_upstream_tries 3;
    proxy_next_upstream_timeout 30s;

    # Add response headers
    add_header X-Backend-Server $upstream_addr always;
    add_header X-Request-ID $request_id always;
}

# Error pages
error_page 502 503 504 /50x.html;
location = /50x.html {
    root /usr/share/nginx/html;
    internal;
}
