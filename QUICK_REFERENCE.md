# Load Balancing Quick Reference Card

## Deployment Commands

### Start Everything
```bash
bash deploy-loadbalanced.sh start
```

### Stop Everything
```bash
bash deploy-loadbalanced.sh stop
```

### Restart Services
```bash
bash deploy-loadbalanced.sh restart
```

### View Logs
```bash
# All services
bash deploy-loadbalanced.sh logs

# Specific container
docker-compose -f docker-compose.loadbalanced.yml logs -f web-1
docker-compose -f docker-compose.loadbalanced.yml logs -f nginx
docker-compose -f docker-compose.loadbalanced.yml logs -f redis
```

## Health Check Commands

```bash
# Basic health
curl http://localhost/health/

# Readiness (checks DB + Redis)
curl http://localhost/ready/

# Liveness
curl http://localhost/live/

# Detailed status
curl http://localhost/status/ | jq
```

## Monitoring Commands

### Container Status
```bash
docker-compose -f docker-compose.loadbalanced.yml ps
```

### Container Resource Usage
```bash
docker stats
```

### Check Load Distribution
```bash
# Watch which backend serves requests
watch -n 1 'curl -s http://localhost/health/ -I | grep X-Backend-Server'
```

### Redis Monitoring
```bash
# Redis info
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli INFO

# Monitor Redis commands
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli MONITOR

# Check sessions
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli KEYS "arena:*" | wc -l
```

## Scaling Commands

### Scale Up (Add 5 more containers)
```bash
# Edit docker-compose.loadbalanced.yml to add web-11 through web-15
# Add to nginx/load-balancer.conf upstream
# Restart
docker-compose -f docker-compose.loadbalanced.yml up -d --scale web=15
```

### Scale Down
```bash
# Stop specific containers
docker-compose -f docker-compose.loadbalanced.yml stop web-10
```

### Rolling Restart (Zero Downtime)
```bash
# Restart containers one by one
for i in {1..10}; do
    docker-compose -f docker-compose.loadbalanced.yml restart web-$i
    sleep 10  # Wait for health check
done
```

## Debugging Commands

### Test Backend Directly (Bypass Load Balancer)
```bash
curl http://localhost:8000/health/  # Won't work - containers are not exposed
docker-compose -f docker-compose.loadbalanced.yml exec web-1 curl http://localhost:8000/health/
```

### Check Nginx Configuration
```bash
# Test nginx config syntax
docker-compose -f docker-compose.loadbalanced.yml exec nginx nginx -t

# View full nginx config
docker-compose -f docker-compose.loadbalanced.yml exec nginx nginx -T
```

### Check Container Health
```bash
# Check health status
docker inspect arena-web-1 --format='{{.State.Health.Status}}'

# View health check logs
docker inspect arena-web-1 --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

### Enter Container Shell
```bash
# Django container
docker-compose -f docker-compose.loadbalanced.yml exec web-1 /bin/bash

# Nginx container
docker-compose -f docker-compose.loadbalanced.yml exec nginx /bin/sh

# Redis container
docker-compose -f docker-compose.loadbalanced.yml exec redis /bin/sh
```

### Check Django Application
```bash
# Run Django shell
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell

# Check migrations
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py showmigrations

# Create superuser
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py createsuperuser
```

## Load Testing

### Start Locust
```bash
cd backend/load_tests
locust -f locustfile.py --host=http://localhost
```

### Run Headless Load Test
```bash
# 100 users, 10/sec spawn rate, 5 minutes
locust -f locustfile.py --host=http://localhost \
    --users 100 --spawn-rate 10 --run-time 5m --headless

# 1000 users, ramp up test
locust -f locustfile.py --host=http://localhost \
    --users 1000 --spawn-rate 15 --run-time 10m --headless \
    --csv=results/load_test
```

## Troubleshooting Scenarios

### Scenario: Container Won't Start
```bash
# 1. Check logs
docker-compose -f docker-compose.loadbalanced.yml logs web-1

# 2. Check if Redis is running
docker-compose -f docker-compose.loadbalanced.yml ps redis

# 3. Check environment variables
docker-compose -f docker-compose.loadbalanced.yml exec web-1 env | grep DB_
```

### Scenario: 502 Bad Gateway
```bash
# 1. Check if any backend containers are running
docker-compose -f docker-compose.loadbalanced.yml ps | grep web

# 2. Check nginx can reach backends
docker-compose -f docker-compose.loadbalanced.yml exec nginx curl http://web-1:8000/health/

# 3. Check nginx error logs
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep error
```

### Scenario: High Response Times
```bash
# 1. Check container resources
docker stats

# 2. Check if containers are at connection limit
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep "limiting connections"

# 3. Check database connections
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell
>>> from django.db import connection
>>> print(connection.queries)

# 4. Check Redis memory
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli INFO memory
```

### Scenario: Session Loss
```bash
# 1. Check Redis is running
docker-compose -f docker-compose.loadbalanced.yml ps redis

# 2. Check session keys in Redis
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli KEYS "arena:session:*"

# 3. Test session from Django
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell
>>> from django.contrib.sessions.backends.cache import SessionStore
>>> s = SessionStore()
>>> s['test'] = 'value'
>>> s.save()
>>> print(s.session_key)
```

## Performance Optimization

### Identify Slow Endpoints
```bash
# View nginx access logs with response times
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep "request_time" | sort -t: -k4 -n

# Check Django query count
docker-compose -f docker-compose.loadbalanced.yml exec web-1 python manage.py shell
>>> from django.conf import settings
>>> settings.DEBUG = True  # Temporary!
>>> # Make request, check connection.queries
```

### Clear Redis Cache
```bash
# Clear all cache keys
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli FLUSHDB

# Clear specific pattern
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli --scan --pattern "arena:cache:*" | xargs docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli DEL
```

### Restart Specific Service
```bash
# Restart single container
docker-compose -f docker-compose.loadbalanced.yml restart web-1

# Restart all web containers
docker-compose -f docker-compose.loadbalanced.yml restart web-1 web-2 web-3 web-4 web-5 web-6 web-7 web-8 web-9 web-10

# Restart nginx only
docker-compose -f docker-compose.loadbalanced.yml restart nginx
```

## Backup and Recovery

### Backup Redis Data
```bash
# Trigger Redis save
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli BGSAVE

# Copy dump.rdb
docker cp arena-redis:/data/dump.rdb ./backup/redis-$(date +%Y%m%d).rdb
```

### View Nginx Config
```bash
# Load balancer config
docker-compose -f docker-compose.loadbalanced.yml exec nginx cat /etc/nginx/conf.d/load-balancer.conf

# Backend config (if copied)
docker-compose -f docker-compose.loadbalanced.yml exec nginx cat /etc/nginx/vhosts/backend.conf
```

## Metrics Collection

### Container Metrics
```bash
# JSON format
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# Export to CSV
docker stats --no-stream --format "{{.Container}},{{.CPUPerc}},{{.MemUsage}}" > metrics.csv
```

### Nginx Metrics
```bash
# Access log summary
docker-compose -f docker-compose.loadbalanced.yml exec nginx tail -1000 /var/log/nginx/access.log | awk '{print $9}' | sort | uniq -c | sort -rn

# Request count by status code
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep -oP 'status: \K\d+' | sort | uniq -c

# Average response time
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep -oP 'request_time: \K[\d\.]+' | awk '{sum+=$1; n++} END {print sum/n}'
```

## Emergency Procedures

### Immediate Scale Down (Performance Issues)
```bash
# Reduce Gunicorn workers
docker-compose -f docker-compose.loadbalanced.yml exec web-1 pkill -HUP gunicorn

# Stop half the containers
docker-compose -f docker-compose.loadbalanced.yml stop web-6 web-7 web-8 web-9 web-10
```

### Immediate Scale Up
```bash
# Start stopped containers
docker-compose -f docker-compose.loadbalanced.yml start web-6 web-7 web-8 web-9 web-10
```

### Emergency Rollback
```bash
# Stop load-balanced setup
docker-compose -f docker-compose.loadbalanced.yml down

# Start original single-container setup
docker-compose up -d
```

## Useful One-Liners

```bash
# Count total requests across all backends
docker-compose -f docker-compose.loadbalanced.yml logs --tail=10000 | grep "GET\|POST" | wc -l

# Check which container is serving most requests
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep -oP 'upstream: web-\d+' | sort | uniq -c | sort -rn

# Monitor real-time request distribution
watch -n 1 'docker-compose -f docker-compose.loadbalanced.yml logs --tail=50 nginx | grep -oP "upstream: web-\d+" | sort | uniq -c'

# Check current connection counts
docker-compose -f docker-compose.loadbalanced.yml exec redis redis-cli INFO clients | grep connected_clients

# Find slowest endpoints
docker-compose -f docker-compose.loadbalanced.yml logs nginx | grep -oP '"request":"\K[^"]+' | sort | uniq -c | sort -rn | head -20
```

## Configuration Files

| File | Purpose |
|------|---------|
| `docker-compose.loadbalanced.yml` | Main deployment config |
| `nginx/load-balancer.conf` | Upstream definitions |
| `nginx/backend-loadbalanced.conf.tpl` | Routing rules |
| `backend/arena_backend/settings.py` | Django Redis config |
| `backend/arena_backend/health.py` | Health check logic |
| `deploy-loadbalanced.sh` | Deployment script |

## Important Endpoints

| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `/health/` | Basic health check | None |
| `/ready/` | Readiness probe (DB+Redis) | None |
| `/live/` | Liveness probe | None |
| `/status/` | Detailed system info | None |
| `/messages/stream/` | SSE streaming | 10 req/s |
| `/auth/*` | Authentication | 5 req/s |
| `/*` | General API | 100 req/s |

## Support Contacts

- **Documentation:** See `LOAD_BALANCING_GUIDE.md`
- **Architecture Diagram:** See guide Phase 1
- **Load Testing:** `backend/load_tests/locustfile.py`
- **Troubleshooting:** See guide Troubleshooting section

---

**Quick Checklist:**
- [ ] All 10 web containers running and healthy
- [ ] Redis running and accepting connections
- [ ] Nginx routing to all backends
- [ ] Health checks passing
- [ ] Load tests show even distribution
- [ ] Response times < 500ms (P95)
- [ ] Error rate < 1%
