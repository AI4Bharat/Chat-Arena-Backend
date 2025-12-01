# Static Files (CSS) Not Loading Fix

## Issue
When visiting `backend.arena.ai4bharat.org`, CSS doesn't load properly (unstyled pages).

## Root Causes

1. **Static files not collected** - Django hasn't collected static files
2. **Nginx not serving static files** - Static file location misconfigured
3. **HTTPS/HTTP mixed content** - Page loads via HTTP but CSS via HTTPS (or vice versa)
4. **CORS issues** - Static files blocked by CORS policy

## Fix 1: Collect Static Files

Django needs to collect all static files to one location for nginx to serve them.

```bash
# Collect static files
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py collectstatic --noinput

# Output should show:
# X static files copied to '/usr/src/backend/static'

# Verify files were collected
docker-compose -f docker-compose.loadbalanced.yml exec web-1 ls -la /usr/src/backend/static/

# Should show folders like:
# admin/  (Django admin CSS/JS)
# rest_framework/  (DRF browsable API CSS)
# drf-yasg/  (Swagger UI CSS)
```

## Fix 2: Verify Nginx Static File Configuration

Check nginx is serving static files:

```bash
# Test static file endpoint
curl -I http://localhost/static/admin/css/base.css

# Should return:
# HTTP/1.1 200 OK
# Content-Type: text/css

# If 404, nginx isn't finding static files
```

**Check nginx configuration:**

```bash
# View nginx config
docker-compose -f docker-compose.loadbalanced.yml exec nginx cat /etc/nginx/vhosts/backend.arena.ai4bharat.org.conf | grep -A 5 "location /static"

# Should see:
# location /static/ {
#     alias /usr/src/backend/static/;
#     expires 30d;
#     add_header Cache-Control "public, immutable";
# }
```

## Fix 3: Check Static Volume is Mounted

Verify the static_volume is properly shared between Django and nginx:

```bash
# Check Django container has static files
docker-compose -f docker-compose.loadbalanced.yml exec web-1 ls /usr/src/backend/static/admin/

# Check nginx container has access
docker-compose -f docker-compose.loadbalanced.yml exec nginx ls /usr/src/backend/static/admin/

# Both should show the same files
```

## Fix 4: Update Django Static Files Settings

Ensure Django settings are correct for static files:

```python
# In backend/arena_backend/settings.py

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'  # Where collectstatic puts files

# If you have additional static directories
STATICFILES_DIRS = [
    # BASE_DIR / 'custom_static',
]
```

## Fix 5: Fix HTTPS/HTTP Mixed Content

If page loads on HTTPS but tries to load CSS from HTTP (or vice versa):

```bash
# Check if static URLs use correct protocol

# In settings.py, ensure:
# For production with HTTPS:
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = True

# For development/testing with HTTP:
# SECURE_SSL_REDIRECT = False
```

## Fix 6: Clear Browser Cache

Sometimes browsers cache the broken CSS:

```bash
# Clear browser cache:
# Chrome: Ctrl+Shift+Delete → Clear browsing data
# Firefox: Ctrl+Shift+Delete → Clear recent history
# Safari: Cmd+Option+E

# Or use incognito/private mode
```

## Fix 7: Verify Static Files Permissions

```bash
# Check permissions on static files
docker-compose -f docker-compose.loadbalanced.yml exec web-1 ls -la /usr/src/backend/static/

# Should be readable by nginx user
# If permission issues:
docker-compose -f docker-compose.loadbalanced.yml exec web-1 chmod -R 755 /usr/src/backend/static/
```

## Testing Static Files

### Test 1: Admin CSS

```bash
# Visit admin page
curl http://localhost/admin/

# Check response includes CSS links:
curl http://localhost/admin/ | grep -o 'href="[^"]*\.css'

# Should show:
# href="/static/admin/css/base.css"
# href="/static/admin/css/login.css"

# Test CSS file directly
curl -I http://localhost/static/admin/css/base.css

# Should return 200 OK
```

### Test 2: Swagger UI CSS

```bash
# Visit Swagger UI
curl http://localhost/swagger/

# Check for CSS
curl http://localhost/swagger/ | grep -o 'href="[^"]*\.css'

# Test swagger CSS directly
curl -I http://localhost/static/drf-yasg/swagger-ui.css

# Should return 200 OK
```

### Test 3: DRF Browsable API CSS

```bash
# Visit API endpoint in browser
curl http://localhost/models/

# Check for DRF CSS
curl http://localhost/models/ | grep -o 'href="[^"]*\.css'

# Should show:
# href="/static/rest_framework/css/bootstrap.min.css"
# href="/static/rest_framework/css/default.css"
```

## Complete Fix Procedure

**Step 1: Collect static files**
```bash
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py collectstatic --noinput
```

**Step 2: Verify files collected**
```bash
docker-compose -f docker-compose.loadbalanced.yml exec web-1 ls -la /usr/src/backend/static/
```

**Step 3: Verify nginx can see files**
```bash
docker-compose -f docker-compose.loadbalanced.yml exec nginx ls -la /usr/src/backend/static/
```

**Step 4: Test static file serving**
```bash
curl -I http://localhost/static/admin/css/base.css
```

**Step 5: Restart nginx (if needed)**
```bash
docker-compose -f docker-compose.loadbalanced.yml restart nginx
```

**Step 6: Test in browser**
```bash
# Open browser and visit:
http://localhost/admin/
http://localhost/swagger/
http://localhost/api/docs/

# All should have proper styling
```

## If Still Not Working

### Check Nginx Logs

```bash
# Watch nginx access logs
docker-compose -f docker-compose.loadbalanced.yml logs -f nginx | grep static

# Look for:
# GET /static/admin/css/base.css HTTP/1.1" 200  (success)
# GET /static/admin/css/base.css HTTP/1.1" 404  (not found)
```

### Check Browser Console

```bash
# Open browser Developer Tools (F12)
# Check Console tab for errors like:
# - "Failed to load resource: net::ERR_FILE_NOT_FOUND"
# - "CORS policy: No 'Access-Control-Allow-Origin' header"
# - "Mixed Content: The page was loaded over HTTPS, but requested an insecure..."
```

### Verify Static URL in Django

```bash
# Open Django shell
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell

# In shell:
from django.conf import settings
print(f"STATIC_URL: {settings.STATIC_URL}")
print(f"STATIC_ROOT: {settings.STATIC_ROOT}")

# Should show:
# STATIC_URL: /static/
# STATIC_ROOT: /usr/src/backend/static
```

## Deployment Script Update

Update your deployment script to always collect static files:

```bash
# In deploy-loadbalanced.sh, add after migrations:

echo "Collecting static files..."
docker-compose -f docker-compose.loadbalanced.yml exec -T web-1 python manage.py collectstatic --noinput || echo "Static files already collected"
```

## Django Admin Styling

If Django admin is specifically not styled:

```bash
# Verify Django admin static files
docker-compose -f docker-compose.loadbalanced.yml exec web-1 ls /usr/src/backend/static/admin/css/

# Should show:
# base.css
# login.css
# dashboard.css
# etc.

# If empty, reinstall Django:
docker-compose -f docker-compose.loadbalanced.yml exec web-1 pip install --force-reinstall Django==5.2.6

# Then recollect static
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py collectstatic --noinput
```

## Swagger/ReDoc Styling

If Swagger UI is not styled:

```bash
# Check drf-yasg static files
docker-compose -f docker-compose.loadbalanced.yml exec web-1 ls /usr/src/backend/static/drf-yasg/

# Should show swagger-ui files

# If missing, reinstall:
docker-compose -f docker-compose.loadbalanced.yml exec web-1 pip install --force-reinstall drf-yasg==1.21.11

# Recollect static
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py collectstatic --noinput
```

---

**Quick Fix Summary:**

1. **Collect static files:** `docker-compose exec web-1 python manage.py collectstatic --noinput`
2. **Verify nginx serves them:** `curl -I http://localhost/static/admin/css/base.css`
3. **Clear browser cache** and reload page
4. **Check browser console** for specific errors (F12 → Console tab)

Most likely cause: Static files not collected. Run `collectstatic` and it should fix it!
