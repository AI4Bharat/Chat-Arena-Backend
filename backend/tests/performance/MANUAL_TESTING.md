# Manual Performance Testing Guide

## Prerequisites
\\\powershell
# Install load testing tool
pip install locust
\\\

## Quick Baseline Tests

### Test 1: Health Check
\\\powershell
# Start Django server
python manage.py runserver 8000

# In another terminal
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/admin/login/
\\\

### Test 2: API Endpoint
\\\powershell
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/api/models/
\\\

## curl-format.txt
Create this file for timing details:
\\\	xt
    time_namelookup:  %{time_namelookup}s\n
       time_connect:  %{time_connect}s\n
    time_appconnect:  %{time_appconnect}s\n
   time_pretransfer:  %{time_pretransfer}s\n
      time_redirect:  %{time_redirect}s\n
 time_starttransfer:  %{time_starttransfer}s\n
                    ----------\n
         time_total:  %{time_total}s\n
\\\

## Using Locust (Recommended)

### Step 1: Create locustfile.py
\\\python
from locust import HttpUser, task, between

class BaselineUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def list_models(self):
        self.client.get("/api/models/")
    
    @task(1)
    def health_check(self):
        self.client.get("/admin/login/")
\\\

### Step 2: Run Locust
\\\powershell
locust -f tests/performance/locustfile.py --host=http://localhost:8000
\\\

Then open: http://localhost:8089

- Users: 10
- Spawn rate: 2/sec
- Run for: 60 seconds

---

**Baseline Metrics to Record:**
- P50, P95, P99 latencies
- Requests/second
- Error rate
- Database query count (Django Debug Toolbar)
