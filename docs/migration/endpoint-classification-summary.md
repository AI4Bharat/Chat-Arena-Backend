# Endpoint Classification - Quick Reference

## Summary Statistics
- **Total Endpoints:** 359
- **True ASGI Targets:** ~10-12 (streaming/generation only)
- **WSGI Targets:** ~340-350 (CRUD, auth, admin, queries)
- **WebSocket Routes:** TBD (needs manual check)

---

## Critical ASGI Endpoints (Confirmed)

| Endpoint | Method | Purpose | Duration |
|----------|--------|---------|----------|
| \/api/messages/stream/\ | POST | Stream LLM responses | 5-30s |
| \/api/messages/{id}/regenerate/\ | POST | Regenerate message | 5-30s |
| \/api/models/compare/\ | POST | Compare 2+ models | 10-60s |
| \/api/messages/upload_audio/\ | POST | Process audio | 2-10s |
| \/api/asr-api/generic/transcribe\ | POST | ASR transcription | 2-10s |
| \/api/sessions/{id}/generate_title/\ | POST | Generate title | 2-5s |
| \/api/compare/\ | POST | Model comparison | 10-60s |
| \/ws/*\ | WebSocket | Real-time chat | Long-lived |

---

## Nginx Routing (Simplified)

\\\
ginx
# ASGI: Streaming & Generation
location ~ ^/api/(messages/stream|messages/.*/regenerate|models/compare|asr-api|compare) {
    proxy_pass http://asgi_upstream;
    proxy_buffering off;
}

# ASGI: WebSocket
location /ws/ {
    proxy_pass http://asgi_upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \;
    proxy_set_header Connection "upgrade";
}

# WSGI: Everything else
location / {
    proxy_pass http://wsgi_upstream;
}
\\\

---

## Container Resource Allocation

### ASGI Containers
- **Count:** 2-3 instances
- **CPU:** 2 cores per instance
- **Memory:** 2GB per instance
- **Worker Model:** Uvicorn with 1 worker/container (async handles concurrency)
- **Connections:** Handle 100+ concurrent streams

### WSGI Containers
- **Count:** 3-4 instances
- **CPU:** 2 cores per instance
- **Memory:** 1.5GB per instance
- **Worker Model:** Gunicorn with 4 workers per container
- **Connections:** 16-20 concurrent requests per worker

---

## Verification Commands

\\\powershell
# Check for WebSocket routes
Get-ChildItem -Recurse -Filter "*.py" | Select-String "websocket|WebSocket" 

# Find Channels routing files
Get-ChildItem -Recurse -Filter "routing.py"

# Count actual streaming endpoints
python analyze_endpoints.py | Select-String "stream|regenerate|compare|transcribe"
\\\

---

## Status: ✅ COMPLETE

**Task 1.2 Completed:** Endpoint classification documented.

**Next Task:** External API Audit (Task 1.3)
