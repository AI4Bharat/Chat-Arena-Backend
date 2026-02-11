# Resource Planning for Hybrid Deployment

## Development Environment

**Single Machine:** Windows 11 laptop/desktop

| Component | CPU | Memory | Notes |
|-----------|-----|--------|-------|
| Django WSGI | Shared | ~500MB | runserver or Uvicorn |
| Django ASGI | Shared | ~500MB | Uvicorn (when testing) |
| PostgreSQL | Shared | ~200MB | Local install |
| Redis | Shared | ~50MB | Docker or local |
| **Total** | ~2 cores | ~1.5GB | Can run on dev machine |

---

## Staging Environment

**Single Server:** 4 cores, 8GB RAM

| Component | CPU | Memory | Count | Total RAM |
|-----------|-----|--------|-------|-----------|
| Nginx | 0.5 | 256MB | 1 | 256MB |
| WSGI | 1 | 1GB | 2 | 2GB |
| ASGI | 1 | 1.5GB | 1 | 1.5GB |
| PostgreSQL | 1 | 2GB | 1 | 2GB |
| Redis | 0.5 | 512MB | 1 | 512MB |
| **Total** | 4 | - | - | **6.3GB** |

**Headroom:** 1.7GB for OS and monitoring

---

## Production Environment

**Recommended:** Multi-node or single powerful server

### Option 1: Single Server (Small Scale)
**Server:** 8 cores, 16GB RAM

| Component | CPU | Memory | Count | Total RAM |
|-----------|-----|--------|-------|-----------|
| Nginx | 1 | 512MB | 1 | 512MB |
| WSGI | 2 | 1.5GB | 2 | 3GB |
| ASGI | 2 | 2GB | 2 | 4GB |
| PostgreSQL | 2 | 4GB | 1 | 4GB |
| Redis | 1 | 2GB | 1 | 2GB |
| **Total** | 8 | - | - | **13.5GB** |

**Headroom:** 2.5GB for monitoring, logs

---

### Option 2: Distributed (Medium Scale)

**3 Servers:** App Server (8 cores, 16GB) + DB Server (4 cores, 8GB) + Cache Server (2 cores, 4GB)

**App Server:**
- Nginx: 1 core, 512MB
- WSGI: 2×2 cores, 3GB total
- ASGI: 2×2 cores, 4GB total

**DB Server:**
- PostgreSQL: 4 cores, 8GB (dedicated)

**Cache Server:**
- Redis: 2 cores, 4GB (dedicated)

---

## Scaling Guidelines

### When to Scale WSGI
- CPU > 70% sustained
- Response time P95 > 500ms
- Request queue depth > 50

**Action:** Add 1 WSGI container

### When to Scale ASGI
- Active connections > 150 per container
- WebSocket latency > 2s
- Memory > 85%

**Action:** Add 1 ASGI container

---

## Cost Estimates (Cloud)

**AWS/GCP/Azure:**

| Environment | Instance Type | Monthly Cost |
|-------------|---------------|--------------|
| Dev | t3.medium (2 cores, 4GB) | \ |
| Staging | t3.large (2 cores, 8GB) | \ |
| Production | t3.xlarge (4 cores, 16GB) | \ |

**Add-ons:**
- RDS PostgreSQL: \-200/month
- ElastiCache Redis: \-100/month

**Total Production:** ~\-400/month

---

**Status:** Reference for deployment planning
