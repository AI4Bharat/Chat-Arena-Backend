# Security Remediation Issues

This file contains GitHub issues for tracking security remediation.
To create these issues, authenticate with GitHub CLI (`gh auth login`) and run the provided script.

---

## How to Create These Issues

### Option 1: Using the provided script
```bash
# First authenticate
gh auth login

# Then run the script
./create-security-issues.sh
```

### Option 2: Create manually via GitHub web interface
Copy each issue below and create it at:
https://github.com/AI4Bharat/Chat-Arena-Backend/issues/new

---

## CRITICAL PRIORITY ISSUES

### Issue 1: [CRITICAL] Rotate SECRET_KEY and move to environment variable
**Labels:** `security`, `critical`, `P0`

**Description:**
The Django SECRET_KEY is currently hardcoded in settings.py with an insecure value. This key is used for:
- JWT token signing
- Session cookie signing
- CSRF token generation
- WebSocket message encryption

**Current State:**
```python
SECRET_KEY = "django-insecure-@r7r$^v&pkqi*%plz(obg#2yt0hie(^-*3t1@j28v+o0fly@-#"
```

**Required Actions:**
- [x] Update settings.py to read SECRET_KEY from environment variable (DONE)
- [ ] Generate new production SECRET_KEY
- [ ] Update all deployment environments with new key
- [ ] Invalidate all existing sessions and tokens
- [ ] Update .env files in all deployments

**References:**
- File: `backend/arena_backend/settings.py:29`
- OWASP: A02:2021 - Cryptographic Failures

---

### Issue 2: [CRITICAL] Disable DEBUG mode in production
**Labels:** `security`, `critical`, `P0`

**Description:**
DEBUG=True is currently set, which exposes sensitive information in error pages including:
- Full stack traces
- Environment variables
- Database queries
- File paths

**Required Actions:**
- [x] Update settings.py to read DEBUG from environment variable (DONE)
- [ ] Verify DEBUG=False in all production deployments
- [ ] Set up proper error logging to replace debug info

**References:**
- File: `backend/arena_backend/settings.py:32`

---

### Issue 3: [CRITICAL] Fix CORS configuration - remove CORS_ORIGIN_ALLOW_ALL
**Labels:** `security`, `critical`, `P0`

**Description:**
`CORS_ORIGIN_ALLOW_ALL = True` combined with `CORS_ALLOW_CREDENTIALS = True` allows any website to make authenticated requests on behalf of users.

**Required Actions:**
- [x] Remove CORS_ORIGIN_ALLOW_ALL from settings.py (DONE)
- [ ] Verify CORS_ALLOWED_ORIGINS contains only legitimate origins
- [ ] Test that frontend applications still work correctly

**References:**
- File: `backend/arena_backend/settings.py:109`
- OWASP: A01:2021 - Broken Access Control

---

### Issue 4: [CRITICAL] Fix IDOR vulnerability in conversation_path endpoint
**Labels:** `security`, `critical`, `P0`, `vulnerability`

**Description:**
The `/api/messages/conversation_path/` endpoint retrieves messages without verifying session ownership, allowing unauthorized access to any user's conversations.

**Vulnerable Code:**
```python
start_message = Message.objects.get(id=start_id)  # No ownership check
end_message = Message.objects.get(id=end_id)      # No ownership check
```

**Required Actions:**
- [ ] Add `session__user=request.user` filter to message queries
- [ ] Add unit tests for authorization
- [ ] Audit other endpoints for similar issues

**References:**
- File: `backend/message/views.py:936-962`
- OWASP: A01:2021 - Broken Access Control

---

### Issue 5: [CRITICAL] Implement input sanitization for LLM prompts
**Labels:** `security`, `critical`, `P0`

**Description:**
User input is passed directly to AI models without sanitization, enabling prompt injection attacks.

**Required Actions:**
- [ ] Create input sanitization utility function
- [ ] Implement pattern detection for injection attempts
- [ ] Add input length limits
- [ ] Sanitize document and audio transcription content
- [ ] Add unit tests for sanitization

**References:**
- File: `backend/message/views.py:192-242`
- Related: OWASP LLM Top 10 - Prompt Injection

---

### Issue 6: [CRITICAL] Secure Redis with authentication
**Labels:** `security`, `critical`, `P0`, `infrastructure`

**Description:**
Redis is configured without password authentication, allowing unauthorized access to session data and cache.

**Required Actions:**
- [x] Add `requirepass` to Redis command in docker-compose.yml (DONE)
- [x] Update settings.py to support Redis password (DONE)
- [ ] Generate strong Redis password for each environment
- [ ] Update all deployments with new Redis password
- [ ] Change Redis port from external to internal exposure

**References:**
- File: `docker-compose.yml:50-54`
- File: `backend/arena_backend/settings.py:252-267`

---

### Issue 7: [CRITICAL] Remove Docker socket mount from cron container
**Labels:** `security`, `critical`, `P0`, `infrastructure`

**Description:**
The cron container has `/var/run/docker.sock` mounted, allowing container escape and host compromise if the container is breached.

**Required Actions:**
- [x] Remove docker.sock volume mount (DONE)
- [ ] Implement alternative scheduling mechanism
- [ ] Test cron functionality still works

**References:**
- File: `docker-compose.yml:34-35`

---

### Issue 8: [CRITICAL] Implement rate limiting on authentication endpoints
**Labels:** `security`, `critical`, `P0`

**Description:**
Authentication endpoints have no rate limiting, enabling brute force and credential stuffing attacks.

**Required Actions:**
- [x] Add throttle classes to REST_FRAMEWORK settings (DONE)
- [ ] Add specific AuthRateThrottle to auth views
- [ ] Configure appropriate rates per endpoint
- [ ] Add monitoring for rate limit violations

**References:**
- File: `backend/user/views.py`

---

### Issue 9: [CRITICAL] Implement PII encryption at rest
**Labels:** `security`, `critical`, `P0`, `gdpr`

**Description:**
User PII (email, phone number, display name) is stored in plaintext in the database.

**Required Actions:**
- [ ] Install django-fernet-fields or similar encryption library
- [ ] Create migration to encrypt existing PII
- [ ] Update User model to use encrypted fields
- [ ] Test that application still functions correctly

**References:**
- File: `backend/user/models.py:14-18`
- GDPR: Article 32 - Security of processing

---

### Issue 10: [CRITICAL] Fix PostgreSQL trust authentication in local docker-compose
**Labels:** `security`, `critical`, `P0`, `infrastructure`

**Description:**
`POSTGRES_HOST_AUTH_METHOD=trust` allows unauthenticated database access.

**Required Actions:**
- [x] Update docker-compose-local.yml with password authentication (DONE)
- [ ] Update local development documentation

**References:**
- File: `docker-compose-local.yml:8`

---

## HIGH PRIORITY ISSUES

### Issue 11: [HIGH] Add HTTPS enforcement settings
**Labels:** `security`, `high`, `P1`

**Description:**
Missing HTTPS enforcement settings allow man-in-the-middle attacks.

**Required Actions:**
- [x] Add SECURE_SSL_REDIRECT, SECURE_HSTS_SECONDS settings (DONE)
- [ ] Enable SECURE_SSL_REDIRECT=True in production
- [ ] Test that HTTP redirects work correctly

---

### Issue 12: [HIGH] Add security headers to nginx
**Labels:** `security`, `high`, `P1`, `infrastructure`

**Description:**
Missing security headers: X-Frame-Options, X-Content-Type-Options, Content-Security-Policy.

**Required Actions:**
- [ ] Add security headers to nginx configuration
- [ ] Test headers with security scanner

---

### Issue 13: [HIGH] Fix Google API key in URL
**Labels:** `security`, `high`, `P1`

**Description:**
Google API key is passed in URL query parameter instead of header, exposing it in logs.

**Required Actions:**
- [ ] Move API key to Authorization header
- [ ] Test Google API integration still works

**References:**
- File: `backend/ai_model/providers/google_provider.py:45`

---

### Issue 14: [HIGH] Implement cost controls for AI APIs
**Labels:** `security`, `high`, `P1`

**Description:**
No rate limiting or cost controls for AI API calls, enabling abuse and excessive charges.

**Required Actions:**
- [ ] Implement per-user API call limits
- [ ] Add cost tracking and alerting
- [ ] Create AI-specific throttle class

---

### Issue 15: [HIGH] Implement GDPR data deletion endpoint
**Labels:** `security`, `high`, `P1`, `gdpr`

**Description:**
No endpoint for users to request data deletion, violating GDPR right to erasure.

**Required Actions:**
- [ ] Create DELETE /api/users/me/ endpoint
- [ ] Implement cascade deletion of all user data
- [ ] Add audit logging for deletions

---

### Issue 16: [HIGH] Reduce JWT token lifetimes
**Labels:** `security`, `high`, `P1`

**Description:**
Access token (60min) and refresh token (7 days) lifetimes are too long.

**Required Actions:**
- [x] Reduce access token to 15 minutes (DONE)
- [x] Reduce refresh token to 24 hours (DONE)
- [ ] Test that token refresh works correctly

---

### Issue 17: [HIGH] Add audit logging
**Labels:** `security`, `high`, `P1`

**Description:**
No audit trail for security-sensitive operations.

**Required Actions:**
- [x] Add LOGGING configuration to settings.py (DONE)
- [ ] Implement audit logging for auth events
- [ ] Implement audit logging for data access
- [ ] Set up log aggregation and alerting

---

### Issue 18: [HIGH] Fix path traversal vulnerability in document extraction
**Labels:** `security`, `high`, `P1`, `vulnerability`

**Description:**
Document paths (doc_path, image_path, audio_path) are not validated, allowing potential path traversal attacks.

**Required Actions:**
- [ ] Add path validation to document extraction
- [ ] Whitelist allowed paths
- [ ] Add unit tests

**References:**
- File: `backend/message/document_utils.py:21-31`

---

## MEDIUM PRIORITY ISSUES

### Issue 19: [MEDIUM] Restrict API documentation access
**Labels:** `security`, `medium`, `P2`

**Description:**
Swagger/ReDoc endpoints are publicly accessible.

**Required Actions:**
- [ ] Restrict API docs to authenticated admin users
- [ ] Hide in production or require authentication

---

### Issue 20: [MEDIUM] Fix WebSocket token in query string
**Labels:** `security`, `medium`, `P2`

**Description:**
WebSocket authentication token passed in query string is logged in access logs.

**Required Actions:**
- [ ] Move token to subprotocol or header
- [ ] Update frontend to use new auth method

---

### Issue 21: [MEDIUM] Add schema validation for JSONFields
**Labels:** `security`, `medium`, `P2`

**Description:**
JSONField inputs (metadata, preferences, attachments) have no schema validation.

**Required Actions:**
- [ ] Add Pydantic or similar schema validation
- [ ] Update serializers with validation

---

### Issue 22: [MEDIUM] Update Docker base images
**Labels:** `security`, `medium`, `P2`, `infrastructure`

**Description:**
Some Docker base images are outdated (certbot v1.29, alpine 3.16).

**Required Actions:**
- [ ] Update certbot to v2.x
- [ ] Update alpine to 3.19+
- [ ] Update nginx to 1.25+
- [ ] Test all containers after update

---

### Issue 23: [MEDIUM] Add request timeouts to AI API calls
**Labels:** `security`, `medium`, `P2`

**Description:**
No timeout configuration for AI API requests, risking resource exhaustion.

**Required Actions:**
- [ ] Add timeout parameter to all AI API calls
- [ ] Implement retry with exponential backoff

---

### Issue 24: [MEDIUM] Implement proper error handling
**Labels:** `security`, `medium`, `P2`

**Description:**
Error messages expose internal details to clients.

**Required Actions:**
- [ ] Create standardized error response format
- [ ] Remove detailed error messages from production responses
- [ ] Log detailed errors server-side only

---

## Tracking Progress

- [ ] All CRITICAL issues resolved
- [ ] All HIGH issues resolved
- [ ] All MEDIUM issues resolved
- [ ] Security re-audit completed
- [ ] Penetration test scheduled
