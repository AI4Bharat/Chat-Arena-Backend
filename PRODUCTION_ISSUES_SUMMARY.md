# Production Issues - Quick Fix Summary

## Current Status
✅ **Backend is running and functional**
✅ **Frontend connects successfully**
✅ **All endpoints working**

## Three Issues to Fix

### Issue 1: HTTPS/SSL Not Working ⚠️

**Problem:** Backend shows "insecure" warning, opens HTTP instead of HTTPS

**Quick Fix:**

```bash
# 1. Verify DNS points to your server
nslookup backend.arena.ai4bharat.org

# 2. Request Let's Encrypt certificate
docker-compose -f docker-compose.loadbalanced.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    --no-eff-email \
    -d backend.arena.ai4bharat.org

# 3. Nginx automatically detects and uses new certificate

# 4. Test HTTPS
curl -I https://backend.arena.ai4bharat.org/health/
```

**Detailed Guide:** [SSL_CERTIFICATE_FIX.md](SSL_CERTIFICATE_FIX.md)

---

### Issue 2: Locust Tests Failing ⚠️

**Problem:** Load tests show all endpoints failing

**Quick Fix:**

```bash
# 1. Ensure AI models exist (required for tests)
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell

# In Django shell, create at least 2 models:
from ai_model.models import AIModel
AIModel.objects.create(name="GPT-4", provider="OpenAI", model_code="gpt-4", is_active=True, capabilities=["text"])
AIModel.objects.create(name="Claude", provider="Anthropic", model_code="claude-3", is_active=True, capabilities=["text"])
exit()

# 2. Run Locust with HTTP (not HTTPS)
cd backend/load_tests
locust -f locustfile.py --host=http://localhost --users 10 --spawn-rate 2 --run-time 1m --headless

# 3. Check results
# Success rate should be > 95%
```

**Common Issues:**
- ❌ Using HTTPS without valid certificate → Use HTTP for testing
- ❌ No models in database → Create models first
- ❌ Wrong host format → Use `http://localhost` not just `localhost`

**Detailed Guide:** [LOCUST_TEST_FIX.md](LOCUST_TEST_FIX.md)

---

### Issue 3: CSS Not Loading ⚠️

**Problem:** Pages appear unstyled, CSS not loading

**Quick Fix:**

```bash
# 1. Collect static files
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py collectstatic --noinput

# Should output:
# "X static files copied to '/usr/src/backend/static'"

# 2. Verify nginx can serve static files
curl -I http://localhost/static/admin/css/base.css

# Should return: HTTP/1.1 200 OK

# 3. Restart nginx (if needed)
docker-compose -f docker-compose.loadbalanced.yml restart nginx

# 4. Clear browser cache and reload
# Chrome: Ctrl+Shift+Delete
# Or use incognito mode
```

**Test it worked:**
```bash
# Visit admin page - should have styling
curl http://localhost/admin/ | grep "base.css"

# Visit Swagger UI - should have styling
curl http://localhost/swagger/ | grep "swagger-ui.css"
```

**Detailed Guide:** [STATIC_FILES_FIX.md](STATIC_FILES_FIX.md)

---

## Complete Fix Procedure

Run all fixes in order:

```bash
# ===== FIX 1: Static Files (CSS) =====
echo "=== Fixing CSS/Static Files ==="
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py collectstatic --noinput
docker-compose -f docker-compose.loadbalanced.yml restart nginx
echo "✓ Static files collected and nginx restarted"

# ===== FIX 2: Create AI Models =====
echo "=== Creating AI Models for Testing ==="
docker-compose -f docker-compose.loadbalanced.yml exec -T web-1 python manage.py shell <<EOF
from ai_model.models import AIModel
if AIModel.objects.count() == 0:
    AIModel.objects.create(name="GPT-4", provider="OpenAI", model_code="gpt-4", is_active=True, capabilities=["text", "code"])
    AIModel.objects.create(name="Claude 3", provider="Anthropic", model_code="claude-3-sonnet", is_active=True, capabilities=["text", "code"])
    AIModel.objects.create(name="Gemini Pro", provider="Google", model_code="gemini-pro", is_active=True, capabilities=["text"])
    print("Created 3 test models")
else:
    print(f"Already have {AIModel.objects.count()} models")
EOF
echo "✓ Models created or already exist"

# ===== FIX 3: Test Load Balancing =====
echo "=== Running Quick Load Test ==="
cd backend/load_tests
locust -f locustfile.py --host=http://localhost --users 5 --spawn-rate 1 --run-time 30s --headless
echo "✓ Load test completed"

# ===== FIX 4: Request SSL Certificate (Optional - for HTTPS) =====
echo "=== SSL Certificate ==="
echo "To enable HTTPS, run:"
echo "docker-compose -f docker-compose.loadbalanced.yml run --rm certbot certonly --webroot --webroot-path=/var/www/certbot --email your-email@example.com --agree-tos -d backend.arena.ai4bharat.org"
echo "(Requires DNS to point to this server)"
```

## Verification Checklist

After running fixes, verify everything works:

```bash
# ✓ Static files collected
docker-compose -f docker-compose.loadbalanced.yml exec web-1 ls /usr/src/backend/static/admin/css/
# Should show: base.css, login.css, etc.

# ✓ Static files served by nginx
curl -I http://localhost/static/admin/css/base.css
# Should return: HTTP/1.1 200 OK

# ✓ CSS loads in browser
# Visit: http://localhost/admin/ (should have proper styling)

# ✓ AI models exist
curl http://localhost/models/ | jq length
# Should return: 3 or more

# ✓ Load tests pass
cd backend/load_tests
locust -f locustfile.py --host=http://localhost --users 5 --spawn-rate 1 --run-time 10s --headless
# Success rate should be > 90%

# ✓ HTTPS works (after certificate)
curl -I https://backend.arena.ai4bharat.org/health/
# Should return: HTTP/2 200 (no warnings)
```

## Browser Tests

Open browser and test:

1. **Admin Page:** http://localhost/admin/
   - Should have blue header
   - Should have styled login form
   - ✅ CSS loaded correctly

2. **Swagger UI:** http://localhost/swagger/
   - Should have green "Authorize" button
   - Should have interactive API docs
   - ✅ CSS loaded correctly

3. **DRF API:** http://localhost/models/
   - Should have Bootstrap styling
   - Should have navbar at top
   - ✅ CSS loaded correctly

## Troubleshooting

### If CSS still not loading:

```bash
# Check nginx logs
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep static | tail -20

# Check browser console (F12 → Console)
# Look for errors like:
# - 404 Not Found (file not collected)
# - CORS error (CORS issue)
# - Mixed content (HTTP/HTTPS mismatch)

# Force recollect
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py collectstatic --clear --noinput
```

### If Locust tests still failing:

```bash
# Test individual endpoints
curl -X POST http://localhost/auth/anonymous/ -H "Content-Type: application/json" -d '{}'
curl http://localhost/models/

# Check backend logs during test
docker-compose -f docker-compose.loadbalanced.yml logs -f web-1 &
locust -f backend/load_tests/locustfile.py --host=http://localhost --users 1 --spawn-rate 1 --run-time 10s --headless
```

### If SSL certificate request fails:

```bash
# Check DNS
nslookup backend.arena.ai4bharat.org

# Check port 80 is accessible
curl http://backend.arena.ai4bharat.org/.well-known/acme-challenge/test

# Check certbot logs
docker-compose -f docker-compose.loadbalanced.yml logs certbot

# Try staging first (for testing)
docker-compose -f docker-compose.loadbalanced.yml run --rm certbot certonly --webroot --webroot-path=/var/www/certbot --email your-email@example.com --agree-tos --staging -d backend.arena.ai4bharat.org
```

## Performance After Fixes

With all fixes applied, you should see:

**Load Test Results (100 users):**
- ✅ Success rate: > 95%
- ✅ Response time P95: < 500ms
- ✅ Requests per second: 100-200 RPS

**Page Load Times:**
- ✅ Admin page: < 1 second
- ✅ Swagger UI: < 2 seconds
- ✅ API endpoints: < 200ms

**SSL/Security:**
- ✅ HTTPS works without warnings
- ✅ Certificate valid and trusted
- ✅ A+ SSL rating (after Let's Encrypt)

## Documentation Links

- **SSL Fix:** [SSL_CERTIFICATE_FIX.md](SSL_CERTIFICATE_FIX.md)
- **Locust Fix:** [LOCUST_TEST_FIX.md](LOCUST_TEST_FIX.md)
- **Static Files Fix:** [STATIC_FILES_FIX.md](STATIC_FILES_FIX.md)
- **Database Connection:** [DATABASE_CONNECTION_FIX.md](DATABASE_CONNECTION_FIX.md)
- **Nginx Configuration:** [NGINX_FIX.md](NGINX_FIX.md)
- **Setup Troubleshooting:** [SETUP_TROUBLESHOOTING.md](SETUP_TROUBLESHOOTING.md)
- **Phase 1 Guide:** [LOAD_BALANCING_GUIDE.md](LOAD_BALANCING_GUIDE.md)
- **Phase 2 Guide:** [PHASE2_GUIDE.md](PHASE2_GUIDE.md)

---

## Summary

**All three issues are fixable with simple commands:**

1. **CSS:** `python manage.py collectstatic --noinput`
2. **Locust:** Create AI models + use `http://localhost`
3. **HTTPS:** Request Let's Encrypt certificate

**Estimated time to fix all:** 5-10 minutes

**Current status:** System is functional, just needs these finishing touches for production readiness!
