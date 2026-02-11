# Detailed Endpoint Classification - Chat Arena Backend

## Executive Summary

**Total Endpoints:** 359
- **ASGI Targets:** 83 (23%) - Streaming, async-heavy operations
- **WSGI Targets:** 276 (77%) - CRUD, auth, admin operations
- **WebSocket Targets:** 0 (needs investigation)

---

## Classification Criteria

### ASGI Targets (Async)
Routes streaming responses, long-lived connections, or external API-heavy operations:
- Streaming chat responses (SSE)
- TTS/ASR audio generation
- Multi-model comparisons (concurrent API calls)
- WebSocket connections

### WSGI Targets (Sync)
Routes short-lived, database-bound operations:
- CRUD endpoints (list, create, retrieve, update, delete)
- Authentication/authorization
- Admin panel operations
- Leaderboard queries (can be cached)

---

## Key ASGI Endpoints Identified

### 1. Streaming Message Generation
**Endpoint:** \POST /api/messages/stream/\
- **Rationale:** Streams LLM responses using SSE
- **Providers:** OpenAI, Anthropic, Google, Mistral, DeepSeek
- **Expected Duration:** 5-30 seconds
- **Concurrency:** High benefit from async

### 2. Message Regeneration
**Endpoint:** \POST /api/messages/{id}/regenerate/\
- **Rationale:** Similar to streaming, regenerates AI responses
- **Strategy:** Convert to async view

### 3. Audio Upload/Processing
**Endpoint:** \POST /api/messages/upload_audio/\
- **Rationale:** Processes audio files, may call TTS/ASR providers
- **Strategy:** Use async file I/O

### 4. Model Comparison
**Endpoint:** \POST /api/models/compare/\
- **Rationale:** Calls 2+ LLM providers concurrently
- **Expected Duration:** 10-60 seconds
- **Concurrency:** Critical for performance

### 5. ASR Transcription
**Endpoint:** \POST /api/asr-api/generic/transcribe\
- **Rationale:** Calls external ASR APIs (Google Speech-to-Text)
- **Expected Duration:** 2-10 seconds

### 6. Chat Session Title Generation
**Endpoint:** \POST /api/sessions/{id}/generate_title/\
- **Rationale:** Calls LLM to generate session title
- **Strategy:** Keep async, low priority

---

## WebSocket Investigation Required

**Issue:** No WebSocket routes detected by the analyzer.

**Expected WebSocket Endpoints:**
- \ws://<domain>/ws/chat-session/<session_id>/\
- May be defined in Channels routing, not Django URLs

**Action Required:** Check \rena_backend/routing.py\ or \chat_session/routing.py\ for WebSocket patterns.

---

## WSGI Endpoints (High-Level)

### Authentication (\user\ app)
- \POST /api/auth/anonymous/\ - Anonymous login
- \POST /api/auth/google/\ - Google OAuth
- \POST /api/auth/phone/\ - Phone authentication
- \POST /api/auth/refresh/\ - Token refresh
**Rationale:** Auth operations are fast, DB-bound, no streaming needed

### Feedback (\eedback\ app)
- \GET /api/feedback/\ - List feedback
- \POST /api/feedback/\ - Submit feedback
- \POST /api/feedback/bulk_create/\ - Bulk feedback
- \GET /api/feedback/my_stats/\ - User stats
**Rationale:** Database writes/reads, no external API calls

### Leaderboards (\leaderboards\ app)
- \GET /api/leaderboard/{arena_type}/\ - Get leaderboard
- \GET /api/leaderboard/contributors/\ - Top contributors
**Rationale:** Database aggregations, can leverage caching

### Models (\i_model\ app)
- \GET /api/models/\ - List models
- \GET /api/models/{id}/\ - Model details
**Rationale:** Static data, no streaming

### Admin Panel
- \/admin/*\ - All admin routes
**Rationale:** Django admin is sync, no async support needed

---

## External API Integration Strategy

### LLM Providers (Async Priority)
| Provider | SDK | Async Support | Migration Strategy |
|----------|-----|---------------|-------------------|
| OpenAI | \openai\ | ✅ Native | Use \AsyncOpenAI\ |
| Anthropic | \nthropic\ | ✅ Native | Use \AsyncAnthropic\ |
| Google Gemini | \google-generativeai\ | ⚠️ Partial | Test async, fallback to \sync_to_async\ |
| Mistral | Custom/\equests\ | ❌ No | Migrate to \httpx.AsyncClient\ |
| DeepSeek | Custom/\equests\ | ❌ No | Migrate to \httpx.AsyncClient\ |
| Meta/Llama | \litellm\ | ✅ Yes | Use async mode |
| Qwen | Custom | ❌ No | Migrate to \httpx.AsyncClient\ |

### TTS Providers (Async Priority)
| Provider | SDK | Async Support | Migration Strategy |
|----------|-----|---------------|-------------------|
| ElevenLabs | \elevenlabs\ | ✅ Native | Use async client |
| Cartesia | \cartesia\ | ✅ Native | Use \AsyncCartesia\ |
| Google TTS | \google-cloud-texttospeech\ | ❌ No | Wrap with \sync_to_async\ |
| Triton | \	ritonclient\ | ❌ No | Keep sync (low usage) |

### ASR Providers
| Provider | SDK | Async Support | Migration Strategy |
|----------|-----|---------------|-------------------|
| Google Speech | \google-cloud-speech\ | ❌ No | Wrap with \sync_to_async\ |

---

## Nginx Routing Configuration

### Recommended Routing Rules

\\\
ginx
# ASGI Upstream (Uvicorn/Daphne on port 8001)
upstream asgi_upstream {
    server backend-asgi-1:8001;
    server backend-asgi-2:8001;
    keepalive 64;
}

# WSGI Upstream (Gunicorn on port 8000)
upstream wsgi_upstream {
    server backend-wsgi-1:8000;
    server backend-wsgi-2:8000;
    keepalive 32;
}

# Route streaming endpoints to ASGI
location ~ ^/api/messages/(stream|upload_audio) {
    proxy_pass http://asgi_upstream;
    proxy_buffering off;
    proxy_read_timeout 300s;
}

# Route regenerate to ASGI
location ~ ^/api/messages/[^/]+/regenerate {
    proxy_pass http://asgi_upstream;
    proxy_buffering off;
}

# Route model comparison to ASGI
location ~ ^/api/models/compare {
    proxy_pass http://asgi_upstream;
    proxy_read_timeout 120s;
}

# Route ASR to ASGI
location ~ ^/api/asr-api {
    proxy_pass http://asgi_upstream;
}

# Route title generation to ASGI
location ~ ^/api/sessions/[^/]+/generate_title {
    proxy_pass http://asgi_upstream;
}

# Route compare endpoint to ASGI
location /api/compare/ {
    proxy_pass http://asgi_upstream;
}

# WebSocket to ASGI (when discovered)
location /ws/ {
    proxy_pass http://asgi_upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade \;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}

# Default: Route everything else to WSGI
location / {
    proxy_pass http://wsgi_upstream;
}
\\\

---

## Implementation Checklist

### Phase 1: Preparation
- [x] Extract all endpoints (359 total)
- [ ] Locate WebSocket routing files
- [ ] Audit external API clients for async support
- [ ] Document classification rationale

### Phase 2: Code Conversion (ASGI)
- [ ] Convert \MessageViewSet.stream\ to async
- [ ] Convert \MessageViewSet.regenerate\ to async
- [ ] Convert \MessageViewSet.upload_audio\ to async
- [ ] Convert \AIModelViewSet.compare\ to async
- [ ] Convert ASR transcription view to async
- [ ] Convert LLM provider clients to async
- [ ] Convert TTS provider clients to async

### Phase 3: Infrastructure
- [ ] Create ASGI container definition
- [ ] Create WSGI container definition
- [ ] Configure Nginx routing rules
- [ ] Set up health checks per container type
- [ ] Configure monitoring/logging differentiation

### Phase 4: Testing
- [ ] Test each ASGI endpoint under load
- [ ] Test WSGI/ASGI session sharing
- [ ] Validate routing rules
- [ ] Performance baseline comparison

---

## Known Issues & Risks

### High Priority
1. **WebSocket Routes Missing:** Analyzer didn't find WebSocket patterns
   - **Risk:** Can't validate ASGI requirement for WebSocket
   - **Mitigation:** Manual check of Channels routing files

2. **Session Count Endpoints:** Many \ChatSessionViewSet\ endpoints classified as ASGI due to "chat" keyword
   - **Risk:** Over-routing to ASGI (most session ops are CRUD)
   - **Mitigation:** Refine classification - only streaming/generation should be ASGI

### Medium Priority
3. **Admin Panel Routes:** Classified some admin/chat_session routes as ASGI
   - **Risk:** Admin panel may break under ASGI
   - **Mitigation:** Force all \/admin/*\ to WSGI

4. **Duplicate Routes:** Many routes have format suffix variations (e.g., \.json\, \.xml\)
   - **Risk:** Routing rules may need wildcards
   - **Mitigation:** Use regex in Nginx

---

## Refined Classification (Corrections)

**Over-classified as ASGI:** Many ChatSessionViewSet CRUD endpoints were flagged due to "chat" keyword.

**Should be WSGI:**
- \GET /api/sessions/\ - List sessions (database query)
- \POST /api/sessions/\ - Create session (database write)
- \GET /api/sessions/{id}/\ - Retrieve session (database read)
- \PATCH /api/sessions/{id}/\ - Update session (database update)
- \DELETE /api/sessions/{id}/\ - Delete session (database delete)
- \POST /api/sessions/{id}/duplicate/\ - Duplicate session (database copy)
- \GET /api/sessions/{id}/export/\ - Export session (fast JSON serialization)
- \GET /api/sessions/{id}/statistics/\ - Session stats (database aggregation)
- \POST /api/sessions/{id}/share/\ - Share session (database update)
- \GET /api/sessions/shared/\ - List shared sessions (database query)
- \GET /api/sessions/trending/\ - Trending sessions (database query with cache)
- \GET /api/sessions/type/\ - Filter by type (database query)

**Should REMAIN ASGI:**
- \POST /api/sessions/{id}/generate_title/\ - Calls LLM
- Any session endpoint that triggers LLM/TTS generation

**Actual ASGI Count:** ~8-12 endpoints (not 83)

---

## Next Steps

1. **Locate WebSocket Routing:**
   \\\powershell
   # Search for WebSocket patterns
   Get-ChildItem -Recurse -Filter "*.py" | Select-String "websocket" -CaseSensitive
   \\\

2. **Refine Classification Script:** Update \nalyze_endpoints.py\ to exclude false positives

3. **Create Routing Map:** Finalize Nginx configuration based on corrected classification

4. **Document:** Update this file with WebSocket findings

---

**Document Version:** 1.0  
**Created:** Feb 5, 2026  
**Last Updated:** Feb 5, 2026  
**Status:** Draft - Needs WebSocket validation
