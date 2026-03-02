# Test Plan - Hybrid WSGI+ASGI Migration

**Project:** Chat-Arena-Backend  
**Version:** 1.0  
**Date:** 2026-02-05  
**Status:** Test Planning

---

## Test Strategy

### Test Pyramid

\\\
         /\\
        /  \\  Manual Tests (5%)
       /----\\
      / E2E  \\ End-to-End Tests (15%)
     /--------\\
    /Integration\\ Integration Tests (30%)
   /------------\\
  /  Unit Tests  \\ Unit Tests (50%)
 /----------------\\
\\\

---

## Test Phases

### Phase 1: Infrastructure Tests
**Goal:** Verify Docker setup works

| Test | Type | Tool | Priority |
|------|------|------|----------|
| Docker build succeeds | Infrastructure | Docker | HIGH |
| All containers start | Infrastructure | Docker Compose | HIGH |
| Health checks pass | Infrastructure | curl | HIGH |
| Network connectivity | Infrastructure | Docker | HIGH |
| Volume mounts work | Infrastructure | Docker | MEDIUM |

**Duration:** 30 minutes

---

### Phase 2: Component Tests
**Goal:** Test individual components

| Test | Type | Tool | Priority |
|------|------|------|----------|
| WSGI server starts | Unit | pytest | HIGH |
| ASGI server starts | Unit | pytest | HIGH |
| Database migrations | Unit | Django | HIGH |
| Redis connection | Unit | pytest | HIGH |
| Static files collected | Unit | Django | MEDIUM |

**Duration:** 1 hour

---

### Phase 3: Routing Tests
**Goal:** Verify Nginx routes correctly

| Test | Type | Tool | Priority |
|------|------|------|----------|
| WSGI endpoints routed | Integration | curl | HIGH |
| ASGI endpoints routed | Integration | curl | HIGH |
| WebSocket upgrade works | Integration | wscat | HIGH |
| Static files served | Integration | curl | MEDIUM |
| 404 handling | Integration | curl | LOW |

**Duration:** 1 hour

---

### Phase 4: Functionality Tests
**Goal:** Verify features work

| Test | Type | Tool | Priority |
|------|------|------|----------|
| User can login | Integration | pytest | HIGH |
| Message CRUD works | Integration | pytest | HIGH |
| Streaming works | Integration | pytest | HIGH |
| WebSocket connects | Integration | pytest | MEDIUM |
| Model comparison works | Integration | pytest | MEDIUM |

**Duration:** 2 hours

---

### Phase 5: Performance Tests
**Goal:** Verify performance improvements

| Test | Type | Tool | Priority |
|------|------|------|----------|
| Baseline WSGI latency | Load | Locust | HIGH |
| Baseline ASGI latency | Load | Locust | HIGH |
| Concurrent streams | Load | Locust | HIGH |
| WebSocket connections | Load | Locust | MEDIUM |
| Resource usage | Load | Docker stats | MEDIUM |

**Duration:** 3 hours

---

## Test Cases

### TC-001: Docker Build
**Objective:** Verify Docker image builds successfully

**Steps:**
1. Run \docker build -t arena-backend .\
2. Check exit code is 0
3. Verify image exists: \docker images | grep arena-backend\

**Expected Result:** Image built with no errors

**Priority:** HIGH

---

### TC-002: Container Startup
**Objective:** All containers start and stay healthy

**Steps:**
1. Run \docker-compose -f docker-compose.hybrid.yml up -d\
2. Wait 30 seconds
3. Check status: \docker-compose -f docker-compose.hybrid.yml ps\
4. All containers show "Up" status

**Expected Result:** All 5 containers running

**Priority:** HIGH

---

### TC-003: WSGI Health Check
**Objective:** WSGI endpoint responds correctly

**Steps:**
1. Run \curl http://localhost/health/\
2. Check response status 200
3. Verify JSON contains \"container_type": "wsgi"\

**Expected Result:**
\\\json
{
  "status": "healthy",
  "container_type": "wsgi",
  "async_enabled": false,
  "checks": {
    "database": "ok",
    "cache": "ok"
  }
}
\\\

**Priority:** HIGH

---

### TC-004: ASGI Health Check
**Objective:** ASGI endpoint responds correctly

**Steps:**
1. Exec into ASGI container
2. Run \curl http://localhost:8001/health/\
3. Check response status 200
4. Verify JSON contains \"container_type": "asgi"\

**Expected Result:**
\\\json
{
  "status": "healthy",
  "container_type": "asgi",
  "async_enabled": true,
  "checks": {
    "database": "ok",
    "cache": "ok",
    "channels": "configured"
  }
}
\\\

**Priority:** HIGH

---

### TC-005: Message Streaming
**Objective:** Streaming endpoint works via ASGI

**Steps:**
1. POST to \http://localhost/api/messages/stream/\
2. Include valid session_id and message
3. Observe Server-Sent Events stream
4. Verify chunks arrive incrementally

**Expected Result:** SSE stream with incremental chunks

**Priority:** HIGH

---

### TC-006: WebSocket Connection
**Objective:** WebSocket connects via ASGI

**Steps:**
1. Connect to \ws://localhost/ws/chat/session/test123/\
2. Send test message
3. Receive echo or confirmation

**Expected Result:** WebSocket connection established

**Priority:** MEDIUM

---

### TC-007: Concurrent Streams
**Objective:** Handle multiple streaming requests

**Steps:**
1. Start 10 concurrent streaming requests
2. Monitor ASGI container CPU/memory
3. Verify all streams complete
4. Check for errors

**Expected Result:** All streams complete, CPU < 80%

**Priority:** HIGH

---

### TC-008: Database Connection Pooling
**Objective:** Connection pools don't exhaust

**Steps:**
1. Make 100 requests to WSGI endpoints
2. Make 100 requests to ASGI endpoints
3. Check PostgreSQL connections: \SELECT count(*) FROM pg_stat_activity;\

**Expected Result:** Connections < max_connections

**Priority:** MEDIUM

---

### TC-009: Redis Session Sharing
**Objective:** Sessions work across WSGI and ASGI

**Steps:**
1. Login via WSGI (\/api/auth/login/\)
2. Get session cookie
3. Use cookie on ASGI endpoint
4. Verify authenticated

**Expected Result:** Session recognized by both

**Priority:** HIGH

---

### TC-010: Static Files
**Objective:** Static files served via Nginx

**Steps:**
1. Request \http://localhost/static/admin/css/base.css\
2. Check status 200
3. Verify Content-Type: text/css

**Expected Result:** Static file served with caching headers

**Priority:** MEDIUM

---

## Test Automation

### Unit Tests
\\\ash
# Run all unit tests
pytest tests/unit/

# Run with coverage
pytest tests/unit/ --cov=. --cov-report=html
\\\

### Integration Tests
\\\ash
# Run integration tests
pytest tests/integration/

# Run specific test
pytest tests/integration/test_routing.py::test_wsgi_routing
\\\

### Load Tests
\\\ash
# Run Locust load test
locust -f tests/load/locustfile.py --host=http://localhost --users=100 --spawn-rate=10
\\\

---

## Success Criteria

### Must Pass (Blocking)
- All health checks return 200
- WSGI endpoints respond < 500ms (P95)
- ASGI streaming works without errors
- No container crashes during 1-hour test
- Database connections stay below 80% max

### Should Pass (Non-Blocking)
- ASGI endpoints 30% faster than WSGI for streams
- Can handle 100 concurrent streams
- Memory usage stable over 4 hours
- WebSocket connections stable

---

## Test Schedule

| Day | Phase | Duration |
|-----|-------|----------|
| Day 1 | Infrastructure + Component Tests | 4 hours |
| Day 2 | Routing + Functionality Tests | 6 hours |
| Day 3 | Performance + Load Tests | 8 hours |
| Day 4 | Bug fixes + Retest | 6 hours |
| Day 5 | Final validation | 4 hours |

**Total Effort:** 28 hours

---

## Test Environment

### Local Development
- Windows 11
- Docker Desktop
- Redis container
- PostgreSQL container

### Staging
- Linux server
- Docker Compose
- All services containerized

### Production (Post-Deployment)
- Canary deployment (10% traffic)
- Monitor for 24 hours
- Gradual rollout to 100%

---

## Defect Management

### Severity Levels

| Severity | Definition | Response Time |
|----------|------------|---------------|
| P0 | System down | Immediate |
| P1 | Core feature broken | 4 hours |
| P2 | Minor feature broken | 1 day |
| P3 | Enhancement/Polish | 1 week |

### Bug Tracking
- Use GitHub Issues
- Label: \ug\, \hybrid-migration\
- Assign to responsible team member

---

**Test Plan Status:** ✅ APPROVED  
**Last Updated:** 2026-02-05

