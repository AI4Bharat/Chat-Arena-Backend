# Performance Optimization Guide
## Fixing SIGKILL Issues on 16 vCPU / 64 GB Machine

---

## Executive Summary

Your containers are being killed due to **memory overcommitment** and **CPU contention**. The original configuration requests more resources than available, causing the Linux OOM killer to terminate processes.

---

## Root Cause Analysis

### Problem 1: Memory Overcommitment (SIGKILL Primary Cause)

| Metric | Original | Problem |
|--------|----------|---------|
| Web containers | 10 | Too many |
| Workers per container | 12 | **Way too many** |
| Threads per worker | 6 | Too high |
| Total threads/container | 72 | Extreme memory usage |
| Memory limit | 3072MB | **Insufficient** |
| Actual memory needed | ~4000-5000MB | **Exceeds limit → OOM** |

**Why SIGKILL happens:**
```
Container Memory Limit: 3072MB
Actual Usage Calculation:
  - Base Django app: ~200MB
  - 12 gthread workers × 300MB each = 3600MB
  - Overhead (GC, buffers): ~200MB
  - Total: ~4000MB

4000MB > 3072MB → OOM Killer → SIGKILL
```

### Problem 2: CPU Overcommitment

| Resource | Original | Available | Status |
|----------|----------|-----------|--------|
| Web containers | 10 × 2 CPU = 20 | 16 vCPU | **OVERCOMMIT** |
| Redis | 2 CPU | - | - |
| **Total** | **22+ CPU** | **16 CPU** | **137% overcommit** |

### Problem 3: Health Check Timeout Mismatch

| Component | Timeout | Issue |
|-----------|---------|-------|
| Gunicorn request | 900s | Very long |
| Health check | 10s | **Too short** |
| Container restart | After 3 failures | SIGKILL |

Workers processing AI requests can't respond to health checks → marked unhealthy → SIGKILL.

---

## Optimized Configuration

### New Resource Allocation

| Component | Containers | CPU/Container | Memory/Container | Total CPU | Total Memory |
|-----------|------------|---------------|------------------|-----------|--------------|
| Web | 6 | 2.5 (limit) | 5GB | 15 | 30GB |
| Redis | 1 | 2 | 10GB | 2 | 10GB |
| Nginx | 1 | 1 | 1GB | 1 | 1GB |
| Buffer | - | - | - | -2 (reserve) | 23GB |
| **Total** | **8** | **16 (reserved)** | **~41GB** | ✓ | ✓ |

### Gunicorn Configuration Changes

| Setting | Original | Optimized | Reason |
|---------|----------|-----------|--------|
| `--workers` | 12 | 4 | (2 × CPU) + 1 formula |
| `--threads` | 6 | 4 | Balanced for I/O-bound |
| `--timeout` | 900 | 300 | More reasonable |
| `--graceful-timeout` | 120 | 60 | Faster recycling |
| `--max-requests` | None | 1000 | **Prevent memory leaks** |
| `--max-requests-jitter` | None | 100 | Stagger restarts |
| `--worker-tmp-dir` | Default | /dev/shm | **Faster heartbeats** |
| `--keep-alive` | Default | 75 | Match nginx |

### Concurrency Comparison

| Metric | Original | Optimized |
|--------|----------|-----------|
| Containers | 10 | 6 |
| Workers/container | 12 | 4 |
| Threads/worker | 6 | 4 |
| **Total concurrent handlers** | **720** | **96** |
| Memory/container | ~4GB actual | ~3GB actual |
| Memory limit | 3GB | 5GB |
| **Headroom** | **-1GB (OOM!)** | **+2GB (safe)** |

---

## Key Changes Made

### 1. docker-compose.loadbalanced.optimized.yml

```yaml
# BEFORE
command: gunicorn --workers 12 --threads 6 --timeout 900 ...
memory: 3072M
containers: 10

# AFTER
command: gunicorn --workers 4 --threads 4 --timeout 300 --max-requests 1000 ...
memory: 5120M
containers: 6
```

### 2. Health Check Improvements

```yaml
# BEFORE - Too aggressive for busy workers
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
  timeout: 10s
  retries: 3

# AFTER - Tolerant of busy workers
healthcheck:
  test: ["CMD", "curl", "-f", "--max-time", "25", "http://localhost:8000/health/"]
  timeout: 30s
  retries: 3
  start_period: 60s
```

### 3. Memory Leak Prevention

```yaml
# Added to gunicorn command
--max-requests 1000        # Recycle workers after 1000 requests
--max-requests-jitter 100  # Stagger recycling
--worker-tmp-dir /dev/shm  # RAM-based heartbeat files
```

### 4. Python Memory Optimization

```yaml
environment:
  - PYTHONMALLOC=malloc           # Use system malloc
  - MALLOC_TRIM_THRESHOLD_=65536  # Return memory to OS sooner
```

---

## Deployment Instructions

### Step 1: Backup Current Configuration

```bash
cp docker-compose.loadbalanced.yml docker-compose.loadbalanced.backup.yml
```

### Step 2: Test New Configuration

```bash
# Use the optimized configuration
docker-compose -f docker-compose.loadbalanced.optimized.yml config --quiet

# If no errors, proceed to deploy
```

### Step 3: Rolling Deployment

```bash
# Stop current deployment gracefully
docker-compose -f docker-compose.loadbalanced.yml down --timeout 120

# Start with optimized configuration
docker-compose -f docker-compose.loadbalanced.optimized.yml up -d

# Monitor startup
docker-compose -f docker-compose.loadbalanced.optimized.yml logs -f
```

### Step 4: Verify Health

```bash
# Check all containers are healthy
docker-compose -f docker-compose.loadbalanced.optimized.yml ps

# Check resource usage
docker stats --no-stream

# Test health endpoints
for i in 1 2 3 4 5 6; do
  curl -s http://localhost:800$i/health/ && echo " - web-$i OK"
done
```

---

## Monitoring Commands

### Check for OOM Events

```bash
# View kernel OOM events
dmesg | grep -i "killed process"

# Check container restarts
docker inspect --format='{{.RestartCount}}' arena-web-1

# View container events
docker events --filter 'event=oom' --filter 'event=kill'
```

### Monitor Resource Usage

```bash
# Real-time container stats
docker stats

# Detailed memory info
docker exec arena-web-1 cat /sys/fs/cgroup/memory/memory.usage_in_bytes

# Check gunicorn workers
docker exec arena-web-1 ps aux | grep gunicorn
```

### Check Gunicorn Worker Health

```bash
# Count active workers
docker exec arena-web-1 pgrep -c gunicorn

# Check worker memory
docker exec arena-web-1 ps -o pid,rss,comm | grep gunicorn
```

---

## Scaling Guidelines

### When to Scale Up (Add Containers)

| Symptom | Action |
|---------|--------|
| Response time > 2s consistently | Add 1-2 containers |
| CPU usage > 80% across all containers | Add containers |
| Queue depth growing | Add containers or workers |

### When to Scale Down

| Symptom | Action |
|---------|--------|
| CPU usage < 30% consistently | Remove 1-2 containers |
| Memory usage < 50% consistently | Reduce memory limits |

### Scaling Formula

```
Containers = ceil(Expected_RPS / (Workers × Threads × Requests_Per_Second_Per_Thread))

For AI workloads (slow responses):
- Requests_Per_Second_Per_Thread ≈ 0.2-0.5
- 6 containers × 4 workers × 4 threads × 0.3 = ~29 RPS sustained

For fast API calls:
- Requests_Per_Second_Per_Thread ≈ 10-50
- 6 containers × 4 workers × 4 threads × 20 = ~1920 RPS sustained
```

---

## Troubleshooting

### Still Getting SIGKILL?

1. **Check actual memory usage:**
   ```bash
   docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"
   ```

2. **If memory > 80% of limit:**
   - Reduce workers: `--workers 3`
   - Or increase limit: `memory: 6144M`

3. **Check for memory leaks:**
   ```bash
   # Watch memory over time
   watch -n 5 'docker stats --no-stream | grep web'
   ```

### Workers Not Responding to Health Checks?

1. **Increase health check timeout:**
   ```yaml
   healthcheck:
     timeout: 60s
   ```

2. **Add dedicated health check worker** (advanced):
   ```python
   # In Django, make health check non-blocking
   @api_view(['GET'])
   def health_check(request):
       return Response({'status': 'ok'})  # Don't do DB checks here
   ```

### High Latency During Deployment?

Use rolling updates:
```bash
# Update one container at a time
for i in 1 2 3 4 5 6; do
  docker-compose -f docker-compose.loadbalanced.optimized.yml up -d --no-deps web-$i
  sleep 30  # Wait for container to be healthy
done
```

---

## Quick Reference Card

### Optimal Settings for 16 vCPU / 64 GB

| Setting | Value |
|---------|-------|
| Web containers | 6 |
| Workers per container | 4 |
| Threads per worker | 4 |
| Memory limit | 5GB |
| CPU limit | 2.5 |
| Health check timeout | 30s |
| Gunicorn timeout | 300s |
| Max requests | 1000 |

### Key Gunicorn Command

```bash
gunicorn arena_backend.wsgi \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --worker-class gthread \
  --threads 4 \
  --timeout 300 \
  --graceful-timeout 60 \
  --keep-alive 75 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --worker-tmp-dir /dev/shm
```

### Files to Use

| Purpose | File |
|---------|------|
| Docker Compose | `docker-compose.loadbalanced.optimized.yml` |
| Nginx Load Balancer | `nginx/load-balancer-optimized.conf` |

---

## Summary of Changes

| Category | Change | Impact |
|----------|--------|--------|
| Containers | 10 → 6 | Less resource contention |
| Workers | 12 → 4 | **Prevents OOM** |
| Threads | 6 → 4 | Balanced concurrency |
| Memory | 3GB → 5GB | **Headroom for spikes** |
| Health timeout | 10s → 30s | **Prevents false failures** |
| Max requests | None → 1000 | **Prevents memory leaks** |
| Worker tmp | disk → /dev/shm | Faster heartbeats |

**Expected Result:** No more SIGKILL, stable operation under load.

---

*Last Updated: January 2026*
