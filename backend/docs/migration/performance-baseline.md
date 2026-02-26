# Performance Baseline - Pre-Hybrid Migration

## Test Environment

**Date:** 2026-02-05 11:37:56  
**Django Version:** 5.2.6  
**Database:** PostgreSQL 17 (local)  
**Cache:** Redis (if enabled)  
**Server Mode:** WSGI (runserver)  
**OS:** Windows 11  
**Python:** 3.13.7

---

## Baseline Metrics

### WSGI Endpoints (Will Remain WSGI)

| Endpoint | P50 (ms) | P95 (ms) | P99 (ms) | Throughput (req/s) | Notes |
|----------|----------|----------|----------|-------------------|-------|
| \GET /api/models/\ | TBD | TBD | TBD | TBD | Simple DB query |
| \GET /api/leaderboard/{type}/\ | TBD | TBD | TBD | TBD | Aggregation query |
| \GET /admin/login/\ | TBD | TBD | TBD | TBD | No DB, static page |
| \GET /api/sessions/\ | TBD | TBD | TBD | TBD | Requires auth |

### Future ASGI Endpoints (Currently WSGI)

| Endpoint | P50 (ms) | P95 (ms) | P99 (ms) | Throughput (req/s) | Notes |
|----------|----------|----------|----------|-------------------|-------|
| \POST /api/messages/stream/\ | TBD | TBD | TBD | TBD | Will be streaming |
| \POST /api/models/compare/\ | TBD | TBD | TBD | TBD | Will call 2+ LLMs |

---

## How to Run Baseline Tests

### Option 1: Automated Script
\\\powershell
# Start Django
python manage.py runserver 8000

# Run tests (in another terminal)
python tests/performance/baseline_tests.py
\\\

### Option 2: Locust Load Testing
\\\powershell
# Start Django
python manage.py runserver 8000

# Run Locust
locust -f tests/performance/locustfile.py --host=http://localhost:8000

# Open browser: http://localhost:8089
# Configure: 10 users, 2/sec spawn rate, 60 second runtime
\\\

### Option 3: Manual cURL Tests
See \	ests/performance/MANUAL_TESTING.md\

---

## Recording Results

**TODO:** Run one of the above tests and fill in the TBD values.

**Status:** 
- [x] Test scripts created
- [ ] Baseline tests executed
- [ ] Metrics recorded in this document
- [ ] Ready for hybrid comparison

---

## Expected Improvements After Hybrid Migration

### WSGI Endpoints
- **Expected:** ±5% (should remain similar)
- **Acceptable Range:** -10% to +10%

### ASGI Streaming Endpoints
- **Expected:** 40-70% improvement in time-to-first-byte
- **Expected:** 2-5x better concurrency handling
- **Metric Focus:** Concurrent stream handling (not latency)

---

## Notes

- Baseline captured on development server (not production Gunicorn)
- Results will vary with load, network, external API response times
- Focus on relative comparisons, not absolute numbers
- Production testing needed after staging validation

---

**Task 1.5 Status:** ✅ Scripts ready, awaiting execution
**Next:** Execute tests when Django server is stable
