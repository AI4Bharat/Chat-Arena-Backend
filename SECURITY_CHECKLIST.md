# Security Remediation Checklist

## Quick Reference Card

| Priority | Timeline | Issues | Status |
|----------|----------|--------|--------|
| P0 - CRITICAL | 24-48 hours | 15 | In Progress |
| P1 - HIGH | 1 week | 24 | Pending |
| P2 - MEDIUM | 2-4 weeks | 22 | Pending |
| P3 - LOW | 1-2 months | 12 | Pending |

---

## Phase 1: CRITICAL (Complete within 24-48 hours)

### Secrets & Configuration

- [x] **C1.** Move SECRET_KEY to environment variable
  - File: `backend/arena_backend/settings.py`
  - Status: Code updated, needs deployment

- [x] **C2.** Disable DEBUG mode via environment variable
  - File: `backend/arena_backend/settings.py`
  - Status: Code updated, verify in production

- [x] **C3.** Remove CORS_ORIGIN_ALLOW_ALL
  - File: `backend/arena_backend/settings.py`
  - Status: Code updated

- [ ] **C4.** Generate new SECRET_KEY for production
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```

- [ ] **C5.** Update production .env with new secrets
  - [ ] SECRET_KEY
  - [ ] REDIS_PASSWORD
  - [ ] DB_PASSWORD
  - [ ] CHANNEL_ENCRYPTION_KEY

### Infrastructure Security

- [x] **C6.** Remove Docker socket mount from cron
  - File: `docker-compose.yml`
  - Status: Code updated

- [x] **C7.** Add Redis authentication
  - Files: `docker-compose.yml`, `docker-compose-local.yml`
  - Status: Code updated, needs new password

- [x] **C8.** Fix PostgreSQL trust authentication
  - File: `docker-compose-local.yml`
  - Status: Code updated

- [ ] **C9.** Restart all containers with new configuration
  ```bash
  docker-compose down
  docker-compose up -d --build
  ```

### Vulnerability Fixes

- [ ] **C10.** Fix IDOR in conversation_path endpoint
  - File: `backend/message/views.py:936-962`
  - Add: `session__user=request.user` to queries

- [ ] **C11.** Add input sanitization for LLM prompts
  - File: `backend/message/views.py`
  - Create: Input sanitization utility

- [x] **C12.** Add rate limiting to REST_FRAMEWORK
  - File: `backend/arena_backend/settings.py`
  - Status: Code updated

- [ ] **C13.** Add rate limiting to auth views
  - File: `backend/user/views.py`
  - Add: `throttle_classes = [AuthRateThrottle]`

### Verification Steps

- [ ] **V1.** Verify DEBUG=False in production
  ```bash
  curl -I https://backend.arena.ai4bharat.org/nonexistent/
  # Should return 404, not debug page
  ```

- [ ] **V2.** Verify CORS configuration
  ```bash
  curl -H "Origin: https://evil.com" \
       -H "Access-Control-Request-Method: GET" \
       -I https://backend.arena.ai4bharat.org/api/
  # Should NOT include Access-Control-Allow-Origin: https://evil.com
  ```

- [ ] **V3.** Verify Redis requires authentication
  ```bash
  redis-cli -h redis-host -p 6379 PING
  # Should return NOAUTH error
  ```

---

## Phase 2: HIGH (Complete within 1 week)

### Security Headers

- [ ] **H1.** Add security headers to nginx
  ```nginx
  add_header X-Frame-Options "DENY" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-XSS-Protection "1; mode=block" always;
  add_header Content-Security-Policy "default-src 'self';" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  ```

- [x] **H2.** Add HTTPS enforcement settings
  - File: `backend/arena_backend/settings.py`
  - Status: Code updated, enable in production

- [ ] **H3.** Enable SECURE_SSL_REDIRECT=True in production

### Authentication

- [x] **H4.** Reduce JWT token lifetimes
  - Access: 60min → 15min ✓
  - Refresh: 7 days → 24 hours ✓

- [ ] **H5.** Add auth-specific rate throttle
  ```python
  class AuthRateThrottle(AnonRateThrottle):
      rate = '5/minute'
  ```

- [ ] **H6.** Fix WebSocket token passing (move from query string)

### API Security

- [ ] **H7.** Fix Google API key in URL → header
  - File: `backend/ai_model/providers/google_provider.py:45`

- [ ] **H8.** Add request timeouts to all AI API calls

- [ ] **H9.** Implement cost controls for AI APIs
  - Per-user limits
  - Daily spending caps

- [ ] **H10.** Sanitize error messages returned to clients

### Data Protection

- [ ] **H11.** Implement PII encryption
  - Install: `django-fernet-fields`
  - Migrate: email, phone_number fields

- [ ] **H12.** Implement GDPR data deletion endpoint
  - Endpoint: `DELETE /api/users/me/`

- [ ] **H13.** Implement data export endpoint
  - Endpoint: `GET /api/users/me/export/`

### Logging & Monitoring

- [x] **H14.** Add logging configuration
  - Status: Code updated

- [ ] **H15.** Implement audit logging for auth events

- [ ] **H16.** Set up log aggregation and alerting

### Vulnerability Fixes

- [ ] **H17.** Fix path traversal in document extraction
  - File: `backend/message/document_utils.py`

- [ ] **H18.** Add file upload validation (magic bytes)

- [ ] **H19.** Fix multi-tenancy isolation

---

## Phase 3: MEDIUM (Complete within 2-4 weeks)

### API Security

- [ ] **M1.** Restrict Swagger/ReDoc to admin users

- [ ] **M2.** Add schema validation for JSONFields

- [ ] **M3.** Add input bounds checking (limit, days, etc.)

- [ ] **M4.** Fix feedback access control

### Infrastructure

- [ ] **M5.** Update Docker base images
  - certbot: v1.29 → v2.x
  - alpine: 3.16 → 3.19+
  - nginx: 1.23 → 1.25+

- [ ] **M6.** Add network isolation in Docker
  ```yaml
  networks:
    internal:
      internal: true
    web:
  ```

- [ ] **M7.** Add health checks to Docker services

### Code Quality

- [ ] **M8.** Replace print() statements with logging

- [ ] **M9.** Add proper exception handling

- [ ] **M10.** Fix race conditions in message positioning

### Compliance

- [ ] **M11.** Add consent management

- [ ] **M12.** Implement data retention policies

- [ ] **M13.** Add privacy policy link

---

## Phase 4: LOW (Complete within 1-2 months)

- [ ] **L1.** Remove API key mentions from comments
- [ ] **L2.** Clean up commented code
- [ ] **L3.** Add stronger display name validation
- [ ] **L4.** Improve email masking algorithm
- [ ] **L5.** Increase anonymous cleanup frequency
- [ ] **L6.** Add secrets management (Vault/AWS Secrets Manager)
- [ ] **L7.** Set explicit volume permissions
- [ ] **L8.** Add consistent restart policies

---

## Post-Remediation Tasks

### Testing

- [ ] **T1.** Run security scanner (OWASP ZAP, Burp Suite)
- [ ] **T2.** Run dependency vulnerability check
  ```bash
  pip-audit
  npm audit  # if applicable
  ```
- [ ] **T3.** Manual penetration testing
- [ ] **T4.** GDPR compliance review

### Documentation

- [ ] **D1.** Update security documentation
- [ ] **D2.** Document incident response procedures
- [ ] **D3.** Update deployment runbook

### Ongoing

- [ ] **O1.** Set up automated dependency updates
- [ ] **O2.** Schedule quarterly security reviews
- [ ] **O3.** Set up security monitoring/alerting

---

## Quick Commands Reference

### Generate Secrets
```bash
# Django SECRET_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Strong random password
openssl rand -base64 32
```

### Deploy Updates
```bash
cd /c/Users/bikss/AI4B/Chat-Arena/Chat-Arena-Backend

# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose up -d --build

# Check logs
docker-compose logs -f web
```

### Verify Security
```bash
# Check for exposed debug info
curl -I https://your-domain.com/nonexistent/

# Check CORS
curl -H "Origin: https://evil.com" -I https://your-domain.com/api/

# Check security headers
curl -I https://your-domain.com/ | grep -E "(X-Frame|X-Content|Content-Security)"
```

---

## Files Modified in This Audit

| File | Changes |
|------|---------|
| `backend/arena_backend/settings.py` | SECRET_KEY, DEBUG, CORS, rate limiting, JWT, security headers, logging |
| `docker-compose.yml` | Redis auth, removed Docker socket |
| `docker-compose-local.yml` | PostgreSQL auth, Redis auth |
| `.gitignore` | Added sensitive file patterns |
| `.env.example` | Created with all required variables |
| `SECURITY_AUDIT_REPORT.md` | Full audit report |
| `SECURITY_ISSUES.md` | GitHub issues for tracking |
| `SECURITY_CHECKLIST.md` | This file |
| `create-security-issues.sh` | Script to create GitHub issues |

---

## Contact & Escalation

For security emergencies:
1. Disable affected endpoints immediately
2. Rotate compromised credentials
3. Contact security team
4. Document incident timeline

---

*Last Updated: January 15, 2026*
*Audit Performed By: Claude Code Security Analysis*
