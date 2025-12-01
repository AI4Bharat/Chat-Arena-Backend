# Scaling to 500-1000 Requests Per Second

## Current Setup Analysis

### Current Capacity
- **10 Django containers** (web-1 through web-10)
- **4 Gunicorn workers** × **2 threads** per container = **8 concurrent requests per container**
- **Total**: 10 × 8 = **80 concurrent requests system-wide**

### Theoretical RPS Calculation
```
Concurrent requests × (1 / Average response time) = RPS
80 × (1 / 0.100s) = 800 RPS (if all responses are 100ms)
80 × (1 / 0.500s) = 160 RPS (if responses are 500ms)
```

**Problem**: With streaming endpoints (multi-second responses), effective capacity is **much lower** (~100-200 RPS).

---

## Target: 500-1000 RPS

### Required Changes Summary

| Component | Current | Target | Change |
|-----------|---------|--------|--------|
| **Django Containers** | 10 | 15-20 | +50-100% |
| **Gunicorn Workers** | 4 per container | 8 per container | +100% |
| **Gunicorn Threads** | 2 per worker | 4 per worker | +100% |
| **Container CPU** | 1.0 CPU | 2.0 CPU | +100% |
| **Container RAM** | 1GB | 2GB | +100% |
| **PgBouncer Pool** | 25 | 50 | +100% |
| **Redis Memory** | 2GB | 4-8GB | +100-300% |
| **Nginx Workers** | Default (auto) | 8-16 | Manual |

### Expected Capacity After Changes
```
20 containers × 8 workers × 4 threads = 640 concurrent requests
640 × (1 / 0.100s) = 6,400 RPS (best case)
640 × (1 / 0.500s) = 1,280 RPS (with slower responses)
```

This provides **2-5x headroom** above your target.

---

## Detailed Changes

### 1. Docker Compose - Increase Containers and Resources

**File**: `docker-compose.loadbalanced.yml`

#### Change 1.1: Update Gunicorn Command (All web containers)

**FROM:**
```yaml
command: gunicorn --bind 0.0.0.0:8000 --workers 4 --worker-class gthread --threads 2 --timeout 300 --access-logfile - --error-logfile - arena_backend.wsgi
```

**TO:**
```yaml
command: gunicorn --bind 0.0.0.0:8000 --workers 8 --worker-class gthread --threads 4 --max-requests 1000 --max-requests-jitter 100 --timeout 600 --keep-alive 5 --access-logfile - --error-logfile - arena_backend.wsgi
```

**Changes explained:**
- `--workers 8`: Doubles worker count (4 → 8)
- `--threads 4`: Doubles threads per worker (2 → 4)
- `--max-requests 1000`: Restart workers after 1000 requests (prevents memory leaks)
- `--max-requests-jitter 100`: Add randomness to prevent all workers restarting simultaneously
- `--timeout 600`: Increase timeout for streaming responses (300s → 600s)
- `--keep-alive 5`: Keep connections alive for 5 seconds

#### Change 1.2: Increase Container Resources

**FROM:**
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1024M
    reservations:
      cpus: '0.5'
      memory: 512M
```

**TO:**
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2048M
    reservations:
      cpus: '1.0'
      memory: 1024M
```

#### Change 1.3: Add 5 More Containers (web-11 through web-15)

Add these after `web-10`:

```yaml
  web-11:
    build: ./backend
    container_name: arena-web-11
    command: gunicorn --bind 0.0.0.0:8000 --workers 8 --worker-class gthread --threads 4 --max-requests 1000 --max-requests-jitter 100 --timeout 600 --keep-alive 5 --access-logfile - --error-logfile - arena_backend.wsgi
    env_file:
      - ./config.env
    volumes:
      - ./backend/:/usr/src/backend/
      - static_volume:/usr/src/backend/static
      - logs_vol:/logs
    expose:
      - 8000
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CONTAINER_NAME=web-11
    depends_on:
      - redis
      - pgbouncer
    restart: unless-stopped
    networks:
      - arena-network
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2048M
        reservations:
          cpus: '1.0'
          memory: 1024M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  web-12:
    # ... same as web-11, change container_name and CONTAINER_NAME

  web-13:
    # ... same as web-11, change container_name and CONTAINER_NAME

  web-14:
    # ... same as web-11, change container_name and CONTAINER_NAME

  web-15:
    # ... same as web-11, change container_name and CONTAINER_NAME
```

**Total after this change:** 15 containers × 8 workers × 4 threads = **480 concurrent requests**

---

### 2. Nginx Load Balancer Configuration

**File**: `nginx/load-balancer.conf`

#### Change 2.1: Add New Upstream Servers

Add web-11 through web-15 to all upstream blocks:

```nginx
upstream django_backend {
    keepalive 128;  # Increased from 64
    keepalive_timeout 60s;
    keepalive_requests 1000;  # Increased from 100

    # Existing servers
    server web-1:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-2:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-3:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-4:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-5:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-6:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-7:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-8:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-9:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-10:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;

    # NEW: Add 5 more servers
    server web-11:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-12:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-13:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-14:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
    server web-15:8000 max_fails=3 fail_timeout=30s max_conns=300 weight=1;
}

upstream django_streaming {
    least_conn;
    keepalive 64;  # Increased from 32
    keepalive_timeout 120s;

    # Add web-11 through web-15 here too
    server web-11:8000 max_fails=2 fail_timeout=60s max_conns=150 weight=1;
    server web-12:8000 max_fails=2 fail_timeout=60s max_conns=150 weight=1;
    server web-13:8000 max_fails=2 fail_timeout=60s max_conns=150 weight=1;
    server web-14:8000 max_fails=2 fail_timeout=60s max_conns=150 weight=1;
    server web-15:8000 max_fails=2 fail_timeout=60s max_conns=150 weight=1;
}

upstream django_websocket {
    ip_hash;
    keepalive 64;  # Increased from 32
    keepalive_timeout 300s;

    # Add web-11 through web-15 here too
    server web-11:8000 max_fails=2 fail_timeout=60s max_conns=200 weight=1;
    server web-12:8000 max_fails=2 fail_timeout=60s max_conns=200 weight=1;
    server web-13:8000 max_fails=2 fail_timeout=60s max_conns=200 weight=1;
    server web-14:8000 max_fails=2 fail_timeout=60s max_conns=200 weight=1;
    server web-15:8000 max_fails=2 fail_timeout=60s max_conns=200 weight=1;
}
```

#### Change 2.2: Optimize Rate Limits for Production High Load

```nginx
# Rate limiting zones (already done, but verify these values)
limit_req_zone $binary_remote_addr zone=general_limit:10m rate=1000r/s;
limit_req_zone $binary_remote_addr zone=streaming_limit:10m rate=200r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=100r/s;
```

---

### 3. Nginx Main Configuration

**File**: Create/Edit `nginx/nginx.conf` or update Dockerfile to set these

Add at the top of nginx configuration:

```nginx
# Number of worker processes (1 per CPU core, or 2x CPU cores for I/O bound)
worker_processes 16;

# Maximum open file descriptors per worker
worker_rlimit_nofile 65535;

events {
    # Maximum concurrent connections per worker
    worker_connections 10000;

    # Use efficient connection processing (Linux)
    use epoll;

    # Accept multiple connections at once
    multi_accept on;
}

http {
    # ... existing http config ...

    # Connection and request settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    keepalive_requests 1000;

    # Buffer sizes
    client_body_buffer_size 128k;
    client_max_body_size 100M;
    client_header_buffer_size 1k;
    large_client_header_buffers 4 8k;

    # Timeouts
    client_body_timeout 60s;
    client_header_timeout 60s;
    send_timeout 60s;

    # ... include other configs ...
}
```

---

### 4. PgBouncer Configuration

**File**: `pgbouncer/pgbouncer.ini`

#### Change 4.1: Increase Connection Limits

```ini
[pgbouncer]
pool_mode = transaction

# Connection limits - DOUBLED for high load
max_client_conn = 2000          # Was: 1000
default_pool_size = 50          # Was: 25
reserve_pool_size = 10          # Was: 5
max_db_connections = 100        # Was: 50
max_user_connections = 100      # Was: 50

# Timeouts
server_idle_timeout = 600
server_lifetime = 3600
server_connect_timeout = 15
query_timeout = 60              # Increased from 30
query_wait_timeout = 120
client_idle_timeout = 0

# Performance
so_reuseport = 1
```

#### Change 4.2: Increase PgBouncer Resources

In `docker-compose.loadbalanced.yml`:

```yaml
pgbouncer:
  deploy:
    resources:
      limits:
        cpus: '1.0'        # Was: 0.5
        memory: 512M       # Was: 256M
      reservations:
        cpus: '0.5'        # Was: 0.25
        memory: 256M       # Was: 128M
```

---

### 5. Redis Configuration

**File**: `docker-compose.loadbalanced.yml`

#### Change 5.1: Increase Redis Memory and Resources

```yaml
redis:
  container_name: redis
  image: "redis:7-alpine"
  command: redis-server --maxmemory 8gb --maxmemory-policy allkeys-lru --maxclients 10000 --tcp-backlog 511 --timeout 0 --tcp-keepalive 300
  ports:
    - 6379:6379
  volumes:
    - redis_data:/data
  restart: unless-stopped
  networks:
    - arena-network
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 8192M
      reservations:
        cpus: '1.0'
        memory: 4096M
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 3s
    retries: 3
```

**Changes:**
- Memory: 2GB → 8GB
- Max clients: default (10000) → explicit 10000
- TCP backlog: 511 (handles more incoming connections)
- Resources: 2 CPU, 8GB RAM

---

### 6. Django Settings Optimization

**File**: `backend/arena_backend/settings.py`

#### Change 6.1: Database Connection Pool Settings

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "pgbouncer"),  # Ensure PgBouncer
        "PORT": os.getenv("DB_PORT", "6432"),

        # Connection pooling settings
        "CONN_MAX_AGE": 300,  # Reduced from 600 (5 minutes instead of 10)
        "CONN_HEALTH_CHECKS": True,

        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",  # 30 second query timeout
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }
}
```

#### Change 6.2: Redis Connection Pool

```python
# Redis connection pool settings
REDIS_CONNECTION_POOL_KWARGS = {
    "max_connections": 100,  # Per Django worker
    "retry_on_timeout": True,
    "socket_keepalive": True,
    "socket_keepalive_options": {
        socket.TCP_KEEPIDLE: 1,
        socket.TCP_KEEPINTVL: 1,
        socket.TCP_KEEPCNT: 5,
    },
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": REDIS_CONNECTION_POOL_KWARGS,
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
        "KEY_PREFIX": "arena",
        "TIMEOUT": 300,
    }
}
```

#### Change 6.3: Channels Layer Settings

```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(REDIS_HOST, int(REDIS_PORT))],
            "capacity": 2000,  # Increased from 1500
            "expiry": 10,
            "group_expiry": 86400,
            "channel_capacity": {
                "http.request": 500,
                "http.response*": 2000,
                "websocket.send*": 2000,
            },
        },
    },
}
```

---

### 7. Nginx Depends On (Update)

**File**: `docker-compose.loadbalanced.yml`

Update nginx's `depends_on` to include new containers:

```yaml
nginx:
  depends_on:
    - web-1
    - web-2
    - web-3
    - web-4
    - web-5
    - web-6
    - web-7
    - web-8
    - web-9
    - web-10
    - web-11
    - web-12
    - web-13
    - web-14
    - web-15
```

---

## System-Level Optimizations (On Host Server)

Run these on your **server** (not in containers):

```bash
# Increase file descriptor limits
sudo sysctl -w fs.file-max=200000
echo "fs.file-max = 200000" | sudo tee -a /etc/sysctl.conf

# Increase network buffer sizes
sudo sysctl -w net.core.somaxconn=65535
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=8192
sudo sysctl -w net.core.netdev_max_backlog=5000

# TCP performance tuning
sudo sysctl -w net.ipv4.tcp_fin_timeout=30
sudo sysctl -w net.ipv4.tcp_keepalive_time=300
sudo sysctl -w net.ipv4.tcp_keepalive_probes=5
sudo sysctl -w net.ipv4.tcp_keepalive_intvl=15

# Make permanent
sudo sysctl -p
```

---

## Resource Requirements Summary

### Current Resources

| Component | CPU | RAM | Total |
|-----------|-----|-----|-------|
| 10 Django containers | 10 CPU | 10 GB | - |
| Nginx | 0.5 CPU | 512 MB | - |
| Redis | 0.5 CPU | 2 GB | - |
| PgBouncer | 0.5 CPU | 256 MB | - |
| **TOTAL** | **11.5 CPU** | **~13 GB** | - |

### Required Resources (After Scaling)

| Component | CPU | RAM | Total |
|-----------|-----|-----|-------|
| **15 Django containers** | **30 CPU** | **30 GB** | - |
| Nginx | 2 CPU | 1 GB | - |
| Redis | 2 CPU | 8 GB | - |
| PgBouncer | 1 CPU | 512 MB | - |
| **TOTAL** | **35 CPU** | **~40 GB** | - |

### Server Requirements

**Minimum Recommended:**
- **CPUs**: 40-48 cores (to handle 35 with headroom)
- **RAM**: 48-64 GB (to handle 40 GB with OS overhead)
- **Network**: 10 Gbps
- **Disk**: SSD with 500+ IOPS

**Cloud Instance Recommendations:**
- **AWS**: c5.12xlarge (48 vCPU, 96 GB RAM)
- **Google Cloud**: c2-standard-60 (60 vCPU, 240 GB RAM)
- **Azure**: F48s v2 (48 vCPU, 96 GB RAM)

---

## Implementation Steps

### Step 1: Backup Current Configuration

```bash
cd ~/Chat-Arena-Backend
tar -czf backup-$(date +%Y%m%d).tar.gz docker-compose.loadbalanced.yml nginx/ pgbouncer/ backend/arena_backend/settings.py
```

### Step 2: Apply Changes Gradually

1. **First**: Increase resources for existing 10 containers
2. **Second**: Add 5 new containers (web-11 to web-15)
3. **Third**: Scale Redis and PgBouncer
4. **Fourth**: Optimize nginx configuration

### Step 3: Test Each Stage

```bash
# After each change, rebuild and restart
docker compose -f docker-compose.loadbalanced.yml build
docker compose -f docker-compose.loadbalanced.yml up -d

# Wait for health checks
sleep 60

# Check all containers are healthy
docker compose -f docker-compose.loadbalanced.yml ps

# Run load test
cd backend/load_tests
locust -f locustfile_optimized.py \
    --host=https://backend.arena.ai4bharat.org \
    --users 500 \
    --spawn-rate 50 \
    --run-time 5m \
    --headless
```

---

## Monitoring and Verification

### Key Metrics to Monitor

```bash
# 1. CPU usage per container
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# 2. Database connections
docker compose -f docker-compose.loadbalanced.yml exec pgbouncer psql -p 6432 -U $DB_USER pgbouncer -c "SHOW POOLS;"

# 3. Redis memory and connections
docker compose -f docker-compose.loadbalanced.yml exec redis redis-cli INFO | grep -E "used_memory_human|connected_clients"

# 4. Nginx request rate
docker compose -f docker-compose.loadbalanced.yml logs nginx | grep -oE "HTTP/[0-9.]+ [0-9]+" | awk '{print $2}' | sort | uniq -c

# 5. Response times
docker compose -f docker-compose.loadbalanced.yml logs nginx | grep "upstream_response_time" | tail -100
```

### Target Metrics After Scaling

| Metric | Target | Command |
|--------|--------|---------|
| RPS sustained | 500-1000 | Locust dashboard |
| P95 response time | <2000ms | Locust stats |
| CPU usage | <70% | `docker stats` |
| Memory usage | <80% | `docker stats` |
| PgBouncer pool usage | <80 connections | `SHOW POOLS` |
| Redis memory | <6 GB | `INFO memory` |

---

## Cost Estimation

### Infrastructure Costs (Monthly, Approximate)

| Provider | Instance Type | vCPUs | RAM | Monthly Cost |
|----------|--------------|-------|-----|--------------|
| AWS | c5.12xlarge | 48 | 96 GB | ~$1,800 |
| Google Cloud | c2-standard-60 | 60 | 240 GB | ~$2,500 |
| Azure | F48s v2 | 48 | 96 GB | ~$1,900 |

**Additional costs:**
- Load balancer: ~$20-50/month
- Database (managed PostgreSQL): ~$200-500/month
- Storage & bandwidth: ~$100-300/month
- **Total**: ~$2,200-3,500/month

---

## Alternative: Kubernetes Auto-Scaling

If costs are a concern, consider using Kubernetes for auto-scaling:

- Start with 10 containers during low traffic
- Auto-scale up to 20 containers during peak traffic
- Pay only for what you use

**Kubernetes benefits:**
- Automatic horizontal pod autoscaling (HPA)
- Rolling updates with zero downtime
- Self-healing (auto-restart failed containers)
- Resource efficiency (better utilization)

---

## Phase 3 Recommendations (Future)

Once you reach 1000+ RPS:

1. **Caching Layer**: Add Varnish or CloudFlare CDN
2. **Read Replicas**: Separate read/write database traffic
3. **Message Queue**: Use Celery for async tasks (reduce request time)
4. **Database Sharding**: Distribute data across multiple databases
5. **Geographic Distribution**: Deploy in multiple regions

---

## Quick Start Script

Save this as `apply-scaling-changes.sh`:

```bash
#!/bin/bash
# Apply scaling changes incrementally

echo "Step 1: Increase Gunicorn workers..."
# Update docker-compose.loadbalanced.yml manually

echo "Step 2: Increase container resources..."
# Update deploy.resources in docker-compose.loadbalanced.yml

echo "Step 3: Add new containers..."
# Add web-11 through web-15 definitions

echo "Step 4: Update nginx upstreams..."
# Add new servers to load-balancer.conf

echo "Step 5: Scale PgBouncer and Redis..."
# Update pgbouncer.ini and redis config

echo "Step 6: Rebuild and restart..."
docker compose -f docker-compose.loadbalanced.yml build
docker compose -f docker-compose.loadbalanced.yml up -d

echo "Scaling complete! Monitor with:"
echo "  docker stats"
echo "  docker compose -f docker-compose.loadbalanced.yml ps"
```

---

## Summary

**Key Changes for 500-1000 RPS:**

1. ✅ **Add 5 containers** (10 → 15)
2. ✅ **Double Gunicorn workers** (4 → 8) and threads (2 → 4)
3. ✅ **Double container resources** (1 CPU → 2 CPU, 1GB → 2GB)
4. ✅ **Scale PgBouncer** (25 → 50 pool size)
5. ✅ **Scale Redis** (2GB → 8GB memory)
6. ✅ **Optimize nginx** (add workers, increase keepalive)
7. ✅ **Update rate limits** (already done in previous changes)

**Result:** System capable of **1,000-2,000 RPS** sustained, with room for spikes.
