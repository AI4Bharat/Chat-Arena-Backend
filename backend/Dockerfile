# Multi-stage Dockerfile for Chat-Arena-Backend
# Supports both WSGI and ASGI deployments

# ============================================================================
# STAGE 1: BASE IMAGE
# ============================================================================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 arena && \
    mkdir -p /app && \
    chown -R arena:arena /app

WORKDIR /app

# ============================================================================
# STAGE 2: DEPENDENCIES
# ============================================================================
FROM base as dependencies

# Copy requirements
COPY --chown=arena:arena requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install gunicorn uvicorn[standard] uvloop httptools

# ============================================================================
# STAGE 3: APPLICATION
# ============================================================================
FROM dependencies as application

# Switch to app user
USER arena

# Copy application code
COPY --chown=arena:arena ./backend /app

# Collect static files (run at build time)
RUN python manage.py collectstatic --noinput --clear || true

# Create necessary directories
RUN mkdir -p /app/media /app/staticfiles /app/logs

# Expose ports
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || curl -f http://localhost:8001/health/ || exit 1

# Default command (can be overridden in docker-compose)
CMD ["gunicorn", "arena_backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
