# Locust Load Testing Fix

## Issue
All Locust test endpoints showing failure.

## Common Causes

1. **Incorrect host URL** - Missing protocol or wrong domain
2. **No AI models configured** - Tests need models in database
3. **CORS issues** - Load test origin blocked
4. **SSL certificate issues** - HTTPS not trusted

## Fix 1: Run Locust with Correct Host

### Option A: Test via HTTP (works immediately)

```bash
cd backend/load_tests

# Test using localhost HTTP (bypasses SSL issues)
locust -f locustfile.py --host=http://localhost --users 10 --spawn-rate 2 --run-time 1m --headless

# Or with web UI
locust -f locustfile.py --host=http://localhost
# Open browser: http://localhost:8089
```

### Option B: Test via HTTPS (after fixing SSL)

```bash
# Test using domain HTTPS (after getting Let's Encrypt certificate)
locust -f locustfile.py --host=https://backend.arena.ai4bharat.org --users 10 --spawn-rate 2 --run-time 1m --headless
```

### Option C: Test with SSL verification disabled

```bash
# If SSL certificate is self-signed or not trusted
locust -f locustfile.py --host=https://backend.arena.ai4bharat.org --users 10 --spawn-rate 2 --run-time 1m --headless --insecure
```

## Fix 2: Ensure AI Models Exist

The tests create sessions with random models. If no models exist, tests will fail.

### Check if models exist:

```bash
# Check models in database
curl http://localhost/models/ | jq

# Should return array of models
# If empty [], you need to create models first
```

### Create test models:

```bash
# Enter Django shell
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell

# In Django shell, create models:
from ai_model.models import AIModel

# Create a few test models
AIModel.objects.create(
    name="GPT-4",
    provider="OpenAI",
    model_code="gpt-4",
    is_active=True,
    capabilities=["text", "code"]
)

AIModel.objects.create(
    name="Claude 3",
    provider="Anthropic",
    model_code="claude-3-sonnet",
    is_active=True,
    capabilities=["text", "code"]
)

AIModel.objects.create(
    name="Gemini Pro",
    provider="Google",
    model_code="gemini-pro",
    is_active=True,
    capabilities=["text"]
)

# Verify
from ai_model.models import AIModel
print(f"Total models: {AIModel.objects.filter(is_active=True).count()}")
# Should show at least 2 models for random selection to work
```

## Fix 3: Update Locustfile for Better Error Handling

Create an updated locustfile with better error handling:

```python
# backend/load_tests/locustfile_debug.py
from locust import HttpUser, task, between
import json
import uuid
import random

class ArenaUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Called when a user starts - authenticate once"""
        print(f"Starting user on host: {self.host}")

        # Authenticate
        with self.client.post(
            "/auth/anonymous/",
            json={},
            catch_response=True
        ) as response:
            if response.status_code in [200, 201]:
                auth_data = response.json()
                self.token = auth_data.get('tokens', {}).get('access')
                if not self.token:
                    response.failure("No access token in response")
                    print(f"Auth response: {response.text}")
                else:
                    print(f"Authenticated successfully")
            else:
                response.failure(f"Auth failed: {response.status_code}")
                print(f"Auth error: {response.text}")

    @task
    def test_health(self):
        """Simple health check"""
        with self.client.get("/health/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
                print(f"Health response: {response.text}")

    @task(3)  # Weight: 3x more likely than health check
    def create_session_and_check(self):
        """Create session without streaming"""
        if not hasattr(self, 'token'):
            return  # Skip if not authenticated

        # Create session
        with self.client.post(
            "/sessions/",
            json={
                "mode": "random",
                "model_a_id": None,
                "model_b_id": None
            },
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
            name="/sessions/ [create]"
        ) as response:
            if response.status_code in [200, 201]:
                session_data = response.json()
                session_id = session_data.get("id")

                if session_id:
                    response.success()
                    print(f"Session created: {session_id}")
                else:
                    response.failure("No session ID in response")
                    print(f"Session response: {response.text}")
            else:
                response.failure(f"Failed to create session: {response.status_code}")
                print(f"Error: {response.text}")
```

**Run debug version:**

```bash
cd backend/load_tests
locust -f locustfile_debug.py --host=http://localhost --users 5 --spawn-rate 1 --run-time 30s --headless
```

## Fix 4: Check Backend Logs During Test

Run tests while watching backend logs:

```bash
# Terminal 1: Watch logs
docker-compose -f docker-compose.loadbalanced.yml logs -f web-1 web-2 web-3

# Terminal 2: Run test
cd backend/load_tests
locust -f locustfile.py --host=http://localhost --users 5 --spawn-rate 1 --run-time 30s --headless
```

Look for errors in logs like:
- Authentication errors
- Database errors
- Model not found errors
- CORS errors

## Fix 5: Test Individual Endpoints First

Before running full load test, test endpoints individually:

```bash
# 1. Health check
curl http://localhost/health/
# Should return: {"status":"healthy",...}

# 2. Anonymous auth
curl -X POST http://localhost/auth/anonymous/ \
    -H "Content-Type: application/json" \
    -d '{}'
# Should return: {"tokens":{"access":"...","refresh":"..."}}

# 3. List models
curl http://localhost/models/
# Should return: [{"id":"...","name":"GPT-4",...},...]

# 4. Create session (using token from step 2)
curl -X POST http://localhost/sessions/ \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer YOUR_TOKEN_HERE" \
    -d '{"mode":"random","model_a_id":null,"model_b_id":null}'
# Should return: {"id":"...","model_a":{...},"model_b":{...}}
```

If any of these fail, fix that endpoint before running load tests.

## Common Error Patterns

### Error: "Connection refused"

**Issue:** Backend not accessible from locust

**Fix:**
```bash
# Ensure containers are running
docker-compose -f docker-compose.loadbalanced.yml ps

# Test connectivity
curl http://localhost/health/

# If localhost doesn't work, use container IP
docker inspect arena-web-1 | grep IPAddress
```

### Error: "401 Unauthorized"

**Issue:** Authentication failing

**Fix:**
```bash
# Test auth endpoint
curl -X POST http://localhost/auth/anonymous/ -H "Content-Type: application/json" -d '{}'

# Check if JWT token is being created
docker-compose -f docker-compose.loadbalanced.yml logs web-1 | grep -i auth
```

### Error: "Missing model IDs"

**Issue:** No models in database

**Fix:** See "Create test models" section above

### Error: "CORS error"

**Issue:** Cross-origin requests blocked

**Fix:** CORS is already configured in settings, but verify:
```python
# Check settings.py has:
CORS_ORIGIN_ALLOW_ALL = True
# Or add locust origin:
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8089",  # Locust web UI
]
```

## Recommended Test Progression

**Level 1: Basic Health Check**
```bash
locust -f locustfile_debug.py --host=http://localhost --users 1 --spawn-rate 1 --run-time 10s --headless
```

**Level 2: Light Load**
```bash
locust -f locustfile.py --host=http://localhost --users 10 --spawn-rate 2 --run-time 1m --headless
```

**Level 3: Medium Load**
```bash
locust -f locustfile.py --host=http://localhost --users 100 --spawn-rate 10 --run-time 5m --headless
```

**Level 4: Heavy Load**
```bash
locust -f locustfile.py --host=http://localhost --users 500 --spawn-rate 25 --run-time 10m --headless
```

**Level 5: Stress Test**
```bash
locust -f locustfile.py --host=http://localhost --users 1000 --spawn-rate 50 --run-time 10m --headless
```

## Troubleshooting Checklist

- [ ] Backend containers are running: `docker-compose ps`
- [ ] Health endpoint works: `curl http://localhost/health/`
- [ ] Auth endpoint works: `curl -X POST http://localhost/auth/anonymous/ -H "Content-Type: application/json" -d '{}'`
- [ ] At least 2 AI models exist: `curl http://localhost/models/ | jq length`
- [ ] Using correct host URL: `http://localhost` or `https://backend.arena.ai4bharat.org`
- [ ] Locust can reach backend: `curl http://localhost/health/` from same machine as locust
- [ ] No errors in backend logs: `docker-compose logs web-1 | grep -i error`

---

**Quick Fix:**
```bash
# 1. Ensure models exist
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell
# (create models as shown above)

# 2. Run simple test
cd backend/load_tests
locust -f locustfile.py --host=http://localhost --users 5 --spawn-rate 1 --run-time 30s --headless

# 3. Check results and logs
docker-compose -f docker-compose.loadbalanced.yml logs web-1 | tail -50
```
