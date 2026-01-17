#!/bin/bash

# =============================================================================
# Security Issues Creation Script
# =============================================================================
# This script creates GitHub issues for security remediation tracking.
#
# Prerequisites:
#   1. GitHub CLI installed: https://cli.github.com/
#   2. Authenticated: gh auth login
#
# Usage:
#   chmod +x create-security-issues.sh
#   ./create-security-issues.sh
# =============================================================================

set -e

# Check if gh is installed and authenticated
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed."
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "Error: Not authenticated with GitHub CLI."
    echo "Run: gh auth login"
    exit 1
fi

REPO="AI4Bharat/Chat-Arena-Backend"

echo "Creating security issues in $REPO..."
echo ""

# Create labels if they don't exist
echo "Creating labels..."
gh label create "security" --description "Security-related issue" --color "d73a4a" --repo "$REPO" 2>/dev/null || true
gh label create "critical" --description "Critical priority" --color "b60205" --repo "$REPO" 2>/dev/null || true
gh label create "high" --description "High priority" --color "d93f0b" --repo "$REPO" 2>/dev/null || true
gh label create "medium" --description "Medium priority" --color "fbca04" --repo "$REPO" 2>/dev/null || true
gh label create "P0" --description "Priority 0 - Immediate" --color "b60205" --repo "$REPO" 2>/dev/null || true
gh label create "P1" --description "Priority 1 - Within 1 week" --color "d93f0b" --repo "$REPO" 2>/dev/null || true
gh label create "P2" --description "Priority 2 - Within 1 month" --color "fbca04" --repo "$REPO" 2>/dev/null || true
gh label create "vulnerability" --description "Security vulnerability" --color "d73a4a" --repo "$REPO" 2>/dev/null || true
gh label create "gdpr" --description "GDPR compliance" --color "5319e7" --repo "$REPO" 2>/dev/null || true
gh label create "infrastructure" --description "Infrastructure related" --color "0052cc" --repo "$REPO" 2>/dev/null || true

echo ""
echo "Creating CRITICAL issues..."

# Issue 1
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Rotate SECRET_KEY and move to environment variable" \
    --label "security,critical,P0" \
    --body "## Description
The Django SECRET_KEY is currently hardcoded in settings.py with an insecure value.

## Impact
- JWT token signing compromised
- Session cookie signing compromised
- CSRF token generation compromised
- WebSocket message encryption compromised

## Required Actions
- [x] Update settings.py to read SECRET_KEY from environment variable (DONE)
- [ ] Generate new production SECRET_KEY
- [ ] Update all deployment environments with new key
- [ ] Invalidate all existing sessions and tokens

## References
- File: \`backend/arena_backend/settings.py:29\`
- OWASP: A02:2021 - Cryptographic Failures"

# Issue 2
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Disable DEBUG mode in production" \
    --label "security,critical,P0" \
    --body "## Description
DEBUG=True is currently set, exposing sensitive information in error pages.

## Required Actions
- [x] Update settings.py to read DEBUG from environment variable (DONE)
- [ ] Verify DEBUG=False in all production deployments
- [ ] Set up proper error logging

## References
- File: \`backend/arena_backend/settings.py:32\`"

# Issue 3
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Fix CORS configuration - remove CORS_ORIGIN_ALLOW_ALL" \
    --label "security,critical,P0" \
    --body "## Description
CORS_ORIGIN_ALLOW_ALL = True allows any website to make authenticated requests.

## Required Actions
- [x] Remove CORS_ORIGIN_ALLOW_ALL from settings.py (DONE)
- [ ] Verify CORS_ALLOWED_ORIGINS contains only legitimate origins
- [ ] Test frontend applications

## References
- File: \`backend/arena_backend/settings.py:109\`"

# Issue 4
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Fix IDOR vulnerability in conversation_path endpoint" \
    --label "security,critical,P0,vulnerability" \
    --body "## Description
The conversation_path endpoint retrieves messages without verifying session ownership.

## Vulnerable Code
\`\`\`python
start_message = Message.objects.get(id=start_id)  # No ownership check
end_message = Message.objects.get(id=end_id)      # No ownership check
\`\`\`

## Required Actions
- [ ] Add session__user=request.user filter to message queries
- [ ] Add unit tests for authorization
- [ ] Audit other endpoints

## References
- File: \`backend/message/views.py:936-962\`"

# Issue 5
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Implement input sanitization for LLM prompts" \
    --label "security,critical,P0" \
    --body "## Description
User input is passed directly to AI models without sanitization, enabling prompt injection.

## Required Actions
- [ ] Create input sanitization utility function
- [ ] Implement pattern detection for injection attempts
- [ ] Add input length limits
- [ ] Sanitize document and audio transcription content

## References
- File: \`backend/message/views.py:192-242\`"

# Issue 6
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Secure Redis with authentication" \
    --label "security,critical,P0,infrastructure" \
    --body "## Description
Redis is configured without password authentication.

## Required Actions
- [x] Add requirepass to Redis command in docker-compose.yml (DONE)
- [x] Update settings.py to support Redis password (DONE)
- [ ] Generate strong Redis password for each environment
- [ ] Update all deployments

## References
- File: \`docker-compose.yml:50-54\`"

# Issue 7
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Remove Docker socket mount from cron container" \
    --label "security,critical,P0,infrastructure" \
    --body "## Description
The cron container has Docker socket mounted, allowing container escape.

## Required Actions
- [x] Remove docker.sock volume mount (DONE)
- [ ] Implement alternative scheduling mechanism
- [ ] Test cron functionality

## References
- File: \`docker-compose.yml:34-35\`"

# Issue 8
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Implement rate limiting on authentication endpoints" \
    --label "security,critical,P0" \
    --body "## Description
Authentication endpoints have no rate limiting.

## Required Actions
- [x] Add throttle classes to REST_FRAMEWORK settings (DONE)
- [ ] Add specific AuthRateThrottle to auth views
- [ ] Configure appropriate rates per endpoint

## References
- File: \`backend/user/views.py\`"

# Issue 9
gh issue create --repo "$REPO" \
    --title "[CRITICAL] Implement PII encryption at rest" \
    --label "security,critical,P0,gdpr" \
    --body "## Description
User PII (email, phone number) is stored in plaintext.

## Required Actions
- [ ] Install django-fernet-fields
- [ ] Create migration to encrypt existing PII
- [ ] Update User model to use encrypted fields
- [ ] Test application functionality

## References
- File: \`backend/user/models.py:14-18\`
- GDPR: Article 32"

echo ""
echo "Creating HIGH priority issues..."

# Issue 10
gh issue create --repo "$REPO" \
    --title "[HIGH] Add security headers to nginx" \
    --label "security,high,P1,infrastructure" \
    --body "## Description
Missing security headers: X-Frame-Options, X-Content-Type-Options, CSP.

## Required Actions
- [ ] Add security headers to nginx configuration
- [ ] Test headers with security scanner"

# Issue 11
gh issue create --repo "$REPO" \
    --title "[HIGH] Fix Google API key in URL" \
    --label "security,high,P1" \
    --body "## Description
Google API key is passed in URL query parameter instead of header.

## Required Actions
- [ ] Move API key to Authorization header
- [ ] Test Google API integration

## References
- File: \`backend/ai_model/providers/google_provider.py:45\`"

# Issue 12
gh issue create --repo "$REPO" \
    --title "[HIGH] Implement GDPR data deletion endpoint" \
    --label "security,high,P1,gdpr" \
    --body "## Description
No endpoint for users to request data deletion (GDPR right to erasure).

## Required Actions
- [ ] Create DELETE /api/users/me/ endpoint
- [ ] Implement cascade deletion of all user data
- [ ] Add audit logging for deletions"

# Issue 13
gh issue create --repo "$REPO" \
    --title "[HIGH] Add audit logging" \
    --label "security,high,P1" \
    --body "## Description
No audit trail for security-sensitive operations.

## Required Actions
- [x] Add LOGGING configuration to settings.py (DONE)
- [ ] Implement audit logging for auth events
- [ ] Implement audit logging for data access
- [ ] Set up log aggregation"

# Issue 14
gh issue create --repo "$REPO" \
    --title "[HIGH] Fix path traversal vulnerability in document extraction" \
    --label "security,high,P1,vulnerability" \
    --body "## Description
Document paths are not validated, allowing potential path traversal.

## Required Actions
- [ ] Add path validation to document extraction
- [ ] Whitelist allowed paths
- [ ] Add unit tests

## References
- File: \`backend/message/document_utils.py:21-31\`"

echo ""
echo "Creating MEDIUM priority issues..."

# Issue 15
gh issue create --repo "$REPO" \
    --title "[MEDIUM] Restrict API documentation access" \
    --label "security,medium,P2" \
    --body "## Description
Swagger/ReDoc endpoints are publicly accessible.

## Required Actions
- [ ] Restrict API docs to authenticated admin users"

# Issue 16
gh issue create --repo "$REPO" \
    --title "[MEDIUM] Fix WebSocket token in query string" \
    --label "security,medium,P2" \
    --body "## Description
WebSocket authentication token in query string is logged in access logs.

## Required Actions
- [ ] Move token to subprotocol or header
- [ ] Update frontend"

# Issue 17
gh issue create --repo "$REPO" \
    --title "[MEDIUM] Add schema validation for JSONFields" \
    --label "security,medium,P2" \
    --body "## Description
JSONField inputs have no schema validation.

## Required Actions
- [ ] Add Pydantic or similar schema validation
- [ ] Update serializers"

# Issue 18
gh issue create --repo "$REPO" \
    --title "[MEDIUM] Update Docker base images" \
    --label "security,medium,P2,infrastructure" \
    --body "## Description
Some Docker base images are outdated.

## Required Actions
- [ ] Update certbot to v2.x
- [ ] Update alpine to 3.19+
- [ ] Update nginx to 1.25+
- [ ] Test all containers"

echo ""
echo "=========================================="
echo "Security issues created successfully!"
echo "View issues at: https://github.com/$REPO/issues"
echo "=========================================="
