# Hybrid Architecture - Visual Diagrams

## Request Flow Diagram

### WSGI Request Flow (CRUD Operations)
\\\
User → Nginx → WSGI Container → PostgreSQL
                    ↓
                  Redis (cache/session)
\\\

### ASGI Request Flow (Streaming)
\\\
User → Nginx → ASGI Container → External API (OpenAI/etc)
                    ↓               ↓
                  Redis         Stream response
                    ↓               ↓
              Channels Layer ← Response
                    ↓
              WebSocket ← → User
\\\

---

## Container Layout

\\\
┌─────────────────────────────────────────────────────────────┐
│                      Docker Host                             │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │ nginx:80/443   │  │  postgres:5432 │  │ redis:6379   │ │
│  └───────┬────────┘  └────────┬───────┘  └──────┬───────┘ │
│          │                    │                   │         │
│  ┌───────┴────────┐          │                   │         │
│  │                │           │                   │         │
│  v                v           v                   v         │
│  ┌──────────┐  ┌──────────┐                               │
│  │ WSGI-1   │  │ ASGI-1   │                               │
│  │ :8000    │  │ :8001    │                               │
│  ├──────────┤  ├──────────┤                               │
│  │ Gunicorn │  │ Uvicorn  │                               │
│  │ 4 workers│  │ 2 workers│                               │
│  └──────────┘  └──────────┘                               │
│                                                             │
│  ┌──────────┐  ┌──────────┐                               │
│  │ WSGI-2   │  │ ASGI-2   │                               │
│  │ :8000    │  │ :8001    │                               │
│  └──────────┘  └──────────┘                               │
└─────────────────────────────────────────────────────────────┘
\\\

---

## Resource Allocation

\\\
Total System Resources: 16 CPU cores, 32GB RAM

├── Nginx: 1 core, 512MB
├── PostgreSQL: 4 cores, 8GB
├── Redis: 1 core, 2GB
├── WSGI Pool (2 containers):
│   ├── Container 1: 2 cores, 1.5GB
│   └── Container 2: 2 cores, 1.5GB
└── ASGI Pool (2 containers):
    ├── Container 1: 2 cores, 2GB
    └── Container 2: 2 cores, 2GB

Headroom: 2 cores, 13.5GB (monitoring, logs, etc.)
\\\

---

**Status:** Visual reference diagrams
