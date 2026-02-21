# Dependency Comparison: Windows vs Production

## Development (Windows 11)
**File:** \equirements_windows.txt\
**Total Packages:** 189

### Excluded Packages
| Package | Reason | Impact |
|---------|--------|--------|
| gunicorn | Unix-only WSGI server | Use Uvicorn for local dev |
| uvloop | Linux-only event loop | Standard asyncio (slightly slower) |
| PyGObject | Linux GTK bindings | Not needed for backend |

---

## Production (Linux Containers)
**File:** \deploy/requirements.txt\
**Total Packages:** 192

### Additional Packages
| Package | Purpose | Required For |
|---------|---------|--------------|
| gunicorn | Production WSGI server | WSGI containers |
| uvloop | High-performance event loop | ASGI containers (optional) |
| PyGObject | System integration | May not be needed (audit) |

---

## Hybrid Architecture Dependencies

### WSGI Containers
\\\	xt
Django==5.2.6
djangorestframework==3.16.1
gunicorn==21.2.0  # Linux only
psycopg2-binary==2.9.10
redis==5.1.2
\\\

### ASGI Containers
\\\	xt
Django==5.2.6
channels==4.3.1
daphne==4.2.1
uvicorn==0.37.0
uvloop==0.21.0  # Linux only, optional
channels-redis==4.2.1
httpx==0.28.1
aiohttp==3.12.15
\\\

### Shared (Both)
\\\	xt
# All AI SDKs
openai==2.8.1
anthropic==0.76.0
litellm==1.80.7
elevenlabs==2.31.0
cartesia==2.0.17

# Database & Cache
psycopg2-binary==2.9.10
redis==5.1.2

# Auth & Utilities
djangorestframework-simplejwt==5.2.2
firebase-admin==7.1.0
\\\

---

## Compatibility Status

✅ **All dependencies compatible with hybrid architecture**

No changes needed to existing requirements files.

---

**Updated:** Feb 5, 2026
