# Risk Assessment - Hybrid WSGI+ASGI Migration

**Project:** Chat-Arena-Backend  
**Date:** 2026-02-05  
**Version:** 1.0  
**Status:** Risk Identification Complete

---

## Risk Matrix

| Risk ID | Risk | Likelihood | Impact | Severity | Mitigation | Owner |
|---------|------|------------|--------|----------|------------|-------|
| R1 | ASGI container crashes under load | Medium | High | **HIGH** | Load testing, circuit breakers | DevOps |
| R2 | Session sharing fails between WSGI/ASGI | Low | High | **MEDIUM** | Redis testing, session validation | Backend |
| R3 | Database connection exhaustion | Medium | High | **HIGH** | Connection pooling, monitoring | Backend |
| R4 | WebSocket connections drop during deployment | High | Medium | **HIGH** | Graceful shutdown, connection migration | DevOps |
| R5 | Nginx routing misconfiguration | Low | Critical | **HIGH** | Config validation, smoke tests | DevOps |
| R6 | Performance regression on WSGI endpoints | Low | Medium | **LOW** | Baseline comparison, monitoring | Backend |
| R7 | Redis failure breaks both stacks | Low | Critical | **MEDIUM** | Redis persistence, fallback sessions | Infrastructure |
| R8 | Async code blocks event loop | Medium | Medium | **MEDIUM** | Code review, profiling | Backend |
| R9 | Memory leaks in ASGI containers | Medium | High | **HIGH** | Memory monitoring, container restarts | DevOps |
| R10 | Team unfamiliarity with async patterns | High | Low | **MEDIUM** | Training, documentation | Team Lead |

---

## Detailed Risk Analysis

### R1: ASGI Container Crashes Under Load

**Description:** ASGI containers may crash or become unresponsive under high concurrent load (100+ streaming connections).

**Likelihood:** Medium  
**Impact:** High (streaming features unavailable)

**Indicators:**
- Container memory usage > 90%
- CPU usage sustained > 95%
- Increased error rate (5xx responses)
- Container restart events

**Mitigation:**
1. **Pre-deployment:**
   - Load test with 200+ concurrent connections
   - Set memory limits with buffer (2GB with 500MB headroom)
   - Configure auto-restart policies

2. **Runtime:**
   - Monitor memory/CPU per container
   - Alert on memory > 85%
   - Circuit breaker for external API calls
   - Rate limiting on streaming endpoints

3. **Response:**
   - Auto-scale ASGI containers
   - Shed load gracefully (return 503)
   - Fallback to WSGI for non-streaming requests

**Recovery Time:** < 2 minutes (auto-restart)

---

### R2: Session Sharing Fails Between WSGI/ASGI

**Description:** User sessions stored in Redis may not be correctly shared between WSGI and ASGI containers.

**Likelihood:** Low  
**Impact:** High (users logged out mid-session)

**Indicators:**
- Authentication failures after routing to different container type
- Session not found errors
- Users forced to re-login

**Mitigation:**
1. **Pre-deployment:**
   - Validate session backend configuration
   - Test session read/write from both WSGI and ASGI
   - Verify cookie settings (domain, path, secure)

2. **Testing:**
   \\\python
   # Test script
   import requests
   
   # Login via WSGI
   session = requests.Session()
   session.post('http://wsgi:8000/api/auth/login/', json={...})
   
   # Verify session works on ASGI
   response = session.get('http://asgi:8001/api/sessions/')
   assert response.status_code == 200
   \\\

3. **Monitoring:**
   - Track auth failures by container type
   - Alert on spike in 401 responses

**Recovery Time:** < 5 minutes (config change + reload)

---

### R3: Database Connection Exhaustion

**Description:** Total database connections (WSGI + ASGI pools) may exceed PostgreSQL max_connections.

**Likelihood:** Medium  
**Impact:** High (database queries fail)

**Indicators:**
- \FATAL: too many clients already\ errors
- Increased query latency
- Connection timeout errors

**Mitigation:**
1. **Pre-deployment:**
   - Calculate total connections: (WSGI containers × workers × pool size) + (ASGI containers × pool size)
   - Set PostgreSQL \max_connections\ = total + 20% buffer
   - Configure connection pooling per container type

2. **Configuration:**
   \\\python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'CONN_MAX_AGE': 600,  # Connection reuse
           'OPTIONS': {
               'connect_timeout': 10,
               'options': '-c statement_timeout=30000'
           }
       }
   }
   
   # WSGI: 20 connections per container
   # ASGI: 10 connections per container
   \\\

3. **Monitoring:**
   - Track active connections: \SELECT count(*) FROM pg_stat_activity;\
   - Alert at 80% of max_connections

**Recovery Time:** < 10 minutes (adjust pool sizes + restart containers)

---

### R4: WebSocket Connections Drop During Deployment

**Description:** Active WebSocket connections will be terminated when ASGI containers restart during deployment.

**Likelihood:** High  
**Impact:** Medium (users must reconnect)

**Indicators:**
- WebSocket disconnect events
- Client reconnection attempts
- User complaints about chat interruptions

**Mitigation:**
1. **Graceful Shutdown:**
   \\\python
   # In ASGI application
   import signal
   
   async def graceful_shutdown(sig):
       print(f"Received signal {sig}, closing connections...")
       # Send close message to all WebSocket connections
       for connection in active_connections:
           await connection.close(code=1001, reason="Server restarting")
       await asyncio.sleep(2)  # Allow time for close frames
   \\\

2. **Client-Side Reconnection:**
   \\\javascript
   // Frontend WebSocket client
   socket.onclose = (event) => {
       if (event.code === 1001) {
           console.log('Server restarting, reconnecting in 2s...');
           setTimeout(() => connectWebSocket(), 2000);
       }
   };
   \\\

3. **Rolling Deployment:**
   - Deploy ASGI containers one at a time
   - Wait 30s between container updates
   - Minimize simultaneous disconnections

**Recovery Time:** < 5 seconds (auto-reconnect)

---

### R5: Nginx Routing Misconfiguration

**Description:** Incorrect Nginx configuration may route requests to wrong backend or cause routing loops.

**Likelihood:** Low  
**Impact:** Critical (entire system unavailable)

**Indicators:**
- 502 Bad Gateway errors
- 404 Not Found for valid endpoints
- Requests timing out
- Nginx error logs: \upstream prematurely closed connection\

**Mitigation:**
1. **Pre-deployment:**
   - Validate Nginx config: \
ginx -t\
   - Test routing in staging
   - Create routing test suite:
     \\\ash
     # Test WSGI routes
     curl http://staging/api/models/ | grep -q "200 OK"
     
     # Test ASGI routes
     curl http://staging/api/messages/stream/ | grep -q "200 OK"
     \\\

2. **Smoke Tests:**
   - Automated tests run after deployment
   - Verify each endpoint category reaches correct backend
   - Check response headers for container identification

3. **Quick Rollback:**
   - Keep previous Nginx config backed up
   - Rollback command: \cp nginx.conf.bak nginx.conf && nginx -s reload\

**Recovery Time:** < 2 minutes (reload config)

---

### R6: Performance Regression on WSGI Endpoints

**Description:** WSGI endpoints may perform worse after hybrid deployment due to resource contention or config changes.

**Likelihood:** Low  
**Impact:** Medium (user experience degraded)

**Indicators:**
- WSGI endpoint P95 latency > baseline + 20%
- Increased CPU usage on WSGI containers
- Database query slowness

**Mitigation:**
1. **Baseline Comparison:**
   - Run load tests before and after migration
   - Compare metrics side-by-side
   - Define acceptable variance (±10%)

2. **Resource Isolation:**
   - Ensure WSGI and ASGI have dedicated resources
   - No shared worker pools
   - Separate container limits

3. **Monitoring:**
   - Real-time latency dashboards per container type
   - Alert on P95 > baseline + 20%

**Recovery Time:** < 15 minutes (rollback or adjust resources)

---

### R7: Redis Failure Breaks Both Stacks

**Description:** Redis failure impacts sessions, cache, and Channels layer simultaneously.

**Likelihood:** Low  
**Impact:** Critical (sessions lost, WebSocket broken)

**Indicators:**
- \Redis connection refused\ errors
- Session authentication failures
- WebSocket routing failures
- Cache miss rate = 100%

**Mitigation:**
1. **Redis Persistence:**
   \\\ash
   # Enable RDB snapshots
   redis-server --save 900 1 --save 300 10 --save 60 10000
   \\\

2. **Fallback Sessions:**
   \\\python
   # settings.py fallback
   SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
   # Falls back to database if Redis unavailable
   \\\

3. **Redis Monitoring:**
   - Health check every 10 seconds
   - Alert on connection failures
   - Auto-restart on crash

4. **High Availability (Production):**
   - Redis Sentinel (3 nodes)
   - Automatic failover

**Recovery Time:** < 5 minutes (restart Redis + restore from snapshot)

---

### R8: Async Code Blocks Event Loop

**Description:** Accidentally using blocking I/O in async code blocks the event loop.

**Likelihood:** Medium  
**Impact:** Medium (ASGI performance degraded)

**Indicators:**
- ASGI response times spike
- Event loop lag increases
- Concurrent requests queue up

**Mitigation:**
1. **Code Review:**
   - Check for blocking calls in async functions
   - Flag: \	ime.sleep()\, \equests.get()\, \open()\ in async code
   - Use: \wait asyncio.sleep()\, \httpx.AsyncClient\, \iofiles\

2. **Linting:**
   \\\python
   # Add to CI/CD
   flake8 --select=ASYNC  # Check async/await usage
   \\\

3. **Profiling:**
   - Use \syncio.create_task()\ for concurrent operations
   - Profile event loop lag in staging

**Recovery Time:** N/A (requires code fix + deployment)

---

### R9: Memory Leaks in ASGI Containers

**Description:** Long-running ASGI containers may accumulate memory due to unclosed connections or leaks.

**Likelihood:** Medium  
**Impact:** High (containers OOM crash)

**Indicators:**
- Container memory usage steadily increasing
- OOMKilled events
- Garbage collection frequency increases

**Mitigation:**
1. **Container Restarts:**
   \\\yaml
   # docker-compose.yml
   deploy:
     restart_policy:
       condition: on-failure
       max_attempts: 3
   \\\

2. **Periodic Restart:**
   - Restart ASGI containers every 24 hours (rolling)
   - Use \--max-requests\ in Uvicorn (if supported)

3. **Memory Monitoring:**
   - Alert on memory growth rate > 10MB/hour
   - Track WebSocket connection count vs memory

4. **Connection Cleanup:**
   \\\python
   # Ensure WebSocket cleanup
   async def disconnect(self, close_code):
       await self.channel_layer.group_discard(
           self.room_group_name,
           self.channel_name
       )
       # Explicit cleanup
       del self.scope
   \\\

**Recovery Time:** < 2 minutes (auto-restart)

---

### R10: Team Unfamiliarity with Async Patterns

**Description:** Development team may struggle with async/await patterns, leading to bugs.

**Likelihood:** High  
**Impact:** Low (development velocity)

**Indicators:**
- Incorrect use of \sync_to_async\
- Missing \wait\ keywords
- Blocking I/O in async functions
- Code review comments on async usage

**Mitigation:**
1. **Training:**
   - 2-hour async/await workshop
   - Document common patterns
   - Code examples repository

2. **Documentation:**
   - Async coding guidelines
   - Do's and Don'ts cheatsheet
   - Common pitfalls

3. **Code Review:**
   - Require async expert review
   - Automated linting
   - Pre-commit hooks

**Recovery Time:** N/A (ongoing process)

---

## Risk Probability × Impact Matrix

\\\
Impact
  ↑
High    │ R3  R1  R9 │         │ R2      │
        │            │         │         │
Medium  │ R8         │ R6      │ R4      │
        │            │         │         │
Low     │ R10        │         │ R5  R7  │
        └────────────┴─────────┴─────────→
          Low       Medium     High    Likelihood
\\\

**High Priority (Address First):**
- R5: Nginx routing misconfiguration
- R7: Redis failure
- R1: ASGI crashes
- R3: DB connection exhaustion
- R4: WebSocket disconnects

---

## Overall Risk Assessment

**Migration Risk Level:** MEDIUM

**Justification:**
- High-impact risks have low likelihood
- Mitigation strategies defined for all risks
- Rollback procedures available
- Team has Django experience (learning curve manageable)

**Risk Acceptance:**
- Benefits (async streaming, better concurrency) outweigh risks
- Risks can be mitigated with proper testing and monitoring
- Rollback path is clear and fast

---

## Monitoring Signals for Risk Detection

| Signal | Check Frequency | Alert Threshold | Risk(s) |
|--------|----------------|-----------------|---------|
| Container restart count | 1 min | > 3 in 10 min | R1, R9 |
| Memory usage | 30 sec | > 85% | R9 |
| CPU usage | 30 sec | > 80% sustained | R1 |
| Auth failure rate | 1 min | > 5% | R2 |
| DB connections | 1 min | > 80% max | R3 |
| WebSocket disconnect rate | 1 min | > 20% | R4 |
| Nginx 502 errors | 1 min | > 10 in 1 min | R5 |
| P95 latency (WSGI) | 1 min | > baseline + 20% | R6 |
| Redis connection errors | 10 sec | > 0 | R7 |
| Event loop lag | 1 min | > 100ms | R8 |

---

## Risk Review Schedule

- **Pre-deployment:** Full risk review with team
- **Post-deployment (Week 1):** Daily risk assessment
- **Post-deployment (Month 1):** Weekly risk review
- **Ongoing:** Monthly risk review, update mitigation strategies

---

**Document Status:** ✅ COMPLETE  
**Last Updated:** 2026-02-05  
**Next Review:** [Schedule after deployment]

**Task 1.7 Status:** In Progress (Risk assessment complete, rollback plan next)
