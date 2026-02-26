# Rollback Plan - Hybrid WSGI+ASGI Migration

**Emergency Contact:** [DevOps Lead]  
**Rollback Decision Maker:** [Tech Lead]  
**Last Updated:** 2026-02-05

---

## Rollback Triggers

Execute rollback if ANY of the following occur within 2 hours of deployment:

### Critical Triggers (Immediate Rollback)
1. **Error rate > 10%** for any endpoint category
2. **Complete service unavailability** (all endpoints returning 5xx)
3. **Data corruption** detected
4. **Security vulnerability** exposed
5. **Database connection failures** affecting > 50% of requests

### High-Priority Triggers (Rollback within 15 minutes)
1. **P95 latency > 2x baseline** for WSGI endpoints
2. **ASGI containers** crashing repeatedly (> 5 restarts in 10 minutes)
3. **Memory leak** detected (usage > 95% sustained)
4. **Session authentication failures** > 5%
5. **Redis connection failures** > 10 per minute

### Medium-Priority Triggers (Evaluate for Rollback)
1. **Performance degradation** (P95 latency > 1.5x baseline)
2. **WebSocket disconnect rate** > 30%
3. **Cache hit rate** drops > 50%
4. **User complaints** spike (> 10 support tickets in 1 hour)

---

## Rollback Procedure

### Phase 1: Stop Deployment (30 seconds)

\\\ash
# 1. Stop any ongoing deployment
docker-compose stop backend-asgi

# 2. Prevent new deployments
touch /tmp/deployment.lock

# 3. Notify team
echo "ROLLBACK IN PROGRESS" | slack-notify
\\\

---

### Phase 2: Quick Rollback (Configuration Only) - 2 Minutes

**Use if:** No database migrations were run, only container/config changes

\\\ash
# 1. Restore previous Nginx configuration
cd /etc/nginx/
cp nginx.conf.pre-hybrid.bak nginx.conf
nginx -t && nginx -s reload

# 2. Stop ASGI containers
docker-compose stop backend-asgi

# 3. Scale up WSGI containers (if scaled down)
docker-compose up -d --scale backend-wsgi=4

# 4. Verify health
curl -f http://localhost/api/health/ || echo "HEALTH CHECK FAILED"

# 5. Check error logs
docker-compose logs --tail=100 backend-wsgi
\\\

**Expected Result:**
- All traffic routes to WSGI containers
- Streaming endpoints return errors or use WSGI fallback
- CRUD/auth/admin endpoints work normally

---

### Phase 3: Full Rollback (Code + Config) - 5 Minutes

**Use if:** Code changes need to be reverted

\\\ash
# 1. Get previous Git commit
cd /app/Chat-Arena-Backend
PREVIOUS_COMMIT=\
echo "Rolling back to commit: \"

# 2. Checkout previous version
git checkout \

# 3. Rebuild and restart containers
docker-compose build backend-wsgi
docker-compose up -d backend-wsgi

# 4. Stop ASGI containers
docker-compose stop backend-asgi

# 5. Restore Nginx config
cp /etc/nginx/nginx.conf.pre-hybrid.bak /etc/nginx/nginx.conf
nginx -s reload

# 6. Verify deployment
./scripts/smoke-test.sh
\\\

---

### Phase 4: Database Rollback (If Needed) - 10 Minutes

**Use if:** Database migrations were applied and need rollback

⚠️ **WARNING:** Only use if migrations are reversible and tested

\\\ash
# 1. Identify migration to roll back to
docker-compose exec backend-wsgi python manage.py showmigrations

# 2. Roll back migrations
# Example: Roll back to migration 0010
docker-compose exec backend-wsgi python manage.py migrate ai_model 0010
docker-compose exec backend-wsgi python manage.py migrate chat_session 0010
# ... for each affected app

# 3. Verify database state
docker-compose exec postgres psql -U arena_user -d arena_production -c "\\dt"

# 4. Restart containers
docker-compose restart backend-wsgi
\\\

---

### Phase 5: Emergency Fallback (If Above Fails) - 15 Minutes

**Use if:** All other rollback attempts fail

\\\ash
# 1. Stop all application containers
docker-compose down

# 2. Restore from backup
# Restore database backup
docker-compose exec postgres pg_restore -U arena_user -d arena_production /backups/pre-migration.dump

# 3. Deploy last known good version
cd /app/Chat-Arena-Backend
git checkout tags/last-stable-release

# 4. Rebuild and start
docker-compose build
docker-compose up -d

# 5. Run health checks
./scripts/full-health-check.sh
\\\

---

## Rollback Validation Checklist

After executing rollback, verify:

- [ ] All containers are healthy (\docker-compose ps\)
- [ ] Database connection successful
- [ ] Redis connection successful
- [ ] Health endpoint returns 200 (\/api/health/\)
- [ ] Admin panel accessible (\/admin/\)
- [ ] User login works
- [ ] API endpoints return expected data
- [ ] Error rate < 1%
- [ ] P95 latency back to baseline
- [ ] No error spikes in logs

---

## Rollback Scripts

### Script 1: Quick Config Rollback

\\\ash
#!/bin/bash
# rollback-config.sh

set -e

echo "🔄 Starting configuration rollback..."

# Stop ASGI
echo "Stopping ASGI containers..."
docker-compose stop backend-asgi

# Restore Nginx
echo "Restoring Nginx configuration..."
cp /etc/nginx/nginx.conf.backup /etc/nginx/nginx.conf
nginx -t && nginx -s reload

# Scale WSGI
echo "Scaling WSGI containers..."
docker-compose up -d --scale backend-wsgi=4

# Health check
echo "Running health check..."
if curl -f http://localhost/api/health/; then
    echo "✅ Rollback successful"
else
    echo "❌ Rollback failed - manual intervention needed"
    exit 1
fi
\\\

### Script 2: Full Code Rollback

\\\ash
#!/bin/bash
# rollback-full.sh

set -e

BACKUP_COMMIT=\

if [ -z "\" ]; then
    echo "Usage: ./rollback-full.sh <commit-hash>"
    exit 1
fi

echo "🔄 Starting full rollback to \..."

cd /app/Chat-Arena-Backend

# Checkout previous version
git checkout \

# Rebuild
docker-compose build backend-wsgi

# Stop ASGI
docker-compose stop backend-asgi

# Restart WSGI
docker-compose up -d backend-wsgi

# Restore Nginx
cp /etc/nginx/nginx.conf.backup /etc/nginx/nginx.conf
nginx -s reload

# Health check
sleep 5
./scripts/smoke-test.sh

echo "✅ Full rollback complete"
\\\

---

## Configuration Backup Procedure

**Before deployment, backup:**

\\\ash
# 1. Nginx configuration
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.pre-hybrid.bak

# 2. Docker Compose configuration
cp docker-compose.yml docker-compose.yml.backup

# 3. Environment files
cp .env .env.backup

# 4. Git commit hash
git rev-parse HEAD > /tmp/pre-migration-commit.txt

# 5. Database snapshot (optional)
docker-compose exec postgres pg_dump -U arena_user arena_production > /backups/pre-migration-\.sql
\\\

---

## Post-Rollback Actions

### Immediate (Within 1 hour)
1. **Incident Report:** Document what went wrong
2. **Notify Stakeholders:** Email/Slack notification
3. **Log Analysis:** Collect and analyze logs
4. **Metrics Review:** Export metrics from time of failure

### Within 24 hours
1. **Root Cause Analysis:** Identify exact failure cause
2. **Fix Strategy:** Plan how to address the issue
3. **Team Retrospective:** Discuss what went wrong
4. **Update Rollback Plan:** Incorporate lessons learned

### Before Next Deployment
1. **Fix Verified:** Issue fixed and tested in staging
2. **Additional Testing:** More comprehensive tests added
3. **Monitoring Enhanced:** Add alerts for detected issue
4. **Team Alignment:** Everyone understands the fix

---

## Rollback Decision Matrix

| Metric | Value | Action |
|--------|-------|--------|
| Error rate | > 10% | Immediate rollback |
| Error rate | 5-10% | Evaluate in 5 minutes |
| Error rate | < 5% | Monitor closely |
| P95 latency | > 2x baseline | Immediate rollback |
| P95 latency | 1.5-2x baseline | Evaluate in 10 minutes |
| Container restarts | > 5 in 10 min | Immediate rollback |
| Auth failures | > 5% | Immediate rollback |
| User complaints | > 20 in 1 hour | Evaluate for rollback |

---

## Communication Plan

### Rollback Announcement Template

\\\
Subject: [URGENT] Production Rollback - Hybrid Migration

Team,

We are executing a rollback of the hybrid WSGI+ASGI deployment due to:
[REASON]

Timeline:
- Rollback started: [TIME]
- Expected completion: [TIME + 5 minutes]
- Status updates: Every 5 minutes

Impact:
- [DESCRIBE USER IMPACT]

Actions:
- [WHO] is executing rollback
- [WHO] is monitoring metrics
- [WHO] is handling user communications

Will update when rollback is complete.

[YOUR NAME]
\\\

---

## Rollback Responsibility Matrix

| Role | Responsibility |
|------|----------------|
| Tech Lead | Make rollback decision |
| DevOps Engineer | Execute rollback procedure |
| Backend Engineer | Verify application functionality |
| QA Engineer | Run smoke tests |
| Product Manager | Communicate with stakeholders |
| SRE | Monitor metrics during rollback |

---

## Testing the Rollback Plan

**Schedule:** Test rollback procedure in staging every 2 weeks

\\\ash
# Staging rollback drill
./scripts/deploy-hybrid.sh staging
sleep 60
./scripts/rollback-config.sh staging
./scripts/verify-rollback.sh
\\\

**Success Criteria:**
- Rollback completes in < 5 minutes
- All services return to healthy state
- No data loss
- Team confident in executing procedure

---

## Rollback Lessons Learned (To Be Updated Post-Migration)

**Date:** [TBD]  
**Issue:** [TBD]  
**Rollback Executed:** [Yes/No]  
**Time to Rollback:** [X minutes]  
**What Worked:**  
**What Didn't Work:**  
**Changes Made to Procedure:**

---

**Document Status:** ✅ COMPLETE  
**Reviewed By:** [Pending]  
**Last Drill:** [Never - schedule after deployment]

**Task 1.7 Status:** ✅ COMPLETE  
**Phase 1 Status:** ✅ ALL TASKS COMPLETE
